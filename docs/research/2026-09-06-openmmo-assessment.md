# OpenMMO 조사와 커스텀 월드 POC 선택

확인일: 2026-09-06. 목적: 해커톤 POC의 기반 선택. 실제 결제 사업 출시 검토와 구분한다.

## 결론

OpenMMO는 사람이 보는 3D 세계에서 AI가 거래하는 장면을 만드는 후보로 적합하다. 거래 코드와 에이전트 클라이언트가 실제로 있다. 그러나 반복 실험·장애 주입·독립 평가가 제품 중심인 이번 POC에서는 작은 커스텀 거래 세계를 직접 만드는 방식을 권장한다. 채택 확정이나 실행 성능 검증은 아니다.

- 연구 대상으로 활용: 적합.
- 독립된 비상업 실험 환경으로 실행: 라이선스의 허용 목적과 실행 조건을 확인한 뒤 검토 가능.
- 저장소를 포크해 MIT/Apache 제출물로 배포: 원본 라이선스를 임의로 바꿀 수 없으므로 그대로 진행할 수 없다.
- 우리 에이전트와 별도 프로세스로 연동: 기술적 후보. 분리했다는 사실만으로 라이선스·대회 제출 요건이 해결되지는 않는다.

## 조사 범위와 한계

- GitHub API로 master의 commit `603807666d7b6f52ede8acb38580b6d35c1c976b` 확인. 커밋 시각은 2026-09-06 11:08:55 UTC.
- README, LICENSE, agent 문서, 경제·거래 문서, 거래 서버·메시지·에이전트 소스, Docker Compose, 클라이언트 패키지, CI 설정을 읽었다.
- 선택 파일 20개는 임시 디렉터리에서 읽었다. 이 저장소에 OpenMMO 코드나 에셋을 편입하지 않았다.
- 설치·빌드·테스트·브라우저 로그인·LLM 호출·대량 지형 생성은 수행하지 않았다. 라이브 서버에서도 행동하지 않았다.
- 코드의 존재와 문서상 지원은 확인했지만 작동·성능·보안 보장은 하지 않는다. 전체 저장소 감사도 아니다.

## 무엇을 제공하는가

| 요소 | 확인 근거 | POC에서의 의미 |
|---|---|---|
| 브라우저 3D 세계 | Svelte/TypeScript + Three.js/Threlte | 사람과 AI의 활동을 보여줄 기반 |
| 게임 서버 | Rust/Tokio, WebSocket, 공유 Rust 타입과 WASM | 서버가 상태와 행동을 판정 |
| AI 클라이언트 | Rust agent-client, 이동·행동·관측·LLM 호출 계층 | 고수준 의사결정과 저수준 실행을 분리 |
| NPC 상점 | `BuyItem`, `BuyItems`, 판매·되사기, 서버 거래 처리 | 게임 화폐 구매를 새로 만들 필요가 줄어듦 |
| 플레이어 거래 | 제안·잠금·확인, revision, 아이템·골드 이전과 원장 | 거래 조건 변경과 동시성 검토에 참고 |
| 흥정 | LLM 가격 제안, 서버의 가격 범위·예산·쿨다운 제한 | 모델 판단과 강제 규칙을 분리하는 사례 |
| 실행 배포 | Compose의 terrain-init/server/client/선택 agent-client | 컨테이너 경로가 있으나 실제 기동 미검증 |
| 검사 | Rust fmt/clippy/test, WASM·Vitest·Svelte 검사 CI 설정 | 테스트 기반 존재. 현 커밋의 CI 성공 여부는 미확인 |

출처: [README][readme], [메시지][messages], [거래 서버][trading], [플레이어 거래][player-trade], [Compose][compose], [CI][ci].

## 그대로 붙이면 안 되는 차이

### 1. 사람과 에이전트의 동등성은 계정 역할까지 같다는 뜻이 아니다

일반 플레이어를 AI가 조종하는 흐름은 공식 문서에 있다. 반면 운영자 지정 공식 NPC에는 특별한 거래 규칙이 적용된다. `player_trade.rs`는 공식 NPC의 자유 거래를 거절하며, `trading.rs::open_trade`는 공식 NPC에게 거래창을 보내는 경로를 제한한다. 모든 AI가 거래 불가능하다는 뜻은 아니다. 사용할 계정 역할과 실제 명령 경로를 확인해야 한다. [일반 에이전트 시작 안내][quickstart], [플레이어 거래][player-trade]

### 2. 게임 거래와 분산 결제는 다른 실패 모델을 갖는다

묶음 구매는 아이템·가격·지갑·수량 등을 검사한 뒤 한 번에 상태를 변경하는 구조다. 결제 제공자와 판매처가 분리되어 지급은 성공했지만 납품은 지연되는 환경은 별도 모델링이 필요하다. 기존 게임의 보호 장치를 제거해 실패를 만들기보다는, 독립된 판매처·지급·배송 서비스를 실험 대상으로 두는 편이 목적에 맞는다.

플레이어 거래 경로에서는 DB 저장 실패를 기록하고 주기적 저장으로 넘기는 코드도 확인했다. 이를 근거로 재시작·장애 상황의 원장 일관성이 검증됐다고 말할 수 없다. 읽기 조사에서 발견한 추가 검증 지점이며, 재현된 버그로 주장하지 않는다. [거래 서버][trading], [플레이어 거래][player-trade]

### 3. 반복 실험 엔진은 추가 작업이다

확인한 문서·코드에서는 실험용 전체 상태 fork/reset, 통제된 가상 시계, 장애 스케줄, 평가용 seed 분리, 실행 이력의 결정론적 재생을 하나의 공개 기능으로 제공하는 것을 찾지 못했다. 파일 저장이나 지형 seed가 있다는 사실은 전체 경제·NPC 메모리·세션 상태를 재현할 수 있다는 뜻이 아니다. 실시간 시계와 메모리 상태가 있는 서버를 검증용으로 분리하는 작업이 남는다.

