
---

## 1. 전체 구조 개요

SMTrust는 크게 두 단계로 구성된다.

1. **Trust Formation** — 이웃 노드의 TrustIndex를 계산하고 trust table을 유지
2. **Attack Detection** — 선택된 preferred parent가 Rank/Blackhole 공격자인지 추가 검증

실행 흐름은 다음 순서다.

```
RPL 초기화 → 토폴로지 생성 → 공격자 노드 배치
→ 이웃 trust 계산 → TrustIndex 계산 → trust table 저장
→ trustworthy parent 후보 필터링 (threshold)
→ preferred parent 선택 (Algorithm 1)
→ Rank/Blackhole attack detection
→ 공격자면 suspicious list 추가 후 재선택
→ 정상이면 라우팅에 사용
→ 주기적/반응적 trust update (trickle timer)
```

---

## 2. Trust Metrics 계산 명세

TrustIndex는 6개 metric의 가중합이다.

```
TrustIndex(Ni, Nj) = w1·TMSR + w2·TM(H0) + w3·TMEL + w4·TMLLS + w5·TMMobility + w6·TMRT

조건: w1 + w2 + w3 + w4 + w5 + w6 = 1
범위: TrustIndex ∈ [0.0, 1.0]
```

논문이 가중치 값을 명시하지 않기 때문에 일반적으로 쓰이는 초기값은 아래와 같다. 실험적으로 조정 가능하다.

```
w1 = 0.25  (TMSR, success rate — 가장 중요)
w2 = 0.15  (TM(H0), historical)
w3 = 0.15  (TMEL, energy)
w4 = 0.20  (TMLLS, link/location stability)
w5 = 0.15  (TMMobility, mobility)
w6 = 0.10  (TMRT, recommended trust)
```

논문 원칙: "current/direct trust values are given more weightage than historical observations" → w1 > w2.

---

### 2-1. TMSR (Success Rate)

```
TMSR(Ni, Nj) = packets_forwarded(Nj) / packets_received(Nj)

- packets_received: Ni가 Nj에게 전달 요청한 (또는 Nj가 수신한) 패킷 수
- packets_forwarded: Nj가 실제로 다음 홉으로 전달한 패킷 수
- overhearing 기반으로 측정 (ContikiRPL 방식)
- 범위: [0.0, 1.0]
- 초기값: 1.0 (모든 노드 신뢰 가정)
```

구현 포인트: Contiki-NG에서 `uip-ds6-nbr`나 패킷 콜백 훅을 사용해 카운터를 유지해야 한다.

---

### 2-2. TM(H0) (Historical Observation)

```
TM(H0)(t) = TrustIndex(t-1)

- 이전 계산 주기의 TrustIndex 값을 그대로 사용
- 초기값: 0.5 (중립 신뢰)
- trust table에 저장된 이전 값을 읽어오면 된다
```

---

### 2-3. TMEL (Energy Level)

```
TMEL(Nj) = current_energy(Nj) / initial_energy(Nj)

- Contiki-NG에서는 energest 모듈 사용
- 범위: [0.0, 1.0]
- 배터리 잔량 비율로 정규화
```

Contiki 구현 예시:

```c
energest_flush();
uint64_t cpu = energest_type_time(ENERGEST_TYPE_CPU);
uint64_t lpm = energest_type_time(ENERGEST_TYPE_LPM);
uint64_t tx  = energest_type_time(ENERGEST_TYPE_TRANSMIT);
uint64_t rx  = energest_type_time(ENERGEST_TYPE_LISTEN);
// 전체 활동 시간 기반으로 소비 에너지 추정 후 정규화
```

---

### 2-4. TMLLS (Location and Link Stability)

```
TMLLS(Nj) = f(RSSI(Nj))

RSSI 기반 정규화:
TMLLS = (RSSI_measured - RSSI_min) / (RSSI_max - RSSI_min)

일반적 파라미터:
- RSSI_min = -100 dBm
- RSSI_max = -40 dBm

클리핑:
if TMLLS < 0: TMLLS = 0
if TMLLS > 1: TMLLS = 1
```

Contiki에서는 `packetbuf_attr(PACKETBUF_ATTR_RSSI)` 또는 `radio_value_t`로 RSSI를 읽을 수 있다.

이동성까지 반영하려면 RSSI의 변동성(분산)도 계산에 포함할 수 있다.

```
TMLLS = α · RSSI_normalized + (1-α) · (1 - RSSI_variance_normalized)
```

---

### 2-5. TMMobility (Mobility)

```
TMMobility(Nj) = 1 - (distance_moved / max_expected_distance)

distance_moved = |current_position - previous_position|

- 위치는 RSSI 기반 추정 또는 GPS 좌표 사용
- Cooja 시뮬레이션에서는 BonnMotion 좌표 직접 접근 가능
- max_expected_distance: 시뮬레이션 영역 대각선 길이 등으로 정규화
- 범위: [0.0, 1.0]
- 많이 움직인 노드일수록 낮은 값 → parent로 불안정
```

