# Progress Log

이전 기록: [2026-09 보관본](archive/progress-2026-09.md).

## 2026-09-12 — 초기 Git 커밋과 push 정책 차단

- Changed: 현재 소스/증거/제출 자료 5,706개를 명시적으로 stage하고 ad64fa9 커밋. 영상 transcript를 현재 preflight 영상과 일치시켰다. [상세](test/git-publication.md).
- Verified: 공개 origin은 빈 저장소, 파일 크기/제외 경로·비밀값 검사·문서 gate·원본 증거 제외 whitespace 검사 완료.
- Blockers/Next: 사용자 요청 push는 overnight 실행 정책이 프로세스 생성을 거절했고 원격 main은 여전히 없다. 수동 push 후 SHA/익명 접근 확인. 규칙 우회·영상 게시·Devpost Submit 없음.

## 2026-09-12 — 실행 전에 영향을 측정하는 preflight 완성

- Status/Changed: 사용자 요청을 소비자 목표→Nova 계획→12개 격리 실행→영향 보고서→별도 결정/export로 구현. 새 preview IAM/runtime/workflow·영어 UI·공식 AWS draw.io·2:53 Daniel 영상/28자막·영어 제출 자료 갱신. [상세](test/preflight-impact.md).
- Verified: `make check` 740 tests/mypy 75, browser 28 PASS. 실제 Nova 초기 A→독립 B 권장; 12칸 재감사·거래 DB 0행·권한 8검사·workflow SUCCEEDED·Runtime 404·Chrome accept/export/reload. 추가 7호출/$0.006197·누계 3,626/$4.380601·cloud 잔여 $3.838425·예약/active 0. 영상 decode/8 seek/음량·draw.io 2페이지/공개 hash 대조.
- Blockers/Next: 요청한 POC 범위 완료, 자동 다음 실행 없음. 실결제/Amazon·실세계 예측·사용자 효과는 미검증. 공개 코드/영상·제출자/Builder ID는 다음 별도 단계이며 commit/push·YouTube 업로드·Devpost Submit 없음. 이전 영상/아키텍처·비교 증거는 보존했다.

## 2026-09-12 — AWS 공식 아이콘과 Chrome 직접 시연 영상

- Changed: 공식 AWS 아이콘 11개·편집 가능한 draw.io 2페이지·공개 SVG/PNG 갱신. 실제 visible Chrome에서 B3 선택/실행/원장/새로고침 재녹화, 2:30 영어 Daniel 영상·24자막·썸네일·제출 문서 갱신.
- Verified: B3 COMPLETE 380·9개 수령·NO_CHANGE, S3 독립 재판정·workflow SUCCEEDED·Runtime 404. 추가 23호출/$0.023002·예약 0, 누계 3,619호출/$4.374404. 영상 전체 decode·8 seek·−16.06 LUFS·최종 패널 검수, draw.io 두 페이지·공개 3파일 hash·관련 lint/docs PASS. [상세](test/chrome-demo-v2.md).
- Next: 최종 MP4 사람 검수와 요청 범위의 코드/영상 게시·제출자/Builder ID·제출. 이전 영상/증거 보존. Git commit/push·YouTube 업로드·Devpost Submit 없음.

## 2026-09-12 — AWS 서버리스 배포와 draw.io/영어 제출 영상

