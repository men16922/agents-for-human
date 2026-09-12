# 실제 Nova 재계획과 제출 영상

> 최신 제출 영상은 [최종 Nova 제출 감사](nova-final-submission.md)의 3:45 편집본이다. 아래 3:30 영상과 비용은 재계획 검증 종료 시점의 보존 기록이다.

2026-09-12. 승인된 Nova 2 Lite 총 $10 범위에서 실제 Medusa 재고 변경 세 건을 실행했다. 두 건은 B 대체 구매로 COMPLETE 380, 한 건은 A 주문 뒤 지급 거절을 반복하다 deadline으로 종료했다. **성공과 실패를 함께 보존하며 모든 일정의 복구나 Peer Review 효과를 주장하지 않는다.**

## 서로 다른 재고 변경 시점

모델은 글로벌 Nova 2 Lite, Strands 구매 도구와 기존 `ReactionSettings(16)`을 사용했다. 각 실행은 별도 동결 기본 정책·새 Medusa 세션, 목표 텐트 3/조명 6·500크레딧·90tick이다. 48모델 호출/60도구·입력 추정 24,000/호출·전체 300,000토큰·모델 예산 $0.50을 캠페인에서 먼저 예약했다. 모델 응답을 스크립트로 대체하거나 일부러 지연시키지 않았다.

| 실행 | 실제 A 텐트 재고 변경 | 실행 / 독립 판정 | 호출 / 기록 모델 비용 |
|---|---|---|---|
| reaction-01 | tick 4, 10→0 | COMPLETED / COMPLETE 380 | 17 / $0.029264 |
| reaction-ui-02 | tick 8, 10→0 | LIMITED, OBSERVATION_DEADLINE_REACHED / FAILED 0 | 36 / $0.061591 |
| reaction-ui-03 | tick 6, 10→0 | COMPLETED / COMPLETE 380 | 18 / $0.026988 |

첫 실행은 오래된 집행 1건 차단·추가 판단 5회, 마지막 녹화 실행은 차단 1건·추가 판단 3회였다. 마지막 실행에서는 tick 6 주문 차단 후 B 주문/지급을 요청했고, 별도 원장에서도 기한 내 3/6 수령·예약 0을 확인했다. 재판단 수는 외부 장애 수나 실제 provider 호출 수와 다르다.

중간 실행은 tick 7에 A 주문을 만든 뒤 tick 8 재고 변경을 맞았다. Nova가 같은 주문의 지급을 반복했으나 HTTP 400/지급 조회 NOT_FOUND가 이어졌다. 최종 원장은 수령 0·지출 0·예약 0이며 deadline 이후 FAILED다. 이 실패를 다른 일정의 성공으로 덮어쓰지 않는다. 서버의 지급 거절과 모델의 회복 실패를 구분한다.

[복사본 독립 재감사](../../evidence/cw06-nova-reactive/copy-reaudit.json)는 세 실행의 attestation과 실제 Store/Admin 재고 변경을 다시 검증했다. [실패 원본](../../evidence/cw06-nova-reactive/reaction-ui-02/result.json), [성공 녹화 원본](../../evidence/cw06-nova-reactive/reaction-ui-03/result.json), 세 실행의 도구·관측·HTTP·usage SQLite와 session export를 보존했다. 학습된 정책 변경을 사용한 실험은 아니다.

## 회계와 실행 도구의 오류

첫 UI 시도 reaction-ui-01은 브라우저 모듈 경로 오류로 모델 생성 전에 종료했다. 실행 디렉터리와 모델 호출이 없음을 확인해 비용 예약을 해제했으며 실패 로그를 보존했다. 첫 비녹화 실행의 사후 집계 도구는 없는 `usage.json`을 읽으려 해 예약을 남겼다. 원본 `execution/report.json`의 전 호출 RECORDED·금액을 확인한 별도 정산 기록으로 해제했다. 이후 도구는 실제 report의 usage를 읽는다. 원본 result에 남은 중간 예약 상태와 최종 캠페인을 구별한다.

