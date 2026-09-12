# Agent Brief — Rehearsal

> ▶ NEXT SESSION: [실행 전 영향 보고서](plans/2026-09-12-preflight-impact.md) P01–P11 작업을 완료했고 [감사](test/preflight-impact.md)에 구현/AWS/Chrome/영상/한계를 기록했다. 현재 공개 UI는 요청→Nova 계획→12개 격리 실행→영향 보고서→별도 결정/export다. actual preview 7호출/$0.006197, 누계 3,626호출/$4.380601, cloud 잔여 $3.838425·active 0. 2:53 영어 Daniel 영상·AWS draw.io를 최종 흐름으로 갱신했다. 초기 로컬 커밋 ad64fa9 완료, 요청한 push는 실행 정책이 거부했다([기록](test/git-publication.md)). 다음은 수동 push·공개 접근 확인이며 영상 게시/제출자/Builder ID·제출은 별도다. Devpost Submit 금지를 유지한다.

> 이전 제출 상태: [Nova 최종 제출 감사](test/nova-final-submission.md)를 따른다. 총 $10 승인 중 3,466호출/$4.191815·예약 0으로 실제 평가를 종료했다. 새 조건 80칸 B0/B1/B2/B3 완료 15/11/8/7(각 20), 납품 대기 지시 보강 후 별도 known pilot 4/4/3/4(각 5)를 보존했다. 3:45 실제 Nova 영어 영상·28자막·재생 검증과 최종 소스 패키지를 확인한다. 남은 제출 단계는 제출자/Builder ID·공개 코드/영상·접근 확인·최종 제출이며 공개 요청은 아직 없다. 추가 유료 실행은 진행 중이지 않다. 모델 우위·사람 관찰·독립 호스트 재현은 입증되지 않았다.

Last Updated: 2026-09-12

## Snapshot

F05 known pilot 9개 실제 Nova 평가의 도구 응답/행동·raw 원장을 [재감사](test/untrusted-supplier.md)했다. 단일 공격 조건의 반복이며 일반 방어·Nova+Medusa F05는 미검증이다.

최신 실제 모델 증거는 [preflight 감사](test/preflight-impact.md)에 있다. 이전 비교/구매 결과는 [Nova 기록](test/nova-live.md)에 보존했다. 아래 긴 구현 설명은 이전 SDK/Medusa 기반의 이력이다. 실제 Nova 호출 완료와 모델 효과 입증을 구별한다.

최종 초안과 로컬 개발 기반, CW00 Medusa 계약·CW01 분리 원장·CW02 독립 검증을 준비했다. Rehearsal은 거래 에이전트의 연습·Peer Review·독립 상거래 환경 전이를 목표로 한다. CW03 실행/원본 usage와 CW04 fork/독립 검토/후보 재실험·B3 세 역할의 공통 호출/비용 한도를 SDK fixture로 검증했다. CW05 Medusa HTTP·독립 판매자·재시작과 동결 B0의 연습/Medusa 6개 알려진 실행(가격/응답 유실·부분 조달)을 검증했다. 실제 모델·Peer Review·학습된 정책 전이는 미검증이다.

F03 실제 납품/SSE 지연·중복·재시작·snapshot 복구, F05 실제 상품 설명/HTTP 권한 경계를 검증했다. 실제 재고 감소 후 스크립트의 B 380 대체 구매·A/C 415 부분 조달도 독립 COMPLETE다. CW06 실제 관측 UI·B 380 원장 대조·중단/커서 복구까지 검증했다(`docs/test/observer-ui.md`). 독립 export 재검증/관측 비교 UI도 실제 Medusa로 검증했다(`docs/test/independent-evidence-ui.md`). 개별 주문/재고도 실제 Store GET/SSE/UI로 검증했다. 지연 표본도 실제 24건/반영 22건으로 계측했다(`docs/test/observation-latency.md`). 두 브라우저의 개별 커서/retention 복구와 같은 v12 상태도 실제 검증했다(`docs/test/two-browser-recovery.md`). 두 구매자의 실제 checkout 경합도 단일 Medusa 조건에서 1건 납품·패자 UNKNOWN/예약 유지로 검증했다(`docs/test/concurrent-stock-race.md`). 최신 macOS gate는 Python 690·mypy 58, 직전 브라우저 검사는 25개 통과. 실행자의 판단/차단 UI도 실제 SDK/Medusa·SSE·독립 export와 동시에 대조했다(`docs/test/execution-reaction-ui.md`). B3 공통 토큰/도구 한도·20칸 pilot(B0만 실행)·영어 제출 자료도 준비했다. 수정 B0도 실제 Medusa에서 380/360 유지·필수 품목 부족 시 주문/지급 없이 0지출로 재검증했다(`docs/test/b0-medusa-rerun.md`). 실제 모델·분산 경합·전체 지연 목표 검증은 남았다.

