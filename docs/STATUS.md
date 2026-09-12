# Status — Rehearsal

Last Updated: 2026-09-12

## Current Baseline
- 현재 제품/배포: [실행 전 영향 보고서 감사](test/preflight-impact.md). Nova 초기 A 제안→12칸 격리 실행→B 권장→별도 결정/원본 재확인/export/reload 실제 Chrome 확인. A/B/C 2/4·4/4·0/4, 미리보기 거래 DB 0행·IAM 격리·Runtime 404. 추가 7호출/$0.006197, 누계 3,626호출/$4.380601·예약 0, cloud 잔여 $3.838425·active 0. 전체 gate 740개/mypy 75·브라우저 28개 PASS. 공식 AWS draw.io 2페이지·2:53 영어 Daniel/28자막·재생/음량/공개 hash 확인. 이전 [B3 영상/배포](test/chrome-demo-v2.md) 보존, 초기 커밋 ad64fa9 완료·push 정책 차단([기록](test/git-publication.md)), 영상 게시·Devpost Submit 없음.
- 이전 후속: [영어 제출 영상/파일 정리](test/youtube-submission.md). 3:58/1080p·영어 UI·Daniel·32자막·썸네일·YouTube 설명 완성, 전체 디코딩/Chromium 재생 PASS. 새 Nova 독립 COMPLETE 380·18호출/$0.027211, 누적 3,484호출/$4.219026·예약 0. 약 999MB 중복/임시 파일 삭제·원본/실패/기존 볼륨 보존. `make check` PASS(Python 690·mypy 58). 공개/Submit 없음; 이전 r2 패키지는 변경 전 후보이며 공개 링크·제출자/Builder ID·접근 확인은 남았다.
- 최신 실제 실행: [Nova 2 Lite 기록](test/nova-live.md). 사용자 총 $10 승인, 정상/Medusa COMPLETE 310, B3 실제 검토·20칸 pilot(목표 완료 B0/B1/B2/B3 4/3/2/3), B2 인용 검사 수정 후 새 조건 COMPLETE 380. 아래 SDK 검증 이력과 구별한다. 비용/예약은 [실행 계획](plans/2026-09-12-nova-live.md).
- 최종 초안: HTML v0.3, 이미지 2종·합성 장면 4개, 상세 계획·전이/실시간 설계, 심사 기준·4분 45초 데모 구성.
- 이전 Aftercare HTML/Markdown은 `archive/aftercare/`에 보관했고 이전 생성기도 보관 폴더에만 쓴다.
- Python 3.12.13·Node 22.23.2 저장소 격리, uv/npm lock, Strands 1.54.0 import 경로 준비.
- FastAPI 읽기 전용 observer bridge와 React 거래 관측실을 연결했다. `make dev`로 미설정/실시간 상태를 확인한다.
- Medusa 2.20.1 독립 설치·backend build·DB migration·health HTTP 200 확인. Enterprise RBAC와 관리자 UI는 비활성. PostgreSQL/Redis는 고정 image digest와 `rehearsal-dev` 프로젝트를 사용한다. 다른 프로젝트 서비스와 분리했다.
- CW00: 실제 Medusa 합성 주문 310, 승인→capture→fulfillment→shipment→delivered, 재고 7/4·예약 0, 재시도·권한 검사 완료.
- CW01: 분리 SQLite 원장·재고/예산 transaction·가상 시계·멱등 지급·이벤트 복구 구현.
- CW02: 독립 raw DB/JSON 검증, 정상/F01/F02/F06 알려진 fixture 증거 저장.
- CW03 준비: 실행 CLI·도구 8개·usage/cost ledger·호출/추정 비용 상한. 실제 SDK+스크립트 모델로 성공/오류/한도/usage 누락 검사.
- CW04 준비: 일관된 fork·정책 schema/diff·독립 Strands 검토/후보 재실험·공통 검토 비용 한도를 SDK fixture로 검증. [B3 초기/후보 구매·검토 공통 호출/비용 한도](test/b3-shared-accounting.md)도 SDK fixture로 검증했다. 공통 토큰·도구 한도도 연결했다. 실제 모델 Peer Review·실제 usage/청구는 미검증.
- CW05 준비: 별도 loopback HTTP 서버·run/역할 권한·독립 1초 시계 worker·HTTP 도구·재시작/응답 유실 검증.
- CW05 Medusa 준비: 고객·소유권·예산 gateway에 구매 HTTP와 독립 판매자를 연결했다. 실제 A/B/C 견적과 B 납품·두 프로세스 재시작·독립 export 판정 검증.
- CW05 B0 준비: 동결 manifest·같은 고정 규칙 실행자의 연습/Medusa 6개 알려진 사례. 갱신 전 0/미완료, 갱신 후 가격/유실 380·부분 조달 360 완료. Strands `--policy` 연결도 SDK fixture로 검사.
- CW05 F03 준비: 영속 관측 journal·고객 polling·SSE·중복/역순 소비·커서 복구 구현, ASGI 포함 회귀 19개 통과. 실제 Medusa 납품·지연/중복·재시작/retention 복구까지 검증.
- CW05 F05 준비: 비신뢰 설명 봉투·공통 SDK 입력 경계 검토, 연습/HTTP·ASGI·Medusa replay 회귀 27개 통과. 실제 Medusa 설명 전달·HTTP 거절·canonical 310 구매 검증. 실제 모델은 미검증.
- CW05 재고 변경 준비: 보존 응답으로 제출 전 거절·제출 후 UNKNOWN/예약 유지·재시작·뒤늦은 단일 정산 회귀 13개 통과. 실제 재고 감소 후 B 380·A/C 415 스크립트 조달 검증. 두 run의 실제 checkout 중첩 194ms·단일 납품·패자 UNKNOWN/예약 310 유지도 검증했다. 분산/다른 경합 순서는 미검증.
- CW06 준비: 읽기 전용 SSE 지도·수령/예산·신선도·커서 복구 UI. 실제 B 380 납품·서버 중단/재연결·독립 원장 대조 검증. 독립 export 재검증·현재 관측 비교 UI도 실제 Medusa COMPLETE로 검증. 개별 주문/재고도 실제 Store GET/SSE/UI로 검증. 지연 표본 24건/반영 22건·단계별 분포/제외를 보존했다. 두 Chromium 프로세스의 개별 커서/retention 복구·같은 v12 상태를 실제 검증했다. 전체 지연 목표·모델 재계획은 남았다.
- CW07 준비: [공통 토큰/도구 한도·20칸 pilot](test/shared-limits-and-pilot.md). 알려진 B0 5개(4 COMPLETE·1 INCOMPLETE 0지출), B1/B2/B3 15개 NOT_RUN. [B2 단일 Agent 시뮬레이션](test/b2-single-agent-simulation.md)과 [동결 평가/배치](test/evaluation-batch.md)는 SDK fixture로 검증했다. B0의 불가능 품목 조건에서 불필요 지출 130→0 수정·가능한 부분 조달 360 유지. [수정 B0의 Medusa 재검증](test/b0-medusa-rerun.md)도 8개 알려진 실행으로 완료했다.
- CW08 준비: [현재 HTTP/공통 원장/반응 UI 증거를 반영한 영어 자료](test/submission-refresh.md)·아키텍처 SVG/Markdown·4:45 영상 대본·준비 목록. SVG Chromium 렌더 확인. [실제 녹화 기반 4:45 영어 영상 초안](test/submission-video.md)·내레이션/자막·재생/디코딩을 검증했다. 사람의 최종 영상 검수·새 호스트 재현·공개 저장소/영상·제출은 남았다.
- 실제 모델 호출과 동결 정책 HTTP 실행은 확인했다. 학습된 정책의 개선·미공개 일반화·제품 효용 실측은 미검증이다.

