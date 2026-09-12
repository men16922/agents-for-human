# CW05 준비 — Medusa 고객 어댑터·예산·독립 증거

2026-09-07. 실제 Medusa 2.20.1 Store API에 구매 계약을 연결했다. 주문 ID·고객/run 소유권·가상 예산·불확실한 지급·납품 관측을 구현했다. 이번 판매자 처리는 검증 스크립트의 명시적인 관리자 호출이다. **독립 판매자 worker·구매 HTTP 서버 연결·동결 정책 전이·실제 모델·CW05 전체 완료는 아직 아니다.**

## 실행과 증거

`make commerce`가 준비된 상태에서 별도 터미널에 `make commerce-adapter-smoke`를 실행한다. 검사가 끝나면 첫 터미널의 Ctrl+C로 전용 서비스를 종료한다. `make check`는 외부 HTTP를 호출하지 않으며 별도의 회귀 검사를 수행한다.

- 구현: [gateway.py](../../src/rehearsal/commerce/gateway.py). 고객 자격증명만 받으며 `/store/` 경로만 허용한다.
- 실측: [adapter_smoke.py](../../scripts/commerce/adapter_smoke.py). CW00의 fixture seed를 재사용하고 run별 새 합성 고객·상품·주문을 만든다.
- 보존 증거: [보고서](../../evidence/cw05-medusa/report.json), [실제 관리자 주문 응답과 두 SQLite의 행](../../evidence/cw05-medusa/evidence.json).
- 독립 판정: [medusa.py](../../src/rehearsal/evaluation/medusa.py). gateway를 import하지 않고 별도 입력인 목표·예산과 raw evidence를 대조한다. 외부 주문·capture·납품 수량·로컬 원장 합계·고객·run·기한이 대상이다. 저장된 verdict는 입력으로 사용하지 않는다.
- 회귀 검사: [test_gateway.py](../../tests/commerce/test_gateway.py). 보존한 실제 응답을 변경해 금액·소유권·수령·capture 모순, 중복, 불확실성, 재시작과 동시 예산 예약을 검사한다. 이 mock 검사는 실측과 구분한다.

보고서에는 run ID·Medusa 버전·npm lock·소스·증거 SHA-256이 있다. 전체 실제 HTTP 요청/응답은 해당 `.local/commerce/<run_id>/responses.json`에 남는다. 토큰·비밀번호는 제거하고 인증 헤더를 기록하지 않는다. 상품·주문·기존 데이터 볼륨은 삭제하지 않는다. 실패한 중간 fixture도 Git 제외 로컬 경로와 전용 DB에 남으며, 보존한 보고서는 마지막 통과 실행이다.

## 두 주문 단계와 예산 경계

`get_quotes`는 고객 cart와 배송 방법을 만들고 실제 금액·품목·통화·배송 옵션을 검증한다. `create_order`는 기존 견적을 확인해 **로컬 구매 의도**를 저장한다. Medusa 주문과 지급 승인은 이후 `authorize_payment`의 cart complete에서 함께 생성된다. 연습 세계의 주문 수락 단계와 물리적으로 같은 transaction이라고 주장하지 않는다.

서버가 저장한 금액으로 별도 지급 원장에 예산을 예약하고, 제출 상태를 commit한 다음 payment collection → session → cart complete를 요청한다. 외부 HTTP 요청 동안 열린 SQLite transaction에 의존하지 않는다. 프로세스/스레드 lock으로 같은 run의 구매 작업을 직렬화하고 지급 원장이 `spent + reserved <= budget`을 강제한다. 다른 구매 의도가 같은 quote를 소비하거나 다른 키로 같은 지급을 덮어쓰면 거절한다.

외부 요청 결과가 불확실하면 예산을 유지한다. 같은 고객의 페이지 처리된 주문 목록에서 서버가 생성한 run/quote metadata를 찾고, 단건 응답의 고객·품목·금액·배송 옵션까지 확인한 뒤 외부 ID를 저장한다. `get_payment`와 제출 후 동일 키 재호출은 GET으로만 대조한다. 새 cart나 대체 지급을 만들지 않는다. 관리자 토큰은 고객 어댑터에 없다.

