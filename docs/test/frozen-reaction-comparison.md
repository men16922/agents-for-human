# 관측 반응 설정을 학습 전 비교 명부에 고정

2026-09-09. [선택 관측 반응 실행](observed-change-replanning.md)을 CW07 외부 비교 명부와 연결했다. B0 고정 규칙은 유지하고, B1·B2·B3의 반응 상한을 동일하게 선언한다. 실제 Medusa 네 실행에서 조건·거래·사용량을 대조했다. 알려진 SDK fixture의 연결 검사이며 학습 전이·Peer Review 효과·미공개 성능 비교는 아니다.

## 설정이 적용되는 범위

새 외부 명부는 `external_reactions`를 명시한다. 아래 설정은 **외부 평가 실행**에만 적용하며 연습/학습 방식을 바꾸지 않는다. B0는 항상 `null`, 모델 세 방식은 모두 `null`이거나 같은 1~32 재판단 상한이어야 한다.

```json
{
  "external_reactions": {
    "B0": null,
    "B1": {"max_replans": 8},
    "B2": {"max_replans": 8},
    "B3": {"max_replans": 8}
  }
}
```

이 필드는 명부의 content hash/ID에 포함된다. 학습 전 `batch-spec.json`과 외부 실행의 `execution/spec.json`에도 해당 방식의 설정을 기록한다. 실행 함수는 명부에서만 값을 읽는다. 설정 누락·추가 키·잘못된 범위·서로 다른 모델군 설정·B0 활성화를 거절한다. 일반 연습 배치에는 이 설정을 사용할 수 없다.

실제 모델용 CLI는 기존 [외부 배치 준비 절차](external-comparison-budget.md)의 `--prepare`에만 `--max-replans 8`을 받는다. `--learn`, `--execute`, `--settle`, `--report`에서 이 옵션을 덮어쓸 수 없다. 예를 들면 다음과 같다. 이 명령은 설정된 실제 모델 명부를 준비할 뿐 HTTP/AWS/model 호출은 하지 않는다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.external_batch --prepare --cases .local/external-cases.json --batch-budget-usd 0.5 --max-replans 8
```

기존 명부에 필드가 없으면 당시 비반응 실행으로 읽는다. 과거 명부/보고서에 새 설정이나 통계를 삽입하지 않는다. 보존된 이전 알림 배치의 독립 재요약이 원래 보고서와 그대로 일치하는 회귀를 두었다.

## 종료 후 판정과 회계

독립 정산은 명부·학습 전 명세·실행 명세·반응 보고서의 설정과 상한을 대조한다. 완료된 반응 실행에는 종료된 관측 worker와 봉인된 관측 artifact가 있어야 한다. 반응 설정·관측 파일이 바뀌거나 누락되면 거래 export가 있어도 정상 정산하지 않는다. 기존 실패 분모와 비용 예약을 유지한다.

새 명부의 요약은 칸별 설정과 `reaction_execution_verified`를 표시한다. 이 값은 해당 반응 설정의 실행/관측 기록이 맞는지 나타내며 거래 성공·초기/이벤트 조건 일치·모델 효과와 별도다. B0와 미실행 칸은 false다. 실제 모델 효과·미공개 평가 표시도 계속 false로 둔다.

B2/B3는 학습 원장을 이어 쓰며 기존 호출/도구/토큰/비용 한도를 재설정하지 않는다. 회귀에서 B3 학습 22호출 뒤 총 23호출 상한을 주면 외부 모델은 1회만 호출되고 구매 POST는 0회였다. 외부 usage 누락 때는 학습 비용 616과 배치 예약 99,384 micro-USD를 유지하며 다음 칸의 실행을 거절했다. 모두 가상 SDK 단가 검사다.

## 실제 Medusa 네 실행

`make commerce`와 `make external-reaction-smoke`를 실행했다. 명부 `reaction-batch_364703e5bcc54663a4e107fd0801269a`는 한 조건 × 네 방식의 4칸이다. 각 새 세션에서 초기 조건과 10tick A 텐트 재고 감소를 원시 Store/Admin 응답으로 검증했다.

SDK 외부 구매자는 A 견적 뒤 12초 지연된 응답으로 오래된 A 주문을 요청하고, 차단 뒤 B 견적/주문/지급을 요청하는 같은 알려진 스크립트를 쓴다. B0는 이 모델 지연 없이 기존 고정 규칙을 실행한다. 따라서 아래 지출 차이는 재판단 또는 학습의 효용 비교가 아니다. SDK 외부 스크립트가 학습된 정책의 품질을 평가한 것도 아니다.

| 방식 / 세션 | 학습 + 외부 SDK 호출 | 전체 토큰 / 도구 | 가상 micro-USD | 독립 거래 | 반응 실행 / 조건 |
|---|---:|---:|---:|---|---|
| B0 `cw00-533cbfdbae09` | 0 + 0 | 0 / 20 | 0 | COMPLETE 310 | 비활성 / true |
| B1 `cw00-3b85b9493017` | 0 + 9 | 180 / 8 | 252 | COMPLETE 380 | true / true |
| B2 `cw00-940d3b623a40` | 23 + 9 | 640 / 30 | 896 | COMPLETE 380 | true / true |
| B3 `cw00-49c149599845` | 22 + 9 | 620 / 26 | 868 | COMPLETE 380 | true / true |

세 모델 방식 모두 대기 중 변경된 A 재고를 담은 커서 11/12를 수신했다. 각 재판단 5회·fresh 조회 13회·오래된 A 집행 차단 1회·실제 B 주문/지급 각 1회·최종 커서/버전 27이다. 원래 학습 호출/도구/거절 목록이 종료 원장의 앞부분에 그대로 남는지도 대조했다.

전체 4 VERIFIED, 조건 일치 4건·반응 실행 검증 3건이다. SDK 72호출·1,440토큰·전체 84도구·가상 2,016 micro-USD, 비용 예약 0이다. 이 한 조건의 알려진 실행으로 성공률이나 Peer Review 효용을 추정하지 않는다.

[보존 manifest](../../evidence/cw07-reactive-comparison/artifact-manifest.json)는 119개 artifact와 별도 manifest를 포함한다. 명부 SQLite·학습/실행·원시 초기/이벤트/거래 증거·관측/구매 HTTP·소스·로그를 보존하고 복사 명부를 독립 재집계했다. 소스 56개 hash·실제 자격증명 미포함·포트 18001/19000/55432/56379 반환·기존 컨테이너 4개/볼륨 2개 보존을 확인했다.

추가 회귀 24개와 기존 외부 배치 검사를 합쳐 60개가 통과했다. `make check` PASS: Python 632개·mypy 56소스·ruff·lock·웹 빌드, 기존 TestClient 경고 2개 유지. 실제 모델·브라우저·AWS·설치·커밋·푸시는 수행하지 않았다.

후속 [CW06 반응 기록 UI](execution-reaction-ui.md)는 보존 기록/API/브라우저와 실제 SDK/Medusa 동시 실행으로 검증했다. 실제 모델 판단 효과와 전체 지연 목표는 별도로 남았다.
