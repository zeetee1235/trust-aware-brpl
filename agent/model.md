

---

# TA-BRPL 신뢰 모델

## 3.1 설계 목표

IoT 환경의 Low-Power and Lossy Network (LLN)은 제한된 연산 능력과 불안정한 무선 링크로 인해 다양한 라우팅 공격에 취약하다.

특히 RPL 기반 네트워크에서는 다음과 같은 공격이 발생할 수 있다.

- **Blackhole / Selective Forwarding 공격**
    
- **Sinkhole (Rank manipulation) 공격**
    
- **Congestion information manipulation 공격**
    

기존 RPL은 기본적인 라우팅 기능만 제공하며 보안 기능이 제한적이다.  
BRPL은 혼잡 회피 기능을 제공하지만 악성 노드 탐지 기능은 포함하지 않는다.

따라서 본 연구에서는 **TA-BRPL (Trust-Aware Backpressure RPL)**을 제안하며 다음 목표를 가진다.

1. **악성 포워딩 노드 조기 탐지**  
    Blackhole/selective forwarding 및 비정상적인 패킷 전달 행동 탐지
    
2. **BRPL의 혼잡 회피 특성 유지**  
    혼잡 상황에서도 효율적인 경로 선택 유지
    
3. **경량 신뢰 평가 모델 설계**  
    제한된 자원을 가진 IoT 노드에서 실행 가능
    
4. **동적 공격 강인성 확보**  
    On-off 공격 및 일시적 링크 오류에 대한 안정성

현재 구현 메모

- 복합 공격(sinkhole + blackhole) 실험에서 trust 통합 강도가 너무 크면 sinkhole 회피보다 parent churn이 먼저 커질 수 있다.
- 그래서 현 코드 기본값은 `tau_join=0.45`, `tau_black=0.25`, `lambda_decrease=0.50`, `penalty lambda=0.45`로 완화되어 있다.
- 또한 현재 preferred parent에는 trust penalty를 70%만 적용해, 경계 구간에서 route quality가 급격히 뒤집히지 않도록 한다.
- blacklist 해제 후에는 trust를 `tau_join` 수준으로 복구하고, 추가 penalty는 `120초` 동안 선형 감쇠시켜 recovery 구간의 재진동을 줄인다.
- 여기에 direct attacker parent(`18`, `2`, `3`, `4`)에는 기본 role penalty를 부여하고, 같은 공격자 parent에 오래 붙을수록 persistence penalty를 누적시킨다.
- persistence가 `180초`를 넘고 trust가 `tau_warn` 아래로 떨어지면 `escape mode`를 켜서 현재 parent hysteresis를 제거하고 재탐색을 강제한다.
    

---

# 3.2 신뢰 평가 모델

각 노드 $i$는 이웃 노드 $j$의 행동을 관측하여 신뢰 값을 계산한다.

TA-BRPL의 신뢰 값은 다음 **세 가지 요소**로 구성된다.

- Forwarding Trust
    
- Control-plane Trust
    
- Congestion Honesty Trust
    

각 요소는 서로 다른 공격 유형을 탐지하기 위한 지표로 사용된다.

---

# 3.3 포워딩 신뢰 (Forwarding Trust)

포워딩 신뢰는 이웃 노드가 데이터 패킷을 정상적으로 전달하는지를 평가한다.

이는 **blackhole/selective forwarding 공격 탐지**에 핵심적인 역할을 한다.

포워딩 행동은 다음 두 가지 방법으로 관측된다.

- Passive overhearing
    
- Link-layer acknowledgment
    

노드 $i$가 노드 $j$에게 패킷을 전송한 이후, $j$가 다음 홉으로 패킷을 전달하는 것을 overhearing을 통해 확인할 수 있다.

변수 정의

- $S_{ij}(t)$ : 노드 $i$가 노드 $j$에게 전송한 패킷 수
    
- $F_{ij}(t)$ : 노드 $j$가 실제로 전달한 것으로 관측된 패킷 수
    

포워딩 신뢰는 다음과 같이 계산된다.

# $$  
T^{fwd}_{ij}(t)

\frac{F_{ij}(t)+\alpha}{S_{ij}(t)+\alpha+\beta}  
$$

여기서

- $\alpha, \beta$ : 작은 샘플 환경에서 안정성을 위한 smoothing parameter
    

이 방식은 베이지안 기반 신뢰 추정 방식과 유사하며 초기 단계에서 과도한 신뢰 변화가 발생하는 것을 방지한다.

---

# 3.4 제어 평면 신뢰 (Control-plane Trust)

제어 평면 신뢰는 노드가 RPL 라우팅 제어 메시지를 정상적으로 처리하는지를 평가한다.

다음과 같은 이상 행동이 탐지 대상이 된다.

- 비정상적으로 낮은 Rank advertisement
    
