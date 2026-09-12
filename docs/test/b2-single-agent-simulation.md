# CW07 — B2 단일 에이전트 시뮬레이션

2026-09-08. 하나의 Strands Agent와 모델 인스턴스가 같은 대화에서 초기 정책의 연습·관측·자기 수정·후보 연습을 수행하는 경로를 연결했다. **검증 provider는 결정론적 SDK fixture다. 실제 모델 효과·B0/B1/B2/B3 비교·미공개 조건 전이는 미검증이다.**

## B3와 구별되는 실행 경로

[b2.py](../../src/rehearsal/experiments/b2.py)의 `run_b2`는 별도 reviewer나 구매용 자식 모델을 만들지 않는다. Agent가 `begin_experiment`로 격리된 세계를 열고 구매 도구 8개를 직접 호출한 뒤 `finish_experiment`에서 독립 판정을 받는다. 첫 연습의 결과가 같은 대화에 남아 다음 정책/구매를 결정하는 입력이 된다. B3는 구매와 별개 문맥의 검토자를 사용하는 경로로 유지한다.

초기 정책은 견적 갱신을 생략하는 기존 알려진 반례 정책이며, 첫 성공 견적 뒤 A 텐트 단가를 100으로 바꾸는 운영자 지정 조건을 사용한다. 처음 보는 조건이나 모델이 발견한 반례로 부르지 않는다. 실제 비교의 초기 정책·조건·반복·연습/평가 예산은 별도로 정해야 한다.

연습은 최대 두 번이며 첫 번째는 지정 초기 정책으로만 시작한다. 한 연습을 닫기 전 다음 연습을 열 수 없고, 두 세계의 출발 snapshot은 같다. 원본 세계는 구매 대상이 아니며 관리자 reset·권한·예산·수취인 변경 도구가 없다. 이전 연습에서 얻은 주문/견적 ID는 다음 세계에서 사용할 수 없다.

후보 정책은 기존 schema로 검증한다. 최종 JSON의 반례 ID는 초기 정책 실험이어야 하며, 제안된 후보는 두 번째 실험에서 실제로 시험한 정책과 같아야 한다. 실험 artifact·fork·원장 export·원본 호출 행 hash를 대조한 뒤 자기 수정 기록과 정책 diff를 저장한다. 파일 변조·임의 ID·안전 경계 변경·시험하지 않은 후보는 거절한다. 후보는 자동 승격하지 않는다.

## 비용·실패·중단 기록

공통 `UsageLedger`에 모든 모델 호출을 `simulation_agent` 역할로 기록한다. controller와 simulation-1/2의 execution ID로 나누며, 연습 시작/종료 도구도 전체 도구 예산에 포함한다. 일반 구매 도구 오류도 시도 수에 남는다. 호출·추정 비용·총 토큰·도구 한도는 연습 사이에서 초기화하지 않는다.

usage 누락/부분 누락·provider 예외는 미확정 비용 10,048 micro-USD와 토큰 9,024 예약을 유지하고 후속 호출/후보 수락을 막는다(현재 fixture 설정). 원본 stream을 확인하므로 SDK의 기본 0으로 덮이지 않는다. 한도나 모델 오류로 연습이 열려 있으면 미완료 상태와 raw 원장을 보존한다. 세션 report는 호출 전에 STARTED로 기록하며 최종 응답의 원문/hash도 보존한다.

## 실행과 확인한 결과

```sh
make b2-smoke       # 실제 Strands SDK + 결정론적 provider fixture
make b2-preflight   # 설정 형식만 확인; AWS client 생성 없음
```

최종 smoke: `b2_81244731ef86458cb854c299149f79ca`. [보고서](../../evidence/cw07-b2-offline/report.json)와 [9개 artifact hash](../../evidence/cw07-b2-offline/manifest.json), 초기/후보 raw export·fork·정책 diff·응답을 보존했다. 원본 DB는 ignored `.local/experiments/`에 남긴다.

| 항목 | 관측 |
|---|---|
| Agent / provider 인스턴스 | 각각 1개, 같은 대화 유지 |
| 독립 Peer Reviewer | 0회 |
| 초기 연습 | INCOMPLETE·지출 0·구매 도구 5회 |
| 후보 연습 | COMPLETE·지출 380·구매 도구 13회 |
| 전체 fixture 호출 | 23회·입력 276/출력 184토큰 |
| 전체 도구 승인 | 22회: 구매 18 + 연습 시작/종료 4 |
| 가상 모델 비용 | 644 micro-USD·실제 청구 없음 |
| 원본/정책 | 부모 보존·후보 자동 승격 없음 |

[회귀 19개](../../tests/experiments/test_b2.py)로 단일 대화/도구 목록, 세 위치의 usage 누락/부분 누락/예외, 네 공통 한도, 잘못된 반례/정책/미실험 후보/변조, 두 연습 제한과 ID 격리를 확인했다. 독립 export 재판정·실험별 usage hash·소스 hash 8개도 별도로 대조했다.

최종 `make check` PASS: Python 345개·mypy 43소스·ruff·lock·웹 빌드. 기존 TestClient 경고 2개 유지. `b2-preflight`는 모델 ID/단가/비용 한도·출처 누락으로 exit 2이며 실제 모델은 호출하지 않았다. 브라우저·Medusa·설치·AWS·커밋·푸시 없음.

## 다음 작업

[개발자 관찰 절차와 빈 양식](../evaluation/developer-observation.md)도 준비했다. 참가자 0명·실측 0회이며 측정할 수 있는 범위는 증빙 판독 시간/정확성이다. 전체 QA 생산성으로 확대 해석하지 않는다.

CW07 1번의 B2 연습 경로는 SDK fixture까지 준비됐다. 다음은 [상세 계획](../plans/2026-09-06-custom-world-poc-plan.md) 2번 B2/B3 학습 뒤 후보 동결과 별도 평가 실행 연결이다. 기존 20칸 pilot의 B1/B2/B3 15칸은 여전히 NOT_RUN이다. 모델 설정 응답이 오면 CW03 정상 실제 호출부터 우선한다.
