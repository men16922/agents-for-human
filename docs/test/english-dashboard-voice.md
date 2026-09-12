# English dashboard and ElevenLabs voice sample

2026-09-12. The user clarified that both the dashboard and test narration should be English. Dashboard labels, actions, status and error messages, accessibility labels, item names, event labels, number formatting and HTML language are now English. Transaction logic, raw status codes, ledgers and model prompts are unchanged. Existing browser tests and live-capture script selectors were updated to the new labels; retained past captures remain immutable.

`make check` PASS: Python 690, mypy 58, lint, dependency locks and web build. `make check-browser` PASS: 25 tests covering observation recovery, independent evidence, execution records and responsive views. Screens at widths 1440, 390 and 320 were captured; desktop and mobile layouts were visually inspected. [Desktop dashboard](../../evidence/cw08-english-voice/dashboard-1440.png) · [mobile dashboard](../../evidence/cw08-english-voice/dashboard-390.png). These are browser fixtures and retained-record replays, not new model transactions. Test ports were released.

## Selected voice and actual sample

The authenticated ElevenLabs voice list identified **Daniel — Steady Broadcaster**, `onwK4e9ZLuTAKqWW03F9`, as a formal British English voice for informative/educational material. That profile was selected for technical narration. The existing `.env` variable `ELVENLAB_ACTOR` was replaced with this ID; the API key and other environment entries were preserved. Credentials are not included in the evidence.

[Listen to the English sample](../../evidence/cw08-english-voice/rehearsal-technical-daniel.mp3) · [sample text](../../evidence/cw08-english-voice/sample.txt) · [generation and QA report](../../evidence/cw08-english-voice/report.json).

One [ElevenLabs TTS request](https://elevenlabs.io/docs/api-reference/text-to-speech/convert) generated 444 characters with `eleven_multilingual_v2`: stability 0.60, similarity 0.75, style 0, speaker boost enabled, speed 0.97. The MP3 is 34.458 seconds, mono, 44.1 kHz. Full decoding and Chromium play/seek checks passed. No human listening evaluation is claimed; the sample is ready for voice approval.

The provider response reports **244 character-cost credits**. The immediate subscription counter had not changed, so its zero delta is not treated as free generation. A USD invoice amount was not inferred. This is separate from the earlier Nova campaign; no new Nova calls were made.

## Submission continuity

The previous r2 source archive and 3:45 video predate this dashboard translation and voice choice. The video still contains its original capture and Samantha narration. This task produced one voice sample, not a replacement full-length video. Before final publication, recapture the English UI, use the selected voice for the final narration if accepted, and regenerate the source package. Public repository/video URLs and entrant information are still pending.