2026-09-08 [오프라인 재고 변경 회귀](medusa-stock-changes.md)에서 제출 후 HTTP 오류도 UNKNOWN으로 반환하도록 보완했다. 제출 전 재고 재조회 거절은 예산을 예약하지 않는다. 이는 보존 응답 재생 결과이며 실제 실행 중 재고 변경 검증은 남았다.

이 보수적인 처리에는 한계가 있다. 제출 상태 저장 후 요청 자체가 전달되지 않았거나 주문 생성 전 중단되면 조회만으로는 완료되지 않고 예산 예약이 남는다. 만료·취소·환급·명시적 같은 cart 재개 절차는 아직 없다. 임의 관리자 cart 변경과 gateway 밖의 구매는 이 가상 예산 경계에 포함하지 않는다.

## 실제 가격·소유권·납품 결과

- A 견적은 텐트 60×3 + 조명 20×6 + 배송 10 = 310. 실제 관리자 상품 가격을 60→100으로 바꾼 뒤 같은 수량으로 cart line을 갱신하자 가격이 재계산됐고 기존 견적은 `STALE_QUOTE`로 거절됐다.
- 가격을 복원하고 새 견적을 구매했다. 실제 cart complete 응답을 받은 직후 테스트 클라이언트에서 버려 `ReadTimeout`을 주입했다. 관측은 `UNKNOWN`, 예산 예약은 310이었다. 실제 TCP 응답 지연 실험과는 구분한다.
- gateway를 새 객체로 열고 GET만으로 기존 주문을 찾아 `RESERVED`를 확인했다. 동일 지급 키 재호출은 같은 지급 ID이며 대체 키는 거절됐다.
- 외부 ID를 구매 도구의 주문 핸들로 사용하거나 다른 run의 로컬 핸들을 제시하면 조회 전에 거절된다. 실제 다른 고객 토큰을 넣어도 `CUSTOMER_SCOPE_MISMATCH`다. Medusa Store API 자체의 공개 단건 조회 동작은 그대로다.
- 남은 예산 190에서 추가 구매 210을 요청하자 외부 payment collection/complete 호출 전에 거절됐다. 오프라인 동시 검사에서는 남은 예산 190에 두 건의 150 요청 중 하나만 예약하고 다른 하나는 거절했다.
- 테스트 판매자가 capture·fulfillment·shipment·delivered를 수행했다. 외부 capture 310·품목별 delivered 수량 3/6과 로컬 spent 310·reserved 0을 대조했다. 반복 조회/재시작에도 수령이 중복되지 않았고 독립 판정은 `COMPLETE`였다.

가격은 견적 수락과 지급 전 cart 갱신 시점에 확인한다. 이후 catalog 변경이 이미 저장된 cart 금액을 자동 변경한다고 가정하지 않는다. Medusa의 [cart 완료 설명](https://docs.medusajs.com/resources/storefront-development/checkout/complete-cart)은 cart snapshot에서 주문·승인 금액이 생성됨을 명시한다. 최종 금액이 예상과 다르면 자동 지급 확정으로 매핑하지 않는다. 자체 세계의 quote version과 Medusa의 최신 가격 경합 보장은 동일하지 않다.

배송 판정은 상태 문자열만 보지 않고 fulfillment의 delivered/canceled 시각과 각 품목의 delivered quantity를 확인한다. 납품 관측 tick은 처음 확인한 시각이므로 지연 관측은 기한 판단에서 보수적이다. manual provider의 기록이며 물리적 배송·수령인 확인·실자금 결제의 증거가 아니다.

## 남은 연결 작업

이후 [구매 HTTP·독립 판매자 연결](medusa-operating.md)에서 A/B/C 견적과 B의 6초 납품 기한·재시작을 검증했다. 실제 외부 재고 변경, F03/F04/F05, 동결 정책 비교와 SSE UI는 남았다. 이 문서의 초기 고객 adapter fixture는 A만 사용하고 기한은 120초다. 여기의 `lead_ticks=2`는 설정값이며 이 초기 검사에서 판매자의 배송 지연 준수를 검사한 것은 아니다.
