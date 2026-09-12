# CW04 — 초기 구매·검토·후보 구매의 공통 비용 원장

2026-09-08. 작업 트리에 있던 B3 실행 연결을 이어서 검증하고, 호출 전 거절 기록과 역할별 토큰·실패/예약 집계를 보강했다. **실행 모델은 모두 결정론적 SDK fixture다. 실제 모델 호출·Peer Review 효과·새 조건 일반화·학습된 정책 전이는 미검증이다.**

## 실행과 회계 경계

[b3.py](../../src/rehearsal/experiments/b3.py)는 초기 구매 → 도구 없는 독립 검토 → 후보 구매 → 두 번째 검토를 연결한다. 구매마다 [기존 실행자의 도구·입력 경계](../../src/rehearsal/agents/executor.py)를 사용하며, 각 단계는 새 모델 인스턴스와 Agent로 시작한다. 초기 정책은 견적 갱신을 생략하고 fixture 검토자가 갱신을 제안한다. 첫 견적 후 A tent 단가를 100으로 바꾸는 운영자 지정 조건이며, 모델이 발견한 반례나 미공개 평가 조건이 아니다.

[model_experiment.py](../../src/rehearsal/experiments/model_experiment.py)는 동일한 부모 snapshot에서 초기/후보 세계를 fork한다. 공개 도구 trace, 실행 중단 사유, 독립 원장 export와 판정, 정책 버전, 호출 ID/hash를 남긴다. [review.py](../../src/rehearsal/experiments/review.py)는 원장·fork·정책·snapshot에 더해 공유 usage의 역할/실험 ID/범위/hash를 대조한다. 모델 구매의 비용을 스크립트 재평가 0호출로 처리하지 않는다. 후보는 자동 승격하지 않고 부모 세계를 보존한다.

[UsageLedger](../../src/rehearsal/agents/metering.py)는 한 세션의 모델 호출 수·추정 비용 상한을 세 역할에 공통 적용한다. 가격표·모델 ID·입출력 한도·fixture/live 범위·호출 상한이 다른 원장은 거절하며 재개할 때도 설정을 변경할 수 없다. 예약과 공유 호출 수 확인은 SQLite transaction 안에서 수행한다.

- `buyer_initial`, `reviewer`, `buyer_candidate`별 호출 수, 기록된 입력/출력/cache 토큰, 추정 비용과 미확정 예약을 집계한다.
- 호출 상태 `STARTED`, `RECORDED`, `USAGE_UNKNOWN`, `ERROR`의 분모를 보존한다. 기록된 토큰 합계는 미확정 호출의 토큰이 0이라는 뜻이 아니다.
- 호출 전 거절은 `admission_rejections`에 역할·실행 ID·사유를 남긴다. 실제 provider 호출 수에 더하지 않으며, 호출이 0회인 후보도 거절 기록에서 확인할 수 있다.
- 원본 provider usage가 없거나 일부만 있으면 예약을 유지한다. 실패나 미확정 호출 뒤에는 다른 역할도 다음 호출을 할 수 없다. 이미 기록한 정책 제안은 보존한다.
- 예산은 입력 상한과 출력 한도로 호출을 사전 승인하는 추정 비용 기준이다. 실제 청구 절대 상한이 아니다. 이 기록 시점의 도구 호출 한도는 구매 실행별이었다. 이후 [공통 토큰·도구 한도](shared-limits-and-pilot.md)를 SDK fixture로 검증했다. B1/B2/B3 비교의 실제 동일 예산 적용은 남아 있다.

## 검증 결과

```sh
make b3-smoke       # 실제 Strands SDK + 결정론적 provider fixture
make b3-preflight   # 설정 형식만 확인, AWS client 생성 없음
make check         # 오프라인 gate
```

최종 `make b3-smoke` PASS: `b3_c41a980a95994cc7894885a6169bf0ab`. [보고서](../../evidence/cw04-b3-offline/report.json)와 [artifact hash 목록](../../evidence/cw04-b3-offline/manifest.json)에 13개 JSON/텍스트 artifact를 보존했다. 원본 SQLite는 ignored `.local/experiments/`에 있고 호출 행은 보고서에도 보존한다. 소스 hash 10개, 원장 export 재판정, 역할별 호출·비용 합계를 별도로 대조했다.

| 역할 | fixture 호출 | 입력 토큰 | 출력 토큰 | 가상 비용(micro-USD) |
|---|---:|---:|---:|---:|
| 초기 구매 | 6 | 72 | 48 | 168 |
| 독립 검토 2회 | 2 | 24 | 16 | 56 |
| 후보 구매 | 14 | 168 | 112 | 392 |
| 합계 | 22 | 264 | 176 | 616 |

가상 단가는 입력 1·출력 2 USD/백만 토큰이며 실제 청구는 없다. 초기 실험은 stale quote로 구매하지 못해 INCOMPLETE·지출 0, 후보는 B 구매·수령 완료로 독립 COMPLETE·380이다. 두 실험의 snapshot hash가 같고 초기 정책·부모 세계는 보존됐다. `CANDIDATE_EVALUATED_NOT_PROMOTED`는 알려진 조건에서 후보 재실험을 기록했다는 뜻이다.

[전용 회귀 19개](../../tests/experiments/test_b3.py) PASS: 역할 전환/후보 도중 공유 호출 상한 4조건, 초기/검토/후보 비용 거절 4조건, 세 역할 각각의 usage 누락·부분 누락·예외 9조건, 정상 증거 대조, attribution 변조·공유 설정/재개 상한 변경 거절. 미확정 호출의 예약 10,048 micro-USD와 후속 호출 차단, 후보 실패 후 revision 보존을 확인했다.

최종 `make check` PASS: Python 304개·mypy 41개 소스·ruff·lock·웹 빌드. 기존 TestClient deprecation 경고 2개는 유지한다. 브라우저·Medusa 검사는 이번에 실행하지 않았다.

`make b3-preflight`는 모델 ID·비용 한도·입력/출력/cache 단가·출처 누락으로 exit 2다. AWS client나 실제 모델은 생성하지 않았다. 설치·전역 설정·커밋·푸시·배포 없음.

## 다음 시작점

[상세 계획 CW04 재개 순서](../plans/2026-09-06-custom-world-poc-plan.md) 3번의 SDK fixture 회계 연결은 완료했다. 모델 ID·단가/출처·비용 범위가 준비되면 CW03 정상 실제 호출부터 검증한 뒤 4번 독립 검토·동일 snapshot 재실험·새 조건 평가로 진행한다. 기존 `review-smoke`는 스크립트 재평가 경로로 계속 구별한다.
