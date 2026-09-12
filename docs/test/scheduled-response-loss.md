# 선언된 지급 응답 지연과 실제 타임아웃을 대조

2026-09-09. [시간표 가격·재고 이벤트](timed-condition-events.md)에 지급 응답 지연을 추가했다. 설정 성공·실제 지연·구매자 타임아웃·거래 완료를 따로 검증한다. 실제 로컬 Medusa의 B0와 SDK 구매자는 응답을 받지 못한 뒤 같은 주문을 조회해 독립 COMPLETE 310에 도달했다.

## 설정과 영속 소비 기록

조건의 `events`에 다음 형식을 사용한다. 시각·ID 규칙은 기존 시간표와 같으며, `delay_ms`는 1~5000의 정수다. 공급처·품목·금액 등 다른 필드는 허용하지 않는다.

```json
{"id":"loss","kind":"payment_response_delay","at_tick":3,"max_lateness_ticks":2,"delay_ms":4000}
```

세션 제어자는 지정 시각에 control 권한으로 `/admin/runs/<run>/faults/scheduled-payment-response`를 호출한다. 구매자 설정에는 control 토큰을 넣지 않는다. 기존 일반 응답 지연 경로는 유지하며, 이번 검사는 기존 장애 설정과 혼용하지 않았다.

`response-faults.sqlite3`에는 run/event ID·요청 지연·설정 시각과 tick을 보존한다. 같은 ID의 재설정과 한 run의 동시 미소비 설정을 거절한다. 서버는 구매 gateway의 지급 처리 반환 뒤에만 한 설정을 CONSUMED로 바꾸고 주문 ID·반환 상태·소비 시각을 기록한다. 정해진 대기 뒤 FINISHED와 종료 시각/tick을 기록한다. 대기 취소는 INTERRUPTED다.

설정은 한 번만 소비한다. CONSUMED나 INTERRUPTED를 새 지급 요청에 다시 적용하지 않는다. 두 DB 인스턴스의 동시 소비와 재개 후 무재소비를 회귀로 검사했다. 이는 서버 프로세스 강제 종료를 실제로 재현한 결과는 아니다. CONSUMED만 남으면 적용 완료를 추정하지 않는다.

## 독립 검증

`OperatingClient`는 지급 POST의 run·주문 ID·시작/종료 시각·HTTP 상태 또는 transport 오류 종류만 기록한다. 인증 헤더·응답 본문·예외 상세는 넣지 않는다. 실행자는 이 기록을 종료 보고서와 함께 고정한다.

세션 종료 export는 해당 run의 원시 장애 기록을 포함한다. 독립 판정은 설정 POST의 정확한 경로/본문·원시 설정 tick·같은 run/event·주문 ID·실제 소비/종료 시각과 선언 지연을 대조한다. 실제 효과의 종료 tick이 구매 실행 구간과 최종 export 안에 있는지도 확인한다.

응답 지연 조건을 충족하려면 같은 주문의 지급 POST가 한 번이고, 소비 시각 이후부터 서버 대기 종료 전 사이에 `ReadTimeout`으로 끝났어야 한다. 설정만 성공했거나 소비하지 않았거나 대기가 중단됐으면 조건 완료가 아니다. 연결 실패 등 다른 오류도 타임아웃 증거로 대신하지 않는다. 거래 성공 여부는 별도 원장 검증을 따른다.

## 실제 Medusa 결과

`make commerce`와 `make external-response-smoke`를 실행했다. 첫 견적 뒤 두 번째 견적 요청을 6tick까지 늦추고 지급 POST의 read timeout을 2초로 설정한 테스트 전용 구매자를 사용했다. 두 구매 방식 모두 3tick에 4초 지연을 설정했다. 별도 미사용 조건은 같은 설정 시각을 60tick으로 옮겼다.

| 조건/방식 | 세션 | 실제 응답 관측 | 서버 적용 기록 | 독립 거래 | 조건 일치 |
|---|---|---|---|---|---|
| 유실 B0 | `cw00-ba8d7411242f` | ReadTimeout 2.002초 | 8→12tick, 4.002초 | COMPLETE 310 | true |
| 유실 B1 SDK | `cw00-b969e32652b2` | ReadTimeout 2.002초 | 7→11tick, 4.002초 | COMPLETE 310 | true |
| 미사용 B0 | `cw00-68746d7ec334` | HTTP 200, 0.409초 | 설정 시각 전 종료 | COMPLETE 310 | false |

지연 두 건 모두 서버의 지급 처리 반환 상태는 RESERVED였다. 구매자의 지급 POST는 각 한 번이고, 이후 조회로 정산·수령을 확인했다. 최종 세 실행은 모두 COMPLETED이며 거래 크레딧 예약은 0이다. 이 결과는 gateway 응답 지연/클라이언트 유실 검사이며 외부 결제 제공자의 응답 유실이나 실제 금융 거래를 뜻하지 않는다.

배치 `response-events_5db80f5526e549eead338d6defbb67ea`는 두 조건 × 네 방식의 8칸 명부를 사전 고정했다. 3 VERIFIED·5 NOT_RUN이며 조건 일치는 2건이다. SDK 호출 14회·280토큰·전체 도구 admission 53회·가상 392 micro-USD/비용 예약 0을 기록했다. B0의 모델 호출은 0회이며 실제 모델·학습 전이·미공개 비교는 아니다.

[보존 manifest](../../evidence/cw07-response-events/artifact-manifest.json)는 69개 artifact와 별도 manifest를 포함한다. 명부 SQLite·세 거래/초기 조건·원시 장애 기록·클라이언트 transport·실행/정산·설정 POST·소스를 보존하고 복사본을 독립 재집계했다. 소스 52개 hash·실제 자격증명 미포함을 대조했다. 포트 18001/19000/55432/56379 반환과 기존 컨테이너 4개·볼륨 2개 보존을 확인했다.

추가 회귀 20개는 단일 소비·중단 상태·설정 충돌·권한/범위·미완료/변조 증거·타임아웃 구별·민감 정보 없는 계측을 검사한다. `make check`는 Python 567개·mypy 52소스·ruff·lock·웹 빌드 PASS다. 기존 TestClient 경고 2개 유지. 실제 모델·브라우저·AWS·설치·커밋·푸시는 수행하지 않았다.

후속 [알림 지연·중복·재전송 일정](scheduled-notifications.md)에서 선언 조건·원시 발행·실제 SSE 수신을 별도로 대조했다. 다음은 CW06 관측 변화 큐와 재판단 연결이다.
