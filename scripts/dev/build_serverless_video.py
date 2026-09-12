#!/usr/bin/env python3
"""Prepare/render the English AWS demo from audited capture and cached narration."""

import argparse
import json
import math
import shutil
import textwrap
from pathlib import Path

from build_submission_video import ROOT, probe, run, timestamp, write


def prepare(capture, output):
    report = json.loads((capture / "browser-report.json").read_text())
    final = report["final"]
    if not report["passed"] or final["verification"]["verdict"]["status"] != "COMPLETE":
        raise ValueError("Verified actual AWS capture required")
    evidence = ROOT / "evidence/serverless-deployment/runs" / final["run_id"]
    audit = json.loads((evidence / "copy-audit.json").read_text())
    if audit["stop_status"] != 404 or audit["workflow_status"] != "SUCCEEDED":
        raise ValueError("Workflow and session-absence checks required")
    usage = final["runtime"]["usage"]
    spent = final["snapshot"]["balance"]["spent"]
    cost = usage["recorded_micro_usd"] / 1e6
    live = report["live_end_seconds"]
    if live > 120:
        raise ValueError("Original-speed recording must fit the submission video")
    scenes = []

    def scene(seconds, tag, title, subtitle, facts, note, source, narration, **extra):
        scenes.append(
            dict(
                seconds=seconds,
                tag=tag,
                title=title,
                subtitle=subtitle,
                facts=facts,
                note=note,
                source=source,
                narration=narration,
                **extra,
            )
        )

    scene(
        22,
        "The developer problem",
        "A payment is not a delivery.",
        "Test a purchasing agent before delegating a transaction.",
        [
            ["Who", "Developers and QA"],
            ["Task", "Reproduce changing conditions"],
            ["Evidence", "Independent transaction records"],
        ],
        "All goods, payments and credits are synthetic.",
        "Product purpose; no measured time saving",
        "A purchasing agent can finish its answer while the goods are still missing. "
        "Rehearsal gives developers and quality assurance teams a controlled place to test "
        "that gap. Change inventory or prices, inspect the agent's actions, and verify "
        "delivery against independent transaction records.",
    )
    scene(
        29,
        "Deployed on AWS",
        "A live demo without an always-on server.",
        "CloudFront + Lambda + AgentCore + DynamoDB + Step Functions + S3.",
        [
            ["Buyer", "Nova 2 Lite / Strands"],
            ["Commerce", "Lambda / DynamoDB"],
            ["Lifecycle", "Bounded + explicitly stopped"],
        ],
        "Storage and requests remain metered.",
        "Deployed architecture; editable draw.io included",
        "The English dashboard is hosted on CloudFront and private S3. An API starts a "
        "bounded workflow. Amazon Nova two Lite runs through Strands on AgentCore. "
        "Lambda and DynamoDB hold the commerce records, while Step Functions advances "
        "the seller independently. The runtime session is stopped after the audit. "
        "Storage and requests still incur usage charges.",
        image=str(ROOT / "submissions/architecture/rehearsal-serverless.png"),
    )
    scene(
        26,
        "Four ways to test",
        "Practice and review are testable choices.",
        "Each live run keeps the same fixed goal, recipient and spending boundary.",
        [],
        "A reviewed policy is not automatically a better policy.",
        "B0, B1, B2 and B3 executed on the deployed AWS path",
        "B zero uses a fixed rule. B one buys directly with Nova. B two lets one agent "
        "practice before entering the live world. B three adds an independent reviewer "
        "with no purchasing tools. Practice, review, and live buying share one usage "
        "ledger. These options let us measure the cost of extra reasoning.",
        table=[
            ["Method", "Before the live purchase"],
            ["B0", "Fixed policy; no model calls"],
            ["B1", "Direct Nova purchasing agent"],
            ["B2", "Single-agent isolated practice"],
            ["B3", "Practice + independent policy review"],
        ],
    )
    scene(
        math.ceil(live) + 3,
        "Continuous actual AWS recording",
        "Nova handles disappearing stock on the deployed system.",
        "",
        [],
        "",
        final["run_id"] + " · actual AWS run · synthetic credits",
        "This recording runs at original speed. Supplier A loses its tents after the "
        "purchase clock starts. Nova chooses supplier B. Watch the payment reservation, "
        "the actual delivery count, and the separate verification result. The agent's "
        "final answer is not the completion authority.",
        live=True,
        liveLabel="ACTUAL NOVA + AWS SERVERLESS · ORIGINAL SPEED · SYNTHETIC CREDITS",
        narration_delay=14,
    )
    scene(
        24,
        "The independently checked result",
        "The journal confirms delivery.",
        "The verifier checks quantities, recipient, budget and delivery timing.",
        [
            ["Delivered", "3 tents + 6 lights"],
            ["Spent / reserved", f"{spent} / 0 credits"],
            ["Recorded model usage", f"{usage['model_calls']} calls / ${cost:.6f}"],
        ],
        "Step Functions succeeded; the stopped Runtime session was confirmed absent.",
        "Downloaded S3 records independently reverified; model estimate is not an AWS invoice",
        f"The independent audit confirms three tents and six lights, delivered on time "
        f"for {spent} credits, with no unresolved payment reservation. This run used "
        f"{usage['model_calls']} model calls and less than one cent of estimated model usage. "
        "The workflow succeeded, and a separate check confirmed that its runtime session "
        "was no longer present.",
    )
    scene(
        32,
        "Results include the failures",
        "More agents did not automatically win.",
        "Earlier frozen evaluation: 20 conditions per method, 80 planned cells.",
        [],
        "Historical practice-world results; not an AWS deployment benchmark.",
        "evidence/cw03-nova-live prospective comparison; one execution per condition",
        "An earlier frozen comparison included twenty conditions per method. The rule "
        "baseline completed fifteen goals. Direct Nova completed eleven, simulation "
        "completed eight, and peer review completed seven. Different starting policies "
        "and one execution per condition limit the comparison. These historical results "
        "do not prove a peer review advantage. Failures remain part of the evidence.",
        table=[
            ["Method", "Goals completed / planned"],
            ["B0 · fixed rules", "15 / 20"],
            ["B1 · direct Nova", "11 / 20"],
            ["B2 · simulation", "8 / 20"],
            ["B3 · peer review", "7 / 20"],
        ],
    )
    scene(
        22,
        "Try the deployed demo",
        "Inspect what happened, not just what was said.",
        "https://d1u9yhii3gor6j.cloudfront.net",
        [
            ["Try", "Choose a method and condition"],
            ["Inspect", "Delivery, spending and audit"],
            ["Reuse", "Source, evidence and draw.io"],
        ],
        "Synthetic POC · finite shared demo allowance · no production-safety claim",
        "Agents for Humans · English narration: ElevenLabs Daniel",
        "Open the hosted demo, choose a method and a condition, and inspect the result. "
        "The repository includes the transaction evidence, reproduction instructions, "
        "and an editable architecture diagram. Rehearsal is a synthetic proof of concept. "
        "The next step is testing whether it helps developers find real integration failures.",
    )
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "storyboard.json",
        {
            "edition": "AWS submission demo",
            "scenes": scenes,
            "capture": str(capture),
            "live_end_seconds": live,
        },
    )
    print("Prepared", output)


