# 수정 B0의 Medusa 재검증

2026-09-09. [known pilot에서 수정한 B0](shared-limits-and-pilot.md)를 실제 로컬 Medusa에서 재실행했다. 기존 3조건의 연습/Medusa 결과를 유지하고, 필수 품목이 없는 새 조건에서도 불필요한 부분 구매를 중단했다. 고정 규칙의 계약 검증이며 학습된 정책이나 실제 모델 성과는 아니다.

## 범위와 결과

`make commerce`로 전용 환경을 준비하고 `make commerce-transfer-smoke`를 실행했다. 스크립트에 `revised-unavailable-item` 조건을 추가했다. 모든 공급자의 텐트 재고가 0이고 조명은 구매 가능하다. 장애 운영자가 실제 inventory location API로 재고를 변경한 뒤, B0는 기존 구매 도구로 받은 견적만 사용했다.

| 알려진 조건 | 연습 판정/지출/도구 | 실제 Medusa 판정/지출/도구 |
|---|---|---|
| 갱신 없음·A 가격 변경 | INCOMPLETE / 0 / 5 | INCOMPLETE / 0 / 5 |
| 갱신·가격 변경·지급 응답 유실 | COMPLETE / 380 / 20 | COMPLETE / 380 / 20 |
| 공급처별 가능한 부분 조달 | COMPLETE / 360 / 47 | COMPLETE / 360 / 47 |
| 필수 텐트 없음·조명 구매 가능 | INCOMPLETE / 0 / 10 | INCOMPLETE / 0 / 10 |

마지막 조건에서 실제 재고 0 변경 POST 세 건이 HTTP 200이었다. 조명 견적 130/170/225는 유효했지만 필수 텐트 견적을 확보하지 못했다. B0는 NO_EXECUTABLE_QUOTE로 종료했고 create_order/authorize_payment 호출이 없었다. 원장과 독립 판정에서도 지출 0을 확인했다. 이 결과는 그 시점의 가시 견적에 관한 판단이며 영구적인 조달 불가능성이나 전역 최적 계획을 뜻하지 않는다.

가격 변경/유실 조건의 지급 요청은 한 번이고 같은 주문 조회로 복구했다. 부분 조달은 조명 170과 텐트 190의 합계 360이며 이미 수령한 물품을 중복 구매하지 않았다. 연습과 Medusa가 같은 새 frozen ID를 사용한다. 실행 소스가 달라졌으므로 과거 동결 ID를 재사용하지 않았다.

## 증거와 검증

원본 실행: `.local/transfer/b0_3b354a081bf0431baf36a597382de888`.

- [8개 실행 결과](../../evidence/cw05-b0-rerun/results.json), [전체 보고서](../../evidence/cw05-b0-rerun/report.json).
- [보존 artifact hash](../../evidence/cw05-b0-rerun/artifact-manifest.json): 25개 파일과 별도 manifest. 정책 2개·각 실행 보고서/trace/raw export·Medusa fixture HTTP 4개·정리 기록 포함.
- [필수 품목 부족의 실제 HTTP](../../evidence/cw05-b0-rerun/revised-unavailable-item/medusa/fixture-http.json), [해당 원장](../../evidence/cw05-b0-rerun/revised-unavailable-item/medusa/evidence.json).
- [정리 기록](../../evidence/cw05-b0-rerun/cleanup.json).

보존한 raw export 8개를 각각 독립 검증기로 다시 읽어 판정·지출을 대조했다. 정책/소스 hash와 하위 보고서/증거 hash를 확인했다. `make check`는 Python 386개·mypy 45소스·ruff·lock·웹 빌드를 통과했다. 기존 TestClient 경고 2개는 유지된다. 브라우저 gate는 이번에 실행하지 않았다.

처음에는 Docker 엔진이 꺼져 있어 설치된 Docker Desktop을 기동했다. 그 과정에서 기존 컨테이너 4개가 자동 기동됐으며 변경하거나 종료하지 않았다. 검사가 끝난 뒤 소유한 gateway/seller/Medusa와 rehearsal-dev Compose 서비스만 종료했다. 포트 18001/19000/55432/56379 반환, 전용 볼륨 2개의 생성 정보·경로 보존, 기존 컨테이너 ID 4개 유지를 대조했다. Docker 엔진은 실행 상태로 두었다.

실제 AWS/모델 호출·실자금 지급·분산 경합·영상·배포·커밋·푸시는 수행하지 않았다. 모델 설정이 준비되면 CW03 실제 호출부터 진행한다. 대기 중에는 CW08/CW09의 격리된 Linux 환경 재현과 제출용 소스/설정 경계를 점검한다.
