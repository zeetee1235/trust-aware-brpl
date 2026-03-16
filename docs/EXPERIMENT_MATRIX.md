# TA-BRPL 실험 매트릭스

> 연구 질문(RQ) 중심 실험 설계 및 측정 계획

---

## 연구 질문 (Research Questions)

### RQ1: PDR 성능

**TA-BRPL은 복합 공격(blackhole + sinkhole) 하에서 RPL / BRPL / SMTrust보다 더 높은 패킷 전달율을 유지하는가?**

- 핵심 주장: 신뢰 기반 우회로 PDR 회복
- 비교군: RPL(기준선), BRPL, SMTrust
- 조건: 공격 시작(350s) 전후 구간별 PDR

### RQ2: 탐지 및 복구 속도

**TA-BRPL은 공격자 탐지와 경로 복구를 더 빠르게 수행하는가?**

- 핵심 주장: asymmetric EWMA로 빠른 신뢰 하락 → 빠른 우회
- 측정: 공격 시작 → 첫 blacklist까지 시간, PDR 회복까지 시간

### RQ3: 혼잡 인식 유지

**TA-BRPL은 신뢰 기반 보안을 추가하면서도 BRPL의 혼잡 인식 성능을 유지하는가?**

- 핵심 주장: trust가 BRPL 비용함수에 통합 → 혼잡 인식 손실 없음
- 측정: 공격 없는 조건에서 TA-BRPL과 BRPL의 E2E delay / 큐 활용률 비교

### RQ4: 신뢰 성분의 기여 (Ablation)

**T_fwd / T_ctrl / T_hon 각 성분이 공격-혼잡 구분에 기여하는가?**

- 핵심 주장: 단일 성분 대비 3-성분 결합이 더 정확함
- 방법: ablation study (성분을 하나씩 제거)

---

## 실험 1: 주요 비교 실험 (RQ1, RQ2)

### 설정

| 항목 | 값 |
|---|---|
| 토폴로지 | GRID 6×6, 36 노드 |
| 프로토콜 | RPL / BRPL / SMTrust / TA-BRPL |
| 공격 | 3개 blackhole + 1개 sinkhole, 시작=350s |
| 시뮬레이션 시간 | 900s |
| 반복 | 30 seeds |
| 분석 단위 | 구간별 (0~150, 150~350, 350~650, 650~900) |

### 측정 지표

**PDR (Packet Delivery Ratio)**
```
PDR_node = RX_at_root(node_i) / TX(node_i)
PDR_global = Σ RX / Σ TX (전체 노드)
PDR_phase = 구간별 집계 (정상 / 공격 / 회복)
```

**E2E 지연**
```
Delay = t_recv - t0 (CSV,DELAY 기반)
평균, 중간값, 90th percentile
```

**RTT**
```
RTT = t_ack - t0 (CSV,RTT 기반)
```

**부모 변경 횟수 (Parent Churn)**
```
parent_churn_node = CSV,PARENT 라인에서 변경 횟수
(정상 구간, 공격 구간 각각 집계)
```

**라우팅 수렴 시간**
```
convergence_time = ROUTING_READY 타임스탬프
```

### 분석 방법

- 30 seeds × 4 프로토콜 → 120 실험
- 각 지표: 평균 ± 95% CI
- 프로토콜 간 비교: Wilcoxon rank-sum test (p < 0.05)
- 구간별 분석: 공격 전(150~350s) vs 공격 후(350~650s) vs 회복(650~900s)

---

## 실험 2: 혼잡 인식 비교 (RQ3)

### 설정

| 항목 | 값 |
|---|---|
| 토폴로지 | GRID 6×6, 공격자 없음 |
| 프로토콜 | RPL / BRPL / TA-BRPL |
| 혼잡 유도 | Root 인접 5개 노드 SEND_INTERVAL=15s |
| 시뮬레이션 시간 | 600s |
| 반복 | 10 seeds |

### 측정 지표

- E2E 지연 분포 (BRPL vs TA-BRPL이 유사해야 함)
- 큐 활용률 (`CSV,BRPL_STATE`의 rho 값)
- Parent 변경 빈도 (BRPL ≈ TA-BRPL이어야 함)
- PDR (세 프로토콜 모두 유사해야 함)

### 기대 결과

