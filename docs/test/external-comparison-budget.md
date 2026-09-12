# 외부 실행의 사전 예약과 전체 비교 분모

2026-09-09. [B3 한 건의 학습/외부 실행 원장](learning-http-budget.md)을 비교 명부의 사전 예약·중단·독립 정산에 연결했다. 실제 로컬 Medusa에서 한 건을 검증했으며 실제 모델은 호출하지 않았다. 이후 [B0/B1/B2/B3 외부 실행](external-four-arms.md)까지 연결했고 공급처 조건 일치 검증은 남았다.

## 실행 전에 고정하는 것

`evaluation/external_batch.py`는 기존 배치의 B0/B1/B2/B3 명부·SQLite 예약을 사용한다. 새 명세에는 `evaluation_environment=external-medusa`를 기록한다. 연습 배치 실행기/보고서는 외부 명부를 거절하고, 외부 제어자도 기존 연습 결과를 받아들이지 않는다. 기존 80개 연습 결과의 환경이나 성과를 바꾸지 않는다.

조건·반복·네 방식·모델/단가/공통 한도·전체 예산·소스 hash를 실행 전에 동결한다. 학습 전에 한 칸의 학습/외부 실행 예산 상한 전액을 예약한다. 선택한 B3 한 칸만 시작해도 나머지 방식은 NOT_RUN으로 분모에 남는다. 아래 최초 검증은 B3만 실행했다. 이후 네 방식의 CLI를 연결했으며 각 방식의 새 실행/학습 기록을 구분한다.

학습이 끝나면 기록 비용을 반영하되 나머지 상한을 계속 보유한다. HTTP 실행 후에도 독립 증빙을 기다리는 동안 반환하지 않는다. 사용량이 모두 확정된 실행을 정산해야 잔액을 반환하고 다음 칸을 허용한다. usage UNKNOWN이면 기록 비용을 제외한 상한을 보유하고 이후 학습을 차단한다. 이 연결에서 중간 비용을 반영한 뒤 정산할 때 학습 비용을 두 번 차감하던 예약 계산도 수정했다.

## 중단과 검증 경계

단계는 LEARNING → WAITING_EXTERNAL → EXTERNAL_RUNNING → AWAITING_EVIDENCE → EXTERNAL_VERIFIED/EXTERNAL_INCOMPLETE다. 학습 실패도 LEARNING_FAILED로 남는다. 시작 기록·PID·경과 시간만으로 프로세스 생존/종료를 판단하거나 실행을 재호출하지 않는다.

HTTP 실행자가 `execution-manifest.json`을 기록한 뒤 제어자가 중단됐다면, 명시적인 정산으로 원래 usage DB·종료 기록·정책·학습 hash·기대 목표/예산·원시 Medusa export를 대조할 수 있다. 모델·구매 HTTP를 다시 호출하지 않는다. 종료 기록이 없거나 증빙이 거절되면 예약을 유지한다. 판정 후에는 선택한 원시 export와 hash만 보존하고 다시 읽어 확인한다.

독립 거래 검증과 비교 조건 검증은 별도다. 현재 검사는 run/목표/예산·정책/학습·usage·주문/원장을 연결한다. 공급처 가격/재고/납기와 이벤트 조건이 명세대로 설치됐다는 증거는 아직 없으므로 `condition_alignment_verified=false`, 방식별 `condition_verified=0`을 유지한다. 거래 완료를 본 평가의 조건 통과나 모델 효용으로 계산하지 않는다.

## 실제 로컬 검사

`make commerce` 기동 후 `make external-batch-smoke`를 수행했다. 명부는 **2조건 × 4방식 = 8칸**, 총 예산/칸별 상한은 가상 100,000 micro-USD다. smoke는 공급처 grid를 Medusa에 설치하지 않는다. 이 검사에서 거래만 검증되고 조건 일치는 미검증이어야 한다.

| 시점 | 전체 분모/진행 상태 | 기록 비용 | 보유 예약 |
|---|---|---:|---:|
| 학습 전 | NOT_RUN 8 | 0 | 0 |
| B3 학습 후 | WAITING_EXTERNAL 1·NOT_RUN 7 | 616 | 99,384 |
| 외부 실행 후 | AWAITING_EVIDENCE 1·NOT_RUN 7 | 1,008 | 98,992 |
| 독립 정산 후 | EXTERNAL_VERIFIED 1·NOT_RUN 7 | 1,008 | 0 |

