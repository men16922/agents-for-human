#!/usr/bin/env python3
"""Generate bounded, cached Daniel narration with ElevenLabs character timestamps.

This explicitly invokes a paid external API. Failed/uncertain requests are not retried.
Reference: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
"""

import argparse
import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    directory = args.directory.resolve()
    if not directory.is_relative_to(root / ".local"):
        raise ValueError("Use an ignored local build directory")
    scenes = json.loads((directory / "storyboard.json").read_text())["scenes"]
    assert sum(len(s["narration"]) for s in scenes) <= 6000
    env = {}
    for line in (root / ".env").read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            env[key.strip()] = value.strip().strip('"').strip("'")
    voice = env["ELVENLAB_ACTOR"]
    assert voice == "onwK4e9ZLuTAKqWW03F9", "Expected the selected Daniel voice"
    os.umask(0o077)
    records = []
    for index, scene in enumerate(scenes):
        body = {
            "text": scene["narration"],
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.75,
                "style": 0,
                "use_speaker_boost": True,
                "speed": 0.97,
            },
        }
        request_hash = hashlib.sha256(
            json.dumps([voice, body], sort_keys=True).encode()
        ).hexdigest()
        audio = directory / f"daniel-{index}.mp3"
        metadata = directory / f"daniel-{index}.json"
        marker = directory / f"daniel-{index}.request-started"
        if metadata.exists():
            record = json.loads(metadata.read_text())
            assert record["request_sha256"] == request_hash
            assert hashlib.sha256(audio.read_bytes()).hexdigest() == record["sha256"]
        else:
            # Exclusive durable marker prevents duplicate billing after uncertain failures.
            with marker.open("x") as handle:
                handle.write(request_hash + "\n")
            request = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
                data=json.dumps(body).encode(),
                headers={
                    "xi-api-key": env["ELEVENLAB_API_KEY"],
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
                credits = response.headers.get("character-cost")
            content = base64.b64decode(payload["audio_base64"], validate=True)
            assert len(content) > 5000
            audio.write_bytes(content)
            record = {
                "text": body["text"],
                "audio": audio.name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "request_sha256": request_hash,
                "characters": len(body["text"]),
                "character_cost": int(credits) if credits is not None else None,
                "alignment": payload["alignment"],
            }
            metadata.write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        print(
            f"Narration {index + 1}/{len(scenes)} cached; {record['characters']} characters",
            flush=True,
        )
    (directory / "generation.json").write_text(
        json.dumps(
            {
                "voice": "Daniel",
                "voice_id": voice,
                "model": "eleven_multilingual_v2",
                "settings": body["voice_settings"],
                "scenes": records,
                "requests": len(records),
                "characters": sum(r["characters"] for r in records),
                "reported_credits": sum(r["character_cost"] for r in records)
                if all(r["character_cost"] is not None for r in records)
                else None,
                "automatic_retries": False,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
