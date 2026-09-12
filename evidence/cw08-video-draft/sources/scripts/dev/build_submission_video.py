#!/usr/bin/env python3
"""Offline English draft from actual capture and explicitly labelled retained evidence."""

import argparse
import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, log):
    with log.open("ab") as output:
        subprocess.run(args, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)


def probe(path):
    return json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
        )
    )


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    return (
        f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:"
        f"{milliseconds // 1000 % 60:02}.{milliseconds % 1000:03}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture, output = args.capture.resolve(), args.output.resolve()
    if any(shutil.which(name) is None for name in ("ffmpeg", "ffprobe", "say", "node")):
        raise RuntimeError("Installed local ffmpeg/ffprobe/say/node required; no auto-install")
    if not output.is_relative_to(ROOT / ".local"):
        raise ValueError("Build into a new ignored local directory")
    smoke = read(capture / "smoke.json")
    if not smoke["passed"] or not smoke["browser"]["passed"]:
        raise ValueError("A passed actual browser capture is required")
    video = capture / "browser/live-capture.webm"
    duration = float(probe(video)["format"]["duration"])
    if not 15 < duration < 55:
        raise ValueError("Keep the full capture at original speed inside the 55-second segment")
    output.mkdir(parents=True, exist_ok=False)
    external = ROOT / "evidence/cw07-reactive-comparison/artifact-manifest.json"
    comparative = read(external)
    review_path = ROOT / "evidence/cw04-b3-offline/review/report.json"
    review = read(review_path)
    transport_path = ROOT / "evidence/cw07-response-events/runs/loss-B1-r1/execution/report.json"
    transport = read(transport_path)
    for manifest in (
        external,
        ROOT / "evidence/cw04-b3-offline/manifest.json",
        ROOT / "evidence/cw07-response-events/artifact-manifest.json",
    ):
        for name, expected in read(manifest)["artifacts"].items():
            assert sha(manifest.parent / name) == expected
    assert review["promoted"] is False
    assert review["rounds"][0]["reexperiment"]["independent_verdict"]["status"] == "COMPLETE"
    timeout = transport["payment_transport_events"][0]
    assert timeout["error_type"] == "ReadTimeout"
    run_id = smoke["runtime"]["run_id"]
    measurements = comparative["measurements"]
    scenes = [
        dict(
            seconds=25,
            tag="The developer problem",
            title="A successful call is not a delivered order.",
            subtitle="Reproduce transaction failures before delegating purchasing tools.",
            facts=[
                ["Who", "Developers and QA"],
                ["What to inspect", "Payment ≠ receipt"],
                ["Completion authority", "Independent raw ledger"],
            ],
            note="Local POC · No measured developer time saving",
            source="Editorial introduction — product purpose, not a measured outcome",
            narration=(
                "A purchasing agent can report success before the goods arrive. Rehearsal "
                "gives developers and quality assurance teams a repeatable way to inspect "
                "those gaps before delegating transactions. This is a local proof of "
                "concept. We have not measured developer time savings."
            ),
        ),
        dict(
            seconds=30,
            tag="A concrete goal",
            title="Three tents. Six lights. Five hundred credits.",
            subtitle="An actual initial frame from the local browser capture.",
            facts=[
                ["Goal", "3 tents + 6 lights"],
                ["Budget", "500 synthetic credits"],
                ["Rule", "Delivery before deadline"],
            ],
            image=str(capture / "browser/initial-frame.png"),
            note="Still image from the recorded run; continuous footage follows.",
            source=run_id + " · Initial browser frame · Local Medusa",
            narration=(
                "Our example is an event: three tents and six lights, with a five hundred "
                "credit budget and a deadline. The credits are synthetic. This is an "
                "initial frame from the working local browser. Completion means delivered "
                "goods, not just an approved payment. The browser only reads "
                "observations. Opening the page cannot place an order."
            ),
        ),
        dict(
            seconds=50,
            tag="Retained practice and review artifacts",
            title="A policy revision stays a proposal.",
            subtitle=(
                "A separate deterministic SDK experiment; this is not new model-review footage."
            ),
            facts=[
                ["Reviewer", "Fresh Agent, no tools"],
                ["Candidate replay", "COMPLETE · 380 credits"],
                ["Automatic promotion", "False"],
            ],
            note=(
                "Same-snapshot reexperiment · Initial buying, review and candidate buying "
                "share limits"
            ),
            source="Retained source: evidence/cw04-b3-offline/review/report.json · candidate-1",
            narration=(
                "These are retained results from a separate deterministic SDK experiment. "
                "B three adds a fresh reviewer with no purchasing tools. A schema checked "
                "policy revision is linked to its input evidence and retried from the "
                "same snapshot. The candidate delivered the goal in this known "
                "experiment, but it was not automatically promoted. Initial buying, "
                "review, and candidate buying share call, token, tool, and estimated cost "
                "limits. B two uses one Agent and conversation without a separate "
                "reviewer. These fixtures verify the connections and accounting. They do "
                "not establish real model review effectiveness."
            ),
        ),
        dict(
            seconds=55,
            tag="Continuous actual browser capture",
            title="Stock changes → stale action blocked → B delivery",
            subtitle="",
            facts=[],
            note="",
            live=True,
            source=run_id
            + " · Local Medusa + deterministic SDK fixture · File integrity ≠ transaction verdict",
            narration=(
                "This is the working browser, recorded at its original speed. The buyer "
                "is a known SDK script, not a live language model. Supplier A loses stock "
                "while the scripted response is pending. Before an order, the wrapper "
                "reads current state and blocks the stale action. The script then "
                "requests supplier B. The browser shows recorded decision changes, the "
                "blocked action, and delivery. A provisional record does not prove that a "
                "process is running. A sealed record checks local file integrity. The "
                "separate export verifier checks the transaction. After the continuous "
                "capture ends, its final frame is held for explanation."
            ),
        ),
        dict(
            seconds=55,
            tag="Separate retained timeout experiment",
            title="An uncertain payment is not a rollback.",
            subtitle="This timeout is from a different run than the stock-recovery footage.",
            facts=[
                [
                    "Actual local request",
                    f"ReadTimeout · {timeout['finished_at'] - timeout['started_at']:.3f}s",
                ],
                ["Recovery rule", "Query the same order"],
                ["Uncertain state", "Keep the reservation"],
            ],
            note=(
                "No replacement payment based only on a failed response · Independent "
                "final COMPLETE 310"
            ),
            source=transport["run_id"]
            + " · Retained local HTTP trace · evidence/cw07-response-events",
            narration=(
                "This is a different retained experiment. A configured local payment "
                "response delay caused an actual HTTP read timeout after about two "
                "seconds. The request failure did not prove that the order or payment had "
                "rolled back. The program kept the uncertain reservation and queried the "
                "same order. It did not create a replacement payment merely because the "
                "response was missing. The final independent export was complete at three "
                "hundred and ten synthetic credits. This checks one controlled local "
                "timeout and recovery path. It does not establish the behavior of a real "
                "payment provider or every distributed failure schedule."
            ),
        ),
        dict(
            seconds=40,
            tag="Separate known-condition rosters",
            title="Report every planned cell and the full cost.",
            subtitle="Four-arm SDK/Medusa integration — not a model-performance ranking.",
            table=[
                ["Arm", "Learning + execution SDK calls", "Synthetic spend", "Fictional micro-USD"],
                *[
                    [
                        method,
                        f"{measurements[f'changed-{method}-r1']['learning_calls']} + "
                        f"{measurements[f'changed-{method}-r1']['execution_calls']}",
                        measurements[f"changed-{method}-r1"]["spent"],
                        measurements[f"changed-{method}-r1"]["fictional_micro_usd"],
                    ]
                    for method in ("B0", "B1", "B2", "B3")
                ],
            ],
            facts=[],
            note="Original B0 pilot is separate: 15 model cells remain NOT_RUN",
            source=(
                "evidence/cw07-reactive-comparison · One known condition × four methods · "
                "SDK fixture rates"
            ),
            narration=(
                "This separate four arm Medusa run checks integration and shared learning "
                "plus execution accounting. The model arms used the same delayed script. "
                "B zero had no such delay. The spending differences cannot measure "
                "learning or Peer Review effectiveness. Missing provider usage is not "
                "zero cost: unresolved reservations block further admissions. The "
                "original five condition pilot is a different roster, with fifteen model "
                "cells still not run. Separate scripted results do not fill those cells "
                "or become a held out model benchmark."
            ),
        ),
        dict(
            seconds=30,
            tag="Reproduce and assess the limits",
            title="Inspect the evidence. Keep the open questions.",
            subtitle="Verified locally on macOS arm64. No public deployment or final submission.",
            facts=[
                ["Local checks", "make check"],
                ["Actual capture", "make commerce-reaction-video"],
                ["English testing guide", "TESTING.md"],
            ],
            note=(
                "Pending: real models · learned transfer · held-out evaluation · "
                "developer observations · independent install"
            ),
            source=(
                "Local draft · English narration: macOS Samantha voice · No voice cloning "
                "or paid model calls"
            ),
            narration=(
                "The intended user is a developer or quality assurance engineer testing "
                "transaction tools. The repository includes English testing instructions "
                "and retained evidence. These commands were verified locally on macOS. "
                "Real model transfer, held out evaluation, developer observations, and "
                "Linux or independent machine reproduction remain pending. This video is "
                "a local draft, not a published submission or a claim of production "
                "readiness."
            ),
        ),
    ]
    write(output / "storyboard.json", {"scenes": scenes})
    log = output / "build.log"
    run(["node", "scripts/dev/video_cards.mjs", str(output)], log)
    captions, start, segments, audio_lengths = ["WEBVTT\n"], 0, [], []
    for index, scene in enumerate(scenes):
        speech = output / f"narration-{index}.txt"
        speech.write_text(scene["narration"])
        audio = output / f"narration-{index}.aiff"
        run(["say", "-v", "Samantha", "-r", "150", "-f", str(speech), "-o", str(audio)], log)
        audio_duration = float(probe(audio)["format"]["duration"])
        assert audio_duration < scene["seconds"] - 0.5, (index, audio_duration)
        audio_lengths.append(audio_duration)
        chunks = textwrap.wrap(scene["narration"], width=115)
        total = sum(len(chunk) for chunk in chunks)
        elapsed = 0.0
        for chunk in chunks:
            finish = elapsed + audio_duration * len(chunk) / total
            captions.append(
                f"{timestamp(start + elapsed)} --> {timestamp(start + finish)}\n"
                + "\n".join(textwrap.wrap(chunk, 58))
                + "\n"
            )
            elapsed = finish
        segment = output / f"segment-{index}.mp4"
        seconds = str(scene["seconds"])
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(output / f"card-{index}.png"),
        ]
        if scene.get("live"):
            command += [
                "-i",
                str(video),
                "-loop",
                "1",
                "-i",
                str(output / "hold-label.png"),
                "-i",
                str(audio),
                "-filter_complex",
                f"[1:v]fps=30,tpad=stop_mode=clone:stop_duration=55,trim=duration=55,setpts=PTS-STARTPTS[clip];"
                f"[0:v][clip]overlay=160:120:shortest=1[base];"
                f"[base][2:v]overlay=0:0:enable='gte(t,{duration})',format=yuv420p[v];"
                f"[3:a]apad,atrim=duration={seconds},aresample=48000[a]",
            ]
        else:
            command += [
                "-i",
                str(audio),
                "-filter_complex",
                f"[0:v]fps=30,format=yuv420p[v];[1:a]apad,atrim=duration={seconds},aresample=48000[a]",
            ]
        command += [
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            seconds,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(segment),
        ]
        run(command, log)
        segments.append(segment)
        start += scene["seconds"]
        print(f"Encoded scene {index + 1}/7; voice {audio_duration:.1f}s / {seconds}s", flush=True)
    (output / "captions.vtt").write_text("\n".join(captions))
    (output / "concat.txt").write_text("".join(f"file '{p.name}'\n" for p in segments))
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(output / "concat.txt"),
            "-i",
            str(output / "captions.vtt"),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "1:0",
            "-c",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-disposition:s:0",
            "default",
            "-movflags",
            "+faststart",
            str(output / "rehearsal-draft.mp4"),
        ],
        log,
    )
    final = probe(output / "rehearsal-draft.mp4")
    assert abs(float(final["format"]["duration"]) - 285) < 0.2
    assert any(
        s["codec_name"] == "h264" and s["width"] == 1920 and s["height"] == 1080
        for s in final["streams"]
    )
    assert any(s["codec_name"] == "aac" for s in final["streams"])
    assert any(s["codec_name"] == "mov_text" for s in final["streams"])
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(output / "rehearsal-draft.mp4"),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-f",
            "null",
            "-",
        ],
        output / "decode.log",
    )
    (output / "transcript.md").write_text(
        "# Rehearsal — local English video draft\n\n"
        + "\n\n".join(
            f"## {scene['title']}\n\n{scene['narration']}\n\nSource: {scene['source']}"
            for scene in scenes
        )
        + "\n"
    )
    write(
        output / "report.json",
        {
            "scope": "local-draft-video-not-model-efficacy-or-publication",
            "published": False,
            "capture": str(capture.relative_to(ROOT)),
            "capture_sha256": sha(video),
            "capture_duration": duration,
            "voice": "macOS Samantha, installed local voice",
            "audio_seconds": audio_lengths,
            "duration_seconds": float(final["format"]["duration"]),
            "probe": final,
            "source_hashes": {
                str(p.relative_to(ROOT)): sha(p)
                for p in [
                    review_path,
                    external,
                    transport_path,
                    ROOT / "scripts/dev/build_submission_video.py",
                    ROOT / "scripts/dev/video_cards.mjs",
                ]
            },
            "video_sha256": sha(output / "rehearsal-draft.mp4"),
            "decode_passed": True,
            "captions": "English mov_text + sidecar WebVTT; approximate narration timings",
        },
    )
    print(f"PASS: 285-second English local draft: {output / 'rehearsal-draft.mp4'}")


if __name__ == "__main__":
    main()
