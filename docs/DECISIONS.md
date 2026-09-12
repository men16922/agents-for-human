# Decisions

## 2026-09-12 — 보고서에서 멈추는 실행 전 영향 측정

- Decision: 새 기본 제품을 동결 계획의 영향 측정과 실행 여부 판단 근거로 둔다. [계약](plans/2026-09-12-preflight-impact.md).
- Reason: 사용자가 실거래 전에 영향을 보여주고 수행 근거를 얻는 흐름을 요청했다. 초기 제안/실행 증거/최종 결정의 권한을 나눠야 한다.
- Impact: 별도 preview IAM에는 commerce invoke/write를 주지 않는다. 모델은 제안·가상 실행만 수행하며 finalizer가 보고서를 만든다. 실제 Amazon 연결 없이 만료·원본 hash/선택 계획에 결합한 brief를 내보낸다. 기존 B0–B3/Medusa 증거는 역사·회귀 경로로 보존한다.


## 2026-09-12 — 공개 데모를 AWS 서버리스로 전환

- Decision: 사용자 배포 승인에 따라 DynamoDB/Lambda commerce, AgentCore Strands, Step Functions seller/finalizer, S3/CloudFront UI를 채택했다. Reason: 심사 대기 동안 상시 Medusa/Postgres/Redis 서버를 운영하지 않는다. Impact: 과거 로컬 Medusa 증거와 새 AWS 기능 검증은 별도 자료로 유지한다.
- Decision: 모델 실행은 전역 예약·동시 실행 1개·유한 횟수로 제한하고, 종료 시 commerce write fence → Runtime stop → 독립 audit 순서를 적용한다. Reason: 늦은 쓰기와 불확실 usage를 성공/무료로 해석하지 않기 위해서다. Impact: 기존 budget을 배포 때 재설정하지 않으며 저장/요청 과금은 별도로 남는다. [상세](test/serverless-deployment.md).

## 2026-09-07 — F03 관측 버전과 전달 커서 분리

- Decision: 고객 snapshot 관측을 별도 journal에 저장하고 전달 시점에 run별 커서를 부여한다. 소비자는 관측 버전으로 전체 상태를 교체한다.
- Reason: 늦은 알림은 새로운 전달 순서로 도착할 수 있다. 관측 버전을 재접속 커서로 사용하면 지연 이벤트를 건너뛰거나 오래된 snapshot으로 상태를 되돌릴 수 있다.
- Impact: 알림은 원장 mutation을 지시하지 않는다. 보존 기간 초과는 최신 snapshot 복구이며, 관측 시각은 외부 납품 발생 시각과 다르다. 현재 오프라인/ASGI만 검증했고 실제 Medusa/SSE는 실행 승인 응답 대기다. `docs/test/medusa-notifications.md` 참고.

## 2026-09-07 — CW05 자체 운영 경계

- Decision: 자체 운영 서버는 18001 loopback 별도 프로세스, run별 buyer/observer/control 자격으로 제한한다. 구매 도구는 HTTP client만 보유하며 원장/시계/납품 관리자 메서드를 받지 않는다.
- Decision: 독립 worker가 단조 시계와 영속 재시작 anchor로 진행한다. HTTP 대기는 sleep+GET이며 시계를 직접 전진시키지 않는다.
- Impact: 자체 엔진을 HTTP로 분리한 성과는 E2가 아니다. 다음 Medusa adapter가 별도 고객/외부 ID/예산/판매자 의미를 검증해야 한다.

## 2026-09-07 — 모델 사용량과 fork 준비

