# Rehearsal 개발 환경

현재 공개 AWS 데모와 배포 절차는 [serverless 배포 안내](../infra/serverless/README.md)를 따른다. 아래 환경은 보존한 로컬 구현/회귀 검사 경로다.
로컬 개발 환경과 CW01·CW02의 합성 거래 세계를 실행할 수 있다. Python health/관측 API, React 거래 관측실, 독립 Medusa core를 실행할 수 있다. CW00의 실제 거래 계약 검사는 추가했으며, 자체 가상 세계·독립 검증도 구현했다. 실제 모델·학습된 정책 전이·AWS 배포는 아직 검증하지 않았다.

## 현재 저장소에서 시작

```sh
make check
make check-browser
make dev
```

`make dev`는 API와 React를 함께 실행한다. 관측 run 연결과 실제 브라우저 재현은 [CW06 관측실](test/observer-ui.md)을 참고한다. `http://127.0.0.1:15173`에서 실제 health API 연결을 확인한다. Ctrl+C로 두 프로세스를 종료한다. 별도 터미널에서 `make commerce`를 실행하면 전용 PostgreSQL/Redis, 마이그레이션, Medusa 서버를 준비한다. 이 명령도 Ctrl+C로 해당 서버·컨테이너만 종료하며 데이터 볼륨은 유지한다.

## 새로운 설치

호스트 전제: macOS/Linux, Python 3.12 이상(bootstrap용), uv 0.11.23, Make, Git, Docker Engine/Desktop와 Compose v2. Docker는 독립 상거래 검사와 컨테이너 재현에 필요하다. macOS arm64와 같은 호스트의 Linux amd64 컨테이너에서 오프라인 gate·브라우저·주요 SDK 실험·Medusa 컴파일을 검증했다. 독립 기기와 Linux Medusa DB/HTTP 실행은 별도다. [Linux 재현 절차와 증거](test/linux-reproduction-20260912.md)를 참고한다.

```sh
make setup
make check-browser
make commerce-smoke
```

`setup`은 공식 Node 배포의 SHA-256을 확인한 뒤 저장소 전용 Node·Python을 설치하고, `uv sync --locked`와 `npm ci`로 의존성을 복원한다. 브라우저 바이너리도 저장소에 설치한다. 네트워크 다운로드가 발생하지만 클라우드 계정·모델·결제 API는 호출하지 않는다. `commerce-smoke` 첫 실행에는 고정 digest의 Docker 이미지가 필요하므로 Docker Hub에 접근할 수 있다.

이미 있는 `.env`는 덮어쓰지 않는다. `make init-env`는 파일이 없을 때만 임의의 로컬 비밀값을 생성한다. `.env.example`은 키 목록 설명용이며 실제 비밀값을 포함하지 않는다. 재설치로 DB 비밀번호를 바꾸지 말 것. `.env`를 잃으면 기존 볼륨을 삭제하지 말고 먼저 저장된 DB와 자격증명의 일치 여부를 확인한다.

## 고정한 구성

| 구성 | 버전·위치 | 목적 |
|---|---|---|
| Python | 3.12.13 · `.tooling/python`, `.venv` | 세계·검증·Strands 개발 |
| uv | 0.11.23 · 호스트 사전 설치 | lock 기반 Python 설치 |
| Node / npm | 22.23.2 / 배포에 포함된 10.9.8 · `.tooling/node` | 웹·독립 상거래 실행 |
| Strands | 1.54.0 · `uv.lock` | Agent·Graph·Bedrock 어댑터 import 확인 |
| 웹 | React 19.2.8, TypeScript 5.9.3, Vite 8.2.2 | 제품 UI 개발 셸 |
| Medusa | 2.20.1 · `services/medusa` | E2 후보인 독립 상거래 백엔드 |
| PostgreSQL / Redis | 17-alpine / 7.2-alpine, `dev/compose.yaml` digest 고정 | 전용 DB·캐시 개발 서비스 |
| Playwright | 1.63.0 · `.tooling/browsers` | HTML·React 로컬 브라우저 검사 |

정확한 전이 의존성은 lock 파일이 기준이다. 초기 npm 감사에서 확인한 lodash·ajv·qs·BullMQ 경유 취약 의존성은 같은 major의 수정 버전으로 고정했다. `package.json`의 overrides와 [검증 기록](test/development-readiness.md)을 함께 본다. Medusa의 React 18 관리자 의존성과 제품의 React 19는 별도 workspace에 둔다. 관리자 UI, Enterprise RBAC, 실제 지급 제공자는 활성화하지 않는다. 현재 Medusa의 event bus와 lock은 기본 단일 프로세스 메모리 구현이다. Redis health가 통과했다고 운영용 분산 이벤트 구성을 검증한 것은 아니다.

## 명령과 검증 범위