- Changed: S3/CloudFront 영어 실험 UI, HTTP API/Lambda admission, AgentCore Strands/Nova, DynamoDB 거래/journal, 독립 Step Functions seller와 종료 verifier 배포. 기존 Medusa 증거 보존. 편집 가능한 draw.io 2페이지·3:34 Daniel 영상·26자막·Devpost 초안 갱신.
- Verified: 실제 AWS 거래 8건 COMPLETE·워크플로 SUCCEEDED·세션 8개 404/종료 확인, S3 export 재검증·DynamoDB 경합/중복/예약·종료 이후 늦은 쓰기·시작 실패 cleanup·IAM·공개 API/브라우저 통과. Nova 112호출/$0.132376·예약 0, 누적 3,596호출/$4.351402. 전체 MP4 decode·Chromium 재생/8 seek·draw.io 두 페이지 열기 확인. [상세](test/serverless-deployment.md).
- Verified: 최종 `make check` PASS(Python 715·mypy 68), 기존 로컬 브라우저 25개 PASS. 다른 컨테이너·기존 50개 볼륨 보존, 개발 포트 종료, 게시 후보/패키지에서 실 API secret 노출 0.
- Next: 승인된 배포·영상·draw.io 작업은 완료했다. 공개 demo는 배포되었고 GitHub commit/push·YouTube 게시·Devpost Submit은 하지 않았다. 모델 효과나 과거 benchmark 향상을 주장하지 않는다.

## 2026-09-12 — 영어 YouTube 제출 영상과 불필요한 복사본 정리

- Changed: 영어 UI 실제 재녹화·Daniel 내레이션·3:58/32자막·썸네일/제목/설명 제작, 제출 문서 링크 갱신. 중복 복사본/임시 환경/렌더 중간 파일 32,997개·998,731,629바이트 삭제, 원본/실패/보존 압축본 유지.
- Verified: 새 실제 Nova 18호출/$0.027211·독립 COMPLETE 380, 복사본 재감사 PASS. 누적 3,484호출/$4.219026·예약 0. ElevenLabs 7요청/2,746자/1,511크레딧. 전체 디코딩·Chromium 8 seek/32자막·`make check` PASS(Python 690·mypy 58). [상세](test/youtube-submission.md).
- Next: 공개 코드/영상 URL·제출자/Builder ID·공개 접근. 업로드·Devpost Submit·커밋/푸시는 수행하지 않았다. 이전 r2 소스 후보는 이번 변경 전이다.

## 2026-09-12 — 영어 대시보드와 ElevenLabs 기술 설명 샘플

- Changed: 사용자 정정에 따라 UI/접근성/상태·오류 문구를 영어로 변경하고 기존 브라우저 검증·캡처 선택자 갱신. `.env`의 ELVENLAB_ACTOR를 Daniel로 교체하고 API 키/다른 설정 유지.
- Verified: `make check` PASS(Python 690·mypy 58), 브라우저 25 PASS·1440/390/320 화면. 실제 TTS 1요청·444자·34.458초 MP3·응답 비용 244크레딧, 전체 디코딩/Chromium 재생·seek PASS. [상세/샘플](test/english-dashboard-voice.md).
- Next: 샘플 청취 후 최종 영어 화면/내레이션·소스 패키지 갱신. 이전 영상/패키지는 보존. Nova 추가 호출 0·공개/커밋/푸시 없음.

## 2026-09-12 — 보존 Nova F05 실제 행동 재감사

- Changed: 알려진 공급처 공격 조건의 기존 실제 평가 9개를 읽기 전용으로 대조하고 F05 검증 범위를 교정했다. 최종 소스 후보 r2에 반영한다.
- Verified: 두 설명 원문/hash·도구 응답 노출, 등록 도구/인자만 호출, raw DB/export 모두 COMPLETE 310·원래 예산/수신처·예약 0. 57개 입력 hash 보존. 최종 답변 3건의 예약 표현 부정확성도 남겼다. [상세](test/untrusted-supplier.md).
- Next: 공개 승인·제출자/Builder ID·영상 게시/접근 확인·최종 제출. 같은 공격 조건의 반복이며 일반 방어/Nova+Medusa F05는 미검증. 추가 모델 호출/비용 0·누적 $4.191815. 커밋·푸시·공개 없음.

## 2026-09-12 — Nova 평가 종료와 최종 제출 자료

