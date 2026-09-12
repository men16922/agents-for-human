# CW05 준비 — 독립 Medusa 판매자와 구매 HTTP 연결

2026-09-07. 구매 HTTP 서버와 별도 Medusa 판매자 프로세스를 연결했다. A/B/C 카탈로그의 견적과 B의 실제 주문·지급·납품, 응답 유실, 두 프로세스 재시작을 확인했다. **동결 정책 전이·실제 모델·F03/F04/F05 전체·SSE UI는 아직 미완료다.**

## 재현과 보존 증거

터미널 1에서 `make commerce`, 준비 후 터미널 2에서 `make commerce-operating-smoke`. 검사는 구매 gateway와 판매자를 별도 프로세스로 기동하고 종료한다. 마지막에 터미널 1의 Ctrl+C로 Medusa와 전용 DB 서비스를 종료한다. 설치·이전 데이터·볼륨은 보존한다.

- [실행 검사](../../scripts/commerce/operating_smoke.py), [공급처 fixture·기동 helper](../../scripts/commerce/operating_fixture.py).
- [구매 HTTP 서버](../../src/rehearsal/commerce/server.py), [독립 판매자](../../src/rehearsal/commerce/seller.py), [판매자 회귀 검사](../../tests/commerce/test_seller.py).
- [최종 보고서](../../evidence/cw05-medusa-operating/report.json), [외부 주문·원장·판매자 작업 증거](../../evidence/cw05-medusa-operating/evidence.json).

실행별 `.local/commerce/<run_id>/operating`에는 `server.json`, `seller.json`, `credentials.json`, run별 고객 원장, 판매자 SQLite, 진단 로그가 남는다. 비밀 파일은 0600이며 Git 제외다. `server.json`에는 고객 토큰과 gateway 역할별 토큰 hash만, `seller.json`에는 관리자 토큰만 전달한다. 같은 OS 사용자의 파일시스템 안에서 프로세스와 자격증명을 분리한 POC이며 OS 수준의 적대적 사용자 격리를 뜻하지 않는다.

보고서에는 실행/재시작 PID·소스/lock/증거 SHA-256이 있다. 전체 fixture·관찰자 HTTP 기록은 Git 제외 `responses.json`, 판매자의 mutation은 `seller.sqlite3`의 작업별 기록과 실제 관리자 주문 응답으로 대조한다. 관찰자 요청 수를 전체 backend 트래픽 수라고 세지 않는다.

## 구매자와 판매자의 역할

기존 `OperatingClient`와 HTTP 도구 8개의 경로를 유지한다. buyer/observer/control 역할과 run 토큰으로 권한을 검사하며, 고객 어댑터가 다시 실제 Medusa 고객 ID·주문 매핑을 확인한다. 금액 주입·잘못된 수량은 입력 검증에서 거절한다. 구매 서버에는 capture·fulfillment·시계 변경·가격 변경 도구가 없다. control의 일회성 지급 응답 지연은 gateway 응답에만 적용한다.

판매자는 구매자가 이미 제출하고 예산을 예약한 의도만 처리한다. 고객/run/견적 metadata·수량·금액·수동 지급 제공자·배송 옵션·창고를 확인한 뒤 capture → fulfillment → shipment → delivery를 진행한다. 새로운 구매나 cart complete를 시작하지 않는다.

작업별 `STARTED`를 commit한 뒤 외부 POST를 보낸다. 응답이 유실되면 다음 GET에서 실제 상태가 진행했는지 확인하고 `OBSERVED`로 대조한다. 외부 상태가 진행하지 않았으면 같은 POST를 무조건 재전송하지 않는다. 해당 작업은 불확실 상태로 남고 health가 실패한다. 이 상태의 명시적 복구/취소는 후속 작업이다.

판매자는 첫 주문 관측 시 `first_seen + lead_ticks`를 영속화한다. 실행 중 시각은 단조 시계로 진행하며 재시작 시에는 저장된 기한을 유지한다. 현재 fixture의 배송 지연은 A 4초/B 6초/C 8초, 목표 기한은 120초다. 표준 연습 시나리오의 10/15/20tick·60tick과 다른 smoke 조건이다. 가상 예산의 SETTLED 매핑은 고객이 외부 capture를 조회할 때 갱신되며, 그전에는 예약으로 예산을 보호한다.

판매자 상태 파일은 PID·heartbeat·오류를 담는다. HTTP health는 5초 이내의 정상 heartbeat만 인정하고, 판매자 중단/오류 시 신규 구매를 503으로 거절한다. 기존 조회는 허용한다. heartbeat는 운영 상태 신호이며 외부 주문이나 목표 완료의 증거로 쓰지 않는다.

## 실제 검사 결과

- 구매 HTTP 무인증 401, 다른 run/observer 쓰기 403, 타 주문 404, 지급 금액 주입 422.
- 실제 공급처 견적 A 310/B 380/C 495. A 텐트 가격 60→100을 실제 관리자 API로 바꾸자 기존 견적 `STALE_QUOTE`를 확인했고 B 새 견적으로 구매했다.
- 지급 응답 1.2초 지연과 고객 timeout 0.4초로 실제 HTTP `UNKNOWN` 관측. 판매자는 별도 프로세스에서 capture·출고를 진행했다.
- 출고 후 판매자를 종료하자 HTTP health·새 구매는 503, observer의 기존 주문 조회는 200이었다.
- 구매 HTTP 서버도 종료했다. 판매자만 재시작한 상태에서 B 납품이 완료됐고, 영속 기한과 실제 delivered 시각을 대조해 6초 이전 납품이 없음을 확인했다.
- 구매 HTTP 서버를 같은 DB/토큰으로 재시작했다. 같은 지급 키는 같은 ID, 수령 텐트 3·조명 6, spent 380/reserved 0이었다. 반복 조회에도 수령이 중복되지 않았다.
- capture·fulfill·ship·deliver 작업은 각 1개이며 모두 실제 관측으로 대조됐다. 프로세스 종료 후 독립 export 검증기는 `COMPLETE`였다.

`make check`에는 판매자의 중단·응답 유실·기한 유지·중복 mutation 거절·잘못된 고객/금액/창고 거절을 검사하는 회귀 8개가 추가됐다. 실제 HTTP 검사와 mock 회귀 결과를 구분한다. manual provider의 합성 지급/납품이며 실자금·물리적 배송 성과는 아니다.

이후 [동결 B0의 연습/Medusa 대조](frozen-policy-transfer.md)에서 가격 변경·지급 응답 유실과 F04의 알려진 부분 조달을 검증했다. 다음은 F03/F05·실행 중 외부 재고 변경과 실제 모델 기반 정책 전이다. 모델 설정 응답이 있으면 CW03 실제 실행·사용량 확인을 먼저 진행한다.
