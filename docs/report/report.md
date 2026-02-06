# Trust-Aware BRPL (Selective Forwarding) Report

## 1. 한 줄 정의 (Elevator pitch)

> **Trust-Aware BRPL**은
> *Backpressure 기반 라우팅(BRPL)에 **노드 신뢰도(Trust)**를 결합하여,
> 공격 노드가 경로에 포함되는 빈도(Exposure)를 줄이고
> Selective Forwarding과 같은 내부 공격에 대한 **내재적 회복력(resilience)**을 분석·향상시키는 접근이다.

핵심은 **탐지(detection)**가 아니라
👉 **라우팅 선택 단계에서 공격 노드를 “덜 쓰게 만드는 구조적 효과”**다.

---

## 2. 왜 기존 BRPL / RPL로는 부족한가 (Problem Framing)

### 2.1 RPL의 구조적 한계

* Objective Function(OF)는 주로:

  * ETX
  * Hop count
  * Energy
* **행동 기반 정보 없음**

  * 패킷을 버리는지
  * forwarding을 성실히 하는지
    → 내부 공격자에 *맹목적*

---

### 2.2 BRPL의 장점과 공백

**BRPL의 장점**

* Queue backlog 기반 → 트래픽 적응성
* Path diversity 증가 → 특정 경로 의존 감소

**하지만**

* 공격 노드도 **정상 노드처럼 backlog만 낮으면 선택됨**
* 즉,

  > *“BRPL은 load에는 똑똑하지만, trust에는 눈이 멀어 있다”*

---

## 3. Trust-Aware BRPL의 핵심 아이디어

### 3.1 기본 구조

BRPL의 parent selection metric에 **Trust 항(term)**을 추가:

```
Weight = α · Backpressure
       + β · Link Quality
       + γ · Trust
```

또는 penalty 방식:

```
Effective Backpressure = BP × Trust
```

👉 Trust ↓ ⇒ 경로 선택 확률 ↓

---

### 3.2 Trust란 무엇인가? (정의가 핵심임)

Trust는 **“이 노드를 경유했을 때 패킷이 살아서 도착할 확률에 대한 경험적 추정치”**

예시 정의:

* **Forwarding ratio**

  ```
  Trust_i = forwarded_packets / received_packets
  ```
* EWMA 적용 가능:

  ```
  Trust_i(t) = λ·Trust_i(t−1) + (1−λ)·obs_i(t)
  ```

중요 포인트:

* 암호 ❌
* IDS ❌
* ML ❌
  👉 **경량 + 분산 + 로컬 관측**

---

## 4. 연구에서 진짜 중요한 관점

### 4.1 “성능 향상”이 아니라 “구조적 효과”를 봐야 함

단순히:

* PDR ↑
* Delay ↓

이건 **논문 레벨에서 약함**

대신, 네가 봐야 할 질문은 이거다:

> **Trust-Aware BRPL은
> 공격 노드를 네트워크 구조상 얼마나 ‘고립’시키는가?**

---

### 4.2 핵심 분석 변수: Exposure

이게 너의 킬러 포인트다.

**Exposure 정의 예시**

* E1: 경로 포함률

  > 전체 패킷 중 attacker를 경유한 비율
* E2: 서브트리 트래픽 비중

  > attacker subtree를 흐르는 traffic 비율
* E3: 시간 기반 포함률

  > attacker가 preferred parent인 시간 비율

그리고 관계식:

```
PDR drop ≈ AttackRate × Exposure
```

👉 Trust는 **AttackRate를 줄이지 않음**
👉 **Exposure를 줄인다**

이 프레임 잡으면 교수/리뷰어 바로 고개 끄덕인다.

---

## 5. Research Questions (RQ)

### RQ1

> Trust-aware BRPL은 Selective Forwarding 공격 하에서
> 공격 노드의 **Exposure를 얼마나 감소시키는가?**

### RQ2

> Path Diversity가 증가할수록
> Trust 정보의 효과는 증폭되는가, 상쇄되는가?

### RQ3

> Trust update 속도(λ)와 공격 강도(α) 사이에
> 안정–진동–붕괴 임계점이 존재하는가?

---

## 6. 실험 설계 (Cooja 기준)

