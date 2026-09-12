from __future__ import annotations

from unittest.mock import patch

import pytest

from rehearsal.agents.runner import ModelSettings, bedrock_model, main


def configured():
    return {
        "AWS_PROFILE": "chosen-profile",
        "AWS_REGION": "us-east-1",
        "REHEARSAL_MODEL_ID": "chosen-model",
        "REHEARSAL_MODEL_BUDGET_USD": "0.1",
        "REHEARSAL_PRICE_INPUT": "1",
        "REHEARSAL_PRICE_OUTPUT": "2",
        "REHEARSAL_PRICE_CACHE_READ": "0",
        "REHEARSAL_PRICE_CACHE_WRITE": "1",
        "REHEARSAL_RATE_SOURCE": "fictional test prices",
    }


def test_model_preflight_missing_settings_has_no_provider_side_effect(capsys):
    with (
        patch("rehearsal.agents.runner.read_settings", side_effect=ValueError("Missing settings")),
        patch("rehearsal.agents.runner.bedrock_model") as factory,
        patch("sys.argv", ["runner"]),
    ):
        assert main() == 2
        factory.assert_not_called()
    assert "Missing settings" in capsys.readouterr().out


def test_valid_preflight_still_does_not_invoke_provider(capsys):
    settings = ModelSettings.from_values(configured())
    with (
        patch("rehearsal.agents.runner.read_settings", return_value=settings),
        patch("rehearsal.agents.runner.bedrock_model") as factory,
        patch("sys.argv", ["runner"]),
    ):
        assert main() == 0
        factory.assert_not_called()
    assert "No AWS client" in capsys.readouterr().out


@pytest.mark.parametrize(
    "key,value",
    [
        ("AWS_PROFILE", ""),
        ("REHEARSAL_MODEL_ID", ""),
        ("REHEARSAL_MODEL_BUDGET_USD", "NaN"),
        ("REHEARSAL_MODEL_BUDGET_USD", "0"),
        ("REHEARSAL_PRICE_INPUT", "-1"),
        ("REHEARSAL_PRICE_OUTPUT", "bad"),
        ("REHEARSAL_MAX_MODEL_CALLS", "0"),
    ],
)
def test_model_settings_reject_missing_or_invalid_values(key, value):
    values = configured() | {key: value}
    with pytest.raises(ValueError):
        ModelSettings.from_values(values)


def test_bedrock_factory_uses_only_explicit_profile_region_model_and_no_retry():
    settings = ModelSettings.from_values(configured())
    with patch("boto3.Session") as session, patch("strands.models.BedrockModel") as model:
        bedrock_model(settings)
        session.assert_called_once_with(profile_name="chosen-profile", region_name="us-east-1")
        arguments = model.call_args.kwargs
        assert arguments["model_id"] == "chosen-model"
        assert arguments["boto_session"] is session.return_value
        assert arguments["max_tokens"] == 1024
        assert arguments["boto_client_config"].retries == {"total_max_attempts": 1}
        assert not arguments["use_native_token_count"]
