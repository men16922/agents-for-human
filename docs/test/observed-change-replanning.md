# 모델 응답을 기다리는 동안 바뀐 재고를 재확인

2026-09-09. [알림 일정 검증](scheduled-notifications.md)에 이어 구매 실행자에 관측 변화 큐와 주문·지급 직전 재확인을 연결했다. 실제 Medusa에서 A 재고 감소를 기다리는 SDK fixture의 오래된 주문을 차단하고, 새 B 견적으로 COMPLETE 380에 도달했다. 이 결과는 연결과 경계의 증거이며 실제 모델의 재계획 능력이나 학습 전이 결과가 아니다.

## 실행 설정과 관측 흐름

기존 [구매 세션](model-session.md)을 준비한 뒤 HTTP 실행자의 `--max-replans 8`로 관측 반응을 명시적으로 켠다. 허용 범위는 1~32다. 생략하면 기존 실행 방식이며 B0 고정 규칙 실행에 이 옵션을 적용하지 않는다. 설정은 실행 전 `spec.json`에 고정된다.

```sh
# 설정 검사만 수행: 모델/HTTP 호출 없음
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --config '<buyer-config.json>' --max-replans 8
# 실제 호출은 모델/단가/예산을 준비한 승인 범위에서 실행
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --config '<buyer-config.json>' --max-replans 8 --execute
```

별도 읽기 스레드는 buyer 권한으로 `/observations?after=<cursor>`를 0.5초 간격으로 조회한다. UI의 SSE와 같은 영속 journal을 소비하며, 새로운 지급이나 구매를 실행하지 않는다. 모든 수신 batch를 `observations.jsonl`에 기록한다. worker는 종료 시 진행 중인 유한 timeout HTTP 요청을 마친 뒤 합류한다.

큐는 관측 버전·전달 커서를 구별하고 최신 상태 하나를 유지한다. 반복 ID·늦은 버전은 현재 상태를 덮어쓰지 못한다. 보존 범위 밖이면 서버가 준 최신 snapshot/cursor로 복구한다. tick만 바뀌거나 목록 순서만 달라진 것은 재판단 조건으로 세지 않는다. 가격·재고·예산·수령·주문/지급 상태 등 검증된 공개 필드의 변화는 하나로 모은다. fresh 조회 전에 캡처한 세대까지만 확인 처리하므로 조회/모델 처리 중 도착한 더 새로운 변화가 사라지지 않는다.

## 모델 입력과 실행 직전 검사

각 모델 호출 전 buyer의 `/snapshot?details=true`로 최신 공개 상태를 읽는다. 첫 호출과 의미 있는 변화가 있을 때만 관측 문맥을 추가한다. 공급처 설명 원문·관리자 정보는 포함하지 않으며 목표·예산·run 검사는 기존 계약을 따른다. 서버는 새 query를 통해 구매자에게 이미 journal에서 공개된 catalog/order 정보를 직접 조회하게 한다.

모델이 `end_turn`을 반환했어도 목표가 미완료이면 관측 변화를 기다린다. 의미 있는 변화가 확인되면 같은 Agent/대화로 다시 판단한다. 시계만 진행할 때는 모델을 다시 호출하지 않는다. 목표 수령·deadline·전체 timeout·기존 호출 한도가 종료 조건이다. 한도로 취소된 SDK 결과가 대기 루프에 남던 결함은 회귀에서 발견해 종료 조건을 수정했다.

`orders`와 `payments` POST 직전에는 다시 읽은 공개 상태를 마지막 판단 기준과 비교한다. 조건이 바뀌면 `OBSERVATION_CHANGED_REPLAN`으로 거절하고 POST를 보내지 않는다. 불완전한 수령/catalog/order 관측·잘린 주문 목록·deadline 도달도 집행하지 않는다. 주문에는 보관한 견적의 만료 tick과 견적을 얻은 판단 기준도 검사한다. 이전 판단의 견적이면 새 견적을 요구하며, 실제 견적 ID·version·기준 tick·만료 tick을 재확인 기록에 남긴다.

이 조회는 최종 재고 예약과 원자적이지 않다. 이후 경합은 gateway/Medusa의 기존 재고·가격·예산 검사와 UNKNOWN 처리에 의존한다. 관측 소비자가 다른 공급처를 자동 선택하거나 UNKNOWN 예약을 해제하지 않는다. 주문·지급·복구 선택은 모델 도구 요청으로만 수행한다.

## 추가 판단의 회계

