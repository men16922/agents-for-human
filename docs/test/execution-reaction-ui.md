# CW06 — 실행자의 판단 기준과 집행 기록

## 읽기 전용 연결

`src/rehearsal/execution_view.py`의 `GET /observer/execution`은 운영자가 선택한 실행 디렉터리를 읽는다. 브라우저의 경로·run 인자는 선택을 바꾸지 못하며 POST는 405다. 모델 응답·공급자 설명·정책·사용량 원문·자격증명·로컬 경로는 반환하지 않는다. 화면에는 고정한 목표/예산과 감사 로그에서 다시 집계한 판단 기준 tick, 추가 판단·집행 차단·재확인·조회 실패 횟수, 소비 cursor/version, 최근 주요 기록 12건만 표시한다.

선택 파일은 Git 제외 경로에 만들고 `REHEARSAL_EXECUTION_CONFIG`로 API 시작 때 지정한다. 목표/예산은 승인한 실행 계약과 대조하고, 선택한 `spec.json`의 실제 bytes로 SHA-256을 계산한다. 실행 디렉터리와 설정을 웹 공개 디렉터리에 복사하지 않는다.

```json
{
  "run_id": "선택한-observer-run",
  "expected_goal": {"items": {"tent": 3, "light": 6}, "deadline_tick": 90, "recipient": "event-venue"},
  "expected_budget": 500,
  "execution_path": "../execution",
  "spec_sha256": "선택한 spec.json의 SHA-256 64자리"
}
```

상대 경로는 선택 파일의 디렉터리를 기준으로 해석한다. `REHEARSAL_OBSERVER_CONFIG`의 run과 같아야 하며, UI는 관측 목표/예산까지 대조한 뒤 기록을 보여준다. 기존 [독립 증빙 설정](independent-evidence-ui.md)은 별도로 사용한다.

```sh
REHEARSAL_OBSERVER_CONFIG="/absolute/path/observer-buyer.json" \
REHEARSAL_EXECUTION_CONFIG="/absolute/path/execution-selection.json" make dev
```

## 임시 기록과 종료 기록

| 상태 | 확인한 범위 | 화면 의미 |
|---|---|---|
| UNCONFIGURED / PENDING | 설정 없음 / 필요한 파일 없음 | 수치 없이 대기 |
| PROVISIONAL | 입력 hash/범위와 완성된 감사 줄 | 임시 기록·종료 미확인 |
| SEALED | 종료 manifest와 spec/report/tools/observations hash, 재집계 수치 일치 | 종료 기록·파일 무결성 확인 |
| REJECTED | 형식·범위·hash·재집계 불일치 | 이전 수치 제거 |

`STARTED` 보고서나 파일의 최근 수정 시각만으로 현재 실행 중이라고 판정하지 않는다. 종료 manifest가 없으면 완료라고 적힌 보고서도 임시 기록이다. 작성 중인 마지막 미완성 줄은 임시 집계에서 제외하며, 봉인된 기록에서는 거절한다. 설정/manifest는 각 16 KiB, 데이터 파일은 각각 8 MiB, 감사 로그는 50,000줄로 제한한다. 중복 JSON 키·안전 정수 범위 위반·다른 목표/run·반응 상한 초과를 거절한다.

종료 보고서의 추가 판단/차단/수신 위치는 감사 로그를 재생한 값과 대조한다. `worker_stopped`도 확인한다. 알 수 없는 오류 원문은 `OTHER`로 제한한다. 해시는 로컬 파일들의 일관성을 확인하며, 외부 서명이나 거래/모델 성공의 증거가 아니다. 판단 횟수는 모델 호출 준비 때 남긴 기록으로, 실제 provider 호출 여부·판단 품질은 별도 검증한다.

UI는 요청이 끝난 뒤 2초 간격으로 다시 읽고 5초 타임아웃을 둔다. API 실패·타임아웃·형식 오류·현재 관측과 다른 실행/목표/예산이면 이전 수치를 표시하지 않는다. 임시 기록이 증가하거나 종료 manifest가 나타나면 다음 조회에서 반영한다.

## 2026-09-09 검증

- `make check` PASS: Python 663개·mypy 57소스·ruff·lock·웹 빌드. Python 31개 추가로 보존된 실제 Medusa B0/B1/B2/B3 기록, 변조/파일 누락·교차 run·입력 범위·재봉인한 잘못된 집계·임시 마지막 줄·비밀 원문 차단·읽기 전용 API를 검사했다. 기존 TestClient 경고 2개 유지.
- `make check-browser` PASS: 25개. 추가 6개는 실제 별도 로컬 API를 통해 보존 기록을 읽었다. 관측 SSE는 보존 snapshot을 재생하며, API를 읽는 요청은 Playwright route로 18002에 전달한다. 새 Medusa 실행이나 실시간 Medusa→SSE 경로를 검사한 것은 아니다.
- B1 기록의 추가 판단 5회·집행 차단 1회·재확인 2회·tick 29/cursor 27을 표시했다. 파일 prefix 증가에서 0/0→0/1, 종료 후 5/1 전환을 확인했다. 종료 한도 사유·변조/연결 실패/5초 정체 후 수치 제거·브라우저 schema 거절을 검사했다.
- 1440/390/320px에서 가로 넘침 없이 렌더링했고 콘솔 오류·브라우저 쓰기 요청은 0이었다. API/웹 자식 종료와 18000/18002/15173 포트 반환을 확인했다.