| 명령 | 수행하는 일 | 수행하지 않는 일 |
|---|---|---|
| `make check-docs` | HTML 구조·파일 링크·하네스 설정·문서 분량 | 브라우저·제품 실행 |
| `make doctor` | 고정 런타임·의존성·SDK import 검사 | 모델 생성·AWS 인증 |
| `make check` | 문서 + doctor + lock·lint·Python 타입·테스트 + 웹 빌드 | 네트워크 설치·Docker·모델 호출 |
| `make check-browser` | 로컬 API·React·SSE/증빙 UI와 제안 HTML의 브라우저 회귀 | 실제 Medusa 거래·실제 모델·전체 지연 목표 |
| `make operating` | 새 run의 별도 18001 HTTP 서버·독립 worker 실행 | Medusa·모델·UI |
| `make operating-smoke` | 실제 HTTP 역할/격리·응답 유실·시계·재시작 검사 후 종료 | Medusa E2·모델 |
| `make operating-sdk-smoke` | 스크립트 모델 SDK→HTTP→worker 구매·수령 후 종료 | 실제 LLM 성과 |
| `make frozen-evaluation-smoke` | B0/B1/B2/B3 알려진 학습·동결·새 세계 평가 SDK fixture | 실제 모델·미공개/정식 비교 |
| `make frozen-evaluation-preflight` | 동결 평가 설정 형식 검사 | AWS client 생성·단가 검증 |
| `make pilot-smoke` | 알려진 5조건 B0·고정 20칸 결과/미실행/실패 분모 | 실제 모델·B1/B2/B3 비교·미공개 평가 |
| `make b2-smoke` | 같은 Agent/대화의 두 연습·정책 제안·공통 회계 SDK fixture | 실제 모델·B2 효과·별도 평가 |
| `make b2-preflight` | B2 설정 형식 확인, 누락 시 실패 | AWS client 생성·단가 검증 |
| `make b3-smoke` | 초기 구매·독립 검토·후보 구매 공통 한도 SDK fixture | 실제 모델·Peer Review 효과 |
| `make b3-preflight` | B3 설정 형식 확인, 누락 시 실패 | AWS client 생성·단가 검증 |
| `make agent-preflight` | 모델 설정 형식 검사, 누락 시 실패 | AWS client 생성·권한/단가 검증 |
| `make agent-run` | 명시적 설정으로 실제 모델 실행·사용량/도구 trace·독립 판정 | 외부 상거래 전이·실제 청구 보장 |
| `make policy-smoke` | 상태 fork·알려진 가격 반례·정책 diff·재실험 | 실제 모델 Peer Review·holdout 평가 |
| `make world-smoke` | 로컬 원장의 정상 합성 구매·tick 10 수령 | 모델·실시간 서버·전이 |
| `make world-fixtures` | 정상/F01/F02/F06 실행·raw 증거 export·독립 판정 | LLM 평가·HTTP 장애 주입·전이 |
| `make commerce-race-smoke` | 기동된 Medusa에서 두 run checkout 중첩·단일 납품·UNKNOWN 예약/재시작/중복 경계 대조 | 분산 lock·임의 경합 순서·모델 판단 |
| `make commerce-convergence-smoke` | 기동된 Medusa에서 두 Chromium 소비자·개별 단절/커서/retention 복구·원장 대조 | 두 구매자 경합·실제 모델·여러 기기 |
| `make commerce-contract` | 기동된 로컬 Medusa의 합성 주문·지급·납품·권한 검사, fixture 보존 | 자체 월드·모델·전이·실자금 |
| `make commerce-smoke` | 전용 DB 기동·migration·Medusa health·정리 | 주문 생성·지급·수령·전이 |
| `make smoke-local` | check + 설치된 overnight 하네스 점검 | 야간 actor/critic 실행·커밋 |

`check`는 설치 누락을 성공으로 건너뛰지 않는다. 문서만 보려는 환경은 `check-docs`를 쓴다. Make가 실패했으면 앞의 PASS 메시지 몇 줄로 완료를 판단하지 않는다.

## 포트와 격리

| 주소 | 서비스 |
|---|---|
| `127.0.0.1:15173` | React/Vite |
| `127.0.0.1:18000` | Python health API |
| `127.0.0.1:18001` | 자체 운영 HTTP 세계 (별도 명령) |
| `127.0.0.1:19000` | Medusa |
| `127.0.0.1:55432` | PostgreSQL |
| `127.0.0.1:56379` | Redis |

기존 5432/9000/8080 서비스와 겹치지 않는다. 프로세스는 loopback에서만 대기한다. 포트가 점유되어 있으면 소유자를 종료하지 않고 오류로 멈춘다. Docker 프로젝트 이름은 `rehearsal-dev`; 종료 시 이 프로젝트에만 `compose down`을 적용하고 볼륨은 제거하지 않는다. 다른 프로젝트의 DB·컨테이너·전역 Node·shell profile은 재사용하거나 변경하지 않는다.

## 로컬 파일과 로그

