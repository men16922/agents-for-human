# 두 브라우저의 상태 일치와 개별 복구 — CW06

2026-09-08. 실제 실행 `cw00-a8e25271ce9e`에서 별도 Chromium 프로세스 두 개가 같은 Medusa run을 관측했다. 한쪽만 단절시킨 동안 재고 변경과 납품이 계속 진행됐고, 복구 후 두 화면이 v12/cursor 12/tick 12에서 일치했다. 이는 같은 호스트·같은 브라우저 엔진의 로컬 검사이며 실제 모델 재계획은 포함하지 않는다.

## 재현

터미널 하나에서 `make commerce`를 실행하고 health 준비를 확인한 뒤 다른 터미널에서 실행한다.

```sh
make commerce-convergence-smoke
```

[Python 조정 스크립트](../../scripts/commerce/convergence_smoke.py)는 새 fixture와 전용 observer/API/web를 만들고, [브라우저 검사](../../scripts/commerce/convergence_browser.mjs)를 실행한 뒤 자신이 시작한 프로세스를 종료한다. Medusa는 첫 터미널에서 Ctrl+C로 종료한다. 기존 데이터 볼륨은 유지한다. 모델 호출은 없다.

테스트용 새 run의 observation retention만 8로 설정한다. 기본 1,000을 바꾸지 않는다. 오른쪽 브라우저 context에만 offline을 적용하고 UI의 다시 연결 버튼으로 기존 stream을 끊는다. 복구할 때 online으로 돌리고 같은 버튼을 누른다. 페이지를 새로고침하지 않으므로 해당 브라우저의 cursor와 계측 세션을 유지한다. 이 조합은 명시적인 단절 주입이며 모든 실제 네트워크 장애의 자동 감지를 검증하지는 않는다.

## 실제 결과

| 단계 | 계속 연결한 브라우저 | 단절한 브라우저 | 확인한 근거 |
| --- | --- | --- | --- |
| 초기 | A 텐트 재고 10, 지출 0 | 같은 상태 | 같은 버전의 화면 값 일치 |
| 짧은 단절 | A 재고 10→0 반영 | cursor 2·tick 1·재고 10 유지 | 별도 Medusa 관리자 재고 변경, 멈춘 화면 대조 |
| 짧은 복구 | 변경 상태 유지 | Last-Event-ID 2로 연결, cursor 3·재고 0 | snapshot 없이 이벤트 복구 |
| 긴 단절 | B 380 구매·수령 9·재고 7/4, 시계 진행 | cursor 3·tick 2·지출 0 유지 | 실제 주문·지급·판매자 납품, 멈춘 화면 대조 |
| 보존 범위 초과 | cursor 12까지 진행 | 여전히 cursor 3 | 서버 retained_after 4 > 3, reset=true |
| 긴 복구 | v12/cursor 12/tick 12 | 같은 상태로 snapshot 복구 | 수령·예산·주문·공급자 재고/단가 전체 화면 값 일치 |

계속 연결한 소비자는 observation 12건, snapshot 0, stream 연결 1, disconnect 0이었다. 단절한 소비자는 observation 3건과 snapshot 1건, stream 연결 3, manual reconnect 4, reset_applied 1, reset_skipped_cursors 9를 기록했다. 단절 중 config 요청 재시도를 포함한 disconnect 카운터는 8이다. 의도한 네트워크 단절 2회와 같은 분모가 아니다.

snapshot은 현재 상태를 회복하며 잃은 9개 cursor 구간의 이벤트 이력을 재구성하지 않는다. 그 구간을 수신 성공으로 세거나 0ms 표본으로 채우지 않았다. 두 소비자의 지연 JSON을 별도 보존했다. 중복/역순 주입은 앞선 [지연 계측 실행](observation-latency.md)의 검증 범위다.

최종 화면의 같은 버전 12를 영속 journal에서 직접 읽어 tick·예산·품목별 수령·공급자별 재고·주문 ID/금액/납품/지급 상태와 대조했다. 별도 raw export는 독립 검증기에서 COMPLETE, 지출 380·예약 0·기한 내 텐트 3/조명 6으로 재판정했다. 검사 중 납품 조회 오류는 0건이었다.

## 보존·검증

- [실행 보고서](../../evidence/cw06-convergence/convergence-report.json), [독립 원장](../../evidence/cw06-convergence/convergence-evidence.json), [화면과 대조한 원본 관측](../../evidence/cw06-convergence/matched-observation.json).
- [브라우저 보고서](../../evidence/cw06-convergence/browser/convergence-browser.json), [계속 연결한 소비자 표본](../../evidence/cw06-convergence/browser/latency-0.json), [복구한 소비자 표본](../../evidence/cw06-convergence/browser/latency-1.json), 두 화면과 각 단계의 값은 같은 디렉터리에 있다.
- [SHA-256 manifest](../../evidence/cw06-convergence/sha256.json)의 artifact 15개와 실행 소스 16개를 대조했다. fixture의 observer/buyer/control/Store/admin 토큰이 저장 JSON에 없고, 브라우저 요청에 Authorization 헤더가 없는지 확인했다.
- `make check` PASS: Python 283개·mypy 39소스·ruff·offline lock·웹 빌드. 기존 TestClient deprecation 2개 유지.
- `make check-browser` PASS: 19개. 새 [두 소비자 회귀](../../tests/browser/convergence.spec.ts)는 독립 context의 커서/짧은 복구/retention reset과 한쪽 cross-run 오류가 다른 쪽을 오염시키지 않는지 검사한다. 이 fixture와 실제 Medusa 검사는 별개다.
- 전용 서비스 종료와 18000/15173/18001/19000/55432/56379 포트 반환, `rehearsal-dev` 볼륨 2개·기존 다른 컨테이너 4개 보존 확인. AWS·유료 모델·배포·커밋·푸시 없음.

## 남은 범위

다른 기기/브라우저 엔진·장시간 부하·전체 지연 목표·실제 모델 재계획은 미검증이다. 이번 스크립트는 구매자 하나와 관측자 둘이다. 두 구매자의 재고 경합이나 원자성을 입증하지 않는다. 후속 [두 구매자 재고 경합](concurrent-stock-race.md)에서 단일 Medusa의 checkout 중첩·단일 납품·패자 UNKNOWN 예약 유지를 별도로 검증했다.
