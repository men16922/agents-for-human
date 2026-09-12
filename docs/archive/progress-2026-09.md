# Progress log archive - 2026-09

## 2026-09-07 — CW01·CW02 구현과 CW03 SDK 준비

- Status: 분리 원장·가상 시계·정상 구매와 독립 검증/F01·F02·F06 완료. CW03 실제 모델·비용 기록은 열려 있다.
- Final gate: `make check` PASS(Python 42·mypy 13소스·ruff·웹 빌드), 증거/lock hash·문서 링크·ignore·5개 포트 반환 확인. 브라우저는 재실행하지 않았다.
- Changed: `src/rehearsal/world`, `evaluation`, `agents/executor.py`, fixture·동작 검사·실행 명령, `docs/test/world-foundation.md`.
- Verified: 정상 310, 가격 변경 후 B 380, 응답 유실 후 동일 지급 조회 310, 불가능 재고 0 집행/기한 실패. `evidence/cw02`에 raw 행·판정 보존 및 재검증.
- Verified: 실제 동시 budget/stock 경합, 중단 후 outbox 복구, 중복·역순 이벤트, run 격리·견적 만료, 원장/증거 변조와 일관된 오계산 반례.
- Verified: Strands SDK + 스크립트 모델 7회 응답/6회 도구 실행, 호출 상한·도구 격리. 실제 LLM 호출·비용으로 세지 않는다.
- Verified: 로컬 Medusa·전용 컨테이너 정상 종료, 다른 4개 실행 컨테이너 유지. 초기 커밋·푸시 없음.
- Blockers: CW03의 AWS profile/리전/모델 ID/비용 상한 미설정. 사용자에게 요청했으며 실제 모델 호출 없음.
- Next: 설정 응답 확인 후 CW03 live adapter·usage/cost ledger·정상 목표 최소 호출. CW04~09와 실시간 UI·전이·평가는 미완료.

## 2026-09-07 — CW00 실제 Medusa 거래 계약

- Status: 정상 주문·지급·납품·권한 spike 완료. 자체 월드·모델·정책 전이는 아직 미구현.
- Changed: `make commerce-contract`, 고정 loopback HTTP 검사, 토큰 제거 실제 응답과 `docs/test/medusa-contract.md`.
- Verified: 초기 52개 HTTP 검사 후 재고 거절·주문 목록 격리·capture 반복 검사를 보강하고 재실행 PASS. 최종 run `cw00-99192f3a1b7d`.
- Verified: 수작업 합계 310, 최종 재고 7/4·예약 0, 5단계 지급/배송 상태, 반복 cart complete 같은 주문·반복 capture 단일 기록.
- Findings: 주문은 delivered에도 pending. Store 단건 조회는 타 고객·비로그인 200, 목록은 고객별 격리.
- Decision: Medusa E2 후보 유지. CW05에 구매자 소유권/run gateway 필수. 임의 멱등 키·응답 유실·실자금 성과는 미검증.
- Next: CW01 분리된 상점·지급 SQLite와 가상 시계·정상 구매·예산/멱등 경계 검사. 커밋·푸시·클라우드 호출 없음.

## 2026-09-06 — 최종 초안과 로컬 개발 준비

- Status: Rehearsal 초안 v0.3 및 개발 기반 준비. 거래·모델·전이 구현은 이후 CW00부터.
- Changed: HTML/계획의 용어·일정 통일, 심사 기준·4분 45초 데모, 개발 안내·검증 기록 작성. 상세 Aftercare 기획과 생성기 경로는 archive로 정리.
- Changed: 저장소 전용 Python/Node, uv/npm lock, health API·React 셸, Medusa·PostgreSQL/Redis, 실행·종료·doctor·브라우저 검사 준비. 하네스 문서와 식별자도 현 방향으로 갱신.
- Verified: `make setup`과 재설치 PASS, 두 lock 해시 유지. 별도 새 Python 환경 import PASS. `make smoke-local` PASS(Python 6, 타입·lint·웹 빌드·하네스), 브라우저 3 PASS.
- Verified: Medusa build·migration·health, dev/commerce 기동·Ctrl+C 종료·재기동 두 차례, loopback과 포트 반환, 다른 컨테이너 보존. npm 전체·운영 audit 0건. 비밀값 미추적 확인.
- Fixed: 반복 SIGINT가 자식 정리를 끊는 문제를 listener/traceback으로 진단·수정했고 회귀 검사 추가. TCP 종료 상태와 실제 포트 점유를 구분했다.
- Verified: 최종 제안서 데스크톱·모바일 캡처 시각 검토, PDF 인쇄 렌더링. 상세 범위는 `docs/test/development-readiness.md`.
- Checkpoint: 사용자 요청으로 현행 기록과 작업 트리를 재대조했다. `make check-docs` PASS, 컨텍스트 문서 분량 준수. `rehearsal-dev` 실행 컨테이너와 개발 포트 listener 모두 0. 기존 항목을 보완했으며 전체 런타임 검사는 재실행하지 않았다.
- Blockers: 로컬 개발 착수의 차단 요소 없음. 실제 주문 계약·모델 권한·전이·성능·Linux·원격 CI는 미검증.
- Next: 구현 요청 시 CW00. 초기 커밋·remote·자동 seed·야간 실행·AWS·실자금·배포·게시 없음.

## 2026-09-06 — Rehearsal 시각 HTML 제안서

- Status: 화면·이미지 포함 기획서 완료. 제품 엔진과 외부 전이는 미구현.
- Changed: `agents-for-human-propsal.html`을 새 방향으로 작성. 이전본은 archive에 보관. AI 생성 이미지 2종과 프롬프트를 `assets/proposal/`에 저장.
- Changed: 재고 변경 → 재계획 → 지급 응답 유실 → 기록 확인의 네 장면, 자동 전환, 모바일 배치, 인쇄 CSS 추가. 합성값·설계 목표·미검증 범위를 명시했다.
- Verified: `make check` PASS. 기존 cached Chromium을 별도 headless 프로세스로 실행해 데스크톱·390px·320px 가로 넘침 없음, 이미지 2종 로드, 네 장면 상태, 재생 초기화·시간 전환·정지, JS 오류 0 확인.
- Verified: 생성 이미지 2종과 데스크톱·모바일 화면 캡처 시각 검토. 인쇄 PDF 렌더링 성공. 기본 Playwright 브라우저 버전 부재는 기존 headless 바이너리 명시로 해결했으며 설치·전역 설정 변경 없음.
- Blockers: 기획서 차단 요소 없음. 제품 실시간 이벤트·모델 호출·외부 백엔드·성과는 검증하지 않았다.
- Next: 구현 요청 시 CW00. README/AGENTS/brief/status/plan의 현재 제안서 진입점을 갱신. 커밋·푸시·배포·야간 실행 없음.

## 2026-09-06 — 커스텀 거래 세계 조사·계획·실시간 요구

- Status: 조사·계획 완료. 제품 구현과 외부 전이 성과는 없음.
- Changed: OpenMMO 조사, 커스텀 월드 POC 계획, 구현 수준·현실 전이·실시간 이벤트 설계 작성.
- Changed: brief/status/plan/decisions/README/AGENTS를 새 방향으로 맞췄다. 이전 제안서·설계는 보존하고 기존 자동 seed는 보류했다.
- Verified: OpenMMO commit `603807666d7b6f52ede8acb38580b6d35c1c976b` 문서·선택 소스 20개를 읽었다. 라이선스·거래·agent-client·Compose·CI 설정 확인. 설치·빌드·기동 미실행.
- Verified: 공식 대회 규칙, Medusa core·payment flow, Stripe 테스트 환경, Strands·평가 연구 문서를 설계 근거로 연결했다.
- Verified: `make check` PASS. Markdown 12개·로컬 링크 14개·코드 fence 검사 오류 0. 문서·설정 검증이며 제품 성능 검증이 아니다.
- Blockers: 문서 작업의 차단 요소 없음. 외부 백엔드 실제 작동, 비용·실시간 지연·Peer Review 효과·사용자 효용은 미검증.
- Next: 구현 요청 시 CW00 독립 상거래 백엔드 계약 spike. 실자금·클라우드·모델·공개 서버 행동·커밋·푸시·야간 실행 없음.