Linux amd64 동일 호스트 컨테이너에서 `make check`(Python 663·mypy 57), 브라우저 25개, B2/B3/동결/80칸 SDK 배치, Medusa 컴파일까지 통과했다. 최초 빌드 설정 누락은 재현 스크립트만 수정했고 운영 설정 검사는 유지했다. 원시 출력 1,504개와 독립 재감사·실패/최종 로그를 보존했다. 독립 기기·Linux DB/HTTP 거래 증거는 아니다. 이후 practice 배치의 토큰·단조 시계 시간/표본·읽기 전용 비교 CLI를 추가했고 macOS gate Python 675·mypy 58을 통과했다(`docs/test/evaluation-metrics.md`). 실제 모델 pilot은 미실행이다. `make commerce-demo`로 실제 SDK/Medusa 검증 후 관측 화면을 유지하는 무료 경로도 확인했다. 별도 브라우저 재접속·Ctrl+C 후 독립 export와 정리를 검증했으며 사람의 관찰은 0회다(`docs/test/demo-inspection.md`).

## Authority

- 시각 기획서: `agents-for-human-propsal.html` v0.3. AI 생성 이미지 2종·합성 장면 4개는 설명용이다.
- 구현 계획: `docs/plans/2026-09-06-custom-world-poc-plan.md`.
- 설계: `docs/design/CUSTOM_WORLD_FIDELITY.md`; 심사·데모: `docs/plans/2026-09-06-submission-story.md`.
- 환경: `docs/DEVELOPMENT.md`; 검증: `docs/test/development-readiness.md`.
- 이전 Aftercare 상세 기획은 `archive/aftercare/`에 있다. private `platform-agent`는 별도이며 편입하지 않는다.

## Read Order

`docs/STATUS.md` → `docs/NEXT_PLAN.md` → 최근 `docs/PROGRESS_LOG.md` → `docs/LESSONS.md`.

## Commands

- `make setup`: 저장소 전용 런타임·lock 의존성·브라우저·로컬 env 준비. 네트워크 다운로드 포함.
- `make check`: 오프라인 문서·설치·SDK import·lint·타입·Python 테스트·웹 빌드.
- `make check-browser`: 실제 로컬 API·웹·제안서 브라우저 검사.
- `make dev`: API/React 거래 관측실. Ctrl+C로 종료.
- `make commerce` / `make commerce-smoke`: 전용 Medusa/DB 기동 또는 health 검사 후 종료.
- `make world-smoke` / `make world-fixtures`: 합성 세계 정상 구매 또는 4개 알려진 사례와 독립 원장 판정.
- `make smoke-local`: check + 설치된 하네스 연결 검사.

## Boundaries

- CW00 완료 증거는 `docs/test/medusa-contract.md`. 건강 상태가 아닌 실제 HTTP 거래·권한·재고를 검사했다.
- Store 단건 주문 조회는 타 고객/비로그인도 200. CW05 gateway에서 소유권/run 격리를 강제해야 한다.
- 무료 가상 크레딧만 사용한다. 실자금·AgentCore Payments·A2A는 MVP 필수가 아니다.
- AWS 자격증명·리전·모델 ID·실제 모델 호출은 CW03에서 확인한다. 현재 검사는 모델을 초기화하지 않는다.
- 설치는 `.tooling`/`.venv`, 비밀값과 로그는 Git 제외 경로에 둔다. 기존 Docker·DB·전역 런타임은 건드리지 않는다.
- `[auto]`는 없다. AWS 데모 배포·origin 등록·초기 로컬 커밋은 완료했고 Git push는 실행 정책에 차단됐다. 야간 실행·YouTube 게시·Devpost Submit은 수행하지 않았다.
