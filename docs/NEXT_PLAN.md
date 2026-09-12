# Next Plan — 거래 리허설 POC

Last Updated: 2026-09-12

## Active Plan

현재 요청의 구현/배포/영상/아키텍처는 [감사](test/preflight-impact.md)로 완료했다. 실행 중인 작업·승인된 자동 seed는 없다. 다음 요청에서 공개 코드/영상·제출자/Builder ID·최종 제출 범위를 정한다. Devpost Submit 금지를 유지한다. 아래 CW 미검증 항목은 장기 검증 이력이며 자동 유료 실행 대상이 아니다.

[AWS 서버리스 배포](plans/2026-09-12-serverless-deployment.md)는 완료했다. 실제 AWS·715개 테스트 결과는 [감사](test/serverless-deployment.md)에, 최신 2:30 Chrome 영상·공식 AWS 아이콘 draw.io와 추가 B3 실행은 [후속 감사](test/chrome-demo-v2.md)에 있다. 남은 공개 코드/영상, 제출자/Builder ID와 최종 제출은 요청 범위에 따라 진행한다. 추가 모델 실행이나 budget 재설정을 자동으로 시작하지 않는다.

이전 제출 결과는 [영어 제출 영상/파일 정리](test/youtube-submission.md)다. 영어 화면 재녹화·Daniel 전체 내레이션·3:58/32자막·썸네일·YouTube 설명은 완료했다. 누적 3,484 Nova 호출/$4.219026·예약 0. 다음은 현재 소스의 공개 준비, 제출자/Builder ID·공개 코드/영상 URL·접근 확인이다. 사용자가 Devpost Submit을 하지 말라고 했으므로 제출은 실행하지 않는다. 이전 r2 압축본은 이번 변경 전 후보이며 추가 유료 실행은 진행 중이지 않다. 모델 우위·독립 held-out·사람 관찰·독립 호스트 재현은 미검증이다.

[상세 계획](plans/2026-09-06-custom-world-poc-plan.md) · [구현 수준·현실 전이](design/CUSTOM_WORLD_FIDELITY.md) · [OpenMMO 조사](research/2026-09-06-openmmo-assessment.md).

최종 초안과 로컬 개발 기반까지 준비했다. [환경 안내](DEVELOPMENT.md)와 [검증 기록](test/development-readiness.md)을 따른다. HTML 합성 장면은 CW06, Medusa health는 CW00 거래 검증 완료가 아니다. CW00은 [실제 계약 검사](test/medusa-contract.md), CW01·CW02는 [로컬 세계·독립 판정](test/world-foundation.md)으로 완료했다. 사용자 요청에 따라 아래 순서로 구현하며 자동 실행 seed가 아니다.