```
PDR: RPL ≈ BRPL ≈ TA-BRPL (공격 없으므로 유사)
E2E delay: BRPL ≈ TA-BRPL < RPL (혼잡 인식 효과)
Parent churn: BRPL ≈ TA-BRPL (신뢰 패널티 미발동)
→ "TA-BRPL이 BRPL 혼잡 인식을 유지함" 입증
```

---

## 실험 3: Ablation Study (RQ4)

### 설정

| 변형 | T_fwd | T_ctrl | T_hon | 비고 |
|---|---|---|---|---|
| BRPL | — | — | — | 기준 (신뢰 없음) |
| TA-BRPL-Fwd | ✅ | ✗ (1.0) | ✗ (1.0) | T_fwd only |
| TA-BRPL-FwdCtrl | ✅ | ✅ | ✗ (1.0) | T_fwd + T_ctrl |
| TA-BRPL-Full | ✅ | ✅ | ✅ | 전체 |

- 반복: 10 seeds
- 조건: 공격 포함 (GRID 6×6, A1~A3)

### 측정 지표

- 탐지율 (Detection Rate): blacklist 이벤트 발생 비율
- 오탐율 (FPR): 정상 노드 blacklist 비율
- PDR 회복률: 공격 후 650~900s 구간 PDR
- 탐지 지연: 공격 시작 → 첫 blacklist 시간

### 기대 결과

```
PDR 회복: Full > FwdCtrl > Fwd > BRPL
탐지율:   Full ≈ FwdCtrl ≈ Fwd (선택적 포워딩은 T_fwd가 주 탐지)
오탐율:   Full ≈ Fwd (T_ctrl이 오탐 감소에 기여는 미미, 이번 공격 유형)
T_hon 기여: C2(혼잡 only) 시나리오에서 오탐 방지에 기여
```

---

## 실험 4: 파라미터 민감도 (보조)

### Sweep 조건

아래 파라미터를 ±20% 범위에서 변경:

| 파라미터 | 기본값 | 범위 | 단계 |
|---|---|---|---|
| `TA_TRUST_TAU_WARN` | 750 | 650~850 | 50씩 |
| `TA_TRUST_TAU_JOIN` | 450 | 350~550 | 50씩 |
| `TA_TRUST_TAU_BLACK` | 250 | 150~350 | 50씩 |
| `TA_TRUST_UPDATE_INTERVAL` | 150s | 60~300s | — |
| `TA_TRUST_LAMBDA_DECREASE` | 500 | 300~700 | — |
| `TA_TRUST_LAMBDA_NORMAL` | 700 | 500~900 | — |

- 한 번에 하나씩 변경 (나머지는 기본값)
- 반복: 5 seeds / 조건
- 측정: PDR, 탐지율, 오탐율

---

## 측정값 → 논문 표/그림 매핑

| 그림/표 | 실험 | 데이터 |
|---|---|---|
| Fig.1: PDR over time (4 프로토콜) | 실험 1 | 구간별 PDR, 시간축 |
| Fig.2: E2E delay CDF | 실험 1 | CSV,DELAY 누적분포 |
| Fig.3: Parent churn heatmap | 실험 1 | CSV,PARENT 변경 횟수 |
| Fig.4: Trust trace (TA-BRPL) | 실험 1 | CSV,TRUST 시계열 |
| Fig.5: Congestion comparison | 실험 2 | delay / queue / PDR |
| Fig.6: Ablation PDR bar | 실험 3 | 구간별 PDR 비교 |
| Fig.7: Sensitivity heatmap | 실험 4 | 파라미터 × PDR |
| Table 1: Statistical summary | 실험 1 | 평균 ± CI, p-value |
| Table 2: Detection metrics | 실험 3 | DR / FPR / latency |

---

## 실험 우선순위 및 일정

| 순서 | 실험 | 목적 | 완료 기준 |
|---|---|---|---|
| 1 | V1~V3 (검증 계획) | 디버깅/동작 확인 | blacklist 이벤트 확인 |
| 2 | Pilot 5 seeds (실험 1) | 파이프라인 검증 | 20개 로그 생성 |
| 3 | 실험 2 (혼잡 비교) | RQ3 검증 | 결과 예상치와 일치 |
| 4 | 본실험 30 seeds (실험 1) | RQ1, RQ2 | 통계적 유의성 확인 |
| 5 | Ablation (실험 3) | RQ4 | 컴포넌트 기여 확인 |
| 6 | 민감도 (실험 4) | 파라미터 정당화 | 기본값 최적성 확인 |
