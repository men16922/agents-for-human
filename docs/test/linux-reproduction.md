# Linux 재현 준비와 오프라인 설치 실패 — 2026-09-09 기록

후속: [2026-09-12 설치·오프라인 전체 검사 통과](linux-reproduction-20260912.md). 아래 실패와 허용 대기는 당시 기록이며, 현재 재현 상태는 후속 문서를 따른다.

2026-09-09. 현재 미커밋 소스의 격리 복사본을 만들고, 로컬에 있던 Linux amd64 이미지에서 의존성 설치를 시도했다. **Linux 전체 재현은 완료하지 못했다.** macOS gate는 통과했지만 Linux 설치는 플랫폼 패키지 캐시 누락으로 실패했다.

## 소스와 실행 범위

[복사 도구](../../scripts/dev/source_snapshot.py)는 Git에 보이는 파일을 새 디렉터리에 복사하고 파일별 SHA-256·크기·실행 권한을 기록한다. `.env`·로컬 DB·런타임·node_modules와 Git 제외 경로를 포함하지 않는다. 강제로 stage한 `.env`, 심볼릭 링크, 상위 경로, 알려진 AWS 키/PEM 개인키 형태를 거절한다. 임의 문자열의 모든 비밀값을 판별하는 도구는 아니므로 실제 공개 전 내용 검토는 별도로 필요하다. 기존 작업 트리를 커밋하거나 수정하지 않는다.

이번 복사본은 `.local/reproduction/linux-20260909/source`의 1,392개 파일·24,298,278바이트다. [소스 명세](../../evidence/cw08-linux-reproduction/source-manifest.json)에 정확한 이름과 hash를 보존했다. 복사 전후 및 컨테이너 검사 후 원본 복사본의 hash가 일치했다. 이후 추가한 Docker 재현 recipe와 문서 변경은 이 최초 복사본에 포함되지 않으므로 다음 실행 전에 새 복사본을 만들어야 한다.

기존 로컬 `node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5`는 Debian 12, Linux x64, Node 22.23.2다. macOS arm64 호스트에서 `--platform linux/amd64`로 실행했다. 다른 사용자의 기기나 원격 CI가 아니다.

컨테이너에 복사본과 저장소 전용 npm 캐시를 읽기 전용으로 제공하고, 내부 `/workspace`와 `/tmp/npm-cache`에 복사해 사용했다. 기존 node_modules·AWS 자격증명·Docker socket·데이터 볼륨을 주입하지 않았다. `--pull=never --network none`을 사용했다.

## 실패 원인과 남은 검사

`npm ci --offline`은 `@esbuild/linux-x64@0.28.2`를 캐시에서 찾지 못해 ENOTCACHED로 실패했다. esbuild의 다운로드 fallback도 네트워크 차단 상태에서 EAI_AGAIN이었다. 의존성을 생략하거나 호스트 설치 경로로 대체해 통과 처리하지 않았다.

| 항목 | 실제 결과 |
|---|---|
| 고정 Node의 Linux 실행 | 22.23.2 / Linux x64 확인 |
| Linux npm 설치 | 실패, exit 1 |
| Linux 웹 빌드 | NOT_RUN |
| Linux Python gate·브라우저·Medusa 빌드 | NOT_RUN |
| 현재 macOS `make check` | Python 391개·mypy 45소스·ruff·lock·웹 빌드 통과 |
| 소스 복사 경계 회귀 | 5개 통과 |

[실패 보고서](../../evidence/cw08-linux-reproduction/output/report.json), [npm 로그](../../evidence/cw08-linux-reproduction/output/npm-ci.log), [호스트 gate](../../evidence/cw08-linux-reproduction/host-gate.log), [artifact/recipe hash](../../evidence/cw08-linux-reproduction/artifact-manifest.json)에 증거를 보존했다. 전용 컨테이너는 종료 상태를 확인한 뒤 제거했고 기존 실행 컨테이너 4개를 보존했다. 사용한 캐시와 소스 원본은 읽기 전용이었다.

Docker 레지스트리/PyPI 연결 확인은 자동 승인 검토에서 “Network access is outside the default unattended loop”로 거절됐다. 대기하던 이 작업 소유의 Docker manifest/credential helper 프로세스도 중단·종료 확인했다. 공개 이미지·런타임·의존성 다운로드/설치 허용을 요청했으며 응답 전에는 네트워크 설치를 진행하지 않는다. 이는 Python/웹 코드가 Linux에서 동작하지 않는다는 증거가 아니라 필요한 의존성이 없는 상태의 설치 실패다.

## 다운로드 허용 후 실행할 절차

[Dockerfile](../../dev/reproduction.Dockerfile)과 [검사 스크립트](../../scripts/dev/reproduction-check.sh)를 준비했다. **아래 전체 빌드/실행은 아직 검증하지 않았다.** 공개 bootstrap 도구·고정 uv/Python/Node·lock 의존성·Chromium과 시스템 라이브러리를 설치하는 빌드 단계 뒤, 네트워크 없는 새 컨테이너에서 gate·브라우저·SDK fixture·Medusa 빌드를 실행한다. 자체 하네스 플러그인을 vendoring하지 않으며 `make smoke-local`/야간 실행은 범위에 넣지 않는다. 제품 `make check`에는 하네스 설치가 필요하지 않다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python scripts/dev/source_snapshot.py .local/reproduction/linux-approved
# Downloads and installation: run after explicit permission.
docker build --platform linux/amd64 -f dev/reproduction.Dockerfile -t rehearsal-dev-reproduction:linux .local/reproduction/linux-approved/source
# Fresh test execution, not a cached build layer. No host credentials or services.
docker run --name rehearsal-dev-linux-check --label com.docker.compose.project=rehearsal-dev --platform linux/amd64 --network none --shm-size=1g rehearsal-dev-reproduction:linux > .local/reproduction/linux-approved/linux-check.log 2>&1
docker inspect rehearsal-dev-linux-check --format '{{.State.Status}} {{.State.ExitCode}}'
```

종료 코드와 원본 로그를 확인하고 생성된 `.local` 증거를 보존한 뒤 이 실행이 만든 컨테이너만 제거한다. 실패하면 중간 결과도 보존한다. 이 재현 절차에는 Medusa DB/실제 HTTP 거래·실제 모델 호출·독립 참가자 관찰·공개/제출이 포함되지 않는다.