## Active Focus

[현재 P01–P11 완료 감사](test/preflight-impact.md)를 기준으로 한다. 신규 유료 실행·예산 초기화·공개/제출은 진행 중이지 않다. 실제 Amazon/실결제 연결·운영 예측 정확도·사용자 효과는 미래 범위다. 아래 CW 기록은 이전 구현·검증 이력으로 보존하며 자동 재개하지 않는다.

## Verification
- 2026-09-12 Nova: 정상/Medusa COMPLETE 310, 두 실제 20칸 pilot·수정 후 B0/B1/B2/B3 완료 4/3/3/4. 전체 1,069호출·$1.275584·예약 0, 48개 원장 재계산 일치. `make check` PASS(Python 690·mypy 58), 회귀 128개. [실제 결과·실패·비용 감사](test/nova-live.md). 모델 효과/최종 청구/실제 모델 영상은 별도.
- 2026-09-12 소스 후보: 2,605개/66,813,488바이트·압축 25,109,839바이트, 전체 해시/권한·현재 소스 대조·해제본 문서 gate PASS. 알려진 비밀값 448개 대조 일치 0. [패키지/완료 조건 감사](test/release-candidate.md). 당시 제품 gate 재실행·모델·공개 없음; 비용 대기는 이후 Nova 승인으로 해소.
- 2026-09-12 직접 시연: `make commerce-demo`의 실제 Medusa B COMPLETE 380·SDK 9호출/180토큰·별도 1440/390 브라우저 재접속/독립 판정·Ctrl+C 후 export/정리 검증. `make check` PASS(Python 682·mypy 58), 회귀 7개·67소스 hash·실제 토큰 미포함·포트 6개/기존 컨테이너 4개/볼륨 50개 보존. [상세](test/demo-inspection.md). 실제 모델/사람 관찰/공개는 아니다.
- 2026-09-12 평가 지표: `make check` PASS(Python 675·mypy 58), 전용 12개+배치 18개 회귀. 새 80칸 SDK 토큰/단조 시계 시간·58소스/1,463파일 hash 재대조, 과거 80칸은 시간 미상/bytes 보존. [읽기 전용 비교 CLI](test/evaluation-metrics.md). 실제 모델/브라우저/Linux/Medusa 이번 미실행; gate 동시 표본은 성능 비교 자료가 아니다.
- 2026-09-12 Linux: `make check` PASS(Python 663·mypy 57), 브라우저 25·B2/B3/동결/80칸 SDK 배치·Medusa 컴파일 PASS. 최초 빌드 환경 누락→원인 확인→재현 스크립트 수정→새 컨테이너 전체 exit 0. 원시 출력 1,504개·80칸 독립 재감사/가상 49,560 micro-USD·예약 0. [상세](test/linux-reproduction-20260912.md). Sonnet 4.6 후보/preflight/읽기 전용 ACTIVE 확인, 유료 호출 0회·[비용 응답 대기](plans/2026-09-12-completion.md).
- 2026-09-09 실행 기록 UI: 실제 SDK/Medusa·API/SSE/브라우저에서 A 차단→B COMPLETE 380·임시/종료 전환·두 export/독립 판정 일치. 5판단/1차단·9 SDK호출/180토큰/가상 252 micro-USD·예약 0. `make check` PASS(Python 663·mypy 57), 직전 브라우저 25개/이번 실제 연결 PASS, 38개 artifact·73소스 hash·자격증명/서비스 정리 대조. [상세](test/execution-reaction-ui.md). 실제 모델 효과는 남았다.