기존 실행을 포함한 캠페인 합계는 **1,140호출·입력 4,245,669/출력 47,690토큰·$1.393427**, 미확정 비용 예약 0이다. [원장별 단가 재계산과 캠페인 대조](../../evidence/cw06-nova-reactive/cost-audit.json)가 일치한다. 캐시 사용량은 0이며 AWS 최종 청구와는 아직 대조하지 않았다. 기존 [초기 Nova 기록](nova-live.md)의 $1.275584는 당시까지의 소계다.

## 실제 Nova 영어 영상

[새 MP4](../../evidence/cw08-nova-video/rehearsal-draft.mp4)는 **210.021초(3:30), 1920×1080 H.264/AAC**다. [영어 자막](../../evidence/cw08-nova-video/captions.vtt)·[전문](../../evidence/cw08-nova-video/transcript.md)·[재생 검사](../../evidence/cw08-nova-video/playback-check.json)를 함께 제공한다. 공개 게시나 제출은 하지 않았다.

| 구간 | 내용 | 증거 범위 |
|---|---|---|
| 0:00–0:20 | 개발자 문제 | 효용 가설 |
| 0:20–0:40 | Nova/Strands/Medusa와 목표 | 실제 초기 프레임 |
| 0:40–1:15 | B3 변경 제안·430→430·거절 | 별도 실제 Nova 보존 기록 |
| 1:15–2:00 | 재고 변경·구매·독립 판정 | reaction-ui-03 원속도 연속 녹화, 종료 뒤 프레임 유지 표시 |
| 2:00–2:25 | 지급 반복·deadline 실패 | 별도 reaction-ui-02 실제 기록 |
| 2:25–3:00 | B0/B1/B2/B3 4/3/3/4, 비용 | 별도 알려진 20칸 pilot-02 |
| 3:00–3:30 | 재현과 미완료 범위 | 실제 호출 비용·한계 |

원본 녹화는 [WebM](../../evidence/cw06-nova-reactive/reaction-ui-03/browser/nova-live.webm)이다. 브라우저 요청은 GET만, Authorization 노출·콘솔 오류 0이었다. 실행 API SEALED와 별도 원장 COMPLETE·동일 run을 확인했다. 재고 이벤트·실행 기록·납품이 서로 다른 증거임을 유지한다. 기존 4:45 SDK 영상은 과거 자료로 보존한다.

설명 화면 7개의 크기/넘침, MP4 전체 디코딩, Chromium 재생·8개 위치 이동·26개 영어 자막 로드를 검사했다. 실제 초기 화면·재생 프레임·마지막 독립 판정 화면도 확인했다. 설치된 macOS Samantha 음성만 사용했으며 사람의 전체 음성/편집 검수는 남았다. 첫 편집의 마지막 음성이 25초 구간에 너무 가까워 그 구간을 30초로 늘린 뒤 새 출력으로 빌드했다.

```sh
scripts/dev/with-env.sh python scripts/dev/build_nova_submission_video.py \
  --capture evidence/cw06-nova-reactive/reaction-ui-03 \
  --output .local/submission-video/new-nova-draft
scripts/dev/with-env.sh node scripts/dev/check_video.mjs .local/submission-video/new-nova-draft
```

영상 생성은 보존 파일과 로컬 도구만 읽으며 새 모델 호출을 하지 않는다. 빌드 당시 생성기와 이후 형식 정리한 버전을 모두 보존했다. 카드 렌더러는 실제 모델/SDK 표시를 storyboard에서 구별하며 기존 SDK 기본값도 유지한다.

전체 `make check` PASS(Python 690·mypy 58·ruff·lock·웹 빌드). 새 소스 생성기의 형식 오류를 수정한 뒤 전체 gate를 통과했다. 이번 모델 실행은 기존 구매 소스를 변경하지 않았다. 전용 서비스는 종료했고 기존 컨테이너 4개·볼륨 50개를 보존했다. Medusa 터미널 종료 코드는 Ctrl+C의 130이며 거래 판정과 별개다.

다음은 사전에 새로 동결한 미공개 평가 조건, 실패 일정의 원인/개선 비교, 공개 제출용 소스 패키지 갱신이다. 개발자 관찰·독립 기기 재현·사람의 영상 검수·공개 저장소/영상·Builder ID·최종 제출도 남았다.
