# CW08 — 영어 제출 초안과 구현 증거 맞추기

2026-09-09. README와 영어 PROJECT/TESTING/ARCHITECTURE/VIDEO_SCRIPT/READINESS, standalone SVG를 현재 로컬 구현과 대조해 갱신했다. 최종 제출이나 게시를 수행한 것은 아니다.

## 반영한 내용

- 기존 B0 pilot의 모델군 15개 NOT_RUN과 별도 SDK/Medusa 네 방식 완료 명부를 구별했다. 원래 명부를 채우거나 모델 비교 성과로 바꾸지 않았다.
- 실제 SDK/Medusa와 반응 UI의 A 재고 감소→오래된 주문 차단→B COMPLETE 380, 5회 판단/1회 차단, SDK 9호출·180 fixture 토큰·가상 252 micro-USD를 연결했다.
- 별도 네 방식의 310/380/380/380·72 SDK호출/1,440 fixture 토큰/가상 2,016 micro-USD를 반영했다. 동일한 지연 스크립트와 지연 없는 B0의 차이로 학습·검토 효과를 비교할 수 없다고 명시했다.
- 테스트 안내에 실제 UI smoke·네 방식 smoke·포트/서비스 수명·실행 선택 schema·반응 옵션/공통 학습 원장·paid CLI 단계 구분을 추가했다.
- 아키텍처에 동결 명부·학습/외부 공통 회계·구매자 변화 소비자·집행 전 재확인·임시/종료 기록 API·별도 독립 export API를 반영했다.
- 영상 대본에서 재고 복구와 별도 지급 타임아웃 실험을 같은 실행으로 편집하지 않도록 출처와 표시를 지정했다. macOS 검증을 독립 호스트 재현으로 확대하지 않았고, 기존 스크린샷을 영상으로 표현하지 않았다.

## 검증

현재 파일에서 영어 자료의 상대 링크 47개와 Make target 19개가 존재함을 확인했다. 실제 external batch CLI의 prepare/learn/execute/settle/report 및 반응 옵션 제약을 코드와 대조했다. 기존 네 방식 artifact 119개와 실제 UI artifact 38개의 digest를 다시 확인한 뒤 기록된 수치와 설명을 맞췄다.

`make check-docs` PASS. SVG 43개 텍스트의 canvas 경계를 검사하고 Chromium에서 렌더링해 시각적으로 확인했다. 직접 SVG 파일의 full-page 캡처는 폰트 로드 후 30초 시간 초과였으며, 동일한 SVG를 HTML에 인라인한 캡처는 성공했다. 결과를 [렌더](../../evidence/cw08-submission-refresh/architecture.png)와 [검증 보고서](../../evidence/cw08-submission-refresh/report.json)에 남겼다. SVG 자체를 이미지 생성 도구로 변경하지 않았다.

문서/도식 변경이며 제품 코드·원래 거래 증거는 변경하지 않았다. 이번에는 Python/전체 브라우저 gate·모델·Medusa·Linux 설치·규칙 웹 재조회·커밋·푸시·게시를 실행하지 않았다. 직전 제품 gate는 Python 663·mypy 57·브라우저 25개와 별도 실제 SDK/Medusa/UI 연결 통과다. READINESS의 규칙 확인 날짜는 이전 2026-09-08 기록임을 유지했다.

다음은 현재 로컬 도구로 실제 SDK/Medusa 화면을 녹화하고 영어 설명/한계 표시를 넣는 영상 초안이다. 실제 모델 효과·새 조건 평가·개발자 관찰·Linux/독립 호스트 재현·공개 저장소/영상·최종 제출은 남았다.