- 2026-09-09 반응 명부: B0 비활성·B1/B2/B3 동일 상한 고정, 실제 네 실행 독립 COMPLETE 310/380/380/380·조건 4건 일치·반응 실행 3건 검증. SDK 학습+실행 72호출/1,440토큰/84도구/가상 2,016 micro-USD·예약 0. `make check` PASS(Python 632·mypy 56), 추가 24개·119개 artifact/소스/원장/비밀값/서비스 정리 대조. [상세](test/frozen-reaction-comparison.md). 알려진 스크립트 연결이며 실제 모델 효과 비교가 아니다.

- 2026-09-09 관측 반응: 12초 SDK 대기 중 실제 A 재고 10→0/커서 11·12 수신·오래된 A 주문 POST 차단·B 주문/지급 각 1회·독립 COMPLETE 380. SDK 9호출/180토큰/8도구/가상 252 micro-USD·예약 0, 재판단 5회. 최초 fixture 실패/미확정 예약도 보존. `make check` PASS(Python 608·mypy 56), 추가 회귀 20개·45개 artifact/56소스 hash·거래/이벤트 재판정·비밀값/서비스 정리 대조. [상세](test/observed-change-replanning.md). 실제 모델 효과/배치 반응 설정/UI 표시는 남았다.

- 2026-09-09 알림 일정: B0/SDK 각각 지연 복사 2개+재전송 2개·발행 기록/SSE 수신 8프레임 일치·old/중복 제거·최종 수량 3/6. 세 실행 COMPLETE 310, 조건 2 true/미사용 false·8칸 중 5 NOT_RUN. SDK 14호출/280토큰/전체 53도구/가상 392 micro-USD·예약 0. `make check` PASS(Python 588·mypy 54), 추가 21개·74개 artifact/소스/비밀값/서비스 정리 대조. [상세](test/scheduled-notifications.md). 모델의 알림 반응/재계획은 미검증.

