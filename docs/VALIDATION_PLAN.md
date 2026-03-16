# TA-BRPL 검증 계획서

> 논문용 대규모 실험 이전에 반드시 통과해야 할 디버깅/검증 실험 목록

---

## 원칙

1. **소형 토폴로지 먼저** — GRID 6×6 이전에 미니 토폴로지로 동작 원리 검증
2. **컴포넌트 단위 검증** — T_fwd → T_ctrl → T_hon → EWMA → blacklist 순서
3. **오탐 검증 필수** — 탐지율만큼 오탐율(FPR)이 낮은지 반드시 확인
4. **공격 vs 혼잡 분리** — 이것이 TA-BRPL의 핵심 기여이므로 반드시 실험

---

## V1. 단일 공격자 미니 토폴로지

### 목적

공격 → T_fwd 하락 → parent change 흐름이 의도대로 동작하는지 최소 환경에서 검증.

### 토폴로지

```
Root(1) ── A_attacker(2) ── Sender(3)
                        └── Sender(4)
                        └── Sender(5)
(대안 경로)
Root(1) ──────────────── Sender(3) (직접 연결 가능하면)
```

- 노드 수: 5~7개
- 공격자: 1개 (Root와 Sender 사이 중간에 위치)
- Sender들은 공격자를 거쳐 Root에 도달 (초기 부모)

### 시나리오

1. 0~200s: 정상 동작 (공격 없음)
2. 200s~: 공격자 100% 드롭 시작

### 확인 항목

| 체크 | 기대 동작 |
|---|---|
| 공격 전 공격자 T_fwd | 1.0 ≈ 0.9+ |
| 공격 시작 후 1 update cycle (150s) 후 T_fwd | < 0.7 |
| T_fwd가 tau_join(0.45) 이하로 하락 | parent change 또는 trust penalty 증가 |
| T_fwd가 tau_black(0.25) 이하 | blacklist 이벤트 |
| `CSV,TRUST_BLACKLIST` 출력 | 타임스탬프 확인 |
| blacklist 후 Sender들이 대안 경로 사용 | `CSV,PARENT` 변경 확인 |
| 대안 경로로 전환 후 PDR 회복 | `CSV,RX` 수 증가 |

### 성공 기준

```
공격 시작 후 2~3 update cycle(300~450s) 이내 blacklist
PDR 회복률 ≥ 80% (대안 경로 있는 경우)
CSV,TRUST_BLACKLIST 이벤트 정확히 발생
```

---

## V2. 정상 노드 오탐(False Positive) 실험

### 목적

공격자 없는 환경에서 정상 노드가 부당하게 신뢰 하락/blacklist 되지 않는지 확인.
**오탐이 높으면 PDR이 오히려 악화되고 논문이 약해짐.**

### 시나리오 A: 무손실 정상 동작

- GRID 6×6, 공격자 없음
- 900s 전체 실행
- 기대: 모든 노드 T_fwd ≥ 0.8 이상 유지

### 시나리오 B: 고트래픽 혼잡 (공격 없음)

- GRID 6×6, 공격자 없음
- 5개 Root 인접 노드: SEND_INTERVAL = 15s (2배 빠름)
- 큐 점유율 ≥ 70% 유도
- 기대: PDR 하락이 있어도 T_fwd는 유지됨
  (혼잡 = 큐에 막힘이지, 포워딩 실패가 아님)

### 확인 항목

| 체크 | 기대값 |
|---|---|
| 정상 노드 T_fwd (900s 후) | ≥ 0.75 |
| blacklist 이벤트 발생 여부 | 0 (없어야 함) |
| SUSPECT 상태 진입 노드 수 | 5% 이하 |
| 혼잡 시 T_hon 변화 | 약간 하락 가능 (혼잡 반영) |
| 혼잡 시 T_fwd 변화 | 미미 (혼잡 ≠ 드롭) |

### 성공 기준

```
FPR(False Positive Rate) < 5%
즉, 공격자 없는 조건에서 정상 노드가 blacklist되는 비율 < 5%
```

---

## V3. 혼잡 vs 공격 분리 실험 (핵심)

### 목적

TA-BRPL의 핵심 주장 검증:
"단순 PDR 하락 ≠ 공격. T_fwd/T_ctrl/T_hon 조합이 구분함."

### 시나리오 구성

| 시나리오 | 혼잡 | 공격 |
|---|---|---|
| C1: Baseline | 없음 | 없음 |
| C2: Congestion only | 있음 (고트래픽) | 없음 |
| C3: Attack only | 없음 (정상 트래픽) | 있음 (100% 드롭) |
| C4: Both | 있음 | 있음 |

### 측정 지표별 기대값

| 지표 | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| PDR | 높음 | 중간 | 낮음 | 낮음 |
| T_fwd | 높음 | **높음** | **낮음** | 낮음 |
| T_hon | 높음 | **낮음** | **높음** | 낮음 |
| T_ctrl | 높음 | 높음 | 높음* | 높음* |
| parent change | 적음 | 중간 | 많음 | 많음 |

*공격자는 DIO 조작을 하지 않으므로 T_ctrl 영향 없음 (정상)

### 검증 포인트

```
C2 vs C3 구분:
  C2: PDR↓ but T_fwd↑, T_hon↓  → "혼잡, 신뢰는 유지"
  C3: PDR↓ and T_fwd↓, T_hon↑  → "공격, T_fwd가 탐지"

이것이 논문에서 "TA-BRPL은 혼잡과 공격을 구분한다"는 주장의 근거.
```

---

## V4. T_ctrl 독립 검증 (sinkhole)

### 목적

