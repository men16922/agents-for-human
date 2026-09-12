# CW03 실행 준비와 CW04 상태 복제·정책 기록

2026-09-07. 실제 AWS/모델 호출 없이 CW03 실행·사용량 원장과 CW04 상태 복제·정책 재실험 경로를 구현했다. **CW03의 실제 모델 완료·비용 검증과 CW04의 모델 기반 Peer Review는 아직 미완료다.**

## CW03의 실행 명령

- `make agent-preflight`: 프로젝트 `.env`와 명시된 환경변수의 설정 형식만 확인한다. AWS client·자격증명 조회·모델 호출을 하지 않는다.
- `make agent-run`: 설정 검증 후 선택한 Bedrock 모델을 실제 호출한다. `.local/model/cw03_<id>`에 지급/상점/사용량 DB, 도구 trace, 최종 응답과 독립 판정을 저장한다. 같은 디렉터리를 덮지 않는다.
- 이번 실제 preflight는 모델 ID·비용 한도·단가 설정이 없어 종료 코드 2로 중단됐다. profile·리전은 환경변수에서 해석될 수 있으나, 임의 기본 모델을 선택하거나 호출하지 않는다.

필수 설정은 `.env.example`에 있다. 사용자에게 요청한 profile·리전·모델 ID·비용 상한을 확인한 뒤, 선택 모델/리전의 공식 단가를 조회해 `REHEARSAL_PRICE_INPUT`, `REHEARSAL_PRICE_OUTPUT`, `REHEARSAL_PRICE_CACHE_READ`, `REHEARSAL_PRICE_CACHE_WRITE`와 `REHEARSAL_RATE_SOURCE`를 채운다. 단위는 USD/백만 토큰이다. 현재 단가나 권한을 검증하지 않았고 실제 `.env`를 덮지 않았다.

기본 호출 제한은 모델 12회·도구 24회·입력 추정 8,000토큰·응답 최대 1,024토큰·전체 120초다. `REHEARSAL_MAX_MODEL_CALLS`, `REHEARSAL_MAX_TOOL_CALLS`, `REHEARSAL_MAX_INPUT_TOKENS`, `REHEARSAL_MAX_OUTPUT_TOKENS`, `REHEARSAL_MODEL_TIMEOUT_SECONDS`로 명시할 수 있다. SDK와 botocore 자동 재시도는 끈다. 별도 원격 CountTokens 호출도 사용하지 않는다.

## 사용량·비용 원장

`src/rehearsal/agents/metering.py`가 SQLite에 호출 직전 `STARTED`를 저장하고, 호출 후 입력·출력·cache read/write usage와 추정 비용을 기록한다. 단가도 run에 고정하며 기존 run의 모델·단가·한도를 바꿀 수 없다.

2026-09-08 보완: SDK가 누락 usage를 0으로 채우는 경로를 재현했다. `ObservedModel`로 provider stream 원본 usage를 보존한 뒤 `AfterModelCallEvent`에서 기록한다. 실패·중단·응답 유실·불완전 usage는 `ERROR` 또는 `USAGE_UNKNOWN`으로 남는다. 도중 종료로 `STARTED`가 남아도 미확정 예약을 유지하고 다음 호출을 막는다. 확인 불가능한 사용량을 0원으로 처리하지 않는다.

비용 계산은 정수 micro-USD로 올림한다. 호출 전 입력 cap과 출력 cap에 따른 보수적 비용을 예약하고, 확인된 usage로 정산한다. 입력 허용 검사는 SDK 추정치에 의존하므로 **실제 청구액의 절대 상한을 보장하지 않는다.** 실제 usage가 예약보다 크면 값을 잘라내지 않고 초과를 기록하며 후속 호출을 막는다. `billing_verified=false`는 항상 유지한다. live 단계에서 실제 모델 usage와 공식 단가를 대조해야 한다.

실행 명령은 모델 종료와 목표 완료를 구분한다. 독립 판정 `COMPLETE`, 실제 기록된 호출 1건 이상, 전체 usage 확인, 비용 추정 한도 내, 정상 종료를 모두 만족해야 exit 0이다. 한도 중단·모델 예외에서도 보고서와 독립 판정을 남긴다.

