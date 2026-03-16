

# TA-BRPL 실험 설계 명세서 

**Trust-Aware BRPL in LLN/WSN — Simulation Specification**

안정화 단계 v1.1 · GRID-M 단일 토폴로지

---

# 1. 실험 개요

본 실험은 **Low-Power and Lossy Network (LLN)** 환경에서 발생하는 **복합 라우팅 공격(blackhole + sinkhole)** 에 대해 제안하는 **TA-BRPL (Trust-Aware Backpressure RPL)** 프로토콜의 탐지 및 회복 성능을 검증하기 위한 시뮬레이션 설계이다.

안정화 단계에서는 **GRID 6×6 토폴로지 (총 36 노드)** 를 사용하며, 제안 프로토콜을 다음 세 가지 baseline 프로토콜과 비교한다.

|항목|값|
|---|---|
|실험 목적|TA-BRPL의 공격 탐지 및 회복 성능 검증|
|시뮬레이션 환경|Cooja / Contiki-NG|
|토폴로지|GRID 6×6 (36 nodes)|
|비교 프로토콜|RPL (MRHOF), BRPL, SMTrust|
|공격 유형|3× Blackhole + 1× Sinkhole|
|공격 강도|Blackhole: 100% drop, Sinkhole: forged low rank|
|반복 실행|시나리오당 30회|
|신뢰구간|95%|

---

# 2. 네트워크 환경

## 2.1 네트워크 파라미터

|항목|값|
|---|---|
|필드 크기|200 m × 200 m|
|Root 위치|(100,100)|
|TX range|50 m|
|Interference range|60 m|
|이동성|없음|
|MAC/PHY|IEEE 802.15.4|
|트래픽 패턴|Periodic sensing|
|패킷 전송 방향|Upstream (toward root)|
|패킷 전송 주기|30 s|
|패킷 크기|50 bytes payload|

**수정 포인트**

기존 문서:

> 이웃 오버히어링 가능

→ 실제 Contiki 기본 설정에서는 **100% overhearing 보장되지 않음**

따라서 문서에서는 다음처럼 쓰는 것이 좋습니다.

**수정**

```
Overhearing: probabilistic overhearing based on wireless reception
```

---

## 2.2 RPL / BRPL 파라미터

|항목|값|
|---|---|
|Routing Protocol|RPL / BRPL|
|Objective Function|MRHOF (ETX 기반)|
|DIO Imin|4096 ms|
|DIO Idoublings|8|
|Redundancy constant|10|
|DAO interval|60 s|
|최대 hop 수|약 5–6 hop|

---

# 3. 노드 배치

## 3.1 노드 구성

|구분|수량|
|---|---|
|Root|1|
|정상 sender|31|
|Blackhole 공격자|3|
|Sinkhole 공격자|1|
|**총 노드 수**|**36**|

---

## 3.2 GRID 6×6 배치

격자 간격은 약 **33 m** 로 설정된다.

좌표 집합

```
{0, 33, 67, 100, 133, 167}
```

토폴로지 구조

```
y=167  N01  N02  N03  N04  N05  N06
y=133  N07  N08  A2   A3   N11  N12
y=100  N13  N14  N15  SH   N17  N18
y= 67  N19  A1   ROOT N22  N23  N24
y= 33  N25  N26  N27  N28  N29  N30
y=  0  N31  N32  N33  N34  N35  N36
```

공격자 위치

|공격자|좌표|역할|
|---|---|---|
|A1 (node 2)|(33,67)|1-hop blackhole|
|A2 (node 3)|(67,133)|2-hop blackhole|
|A3 (node 4)|(100,133)|2-hop blackhole|
|SH (node 18)|(100,100)|중앙 sinkhole|

배치 의도

- **A1 / A2 / A3** : Root 방향 포워딩 드롭으로 데이터 평면 훼손

- **SH (node 18)** : 중앙 위치에서 낮은 rank를 광고해 parent 쏠림 유도
    

---

# 4. 공격 모델

|항목|값|
|---|---|
|공격 유형|복합 공격: blackhole + sinkhole|
|공격자 수|4|
|공격 대상|Blackhole은 데이터 패킷, sinkhole은 DIO rank advertisement|
|제어 패킷|Blackhole 노드는 정상 전달, sinkhole은 저랭크 DIO 광고|
|드롭 확률|Blackhole 100%|
|공격 협력|없음|
|공격 시작|350 s|
|공격 종료|시뮬레이션 종료|

blackhole 모델

```
P(drop) = 1.0
for forwarded UDP packets toward root
```

sinkhole 모델

```
Advertised rank = ROOT_RANK + 1
Periodic fake DIO every 15 s after 350 s
```

---

# 5. 시뮬레이션 타임라인

총 시뮬레이션 시간

```
900 seconds
```

|단계|시간|설명|
|---|---|---|
|Warm-up|0–150 s|DODAG 형성|
|정상 운영|150–350 s|baseline 성능 측정|
|공격 시작|350 s|공격 활성화|
|공격 지속|350–650 s|탐지 및 경로 변경|
|안정화|650–900 s|회복 성능 측정|