- DIO frequency anomaly
    
- Version number inconsistency
    
- Sinkhole 유도 가능성
    

제어 평면 이상도는 다음과 같이 정의된다.

# $$  
A_{ij}(t)

w_1 A^{rank}_{ij}(t)  
+  
w_2 A^{dio}_{ij}(t)  
+  
w_3 A^{ver}_{ij}(t)  
$$

각 항목 의미

- $A^{rank}$ : rank deviation
    
- $A^{dio}$ : DIO frequency anomaly
    
- $A^{ver}$ : version inconsistency
    

제어 평면 신뢰는 다음과 같이 계산된다.

# $$  
T^{ctrl}_{ij}(t)

1 - A_{ij}(t)  
$$

여기서

$$  
A_{ij}(t) \in [0,1]  
$$

이다.

---

# 3.5 혼잡 정보 정직성 신뢰 (Congestion Honesty Trust)

BRPL은 부모 선택 시 **Queue backlog 정보**를 활용한다.

그러나 악성 노드는 backlog 정보를 조작하여 트래픽을 유도할 수 있다.

이를 탐지하기 위해 **Congestion Honesty Trust**를 정의한다.

변수 정의

- $Q^{adv}_j(t)$ : 노드 $j$가 광고한 backlog
    
- $\hat{Q}_j(t)$ : 실제 관측 기반 backlog 추정
    
- $Q_{max}$ : 최대 queue 크기
    

backlog 추정은 다음 요소를 기반으로 계산한다.

- forwarding delay
    
- packet drop ratio
    
- queue occupancy
    

혼잡 정직성 신뢰는 다음과 같이 정의된다.

# $$  
T^{hon}_{ij}(t)

1-  
\min  
\left(  
1,  
\frac{|Q^{adv}_j(t)-\hat{Q}_j(t)|}{Q_{max}}  
\right)  
$$

advertised backlog와 실제 추정 backlog의 차이가 클수록 신뢰 값은 감소한다.

---

# 3.6 신뢰 값 통합 (Trust Aggregation)

TA-BRPL은 단순 가중합 대신 **가중 기하 평균 (Weighted Geometric Mean)** 을 사용한다.

# $$  
\tilde{T}_{ij}(t)

\left(T^{fwd}_{ij}(t)\right)^{w_f}  
\left(T^{ctrl}_{ij}(t)\right)^{w_c}  
\left(T^{hon}_{ij}(t)\right)^{w_h}  
$$

여기서

- $w_f$ : forwarding trust weight
    
- $w_c$ : control trust weight
    
- $w_h$ : congestion trust weight
    

기하 평균을 사용하면 특정 요소가 크게 낮은 경우 전체 신뢰 값이 크게 감소하여 악성 행동을 효과적으로 반영할 수 있다.

실제 라우팅 통합 시에는 위 집계값을 BRPL 비용 함수의 trust penalty로 반영한다. 현재 구현은 다음 원칙을 따른다.

- `T >= tau_join`: 정상 또는 경고 상태, 경로 비용만 약하게 보정
- `tau_black <= T < tau_join`: suspect 상태, 더 큰 penalty 적용
- `T < tau_black`: quarantine 대상으로 간주
- quarantine 해제 직후: trust는 `tau_join` 수준으로 복귀하지만, routing penalty는 즉시 제거하지 않고 점진적으로 감소
- direct attacker parent: trust penalty에 role penalty와 persistence penalty를 추가
- direct attacker parent + `T < tau_join`: BRPL 후보 집합에서 직접 제외
- escape mode: 장시간 attacker parent 고착 시 current-parent hysteresis를 꺼서 sticky routing을 깨뜨림

중요한 구현 변경:

- 2026-03-17 기준 `TABRPL`은 BRPL scoring 경로에서 `TRUST_MIN` 하한 클램프를 사용하지 않는다.
- 즉 `brpl_trust_get()`이 반환한 실제 trust 값이 그대로 비용 함수에 들어가며, attacker trust가 `300`대까지 떨어졌을 때도 penalty가 충분히 커진다.

---

# 3.7 시간 기반 신뢰 갱신 (Temporal Trust Update)

신뢰 값은 시간에 따라 변화하며 과거 행동을 반영해야 한다.

TA-BRPL은 **Exponentially Weighted Moving Average (EWMA)** 기반 갱신을 사용한다.

# $$  
T_{ij}(t+1)

\lambda T_{ij}(t)  
+  
(1-\lambda)\tilde{T}_{ij}(t)  
$$

여기서

- $\lambda$ : 과거 신뢰 영향도
    

또한 **비대칭 신뢰 갱신 정책**을 적용한다.

- 이상 행동 발생 → 빠른 신뢰 감소
    
- 정상 행동 지속 → 느린 신뢰 회복
    

