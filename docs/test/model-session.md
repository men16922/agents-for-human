# 외부 모델 실행을 위한 Medusa 세션

2026-09-09. [계측 HTTP 실행자](metered-http-model.md)에 새 Medusa run의 수명·구매자 설정 전달·종료 시 증거 export를 연결했다. 세션 제어자는 모델을 호출하지 않는다. 실제 모델 호출과 학습 정책 전이는 여전히 미검증이다.

## 실행 방법

먼저 모델 ID·단가/출처·예산을 준비한다. 기본 preflight는 설정만 검사하며 외부 run/클라이언트/시계를 만들지 않는다. 현재 설정 누락에서는 exit 2이며, 실제 실행 준비 완료로 표시하지 않는다.

```sh
make commerce-model-session-preflight
```

설정이 준비된 뒤 터미널 A에서 `make commerce`로 전용 Medusa를 기동한다. 터미널 B에서 아래 명령으로 새 세션을 열면 seller/gateway를 유지하고 `buyer-config.json` 경로를 출력한다. 선택한 학습 정책을 사용할 경우 `--policy <frozen-policy.json>`을 함께 지정한다. 생략하면 명시적 기본 Policy를 동결한다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python scripts/commerce/model_session.py --serve
```

터미널 C에서 출력된 구매자 설정으로 실행한다. **`--execute`는 별도의 명시적 모델 호출**이다. 실제 입력의 목표·기한은 서버와 일치해야 하며, 운영 시계는 세션 준비 이후 계속 진행한다. 기한이 지나거나 이미 사용한 run을 되감아 재사용하지 않는다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.commerce.model_runner --config '<printed-buyer-config.json>' --execute
```

구매가 끝났거나 중단할 때 터미널 B에서 Ctrl+C를 누르거나 아래 stop 요청을 보낸다. stop 요청 자체는 프로세스 생존/종료의 증거가 아니므로 session 상태, 실제 프로세스와 포트를 대조한다. 세션 제어자는 별도로 실행한 구매자 프로세스를 종료하지 않는다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python scripts/commerce/model_session.py --stop '<printed-session-directory>'
```

세션은 마지막 조회 후 소유한 gateway/seller를 정지하고 원장/실제 Medusa 주문을 export한다. `evidence.json`과 `selection.json`을 저장한다. `.local/commerce-model/<run_id>/execution-manifest.json`이 준비됐다면 실행 주문과 독립 원장을 대조한 `attestation.json`도 저장한다. 없으면 NOT_READY다. 마지막에는 터미널 A의 Medusa도 Ctrl+C로 종료한다. 데이터·볼륨·미확정 예약은 보존한다.

프로세스 종료와 거래 완료는 별도다. 세션이 STOPPED여도 원장은 INCOMPLETE/UNKNOWN일 수 있다. 종료 export는 해당 시점의 관측이며 외부 요청의 이후 확정이나 취소·환급을 보장하지 않는다. 시작/내보내기 실패에도 이미 시작한 소유 프로세스를 정리하고, 정리하지 못한 자식이 있으면 CLEANUP_FAILED로 남긴다. 같은 프로세스에 반복해서 종료 신호가 와도 정리 절차를 중단하지 않는다.

## 설정과 권한 경계

`buyer-config.json`에는 run ID, 구매자 토큰, 기대 목표/예산, 상대 정책 경로만 넣는다. 다른 고객·판매자·관리자·control 토큰은 전달하지 않는다. 파일 권한은 0600, 세션 폴더는 0700이며 Git 제외 `.local/commerce/<session-id>/model-session` 아래에 둔다. 제공한 동결 정책은 원본 bytes/ID를 유지한다. 토큰은 stdout/session 보고서에 넣지 않는다.

`--fixture-serve`는 모델 설정 없이 로컬 진단용 세션을 여는 명시적 옵션이다. 그 자체로 모델을 호출하지 않으며 이번 실측에 이 모드를 사용했다. `--serve`의 설정 검사를 조용히 우회하거나 실제 모델 검증으로 사용하지 않는다. 빈 포트인지 확인한 후 새 fixture를 만들며 기존 프로세스나 run을 재사용하지 않는다.

## 검증 결과

| 실제 세션 | 구매 실행 | 종료 판정 | 실행 연결 |
|---|---|---|---|
| `cw00-4aa4645911df` | 별도 프로세스의 SDK fixture, 14호출/280토큰/13도구/가상 392 micro-USD | COMPLETE 310·예약 0 | 주문 ID와 원장 일치, VERIFIED |
| `cw00-2c447f003ed1` | 없음, 기존 동결 정책 bytes를 전달받아 대기 후 종료 | INCOMPLETE 0 | NOT_READY |

두 세션 모두 제어자의 모델 호출은 0이다. 두 번째 세션은 첫 번째의 정책 파일을 입력받았으며 초기 지출/수령 없이 시작했다. stop CLI 요청으로 자식 종료·원장 export·구매자 설정과 역할 경계를 확인했다. 실제 모델이 아닌 SDK fixture 구매이므로 사용자 설정/모델 호출의 정식 통과 사례가 아니다.

[보존 증거](../../evidence/cw05-model-session/artifact-manifest.json)는 17개 artifact와 별도 manifest다. 각 세션 보고서·원장·선택/판정·동결 정책·HTTP 응답, 첫 세션의 실행 보고서/trace를 포함한다. 구매자 비밀 설정은 제외했고 실제 토큰 문자열 미포함을 대조했다. 보존 export와 실행 기록으로 독립 판정을 재수행했다. 소유 서비스 종료 후 포트 18001/19000/55432/56379, 기존 컨테이너 4개·전용 볼륨 2개 보존을 확인했다.

전용 회귀 11개로 무호출 preflight·buyer-only/파일 권한·정상 종료·미시작 실행·자식 실패·부분 시작 실패·export/metadata 기록 오류·stop marker symlink·반복 신호를 검사했다. 보존된 실제 재고 경합 원장의 UNKNOWN/예약 310도 종료 후 그대로 남는지 대조했다. 이는 새 실제 경합이나 종료 중 외부 요청의 모든 순서 검증은 아니다.

실측 후 실패 출력 검사에서 자식 정리에 실패해도 마지막 메시지가 STOPPED인 결함을 발견했다. 재현한 테스트 실패를 고쳐 실제 상태(CLEANUP_FAILED)를 출력하도록 했다. [실측 소스](../../evidence/cw05-model-session/executed-session-source.txt)와 [출력만 바뀐 diff](../../evidence/cw05-model-session/post-run-status-label.diff.txt)를 보존했다. 변경 후 `make check`는 Python 423개·mypy 46소스·ruff·lock·웹 빌드 통과, 기존 TestClient 경고 2개 유지다. 브라우저는 이번에 실행하지 않았다.

[B3 한 건의 학습/외부 실행 합산 원장·한도·분모](learning-http-budget.md)는 이어서 검증했다. 학습 증빙이 있는 정책의 구매 실행에는 원래 B3 디렉터리를 `--learning`으로 지정해야 한다. 전체 비교 roster 연결은 남았다. 이벤트 관측 큐 기반 모델 재판단과 실제 모델/미공개 비교도 남았다. Linux 의존성 다운로드·설치는 별도 자동 승인 거절 후 허용 응답 대기 상태다.
