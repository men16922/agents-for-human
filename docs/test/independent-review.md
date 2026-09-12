# CW04 — 독립 검토 실행과 후보 재실험

2026-09-08. 도구 없는 독립 Strands 검토 실행, 후보 정책 검증, 같은 snapshot 재실험, 라운드 공통 사용량 원장을 연결했다. **검증 모델은 SDK 프로토콜 fixture다. 실제 모델 검토·Peer Review 효과·새 조건 일반화·학습된 정책 전이는 미검증이다.**

## 실행 경로

[review.py](../../src/rehearsal/experiments/review.py)는 운영자가 지정한 1~2개 실험 artifact와 인접 `evidence.json`·`fork.json`만 읽는다. 정책 버전, 원장 hash, READY fork의 run/정책/snapshot을 대조하고 독립 판정을 다시 계산한다. 저장된 성공 문구만으로 판정하지 않는다. 검토 입력은 정책과 실험의 공개 도구 trace·독립 판정이며 임의 파일 조회 도구를 제공하지 않는다.

최대 2라운드이며 라운드마다 새로운 모델 인스턴스·Agent·대화 문맥을 사용한다. 등록 도구는 없고 도구 요청도 거절한다. 공급처 설명과 실험 문구는 비신뢰 데이터다. 출력은 JSON 객체 하나로 제한하며 `decision`, `reason`, `counterexamples`, `candidate_policy`만 받는다. 중복 JSON 키·모르는 실험 ID·권한/예산 필드·미확정 지급 대체 정책·잘린 응답은 거절한다.

후보가 있으면 기존 `record_revision`으로 실험 hash와 정책 diff를 기록하고, 운영자가 연결한 기존 스크립트 재실험을 수행한다. 재실험 artifact의 원장·fork·동일 snapshot을 다시 검증한다. 기존 명령의 재평가 계약은 `known-scripted-counterexample-not-model-review`다. 이후 [B3 공통 회계](b3-shared-accounting.md)에서 초기/후보 구매 실행자와 검토의 공유 원장을 SDK fixture로 검증했다. 새 조건 평가는 남았다.

상태 `CANDIDATE_EVALUATED_NOT_PROMOTED`는 후보의 알려진 사례 재실험을 기록했다는 뜻이다. 원래 정책은 보존하며 자동 승격하지 않는다. 다음 검토가 실패하거나 예산이 부족해도 이미 기록한 제안을 지우지 않는다.

## 사용량을 0으로 오인하지 않는 경계

모든 검토 라운드가 한 `UsageLedger`의 비용 한도를 공유한다. 라운드별 사용량, 검토자 합계, 스크립트 재평가의 모델 호출 0회를 구별한다. 전체 모델 호출 설정도 라운드 간 적용하며, 실패/미확정 usage가 있으면 다음 라운드를 막는다. 비용은 설정된 가상/실제 단가에 따른 추정이며 청구 절대 상한이나 실제 청구 확인이 아니다.

새 검사에서 Strands 1.54.0이 원본 metadata가 없거나 usage 필드가 빠져도 기본 0을 채우는 동작을 재현했다. 기존 계측은 이를 RECORDED로 오인할 수 있었다. `ObservedModel`이 SDK 집계 전 provider stream의 원본 usage 존재 여부를 보존하도록 바꾸고 CW03 구매 실행자와 검토자 양쪽에 적용했다. 누락은 `USAGE_UNKNOWN`·예약 유지이며 다음 호출을 거절한다.

## 명령과 증거

```sh
make review-smoke       # 오프라인 SDK fixture, 실제 모델 호출 없음
make review-preflight   # 설정 형식만 확인, AWS client 생성 없음
```

실제 검토는 모델 설정·단가·비용 범위 확인 후 `scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.experiments.review_runner --execute`로 명시한다. 이 명령도 재실험자는 스크립트이며 모델 기반 구매 평가가 아니다. 이번 preflight는 모델 ID·비용·단가·출처 누락으로 exit 2, 실제 호출은 0회다.

`make review-smoke` PASS: 알려진 stale quote 실패를 검토하는 fixture가 재조회 정책을 제안하고, 같은 snapshot의 B 380 재실험을 COMPLETE로 확인한 뒤 두 번째 fixture가 변경 없음을 응답했다. [보고서](../../evidence/cw04-review-offline/review/report.json), [검토 전 실험](../../evidence/cw04-review-offline/before/experiment.json), [재실험](../../evidence/cw04-review-offline/review/round-1/reexperiment/experiment.json)을 보존했다. 입력·응답·fork·원장·revision과 소스 hash를 대조했다.

fixture 응답 2회, 가상 입력 24·출력 16토큰, 가상 단가로 **56 micro-USD**다. 실제 청구된 비용이 아니다. [독립 검토 회귀](../../tests/experiments/test_review.py) 18개와 [구매 실행자 raw usage 회귀](../../tests/agents/test_executor.py) 3개 추가 PASS. 최종 `make check` PASS: Python 212개, mypy 36개 소스, ruff·lock·웹 빌드. 기존 TestClient 경고 2개 유지.

모델·AWS·브라우저·Medusa 실행·설치·커밋·푸시 없음. 이후 완료 범위와 다음 시작점은 [B3 공통 회계 기록](b3-shared-accounting.md)과 [현재 계획](../NEXT_PLAN.md)을 따른다.
