# Nova 실행 종료와 최종 제출 자료

2026-09-12. 승인된 Nova 2 Lite 구성으로 실제 실행과 비교 평가를 종료했다. **총 3,466호출·기록 모델 비용 $4.191815·미확정 예약 0**이다. 영어 제출 문서와 실제 모델 영상은 로컬에 준비됐고 공개·최종 제출은 아직 수행하지 않았다.

## 실제 결과

- [정상 구매·검토·앞선 두 pilot](nova-live.md): Nova 정상 구매와 동결 정책의 실제 Medusa 실행은 각각 독립 COMPLETE 310. B3 정책 변경·같은 snapshot 재실험은 확인했지만 지출은 전후 430으로 같았다. 실패한 검토도 보존했다.
- [실제 재고 변경](nova-reactive-video.md): Nova/Medusa 실행 세 건 중 COMPLETE 380 두 건, 지급 거절 반복 후 deadline 실패 한 건이다. 성공 사례의 읽기 전용 UI와 독립 export가 일치했다.
- [사전 동결한 새 조건 80칸](nova-prospective.md): B0/B1/B2/B3 목표 완료는 **15/11/8/7(각 20)**, 비용 $2.312011. B0가 가장 많이 완료했다. 조건은 이전 데이터와 중복이 없지만 독립 외부 held-out이 아니며 각 B2/B3 셀에서 새로 학습했다.
- [납품 대기 지시 보강 후 별도 known pilot](nova-delivery-prompt.md): **4/4/3/4(각 5)**, 비용 $0.486377. 가상 시계와 수령 확인 지시 여섯 줄을 보강했고 서버/원장/권한 경계는 유지했다. B2 학습 거절 한 건을 분모와 비용에 포함했다. 보강 전 80칸을 덮어쓰지 않았다.

기본 구매 경로는 단일 Nova 실행이다. B2/B3는 별도 연습·검토 실험이며 비용 대비 우위가 입증되지 않았다. 목표 실패, 모델 출력 오류, 학습 거절, 실제 지급 거절 반복은 모두 보존한다.

[F05 known pilot의 사후 재감사](untrusted-supplier.md)도 추가했다. 같은 악성 설명 조건의 실제 Nova 평가 9건에서 권한 밖 도구/추가 인자 시도 없이 canonical 310·독립 COMPLETE를 확인했다. 세 최종 답변의 예약 금액 표현은 실제 원장 0과 달라 그대로 기록했다. 추가 모델 호출/비용은 0이며, 미공개 공격 방어 또는 Nova+Medusa F05 검증은 아니다.

## 비용

모델은 `global.amazon.nova-2-lite-v1:0`, 요청 리전 `us-west-2`, 프로필 `q-user`다. 승인 총 $10 중 기록 잔여 예산은 $5.808185이며 추가 유료 작업은 실행 중이지 않다. [전체 비용 재계산](../../evidence/cw07-nova-delivery-prompt/campaign-cost-audit.json)은 모든 호출의 원본 usage·보존 공식 단가·캠페인 합계가 일치함을 확인했다.

입력 12,763,557/출력 144,489토큰이며 캐시 read/write는 0이다. $4.191815는 사용량 기반 모델 비용으로, 최종 AWS 청구·세금·다른 AWS 서비스 비용과 대조한 총 청구액은 아니다. 연습 세계의 310/380/430 등은 실제 결제액이 아닌 합성 크레딧이다.

## 영상과 제출 문서

[최종 영어 MP4](../../evidence/cw08-nova-final-video/rehearsal-draft.mp4)는 **225.021초(3:45)**, 1920×1080 H.264/AAC와 내장 자막으로 구성했다. [영어 자막](../../evidence/cw08-nova-final-video/captions.vtt)·[내레이션 원문](../../evidence/cw08-nova-final-video/transcript.md)·[생성 기록](../../evidence/cw08-nova-final-video/report.json)을 함께 보존했다.

실제 Nova/Medusa 연속 녹화와 별도 실패 실행, 보강 전 80칸과 보강 후 20칸을 구분한다. 전체 영상 디코딩과 [Chromium 재생](../../evidence/cw08-nova-final-video/playback-check.json)은 PASS: 8개 seek, 자막 28개, 브라우저 오류 0. 최종 비교 카드와 아키텍처를 렌더해 확인했다. 이는 사람의 내레이션 청취/편집 검수나 공개 접근 검증을 대체하지 않는다. 이전 3:30 및 SDK 영상은 이력으로 보존했다.

[영어 설명](../submission/PROJECT.md), [제출 양식 문안](../submission/FORM.md), [테스트 안내](../submission/TESTING.md), [아키텍처](../submission/architecture.svg), [README](../../README.md)에 최종 결과와 한계를 반영했다. 테스트 안내의 실제 Nova artifact 읽기 명령은 AWS 호출 없이 로컬에서 확인했다.

## 로컬 검증과 소스 패키지

최신 `make check`는 PASS(Python 690, mypy 58, ruff/lock/웹 빌드). [전체 로그](../../evidence/cw09-nova-final/final-submission-gate.log)를 보존했다. 새 실제 실행의 독립 복사본 재감사와 비용 대조는 각 평가 폴더에 있다. 실행 전후 소스를 별도로 보존해 프롬프트 변경 시점을 구분한다.

최종 패키지의 고정 로컬 경로는 `.local/release-candidate-nova-20260912-r2/rehearsal-source.tar.gz`이며, 동일 디렉터리의 `source-manifest.json`·`package-report.json`에 파일별 hash, 압축본 hash, 해제본 대조와 문서 gate 결과를 기록한다. `scripts/dev/source_snapshot.py`로 Git-visible 파일만 복사하고 ignored 런타임/의존성/자격증명은 제외한다. 이 문서와 최종 checkpoint를 포함한 뒤 압축하며 자기 자신을 재귀적으로 포함하지 않도록 패키지 보고서는 ignored 경로에 둔다. [최종 artifact/정리 감사](../../evidence/cw09-nova-final/verification.json)는 보존 증거와 서비스 정리 상태를 기록한다.

패키지 해제본의 문서 검사는 제품 실행이나 독립 기기 재현이 아니다. 기존 같은 호스트 Linux 검사도 독립 호스트 검증으로 확대하지 않는다. 소스/증거 패턴 검사와 알려진 비밀값 대조는 모든 형식의 비밀값을 탐지한다는 보장이 아니다.

## 남은 제출 단계

1. 제출자·팀 이름과 AWS Builder ID를 반영한다. 현재 제공되지 않아 [제출 양식](../submission/FORM.md)에 대기 상태로 남겼다.
2. 준비된 소스를 공개 저장소로 게시하고 최종 영상을 YouTube/Vimeo에 공개한 뒤 접근·링크를 확인한다. 현재 초기 커밋·remote·공개 URL이 없다.
3. 심사자가 무료로 실행/검토할 수 있는 접근 경로와 실제 공개 링크를 교차 확인하고 최종 제출한다. 호스팅 배포는 수행하지 않았다.

사람 관찰 참가자는 0명이며 검증 시간 절감, Peer Review 우위, 독립 held-out 일반화, 미공개 공격 및 Nova+Medusa F05 판단, 분산 경합/다른 일정, 전체 지연 목표는 입증되지 않았다. 제출 자료에는 구현된 기능과 이 한계를 함께 제시한다. 커밋·푸시·게시·최종 제출은 요청된 실행 범위에서 진행하며 이 로컬 패키지 작업은 공개를 수행하지 않는다.
