# 두 구매자의 희소 재고 경합 — CW05

2026-09-08. 실제 Medusa 실행 `cw00-608e1d67aec7`에서 두 run이 A 공급자의 텐트 3개·조명 6개 한 묶음을 동시에 구매했다. checkout HTTP 구간이 194.294ms 겹쳤고, 주문 하나만 생성·납품됐다. 다른 run은 HTTP 400 이후 UNKNOWN·예약 310을 유지했다. 단일 Medusa 프로세스의 이 경합 조건을 검증한 것이며 모든 동시 실행의 원자성을 입증하지 않는다.

## 잠금 경계와 재현

gateway의 `RLock`/`flock`은 각 run 디렉터리의 `gateway.lock`에 걸린다. 같은 run의 별도 gateway 객체는 직렬화되지만 두 run의 외부 재고를 함께 잠그지는 않는다. 설치된 Medusa 2.20.1의 `complete-cart.js`는 cart ID를 잠그고, `reserve-inventory.js`는 inventory item ID 목록으로 `locking.execute` 안에서 예약을 만든다. 현재 Medusa lock은 단일 프로세스 구성이며 운영용 분산 lock 검증은 아니다.

`make commerce`로 전용 Medusa가 준비된 뒤 실행한다.

```sh
make commerce-race-smoke
```

[검사 조정자](../../scripts/commerce/race_smoke.py)는 별도 고객·run·가상 예산 500을 가진 두 구매자를 준비한다. [검사용 gateway factory](../../scripts/commerce/race_gateway.py)는 실제 `StoreAPI`와 기존 제품 gateway를 사용하되, 각 요청의 POST `/complete` 직전에서 barrier로 서로 기다린다. 두 요청이 재고 재확인·지급 collection/session 준비를 모두 마친 뒤 실제 Medusa HTTP를 시작한다. 응답은 조작하지 않는다. 요청 시각·메서드·경로·오류만 기록하며 토큰이나 요청 본문은 기록하지 않는다.

barrier 도착 두 건이 첫 checkout 시작보다 앞서며, `min(종료) - max(시작)`이 양수인지 검사한다. 이는 클라이언트의 실제 HTTP 요청 구간 중첩 증거다. Medusa 내부 명령 각각의 실행 순서를 모두 계측한 것은 아니다. 검사용 factory는 일반 gateway factory에 편입하지 않았다.

## 실제 결과

| 항목 | 납품된 run (`other`) | 미확정 run (`buyer`) |
| --- | --- | --- |
| 자체 주문/지급 key | 두 run에서 동일 문자열 사용 | run별 격리 |
| checkout 결과 | order 응답 | `MEDUSA_HTTP_400` |
| 인증된 Store 주문 목록 | 1개 | 0개 |
| 최종 수령 | 텐트 3·조명 6 | 0·0 |
| 지출 / 예약 / 가용 | 310 / 0 / 190 | 0 / 310 / 190 |
| 독립 판정 | COMPLETE | UNKNOWN |

실제 재고는 초기 텐트 3·조명 6에서 최종 0·0, 예약 수량도 0이었다. 납품 조회 오류는 0건이었다. checkout 오류 본문은 StoreAPI가 보존하지 않으므로 구체적인 Medusa 오류 code를 추정하지 않는다.

동일 지급 key를 다시 동시에 호출하고 gateway를 재시작한 뒤 재조회해도 상태·예산·수령은 유지됐다. 전체 trace에서 두 run을 합쳐 checkout POST는 2회뿐이었다. 각 예산 원장에 intent는 1개이며, 다른 run의 주문 ID는 양방향 NOT_FOUND였다. 미확정 run의 B 380 대체 주문은 접수되지만 지급은 BUDGET_EXCEEDED로 거절됐고 새로운 intent는 생기지 않았다.

두 고객의 실제 Store 주문 목록을 로컬 mapping과 별도로 조회했다. 미확정 run의 외부 주문이 없다는 현재 관측을 근거로 예약을 자동 해제하지 않았다. collection/session 생성 이후 전체 rollback·지급 취소를 확인하는 계약이 없기 때문이다. 패자의 무기한 예약·명시적 취소/해제 경로는 여전히 미구현이며, 이 검사 통과가 그 사용성 문제의 해결을 뜻하지 않는다.

## 검사와 증거

- [실행 보고서](../../evidence/cw05-race/race-report.json), [구매자 원장](../../evidence/cw05-race/race-evidence-0.json), [다른 구매자 원장](../../evidence/cw05-race/race-evidence-1.json), [실제 요청 trace 262건](../../evidence/cw05-race/race-trace.jsonl), [SHA-256 manifest](../../evidence/cw05-race/sha256.json).
- 각 raw export를 독립 검증기로 재계산해 COMPLETE/UNKNOWN을 확인했다. 두 barrier 도착·HTTP 중첩·재시작/재조회 포함 checkout 총 2회를 trace에서 다시 계산했다. 실행 소스 9개(설치된 Medusa workflow/step 포함)와 artifact 4개 hash를 대조했다.
- 저장 JSON/JSONL에 fixture observer/buyer/control/Store/admin 토큰이 없는지 확인했다. 새 fixture만 사용하며 기존 프로젝트·상품·볼륨을 삭제하지 않았다.
- [오프라인 회귀](../../tests/commerce/test_stock_changes.py) 2개 추가: 별도 gateway 객체 4개의 같은 key 동시 지급→checkout/intent/정산 각 1개, 두 주문의 동시 지급→하나 SETTLED·하나 BUDGET_EXCEEDED. 실제 파일 잠금을 사용하는 HTTP replay이며 Medusa 재고 경합과는 별도다.
- `make check` PASS: Python 285개·mypy 39개 소스·ruff·offline lock·웹 빌드. 기존 TestClient deprecation 2개 유지. 브라우저 코드는 변경하지 않았으며 이번 작업에서 browser gate는 재실행하지 않았다(직전 19개 통과).
- 전용 서비스 종료 후 18001/19000/55432/56379 포트 반환과 다른 개발 포트 18000/15173 비점유, 데이터 볼륨 2개·기존 다른 컨테이너 4개 보존 확인. 실제 모델 0회, AWS·배포·커밋·푸시 없음.

## 다음 범위

분산 Medusa 인스턴스·다른 경합 시점·장시간 부하·실제 모델의 대체 판단은 미검증이다. 모델 설정 대기 중 다음 로컬 우선순위는 [CW04 독립 검토 연결](../plans/2026-09-06-custom-world-poc-plan.md)의 3번, 구매 재실험에도 공통 사용량/비용 한도를 적용하는 B3 실행 연결이다. fixture로 실제 Peer Review 효과를 주장하지 않는다.
