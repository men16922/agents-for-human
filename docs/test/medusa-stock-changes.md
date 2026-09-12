# CW05 — 실행 중 재고 변경의 오프라인 계약

2026-09-08. 오프라인 회귀 이후 실제 Medusa 재고 변경과 스크립트의 대체·부분 조달까지 검증했다. **모델 재계획·학습된 정책 전이는 미검증이다.** 후속 [두 구매자 재고 경합](concurrent-stock-race.md)은 단일 Medusa 프로세스의 checkout 중첩·단일 납품·패자 UNKNOWN 예약을 검증했다. 분산/임의 경합 순서의 원자성은 미검증이다. [재개 계획](../plans/2026-09-06-custom-world-poc-plan.md)의 1~3번 중 제출 전 두 변경 시점의 실제 검사를 마쳤다.

## 응답 근거와 재현 범위

[CW00 보존 응답](../../evidence/cw00/2026-09-07-medusa-contract.json)에는 텐트 100개 추가 요청의 HTTP 400과 `code=insufficient_inventory`가 있다. [CW05 보존 증거](../../evidence/cw05-medusa/evidence.json)의 cart/order 구조와 이 오류 응답을 `httpx.MockTransport`로 재생한다. 실제 `StoreAPI`→gateway→임시 SQLite 원장 경로를 사용하며 소켓이나 모델 API를 호출하지 않는다.

시점과 재고 감소는 테스트가 통제한다. 특히 payment collection/session/complete에 400을 주는 사례는 제출 이후 오류 처리 검사를 위한 합성 주입이다. 실제 Medusa가 해당 시점에 같은 재고 오류를 반환했다는 기록이 아니다. 재고 복원 후의 주문·납품 응답과 뒤늦은 주문 관측도 보존 구조를 사용한 fixture이며 새 외부 거래 증거가 아니다.

## 확인한 경계

| 오류 시점 | 구매·지급 상태 | 예산과 다음 호출 |
|---|---|---|
| 견적 후 `create_order` 재조회 | 로컬 구매 의도 생성 전 거절 | spent/reserved=0/0, 외부 지급 요청 없음 |
| 수락 후 `authorize_payment` 재조회 | 구매는 ACCEPTED, 지급 intent 없음 | spent/reserved=0/0, 재고 복원 후 같은 구매 키로 진행 가능 |
| SUBMITTED 저장 후 collection/session/complete 오류 | 구매는 SUBMITTED, 도구 관측 UNKNOWN | spent/reserved=0/310, 재시작·동일 키 재호출은 GET 대조만 수행 |
| 제출 후 주문 조회 HTTP 오류 | UNKNOWN과 정제된 HTTP 오류 코드 | 예약 유지, 원문 외부 진단은 전달하지 않음 |
| 기존 주문이 뒤늦게 검증 가능한 상태로 조회됨 | 같은 주문·intent를 대조해 SETTLED | spent/reserved=310/0, 반복 조회에도 정산·수령 중복 없음 |

재고가 복원돼도 제출 후 UNKNOWN을 새 지급으로 덮지 않는다. 남은 예산 190에 310짜리 대체 구매를 지급하려 하면 `BUDGET_EXCEEDED`로 거절하며 기존 예약은 유지한다. 고객·금액 등 구조화 증거의 모순은 별도 계약 오류로 남기고 UNKNOWN으로 숨기지 않는다.

## 진단·수정·검증

최초 새 회귀 7개 중 제출 이후 HTTP 오류 3개가 실패했다. 원인은 `StoreAPI`가 HTTP 실패를 일반 `ContractError`로 올리고, `authorize_payment`는 전송 오류만 UNKNOWN으로 변환했기 때문이다. 이때 원장에는 SUBMITTED와 예약 310이 남지만 구매 도구에는 일반 거절이 전달됐다.

