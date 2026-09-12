# 프로젝트 완료 재개 — 2026-09-12

현재 모델 실행은 [Nova 2 Lite 승인/실제 실행 계획](2026-09-12-nova-live.md)을 따른다. 아래 Sonnet $20 제안의 응답 대기는 이후 Nova 총 $10 승인으로 대체됐다. 과거 준비 기록을 실제 실행 결과와 혼동하지 않는다.

사용자는 프로젝트 완료까지 자율 진행하되 AWS 배포 등 비용이 발생할 수 있는 작업만 질문하도록 요청했다. 무료 공개 의존성 다운로드와 저장소 격리 설치는 이 요청 범위에서 진행한다. 이전 Linux 설치 허용 대기는 해소됐다. 유료 모델 호출은 별도 비용 응답 전까지 실행하지 않는다.

## 실행 순서

1. 완료: [Linux 동일 호스트 컨테이너 재현](../test/linux-reproduction-20260912.md). 새 소스 복사본의 의존성 설치 후 네트워크 없는 새 컨테이너에서 전체 스크립트가 통과했다(Python 663·mypy 57·브라우저 25·SDK/80칸 배치·Medusa 컴파일). 최초 실패도 보존하며 기존 컨테이너·볼륨은 변경하지 않는다. 같은 macOS 호스트의 Linux 컨테이너 증거를 독립 사용자/원격 CI 증거로 부르지 않는다.
2. 모델 비용 응답 후 CW03 정상 구매 → CW04 실제 검토/재실험 → 동결 외부 실행 → 알려진 pilot → 동결된 새 조건 평가 순서로 진행한다. 실제 결과가 실패여도 전체 분모와 비용에 포함한다.
3. 현재 실제 결과로 제출 자료·영상·재현 절차를 갱신하고 공개 후보 파일을 검수한다. 개발자 관찰과 사람의 영상 검수는 실제 참여 기록이 있어야 완료한다.
4. 공개 저장소/영상과 심사용 실행 경로·Builder ID 등 제출 필드를 갖추고 공식 요구와 대조한다. 계정 입력이 필요한 항목은 준비 가능한 내용을 먼저 완성한다. 비용이 발생하는 호스팅은 별도 확인한다.

## 유료 실행 제안 — 응답 대기

[로컬 소스 패키지/완료 조건 감사](../test/release-candidate.md)까지 마쳤다. 2,605개 소스의 압축/해제 해시·권한과 문서 gate를 확인했다. 이 후보는 감사 문서와 최종 모델 결과 이전 상태다. 비용 응답 없이는 다음 필수 CW03 실제 실행을 진행할 수 없으며, 기존 fixture 검사를 추가하는 것으로 실제 모델 완료 조건을 대신하지 않는다.

비용 대기 중 [practice 배치 토큰·실행 시간 보고서](../test/evaluation-metrics.md)를 추가했다. `python -m rehearsal.evaluation.metrics <batch-directory>`는 원본 사용량과 새 단조 시계 표본을 읽기 전용으로 집계한다. 실제 모델 pilot은 여전히 미실행이다.

무료 심사 실행 경로는 [직접 관측 시연](../test/demo-inspection.md)으로 보강했다. `make commerce` 뒤 `make commerce-demo`는 실제 SDK/Medusa 검증 후 화면을 유지한다. 별도 브라우저 재접속과 Ctrl+C 후 독립 export/정리까지 확인했다. 공개 접근·사람의 설치/관찰을 수행한 것은 아니다.

- 프로필 `q-user`, 요청 리전 `us-west-2`, 모델 `us.anthropic.claude-sonnet-4-6`.
- 읽기 전용 Bedrock `GetInferenceProfile`에서 `ACTIVE` 확인. 모델 호출 권한/실제 추론 성공을 뜻하지 않는다.
- Standard 미국 리전 간 추론, USD/100만 토큰: 입력 3.30, 출력 16.50, cache read 0.33, 5분 cache write 4.125. 현재 실행자는 명시적 prompt cache를 설정하지 않는다.
- [Anthropic 공식 가격표, 2026-05-27, 5쪽](https://www-cdn.anthropic.com/files/4zrzovbb/website/3684c2faafb97418665782cea0001f439f74b1d2.pdf#page=5), [AWS 모델 ID/리전](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html)을 2026-09-12 확인했다.
- 첫 정상 구매는 실행 예산 $1, 최대 20회 호출·30회 도구·100,000토큰·180초. `.local/model-proposal/sonnet46.env`에 비활성 후보 설정을 두었으며 `make agent-preflight` PASS. 유료 호출 0회.
- 총 $20 제안: 누적 기록 비용과 미확정 예약·다음 실행 예약을 함께 계산해 $18 이내에서 admission한다. 다른 단계의 원장을 중복 계산하지 않고 학습/평가를 모두 포함한다. 미확정 usage는 비용이 0이라는 뜻이 아니며 다음 유료 실행을 막는다. 원장 비용 한도는 추정치로 실제 AWS 청구 절대 상한이 아니다.
- 사용자 응답 없이 모델을 실행하거나 임의의 예산을 승인 상태로 바꾸지 않는다.

## 제출 일정

[공식 규칙](https://agentsforhumans.devpost.com/rules)을 2026-09-12 다시 확인했다. 마감은 2026-09-14 17:00 PDT / 2026-09-15 09:00 KST. 공개 코드·MIT/Apache·README·아키텍처·5분 이하 공개 YouTube/Vimeo 영상·Builder ID·무료 심사 접근이 필요하다. AgentCore와 호스팅은 선택이다.