- 2026-09-09 지급 응답 일정: B0/SDK 두 건의 3tick 설정→4.002초 실제 지연→2.002초 ReadTimeout·같은 주문 조회→독립 COMPLETE 310. 미사용 일정 B0도 COMPLETE 310/조건 false. 8칸 중 3 VERIFIED·5 NOT_RUN, SDK 14호출/280토큰/전체 53도구/가상 392 micro-USD·비용 예약 0. `make check` PASS(Python 567·mypy 52), 추가 20개 회귀·69개 artifact/소스/비밀값/서비스 정리 대조. [상세](test/scheduled-response-loss.md). 실제 모델·외부 결제 제공자 응답 유실 증거는 아니다.

- 2026-09-09 납품 전환: 실제 GET 6개에서 fulfillment 납품 표시/품목 납품 0의 중간 상태 포착. 같은 입력 회귀 4실패→12통과, 실제 수정 후 UNKNOWN 1건·GET 재조회/단일 checkout·독립 COMPLETE 310. 이벤트 재실행의 B0 두 건도 COMPLETED/독립 COMPLETE 380·310으로 검증했다. `make check` PASS(Python 547·mypy 50), 기존 gateway/재고 포함 59개·84개 artifact/소스/비밀값/서비스 정리 대조. [상세](test/delivery-transition.md). 실제 모델·분산 일관성 증거는 아니다.

- 2026-09-09 시간표 이벤트: 최종 8칸 중 3실행/5 NOT_RUN, 10/12tick 가격·재고 변경 2실행 일치·50/52tick 미발생 조건 false. 독립 원장 COMPLETE 380/310·SDK INCOMPLETE 0, 실행/원장 결합 VERIFIED 1·INCOMPLETE 2. SDK 9회 admission/8회 usage·160토큰/가상 224 micro-USD·미확정 예약 99,776/다음 칸 차단. `make check` PASS(Python 535·mypy 50), 추가 37개 회귀·이전 실패 포함 229개 artifact/10세션·소스/비밀값/서비스 정리 확인. [상세](test/timed-condition-events.md). 납품 전환 부근 조회 불일치 진단·실제 모델·다른 이벤트 일정은 남았다.