- Changed: 새 조건 80칸을 보존하고 납품 대기 지시 여섯 줄 보강 후 별도 known pilot 20칸 검증. 최종 3:45 실제 Nova 영어 영상·28자막과 제출 문서 갱신.
- Verified: B0/B1/B2/B3 15/11/8/7(각 20), 보강 후 4/4/3/4(각 5). 누적 3,466호출/$4.191815·예약 0, 복사본 독립 재감사·단가 재계산 일치. `make check` PASS(Python 690·mypy 58), 영상 전체 디코딩/Chromium 재생 PASS. [최종 감사](test/nova-final-submission.md).
- Next: 최종 소스 패키지 확인 후 제출자/Builder ID·공개 코드/영상·접근 확인·최종 제출. 독립 held-out·사람 관찰·독립 호스트는 미검증. 유료 작업 실행 중 아님. 커밋·푸시·공개 없음.

## 2026-09-12 — 실제 Nova 재계획과 3:30 영어 영상

- Changed: 실제 재고 변경 3건·Nova/UI 연속 녹화, 성공/실패와 실제 비교를 반영한 영어 영상·자막·재현 생성기.
- Verified: COMPLETE 380 두 건·deadline 실패 한 건, 누적 1,140호출/$1.393427/예약 0. 독립 복사본 판정·690 Python/mypy 58 gate·MP4 전체 디코딩/재생/26자막 PASS. [상세](test/nova-reactive-video.md).
- Next: 미공개 평가·실패 일정 개선 비교·최종 소스 패키지/공개 제출 준비. 사람 검수·관찰·독립 기기·공개는 남았다. 커밋/푸시 없음.

## 2026-09-12 — 승인된 Nova 실제 구매·Medusa·두 pilot

- Changed: Nova 2 Lite 글로벌/총 $10 승인 실행. 실제 응답의 JSON fence·B2 keep 인용 결함을 재현·수정하고 provider 종료 사유를 보존.
- Verified: 정상/Medusa COMPLETE 310, 두 20칸 pilot·수정 후 B0/B1/B2/B3 4/3/3/4. 전체 1,069호출·$1.275584·예약 0, 48원장 대조. `make check` PASS(Python 690·mypy 58), 회귀 128개. [증거/비용/한계](test/nova-live.md).
- Next: 실제 모델 미완료 종료·이벤트 재계획, 미공개 평가·실제 모델 영상·공개 제출. Peer Review 우위·최종 AWS 청구는 미검증. 기존 서비스/볼륨 보존, 커밋·푸시·게시 없음.

## 2026-09-12 — 로컬 소스 패키지와 완료 조건 대조

- Changed: Git-visible 소스 2,605개를 로컬 압축·해제하고 [패키지 감사](test/release-candidate.md)와 6개 보존 artifact/hash를 기록. STATUS의 오래된 모델 설정 누락 설명을 비용 응답 대기로 교정.
- Verified: 66,813,488바이트/압축 25,109,839바이트, 원본·복사본·해제본 전체 hash/실행 권한 일치. 해제본 문서 gate PASS. 알려진 비밀값 448개 대조 일치 0·credential 필드 미분류 0. 이번 제품 gate/실제 모델은 미실행.
- Blockers: 첫 $1/총 $20 유료 모델 비용 응답이 계속 없어 CW03~07 실제 모델 경로는 미완료. 독립 기기·관찰 참가자·사람의 영상 검수·공개/제출도 남았다.
- Next: 비용 응답 후 CW03 정상 실제 구매부터 재개. 압축본은 이번 checkpoint 전 후보이므로 최종 공개 전 다시 생성/검수. 커밋·푸시·배포·게시 없음.

## 2026-09-12 — 무료 거래 시연의 직접 관측 창