## 2026-09-06 — 구현 계획·설계 v1

- Status: 계획·설계 완료, 제품 구현 미착수.
- Changed: `docs/design/` 2개와 `docs/plans/2026-09-06-aftercare-implementation-plan.md`; 상태·판정·승인·API·검사·작업 의존성 구체화.
- Changed: brief/status/plan/decisions/README를 P01 시작점에 맞췄다. 기존 자동 seed 2개와 제안서는 유지했다.
- Verified: Strands interrupt/session, AgentCore 세션, Lambda Invoke/UpdateAlias·비동기 전달, Scheduler 주기, DynamoDB transaction 공식 문서를 읽고 설계에 반영했다.
- Verified: `make check` PASS. Markdown 5개 문서의 로컬 링크 19개, 코드 fence, P01–P12/L01–L06 존재, 자동 seed H01/H02 유지 확인. Mermaid는 코드 검토만 수행했고 시각 렌더링은 미검증.
- Blockers: 문서 작성에 남은 차단 요소 없음. 모델·리전·패키지 lock과 실제 비용은 L01/L02에서 확인할 항목이다.
- Next: 구현 요청 시 상세 계획 P01의 Python 패키지·독립 배송비 fixture·fake Clock·테스트부터 시작한다. 커밋·야간 실행·AWS 호출은 수행하지 않았다.

## 2026-09-06 — Harness initialization

- 기존 기획 3개 HTML과 상세 Markdown을 보존하고 로컬 Git 저장소를 초기화했다.
- 플러그인 installer로 저장소 상태만 설치했다. runner·공통 engineering bible은 복사하지 않았다.
- 오프라인 gate, Makefile 연결, 엔진별 권한 설정과 작업 문서를 작성했다.
- 초기 오프라인 백로그 2개를 등록했다. 제품 구현과 모델 기반 loop는 실행하지 않았다.
- 검증: `make check` PASS; `make smoke-local` PASS (`harness-init.sh --check`와 `make overnight-where` 포함).
- 플러그인 선택 불일치(Claude cache 1.4.0 / Codex cache 1.5.0)를 발견해 per-repo `harness_root`를 요청한 1.5.0 경로로 고정했다. 이후 두 확인 경로가 동일하다.
- 임시 fixture 검증에서 macOS `/var` → `/private/var` 심볼릭 링크 때문에 정상 anchor를 거부하는 문제를 발견했다. 입력 경로 정규화 후 정상 fixture 통과·깨진 anchor와 잘못된 JSON의 실패를 확인했다. 원본 제안서는 변경하지 않았다.
- `make -n overnight-once`는 runner 명령 연결만 확인했다. 모델·actor·critic·자동 커밋은 실행하지 않았으며 아직 초기 HEAD와 remote가 없다.

## 2026-09-08 — F05 비신뢰 문구·도구 경계 오프라인 검증

- Changed: 문서보다 앞선 기존 F05 봉투·프롬프트·입력 경계·시나리오·SDK 검사 4개를 보존하고 검토했다. 입력 타입 검사 수정, 연습/HTTP 잘못된 인자 18개·ASGI 1개·Medusa replay 4개 회귀를 추가했다.
- Diagnosed: 최초 `make check`는 mypy의 `object has no attribute values`로 실패. 명시적 사전 타입 확인 후 동일 mypy 34개 소스 PASS.
- Verified: 최종 `make check` PASS(Python 178·mypy 34소스·ruff·lock·웹 빌드). F05 27개는 공격 문구 전달, 권한 밖 호출 거절, canonical 금액, fork/재시작, 구조화 가격 변경 거절, 허위 완료와 원장 판정 분리를 검사한다.
- Limits: SDK 모델은 의도적으로 공격 요청을 실행하는 fixture이며 모델 판단력 증거가 아니다. HTTP MockTransport·ASGI TestClient·보존 Medusa 응답 사용; 실제 Medusa/F05 모델·F03 실제 SSE는 미검증. 기존 TestClient 경고 2개 유지.
- Scope: AWS·모델 API·설치·서비스 기동·커밋·푸시 없음. 기존 frozen B0 증거는 과거 실행으로 보존했다. 상세: [F05 기록](../test/untrusted-supplier.md).
- Next: 모델 설정 응답 시 CW03 우선. 응답 전 상세 계획의 실행 중 외부 재고 변경 1번 오프라인 계약/회귀. F03 실제 HTTP 검사는 기존 승인 응답 대기.

## 2026-09-07 — F03 영속 알림·SSE 오프라인 구현

- Changed: 관측 버전/전달 커서 분리, 영속 대기열·지연/중복/재전달, 고객 polling worker, 역할별 SSE/조회, 최신 snapshot 복구와 참조 소비자.
- Verified: `make check` PASS(Python 151·mypy 33소스·ruff·웹 빌드). F03 회귀 19개는 원자성·동시 전달·중복/역순·run 격리·ASGI 재접속/보존 기간 복구·진행 중 thread 종료 대기를 확인한다.
- Diagnosed: 관측 task 예외 시 client 정리가 건너뛰어지는 실패를 재현했다. ExitStack으로 자원 해제를 보장하고 예외 후 재기동·중복 observer 거절 회귀를 통과했다.
- Limits: 실제 `make commerce-notification-smoke`는 작성만 했으며 미실행. Medusa 기동 이후 추가 loopback health 조회를 자동 승인 검토가 무인 네트워크 접근 사유로 거절했다. 실행 승인 응답 대기다.
- Cleanup: 기동한 전용 Medusa/DB 종료·포트 18001/19000/55432/56379 반환·볼륨 보존 확인. 새 실제 주문·모델 호출·브라우저 검사·커밋·푸시 없음.
- Next: `docs/test/medusa-notifications.md`의 로컬 HTTP 실행 승인 후 실제 검증·증거 보존. 대기 중 F05 도구 계약/회귀, 모델 설정 응답 시 CW03 우선.

## 2026-09-07 — F03 구현 전 재개 지점 저장

- Status: 동결 B0 완료 기록을 유지하고 F03 구현 전 계획만 저장했다. 새 제품 코드·실행 증거는 추가하지 않았다.
- Changed: 상세 계획에 관측 journal → 권한별 SSE/복구 → 알림 장애 주입 → 실제 Medusa 대조 순서를 추가하고 brief의 첫 작업을 연결했다.
- Verified: 기존 brief/status/plan/log 대조와 `make check-docs` PASS(문서 참조·설정·경로·분량). 이전 `make check` 132개 통과 기록은 재실행 결과가 아니다.
- Blockers: 실제 모델 실행은 모델 ID·비용 설정 응답과 공식 단가 확인이 필요하다. F03 로컬 구현은 독립적으로 진행할 수 있다.
- Next: 상세 계획의 「CW05 F03 재개 순서」 1번. 커밋·푸시·서비스 기동 없음.

## 2026-09-07 — 동결 정책·B0 연습/Medusa 대조

