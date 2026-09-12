# CW01·CW02 — 로컬 거래 세계와 독립 검증

2026-09-07. CW00의 Medusa 계약을 기준으로 자체 합성 세계의 상태·원장·가상 시계·정상 구매(CW01), 독립 검증과 F01/F02/F06(CW02)을 구현했다. 제품 UI는 아직 health 개발 셸이며 실제 모델·정책 전이·실시간 서버는 미완료다.

## 실행과 저장된 증거

```sh
make world-smoke
make world-fixtures
make check
```

Docker·네트워크·모델 없이 실행한다. 매번 `.local/world/normal_<id>` 또는 `.local/evaluation/cw02_<id>` 아래에 별도 SQLite 파일과 JSON 증거를 만든다. 기존 실행을 덮거나 초기화하지 않는다.

현재 고정 증거는 [4개 사례 보고서](../../evidence/cw02/report.json)와 [정상](../../evidence/cw02/normal.json), [F01](../../evidence/cw02/F01.json), [F02](../../evidence/cw02/F02.json), [F06](../../evidence/cw02/F06.json)이다. 알려진 수작업 fixture이며 holdout 평가나 LLM 성공률이 아니다. 각 증거에는 시나리오, run 메타데이터, 실제 DB 행, 판정이 들어 있다. 보고서에는 구현·검증 파일 해시를 기록했다.

저장된 판정을 신뢰하지 않고 다시 계산할 수 있다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -c \
  'from pathlib import Path; from rehearsal.evaluation.verifier import verify_export; print(verify_export(Path("evidence/cw02/normal.json")))'
