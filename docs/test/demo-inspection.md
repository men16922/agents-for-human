# 무료 로컬 시연 — 거래 후 화면 유지와 종료 검증

2026-09-12. 기존 실제 SDK/Medusa 브라우저 검사는 결과 확인 직후 화면 서버를 종료했다. 심사자나 새 사용자가 직접 증빙을 살펴볼 수 있도록 `make commerce-demo`를 추가했다. 검증된 시연 뒤에도 관측 API·웹·gateway·seller를 유지하고, Ctrl+C 때 최종 독립 export와 소유 프로세스 정리를 수행한다.

## 실행 절차

`make setup`이 끝난 저장소에서 터미널 A:

```sh
make commerce
```

Medusa health 준비 메시지가 나온 뒤 터미널 B:

```sh
make commerce-demo
```

명령은 새 로컬 합성 거래를 만들고, 실제 Medusa 재고 변경·오래된 A 주문 차단·스크립트의 B 구매·납품·SSE·독립 증빙을 검사한다. `Inspection ready`가 나오면 `http://127.0.0.1:15173`을 열어 상태와 증거를 살펴본다. 브라우저의 **증거 다시 검증** 버튼은 원본 export를 독립 검증한다. 새로고침도 가능하다. 이 모드의 구매자는 명시적인 SDK fixture이며 실제 모델을 호출하지 않는다. 웹 화면은 읽기 전용이다.

터미널 B에서 Ctrl+C로 관측 시간을 종료하고 최종 export/정리 메시지를 확인한다. 그 다음 터미널 A에서 Ctrl+C로 Medusa·전용 DB를 종료한다. 데이터 볼륨은 유지한다. 관측 중인 다른 서버를 재사용하지 않으며, 필요한 포트가 점유돼 있으면 실패한다.

직접 실행할 때 `--inspect 30`처럼 검사 후 유지 시간을 1~3,600초로 제한할 수도 있다. `--inspect` 또는 `--inspect 0`은 Ctrl+C까지 유지한다. 이 옵션이 없는 기존 `commerce-reaction-ui-smoke`의 자동 종료 동작은 그대로다. `inspection.json`의 FINISHED는 관측 창의 종료이며, 거래 판정이나 모든 서비스 종료를 대신하지 않는다.

## 실제 확인

- `make check`: Python 682개·mypy 58소스·ruff·lock·웹 빌드 통과. 추가 회귀 7개로 Ctrl+C·시간 한도·API/seller 종료·worker 오류·잘못된 입력을 확인했다.
- 실제 `make commerce-demo`: run `cw00-f14ce07ebdb9-buyer`, B 납품 380·예약 0, SDK 9호출/180토큰/가상 252 micro-USD. 독립 export/attestation COMPLETE. 실제 모델 호출 0회.
- 자동 시연 브라우저가 종료한 뒤 별도 Chromium으로 1440/390 너비 접속·새로고침·재연결·증거 재검증을 확인했다. 요청은 GET뿐이며 브라우저에 Authorization이 없고 페이지 오류/가로 넘침이 없었다. 화면도 직접 확인했다.
- 관측 창은 39.44초 유지한 뒤 Ctrl+C로 종료했다. `inspection.json`은 FINISHED/OPERATOR_INTERRUPT, 세션 STOPPED·cleanup 오류 0, 최종 export를 복사본에서 다시 독립 검증했다.
- 두 make 터미널은 SIGINT 때문에 종료 코드 1을 반환했다. 이를 exit 0 성공으로 기록하지 않았다. 거래 결과·export·실제 정리는 별도 증거로 확인했다. 포트 6개 반환, 기존 실행 컨테이너 4개·볼륨 50개 보존을 대조했다.

[검증 요약](../../evidence/cw08-demo-inspection/verification.json), [브라우저 기록](../../evidence/cw08-demo-inspection/browser.json), [독립 재판정](../../evidence/cw08-demo-inspection/independent-attestation.json), [artifact 명세](../../evidence/cw08-demo-inspection/artifact-manifest.json)를 보존했다. 실제 구매자/관측자/control 토큰과 로컬 비밀값이 포함되지 않았는지 대조했다.

이 결과는 현재 Mac에서 실행한 무료 테스트 경로다. 새 사람의 설치, 독립 호스트, 실제 모델 판단, 개발자 관찰, 공개 접근이나 최종 제출을 완료한 것은 아니다. 참가자 수는 0명이다.
