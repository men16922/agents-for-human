# 개발 착수 전 준비와 초안 확정

2026-09-06. 최종 증거: [개발 준비 검증](../test/development-readiness.md). 사용자 목표: 초안을 최종 정리·최적화하고 실제 개발 전 환경을 갖춘다. 기능 구현의 시작점은 CW00이며, 이 문서는 그 이전의 문서·도구·실행 기반을 다룬다.

## 완료 증거

| 항목 | 완료를 입증할 증거 |
|---|---|
| 최종 초안 | 최신 HTML과 상세 계획의 목표·용어·범위·일정 일치, 이전 제안 보관, 공식 심사 기준과 데모 연결 |
| 재현 가능한 의존성 | Python/Node 고정 버전, uv/npm lock, 저장소 전용 설치, lock 변경 없는 재설치 |
| 개발 시작점 | Python 패키지·HTTP health·React/TypeScript 개발 셸의 import/typecheck/build/로컬 기동 |
| 독립 거래 환경 준비 | 전용 PostgreSQL/Redis, Medusa core 고정 버전·마이그레이션·health 확인. 주문 전이는 CW00 이후 |
| 안전한 반복 실행 | loopback 바인딩, 전용 Compose 프로젝트, 기존 서비스 비간섭, 비밀값 미추적, 기동·종료·재기동 확인 |
| 검사 경로 | 문서 gate, 개발 도구 검사, 브라우저 검증, 누락 시 실패하는 사전 점검, 검증 명령·결과 기록 |
| 인수인계 | README 빠른 시작, 환경 변수 예시, 명령·포트·문제 해결, 최신 brief/status/plan |

완료 판정은 실제 명령과 런타임 결과에 근거한다. 로컬 환경 준비는 Strands 모델 호출, 거래 엔진, 외부 전이 성공, AWS 배포 또는 실제 운영의 완료가 아니다.

## 작업 순서

1. 기획의 용어·심사 기준·데모·일정을 통일한다. 이전 파일은 지우지 않고 보관한다.
2. 저장소 전용 Python/Node와 lock 기반 의존성 설치 경로를 만든다. 전역 Node/Conda 설정을 바꾸지 않는다.
3. 도메인 기능 없는 health API와 React 개발 셸을 둔다. 독립 Medusa는 실제 core 패키지로 준비한다.
4. 기존 Docker 서비스의 포트를 피하고 PostgreSQL/Redis를 저장소 전용으로 기동한다. Medusa 마이그레이션·health 확인 후 종료한다.
5. 재설치·재기동과 문서/도구/브라우저 검사를 수행한다. 제품 구현 항목은 완료로 처리하지 않는다.

## 사전 조사와 선택

- Python 3.12.13, Node 22.23.2를 저장소에 격리한다. Strands Python은 3.10 이상, Medusa는 LTS Node 20.19+/22.12+를 요구한다.
- 현재 시스템 Node 26을 그대로 사용하지 않는다. 전용 실행 wrapper가 고정 Node를 선택한다.
- React 웹 앱과 Medusa의 관리자 의존성은 npm workspace에서 각각 관리한다. 관리 UI는 이번 환경 준비에서 비활성화한다.
- SQLite는 자체 세계용 Python 표준 라이브러리 경로, PostgreSQL/Redis는 독립 Medusa 개발 환경이다. 기존 다른 프로젝트 DB를 재사용하지 않는다.
- 모델 ID·AWS 권한·리전별 지원은 실제 모델 연결 단계에서 확인한다. 설정 예시는 제공하지만 존재하지 않는 권한을 준비 완료로 표시하지 않는다.

출처: [Strands Python](https://strandsagents.com/docs/user-guide/quickstart/python/), [Medusa 설치](https://docs.medusajs.com/learn/installation), [Node 22 배포](https://nodejs.org/download/release/v22.23.2/).
