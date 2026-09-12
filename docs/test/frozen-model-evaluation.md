# CW07 — 연습 뒤 정책 동결과 별도 평가 세계

2026-09-08. B2/B3 연습 결과를 기존 동결 정책 manifest로 연결하고, 새로운 구매 Agent와 별도 세계에서 평가하는 경로를 구현했다. B0/B1은 연습 없이 고정 정책을 평가한다. **B1~B3의 현재 실행은 결정론적 SDK fixture이며 실제 모델 성능·학습 효과·미공개 조건 평가를 뜻하지 않는다.**

## 동결과 새 실행의 경계

[frozen_run.py](../../src/rehearsal/evaluation/frozen_run.py)의 `run_cell`은 시작 전에 방식·학습/평가 조건·설정·소스 hash를 `spec.json`으로 보존한다. 조건의 실제 내용이 같으면 이름이나 seed만 달라도 거절한다. 현재 학습은 알려진 견적 후 가격 변경, 평가는 처음부터 A 텐트 재고가 0인 알려진 조건이다. 이 차이를 미공개 조건 일반화로 부르지 않는다.

B2는 같은 Agent의 자기 연습, B3는 별도 검토자가 포함된 기존 실행 경로를 사용한다. 학습이 한도·실패·미확정 usage로 끝나면 평가를 NOT_RUN으로 남긴다. 조용히 초기 정책으로 대체해 평가 성공을 만들지 않는다. NO_CHANGE일 때는 명시적으로 초기 정책을 유지한다.

정책을 고를 때 학습 보고서·실험·검토·응답 등 JSON/텍스트 자료의 hash를 동결 manifest에 연결한다. 평가는 새로운 Agent·provider 인스턴스·대화·세계에서 실행하며 **동결 정책만 전달**한다. 학습 trace나 평가 조건 전체를 프롬프트에 붙이지 않는다. 세계의 공개 구매 도구로 목표·재고/견적을 관측한다. 후보 사용은 평가를 위한 것이며 운영 정책의 자동 승격은 아니다.

평가 직전 manifest를 다시 읽고, 이후에도 정책 파일·학습 자료·spec·소스의 변경을 확인한다. 학습 모델 인스턴스를 평가에 재사용하거나 동결 파일을 바꾼 경우 provider 호출 전에 거절한다. 평가 중 학습 자료 변조가 발견되면 평가의 원장은 보존하되 연결 결과를 REJECTED로 남긴다.

## 학습과 평가가 나눠 쓰는 한도

[기존 단일 구매 실행자](../../src/rehearsal/agents/runner.py)에 공유 원장을 선택적으로 받을 수 있게 했다. B2/B3 학습의 `usage.sqlite3`를 같은 설정으로 다시 열어 평가 호출을 `buyer_evaluation` 역할로 기록한다. 설정이 다르거나 같은 실행 accounting ID가 이미 있으면 거절한다. 학습의 비용·토큰·도구 수를 뺀 잔여 한도만 평가에 사용할 수 있다.

보고서에는 `learning_usage`, 평가 역할의 `evaluation_usage`, 전체 `total_usage`가 있다. 전체 비용에 학습 비용을 다시 더하지 않는다. usage 누락은 예약을 유지하며, 평가가 0회 호출로 한도 거절된 경우도 실패/미실행 상태와 이유를 남긴다. B0는 모델 호출이 없으므로 고정 규칙 도구 trace 수를 별도로 합산한다.

원장 COMPLETE와 Agent 정상 종료는 별도다. 최종 응답이 잘리면 Strands 1.54.0은 `MaxTokensReachedException`을 발생시킨다. 실제 fixture에서 납품 COMPLETE·usage 기록 완료와 실행 ERROR를 동시에 확인했고, 평가 정상 완료로 취급하지 않았다.

## 재현과 알려진 관측

```sh
make frozen-evaluation-smoke       # B0 + B1/B2/B3 SDK fixture; AWS 없음
make frozen-evaluation-preflight   # 설정 형식만 검사, AWS client 없음
```

최종 실행: `frozen_1882f855b318409884a7f6c950d86308`. [전체 보고서](../../evidence/cw07-frozen-evaluation/report.json), [46개 artifact hash](../../evidence/cw07-frozen-evaluation/manifest.json). 각 방식의 spec·동결 정책·학습/평가 보고서·도구 trace·raw export를 보존했다. DB는 ignored `.local/evaluation/`에 남긴다.

| 방식 | 학습 비용 | 평가 비용 | 총 fixture 호출/토큰 | 총 도구 | 평가 원장 |
|---|---:|---:|---:|---:|---|
| B0 고정 규칙 | 0 | 0 | 0 / 0 | 24 | COMPLETE·380 |
| B1 단일 구매 | 0 | 392 | 14 / 280 | 13 | COMPLETE·380 |
| B2 자기 연습 | 644 | 392 | 37 / 740 | 35 | COMPLETE·380 |
| B3 독립 검토 포함 | 616 | 392 | 36 / 720 | 31 | COMPLETE·380 |

비용 단위는 **가상 micro-USD**이며 입력 1·출력 2 USD/백만 토큰이라는 fixture 단가를 사용한다. 네 방식은 동일한 평가 조건/목표와 48호출·48도구·100,000토큰·100,000 micro-USD 한도를 사용했다. B0/B1의 고정 입력은 견적 갱신을 하는 정책이며 B2/B3 학습은 기존 견적 갱신 누락 사례에서 시작한다. 따라서 이것은 동일한 초기 정책으로 수행한 정식 비교 평가가 아니라 구성/회계 연결 검증이다. 현재 후보와 고정 입력이 같은 정책으로 귀결됐다는 사실도 효과로 해석하지 않는다.

원장 export 재판정, 호출 원본 행으로 토큰/비용 재합산, 단계별 비용 합계, 학습/동결/spec/소스 hash를 독립 대조했다. 알려진 5조건×4방식 pilot의 B1/B2/B3 15칸은 실제 모델 실행이 없어 여전히 NOT_RUN이다. 이 단일 조건 SDK fixture로 그 칸을 채우지 않았다.

## 검사와 남은 범위

[전용 회귀 23개](../../tests/evaluation/test_frozen_run.py): 네 정상 방식, 새 대화/정책 전달, B2/B3 각각의 호출·토큰·비용·도구 잔여 한도, 평가 usage 누락/부분 누락/예외, 학습 실패, 동결 파일 수정/삭제, 학습 자료 변조, provider 문맥 재사용, 조건 이름/seed 재포장, 납품 뒤 응답 잘림을 검사했다.

최종 `make check` PASS: Python 368개·mypy 44소스·ruff·lock·웹 빌드. 기존 TestClient 경고 2개 유지. 첫 전체 gate의 잘린 응답 기대값 1건은 실제 SDK 예외 기록을 확인한 뒤 교정했으며 재실행 PASS다.

`frozen-evaluation-preflight`는 모델 ID·단가·한도·출처 누락으로 exit 2다. 실제 호출 경로는 `--execute --method B1`(또는 B2/B3)처럼 한 방식을 명시해야 하고, 한 설정 예산으로 학습+평가를 실행한다. 실제 실행·공식 단가/권한 검증은 아직 하지 않았다.

다음은 다중 조건·반복·방식별 전체 분모를 고정하는 평가 배치/명세와 실제 모델 실행이다. 미공개 20조건 본 평가·개발자 관찰·수정 B0의 Medusa 재실행·모델 재계획·전체 지연 목표는 남았다. 이번에는 브라우저·Medusa·설치·AWS·커밋·푸시·배포를 수행하지 않았다.
