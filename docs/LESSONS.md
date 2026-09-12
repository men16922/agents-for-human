# Lessons

- 2026-09-12: Medusa build도 `medusa-config.ts`의 DATABASE_URL/REDIS_URL/JWT_SECRET/COOKIE_SECRET 검사를 실행한다. 오프라인 컴파일에는 명시적 build-only 값과 접속 불가 loopback 주소를 명령 범위로 제공한다. 운영 필수값 검사를 완화하지 않는다. `docs/test/linux-reproduction-20260912.md`.

- 2026-09-06: make/uv가 Ctrl+C를 중복 전달할 수 있다. 자식 프로세스 그룹 정리 중 SIGINT를 차단하고 실제 포트 반환까지 확인한다. 재현·회귀 검사는 `tests/dev/test_local_environment.py`.
- 2026-09-06: bootstrap/의존성 재설치는 같은 환경에서 병렬 실행하지 않는다. 별도 검증은 wrapper 뒤 `env UV_PROJECT_ENVIRONMENT=...`로 명시하고 lock 해시·실제 import로 확인한다.
- 2026-09-06: 브라우저 검사와 `make dev`는 같은 포트를 사용하므로 순차 실행한다. 포트 점유 오류를 기존 서버 재사용으로 숨기지 않는다.
- 2026-09-07: Medusa 2.20.1의 Store 주문 목록과 단건 조회는 인증 범위가 다르다. 목록 격리 검사로 단건 소유권을 추정하지 않는다. CW00 HTTP 증거 참고.
- 2026-09-07: 운영 서버 restart probe는 uvicorn과 같은 SO_REUSEADDR 의미를 사용한다. TIME_WAIT와 살아 있는 LISTEN을 구분하는 회귀 검사는 `tests/operating/test_lifecycle.py`.
- 2026-09-07: Medusa 관리자 주문 응답도 customer_id/currency_code는 명시적 fields 확장이 필요하다. 독립 증거 필드 누락은 UNKNOWN이며 저장된 성공 판정으로 대체하지 않는다. `tests/commerce/test_gateway.py`.
- 2026-09-08: Medusa checkout은 여러 외부 요청으로 구성된다. SUBMITTED 이후 HTTP 400만으로 전체 rollback을 추정하지 않는다. 외부 HTTP 오류는 UNKNOWN·예약 유지, 로컬 고객/금액 모순은 계약 거절로 구별한다. `tests/commerce/test_stock_changes.py`.
- 2026-09-08: Medusa 2.20.1 line-item update의 재고 확인은 갱신한 variant만 대상이다. 모든 line을 재확인해야 하며, 한 요청으로 전체 재고를 검사하는 replay fixture는 거짓 통과를 만들었다. 실제 두 번째 품목 감소와 교정 회귀로 확인했다.
- 2026-09-08: Strands 1.54.0은 누락된 provider usage를 SDK stream 집계에서 0으로 채운다. `ObservedModel`로 원본 metadata를 확인해야 USAGE_UNKNOWN을 유지한다. 구매 실행자·독립 검토 SDK 회귀로 확인했다.
- 2026-09-08: B0 부분 조달은 모든 잔여 품목의 공개 견적 후보를 먼저 확인한다. 일부 품목만 가능한 조건에서 130을 쓰고 중단한 결함을 known pilot으로 발견했다. 수정 전후 원장과 `tests/experiments/test_baseline.py` 회귀를 보존했다.

- 2026-09-09: 시간표 이벤트 검사에서 B0 실행 INCOMPLETE(`EXTERNAL_DELIVERY_MISMATCH`)와 종료 후 독립 원장 COMPLETE가 함께 관찰됐다. 최종 납품으로 실행 상태를 덮어쓰지 않고 raw 원장·실행 결합·조건 일치를 별도 집계한다. 후속 `docs/test/delivery-transition.md`에서 fulfillment 표시→주문 수량 갱신 사이의 실제 GET을 포착했다. 미수령 pending은 UNKNOWN으로 처리하고 확인된 수령 역행은 계속 거절한다.