- Changed: `make commerce-demo` / `--inspect [SECONDS]`로 자동 검증 뒤 실제 API/웹/gateway/seller를 유지. Ctrl+C 후 독립 export·소유 프로세스 정리, child/worker 실패는 FAILED로 남김. [상세](test/demo-inspection.md).
- Verified: `make check` PASS(Python 682·mypy 58), 회귀 7개. 실제 Medusa B COMPLETE 380·SDK 9호출/180토큰/가상 252 micro-USD. 별도 1440/390 브라우저 접속·재로드·독립 판정, 실제 화면 확인. 관측 39.44초 후 SIGINT·세션 STOPPED/정리 오류 0·복사본 독립 재검증.
- Boundaries: make 터미널 종료 코드 1(SIGINT)은 거래 판정과 별도 기록. 포트 6개·기존 컨테이너 4개/볼륨 50개 보존, 67소스 hash·실제 토큰 미포함 확인. 실제 모델 0회·사람 참가자 0명, 공개/독립 호스트 검증 아님.
- Next: 비용 응답 후 CW03 정상 실제 호출. 영어 사용 절차·README·진입 문서 반영. 커밋·푸시·배포 없음.

## 2026-09-12 — Pilot용 토큰·실행 시간 비교 보고서

- Changed: practice 배치 셀의 단조 시계 시간/hash·원본 토큰 재합산·읽기 전용 JSON/Markdown 비교 CLI. 미실행/중단/불완전 usage/손상/과거 기록의 분모와 unavailable 유지. [상세](test/evaluation-metrics.md).
- Verified: `make check` PASS(Python 675·mypy 58), 전용 12개+배치 18개 회귀. 새 80칸 SDK 원본/시간/토큰 재계산·58소스/1,463파일 hash; 과거 Linux 80칸의 시간 미상·bytes 보존 확인. 새 실행은 gate 동시 진행이므로 성능 비교에 사용하지 않는다.
- Next: 비용 응답 후 CW03 정상 실제 호출→pilot. 실제 유료 호출 0회, 이번 Linux/브라우저/Medusa 재실행 없음. 원래 pilot의 모델 셀·미공개 평가·개발자 관찰은 미완료다.

## 2026-09-12 — Linux 재현 완료와 유료 모델 실행 준비

- Changed: 무료 설치 허용 범위를 확인하고 격리 Linux 재현 수행. Medusa 컴파일 환경값 누락을 재현 스크립트의 build-only 설정으로 수정. 운영 설정 검사는 유지. [상세](test/linux-reproduction-20260912.md).
- Verified: 최초 실패→동일 이미지 환경값만 제공한 빌드 PASS→새 컨테이너 전체 exit 0. Python 663·mypy 57·브라우저 25·B2/B3/동결/80칸 SDK 배치·Medusa 빌드 PASS. network none·mount 없음. 원시 출력 1,504개·소스 복사본 해시·80칸 독립 재감사/가상 비용 49,560·예약 0 확인.
- Prepared: Sonnet 4.6/q-user/us-west-2 읽기 전용 ACTIVE·공식 네 단가 확인·`make agent-preflight` PASS. 첫 $1/총 $20 비용 제안 응답 대기, 실제 유료 호출 0회. 공식 마감/제출 요건 재확인.
- Next: [완료 재개 계획](plans/2026-09-12-completion.md)의 비용 응답 확인 후 CW03 정상 호출. 독립 호스트·실제 모델/미공개 평가·관찰·사람의 영상 검수·공개/제출은 미완료. 커밋·푸시·배포 없음.

## 2026-09-09 — 지연 시작점 감사와 실제 재고 변경 계측

- Changed: `commerce-latency-smoke`·20개 사전 명부·실제 재고 변경 구간·DOM 첫 반영/두 프레임·영속 journal 대조. [상세](test/source-latency.md).
- Verified: 기존 24표본/반영 22건 재계산·시계 19건과 정확 발생 시각 부재 확인. 실제 20건×2 모두 반영·POST/재고/버전/cursor/범위/분위수 독립 대조. 첫 gate 동시 실행은 별도 보존; gate 종료 후 p95 하한~상한 1,275~1,316ms(로컬 시계 전제·외부 조회 대기 포함). Gate/Evidence: `make check` PASS(Python 663·mypy 57), Node 문법/실제 브라우저 2실행 PASS. 18개 artifact·16소스 hash·알려진 토큰 미포함·포트 6개/기존 컨테이너 4개/볼륨 2개 보존. 내부 이벤트 지연 목표 달성으로 승격하지 않았다.
- Next: 모델 설정 제공 후 CW03 실제 정상 호출/pilot, Linux 설치 허용 후 재현. 실제 모델/관찰·영상 사람 검수·공개/제출 미완료. 모델·AWS·설치·커밋·푸시 없음.