- Changed: 정책/프롬프트/소스 hash 동결 manifest, 명시적 B0 고정 규칙 실행자, Strands 정책 주입과 CW03 `--policy`, 6개 연습/외부 대조 검사.
- Verified: `scripts/commerce/transfer_smoke.py` PASS. 같은 frozen ID로 갱신 전 가격 거절 0/미완료, 갱신 후 가격/응답 유실 380/완료, 부분 조달 360/완료를 두 환경에서 확인. `evidence/cw05-frozen-b0` 보존.
- Verified: `make check` PASS(Python 132·mypy 31소스·ruff·웹 빌드). 동결/프롬프트/usage·B0 회귀 10개. 브라우저·실제 모델은 미실행.
- Verified: 동결 2개·소스/하위 artifact hash·원장 6개 재판정·문서 링크 대조, 전용 서비스 종료/포트 반환/볼륨 보존. 실제 model preflight는 모델 ID·비용/단가 누락으로 exit 2.
- Limits: 알려진 B0 fixture이며 학습된 정책·LLM·Peer Review 효과나 미공개 조건 결과가 아니다. F03/F05·실행 중 재고 변경·실제 모델 실행은 남았다.
- Docs: 기존 로그 11개 항목의 원문을 보존해 최신 4개와 `docs/archive/progress-2026-09.md`로 분리했다. 새 기록 전 119→45줄, archive 78줄.
- Next: `docs/test/frozen-policy-transfer.md` → F03 납품 알림·F05 비신뢰 문구·실행 중 재고 변경. 모델 설정 응답 시 CW03 우선. 커밋·푸시 없음.

## 2026-09-07 — CW05 Medusa HTTP·독립 판매자 체크포인트

- Changed: 구매 HTTP 경로·고객/역할 토큰, 별도 판매자 프로세스·영속 작업/납품 기한, A/B/C 실제 카탈로그와 기동/종료 helper.
- Verified: `make commerce-operating-smoke` PASS. 견적 310/380/495, A 실제 가격 변경 거절→B 380, HTTP UNKNOWN, 구매 서버 정지 중 납품·판매자/구매 서버 재시작, 독립 COMPLETE.
- Verified: `make check` PASS(Python 122·mypy 29소스·ruff·웹 빌드). 새 판매자 회귀 8개는 응답 유실·불확실 재전송 거절·기한/중복·고객/금액/창고 경계를 검사한다.
- Evidence: `evidence/cw05-medusa-operating`에 외부 주문·원장·판매자 4개 작업·기한·PID·소스 hash 보존/대조 완료. 전용 서비스 종료·포트 반환·볼륨 보존 확인. 상세는 `docs/test/medusa-operating.md`.
- Limits: 실제 모델·Peer Review·동결 정책 전이·F03/F04/F05 전체·SSE는 미완료. 불확실 외부 mutation의 명시적 재개/취소는 남았다.
- Next: 사용자 checkpoint 요청으로 기록. 모델 설정 응답 시 CW03 우선, 응답 전 동결 정책의 Medusa 실행과 F03/F04/F05·외부 재고 변경. 커밋·푸시 없음.

## 2026-09-07 — CW05 Medusa 고객·예산 어댑터

- Status: 실제 고객 API gateway와 독립 외부 증거 검사 완료. 별도 판매자 worker·HTTP 연결·정책 전이와 CW05 전체는 미완료.
- Changed: 영속 고객/run/외부 ID 매핑, cart 가격 재확인, 제출 전 예산 예약, 불확실 요청의 GET 대조, capture·실제 납품 수량 반영.
- Verified: `make commerce-adapter-smoke` 77개 HTTP 요청 PASS. 실제 가격 변경 거절·완료 응답 유실/재시작 후 같은 주문 복구·소유권·예산 거절·310 집행/수령. `evidence/cw05-medusa` 보존, 소스/lock/증거 hash 일치.
- Verified: 변조·중복·재시작·동시 예산 admission 회귀 검사 28개. `make check` PASS(Python 114·mypy 27소스·ruff·웹 빌드). 브라우저·실제 모델 미실행.
- Verified: fixture seed 분리 후 기존 `make commerce-contract` 57개 요청 PASS. 전용 서비스 종료·포트 반환·볼륨 보존 확인. 이번 판매자는 테스트 코드의 명시적 관리자 호출이며 독립 실행/지연 검증은 아니다.
- Finding: 관리자 주문 기본 필드에는 customer_id/currency_code가 없다. 독립 export에서 명시적으로 확장해야 하며 누락 시 UNKNOWN으로 남긴다.
- Limit: 제출 후 주문 미생성 상태는 예산 예약을 유지한다. 명시적 재개·취소·환급은 남았고 실제 모델·전이 성과 없음.
- Next: `docs/test/medusa-adapter.md` → 독립 판매자 worker·기존 구매 HTTP 경로 연결·B/C 공급처. 모델 설정 응답 시 CW03 우선. 커밋·푸시 없음.

## 2026-09-07 — CW05 자체 운영 HTTP 경계

- Status: 로컬 운영 서버·HTTP 도구·독립 worker 준비 완료. Medusa 전이 adapter와 CW05 전체는 미완료.
- Changed: 구매/observer/control run별 토큰, canonical 금액·교차 run 거절, 영속 시계/일회성 응답 지연, 별도 프로세스 helper와 SDK HTTP 도구.
- Verified: `make operating-smoke` PASS(401/403/404, stale 견적 409, HTTP UNKNOWN→SETTLED, B 380·수령, 재시작 상태 보존).
- Verified: `make operating-sdk-smoke` PASS(scripted 7회 응답/6도구로 실제 HTTP A 310·수령). `evidence/cw05-http`에 정지 후 독립 증거 저장.
- Diagnosed: 재시작 errno 48은 TIME_WAIT probe 오인. LISTEN/CLOSED + SO_REUSEADDR 비교로 원인 확인 후 회귀 검사·실제 재시작 PASS.
- Final gate: `make check` PASS(Python 86·mypy 24소스·ruff·웹 빌드). ASGI dependency deprecation 2개는 남았고 lock 변경 없음.
- Next: CW05 Medusa 고객 API·외부 ID/소유권·예산/판매자 adapter. 모델 설정 응답 시 CW03 실제 호출을 우선한다. 커밋·푸시·AWS 없음.

## 2026-09-07 — CW03 실행·비용 원장과 CW04 fork 준비

- Status: 실제 모델 설정 응답 전 로컬 준비를 확장했다. CW03 실제 실행·CW04 모델 Peer Review는 미완료.
- Final gate: `make check` PASS(Python 75·mypy 19소스·ruff·웹 빌드), 변경 문서 링크·정책/실험 artifact hash 확인. 브라우저·AWS는 실행하지 않았다.
- Changed: 명시적 model runner/preflight, usage SQLite·추정 비용 admission·실패/미확정 보존, 제한/timeout 후 독립 판정.
- Changed: 일관된 run fork·이벤트/receipt 재식별·실패 fork 재개 거절, 정책 content version/diff·반례 artifact 연결·같은 snapshot 재실험.
- Verified: SDK scripted 실행 7모델 fixture/6도구·usage와 가상 단가 계산, 실패 usage 보존·한도 취소·명시적 provider 인자 검사.
- Verified: `make policy-smoke` PASS. 기존 정책 stale 견적 거절/0 집행, 재조회 정책 B 380 수령, 원본 상태 유지. 공개 보존 경로 `evidence/cw03-offline`, `evidence/cw04-offline`.
- Blockers: 실제 preflight는 모델/비용 설정 누락으로 exit 2; AWS client·모델 호출 없음.
- Next: 모델 설정/공식 단가 후 CW03 실제 실행. 응답 전에는 CW05 로컬 HTTP·소유권·운영 worker 준비가 가능하다.

## 2026-09-08 — CW04 B3 초기 구매·검토·후보 구매 공통 회계

