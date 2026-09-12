# AWS 서버리스 전환과 배포

2026-09-12 사용자 승인: 직전 제안한 전체 AWS 서버리스 구성으로 전환하고 AWS에 배포한다. 이 문서가 현재 배포 작업의 우선 계획이다. 기존 Medusa/SQLite 근거와 제출 영상은 당시 실행 근거로 보존하며 새 DynamoDB 실행과 혼동하지 않는다. Git origin 등록은 완료했지만 이번 배포 요청만으로 커밋/푸시나 Devpost Submit을 실행하지 않는다.

## 완료 조건

1. 영어 React 대시보드를 private S3 + CloudFront HTTPS로 제공한다. 외부 사용자가 제한된 시나리오/방식을 선택해 실험을 시작하고 진행/주문/비용/독립 판정을 볼 수 있다. 읽기 전용 로컬 관측 경로도 회귀를 유지한다.
2. API Gateway + Lambda가 실험 시작/조회 및 서버 측 실행 admission을 담당한다. 사용자는 recipient, budget, AWS resource, arbitrary prompt/code를 지정하지 못한다. 중복 시작은 같은 실행을 조회하며 임의 원장 변경은 불가하다.
3. Strands + Nova 2 Lite를 AgentCore Runtime에 배포한다. 기본 구매와 기존 시뮬레이션/독립 Peer Review 경로를 유지하고 학습/검토/구매 usage를 같은 실행 예산에 포함한다. SDK fixture를 실제 Nova 결과로 표현하지 않는다.
4. Lambda + DynamoDB가 실험별 재고/견적/주문/합성 지급/배송을 처리한다. 조건부 원자적 갱신·멱등 요청·목표/예산/수신처 고정·불확실 결과 예약 보존을 검증한다. agent 역할은 구매 도구만 호출하며 판매자/검증기 권한을 갖지 않는다.
5. Step Functions Standard가 배송/가격/재고 변경 시점을 독립 진행하고 전체 실행 deadline/오류 정리를 담당한다. 실행을 마치면 Runtime 세션을 명시적으로 종료한다. 항상 켜진 EC2/Fargate/RDS/Redis/ALB/NAT/Provisioned Concurrency를 만들지 않는다.
6. 상태/감사 이벤트를 실행 중 DynamoDB에 원자적으로 보존하고 독립 verifier가 원장으로 결과를 다시 계산한다. S3에 원본+결과를 보관하며 중단/실패/미상은 성공으로 승격하지 않는다.
7. 로컬 회귀·실제 AWS 기본 거래·이벤트·중복/권한/비용 admission·CloudFront 브라우저 실행·세션 종료/잔여 자원·공개 링크를 확인한다. 실제 배포와 일치하는 편집 가능한 `.drawio` 아키텍처 및 미리보기, 테스트 안내/Devpost 초안과 영상도 새 배포에 맞춰 갱신한다. GitHub/YouTube/Devpost 게시를 임의로 수행하지 않는다.

## 배포 경계와 비용

- 기존 승인 계정/profile `q-user`, 리전 `us-west-2`, 모델 `global.amazon.nova-2-lite-v1:0`을 사용한다. 새 AWS 리소스는 `rehearsal-serverless` 접두어와 프로젝트 태그로 추적한다. 기존 프로젝트 리소스는 변경하지 않는다.
- 기존 모델 캠페인 $4.219026/미확정 0을 보존한다. 총 $10 승인 잔액에서 신규 서버리스 모델 실행은 우선 전역 $4 한도로 분리 예약하고, 실행당 최대 $0.50·동시 실행 1·유한 실행 횟수/마감시간을 서버에서 강제한다. 한도 소진은 화면에 표시하며 재설정/자동 증액하지 않는다.
- AWS 배포는 승인되었다. 모델 $10 한도와 인프라 과금은 별개다. 온디맨드 저장/요청/워크플로/Runtime 비용과 종료 상태를 기록한다. AWS Budgets 알림을 실제 하드 차단이라고 표현하지 않는다.
- 서버리스 운영 DB는 DynamoDB다. 기존 격리 연습 SQLite는 필요 시 AgentCore의 일시 파일 영역에서 사용하며, 항상 켜진 DB/호스트가 아니다. 연습 원장도 S3에 보존한다.
- 공개 시연은 합성 상품/크레딧만 사용한다. 실행 ID별 격리와 전역 예산 admission을 적용하며 비밀값/자격증명/내부 파일 경로는 브라우저에 제공하지 않는다.

## 순서

- [x] S01: DynamoDB 거래 모델/독립 검증/동시성·재시도·부정 입력 회귀.
- [x] S02: 서버리스 adapter·기존 Strands/B2/B3 공통 계측·실행 상태/결과 export.
- [x] S03: CloudFormation/배포 패키징·IAM 역할 분리·Step Functions·자동 세션 정리.
- [x] S04: 영어 실험 시작/조회 UI와 정적 배포, 로컬/실제 AWS 검증.
- [x] S05: 새 실제 배포 영상·아키텍처·제출 자료·비용/정리/완료 감사.

공식 기준: [AgentCore Python CodeZip](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html), [Runtime HTTP 계약](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html), [DynamoDB 트랜잭션](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html), [Step Functions Wait](https://docs.aws.amazon.com/step-functions/latest/dg/state-wait.html).

검증/제출 산출물은 [서버리스 실제 배포 감사](../test/serverless-deployment.md)에 모았다. 최종 `make check`(715 tests / 68 source files), 공개 AWS/브라우저·세션 종료, 영상/자막과 draw.io 검증을 완료했다. 모든 S01–S05 완료 조건을 충족했다.
