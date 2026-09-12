# CW06 — 공급자 재고와 개별 주문 관측

## 읽기 계약

Medusa 2.20.1의 실제 `/store/products` GET에서 `variants[id][]`·region·명시적 fields로 선택한 run의 variant만 조회했다. 설치된 Store products route와 `variant-inventory-quantity.js`도 확인했다. `inventory_quantity`는 publishable key의 판매 채널에서 계산한 가용량이다. 관측 단가는 Store의 `calculated_amount`이며 배송비가 포함된 확정 견적이 아니다. [보존 Store 응답](../../evidence/cw06-catalog-contract/products.json)은 `cw00-d6c09eac6808`의 고객/run 설정으로 읽었다.

`commerce/details.py`는 목표 품목의 최대 100개 variant를 GET으로 읽고, 공급자·품목·가용량·상품 단가·재고 관리/추가 주문 허용 여부만 노출한다. 상품 설명·외부 ID·가격 원문은 전달하지 않는다. 누락/잘못된 가격·통화·재고·플래그는 미확정이며 0이나 무한 재고로 대체하지 않는다. 재고를 관리하지 않는 상품은 수량을 null로 두고 이를 화면에 구분한다.

주문은 선택한 gateway DB의 로컬 ID를 따라 고객 identity·외부 소유권/금액/납품 계약을 확인한다. 최근 50개만 표시하고 전체 개수/잘림 여부를 함께 준다. 외부 ID를 브라우저에서 받아 조회하지 않는다. 주문과 결제 상태는 별도이며, 접수 후 결제 예약이 이미 기록된 경우 RESERVED를 유지한다. 조회 실패는 UNKNOWN이고, 구매·지급 POST를 재실행하지 않는다.

`observe_world(include_details=True)`와 observer 역할의 snapshot, 고객 polling journal/SSE에 `commerce` 봉투를 추가했다. buyer 도구의 기존 기본 snapshot 계약은 유지한다. 외부 호출은 GET만 사용하되, 기존 GET 정합화가 확인한 지급/수령 정보는 로컬 원장에 반영될 수 있다. 여러 Store 조회가 하나의 외부 원자적 snapshot을 구성하는 것은 아니다.

`public_details`와 TypeScript Projection이 run·품목·상태·수량·중복·경계를 검증한다. 카탈로그 조회 실패는 주문을 숨기지 않는다. 지급/수령을 현재 확인할 수 없으면 `receipt_status=UNAVAILABLE`로 표시하여 화면이 0개 수령으로 오해되지 않게 한다. 이때 현재 관측과 독립 증거의 일치 판정도 보류한다. 연결 끊김·이전 버전 복구는 기존 SSE 규칙을 따른다.

## 화면과 실제 실행

지도 공급자 노드에 관측 재고를 표시하고, 별도 표에는 상품 단가와 재고 상태를 표시한다. 실행 주문에는 품목·금액·납품/지급 상태·접수 tick·로컬 ID가 있다. 지도 연결선은 구조를 뜻하며 실제 주문 경로라고 표시하지 않는다.

`make commerce-observer-smoke`의 최종 `cw00-e321e1e78fd9`는 PASS다. 실제 A 텐트 재고 10→0을 브라우저가 cursor 1→2에서 확인한 뒤 기존 견적 주문 거절을 검사했다. B 구매 후 화면에서 텐트/조명 재고 7/4·납품 확인·정산 완료·수령 9·지출 380·예약 0을 확인했다. 서버 중단/커서 복구와 독립 export 재검증 UI도 통과했다.

[보고서](../../evidence/cw06-commerce-details/observer-report.json)·[초기 화면 값](../../evidence/cw06-commerce-details/browser/initial.json)·[재고 변경](../../evidence/cw06-commerce-details/browser/stock-change.json)·[납품 화면 값](../../evidence/cw06-commerce-details/browser/received.json)·[영속 journal 최신 이벤트](../../evidence/cw06-commerce-details/journal-latest.json)·[1440px](../../evidence/cw06-commerce-details/browser/evidence-1440.png)·[390px](../../evidence/cw06-commerce-details/browser/evidence-390.png)를 보존했다. 납품 중 `EXTERNAL_DELIVERY_MISMATCH` 1회는 기존 제한 GET 재조회로 정상 관측됐으며, 구매/결제 재요청은 없다. 해당 오류가 없어졌다고 주장하지 않는다.

실행 후 mypy의 중첩 dict 추론 오류를 고치기 위해 `result: Json` 타입 선언만 추가했다. [전후 소스 hash](../../evidence/cw06-commerce-details/post-live-type-check.json)와 정확히 그 선언만 다른지 대조했다. 실행 로직은 동일하다. 원장 COMPLETE 재판정·증거/소스 hash·이번 fixture 토큰 미포함을 확인했다.

## 검증과 다음 단계

`make check` PASS: Python 274·mypy 39소스·ruff·lock·웹 빌드. 세부 관측 회귀 19개는 보존 실제 응답, GET-only 동작, journal whitelist/Projection, 카탈로그 실패·주문 미확정·고객 불일치·범위/수량 변조·접수 시 예약/미지급·최근 50개 경계를 검사한다. `make check-browser` PASS: 기존 12개와 세부 관측/미확정 UI 1개, 320/390/1440px overflow 검증. 모델/AWS·실자금·배포·커밋·푸시 없음. 전용 서비스 종료·포트 6개 반환·볼륨 2개/기존 컨테이너 4개 보존을 확인했다.

후속 [지연 계측](observation-latency.md)에서 Store 조회 시작/소요 시간, 관측 생성·게시·브라우저 수신/반영과 지연·중복·재접속·누락/시계 차이 분모를 보존했다. 많은 주문에서 순차 HTTP 조회가 오래 걸릴 수 있으며 현재 처리량·지연 목표 달성은 미검증이다. 실제 모델 재계획·학습된 정책 전이·동시 재고 경합도 별도다.