Recovery Time 정의

```
공격 시작 이후
신뢰 임계값 하락 → parent 변경 → PDR 정상복귀
까지 걸린 시간
```

---

# 6. 신뢰 모델 파라미터

|항목|값|
|---|---|
|초기 trust|0.5|
|trust update interval|150 s|
|TA-BRPL tau_warn / tau_join / tau_black|0.70 / 0.45 / 0.25|
|TA-BRPL blacklist 해제 복구값|0.45|
|TA-BRPL blacklist duration|120 s|
|TA-BRPL release cooldown|120 s|
|TA-BRPL release penalty scale|1.60 → 1.00 (linear decay)|
|TA-BRPL attacker-parent base penalty|1.70|
|TA-BRPL persistence window / step|120 s / +0.25|
|TA-BRPL persistence max penalty|2.60|
|TA-BRPL escape trigger|180 s on attacker-parent + trust < 0.70|
|TA-BRPL escape penalty|3.20 + hysteresis off + DIS/reevaluation|
|TA-BRPL lambda_decrease / lambda_normal|0.50 / 0.70|
|TABRPL trust penalty lambda|0.45|
|TABRPL current-parent penalty scale|0.70|

신뢰 갱신 식

```
trust_new = α × trust_old + (1-α) × observation
```

Parent 제외 조건

```
if trust < 0.25
remove from parent set
```

TA-BRPL 튜닝 메모

- sinkhole+blackhole 복합 공격에서 기본 설정은 trust penalty와 blacklist가 너무 강해 `TABRPL`의 parent churn이 과도하게 증가했다.
- 따라서 현재 기본 실험값은 `tau_join`과 `tau_black`를 낮추고, trust 하락 반응을 완만하게 만들고, 현재 preferred parent에는 penalty를 70%만 적용하도록 조정했다.
- recovery 보정을 위해 blacklist 해제 직후에는 trust를 `0.45`로 복구하되, routing penalty는 즉시 풀지 않고 `120초` 동안 `1.60 → 1.00`으로 단계적으로 완화한다.
- 추가로 attacker parent(`18`, `2`, `3`, `4`)에 대해서는 direct-parent base penalty를 주고, 같은 공격자 parent에 오래 붙을수록 penalty를 누적 증가시키는 persistence-aware penalty를 적용한다.
- attacker parent가 `180초` 이상 유지되고 trust가 `0.70` 미만이면 `escape mode`에 들어가며, 이때는 preferred-parent hysteresis를 끄고 임시 강패널티와 `DIS + DIO reset`으로 alternate parent scan을 유도한다.
- 목적은 공격자를 놓치는 것이 아니라, 경계 상황에서 불필요한 parent switching을 줄이고 route quality와 trust의 균형을 맞추는 것이다.

---

# 7. 혼잡 유도

이 부분은 **굉장히 좋은 설계인데 약간만 수정하면 좋습니다.**

현재:

```
200–300 s 구간
5개 노드 주기 15s
```

여기서 하나 추가해야 합니다.

**Queue size**

Contiki 기본

```
QUEUEBUF_NUM = 8
```

문서에 넣는 것이 좋습니다.

---

혼잡 유도 설계

|항목|값|
|---|---|
|유도 구간|200–300 s|
|방법|특정 노드 주기 단축|
|대상 노드|Root 인접 sender nodes (sinkhole 시나리오에선 주로 17, 22, 27, 28)|
|전송 주기|15 s|
|큐 크기|8 packets|
|혼잡 기준|queue ≥ 70%|

---

# 8. 에너지 모델

|항목|값|
|---|---|
|모델|CC2420|
|전압|3.0 V|
|TX|17.4 mA|
|RX|18.8 mA|
|Idle|0.426 mA|
|Sleep|0.021 mA|

에너지 계산

```
E = V × I × t
```

---

# 9. 성능 지표

|Metric|설명|
|---|---|
|PDR|Packet Delivery Ratio|
|End-to-end delay|생성 → Root 수신|
|Throughput|pkt/s|
|Control overhead|DIO/DAO/DIS|
|Parent changes|parent switch|
|Recovery time|공격 대응 시간|
|Trust convergence|trust 안정화|
|Energy consumption|mJ|

---

# 10. 비교 프로토콜

|Protocol|Congestion aware|Trust|대응|
|---|---|---|---|
|RPL|✗|✗|없음|
|BRPL|✓|✗|없음|
|SMTrust|✗|✓|부분|
|TA-BRPL|✓|✓|완전|

---

# 11. 통계 처리

|항목|값|
|---|---|
|반복 횟수|30|
|난수 seed|1–30|
|신뢰구간|95%|
|통계검정|Wilcoxon rank-sum|
|결과표현|mean ± CI|

---

# 12. 향후 확장 실험

|항목|상태|
|---|---|
|토폴로지 확장|예정|
|노드 규모 확장|예정|
|드롭률 변화|예정|
|On-off 공격|예정|

---
