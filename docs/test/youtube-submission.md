# 영어 제출 영상과 로컬 파일 정리

2026-09-12. 사용자 요청에 따라 불필요한 로컬 복사본을 삭제하고 [YouTube 업로드용 MP4](../../submissions/video/rehearsal-demo.mp4)를 제작했다. 영어 화면·ElevenLabs Daniel 내레이션·영어 자막이며, 공개 업로드와 Devpost Submit은 수행하지 않았다.

## 영상

- 238.021초(3:58), 1920×1080/30fps H.264·AAC stereo, 내장 mov_text와 영어 [SRT](../../submissions/video/captions.en.srt)/[VTT](../../submissions/video/captions.en.vtt) 32개.
- [썸네일](../../submissions/video/thumbnail.png) 1280×720, [제목·설명·챕터](../../submissions/video/youtube.md), [대본](../../submissions/video/transcript.md).
- 새 실제 Nova/Medusa 연속 녹화를 원래 속도로 포함한다. 녹화가 끝난 뒤 정지 화면에는 별도 표시가 있다. 과거 실패 실행과 두 비교 집단은 별도 자료로 명시한다.
- 전체 ffmpeg 디코딩·Chromium 재생/8개 seek·자막 로딩 PASS. 표/마지막 카드·영어 화면·썸네일을 이미지로 확인했다. 음성의 사람 청취 검수나 공개 접근 검증을 뜻하지 않는다.
- [생성 기록](../../evidence/cw08-youtube-submission/report.json), [재생 검사](../../evidence/cw08-youtube-submission/playback-check.json), [음성 및 문자 정렬](../../evidence/cw08-youtube-submission/generation.json)을 보존했다. 렌더 시 캐시된 음성을 사용해 재인코딩에 추가 TTS 요청이 발생하지 않는다.

## 새 실제 실행과 비용

`youtube-ui-01` / `cw00-f94d15615950-buyer`: 공급처 A의 텐트 재고를 tick 6에 0으로 변경했다. 실제 Nova 18호출·$0.027211, 독립 COMPLETE·텐트 3/조명 6·지출 380·예약 0이다. [실행 원본](../../evidence/cw08-youtube-submission/capture/result.json)과 [독립 재감사](../../evidence/cw08-youtube-submission/verification.json)를 보존했다. 알려진 한 일정의 성공이며 다른 경합이나 모델 효과로 일반화하지 않는다.

캠페인 누적은 3,484호출·$4.219026·미확정 예약 0이다. 승인 $10 이내이며 usage 기반 추정으로 최종 AWS 청구액은 아니다. ElevenLabs는 별도 서비스로 전체 내레이션 7요청·2,746자·응답 헤더 기준 1,511크레딧을 소비했다. 기존 샘플은 별도 244크레딧이다. 크레딧을 달러 청구액으로 환산하지 않았다. 모델은 `eleven_multilingual_v2`, actor는 기존 승인 Daniel 그대로다. API 키와 다른 `.env` 값은 변경하지 않았다. 자막은 [공식 문자 정렬 API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)의 응답을 사용했다.

## 정리 범위

[삭제 명세](../../evidence/cw08-youtube-submission/cleanup.json)에 삭제 경로·파일 수·논리 바이트를 기록했다. 세 소스 후보의 source/extracted 복사본은 파일별 SHA-256을 보존된 tar와 대조한 뒤 삭제했다. 이전 압축본·manifest·검사 로그는 유지했다. 별도 fresh-venv와 재생성 가능한 검사 캐시/리포트도 삭제했다. 실제 디스크 회수량은 파일 시스템 공유 블록/압축에 따라 논리 합계와 다를 수 있다.

제품 코드·현재 의존성/고정 런타임·실험 원장·과거 실패·이전 영상 원본·다른 프로젝트·Docker 볼륨은 보존했다. 이전 r2 압축본은 영어 UI와 이번 영상 변경 전의 역사적 후보다. 현재 소스 패키지로 표시하지 않는다. 최종 제작 중간 파일도 검증된 제출 파일/보존 음성과 대조한 뒤 정리했다.

로컬 `make check`는 PASS(Python 690·mypy 58·ruff·lock·웹 빌드)이며 [검사 로그](../../evidence/cw08-youtube-submission/check.log)를 보존했다. 제품/브라우저 구현은 이번 작업에서 바꾸지 않았고 기존 브라우저 25개 결과와 이번 실제 연결/영상 재생 검사를 구분한다.

## 재제작과 남은 단계

`scripts/dev/build_nova_submission_video.py --prepare-only`로 storyboard를 만들고, 명시적 유료 제작 시 `scripts/dev/narrate_submission.py`로 내레이션을 생성한다. 이후 `--narration-dir`로 캐시된 음성·텍스트/hash를 대조해 렌더한다. 불확실하게 종료된 음성 요청에는 자동 재시도가 없다. 일반 로컬 검사는 유료 API를 호출하지 않는다.

공개 저장소/영상 URL·제출자/Builder ID·공개 접근 확인·최종 제출은 별도 단계다. 현재 요청은 파일 제작/정리로 완료하며 커밋·푸시·공개는 수행하지 않았다.