- 2026-09-09 정적 초기 조건: 실제 Medusa 5건 조건 일치·COMPLETE 430 네 건/INCOMPLETE 0 한 건·전체 8칸 중 3 NOT_RUN. 변조/오래된 증거의 실행 전 거절·살아 있는 세션 관측 갱신 확인. SDK 총 87호출/1,740토큰/109도구/가상 2,436 micro-USD·예약 0. `make check` PASS(Python 498·mypy 49), 추가 28개 회귀·122개 artifact·소스/비밀값/서비스 정리 대조. [상세](test/static-initial-conditions.md). 초기 관측 범위이며 원자적 격리·실행 중 이벤트·실제 모델 효과는 미검증.

- 2026-09-09 네 외부 방식: B0/B1/B2/B3 새 Medusa 세션 각 COMPLETE 310·4/4 거래 검증·조건 일치 0건. SDK 총 87호출/1,740토큰/95도구/가상 2,436 micro-USD·정산 후 예약 0. `make check` PASS(Python 470·mypy 48), 추가 13개·외부 배치 총 29개 회귀. 93개 artifact·학습/거래 재판정·소스/비밀값/서비스 정리 대조. [상세](test/external-four-arms.md). 실제 모델·동등 초기 정책·미공개 비교 아님.

- 2026-09-09 외부 배치: 8칸 사전 명부에서 B3 1건 독립 거래 VERIFIED·7 NOT_RUN, 가상 비용 1,008/정산 후 예약 0·다음 상한 예약은 BATCH_COST_LIMIT. 조건 일치 0건. `make check` PASS(Python 457·mypy 48), 전용 회귀 16개·기존 배치 18개. 35개 artifact·전체 재집계·소스/토큰/서비스 정리 확인. [상세](test/external-comparison-budget.md). B0/B1/B2 어댑터·조건 일치·실제 모델은 남았다.

- 2026-09-09 B3→Medusa 회계: 학습 22+실행 14호출·총 720토큰/31도구/가상 1,008 micro-USD, 독립 COMPLETE 310·예약 0. 한도 소진/0회 실패·중단 분모/학습 예산 생략 거절. `make check` PASS(Python 441·mypy 47), 추가 18개 회귀·25개 artifact·원장/소스 47개 hash·서비스 정리 대조. [상세](test/learning-http-budget.md). 한 건의 SDK 연결이며 전체 비교 roster/실제 모델은 남았다.

- 2026-09-09 외부 세션: SDK 구매 세션 COMPLETE 310/별도 실행 판정 VERIFIED, 구매 없는 세션 INCOMPLETE 0/NOT_READY. buyer-only 0600·정책 bytes·stop 요청/자식 정리/원장 export 확인. `make check` PASS(Python 423·mypy 46), 회귀 11개·UNKNOWN 예약 310 보존. 17개 artifact·실측 후 실패 출력 교정 diff 보존. [상세](test/model-session.md). 실제 모델·브라우저 없음.

- 2026-09-09 모델 HTTP 연결: `make check` PASS(Python 412·mypy 46), 회귀 21개·`make commerce-model-smoke` PASS. SDK fixture 14호출·280토큰·13도구·가상 392 micro-USD, 실제 Medusa 지급 유실/단일 요청·310 납품·실행 NOT_VERIFIED와 별도 주문/원장 판정 일치. 11개 artifact·소스 46개 hash·비밀값/서비스 정리 대조. [상세](test/metered-http-model.md). 실제 모델/브라우저는 미실행.

- 2026-09-09 Linux 준비: 소스 1,392개 격리 복사/hash·경계 회귀 5개 검증. 기존 Linux x64 Node 22.23.2·network none에서 npm 설치가 esbuild/linux-x64 캐시 누락으로 실패(exit 1), Linux gate/웹/브라우저는 NOT_RUN. macOS `make check` PASS(Python 391·mypy 45). 전용 컨테이너 제거·기존 4개 보존. [증거/재개 절차](test/linux-reproduction.md). 네트워크 설치는 자동 승인 거절 후 사용자 허용 대기.

