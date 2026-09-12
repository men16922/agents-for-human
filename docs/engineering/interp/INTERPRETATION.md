# Engineering Interpretation — Rehearsal

공통 bible은 `make overnight-where`가 출력하는 플러그인의 `templates/docs/engineering/`에서 읽는다.

## HARNESS — 현재 성숙도와 경계

- 현재 초안·개발 기반 단계. `make check`는 고정 런타임과 설치된 의존성을 요구한다. 설치 명령 `make setup`은 대화형 개발 준비 범위이며 야간 seed가 아니다.
- Claude: `scripts/overnight/overnight-settings.json`; Codex: `.codex/rules/overnight.rules`; opencode: `scripts/overnight/opencode.json`.
- AGY 설정은 저장소의 snippet만 준비했다. 전역 설정에는 병합하지 않았다. Kiro 프로필은 installer가 생성했으며 실제 엔진 실행은 검증하지 않았다.
- 명령 규칙은 보조 경계이며 네트워크 sandbox의 대체물이 아니다. runner의 엔진별 sandbox·권한 정책도 함께 적용한다.

## LOOP — 실행 경로

- runner: `<resolved HARNESS_ROOT>/templates/scripts/overnight/run.sh`.
- 이 컴퓨터는 Claude/Codex 캐시 버전이 달라 config의 `harness_root`를 요청한 1.5.0 경로로 고정했다. 다른 환경에서는 경로를 재설정한다.
- 기본 엔진 Claude; actor·critic 모델은 CLI 기본값. 저장소에 runner/helper를 복사하지 않는다.
- 백로그: `docs/NEXT_PLAN.md`의 `[auto]`만 소비. 최초 실행 전 초기 커밋과 clean worktree 필요.
- 실행 요청 시 `/overnight-seed`로 재점검하고 `MAX_ITER=1 make overnight-once`로 1회 검증, 후속 검수는 `/overnight-report`.
- 이번 설치에서는 모델 기반 실행·자동 커밋을 하지 않았다.

## VERIFICATION — 세 계층

- 기계적: `make check`는 문서·설정과 개발 도구·SDK import·Python 검사·React 빌드를 확인한다. `check-browser`는 별도 로컬 브라우저 검사다. 거래·모델·AWS 성공을 증명하지 않는다.
- 의미적: `OVERNIGHT_CRITIC=auto` 사용 시 플러그인 critic + 저장소 `scripts/overnight/CRITIC_PROMPT.md`. 목표를 실측처럼 쓰거나 미확정 지급을 성공으로 바꾸는 변경을 검토한다.
- 사람: 모바일 가독성, 기획의 설득력, 에이전트의 필요성, 사용자 테스트와 실제 AWS 결과를 확인한다. 이 작업은 `[manual]`이다.

## AGENTIC — 실행 단위

단일 엔진·단일 항목. 별도 병렬 lane은 구성하지 않는다. future runner의 critic은 구현자와 독립된 읽기 전용 검토다.

## CONTEXT — 복원과 문서 예산

`AGENT_BRIEF` → `STATUS` → `NEXT_PLAN` → 최근 `PROGRESS_LOG` → `LESSONS`.
brief 60줄, status/plan/log 120줄, lessons 40줄. 완료 요약은 `COMPLETED_SUMMARY`, 결정은 `DECISIONS`, 장기 로그는 `docs/archive/`.

## PROMPT — 지침 출처

iteration prompt와 contract는 플러그인 기본값을 사용한다. 저장소 override는 critic의 제품 불변 조건만 둔다. 제품용 런타임 프롬프트는 아직 없다.
