# AWS 서버리스 전환과 실제 배포 검증

2026-09-12 사용자 승인으로 서버리스 전환과 AWS 배포를 수행했다. 기존 로컬 Medusa/SQLite 실험은 보존했고, 현재 공개 실행 경로의 운영 DB는 DynamoDB다.

- 공개 영어 데모: **https://d1u9yhii3gor6j.cloudfront.net**
- 편집 가능한 아키텍처: [draw.io 2페이지](../../submissions/architecture/rehearsal-serverless.drawio), [SVG](../../submissions/architecture/rehearsal-serverless.svg), [PNG](../../submissions/architecture/rehearsal-serverless.png).
- 최신 제출 영상: [2:30 Chrome 영어 MP4](../../submissions/video/rehearsal-demo.mp4), [영어 자막](../../submissions/video/captions.en.srt), [YouTube 설명](../../submissions/video/youtube.md).
- 원시 배포 감사: [deployment-audit.json](../../evidence/serverless-deployment/deployment-audit.json). 배포/재현 방법은 [infra/serverless](../../infra/serverless/README.md).

## 실제 구성

계정 `908601828278`, 리전 `us-west-2`, operator profile `q-user`에 `rehearsal-serverless-base`와 `rehearsal-serverless-app` 두 CloudFormation 스택을 배포했다. base는 private S3 두 개와 PAY_PER_REQUEST DynamoDB 두 개를 보존한다. app은 CloudFront, HTTP API Gateway, 역할이 분리된 Lambda 다섯 개, Step Functions Standard, AgentCore Runtime을 제공한다.

Runtime은 ARM64 Python 3.12 code ZIP으로 배포했으며 Strands와 `global.amazon.nova-2-lite-v1:0`을 사용한다. B2/B3의 격리 연습 SQLite는 관리형 Runtime 세션의 임시 파일이며 S3로 export한다. 상시 DB 서버가 아니다. 실제 판매자/거래/감사 데이터는 DynamoDB에 있다. Buyer IAM은 commerce Lambda만 호출하며 seller와 거래 DB 직접 쓰기, 최종 `commerce-evidence.json` 덮어쓰기를 허용하지 않는다.

Step Functions가 연습 종료 후 구매 시계를 시작하고 가격/재고/납품을 독립 진행한다. 최종 검증 전에 control의 closing 상태를 원자적으로 설정한다. 거래 commit의 같은 트랜잭션이 이 상태를 확인하므로, 종료 전에 준비된 쓰기도 종료 후에는 반영되지 않는다. Runtime을 중단한 다음 verifier가 원본 journal에서 결과를 재계산하고 S3에 보존한다. Runtime 최종 문장은 성공 판정 근거가 아니다.

## 검증 결과와 범위

| 검사 | 실제 근거 | 범위 |
|---|---|---|
| 조건부 거래/재시도 | [transactions.json](../../evidence/serverless-deployment/transactions.json) | 실제 DynamoDB에서 재고 경합 승인 1개, commit 뒤 응답 실패 주입, 같은 키 재시도·예약 보존·독립 COMPLETE 310. 실제 네트워크 패킷 유실 실험은 아님 |
| 전역 admission | [admission-test.json](../../evidence/serverless-deployment/admission-test.json) | 동시 요청 둘 중 하나만 승인, 중복 요청에 추가 예약 없음, 다른 method 재사용 거부, 1회 환급. Runtime/model 호출 없음 |
| 종료 이후 늦은 쓰기 | [closure-test.json](../../evidence/serverless-deployment/closure-test.json) | 실제 DynamoDB에서 미리 만든 commit을 closing 뒤 거부하고 감사 snapshot 불변 확인 |
| 시작 실패 정리 | [failed-bootstrap-test.json](../../evidence/serverless-deployment/failed-bootstrap-test.json) | 실제 Lambda/DynamoDB component 검사. 누락된 genesis·주입한 workflow 오류를 INVALID로 보존, closing 뒤 claim 거부, 호출하지 않은 run의 0비용 slot 정리. 실제 Step Functions 장애를 유발한 검사는 아님 |
| IAM 분리 | [구매 권한](../../evidence/serverless-deployment/iam-test.json), [증거 쓰기 권한](../../evidence/serverless-deployment/evidence-iam-test.json) | AWS IAM simulator의 허용/거부. 모델 보안 일반화 실험은 아님 |
| 공개 API | [api-contract.json](../../evidence/serverless-deployment/api-contract.json) | CloudFront 경유 JSON·추가 budget·잘못된 scope/scenario 거부, 종료 run 중복 요청 재사용, scope 충돌 거부 |
| 실제 모델과 상거래 | [전체 실행 감사](../../evidence/serverless-deployment/deployment-audit.json) | B0/B1/B2/B3와 재고/공급처 공격 조건, 거래 8건 모두 독립 COMPLETE. 서로 다른 조건과 반복 녹화가 섞인 기능 검증이며 비교 벤치마크가 아님 |
| 종료/보존 | 각 run의 `stop-recheck.json`, `copy-audit.json`, `workflow.json` | 8개 세션 모두 별도 Stop 재조회에서 404/terminated, 워크플로 SUCCEEDED, 다운로드한 S3 원장을 독립 재검증 |
| 브라우저 | [최종 녹화 검사](../../evidence/serverless-deployment/browser/cloud-b1-framed/browser-report.json) | 공개 UI에서 실제 시작·조회·완료, 새로고침 같은 run, 1600px 녹화와 390/320px 화면 overflow 없음 |
| draw.io | [열기 기록](../../evidence/serverless-deployment/drawio-open.json), [두 번째 페이지](../../evidence/serverless-deployment/drawio-boundaries.png) | 실제 diagrams.net에서 두 페이지를 열고 구조/문구 확인. 단일 래스터 이미지를 넣은 파일이 아닌 편집 가능한 노드/연결선 |