- 2026-09-09 B0 재검증: `make commerce-transfer-smoke` PASS(기존 6개+필수 품목 부족 2개). 실제 Medusa 380/360 유지·부족 조건 유효 조명 견적 130/170/225에도 주문/지급 0·독립 INCOMPLETE 0. `make check` PASS(Python 386·mypy 45), 25개 artifact·8개 raw 재판정/hash·포트/볼륨/기존 컨테이너 보존 확인. [상세](test/b0-medusa-rerun.md).

- 2026-09-09 배치: `make check` PASS(Python 386·mypy 45), 전용 회귀 18개·`make evaluation-batch-smoke` PASS. known grid 20조건×4방식=80 EVALUATED/독립 COMPLETE, 총 가상 비용 49,560 micro-USD·미확정 예약 0. `evidence/cw07-evaluation-batch/` 903개 artifact·raw 재판정/usage 합계/소스 45개 hash 확인. 실패/중단/미실행 전체 분모·총 예산 예약/재개 검증. 실제 모델/미공개 평가·브라우저/Medusa 이번 미실행. [상세](test/evaluation-batch.md).

- 2026-09-08 동결 평가: `make check` PASS(Python 368·mypy 44), `make frozen-evaluation-smoke` PASS. B0/B1/B2/B3 알려진 평가 모두 COMPLETE 380, 총 호출 0/14/37/36·가상 비용 0/392/1036/1008 micro-USD. 학습+평가 원장 공유·새 Agent/세계·동결/학습 hash·실패/잔여 한도 회귀 23개. `evidence/cw07-frozen-evaluation/` 46개 artifact·raw 재판정/단계 합계/hash 대조. preflight 설정 누락 exit 2. 실제 모델/미공개 비교 아님. [상세](test/frozen-model-evaluation.md).

- 2026-09-08 B2: `make check` PASS(Python 345·mypy 43), `make b2-smoke` PASS(`b2_81244731ef86458cb854c299149f79ca`). 단일 Agent/대화·Peer Reviewer 0회·fixture 23호출/460토큰/22도구/644 micro-USD, 초기 INCOMPLETE 0·후보 COMPLETE 380·동일 snapshot/부모 보존. 추가 회귀 19개와 `evidence/cw07-b2-offline/` 9개 artifact·raw 재판정·usage/source hash 대조. `b2-preflight` 설정 누락 exit 2. 실제 모델/브라우저/Medusa 미실행.

- 2026-09-08 공유 한도/pilot: `make check` PASS(Python 326·mypy 42), `make b3-smoke`·`make pilot-smoke` PASS. 추가 회귀 22개, B3 fixture 22호출·440토큰·18도구·616 micro-USD. B0 5개와 모델군 NOT_RUN 15개 보존·수정 전후 불가능 품목 지출 130→0. `evidence/cw04-shared-limits/`, `evidence/cw07-known-pilot/{before,after}/` 총 49개 artifact·독립 재요약/hash 확인. 영어 자료·아키텍처 SVG 렌더 확인, 제품 브라우저/Medusa/실제 모델 이번 미실행.

- 2026-09-08 CW04 B3: `make check` PASS(Python 304·mypy 41), `make b3-smoke` PASS. 초기/검토/후보 6/2/14 fixture 호출·가상 비용 616 micro-USD, 초기 INCOMPLETE 0/후보 COMPLETE 380·동일 snapshot·부모 보존. 회귀 19개로 공통 한도·실패/누락 usage 예약·역할별 거절/토큰 집계 확인. `evidence/cw04-b3-offline/`의 13개 artifact·소스 10개 hash·독립 원장 재판정 대조. `b3-preflight`는 모델/단가/한도 누락 exit 2. 실제 모델·브라우저·Medusa 이번 미실행.

