#!/usr/bin/env python3
"""Build a local English submission draft from verified actual Nova/Medusa artifacts."""
import argparse
import math
import shutil
import textwrap
from pathlib import Path
from build_submission_video import ROOT, read, write, sha, run, probe, timestamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    capture, output = args.capture.resolve(), args.output.resolve()
    if any(shutil.which(name) is None for name in ('ffmpeg', 'ffprobe', 'say', 'node')):
        raise RuntimeError('Installed local media tools required')
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('Use a new ignored local output directory')
    result = read(capture / 'result.json')
    browser = read(capture / 'browser/browser-report.json')
    if not browser['passed'] or not result['attestation']['success']:
        raise ValueError('Verified actual transaction and browser capture required')
    if result['runtime']['scope'] != 'live-model':
        raise ValueError('Actual model scope required')
    video = capture / 'browser/nova-live.webm'
    duration = float(probe(video)['format']['duration'])
    live_seconds = math.ceil(duration / 5) * 5 + 5
    if not 10 < duration or live_seconds > 135:
        raise ValueError('Full original-speed capture must fit below five minutes')
    output.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'evidence/cw03-nova-live'
    review_path = base / 'b3-price-02/review/report.json'
    external = base / 'pilot-02-copy-reaudit.json'
    pilot = read(external)
    transport_path = ROOT / 'evidence/cw06-nova-reactive/reaction-ui-02/result.json'
    failed = read(transport_path)
    runtime = result['runtime']
    verdict = result['attestation']['evidence_review']['verdict']
    run_id = runtime['run_id']
    calls = len(runtime['usage']['calls'])
    cost = runtime['usage']['recorded_micro_usd'] / 1_000_000
    def scene(seconds, tag, title, subtitle, facts, note, source, narration, **extra):
        return dict(seconds=seconds, tag=tag, title=title, subtitle=subtitle, facts=facts,
                    note=note, source=source, narration=narration, **extra)
    scenes = [
        scene(20, 'The developer problem', 'Did the goods arrive?',
              'Test a transaction agent before giving it purchasing tools.',
              [['User', 'Developers and QA'], ['Risk', 'Payment ≠ delivery'], ['Evidence', 'Independent ledger']],
              'Local POC · Synthetic credits', 'Product purpose; no measured developer time saving',
              'A successful payment is not a delivered order. Rehearsal helps developers and quality assurance teams test transaction agents before delegation. It combines controlled failures, isolated practice, policy review, and an independent commerce ledger.'),
        scene(20, 'The working system', 'A real model. A separate commerce backend.',
              'Amazon Nova 2 Lite → Strands tools → Medusa → independent verification.',
              [['Goal', '3 tents + 6 lights'], ['Budget', '500 credits'], ['Model', 'Amazon Nova 2 Lite']],
              'Actual initial frame from this recording', run_id,
              'The buyer is Amazon Nova two Lite on Bedrock, running through Strands. It must deliver three tents and six lights within five hundred synthetic credits. Medusa manages the commerce records. The browser observes those records and cannot buy anything.',
              image=str(capture/'browser/initial.png')),
        scene(35, 'Actual review, retained artifacts', 'A proposed change is not an improvement.',
              'A fresh reviewer has no purchasing tools; every proposal requires evidence.',
              [['Proposed field', 'Refresh quote: false → true'], ['Before / candidate', '430 / 430 credits'], ['Outcome', 'No measured improvement']],
              'A later malformed review rejected this attempt; preserved in the denominator.',
              'Separate actual Nova B3 price-02 experiment; not this browser run',
              'In a separate actual Nova run, a tool free reviewer proposed refreshing quotes before ordering. We replayed that candidate from the same snapshot. Both executions spent four hundred and thirty credits, so the proposal did not improve the result. A later review returned an invalid field and the attempt was rejected. Initial buying, review, and candidate testing share one budget. We retain rejected attempts and their costs.'),
        scene(live_seconds, 'Continuous actual capture', 'Actual Nova purchasing under a stock change', '', [], '',
              run_id+' · Independent transaction evidence follows the execution record',
              'This is an actual Nova run against local Medusa, shown at its original speed. The controller changes supplier A stock during the session. Model decisions pass through server checks before any order or payment. The browser shows the observed changes, delivery status, and recorded execution decisions. A sealed execution log proves file consistency. The separate export verifier establishes whether the goods arrived. After the recording ends, the final frame is held.',
              live=True, liveLabel='ACTUAL NOVA 2 LITE · LOCAL MEDUSA · SYNTHETIC CREDITS · ORIGINAL SPEED'),
        scene(25, 'A different actual run failed', 'Keep the failure in the report.',
              'Stock disappeared after the A order was created, before payment.',
              [['Payment', 'Repeated HTTP 400'], ['Final delivery', '0 tents / 0 lights'], ['Stop', 'Deadline reached']],
              'No replacement or successful-delivery claim inferred from a failed response.',
              failed['runtime']['run_id']+' · Separate actual Nova run, reaction-ui-02',
              'A different run failed. Stock disappeared after the A order was created. Payment was rejected, and Nova repeatedly retried the same payment instead of finding a valid recovery. It reached the deadline with nothing delivered. This failure remains in the evidence. The earlier successful run does not establish recovery for every timing.'),
        scene(35, 'Known-condition comparison', 'Peer Review has no demonstrated advantage yet.',
              'Five known conditions per arm, including one impossible goal.', [],
              'All learning, review and evaluation model costs included; not an invoice reconciliation.',
              'Separate frozen pilot-02 · USD 0.515321 · zero unresolved cost reservations',
              'The separate post fix pilot tested five known conditions per method. The fixed rule baseline completed four. The single model completed three. The model with simulation completed three. Simulation with Peer Review completed four, matching the baseline. The entire batch cost about fifty two cents in reported model usage. These small known samples do not demonstrate a Peer Review advantage. Failed and impossible cases remain in every denominator.',
              table=[['Arm','Goal complete / planned','Recorded model USD'], *[[m, str(pilot['methods'][m]['goal_complete'])+'/5', f"{pilot['methods'][m]['recorded_micro_usd']/1e6:.6f}"] for m in ['B0','B1','B2','B3']]]),
        scene(30, 'Reproduce and inspect', 'Inspect outcomes, costs and open questions.',
              'Source, English testing guide, architecture and retained evidence.',
              [['Local gate', 'make check'], ['This recorded run', f'{calls} calls · ${cost:.4f}'], ['Independent verdict', f"{verdict['status']} · {verdict['spent']} credits"]],
              'Remaining: held-out generalization · developer observations · independent-machine reproduction',
              'Local English draft · Installed macOS Samantha narration · Not yet published',
              'The source includes English testing instructions, the architecture, and retained evidence. Local checks run on macOS and a same host Linux container. Independent machine reproduction, held out generalization, and observed developer time savings remain open. This proof of concept demonstrates bounded model execution and inspectable transaction outcomes. It does not claim production readiness or better policies.'),
    ]
    write(output / "storyboard.json", {"scenes": scenes})
    log = output / "build.log"
    run(["node", "scripts/dev/video_cards.mjs", str(output)], log)
    captions, start, segments, audio_lengths = ["WEBVTT\n"], 0, [], []
    for index, scene in enumerate(scenes):
        speech = output / f"narration-{index}.txt"
        speech.write_text(scene["narration"])
        audio = output / f"narration-{index}.aiff"
        run(["say", "-v", "Samantha", "-r", "165", "-f", str(speech), "-o", str(audio)], log)
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
                f"[1:v]scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2,fps=30,tpad=stop_mode=clone:stop_duration={seconds},trim=duration={seconds},setpts=PTS-STARTPTS[clip];"
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
        print(f"Encoded scene {index + 1}/{len(scenes)}; voice {audio_duration:.1f}s / {seconds}s", flush=True)
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
    assert abs(float(final["format"]["duration"]) - sum(s["seconds"] for s in scenes)) < 0.2
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
            "scope": "actual-nova-local-draft-video-not-model-efficacy-or-publication",
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
                    ROOT / "scripts/dev/build_nova_submission_video.py",
                    ROOT / "scripts/dev/video_cards.mjs",
                ]
            },
            "video_sha256": sha(output / "rehearsal-draft.mp4"),
            "decode_passed": True,
            "captions": "English mov_text + sidecar WebVTT; approximate narration timings",
        },
    )
    print(f"PASS: English actual-Nova local draft: {output / 'rehearsal-draft.mp4'}")


if __name__ == "__main__":
    main()
