# B3 학습 예산을 실제 Medusa 실행까지 이어 쓰기

2026-09-09. 완료된 B3 학습 원장을 외부 HTTP 실행에서도 사용하도록 연결했다. 알려진 SDK fixture의 학습과 실제 로컬 Medusa 구매를 한 번씩 수행했다. 실제 모델·정책 전이 효과·미공개 비교 결과는 아니다.

## 전달 계약

`commerce/learning_budget.py`는 완료된 B3 보고서의 상태·부모 보존·사용량·소스 hash와 초기/검토 artifact를 확인한다. 선택된 후보 정책과 학습 JSON/text hash를 함께 동결한다. 외부 실행은 그 정책과 원래 `usage.sqlite3`를 사용하며 별도 usage DB를 만들지 않는다. 누락/빈 DB는 읽기 전용 조회에서 실패한다.

모델 ID·단가·비용/토큰/호출/도구 한도·scope는 기존 원장과 같아야 한다. 학습 증빙이 있는 정책을 `--learning` 없이 실행해 새 예산을 만드는 경로도 거절한다. 추가 한도가 필요하면 처음 학습을 시작하기 전에 전체 학습/실행 예산을 정해야 한다.

원장의 `http_transfer`에 외부 실행 한 칸을 등록한다. 학습 세션당 한 번만 등록할 수 있다. 모델 호출 전 오류도 분모에 남으며 중단된 STARTED·실패·사용량 UNKNOWN을 자동 재시도하지 않는다. 별도 디렉터리나 새 run ID로도 같은 학습 원장을 다시 소비할 수 없다. 이 제약은 이번 한 건의 handoff 범위다. 기존 20조건×4방식 비교 roster의 전체 예산과 외부 실행 상태를 합치는 작업은 남았다.

보고서는 학습 당시 usage, 외부 실행 ID에 속한 usage, 전체 usage를 구분한다. 학습이 완료됐다는 이유로 외부 실행을 성공 처리하지 않는다. 외부 실행의 실제 호출·usage 확정과 별도 주문/원장 판정이 필요하다. 학습 artifact 변경은 다음 모델 호출/도구 실행을 중단하며, 사용량 누락의 예약도 원래 DB에 남긴다.

## 설정 후 실행 순서

아래 명령은 운영자가 실제 모델 설정과 완료된 B3 학습 경로를 준비한 뒤 사용한다. 현재 실제 모델로 실행하지 않았다. `LEARNING_DIR`, `POLICY_FILE`, `BUYER_CONFIG`는 해당 로컬 경로로 지정한다. 정책 파일은 학습 폴더 밖의 새 파일이어야 한다.

```sh
scripts/dev/with-env.sh uv run --offline python -m rehearsal.commerce.learning_budget \
  --learning "$LEARNING_DIR" --policy-output "$POLICY_FILE"
```

이 단계는 학습 파일/원장 검사와 동결 파일 생성만 수행한다. HTTP/AWS 클라이언트나 모델을 호출하지 않는다. [세션 CLI](model-session.md)를 `--serve --policy "$POLICY_FILE"`로 열고, 출력된 구매자 설정으로 실행한다. 새 세션의 외부 시계가 진행되므로 모델 설정/학습 동결을 먼저 마친다.

```sh
scripts/dev/with-env.sh uv run --offline python -m rehearsal.commerce.model_runner \
  --config "$BUYER_CONFIG" --learning "$LEARNING_DIR"
scripts/dev/with-env.sh uv run --offline python -m rehearsal.commerce.model_runner \
  --config "$BUYER_CONFIG" --learning "$LEARNING_DIR" --execute
```

첫 명령은 preflight다. 실행 후 세션을 종료하면 독립 export와 실행 주문을 대조한다. [계측 HTTP 실행](metered-http-model.md)의 NOT_VERIFIED/독립 attestation 구분을 그대로 사용한다. 학습 후 다른 평가가 이미 원장을 소비했다면 새 외부 예산으로 간주하지 않고 거절한다.

## 검증 결과

`make commerce`로 전용 서비스를 기동한 뒤 `make commerce-learning-smoke`를 수행했다. smoke는 가상 단가·한도를 시작 전에 고정하고 SDK 학습을 마친 후에만 새 Medusa 세션을 만든다.

| 단계 | SDK 모델 호출 | 토큰 | 허용 도구 호출 | 가상 micro-USD |
|---|---:|---:|---:|---:|
| B3 초기 구매·검토·후보 구매 | 22 | 440 | 18 | 616 |
| 외부 HTTP 구매 | 14 | 280 | 13 | 392 |
| 원래 원장의 전체 합계 | 36 | 720 | 31 | 1,008 |

학습 실행은 `b3-http_b92d83ca01774e8c8eecb0c1777bbe1e`, 실제 Medusa 세션은 `cw00-e1790ade5f94`다. 독립 원장은 COMPLETE·지출 310·예약 0이고 실행 주문과 일치했다. 사용량 미확정 비용 예약은 0이다. 학습 22개 call row가 외부 실행 후에도 동일하며 정책/학습 artifact hash도 일치했다. 실제 모델 호출은 0회다.

[보존 증거](../../evidence/cw05-learning-budget/artifact-manifest.json)는 25개 artifact와 별도 manifest다. 학습 원시 증빙·정책·실행 spec/report/trace·세션 export/판정·초기 Medusa HTTP를 포함하며 소스 47개 hash를 대조했다. 보존된 학습/Medusa 증거를 다시 독립 판정하고 합산 비용·토큰·도구 수를 재계산했다. 실제 credentials의 문자열 미포함도 검사했다. 소유 서비스 종료 후 포트 18001/19000/55432/56379 해제, 기존 컨테이너 4개·볼륨 2개 보존을 확인했다.

추가 회귀 18개는 합산/단계 귀속, 비용·토큰·호출·도구 한도 소진, 0회 오류/중단 후 재등록, 정책/학습/원장 변경·누락, 한도 변경, 실행 중 artifact 변경, usage 누락 예약, 학습 예산 생략 거절을 검사한다. HTTP 회귀는 기존 포함 39개다. `make check`는 Python 441개·mypy 47소스·ruff·lock·웹 빌드 통과, 기존 TestClient 경고 2개 유지다. 브라우저·AWS·설치·배포·커밋·푸시는 수행하지 않았다.

[B3의 사전 비교 명부·전체 예산·중단/독립 정산](external-comparison-budget.md)도 이어서 검증했다. B0/B1/B2 외부 어댑터와 선언 조건/실제 환경 일치 증거는 남았다. 실제 모델 설정과 Linux 다운로드/설치 허용 대기, CW06 이벤트 기반 재판단, 독립 호스트 재현·관찰·공개 제출도 남았다.
