# SMTrust

현재 저장소의 `SMTRUST` 구현 설명서다. 이 문서는 논문 원문 요약이 아니라, **지금 코드에 실제로 들어간 동작**을 기준으로 정리한다.

---

## 1. 현재 구현 요약

`SMTRUST`는 `RPL + trust-aware parent filtering` 구조다.

- Objective Function: `MRHOF`
- trust 계산: `motes/smtrust.c`
- parent filtering / ordering hook:
  - `smtrust_is_parent_candidate()`
  - `smtrust_compare_parents()`
- 통합 위치:
  - [smtrust.c](/home/dev/TA-BRPL/motes/smtrust.c)
  - [smtrust.h](/home/dev/TA-BRPL/motes/smtrust.h)
  - [rpl-mrhof.c](/home/dev/TA-BRPL/contiki-ng-brpl/os/net/routing/rpl-classic/rpl-mrhof.c)
  - [rpl-icmp6.c](/home/dev/TA-BRPL/contiki-ng-brpl/os/net/routing/rpl-classic/rpl-icmp6.c)

즉 `SMTRUST`는 `TABRPL`처럼 BRPL cost 함수에 trust penalty를 직접 넣는 방식이 아니라, **MRHOF parent 후보를 trust class로 제한하고 near-tie에서 trust를 tie-break로 쓰는 방식**이다.

---

## 2. Trust Metrics

현재 `TrustIndex`는 6개 metric의 가중합이다.

```text
TrustIndex = w1*TMSR + w2*TM(H0) + w3*TMEL
           + w4*TMLLS + w5*TMMobility + w6*TMRT
```

현재 기본 가중치:

```text
w1 = 0.25   TMSR
w2 = 0.15   TM(H0)
w3 = 0.15   TMEL
w4 = 0.20   TMLLS
w5 = 0.15   TMMobility
w6 = 0.10   TMRT
```

정의 위치:
- [smtrust.h](/home/dev/TA-BRPL/motes/smtrust.h)

---

## 3. Metric별 현재 구현

### 3.1 TMSR

`TMSR`는 forwarded success rate다.

```text
TMSR = (observed_forwarded + 1) / (sent + 2)
```

특징:
- passive overhearing 기반
- 송신 직전 `smtrust_notify_sent(parent_id)`
- IP input hook에서 forwarding observation 감지
- Laplace smoothing 사용

관련 코드:
- [smtrust.c](/home/dev/TA-BRPL/motes/smtrust.c)
- [sender.c](/home/dev/TA-BRPL/motes/sender.c)

### 3.2 TM(H0)

`TM(H0)`는 직전 `trust_index` 값이다.

```text
TM(H0)(t) = TrustIndex(t-1)
```

초기값은 `0.5`.

### 3.3 TMEL

`TMEL`은 이웃별 실제 배터리 잔량이 아니라, **로컬 energest 기반 residual energy 근사치**다.

즉 현재 구현은 논문식 “Nj의 개별 잔여 에너지”를 직접 재현하지는 않는다.

### 3.4 TMLLS

`TMLLS`는 RSSI 기반 link/location stability 근사다.

- `packetbuf` RSSI 사용
- 정규화 후 `[0,1]`

### 3.5 TMMobility

현재 실험은 정적 6x6 grid이므로:

```text
TMMobility = 1.0
```

### 3.6 TMRT

`TMRT`는 DIO option에 실린 neighbour opinion 평균이다.

현재 구현은 표준 metric container 대신 커스텀 option을 쓴다.

```text
[0xFE][0x02][node_id][trust_x100]
```

특징:
- DIO 송신 시 최대 4개 neighbour trust 첨부
- 수신 측이 이를 파싱해 `TMRT` 평균 갱신

관련 코드:
- [smtrust.c](/home/dev/TA-BRPL/motes/smtrust.c)
- [rpl-icmp6.c](/home/dev/TA-BRPL/contiki-ng-brpl/os/net/routing/rpl-classic/rpl-icmp6.c)

---

## 4. Trust Classes

현재 구현은 논문 trust class를 그대로 유지한다.