- Changed: 작업 트리의 B3 구매/검토 연결을 이어서 검증. 역할별 토큰·호출 상태·실패/예약·호출 전 거절 기록을 보강하고 전용 회귀 19개 추가. 초기/후보는 동일 snapshot·기존 구매 도구·별도 Agent를 사용한다.
- Verified: `make b3-smoke` PASS(`b3_c41a980a95994cc7894885a6169bf0ab`). 초기/검토/후보 6/2/14 fixture 호출·가상 비용 616 micro-USD, 초기 INCOMPLETE 0·후보 COMPLETE 380·부모/초기 정책 보존. 공통 한도·세 역할의 usage 누락/부분 누락/예외·실패 뒤 차단·attribution 변조를 검사했다.
- Gate: `make check` PASS(Python 304·mypy 41·ruff·lock·웹 빌드). `evidence/cw04-b3-offline/` 13개 artifact·소스 hash 10개·독립 export 재판정·역할 합계 대조. `b3-preflight`는 모델 ID/단가/한도 누락 exit 2.
- Limits: 알려진 반례의 결정론적 provider fixture다. 실제 모델·Peer Review 효과·새 조건·실제 청구는 미검증. 도구 상한은 구매별이며 비교군의 총 예산 일치는 남았다. 브라우저/Medusa·설치·AWS·커밋·푸시 없음.
- Next: 모델 설정 준비 후 CW03 정상 실제 호출, 상세 계획 CW04 4번 동일 snapshot 재실험·새 조건 평가. [상세 기록](../test/b3-shared-accounting.md).

## 2026-09-08 — CW05 두 구매자의 실제 재고 경합

- Changed: 실제 checkout 직전 barrier/요청 trace를 남기는 검사용 gateway와 `commerce-race-smoke` 추가. 제품 gateway 경로는 변경하지 않았다. 같은 run의 동시 key/예산 회귀 2개 추가.
- Verified: 실제 `cw00-608e1d67aec7` PASS. 두 run checkout HTTP 중첩 194ms·주문/납품 1개·최종 재고/예약 0. 승자 COMPLETE 310, 패자 HTTP 400→UNKNOWN/예약 310. 재조회/재시작 포함 checkout 총 2회·타 run 주문 거절·대체 지급 BUDGET_EXCEEDED.
- Gate: `make check` PASS(Python 285·mypy 39·ruff·lock·웹 빌드). browser gate 이번 미실행(직전 19개 통과). `evidence/cw05-race/`의 원장/trace 262건·소스 9개/증거 4개 hash·토큰 미포함·서비스 종료/포트/볼륨/기존 컨테이너 보존 확인.
- Limits: 단일 Medusa·한 경합 순서다. 패자 예약 해제/취소는 미구현이며 UNKNOWN을 성공이나 rollback으로 바꾸지 않았다. 실제 모델·분산 원자성·배포·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW04 3번 B3 구매 재실험·검토의 공통 사용량/비용 한도 연결. [상세 기록](../test/concurrent-stock-race.md).

## 2026-09-08 — CW06 두 브라우저의 독립 복구·상태 일치

- Changed: 별도 Chromium 프로세스 둘·한쪽 offline/다시 연결·짧은 커서/retention 초과 복구용 `commerce-convergence-smoke` 추가. 제품 경로는 변경하지 않았다.
- Verified: 실제 실행 `cw00-a8e25271ce9e` PASS. cursor 2 짧은 복구·cursor 3→12 snapshot 복구, 반대 브라우저는 중단 없이 재고/납품 관측. 두 화면 v12/tick 12의 수령/예산/주문/재고를 영속 관측 및 독립 COMPLETE 380과 대조.
- Gate: `make check` PASS(Python 283·mypy 39), `make check-browser` PASS(19개). 독립 소비자/run 오류 격리 회귀 1개 추가. `evidence/cw06-convergence/` artifact 15개/소스 16개 hash·토큰 미포함·화면·서비스 종료/포트 6개·볼륨/기존 컨테이너 보존 확인.
- Limits: 같은 호스트/Chromium·의도한 retention 8·수동 reconnect 단절이다. snapshot은 누락 구간의 현재 상태만 회복한다. 다른 기기·두 구매자 재고 경합·실제 모델·전체 지연 목표는 미검증. AWS/모델·배포·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW05 재고 변경 4번 두 구매자의 희소 재고 경합·예산/중복 경계. [상세 기록](../test/two-browser-recovery.md).

## 2026-09-08 — CW06 관측 지연 분포·제외 계측

- Changed: 영속 조회 시각/소요 시간·서버 프로세스별 분모, 브라우저 최대 2,000개 원시 표본·6구간 분위수/유형 필터/JSON 저장. 중복/역순/배치 반영/hidden/시계 차이/재접속/퇴출 사유 보존.
- Verified: 실제 `commerce-observer-smoke` PASS(`cw00-002ddeffbd43`). 수신 24건·반영 22건, 관측→반영 p95 966ms·조회 시작→반영 p95 1,028ms. 이전 버전/중복 납품 2건의 2,167ms 게시 지연도 보존. B 380·수령 9·독립 COMPLETE·서버 재접속.
- Gate: `make check` PASS(Python 283·mypy 39), `make check-browser` PASS(18개). 원시 표본 24건과 영속 journal 시각 대조·6구간 독립 Python 재계산·소스/증거 hash 9개·토큰 미포함·화면 확인. 서비스 종료/포트 6개 반환·볼륨/기존 컨테이너 보존.
- Limits: 단일 로컬 실행·2회 animation frame 근사·단계별 다른 분모다. 외부 발생 시각/전체 1초 목표/실제 모델 효과는 미검증. 모델/AWS·배포·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW06 7번 두 브라우저 상태 일치·개별 재접속/retention 복구. [상세 기록](../test/observation-latency.md), `evidence/cw06-latency/`.

## 2026-09-08 — CW06 공급자 재고·개별 주문 관측

- Changed: 고정 Store GET의 가용량/상품 단가와 로컬 주문 납품/지급 상태를 journal/SSE/UI에 연결. 최대 100품목/최근 50주문·총수·whitelist·미확정 수령 표시, 접수 중 결제 예약 보존.
- Verified: `commerce-observer-smoke` PASS(`cw00-e321e1e78fd9`): UI A 재고 10→0→주문 거절, B 재고 7/4·납품/정산·수령 9·독립 COMPLETE 380·서버 재접속. raw journal/화면/원장/hash는 `evidence/cw06-commerce-details/`.
- Gate: `make check` PASS(Python 274·mypy 39), `make check-browser` PASS(13개). 회귀 19개+UI 1개 추가. mypy용 Json 선언만 실행 후 추가했고 전후 hash 차이 대조. 토큰 미포함·원장 재판정·전용 서비스 종료/포트 6개·볼륨/기존 컨테이너 보존.
- Limits: 납품 조회 불일치 1회는 제한 GET 재조회로 회복. 여러 GET은 원자적 snapshot이 아니며 상품 단가는 확정 견적이 아니다. 실제 모델·지연 목표·동시 경합 미검증, AWS/모델·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW06 6번 조회/관측/게시/브라우저 지연 표본 계측. [상세 기록](../test/commerce-observation-details.md).

## 2026-09-08 — CW06 독립 증거 재검증·관측 비교 화면

- Changed: 서버 선택 manifest의 run/목표/예산/hash로 raw export 재검증. 브라우저에 판정/시점/해시만 전달, 과거 COMPLETE와 현재 상태 비교·재검증 실패 시 이전 성공 제거.
- Verified: `commerce-observer-smoke` PASS(`cw00-d6c09eac6808`): 실제 B 380·수령 9·예약 0 export→API 재판정 COMPLETE→브라우저 증거 tick 23·관측 일치. HTTP·화면·원장/hash는 `evidence/cw06-evidence-ui/`.
- Gate: `make check` PASS(Python 255·mypy 38), `make check-browser` PASS(12개). 변조/누락/run/목표/예산/해시 회귀 25개, UI 비교·실패 갱신 3개 추가. 토큰 미포함·독립 재판정·소스 hash·서비스 종료/포트 6개/볼륨/기존 컨테이너 유지 확인.
- Docs: 오래된 진행 항목 8개를 월별 보관본에 보존하고 이동 링크를 교정했다. 최신 상태/시작점 유지.
- Limits: 명시적 export 시점의 수동 Medusa 기록이며 실시간 최종성·실제 물품·모델 효과를 뜻하지 않는다. 모델/AWS·배포·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW06 5번 개별 주문·공급자 재고 읽기 전용 관측 계약. [상세 기록](../test/independent-evidence-ui.md).

