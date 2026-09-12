# 실행 전 영향 보고서 — 구현·AWS·영상 감사

2026-09-12. [완료 기준](../plans/2026-09-12-preflight-impact.md) · [공개 대시보드](https://d1u9yhii3gor6j.cloudfront.net) · [실제 실행 원본](../../evidence/preflight/preview-ed7060a53bc676ce628912b90c666ae9/audit.json).

## 제품과 실행 경계

사용자의 가족 캠핑 요청을 고정했다. 배송비 포함 $200 이내, 텐트 1개·랜턴 2개를 금요일 18시까지 집으로 배송한다. 텐트가 없으면 랜턴만 사지 않는다. 가격/재고/납기는 실제 Amazon 데이터가 아닌 운영자 소유 합성 카탈로그다. 실제 날짜와 별도로 수요일 18시부터 가상 분 시계를 사용한다.

Nova/Strands가 초기 공급자 계획을 제안하고 simulation-only 도구를 호출한다. 서버가 A/B/C×4조건 전체 12칸을 채운다. 각 칸은 같은 동결 snapshot에서 독립 state/journal을 생성한다. 주문·지급·배송 상태 전이를 실제 Python 코드로 실행하며, 모델의 수치 예측을 결과로 쓰지 않는다. 독립 verifier가 원장을 재생해 기한 내 수령·지출·예약·중복을 계산한다.

보고서에서 자동 실행을 멈춘다. 별도 accept는 report/plan hash와 15분 만료를 검사하고 원본을 다시 읽는다. source revision 조건 검사와 decision Put은 같은 DynamoDB transaction이다. 재전송은 원래 brief를 반환하며 시간을 갱신하지 않는다. API가 생성하는 것은 실행 검토용 증빙이지 실결제 승인이나 실제 Amazon 주문이 아니다.

## 실제 AWS/Chrome 결과

실행 ID: `preview-ed7060a53bc676ce628912b90c666ae9`. 실제 Google Chrome `headless:false`, 실제 공개 API·Nova 응답. API mock이나 미리 준비한 UI 결과를 사용하지 않았다. [브라우저 원본](../../evidence/preflight/chrome/browser-report.json)과 [녹화](../../evidence/preflight/chrome/chrome-demo.webm)를 보존했다.

| 계획 | 정상 지출 | 정상 가상 도착 | 충족한 조건/전체 |
|---|---:|---|---:|
| A — 실제 Nova 초기 제안 | $149 | 목요일 18:02 | 2/4 |
| B — 독립 결과 기반 권장 | $179 | 금요일 12:02 | 4/4 |
| C | $129 | 월요일 18:02 | 0/4 |

A 재고 소진/가격 상승은 결제 전 차단됐다. 지급 응답 유실 칸은 지급 확정 뒤 응답만 숨기고 UNKNOWN 예약을 유지한 뒤 같은 주문을 조회한다. 중복 지급 0·최종 미확정 예약 0. 재고·가격 충격은 A에만 적용했다. B 자체의 재고/가격 충격, 실제 운송사·네트워크 장애, 운영 성공 확률은 검증하지 않았다.

실제 Nova 7호출, 입력 16,422/출력 507·총 16,929토큰·모델 비용 추정 $0.006197·미확정 예약 0. 공통 상한 예약은 $0.50이고 기존 총 예산을 늘리거나 초기화하지 않았다. 실행 후 공유 잔여 $3.838425·active 0·27회 입장 잔여. 이전 누계와 합치면 Nova 3,626호출/$4.380601이다. 비용은 원본 usage×설정 단가이며 AWS 최종 청구/인프라 비용은 별도다.

S3 input/raw/최종 보고서를 내려받아 12칸 원장/결과와 hash를 독립 재검증했다. Step Functions `SUCCEEDED`, finalizer의 stop과 별도 `ResourceNotFoundException`/404를 확인했다. 이 preview ID의 commerce table 행은 0개다. PreviewAgentRole의 commerce/seller invoke, commerce Put, input/최종 report/evidence overwrite 거절과 raw write/input read 허용을 [실제 IAM 정책 시뮬레이터](../../evidence/preflight/iam.json)로 확인했다. 정책 시뮬레이션은 공격 모델 효능 검사가 아니다.

별도 preview runtime/IAM/워크플로우를 추가했고 기존 B0–B3 경로는 `?legacy=1`에 보존했다. 함수와 runtime은 실행 시 동작하고, S3/DynamoDB·로그는 보존된다. 새 runtime 로그도 보존 7일로 설정했다. 공개 Chrome 390px 화면에서도 저장된 보고서/결정 복구·가로 넘침 0·쓰기 요청 0을 확인했다. 기존 거래 DB·Medusa/다른 프로젝트는 변경하지 않았다.

## 로컬 검증

- `make check`: Python 740개, mypy 75소스, ruff·lock·문서·웹 빌드 PASS.
- `make check-browser`: 28개 PASS. 신규 3개는 명시적 HTTP fixture로 전체 분모, 상세 지급 증거, 결정/reload, 만료, 모바일 overflow 0, 키보드 조작, 실패 start의 동일 request ID를 확인했다.
- `tests/preflight`: 25개. 실제 상태 전이·격리·템플릿 제약·미완료/변조/누락/중복 증거·동결 계획·부분 구매 차단·만료/원본 변경·원자 결정 경합·재전송·모델 usage 누락을 확인했다.
- SDK fixture에서는 모델이 1칸만 호출해도 서버가 12칸을 채웠고, 초기 A 제안이 독립 B 권장 판정을 덮어쓰지 못했다. 모델 실패/usage 누락 시 evidence 미완료·비용 예약을 보존했다. 이는 실제 Nova 성능 증거와 구별한다.

## 영상과 아키텍처

[제출 MP4](../../submissions/video/rehearsal-demo.mp4)는 173.46초/1920×1080/30fps H.264·AAC, 영어 Daniel·자막 28개다. 영상은 위 실제 Chrome의 요청→Nova→보고서→조건별 상세→accept/export→reload를 편집했고, 원속도 구간과 정지 프레임을 구별했다. 전체 decode·Chromium 재생·8 seek·자막 로드·콘솔 오류 0을 확인했다. 최종 결과/지급/결정 프레임을 육안 대조했다. 음량 −16.03 LUFS·true peak −1.51 dBTP. ElevenLabs 10회/1,914자·응답 헤더 비용 1,052 credits, 실패 자동 재시도 없음. 사람의 전체 청취 평가는 별도다.

[공식 AWS 아이콘 draw.io](../../submissions/architecture/rehearsal-serverless.drawio)·SVG/PNG는 별도 미리보기 권한과 보고서/결정 경계로 갱신했다. diagrams.net 두 페이지 열기·텍스트/경계와 PNG 렌더를 확인했다. 공개 3파일의 bytes/hash가 로컬과 일치한다. 이전 아키텍처·2:30 영상은 `evidence/preflight/previous-*`에 보존했다.

최종 배포 ZIP의 Python 75개가 현재 소스와 일치하고 원본 source hash도 유지됐다. [무결성 manifest](../../evidence/preflight/manifest.json)에 evidence 62개와 source hash를 남겼다. 현재 알려진 비밀값과 새 텍스트 자료를 대조한 일치는 0개다.

## 요구별 대조와 한계

| 기준 | 검증 경로 |
|---|---|
| P01–P04 동결 입력/계획·Nova·격리 실행·영향 보고서 | `src/rehearsal/preflight/`, 25개 회귀, 실제 12칸 재감사 |
| P05 자동 거래 중지·별도 결정/재확인 | 별도 IAM, commerce 0행, accept/download/reload, source race·만료·변조·재전송 회귀 |
| P06 영어 UI·반응형·증빙 | Chrome 실제 실행, 3개 브라우저 회귀와 화면 대조 |
| P07 서버리스·기존 예산·종료 | CloudFormation update, IAM 8검사, S3/DDB/usage·workflow·runtime 404 |
| P08 전체 검사 | `make check`, `make check-browser` |
| P09 제출 이야기·AWS diagram | README/영어 PROJECT/TESTING/ARCHITECTURE/Devpost와 최종 코드/실행 대조 |
| P10 실제 Chrome/Daniel 영상 | raw 녹화·MP4·자막·QA·편집 출처 보존 |
| P11 기록·범위 | 이 감사, brief/status/plan/log 갱신, 아래 미실행 구별 |

요청한 POC 구현·배포·영상·아키텍처 작업과 공개 제출은 별개다. Git commit/push·YouTube 업로드·Devpost Submit은 하지 않았다. 공개 코드/영상 URL·제출자/Builder ID·최종 제출은 남았다. 현재 소비자 시나리오에 맞춰 Devpost 로컬 초안의 트랙을 Everyday Agents로 제안했으며 웹 폼은 변경하지 않았다. [공식 트랙 설명](https://agentsforhumans.devpost.com/).

실제 Amazon 연동, 실제 자금 집행, 운영 예측 정확도, 독립 held-out 일반화, 사용자 의사결정/시간 절감은 완료 주장에 포함하지 않는다. source recheck는 현재 합성 카탈로그에 대한 검사다. 새로운 프로덕션 연결에는 실제 시스템의 최신 조건과 별도 실행 권한을 다시 검사해야 한다.
