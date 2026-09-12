# Linux 오프라인 재현 — 빌드 설정 수정 후 통과

2026-09-12. 무료 다운로드·설치를 포함한 자율 진행 요청에 따라 이전 Linux 설치 대기를 해소했다. **같은 macOS arm64 호스트의 Linux amd64 컨테이너에서 전체 재현 스크립트가 exit 0으로 완료됐다.** 별도 사용자/기기, 원격 CI, Linux Medusa DB/HTTP 거래 검증은 아니다.

## 환경과 보존 범위

- Git에 보이는 현재 파일 2,551개를 `.local/reproduction/linux-20260912/source`에 격리 복사했다. 원본 복사본 전체 해시가 설치/실행 후에도 일치했다.
- 고정 Node 이미지에서 공개 apt/PyPI/Node/npm/Chromium 의존성을 설치했다. 저장소 고정 Python 3.12.13·Node 22.23.2·uv 0.11.23과 lock을 사용했다. 이전 `esbuild/linux-x64` 캐시 누락은 네트워크 설치로 해소됐다.
- 검사 컨테이너 세 개 모두 `network=none`, host mount 없음, AWS/모델 설정 주입 없음이었다. 최초 전체 검사·원인 확인용 빌드·수정 후 전체 검사를 별도 컨테이너로 실행했다.
- 이미지 `rehearsal-dev-reproduction:linux-20260912`, digest와 세 컨테이너의 시작/종료/exit는 [보고서](../../evidence/cw08-linux-reproduction-20260912/report.json)에 있다.
- 수정 후 검사는 최초 설치 이미지로 만든 새 컨테이너에 **수정한 재현 스크립트 한 파일만** `docker cp`한 뒤 실행했다. 의존성을 재설치하거나 실패한 컨테이너를 재사용하지 않았다. 테스트한 파일 해시는 현재 스크립트와 일치했다. 최초 이미지 자체에는 수정 전 스크립트가 있으므로 그대로 실행하면 이전 실패가 재현된다. 새 전체 빌드는 아래 현재 소스 절차를 사용한다.

## 실패 → 원인 확인 → 수정

최초 전체 실행은 문서·Python 663개·mypy 57소스·웹·브라우저 25개·B2/B3·동결 평가·80칸 배치까지 통과한 뒤 Medusa build에서 실패했다. 오류는 `Missing DATABASE_URL`이었다. Medusa 설정은 컴파일 때에도 네 환경값을 요구하지만 준비한 재현 스크립트가 이를 제공하지 않았다.

같은 이미지의 새 컨테이너에서 DB/Redis 주소를 `127.0.0.1:1`로, JWT/cookie를 명시적인 build-only 문자열로 제공하는 단일 실험을 수행했다. 네트워크 차단 상태에서 빌드가 exit 0, backend compilation 5.49초로 완료됐다. DB나 실제 비밀값이 필요한 단계가 아니라 구성값 검증에서 막힌 것임을 확인했다.

[재현 스크립트](../../scripts/dev/reproduction-check.sh)의 Medusa 컴파일 명령에만 같은 임시 환경을 추가했다. 운영 `medusa-config.ts`의 필수 설정 검사는 변경하지 않았다. 새 컨테이너에서 전체 스크립트를 다시 실행했고 마지막 Medusa compilation도 4.77초, 전체 exit 0으로 통과했다.

## 최종 결과

| 검사 | 결과 |
|---|---|
| `make check` | PASS: 문서·런타임/import·lock·ruff·mypy 57·Python 663·웹 빌드 |
| `make check-browser` | PASS: 25개, 58.8초 |
| `make b2-smoke`, `make b3-smoke` | PASS: SDK fixture, 후보 미승격 유지 |
| `make frozen-evaluation-smoke` | PASS: 네 방식 EVALUATED |
| `make evaluation-batch-smoke` | PASS: 80/80 EVALUATED; 호스트에서 원본 해시·계약·독립 export·usage 재판정 일치 |
| `npm run medusa:build` | PASS: backend compilation; DB/거래 실행 없음 |

배치 원장은 가상 49,560 micro-USD, 미확정 예약 0이다. 실제 요금이나 모델 효과가 아니다. [호스트 재감사 결과](../../evidence/cw08-linux-reproduction-20260912/batch-reaudit.json)를 별도 보존했다. 원시 출력 1,504개는 ignored `.local/reproduction/linux-20260912/container-local-fixed/`에 유지하고 [파일 해시 명세](../../evidence/cw08-linux-reproduction-20260912/raw-output-manifest.json)를 보존했다. 공개 증거 폴더에는 최초 실패·원인 확인·최종 실행 로그, 소스 명세와 실제 테스트한 스크립트가 있다. 이 검사에서 새 실제 모델 호출은 0회다.

세 검사 컨테이너는 종료 상태와 소유 label을 대조한 뒤 제거했다. 기존 실행 컨테이너 4개와 데이터 볼륨은 보존했으며 재현 이미지는 남겼다. [정리 확인](../../evidence/cw08-linux-reproduction-20260912/cleanup.json).

## 현재 소스로 다시 실행

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python scripts/dev/source_snapshot.py .local/reproduction/linux-fresh
docker build --platform linux/amd64 -f dev/reproduction.Dockerfile -t rehearsal-dev-reproduction:fresh .local/reproduction/linux-fresh/source
docker run --name rehearsal-dev-linux-fresh --label com.docker.compose.project=rehearsal-dev --platform linux/amd64 --network none --shm-size=1g rehearsal-dev-reproduction:fresh
docker inspect rehearsal-dev-linux-fresh --format '{{.State.Status}} {{.State.ExitCode}}'
```

빌드 단계에는 공개 다운로드가 필요하다. 마지막 실행은 오프라인이며 실제 모델/클라우드/Medusa DB를 기동하지 않는다. 새 소스 명세와 종료 코드·원시 로그를 남기고, 자신이 만든 컨테이너만 종료/제거한다. 원시 출력 없이 이전 성공 문자열만으로 새 재현을 통과 처리하지 않는다.