[오프라인 SDK 보고서](../../evidence/cw03-offline/report.json), [원장 증거](../../evidence/cw03-offline/evidence.json), [도구 trace](../../evidence/cw03-offline/tools.jsonl)를 보존했다. 스크립트 모델 7회 응답·6회 도구 실행, fixture 입력 84·출력 56을 기록했다. 가상의 입력 1/출력 2 USD/백만 단가로 계산한 **196 micro-USD는 계산 검사값이며 실제 사용 비용이 아니다.** 실제 AWS·모델 호출은 0회다.

## CW04의 상태 복제

`src/rehearsal/world/fork.py`는 상점→지급 순서로 두 저장소를 잠가 일관된 snapshot을 확보한 뒤 선택한 run만 복사한다. 다른 run 데이터·모델 자격증명·사용량 원장은 복사하지 않는다. 원본에는 쓰지 않는다.

- 복제 대상은 독립 디렉터리의 두 SQLite DB이며 `environment=practice`, 새 run/policy ID와 parent snapshot hash를 기록한다.
- 주문·견적·지급 ID는 복제 저장소 안에서 보존한다. 이벤트 ID와 receipt 참조는 새로 발급하고 `fork.json`에 부모 이벤트 대응을 남긴다. 복제된 과거는 `inherited_snapshot`이며 새로 실행한 거래가 아니다.
- 미지급 예약·지급 확정 후 미반영 outbox·이미 수령한 상태를 모두 복제하고 재처리 중복을 막는다.
- 모르는 schema·기존 목적지·없는 source run은 거절한다. 복제 도중 실패한 `CREATING` 저장소는 `World`로 다시 열 때도 거절한다. 원본이나 실패한 대상 폴더를 자동 삭제하지 않는다.
- 이 복제기는 로컬 SQLite 세계 전용이다. Medusa DB를 복제하거나 외부 정책 전이를 수행하지 않는다.

## 정책 데이터와 반례 연결

`Policy`는 공급처 선택 기준, 견적 재조회, 후보 수, 대기 간격의 작은 데이터 schema다. content hash로 버전을 만든다. 임의 코드·모르는 필드·미확정 지급의 새 결제 정책을 받지 않는다. 서버의 예산·수취인·멱등 규칙은 정책 변경 대상이 아니다.

`record_revision`은 최대 2라운드·라운드별 1~2개 반례와 실제 실험 artifact hash를 연결해 before/after 정책 diff를 저장한다. 반례의 policy version이 다르면 거절하고 기존 기록을 덮지 않는다. 제안은 자동 채택되지 않는다.

```sh
make policy-smoke
```

같은 pre-purchase snapshot을 두 번 복제해 A 가격 변경을 주입한다. 기존 정책은 stale quote로 거절되어 기한에 목표 실패·지출 0, 재조회 정책은 B 380을 선택해 수령한다. 별도 보고서가 반례 → 정책 diff → 재실험 ID/hash를 연결한다. 실험은 구매 모델과 동일한 등록 도구를 호출한다.

[재실험 보고서](../../evidence/cw04-offline/report.json), [기존 정책](../../evidence/cw04-offline/before/experiment.json), [수정 정책](../../evidence/cw04-offline/after/experiment.json), [정책 변경 기록](../../evidence/cw04-offline/revisions/policy-19bfdf8cfe268f1c--policy-d3b91f7487599065.json)을 보존했다.

검토자는 `scripted-fixture`다. 알려진 한 사례에서 경로를 확인했으며 모델 토론 효과·새 조건 일반화·정책 자동 승격은 검증하지 않았다. 이 재실험 runner는 구매 전 snapshot만 받는다. fork 자체의 중간 거래 상태 지원과 구별한다.

2026-09-08 후속: [독립 검토 실행 경로](independent-review.md)와 원본 usage 경계를 추가하고 SDK fixture로 검증했다. 실제 모델 검토와 B3 전체 평가는 여전히 미완료다.

최종 오프라인 `make check`: Python 75개·mypy 19개 소스·ruff·웹 빌드 PASS. 문서 링크와 정책/재실험 artifact hash도 대조했다. 브라우저·실제 모델·AWS 호출은 이번 작업에서 실행하지 않았다.