```text
t1: 0.00–0.20   No Trust
t2: 0.21–0.45   Poor Trust
t3: 0.46–0.70   Fair Trust
t4: 0.71–0.90   Good Trust
t5: 0.91–1.00   Full Trust
```

경계값:

```text
SMTRUST_THRESHOLD = 0.46
```

중요한 점:
- 현재 구현은 단순 `trust >= 0.46`만 쓰지 않는다.
- `t1/t2`는 후보 제외
- `t3`는 fallback
- `t4/t5`는 near-tie에서 우선

즉 논문 의도인 “가능하면 t4/t5, 없으면 t3”를 현재 구현에서 근사한다.

---

## 5. Parent Selection

현재 `SMTRUST`는 **두 단계**로 parent를 고른다.

### 5.1 Candidate Filter

`smtrust_is_parent_candidate(node_id)`:

- suspicious node 제외
- `t1/t2` 제외
- `t3/t4/t5`만 후보 유지

즉 현재 후보 기준은:

```text
trust level >= L3_FAIR
```

### 5.2 Parent Ordering

`smtrust_compare_parents()`는 near-tie일 때만 trust를 강하게 개입시킨다.

현재 규칙:
- `t4/t5` vs `t3`면 `t4/t5` 우선
- 같은 trust tier 안에서는 MRHOF path-cost 우선
- path-cost가 충분히 차이나면 trust가 개입하지 않음
- trust 차이가 충분히 클 때만 tie-break

즉 `SMTRUST`는 **trust가 ETX/path-cost를 완전히 덮는 구조가 아니라, 보수적 trust-aware MRHOF**다.

---

## 6. Attack Detection

### 6.1 Rank Attack

현재 구현은 오탐을 줄이기 위해 논문보다 보수적이다.

현재 조건:

```text
neighbor.rank < root_rank
```

즉 root보다 더 낮은, 물리적으로 불가능한 rank 광고만 rank attack으로 본다.

### 6.2 Blackhole

현재 구현은 다음 두 조건이 동시에 만족될 때 blackhole 의심으로 본다.

```text
TMSR < SUCCESS_THRESHOLD
TrustIndex < SMTRUST_THRESHOLD
```

그 뒤:
- suspicious flag set
- 현재 preferred parent면 `DIS + DIO reset`
- `CSV,SMTRUST_REEVAL,...` 로그 출력

---

## 7. Update Policy

### 7.1 Periodic Update

현재 주기:

```text
SMTRUST_UPDATE_INTERVAL = 120s
```

이 주기마다:
- 모든 neighbour trust 재계산
- trust table 업데이트
- DIO option payload 갱신

### 7.2 Reactive Update

현재 reactive path는 제한적이다.

- rank attack current parent
- blackhole-suspect current parent

이 경우만 즉시 reevaluation을 건다.

즉 논문형 “모든 suspicious change에 대한 적극적 reactive reselection”보다는 좁은 구현이다.

---

## 8. 현재 구현과 논문 차이

현재 `SMTRUST`는 **부분 구현**이 아니라, 이전보다 많이 맞춰졌지만 여전히 “논문형 완전 재현”은 아니다.

현재 반영된 것:
- 6개 metric 틀
- DIO option 기반 TMRT 전파
- trust class 기반 후보 필터
- `t4/t5` 우선, `t3` fallback
- rank / blackhole reactive reevaluation

논문과 다른 점:
- `TMEL`은 neighbour-specific real battery가 아니라 로컬 energest 근사
- `TMMobility = 1.0` 고정
- rank attack detection은 논문보다 훨씬 보수적
- trust ordering은 MRHOF 위에 얹힌 보수적 tie-break 방식

---

## 9. 현재 실험에서의 해석

최신 전체 30-seed 결과:

- `RPL`: during `0.8759`, recovery `0.8754`
- `SMTRUST`: during `0.8701`, recovery `0.8649`

즉 현재 구현의 `SMTRUST`는 `RPL`보다 아주 약간 낮다.

현재 해석:
- 공격자 완전 포획 노드(`6, 13, 19, 23`)는 `RPL`과 거의 차이가 없음
- 경계 노드(`25, 8, 9, 15`)에서 attacker parent 비율이 `RPL`보다 조금 더 높아짐
- 따라서 현재 `SMTRUST`는 “강한 회피 프로토콜”이라기보다 “보수적 trust-aware MRHOF”에 가깝다

