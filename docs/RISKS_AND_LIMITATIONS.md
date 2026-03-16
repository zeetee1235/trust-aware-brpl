# TA-BRPL 리스크 및 한계

> 구현 리스크, 실험 한계, 논문 작성 시 명시해야 할 사항

---

## 1. 구현 리스크

### R1. Overhearing 불완전성 (높음)

**문제:**
`ta_ip_input_hook()`은 IP 레이어에서 수동 청취(overhearing)로 포워딩 이벤트를 감지한다.
그런데 Contiki-NG의 IP input hook은 **이 노드가 수신한** 패킷에만 호출된다.
라디오 범위 내의 패킷이라도 MAC 레이어에서 필터링되면 IP 레이어에 도달하지 않는다.

**영향:**
- F_ij (관찰된 포워딩 횟수)가 과소 계상 → T_fwd 과소 평가
- 정상 노드도 T_fwd가 낮게 계산될 수 있음 (오탐 위험)
- UDGM 무손실 모델에서는 완화되지만, 실제 환경에서 더 심각

**완화 방법:**
- Bayesian smoothing (α, β) 파라미터가 완충
- UDGM SUCCESS_RATIO_TX/RX = 1.0 가정 → 현재 실험에서는 이 문제 최소화
- 논문 한계 섹션에 명시

**논문 문장:**
> The overhearing-based forwarding observation relies on passive radio monitoring. In the noiseless UDGM model used in our Cooja experiments, this is approximated as reliable, but real-world wireless links may yield incomplete observations, resulting in conservative T_fwd estimates.

---

### R2. T_hon 큐 추정 정확도 (중간)

**문제:**
T_hon은 `Q_adv - Q_est`를 비교하는데, `Q_est`는 로컬 큐 점유율에서 추정한다.
이웃 노드의 실제 큐를 직접 알 수 없으므로 추정이 부정확할 수 있다.

**영향:**
- 혼잡한 정상 노드가 큐 불일치로 T_hon 하락 → 오탐 가능
- T_hon의 실제 기여가 논문에서 약하게 나타날 수 있음

**완화 방법:**
- T_hon 가중치를 낮게 유지 (20%)
- ablation에서 T_hon 제거 시 PDR 변화가 미미하면 솔직하게 인정
- brpl-queue.h의 `p->brpl_queue` 값이 있으면 우선 사용 (현재 구현)

---

### R3. T_ctrl 부분 검증 한계 (중간)

**문제:**
현재 실험에는 `sinkhole_attacker.c`가 추가되어 T_ctrl이 완전히 놀지는 않지만,
제어 평면 이상 검증이 node 18의 단일 sinkhole 패턴에 집중되어 있다.
Version Number Attack, colluding sinkhole, 불규칙 DIO burst 등은 아직 포함되지 않는다.

**영향:**
- T_ctrl이 sinkhole rank spoofing에는 반응할 수 있으나 일반화된 control-plane resilience를 모두 증명하진 못함
- 단일 공격 위치 의존성이 남아 있음

**완화 방법:**
- 현재 문서에는 "blackhole + sinkhole" 복합 실험으로 범위를 명시
- T_ctrl은 sinkhole 탐지 검증까지는 포함, 더 넓은 control-plane 공격은 미래 확장으로 분리
- ablation에서 T_ctrl 제거 시 parent exposure나 churn 변화도 함께 보고

**논문 문장:**
> While T_ctrl is now exercised by a dedicated sinkhole node that forges low DIO rank advertisements, our evaluation still covers only a narrow subset of control-plane attacks. Broader validation against colluding or version-based attacks is left for future work.

---

### R4. math.h pow() 오버헤드 (낮음, Cooja 한정)

**문제:**
`aggregate_trust()`에서 `pow(T_fwd, 0.5) * pow(T_ctrl, 0.3) * pow(T_hon, 0.2)`
를 부동소수점으로 계산한다.

**영향:**
- Cooja(JVM 호스트): 문제없음 (`-lm` 링크로 해결됨)
- 실제 MCU(CC2420 등): FPU 없어 매우 느림, 배터리 소모
- **현재 실험은 Cooja이므로 직접 영향 없음**

**완화 방법:**
- 논문에서 "Cooja simulation 결과, 실제 하드웨어 배포 시 정수 근사 필요" 언급
- 정수 근사 구현 방법: lookup table 또는 고정소수점 sqrt 근사

---

### R5. blacklist 해제 후 재진입 위험 (중간)

**문제:**
blacklist 해제 후 trust는 `tau_join(450)`로 복구되지만,
공격자가 계속 공격 중이면 recovery 관찰 구간에서 다시 trust가 하락할 수 있다.
이 경우 `parent_churn`이 증가할 수 있다.

**현재 정책:** blacklist 해제 직후 부모 후보는 복귀시키되,
추가 routing penalty를 `120초` 동안 `1.60 → 1.00`으로 선형 감쇠시킨다.
또한 현재 preferred parent에는 별도 hysteresis를 유지한다.
또한 2026-03-17 기준 direct attacker parent는 `trust < tau_join`이면 후보 집합에서 직접 제외된다.

