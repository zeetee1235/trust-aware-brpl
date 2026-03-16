# TA-BRPL 아키텍처 문서

> Trust-Aware Backpressure RPL — Contiki-NG / Cooja 연구 플랫폼

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [프로토콜 변형 (4종)](#3-프로토콜-변형-4종)
4. [모트 펌웨어](#4-모트-펌웨어)
5. [신뢰 모델](#5-신뢰-모델)
6. [설정 시스템](#6-설정-시스템)
7. [시뮬레이션 토폴로지](#7-시뮬레이션-토폴로지)
8. [실험 프레임워크](#8-실험-프레임워크)
9. [CSV 로그 포맷](#9-csv-로그-포맷)
10. [빌드 시스템](#10-빌드-시스템)
11. [데이터 흐름](#11-데이터-흐름)

---

## 1. 프로젝트 개요

TA-BRPL은 IoT LLN(Low-power Lossy Network)에서 **복합 라우팅 공격(blackhole + sinkhole)** 에 대한 라우팅 복원력을 평가하는 연구 시뮬레이션 플랫폼이다.

### 핵심 아이디어

기존 BRPL(Backpressure RPL)의 혼잡 인식 메트릭에 **온노드 행동 신뢰(Behavioral Trust)** 를 결합하여 신뢰도가 낮은 포워더를 부모 선택에서 배제한다.

### 비교 대상 (4개 프로토콜)

| 프로토콜 | 라우팅 | 신뢰 모델 | 특징 |
|---|---|---|---|
| **RPL** | MRHOF + ETX | 없음 | 순수 RPL 기준선 |
| **BRPL** | rpl_brpl OF | 없음 | 혼잡 인식 부모 선택 |
| **SMTrust** | MRHOF + ETX | 6-성분 가중합 | 사회적 메트릭 신뢰 |
| **TA-BRPL** | rpl_brpl OF | 3-성분 기하평균 | 신뢰 인식 백프레셔 RPL |

### 실험 조건 요약

- 시뮬레이터: Cooja (Contiki-NG, JVM 호스트)
- 토폴로지: GRID 6×6 (36 노드)
- 공격: 3개 blackhole + 1개 sinkhole, 350s 이후 시작
- 시뮬레이션 시간: 900s
- 반복 횟수: 30회 / 95% CI / Wilcoxon rank-sum

---

## 2. 디렉토리 구조

```
TA-BRPL/
├── motes/                      # 모트 펌웨어 소스 (Contiki-NG C)
│   ├── sender.c                # UDP 센서 송신기 (RPL/BRPL/TA-BRPL/SMTrust)
│   ├── receiver_root.c         # RPL 루트 + UDP 수신 로거
│   ├── attacker.c              # blackhole 공격자
│   ├── sinkhole_attacker.c     # sinkhole 공격자
│   ├── ta-brpl-trust.h/c       # TA-BRPL 온노드 신뢰 모델
│   ├── smtrust.h/c             # SMTrust 사회적 메트릭 신뢰 모델
│   ├── Makefile.rpl            # RPL 기준선 빌드
│   ├── Makefile.brpl           # BRPL 빌드
│   ├── Makefile.tabrpl         # TA-BRPL 빌드
│   ├── Makefile.smtrust        # SMTrust 빌드
│   ├── Makefile.receiver       # 루트 노드 빌드 (공유)
│   ├── Makefile.attacker       # blackhole 공격자 빌드
│   ├── Makefile.sinkhole_rpl   # sinkhole 빌드 (RPL/SMTrust)
│   └── Makefile.sinkhole_brpl  # sinkhole 빌드 (BRPL/TA-BRPL)
│
├── contiki-ng-brpl/            # git 서브모듈 (커스텀 BRPL OF 포함)
│   └── os/net/routing/
│       └── rpl-classic/
│           ├── rpl-brpl.c      # BRPL Objective Function (rpl_brpl)
│           └── brpl-queue.h    # BRPL 큐 상태 API
│
├── configs/
│   └── scenarios/              # Cooja 시뮬레이션 시나리오 (.csc)
│       ├── GRID6x6_RPL.csc
│       ├── GRID6x6_BRPL.csc
│       ├── GRID6x6_TABRPL.csc
│       └── GRID6x6_SMTRUST.csc
│
├── scripts/
│   ├── run_sweep.sh            # 헤드리스 스윕 실행기 (4프로토콜 × 30시드)
│   ├── analyze_results.R       # R 통계 분석
│   ├── plot_sweep_figures.R    # R 시각화
│   ├── plot_pdr_sweep_figures.R
│   ├── attach_pdr.py           # PDR 계산 후처리
│   └── cooja_script.js         # Cooja ScriptRunner 헬퍼
│
├── tools/
│   ├── parse_results.py        # CSV 로그 파서
│   ├── analyze_cooja_crash.py  # 크래시 분석
│   ├── compare_scenarios.py    # 시나리오 비교
│   └── summary.R               # 요약 통계
│
├── agent/                      # 설계 명세 문서
│   ├── model.md                # TA-BRPL 신뢰 모델 수식 명세
│   ├── experiment.md           # 실험 설계 명세 v1.1
│   └── SMTrust.md              # SMTrust 구현 명세
│
├── docs/                       # 문서 / 논문
│   ├── ARCHITECTURE.md         # 본 문서
│   ├── paper/                  # LaTeX 논문 초안
│   └── report/                 # LaTeX 보고서
│
├── figures/                    # 생성된 그림
├── project-conf.h              # 전역 컴파일 타임 설정
├── flake.nix / shell.nix       # Nix 개발 환경
└── env.sh / setup.sh           # 환경 설정 스크립트
```

---

## 3. 프로토콜 변형 (4종)

### 3.1 컴파일 타임 플래그

모든 프로토콜 변형은 동일한 `sender.c` 소스를 공유하고 컴파일 플래그로 분기한다.

```
RPL_BASELINE_MODE=1   → 순수 RPL (MRHOF + ETX)
BRPL_MODE=1           → BRPL Objective Function 활성화
TABRPL_MODE=1         → BRPL + TA-BRPL 신뢰 모델
SMTRUST_MODE=1        → RPL + SMTrust 신뢰 필터링
```

### 3.2 프로토콜별 특성

#### RPL (기준선)
- Objective Function: MRHOF (Minimum Rank with Hysteresis)
- 메트릭: ETX (Expected Transmission Count)
- 부모 선택: 최소 랭크 기반
- 신뢰 없음 → 공격 감지 불가

#### BRPL
- Objective Function: `rpl_brpl` (커스텀 OF, 서브모듈 내)
- 메트릭: 큐 점유율 기반 백프레셔 비용
- `brpl_trust_get()` 약 심볼(weak symbol) → 기본값 1000(최대 신뢰) 반환
- 혼잡 회피는 되나 공격 감지 불가

#### SMTrust
- Objective Function: MRHOF (순수 RPL)
- 신뢰: 6-성분 가중합 TrustIndex ∈ [0, 1]
- 부모 선택: Phase 1(신뢰 필터링) → Phase 2(랭크 기반)
- `brpl_trust_get()` 오버라이드 → 1000 반환 (BRPL OC 미사용)

#### TA-BRPL
- Objective Function: `rpl_brpl`
- 신뢰: 3-성분 가중 기하평균 → `brpl_trust_get()` 오버라이드
- BRPL 비용 함수에 신뢰 패널티 직접 통합
- 신뢰 낮은 노드 → 라우팅 비용 증가 → 자연스러운 경로 우회
- 현재 기본 튜닝: `tau_warn=700`, `tau_join=450`, `tau_black=250`,
  `BRPL_CONF_TRUST_LAMBDA_PENALTY=450`, `BRPL_CONF_CURRENT_PARENT_PENALTY_SCALE=700`
- recovery 튜닝: blacklist 해제 직후 trust는 `tau_join`으로 복귀하고,
  추가 penalty는 `120초` 동안 `1.60 → 1.00`으로 선형 감쇠
- persistence 튜닝: attacker parent(`18`, `2`, `3`, `4`)에는 기본 penalty를 주고,
  같은 attacker parent 지속 시간이 길수록 penalty를 단계적으로 증가
- escape mode: attacker parent 고착이 `180초`를 넘고 trust가 `tau_warn` 미만이면
  preferred-parent hysteresis를 끄고 `DIS + DIO reset`으로 재평가를 유도
- 목적: sinkhole 회피 효과는 유지하되, 과도한 parent churn을 줄이는 것

---

## 4. 모트 펌웨어

### 4.1 sender.c — UDP 센서 송신기

**역할:** 모든 일반 센서 노드(id=5~36)에서 실행. 프로토콜 변형별로 동작이 다름.

**상태 머신 (이벤트 기반):**
```
시작
 ├─ trust_init() (TABRPL/SMTRUST)
 ├─ DIS 브로드캐스트
 └─ 루프:
     ├─ [trust_timer] → trust_update_all() + trust_log_all()
     ├─ [routing_timer] → DODAG 참여 확인, 미참여시 DIS 재전송
     ├─ [dis_timer] → DODAG 미참여시 DIS keep-alive
     └─ [tx_timer] → 30s마다 UDP 패킷 전송
```

**핵심 타이머:**
| 타이머 | 간격 | 조건 |
|---|---|---|
| `tx_timer` | 30s | 항상 |
| `trust_timer` | 150s (TA-BRPL) / 120s (SMTrust) | 해당 모드만 |
| `routing_timer` | 2s poll | DODAG 미참여시 |
| `dis_timer` | 30s | DODAG 미참여시 |

**CSV 출력:**
```
CSV,PROTOCOL,<id>,TABRPL|SMTRUST|BRPL|RPL
CSV,LLADDR,<id>,<hex>
CSV,TX,<id>,<seq>,<t0>,<joined>
CSV,RTT,<seq>,<t0>,<t_ack>,<rtt_ticks>,<len>
CSV,PARENT,<id>,<ip|none>
CSV,ROUTING,<id>,<joined>,<parent_ip>,<rank>
CSV,TRUST,...   (TABRPL/SMTrust 모드)
```

---

### 4.2 receiver_root.c — RPL 루트 노드

**역할:** id=1, DODAG 루트, UDP 수신 및 에코 응답.

**초기화 시퀀스:**
```
1. aaaa::1 주소 설정
2. aaaa::/64 프리픽스 등록
3. NETSTACK_ROUTING.root_start()
4. UDP 포트 8765 등록
```

**RTT 측정 메커니즘:**
- 수신 패킷에서 `seq=N t0=T` 파싱
- 동일 내용을 에코 응답 → 송신기에서 RTT 계산

**CSV 출력:**
```
CSV,RX,node=1,<src_ip>,<seq>,<t_recv>,<t0>,<len>
CSV,DELAY,<seq>,<delay_ticks>
```

---

### 4.3 attacker.c — blackhole 공격자

**역할:** id=2(A1), id=3(A2), id=4(A3). DODAG에 정상 참여 후 공격 수행.

**공격 로직:**
```c
// netstack IP output hook
ip_output_hook() {
  if (시뮬레이션 시간 < ATTACK_WARMUP_SECONDS) → 전달
  if (!is_forwarded_udp_to_root()) → 전달   // 제어 패킷 보호
  전달 대상 UDP 데이터 패킷이면 → DROP  // 100% 드롭
  else → 전달
}
```

**제어 패킷 보호:** DIO / DAO / DIS는 항상 포워딩 (공격 은닉 목적).

**주요 파라미터:**
- `ATTACK_WARMUP_SECONDS` = 350 (공격 시작 시간)
- `ATTACK_DROP_PCT` = 100 (드롭 확률 %)

**CSV 출력:**
```
CSV,PROTOCOL,<id>,ATTACKER
CSV,ATTACK_PARAMS,<id>,drop_pct=100,warmup=350
CSV,ATTACK_ENABLED,<id>
CSV,FWD,<id>,<total_fwd>,<udp_to_root>,<dropped>
```

---

### 4.4 sinkhole_attacker.c — sinkhole 공격자

**역할:** id=18. 기존 sender 하나를 대체하며, 350s 이후 낮은 rank DIO를 주기적으로 광고해 주변 노드를 parent로 끌어들인다.

**공격 로직:**
```c
if (time < ATTACK_WARMUP_SECONDS) → 정상 rank 광고
else {
  advertised_rank = ROOT_RANK + SINKHOLE_RANK_DELTA;
  dio_output(...);  // 15s 주기
}
```

**주요 파라미터:**
- `ATTACK_WARMUP_SECONDS` = 350
- `SINKHOLE_RANK_DELTA` = 1
- `SINKHOLE_DIO_PERIOD_SECONDS` = 15

**CSV 출력:**
```
CSV,PROTOCOL,<id>,SINKHOLE
CSV,ATTACK_PARAMS,<id>,mode=sinkhole,warmup=350,rank_delta=1,dio_period=15
CSV,ATTACK_ENABLED,<id>
CSV,SINKHOLE_DIO,<id>,<count>
```

---

## 5. 신뢰 모델

### 5.1 TA-BRPL 신뢰 모델 (ta-brpl-trust.h/c)

#### 아키텍처

```
IP Input Hook (netstack_ip_packet_processor)
    │
    ├─ MAC sender ≠ IP source → ta_trust_notify_forwarded(mac_id)  [T_fwd]
    └─ ICMPv6 RPL DIO 수신   → ta_trust_notify_dio(mac_id, rank, ver) [T_ctrl]

송신 직전 → ta_trust_notify_sent(parent_id)                         [T_fwd]
큐 상태   → ta_trust_notify_backlog(node_id, q_adv, q_max)          [T_hon]

주기 업데이트 (150s):
    ta_trust_update_all()
    │
    ├─ compute_t_fwd()   → (F + α) / (S + α + β)
    ├─ compute_t_ctrl()  → 1 - 이상 점수
    ├─ compute_t_hon()   → 1 - |Q_adv - Q_est| / Q_max
    ├─ aggregate_trust() → T_fwd^0.5 × T_ctrl^0.3 × T_hon^0.2
    └─ ewma_update()     → 비대칭 EWMA
```

#### 신뢰 성분

**T_fwd (포워딩 신뢰, 가중치 50%)**
```
T_fwd = (F_ij + α) / (S_ij + α + β)

F_ij : 수동 청취(overhearing)로 관찰된 포워딩 횟수
S_ij : 해당 노드를 통해 전송한 패킷 수
α, β : Bayesian 평활화 파라미터 (초기값 = 1)
```

**T_ctrl (제어 평면 신뢰, 가중치 30%)**
```
T_ctrl = 1 - A_ij

A_ij = (w_rank × A_rank + w_dio × A_dio + w_ver × A_ver) / 10

A_rank : 비정상 랭크 변화 횟수 / 윈도우
A_dio  : 비정상 DIO 빈도
A_ver  : 버전 불일치 횟수
```

**T_hon (혼잡 정직성 신뢰, 가중치 20%)**
```
T_hon = 1 - min(1, |Q_adv - Q_est| / Q_max)

Q_adv : 이웃 노드가 광고한 큐 점유율
Q_est : 로컬에서 추정한 해당 노드 큐 점유율
Q_max : 최대 큐 크기 (8)
```

**통합 신뢰 (가중 기하평균)**
```
T̃ = T_fwd^(5/10) × T_ctrl^(3/10) × T_hon^(2/10)
```

**시간적 업데이트 (비대칭 EWMA)**
```
λ = λ_decrease = 0.2  (신뢰 감소시: 빠른 반응)
λ = λ_normal   = 0.7  (신뢰 증가시: 느린 회복)

T(t+1) = λ × T(t) + (1-λ) × T̃
```

#### 신뢰 임계값 정책

| 상태 | 조건 | 동작 |
|---|---|---|
| `TA_TRUST_NORMAL` | T ≥ 750 | 정상 부모 후보 |
| `TA_TRUST_SUSPECT` | 550 ≤ T < 750 | BRPL 비용 패널티 적용 |
| `TA_TRUST_UNTRUSTED` | 350 ≤ T < 550 | 부모 후보 제외 |
| `TA_TRUST_BLACKLISTED` | T < 350 | 300s 격리 |

#### BRPL 통합 인터페이스

```c
// rpl-brpl.c의 약 심볼(weak symbol) 오버라이드
uint16_t brpl_trust_get(uint16_t node_id) {
    return ta_trust_get(node_id);  // 0~1000 반환
}
// BRPL은 이 값을 라우팅 비용 함수에 통합
```

#### 데이터 구조

```c
typedef struct {
  uint16_t node_id;
  uint8_t  valid;
  // T_fwd
  uint32_t fwd_sent;       // S_ij
  uint32_t fwd_observed;   // F_ij
  // T_ctrl
  uint16_t ctrl_rank_dev_count;
  uint8_t  ctrl_dio_count;
  uint8_t  ctrl_version_mismatch;
  uint16_t prev_rank;
  uint8_t  prev_version;
  // T_hon
  uint16_t hon_q_adv;
  uint16_t hon_q_max;
  uint8_t  hon_valid;
  // 결과
  uint16_t trust;          // 0~1000
  uint8_t  blacklisted;
  clock_time_t blacklist_until;
} ta_trust_entry_t;
```

---

### 5.2 SMTrust 신뢰 모델 (smtrust.h/c)

#### 아키텍처

```
IP Input Hook (netstack_ip_packet_processor)
    │
    ├─ RSSI 샘플링 → TMLLS 계산용
    ├─ MAC sender ≠ IP source → pkts_observed++ (TMSR용)
    └─ ICMPv6 RPL DIO 수신
        ├─ 랭크/시퀀스 추출 → detect_rank_attack()
        └─ DIO 확장(0xFE태그) → TMRT 추출

smtrust_notify_sent(parent_id) → pkts_sent++  (TMSR용)

주기 업데이트 (120s):
    smtrust_periodic_update()
    │
    ├─ compute_tmsr()       TMSR = F / S
    ├─ compute_tmel()       TMEL = 잔여에너지 비율
    ├─ compute_tmlls()      TMLLS = (RSSI - min) / (max - min)
    ├─ compute_tmrt()       TMRT = 이웃 추천 평균
    ├─ tm_h0 = 이전 trust_index
    ├─ tm_mobility = 1.0 (정적 토폴로지)
    └─ compute_trust_index() = 가중합
```

#### TrustIndex 공식

```
TrustIndex = 0.25·TMSR + 0.15·TM(H0) + 0.15·TMEL
           + 0.20·TMLLS + 0.15·TMMobility + 0.10·TMRT
```

#### 신뢰 수준 (Fuzzy Membership)

| 레벨 | 범위 | 설명 | 라우팅 |
|---|---|---|---|
| L1 | 0.00–0.20 | No Trust | 금지 |
| L2 | 0.21–0.45 | Poor Trust | 금지 |
| L3 | 0.46–0.70 | Fair Trust | 대안만 |
| L4 | 0.71–0.90 | Good Trust | 허용 |
| L5 | 0.91–1.00 | Full Trust | 선호 |

**부모 후보 임계값:** `SMTRUST_THRESHOLD` = 0.46 (L3 이상)

#### 공격 감지

```
랭크 공격: DIO 시퀀스 증가 없이 랭크 변경 감지
블랙홀:    TMSR < 0.5 AND TrustIndex < 0.46
```

#### TMRT 전파 (DIO 확장)

```
DIO 메시지에 커스텀 확장 삽입:
  [0xFE][node_id_byte][trust_index × 100]
이웃 노드가 이 DIO를 수신하면 해당 노드에 대한 추천 신뢰로 활용
```

---

## 6. 설정 시스템

### 6.1 project-conf.h — 전역 파라미터

```c
/* ── 라우팅 드라이버 ────────────────────────────── */
NETSTACK_CONF_ROUTING = rpl_classic_driver

/* ── 프로토콜 변형 (Makefile CFLAGS에서 주입) ─────
   RPL_BASELINE_MODE → MRHOF + ETX
   BRPL_MODE         → rpl_brpl OC
   TABRPL_MODE       → BRPL + ta-brpl-trust.c
*/

/* ── RPL 파라미터 ────────────────────────────────
   DIO_INTERVAL_MIN       = 12  (Imin = 4096ms)
   DIO_INTERVAL_DOUBLINGS = 8
   DIO_REDUNDANCY         = 10
*/

/* ── 트래픽 파라미터 ─────────────────────────────
   SEND_INTERVAL_SECONDS  = 30
   WARMUP_SECONDS         = 150
*/

/* ── TA-BRPL 신뢰 파라미터 ───────────────────────
   TA_TRUST_SCALE         = 1000
   TA_TRUST_TAU_WARN      = 750
   TA_TRUST_TAU_JOIN      = 550
   TA_TRUST_TAU_BLACK     = 350
   TA_TRUST_INIT          = 500
   TA_TRUST_LAMBDA_NORMAL = 700
   TA_TRUST_LAMBDA_DECREASE = 200
   TA_TRUST_UPDATE_INTERVAL = 150
   TA_TRUST_W_FWD/CTRL/HON = 5/3/2
   TA_TRUST_BLACKLIST_DURATION = 300
   TA_TRUST_MAX_NEIGHBORS = 16
*/

/* ── BRPL 파라미터 ───────────────────────────────
   TRUST_SCALE            = 1000
   TRUST_MIN              = 550  (= tau_join)
   BRPL_CONF_QUEUE_MAX    = 8
*/
```

### 6.2 Makefile 계층

```
motes/Makefile.{rpl,brpl,tabrpl,smtrust,receiver,attacker,sinkhole_rpl,sinkhole_brpl}
    │
    └─ $(CONTIKI)/Makefile.include   ← contiki-ng-brpl/Makefile.include
        └─ TARGET=cooja 빌드 규칙
```

**각 Makefile의 역할:**

| Makefile | 소스 | 추가 소스 | 주요 플래그 |
|---|---|---|---|
| `Makefile.rpl` | sender.c | — | `RPL_BASELINE_MODE=1` |
| `Makefile.brpl` | sender.c | — | `BRPL_MODE=1`, `BRPL_CONF_TRUST_ENABLE=0` |
| `Makefile.tabrpl` | sender.c | ta-brpl-trust.c | `BRPL_MODE=1`, `TABRPL_MODE=1`, `BRPL_CONF_TRUST_ENABLE=1`, `LDLIBS+=-lm` |
| `Makefile.smtrust` | sender.c | smtrust.c | `SMTRUST_MODE=1`, `RPL_BASELINE_MODE=1`, `LDLIBS+=-lm` |
| `Makefile.receiver` | receiver_root.c | — | — |
| `Makefile.attacker` | attacker.c | — | `ATTACK_DROP_PCT=100`, `ATTACK_WARMUP_SECONDS=350` |
| `Makefile.sinkhole_rpl` | sinkhole_attacker.c | — | `RPL_BASELINE_MODE=1`, `ATTACK_MODE=1`, `ATTACKER_NODE_ID=18`, `SINKHOLE_RANK_DELTA=1` |
| `Makefile.sinkhole_brpl` | sinkhole_attacker.c | — | `BRPL_MODE=1`, `ATTACK_MODE=1`, `ATTACKER_NODE_ID=18`, `SINKHOLE_RANK_DELTA=1` |

---

## 7. 시뮬레이션 토폴로지

### 7.1 GRID 6×6 레이아웃

```
y\x   0    33   67   100  133  167
  0  [ 5] [ 6] [ 7] [ 8] [ 9] [10]
 33  [11] [12] [13] [14] [15] [16]
 67  [17] [A1] [RT] [A3] [20] [21]   ← y=67 행
100  [22] [23] [24] [25] [26] [27]
133  [28] [29] [A2] [30] [31] [32]   ← y=133 행 (A2, A3)
167  [33] [34] [35] [36] [ -] [ -]

RT = Root (id=1, x=67, y=67)
A1 = Attacker (id=2, x=33, y=67)  ← 1-hop (34m < 50m TX range)
A2 = Attacker (id=3, x=67, y=133) ← 2-hop (66m > 50m)
A3 = Attacker (id=4, x=100, y=67) ← 1-hop (33m)
```

**공격자 배치 전략:**
- A1: 루트 바로 옆(1-hop) → 많은 트래픽 경유, 고영향
- A2: 2-hop 위치 → 중간 계층 공격
- A3: 루트 근접(1-hop) → 광범위 서비스 교란

### 7.2 라디오 환경

| 파라미터 | 값 |
|---|---|
| 라디오 모델 | UDGM (Unit Disk Graph Model) |
| TX 범위 | 50.0m |
| 간섭 범위 | 60.0m |
| TX 성공률 | 1.0 (무손실) |
| RX 성공률 | 1.0 |
| 간격 | 33m (인접 노드 항상 TX 범위 내) |

### 7.3 CSC 파일 구조

4개의 `.csc` 파일은 동일한 구조를 가지며 `sender_type`의 `<commands>` 항목만 다르다.

```xml
<simconf>
  <simulation>
    <randomseed>123456</randomseed>   <!-- run_sweep.sh가 패치 -->
    <radiomedium>UDGM ...</radiomedium>
    <motetype>root_type  → Makefile.receiver</motetype>
    <motetype>sender_type → Makefile.{rpl|brpl|tabrpl|smtrust}</motetype>
    <motetype>attacker_type → Makefile.attacker</motetype>
    <motetype>sinkhole_type → Makefile.{sinkhole_rpl|sinkhole_brpl}</motetype>
    <!-- 36개 mote 배치 (id, position) -->
    <plugin>ScriptRunner: TIMEOUT(900000), CSV 로그 수집</plugin>
  </simulation>
</simconf>
```

---

## 8. 실험 프레임워크

### 8.1 실험 타임라인

```
0s ─────────── 150s ─────────── 350s ─────────────── 650s ────── 900s
│   워밍업        │   정상 동작    │    공격 + 탐지/복구  │   안정화   │
│  (DODAG 형성)  │  (기준선 측정) │  (공격자: 100% 드롭) │  (회복)    │
```

### 8.2 run_sweep.sh — 헤드리스 스윕

```bash
# 기본 실행 (4 프로토콜 × 30 시드 = 120 runs, 4개 병렬)
./scripts/run_sweep.sh

# 커스텀 옵션
./scripts/run_sweep.sh \
    --protocols RPL,TABRPL \
    --seeds 1-10 \
    --jobs 8
```

**동작 흐름:**

```
1. 인자 파싱 (--protocols, --seeds, --jobs)
2. Cooja gradlew 존재 확인
3. 시나리오 CSC 존재 확인
4. 작업 목록 생성: {PROTO}:{SEED} × 120개
5. xargs -P N 으로 병렬 실행
   └─ run_one(PROTO, SEED):
       ├─ done 파일 존재시 스킵 (재실행 방지)
       ├─ CSC 임시 복사 + randomseed 패치 (sed)
       ├─ gradlew run --args="-nogui=<tmp.csc>" 실행
       ├─ CSV 라인 필터링 → results/${PROTO}/${SEED}/sim.log
       └─ done 센티넬 파일 생성
```

**출력 디렉토리:**
```
results/
├── RPL/1/sim.log, done
├── RPL/2/sim.log, done
...
├── BRPL/1/sim.log, done
├── SMTRUST/1/sim.log, done
└── TABRPL/1/sim.log, done
```

### 8.3 Cooja 실행 경로

```bash
/home/dev/contiki-ng/tools/cooja/gradlew \
    --no-watch-fs --parallel --build-cache \
    -p /home/dev/contiki-ng/tools/cooja \
    run --args="-nogui=<scenario.csc>"
```

### 8.4 성능 메트릭

| 메트릭 | 측정 방법 | CSV 소스 |
|---|---|---|
| PDR (Packet Delivery Ratio) | TX 대비 RX 비율 | CSV,TX / CSV,RX |
| E2E 지연 | t_recv - t0 | CSV,DELAY |
| RTT | t_ack - t0 | CSV,RTT |
| 부모 변경 횟수 | PARENT 라인 변화 | CSV,PARENT |
| 라우팅 수렴 시간 | ROUTING_READY까지 | ROUTING_READY |
| 신뢰값 분포 | 주기적 신뢰 로그 | CSV,TRUST |
| 공격 탐지 시간 | BLACKLIST 이벤트 | CSV,TRUST_BLACKLIST |

### 8.5 통계 분석

- **반복:** 30회 / 프로토콜
- **신뢰구간:** 95% CI
- **검정:** Wilcoxon rank-sum (비모수)
- **도구:** `scripts/analyze_results.R`, `scripts/plot_sweep_figures.R`

---

## 9. CSV 로그 포맷

Cooja 시뮬레이션 로그에서 `CSV,` 접두사를 가진 라인이 데이터다.

### 9.1 전체 CSV 타입 목록

```
# === 초기화 ===
CSV,PROTOCOL,<node_id>,<TABRPL|SMTRUST|BRPL|RPL|ATTACKER>
CSV,LLADDR,<node_id>,<aa:bb:cc:dd:ee:ff:gg:hh>

# === 라우팅 상태 ===
CSV,PARENT,<node_id>,<parent_ipv6|none>
CSV,ROUTING,<node_id>,<joined>,<parent_ip>,<rank>

# === 트래픽 ===
CSV,TX,<sender_id>,<seq>,<t0_ticks>,<dag_joined>
CSV,RX,node=1,<src_ip>,<seq>,<t_recv_ticks>,<t0_ticks>,<len>
CSV,RTT,<seq>,<t0_ticks>,<t_ack_ticks>,<rtt_ticks>,<len>
CSV,DELAY,<seq>,<delay_ticks>

# === TA-BRPL 신뢰 ===
CSV,TRUST,<self_id>,<nbr_id>,<t_fwd>,<t_ctrl>,<t_hon>,<t_agg>,<t_ewma>
CSV,TRUST_BLACKLIST,<self_id>,<nbr_id>
CSV,TRUST_UNBLACKLIST,<self_id>,<nbr_id>

# === SMTrust 신뢰 ===
CSV,SMTRUST,<self_id>,<nbr_id>,<tmsr>,<tm_h0>,<tmel>,<tmlls>,<tmrt>,<ti>

# === 공격자 ===
CSV,ATTACK_PARAMS,<id>,drop_pct=100,warmup=350
CSV,ATTACK_ENABLED,<id>
CSV,FWD,<id>,<total_fwd>,<udp_to_root_fwd>,<dropped>

# === 시뮬레이션 제어 ===
ROUTING_READY joined=1 reachable=1
SIMULATION_DONE
```

### 9.2 시간 단위

- 모든 타임스탬프: Contiki `clock_time()` 틱 (CLOCK_SECOND 단위)
- 실제 시간 = ticks / CLOCK_SECOND

---

## 10. 빌드 시스템

### 10.1 빌드 명령

```bash
cd motes

# RPL
make -f Makefile.rpl TARGET=cooja WERROR=0

# BRPL
make -f Makefile.brpl TARGET=cooja WERROR=0

# TA-BRPL
make -f Makefile.tabrpl TARGET=cooja WERROR=0

# SMTrust
make -f Makefile.smtrust TARGET=cooja WERROR=0

# 루트 노드 (공유)
make -f Makefile.receiver TARGET=cooja WERROR=0

# 공격자
make -f Makefile.attacker TARGET=cooja WERROR=0
make -f Makefile.sinkhole_rpl TARGET=cooja WERROR=0
```

### 10.2 빌드 산출물

```
motes/build/cooja/
├── sender.cooja       (RPL / BRPL / TA-BRPL / SMTrust 공유 이름)
├── receiver_root.cooja
├── attacker.cooja
└── sinkhole_attacker.cooja
```

### 10.3 알려진 주의사항

| 항목 | 설명 |
|---|---|
| `-lm` 링크 | `CFLAGS`가 아닌 `LDLIBS`에 지정해야 함 (Contiki Makefile.include 링크 순서) |
| `uip_icmp6_hdr` 없음 | Contiki-NG는 `struct uip_icmp_hdr` (uip.h) 사용. `UIP_ICMP_BUF` 매크로로 접근 |
| `packetbuf_addr()` | `net/packetbuf.h` 명시적 include 필요 |
| IDE IntelliSense | Contiki 헤더 경로 미인식 → 가상 오류 표시. 실제 빌드는 정상 |

---

## 11. 데이터 흐름

### 11.1 전체 시스템 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                        Cooja Simulator                       │
│                                                             │
│  Sender Node (id=5~36)                                      │
│  ┌────────────────────────┐                                 │
│  │ sender_process          │                                │
│  │  ├─ trust_update_all() ─┤──→ CSV,TRUST (serial)         │
│  │  ├─ UDP send ───────────┼──→ CSV,TX (serial)            │
│  │  └─ echo_rx_callback() ─┤──→ CSV,RTT (serial)           │
│  │                         │                               │
│  │ ta_ip_input_hook()      │                               │
│  │  ├─ overhearing ────────┤→ fwd_observed++               │
│  │  └─ DIO parse ──────────┤→ ctrl_rank_dev_count++        │
│  └────────────────────────┘                                 │
│           │ UDP/IPv6                                        │
│           ↓ (경유: Attacker)                                │
│  Attacker Node (id=2,3,4)                                   │
│  ┌──────────────┐                                          │
│  │ ip_output_hook│                                         │
│  │ 50% DROP ────┤→ CSV,FWD (serial)                       │
│  └──────────────┘                                          │
│           │                                                 │
│           ↓                                                 │
│  Root Node (id=1)                                           │
│  ┌──────────────┐                                          │
│  │ udp_rx_callback│                                        │
│  │ ├─ CSV,RX ───┤→ serial                                 │
│  │ └─ echo_reply┤→ 송신기에 RTT 응답                       │
│  └──────────────┘                                          │
│           │ serial output                                   │
│           ↓                                                 │
│  ScriptRunner: log 수집 → TIMEOUT(900000) → testOK()       │
└─────────────────────────────────────────────────────────────┘
           │
           ↓ (run_sweep.sh 필터링)
  results/${PROTO}/${SEED}/sim.log
           │
           ↓ (tools/parse_results.py)
  pandas DataFrame / CSV 집계
           │
           ↓ (scripts/analyze_results.R)
  통계 분석 + 시각화 (PDF 그림)
```

### 11.2 신뢰 피드백 루프 (TA-BRPL)

```
패킷 전송 ──→ ta_trust_notify_sent(parent)
    │
    ↓ 150s 후
패킷 관찰 ←── ta_trust_notify_forwarded(mac_id)   [IP hook]
DIO 수신   ←── ta_trust_notify_dio(mac_id, r, v)   [IP hook]
큐 상태    ←── ta_trust_notify_backlog(id, q, max)

    ↓ 주기 업데이트
compute_t_fwd/ctrl/hon()
    ↓
aggregate_trust() → T̃ (가중 기하평균)
    ↓
ewma_update() → T(t+1)  [비대칭 λ]
    ↓
brpl_trust_get() 오버라이드
    ↓
BRPL OC: routing_cost += trust_penalty
    ↓
부모 선택 영향 → 신뢰 낮은 노드 자동 우회
```

---

*문서 생성일: 2026-03-16*
*코드베이스 버전: main 브랜치 (b2d0cc0)*
