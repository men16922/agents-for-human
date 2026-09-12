# Medusa 납품 전환 중 불완전한 조회를 UNKNOWN으로 유지

2026-09-09. [시간표 이벤트 검사](timed-condition-events.md)에서 B0가 `EXTERNAL_DELIVERY_MISMATCH`로 중단됐지만 종료 후 독립 원장은 COMPLETE 310이었다. 실제 Store GET을 수집해 원인을 확인하고, 관측이 완성될 때까지 같은 주문을 조회하도록 수정했다.

## 실제 응답으로 확인한 원인

새 Medusa 주문의 납품 전후를 네 독립 Store 소비자로 수집했다. 총 1,286개 GET 중 6개에서 `fulfillment_status=delivered`와 fulfillment의 `delivered_at`은 설정됐지만 tent/light의 `delivered_quantity`는 모두 0이었다. 같은 응답에서 품목 수량·fulfilled/shipped 수량은 각각 3/6이었다. 뒤이어 일관된 납품 응답 6개를 확인했다.

불일치 응답들의 요청 시작부터 종료까지 관측 구간은 약 72.4ms였다. 이는 수집 요청들의 범위이며 전환 상태의 정확한 지속 시간이나 서비스 지연 목표 실측은 아니다.

설치된 Medusa 2.20.1의 `@medusajs/core-flows/dist/order/workflows/mark-order-fulfillment-as-delivered.js`도 이 순서를 보여 준다. fulfillment 납품 workflow를 실행한 뒤 주문 품목 수량을 기록하는 `registerOrderDeliveryStep`을 실행한다. 두 단계 사이 GET이 전체 상태의 원자적 snapshot이라는 보장은 없다. 실제 응답을 그대로 재생했을 때 수정 전 payment/order/snapshot 조회와 기존 지급 정산 유지 검사 4개가 실패했고, 모두 `EXTERNAL_DELIVERY_MISMATCH`였다.

## 변경한 판정과 유지한 거절 조건

gateway는 아직 수령을 기록하지 않은 주문에서 다음 조건을 모두 만족하면 `EXTERNAL_DELIVERY_PENDING`을 관측 미확정으로 구별한다.

- 단일 fulfillment에 shipped/delivered 시각이 있고 취소되지 않았다.
- 품목별 fulfilled/shipped 수량은 주문 수량과 같다.
- 납품 수량은 0 이상 주문 수량 이하이나 아직 모든 품목의 수량이 일치하지 않는다.
- 기존 고객/run·견적·품목·금액 검사를 통과했다.

payment와 order GET은 이 경우 UNKNOWN을 반환한다. snapshot도 예외로 중단되지 않으며 수령을 새로 기록하지 않는다. 이미 기록된 지급 정산을 되돌리거나 미확정 예약을 해제하지 않는다. 구매자는 같은 주문/지급을 다시 조회할 수 있고, 서버는 추가 checkout을 수행하지 않는다. 수량까지 일치하는 뒤의 응답을 확인한 뒤에만 수령을 한 번 기록한다.

이미 수령이 확인된 주문의 수량 역행, 취소·납품 시각 부재, 미출고 수량, 음수/초과 수량, 금액·고객 모순은 계속 거절한다. 광범위한 계약 오류를 자동 재시도로 바꾸지 않았다. 판매자 구현이나 실제 모델 정책도 변경하지 않았다.

## 수정 전후 검증

같은 보존 응답을 사용하는 회귀 12개는 수정 전 4실패/8통과에서 수정 후 12통과로 바뀌었다. 기존 gateway·재고 회귀를 포함한 59개도 통과했다. 예약 310 유지, 이전 SETTLED 유지, 후속 GET의 단일 수령/정산, 쓰기 HTTP 미발생, 모순 거절을 검사한다.

`make commerce-delivery-smoke`도 실제 Medusa에서 PASS다. 배치 `delivery-fixed_e977a53818c945f8a844925216dd3aa5`에서는 373회의 gateway 지급 조회 중 전환 상태 1건이 UNKNOWN이었고, 예산 불변·수령 미기록을 확인했다. 후속 일관된 응답 뒤 독립 COMPLETE 310·예약 0이었다. checkout은 1회였으며 이후 provider 요청은 GET뿐이었다. 이 검사는 adapter를 직접 호출했고 실제 provider HTTP와 독립 판매자를 사용했다.

기존 `make external-events-smoke`도 새 동결 명부로 다시 실행해 PASS다(`events_71ad9e676aa14db78b28b441908cd54a`). 시간표 B0 `cw00-f1fac002f940`은 COMPLETED/독립 COMPLETE 380, 미발생 일정 B0 `cw00-be8fd2089495`는 COMPLETED/독립 COMPLETE 310이었다. 이벤트 일치는 각각 true/false로 유지됐다. SDK `cw00-377513a9406c`의 오래된 견적 선택 실패·사용량 미확정은 그대로다. 전체 8칸 중 결합 VERIFIED 2·INCOMPLETE 1·NOT_RUN 5이며, 가상 비용 224/미확정 예약 99,776 micro-USD도 보존했다.

[보존 manifest](../../evidence/cw05-delivery-transition/artifact-manifest.json)는 84개 artifact와 별도 manifest를 포함한다. 실제 전환 GET·전후 source/diff·동일 입력 회귀 로그·수정 후 provider 관측·재실행 명부/원장/trace·독립 재집계를 보존했다. 초기 수집과 수정 후 실행의 두 원장 및 이벤트 세 실행을 독립 재판정했다. 소스 50개 hash와 실제 자격증명 미포함을 대조했다. 포트 18001/19000/55432/56379를 반환했고 기존 컨테이너 4개·볼륨 2개를 보존했다.

전체 `make check`는 Python 547개·mypy 50소스·ruff·lock·웹 빌드 PASS다. 기존 TestClient 경고 2개가 유지된다. 실제 모델·브라우저·AWS·설치·커밋·푸시는 수행하지 않았다.

## 범위와 다음 작업

이 수정은 실제 포착한 Medusa 납품 전환의 불완전한 읽기를 처리한다. 모든 외부 API의 일관성, 분산 경합, 실제 모델의 복구 판단을 증명하지 않는다. 후속 [지급 응답 지연/타임아웃](scheduled-response-loss.md) 일정은 실제 검증했다. 다음은 알림 지연/중복·재전송 일정 연결이다. SDK fixture의 오래된 견적 선택 실패와 실제 모델 기반 재계획은 별도로 남아 있다.