T_ctrl (제어 평면 신뢰)이 실제로 기여하는지 확인.
현재는 node 18 sinkhole이 낮은 rank DIO를 광고하므로 T_ctrl을 부분 검증할 수 있다.
다만 단일 위치, 단일 패턴이라 추가 검증이 더 필요하다.

### 시나리오

```
motes/sinkhole_attacker.c: DIO의 rank를 낮게 광고 (sinkhole 공격)
→ T_ctrl.A_rank 증가
→ T_ctrl 하락
→ blacklist
```

> 현재 코드베이스에는 기본 sinkhole 시나리오가 포함되어 있으며, 향후엔 colluding sinkhole / version attack으로 확장한다.

---

## V5. EWMA 파라미터 민감도

### 목적

lambda 값 선택의 정당화.

### 실험 조건

GRID 6×6, 1개 공격자(A1), 단일 seed, 공격 시작 350s.

| 조건 | λ_decrease | λ_normal |
|---|---|---|
| 기본값 | 0.5 | 0.7 |
| 빠른 반응 | 0.1 | 0.7 |
| 느린 반응 | 0.4 | 0.7 |
| 빠른 회복 | 0.2 | 0.5 |
| 느린 회복 | 0.2 | 0.9 |

### 측정 지표

- 공격 후 blacklist까지 소요 시간
- 오탐 발생 여부
- 회복 후 신뢰 복귀 시간

---

## V6. 임계값 민감도

### 목적

tau_warn / tau_join / tau_black 값 선택 정당화.

### 실험 조건 (각 1 seed, 빠른 확인용)

| tau_warn | tau_join | tau_black | 기대 |
|---|---|---|---|
| 0.70 | 0.45 | 0.25 | 현재 기본값 |
| 0.80 | 0.60 | 0.40 | 더 보수적 |
| 0.70 | 0.50 | 0.30 | 더 완화 |
| 0.75 | 0.40 | 0.25 | join 임계 낮춤 |

### 측정

- Precision (탐지 정확도)
- Recall (탐지 완전성)
- PDR after detection

---

## V7. Pilot 실험 (5 seeds)

**목적:** 30회 본실험 전 파이프라인 전체 검증

```bash
./scripts/run_sweep.sh --protocols RPL,BRPL,SMTRUST,TABRPL --seeds 1-5 --jobs 4
```

---

## V8. Recovery 안정화 검증

### 목적

blacklist 해제 이후 recovery 구간의 과도한 route 재평가를 줄였는지 확인한다.

### 확인 로그

- `CSV,TRUST_UNBLACKLIST,node_id,tick,trust,penalty_scale,cooldown`
- `CSV,TRUST_RECOVERY,self_id,nbr_id,tick,trust,penalty_scale`
- `CSV,TRUST_REDROP,node_id,tick,trust`
- `CSV,TRUST_RECOVERY_DONE,node_id,tick,trust`
- `CSV,TRUST_ROUTEGUARD,self_id,nbr_id,exposure_s,trust,penalty_scale,escape`
- `CSV,TRUST_ESCAPE,self_id,nbr_id,tick,trust`
- `CSV,ROUTE,node_id,tick,parent_id,rank,hop_est,parent_switch_count,...`

### 핵심 체크

| 체크 | 기대 |
|---|---|
| release 직후 60~120초 parent switch count | 이전보다 감소 |
| release 이후 hop count | 급격한 왕복 없이 완만 |
| release 이후 trust 재하락 횟수 | seed당 소수 |
| release 후 same parent 재선택 비율 | 무작위 재진입보다 안정적 |

### 현재 구현

- release 시 trust는 `tau_join`으로 복구
- routing penalty는 `120초` 동안 `1.60 → 1.00` 선형 감쇠
- 현재 preferred parent에는 기존 hysteresis를 계속 적용
- attacker parent는 direct role penalty + persistence penalty를 받음
- `escape mode`가 켜지면 current-parent hysteresis를 꺼서 sticky attacker parent에서 빠져나오게 함

### 확인 항목

- [ ] 20개 실험 전체 sim.log 생성됨
- [ ] parse_results.py가 오류 없이 실행됨
- [ ] PDR/delay/trust trace CSV 생성됨
- [ ] 4개 프로토콜 간 PDR 차이가 예상과 일치하는지 확인

### 기대 결과 (정성적)

```
공격 하 PDR 순서: TA-BRPL > BRPL ≈ SMTrust > RPL
공격 탐지 속도:   TA-BRPL > SMTrust > BRPL(없음) > RPL(없음)
E2E 지연 공격 후: TA-BRPL ≈ BRPL < RPL < SMTrust (예상)
```

---

## 검증 진행 매트릭스

| 실험 | 우선순위 | 구현 필요 | 완료 |
|---|---|---|---|
| V1. 단일 공격자 미니 토폴로지 | ★★★★★ | 미니 CSC 파일 생성 | ⬜ |
| V2. 오탐 실험 | ★★★★★ | 공격자 없는 시나리오 | ⬜ |
| V3. 혼잡 vs 공격 분리 | ★★★★★ | C1~C4 시나리오 CSC | ⬜ |
| V4. T_ctrl 독립 검증 | ★★★☆ | sinkhole 시나리오 확장 필요 | ⬜ |
| V5. EWMA 민감도 | ★★★☆ | CFLAGS 파라미터 변경만 | ⬜ |
| V6. 임계값 민감도 | ★★★☆ | CFLAGS 파라미터 변경만 | ⬜ |
| V7. Pilot 5 seeds | ★★★★ | run_sweep.sh 준비됨 | ⬜ |
