# CW00 — Medusa 거래 계약 실측

2026-09-07. Medusa 2.20.1의 로컬 HTTP 거래 계약 spike 완료. 자체 월드·모델 실행·동결 정책 전이(E2)는 아직 수행하지 않았다. 수동 지급 제공자 `pp_system_default`, 배송 제공자 `manual_manual`을 사용했으며 실제 자금·배송은 없다.

## 재현과 증거

터미널 1에서 `make commerce`, 준비 후 터미널 2에서 `make commerce-contract`. 종료는 터미널 1의 Ctrl+C다. 실행마다 `cw00-<id>` 판매자·고객·판매 채널·상품·주문 fixture를 추가하고 기존 자료와 볼륨을 보존한다. 공유 합성 미국 리전 하나를 재사용한다. 설치·계정·카탈로그는 테스트 운영자 권한이며 구매 도구가 아니다.

- 실행 코드: [contract_spike.py](../../scripts/commerce/contract_spike.py).
- 고정 실행: `cw00-99192f3a1b7d`, [실제 HTTP 요청·응답 JSON](../../evidence/cw00/2026-09-07-medusa-contract.json). 비밀번호·토큰은 제거했고 synthetic 주소·ID는 보존했다.
- 실행별 전체 응답은 `.local/commerce/<run_id>/responses.json`, CLI 진단은 같은 폴더의 `bootstrap.log`. 인증 헤더는 수집하지 않는다.
- 증거에는 코드·npm lock SHA-256, 설치 버전, UTC 시작 시각과 요청별 역할·경로·상태·응답이 있다. `passed`는 이 코드의 계약 assertions가 통과했다는 뜻이다.
- `make check`에는 서버 호출을 넣지 않는다. 별도 명령의 실패는 그대로 실패로 반환된다.

## 수작업 정답과 실제 결과

텐트 60 × 3 + 조명 20 × 6 + 배송 10 = **310**. 통화 필드는 Medusa의 `usd`지만 이번 데이터는 무료 합성 단위다. 센트로 다시 나누거나 크레딧의 현금 가치를 주장하지 않는다. 초기 재고 각 10에서 납품 후 텐트 7·조명 4, 예약 0을 실제 재고 API로 확인했다.

| 관측 시점 | `status` | `payment_status` | `fulfillment_status` | 자체 계약 의미 |
|---|---|---|---|---|
| payment session 생성 | 주문 생성 전 | session `pending` | 없음 | 지급 준비; 예산 예약의 증거는 아님 |
| cart complete | `pending` | `authorized` | `not_fulfilled` | 주문 수락·지급 승인; 아직 확정/수령 아님 |
| 판매자 capture | `pending` | `captured` | `not_fulfilled` | `SETTLED` / `PAID`에 대응하는 합성 지급 확정 |
| fulfillment 생성 | `pending` | `captured` | `fulfilled` | 배송 준비 / `FULFILLING` |
| shipment 생성 | `pending` | `captured` | `shipped` | 발송; 수령 아님 |
| mark-as-delivered | `pending` | `captured` | `delivered` | 테스트 판매자의 납품 기록 / `DELIVERED` |

`order.status=pending`은 거래 실패나 미배송을 뜻하지 않는다. 목표 판정은 지급·fulfillment·품목 수량과 기한을 별도로 대조해야 한다. manual provider의 delivered는 실제 수령인의 독립 확인을 증명하지 않는다.

## 권한 실측

| 요청 | 구매 고객 | 비로그인 + publishable key | 다른 고객 | 판매자 |
|---|---|---|---|---|
| `GET /admin/orders` | 401 | 401 | 미검사 | 200 계열 관리자 경로 사용 |
| `POST /admin/payments/:id/capture` | 401 | 미검사 | 미검사 | 200 |
| `POST /admin/orders/:id/fulfillments` | 401 | 미검사 | 미검사 | 200 |
| `GET /store/orders` | 자신의 주문 포함 | 401 | 대상 주문 없음 | 구매 권한으로 사용하지 않음 |
| `GET /store/orders/:id` | 200 | **200** | **200** | 평가용 관리자 경로 사용 |

RBAC 비활성 core의 판매자는 넓은 관리자 권한이다. 판매자별 다중 테넌트 격리를 검증한 것이 아니다. Store의 주문 단건 조회는 목록과 달리 소유권을 강제하지 않는다. 설치 소스 `dist/api/store/orders/middlewares.js`와 `[id]/route.js`에서도 단건 조회의 고객 인증/소유자 필터 부재를 확인했다.

**결정:** Medusa core를 E2 후보로 유지한다. CW05는 구매자 소유권·run→외부 ID 매핑을 강제하는 제한된 gateway를 두고 원본 Store API를 UI/모델에 직접 노출하지 않는다. 구매자가 허용된 자신의 주문 상태를 보는 의미는 유지하고, 관리자 토큰·다른 주문·추가 복구 정보를 전달하지 않는다. [Medusa gateway](medusa-adapter.md)의 고객/run 거절 검사는 이후 구현·실측했다. 구매 HTTP 경로 연결은 남았다.

## 재시도·거절과 아직 다른 계약

- 같은 `cart_id`의 complete 두 번 → 같은 `order_id`. 임의 멱등 키의 동일 payload/충돌 보장을 검증한 것은 아니다.
- 동일 지급의 전체 capture 두 번 → 같은 capture ID 하나, 금액 310. 부분 capture·동시 요청·환불은 미검사.
- 텐트 100개 추가 요청 → 400, 원래 cart 수량 3/6 유지. 현재 재고 부족 거절을 확인했으며 가격 변경/재고 경합 시험은 이후 작업이다.
- 고객은 관리자 capture/fulfillment를 수행하지 못한다. 테스트 판매자의 처리와 구매자의 도구 호출을 구별한다.
- `UNKNOWN`은 조회/응답을 받지 못한 클라이언트의 관측이다. Medusa 원장의 실패 상태로 매핑하지 않는다. 이번에는 네트워크 응답 유실을 주입하지 않았다.
- Medusa에는 이 POC의 500크레딧 예산 원장이 없다. 자체 지급 저장소가 `spent + reserved <= budget`을 강제해야 한다. 승인과 capture는 서로 다르므로 단일 성공 플래그로 합치지 않는다.
- `quote_version`·가상 tick·run 격리는 자체 계약이다. Medusa cart 가격 재계산과 동일하다고 가정하지 않는다. CW01은 이를 명시하고 CW05의 대조 검사로 전이 범위를 제한한다.

공식 계약 참고: [cart 완료](https://docs.medusajs.com/resources/storefront-development/checkout/complete-cart), [payment collection](https://docs.medusajs.com/resources/commerce-modules/payment/payment-collection). 위 상태·권한 결과의 근거는 문서 추론이 아니라 고정 버전의 실제 응답이다.
