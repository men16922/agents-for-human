# CW06 — 읽기 전용 거래 관측실

## 구현 범위

React 셸을 로컬 관측 화면으로 연결했다. `src/rehearsal/observer_view.py`는 고정 `127.0.0.1:18001`의 선택한 run에서 observations/SSE만 읽는다. `REHEARSAL_OBSERVER_CONFIG`가 가리키는 파일에는 `run_id`와 observer 토큰만 허용하며, 브라우저에는 run ID와 연결 여부만 전달한다. URL·run·Authorization·cookie를 사용자 요청에서 upstream으로 전달하지 않는다. redirect·비정상 응답은 일반 오류로 처리한다. JavaScript와 서버 커서는 안전한 정수 범위로 제한한다.

`web/src/observation.ts`의 소비자는 부분 SSE 프레임, 중복·역순·retention snapshot, run/이벤트 내용/동일 버전 충돌을 검사한다. 재접속은 마지막 커서를 사용하며, 오류 시 마지막 상태를 보존한다. 내용 검증 실패는 자동 재시도를 멈추고 사용자의 다시 연결을 기다린다. 최근 이벤트 지문 1,000개·화면 기록 30개·미완성 프레임 1 MiB를 상한으로 둔다.

지도·수령량·spent/reserved/available·tick은 snapshot에서 가져온다. 후속 [주문/재고 관측](commerce-observation-details.md)에서 가용 재고·개별 주문 상태를 추가했다. 지도 연결선은 개별 주문 경로가 아니다. 지도 연결선은 구조만 뜻한다. 5초 이상 고객 조회가 없거나 upstream 오류/연결 끊김이면 이전 관측이라고 표시한다. 목표 수량을 채워도 `관측상 수령 충족`이며, 별도 증거를 선택하기 전에는 `독립 원장 검증 전`을 유지한다. 선택한 raw export의 [독립 재검증 UI](independent-evidence-ui.md)를 추가했으며 현재 관측과 증거 시점은 구별한다.

지연값은 마지막으로 적용한 관측의 `observed_at`부터 React commit 이후 두 번째 animation frame까지의 로컬 시계 차이다. 외부 거래 발생 시점부터의 종단 지연·분포·목표 달성 증거는 아니다. 시계가 역전되면 `시계 차이`로 표시한다. UI는 구매·관리자 명령·모델 호출을 수행하지 않는다.

## 로컬 실행

`make dev`는 observer 설정이 없으면 빈 상태와 health 연결을 보여 준다. 기존 Medusa fixture 준비 함수는 ignored run 디렉터리에 `operating/observer-buyer.json`과 `observer-other.json`을 0600 권한으로 생성한다. 선택한 run의 gateway와 독립 판매자가 실행 중인 상태에서 다음과 같이 연결한다.

```sh
REHEARSAL_OBSERVER_CONFIG="$PWD/.local/commerce/<run-id>/operating/observer-buyer.json" make dev
```

서비스는 loopback만 사용한다. 브라우저 주소는 `http://127.0.0.1:15173`이다. 토큰 파일을 웹 디렉터리나 증거 보존 디렉터리로 복사하지 않는다. 공개 호스팅·원격 다중 사용자 접근은 이 구성의 범위에 없다.

재현 가능한 실제 거래 검사는 별도 터미널의 `make commerce`를 전제로 한다.

```sh
make commerce-observer-smoke
```

이 명령은 새 fixture의 A 텐트 재고를 낮추고 기존 견적의 주문 거절을 확인한 뒤, 스크립트로 B를 구매한다. 자체 gateway/API/web/Chromium을 시작해 초기 0 → 수령 9·지출 380 → gateway 중단 → 커서 재접속을 검사한다. 종료 시 자신이 시작한 프로세스만 종료하고 SQLite·Medusa DB·볼륨을 보존한다. 실행 중에는 같은 포트를 쓰는 `make check-browser`/`make dev`를 함께 시작하지 않는다.

