# CW08 — 실제 브라우저 녹화와 영어 영상 초안

2026-09-09. [영어 영상 초안 MP4](../../evidence/cw08-video-draft/rehearsal-draft.mp4)를 로컬에서 제작했다. 길이는 285.021초(4분 45초), 1920×1080 H.264/AAC이며 영어 자막 트랙을 포함한다. [WebVTT](../../evidence/cw08-video-draft/captions.vtt)·[영어 전문](../../evidence/cw08-video-draft/transcript.md)도 제공한다. 게시·최종 제출은 하지 않았다.

## 영상 구성과 근거

| 구간 | 내용 | 범위 |
|---|---|---|
| 0:00–0:25 | 개발자 문제·거래 완료 기준 | 설명 화면, 효용 실측 없음 |
| 0:25–0:55 | 텐트 3/조명 6·500크레딧 목표 | 이번 실행의 실제 초기 프레임, 정지 이미지 표시 |
| 0:55–1:45 | B3 정책 제안·독립 검토·후보 결과 | 별도 보존 SDK artifact, 새 모델 검토 영상 아님 |
| 1:45–2:40 | A 재고 변경·오래된 주문 차단·B 납품·실행/원장 판정 | 실제 SDK/Medusa/UI 원속도 녹화, 종료 뒤 최종 프레임 유지 표시 |
| 2:40–3:35 | 2초 ReadTimeout·동일 주문 재조회 | 별도 `cw00-b969e32652b2-buyer` 보존 실제 HTTP 기록 |
| 3:35–4:15 | 네 방식 비용/거래·원래 pilot 분모 | 알려진 별도 명부, 모델 효용 비교 아님 |
| 4:15–4:45 | 재현 안내·남은 검증 | macOS 로컬 범위와 미완료 항목 |

최종 녹화는 `reaction-ui_93d93f9c5de24f1fa65ab51bc6952124` / `cw00-5b4262f60244-buyer`다. 독립 COMPLETE 380·예약 0·추가 판단 4회·오래된 주문 차단 1회이며 SDK 9호출/180 fixture 토큰/가상 252 micro-USD다. [원본 녹화](../../evidence/cw08-video-draft/capture/browser/live-capture.webm), [실행 보고서](../../evidence/cw08-video-draft/capture/smoke.json), [브라우저/API 기록](../../evidence/cw08-video-draft/capture/browser/browser-report.json), 실행 중/종료 후 export를 보존했다. 같은 run의 실행 기록과 독립 판정을 대조했고 원장 판정은 두 export 모두 COMPLETE다.

새 녹화에서는 판단 기록이 4회이며 이전 시연의 5회를 복사하지 않았다. 시점별 공개 상태를 합쳐 처리하므로 같은 스크립트라도 관측/판단 횟수를 고정 성능값으로 사용하지 않는다. 모든 실제 모델 효과·Peer Review 효용·외부 청구는 미검증이다.

## 제작과 재현

추가 다운로드 없이 기존 `/opt/homebrew/bin/ffmpeg`, `ffprobe`, macOS `say`의 Samantha 영어 음성, 설치된 Chromium을 사용했다. 영상 설명 화면은 보존 JSON과 실제 프레임에서 생성하며 제품 화면을 합성하거나 네트워크 응답을 가로채지 않는다. 자막 시간은 음성 길이에 비례한 근사값이다. 최종 공개 전 사람이 발음·자막·편집을 검수해야 한다.

```sh
# 터미널 A: 전용 Medusa 준비
make commerce
# 터미널 B: 새 실제 SDK/Medusa/브라우저 녹화; 실제 모델 호출 없음
make commerce-reaction-video
# 녹화가 끝나면 터미널 A에서 Ctrl+C로 전용 서비스를 종료한다.

# --capture에는 위 명령이 출력한 새 디렉터리를 지정한다.
scripts/dev/with-env.sh python scripts/dev/build_submission_video.py \
  --capture .local/evaluation/<capture-directory> \
  --output .local/submission-video/<new-draft-directory>
scripts/dev/with-env.sh node scripts/dev/check_video.mjs .local/submission-video/<new-draft-directory>
```

편집 도구가 없으면 오류로 종료하며 설치를 시도하지 않는다. 출력은 새 `.local` 디렉터리만 허용한다. raw 영상 전체를 원속도로 넣고 남는 구간은 종료 프레임 유지로 표시한다. paid 모델 명령이나 게시 명령은 없다.

## 검수와 정리

첫 녹화는 full-page 스크린샷이 viewport를 바꾸는 순간 마지막 프레임이 작게 보였다. 두 번째는 크기는 정상이나 독립 판정이 화면 아래에 있었다. 녹화 때는 viewport 스크린샷만 사용하고 마지막 독립 판정 패널을 화면 안으로 이동해 교정했다. 세 실행의 거래 검사는 모두 통과했으며 앞선 두 편집본만 시각 검수에서 보류했다. 해당 원본 영상/검수 사유를 `reviewed-attempt-1/2`에 보존했다.

최종 MP4의 전체 영상/오디오 디코딩, 실제 Chromium 재생·8개 위치 이동, 영어 자막 33개 로드·표시를 확인했다. 재생/코덱 오류와 페이지 오류는 0이다. 오디오 평균 -20.1dB·최대 -4.7dB, 7개 설명 화면의 canvas 넘침 0을 확인했다. 최종 원본 프레임과 편집 화면을 직접 검토했으며, 음성을 사람이 전부 청취한 검수는 별도로 남았다.

`make check` PASS(Python 663·mypy 57·ruff·lock·웹 빌드). 이후 마지막 녹화 화면 위치만 조정했고 해당 실제 SDK/Medusa 녹화 검사·Node 문법 검사를 통과했다. 기존 전체 브라우저 회귀 25개는 직전 UI 단계의 기록이며 이번에는 실제 녹화 검사 세 번과 MP4 재생 검사를 수행했다.

[manifest](../../evidence/cw08-video-draft/artifact-manifest.json)에 73개 artifact와 별도 manifest를 저장했다. 원본/최종 영상 hash·복사본의 두 attestation/실행 요약·실제 자격증명 문자열 미포함을 대조했다. 소유 서비스 종료와 포트 18000/18001/19000/15173/55432/56379 반환, 기존 컨테이너 4개·볼륨 2개 보존을 확인했다. 빌드 중 임시 영상/음성은 ignored 경로에 유지했다.

다음은 CW03~CW09와 제출 체크리스트의 잔여 요구를 실제 증거와 대조하는 최종 준비 감사다. 실제 모델 설정/효과·미공개 평가·개발자 관찰·Linux/독립 호스트 재현·초기 커밋/공개 저장소·영상 공개·Builder ID·제출은 남아 있다.