### 비교군

* RPL
* BRPL
* **Trust-Aware BRPL**

### 공격 모델

* Selective Forwarding (α = 0.1 ~ 0.9)
* 위치 고정 (중간 parent)

### 측정 지표

* PDR
* Delay
* Control overhead
* **Exposure (필수)**
* Parent switching rate (부가 지표)

---

## 7. 이 주제의 “논문 포지션”

이건 방어 논문이 아니다.

> ❌ “공격을 탐지했다”
> ❌ “보안이 강화됐다”

대신:

> ✅ “라우팅 구조 관점에서
> 내부 공격이 **언제, 얼마나 관측 가능/완화 가능한지** 분석했다”

Trust 수식은 “그럴듯해 보이는 휴리스틱”이면 안 되고,
👉 **왜 이 정의가 합리적인지에 대한 근거 사슬**이 반드시 있어야 한다.

---

## 8. Trust 정의의 근거 (논문용 방어 논리)

### 8.1 Trust를 무엇으로 볼 것인가 (개념적 출발점)

> **Trust = 해당 노드를 경유한 패킷이 정상적으로 전달될 조건부 확률**

수식적으로:

```
T_i := P(packet delivered | forwarded by node i)
```

이 정의는 다음과 연결된다:

* Selective Forwarding 공격 = 이 확률을 인위적으로 낮춤
* Routing metric에 들어가도 **의미 보존**

---

### 8.2 관측 가능한 근사치로의 환원

직접 관측 불가 → **local observable estimator**로 근사

```
T̂_i = N_i^{fwd} / N_i^{rx}
```

* Bernoulli trial 기반 **빈도 추정**
* Maximum Likelihood Estimator (MLE)

---

### 8.3 시간 가변 환경을 고려한 안정화 (EWMA)

```
T_i(t) = λ·T_i(t−1) + (1−λ)·T̂_i(t)
```

* Low-pass filter 역할
* 링크 변동/일시적 충돌을 흡수

---

## 9. Trust를 라우팅에 넣는 방식의 정당성

### 9.1 Backpressure의 의미 재해석

```
BP_ij = Q_i − Q_j − c_ij
```

이는 “j로 보냈을 때 **성공적으로 전달될 잠재력**”

Trust는 이 성공 확률을 조정하는 항이다.

---

### 9.2 확률적 관점에서의 결합

```
E[Progress_ij] ∝ BP_ij × P(success via j)
P(success via j) ≈ T_j
```

따라서:

```
BP_trust_ij = BP_ij × T_j
```

👉 임의 가중치가 아닌 **의미 보존 결합**

---

## 10. 공격 모델과의 수학적 연결

Selective Forwarding 공격에서:

```
T_i ≈ 1 − α
```

Exposure가 주어지면:

```
PDR ≈ 1 − α · Exposure
```

Trust-aware routing의 효과는:

```
Exposure_trust < Exposure_BRPL
```

→ PDR 향상은 **탐지 덕분이 아니라**
→ **노출 감소(Exposure reduction)** 덕분

---

## 11. 구현 메모 (현 코드 기준)

* **Trust 계산**: forwarder의 `CSV,FWD` 로그를 이용하여 forwarding ratio를 추정하고 EWMA로 평활화.
* **Trust 전달**: trust_engine이 `TRUST,<node>,<value>` 형태로 motes에 주입.
* **Exposure 측정**: `CSV,FWD` 및 `CSV,PARENT` 로그를 통해 attacker 노드 노출률을 계산.
* **스케일링**: 내부 계산은 0~1, 무선 노드 전달은 0~1000 스케일.

---

## 12. 논문용 Trust 정의 섹션 (바로 사용 가능)

> **Definition of Trust**  
> In this work, trust is defined as the conditional probability that a packet is successfully forwarded when routed through a given node.  
> Since this quantity is not directly observable, we estimate it using the forwarding ratio based on locally monitored packet transmissions.  
> To mitigate short-term fluctuations caused by wireless dynamics, an exponentially weighted moving average (EWMA) is employed.  
> This trust value is then incorporated into the BRPL backpressure metric as a multiplicative scaling factor, reflecting the expected effective forwarding utility.
