# 개발 착수 준비 검증

2026-09-06 · macOS arm64. 범위는 초안과 로컬 개발 기반이다. 아래 기록은 제품 거래·모델 실행·외부 전이 성공 또는 배포를 뜻하지 않는다.

## 확인한 기반

| 항목 | 관측 |
|---|---|
| 초안 | Rehearsal HTML, 생성 이미지 2종, 합성 장면 4개, 상세 계획·설계·심사/데모 초안 |
| 격리 설치 | Python 3.12.13 / Node 22.23.2, 저장소 전용 경로와 lock 의존성 |
| 새 Python 환경 | 별도 `.local/fresh-venv`에서 lock 설치 후 프로젝트·Strands·FastAPI import 성공 |
| 오프라인 gate | 문서·설정, doctor, lock, ruff, mypy, Python 개발 기반 테스트, React 빌드 |
| 브라우저 | 제안서 오프라인·320/390/1440px 배치·장면 전환·자동 재생 종료, React 실제 API·연결 실패 표시 |
| 독립 Medusa | 2.20.1 backend build, DB migration, `/health` HTTP 200, RBAC 비활성 |
| 기동·종료 | `make dev`와 `make commerce`의 loopback 바인딩, Ctrl+C 후 사용 포트 반환 확인 |
| 기존 환경 | 검사 전후 다른 Docker 컨테이너 이름 집합 동일 |
| 비밀값 | `.env` mode 0600, 재실행 보존, Git 제외; Git 추가 후보에서 생성 비밀값 일치 0 |
| 의존성 감사 | `npm audit --json` 및 `--omit=dev`: info/low/moderate/high/critical 모두 0 |

최종 명령 결과는 아래 실행 기록에 정리했다. npm 결과는 해당 시점의 공개 advisory 조회 결과이며 모든 취약점 부재를 보장하지 않는다. Python 패키지의 취약점 감사는 이번 npm 결과의 범위에 포함되지 않는다.

## 수정한 환경 결함

- CLI가 요구하는 `ts-node`를 Medusa 개발 의존성에 고정했다. 타입·backend build·migration·기동으로 확인했다.
- Medusa 전이 의존성의 lodash/ajv/qs 및 BullMQ 경유 uuid advisory를 확인했다. 같은 major의 수정 버전으로 overrides를 고정하고 lock을 갱신했다. 자동 major downgrade나 `audit fix --force`는 쓰지 않았다.
- `make`/`uv`가 Ctrl+C를 중복 전달하면 첫 자식 종료 대기 중 정리가 끊겨 Vite가 남았다. 실제 listener·프로세스 그룹과 KeyboardInterrupt traceback으로 재현했다. 정리 구간에서 중복 SIGINT를 무시하도록 수정했고 두 자식 그룹 종료 회귀 검사를 추가했다.
- 종료 직후 LISTEN 프로세스가 없어도 일반 bind가 실패하고 같은 시점의 SO_REUSEADDR bind는 성공하는 TCP 종료 상태를 확인했다. 포트 검사에서 이 상태를 허용하며, 실제 점유 중인 포트는 여전히 실패한다.
- 재설치 검증 중 별도 가상환경 경로를 누락한 명령이 개발 환경의 패키지를 제거한 적이 있다. doctor가 실패를 검출했다. 이후 wrapper는 `.venv` 경로를 고정하고, 격리 검증은 명시적인 별도 환경으로 수행했다. `make setup`으로 복원한 뒤 검증했다.

## 재현 명령

```sh
make setup
make check
make check-browser
make commerce-smoke
```

정상 개발은 `make dev`, 독립 상거래는 `make commerce`다. 실행을 끊은 후 같은 명령으로 다시 시작할 수 있다. 로컬 검증 로그는 `.local/`에 있으며 공개할 원장·성과 기록이 아니다.

## 개발 이후에만 검증할 항목

CW00의 고객/판매자 권한과 실제 주문·지급·fulfillment 계약, CW01~02 세계·원장·실패, CW03 모델 권한·호출·비용, CW04~07 Peer Review·실시간·E2 전이·비교 평가가 남아 있다. 이 항목들을 개발 준비의 통과로 대신하지 않는다. Linux/원격 CI/새 AWS 계정/공개 배포는 미검증이다.

## 최종 실행 기록

- `make setup` 종료 코드 0. `make setup-deps`로 다시 설치한 후 `uv.lock`과 `package-lock.json` SHA-256 일치.
- 별도 새 Python 환경의 프로젝트/Strands/FastAPI import 통과.
- `make smoke-local` 종료 코드 0: ruff·mypy, Python 6개, React production build, 하네스 설치 검사 통과.
- `make check-browser` 종료 코드 0: 브라우저 3개 통과.
- 수정 후 `make dev`와 `make commerce`의 전체 기동·Ctrl+C 종료를 두 차례 확인. API/웹/Medusa/DB 포트 모두 loopback, 종료 후 재사용 가능. 기존 Docker 컨테이너 집합 동일.
- 최종 HTML 데스크톱·모바일 화면 캡처 시각 확인, 인쇄 PDF 렌더링 성공. PDF의 출판용 페이지별 교정은 수행하지 않았다.
- `npm audit --json` 전체 의존성 및 `--omit=dev` 결과 모두 0건.
- 비밀값·빌드·캐시 제외 확인. 커밋·푸시·배포·게시·AWS 호출·실자금 거래 없음.

## 목표 완료 대조

| 사용자 목표에서 도출한 요구 | 최종 근거 | 판정 |
|---|---|---|
| 초안 최종 정리 | HTML v0.3, 상세 계획 v0.2, 현실 전이 설계와 심사/데모 구성 일치 | 완료 |
| 최적화·보관 | 모바일 제목 줄바꿈 조정, 이전 기획 archive 이동, 최신 진입점 통일, Markdown 32개·로컬 파일 링크 35개 오류 0 | 완료 |
| 고정 개발 환경 | 저장소 전용 Python/Node, uv/npm lock 재설치 해시 유지, 새 Python 환경 import | 완료 |
| 개발 실행 기반 | Python health/React 빌드·실제 API 연결, Strands 역할 import | 완료 |
| 독립 상거래 환경 | Medusa backend build·migration·health, 전용 DB/Redis | 완료 |
| 반복 실행과 검사 | Python 6·브라우저 3, 하네스, 기동·종료·재기동·누락/충돌 실패·기존 서비스 보존 | 완료 |
| 개발 인수인계 | README·환경 예시·실행 안내·brief/status/next plan, CW00 시작점 | 완료 |

이 판정은 사용자가 요청한 **실제 개발 전 준비**의 완료다. 제품 개발 CW00~CW09, 모델 권한 확인, 공개·배포·제출은 향후 작업으로 유지한다.