## 검증

- 브리지 회귀 18개: 미설정·읽기 전용 경로, 고정 URL/run·서버 토큰, credential 미반사, redirect/잘못된 upstream 거절, 안전 커서, SSE chunk·연결 종료/오류 정리.
- 브라우저 묶음 9개: 기존 3개 + SSE 프레이밍/Projection 3개 + UI 3개. 미설정, 중복·역순·reset·충돌, 커서 재연결, 끊김 보존, 320/390/1440px overflow와 콘솔 오류를 검사한다.
- 실제 Medusa/브라우저 결과와 증거 경로는 아래 실행 기록에서 구분한다. 브라우저 fixture를 실측 거래나 모델 효과로 계산하지 않는다.

## 2026-09-08 실제 실행

최종 `cw00-3f3dac1b04a9`는 PASS다. [보존 보고서](../../evidence/cw06-observer/observer-report.json)·[독립 원장](../../evidence/cw06-observer/observer-evidence.json)·[브라우저 요청/최종 상태](../../evidence/cw06-observer/browser/browser-report.json)·[화면 1440px](../../evidence/cw06-observer/browser/live-1440.png)·[390px](../../evidence/cw06-observer/browser/live-390.png)를 남겼다. A 텐트 재고 10→0 후 기존 견적 주문은 거절됐고, B 구매는 독립 COMPLETE 380·예약 0·수령 텐트 3/조명 6이다. 화면의 가용 예산은 120이다. gateway 중단 시 마지막 수령 상태를 유지하고 cursor 19에서 다시 연결해 20을 수신했다. 브라우저 요청에는 Authorization이 없다.

수령 화면에서 마지막 관측→화면 반영은 460ms, 재접속 직후는 948ms였다. 각 한 시점의 최신 관측 값이며 납품 발생부터의 지연 표본이나 목표 달성을 뜻하지 않는다. JSON/이미지 hash manifest와 코드 hash를 보존·대조했고, 별도 원장으로 COMPLETE를 다시 계산했다. 저장 파일에 이번 fixture의 observer/buyer/control/Store/admin 토큰이 없는지 확인했다.

앞선 두 실행도 숨기지 않았다. `cw00-4929ed5f3338`은 브라우저까지 통과했지만 독립 검증 호출의 필수 인자 누락으로 스크립트가 실패했다. `cw00-c0982f557ab7`은 납품 조회에서 `EXTERNAL_DELIVERY_MISMATCH`로 중단됐고, 이후 Store HTTP 조회는 정상 수량이었다. 당시 불일치 응답 전문은 없으므로 정확한 중간 필드 상태는 확정하지 않는다. [실패 보고서](../../evidence/cw06-observer/delivery-read-failure/observer-report.json)와 [후속 원본 조회](../../evidence/cw06-observer/delivery-read-failure/delivery-diagnostic.json)를 보존했다. gateway의 불일치 거절은 유지하고, smoke만 오류를 기록하면서 GET 수령 조회를 25초 내 재시도하도록 바꿨다. 구매·결제 POST는 재실행하지 않는다. 최종 실행의 read 오류는 0회다.

최종 gate는 `make check`(Python 230·mypy 37소스·ruff·lock·웹 빌드)와 `make check-browser`(9개)다. 실제 서비스 실행 중 같은 포트로 browser gate를 시작한 시도는 점유 오류로 거절됐으며, 서비스 정리 후 다시 검사했다. 18000/15173/18001/19000/55432/56379 포트 반환과 전용 볼륨 보존을 확인했다. 모델·AWS·실자금·배포·커밋·푸시 실행은 없다.

## 남은 범위

[지연 표본 분포](observation-latency.md)는 후속 구현·실제 실행으로 검증했다. 외부 변화에 따른 실제 모델 재계획과 전체 지연 목표 평가는 남았다. 현재 실제 구매는 알려진 조건의 스크립트 실행이다.
