
---

# 논문/연구 큰 방향

## 핵심 메시지

> **Sinkhole은 즉시 패킷을 버리지 않더라도, 먼저 네트워크를 장악할 수 있다.**
> 그리고 그 장악된 위치는 이후 **selective forwarding / packet drop**으로 언제든 availability 공격으로 전환될 수 있다.
> 따라서 방어의 핵심은 단순 PDR 방어만이 아니라,
> **공격자의 경로 지배력(route capture)을 줄이고, 장악 이후의 피해를 완화하는 것**이다.

이걸 바탕으로:

* **시나리오 1 = Sinkhole only**
* **시나리오 2 = Sinkhole + Packet Drop**

두 단계로 갑니다.

그리고 프로토콜은 일단:

> **BRPL 기반 trust-aware routing (TA-BRPL)**

로 유지하되,
논문의 주인공은 **BRPL 자체가 아니라 sinkhole 방어**로 둡니다.

---

# 1. 논문 제목(러프 후보)

### 한국어 스타일

1. **LLN 환경에서 Sinkhole 기반 경로 장악 및 선택적 패킷 손실 공격에 대한 Trust-Aware BRPL 방어 기법**
2. **Contiki-NG/Cooja 기반 LLN에서 Sinkhole Route Capture 완화를 위한 TA-BRPL**
3. **Trust-Aware BRPL을 이용한 LLN Sinkhole 경로 장악 및 전달성 저하 공격 대응**

### 영어 스타일

1. **TA-BRPL: Trust-Aware BRPL Against Sinkhole-Induced Route Capture in LLNs**
2. **Mitigating Sinkhole Route Capture and Selective Packet Dropping in LLNs via Trust-Aware BRPL**
3. **A Trust-Aware BRPL Approach for Resilient Routing Under Sinkhole and Packet-Dropping Attacks**

---

# 2. 한 줄 논문 포지션

이 논문은 사실상 이렇게 설명하면 됩니다:

> **“우리는 PDR만 보지 않는다.**
> **먼저 공격자가 네트워크를 장악하는 문제를 정의하고,**
> **그 장악이 실제 packet dropping으로 이어졌을 때의 피해를 함께 평가한다.”**

이게 중요합니다.
왜냐면 이 framing 덕분에:

* sinkhole only에서 PDR 차이가 작아도 논리적으로 의미가 생기고
* sinkhole+drop에서 PDR 방어도 자연스럽게 연결됩니다.

즉 논문이 **“PDR이 안 오르면 망했다”**에서 벗어날 수 있습니다.

---

# 3. 연구 질문 (Research Questions)

이건 논문 뼈대라서 아주 중요합니다.

## RQ1.

**Sinkhole 공격은 패킷 드롭이 없더라도 LLN에서 경로 장악(route capture)을 유의미하게 유발하는가?**

→ 시나리오 1에서 검증

---

## RQ2.

**Trust-aware parent selection은 sinkhole에 의한 attacker dependency를 줄일 수 있는가?**

→ attacker parent share, exposure, subtree size로 검증

---

## RQ3.

**경로 장악된 sinkhole이 selective packet dropping으로 전환될 때, TA-BRPL은 전달성(PDR) 붕괴를 완화할 수 있는가?**

→ 시나리오 2에서 검증

---

## RQ4.

**이러한 방어는 churn, control overhead, delay 측면에서 어느 정도 trade-off를 갖는가?**

→ 부작용 평가

---

# 4. 위협 모델 (Threat Model)

이 부분은 논문에서 꽤 중요합니다.

---

## 4.1 네트워크 가정

* 대상 환경: **Low-power and Lossy Network (LLN)**
* 다수 센서 노드가 단일 root로 트래픽을 전송
* 라우팅은 BRPL 기반 DODAG 구조
* 공격자는 내부 노드 1개 (합법적으로 네트워크에 참여 가능한 compromised node)

---

## 4.2 공격자 능력

공격자는 다음을 수행 가능:

1. **Sinkhole behavior**

   * 유리한 parent처럼 보이도록 rank/경로 attractiveness 조작
   * 주변 노드가 자신을 preferred parent로 선택하도록 유도

2. **Packet dropping behavior**

   * 자신을 경유하는 패킷 중 일부 또는 전부를 드롭
   * selective forwarding / grayhole / blackhole 형태 가능

---

## 4.3 공격 단계

### Phase 1 — Route Capture

공격자는 우선 **자신을 경유하는 트래픽 비율을 높이는 것**을 목표로 함.

### Phase 2 — Availability Degradation

충분한 경로 장악 이후, 공격자는 **선택적 패킷 손실**을 통해 가용성을 저하시킴.

---

## 4.4 방어 목표

방어 목표는 단순히 “즉시 PDR 최대화”가 아니라:

