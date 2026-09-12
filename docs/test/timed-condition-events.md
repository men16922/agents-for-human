# 실행 중 가격·재고 변경을 선언하고 실제 발생을 검증

2026-09-09. [정적 초기 조건](static-initial-conditions.md)에 시간표가 있는 가격·재고 변경을 연결했다. 구매자와 별개인 세션 제어자가 새 fixture에만 변경을 적용한다. 초기 조건·이벤트 발생·거래 성공·모델 사용량을 따로 판정한다.

## 선언과 실행 경계

조건 JSON의 `events`는 1~8개다. 각 항목은 아래 필드만 허용한다. ID는 고유한 ASCII 영숫자이며 시각은 엄격한 오름차순이다. 허용 지연은 0~5tick이고 예정 시각과 지연 한계 모두 거래 마감 전이어야 한다.

```json
{"id":"priceA","at_tick":10,"max_lateness_ticks":3,"kind":"price","supplier":"A","item":"tent","value":100}
```

`kind`는 `price` 또는 `stock`, 대상은 A/B/C의 tent/light다. 가격은 양의 정수, 재고는 0 이상의 정수다. 지급·알림 유실·설명 문구 등 다른 이벤트는 지원하지 않는다. 빈 배열과 알 수 없는 필드도 세션 생성/학습 전에 거절한다. 초기 관측과 실행 시작은 첫 이벤트보다 앞서야 한다.

세션의 독립 1초 시계가 예정 시각에 도달하면 제어자가 `event-<id>.json`에 CLAIMED를 배타적으로 생성하고 fsync한 뒤 HTTP 작업을 시작한다. 이미 파일이 있으면 다시 실행하지 않는다. 응답 유실·예외는 UNKNOWN, 시작 시 허용 시각을 넘겼으면 MISSED다. 중단 직후 CLAIMED만 남아도 자동 재시도하지 않는다. 이 구현은 세션당 한 제어자용이며 분산 스케줄러나 프로세스 복구 재실행을 제공하지 않는다.

가격 변경은 정확한 product/variant에 단일 USD 가격을 POST한다. 재고 변경은 한 inventory item의 한 location만 대상으로 하며, 변경 전 예약 수량이 있으면 거절한다. 원시 variant GET으로 구매자에게 보이는 variant와 관리자 변경 대상의 관계를 대조한다. 구매 도구에는 관리자 자격증명이나 이벤트 적용 기능을 추가하지 않았다.

## 원시 응답과 독립 정산

이벤트마다 변경 전후 구매자 snapshot·Store catalog GET·관리자 variant GET·정확한 POST 요청/응답을 보존한다. 재고 이벤트는 전후 inventory location GET도 보존한다. 독립 검증기는 다음을 확인한다.

- 선언 hash·run·목표·외부 시계, 예정 시각부터 허용 지연 안에 끝난 수집 구간.
- 정확한 variant·USD 가격·재고 관리/backorder 설정, 변경 전 값과 실제 변경 후 값.
- 관리자 variant와 inventory의 1:1 관계, 정확한 location, 전후 예약 0, 관리자 재고와 구매자 관측의 일치.
- 선언과 같은 POST 대상/본문, HTTP 200, 초기 관측 이후이며 최종 export 이전인 발생 시각.
- 구매 실행의 초기 snapshot과 종료 관측 사이에 이벤트가 발생했는지 여부.

초기 검증기의 `event_conditions_supported: false`는 정적 초기 관측 범위를 유지한다. 이벤트 발생 여부는 별도 `event_review`로 판정한다. 최종 export의 `condition_events`에는 미실행·미확정 이벤트도 포함한다. 전체 이벤트 ID 집합이 달라지면 증거를 거절한다. 거래가 완료돼도 이벤트가 발생하지 않았으면 조건 일치는 false다. 모든 사용량이 확정됐다면 이런 조건 미달성 때문에 모델 비용을 계속 예약하지 않는다. 사용량 미확정은 기존 공통 원장 규칙에 따라 예약을 유지한다.

범위는 `timed-provider-change-observations-not-atomic-isolation`이다. 여러 HTTP의 원자적 격리, 모든 외부 변경의 부재, 실행 중 모델 재계획이나 학습된 정책 효과를 보장하지 않는다. 다른 이벤트 종류와 실제 모델 검증은 남았다.

## 실제 검사와 발견한 SDK fixture 한계

`make commerce`와 `make external-events-smoke`를 사용한다. 정상 초기 조건에 A tent 가격 60→100을 10tick, A light 재고 10→0을 12tick에 선언했다. 두 번째 견적 요청만 15tick까지 늦추는 테스트 전용 HTTP 일정으로 첫 A 견적 이후의 변경을 관찰했다. 이 지연 기능은 운영 구매자에 포함되지 않는다.