금액은 가상 micro-USD이며 AWS 청구가 아니다. 학습 전에 상한 100,000이 예약되는 것은 별도 회귀에서 모델 factory 내부 조회로 확인했다. 실제 Medusa는 `cw00-376a4a6036f6`이며 원장 COMPLETE·지출 310·예약 0이다. 다음 B3 칸은 상한 전액을 예약할 잔여 전체 예산이 부족해 `BATCH_COST_LIMIT`으로 거절됐고 추가 학습은 없었다. 실제 모델 호출 0회, 조건 일치 확인 0건이다.

원본은 `.local/evaluation/external-b3_c50e6d5ec83d407e82705d10f5ab8f5c`다. [35개 artifact와 manifest](../../evidence/cw07-external-batch/artifact-manifest.json)에 명부 SQLite·단계별 집계·학습 원시 증거·HTTP 실행·별도 export/선택/판정·세션/초기 HTTP를 보존했다. 복사본의 전체 보고서·학습/거래 원장을 재판정하고 소스 48개 hash·실제 토큰 문자열 미포함을 대조했다. 소유 서비스 종료 후 포트 18001/19000/55432/56379 반환, 기존 컨테이너 4개·볼륨 2개 보존을 확인했다.

전용 회귀 16개로 사전 예약·전체 분모·연습/외부 환경 분리·학습/실행 합산 예산·중단/0회 재실행·usage 누락·예약 중복 차감·증빙/명부/비용 변경·다른 목표·지원되지 않는 방식·종료 기록을 이용한 무호출 정산·잘못된 선택 거절을 검사했다. 기존 배치 18개도 통과했다. `make check`: Python 457개·mypy 48소스·ruff·lock·웹 빌드 통과, 기존 TestClient 경고 2개 유지. 브라우저·실제 모델·AWS·설치·배포·커밋·푸시는 수행하지 않았다.

## 설정 후 수동 실행

외부 명부에는 `training`과 `cases`를 담은 명시적인 JSON이 필요하다. `cases`의 각 값은 연습 시나리오 형식이며 `goal`에 budget/items/deadline_tick/recipient를 포함한다. 사용하려는 세션의 목표/예산과 같아야 한다. 현재 세션 fixture는 venue·120tick·예산 500이다. 공급처 조건을 임의로 같다고 가정하지 않는다.

```sh
scripts/dev/with-env.sh uv run --offline python -m rehearsal.evaluation.external_batch \
  --prepare --cases "$CASE_FILE" --batch-budget-usd "$TOTAL_MODEL_BUDGET_USD"
scripts/dev/with-env.sh uv run --offline python -m rehearsal.evaluation.external_batch \
  --learn "$BATCH_DIR" --cell "$B3_CELL"
```

준비 단계는 모델 설정을 검사하고 명부만 생성한다. 학습 명령은 선택한 칸을 먼저 예약한 뒤 모델을 호출한다. 학습이 완료되면 [세션 CLI](model-session.md)를 해당 칸의 `runs/<cell>/policy.json`으로 연다. 그 뒤 출력된 구매자 설정을 사용한다. 각 명령은 사용자가 준비한 경로·예산을 전제로 하며 실제 모델 명령을 이번에 수행하지 않았다.

```sh
scripts/dev/with-env.sh uv run --offline python -m rehearsal.evaluation.external_batch \
  --execute "$BATCH_DIR" --cell "$B3_CELL" --buyer-config "$BUYER_CONFIG"
# 세션을 종료해 export/selection을 만든 뒤:
scripts/dev/with-env.sh uv run --offline python -m rehearsal.evaluation.external_batch \
  --settle "$BATCH_DIR" --cell "$B3_CELL" --selection "$EVIDENCE_SELECTION"
scripts/dev/with-env.sh uv run --offline python -m rehearsal.evaluation.external_batch \
  --report "$BATCH_DIR"
```

[네 방식의 실행](external-four-arms.md)은 이어서 검증했다. 다음은 선언한 공급처/이벤트 조건을 실제 Medusa에 적용한 증거와 판정을 연결하는 작업이다. 이 단계가 완료돼도 실제 모델·동등 초기 정책·미공개 조건·반복 평가의 증거는 별도로 필요하다.

후속 [정적 초기 조건 검사](static-initial-conditions.md)에서는 새 실행 5건의 조건 일치를 독립 검증했다. 이 문서의 이전 실행은 조건 증거가 없어 계속 미검증이며, 실행 중 이벤트 조건은 아직 지원하지 않는다.