* 공격자 parent 선택 비율 감소
* 공격자 경유 트래픽 감소
* packet drop 발생 시 PDR 붕괴 완화
* 과도한 churn/overhead 없이 동작

---

# 5. 시스템/기법 설명 (러프)

여기서는 아주 복잡하게 가지 말고, 일단 러프하게 이렇게 둡니다.

---

## 5.1 기본 아이디어

TA-BRPL은 각 후보 parent에 대해:

* **기존 BRPL 라우팅 metric**
* **신뢰도(trust)**

를 함께 고려하여 parent를 선택합니다.

즉, 단순히 “좋아 보이는 rank”만 따라가지 않고,

> **“전달 행위와 제어행위 모두에서 의심스러운 노드”를 덜 선호**

하도록 만듭니다.

---

## 5.2 Trust 구성 (논문 초안 수준)

신뢰도는 2개 축으로 둡니다:

### (A) Forwarding trust

* 패킷 전달 성공/실패 관측 기반
* selective forwarding / grayhole 탐지 목적

### (B) Control-plane trust

* 비정상적인 sinkhole 유인 행위 탐지
* rank inconsistency / route attractiveness anomaly 기반

---

## 5.3 최종 parent 선택

최종적으로 후보 parent의 cost는:

> **기존 BRPL metric × trust penalty**

형태로 반영

즉 trust가 낮은 노드는
queue/backpressure 측면에서 좋아 보여도 덜 선호되게 함.

이 정도만 초안에는 넣어도 충분합니다.

---

# 6. 실험 시나리오 (핵심)

이건 아주 중요합니다.
논문 전체를 2개 시나리오로 정리합니다.

---

# Scenario 1 — Sinkhole Only

## 목적

**공격자가 패킷을 버리지 않아도 네트워크를 얼마나 장악할 수 있는지** 확인

## 공격 설정

* 공격자: sinkhole behavior만 수행
* packet drop = 0%
* rank lure = ON

## 보고 싶은 것

이 시나리오에서 핵심은 **PDR이 아님**

### 주요 지표

* **Attacker Parent Share**

  * 공격자를 preferred parent로 사용하는 노드 비율
* **Exposure E1**

  * 루트에 도달한 패킷 중 공격자를 경유한 비율
* **Exposure E3**

  * 시간 기준 공격자 선호 parent 점유율
* **Attacker Subtree Size (추정)**
* **Parent churn**
* **PDR (보조지표)**

## 기대 결과

* Baseline BRPL은 공격자 쪽으로 parent가 몰림
* TA-BRPL은 장악도를 줄임

즉 이 시나리오는:

> **“공격자는 이미 네트워크를 먹을 수 있다”**

를 보여주는 단계입니다.

---

# Scenario 2 — Sinkhole + Packet Drop

## 목적

**장악된 sinkhole이 실제로 availability 공격을 시작했을 때의 피해와 방어 효과** 확인

## 공격 설정

* 공격자: sinkhole behavior 유지
* 추가로 selective forwarding / packet drop 수행

## packet drop 강도 (러프 추천)

처음에는 너무 많이 하지 말고 이 정도만:

* **30%**
* **70%**

또는 아주 러프하게 더 줄이면:

* **50% only**

내 추천은 논문 초안/빠른 실험용으로는:

> **50% 하나 먼저 돌리고**,
> 결과 괜찮으면 30/70으로 확장

이게 좋습니다.

## 주요 지표

여기서는 **PDR이 주연**

### 주요 지표

* **PDR**
* **Delay**
* **Exposure E1**
* **Attacker Parent Share**
* **Parent churn**
* **Control overhead**

## 기대 결과

* Baseline BRPL은 sinkhole 장악 이후 drop에 크게 취약
* TA-BRPL은 attacker dependency가 낮아 상대적으로 피해 완화

즉 이 시나리오는:

> **“장악이 실제 피해로 이어질 때, TA-BRPL이 얼마나 덜 망가지게 하는가”**

를 보여주는 단계입니다.

---

# 7. Baseline 구성

이건 논문 설득력에 중요합니다.

너무 많이 벌리지 말고 러프하게 이 정도면 됩니다.

## 비교 대상

### B1. **BRPL (Trust OFF)**

* 기본 baseline
* 논문의 직접 비교 대상

### B2. **TA-BRPL (Trust ON)**

* 제안 기법

### (선택) B3. **RPL (MRHOF/ETX)**

이건 여유 있으면 넣고,
지금은 **없어도 초안은 굴러갑니다.**

---

## 내 추천

지금은 우선 이렇게:

> **BRPL vs TA-BRPL**

2개로 먼저 결과를 뽑고,
논문 다듬을 때 필요하면 RPL baseline 추가.

이게 속도 면에서 가장 좋습니다.

---

# 8. 토폴로지 설계 (러프 버전)