## 2026-09-08 — CW06 관측실·실제 Medusa SSE 브라우저 검증

- Changed: observer 전용 loopback bridge·별도 0600 설정·React 지도/수령/예산·신선도, 중복/역순/reset·커서 재연결·검증 실패 중단. 구매/관리자 명령·브라우저 토큰 없음.
- Verified: `make commerce-observer-smoke` PASS(`cw00-3f3dac1b04a9`): A 재고 10→0→주문 거절, B 380·수령 9·예약 0·독립 COMPLETE, UI 중단/커서 19→20 복구. 최신 관측 반영 460/948ms는 단일 시점이며 종단 성능 주장 없음.
- Evidence: `evidence/cw06-observer/`에 raw 원장·HTTP·브라우저·화면·hash와 최초 인자 누락/납품 조회 실패도 보존. 후속 조회는 정상이며 당시 불일치 필드는 미확정. gateway 거절 유지, smoke의 GET만 제한 재조회.
- Gate: `make check` PASS(Python 230·mypy 37), `make check-browser` PASS(9개). 실제 서비스 정리 후 browser gate 재실행. credential 미포함·원장 재판정·포트 6개 반환·전용 볼륨/다른 컨테이너 보존.
- Limits: 독립 verdict의 UI 연결·실제 모델 재계획·지연 분포·전이 효과 미검증. 모델/AWS·배포·설치·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출 우선. 대기 중 상세 계획 CW06 4번 독립 verdict/artifact 증빙 화면 연결. [상세 기록](../test/observer-ui.md).

## 2026-09-08 — CW04 독립 검토·후보 재실험 오프라인 연결

- Changed: 도구 없는 새 Strands 검토자·JSON 후보 schema·1~2개 반례·최대 2라운드, artifact/fork/원장 재검증·revision·동일 snapshot 재실험. 원래 정책 유지, 자동 승격 없음.
- Diagnosed: SDK가 원본 usage 누락을 0으로 채워 기존 계측이 실제 0 사용으로 기록할 수 있었다. provider stream을 관측해 CW03/검토자 모두 누락을 USAGE_UNKNOWN으로 남기고 후속 호출을 차단했다.
- Verified: `make review-smoke` PASS. fixture 검토 2회·정책 diff·B 380 알려진 재실험 COMPLETE, 가상 비용 56 micro-USD. `evidence/cw04-review-offline/`에 소스/입력/응답/원장/fork/revision hash 보존·대조.
- Gate: `make check` PASS(Python 212·mypy 36소스·ruff·lock·웹 빌드). 검토 회귀 18개·원본 usage 누락 3개 추가. 기존 TestClient 경고 2개 유지.
- Limits: 실제 모델·검토 효과·B3 전체 모델 구매 비용·새 조건 평가·자동 승격은 미검증. `review-preflight`는 모델 ID·비용·단가/출처 누락으로 exit 2. AWS·모델·Medusa·브라우저 실행·설치·커밋·푸시 없음.
- Next: [독립 검토 기록](../test/independent-review.md). 모델 설정 응답 시 CW03 실제 호출 우선, 대기 중 상세 계획 CW06 관측 UI 1번 읽기 전용 연결부터 진행.

## 2026-09-08 — 실제 재고 변경·F03 SSE·F05 설명 전달

- Changed: `commerce-stock-smoke`·`commerce-supplier-smoke` 추가. 첫 line만 재고를 확인하던 gateway를 모든 line 재확인으로 수정하고 replay fixture도 Medusa의 단건 검증 범위로 교정했다.
- Diagnosed: 최초 실제 재고 실행은 두 번째 품목 부족을 놓쳐 SUBMITTED/예약 310이 남았다. 설치된 Medusa workflow의 단건 inventory 확인을 대조했고 교정 fixture에서 2개 회귀 실패→수정 후 통과. 실패 보고서 보존.
- Verified: 새 `commerce-stock-smoke` PASS. 실제 재고 감소 후 B 380 대체 구매·A/C 415 부분 조달, 원장 2개 COMPLETE·재시작·예약 0. `evidence/cw05-stock/`.
- Verified: `commerce-notification-smoke` PASS. 실제 납품·약 2.010초 지연/중복·역순·pending/커서 재시작·retention reset, 독립 COMPLETE 310. `evidence/cw05-notifications/`.
- Verified: `commerce-supplier-smoke` PASS. 실제 상품 설명·hash 전달, 권한 밖 HTTP 요청 거절, 구매 전 INCOMPLETE→canonical 310 구매 COMPLETE. `evidence/cw05-supplier/`.
- Gate: `make check` PASS(Python 191·mypy 34소스·ruff·lock·웹 빌드). 소스/증거 hash·credential 미포함, 전용 프로세스/DB 종료·포트 18001/19000/55432/56379 반환·볼륨 2개 보존·다른 Docker 컨테이너 유지 확인.
- Limits: 실제 모델·Peer Review 효과·학습된 정책 전이·동시 재고 경합·브라우저 UI는 미검증. 첫 실패의 예약은 보존했으며 자동 환급 없음. AWS·모델 API·설치·커밋·푸시 없음.
- Next: 모델 설정 응답 시 CW03 실제 호출 우선. 대기 중 CW04 독립 검토 실행 경로·후보 정책 검증·비용 집계의 오프라인 연결을 준비하고 이후 CW06 실시간 화면으로 진행.

## 2026-09-08 — 실행 중 재고 변경·지급 불확실 경계

- Changed: 실제 StoreAPI·MockTransport·보존 Medusa 구조를 사용하는 재고 변경 회귀 13개 추가. 외부 HTTP 오류 타입을 분리하고 제출 이후·지급 조회 HTTP 실패를 UNKNOWN으로 반환한다.
- Diagnosed: 최초 회귀 7개 중 3개 실패. 제출 후 400이 일반 거절로 노출되지만 원장에는 SUBMITTED·예약 310이 남았다. 수정 후 같은 7개 통과, 로컬 고객/금액 모순은 거절을 유지하도록 추가 검사했다.
- Verified: `make check` PASS(Python 191·mypy 34소스·ruff·lock·웹 빌드). 제출 전 예약 0, 제출 후 예약 310 유지, 재시작/동일 키 GET 대조, 대체 구매 예산 거절, 뒤늦은 기존 주문 단일 정산 확인. 기존 TestClient 경고 2개 유지.
- Limits: HTTP 400 재고 응답은 CW00 보존 응답이며 주입 시점은 합성이다. 실제 Medusa 재고 경합·부분 대체 조달·모델 재계획은 미검증. 주문 없는 SUBMITTED의 예약 해제/재개는 여전히 미구현.
- Scope: AWS·모델 API·설치·서비스 기동·커밋·푸시 없음. 상세: [재고 변경 기록](../test/medusa-stock-changes.md).
- Next: 상세 계획의 실행 중 외부 재고 변경 2번 로컬 검사 스크립트 준비. 모델 설정 응답 시 CW03 우선, F03 실제 HTTP는 기존 승인 응답 대기.

## 2026-09-09 — 정적 초기 조건 적용·독립 원시 관측 대조

