# Aftercare — 데이터·API·검증 계약 v1

작성: 2026-09-06 · 상태: 구현 전 · 상위 설계: [AFTERCARE_DESIGN](AFTERCARE_DESIGN.md)

아래 JSON은 형식을 설명하는 합성 예시다. 실제 AWS ID와 실행 결과가 아니다. 구현 시 이 계약을 `contracts/`의 schema와 동작 테스트로 옮긴다.

## 1. 공통 규칙

- 외부 JSON은 `schema_version: 1`, 시간은 UTC ISO 8601, 금액은 KRW 정수, ID는 서버 발급 불투명 문자열을 사용한다.
- 변경 요청에는 `Idempotency-Key`를 요구한다. 같은 사용자·경로·key와 같은 정규화 body는 동일 결과를 반환하고, body가 다르면 `409 IDEMPOTENCY_CONFLICT`다.
- 일반 API의 알 수 없는 필드·enum·잘못된 시각·음수 금액은 `422`다. 배포 transport metadata는 별도 envelope에서 제거한 뒤 domain payload를 검증한다.
- `owner_sub`, `workspace_id`, ARN, 권한 scope는 사용자 body가 아닌 인증·등록 정보에서 얻는다.
- optimistic concurrency는 job의 `state_version`, 서비스의 `policy_revision`, AWS의 `alias_revision`으로 구분한다. 서로 대체하지 않는다.
- trace에는 request/job/action/evidence ID를 남기고 토큰·자격증명·원본 개인정보를 기록하지 않는다.

## 2. 배송비 검사

등록 probe contract ID는 `shipping-quote-v1`. POST `/quote` 입력은 `zone_id`와 `subtotal_krw`다. 합성 권역은 `MAINLAND`, `REMOTE` 두 개다.

기본 배송비 3,000원은 주문 합계 50,000원 이상이면 면제한다. 원격 지역 추가비 3,000원은 면제하지 않는다. 기대값은 서비스 코드에서 import하지 않고 독립 fixture에 저장한다.

| probe_id | zone_id | subtotal_krw | expected shipping_fee_krw |
|---|---|---:|---:|
| Q01 | MAINLAND | 49000 | 3000 |
| Q02 | MAINLAND | 50000 | 0 |
| Q03 | REMOTE | 49000 | 6000 |
| Q04 | REMOTE | 50000 | 3000 |
| Q05 | REMOTE | 70000 | 3000 |

정상 body는 `shipping_fee_krw`, `currency: KRW`, `zone_id`를 포함한다. 숫자 문자열·필드 누락도 실패다. live 응답에는 관측용 실행 버전·요청 ID를 연결한다. Lambda SDK의 HTTP 성공과 application의 HTTP/body 성공을 별도 필드에 저장한다.

- **A:** 새 버전이 Q04/Q05의 추가비까지 면제해 0원을 반환한다. HTTP는 200이다.
- **B:** 정상·새 버전이 함께 쓰는 권역 조회 의존성이 실패한다. 양쪽 기능 검사 실패, rollback 0회가 기대값이다.
- **C:** probe worker의 읽기/호출 권한 또는 수집 경로를 주입기가 차단한다. 이것은 대상 서비스 기능 실패의 증거가 아니며 health `UNKNOWN`이다.
- **D:** 조사·승인 중 다른 배포가 alias revision을 바꾼다. 오래된 변경안은 폐기하고 기존 job은 `SUPERSEDED`가 된다.

배포 버전과 결함 주입은 Demo Controller만 알고, actor는 동일한 배포 이벤트·도구 관측만 받는다. baseline도 같은 probe와 변경 한도를 사용한다.

## 3. 배포 이벤트

```json
{
  "schema_version": 1,
  "event_id": "evt_example",
  "service_id": "shipping-demo",
  "deployment_id": "release_example",
  "deployed_at": "2026-09-07T03:00:00Z",
  "current_version": "42",
  "previous_version": "41",
  "alias_revision": "revision_example",
  "change_summary": "Updated shipping fee calculation"
}
```

EventBridge source는 `aftercare.deployer`, detail-type은 `DeploymentCompleted`로 정한다. source 이름만으로 인증하지 않고 허용 producer role과 bus policy를 사용한다.

job 중복 키는 `(service_id, deployment_id)`다. 같은 key에 다른 버전·revision이 들어오면 원본 job을 수정하지 않고 충돌을 기록한다. 신뢰하는 producer라도 등록 서비스·이전 버전·현재 alias를 조회해 확인한다. 허용 시각 오차는 미래 60초, 지연 5분 이내로 시작하며 범위를 벗어난 이벤트는 자동 변경 없이 인계한다.

