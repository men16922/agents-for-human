# AWS 아이콘 아키텍처와 Chrome 직접 시연 영상

2026-09-12 사용자가 AWS 아이콘 아키텍처와 실제 Chrome 대시보드 시연 중심의 영상 재편집을 요청했다. 결과물은 [2:30 영어 영상](../../submissions/video/rehearsal-demo.mp4), [24개 영어 자막](../../submissions/video/captions.en.srt), [썸네일](../../submissions/video/thumbnail.png), [YouTube 설명](../../submissions/video/youtube.md), [편집 가능한 AWS draw.io](../../submissions/architecture/rehearsal-serverless.drawio)다.

## 실제 시연과 근거

설치된 Google Chrome을 `channel: chrome`, `headless: false`로 열고 공개 대시보드에서 B0→B1→B2→B3 선택, Stock disappears 조건 선택, Run 버튼 클릭, 진행/결과 확인, timeline 확인과 새로고침을 직접 수행했다. 전용 Chrome 창을 사용했으며 API mock이나 결과 데이터 교체는 없다. 화면의 포인터 원만 녹화용 주석으로 추가했다. [원본 WebM](../../evidence/chrome-demo-v2/capture/chrome-demo.webm), [조작 시각과 실제 API 관측](../../evidence/chrome-demo-v2/capture/browser-report.json), [재현 녹화 스크립트](../../scripts/dev/capture_chrome_demo.mjs)를 보존했다.

새 실행은 `rehearsal-ed2ce2fd186d5a909b679236b6b8a9d5`다. 공급처 A 재고 감소 이후 B에서 구매했고, 독립 원장 판정은 COMPLETE, 기한 내 tent 3/light 6, spent 380/reserved 0이었다. 학습 결과는 `NO_CHANGE`다. [다운로드한 S3 증거 재검증](../../evidence/serverless-deployment/runs/rehearsal-ed2ce2fd186d5a909b679236b6b8a9d5/copy-audit.json)으로 같은 verdict, Step Functions SUCCEEDED, 별도 Runtime 재조회 404/세션 부재를 확인했다. 모델 우위나 Peer Review 효과를 입증하는 비교 실험은 아니다.

추가 모델 사용량은 **23호출/$0.023002**, 미확정 예약 0이다. 연습 구매 13호출/$0.013738, 도구 없는 검토 1호출/$0.001129, 실제 구매 9호출/$0.008135를 합한 값이다. 서버리스 실행 전체는 135호출/$0.155378, 기존 캠페인 포함 3,619호출/$4.374404다. [추가 실행/전역 예산 감사](../../evidence/chrome-demo-v2/run-audit.json) 시 allowance $3.844622, admissions 28개, active 0이었다. 이는 모델 usage 추정치이며 AWS 인프라 청구 총액이 아니다. 예산은 재설정하지 않았다.

## 영상 편집과 검수

참고한 [RoadPilot 영상](https://www.youtube.com/watch?v=SoMfLvUfG0Y)은 Chrome에서 열어 초반의 짧은 제목, 어두운 배경, 금색 강조와 실제 제품 화면 배치를 확인했다. 후반 seek에서는 버퍼링이 있어 전체 장면을 확인했다고 주장하지 않는다. 참고 영상의 영상/음성/자산은 결과물에 사용하지 않았다.

완성본은 **150.2초(2:30), 1920×1080, 30 fps, H.264/AAC**이며 실제 UI 녹화를 쓰는 장면은 111.37초다. 도입→조건 선택→학습→실제 구매→독립 판정→원장→새로고침→AWS 구성→접속 안내 순서다. 설정/결과/원장을 확대했고 로딩 대기는 장면 전환으로 덜어냈다. 녹화가 재생되는 동안에는 원속도를 유지하며, 내레이션용 정지 화면에는 `PAUSED FRAME`을 표시했다. 전체 영상이 무편집 연속 녹화라고 표현하지 않는다.

ElevenLabs Daniel 9요청/1,657자/응답 보고 911크레딧으로 영어 음성을 생성했다. 자동 재시도는 없었으며 두 차례의 화면 편집에서는 같은 음성을 재사용했다. 비용 패널이 잘리는 첫 편집을 수정했고, 최종 결과/학습/원장의 화면을 다시 확인했다. FFmpeg에 drawtext/subtitles 필터가 없어 설치를 추가하지 않고 로컬 Chrome으로 자막 PNG를 렌더링했다. 화면에 영어 24자막을 넣었고 SRT/VTT와 자막 트랙도 포함했다.

- [제작·편집 구간 기록](../../evidence/chrome-demo-v2/build-report.json), [영어 음성/시각](../../evidence/chrome-demo-v2/generation.json), [대본](../../submissions/video/transcript.md).
- [Chromium 재생/8 seek/24자막 PASS](../../evidence/chrome-demo-v2/playback-check.json), FFmpeg 전체 영상/음성 디코딩 PASS.
- [음량 재측정](../../evidence/chrome-demo-v2/audio-check.log): integrated −16.06 LUFS, true peak −1.49 dBTP.
- 최종 시각 확인: [학습](../../evidence/chrome-demo-v2/final-learning-check.png), [결과/비용](../../evidence/chrome-demo-v2/final-result-check.png), [전체 원장](../../evidence/chrome-demo-v2/final-timeline-check.png).
- [최종 파일 SHA-256](../../evidence/chrome-demo-v2/deliverable-hashes.json). 이전 3:34 영상은 [별도 보존](../../evidence/chrome-demo-v2/previous-video/rehearsal-demo.mp4)했다.

## AWS 아키텍처

[AWS 공식 2026-07-31 아이콘 패키지](https://aws.amazon.com/architecture/icons/)에서 필요한 11개 SVG만 원본 그대로 보존했다. AgentCore 전용 아이콘, Bedrock, CloudFront, API Gateway, Lambda, Step Functions, DynamoDB, S3와 Cloud/Region 경계 아이콘을 사용했다. CloudFront와 global inference는 us-west-2 경계 바깥 AWS Cloud 안에 표시했다. 각 아이콘·문구·연결선은 draw.io에서 편집 가능하며 SVG 데이터가 내장되어 외부 이미지 링크에 의존하지 않는다.

[draw.io 실제 열기](../../evidence/chrome-demo-v2/drawio-open.png)와 [권한/비용 페이지](../../evidence/chrome-demo-v2/drawio-boundaries.png)를 확인했고 SVG/PNG를 렌더링했다. 기존 공개 사이트의 architecture 파일 3개를 갱신하고 CloudFront 해당 경로만 invalidation했다. [공개 HTTP/hash 대조](../../evidence/chrome-demo-v2/diagram-publication.json)는 세 파일 모두 HTTP 200·로컬 SHA-256 일치다. [출처 목록](../../assets/architecture/aws/sources.json)과 [제3자 고지](../../THIRD_PARTY_NOTICES.md)에 원본을 기록했다.

이번 변경은 녹화/편집/아키텍처 생성기와 제출 문서다. 관련 Python lint/format·JS syntax·문서 gate를 검사했다. 제품 코드를 변경하지 않아 이전 715개 Python/25개 로컬 브라우저 회귀를 다시 실행하지 않았다. Git commit/push, YouTube 업로드, Devpost Submit은 수행하지 않았다.