- 2026-09-08 두 구매자 경합: `make check` PASS(Python 285·mypy 39), `commerce-race-smoke` PASS(`cw00-608e1d67aec7`). checkout 중첩 194ms·실제 주문/납품 1개·원장 COMPLETE 310/UNKNOWN 예약 310, 재시작·재조회 포함 checkout 총 2회·대체 지급 예산 거절. `evidence/cw05-race/`의 원장/trace/hash/토큰과 서비스 종료/포트/볼륨/기존 컨테이너 확인. browser gate는 이번 미실행(직전 19개 통과).

- 2026-09-08 두 브라우저: `make check` PASS(Python 283·mypy 39), `make check-browser` PASS(19개), `commerce-convergence-smoke` PASS(`cw00-a8e25271ce9e`). 한쪽 단절 중 재고/납품 진행·cursor 2 짧은 복구·cursor 3→12 snapshot 복구, 두 화면 v12/원본 관측/독립 COMPLETE 380 대조. `evidence/cw06-convergence/` 보존·hash/토큰·전용 서비스/포트/볼륨/기존 컨테이너 확인.

- 2026-09-08 지연 계측: `make check` PASS(Python 283·mypy 39), `make check-browser` PASS(18개). 실제 수신 24건/반영 22건, 관측→반영 p95 966ms·조회 시작→반영 p95 1,028ms. 지연 납품 2건의 게시 지연 2,167ms와 미반영 사유 보존. `evidence/cw06-latency/`의 원시 표본/journal·독립 재계산·hash 대조, 서비스 종료/포트/볼륨/기존 컨테이너 확인. 전체 1초 목표 통과는 아니다.

- 2026-09-08 주문/재고 UI: `make check` PASS(Python 274·mypy 39), `make check-browser` PASS(13개). 실제 A 재고 10→0, B 구매 후 재고 7/4·납품/정산·독립 COMPLETE 380·재연결. `evidence/cw06-commerce-details/` 보존. 납품 조회 불일치 1회는 제한 GET 재조회로 회복. 전용 서비스/포트/볼륨 정리 확인.

- 2026-09-08 독립 증빙 UI: `make check` PASS(Python 255·mypy 38), `make check-browser` PASS(12개). `commerce-observer-smoke` PASS(`cw00-d6c09eac6808`): 실제 B 380 export 재검증→브라우저 증거 시점 COMPLETE·관측 일치. `evidence/cw06-evidence-ui/` 보존·hash/토큰/원장 확인. 전용 서비스 종료·포트/볼륨/기존 컨테이너 확인.

- 2026-09-08 CW06 최종 `make check` PASS(Python 230·mypy 37소스), `make check-browser` PASS(9개). 실제 `commerce-observer-smoke` PASS: A 재고 감소→스크립트 B 380·수령 9, 브라우저 중단/커서 복구·독립 COMPLETE. `evidence/cw06-observer/`에 실패 2건·최종 증거/화면/hash 보존. 토큰 미포함·전용 서비스 종료·포트 6개 반환·볼륨 보존 확인.

- `scripts/commerce/transfer_smoke.py` PASS: 3개 조건×연습/Medusa 총 6개 알려진 실행. 같은 frozen ID, 독립 원장 0/미완료·380/완료·360/완료, 도구 5/20/47회. 실행 명령은 `make commerce-transfer-smoke`로 연결했다.

- `make commerce-operating-smoke` PASS: A/B/C 310/380/495 견적, A 가격 변경→B 구매 380, HTTP 응답 유실, 구매 HTTP 정지 중 독립 납품, 판매자·gateway 재시작, 원장 COMPLETE. `evidence/cw05-medusa-operating/` 보존.

- `make commerce-adapter-smoke` PASS: 실제 가격 갱신·응답 유실 후 GET 복구·고객/run 격리·예산 거절·capture/납품·재시작, 독립 판정 COMPLETE(310). `evidence/cw05-medusa/` 보존.
- 공통 fixture seed 분리 후 `make commerce-contract` 재실행 PASS.
- `make operating-smoke` PASS: 실제 HTTP 권한·가격/재고 계약·응답 유실·독립 진행·동일 DB 재시작, 종료 후 원장 COMPLETE.
- `make operating-sdk-smoke` PASS: 스크립트 모델 SDK→HTTP 도구→별도 worker→310 구매·수령. 실제 모델은 아니다. `docs/test/operating-http.md` 참고.