관측 기한은 검증된 이벤트의 서버 수락 시각부터 계산한다. 배포 시각과 수락 시각을 함께 보여주어 지연 수신을 숨기지 않는다. alias가 이미 더 최신이면 job을 `SUPERSEDED`로 기록한다.

## 4. 저장 모델

DynamoDB 테이블 한 개를 사용한다. 아래 key는 v1 access pattern을 위한 설계이며 구현에서 통합 테스트로 확정한다. `JOB` ID로 접근하더라도 API는 소유권을 별도로 검사한다.

| 항목 | PK / SK | 필수 데이터 |
|---|---|---|
| Service | `SERVICE#{id}` / `META` | owner workspace, 허용 ARN/alias/버전, 검사 ID, policy_revision, mode |
| Job | `JOB#{id}` / `META` | owner_sub, service/deployment ID, phase, health, outcome, state_version, incident_epoch, started/deadline/next_due, lease, stop_requested, action_count |
| 배포 중복 방지 | `SERVICE#{id}` / `DEPLOY#{deployment_id}` | canonical payload hash, job_id |
| Action | `JOB#{id}` / `ACTION#{id}` | kind, target_version, expected_alias_revision, policy_revision, epoch, evidence IDs, expires_at, status, result |
| Approval | `JOB#{id}` / `APPROVAL#{action_id}` | approver, decision, action_digest, decided_at, expires_at |
| Observation | `JOB#{id}` / `OBS#{batch_id}` | epoch, contract, route, target/executed version, timestamps, sample count, verdict, S3 reference/hash |
| Event | `JOB#{id}` / `EVENT#{sequence}` | event_type, server timestamp, IDs, UI 요약 |
| Idempotency | `USER#{sub}` / `REQ#{route_hash}#{key_hash}` | request hash, operation ID, response/status |
| Demo lock | `SERVICE#{id}` / `DEMO_LOCK` | run_id, owner_sub, worker lease, reset state |
| Quota | `USER#{sub}` / `QUOTA#{UTC_date}` | reserved runs, counters, limit policy |

GSI1은 active job에만 `DUE` / `next_due_at#job_id`를 부여해 due 후보를 query한다. GSI2는 `OWNER#{sub}` / `started_at#job_id`로 목록을 가져온다. GSI는 탐색용이며 갱신 전에는 원본 항목을 재확인한다.

S3 key는 `jobs/{job_id}/evidence/{evidence_id}.json` 또는 `jobs/{job_id}/sessions/{checkpoint_id}.json`이다. 파일 저장 뒤 hash와 참조를 DB에 등록한다. 저장 중 실패한 항목은 verdict 근거로 사용하지 않는다. TTL은 보관 종료용이며 승인 만료·작업 종료·잠금 해제에 사용하지 않는다. 심사 증거는 심사 종료까지 유지하는 보관 정책을 L04에서 확정한다.

## 5. 관측과 판정

```json
{
  "schema_version": 1,
  "batch_id": "batch_example_02",
  "job_id": "job_example",
  "incident_epoch": 1,
  "contract_id": "shipping-quote-v1",
  "route": "active_alias_http",
  "started_at": "2026-09-07T03:03:00Z",
  "completed_at": "2026-09-07T03:03:02Z",
  "expected_version": "41",
  "sample_count": 5,
  "probe_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
  "verdict": "PASS",
  "evidence_id": "evidence_example"
}
```

실제 evidence는 각 요청의 입력 hash, HTTP 상태, body 판정, `executed_version`, 함수/Gateway 요청 ID, 시작·종료 시각을 포함한다. 위 summary만으로 회복을 판정하지 않는다.

판정 함수의 입력은 `job snapshot + action result + observation batches + now + current alias`이며 반환은 다음과 같다.

```json
{
  "health": "PASS",
  "recovery_confirmed": true,
  "reason_code": "POST_ACTION_PROBES_PASSED",
  "evidence_ids": ["evidence_example_01", "evidence_example_02"],
  "verified_version": "41",
  "verified_at": "2026-09-07T03:03:02Z"
}
```