실제 AWS 기능 검증에 사용한 모든 run과 model usage는 `deployment-audit.json`에 있다. 최초 stock-change 녹화는 이벤트가 승인 후에 발생해 A에서 310으로 완료했다. 이후 v2 시나리오는 이벤트를 구매 시작 2초 뒤로 앞당겼고 B3 및 B1의 B 380 거래를 확인했다. 이전 결과를 대체하거나 회복 성공으로 재해석하지 않았다. 마지막 추가 녹화는 가려진 납품/비용 패널을 온전히 보이게 하기 위한 것이며 그 모델 비용도 포함했다.

B2 실제 연습+구매는 41호출/$0.065394, B3 실제 구매+tool-free review+외부 구매는 26호출/$0.026492였다. 두 학습 결과는 모두 `NO_CHANGE`였다. 이 기능 검증은 새로운 정책의 우위를 입증하지 않는다. 공급처 공격 한 건은 원래 수신처와 500-credit 경계 안에서 COMPLETE 310이었으며 일반적인 prompt-injection 방어 성능을 뜻하지 않는다.

## 비용과 대기 상태

이번 서버리스 검증·녹화는 **112호출 / $0.132376**, 미확정 모델 예약 0이다. 이전 캠페인 **3,484호출 / $4.219026**과 합하면 **3,596호출 / $4.351402**다. 공급자 raw usage와 지정 rate card로 산출한 모델 추정치이며 AWS 청구서와 인프라 비용을 정산한 값이 아니다.

공개 데모는 처음 $4 model allowance, 실행당 $0.50 예약, 동시 실행 1개, 총 admission 40개, 2026-10-10 00:00 UTC 마감으로 제한했다. 감사 시 잔여 allowance는 **$3.867624**, 남은 admission은 **29개**, active slot은 **0**이다. 정상적으로 기록된 실제 비용만 차감하고 불확실 usage는 예약을 유지한다. 배포 스크립트는 기존 예산을 초기화하거나 늘리지 않는다.

Runtime은 idle 60초/max lifetime 420초이며 매 실행 종료 시 명시적으로 중단한다. 두 스택에는 EC2, ECS/Fargate, RDS, ElastiCache/Redis, ALB, NAT 또는 provisioned concurrency가 없다. DynamoDB는 온디맨드이고 private S3의 anonymous GET은 403이었다. Lambda 로그와 Runtime 로그 보존은 7일이다. 데이터 저장, API 요청, 워크플로, 로그, Lambda/Runtime 실행에는 서비스별 사용료가 남는다. 무조건 무료나 청구액 0이라고 표현하지 않는다.

## 최초 영상과 제출 파일

현재 영상은 [Chrome 재녹화/편집 감사](chrome-demo-v2.md)의 2:30 버전이다. 아래는 최초 3:34 버전의 기록이며 [이전 MP4](../../evidence/chrome-demo-v2/previous-video/rehearsal-demo.mp4)를 보존했다. 추가 실행은 23호출/$0.023002이고 최신 누계·예산은 후속 감사에 있다.

최종 영상은 **214초(3:34), 1920×1080, 30 fps, H.264/AAC, 영어 26자막**이다. 실제 AWS run `rehearsal-36a3f7aa2dc930cd1a26bc4c239226ad`의 원속도 녹화를 사용했다. 이 run은 9호출/$0.007956, B 380, independent COMPLETE, 예약 0이다. 후반 80-cell 결과는 과거 practice-world 비교임을 명시했다.

ElevenLabs Daniel 음성은 최초 7요청 2,227자와 숫자 변경에 따른 1개 장면 재생성 313자를 사용했다. 변경하지 않은 여섯 장면은 캐시를 재사용했다. 총 요청 8개/보고 크레딧 1,396이며 자동 재시도는 없었다. 전체 MP4 decode와 Chromium 재생·8개 seek·영어 자막 검사를 통과했다. [제작 기록](../../evidence/serverless-deployment/video/build-report.json), [재생 검사](../../evidence/serverless-deployment/video/playback-check.json), [파일 hash](../../evidence/serverless-deployment/video/deliverable-hashes.json)를 보존했다.

이전 3:58 Medusa 제출 영상은 [이전 영상 보관](../../evidence/cw08-youtube-submission/medusa-video-v1/rehearsal-demo.mp4)에 보존했다. 새 Devpost 초안, README, testing/architecture/form/readiness 문서는 현재 hosted 경로를 반영한다. GitHub commit/push, YouTube 업로드, Devpost Submit은 실행하지 않았다.

## 로컬 검증

최종 [`make check` 로그](../../evidence/serverless-deployment/final-check.log)는 Python **715개**, mypy **68개 파일**, lint·문서·web build 통과를 기록한다. 최종 [로컬 브라우저 회귀 **25개**](../../evidence/serverless-deployment/final-browser.log)도 별도 통과했고, 공개 AWS 브라우저 검사는 위 실제 실행 기록으로 구별한다. 테스트 수집 중 기존 파일과 동명인 새 `test_metering.py`가 충돌해 새 파일만 고유 이름으로 바꿨다. 이것은 테스트 수집 오류였으며 제품 코드나 기존 테스트를 삭제하지 않았다.

최초 앱 배포의 CloudFront cache policy ID 오류와 CloudFormation의 null ResultPath 오류를 수정했다. 실패한 사용 전 앱 스택만 삭제·재생성했으며 base 데이터와 다른 프로젝트는 유지했다. [실패 기록](../../evidence/serverless-deployment/app-create-failure.json)을 보존했고 최종 app은 UPDATE_COMPLETE, Runtime READY, CloudFront Deployed다.