- Changed: 명시적 정적 조건 schema·새 fixture 가격/재고/배송비/납기 적용·Store/Admin GET/빈 원장 검증·5tick 신선도·불변 증거 고정·세션 관측 갱신·배치 독립 정산 연결.
- Verified: `make external-conditions-smoke` PASS(`conditions_33b0c0af7c224e86b8277ffe1e20e8d1`). 새 Medusa 5건 초기 조건 일치·네 방식 COMPLETE 430·필수 품목 부족 B0 INCOMPLETE 0·전체 8칸 중 3 NOT_RUN. 변조/오래된 증거는 실행 칸 소비 전 거절했고 실제 세션 갱신 후 실행했다.
- Gate/Evidence: `make check` PASS(Python 498·mypy 49), 추가 28개 회귀. 122개 artifact·5초기/5거래/4학습 원장·복사 명부/소스 49개 hash·비밀값/포트/컨테이너/볼륨 대조. SDK 87호출/1,740토큰/109도구/가상 2,436 micro-USD·예약 0. [상세](../test/static-initial-conditions.md).
- Next: CW05 모델 HTTP 3번의 실행 중 이벤트 조건 적용·발생 증거 연결. 초기 관측 일치는 원자적 격리·이벤트·실제 모델 효과 증거가 아니다. 브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 네 비교 방식의 외부 실행·공통 원장

- Changed: 방식별 BudgetCarryover·B0/B1 무학습 준비·B2 단일 Agent 원장 연결·B0 고정 실행/도구 admission·방식/모델 모드 교체 거절. 기존 B3 호환 유지.
- Verified: `make external-arms-smoke` PASS(`external-arms_2b89e91300a34bf887e621853c6f22f8`). 새 Medusa 4세션 모두 독립 COMPLETE 310, SDK 총 87호출·1,740토큰·95도구·가상 2,436 micro-USD/정산 후 예약 0. 조건 일치 0건.
- Gate/Evidence: `make check` PASS(Python 470·mypy 48), 추가 13개·외부 배치 총 29개 회귀. 93개 artifact·4거래/4학습 원장·복사 명부 재집계·소스 48개 hash·비밀값/포트/컨테이너/볼륨 보존 확인. [상세](../test/external-four-arms.md).
- Next: CW05 모델 HTTP 3번의 선언 공급처/이벤트 조건 적용·실행 전 원시 관측 일치·배치 판정 연결. 실제 모델/동등 초기 정책/미공개 비교 아님. 브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — B3 외부 실행을 사전 명부·전체 예산에 연결

- Changed: 연습/외부 명세 분리·8칸 사전 명부·학습 전 상한 예약·학습/실행 비용 반영·usage UNKNOWN 예약·독립 증빙 정산·중단 후 종료 기록으로 무호출 정산. 중간 비용의 이중 차감 수정.
- Verified: `make external-batch-smoke` PASS(`external-b3_c50e6d5ec83d407e82705d10f5ab8f5c`, Medusa `cw00-376a4a6036f6`). B3 1건 독립 COMPLETE 310·7 NOT_RUN·가상 비용 1,008/정산 후 예약 0·다음 상한 예약 거절. 공급처 조건 일치는 0건.
- Gate/Evidence: `make check` PASS(Python 457·mypy 48), 전용 16개·기존 배치 18개 회귀. 35개 artifact·복사 명부 재집계/원장 재판정·소스 48개 hash·비밀값/포트/컨테이너/볼륨 보존 확인. [상세](../test/external-comparison-budget.md).
- Next: CW05 모델 HTTP 3번의 B0/B1/B2 외부 어댑터와 선언 조건/실제 환경 일치 증거. 실제 모델/동등 초기 정책/미공개 평가 아님. 브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — B3 학습 예산을 실제 Medusa 실행까지 유지

- Changed: 완료 B3 학습/동결 증빙 검증·원래 usage DB 전달·한도 변경/누락 거절·외부 한 칸의 durable 등록·단계별/전체 회계. 학습 정책에서 새 예산 생성 거절.
- Verified: `make commerce-learning-smoke` PASS(`b3-http_b92d83ca01774e8c8eecb0c1777bbe1e`, Medusa `cw00-e1790ade5f94`). SDK 학습 22+실행 14호출·총 720토큰/31도구/가상 1,008 micro-USD·독립 COMPLETE 310·예약 0.
- Gate/Evidence: `make check` PASS(Python 441·mypy 47), 추가 회귀 18개·HTTP 총 39개. 25개 artifact·원장 재판정·학습 call prefix/소스 47개 hash·실제 토큰 미포함·포트/기존 컨테이너/볼륨 보존. [상세](../test/learning-http-budget.md).
- Next: 상세 계획 CW05 모델 HTTP 3번의 남은 전체 비교 roster 예산/외부 실행 상태 연결. 실제 모델/미공개 비교·브라우저 이번 미실행. 설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 외부 실행 세션·구매자 설정 전달

- Changed: 무호출 preflight·새 Medusa run/seller/gateway 유지·buyer-only 0600·동결 입력·STOP/신호·종료 export/준비된 실행 판정 CLI.
- Verified: 실제 `cw00-4aa4645911df` 별도 SDK 구매 COMPLETE 310/VERIFIED, `cw00-2c447f003ed1` 구매 없음 INCOMPLETE 0/NOT_READY·정책 bytes 유지. 세션 제어자의 모델 호출 0.
- Gate/Evidence: `make check` PASS(Python 423·mypy 46), 회귀 11개·UNKNOWN 예약 310 보존. 실측 후 정리 실패의 잘못된 STOPPED 출력 재현/수정·소스/diff와 17개 artifact·원장/토큰/포트/볼륨/기존 컨테이너 대조. [상세](../test/model-session.md).
- Next: 모델/Linux 설치 허용 응답 시 해당 실행 우선. 대기 중 상세 계획 CW05 모델 HTTP 3번 학습/외부 실행의 합산 비용·한도/분모 연결. 실제 모델·브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 계측 모델 실행과 실제 Medusa HTTP 연결

- Changed: buyer-only 입력·동결 정책·호출/토큰/도구/비용·fresh run/POST 계약 검사·사용량 누락 보존·독립 export/실행 주문 대조 CLI.
- Verified: `make commerce-model-smoke` PASS(`cw00-670ce8b66bc3`). 실제 Medusa 310/예약 0·지급 유실/요청 1회, SDK fixture 14호출·280토큰·13도구·가상 392 micro-USD·구매 HTTP 23회. 실행 NOT_VERIFIED와 별도 독립 판정 구분.
- Gate/Evidence: `make check` PASS(Python 412·mypy 46), 회귀 21개. `evidence/cw05-metered-http/` 11개 artifact·소스 46개 hash·독립 재판정·실제 토큰 미포함·포트/볼륨/기존 컨테이너 보존. [상세](../test/metered-http-model.md).
- Limits/Next: 실제 모델·학습 전이·브라우저 미검증. 모델/Linux 설치 허용 응답 확인, 대기 중 상세 계획 CW05 모델 HTTP 2번 세션 유지·buyer-only 설정 전달 CLI. 설치·AWS·커밋·푸시 없음.

## 2026-09-09 — Linux 소스 격리·캐시 누락 진단

- Changed: Git 가시 소스 복사·hash·비밀 경로/심볼릭 링크 거절 도구와 미실행 Dockerfile/검사 recipe 준비.
- Verified: 1,392개/24,298,278바이트 복사/hash·경계 회귀 5개. macOS `make check` PASS(Python 391·mypy 45). Linux x64 Node 22.23.2 확인.
- Failed: network none npm 설치는 esbuild/linux-x64 캐시 누락 ENOTCACHED/exit 1. Linux Python/웹/브라우저/Medusa 빌드 NOT_RUN. [원본 로그/증거](../test/linux-reproduction.md). 전용 컨테이너·메타데이터 조회 프로세스 종료, 기존 컨테이너 4개 보존.
- Blockers/Next: 자동 승인 검토가 외부 네트워크를 무인 범위 밖으로 거절. 공개 의존성 다운로드/설치 허용 응답 후 새 복사본→Docker build→network none gate. 모델 설정 응답 시 CW03 우선. 커밋·푸시 없음.

## 2026-09-09 — 수정 B0 실제 Medusa 재검증

