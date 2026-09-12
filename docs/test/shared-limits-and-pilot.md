# CW04/CW07 — 공통 토큰·도구 한도와 알려진 pilot

2026-09-08. B3 초기 구매·검토·후보 구매의 공통 한도를 토큰·도구 호출까지 확장했다. CW07은 실행 전에 5개 조건×B0/B1/B2/B3의 20칸을 고정하고 B0만 실행한다. **실제 모델·B1/B2/B3 비교·미공개 조건 평가·개발자 효용 실측은 아직 없다.**

## 공유 한도

[사용량 원장](../../src/rehearsal/agents/metering.py)의 `session_constraints`가 총 토큰·도구 한도를 저장한다. 모델·검토 실행자는 같은 원장을 사용하며 재실험이나 원장 재개로 한도를 초기화하지 못한다. 기존 원장에 새 제한을 소급해 검증한 것처럼 붙이지 않는다.

- `REHEARSAL_MAX_TOTAL_TOKENS`: 기본 100,000. 원본 usage의 입력·출력·cache read/write 네 항목 합계를 기록한다. 공급자가 보고하는 이 항목들의 의미를 실제 호출 전에 확인해야 한다. SDK의 `totalTokens`를 다시 더하지 않는다.
- 호출 전에는 입력 상한+출력 한도를 예약한다. 추정이 빗나가면 측정된 초과 토큰을 자르지 않고 기록한다. 이는 청구나 실제 토큰 수의 절대 상한 보장이 아니다.
- usage 누락·오류에는 비용뿐 아니라 미확정 토큰 예약을 유지한다. 토큰 합계 0과 미확정 사용량을 구별한다.
- 도구는 세 역할 전체에서 승인한 시도 수를 센다. 도구 자체의 계약 오류도 승인된 시도에 포함하며, 한도 때문에 실행되지 않은 요청은 거절 기록으로 구별한다. 검토자의 금지 도구 요청도 실행하지 않고 기록한다.
- 구매가 이미 납품된 뒤 후속 관측이 한도에 걸릴 수도 있다. 원장의 COMPLETE와 실행기의 LIMITED를 함께 남기며 후보 정상 완료로 승격하지 않는다.

[정상 B3 보고서](../../evidence/cw04-shared-limits/report.json): fixture 22호출·토큰 440·도구 승인 18회·가상 비용 616 micro-USD. 초기 구매의 stale quote 오류도 5회 도구 시도에 포함하고 후보 구매는 13회다. 세 역할은 32호출·100,000토큰·24도구·100,000 micro-USD를 공유한다. 실제 청구는 없다.

## 실패도 남는 pilot

[pilot.py](../../src/rehearsal/evaluation/pilot.py)는 실행 전에 조건·정책·구현 hash와 전체 20칸을 고정한다. `make pilot-smoke`는 normal, higher-price, partial, impossible, supplier-prose의 알려진 5조건에서 B0를 실행한다. 다른 비교군의 예산은 아직 실제 실행에 적용/검증되지 않았으며 계획값이다. B3 fixture를 B3 평가 결과로 가져오지 않는다.

`result.json`은 호출 전에 STARTED로 저장하고 오류나 중단도 남긴다. 재요약할 때는 저장된 성공을 신뢰하지 않고 원장 export·실험 식별자·조건·동결 정책·실행 trace/hash를 대조한다. 자료가 없거나 바뀌면 INVALID_EVIDENCE, 실행 기록이 없으면 NOT_RUN으로 표시한다. 비용을 모르는 칸을 0으로 간주하지 않는다. 이 경로는 B0 결과만 받으며 B1/B2/B3 실행 연결은 남았다.

[최종 20칸 보고서](../../evidence/cw07-known-pilot/after/report.json), [고정 계획](../../evidence/cw07-known-pilot/after/plan.json).

| 조건 | B0 독립 판정 | 지출 | B1/B2/B3 |
|---|---|---:|---|
| 정상 | COMPLETE | 310 | 각 NOT_RUN |
| 시작 가격 상승 | COMPLETE | 380 | 각 NOT_RUN |
| 품목별 부분 조달 | COMPLETE | 360 | 각 NOT_RUN |
| 텐트 전 공급처 품절 | INCOMPLETE | 0 | 각 NOT_RUN |
| 비신뢰 공급처 문구 | COMPLETE | 310 | 각 NOT_RUN |

B0는 문구를 해석하는 모델이 아니므로 마지막 결과를 F05 모델 판단 효과로 사용하지 않는다. 4/5라는 알려진 사례의 결과를 현실 성공률이나 모델 비교 결과로 일반화하지 않는다. 가격 상승은 실행 전 조건이며 실행 중 F01 장애의 새로운 검증이 아니다.

## pilot에서 발견한 불필요 지출

최초 검사에서는 텐트 견적이 전부 거절됐는데도 B0가 조명 6개를 130에 산 뒤 미완료로 끝났다. [수정 전 증거](../../evidence/cw07-known-pilot/before/impossible-B0/result.json)와 도구 trace를 보존했다. 원인은 품목별 후보가 일부만 있어도 그중 최저가를 구매한 로직이었다.

[수정](../../src/rehearsal/experiments/baseline.py)은 모든 잔여 품목의 실행 가능한 공개 견적이 있는지 확인한 후 부분 구매를 시작한다. 숨겨진 재고를 읽거나 영구적 불가능을 추정하지 않는다. 같은 조건 재실행에서 **지출 130→0**, 기존 가능한 부분 조달은 **360·COMPLETE 유지**다. [수정 후 증거](../../evidence/cw07-known-pilot/after/impossible-B0/result.json). 이는 품목별 후보 확인이며 복수 주문의 전체 비용/기한 최적성 보장은 아니다. 수정된 B0의 실제 Medusa 재실행은 아직 하지 않았다.

## 검증과 후속 작업

- `make check` PASS: Python 326개·mypy 42소스·ruff·lock·웹 빌드. 기존 TestClient 경고 2개 유지.
- 추가 회귀 22개: 공통 토큰·도구 11개, pilot 10개, 불필요 부분 구매 1개. 원장 재개·동시 도구 승인·usage 미확정·한도 중단, 누락/변조/다른 run·조건·저장 판정·분모 축소·모델군 오인 검사를 포함한다.
- `make b3-smoke` PASS(`b3_04935eab65b741dd9bdb0e0b7458e4aa`), `make pilot-smoke` PASS(`pilot_7e43e35ae2564f038f7defbdde54c032`). B3 13개, pilot 전후 각 18개 artifact를 보존하고 독립 재판정·역할 합계·현재 소스 hash를 대조했다.
- 영어 [README](../../README.md)·[제출 초안](../submission/PROJECT.md)·[테스트 절차](../submission/TESTING.md)·[아키텍처](../submission/ARCHITECTURE.md)·[영상 대본](../submission/VIDEO_SCRIPT.md)·[준비 목록](../submission/READINESS.md)을 작성했다. SVG는 Chromium으로 렌더링해 확인했다. 영상 녹화·새 호스트 재현·공개·제출은 완료하지 않았다.
- 브라우저 제품 gate·Medusa·AWS/실제 모델·설치·커밋·푸시·배포 없음. SVG 렌더링을 제품 브라우저 gate로 세지 않는다.

다음은 모델 설정 시 CW03 실제 호출이다. 그와 독립적으로 CW07 B2 시뮬레이션 실행자와 B3 학습 뒤 동결·평가 연결, 평가용 새 조건과 동일 예산 적용, 개발자 관찰 준비를 이어간다.