[gateway](../../src/rehearsal/commerce/gateway.py)에 `MedusaHTTPError`를 두어 외부 HTTP 실패와 로컬 원장/소유권 오류를 구별했다. 제출 이후 오류와 지급 조회 HTTP 실패는 UNKNOWN 및 `MEDUSA_HTTP_<status>`로 반환한다. 제출 전 재고 거절과 로컬 계약 오류는 기존 거절을 유지한다. 예산을 해제하거나 checkout을 자동 재시도하지 않는다.

[회귀 검사](../../tests/commerce/test_stock_changes.py) 13개 PASS: 두 품목×제출 전 두 시점, 제출 후 400 세 시점·timeout·비주문 응답, 재시작·다른 키 거절·대체 구매 예산 제한, 뒤늦은 단일 정산, 조회 실패, 고객/금액 모순. 최종 `make check` PASS(Python 191개·mypy 34개 소스·ruff·lock·웹 빌드). 기존 TestClient deprecation 경고 2개는 남았다.

## 남은 작업

제출 상태만 남고 외부 주문이 없는 경우 예약을 자동 해제할 수 없다. 명시적 재개·취소·만료 계약은 여전히 미구현이다. 오류 코드 하나로 여러 외부 요청이 모두 rollback됐다고 판정하지 않는다.

초기 오프라인 작업에는 서비스 기동이 없었다. 아래 후속 실제 검사는 전용 서비스를 기동해 수행했다. 모델 설정이 준비되면 CW03 실제 호출을 우선한다.

## 실제 Medusa에서 발견한 추가 문제와 수정

`make commerce-stock-smoke`의 최초 실행 `cw00-aeeca4b1ee7f`는 첫 품목 텐트 감소는 거절했지만 조명 감소를 지급 전에 잡지 못했다. 구매는 SUBMITTED, spent/reserved=0/310이 남았다. [실패 보고서](../../evidence/cw05-stock/initial-failed-report.json)를 보존했다. 해당 실패 보고서에는 실행 소스 hash가 없으며 원본 상세 상태는 Git 제외 실행 디렉터리에 남는다.

설치된 Medusa 2.20.1의 `update-line-item-in-cart` workflow는 갱신한 품목만 inventory confirmation에 전달한다. 기존 gateway는 첫 line만 갱신했다. 오프라인 fixture는 한 line 갱신으로 모든 품목을 검사해 이를 놓쳤다. fixture를 실제 범위에 맞추자 기존 회귀 2개가 실패했고, gateway가 모든 line을 순차 재확인하도록 수정한 뒤 통과했다. 이는 외부 지급 제출 전 검사이며 최종 checkout과의 원자적 재고 예약을 보장하지 않는다.

## 실제 실행 결과

새 실행 `cw00-6c9d582acfa3`에서 [검사 스크립트](../../scripts/commerce/stock_smoke.py) PASS. [보고서](../../evidence/cw05-stock/stock-report.json)·[관리자 요청/응답](../../evidence/cw05-stock/responses.json)·run별 원장 export를 보존하고 소스/증거 hash를 대조했다.

- 견적 후 A 텐트 10→0: 이전 견적 주문 거절, 예산 예약 0. B 대체 구매 380, 텐트 3·조명 6 수령, 독립 COMPLETE.
- A 텐트 복원 후 다른 고객의 주문 수락→A 조명 10→0: 지급 전 거절, intent 없음·예약 0. A 텐트 190 + C 조명 225 = 415 부분 조달, 독립 COMPLETE.
- 구매 서버 재시작 후 두 run의 잔액·수령 상태 일치. 별도 판매자 작업 12개 OBSERVED, 최종 외부 예약 수량 0. 다른 고객과 공유하는 공급처 재고 감소도 실제 조회했다.

이 결과는 알려진 조건의 스크립트 구매이며 모델이나 B0 동결 정책의 개선 결과가 아니다. 최초 실패의 미확정 예약을 자동 해제하지 않았고 새 fixture에서 재검증했다. AWS·모델 호출·설치·커밋·푸시 없음. 전용 프로세스/DB 종료·포트 반환·볼륨 보존 확인.
