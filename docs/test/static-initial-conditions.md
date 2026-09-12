# 선언한 초기 조건을 실제 Medusa 관측과 대조

2026-09-09. [네 방식의 외부 실행](external-four-arms.md)에 가격·재고·배송비·납기 설정을 적용하고, 실행 전 원시 응답으로 조건 일치를 검증했다. 새 로컬 Medusa 세션 5건에서 초기 조건 일치를 확인했다. 거래 결과는 COMPLETE 4건과 INCOMPLETE 1건이다. 모델 역할은 SDK fixture이며 실제 모델 효과를 측정하지 않았다.

## 적용 범위와 독립 검증

`evaluation/conditions.py`는 목표 품목·수량·수령인·예산·마감, A/B/C의 tent/light 가격·재고, 배송비·납기 설정만 허용한다. 추가 필드와 이벤트·공급자 설명 조건은 비어 있어도 거절한다. 세션 생성과 외부 배치 학습 전에 검사하므로 지원하지 않는 조건을 조용히 무시하지 않는다.

`case_fixture.py`는 새로 생성한 fixture의 variant 가격·재고와 배송 옵션에만 변경을 적용한다. 이후 binding의 목표·예산·납기를 설정하고 판매자와 gateway를 시작한다. 구매자에게 관리자 자격증명을 전달하지 않는다.

초기 증거는 다음 자료를 함께 보존한다.

- 구매자 Store GET의 정확한 6개 variant: USD 계산 가격·가용 재고·재고 관리·backorder 설정.
- 관리자 GET의 정확한 3개 배송 옵션: 단일 USD 고정 배송비·가격 규칙 부재.
- 실제 binding: run·목표·예산·공급처 ID·납기 설정. 납기는 판매자 설정값이며 현실 배송 시간의 실측이 아니다.
- 수집 전후 snapshot과 빈 독립 export: 지출·예약·수령 0, 견적·구매·제출·외부 주문 없음.

수집 구간은 최대 5tick이고 실행 시작은 수집 종료 후 최대 5tick 이내여야 한다. 외부 시계의 1tick은 1초다. 조건이 다르거나 오래되면 실행 칸을 소비하기 전에 거절한다. 실행자도 첫 snapshot에서 신선도를 재확인한다. 조건 증거는 새 파일로 저장하며, 선택된 bytes의 SHA와 독립 판정을 실행 명세에 고정한다. 정산 때 다시 원시 증거를 검증하고 최종 export의 binding까지 대조한다.

이 검증의 범위는 `static-initial-observation-not-atomic-isolation`이다. 여러 GET의 원자적 격리, 수집 직후 다른 주체의 변경 부재, 실행 중 이벤트 조건은 보장하지 않는다. `condition_alignment_verified`는 이 범위의 초기 조건 일치를 뜻하며 거래 성공과 별도로 집계한다. 이전 조건 증거 없는 실행은 계속 false다.

## 실제 검사 결과

`make commerce`와 `make external-conditions-smoke`를 실행했다. 목표는 tent 3개·light 6개, 예산 600, 마감 120tick, 수령인 venue다.

| 공급처 | tent 가격/재고 | light 가격/재고 | 배송비 | 납기 설정 |
|---|---:|---:|---:|---:|
| A | 65 / 0 | 21 / 10 | 11 | 3tick |
| B | 85 / 8 | 25 / 9 | 25 | 7tick |
| C | 100 / 4 | 35 / 7 | 30 | 12tick |

이 조건에서는 B의 총액이 430이다. 별도 불가능 조건은 모든 공급처의 tent 재고만 0으로 바꿨다. 실행 전에 두 조건 × 네 방식의 8칸 명부를 고정했다.