### 4. Strands 연결은 별도 구현이다

현재 agent-client는 자체 드라이버가 Claude/Codex/OpenRouter/OpenAI 계열 백엔드를 호출하는 형태로 설명되어 있다. 외부 제어용 MCP는 문서상 제거되었고 관전 패널은 읽기 전용이다. Strands를 단순히 모델 URL로 교체했다고 충족한 것으로 간주하지 않는다. Strands가 계획·도구 실행을 실제 소유하는 WebSocket 어댑터 또는 제어 브리지가 필요하다. [에이전트 문서][agent]

### 5. 작은 영역으로 실행할 수 있지만 가벼운 단일 웹 앱은 아니다

README는 전체 지형 생성 결과를 약 73 GB라고 안내한다. 그러나 지형 CLI에는 region 범위 제한이 있고 Compose는 기본적으로 -2..1 범위를 지정한다. 따라서 73 GB가 최소 실행 요구량이라고 말하면 부정확하다. 작은 영역의 실제 디스크·기동 시간은 측정하지 않았다.

Rust, Node, WASM 생성과 별도 바이너리 에셋이 필요하다. 기본 브라우저 로그인은 Google OAuth 설정을 요구한다. 에셋은 Hugging Face dataset과 `assets.lock`을 통해 별도 관리한다. [지형 생성][terrain], [Compose][compose], [에셋 안내][assets]

## POC 기준 라이선스 판단

현재 LICENSE는 **PolyForm Noncommercial 1.0.0**이다. 비상업 목적을 허용하고 개인 연구·실험 등을 열거하지만, 개인 사용 조항에는 예상되는 상업적 활용이 없는 경우라는 조건이 있다. 해커톤 POC라는 명칭만으로 해당 프로젝트의 허용 여부를 확정하지 않는다. 상금 유무만으로 자동 금지라고 단정하는 것도 피한다. [LICENSE][license]

해커톤은 제출 저장소에 MIT/Apache 라이선스를 요구하며 기존 코드 공개, 제삼자 사용 권한, 재현에 필요한 코드·에셋·설명도 요구한다. 우리 어댑터만 MIT로 공개하는 경우와 원본을 포함한 배포는 다르다. OpenMMO를 핵심 필수 의존성으로 삼으려면 권리자에게 구체적 사용·배포 허용 범위를, 주최 측에 제출 구성을 확인할 필요가 있다. 이번 조사에서는 누구에게도 연락하지 않았다. [대회 규칙][rules]

에셋 문서는 AI 생성·외부 도구·인터넷 출처를 개별 기록한다. 코드 LICENSE를 읽었다는 이유로 모든 이미지·모델·음원의 재배포 권리가 확보됐다고 해석하지 않는다. 본 POC에는 직접 만든 도형·아이콘을 쓰는 방안을 권장한다.

## 같은 목표에서 비교

아래는 코드 조사에 기반한 개발 판단이며 실측 견적이나 객관적 점수가 아니다.

| 항목 | OpenMMO 연동 | 작은 커스텀 월드 |
|---|---|---|
| 풍부한 3D 장면 | 강점 | 단순 도형·애니메이션부터 작성 |
| 기존 구매·거래 | 활용 후보 | 최소 거래 흐름 작성 필요 |
| 반복 실험과 복원 | 기존 상태를 분리·확장해야 함 | 처음부터 run별 상태와 가상 시계 설계 |
| 분산 지급·납품 실패 | 별도 기능 추가 필요 | 세 서비스와 장애 경로를 직접 정의 |
| 에이전트 제어 | 기존 프로토콜과 Rust 드라이버 적응 | 필요한 도구 계약만 제공 |
| 공개 재현 | 원본·에셋 권한과 환경 확인 | 자체 코드·도형으로 단순화 가능 |
| 독창성 증거 | 기존 AI 거래와 우리 기여 구분 필요 | 실험·검토·정책 개선에 집중 |
| 주요 위험 | 세계 통합 작업이 검증 기능보다 커짐 | 스스로 만든 시험에서만 잘하는 편향 |

## 권장 선택과 다시 검토할 조건

현재 권장안은 독립 커스텀 월드다. OpenMMO의 코드를 옮기지 않고, 관측/계획/실행 분리와 서버 강제 검증이라는 일반적인 설계 원칙을 참고한다. [상세 POC 계획](../plans/2026-09-06-custom-world-poc-plan.md).

OpenMMO를 다시 후보로 올릴 조건: 3D 플레이 자체가 필수 데모가 됨, 라이선스·제출 경로 확인, 작은 사설 월드 기동, Strands 일반 플레이어의 구매·인벤토리 확인, 초기 상태 복원까지 한 작업일 안에 검증됨. 작업일은 조사상 제안한 시간 제한이지 완료 예상 보장이 아니다. 남의 공개 서버에서 장애를 주입하거나 거래 실험을 수행하지 않는다.

[readme]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/README.md
[license]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/LICENSE
[agent]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/doc/AGENT_CLIENT.md
[quickstart]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/doc/AGENT_CLIENT_QUICKSTART.md
[messages]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/shared/src/messages.rs
[trading]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/server/src/game_state/trading.rs
[player-trade]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/server/src/game_state/player_trade.rs
[compose]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/docker-compose.yml
[ci]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/.github/workflows/ci.yml
[terrain]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/doc/TERRAIN_GENERATION.md
[assets]: https://github.com/Julian-adv/OpenMMO/blob/603807666d7b6f52ede8acb38580b6d35c1c976b/doc/ASSETS.md
[rules]: https://agentsforhumans.devpost.com/rules
