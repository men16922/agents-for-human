# Nova 미완료 종료의 원인 구분

2026-09-12. 실제 실패는 한 종류가 아니다. 알려진 pilot과 진행 중인 새 조건 배치의 원본 종료 사유·응답·독립 수령 판정을 구별한다. 배치 중에는 설정이나 구매 소스를 변경하지 않는다.

1. `malformed_model_output`: pilot-02의 higher-price B2와 partial B1은 이 provider 종료 사유를 반환했다. AWS [Nova 2 응답 schema](https://docs.aws.amazon.com/nova/latest/nova2-userguide/request-response-schema.html)는 이를 잘못된 모델 출력으로 설명하며 `max_tokens`·`malformed_tool_use`와 별개로 정의한다. 따라서 원본 오류를 단순 출력 한도 도달이나 우리 JSON 검토 파서 문제로 바꾸어 기록하지 않는다.
2. 정상 `end_turn`이지만 납품 전 종료: 새 조건 price-1 B3는 지급 뒤 현재 재고가 비었고 tick 15에 도착할 것이라고 설명하며 응답을 마쳤다. SDK 실행 절차는 COMPLETED이나 독립 평가 상태는 EVALUATION_INCOMPLETE다. 현재 API 오류가 아니고, 목표 수령 전에 실행을 끝낸 모델 행동이다. 최종 평가에서 구분 집계한다.
3. 실제 지급 재시도/기한 종료: [reaction-ui-02](nova-reactive-video.md)는 주문 뒤 재고 감소·HTTP 400에 같은 지급을 반복했다. OBSERVATION_DEADLINE_REACHED로 멈췄고 독립 수령은 0이다. 앞선 두 종류와 합쳐 파서 오류라고 부르지 않는다.

기존 Bedrock 생성기는 max_tokens만 명시하고 temperature/top_p를 전달하지 않는다. 설치된 Strands 어댑터도 없는 값을 요청에 추가하지 않으며 Nova 기본값에 맡긴다. AWS의 [Nova 2 도구 호출 지침](https://docs.aws.amazon.com/nova/latest/nova2-userguide/advanced-prompting-techniques.html)은 비추론 모드에 temperature 0.7/topP 0.9를 안내한다. 구세대 Nova 지침의 greedy decoding 권고를 근거로 현재 batch 설정을 중간에 바꾸지 않는다.

후속 개선 비교는 원본 배치를 종료·보존한 뒤 새 버전/명부로 진행해야 한다. 우선 실행 종료와 목표 완료의 차이를 보고하고, 목표가 남았을 때 명시적으로 대기/수령 확인하도록 하는 프롬프트 변경은 별도 같은 조건 대조로 평가한다. 재시도·출력 한도·추론 모드 변경이 효과를 낼 것이라는 결론은 아직 없다.