| 조건/방식 | Medusa 세션 | SDK 호출 | 토큰 | 도구 admission | 가상 micro-USD | 독립 거래 판정 |
|---|---|---:|---:|---:|---:|---|
| 변경 B0 | `cw00-eefdd286b077` | 0 | 0 | 20 | 0 | COMPLETE 430 |
| 변경 B1 | `cw00-59cfbd217e48` | 14 | 280 | 13 | 392 | COMPLETE 430 |
| 변경 B2 | `cw00-7a3847796738` | 37 | 740 | 35 | 1,036 | COMPLETE 430 |
| 변경 B3 | `cw00-ee6f231f8c7f` | 36 | 720 | 31 | 1,008 | COMPLETE 430 |
| 불가능 B0 | `cw00-a9ed3be65f59` | 0 | 0 | 10 | 0 | INCOMPLETE 0 |

실행 5건 모두 초기 조건 일치다. 불가능 조건 B1/B2/B3은 NOT_RUN 3건으로 남겼다. 총 87호출·1,740토큰·109도구·가상 비용 2,436 micro-USD이며 학습 비용도 포함한다. 정산 후 모델 비용 예약은 0이다. 실제 모델/API 호출이나 청구값이 아니다.

첫 B0에서는 원시 재고 값을 바꾼 증거를 구매 전에 거절했다. 실제 시계가 신선도 한도를 넘을 때도 실행 디렉터리 생성 전에 거절했다. 살아 있는 세션의 읽기 전용 갱신 요청으로 새 증거를 수집한 후 같은 칸을 정상 실행했다. 최초 증거와 갱신 증거를 모두 보존했다.

원본 배치는 `.local/evaluation/conditions_33b0c0af7c224e86b8277ffe1e20e8d1`이다. [보존 manifest](../../evidence/cw07-static-conditions/artifact-manifest.json)는 122개 artifact와 별도 manifest를 포함한다. 복사 명부 재집계·5개 초기 증거·5개 거래 판정·4개 학습 원장·소스 49개 hash를 대조했다. 실제 자격증명 미포함, 포트 18001/19000/55432/56379 반환, 기존 컨테이너 4개와 볼륨 2개 보존을 확인했다.

## 실행과 재개

[외부 배치 절차](external-comparison-budget.md)로 설정·명부·선택 칸의 학습을 준비한다. 세션의 `--case`에는 명부에서 선택한 조건과 정확히 같은 JSON을 전달한다. 아래 경로는 준비한 실제 경로로 바꾼다.

```sh
scripts/dev/with-env.sh python scripts/commerce/model_session.py --serve \
  --policy <batch>/runs/<cell>/policy.json --case <declared-case.json>
scripts/dev/with-env.sh python scripts/commerce/model_session.py \
  --refresh-conditions <session-directory>
scripts/dev/with-env.sh python -m rehearsal.evaluation.external_batch \
  --execute <batch> --cell <cell> --buyer-config <session-directory>/buyer-config.json \
  --conditions <fresh-conditions-path>
```

갱신 명령은 새 증거 경로를 출력한다. 출력된 파일로 5tick 이내 실행을 시작하며, 오래되면 다시 갱신한다. 갱신은 서버를 재시작하거나 조건을 재설정하지 않는다. 종료/export·독립 정산은 기존 세션/배치 절차를 따른다.

추가 회귀 28개는 원시 가격/재고/배송비/통화/권한 범위/시간/빈 원장 변조, 미지원 조건, 고정 증거 변경, 실행 전 거절과 갱신을 검사한다. `make check`는 Python 498개·mypy 49소스·ruff·lock·웹 빌드 통과다. 기존 TestClient 경고 2개가 유지된다. 이번 브라우저·실제 모델·AWS·설치·배포·커밋·푸시는 수행하지 않았다.

후속 [시간표 이벤트 검사](timed-condition-events.md)에서 가격·재고 변경의 적용 시점과 실제 발생 증거를 연결했다. 이 문서의 이전 실행은 정적 초기 조건 검사로 유지한다. 실제 모델·동등 초기 정책·미공개 조건 비교·Peer Review 효과는 별도 검증 대상이다.