- Changed: 기존 전이 검사에 필수 텐트 부족·조명 구매 가능 조건 추가. 구매 실행자는 변경하지 않았다.
- Verified: `make commerce-transfer-smoke` PASS(4조건×연습/Medusa). 380/360 유지, 필수 품목 부족 때 주문/지급 없이 INCOMPLETE 0·도구 10회. 실제 재고 0 POST 3개·유효 조명 견적 130/170/225 대조.
- Evidence/Gate: `evidence/cw05-b0-rerun/` 25개 artifact·8개 raw 독립 재판정·정책/소스/hash·비밀값·정리 확인. `make check` PASS(Python 386·mypy 45). [상세](../test/b0-medusa-rerun.md).
- Limits: Docker 기동 후 기존 컨테이너 4개 보존·전용 서비스 종료/포트/볼륨 유지. 실제 모델·브라우저·설치·AWS·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW08/CW09 1번 격리 소스/설정·Linux 재현 준비.

## 2026-09-09 — 평가 배치·총 예산·중단/재개

- Changed: 다중 조건/반복 명세·전체 명부·영속 비용 예약·미확정 중단·미시작만 재개·독립 raw/usage/artifact 집계.
- Verified: `make check` PASS(Python 386·mypy 45), 회귀 18개·known grid 80칸 EVALUATED/COMPLETE·가상 49,560 micro-USD. `evidence/cw07-evaluation-batch/` 903개 artifact·소스 45개 hash·독립 재요약 일치. [상세](../test/evaluation-batch.md).
- Limits/Next: SDK fixture이며 실제 모델/미공개 비교 아님. 모델 설정 시 CW03 실제 호출 우선, 대기 중 수정 B0의 Medusa 전이 재실행. 이번 브라우저/Medusa·AWS·커밋·푸시 없음.

## 2026-09-08 — 학습 뒤 정책 동결·새 Agent/세계 평가

- Changed: B2/B3 학습 artifact 동결·새 구매 Agent/대화/세계와 학습 원장 재개 공유. B0/B1 고정 정책 연결. 조건 이름/seed 재포장·동결/학습 파일 변경·문맥 재사용 거절.
- Verified: `make check` PASS(Python 368·mypy 44), 회귀 23개. `make frozen-evaluation-smoke` PASS: 네 방식 알려진 평가 COMPLETE 380, 총 fixture 호출 0/14/37/36·가상 비용 0/392/1036/1008 micro-USD. 잘린 응답은 SDK MaxTokensReachedException/실행 ERROR·원장 COMPLETE로 구별.
- Evidence: `evidence/cw07-frozen-evaluation/` 46개 artifact·raw 재판정·원본 usage 재합산·학습/동결/spec/source hash 대조. [상세 기록](../test/frozen-model-evaluation.md). preflight 모델/단가/한도 누락 exit 2.
- Limits: 같은 초기 정책의 정식 비교나 실제 모델/미공개 평가가 아니다. pilot 모델군 15칸은 NOT_RUN 유지. 브라우저/Medusa·설치·AWS·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW07 3번 다중 조건·반복·전체 분모의 평가 명세/배치 연결.

## 2026-09-08 — B2 단일 대화 시뮬레이션·관찰 절차 준비

- Changed: 단일 Strands Agent/모델이 같은 대화에서 두 격리 연습·구매·독립 판정·자기 수정. 별도 검토자 없이 정책/실험/usage hash 대조·부모 보존. 개발자 증빙 판독 비교 절차/빈 양식 준비(참가자 0명).
- Verified: `make check` PASS(Python 345·mypy 43), 추가 회귀 19개. `make b2-smoke` PASS(23 fixture 호출·460토큰·22도구·644 micro-USD). 초기 INCOMPLETE 0·후보 COMPLETE 380·동일 snapshot·Peer Reviewer 0회.
- Evidence: `evidence/cw07-b2-offline/` 9개 artifact·raw export 재판정·호출/소스 8개 hash 확인. [상세 기록](../test/b2-single-agent-simulation.md). `b2-preflight` 모델/단가/한도 누락 exit 2.
- Limits: 실제 모델/새 조건·B1/B2/B3 평가·실제 개발자 관찰 미검증. 브라우저/Medusa·설치·AWS·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 정상 실제 호출. 대기 중 상세 계획 CW07 2번 B2/B3 학습 뒤 동결·별도 평가 연결.

## 2026-09-08 — 공통 토큰/도구 한도·known pilot·영어 제출 준비

- Changed: 세 역할의 영속 총 토큰/도구 admission·재개/미확정 예약·거절 집계. 20칸 동결 pilot/B0 5개·독립 재요약과 실패/미실행 분모. B0 품목 후보 누락 때 부분 구매 중단. 영어 README·제출/테스트/영상 대본·아키텍처·준비 목록.
- Verified: `make check` PASS(Python 326·mypy 42), 추가 회귀 22개. `make b3-smoke` PASS(22 fixture 호출·440토큰·18도구·616 micro-USD). `make pilot-smoke` PASS(B0 4 COMPLETE·1 INCOMPLETE, 모델군 15 NOT_RUN). 불가능 품목 지출 130→0·가능한 부분 조달 360 유지.
- Evidence: B3 13개·pilot 수정 전후 각 18개 artifact·독립 원장/재요약·현재 소스 hash 확인. SVG Chromium 렌더 확인. [상세 기록](../test/shared-limits-and-pilot.md).
- Limits: 수정 B0의 Medusa·제품 browser gate 이번 미실행. 실제 모델/비교·미공개 평가·개발자 관찰·영상/공개/제출은 남았다. 설치·AWS·커밋·푸시 없음.
- Next: 모델 설정 시 CW03 실제 호출. 대기 중 상세 계획 CW07 1번 B2 단일 에이전트 시뮬레이션 실행자·이후 B3 동결/평가.

## 2026-09-09 — 시간표 가격·재고 변경과 독립 이벤트 판정

- Changed: 명시적 이벤트 schema·독립 제어자 일정/배타적 claim·실패 후 무재시도·변경 전후 Store/Admin GET·정확한 POST/시각·최종 export/배치 판정 연결. 초기/이벤트/거래/usage 상태를 구별한다.
- Verified: `make external-events-smoke` PASS(`events_7d6c250bf3034d9d9966a31761cc6618`). 8칸 중 3실행/5 NOT_RUN, 시간표 변경 2실행 일치·미발생 false. 독립 COMPLETE 380/310·SDK INCOMPLETE 0; 실행 결합 VERIFIED 1·INCOMPLETE 2. SDK 9회 admission/8회 usage·160토큰/49도구·가상 224 micro-USD·미확정 예약 99,776/다음 칸 차단.
- Gate/Evidence: `make check` PASS(Python 535·mypy 50), 추가 37개 회귀. 이전 실패와 기대값 교정 포함 229개 artifact/10세션·4명부 재집계·원시 증거/소스 hash·실제 비밀값/서비스 정리 대조. [상세](test/timed-condition-events.md).
- Next: 납품 전환 부근 `EXTERNAL_DELIVERY_MISMATCH` 진단·회귀 후 다른 이벤트 일정/발생 증거 연결. SDK의 오래된 견적 선택·미확정 usage는 실제 모델 증거가 아니다. 브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 납품 전환 GET의 UNKNOWN 처리·재조회 복구

