#!/usr/bin/env python3
"""Edit a verified, visible Google Chrome recording into the English submission demo."""
# ruff: noqa: E501

import argparse
import json
import math
import shutil
from pathlib import Path

from build_submission_video import ROOT, probe, run, timestamp, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory.resolve()
    if not out.is_relative_to(ROOT / ".local"):
        raise ValueError("Build in an ignored local directory")
    story = json.loads((out / "storyboard.json").read_text())
    capture = ROOT / story["capture"]
    report = json.loads((capture / "browser-report.json").read_text())
    assert report["passed"] and report["browser"] == "Google Chrome" and not report["headless"]
    final = report["final"]
    if story.get("product") == "preflight":
        assert final["report"]["status"] == "REPORT_READY"
        audit = json.loads(
            (ROOT / "evidence/preflight" / final["run_id"] / "audit.json").read_text()
        )
        assert audit["passed"] and audit["workflow_status"] == "SUCCEEDED"
        assert audit["commerce_table_rows"] == 0
    else:
        assert final["verification"]["verdict"]["status"] == "COMPLETE"
        audit = json.loads(
            (
                ROOT / "evidence/serverless-deployment/runs" / final["run_id"] / "copy-audit.json"
            ).read_text()
        )
        assert audit["workflow_status"] == "SUCCEEDED" and audit["stop_status"] == 404
    generation = json.loads((out / "generation.json").read_text())
    log = out / "build.log"
    captions = ["WEBVTT\n"]
    total = 0
    edits = []
    scenes = story["scenes"]
    for i, (scene, voice) in enumerate(zip(scenes, generation["scenes"], strict=True)):
        assert scene["narration"] == voice["text"]
        duration = float(probe(out / voice["audio"])["format"]["duration"])
        scene["seconds"] = math.ceil(max(scene["seconds"], duration + 1.2) * 30) / 30
        alignment = voice["alignment"]
        chars = "".join(alignment["characters"])
        cursor = 0
        scene["caption_cues"] = []
        while cursor < len(chars):
            finish = min(cursor + 84, len(chars))
            if finish < len(chars):
                boundary = chars.rfind(" ", cursor + 30, finish)
                if boundary > cursor:
                    finish = boundary + 1
            value = chars[cursor:finish].strip()
            if value:
                scene["caption_cues"].append(
                    {
                        "start": alignment["character_start_times_seconds"][cursor],
                        "end": alignment["character_end_times_seconds"][finish - 1],
                        "text": value,
                    }
                )
            cursor = finish
    assert sum(s["seconds"] for s in scenes) < 180
    write(out / "storyboard.json", story)
    run(["node", "scripts/dev/chrome_video_frames.mjs", str(out)], log)
    for i, (scene, voice) in enumerate(zip(scenes, generation["scenes"], strict=True)):
        duration = scene["seconds"]
        segments = []
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(out / f"frame-{i}.png"),
        ]
        has_clip = "source_start" in scene
        if has_clip:
            a, b = scene["source_start"], scene["source_end"]
            clip_seconds = b - a
            command += [
                "-ss",
                str(a),
                "-t",
                str(clip_seconds),
                "-i",
                str(capture / "chrome-demo.webm"),
            ]
            x, y, w, h = scene["crop"]
            box = (72, 142, 1776, 814)
            if scene["kind"] == "learning":
                box = (1020, 142, 760, 814)
            if scene["kind"] == "result":
                box = (72, 142, 1776, 814)
            if scene["kind"] == "timeline":
                box = (72, 276, 1776, 480)
            bx, by, bw, bh = box
            segments.append(
                f"[1:v]setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={bw}:{bh}:force_original_aspect_ratio=decrease,pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=0x0b121e,fps=30,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration}[clip]"
            )
            segments.append(f"[0:v][clip]overlay={bx}:{by}:shortest=1[composite]")
            base = "composite"
            edits.append(
                dict(
                    scene=i,
                    source_start=a,
                    source_end=b,
                    original_speed=True,
                    held_seconds=max(0, duration - clip_seconds),
                    crop=scene["crop"],
                )
            )
            ai = 2
        else:
            base = "0:v"
            ai = 1
        command += ["-i", str(out / voice["audio"])]
        image_index = ai + 1
        if has_clip and duration > clip_seconds + 0.05:
            command += ["-loop", "1", "-i", str(out / "held-label.png")]
            segments.append(
                f"[{base}][{image_index}:v]overlay=72:977:enable='gte(t,{clip_seconds})'[held]"
            )
            image_index += 1
            base = "held"
        for cue_index, cue in enumerate(scene["caption_cues"]):
            command += ["-loop", "1", "-i", str(out / f"caption-{i}-{cue_index}.png")]
            segments.append(
                f"[{base}][{image_index}:v]overlay=0:0:enable='between(t,{cue['start']},{cue['end']})'[caption{cue_index}]"
            )
            image_index += 1
            base = f"caption{cue_index}"
        segments.append(f"[{base}]format=yuv420p[v]")
        segments.append(f"[{ai}:a]apad,atrim=duration={duration},aresample=48000[a]")
        command += [
            "-filter_complex",
            ";".join(segments),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(out / f"segment-{i}.mp4"),
        ]
        run(command, log)
        alignment = voice["alignment"]
        chars = "".join(alignment["characters"])
        cursor = 0
        while cursor < len(chars):
            finish = min(cursor + 84, len(chars))
            if finish < len(chars):
                boundary = chars.rfind(" ", cursor + 30, finish)
                if boundary > cursor:
                    finish = boundary + 1
            value = chars[cursor:finish].strip()
            if value:
                a = total + alignment["character_start_times_seconds"][cursor]
                b = total + alignment["character_end_times_seconds"][finish - 1]
                captions.append(f"{timestamp(a)} --> {timestamp(b)}\n" + value + "\n")
            cursor = finish
        scene["timeline_start"] = total
        total += duration
        print(f"Encoded scene {i + 1}/{len(scenes)}: {duration:.2f}s", flush=True)
    write(out / "storyboard.json", story)
    (out / "captions.vtt").write_text("\n".join(captions))
    (out / "captions.srt").write_text(
        "\n".join(
            str(i) + "\n" + cue.split("\n", 1)[0].replace(".", ",") + "\n" + cue.split("\n", 1)[1]
            for i, cue in enumerate(captions[1:], 1)
        )
    )
    (out / "concat.txt").write_text(
        "".join(f"file 'segment-{i}.mp4'\n" for i in range(len(scenes)))
    )
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
            str(out / "concat.txt"),
            "-i",
            str(out / "captions.vtt"),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "1:0",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-movflags",
            "+faststart",
            str(out / "rehearsal-demo.mp4"),
        ],
        log,
    )
    shutil.copy2(out / "frame-0.png", out / "thumbnail.png")
    write(
        out / "build-report.json",
        dict(
            seconds=total,
            captions=len(captions) - 1,
            run_id=final["run_id"],
            capture=story["capture"],
            edits=edits,
            probe=probe(out / "rehearsal-demo.mp4"),
            screen_seconds=sum(s["seconds"] for s in scenes if "source_start" in s),
            burned_english_captions=True,
            audio_target_lufs=-16,
        ),
    )


if __name__ == "__main__":
    main()
