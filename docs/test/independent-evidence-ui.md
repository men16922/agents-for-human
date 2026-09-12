# CW06 — 독립 증거 재검증과 관측 비교

## 판정 경계

관측 수령량과 독립 판정은 서로 다른 근거다. `src/rehearsal/evidence_view.py`는 서버가 명시적으로 선택한 Medusa raw export를 매 요청마다 다시 읽고 `verify_medusa`로 판정한다. 파일의 기존 `verdict`·`passed`는 사용하지 않는다. 반환에는 판정·수령/지출/예약·기준 목표/예산·증거 tick·파일/검증기 SHA-256만 포함한다. 고객·주소·외부 주문 전문·토큰·로컬 파일 경로는 브라우저로 전달하지 않는다.

선택 파일은 브라우저 인자가 아닌 `REHEARSAL_EVIDENCE_CONFIG` 환경변수로 지정한다. manifest에는 다음 5개 필드만 허용한다.

```json
{
  "run_id": "선택한-observer-run",
  "expected_goal": {"items": {"tent": 3, "light": 6}, "deadline_tick": 120, "recipient": "venue"},
  "expected_budget": 500,
  "artifact_path": "../observer-evidence.json",
  "sha256": "선택한 파일의 SHA-256 64자리"
}
```

`expected_goal`과 예산은 승인한 run 설정에서 가져오며 export에 들어 있는 기준을 그대로 신뢰하지 않는다. 상대 artifact 경로는 manifest 디렉터리가 기준이다. run은 observer 설정의 run과 같아야 한다. hash 불일치·다른 run·형식 오류는 REJECTED, 미설정은 UNCONFIGURED, 아직 없는 파일은 PENDING이다. VERIFIED는 재검증을 수행했다는 뜻이며 실제 판정은 COMPLETE/INCOMPLETE/FAILED/UNKNOWN으로 나뉜다. 독립 검증의 누락 데이터는 UNKNOWN을 유지한다.

manifest는 16 KiB, export는 8 MiB로 제한하며 중복 JSON 키·안전 정수 범위 밖의 기준·잘못된 goal을 거절한다. 선택 파일은 원자적 교체로 갱신할 수 있다. digest는 로컬에서 선택한 파일을 식별하며 외부 서명이나 제출자의 정직성을 인증하지 않는다.

## 화면

`web/src/Evidence.tsx`는 증거 재검증 버튼과 증거 시점 판정/해시를 제공한다. 현재 run·목표·예산·tick·지출/예약·수령량과 비교해 일치 여부를 표시한다. 실행/기준이 다르거나 관측보다 뒤의 증거, 원장 값 불일치, 현재 관측 미수신은 각각 별도로 알린다. 연결이 끊겼으면 마지막 관측과의 비교임을 표시한다. 과거 COMPLETE를 현재 성공이라고 표시하지 않는다.

재검증을 시작하거나 API/파일 검증이 실패하면 이전 성공 표시를 버린다. UI 판정은 수동 제공자와 가상 크레딧을 쓰는 Medusa 기록의 증거 시점에 한정된다. 실제 물품 수령·실시간 최종성·모델의 학습 효과를 뜻하지 않는다.

## 실행

```sh
REHEARSAL_OBSERVER_CONFIG="/absolute/path/observer-buyer.json" \
REHEARSAL_EVIDENCE_CONFIG="/absolute/path/selection.json" make dev
```

로컬 fixture 전체 재현은 `make commerce`가 실행 중일 때 `make commerce-observer-smoke`다. 이 명령은 승인한 run 설정의 목표/예산과 새 export의 digest로 ignored `browser/selection.json`을 작성한다. 실제 브라우저가 증거 API를 호출하고 B 380·예약 0·목표 수령과 현재 관측의 일치를 확인한다. 두 설정 경로를 공유하거나 공개 웹 디렉터리에 복사하지 않는다.

## 검증 범위

- Python 25개: 보존된 실제 Medusa export 재판정, 고정 run·읽기 전용 경로, private 필드 미노출, 원본 hash 변경, 다른 run, 목표/예산·capture·수령량/receipt 변조, malformed/누락 증거, 파일 제거·선택 갱신 후 성공 재사용 방지.
- 브라우저 3개 추가: run/목표/예산/시점/원장 비교, 과거 성공과 현재 다른 목표 구별, hash 오류로 재검증 실패 시 이전 성공 제거. 기존 9개 관측/제안서 검사도 유지한다.
- 실제 Medusa export → 검증 API → 브라우저 표시 결과와 hash는 실행 기록에 별도로 남긴다. UI fixture가 실제 모델/상거래 성능을 증명하지 않는다.

## 2026-09-08 실제 연결 결과

`cw00-d6c09eac6808`에서 `make commerce-observer-smoke` PASS. 실제 A 재고 감소 후 B 380·예약 0·수령 텐트 3/조명 6의 export를 생성하고, API가 독립 COMPLETE를 다시 계산했다. 브라우저는 증거 tick 23의 판정과 현재 관측 값 일치를 표시했다. [보고서](../../evidence/cw06-evidence-ui/observer-report.json)·[API/화면 판정](../../evidence/cw06-evidence-ui/browser/evidence-browser.json)·[원장](../../evidence/cw06-evidence-ui/observer-evidence.json)·[1440px](../../evidence/cw06-evidence-ui/browser/evidence-1440.png)·[390px](../../evidence/cw06-evidence-ui/browser/evidence-390.png)를 보존했다.

`make check` PASS(Python 255·mypy 38소스·ruff·lock·웹 빌드), `make check-browser` PASS(12개). 브라우저에서 응답을 가로채지 않은 실제 API/Medusa 경로도 검사했으며, 수령 조회 오류 0·브라우저 콘솔 오류 0이다. export와 UI 판정의 digest, 실행 소스 hash, 독립 재판정, 토큰 미포함을 확인했다. 새 서비스를 종료하고 포트 6개를 반환했다. 전용 볼륨 2개·기존 다른 컨테이너 4개는 유지했다. 모델/AWS·실자금·배포·커밋·푸시는 실행하지 않았다.

## 남은 작업

[주문/재고 관측](commerce-observation-details.md)을 추가했다. [지연 표본](observation-latency.md)도 추가했다. 실제 모델 재계획, 전체 지연 목표 평가, B0~B3 비교와 새 조건 평가, 개발자 관찰이 남았다. 증거는 명시적으로 선택한 export이며 자동 live export/배포는 구현하지 않았다.