- 2026-09-08 최종 `make check` PASS: Python 212개, mypy 36개 소스, ruff·lock·웹 빌드. 독립 검토 18개·원본 usage 누락 3개 추가. SDK의 누락 usage 기본 0을 원본 stream 관측으로 구별한다. TestClient deprecation 2개 유지. 앞선 실제 Medusa 검사 3종 증거는 보존했다. 이번 검토 연결에서는 브라우저·Medusa·실제 모델은 미실행.
- 2026-09-08 실제 `commerce-stock-smoke`·`commerce-notification-smoke`·`commerce-supplier-smoke` PASS. `evidence/cw05-{stock,notifications,supplier}`에 독립 원장·요청/응답·소스/증거 hash 보존. 최초 재고 실패도 보존. 전용 프로세스/DB 종료·포트 4개 반환·볼륨 2개 보존·다른 컨테이너 유지 확인.
- 증거 hash·변경 Markdown 링크·비밀값 ignore 확인. 개발 포트 5개 반환, 전용 Medusa/컨테이너 종료 확인.
- 초기 개발 환경·lock 재설치·최초 브라우저/감사 기록은 [개발 기반 검증](test/development-readiness.md), 실제 계약은 [CW00 기록](test/medusa-contract.md), 자체 원장은 [CW01/CW02 기록](test/world-foundation.md)에 보존했다.
- Git 초기 커밋·remote 없음. AWS는 승인된 Nova 호출만 수행. 커밋·푸시·실자금·배포·게시·야간 실행 없음.

## Open Product Questions

- Store 단건 조회 자체는 타 고객·비로그인 200. Medusa gateway의 고객/run 검사를 구매 HTTP에 연결해 검증했다. 원본 Store 경로를 구매 도구에 노출하지 않는다.
- Medusa에는 가상 예산·견적 버전이 없다. gateway 별도 원장으로 예약하며 cart 갱신의 가격 확인과 자체 quote version의 보장은 다르다.
- 정책 전이, Peer Review의 비용 대비 효과, 실시간 지연 목표 달성: CW03~07.
- 개발자 검증 시간 절감: 사용자 관찰 미수행. 사업성은 가설.
- Nova 2 Lite 글로벌/총 $10/첫 $1 승인과 실제 호출이 기존 Sonnet 비용 응답 대기를 대체했다. [현재 모델/단가/실행 계획](plans/2026-09-12-nova-live.md)의 캠페인 원장과 미확정 예약을 먼저 확인한다.
- 실제 Nova 원본 usage와 공식 단가를 대조했으며 최종 AWS 청구 검증은 아직 없다. 입력 추정 기반의 비용 제한은 실제 청구 절대 상한이 아니다.
- 자체/Medusa 판매자·HTTP와 B0의 알려진 계약 전이는 검증했다. 모델 기반 정책 전이·미공개 공격/Nova+Medusa F05 판단·분산/다른 순서의 재고 경합·전체 지연 목표 검증은 남았다. F04도 모델 실행/새 조건 검증은 아직 없다.
- Medusa 제출 후 주문이 생성되지 않은 불확실 요청은 예산 예약이 남는다. 명시적 재개·만료/취소/환급은 미구현. 자체 세계의 거절된 미지급 주문도 재고 예약을 유지한다.
- OpenMMO는 소스 조사만 했다. 코드·에셋을 편입하지 않았으며 채택하지 않는다.
- macOS arm64·동일 호스트 Linux amd64 오프라인 재현을 확인했다. 독립 호스트·Linux DB/HTTP·원격 CI·공개 접근은 별도 검증 대상이다.