- Decision: 호출 전 비용 예약과 응답 usage를 별도 SQLite에 기록한다. 누락/오류/프로세스 중단은 미확정 비용으로 보존하고 후속 호출을 막는다. 단가는 모델/리전 확인 후 명시하며 청구 검증으로 표현하지 않는다.
- Decision: 모델은 명시적 profile·region·ID로만 생성하고 SDK/provider 재시도를 끈다. 오프라인 preflight는 client를 만들지 않는다.
- Decision: fork는 선택한 run의 두 DB를 함께 잠가 확보하고 별도 디렉터리에 기록한다. 이력은 inherited snapshot으로 표시하며 이벤트/receipt ID를 재발급한다.
- Decision: 정책 제안은 data schema·content version·반례/재실험 hash로 남긴다. scripted 검토의 성공을 모델 Peer Review 효과나 자동 승격으로 표현하지 않는다.

## 2026-09-07 — CW01·CW02 저장 경계와 독립 판정

- Decision: 상점과 지급은 별도 SQLite 파일, 각각 `BEGIN IMMEDIATE` + outbox를 사용한다. 공동 DB transaction으로 분산 경계를 숨기지 않는다. 주문별 지급 intent는 하나로 제한한다.
- Decision: 독립 검증기는 서버 메서드를 호출하지 않고 외부 fixture와 raw 행·이벤트를 재계산한다. JSON에 저장된 성공 판정도 신뢰하지 않는다.
- Impact: 가속 연습은 명시적 tick 진행이며 운영 worker·HTTP 장애 주입은 후속 단계다. Strands 스크립트 모델 검사와 실제 LLM 결과·비용을 구별한다.

## 2026-09-07 — CW00 계약을 기준으로 Medusa 후보 유지

- Decision: 고정 Medusa core + manual provider를 E2 백엔드 후보로 유지한다. 실제 API로 합계 310·주문·지급·납품·재고 검증이 가능했다. 실자금/정책 전이는 미검증이다.
- Impact: 상태는 주문·지급·납품을 각각 매핑한다. delivered에도 order.pending이므로 order 상태 단독 성공 판정을 금지한다.
- Impact: Store 단건 조회의 고객 소유권 공백은 CW05 gateway에서 막는다. 구매자에게 관리자 자격이나 다른 run ID를 전달하지 않는다. 임의 멱등 키/예산/견적 버전은 Medusa 내장 계약으로 가정하지 않는다.

## 2026-09-06 — 초안 확정과 로컬 개발 기반

- 최신 HTML·구현 계획·전이 설계를 Rehearsal 초안으로 통일했다. 상세 Aftercare HTML/Markdown은 `archive/aftercare/`에 보관하고 생성기도 그 폴더에만 쓰도록 제한했다.
- 사용자 목표에 따라 제품 구현 전 로컬 준비를 수행한다. 고정 Python/Node, lock 의존성, health API·React 개발 셸·Medusa 기동을 포함하며 주문·모델·AWS·전이는 이후 CW 작업이다.
- 하네스 project_name도 Rehearsal로 갱신했다. `make check`는 설치된 개발 기반까지 검사하며 누락을 skip하지 않는다. 설치·컨테이너 기동은 별도 명령이다.
- 자동 seed·초기 커밋·remote는 만들지 않는다. runtime 준비가 야간 실행 승격을 뜻하지 않는다.
- npm 전이 의존성의 보안 수정은 같은 major의 lodash/ajv/qs/BullMQ overrides로 고정하고 기동·검사를 다시 수행한다. 강제 Medusa 다운그레이드는 하지 않는다.

## 2026-09-06 — 거래 리허설 POC로 전환