```

## CW01의 구현 경계

- `src/rehearsal/world/shop.py`: 서버가 보관한 견적·가격 버전·만료, 재고 예약, 주문, 납품 인벤토리.
- `src/rehearsal/world/payments.py`: 별도 `payments.sqlite3`의 계정·지급 intent·outbox. `spent + reserved <= budget`을 SQL 제약과 `BEGIN IMMEDIATE` 안에서 강제한다.
- `shop.sqlite3`와 지급 DB 사이에는 공동 transaction이 없다. 지급 commit 이후 상점 반영 전에 중단되어도 outbox 재조회와 영속 receipt로 복구한다. 중복·역순 지급 이벤트는 주문을 되돌리거나 재고를 중복 소비하지 않는다.
- 구매 도구는 `order_id`를 전달하며 금액·수취 공급처는 서버의 주문에서 결정한다. 같은 키·같은 내용은 기존 지급, 다른 내용은 충돌이다. 다른 키로 같은 주문의 새 intent를 만들 수도 없다.
- 지급은 `RESERVED → SETTLED`, 주문은 `ACCEPTED → PAYMENT_PENDING → PAID → FULFILLING → DELIVERED`. `PAID`는 별도 이벤트로 남고 정상 경로에서 같은 상점 transaction 안에 배송 준비로 진행한다. 전송 전의 요청을 별도 `CREATED` 행으로 저장하지 않는다.
- 정수 크레딧만 허용한다. 정상 A 견적은 310, B는 380, C는 495다. 지급 승인만으로 물품이 보이지 않으며 공급처의 lead tick 이후 실제 인벤토리에 반영한다.
- 가상 시각은 run에 영속 저장되고 역행하지 않는다. 큰 시간 이동도 납품 기록에는 실제 예정 tick을 남긴다. `OperatingClock`은 단조 시계 primitive만 제공한다. 독립 worker가 실시간으로 진행하는 운영 서비스는 CW05/06 작업이다.
- 현재는 양수 지급·정상 확정만 구현했다. 지급 예약 만료·취소·환급·부분 fulfillment·분산 다중 인스턴스는 아직 없다. 예산 거절된 미지급 주문의 재고 예약은 유지되므로 후속 정책에서 무분별한 주문을 만들면 안 된다.

## CW02의 독립 판정

`src/rehearsal/evaluation/verifier.py`는 World/Shop/PaymentLedger의 판정이나 상태 전이 함수를 호출하지 않는다. 별도 SQLite read-only 연결로 읽고, 외부에서 전달한 fixture와 지급·주문·가격 변경 이력·재고·납품 이벤트를 대조한다. 읽는 동안 DB가 바뀌거나 증거가 빠졌으면 `UNKNOWN`이다. 온라인 운영의 최종 일관성 판정은 CW05에서 별도 구성해야 한다.

| 사례 | 실제 동작 | 독립 결과 |
|---|---|---|
| 정상 | A에서 3/6 구매, tick 10 수령 | `COMPLETE`, 집행 310·예약 0 |
| F01 가격 변경 | A 텐트 60→100, 이전 견적 거절, 새 후보 중 B 380 선택 | `COMPLETE`, 집행 380·예약 0 |
| F02 응답 유실 | 지급 commit 뒤 클라이언트 함수 경계에서 TimeoutError, 동일 주문 지급 재조회 | 관측 `UNKNOWN→SETTLED`, 최종 `COMPLETE`, 집행 310·지급 1건 |
| F06 불가능 재고 | 모든 공급처 텐트 0, 구매 가능 견적 없음, 기한 도달 | `FAILED/DEADLINE_MISSED`, 집행·예약 0 |

F02는 로컬 함수 경계의 통제된 응답 유실이다. HTTP proxy·실제 Medusa 응답 유실은 아직 검사하지 않았다. 아직 도착하지 않았고 기한이 남은 목표는 `INCOMPLETE`, 늦은 납품은 수량이 맞아도 `FAILED`다. 클라이언트가 응답을 못 받은 상태와 독립 검증기가 아는 원장 상태를 구분한다.

검사에는 예산 310/309 경계, 실제 thread 동시 요청의 예산·재고 경합, 중단 후 재기동, 중복·역순 이벤트, run 격리, 만료 견적·정수 입력을 포함했다. 검증기에는 금액·수량·수취인·재고·이벤트 삭제·다른 run 행·중복 행을 변조한 반례와, 서버가 모든 금액을 일관되게 잘못 계산한 반례를 넣었다.

최종 `make check`에서 기존 개발 기반을 포함한 Python 42개 검사·mypy 13개 소스·ruff·웹 빌드가 통과했다. 이번에는 브라우저 검사를 재실행하지 않았다.

## CW03의 준비와 남은 실행

`src/rehearsal/agents/executor.py`에 Strands 1.54.0의 구매 도구 8개와 모델·도구 호출 횟수 상한을 연결했다. 모델 객체를 명시적으로 주입해야 하며 기본 AWS 모델을 자동 생성하지 않는다. 도구에는 run 선택·seed·fixture·관리자 초기화/가격 변경/납품 완료 권한을 주지 않는다.

`wait_for_updates`는 가속 연습에서 1~10 tick 대기를 요청하고 시뮬레이터 판매자가 이미 승인된 지급을 처리하는 경계다. 운영 환경에서는 허용하지 않는다. 실시간 서버나 외부 판매자 처리를 구현한 것으로 세지 않는다.

실제 Strands SDK 루프 + 스크립트 모델 검사에서는 7회 모델 fixture 응답, 6회 도구 실행으로 정상 목표를 독립 확인했다. 입력 84·출력 56은 fixture가 주입한 usage 값으로, **실제 LLM 토큰 소비나 비용이 아니다**. 호출 상한과 도구 권한 거절도 SDK 경로로 검사했다. [사용량 원장·Bedrock 실행 명령과 fork 준비](model-runner-and-policy-fork.md)를 추가했다. 실제 모델·비용 검증은 아직 남아 있다.

현재 `.env`의 `AWS_PROFILE`, `AWS_REGION`, `REHEARSAL_MODEL_ID`가 비어 있다. 사용할 profile·리전·모델 ID와 비용 상한을 사용자에게 요청했다. 응답 전에는 실제 AWS·모델 호출을 하지 않았다.

SDK 구현 근거: [Strands hooks](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/), [Bedrock model](https://strandsagents.com/docs/user-guide/concepts/model-providers/amazon-bedrock/). 고정 설치 소스와 실제 오프라인 SDK 실행을 함께 대조했다.