**영향:**
- release 이후 재하락(redrop)이나 우회 경로 유지가 남을 수 있음
- 로그 볼륨 증가
- direct attacker exclusion이 공격자 식별 오류를 만났을 때 정상 parent를 과도하게 배제할 위험이 있음

**완화:** `CSV,TRUST_UNBLACKLIST`, `CSV,TRUST_RECOVERY`, `CSV,TRUST_REDROP`
로그로 release 직후 60~120초 구간을 별도 분석한다.

---

## 2. 실험 설계 한계

### L1. 정적 토폴로지

**한계:** GRID 6×6은 고정 배치다. 이동성(mobility)이 없다.
TMMobility (SMTrust) = 1.0으로 고정. TA-BRPL도 이동 감지 없음.

**영향:** 실제 IoT 환경(농장, 물류창고 등)에서 이동 노드가 있으면
신뢰 모델이 링크 변화를 공격으로 오인할 위험이 있음.

**논문 문장:**
> Our evaluation assumes a static deployment. In mobile scenarios, transient link degradation may cause false positive trust decrements. Extending TA-BRPL with mobility-aware trust updates is left for future work.

---

### L2. 공격 범위 제한 (blackhole + sinkhole)

**한계:** 현재 구현은 3개 blackhole + 1개 sinkhole 조합까지만 포함한다.
Sybil, collusion attack, Version Number Attack, congestion-information forgery는 포함되지 않는다.

**영향:**
- T_ctrl의 기본 sinkhole 탐지 기능은 검증되지만, 더 복잡한 제어 평면 공격 일반화는 아직 부족
- 공격자 협력(collusion) 시 신뢰 테이블이 오염될 수 있음

---

### L3. 무손실 라디오 모델 (UDGM)

**한계:** UDGM SUCCESS_RATIO_TX=1.0, SUCCESS_RATIO_RX=1.0.
현실 무선 환경의 패킷 손실, 간섭, 멀티패스 없음.

**영향:**
- PDR이 실제보다 높게 나올 수 있음
- T_fwd 계산이 실제보다 정확함 (overhearing 신뢰도 높음)
- 실제 환경에서는 α, β Bayesian 파라미터 튜닝 필요

---

### L4. 30회 반복 + Wilcoxon 한계

**한계:**
- 30회는 통계적으로 충분하나, trust가 시드에 따라 편차가 큰 경우 불충분할 수 있음
- Wilcoxon rank-sum은 분포 형태를 가정하지 않으나, 표본이 작으면 검정력이 낮음

---

### L5. DIO 확장 (SMTrust TMRT)

**한계:** SMTrust의 TMRT는 DIO 메시지에 커스텀 확장을 삽입하는 방식이다.
이는 표준 RPL DIO 포맷을 벗어나며, 실제 표준 RPL 노드와 호환되지 않는다.

**영향:**
- 순수 SMTrust가 아닌 경우 DIO 확장이 무시됨 → TMRT ≈ 0.5 (초기값)
- 이 한계가 SMTrust 성능에 영향을 줄 수 있음

---

## 3. 논문 Limitations 섹션 초안

```
Our work has the following limitations:

(1) Overhearing reliability: T_fwd estimation relies on passive
overhearing at the IP layer. The UDGM model assumes lossless radio,
which overestimates overhearing coverage. Real deployments with
lossy links may yield incomplete forwarding observations.

(2) Static topology: All experiments use a fixed 6×6 grid. TA-BRPL
has not been evaluated under mobility, which may induce false
positives due to legitimate link variability.

(3) Attack scope: We evaluate a combined blackhole + sinkhole setup.
This exercises both forwarding-plane and a basic rank-manipulation
control-plane attack, but does not cover collusion, Sybil, or version
number attacks.

(4) Simulation fidelity: Cooja with UDGM does not model real-world
wireless channel effects (multipath, interference, duty cycling).
Results represent an idealized network condition.

(5) Floating-point trust computation: The weighted geometric mean
uses double-precision pow(). This is feasible in Cooja (JVM-hosted)
but would require fixed-point approximation on bare-metal MCUs.
```

---

## 4. 미래 확장 방향

| 항목 | 설명 |
|---|---|
| 고급 control-plane 공격 | colluding sinkhole, version attack 검증 |
| 이동성 지원 | 이동 인식 T_ctrl 확장 |
| 다중 공격 결합 | collusion + blackhole |
| 실제 하드웨어 검증 | CC2538/Z1 mote 배포, 정수 근사 |
| 에너지 소비 분석 | trust update 오버헤드 측정 |
| 동적 임계값 | 네트워크 밀도에 따른 tau 자동 조정 |
| BRPL λ/γ 자동 조정 | 링크 품질에 따른 패널티 강도 동적 변경 |
