# Optional local transaction and evaluation commands.
operating:
	$(DEV) uv run --offline --no-sync python -m rehearsal.operating.local

operating-sdk-smoke:
	$(DEV) uv run --offline --no-sync python scripts/dev/operating_sdk.py

operating-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.operating.local --smoke

policy-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.rehearse

.PHONY: review-smoke review-preflight
review-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.review_runner --offline-fixture

review-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.review_runner

.PHONY: b3-smoke b3-preflight
b3-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b3 --offline-fixture

b3-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b3

.PHONY: pilot-smoke
pilot-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.pilot

.PHONY: b2-smoke b2-preflight
b2-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b2 --offline-fixture

b2-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b2

.PHONY: frozen-evaluation-smoke frozen-evaluation-preflight
frozen-evaluation-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.frozen_run --offline-fixture

frozen-evaluation-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.frozen_run

.PHONY: evaluation-batch-smoke
evaluation-batch-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.batch --offline-fixture

agent-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.agents.runner

agent-run:
	$(DEV) uv run --offline --no-sync python -m rehearsal.agents.runner --execute

world-fixtures:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.fixtures

world-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.world.demo

commerce-contract:
	$(DEV) uv run --offline --no-sync python scripts/commerce/contract_spike.py

.PHONY: commerce-adapter-smoke
commerce-adapter-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/adapter_smoke.py

.PHONY: commerce-operating-smoke
commerce-operating-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/operating_smoke.py

.PHONY: commerce-transfer-smoke
commerce-transfer-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/transfer_smoke.py

.PHONY: commerce-model-smoke
commerce-model-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/model_smoke.py

.PHONY: commerce-model-session-preflight
commerce-model-session-preflight:
	$(DEV) uv run --offline --no-sync python scripts/commerce/model_session.py

.PHONY: commerce-notification-smoke
commerce-notification-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/notification_smoke.py

.PHONY: commerce-stock-smoke
commerce-stock-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/stock_smoke.py

.PHONY: commerce-supplier-smoke
commerce-supplier-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/supplier_smoke.py

.PHONY: commerce-observer-smoke
commerce-observer-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/observer_smoke.py

.PHONY: commerce-convergence-smoke
commerce-convergence-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/convergence_smoke.py

.PHONY: commerce-race-smoke
commerce-race-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/race_smoke.py

commerce-smoke:
	$(DEV) uv run --offline --no-sync python scripts/dev/local.py commerce-smoke



.PHONY: commerce-learning-smoke
commerce-learning-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/learning_smoke.py

.PHONY: external-batch-smoke
external-batch-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/external_batch_smoke.py

.PHONY: external-arms-smoke
external-arms-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/all_arms_smoke.py

.PHONY: external-conditions-smoke
external-conditions-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/conditions_smoke.py

.PHONY: external-events-smoke
external-events-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/events_smoke.py

.PHONY: commerce-delivery-smoke
commerce-delivery-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/delivery_smoke.py

.PHONY: external-response-smoke
external-response-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/response_smoke.py

.PHONY: external-notification-smoke
external-notification-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/notification_events_smoke.py

.PHONY: commerce-reaction-smoke
commerce-reaction-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_smoke.py

.PHONY: external-reaction-smoke
external-reaction-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_batch_smoke.py

.PHONY: commerce-latency-smoke
commerce-latency-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/latency_smoke.py
