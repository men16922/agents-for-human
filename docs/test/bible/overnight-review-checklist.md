# Rehearsal — Overnight 검수 기준

이 문서는 반복 사용하는 기준이다. 실행별 결과는 `/overnight-report`에서 `docs/test/history/*-overnight-review-checklist.md`로 만든다. 실행하지 않은 항목은 완료 표시하지 않는다.

## 1. 실행 결과

- [ ] runner 종료와 이유, 시작·종료 커밋, 실제 처리한 `[auto]` 항목을 로그와 Git으로 확인한다.
- [ ] `make check`를 독립적으로 다시 실행한다. 설치 점검이 필요하면 `make smoke-local`을 수행한다.
- [ ] 작업별 diff를 읽어 완료 기준과 범위가 맞는지 확인한다. 실행 기록과 모델의 자기 보고가 다르면 기록을 우선한다.

## 2. 문서와 제품 불변 조건

- [ ] 최신 독립 기획서 `agents-for-human-propsal.html`과 이전 생성본 `archive/aftercare/proposal.html`의 역할이 유지되는가?
- [ ] 목표·설계 예시가 실측 또는 배포 완료 주장으로 바뀌지 않았는가?
- [ ] 테스트가 실제 실패를 검출하며 skip·완화·고정 결과로 gate를 통과시키지 않았는가?
- [ ] 향후 제품 코드에서 지급 미확정·배송 대기·목표 완료를 구분하고 독립 기록을 대조하는가?
- [ ] private `platform-agent`, 외부 서비스, 전역 설정과 무관한 파일에 변경이 없는가?

## 3. 사용자 검토와 다음 단계

- [ ] 시각 변경이 있으면 데스크톱·모바일에서 가독성과 목차 이동을 확인한다.
- [ ] 미해결 항목은 원인·증거·다음 행동과 함께 기록한다. 완료 항목은 요약으로 옮긴다.
- [ ] 로컬 gate 결과와 실제 AWS·모델·사용자 검증 결과를 구분한다.
- [ ] 남은 `[auto]`를 다시 세고 `/overnight-seed`로 후속 범위를 정한다. 소진이면 종료가 정상이다.

커밋 검토 후의 push·저장소 공개·배포는 별도 사용자 요청에 따른다. 이 체크리스트 자체는 해당 작업을 승인하지 않는다.

공통 지침은 `make overnight-where`가 가리키는 플러그인의 `templates/docs/engineering/`, 저장소 적용은 `docs/engineering/interp/INTERPRETATION.md`를 참고한다.
