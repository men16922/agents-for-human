# 로컬 소스 패키지와 잔여 완료 조건

> 이 문서는 실제 Nova 실행 전의 보존 기록이다. 현재 비용/모델/제출 상태는 [최종 Nova 제출 감사](nova-final-submission.md)를 따른다. 아래 비용 응답 대기는 이미 해소됐다.

2026-09-12. 공개 전 소스 후보를 압축하고, 해제한 파일의 무결성과 문서 검사를 확인했다. **프로젝트 전체는 미완료이며 다음 필수 실행은 비용 응답 후 CW03 실제 모델 정상 구매다.** 이 검사는 모델 호출·공개·배포를 포함하지 않는다.

## 패키지 검증

- Git에 보이는 소스 2,605개, 66,813,488바이트를 격리 복사했다. ignored 환경·의존성·실행 자격증명은 제외했다. 보존 증거의 fixture SQLite 16개는 포함했다.
- 로컬 압축본: `.local/release-candidate-20260912/rehearsal-source.tar.gz`, 25,109,839바이트. SHA-256: `f47bdb074c55dd30db6ed34d88024cc4d1b7939faf3be1693892f5c46658913e`.
- 압축 해제 후 전체 파일 집합·해시·실행 권한이 일치했다. 심볼릭 링크·특수 파일은 없다. 이번 checkpoint 직전 현재 소스와도 2,605개 해시가 일치했다.
- 해제본에서 `python3 scripts/check.py` PASS. 의존성을 포함하지 않았으므로 해제본의 제품/runtime gate는 NOT_RUN이다. 기존 macOS Python 682·mypy 58 및 Linux 검증 결과를 이번 패키지의 신규 실행으로 취급하지 않는다.
- 알려진 로컬 자격증명 파일 179개에서 수집한 비밀값과 환경값 총 448개를 토큰 패턴으로 대조해 일치 0개를 확인했다. 별도 credential 필드 검사에서는 `[REDACTED]` 672개, 런타임 `Bearer ` 접두사 22개, 테스트 Authorization 문자열 3개를 분류했고 미분류 항목은 없었다. 패턴 검사는 임의 형식의 모든 비밀값을 찾아낸다는 보장이 아니다.
- [MIT](../../LICENSE)·[의존성/생성 이미지 고지](../../THIRD_PARTY_NOTICES.md)가 포함됐다. 이 검사를 법률 검토나 모든 배포 권리의 보증으로 표현하지 않는다.

[패키지 보고서](../../evidence/cw09-release-candidate/package-report.json), [소스 명세](../../evidence/cw09-release-candidate/source-manifest.json), [재검증](../../evidence/cw09-release-candidate/verification.json), [artifact 해시](../../evidence/cw09-release-candidate/artifact-manifest.json)를 보존했다. 압축본은 이번 감사 문서/checkpoint와 향후 실제 모델 결과를 포함하지 않는다. 최종 공개 시 새 후보를 만들고 변경분을 다시 검사해야 한다.

## 완료 조건 대조

현재 [우선순위 계획](../NEXT_PLAN.md), [CW 완료 조건](../plans/2026-09-06-custom-world-poc-plan.md), [제출 목록](../submission/READINESS.md)을 대조했다. 아래 기존 실행 근거는 연결된 보존 기록이며 이번에 전체 제품 실행을 반복한 것은 아니다.

| 범위 | 현재 증거와 판정 | 남은 필수 증거 |
|---|---|---|
| CW00~02 | [Medusa 계약](medusa-contract.md)·[세계/독립 판정](world-foundation.md)의 로컬 구현 검증 완료 | 이후 실제 모델 결과에도 독립 판정을 적용 |
| CW03 | 후보/preflight 준비, 실제 모델 0회 | 비용 응답 후 정상 목표 완료·원본 usage·비용 |
| CW04 | [B3 SDK 연결](b3-shared-accounting.md)은 알려진 fixture | 실제 검토·반례→정책 diff→동일 snapshot 재실험·새 조건 평가 |
| CW05 | [동결 네 방식](frozen-reaction-comparison.md)의 SDK/실제 Medusa 계약 검증 | 실제 모델 정책 전이·F05 판단. 분산 경합으로 주장 범위를 확대하지 않음 |
| CW06 | 실제 관측/복구·[변경→화면 시간](source-latency.md)·SDK 재판단 검증 | 실제 모델 재계획·전체 지연 목표 증거 |
| CW07 | [원래 pilot](shared-limits-and-pilot.md) 모델 15칸 NOT_RUN, 별도 known SDK 배치·[지표 CLI](evaluation-metrics.md) 준비 | 실제 모델 pilot·동결 미공개 평가·전체 비용/실패 분모·개발자 관찰(현재 0명) |
| CW08 | [같은 호스트 Linux](linux-reproduction-20260912.md)·[직접 시연](demo-inspection.md)·[4:45 영상 초안](submission-video.md) | 독립 호스트·사람의 영상/음성 검수·최종 모델 결과 반영 |
| CW09 | 이번 로컬 소스 패키지·영어 자료. Git 커밋/remote 없음 | 공개 코드/영상·심사 접근 확인·Builder ID·최종 제출 |

## 재개 조건

[완료 계획](../plans/2026-09-12-completion.md)의 첫 $1/총 $20 모델 비용 제안에는 아직 응답이 없다. 이 조건은 Linux 재현·평가 지표·직접 시연·소스 패키지 준비를 진행하는 동안 계속 유지됐다. 필수 실제 모델 경로를 SDK fixture로 대체해 완료 처리하지 않는다. 비용 응답이 오면 CW03 → CW04 → 동결 외부 실행 → pilot 순서로 재개한다.

공개 자료는 최종 결과를 반영해야 하며, 실제 참가자 관찰·독립 기기·영상 사람 검수·제출자 계정 정보도 자동 검사로 대신할 수 없다. 커밋·푸시·AWS 배포·게시·제출은 이번에 수행하지 않았다.