- [x] CW03 — [실제 Nova 단일 실행](test/nova-live.md): 11모델 호출/10도구, 텐트 3·조명 6·독립 COMPLETE 310·예약 0, 입력 30,379/출력 437·$0.010210. 원본 사용량 비용이며 최종 청구 검증은 별도다.
- [ ] CW04 — 상태 fork·반례 검토·정책 개선. 일관된 fork·정책 schema/diff·[독립 검토/후보 재실험](test/independent-review.md)을 SDK fixture로 준비했다. [B3 초기 구매·검토·후보 구매의 공통 호출/비용 한도](test/b3-shared-accounting.md)도 SDK fixture로 검증했다. 실제 Nova 검토·구매 usage·별도 동결 평가를 확인했다. 정책 개선 효과·미공개 일반화 검증은 남았다. Done: 실험 ID와 정책 diff 연결.
- [ ] CW05 — 운영형 샌드박스와 독립 백엔드 어댑터. Medusa/독립 판매자·[동결 B0 6개 알려진 실행](test/frozen-policy-transfer.md), [F03 실제 SSE](test/medusa-notifications.md), [F05 실제 설명/HTTP](test/untrusted-supplier.md), [실제 재고 감소 후 스크립트 조달](test/medusa-stock-changes.md)을 검증했다. [두 구매자의 희소 재고 경합](test/concurrent-stock-race.md)도 단일 Medusa 조건에서 검증했다. [수정 B0 재검증](test/b0-medusa-rerun.md)도 기존 결과 유지·불필요 구매 0으로 확인했다. [계측 모델 HTTP 실행/별도 원장 판정](test/metered-http-model.md)도 SDK fixture+실제 Medusa로 검증했다. [세션 유지/설정 전달 CLI](test/model-session.md)도 실제 Medusa로 검증했다. [B3 한 건의 학습/외부 실행 합산 원장·한도·분모](test/learning-http-budget.md)도 검증했다. [B3의 전체 명부 사전 예약/중단/독립 정산](test/external-comparison-budget.md)도 검증했다. [네 방식의 외부 실행](test/external-four-arms.md)도 검증했다. [정적 초기 조건 적용/원시 관측 일치](test/static-initial-conditions.md)도 실제 Medusa 5건으로 검증했다. [시간표 가격/재고 이벤트](test/timed-condition-events.md)의 실제 적용·발생 증거도 연결했다. [납품 전환 UNKNOWN/재조회](test/delivery-transition.md)도 실제 GET·회귀·기존 이벤트 재실행으로 검증했다. [지급 응답 지연/실제 타임아웃](test/scheduled-response-loss.md)도 선언 일정·영속 소비·실제 복구로 검증했다. [알림 지연/중복·재전송 일정](test/scheduled-notifications.md)도 원시 발행/실제 SSE 수신 대조로 검증했다. [CW06 관측 반응](test/observed-change-replanning.md)도 선택 실행 설정으로 연결했다. [동결 명부/반응 설정](test/frozen-reaction-comparison.md)도 실제 네 방식으로 검증했다. [실행자 반응 UI](test/execution-reaction-ui.md)를 실제 SDK/Medusa 실행·SSE·종료 기록·독립 export와 동시에 대조했다. [영어 제출 초안/아키텍처](test/submission-refresh.md)를 현재 증거와 대조해 갱신했다. [4:45 영어 영상 초안](test/submission-video.md)도 실제 SDK/Medusa 녹화·영어 내레이션/자막·재생 검수로 제작했다. [잔여 요구 감사](test/readiness-audit.md)에서 250개 보존 artifact·영어 링크 51개·새 소스 복사본 2,526개를 대조했다. [지연 시작점 감사·실제 재고 변경 계측](test/source-latency.md)도 마쳤다. 별도 gate 종료 후 20건의 변경→화면 p95 범위는 로컬 시계 전제 1,275~1,316ms이며 내부 이벤트만의 목표 판정은 아니다. 실제 Nova 정상 구매·동결 정책 Medusa 거래와 비용 승인은 완료했다. 독립 호스트 재현·실제 관찰·공개 제출은 남았다. 남은 범위는 실제 모델 기반 정책 전이·미공개 공격/Nova+Medusa F05 판단·분산/다른 경합 순서다. Done: 동결 정책의 외부 실행·원장 증빙.
- [ ] CW06 — 실시간 2D 지도·SSE·증빙 UI·상태 변화 재계획. [읽기 전용 지도/SSE](test/observer-ui.md)·실제 B 380 원장 대조·재접속을 검증했다. [독립 증빙 UI](test/independent-evidence-ui.md)도 연결했다. [주문/재고 관측](test/commerce-observation-details.md)도 검증했다. [지연 표본 계측](test/observation-latency.md)도 검증했다. [두 브라우저의 상태 일치·개별 재접속/retention 복구](test/two-browser-recovery.md)도 실제 검증했다. [관측 변화 큐·최신 상태 재확인·재판단/공통 한도](test/observed-change-replanning.md)를 SDK fixture+실제 Medusa A 차단/B 380으로 검증했다. [비교 명부의 반응 설정](test/frozen-reaction-comparison.md)도 검증했다. 반응 UI는 보존 기록/API/브라우저와 실제 SDK/Medusa 동시 실행으로 검증했다. 실제 Nova 재계획 3건 중 두 성공·한 실패와 동시 UI/영상은 검증했다. 전체 지연 목표·다른 일정의 회복은 남았다. Done: 재접속 복구·중복 제거·신선도·지연 측정, 외부 변경 반영.
- [ ] CW07 — 비교 평가·개발자 관찰. [공통 토큰/도구 한도·20칸 pilot](test/shared-limits-and-pilot.md)·B0 5개를 검증했다. [B2 단일 Agent 연습](test/b2-single-agent-simulation.md)도 SDK fixture로 준비했다. 원래 명부의 B1/B2/B3 15개는 NOT_RUN으로 보존하며 별도 Nova 20칸 pilot 두 번을 완료했다. [B2/B3 동결·새 Agent/세계 평가](test/frozen-model-evaluation.md)도 SDK fixture로 검증했다. [20조건×4방식 배치·총 예산·중단/재개](test/evaluation-batch.md)도 SDK fixture로 검증했다. 실제 모델 known pilot 세 번과 사전 동결한 새 조건 80칸을 완료했다. [80칸 결과](test/nova-prospective.md)와 [납품 지시 보강 후 pilot](test/nova-delivery-prompt.md)을 구별한다. 독립 외부 held-out·개발자 관찰은 남았다. [관찰 절차/양식](evaluation/developer-observation.md)은 준비됐고 참가자 0명이다. [읽기 전용 토큰/실행 시간 비교](test/evaluation-metrics.md)는 준비했다. 승인된 평가 실행은 종료했으며 추가 유료 실행은 현재 계획하지 않았다. Done: 전체 분모·실패·비용·표본 한계 포함.
- [ ] CW08/CW09 — [영어 제출 자료](submission/READINESS.md)·README·테스트 절차·아키텍처·영상 대본 준비. [Linux 동일 호스트 컨테이너 재현](test/linux-reproduction-20260912.md)은 전체 오프라인 gate·브라우저·SDK·Medusa 컴파일까지 통과했다. [무료 직접 관측 시연](test/demo-inspection.md)은 실제 Medusa·별도 브라우저·종료 export로 검증했다. [로컬 4:45 영어 영상 초안](test/submission-video.md)은 실제 SDK/Medusa 녹화로 제작했다. 독립 호스트·최종 3:58 실제 Nova/Daniel 영상의 사람 검수·공개 저장소/영상/접근·Builder ID·최종 결과 반영은 남았다. 공개·배포·제출은 해당 실행 요청 범위에서 진행.

## Deferred Prior Direction

Aftercare P01–P12/L01–L06은 [이전 계획](plans/2026-09-06-aftercare-implementation-plan.md)에 남긴다. 방향이 바뀌었으므로 현재 작업으로 실행하지 않는다.

하네스 보강 H01(문서 gate 실패 fixture), H02(이전 Markdown/HTML 해시)는 미완료 상태로 보류한다. 기존 승인을 새 제품 구현 승인으로 해석하지 않으며 자동 seed로 소비하지 않는다. 이후 야간 실행 요청이 있으면 현 방향에 맞춰 다시 seed한다.

## Rules

- 로컬 환경은 설치·검증했다. 이후 클라우드·모델 호출·서비스 가입·게시를 개발 준비 완료로 간주하지 않는다.
- 초기 커밋과 clean worktree 확보 전 runner를 실행하지 않는다.
- 가상 환경 성과와 외부 전이·실자금 운영을 구별한다.