[보존 manifest](../../evidence/cw06-execution-ui/artifact-manifest.json)에 11개 artifact와 별도 manifest를 남겼다. [보고서](../../evidence/cw06-execution-ui/report.json), [B1 재집계](../../evidence/cw06-execution-ui/B1-summary.json), [데스크톱](../../evidence/cw06-execution-ui/reaction-1440.png), [320px](../../evidence/cw06-execution-ui/reaction-320.png), [임시 기록](../../evidence/cw06-execution-ui/provisional.png)을 포함한다. 기존 [동결 네 방식 원본](frozen-reaction-comparison.md)을 재사용했고 source/input hash로 연결했다. 새 거래·실제 모델·설치·AWS·커밋·푸시는 수행하지 않았다.

## 2026-09-09 실제 SDK/Medusa와 UI 동시 검증

`make commerce`로 전용 Medusa를 시작한 뒤 `make commerce-reaction-ui-smoke`를 실행했다. `reaction-ui_c900888b02084a2d87daa91a028617ae` / `cw00-8eb3dfe3d12a-buyer`가 통과했다. 이번 브라우저는 route 가로채기 없이 실제 API·SSE·실행 기록·독립 증빙 경로를 사용했다. 구매자는 Strands SDK의 알려진 지연 fixture이며 실제 모델 판단은 아니다.

브라우저가 A 재고 10/지출 0의 초기 화면을 확인한 후 구매 실행을 시작했다. 생성된 spec의 hash와 run/목표/예산으로 선택 파일을 원자적으로 연결했다. 첫 판단 tick 1→A 재고 10→0→오래된 A 주문 차단 tick 13→B 주문/지급 직전 재확인 tick 14→수령 텐트 3/조명 6→종료 기록까지 같은 화면에서 확인했다. 주문/지급 POST는 각각 1회였으며, 차단된 A 주문은 POST되지 않았다.

실행 감사와 UI의 최종 추가 판단 5회·차단 1회·집행 전 재확인 2회·판단 기준 tick 30·실행자 cursor/version 28이 일치했다. 별도 브라우저 관측은 계속 진행돼 최종 cursor/version 30에 도달했다. 두 소비자는 다른 역할/조회 시점을 가지므로 커서의 동일성을 요구하지 않는다. 브라우저가 받은 실행 API 상태는 PENDING→PROVISIONAL→SEALED였고, 실제 실행 프로세스가 살아 있는 동안에도 UI는 임시 기록으로만 표시했다.

실행 중 생성한 export와 서비스를 멈춘 뒤 생성한 export를 각각 독립 재검증했다. 모두 COMPLETE 380·예약 0·기한 내 텐트 3/조명 6이었다. 실행의 별도 attestation도 두 export에 대해 성공이며, UI는 독립 증거 시점 COMPLETE와 현재 관측 값 일치를 표시했다. SDK 9호출·180토큰·8도구·가상 252 micro-USD·usage 예약 0이다.

[실제 연결 manifest](../../evidence/cw06-live-reaction-ui/artifact-manifest.json)에 38개 artifact와 별도 manifest를 보존했다. [실행 보고서](../../evidence/cw06-live-reaction-ui/smoke.json), [실시간 브라우저/API 기록](../../evidence/cw06-live-reaction-ui/browser/browser-report.json), [차단 시점](../../evidence/cw06-live-reaction-ui/browser/live-blocked.png), [최종 화면](../../evidence/cw06-live-reaction-ui/browser/live-1440.png), [390px](../../evidence/cw06-live-reaction-ui/browser/live-390.png), 두 export·실행 원장·재고 이벤트·HTTP 기록을 포함한다. 복사본의 실행 요약/두 attestation/조건 이벤트를 재판정하고 소스 73개 hash·실제 자격증명 미포함을 대조했다.

`make check` PASS(Python 663·mypy 57·ruff·lock·웹 빌드). 브라우저 회귀 25개는 직전 UI 단계에서 통과했으며 이번에는 위 실제 연결 검사를 수행했다. 브라우저 API 요청 27건은 모두 GET/Authorization 없음, 콘솔 오류 0·1440/390px 가로 넘침 0이다. Session STOPPED·cleanup 오류 0, 포트 18000/18001/19000/15173/55432/56379 반환·기존 컨테이너 4개/볼륨 2개 보존을 확인했다. 모델/AWS·다운로드/설치·커밋·푸시는 수행하지 않았다.

실제 모델 재계획 효과·학습 전이·전체 지연 목표는 별도로 남았다. 다음은 현 구현과 증거에 맞춰 영어 제출 초안의 아키텍처·재현 경로·시연 범위와 미검증 표시를 갱신한다. 공개·제출이나 실제 모델 성과를 뜻하지 않는다.
