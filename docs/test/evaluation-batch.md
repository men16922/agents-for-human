# 알려진 조건의 평가 배치와 전체 분모

검증일: 2026-09-09. [동결 평가 실행자](frozen-model-evaluation.md)에 다중 조건·반복 명세, 영속 예약, 중단 후 재개, 독립 결과 집계를 연결했다. 실제 모델 호출이나 정식 미공개 비교는 수행하지 않았다.

## 실행과 보존 증거

```sh
make evaluation-batch-smoke
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.batch --report evidence/cw07-evaluation-batch
```

실행 원본은 `.local/evaluation/batch_4a7cf4ece35f492cb0626edecaca7869`다. [배치 명세](../../evidence/cw07-evaluation-batch/manifest.json)와 [결과](../../evidence/cw07-evaluation-batch/report.json), [artifact hash](../../evidence/cw07-evaluation-batch/artifact-manifest.json)를 보존했다. 903개 파일에는 배치 SQLite 명부와 각 실행의 JSON/text/raw export가 포함된다. 자식 실행의 내부 DB는 포함하지 않는다. 복사본에서 raw export를 독립 재판정하고 usage 비용을 재합산해 원본 보고서와 일치함을 확인했다. 실행 소스 45개 hash도 대조했다.

A의 tent 재고가 0인 조건에서 B의 tent 단가 70/75/80/85/90과 배송 시간 10/15/20/25를 조합한 **공개된 known grid**다. 20조건 × 1반복 × 4방식 = 80칸을 실행 전에 확정했다. 반복은 1~10회 지원하지만 이번 보존 배치는 1회다.

| 방식 | 계획/실행 | 독립 COMPLETE | 가상 모델 비용(micro-USD) |
|---|---:|---:|---:|
| B0 | 20/20 | 20 | 0 |
| B1 | 20/20 | 20 | 8,120 |
| B2 | 20/20 | 20 | 21,000 |
| B3 | 20/20 | 20 | 20,440 |

총 가상 비용은 49,560 micro-USD다. 미확정 예약은 0이며, 배치 한도 500,000·모델 칸별 한도 100,000 micro-USD를 사용했다. 단가는 SDK fixture용 가상값으로 실제 AWS 청구가 아니다. B2/B3는 학습부터 평가까지 동일 사용량 원장과 호출/토큰/도구/비용 한도를 유지한다.

## 중단과 회계 경계

명세는 조건·반복·방식·설정·소스 hash와 전체 명부를 고정한다. 조건 이름/seed만 바꾸거나 학습 조건을 재사용하는 입력은 거절한다. 각 칸은 SQLite transaction으로 먼저 RUNNING/예약 상태가 된 뒤 실행한다. 동시에 두 실행자가 같은 칸을 받지 못한다.

모델 칸을 시작하기 전에 해당 칸의 비용 상한 전액을 배치에서 예약한다. 사용량이 모두 기록되면 실제 기록 비용만 남기고 예약 잔액을 반환한다. 후속 칸의 전체 예약을 감당하지 못하면 BATCH_COST_LIMIT으로 멈춘다. 호출 전 추정 예산이며, 실제 사용량 초과분을 삭제하거나 청구의 엄격한 상한으로 표현하지 않는다.

사용량 누락이나 실행자 예외로 비용이 확정되지 않으면 남은 칸 예약을 유지하고 UNRESOLVED_USAGE로 멈춘다. 프로세스 중단으로 RUNNING이 남으면 UNRESOLVED_ATTEMPT로 멈춘다. 이 상태만으로 프로세스가 살아 있다고 판단하지 않는다. 자동 재호출·예약 해제·미확정 실행 조정은 구현하지 않았다. 안전하게 완료된 칸은 재실행하지 않고 아직 시작하지 않은 칸만 재개한다.

독립 보고서는 원본 명부의 모든 칸을 유지한다. NOT_RUN/RUNNING/ERROR/EVALUATION_INCOMPLETE/INVALID_EVIDENCE를 제외해 성공률을 높이지 않는다. 원장 목표 완료와 실행 성공 상태를 구별하며, 잘린 최종 응답은 원장이 COMPLETE여도 EVALUATION_INCOMPLETE다. 증거가 변경되면 기존 비용과 분모는 보존하고 후속 실행을 차단한다. 파일 hash는 로컬 보존·변경 탐지 용도이며 외부 서명이나 악의적인 저장소 관리자에 대한 인증 수단이 아니다.

## 검증과 한계

전용 회귀 18개로 전체 명부·재개·중복 admission·총 예산 부족·usage 누락·예외·중단·증거 변경/삭제·명부 삭제·음수 비용·소스/명세 변경·조건 분리를 검사했다. 초기 실패 5개는 짧은 배송 조건에서 호출 수가 줄어드는 것을 예상값에 반영하지 못한 테스트 오류였다. 원본 호출 13회/364 micro-USD와 구매 380을 대조한 뒤 수정했다.

`make check`는 Python 386개·mypy 45소스·ruff·lock·웹 빌드를 통과했다. 기존 TestClient 경고 2개는 유지된다. 브라우저와 Medusa는 이번 배치에서 실행하지 않았다.

SDK fixture는 관측된 배송 시간으로 대기 횟수를 계산한다. 80/80은 이 알려진 코드 경로의 연결 검증이며 모델의 추론, Peer Review 효과, 통계적 우월성이나 실제 물품 거래 성과가 아니다. B0/B1의 초기 정책과 B2/B3의 학습용 초기 정책도 다르므로 같은 초기 정책의 정식 비교로 사용하지 않는다. 기존 5조건 pilot의 모델군 15칸은 여전히 NOT_RUN이다.

실제 모델 배치는 설정과 별도 전체 예산을 명시해 먼저 준비한다. 준비 단계는 AWS client를 만들지 않는다. 아래 금액 표시는 입력할 값이며 실행 가능한 기본 예산이 아니다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.batch --prepare-live --batch-budget-usd '<approved-total-usd>' --repeats 1
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.batch --execute '<prepared-batch-directory>'
```

이 CLI의 기본 조건은 같은 known grid다. 실제 호출을 하더라도 이를 미공개 평가로 재명명하지 않는다. 모델 ID·공식 단가/출처·칸별/전체 예산이 준비된 후 CW03 정상 호출부터 확인하고, 정식 비교에는 초기 정책·학습 조건·새 평가 조건·반복과 누출 통제를 별도로 검토해야 한다. 모델 설정 대기 중 다음 검증은 수정된 B0의 기존 Medusa 전이 재실행이다.