Cooja 환경에서는 노드 위치를 주기적으로 기록하고 이전 위치와의 유클리드 거리를 계산하면 된다.

---

### 2-6. TMRT (Recommended Trust)

```
TMRT(Ni, Nj) = (1/|neighbors(Ni)|) · Σ TrustIndex(Nk, Nj)
               for all Nk ∈ neighbors(Ni), Nk ≠ Ni, Nk ≠ Nj

- 1-hop 이웃들이 Nj에 대해 갖고 있는 trust 값의 평균
- DIO 메시지의 DAG metric container에 trust 값을 실어 전파
- 초기값: 0.5
```

현재 구현은 DAG metric container를 직접 바꾸지 않고, DIO option 영역에
커스텀 SMTrust option `[0xFE][len=2][node_id][trust_x100]` 를 최대 4개까지 붙여 전파한다.
수신 측은 이 옵션들을 파싱해 `TMRT` 평균값을 갱신한다.

---

## 3. Trust Rating (Fuzzy Trust Level)

```
TrustIndex 범위    등급    사용 여부
─────────────────────────────────────
0.00 – 0.20       t1: No Trust        라우팅 불가
0.21 – 0.45       t2: Poor Trust      라우팅 불가
0.46 – 0.70       t3: Fair Trust      t4/t5 없을 때만 사용
0.71 – 0.90       t4: Good Trust      신뢰 가능
0.91 – 1.00       t5: Full Trust      신뢰 가능

TRUST_THRESHOLD = 0.46
```

현재 구현은 다음 규칙으로 근사한다.

- `t1`, `t2` 및 suspicious node는 후보에서 즉시 제외
- rank 조건을 만족하지 않는 후보는 우선 탈락
- MRHOF path-cost 차이가 충분히 크면 trust는 개입하지 않음
- path-cost가 거의 비슷한 near-tie 상황에서만 trust가 ordering에 개입
- 그 near-tie 안에서 `t4/t5` 후보가 `t3` 후보보다 우선
- trust 차이가 충분히 클 때만 trust로 tie-break, 아니면 MRHOF ETX/path-cost 유지

---

## 4. Algorithm 1: Trustworthy Parent Selection

논문의 알고리즘을 Contiki-NG/MRHOF에 맞게, trust가 ETX/path-cost를
완전히 덮지 않도록 보수적으로 근사하면 다음과 같다.

```
INPUT:  potential_parents[p1, p2, ..., pn] in NeighborList of Ni
OUTPUT: preferredParent

/* Phase 1: trust 계산 */
FOR all Nj in NeighborList:
    TrustIndex(Ni, Nj) = compute_trust(Ni, Nj)   // 식 (1) 적용
    TrustTable(Ni).update(Nj, TrustIndex)

/* Phase 2: parent 선택 */
FOR all (p1, p2) in potential_parents:

    IF p1.metric ≤ MAX_LINK_METRIC AND p2.metric ≤ MAX_LINK_METRIC:

        IF p1.TrustIndex ≥ TRUST_THRESHOLD AND p2.TrustIndex ≥ TRUST_THRESHOLD:

            IF p1.Rank ≤ Ni.Rank AND p2.Rank ≤ Ni.Rank:
                /* 둘 다 조건 만족 */
                IF abs(p1.path_cost - p2.path_cost) > NEAR_TIE:
                    preferredParent = lower_path_cost_parent
                ELSE IF p1.TrustIndex > p2.TrustIndex + DELTA:
                    preferredParent = p1
                ELSE IF p2.TrustIndex > p1.TrustIndex + DELTA:
                    preferredParent = p2
                ELSE:
                    preferredParent = lower_path_cost_parent

            ELSE IF p1.Rank ≤ Ni.Rank OR p2.Rank ≤ Ni.Rank:
                /* 하나만 rank 조건 만족 → 더 낮은 rank 선택 */
                IF p1.Rank < p2.Rank:
                    preferredParent = p1
                ELSE:
                    preferredParent = p2

            ELSE:
                preferredParent = NULL

    ELSE IF p1.metric ≤ MAX_LINK_METRIC OR p2.metric ≤ MAX_LINK_METRIC:
        /* link metric만 만족 → 더 나은 metric 선택 */
        IF p1.metric ≤ p2.metric:
            preferredParent = p1
        ELSE:
            preferredParent = p2

    ELSE:
        preferredParent = NULL

RETURN preferredParent
```

핵심 우선순위 정리:

```
1순위: link metric 조건 통과
2순위: trust threshold / suspicious 필터
3순위: rank 조건 통과 (loop-free 보장)
4순위: MRHOF path-cost가 near-tie인지 확인
5순위: near-tie일 때만 trust level(t4/t5 > t3) 및 trust 값 비교
6순위: 그 외에는 MRHOF ETX/path-cost
```

---

## 5. Attack Detection 명세

### 5-1. Rank Attack Detection

```
TRIGGER: DIO 메시지 수신 시

현재 구현은 오탐을 줄이기 위해 더 보수적으로 동작한다.

IF neighbor.rank < ROOT_RANK:   // 물리적으로 불가능한 광고
    → suspicious DIO → Rank Attack 판정
    → suspicious_list 추가
    → 현재 preferred parent이면 즉시 재평가
```

