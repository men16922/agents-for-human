# 모델 실행 계측과 Medusa HTTP 연결

2026-09-09. 합성 World 전용이던 모델 실행 경로에 별도의 구매 HTTP 실행자를 추가했다. 실제 Medusa 검증에는 **결정론적 Strands SDK provider fixture**를 사용했다. 실제 모델 판단이나 학습 정책 전이는 아직 검증하지 않았다.

## 구현과 권한

[HTTP 실행자](../../src/rehearsal/commerce/model_runner.py)는 기존 구매 도구 8개·동결 정책 프롬프트·raw-provider 사용량 원장·호출/토큰/도구/비용 상한을 사용한다. 구매자 토큰·run ID·기대 목표/예산·정책 경로만 설정으로 받는다. 고객 원장 DB, 관리자/판매자 토큰, 임의 외부 origin은 받지 않는다. CLI origin은 `http://127.0.0.1:18001`로 고정했다.

시작 전 목표·예산·run·운영 시계를 대조하고 기존 지출/예약/수령 또는 지난 기한이 있으면 모델 호출 전에 거절한다. POST 전에는 같은 계약의 snapshot을 재확인한다. 이 GET은 범위 대조이며 견적 선택·대체 구매를 대신하지 않는다. 모델 도구 수와 별도로 횟수를 기록한다. 도구 실행 전 소스/명세 변경도 차단한다.

CLI의 기록 경로는 `.local/commerce-model/<run_id>`다. 이미 존재하는 실행 디렉터리는 재사용하지 않는다. 중단/오류/usage 누락의 예약을 유지하며 자동 모델 재호출·추가 지급·예약 해제를 하지 않는다. SDK 종료·원장 완료·실제 모델 효과는 서로 다른 결과다.

## 실행 종료와 거래 증거의 분리

실행 보고서는 항상 `transaction_status=NOT_VERIFIED`, `success=false`로 남는다. `runtime_accounted`는 SDK 종료와 사용량 기록 상태만 뜻한다. 독립 판정은 원장 export를 별도로 선택한 뒤 `--attest`로 수행한다.

후속 판정은 실행 spec/report/tool trace hash, 기대 목표/예산/run, 선택 export hash와 원장을 대조한다. 외부 원장에 있는 구매 ID가 실행 도구의 create_order 응답 ID와 정확히 일치해야 한다. 다른 실행의 완성된 주문을 같은 run의 성과로 끼워 넣으면 `orders_match_execution=false`다. 잘린 최종 응답은 원장이 COMPLETE여도 실행 성공으로 승격하지 않는다.

로컬 manifest/hash는 변경 탐지 수단이며 외부 서명이나 저장소 관리자의 악의적 동시 변조를 방지하는 인증 수단은 아니다. CLI 실행 종료 코드 0도 거래 완료를 뜻하지 않으므로 출력의 NOT_VERIFIED를 확인한다.

## 검증 결과

`make commerce`를 기동한 상태에서 `make commerce-model-smoke`를 실행했다. [검사 스크립트](../../scripts/commerce/model_smoke.py)는 새 Medusa fixture와 별도 seller/gateway를 준비한다. 모델에는 구매자 권한만 주고, 독립 운영자가 지급 응답을 1.2초 지연시켰다. 구매 HTTP timeout은 지급 요청에서만 0.4초로 제한했다.

| 항목 | 실제 기록 |
|---|---|
| Medusa fixture | `cw00-670ce8b66bc3` |
| SDK fixture 호출 / 토큰 / 도구 | 14 / 280 / 13 |
| 추가 계약 확인 GET / 전체 구매 HTTP 요청 | 8 / 23 |
| 가상 모델 비용 | 392 micro-USD |
| 지급 요청 | 1회, ReadTimeout → UNKNOWN |
| 독립 원장 | COMPLETE, 집행 310, 예약 0, 텐트 3·조명 6 |
| 실행 주문과 원장 주문 | 일치 |
| 실제 모델/AWS 호출 | 0 |

[실행 보고서](../../evidence/cw05-metered-http/execution/report.json)는 미검증 상태이며, [별도 판정](../../evidence/cw05-metered-http/attestation.json)이 거래 완료를 확인한다. [구매 HTTP](../../evidence/cw05-metered-http/buyer-http.jsonl), [raw 원장](../../evidence/cw05-metered-http/evidence.json), [artifact manifest](../../evidence/cw05-metered-http/artifact-manifest.json)에 11개 artifact와 소스 46개 hash 대조·정리 결과를 보존했다. 복사본에서 다시 독립 판정했으며 실제 토큰이 보존 파일에 없음을 대조했다.

전용 회귀 21개로 실행/판정 분리·계약 변경·기존 실행 거절·사용량 누락·한도·잘린 응답·입력/증거 변경·다른 주문 attribution·buyer-only 설정과 무호출 preflight를 검사했다. `make check`는 Python 412개·mypy 46소스·ruff·lock·웹 빌드를 통과했다. 기존 TestClient 경고 2개는 유지된다. 브라우저 gate는 이번에 실행하지 않았다. 초기 회귀의 비용 예상값 364는 fixture가 기본 3회 대기를 사용한다는 점을 놓친 테스트 오류였고, 원본 14호출·392로 대조 후 수정했다.

검사 후 소유한 gateway/seller/Medusa/전용 Compose 서비스를 종료했다. 포트 18001/19000/55432/56379 반환과 기존 컨테이너 4개·전용 볼륨 2개 보존을 확인했다.

## 실제 모델 실행 입력과 남은 연결

아래는 이미 새 Medusa gateway를 준비한 운영자가 만드는 **Git 제외 설정**의 형식이다. 실제 buyer 토큰은 `.local/`의 0600 파일에만 넣는다. 원래 다중 역할 credentials.json 전체를 실행자에 넘기지 않는다.

```json
{
  "run_id": "fresh-medusa-run-id",
  "buyer_token": "",
  "expected_goal": {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
  "expected_budget": 500,
  "policy_path": "policy.json"
}
```

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --config .local/commerce-model-config.json
# Explicit paid execution after model ID, official rates and budget are ready:
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --config .local/commerce-model-config.json --execute
# Read-only: reuse the existing independent export-selection schema.
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --attest .local/commerce-model/fresh-medusa-run-id --evidence-selection .local/selected-export.json
```

preflight는 설정만 검사하며 HTTP/AWS client를 만들지 않는다. 거래 운영 시계는 모델 설정을 기다려주지 않으므로 실제 실행 설정을 준비한 뒤 새 외부 run을 만들어야 한다. 현재 `commerce-model-smoke`는 SDK fixture 실행과 서비스 정리까지 수행하는 검사다. 서비스 유지와 buyer-only 설정/동결 입력 전달은 [별도 세션 CLI](model-session.md)로 연결하고 실제 Medusa에서 검증했다. 실제 모델 사용은 설정 후 별도 실행한다.

이 경로의 모델 예산은 외부 실행 한 번의 예산이다. B3의 학습 비용과 합친 정식 E2 비교, 관측 큐를 통한 이벤트 기반 재판단, 미공개 평가·실제 모델 전이·분산 경합은 남았다. Linux 공개 의존성 설치는 별도로 자동 승인 거절 뒤 허용 응답 대기 중이다.