def render(output):
    story = json.loads((output / "storyboard.json").read_text())
    scenes, live = story["scenes"], story["live_end_seconds"]
    generation = json.loads((output / "generation.json").read_text())
    assert len(generation["scenes"]) == len(scenes)
    for scene, voice in zip(scenes, generation["scenes"], strict=True):
        assert scene["narration"] == voice["text"]
        seconds = float(probe(output / voice["audio"])["format"]["duration"])
        scene["seconds"] = max(
            scene["seconds"], math.ceil(seconds + scene.get("narration_delay", 0)) + 2
        )
    assert sum(s["seconds"] for s in scenes) < 300
    write(output / "storyboard.json", story)
    log = output / "build.log"
    run(["node", "scripts/dev/video_cards.mjs", str(output)], log)
    captions, start, segments = ["WEBVTT\n"], 0, []
    video = Path(story["capture"]) / "cloud-live.webm"
    for index, (scene, voice) in enumerate(zip(scenes, generation["scenes"], strict=True)):
        audio = output / voice["audio"]
        alignment = voice["alignment"]
        chars = "".join(alignment["characters"])
        delay = scene.get("narration_delay", 0)
        cursor = 0
        while cursor < len(chars):
            finish = min(cursor + 100, len(chars))
            if finish < len(chars):
                boundary = chars.rfind(" ", cursor + 35, finish)
                if boundary > cursor:
                    finish = boundary + 1
            text = chars[cursor:finish].strip()
            if text:
                a = start + delay + alignment["character_start_times_seconds"][cursor]
                b = start + delay + alignment["character_end_times_seconds"][finish - 1]
                captions.append(
                    f"{timestamp(a)} --> {timestamp(b)}\n"
                    + "\n".join(textwrap.wrap(text, 58))
                    + "\n"
                )
            cursor = finish
        seconds = str(scene["seconds"])
        segment = output / f"segment-{index}.mp4"
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
                f"[1:v]trim=duration={live},setpts=PTS-STARTPTS,"
                "scale=1600:900:force_original_aspect_ratio=decrease,"
                f"pad=1600:900:(ow-iw)/2:(oh-ih)/2,fps=30,"
                f"tpad=stop_mode=clone:stop_duration={seconds},trim=duration={seconds}[clip];"
                "[0:v][clip]overlay=160:120:shortest=1[base];"
                f"[base][2:v]overlay=0:0:enable='gte(t,{live})',format=yuv420p[v];"
                f"[3:a]adelay={delay * 1000}:all=1,apad,atrim=duration={seconds},"
                "aresample=48000[a]",
            ]
        else:
            command += [
                "-i",
                str(audio),
                "-filter_complex",
                f"[0:v]fps=30,format=yuv420p[v];[1:a]apad,atrim=duration={seconds},"
                "aresample=48000[a]",
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
        print(f"Encoded scene {index + 1}/{len(scenes)}", flush=True)
    (output / "captions.vtt").write_text("\n".join(captions))
    (output / "captions.srt").write_text(
        "\n".join(
            str(i) + "\n" + cue.split("\n", 1)[0].replace(".", ",") + "\n" + cue.split("\n", 1)[1]
            for i, cue in enumerate(captions[1:], 1)
        )
    )
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
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-movflags",
            "+faststart",
            str(output / "rehearsal-demo.mp4"),
        ],
        log,
    )
    shutil.copy2(output / "card-0.png", output / "thumbnail.png")
    write(
        output / "build-report.json",
        {
            "seconds": start,
            "captions": len(captions) - 1,
            "probe": probe(output / "rehearsal-demo.mp4"),
            "capture": story["capture"],
            "live_end_seconds": live,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".local"):
        raise ValueError("Build in an ignored local directory")
    if args.render:
        render(output)
    else:
        prepare(args.capture.resolve(), output)


if __name__ == "__main__":
    main()
