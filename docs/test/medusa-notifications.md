# CW05 F03 — 납품 관측 알림과 재접속

2026-09-08 갱신. 영속 관측 journal, 고객 API 기반 worker, buyer/observer SSE와 참조 소비자를 구현하고 **실제 Medusa 납품·SSE 복구까지 검증했다.** 브라우저 UI·모델 재계획은 미완료다.

## 원장과 알림의 경계

[관측 journal](../../src/rehearsal/commerce/observations.py)은 고객 gateway의 전체 snapshot을 별도 `observations.sqlite3`에 저장한다. 수령·지급의 원본은 기존 Medusa/고객 원장이며 알림의 전달·재전달은 capture·납품이나 수량 누적을 실행하지 않는다. 고객 polling은 실제 외부 상태를 조회하고 기존 gateway의 파생 지급/수령 기록을 갱신할 수 있다. 별도 판매자만 외부 납품을 진행한다.

관측 버전은 이 프로세스가 본 snapshot의 순서다. Medusa 전체 이벤트의 발생 순서나 실제 납품 시각을 뜻하지 않는다. 전달 커서는 알림이 실제 공개될 때 run별로 증가한다. 늦은 관측 이벤트가 더 높은 전달 커서를 받을 수 있고, 같은 이벤트의 복사본도 각각 커서를 받는다. 따라서 재접속 이후의 커서 조회에서도 늦은 알림을 놓치지 않는다.

관측 저장과 대기열 추가, 대기열 제거와 전달 커서 발급은 각각 SQLite transaction으로 처리한다. 기본 최근 전달 1,000개를 보존한다. 아직 대기 중인 이벤트와 최신 관측은 보존 기간 정리에서 제외한다. 보존 범위 밖 커서는 최신 전체 snapshot과 현재 커서로 명시적으로 복구한다. 최신 snapshot에는 아직 전달이 지연 중인 관측이 포함될 수 있다.

참조 `Projection`은 최신 관측의 전체 상태로 교체한다. 중복은 무시하고, 오래된 버전은 최신 상태를 되돌리지 않는다. 다른 run·보관 중인 동일 event ID의 내용 충돌·동일 최신 버전의 상태 충돌을 거절한다. fingerprint는 최근 1,000개만 보관하며, 그 이전 버전도 최신 상태를 교체할 수 없다.

## HTTP와 장애 주입

- `GET /runs/{run_id}/observations?after=0&limit=100`: 전달 배치·다음 커서·마지막 성공 관측·신선도. 미래 커서는 409, 음수/잘못된 limit는 422.
- `GET /runs/{run_id}/events`: 같은 관측을 SSE로 전송한다. `Last-Event-ID`가 `after`보다 우선한다. `observation`은 전달, `snapshot`은 보존 기간 초과 복구, `status`는 관측 실패·신선도다. status는 SSE ID를 전진시키지 않는다.
- `POST /admin/runs/{run_id}/faults/delivery-notification`: control만 다음 수령 증가 알림에 0~5,000ms 지연·1~3개 복사를 설정한다.
- `POST /admin/runs/{run_id}/faults/replay-notification`: control만 같은 run에서 보관 중인 event ID를 재전달한다. 임의 snapshot·금액·외부 event ID는 주입할 수 없다.

읽기는 buyer/observer 토큰, 장애 주입은 control 토큰이 필요하다. 토큰을 URL에 넣지 않는다. 이후 브라우저는 Authorization 헤더를 지원하는 fetch stream으로 연결해야 하며 아직 구현하지 않았다. SSE 형식은 [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events), 전송은 [Starlette StreamingResponse](https://www.starlette.io/responses/#streamingresponse)를 따른다.

[관측 worker](../../src/rehearsal/commerce/observer.py)는 각 고객을 약 1초 간격으로 조회하고 별도 루프가 0.2초 간격으로 대기 알림을 공개한다. 이는 목표 polling 간격이며 실측 지연 보장이 아니다. 성공 관측이 5초 이상 오래됐거나 실패하면 stale로 표시한다. tick만 바뀐 이벤트는 `clock.observed`이며 모델 호출을 자동 발생시키지 않는다. `observer.lock`으로 중복 worker를 막고 종료 시 진행 중인 HTTP thread를 기다린 뒤 고객 client를 닫는다.

## 검증 범위와 재개

[회귀 검사](../../tests/commerce/test_observations.py) 19개 PASS: 지연·중복·역순·재시작, 보존 기간 복구, transaction 중 실패의 rollback, 동시 publisher의 단일 전달, run 격리, 실패/오래된 관측, 상태 충돌, HTTP 권한·입력 범위, 종료 시 thread 완료 대기·worker 예외 후 자원 해제·중복 worker 거절. 실제 ASGI streaming 경로에서 재접속 헤더 우선순위와 snapshot reset도 확인했다. 외부 소켓·실제 Medusa 주문을 사용한 검사는 아니다.

[실제 검사 스크립트](../../scripts/commerce/notification_smoke.py)는 `make commerce` 준비 후 `make commerce-notification-smoke`로 실행하도록 작성했다. A 합성 구매 310 → 독립 판매자 납품 → 2초 지연/중복 알림 → 이전 snapshot 재전달 → 구매 서버 재시작 → 보존 범위 초과 복구 → 독립 원장 판정을 검사한다. 실행 결과·원장·SSE 프레임·소스 hash는 `.local/commerce/<run_id>/notification-{report,evidence}.json`에 기록하도록 했으며, 2026-09-07에는 미실행이었으며 아래 2026-09-08 실행 결과와 보존 증거를 참고한다.

2026-09-07에는 Medusa build·migration·health 이후 loopback 조회가 자동 승인 검토에서 “Network access is outside the default unattended loop.” 사유로 거절돼 실제 검사가 미실행이었다. 전용 서비스를 종료하고 볼륨을 보존했다. 아래 2026-09-08 실제 결과로 이 대기 상태를 해소했다.

## 실제 HTTP/SSE 검증 — 2026-09-08

사용자의 최대한 수행 요청에 따라 로컬 전용 환경을 기동하고 `make commerce-notification-smoke` PASS. 실행 ID `cw00-f4e543a11e34`, [보고서·SSE 프레임](../../evidence/cw05-notifications/notification-report.json), [독립 원장](../../evidence/cw05-notifications/notification-evidence.json), [관리자 요청/응답](../../evidence/cw05-notifications/responses.json)을 보존했다.

실제 A 구매 310·별도 판매자 납품 뒤 약 2.010초 지연과 중복 알림을 확인했다. 오래된 snapshot 재전달로 수령이 줄지 않고, 구매 서버 재시작 후 pending 2개·커서가 복구됐다. 보존 범위 밖 커서는 snapshot reset으로 복구했다. 무인증 401·다른 run 403·구매자의 장애 주입 403을 확인했다. 최종 소비자 상태가 고객 snapshot과 일치하며 독립 원장은 COMPLETE(310·예약 0)다.

소스·증거 hash와 실제 credential 미포함을 확인했다. 전용 프로세스/DB 종료·포트 반환·볼륨 보존. 모델·브라우저 UI·화면 지연·공개 접근 검증은 없으며, 위 지연은 이번 알려진 fixture의 관측값이다.