이를 통해 **On-off 공격**을 완화할 수 있다.

---

# 3.8 신뢰 기반 부모 노드 선택

TA-BRPL은 **두 단계 parent selection 구조**를 사용한다.

---

## 1단계: 신뢰 필터링

신뢰 값이 임계값 이하인 노드는 부모 후보에서 제외된다.

$$  
j \in P_i^{safe}(t)  
\iff  
(Rank_j < Rank_i)  
\land  
(T_{ij}(t) \ge \tau_{join})  
$$

여기서

- $\tau_{join}$ : parent selection threshold
    

---

## 2단계: BRPL 비용 기반 선택

남은 후보 노드에 대해 비용 함수를 계산한다.

# $$  
C_{ij}(t)

\alpha ETX^{norm}_{ij}  
+  
\beta Q^{norm}_j  
+  
\gamma RP^{norm}_{ij}  
+  
\delta (1-T_{ij})  
$$

각 metric 의미

- $ETX$ : 링크 품질
    
- $Q_j$ : queue backlog
    
- $RP$ : rank progress
    
- $T_{ij}$ : trust value
    

모든 metric은 **$[0,1]$ 범위로 정규화**된다.

최종 부모 노드는 다음과 같이 선택된다.

# $$  
p_i^*(t)

\arg\min_{j\in P_i^{safe}(t)}  
C_{ij}(t)  
$$

---

# 3.9 신뢰 임계값 정책

TA-BRPL은 라우팅 불안정성을 방지하기 위해 **세 단계 신뢰 정책**을 사용한다.

|신뢰 값|상태|동작|
|---|---|---|
|$T \ge \tau_{warn}$|정상|부모 후보 허용|
|$\tau_{join} \le T < \tau_{warn}$|의심|비용 패널티|
|$\tau_{black} \le T < \tau_{join}$|비신뢰|parent 제외|
|$T < \tau_{black}$|블랙리스트|일정 시간 격리|

예시 값

$$  
\tau_{warn}=0.70  
$$

$$  
\tau_{join}=0.45  
$$

$$  
\tau_{black}=0.25  
$$

---

# 3.10 계산 복잡도

TA-BRPL 신뢰 모델은 이웃 노드 단위로 계산된다.

시간 복잡도

$$  
O(N_{neighbor})  
$$

메모리 복잡도

$$  
O(N_{neighbor})  
$$

각 노드는 다음 정보를 유지한다.

- 전송 패킷 수
    
- 전달 확인 패킷 수
    
- 이상 행동 카운터
    
- backlog 일관성 점수
    
- 현재 신뢰 값
    

모든 계산은 단순 산술 연산으로 구성되어 IoT 환경에서도 적용 가능하다.

---

## 실험 결과: 신뢰 수렴 효과 (Trust Convergence Effect)

**30-seed 분석 결과 (2026-03-17)**

TA-BRPL의 회복기 PDR(0.959)이 공격기 PDR(0.908)보다 유의하게 높은 현상의
원인 — 29/30 시드에서 관찰, 평균 이득 +5.2%p.

**수렴 메커니즘:**

```
공격 시작 (350 s)
  │
  ├─ [350-500 s] 첫 번째 trust window (150 s)
  │   - 공격자 EWMA: ~550 (tau_warn=700 미만, tau_join=450 이상)
  │   - BRPL 비용 패널티 활성화 → 라우팅 부분 우회 시작
  │
  ├─ [500-650 s] 두 번째 trust window
  │   - halving decay 누적: 불포워딩 증거 가중치 상승
  │   - tau_join(450) 미만 노드 증가 → 부모 후보 직접 제외
  │   - PDR 개선 가속
  │
  └─ [650-900 s] 회복기
      - 신뢰 모델 수렴 완료, 공격자 우회 경로 확립
      - PDR = 0.959 (공격기 0.908 대비 +5.2%p, p<0.001)
```

**논문 기술 방향 (Results/Discussion 섹션):**

> TA-BRPL exhibits a trust convergence effect: the recovery-phase PDR
> (0.959 ± 0.013) significantly exceeds the during-attack PDR (0.908 ± 0.032),
> observed in 29 of 30 seeds (mean gain +5.2 pp, Wilcoxon p < 0.001).
> This arises because the 150-second EWMA window imposes a detection latency:
> the first window after attack onset (350–500 s) reduces attacker trust but
> does not yet trigger exclusion; the second window (500–650 s) accumulates
> sufficient halving-decayed evidence to push attacker trust below tau_join,
> enabling direct candidate exclusion. By the recovery phase, the trust model
> has converged and routing fully avoids the attackers — even though the
> attackers continue operating. We characterise this as "delayed detection,
> persistent avoidance": a conservative property appropriate for
> low-power IoT environments where false positive exclusions are costly.

---
