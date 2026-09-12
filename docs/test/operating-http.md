# CW05 준비 — 운영 HTTP 서버·권한·독립 시계

2026-09-07. 자체 합성 세계를 별도 프로세스와 HTTP 도구로 실행하는 운영 서버를 구현했다. **독립 Medusa 어댑터, 동결 정책의 E2 전이, F03/F04/F05 전체 검증은 아직 미완료다.**

## 실행과 범위

```sh
make operating
make operating-smoke
make operating-sdk-smoke
```

세 명령은 같은 `127.0.0.1:18001`을 사용하므로 순차 실행한다. `operating`은 새 run 두 개를 만들고 계속 실행하며 Ctrl+C로 종료한다. `operating-smoke`는 별도 프로세스로 HTTP·권한·실제 시간 진행·응답 유실·재시작을 확인하고 종료한다. `operating-sdk-smoke`는 실제 SDK + 스크립트 모델을 HTTP 도구에 연결해 정상 구매를 확인하고 종료한다. 실제 AWS·모델·Docker 호출은 없다.

각 명령은 `.local/operating/http_<id>`에 두 원장, clock/fault control DB, `server.json`, `credentials.json`, 서버 진단과 증거를 보관한다. 비밀값 파일은 mode 0600/폴더 0700이며 Git 제외다. 기존 실행·다른 프로젝트·데이터 볼륨을 삭제하지 않는다. 구매자에게는 자신의 buyer 토큰만 제공하고 관찰자·control 토큰은 분리한다.

`make check`는 ASGI 권한·입력·클라이언트·lifecycle 회귀 검사를 포함한다. 별도 프로세스의 실제 HTTP 검사는 위 두 smoke 명령의 결과로 구분한다. 기존 18000 health API와 React 개발 셸은 유지했다.

## 구매자와 관찰자의 경계

| 경로 | 권한·동작 |
|---|---|
| `GET /runs/:run/snapshot` | 같은 run의 buyer/observer; goal·시계·잔액·수령·공급처 이름 |
| `POST /runs/:run/quotes` | buyer; 서버의 현재 가격·재고로 견적 |
| `POST /runs/:run/orders` | buyer; 서버 견적 ID와 멱등 키 |
| `GET /runs/:run/orders/:order` | 같은 run의 buyer/observer, 다른 주문은 404 |
| `POST /runs/:run/payments` | buyer; order ID와 멱등 키만 허용, 금액 주입은 422 |
| `GET /runs/:run/payments/:order` | 같은 run의 기존 지급 조회; 새 지급 없음 |
| `/admin/runs/:run/...` | 해당 run의 control만 가격 변경·일회성 응답 지연 주입 |

누락/잘못된 토큰은 401, 다른 run 또는 역할은 403이다. observer는 쓰기 불가다. buyer에게 초기화·시계 변경·지급 확정·납품 완료 경로를 주지 않는다. 단건 주문의 run/소유권도 검사한다. 이는 자체 gateway의 검사이며, CW00에서 발견한 Medusa Store API 자체의 소유권 공백을 수정한 것은 아니다.

snapshot에서 seed·fixture·장애 계획·control 시각·원장 DB 경로를 제거했다. 모델은 고정 run에 바인딩된 HTTP 도구 8개만 사용한다. HTTP client는 loopback origin만 허용하고, 응답 유실 시 `UNKNOWN`을 반환해 자동 대체 지급이나 숨겨진 복구를 하지 않는다.

## 모델을 기다리지 않는 시간과 판매자

서버 worker는 독립 task/thread에서 1초=1tick 시계를 진행하고 이미 승인된 지급을 확정·납품한다. 요청 처리나 모델의 생각 시간을 tick의 동력으로 사용하지 않는다. HTTP 대기 도구는 실제 1~10초를 기다린 후 GET만 수행한다.

실행 중에는 단조 시계, 재시작 시에는 영속 wall-clock anchor와 마지막 tick 중 앞선 값을 사용한다. 서버가 멈춘 시간도 재시작 시 반영한다. OS 시각 변경·장기간 장애의 운영 정확성은 별도 검증 대상이다. 새로 처리하는 지급을 과거 tick에 소급하지 않는다.

같은 디렉터리의 worker는 프로세스 lock으로 하나만 허용한다. 종료할 때 진행 중인 SQLite 작업까지 기다린 뒤 lock을 반환한다. worker 예외는 health 503과 새 구매 쓰기 거절로 드러내며 기존 상태 조회는 유지한다.

## 실제 HTTP 결과

[HTTP 보고서](../../evidence/cw05-http/http-report.json)와 [정지 후 독립 원장 증거](../../evidence/cw05-http/http-evidence.json)를 보존했다. smoke는 실행 시간을 줄인 합성 fixture(`http-smoke-v1`, 기한 30tick·배송 2tick)를 사용했다.

- 무인증 401, 다른 run 403, observer 쓰기 403, 다른 고객의 주문 ID 조회 404.
- A 견적 후 텐트 가격 60→100, 이전 견적 `STALE_QUOTE`/409, B에서 380으로 새 구매.
- 서버 지급 commit 이후 HTTP 응답을 700ms 지연, client timeout 150ms에서 `UNKNOWN` 확인.
- 구매 요청 없이 2.2초 기다리는 동안 worker가 진행. 같은 주문 지급 재조회 `SETTLED`, 같은 키 재시도는 같은 지급 ID.
- 수령 텐트 3·조명 6, 집행 380·예약 0. 동일 DB/config로 서버를 다시 띄워 시각·재고·지급 ID 유지 확인.
- 프로세스를 종료한 뒤 독립 검증기 `COMPLETE`. 응답 지연은 자신의 loopback 요청에만 주입했다.

[SDK→HTTP 보고서](../../evidence/cw05-http/sdk-report.json)와 [독립 증거](../../evidence/cw05-http/sdk-evidence.json)도 저장했다. 실제 SDK의 7개 scripted 응답·6개 도구 호출로 A에서 310 구매·수령했다. SDK/HTTP 연결 검증이며 실제 LLM 성과나 토큰 소비는 아니다.

## 재시작 검사에서 수정한 점

첫 재시작은 포트 probe에서 errno 48로 실패했다. 종료 직후 TCP 연결을 재현해 활성 LISTEN에서는 일반/`SO_REUSEADDR` probe 모두 실패하고, 서버가 닫힌 뒤에는 일반 probe만 실패하는 것을 확인했다. probe를 uvicorn과 같은 `SO_REUSEADDR` 의미로 맞추고 실제 HTTP 재시작을 다시 통과시켰다. 활성 listener를 재사용하거나 종료하지 않는 회귀 검사도 추가했다.

[Medusa 고객 gateway](medusa-adapter.md)의 고객 API·외부 ID/소유권·예산 원장과 [독립 판매자·구매 HTTP 연결](medusa-operating.md)을 이후 실측했다. 동결 정책의 외부 실행은 남았다. 같은 자체 엔진의 HTTP 성공을 E2 전이로 세지 않는다.