- `.tooling/`: 런타임·패키지 캐시·브라우저. 배포물에 포함하지 않는다.
- `.local/logs/medusa.log`: 서버 진단. 공개 전에 원문을 검토하며, 원장을 대신하는 증거로 쓰지 않는다.
- `.local/commerce-smoke.json`: health 검사 범위. 매 검사 결과이며 제품 성공 기록이 아니다.
- `.env`: mode 0600으로 생성하는 로컬 DB 비밀값. Git 제외.
- `web/dist/`, `.medusa/`, `test-results/`: 재생성 가능한 결과. Git 제외.

## 모델 연결은 CW03에서

`AWS_PROFILE`, `AWS_REGION`, `REHEARSAL_MODEL_ID`는 향후 명시적으로 연결할 설정이다. 이 환경 셸은 AWS 자격증명을 소비하지 않는다. 현재 import 검사만 통과했으며 계정 권한·리전별 모델 가용성·호출 비용은 확인하지 않았다. 모델 기능을 시작할 때 실제 선택 모델의 접근 권한과 최소 호출을 별도 검증하고 비용을 기록한다.

출처: [Strands Python](https://strandsagents.com/docs/user-guide/quickstart/python/), [Medusa 설치](https://docs.medusajs.com/learn/installation), [Node 고정 배포](https://nodejs.org/download/release/v22.23.2/). 라이선스·재배포 범위는 [Third-party notices](../THIRD_PARTY_NOTICES.md)를 따른다.

CW00 재현: `make commerce`가 준비된 뒤 별도 터미널에서 `make commerce-contract`. 실행마다 테스트 데이터를 추가한다. [실측 계약과 증거](test/medusa-contract.md)를 따른다.

자체 세계·독립 검증 및 CW03 준비의 범위는 [world-foundation](test/world-foundation.md)을 따른다. `make check`에 세계·검증기·SDK fixture 테스트를 포함하며 실제 모델은 호출하지 않는다.

CW03 실행·추정 비용 제한과 CW04 fork 준비는 [별도 검증 기록](test/model-runner-and-policy-fork.md)을 따른다. `agent-run`은 실제 모델 호출 명령이며 오프라인 gate에 포함하지 않는다.

CW05 자체 HTTP 서버·권한·실시간 worker 검증은 [operating-http](test/operating-http.md)를 따른다. 세 operating 명령은 같은 포트를 쓰므로 순차 실행한다.

CW05 실제 Medusa 고객·예산 gateway는 `make commerce-adapter-smoke`로 검사한다. 서버 준비 후 실행하며 [계약·증거·남은 연결 범위](test/medusa-adapter.md)를 따른다.

CW05 구매 HTTP·독립 Medusa 판매자·A/B/C 공급처는 `make commerce-operating-smoke`로 검사한다. [별도 프로세스·재시작 증거](test/medusa-operating.md)를 따른다. 같은 18001 포트를 사용하므로 기존 operating 명령과 순차 실행한다.

동결 정책의 B0 고정 규칙 대조는 `make commerce-transfer-smoke`. [최초 6개 실행과 제한](test/frozen-policy-transfer.md) 및 [수정 B0의 8개 재검증](test/b0-medusa-rerun.md)을 따른다. 실제 모델 성과와 구분하며, CW03 CLI의 `--policy <manifest>`는 모델/비용 설정 후 사용할 별도 경로다.

모델 계측과 실제 구매 HTTP의 연결 검사는 `make commerce-model-smoke`다. [SDK fixture/Medusa 실제 거래와 독립 후속 판정](test/metered-http-model.md)을 구별한다. 실제 모델용 CLI의 설정/실행 범위도 해당 문서를 따른다.

외부 모델 실행용 세션은 [Medusa 세션 CLI](test/model-session.md)를 따른다. `make commerce-model-session-preflight`는 설정만 검사한다. 실제 모델 설정 전에 외부 시계를 시작하지 않으며, fixture 진단은 명시적 별도 모드다.

관측 변화에 반응하는 구매 실행은 [선택 반응 설정/검증](test/observed-change-replanning.md)을 따른다. `make commerce-reaction-smoke`는 실제 Medusa와 알려진 SDK 지연/재고 변경을 검사하며 실제 모델 호출은 없다.

외부 비교 명부의 관측 반응 설정은 [동결 반응 비교](test/frozen-reaction-comparison.md)를 따른다. `--max-replans`는 명부 준비 때만 지정하며, `make external-reaction-smoke`는 네 방식의 실제 Medusa/SDK 연결 검사다.

실행자의 판단/차단 기록 UI는 [실행 기록 선택과 검증](test/execution-reaction-ui.md)을 따른다. API 시작 때 `REHEARSAL_EXECUTION_CONFIG`로 입력 hash·run·목표/예산을 고정한다. 임시 기록과 종료 기록을 구별하며 구매/모델 호출은 없다.

`make commerce`가 준비된 뒤 `make commerce-reaction-ui-smoke`는 실제 SDK/Medusa 실행과 API/SSE/반응 UI/독립 증빙을 동시에 검사한다. 알려진 A 차단/B 380 fixture이며 실제 모델 효과 검증은 아니다. `make dev`·브라우저 검사와 같은 포트를 쓰므로 순차 실행한다.