여기서 제일 중요한 건:

> **sinkhole이 실제로 장악하기 쉬운 구조를 하나는 넣어야 한다**

입니다.

---

## 최소 토폴로지 2개 추천

### T1. **Grid / Random-like**

* 일반적이고 baseline 성격
* path diversity 있음
* sinkhole 효과가 상대적으로 약할 수 있음

→ “일반적 환경”

---

### T2. **Bottleneck / Two-cluster**

* 공격자가 중간 관문 근처에 위치
* route capture 효과가 크게 보임

→ “공격이 실제로 잘 먹히는 환경”

---

## 내 추천

처음엔 이 2개만 가세요.

* **T1 = Grid**
* **T2 = Two-cluster bottleneck**

이 둘만으로도 메시지가 충분히 나옵니다.

---

# 9. 노드 수 (러프)

지금은 너무 벌리지 마세요.

## 추천

* **Small: 16**
* **Medium: 36**

처음엔 **36만 먼저** 돌려도 됩니다.

빠르게 보고 싶으면:

> **36 nodes only**

로 시작하세요.

이유는 간단합니다:

* 너무 작으면 의미 약함
* 너무 크면 시간 오래 걸림
* 36은 적당히 “네트워크” 느낌 남

---

# 10. 실험 매트릭스 (아주 러프)

처음엔 이렇게 최소로 시작하면 됩니다.

---

## 최소 실험 세트

### Topology

* Grid
* Bottleneck

### Protocol

* BRPL
* TA-BRPL

### Scenario

* Sinkhole only
* Sinkhole + Drop(50%)

### Seeds

* 5 seeds

---

## 총 실험 수

2 × 2 × 2 × 5 = **40 runs**

이 정도면 **초기 초안용으로 아주 적당**합니다.

---

# 11. 논문에서 보고 싶은 그림들

이건 중요합니다.
결국 논문은 **그림이 메시지를 말해야** 합니다.

---

## Figure 1 — System / Threat Overview

그림 하나로:

* 정상 LLN
* sinkhole route capture
* 이후 packet drop

흐름 보여주기

---

## Figure 2 — Scenario 1 결과

### y축 후보

* attacker parent share
* exposure E1

### x축

* topology / protocol

이 그림으로:

> “PDR이 아니라, 공격자 장악이 실제로 줄었다”

를 보여줍니다.

---

## Figure 3 — Scenario 2 결과

### y축

* PDR

### x축

* topology / protocol

이 그림으로:

> “장악 이후 availability 공격에서도 덜 망가졌다”

를 보여줍니다.

---

## Figure 4 — Trade-off

### y축

* churn or overhead

이 그림으로:

> “대신 이런 비용이 있었다”

를 정리

이게 있어야 리뷰어가 덜 뭐라 합니다.

---

# 12. 논문 결과 해석 방향 (매우 중요)

이거 잘 잡아야 함.

---

## Scenario 1 해석

> Sinkhole-only 공격은 즉각적인 packet dropping이 없더라도,
> 공격자에 대한 parent concentration과 path exposure를 증가시켜
> 네트워크를 공격자 의존 구조로 왜곡시킨다.
> TA-BRPL은 이러한 route capture를 완화함으로써
> 이후 availability 공격에 대한 잠재적 취약성을 줄인다.

---

## Scenario 2 해석

> Sinkhole-induced route capture 상태에서 packet dropping이 시작되면
> baseline BRPL은 공격자 의존으로 인해 PDR 저하가 크게 나타난다.
> 반면 TA-BRPL은 사전에 attacker dependency를 줄였기 때문에
> packet dropping이 실제로 발생하더라도 피해를 완화할 수 있다.

---

## Trade-off 해석

> 다만 trust-aware routing은 더 보수적인 parent selection으로 인해
> 일부 환경에서는 churn 또는 경로 우회 비용을 유발할 수 있다.
> 이는 보안성과 전달성 사이의 trade-off로 해석된다.

이 세 문단만 잘 잡아도 논문 초안 뼈대가 거의 됩니다.

---

# 13. “왜 BRPL이냐?”에 대한 방어 문장 (중요)

이건 리뷰어 방어용입니다.

짧게 가야 합니다.

> We build on BRPL as the routing substrate because sinkhole attacks in LLNs not only distort parent selection but can also concentrate traffic around malicious forwarders.
> A BRPL-based design allows us to study trust-aware mitigation in a routing framework that remains sensitive to congestion and queue dynamics, rather than relying solely on static path preference.

한국어로 하면:

> 본 연구는 sinkhole 공격이 단순히 부모 선택을 왜곡하는 것뿐 아니라, 특정 악성 노드 주변으로 트래픽을 집중시켜 혼잡 및 전달성 저하를 유발할 수 있다는 점을 고려하여 BRPL을 기반 라우팅으로 사용한다.
> 이를 통해 정적 경로 선호만이 아니라 queue/backpressure 특성을 고려하는 환경에서 trust-aware 방어를 평가한다.