## 2026-09-09 — 완료 조건과 배포 후보 파일 감사

- Changed: CW03~CW09 완료 조건/증거/재개 조건 표와 새 로컬 소스 명세. [상세](test/readiness-audit.md).
- Verified: 5개 manifest의 artifact 250개 hash·영어 상대 링크 51개·복사본 2,526개/62,695,642바이트 hash 일치. 영상 현재 제작 소스 일치. 원래 pilot 4 COMPLETE/1 INCOMPLETE/15 NOT_RUN·B3 후보 미승격·known 명부 확인.
- Blockers: `make agent-preflight` exit 2(모델 ID/예산/네 단가/출처 누락). Linux 설치·실제 모델/관찰·사람의 영상 검수·공개/제출은 미완료. 제품 gate/모델/Medusa/설치/게시를 새로 실행하지 않았다.
- Next: CW06 지연 목표의 내부 이벤트 시작 시각과 원시 표본 분모/제외 대조. 모델 설정 제공 시 CW03 우선. `make check-docs` PASS.

## 2026-09-09 — 실제 UI 녹화와 4:45 영어 영상 초안

- Changed: 선택 녹화 모드·`commerce-reaction-video`·로컬 카드/내레이션/자막/MP4 제작·재생 검수 도구. 첫 full-page 축소/두 번째 판정 위치를 교정하고 초기 원본/검수 사유 보존.
- Verified: 최종 `cw00-5b4262f60244-buyer` 실제 COMPLETE 380·4판단/1차단·SDK 9호출/180토큰/가상 252 micro-USD. 원속도 영상+별도 보존 결과 카드·285.021초 1080p H.264/AAC/영어 자막 33개·전체 디코딩/Chromium 재생/8개 seek·최종 판정 프레임 확인.
- Gate/Evidence: `make check` PASS(Python 663·mypy 57), 이후 최종 카메라 위치는 실제 녹화/Node 문법으로 검사. 73개 artifact·영상 hash·복사본 두 attestation/실행 요약·실제 비밀값/포트 6개/기존 컨테이너 4개/볼륨 2개 확인. [상세](test/submission-video.md).
- Next: 잔여 요구/증거 감사. 사람의 전체 음성/영상 검수·실제 모델/미공개 평가·독립 재현·공개/제출은 남았다. 다운로드/설치·AWS·커밋·푸시·게시 없음.

## 2026-09-09 — 영어 제출 초안과 현재 구현/증거 대조

- Changed: README·영어 PROJECT/TESTING/ARCHITECTURE/VIDEO_SCRIPT/READINESS·SVG. 원래 pilot의 미실행 셀과 별도 네 방식 SDK 명부 구별, 공통 원장/반응 UI/두 판정·재현/영상 출처와 한계 반영.
- Verified: 실제 UI 38개/네 방식 119개 artifact hash·수치·CLI 대조, 영어 링크 47개/Make target 19개 확인, `make check-docs` PASS. SVG 43개 텍스트 경계/동일 소스 HTML 인라인 Chromium 렌더 확인; 직접 SVG 캡처 timeout은 별도 기록. [상세](test/submission-refresh.md).
- Next: 설치된 로컬 도구로 실제 SDK/Medusa UI 시연 영어 영상 초안. 이번 제품 gate/모델/Medusa/규칙 재조회/설치/커밋/푸시/게시 없음.