`recovery_confirmed`는 job 종료와 별개다. 남은 관측 기간을 계속 수행한다. action 없이 회복하면 최신 실패 관측 이후의 두 묶음과 같은 버전의 현재 alias를 확인하고 `recovery_kind: observed_without_action`으로 기록한다. 에이전트가 복구했다고 표현하지 않는다. 실제 변경 후의 회복은 `post_action`으로 구분한다.

| 조건 | 판정 |
|---|---|
| 검사 1개라도 실제 기능 실패 | `FAIL`, 회복 false |
| 빈 표본·부분 표본·수집 오류 | `UNKNOWN`, 회복 false |
| 같은 batch/sample을 두 번 제출 | 중복 저장 무시, 두 묶음으로 세지 않음 |
| 오래된 표본·조치 전 시작한 요청 | 회복 근거에서 제외; 유효 표본 없으면 `STALE` 또는 `UNKNOWN` |
| 다른 epoch·contract·version·경로 | 회복 근거에서 제외하고 불일치 이유 기록 |
| 이전 버전 직접 호출만 통과 | 조사 근거만 충족, alias 경로 회복 false |
| 두 묶음 통과 + 현재 alias 불변 + evidence 저장 | 회복 true, `WATCHING`으로 복귀 |
| 회복 뒤 다시 실패 | epoch 증가, 이전 recovery 판정 무효, 추가 자동 rollback 금지 |

## 6. 변경과 승인

rollback 변경안에는 같은 계약·epoch·입력 집합의 **현재 버전 완전한 실패 묶음과 이전 버전 완전한 통과 묶음**이 필요하다. 둘 다 최신성 범위 안이어야 하며 관측 충돌·빈 표본이 있으면 허용하지 않는다. 이전 버전이 호환 가능 목록에 있고 정책·job 기한이 유효해야 한다. 이 조건은 모델 설명과 별개로 서버가 검사한다.

`Action.status`는 `PROPOSED → APPROVED → EXECUTING → APPLIED/NOT_APPLIED/UNKNOWN`이다. 사전 위임 정책도 policy 검사 후 서버가 `APPROVED`를 기록한다. 실행 전에는 `REJECTED`, `EXPIRED`, `SUPERSEDED`로 종료할 수 있다.

Action digest는 job/epoch/대상/목표 버전/expected alias revision/policy revision/근거/만료를 포함한 canonical JSON의 hash다. action 내용을 바꾸면 새 ID와 새 승인이 필요하다. 승인 수락은 늦어도 `min(action.expires_at, job.deadline_at)` 이전이어야 한다. 기본 승인 유효기간은 5분으로 제안한다.

실행 시 action의 policy revision은 job에 저장된 불변 정책 snapshot과 대조한다. 서비스 정책 수정은 다음 job부터 적용한다. 진행 중 job의 권한을 즉시 거두려면 stop 명령을 사용하며, stop 여부는 실행 직전에 현재 값을 검사한다.

| 경합·장애 | 처리 |
|---|---|
| 승인 중복 전송 | 같은 결정은 기존 결과 반환; 반대 결정은 409 |
| 승인 후 새 배포 | revision 불일치 → action 폐기, 이전 승인 승계 금지 |
| 취소가 실행 예약보다 먼저 | transaction 실패, AWS 변경 0회 |
| 실행 예약이 취소보다 먼저 | `STOPPING`, 진행 중 결과 조회 후 종료 |
| UpdateAlias timeout | action `UNKNOWN`, 조회만 수행; 동일 변경 재전송 금지 |
| 호출 전 crash인지 호출 후 crash인지 모름 | action 예약을 소비된 것으로 유지; 조회·인계, 한도 복구 금지 |
| 조회에서 다른 최신 버전 발견 | `SUPERSEDED`, 목표 버전으로 다시 덮지 않음 |
| 변경 기록 뒤 재검사 실패 | `UNRESOLVED`/`UNVERIFIED` 인계; APPLIED는 보존 |

API 응답만으로 자신의 변경이 적용됐다고 단정하지 않는다. `UpdateAlias` 성공 응답·AWS request ID·재조회 revision이 없고 목표 버전만 관측되면 “목표 버전 관측, 실행 귀속 불명”으로 기록한다. 건강 회복과 자신의 조치 성공을 분리해 보고한다.

## 7. 업무 API

Cognito access token의 서명·issuer·audience/client 설정과 scope를 API 계층에서 검증한다. 사용자 소유권은 endpoint마다 검사하며 조회할 수 없는 다른 사용자의 job은 `404`다. demo와 실제 업무 명령은 다른 권한 scope를 사용한다.