즉,
BRPL은 **논문의 “차별화 배경”**으로 쓰고,
주인공은 여전히 **sinkhole 방어**로 둡니다.

---

# 14. 지금 바로 실행 가능한 “첫 번째 논문 초안 구조”

---

## 1. Introduction

* LLN/RPL 계열에서 sinkhole 위협 설명
* 단순 packet drop보다 먼저 route capture가 문제임
* 기존 연구는 주로 delivery/PDR 중심
* 우리는 route capture → drop escalation 구조를 본다
* 기여점 정리

---

## 2. Background

* LLN, RPL/BRPL 간단 설명
* sinkhole / selective forwarding
* trust-aware routing 배경

---

## 3. Threat Model and Proposed Method

* 공격자 모델
* Scenario 1 / 2
* TA-BRPL trust 개요

---

## 4. Experimental Setup

* Contiki-NG / Cooja
* topology
* node count
* seeds
* metrics

---

## 5. Results

### 5.1 Sinkhole-only

* route capture 분석

### 5.2 Sinkhole + Drop

* PDR degradation 분석

### 5.3 Trade-offs

* churn, overhead, delay

---

## 6. Discussion

* route capture 먼저 막는 것의 의미
* PDR만으로 보안을 평가하면 안 되는 이유
* 한계점

---

## 7. Conclusion

* 요약
* 향후 확장

---

# 최종 러프 결론

지금 네 방향은 이렇게 정리하면 됩니다:

> **TA-BRPL은 “패킷 드롭이 시작된 뒤 수습하는 기법”이 아니라,**
> **먼저 sinkhole의 경로 장악 자체를 줄여서**
> **그 이후 availability 공격 피해를 완화하는 기법**이다.

그리고 실험은 아주 러프하게 먼저:

* **Topology**: Grid, Bottleneck
* **Protocol**: BRPL, TA-BRPL
* **Scenario**: Sinkhole only, Sinkhole+Drop(50%)
* **Seeds**: 5

이렇게 시작하면 됩니다.

---

# 15. 진행 로그 (2026-03-27)

`scripts/run_sinkhole_sweep.sh`로 40-run(2 topo x 2 proto x 2 scenario x 5 seeds) 완료.

## 15.1 Baseline (`results/sinkhole_sweep`)

- `GRID / BRPL / SINK_DROP50`: PDR_dur=0.894, att_share=0.090, hit_ratio=0.106, churn=0.1
- `GRID / TABRPL / SINK_DROP50`: PDR_dur=0.768, att_share=0.165, hit_ratio=0.200, churn=2.1
- `BOTTLE / BRPL / SINK_DROP50`: PDR_dur=0.748, att_share=0.188, hit_ratio=0.188, churn=0.4
- `BOTTLE / TABRPL / SINK_DROP50`: PDR_dur=0.738, att_share=0.149, hit_ratio=0.263, churn=2.7

관찰:
- GRID에서는 TA-BRPL이 BRPL 대비 열세(PDR/노출/churn 모두 악화)
- BOTTLE에서는 att_share 일부 개선, 그러나 hit_ratio/churn 악화

## 15.2 단일 전역 파라미터 재검증

- `TA_TRUST_ESCAPE_BETTER_TRUST_MARGIN: 0 -> 80`
  - 결과: baseline과 사실상 동일(지표 변화 없음)

- `TA_TRUST_TAU_JOIN: 520 -> 600` (`results/sinkhole_sweep_tau600`)
  - `GRID / TABRPL / SINK_DROP50`: PDR_dur +0.0016, att_share -0.0005, churn +0.04
  - `BOTTLE / TABRPL / SINK_DROP50`: PDR_dur -0.0049, att_share +0.0109, hit_ratio +0.0125
  - 토폴로지 평균 우위 달성 실패(개선 일관성 부족)

## 15.3 현재 원인 가설

1. Sinkhole-only에서도 공격자 `trust_fwd`가 임계 근처(약 525)로 유지되어, 임계값 기반 배제가 약함.
2. TA-BRPL의 parent switching(churn)이 BRPL 대비 크게 높아, drop 시나리오에서 이득을 상쇄.
3. 일부 케이스에서 att_share는 줄어도 hit_ratio가 증가해 "더 넓은 노드가 한 번씩 공격자 경유"하는 패턴이 남음.

## 15.4 다음 액션

1. `T_ctrl` sinkhole 유인 탐지 신호 강화(고정 저-rank 광고 패널티 추가).
2. trust-triggered escape와 BRPL switch hysteresis 결합으로 churn 억제.
3. 동일 매트릭스(40-run)로 재검증 후, RQ1~RQ4 문장화.