재판단 상한은 의미 있는 상태 변화가 모델 입력에 전달되는 횟수다. 외부 재고 변화뿐 아니라 실행자의 주문 생성·지급·납품 상태 변화도 포함한다. 초기 관측 입력은 이 횟수에서 제외한다. 이를 모델 호출 횟수나 외부 장애 수와 혼동하지 않는다.

추가 호출도 기존 `Limits`와 `UsageLedger`, 전달받은 학습 원장을 공유한다. 새 Agent·별도 예산·usage 초기화를 만들지 않는다. SDK의 예상 입력량은 hook 전에 계산되므로, 추가한 관측 텍스트의 UTF-8 바이트 수를 보수적으로 더한 뒤 입력/비용 예약을 검사한다. 사용량 미확정은 예약을 유지하고 다음 호출을 차단한다. fresh 조회·관측 polling은 모델 도구 admission과 별도로 기록한다. 이 비용 제한을 실제 청구 절대 상한으로 주장하지 않는다.

## 실제 Medusa 검사

`make commerce`와 `make commerce-reaction-smoke`를 실행했다. 명시된 이벤트가 10tick에 A 텐트 재고를 10→0으로 바꾸고 원시 Store/Admin 응답으로 이를 확인했다. 테스트용 SDK 모델은 첫 A 견적 뒤 응답을 12초 늦추고 오래된 A 주문을 요청한다. 차단 뒤 B 견적·주문·지급·수령 확인을 요청하는 알려진 스크립트다.

| 시도 | 실행 / 독립 거래 | 관측 및 구매 | SDK 회계 |
|---|---|---|---|
| 최초 `cw00-e59ffb4433b2` | ERROR / INCOMPLETE 0 | A 차단, B 미지급 주문 뒤 fixture 오류 | 5 admission·4 usage·80토큰·가상 112 micro-USD·미확정 예약 10,048 |
| 교정 `cw00-584c29b5fd4a` | COMPLETED / COMPLETE 380 | A 차단, B 주문/지급 각 1회·텐트 3/조명 6 수령 | 9 admission/usage·180토큰·8도구·가상 252 micro-USD·예약 0 |

최초 오류는 fixture가 실제 Medusa 주문에 없는 `due_tick`으로 주문을 찾은 것이었다. 실제 응답의 `quote_id`·`status`로 식별하도록 교정했으며 최초 실행/원장/미확정 예약은 보존했다. 두 시도는 별도 세션·별도 예산이다. 실패 시도의 미확정 예약을 재시도 결과로 정산하지 않았다.

교정 실행 `reaction_44ee83ff799943b5bf4660388a514fad`는 12.002초 모델 대기 중 변경된 A 재고를 담은 커서 11/12의 두 batch를 수신했다. 최종 소비 커서/버전은 27, 재판단 5회·fresh 조회 13회·오래된 집행 차단 1회다. 실제 거래 원장과 실행 주문을 독립 대조했다. 전체 지연 목표·실제 모델 판단·미공개 조건 비교·분산 경합의 증거는 아니다.

[보존 manifest](../../evidence/cw06-reactive-buyer/artifact-manifest.json)는 두 시도의 45개 artifact와 별도 manifest를 포함한다. 실행/관측/구매 HTTP·원시 초기/변경 조건·독립 거래 export·사용량 SQLite·fixture 수정 전 소스·로그를 보존했다. 복사본에서 거래와 이벤트를 다시 판정하고 소스 56개 hash·실제 자격증명 미포함을 확인했다. 재판정 시각은 새로 생성되며 판정 내용은 원본과 일치한다. 전용 서비스 종료·포트 4개 반환·기존 컨테이너 4개/볼륨 2개 보존도 대조했다.

`make check`는 Python 608개·mypy 56소스·ruff·lock·웹 빌드 PASS이며 기존 TestClient 경고 2개를 유지한다. 추가 회귀 20개는 중복/역순/retention·처리 중 최신 세대·모델 대기 중 변경/오래된 POST 차단·만료/견적 기준·미확정 수령·재판단/공통 호출 한도·usage 누락·관측 증거 변조·end_turn 뒤 변화 재호출·시계만 진행할 때 무재호출을 검사한다. 실제 모델·브라우저·AWS·설치·커밋·푸시는 수행하지 않았다.

후속 [CW07 동결 비교 명부/반응 설정](frozen-reaction-comparison.md)에서 새 명부의 설정과 공통 원장을 검증했다. 이전 명부/결과는 비반응 실행으로 유지한다. 후속 [읽기 전용 반응 UI](execution-reaction-ui.md)도 보존 기록/API/브라우저와 실제 SDK/Medusa 동시 실행으로 검증했다. 실제 모델 효과는 별도로 남았다.