| Method / Path | 목적·입력 | 결과 |
|---|---|---|
| `GET /v1/services` | 접근 가능한 등록 서비스 | service ID, 표시명, 정책, 연결 상태 |
| `PATCH /v1/services/{id}/policy` | mode, 관측 기간, expected_policy_revision | 새 정책 revision; 진행 job은 기존 snapshot 유지, 긴급 중단은 별도 stop |
| `GET /v1/jobs?cursor=...` | 소유 job 목록, limit 최대 50 | card 목록, 불투명 cursor |
| `GET /v1/jobs/{id}` | job 상세 | phase, health, outcome, next_step, freshness, version, 허용 UI action |
| `GET /v1/jobs/{id}/events?after=...` | 저장된 timeline | sequence 기반 증분 event |
| `GET /v1/jobs/{id}/evidence/{evidence_id}` | 등록 evidence 조회 | redacted 구조화 근거; 임의 S3 key 받지 않음 |
| `POST /v1/jobs/{id}/approvals` | action_id, approve/reject, expected_state_version | 202 + operation ID, 실행 성공을 의미하지 않음 |
| `POST /v1/jobs/{id}/stop` | expected_state_version | 202 STOPPING 또는 200 STOPPED |
| `POST /v1/demo/runs` | A/B/C, default/demo profile | 202 run/job ID 또는 409 DEMO_BUSY |

공개 `start arbitrary deployment`나 `execute arbitrary action` API는 만들지 않는다. demo controller가 실제 배포를 수행한 뒤 배포 이벤트를 발행한다. policy 변경은 등록된 범위 내에서만 가능하며 허용 ARN·임의 URL을 body로 추가할 수 없다.

공통 오류 형식은 `{"error":{"code":"STALE_STATE","message":"...","retryable":false,"request_id":"..."}}`다. 인증 401, 권한 403, 없는 자원 404, 경합 409, 입력 422, quota 429, 일시 의존성 장애 503을 구분한다. `202`를 받은 UI는 job을 다시 읽으며 낙관적으로 “복구 완료”를 표시하지 않는다.

## 8. Strands 도구 계약

| 도구 | 모델이 제공할 입력 | 서버가 보장할 조건 |
|---|---|---|
| `inspect_release` | 없음 (job context 사용) | 등록된 서비스의 현재 alias·고정 이전 버전·변경 설명 |
| `read_evidence` | evidence kind, 제한된 시간 범위 | job 범위, 최대 50개 요약, source ID, truncation 표시 |
| `run_registered_probe` | current/previous/dependency | 등록 검사만 실행; 요청 수와 시간 예산 차감 |
| `prepare_action` | rollback, evidence IDs, rationale | 정책·대상·revision·근거 검증 후 고정 action ID 반환 |
| `execute_approved_action` | action_id | interrupt/resume와 서버 승인 검증; 별도 Executor 호출 |
| `request_handoff` | reason_code, evidence IDs, 필요한 결정 | 실제 상태와 근거를 검증한 뒤 인계 기록; 정상 판정 권한 없음 |

모든 결과는 `ok`, `data`, `evidence_ids`, `error_code`, `retryable`을 제공한다. 문자열 설명만 반환해 실패와 성공을 섞지 않는다. prompt와 로그에는 모델이 볼 수 있는 도구 명세를 저장해 조사 경로를 재현한다.

## 9. 필수 테스트와 증거

- 순수 domain: 금액·enum·기한 경계, phase/health/outcome 조합, terminal 재개 금지.
- 판정: 5개 고유 검사 × 2묶음, stale·pre-action·wrong version·다른 epoch·부분 표본·반복 표본의 거부.
- application: event 중복, 저장 후 dispatch 실패, 오래된 lease, 승인 재전송, 중단과 실행 예약 경합.
- AWS adapter stub: FunctionError/ExecutedVersion, UpdateAlias 412/timeout, 쓰기 재시도 없음, 조회로 결과 조정.
- Strands adapter: 새 Agent 인스턴스에서 interrupt 복원, 부작용 없이 중단, 승인 한 번으로 실행 예약 한 번.
- API: 다른 사용자 job 접근, stale version, idempotency conflict, quota 동시 예약, DEMO_BUSY.
- live: A/B/C와 동시 배포, 브라우저 종료 후 재접속, 30분 기본 관측, 실제 AWS version·요청 ID·비용 기록.

이 목록은 구현해야 할 테스트 계약이다. 현재 실행한 테스트 수나 통과 실적이 아니다.
