# 선언 알림 일정과 실제 SSE 수신을 대조

2026-09-09. [지급 응답 일정](scheduled-response-loss.md)에 이어 납품 알림의 지연·복사본·재전송을 실행 조건에 연결했다. 실제 로컬 Medusa의 B0와 SDK 실행에서 발행 기록과 별도 SSE 소비자의 수신 프레임을 대조했다. 알림 수신은 모델 재계획의 증거가 아니다.

## 선언과 영속 기록

`events`에는 다음처럼 설정한다. 공통 일정·ID 규칙은 [시간표 이벤트](timed-condition-events.md)를 따른다. 지연은 0~5000ms, 복사본은 1~3개다. 재전송은 앞서 선언한 `delivery_notification`의 ID를 참조해야 한다.

```json
[
  {"id":"notice","kind":"delivery_notification","at_tick":3,"max_lateness_ticks":2,"delay_ms":2000,"copies":2},
  {"id":"replay","kind":"notification_replay","at_tick":23,"max_lateness_ticks":2,"delay_ms":1000,"copies":2,"source_event":"notice"}
]
```

세션 제어자는 control 전용 `/admin/runs/<run>/faults/scheduled-notification`을 호출한다. 구매자 설정에는 control 토큰을 넣지 않는다. 같은 ID의 재설정·기존 장애 설정 덮어쓰기·다른 run의 관측 재전송을 거절한다. 한 run의 미소비 납품 설정은 하나, 전체 일정은 최대 8개다. 재전송은 원본의 모든 복사본이 발행된 뒤에만 설정할 수 있다.

관측 journal은 납품 수량 증가를 읽었을 때 설정을 한 번 소비하고, 원래 관측·직전 관측·복사본별 큐 번호와 예정 시각을 같은 transaction에 보존한다. 발행할 때 실제 커서·시각 기록과 큐 제거도 함께 처리한다. 재전송은 원래 관측 ID와 내용을 유지하며 새 발행 커서를 받는다. 관측 알림 자체는 지급·납품·수령 원장을 변경하지 않는다.

일정이 참조하는 원본 관측은 공개 커서 보존 범위를 넘어도 제한된 감사 자료로 남긴다. 공개 커서의 보존 범위가 늘어나는 것은 아니다. retention=1과 DB 재개 후 원본 재전송, 두 journal 인스턴스의 동시 발행을 회귀로 검증했다. 이번 실제 Medusa 실행에서 서버 강제 종료나 브라우저 재접속을 다시 수행한 것은 아니다.

## 조건 판정과 수신 판정

독립 조건 검사는 설정 POST의 경로·본문·원시 전후 tick, run/목표, 설정/소비 기록, 실제 수량 증가, 복사본 분모·큐 연결·고유 커서·지연 이후 발행을 대조한다. 재전송은 같은 원본 내용이며 원본 발행 뒤의 커서를 가져야 한다. 시작 시계는 초기 원시 binding과 일치해야 하고, 최종 발행 tick은 구매 실행 구간과 종료 export 안에 있어야 한다.

설정만 했거나 복사본이 아직 발행되지 않았으면 조건 완료로 세지 않는다. 이 조건 판정의 범위는 발행까지다(`publication_only: true`). SSE 수신은 smoke의 독립 소비자가 별도로 검사하며, 각 수신 프레임의 관측 전체 내용·커서·발행 시각을 원시 발행 기록과 대조한다.

## 실제 Medusa 결과

`make commerce`와 `make external-notification-smoke`를 실행했다. 테스트 구매자는 두 번째 견적을 6tick까지 늦추고, 목표 수량이 채워진 snapshot 응답을 28tick까지 보류하며 읽기 전용 조회를 계속했다. 이는 선언 알림을 실행 구간 안에서 관찰하기 위한 fixture 동작이다. 모델의 SSE 반응이나 추가 재계획 호출은 구현하지 않았다. 미사용 대조 조건은 일정을 63/83tick으로 옮겼다.

| 조건/방식 | 세션 | 납품 알림 발행 | 재전송 발행 | 독립 거래 / 조건 |
|---|---|---|---|---|
| 지연 B0 | `cw00-aecec0dfe8ac` | 21tick, 2.057초 후, 커서 19/20 | 24tick, 1.032초 후, 커서 24/25 | COMPLETE 310 / true |
| 지연 B1 SDK | `cw00-681f3c251c9d` | 21tick, 2.068초 후, 커서 19/20 | 24tick, 1.144초 후, 커서 24/25 | COMPLETE 310 / true |
| 미사용 B0 | `cw00-059b4ff25ec4` | 설정 전 종료 | 설정 전 종료 | COMPLETE 310 / false |

표의 지연은 설정 시각이 아니라 큐 소비부터 발행까지다. 지연 두 건 모두 3tick 설정·23tick 재전송 설정을 지켰다. 소비자는 각 4개 프레임을 수신했고, 이미 더 최신 snapshot이 도착해 첫 지연 관측은 `old`, 나머지 세 개는 `duplicate`였다. 최종 재고는 텐트 3·조명 6을 유지했다. 총 8개 수신 프레임이 실제 발행 기록과 일치했다. 이 표본으로 전체 지연 목표 달성을 주장하지 않는다.

배치 `notification-events_b07ec2b16a204b0fbb623a8c4fce9038`는 두 조건 × 네 방식의 8칸을 사전 고정했다. 실행 3건 모두 COMPLETED/독립 VERIFIED이며 5건은 NOT_RUN, 조건 일치는 2건이다. SDK fixture 14호출·280토큰·전체 도구 admission 53회·가상 392 micro-USD, 비용 예약 0이다. 실제 모델 호출은 0회다.

[보존 manifest](../../evidence/cw07-notification-events/artifact-manifest.json)는 74개 artifact와 별도 manifest를 포함한다. 명부 SQLite·세 실행/초기 조건/거래 export·일정 원시 기록·SSE 프레임·소스·로그를 보존하고 복사 명부를 독립 재집계했다. 소스 54개 hash와 실제 자격증명 미포함을 대조했다. 전용 서비스를 종료하고 포트 18001/19000/55432/56379 반환, 기존 컨테이너 4개와 볼륨 2개 보존을 확인했다.

추가 회귀 21개는 지연/복사/재전송·미발행·동시 발행·retention/재개·권한·설정 충돌·변조/누락 증거를 검사한다. `make check` PASS: Python 588개·mypy 54소스·ruff·lock·웹 빌드. 기존 TestClient 경고 2개 유지. 실제 모델·브라우저·AWS·설치·커밋·푸시는 수행하지 않았다.

후속 [관측 변화 큐/재확인/재판단 한도](observed-change-replanning.md)를 SDK fixture+실제 Medusa로 검증했다. 다음은 CW07 비교 명부에 반응 설정을 고정하는 작업이다.