- Cause: 실제 Medusa GET 6개에서 fulfillment 납품 표시와 품목 납품 수량 0이 공존했다. 설치된 workflow의 fulfillment 갱신→주문 수량 기록 순서와 일치한다. 보존 응답 회귀 4개로 원래 계약 오류를 재현했다.
- Changed: 미수령·단일 비취소 납품·출고 수량 충족·부분 납품 수량만 pending으로 구별한다. payment/order는 UNKNOWN·snapshot은 미수령을 유지하고 후속 GET으로만 복구한다. 수령 역행/금액/소유권 모순 거절 유지.
- Verified: 회귀 4실패→12통과·기존 gateway/재고 포함 59개. `make commerce-delivery-smoke` 실제 pending 1건·예산 불변/단일 checkout·독립 COMPLETE 310. 기존 이벤트 재실행 PASS, B0 두 건 COMPLETED/독립 COMPLETE 380·310. SDK 실패/미확정 예약은 유지.
- Gate/Evidence: `make check` PASS(Python 547·mypy 50), 84개 artifact·전후 source/diff·원시 GET/원장/명부 재판정·소스 hash·실제 비밀값/포트/컨테이너/볼륨 대조. [상세](test/delivery-transition.md).
- Next: CW05 모델 HTTP 3번의 지급 응답 유실·알림 지연/중복 등 남은 이벤트 일정/발생 증거. 실제 모델·브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 선언 지급 응답 지연·실제 타임아웃 대조

- Changed: run/event별 영속 설정/단일 소비/종료·지급 처리 후 지연·민감 정보 없는 클라이언트 transport 계측·선언 일정과 원시 소비/타임아웃/실행 구간 검증.
- Verified: `make external-response-smoke` PASS(`response-events_5db80f5526e549eead338d6defbb67ea`). B0/SDK 실제 4.002초 지연 중 2.002초 ReadTimeout 후 같은 주문 조회로 COMPLETE 310. 미사용 일정은 COMPLETE 310/조건 false. 8칸 중 3 VERIFIED·5 NOT_RUN, SDK 14호출/280토큰/전체 53도구/가상 392 micro-USD·예약 0.
- Gate/Evidence: `make check` PASS(Python 567·mypy 52), 추가 20개 회귀·69개 artifact·원시 조건/장애/거래/명부 재집계·소스 hash·실제 비밀값/포트/컨테이너/볼륨 대조. [상세](test/scheduled-response-loss.md).
- Next: CW05 모델 HTTP 3번의 알림 지연/중복·재전송 일정/발생 증거. 실제 모델·브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 선언 알림 지연·복사·재전송과 실제 SSE 대조

- Changed: run/event별 원자적 설정/소비·복사 큐/발행 커서 기록·원본 재전송·retention 이후 감사 자료·시계/실행 구간/원시 증거 조건 판정.
- Verified: `make external-notification-smoke` PASS(`notification-events_b07ec2b16a204b0fbb623a8c4fce9038`). B0/SDK 각각 4프레임·발행/수신 일치·old/중복 제거·최종 3/6. 세 실행 COMPLETE 310·조건 2 true/미사용 false·8칸 중 5 NOT_RUN. SDK 14호출/280토큰/53도구/가상 392 micro-USD·예약 0.
- Gate/Evidence: `make check` PASS(Python 588·mypy 54), 추가 21개 회귀·74개 artifact·독립 재집계·소스/실제 비밀값/포트/기존 컨테이너/볼륨 대조. [상세](test/scheduled-notifications.md).
- Next: CW05 모델 HTTP 4번의 CW06 관측 변화 큐·최신 버전 유지·재확인·추가 호출 한도. 실제 모델 반응/재계획·브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 관측 변화 큐·집행 직전 재확인과 실제 B 복구

- Changed: 선택 반응 설정·별도 읽기 소비자·최신 관측/중복 합치기·추가 판단/공통 usage 한도·주문/지급 직전 상태/견적 검사·종료 후 변화 재호출/시계 무재호출.
- Verified: `make commerce-reaction-smoke` 교정 실행 PASS(`reaction_44ee83ff799943b5bf4660388a514fad`). 12초 모델 대기 중 A 재고 10→0/커서 11·12 수신·오래된 A POST 차단·B 주문/지급 각 1회·독립 COMPLETE 380. SDK 9호출/180토큰/8도구/가상 252 micro-USD·예약 0·재판단 5회.
- Gate/Evidence: `make check` PASS(Python 608·mypy 56), 추가 회귀 20개·45개 artifact/56소스 hash·거래/이벤트 재판정·실제 비밀값/서비스 정리 대조. 최초 fixture `due_tick` 오인 실패/미확정 예약 10,048 보존. [상세](../test/observed-change-replanning.md).
- Next: CW07 동결 비교 명부/실행 계약의 반응 설정. 실제 모델 효과·UI 반응 표시·브라우저·설치·AWS·커밋·푸시 없음. 이전 로그 12항목은 월별 보관본으로 이동했다.

## 2026-09-09 — 동결 비교 명부의 반응 설정·공통 원장

- Changed: 학습 전 명부/방식별 실행 계약에 반응 설정 고정·B0 비활성/모델군 동일 상한·실행 시 덮어쓰기/변조/누락 거절·반응 실행 별도 집계·과거 명부 호환.
- Verified: `make external-reaction-smoke` PASS(`reaction-batch_364703e5bcc54663a4e107fd0801269a`). 실제 네 방식 COMPLETE 310/380/380/380·조건 4건·반응 실행 3건. 학습+실행 72 SDK호출/1,440토큰/84도구/가상 2,016 micro-USD·예약 0, 학습 원장 앞부분/실제 관측·POST 대조.
- Gate/Evidence: `make check` PASS(Python 632·mypy 56), 추가 24개 회귀·119개 artifact·복사 명부/거래/조건 재집계·소스/실제 비밀값/서비스 정리 대조. [상세](../test/frozen-reaction-comparison.md).
- Next: CW06 실행자의 관측 기준·재판단/집행 차단·중단 사유 읽기 전용 UI. 실제 모델 효과·미공개 비교·브라우저·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 실행자의 판단/집행 기록 UI

- Changed: 운영자 선택 spec/run/목표/예산 고정·종료 hash/감사 재집계·읽기 전용 요약 API·임시/종료 상태·판단/차단/중단 사유 UI·2초 조회/5초 타임아웃.
- Verified: 보존 Medusa B0/B1/B2/B3 재집계, 실제 API/브라우저 5판단/1차단·임시 증가/종료 전환·파일 변조/다른 run/연결 실패/정체 후 이전 수치 제거. 1440/390/320px 가로 넘침·콘솔 오류·쓰기 요청 0.
- Gate/Evidence: `make check` PASS(Python 663·mypy 57), `make check-browser` PASS(25개), 추가 Python 31개/브라우저 6개·11개 artifact·소스/입력 hash·포트 3개 반환. [상세](../test/execution-reaction-ui.md).
- Next: 진행 중인 SDK/Medusa와 UI를 동시에 연결해 같은 run의 SSE/종료 기록/독립 export 대조. 새 Medusa 거래·실제 모델·설치·AWS·커밋·푸시 없음.

## 2026-09-09 — 실제 SDK/Medusa 실행과 반응 UI 동시 대조

- Changed: `commerce-reaction-ui-smoke`·브라우저 시나리오. 초기 화면→입력 선택→A 재고 변경/오래된 주문 차단→B 납품→종료 기록→독립 export를 같은 실행으로 검사.
- Verified: `reaction-ui_c900888b02084a2d87daa91a028617ae` PASS. 실제 B COMPLETE 380·예약 0·5판단/1차단·SDK 9호출/180토큰/가상 252 micro-USD. 실행자 cursor 28/브라우저 30, 실행 중/종료 후 export 두 건 독립 판정 일치.
- Gate/Evidence: `make check` PASS(Python 663·mypy 57), 실제 API/SSE/브라우저 연결 PASS·요청 27 GET/Authorization 없음·콘솔/넘침 0. 38개 artifact·73소스 hash·복사본 재판정/실제 비밀값/포트 6개/기존 컨테이너 4개/볼륨 2개 대조. [상세](../test/execution-reaction-ui.md).
- Next: 현재 구현/증거에 맞춰 영어 제출 초안·재현·시연 범위 갱신. 실제 모델 효과·설치·AWS·커밋·푸시 없음.
