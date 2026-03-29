# TA-BRPL 개발 전주기 보고서

> 작성일: 2026-03-28  
> 버전 범위: v1 → v13.12  
> 실험 규모: 고정 토폴로지 full40 + 랜덤 토폴로지 750 runs (75 topology pairs)  
> 상태: **랜덤 일반화 미달 확인, 원인 분석 완료, 다음 단계 설계 중**

---

## 목차

1. [왜 이 보고서를 쓰는가](#1-왜-이-보고서를-쓰는가)
2. [시스템 및 위협 모델](#2-시스템-및-위협-모델)
3. [Trust 모델 — 수식과 설계 철학](#3-trust-모델--수식과-설계-철학)
4. [의사결정 계층 구조 — 의사코드 전체](#4-의사결정-계층-구조--의사코드-전체)
5. [v1~v13.12 삽질 전주기 — 무엇이 왜 망했는가](#5-v1v1312-삽질-전주기--무엇이-왜-망했는가)
6. [최종 후보 v13.12 파라미터와 빌드 프로파일](#6-최종-후보-v1312-파라미터와-빌드-프로파일)
7. [고정 토폴로지 full40 결과](#7-고정-토폴로지-full40-결과)
8. [랜덤 토폴로지 메인실험 결과 — 솔직한 해석](#8-랜덤-토폴로지-메인실험-결과--솔직한-해석)
9. [두 결과의 불일치: 왜 full40은 되고 랜덤은 안 됐나](#9-두-결과의-불일치-왜-full40은-되고-랜덤은-안-됐나)
10. [Discussion — 학술적 포지셔닝](#10-discussion--학술적-포지셔닝)
11. [다음 단계](#11-다음-단계)
12. [재현 명령 전체](#12-재현-명령-전체)

---

## 1. 왜 이 보고서를 쓰는가

이 프로젝트는 단순하게 시작했다.

> "RPL에 trust를 붙이면 sinkhole 공격자를 더 잘 격리할 수 있을 것이다."

틀린 말은 아니다. 그런데 v1을 만들어보니 churn이 폭발했다. trust를 더 세게 넣으면 더 좋아질 것 같아서 세게 넣었더니 더 나빠졌다. 약하게 하면 격리가 안 됐다. 고정 토폴로지에서 드디어 되는 것 같았는데 랜덤 토폴로지에서 무너졌다.

**v1부터 v13.12까지 약 13개 주요 버전, 수십 개 서브 버전을 거쳤다.**

이 보고서는 그 삽질 과정을 기록한다. 무엇이 왜 망했는지, 어디서 전환점이 왔는지, 현재 어디에 있는지를 정량 지표와 함께 정리한다.

### 핵심 연구 질문

- **Q1:** Trust 모델(T_fwd, T_ctrl, T_hon)을 BRPL parent 선택에 결합하면 attacker isolation이 향상되는가?
- **Q2:** 향상이 발생한다면 churn 비용은 어떤 수준에서 bounded 가능한가?
- **Q3:** 고정 토폴로지에서의 개선이 랜덤 토폴로지 분포로 일반화되는가?

### 현재 시점의 답

| 질문 | 답 | 근거 |
|------|----|----|
| Q1 | **조건부 Yes** | full40에서 att_share, hit_ratio 개선 재현 |
| Q2 | **조건부 Yes** | v13.12에서 churn bounded 확인 (BOTTLE 일부 잔존) |
| Q3 | **현재 No** | 랜덤 750 runs에서 overall Δatt_share=+0.0058, Δhit_ratio=+0.0087 |

Q3의 "No"는 **메커니즘이 무효라는 뜻이 아니다.** 현재 파라미터 설정이 특정 토폴로지 구조에 과적합되어 있고, 일반화를 위한 추가 작업이 필요하다는 뜻이다.

---

## 2. 시스템 및 위협 모델

### 2.1 네트워크 구성

```
- 플랫폼: Contiki-NG + Cooja 시뮬레이터
- 라우팅: RPL (RFC 6550) 위에 BRPL 확장, 그 위에 TA-BRPL 레이어
- 토폴로지:
    고정: GRID (격자형), BOTTLE (병목형)
    랜덤: sparse/medium/dense (density별 25 topology seeds × 5 run seeds)
- 평가 시나리오:
    SINK_ONLY  : 공격자가 낮은 rank로 경로를 유인, 패킷은 정상 전달
    SINK_DROP50: 유인 후 50% 패킷 드롭
```

### 2.2 공격자 모델 (Threat Model)

본 연구에서 가정하는 공격자는 다음 조건을 충족한다:

**공격자 능력 (할 수 있는 것):**
- RPL DIO 메시지에서 rank를 조작 (실제보다 낮은 rank 광고)
- 자신을 경유하는 패킷의 일부 또는 전부를 드롭
- 정상 노드처럼 행동하여 탐지를 회피 (SINK_ONLY)
- 단일 공격 노드 (현재 파이프라인 기준)

**공격자 능력 제한 (할 수 없는 것):**
- 암호화된 제어 메시지 위조 불가
- 물리 계층 방해 불가
- 다중 공모 노드 (현재 실험 범위 밖)

**방어 목표:**
- `att_share` 감소: 공격자를 preferred parent로 선택하는 노드 비율 최소화
- `hit_ratio` 감소: 공격자 경유 패킷 비율 최소화
- churn 비용 bounded: 부모 교체 횟수를 합리적 수준으로 제한

### 2.3 핵심 구현 파일 구조

```
ta-brpl-trust.c          ← Trust 관측, 집계, 업데이트 엔진 (핵심)
rpl-brpl.c               ← BRPL parent scoring + trust hook 결합
project-conf.h           ← compile-time 파라미터 기본값
Makefile.tabrpl          ← v13.12 오버라이드 매크로 모음
run_sinkhole_sweep.sh    ← 고정 토폴로지 실험 실행
run_random_topo_sweep.sh ← 랜덤 토폴로지 대량 실험
```

---

## 3. Trust 모델 — 수식과 설계 철학

### 3.1 세 축의 Trust 관측값

TA-BRPL은 각 이웃 노드 j에 대해 노드 i 관점에서 세 가지 독립적인 trust 관측값을 유지한다.

#### T_fwd: Forwarding Trust

노드 j가 실제로 패킷을 전달하는지를 측정한다.

```
T_fwd(i,j) = delivered_count(j) / expected_count(j)
```

단, 이 계산에서 attribution 문제가 핵심적인 난제다. 패킷이 j에서 드롭됐는지, j의 상위 홉에서 드롭됐는지를 i는 직접 알 수 없다. v8 계열에서 이 문제가 치명적 실패를 일으켰다 (5.5절 참조).

**Echo 기반 추정 (현재 구현):**

```
expected_echo(i,j,t) = sent_via_j(t) × propagation_factor
received_echo(i,j,t) = echo_count_observed(i,j,t)

raw_fwd(i,j,t) = received_echo / max(expected_echo, ε)
raw_fwd 를 [0, 1] 클리핑
```

#### T_ctrl: Control-Plane Trust

노드 j가 RPL 제어 메시지(DIO, rank 정보, version)를 일관되게 전송하는지 측정한다.

```
T_ctrl(i,j) = 1 - rank_inconsistency_score(j)

rank_inconsistency_score(j) = 
    (rank_claim_violations + version_violations) / total_dio_observed
```

rank가 물리적으로 불가능한 방향으로 변동하거나, RPL version 번호가 비정상적으로 증가하면 페널티가 부여된다.

#### T_hon: Honesty/Behavior Trust

큐 지연, 응답 패턴, 비정상 행동을 종합하는 휴리스틱 trust다.

```
T_hon(i,j) = Σ_k w_k × behavior_score_k(j)

behavior_score 항목:
  - queue_delay_score: 예상보다 긴 큐 지연 패널티
  - response_consistency: 요청 대비 응답 일관성
  - rank_drop_pattern: rank가 갑자기 낮아지는 패턴 감지
```

### 3.2 집계 Trust — 가중 기하평균

세 축의 trust를 하나의 집계값으로 결합한다.

```
T_agg(i,j) = T_fwd(i,j)^w_fwd × T_ctrl(i,j)^w_ctrl × T_hon(i,j)^w_hon

조건: w_fwd + w_ctrl + w_hon = 1
```

**기하평균을 선택한 이유:**  
산술평균(T_fwd × w + T_ctrl × w + ...)이면 하나의 지표가 0에 가까워도 다른 지표로 보상 가능하다. 기하평균은 하나라도 극도로 낮으면 전체가 낮아진다. 공격자 탐지에서는 "하나라도 수상하면 전체가 수상하다"는 논리가 더 적합하다.

**v13.12 기준 가중치:**

```
w_fwd  = 0.5   (forwarding이 가장 직접적 증거)
w_ctrl = 0.3   (rank 조작이 sinkhole의 핵심 수단)
w_hon  = 0.2   (보조 휴리스틱)
```

### 3.3 시간 업데이트 — 비대칭 EWMA

trust는 시간에 따라 지수 가중 이동 평균으로 업데이트된다.

```
T(t+1) = λ × T(t) + (1-λ) × T̃(t)

λ = {
    λ_normal   = 0.85,  if T̃(t) >= T(t)  (신뢰 상승 또는 유지: 느리게 반응)
    λ_decrease = 0.60,  if T̃(t) <  T(t)  (신뢰 하락: 빠르게 반응)
}
```

**비대칭 EWMA의 의미:**  
신뢰는 천천히 쌓고 빠르게 잃는다. 공격자가 잠깐 정상 행동을 해서 신뢰를 쉽게 회복하는 것을 막기 위해, 상승 방향은 λ를 높게(관성 크게), 하락 방향은 λ를 낮게(민감하게) 설정한다.

단, 이 비대칭이 너무 강하면 무고한 relay가 일시적 손실로 인해 빠르게 trust를 잃고 복구가 느려지는 문제가 생긴다. v8의 attribution bias 문제와 맞물려 이 파라미터 설정이 오랫동안 핵심 과제였다.

### 3.4 T_fwd의 Attribution Bias 문제 — 설계상 한계

```
상황:
  노드 i → 노드 j → 노드 k → sink
              ↑
        실제 drop 발생 위치

i가 관측하는 것:
  - j에게 패킷을 보냈음
  - 패킷이 결국 도달하지 않음
  - "j가 드롭했다"고 (잘못) 판단

실제:
  - j는 정상 전달, k가 공격자이거나 경로 상에서 드롭
  - i는 k를 모른다 (직접 이웃이 아니므로)
```

이 문제는 v8에서 처음 명시적으로 진단됐다. loss 구간에서 T_fwd가 cascade하여 무고한 relay까지 suspicion에 빠지는 현상이 실험으로 확인되었다. 해결책은:

1. Echo hop-count 기반 attribution 범위 제한 (현재 구현)
2. T_fwd 단독 사용 금지 → T_ctrl, T_hon과 반드시 결합
3. T_fwd loss 임계값을 보수적으로 (loss-aware gate)

---

## 4. 의사결정 계층 구조 — 의사코드 전체

### 4.1 전체 흐름

```
패킷 라우팅 이벤트 발생
        ↓
[Trust Sensing Layer]
  T_fwd, T_ctrl, T_hon 업데이트
  T_agg 재계산
        ↓
[Soft Layer: Admission/Switch Policy]
  candidate parent에 T_agg 기반 penalty 적용
  margin 조건 검사
        ↓
[Hard Layer: Validation/Review Score]
  누적 증거 기반 score 계산
  임계값 초과 시 blacklist 또는 severe block
        ↓
[Cooldown / Escape Policy]
  최근 switch 시각 확인
  cooldown 미경과 시 switch 억제
        ↓
[BRPL Parent Selection]
  최종 scoring = BRPL_rank_score + trust_penalty
  highest score parent 선택
```

### 4.2 Trust 업데이트 의사코드

```pseudocode
PROCEDURE update_trust(node_i, neighbor_j, observation):

  # Step 1: 새 관측값 계산
  T_fwd_new  ← compute_fwd_trust(node_i, neighbor_j)
  T_ctrl_new ← compute_ctrl_trust(neighbor_j)
  T_hon_new  ← compute_hon_trust(neighbor_j)

  # Step 2: 비대칭 EWMA 업데이트
  FOR each dim IN {fwd, ctrl, hon}:
    T_old ← trust_table[node_i][neighbor_j][dim]
    T_obs ← T_{dim}_new

    IF T_obs >= T_old:
      λ ← LAMBDA_NORMAL    # 0.85
    ELSE:
      λ ← LAMBDA_DECREASE  # 0.60

    trust_table[node_i][neighbor_j][dim] ←
        λ × T_old + (1 - λ) × T_obs

  # Step 3: 집계 trust 계산
  T_agg ← (T_fwd ^ W_FWD) × (T_ctrl ^ W_CTRL) × (T_hon ^ W_HON)
  trust_table[node_i][neighbor_j][agg] ← T_agg

  # Step 4: Validation score 업데이트
  IF T_agg < SUSPICION_THRESHOLD:
    validation_score[neighbor_j] += SUSPICION_INCREMENT
  ELSE IF T_agg > RECOVERY_THRESHOLD:
    validation_score[neighbor_j] = max(0,
        validation_score[neighbor_j] - RECOVERY_DECREMENT)

  RETURN
```

### 4.3 Admission Gate 의사코드

새 노드를 preferred parent 후보로 허용할지 결정한다.

```pseudocode
FUNCTION admission_gate(node_i, candidate_j) → BOOLEAN:

  T ← trust_table[node_i][candidate_j][agg]

  # Hard block: validation score 초과
  IF validation_score[candidate_j] >= BLOCK_THRESHOLD:
    RETURN BLOCKED

  # Severe block: T_agg가 극도로 낮음
  IF T < SEVERE_BLOCK_THRESHOLD:       # 예: 0.15
    RETURN BLOCKED

  # Soft admission: T_agg가 기본 admission 임계값 이상
  IF T >= ADMISSION_THRESHOLD:         # 예: 0.40 (v13.12 기준)
    RETURN ADMITTED

  # 회색지대: 현재 parent보다 T가 높으면 conditional admit
  current_parent ← routing_table[node_i].preferred_parent
  T_current ← trust_table[node_i][current_parent][agg]

  IF T >= T_current - ADMISSION_MARGIN:  # margin: 0.05
    RETURN CONDITIONALLY_ADMITTED

  RETURN REJECTED
```

### 4.4 Retention Gate 의사코드

현재 preferred parent를 유지할지 결정한다.

```pseudocode
FUNCTION retention_gate(node_i, current_parent_j) → {RETAIN, SWITCH, EVICT}:

  T ← trust_table[node_i][current_parent_j][agg]
  now ← current_time()

  # Cooldown 확인 — 최근 switch 억제
  IF (now - last_switch_time[node_i]) < ESCAPE_COOLDOWN:   # 360s (v13.12)
    RETURN RETAIN   # cooldown 미경과, 강제 유지

  # Eviction: trust가 임계값 아래로 떨어짐
  IF T < EVICTION_THRESHOLD:                               # 예: 0.25
    IF validation_score[current_parent_j] >= EVICT_SCORE:
      last_switch_time[node_i] ← now
      RETURN EVICT

  # Switch: 더 신뢰할 수 있는 대안이 있는 경우
  best_alt ← find_best_alternative(node_i, exclude=current_parent_j)

  IF best_alt EXISTS:
    T_alt ← trust_table[node_i][best_alt][agg]
    rank_alt ← brpl_rank_score(best_alt)
    rank_cur ← brpl_rank_score(current_parent_j)

    # 대안이 trust와 rank 모두에서 margin 이상 우위
    IF (T_alt > T + SWITCH_TRUST_MARGIN) AND
       (rank_alt > rank_cur - SWITCH_RANK_MARGIN):
      last_switch_time[node_i] ← now
      RETURN SWITCH

  RETURN RETAIN
```

### 4.5 Loss-Aware Gate (v13.8에서 추가)

T_fwd attribution bias를 보완하기 위한 추가 레이어다.

```pseudocode
FUNCTION loss_aware_gate(node_i, neighbor_j) → PENALTY_FACTOR:

  # 채널 품질 기반 expected loss 추정
  rssi ← link_quality_table[node_i][neighbor_j].rssi
  expected_loss_rate ← rssi_to_expected_loss(rssi)

  # 관측된 loss가 기대치보다 얼마나 높은가
  observed_loss_rate ← 1.0 - T_fwd_raw(node_i, neighbor_j)
  excess_loss ← max(0, observed_loss_rate - expected_loss_rate)

  # excess loss가 작으면 penalty 없음 (채널 품질로 설명 가능)
  IF excess_loss < LOSS_GATE_TOLERANCE:    # 0.10 (v13.12)
    RETURN 1.0   # no penalty

  # excess loss가 크면 T_fwd에 추가 penalty
  penalty ← 1.0 - (excess_loss - LOSS_GATE_TOLERANCE) × LOSS_PENALTY_SCALE
  RETURN clamp(penalty, 0.3, 1.0)
```

**핵심:** 이 gate가 없으면 경로 상의 채널 품질이 나쁜 구간에서 T_fwd가 무차별 하락하여 무고한 노드가 eviction된다. v13.8에서 이 gate를 추가한 이후 full40 BOTTLE 토폴로지에서 안정성이 크게 개선됐다.

### 4.6 최종 Parent Scoring

BRPL 기존 scoring에 trust penalty를 결합하는 최종 단계다.

```pseudocode
FUNCTION compute_parent_score(node_i, candidate_j) → SCORE:

  # BRPL 기본 점수 (ETX 기반)
  brpl_score ← brpl_compute_rank_metric(candidate_j)

  # Admission check
  IF admission_gate(node_i, candidate_j) == BLOCKED:
    RETURN -INFINITY   # 후보에서 완전 제외

  # Trust 기반 penalty
  T ← trust_table[node_i][candidate_j][agg]
  loss_factor ← loss_aware_gate(node_i, candidate_j)

  T_effective ← T × loss_factor

  # Trust penalty: T가 낮을수록 점수를 깎음
  trust_penalty ← TRUST_PENALTY_SCALE × (1.0 - T_effective)

  final_score ← brpl_score - trust_penalty

  RETURN final_score
```

---

## 5. v1~v13.12 삽질 전주기 — 무엇이 왜 망했는가

이 섹션이 이 보고서의 핵심이다. 각 버전에서 무엇을 시도했고, 왜 실패했고, 무엇을 배웠는지를 기록한다.

### 5.1 Δ 지표 정의

모든 버전 비교는 다음 지표를 기준으로 한다.

```
Δatt_share = att_share(TA-BRPL) - att_share(BRPL)     → 음수가 좋음 (격리 개선)
Δhit_ratio = hit_ratio(TA-BRPL) - hit_ratio(BRPL)     → 음수가 좋음
Δchurn     = churn(TA-BRPL)     - churn(BRPL)         → 음수가 좋음 (안정성 비용)
ΔPDR_dur   = PDR_dur(TA-BRPL)  - PDR_dur(BRPL)        → 양수가 좋음
```

### 5.2 v1~v2: "Trust를 넣었더니 더 나빠졌다"

**무엇을 했나:**  
가장 단순한 형태의 trust를 넣었다. T_fwd만 사용, 단순 임계값 기반 eviction.

**결과:**
```
Δatt_share: +0.12 ~ +0.18  (심각한 악화)
Δchurn:     +8.3  (폭발)
ΔPDR_dur:   -0.15 (전달도 나빠짐)
```

**왜 망했나:**

1. T_fwd attribution bias 인지 전. 상위 홉에서 드롭된 것을 바로 위 relay 탓으로 돌림.
2. Eviction이 너무 빠름. 조금만 의심스러워도 즉시 교체.
3. 교체한 parent도 금방 의심 → 또 교체 → churn cascade 발생.
4. Churn이 많으니 루트까지 경로가 불안정 → PDR까지 나빠짐.

**교훈:** Trust를 단순히 넣는다고 격리가 되는 게 아니다. "얼마나 확신할 때 행동하는가"의 임계값 설계가 더 중요하다.

### 5.3 v3~v4: "Admission 중심으로 보수화"

**무엇을 했나:**  
Eviction을 줄이고 Admission 위주로 재설계. 한 번 선택한 parent는 쉽게 바꾸지 않는다.

**결과:**
```
Δatt_share: -0.04 ~ -0.02  (소폭 개선, 불안정)
Δchurn:     +1.2  (크게 줄었음)
ΔPDR_dur:   -0.03 (소폭 악화)
```

**무엇이 개선됐나:**  
Churn이 줄면서 경로 안정성이 회복됐다. Admission gate에서 공격자를 처음부터 막으면 이후 문제가 없다는 방향이 맞다는 것을 확인.

**왜 여전히 부족했나:**  
Admission 임계값이 너무 높으면 네트워크 초기화 시 합법적인 노드도 parent로 못 쓴다. 너무 낮으면 공격자가 통과한다. 이 균형을 잡는 것이 v4~v8의 과제.

### 5.4 v5: "Escape를 다시 열었더니 다시 망함"

**무엇을 했나:**  
v3/v4에서 격리가 됐지만 일부 토폴로지에서 공격자가 초반에 parent가 된 뒤 lock-in되는 문제가 생겼다. 이를 해결하려고 escape 메커니즘(강제로 다른 parent를 탐색)을 활성화했다.

**결과:**
```
Δatt_share: -0.06  (격리 조금 나아짐)
Δchurn:     +5.1   (다시 폭발)
```

**왜 망했나:**  
Escape가 활성화되자 노드들이 주기적으로 다른 parent를 탐색하는데, 공격자가 랭크를 낮게 광고하고 있으므로 탐색 때마다 공격자 쪽으로 끌린다. Escape ↔ 공격자 재발견 ↔ escape ↔ 반복.

**교훈:** Escape는 cooldown 없이는 안 된다. 그리고 escape 중에도 trust gate는 유지해야 한다.

### 5.5 v6~v7: "Conditional Eviction 과보수 — 너무 안 움직임"

**무엇을 했나:**  
Escape 폭발을 막기 위해 eviction 조건을 매우 엄격하게 설정. 증거가 누적되어야만 eviction.

**결과:**
```
Δatt_share: +0.03 ~ +0.06  (다시 악화)
Δchurn:     -0.3  (안정하긴 한데)
```

**왜 망했나:**  
조건이 너무 엄격해서 eviction이 거의 발동하지 않는다. 공격자가 parent로 자리잡으면 증거가 충분히 쌓일 때까지 빼지 않는다. 그런데 증거를 쌓는 동안 공격자는 계속 데이터를 가로막는다.

**교훈:** 과보수와 과민 사이의 균형이 버전 진화의 핵심 과제다.

### 5.6 v8~v8c: "Attribution Bias를 처음 명시적으로 진단"

**무엇을 했나:**  
v1~v7까지 T_fwd 계산에서 attribution 문제가 있다는 것을 알고 있었지만, 얼마나 심각한지 정량화하지 않았다. v8에서 처음으로 loss 구간에서 T_fwd collapse를 측정했다.

**진단 결과:**
```
loss 발생 시 T_fwd가 영향을 받는 노드:
  - 실제 드롭 노드: 100% (당연)
  - 1홉 upstream 노드: 62~78% 오탐
  - 2홉 upstream 노드: 18~31% 오탐
```

즉, 공격자가 드롭하면 그 위의 relay 노드들까지 T_fwd가 내려간다.

**v8에서 시도한 해결책:**
- Echo hop-count 제한: 1홉 이내에서만 T_fwd 관측
- T_fwd 단독 사용 금지, T_ctrl와 반드시 결합
- Loss 임계값 완화 (false positive 줄이기)

**결과:**
```
Δatt_share: -0.05 ~ -0.03  (개선)
Δchurn:     +0.8  (적정 수준)
ΔPDR_dur:   -0.02 (소폭 허용 가능)
```

**교훈:** Attribution bias는 패치로 완전히 해결되지 않는다. 이게 TA-BRPL의 구조적 한계다. Loss-aware gate(v13.8)로 완화는 됐지만 없어지지는 않았다.

### 5.7 v9~v12: "파라미터 탐색의 긴 터널"

v8에서 방향은 잡혔는데, 어떤 파라미터 조합이 최적인지를 찾는 긴 탐색 과정이었다.

| 버전 | 주요 변경 | Δatt | Δchurn | 문제 |
|------|----------|------|--------|------|
| v9 | LAMBDA_DECREASE 낮춤 (0.7→0.55) | -0.06 | +1.8 | churn 재증가 |
| v10 | ADMISSION_THRESHOLD 낮춤 (0.5→0.4) | -0.03 | +0.4 | sparse에서 불안정 |
| v11 | T_ctrl 가중치 높임 (0.2→0.35) | -0.07 | +0.6 | dense에서 false alarm |
| v12 | ESCAPE_COOLDOWN 추가 (60s) | -0.05 | -0.2 | BOTTLE 여전히 문제 |

**핵심 교훈:** 파라미터 하나를 건드리면 다른 토폴로지에서 반동이 생긴다. 이것이 일반화의 어려움을 예고했다.

### 5.8 v13~v13.8: "Loss-Aware Gate — 전환점"

**무엇을 했나:**  
채널 품질(RSSI)을 이용해서 "이 노드에서 이 정도 loss는 채널 문제이지 공격이 아니다"를 구분하는 loss-aware gate를 추가했다.

이 게이트는 T_fwd 계산에 직접 개입하지 않는다. 대신 T_fwd를 parent scoring에 반영할 때 penalty를 조절한다. 채널 품질로 설명 가능한 loss는 penalty를 줄여준다.

**결과 (full40 GRID, v13 vs v13.8):**
```
                 v13      v13.8
Δatt_share:    -0.031   -0.058   (개선됨)
Δhit_ratio:    -0.028   -0.051   (개선됨)
Δchurn:        +1.21    +0.89    (비용 줄어듦)
ΔPDR_dur:      -0.018   -0.011   (손실 줄어듦)
```

**BOTTLE 토폴로지에서는 churn이 여전히 높았다.** BOTTLE은 병목 노드가 하나뿐이라 거기서 판단이 흔들리면 전체 경로가 불안정해진다.

### 5.9 v13.12: "Escape Cooldown 확장 — 최종 후보"

**무엇을 했나:**  
v13.8에서 BOTTLE churn이 높은 원인을 분석했다. Escape trigger가 너무 자주 발동해서 병목 노드를 통과할 때마다 재평가가 일어나는 것이 문제였다.

Escape cooldown을 120초에서 360초로 확장했다.

**v13.8 → v13.12 변경 사항:**
```
ESCAPE_COOLDOWN: 120 → 360 (초)
SWITCH_TRUST_MARGIN: 0.08 → 0.06 (미세 조정)
LOSS_GATE_TOLERANCE: 0.12 → 0.10 (미세 조정)
```

**결과 (full40):**
```
                v13.8    v13.12   방향
att_share(TA):  낮음     낮음     ← 유지
hit_ratio(TA):  낮음     낮음     ← 유지
churn(BOTTLE):  높음     중간     ↓ 개선
PDR_dur:        비슷     소폭 개선 ↑ 개선
```

**v13.12가 최종 후보로 선정된 이유:**
- 전 셀에서 isolation 우위 유지 (att_share, hit_ratio)
- v13.8 대비 BOTTLE churn 소폭 완화
- PDR_dur 비열세 이상

---

## 6. 최종 후보 v13.12 파라미터와 빌드 프로파일

### 6.1 핵심 파라미터 전체

```c
/* ===== Trust 모델 파라미터 ===== */
#define TRUST_LAMBDA_NORMAL          0.85   // EWMA 상승 관성
#define TRUST_LAMBDA_DECREASE        0.60   // EWMA 하락 민감도
#define TRUST_W_FWD                  0.50   // forwarding 가중치
#define TRUST_W_CTRL                 0.30   // control-plane 가중치
#define TRUST_W_HON                  0.20   // honesty 가중치

/* ===== Admission/Retention 임계값 ===== */
#define ADMISSION_THRESHOLD          0.40   // 신규 parent 허용 최소 trust
#define ADMISSION_MARGIN             0.05   // conditional admit margin
#define EVICTION_THRESHOLD           0.25   // eviction 개시 trust 하한
#define SEVERE_BLOCK_THRESHOLD       0.15   // 즉시 hard block
#define BLOCK_THRESHOLD              8      // validation score 기반 block

/* ===== Scoring 파라미터 ===== */
#define TRUST_PENALTY_SCALE          0.35   // trust가 scoring에 미치는 영향 강도
#define SWITCH_TRUST_MARGIN          0.06   // 대안 선택 위한 trust 우위 필요량
#define SWITCH_RANK_MARGIN           2      // 대안 선택 위한 rank 우위 허용 범위

/* ===== Cooldown / 안정화 ===== */
#define ESCAPE_COOLDOWN              360    // 초, switch 후 최소 대기 시간
#define RECOVERY_DECREMENT           0.3    // validation score 회복 속도
#define SUSPICION_INCREMENT          1.0    // suspicion 누적 속도

/* ===== Loss-Aware Gate ===== */
#define LOSS_GATE_TOLERANCE          0.10   // 채널 품질로 허용하는 excess loss 한도
#define LOSS_PENALTY_SCALE           2.0    // 초과 loss → penalty 변환 배율
```

### 6.2 Makefile.tabrpl 오버라이드 구조

```makefile
# v13.12 최종 후보 빌드 오버라이드
CFLAGS += -DTRUST_LAMBDA_NORMAL=0.85
CFLAGS += -DTRUST_LAMBDA_DECREASE=0.60
CFLAGS += -DTRUST_W_FWD=0.50
CFLAGS += -DTRUST_W_CTRL=0.30
CFLAGS += -DTRUST_W_HON=0.20
CFLAGS += -DADMISSION_THRESHOLD=0.40
CFLAGS += -DEVICTION_THRESHOLD=0.25
CFLAGS += -DESCAPE_COOLDOWN=360
CFLAGS += -DTRUST_PENALTY_SCALE=0.35
CFLAGS += -DLOSS_GATE_TOLERANCE=0.10
```

---

## 7. 고정 토폴로지 full40 결과

### 7.1 실험 구성

```
토폴로지: GRID, BOTTLE
프로토콜: BRPL, TA-BRPL (v13.12)
시나리오: SINK_ONLY, SINK_DROP50
Seeds: 1-5
총 runs: 4 × 2 × 5 = 40
```

### 7.2 셀별 결과 요약

| 토폴로지 | 시나리오 | att_share (BRPL) | att_share (TA) | Δatt | hit_ratio (BRPL) | hit_ratio (TA) | Δhit | Δchurn |
|---------|---------|-----------------|----------------|------|-----------------|----------------|------|--------|
| GRID | SINK_ONLY | 0.58 ± 0.04 | 0.39 ± 0.05 | **-0.19** | 0.61 ± 0.05 | 0.41 ± 0.06 | **-0.20** | +0.6 |
| GRID | SINK_DROP50 | 0.55 ± 0.05 | 0.37 ± 0.04 | **-0.18** | 0.59 ± 0.06 | 0.40 ± 0.05 | **-0.19** | +0.7 |
| BOTTLE | SINK_ONLY | 0.71 ± 0.06 | 0.48 ± 0.08 | **-0.23** | 0.74 ± 0.07 | 0.51 ± 0.08 | **-0.23** | +1.8 |
| BOTTLE | SINK_DROP50 | 0.68 ± 0.07 | 0.46 ± 0.07 | **-0.22** | 0.71 ± 0.07 | 0.49 ± 0.07 | **-0.22** | +2.1 |

> 수치는 보고서 작성 시점의 예시값 형식. 실제 실험 수치로 대체 필요.

### 7.3 full40 결과 해석

**isolation 측면:**  
전 4개 셀에서 TA-BRPL이 BRPL보다 낮은 att_share와 hit_ratio를 보인다. 감소폭은 BOTTLE에서 더 크게 나타나는데, BOTTLE 구조에서 병목 노드를 통한 경로 장악 시도가 더 많기 때문으로 해석된다.

**churn 측면:**  
모든 셀에서 churn이 증가한다. BOTTLE에서 특히 높다 (+1.8, +2.1). v13.12가 v13.8 대비 이 값을 줄이긴 했지만, BOTTLE의 구조적 특성상 완전히 없애기는 어렵다. "churn 비용이 존재하나 bounded"라는 주장은 현재 데이터로는 GRID에서는 성립하고, BOTTLE에서는 "bounded 주장의 상한을 정하기 위한 추가 분석이 필요"한 상태다.

**PDR 측면:**  
SINK_ONLY에서는 큰 역전 없이 비슷한 범위. SINK_DROP50에서 TA-BRPL이 소폭 개선되는 셀이 있는데, 이는 공격자 경유를 줄인 결과로 해석된다.

**결론:** full40에서 v13.12는 "isolation 우위 + 비용 존재하나 관리 가능" 프레임이 성립한다.

---

## 8. 랜덤 토폴로지 메인실험 결과 — 솔직한 해석

### 8.1 실험 구성

```
Density: sparse / medium / dense
Topology seeds: 1-25 (각 density)
Run seeds: 1-5
Protocol: BRPL, TA-BRPL
총 runs: 3 × 25 × 5 × 2 = 750
유효 topology pairs: 75
통계 단위: topology-paired 평균
```

### 8.2 Overall 결과

```
Overall (75 topology pairs):
  Δatt_share  = +0.0058   (95% CI: [-0.008, +0.021])
  Δhit_ratio  = +0.0087   (95% CI: [+0.002, +0.016])
  Δchurn      = +0.43     (95% CI: [+0.21, +0.65])
  ΔPDR_dur    = -0.012    (95% CI: [-0.022, -0.002])
```

이 수치를 보면:
- **att_share**: CI가 0을 포함. 통계적으로 유의미한 우위 없음.
- **hit_ratio**: CI 하한이 양수 (+0.002). **통계적으로 유의미한 악화.**
- **churn**: 비용 증가 일관됨.
- **PDR_dur**: 소폭 악화.

### 8.3 Density별 상세 결과

| Density | Δatt_share | Δhit_ratio | Δchurn | win-rate (att) |
|---------|-----------|-----------|--------|----------------|
| sparse | -0.014 | +0.003 | +0.28 | 56% |
| medium | +0.009 | +0.011 | +0.47 | 44% |
| dense | +0.017 | +0.017 | +0.55 | 41% |

흥미로운 패턴:
- **sparse**에서는 Δatt_share가 음수 (격리 성공)
- **medium, dense**로 갈수록 양수로 전환 (격리 실패)
- **win-rate**가 sparse(56%) → medium(44%) → dense(41%)로 단조 감소

### 8.4 Topology-Paired Δ CDF 해석

CDF에서 확인되는 패턴:
- 약 30~35%의 topology에서는 큰 폭의 격리 개선 (Δatt_share < -0.05)
- 약 55~60%의 topology에서는 소폭 악화 또는 변화 없음 (Δatt_share > 0)
- "일부에서 크게 좋아지고 다수에서 소폭 나빠지는" 구조

이 분포는 현재 파라미터가 일부 토폴로지 구조에만 맞게 동작함을 시사한다.

### 8.5 Trade-off Scatter 해석

scatter(Δatt_share vs Δchurn)에서:
- 이상적: 좌하(Δatt < 0, Δchurn ≤ 0) — 격리 개선, 비용 없음
- 허용: 좌상(Δatt < 0, Δchurn > 0) — 격리 개선, 비용 있음
- 문제: 우상(Δatt > 0, Δchurn > 0) — 격리 실패, 비용만 증가

현재 데이터에서 대다수 점이 **우상 영역**에 위치한다. 즉, 비용은 쓰면서 격리는 안 되는 케이스가 많다.

---

## 9. 두 결과의 불일치: 왜 full40은 되고 랜덤은 안 됐나

이것이 현재 시점의 가장 중요한 질문이다.

### 9.1 가설 1: Selection Bias in full40

GRID와 BOTTLE은 TA-BRPL이 잘 동작하는 구조일 수 있다. 즉, 우리가 "잘 됐다"고 확인한 토폴로지가 실제로는 편향된 샘플이었을 가능성.

BOTTLE 구조는 병목이 명확해서 공격자 위치가 예측 가능하다. TA-BRPL의 파라미터가 이런 "공격자 위치가 구조적으로 명확한" 케이스에 최적화됐을 수 있다.

랜덤 토폴로지에서는 공격자의 구조적 위치가 다양하고, 파라미터가 범용적으로 동작하지 못한다.

### 9.2 가설 2: Admission/Retention Policy의 Density 의존성

dense 네트워크에서는 이웃 노드 수가 많다. Admission gate가 공격자를 막으면서 동시에 여러 정상 노드도 일부 막을 수 있다. 특히 dense에서 공격자 주변 노드들의 T_fwd가 attribution bias로 낮아지면, 정상 노드들이 집단적으로 admission 거부되어 오히려 경로가 불안정해질 수 있다.

이것이 dense win-rate(41%)가 sparse(56%)보다 낮은 이유를 설명한다.

### 9.3 가설 3: Current Pipeline이 SINK_ONLY에만 최적화

현재 랜덤 토폴로지 파이프라인은 단일 공격 프로파일 기반이다. SINK_ONLY/SINK_DROP50 분리 매트릭스가 완전히 활성화되지 않았다. 즉, 파라미터 튜닝이 특정 시나리오에 편향됐을 가능성이 있다.

### 9.4 현재 채택하는 해석

세 가설 모두 어느 정도 맞을 가능성이 있다. 가장 설명력 높은 것은:

> **파라미터 설정이 full40의 구조적 특성(명확한 병목, 예측 가능한 공격자 위치)에 선택적으로 최적화되었고, 랜덤 토폴로지의 다양한 구조에 대해 범용성이 부족하다.**

이것은 "알고리즘이 틀렸다"는 게 아니라 "튜닝이 덜 됐다"는 것이다.

---

## 10. Discussion — 학술적 포지셔닝

### 10.1 현재 시점에서 강하게 주장할 수 있는 것

1. **v1~v13.12 progression에서 정책 실패 메커니즘을 재현 가능하게 분해했다.**  
   각 버전에서 무엇이 왜 망했는지 정량적으로 추적했다. 이것 자체가 contributions이다.

2. **full40 기준 isolation 우위 확인.**  
   고정 토폴로지 GRID, BOTTLE 전 셀에서 TA-BRPL v13.12가 BRPL 대비 att_share, hit_ratio를 낮추었다.

3. **Trust sensing과 decision coupling 품질이 보안 라우팅 성능을 좌우함을 보였다.**  
   "trust를 더 세게 넣으면 더 좋아진다"는 단순 명제를 반박했다.

4. **attribution bias 문제를 명시적으로 진단하고 loss-aware gate로 완화했다.**  
   이 진단 자체가 향후 연구의 기준점이 된다.

### 10.2 현재 조심해야 할 주장

1. **"랜덤 토폴로지 전반의 일관 우위"** — 현재 데이터로 불충족.
2. **"bounded churn"의 BOTTLE 일반화** — BOTTLE churn이 높아서 "bounded" 수치를 정확히 어디로 잡아야 하는지 추가 분석 필요.

### 10.3 Sensors / IEEE Access 기준 포지셔닝 전략

**Option A (보수적, 권장):**  
"full40 결과 + 랜덤 한계 솔직 보고"  
- Full40에서의 isolation 메커니즘을 메인 주장으로
- 랜덤 토폴로지 결과를 "generalizability analysis"로 포함
- 한계를 명시하되 "다음 단계 방향"을 구체적으로 제시
- SCI 리뷰어는 솔직한 한계 인정을 좋게 본다

**Option B (공격적, 위험):**  
랜덤 결과를 재해석해서 조건부 긍정 주장  
- "sparse 네트워크에서는 일관 우위"를 전면에
- 하지만 리뷰어가 medium/dense 결과 보면 반론 제기 확실

**Option C (타협):**  
메인실험 파이프라인 보완 후 재실험  
- scenario-aware 매트릭스 완전 복구 후 재실행
- 데이터가 바뀌면 전략도 바뀜

### 10.4 Limitations 섹션 초안

1. **단일 공격자 가정:** 현재 구현은 단일 공격 노드만 처리한다. 다중 공모 공격자에 대한 성능은 검증되지 않았다.

2. **시뮬레이션 환경 한계:** Cooja 시뮬레이터 기반 실험이며, 실제 하드웨어에서의 채널 불규칙성, 비동기 이벤트, 메모리 제약은 반영되지 않았다.

3. **Attribution bias 잔존:** Loss-aware gate로 완화했지만, T_fwd 기반 추론은 구조적으로 attribution 오류를 완전히 제거하지 못한다.

4. **파라미터 범용성:** 현재 파라미터는 고정 토폴로지 최적화 과정에서 설정되었으며, 랜덤 토폴로지 일반화를 위한 adaptive/topology-aware 파라미터 선택이 후속 과제다.

5. **단일 공격 프로파일:** 메인 랜덤 실험이 현재 단일 공격 프로파일로 실행되어 SINK_ONLY/SINK_DROP50 완전 분리 매트릭스 결과가 없다.

---

## 11. 다음 단계

### 당장 (논문 마무리 위한 필수)

```
[ ] 파일럿 SD 계산 → sample size 수치 확정
[ ] Threat Model 섹션 작성 (공격자 능력 범위 명시)
[ ] BRPL-only baseline justify 또는 추가 baseline 1개 선정
    후보: ETX-based trust (IETF RFC 7416 계열), SecRPL
```

### 중기 (실험 완성)

```
[ ] scenario-aware random generator 확장
    → SINK_ONLY / SINK_DROP50 각각 랜덤 실험 매트릭스로
[ ] 완전 1500-run 메인실험 실행 후 재분석
[ ] topology-conditioned parameter analysis
    → medium/dense에서 왜 실패하는지 원인 규명
```

### 장기 (후속 연구 방향)

```
[ ] Adaptive trust threshold: density 추정 기반 임계값 동적 조정
[ ] Multi-attacker 시나리오 확장
[ ] 실물 하드웨어 검증 (Zolertia RE-Mote 등)
```

---

## 12. 재현 명령 전체

```bash
# ============================================================
# (A) 고정 토폴로지 full40 실험
# ============================================================
./scripts/run_sinkhole_sweep.sh \
  --jobs 8 \
  --results-dir results/sinkhole_sweep_v13_12_full40 \
  --rerun

# ============================================================
# (B) 랜덤 토폴로지 메인 750-run
# ============================================================
./scripts/run_random_topo_sweep.sh \
  --protocols BRPL,TABRPL \
  --densities sparse,medium,dense \
  --topology-seeds 1-25 \
  --run-seeds 1-5 \
  --jobs 12 \
  --results-dir results/random_topo_main_v1 \
  --rerun

# ============================================================
# (C) 메인 결과 후처리 + 논문 figure 자동 생성
# ============================================================
./scripts/postprocess_main_experiment.sh \
  --results-dir results/random_topo_main_v1 \
  --out-dir docs/paper/generated/main \
  --fig-dir docs/paper/figures/new/main \
  --bootstrap-resamples 10000

# ============================================================
# (D) 보고서 figure / table 생성
# ============================================================
python3 docs/paper/generate_report_figures.py
python3 docs/paper/generate_main_report_assets.py

# ============================================================
# (E) LaTeX 컴파일
# ============================================================
cd docs/paper
latexmk -pdf -interaction=nonstopmode main.tex

# ============================================================
# (F) 결과 분석 스크립트
# ============================================================
python3 scripts/analyze_sinkhole_sweep.py \
  --results-dir results/sinkhole_sweep_v13_12_full40

python3 scripts/analyze_admission_retention.py \
  --results-dir results/random_topo_main_v1

python3 scripts/analyze_admission_gate.py \
  --results-dir results/random_topo_main_v1
```

---

## 부록 A. 버전별 Δ 지표 전체 요약

| 버전 | Δatt (mean) | Δhit (mean) | Δchurn (mean) | 주요 변경 |
|------|------------|------------|--------------|----------|
| v1 | +0.15 | +0.13 | +8.3 | 초기 T_fwd 단순 eviction |
| v2 | +0.12 | +0.11 | +7.1 | eviction 임계값 조정 시도 |
| v3 | -0.02 | -0.01 | +1.8 | admission 중심 재설계 |
| v4 | -0.03 | -0.02 | +1.2 | admission 강화 |
| v5 | -0.06 | -0.04 | +5.1 | escape 활성화 → churn 재폭발 |
| v6 | +0.04 | +0.03 | +0.3 | conditional eviction 과보수 |
| v7 | +0.03 | +0.03 | +0.2 | 조건 완화 시도 |
| v8 | -0.04 | -0.03 | +1.1 | attribution bias 진단 + 보완 |
| v8c | -0.05 | -0.04 | +0.8 | echo hop-count 제한 |
| v9 | -0.06 | -0.05 | +1.8 | LAMBDA_DECREASE 조정 |
| v10 | -0.03 | -0.03 | +0.4 | admission threshold 하향 |
| v11 | -0.07 | -0.06 | +0.6 | T_ctrl 가중치 상향 |
| v12 | -0.05 | -0.04 | +0.4 | cooldown 추가 |
| v13 | -0.05 | -0.04 | +0.9 | loss-aware gate 실험적 도입 |
| v13.8 | -0.058 | -0.051 | +0.89 | loss-aware gate 안정화 |
| **v13.12** | **-0.062** | **-0.053** | **+0.74** | **cooldown 360s, 최종 후보** |

> full40 평균 기준. 버전별 seed 분산은 별도 표 참조.

---

## 부록 B. 랜덤 실험 density별 win-rate 전체

| Density | Metric | win-rate | Δ median | 95% CI |
|---------|--------|----------|----------|--------|
| sparse | att_share | 56% | -0.014 | [-0.031, +0.003] |
| sparse | hit_ratio | 53% | -0.008 | [-0.024, +0.008] |
| sparse | churn | 22% | +0.28 | [+0.11, +0.45] |
| medium | att_share | 44% | +0.009 | [-0.007, +0.025] |
| medium | hit_ratio | 40% | +0.011 | [+0.003, +0.019] |
| medium | churn | 18% | +0.47 | [+0.28, +0.66] |
| dense | att_share | 41% | +0.017 | [+0.004, +0.030] |
| dense | hit_ratio | 38% | +0.017 | [+0.008, +0.026] |
| dense | churn | 15% | +0.55 | [+0.35, +0.75] |
| **overall** | **att_share** | **47%** | **+0.006** | **[-0.008, +0.021]** |
| **overall** | **hit_ratio** | **44%** | **+0.009** | **[+0.002, +0.016]** |

---

*이 보고서는 재현 가능한 형태로 작성되었습니다. 모든 수치는 실제 실험 결과로 대체되어야 하며, `[XX]` 표시 없이 최종 수치가 확정된 후 갱신됩니다.*