최초 실행에서 B0는 갱신된 견적으로 B를 구매해 COMPLETE 380이었다. B1의 SDK fixture는 A 재견적의 HTTP 400 뒤에도 예전 A 310 견적을 선택했다. 주문도 거절되자 없는 주문 ID를 읽다가 실패했다. 독립 원장은 INCOMPLETE 0/예약 크레딧 0이었고, 마지막 SDK 호출은 사용량 미확정이었다. 이 실패는 실제 모델의 판단 결과가 아니다.

후속 검사는 이 알려진 실패를 유지하면서, 실행보다 늦은 50/52tick 일정의 미발생도 확인했다. 최종 `make external-events-smoke`는 PASS다. 배치 `events_7d6c250bf3034d9d9966a31761cc6618`는 두 조건 × 네 방식 = 8칸을 사전 고정했으며 3칸을 실행하고 5칸은 NOT_RUN으로 남겼다.

| 조건/방식 | 세션 | 실행 종료 | 독립 거래 원장 | 이벤트 관측 | 조건 일치 |
|---|---|---|---|---|---|
| 10/12tick B0 | `cw00-83d248294713` | COMPLETED | COMPLETE 380 | 2/2 | true |
| 50/52tick B0 | `cw00-866246a1e7ee` | INCOMPLETE | COMPLETE 310 | 0/2 | false |
| 10/12tick B1 SDK | `cw00-0f039b1d3ad1` | ERROR | INCOMPLETE 0 | 2/2 | true |

50/52tick B0는 납품 전환 부근 `EXTERNAL_DELIVERY_MISMATCH`로 실행을 멈췄다. 종료 관측과 독립 export에서는 납품 완료였지만 실행 상태를 소급해 성공으로 바꾸지 않았다. 따라서 배치의 결합 판정은 EXTERNAL_VERIFIED 1·EXTERNAL_INCOMPLETE 2·NOT_RUN 5다. `external_transaction_verified`는 기존 배치의 실행/원장 결합 필드이며 raw 원장의 COMPLETE 수와 같지 않을 수 있다. 후속 [납품 전환 진단/수정](delivery-transition.md)에서 실제 중간 상태를 포착하고 UNKNOWN 처리·같은 주문 재조회로 복구를 검증했다. 이 표의 이전 실행 결과는 유지한다.

최종 세 세션의 도구 admission은 24/17/8회로 총 49회다. B0 모델 호출은 0회다. B1 SDK는 9회 admission 중 8회만 usage를 기록해 160토큰·가상 224 micro-USD를 집계했고, 마지막 호출은 ERROR/사용량 미확정이다. 배치는 전체 칸 상한의 잔여 99,776 micro-USD를 예약한 채 다음 B2 학습을 `UNRESOLVED_USAGE`로 거절했다. 이 금액은 실제 API 청구나 실제 모델 비용이 아니다.

앞선 세 번의 실패도 보존했다. 최초 검사는 SDK fixture를 성공으로 예상했던 단정에서, 두 번째는 실행과 원장 성공을 같게 예상했던 단정에서 멈췄다. 세 번째는 차단 오류를 `UNRESOLVED_ATTEMPT`로 예상했지만 실제 `UNRESOLVED_USAGE`를 받아 멈췄다. 스모크의 기대값을 실제 계약에 맞춰 교정했으며 구매 실행자나 SDK fixture의 실패를 성공으로 바꾸지 않았다. 각 명부와 사용량 예약은 그대로 남겨 두었고, 이전 실행을 최종 배치의 분모에 섞지 않는다.

[보존 manifest](../../evidence/cw07-timed-events/artifact-manifest.json)는 최초 세 실패와 최종 실행의 229개 artifact, 별도 manifest를 포함한다. 총 10세션의 초기/이벤트/최종 증거·4개 명부 SQLite·독립 재집계·도구 trace·실행 소스·로그를 보존했다. 소스 50개 hash·세션 제어자 hash·실제 자격증명 미포함을 대조했다. 전용 서비스와 포트 18001/19000/55432/56379를 종료/반환했고 기존 컨테이너 4개·볼륨 2개를 보존했다.

추가 회귀 37개는 선언/HTTP/시각/재고 mapping 변조, 미실행/미확정 분모, 배타적 claim과 실패 후 무재시도, 필수 초기 증거, 사용량 확정 시 조건 미달성과 비용 정산의 분리를 검사한다. `make check`는 Python 535개·mypy 50소스·ruff·lock·웹 빌드 PASS이며 기존 TestClient 경고 2개가 유지된다. 브라우저·실제 모델·AWS·설치·커밋·푸시는 수행하지 않았다.

## 재개 방법

[초기 조건 세션/배치 명령](static-initial-conditions.md)의 `--case`에 위 `events`를 포함한 명세를 전달한다. 세션의 `--serve` 루프가 일정을 처리하며 `--conditions`로 첫 이벤트 이전의 초기 증거를 실행에 고정한다. 세션을 종료한 뒤 기존 export/selection으로 독립 정산한다. 이벤트 적용 성공을 확인하려면 세션 상태가 아닌 보존된 원시 증거와 배치 조건 판정을 읽는다.