`RANK_THRESHOLD`는 실험적으로 결정하는 값이다. 논문은 명시하지 않지만 일반적으로 `DEFAULT_RANK_INCREMENT`의 2배 정도로 설정한다.

---

### 5-2. Blackhole Attack Detection

```
TRIGGER: preferred parent 선택 후 패킷 전달 모니터링

overhearing으로 parent가 패킷을 drop하는지 관찰:

IF preferred_parent.TMSR < SUCCESS_THRESHOLD:         // 성공률 낮음
    AND preferred_parent.TrustIndex < TRUST_THRESHOLD: // trust도 낮음
        → Blackhole Attack 판정
→ attacker를 suspicious_list에 추가
→ 현재 preferred parent이면 `DIS + DIO reset`으로 즉시 재평가
```

`SUCCESS_THRESHOLD`는 논문 명시 없음. 실험적으로 0.5 ~ 0.7 범위에서 설정한다.

---

## 6. Trust Update 명세

### 6-1. Periodic Update (주기적)

```
periodic timer 이벤트 발생 시:
→ NeighborList 전체 재순회
→ 각 이웃에 대해 TrustIndex 재계산
→ TrustTable 업데이트
→ 이후 outgoing DIO에 trust option을 부착해 전파

현재 주기: `SMTRUST_UPDATE_INTERVAL = 120s`
```

### 6-2. Reactive Update (반응적)

```
현재 구현의 reactive path는 다음 두 경우다.

- current preferred parent가 rank attack으로 의심됨
- current preferred parent가 blackhole로 의심됨

이 경우:
→ suspicious_list 추가
→ `CSV,SMTRUST_REEVAL,...` 로그 출력
→ `DIS + DIO reset`으로 parent selection 재실행 유도
```

---

## 7. Trust Propagation (DIO 확장)

현재 구현은 DIO option 영역에 아래 형식의 커스텀 option을 반복 부착한다.

```
[0xFE][0x02][node_id][trust_x100]
```

- `node_id`: 해당 trust가 가리키는 neighbour
- `trust_x100`: TrustIndex × 100
- 노드당 최대 4개 option 전송

---

## 8. Trust Table 자료구조

각 노드는 다음 trust table을 메모리에 유지한다.

```c
typedef struct {
    uip_ipaddr_t  node_id;
    float         trust_index;      // 현재 TrustIndex
    float         tmsr;             // success rate
    float         tmel;             // energy level
    float         tmlls;            // link/location stability
    float         tm_mobility;      // mobility
    float         tmrt;             // recommended trust
    float         tm_h0;            // 이전 TrustIndex (historical)
    uint32_t      pkts_received;    // TMSR 계산용 카운터
    uint32_t      pkts_forwarded;   // TMSR 계산용 카운터
    float         prev_x, prev_y;   // TMMobility용 이전 위치
    uint8_t       dio_seq;          // Rank attack 탐지용
    uint16_t      prev_rank;        // Rank attack 탐지용
    uint8_t       is_suspicious;    // 공격자 플래그
} smtrust_entry_t;

#define MAX_TRUST_TABLE_SIZE 20     // 노드 수에 맞게 조정
smtrust_entry_t trust_table[MAX_TRUST_TABLE_SIZE];
```

---

## 9. 구현 순서 권고

Contiki-NG/Cooja 기준으로 구현 순서를 추천하면 다음과 같다.

**1단계**: trust table 자료구조 정의 및 초기화 루틴 작성

**2단계**: TMSR 카운터 구현 (패킷 송수신 콜백)

**3단계**: TMEL, TMLLS(RSSI), TMMobility 계산 함수 작성

**4단계**: TMRT를 위한 DIO 확장 (trust 값 교환)

**5단계**: TrustIndex 가중합 계산 함수 구현

**6단계**: Algorithm 1에 가까운 parent ordering 구현, `rpl-mrhof.c`에 hook으로 통합

**7단계**: Rank attack detection 추가 (현재는 physically-impossible rank만 탐지)

**8단계**: Blackhole attack detection 추가 (TMSR 모니터링 루틴)

**9단계**: trickle timer 기반 periodic update 연결

**10단계**: Cooja 시뮬레이션 셋업 (30 노드, 3 공격자, BonnMotion mobility)

---

## 10. 핵심 파라미터 요약

```
TRUST_THRESHOLD         = 0.46
SUCCESS_THRESHOLD       = 0.5 ~ 0.7  (실험적 결정)
RANK_THRESHOLD          = 2 × DEFAULT_RANK_INCREMENT  (실험적)
MAX_LINK_METRIC         = 기존 MRHOF의 MAX_LINK_METRIC 값 사용
trust_level ranges      = [0.0–0.20, 0.21–0.45, 0.46–0.70, 0.71–0.90, 0.91–1.00]
initial TrustIndex      = 0.5
initial TMSR            = 1.0
update mechanism        = periodic 120s + suspicious current parent에 대한 reactive reevaluation
```

---
