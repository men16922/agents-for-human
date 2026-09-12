# Pilot 준비용 토큰·실행 시간 보고서

2026-09-12. 기존 practice 배치에는 비용·도구 수가 있었지만, pilot에서 다음 평가 예산을 정하는 데 필요한 총 토큰과 실행 시간 비교 표가 없었다. 이를 원본 사용량·단조 시계 기록과 연결했다. **보고서 기능의 오프라인 검증이며 실제 모델 pilot을 수행한 것은 아니다.**

## 동작과 범위

- `batch.run_pending`은 학습·평가를 포함한 한 셀의 시작/종료 `perf_counter_ns`를 `timing.json`에 기록한다. 이 파일은 기존 artifact hash 감사에 포함한다. 배치 준비·최종 집계 시간은 제외하며, provider 지연·복구 시간·UI 지연으로 부르지 않는다.
- 토큰은 각 원본 RECORDED 호출의 입력·출력·cache read/write를 재합산하고 저장된 총합과 대조한다. B2/B3의 학습과 평가를 함께 포함한다. 미확정 usage는 불완전 표본으로 남긴다.
- 새 읽기 전용 CLI는 네 방식의 전체 분모·상태·목표 완료·토큰/모델/도구 호출·기록 비용/미확정 예약·시간 표본 수·중앙값/p95를 JSON 또는 Markdown으로 출력한다.
- 미실행·중단·손상된 증거는 시간/토큰 0으로 바꾸지 않는다. 실패로 종료한 셀의 유효한 소요 시간은 표본에 포함한다. 과거의 wall-clock 시각만으로 새 단조 시계 시간을 합성하지 않는다.
- 현재 대상은 `rehearsal-evaluation-batch-v1`의 practice 배치다. 원래 B0-only pilot, 외부 Medusa 배치 또는 개발자 관찰을 합친 결과가 아니다.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.metrics .local/evaluation/<batch-directory>
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.metrics .local/evaluation/<batch-directory> --format json
```

## 검증

`make check` PASS: Python 675개·mypy 58소스·ruff·lock·웹 빌드. 전용 회귀 12개와 기존 배치 18개를 통과했다. 고정된 두 단조 시계 구간으로 중앙값/p95를 확인했고, 미실행·usage 누락·중단·일반 오류·과거 기록·토큰 합계 및 시간 변조를 검사했다. artifact hash를 다시 만든 경우에도 잘못된 시간 차이·음수/boolean 값과 토큰 합계 불일치를 거절한다.

새 `make evaluation-batch-smoke`는 80/80 EVALUATED였다. [비교 표](../../evidence/cw07-evaluation-metrics/metrics.md)와 [JSON](../../evidence/cw07-evaluation-metrics/metrics.json)을 실제 CLI로 생성했다. 기록 토큰은 B0/B1/B2/B3 각각 0/5,800/15,000/14,600이며 가상 비용 합계는 기존 49,560 micro-USD, 미확정 예약 0을 유지했다. **이 스크립트 실행은 gate와 동시에 진행했으므로 시간 값은 성능 비교 자료가 아니다.** 실제 모델의 속도·효율 순위로 쓰지 않는다.

[독립 재계산 기록](../../evidence/cw07-evaluation-metrics/verification.json)은 80칸의 원본 호출·시간·artifact hash·58개 소스 hash를 다시 대조했다. 원시 파일 1,463개는 `.local/evaluation/batch_f3a06d30f04b40dfa6fdeeb3d5d20dfe`에 보존하고 [해시 명세](../../evidence/cw07-evaluation-metrics/raw-manifest.json)를 남겼다. 이전 Linux 80칸 자료도 재감사했고 시간 표본은 0/값 unavailable로 유지했다. 읽기 전후 원시 bytes가 일치했다.

이번 브라우저·Linux·Medusa·실제 모델은 새로 실행하지 않았다. Linux 663개·브라우저 25개는 [직전 재현](linux-reproduction-20260912.md)의 범위다. 다음은 [비용 응답](../plans/2026-09-12-completion.md) 후 실제 정상 호출과 pilot이며, 기존 SDK 데이터를 실제 모델 결과로 승격하지 않는다.