- 현재 authority는 커스텀 월드 POC 계획과 현실 전이 설계다. 아래 Aftercare 결정은 역사적 기록이다. 전환 이전 HTML은 보존하되 최신 제안으로 취급하지 않는다.
- 사용자는 실제 사업 출시보다 해커톤 실증을 우선한다. 실자금 없는 가상 거래와 Peer Review를 기본 범위로 둔다.
- OpenMMO는 조사 후보이며 권장 구현은 독립적인 작은 2D 세계다. 소스 재사용·실행·성능·제출 적합성을 확정하지 않았다.
- 자체 세계 성공만으로 현실 적용을 주장하지 않는다. CW00으로 독립 상거래 백엔드 계약을 먼저 확인하고 E2 전이를 설득 목표로 둔다.
- AgentCore Payments와 A2A는 필수가 아니다. Strands가 실험·도구 실행을 실제 담당하고, 자금·원장 규칙은 코드가 강제한다.
- 사용자 요구에 따라 실시간 운영 상태 반영을 필수로 둔다. LLM 호출과 세계 시계를 분리하고, 연습 snapshot 이후 달라진 견적·재고는 집행 전에 재검증한다.
- 기존 자동 seed와 제품 작업은 보류하고 새 CW 작업을 자동 승격하지 않는다.

## 2026-09-06

- 최신 제품 기획은 `agents-for-human-propsal.html`이다. 요청한 파일명을 유지한다.
- `archive/aftercare/proposal.md` → `archive/render_proposal.py` → `archive/aftercare/proposal.html`은 이전 상세 기획의 생성 경로다. 최신 독립 HTML을 덮는 용도로 사용하지 않는다.
- 하네스 동작과 engineering bible은 플러그인이 원본이며 저장소에는 설정·문서만 둔다.
- 현재 gate는 Python 표준 라이브러리로 동작하는 문서·설정 검사다. 제품 코드 도입 시 실제 런타임 동작 검증을 추가한다.
- 기본 엔진은 템플릿의 Claude를 유지하고 actor·critic 모델 이름은 비워 설치된 CLI의 기본값을 사용한다. 병렬 lane은 구성하지 않는다.
- 자동 작업의 범위는 오프라인 초기 seed 2개다. 실제 야간 실행과 로컬 커밋은 이번 설치에 포함하지 않는다.
- AWS·모델 호출·배포·게시·사용자 평가는 별도 실행 단계다. 로컬 검사 결과를 해당 단계의 완료로 보고하지 않는다.
- 설치 점검에서 helper는 Claude 캐시 1.4.0, Makefile은 Codex 캐시 1.5.0을 선택했다. 저장소의 `harness_root`를 요청한 1.5.0 설치 경로로 고정해 일치시켰다. 다른 환경에서는 경로를 재설정한다.

## 2026-09-06 — 제품 설계 v1

- Decision: Python domain/application + Strands adapter, React/TypeScript 웹, CDK TypeScript를 기본안으로 둔다. Reason: 결정론적 정책을 SDK에서 분리하면서 제안서의 AWS 구성을 구현한다. Impact: SDK/model/region 조합은 L01에서 확인·lock한다.
- Decision: phase·health·outcome을 분리한다. Reason: 작업 종료·조치 실행·회복 관측은 서로 다른 사실이다. Impact: UI와 평가기가 같은 상태 계약을 사용한다.
- Decision: 승인·실행 예약은 DB 조건부 변경, 실제 alias는 RevisionId와 재조회로 보호한다. Reason: DB와 AWS 변경은 하나의 transaction이 아니다. Impact: timeout을 성공이나 무조건 재시도로 처리하지 않는다.
- Decision: 기본 정책은 승인 필요, 명시적으로 설정한 demo만 사전 위임을 사용한다. Reason: 최초 사용자가 변경 범위를 이해해야 한다. Impact: 승인 snapshot과 정책 revision 검증 필요.
- Decision: 공유 demo 서비스에 동시 실행 1개를 허용한다. Reason: 짧은 일정에 alias·장애 주입의 사용자 간 간섭을 줄인다. Impact: 다른 사용자는 DEMO_BUSY 안내를 받고 재시도한다.
- Decision: P01부터 제품 코어를 구현하고 첫 이틀에 실제 사례 A를 연결한다. Reason: 하네스 보강만으로 제출 가치가 생기지 않는다. Impact: H01/H02는 유지하되 제품 선행 조건으로 두지 않는다.
