노드별 마지막 seq 추적 → 누락(missed) 계산
샘플 신뢰도: sample = 1000 / (1 + missed) (0~1000 스케일)
EWMA: trust = alpha*sample + (1-alpha)*prev
로그: CSV,TRUST,<node_id>,<seq>,<missed>,<trust>


일단은.. 먼저 brpl이 selective forwarding 공격에 더 취약하다는것을 증명
이후 해결방안까지 제공 신뢰기반



BRPL은 트래픽 상황에 따라 동적으로 경로를 조정하지만,
이러한 특성은 Selective Forwarding 공격 시
악성 노드를 오히려 우수한 경로로 인식하게 만들어
공격 효과를 증폭시킬 수 있다.