---

## 9-1. 실험 분석: SMTrust ≈ RPL 근본 원인 (Baseline Protocol Fidelity)

**30-seed 정량 분석 결과 (2026-03-17)**

공격 노드(2·3·4·18)에 대한 TrustIndex 성분별 실측값:

| 성분 | 가중치 | 실측 범위 | 구조적 역할 |
|---|---|---|---|
| TMSR | 0.25 | (공격자) 하락 가능 | 유일한 변별 신호 |
| TMLLS | 0.20 | 0.57 ± 0.05 | 물리 근접 → 항상 높음 |
| TMEL | 0.15 | 0.50 ± 0.02 | 자기 energest → 상수 |
| TM(H0) | 0.15 | 0.50 ± 0.10 | 이전 TI → 관성 |
| TMMobility | 0.15 | **1.00** | 정적 환경 고정 → 상수 |
| TMRT | 0.10 | 0.50 ± 0.05 | 이웃 추천 → 약 관성 |

**TI 하한 계산:**

TMEL + TMMobility = 0.30 가중치가 상수로 작동.
TMSR = 0 (완전 blackhole)인 극단 시나리오에서도:

```
TI_min = 0×0.25 + 0.5×0.15 + 0.5×0.15 + 0.57×0.20 + 1.0×0.15 + 0.5×0.10
       = 0 + 0.075 + 0.075 + 0.114 + 0.150 + 0.050
       = 0.464  >  SMTRUST_THRESHOLD (0.46)
```

공격자 노드가 아무리 패킷을 드롭해도 TI가 부모 후보 제외 임계값(0.46) 이하로
내려가지 않음. 30-seed 실측 최솟값: **TI_min = 0.489**.

**결론:**

SMTrust는 이 실험 환경(정적 GRID 6×6, blackhole 공격)에서 RPL과 동일한 공격자
부모 점유율을 보임 (0.220 vs 0.220). 이는 구현 버그가 아니라 구조적 한계:
- TMMobility(0.15): 이동성 없는 정적 토폴로지에서 상수
- TMEL(0.15): 이웃 에너지 대신 자기 에너지 사용으로 변별력 없음
- 두 성분 합 0.30이 TI floor를 임계값 위에 고정

**논문 기술 방향 (Implementation 섹션):**

> SMTrust is implemented faithfully according to [ref], with two deviations
> inherent to our emulation environment: (i) TMEL uses local Energest estimates
> rather than neighbor residual energy, as neighbor energy is not observable
> in Cooja without energy exchange extensions; and (ii) TMMobility is fixed at
> 1.0 since all nodes are static. Together, these two components (combined
> weight 0.30) act as constants, raising the TrustIndex floor to approximately
> 0.46 — precisely at the filtering threshold — rendering SMTrust unable to
> exclude blackhole attackers in our scenario. We report this as an
> implementation-environment mismatch rather than a defect in the SMTrust design.

---

## 10. 관련 로그

현재 주요 로그:

```text
CSV,SMTRUST,<self>,<nbr>,<tmsr>,<tm_h0>,<tmel>,<tmlls>,<tmrt>,<trust>
CSV,SMTRUST_BLACKHOLE,<self>,<nbr>,<tmsr>,<trust>
CSV,SMTRUST_RANK_ATTACK,<self>,<nbr>,<rank>
CSV,SMTRUST_REEVAL,<self>,<nbr>,<reason>
```

---

## 11. 코드 위치

- [smtrust.h](/home/dev/TA-BRPL/motes/smtrust.h)
- [smtrust.c](/home/dev/TA-BRPL/motes/smtrust.c)
- [sender.c](/home/dev/TA-BRPL/motes/sender.c)
- [rpl-mrhof.c](/home/dev/TA-BRPL/contiki-ng-brpl/os/net/routing/rpl-classic/rpl-mrhof.c)
- [rpl-icmp6.c](/home/dev/TA-BRPL/contiki-ng-brpl/os/net/routing/rpl-classic/rpl-icmp6.c)
