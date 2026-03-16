# TA-BRPL 구현 계획서

> 단계별 MVP 구현 순서 및 각 단계별 완료 기준

---

## 0. BRPL 비용함수 결합식 확정 (핵심 설계 결정)

### 0.1 rpl-brpl.c 실제 동작 구조

서브모듈 `rpl-brpl.c`의 실제 parent 선택 흐름:

```
brpl_best_parent(p1, p2)
  │
  ├─ brpl_weight_base(p)        // BRPL 기본 가중치
  │   weight = (θ × P_norm - (1-θ) × ΔQ_norm) / 1000
  │
  └─ brpl_apply_trust_penalty(weight, p)   // 신뢰 패널티 적용
      ↓
  낮은 weight를 가진 부모 선택 (weight가 작을수록 좋음)
```

**BRPL 기본 가중치 수식:**
```
weight_base = (θ × P̃_norm - (1-θ) × ΔQ_norm) / 1000

θ     = β + (1-β)(1-ρ)           // 토폴로지 안정성 × 혼잡 여유
P̃_norm = (ETX + rank) / P_max    // 정규화 경로 비용
ΔQ_norm = (q_self - q_nbr) / q_max  // 큐 차이 (백프레셔)
```

**신뢰 패널티 결합식 (현재 구현):**

γ=1 (선형):
```
w_trust = weight_base × T / (1000 + λ × (1000 - T))
```

γ=2 (이차):
```
w_trust = weight_base × T² / (1000² + λ × (1000-T)²)
```

여기서:
- `T` = `brpl_trust_get(node_id)` 반환값 (0~1000), TA-BRPL이 오버라이드
- `T_min` = 450 (= tau_join): 이 미만이면 trust는 450으로 클램프 → **실질적 route-entry 하한**
- `λ` = `BRPL_CONF_TRUST_LAMBDA_PENALTY`: 패널티 강도
- `γ` = `TRUST_PENALTY_GAMMA`: 패널티 곡률

### 0.2 TA-BRPL 통합 시 실제 결합 방식

TA-BRPL은 `brpl_trust_get()` 오버라이드만 하면 된다.
rpl-brpl.c 내부가 나머지를 처리한다.

```c
// ta-brpl-trust.c에서 이것만 구현하면 됨
uint16_t brpl_trust_get(uint16_t node_id) {
    return ta_trust_get(node_id);  // 0~1000
}
```

**완전한 결합식:**
```
score(p) = weight_base(p) × T(p)^γ / (1000^γ + λ × (1000-T(p))^γ)

T(p) = max(TRUST_MIN, ta_trust_get(p.node_id))
     = max(450, T̃_ewma(p))

T̃_ewma = EWMA(T_fwd^0.5 × T_ctrl^0.3 × T_hon^0.2 × 1000)
```

### 0.3 파라미터 기본값 및 정당화

| 파라미터 | 값 | 근거 |
|---|---|---|
| `TRUST_MIN` (= tau_join) | 450 | 신뢰 임계값 이하 → route penalty 하한 |
| `TRUST_PENALTY_GAMMA` | 1 (선형) | 단순/예측 가능, 첫 구현에 적합 |
| `BRPL_CONF_TRUST_LAMBDA_PENALTY` | 450 | 완화된 패널티, churn 감소 목적 |

> **γ=2 (이차)는 논문 완성 이후 ablation으로 비교 가능. 기본값은 γ=1.**

---

## 1단계: RPL baseline 완성

**목표:** "측정 파이프라인이 돌아간다"

### 구현 체크리스트

- [ ] `make -f Makefile.rpl TARGET=cooja WERROR=0` 빌드 성공
- [ ] `make -f Makefile.receiver TARGET=cooja WERROR=0` 빌드 성공
- [ ] Cooja GRID6x6_RPL.csc 헤드리스 실행 900s 정상 종료
- [ ] `CSV,TX` 라인이 모든 송신 노드에서 주기적으로 출력됨
- [ ] `CSV,RX` 라인이 루트에서 수신 확인됨
- [ ] `CSV,RTT` 라인이 RTT 측정값을 포함함
- [ ] `CSV,PARENT` 라인이 부모 변경을 추적함
- [ ] PDR = TX 수 대비 RX 수 계산 가능한지 후처리 스크립트 확인

### 검증 기준

```
기대 PDR: ~95% 이상 (무손실 라디오, 공격 없음)
기대 RTT: ~수백 ms ~ 수 s (hop 수에 비례)
모든 35개 송신 노드가 ROUTING_READY 이전에 DODAG 참여 완료
```

---

## 2단계: BRPL 단독 완성

**목표:** "BRPL 자체가 재현된다"

### 구현 체크리스트

- [ ] `make -f Makefile.brpl TARGET=cooja WERROR=0` 빌드 성공
- [ ] `GRID6x6_BRPL.csc` 실행 정상
- [ ] `CSV,BRPL_WEIGHT` 라인 출력 확인 (rpl-brpl.c 내부 로그)
- [ ] `CSV,BRPL_STATE` 라인 출력 확인 (큐 상태)
- [ ] `brpl_trust_get()` 기본값 1000 동작 확인 (패널티 없음)
- [ ] 혼잡 시 queue 기반 parent 변경이 RPL과 다른 패턴 보이는지 확인

### 검증 기준

```
BRPL과 RPL의 PDR 차이 < 2% (공격 없는 상태에서는 비슷해야 함)
혼잡 인위 발생 시 BRPL이 RPL보다 낮은 E2E delay 보임
```

---

## 3단계: attacker.c 결합

**목표:** "blackhole 공격 모델이 제대로 먹힌다"

### 구현 체크리스트

- [ ] `make -f Makefile.attacker TARGET=cooja WERROR=0` 빌드 성공
- [ ] 350s 이전: `CSV,FWD` dropped=0
- [ ] 350s 이후: dropped ≈ 100% of udp_to_root
- [ ] DIO/DAO/DIS는 드롭 없이 통과 (attacker.c의 `is_forwarded_udp_to_root()` 확인)
- [ ] 공격 노드가 DODAG에서 정상 부모로 선택되는지 확인 (RPL baseline에서)
- [ ] 공격 시작 직후 RPL PDR이 하락함을 확인

### 검증 기준

```
공격 전 PDR: ~95%
공격 후 RPL PDR: 공격 경로 비중에 따라 큰 폭 하락
CSV,ATTACK_ENABLED 로그 타임스탬프 ≈ 350s
```

## 3-1단계: sinkhole_attacker.c 결합

**목표:** "저랭크 DIO 광고로 parent 쏠림이 실제 발생한다"

### 구현 체크리스트

- [ ] `make -f Makefile.sinkhole_rpl TARGET=cooja WERROR=0` 빌드 성공
- [ ] `make -f Makefile.sinkhole_brpl TARGET=cooja WERROR=0` 빌드 성공
- [ ] 350s 이전: sinkhole 노드가 정상 rank로 동작
- [ ] 350s 이후: `CSV,SINKHOLE_DIO`가 주기적으로 출력
- [ ] 주변 노드의 `CSV,RPL_PARENT` 또는 `CSV,PARENT`가 node 18로 쏠리는지 확인
- [ ] sinkhole이 기존 sender 하나를 대체했는지 시나리오 파일에서 확인

### 검증 기준

```
CSV,ATTACK_ENABLED,18 타임스탬프 ≈ 350s
공격 활성화 이후 node 18 관련 parent 전환 이벤트 증가
```

---

## 4단계: TA-BRPL T_fwd only MVP

**목표:** "신뢰 기반 우회가 실제로 발생한다"

### 구현 범위

이 단계에서는 T_fwd만 활성화, T_ctrl/T_hon은 더미값(1.0) 사용.

```c
// 임시: T_ctrl = T_hon = 1.0
compute_t_ctrl() → return TA_TRUST_SCALE;
compute_t_hon()  → return TA_TRUST_SCALE;
aggregate_trust() → T_fwd^1.0 (다른 성분 무시)
```

### 구현 체크리스트

- [ ] `ta_trust_notify_sent(parent_id)` 호출 시 fwd_sent 증가 확인
- [ ] IP input hook에서 overhearing 감지 시 fwd_observed 증가 확인
- [ ] 150s 주기 업데이트 후 `CSV,TRUST` 라인 출력 확인
- [ ] 공격자 노드의 T_fwd가 350s 이후 감소하는지 확인
- [ ] `brpl_trust_get()` 오버라이드가 BRPL에 실제 반영되는지 확인 (`CSV,BRPL_TRUST` 확인)
- [ ] T_fwd 감소 후 parent change 발생 확인

### 검증 기준

```
공격자 T_fwd: 350s~450s 구간에서 0.8 → 0.5 이하로 하락
공격 후 100~200s 내에 parent change 이벤트 발생
우회 후 PDR 회복 확인
```

---

## 5단계: T_ctrl, T_hon 추가

**목표:** "3-성분 신뢰가 각각 독립 기여한다"

### 5a. T_ctrl 추가

- [ ] DIO IP hook에서 rank, version 파싱 정상 동작
- [ ] 정상 노드에서 T_ctrl ≈ 1.0 유지 확인
- [ ] rank anomaly 인위 주입 테스트 (Cooja CLI에서 rank 조작은 어려우므로 로그로 확인)

### 5b. T_hon 추가

- [ ] `ta_trust_notify_backlog()` 호출 경로 확인 (brpl-queue.h 연동)
- [ ] Q_est 추정 로직 정상 동작 확인
- [ ] 정상 혼잡 시 T_hon ≈ 1.0, 공격 + 큐 조작 시 T_hon 하락

### 5c. 가중 기하평균 통합

- [ ] `aggregate_trust()` = `pow(Tf, 0.5) * pow(Tc, 0.3) * pow(Th, 0.2) * 1000`
- [ ] `math.h pow()` 정상 링크 (`LDLIBS += -lm`)
- [ ] 세 성분 값 `CSV,TRUST` 출력 확인

---

## 6단계: EWMA + blacklist 완성

**목표:** "시간적 신뢰 업데이트 및 격리 정책이 동작한다"

### 6a. 비대칭 EWMA

```c
λ = (T_new < T_old) ? TA_TRUST_LAMBDA_DECREASE   // 0.2 (빠른 하락)
                    : TA_TRUST_LAMBDA_NORMAL;      // 0.7 (느린 회복)
T(t+1) = (λ × T(t) + (1000-λ) × T̃) / 1000
```

- [ ] 신뢰 하락 시 λ=0.2 적용 확인 (빠른 반응)
- [ ] 신뢰 회복 시 λ=0.7 적용 확인 (느린 복귀)

### 6b. blacklist 정책 구현

**확정된 정책:**

| 항목 | 결정 | 이유 |
|---|---|---|
| 격리 중 trust update | 계속 수행 | 회복 감지 위해 필요 |
| 격리 해제 조건 | 타임아웃(300s) + trust ≥ tau_black | 조기 해제 방지 |
| 해제 직후 부모 후보 복귀 | 즉시 (단, trust = tau_black로 설정) | 낮은 신뢰로 시작 |
| 유예시간 | 없음 (trust 값으로 자연 제어) | EWMA가 완충역할 |
| 반복 blacklist 시 duration | 고정 300s (1차 구현) | 추후 sensitivity로 검증 |

- [ ] `blacklist_until` 타임스탬프 로직 구현
- [ ] 격리 중 `ta_trust_is_parent_candidate()` → false
- [ ] `CSV,TRUST_BLACKLIST,<self>,<nbr>,reason=fwd|ctrl|hon` 출력
- [ ] `CSV,TRUST_UNBLACKLIST` 출력 (해제 시)
- [ ] 해제 후 `trust = tau_black` (350) 설정 확인

---

## 7단계: 로그 보강

**목표:** "논문 결과 추출 가능한 완전한 로그 체계"

### 추가할 CSV 타입

```c
// 1. 부모 변경 이벤트 (sender.c에 추가)
printf("CSV,PARENT_CHANGE,%u,%s,%s,%lu\n",
       id, old_parent_str, new_parent_str, (unsigned long)clock_time());

// 2. 신뢰 상태 전이 (ta-brpl-trust.c에 추가)
printf("CSV,TRUST_STATE,%u,%u,%s,%lu\n",
       self_id, nbr_id, status_str, (unsigned long)clock_time());
// status_str: "NORMAL" | "SUSPECT" | "UNTRUSTED" | "BLACKLISTED"

// 3. blacklist 사유 (ta-brpl-trust.c에 추가)
printf("CSV,TRUST_BLACKLIST,%u,%u,reason=%s,%lu\n",
       self_id, nbr_id, reason_str, (unsigned long)clock_time());
// reason_str: "fwd" | "ctrl" | "hon" | "combined"

// 4. 라우팅 회복 감지 (sender.c에 추가)
printf("CSV,RECOVERY,%u,%lu,%s\n",
       id, (unsigned long)clock_time(), new_parent_str);
```

### 기존 BRPL 내부 로그 활용 (이미 구현됨)

```
CSV,BRPL_STATE,<id>,<qx>,<qmax>,<q_avg>,<rho>,<theta>,<pmax>
CSV,BRPL_METRIC,<id>,<parent>,<link_metric>,<rank>,<p_tilde>
CSV,BRPL_WEIGHT,<id>,<parent>,<qx>,<qy>,<qmax>,<p_tilde>,<p_norm>,<dq_norm>,<theta>,<weight>
CSV,BRPL_TRUST,<id>,<parent>,<trust>,<trust_min>,<gamma>,<score>
CSV,BRPL_BEST,<id>,<p1>,<w1>,<p2>,<w2>,<best>
```

---

## 8단계: SMTrust 안정화

**전제 조건:** 7단계까지 완료, TA-BRPL 실험 결과 확인됨

### 주요 확인 항목

- [ ] smtrust.c 빌드 정상 (`GRID6x6_SMTRUST.csc`)
- [ ] RSSI 기반 TMLLS 정상 계산 (packetbuf_attr RSSI)
- [ ] DIO extension (0xFE 태그) 파싱 정상
- [ ] 6-성분 TrustIndex 가중합 정확도 확인
- [ ] rank attack 감지 (attacker가 rank를 조작하지 않으므로 이 기능은 미발동 예상)
- [ ] blackhole 감지 (TMSR < 0.5 → suspicious 플래그)

---

## 9단계: 30회 본실험 + 통계

**전제 조건:** 8단계까지 완료

```bash
./scripts/run_sweep.sh --protocols RPL,BRPL,SMTRUST,TABRPL --seeds 1-30 --jobs 4
```

- [ ] 120개 실험 전체 정상 완료
- [ ] `results/<PROTO>/<seed>/sim.log` 전체 존재
- [ ] `tools/parse_results.py`로 CSV 집계
- [ ] `scripts/analyze_results.R`로 통계 분석
- [ ] PDR / delay / parent_churn / trust_trace 그래프 생성

---

## 진행 상태 추적

| 단계 | 상태 | 비고 |
|---|---|---|
| 0. BRPL 비용함수 확정 | ✅ 완료 | γ=1, λ=500, 수식 문서화 |
| 1. RPL baseline | ✅ 빌드 성공 | 헤드리스 실행 미검증 |
| 2. BRPL 단독 | ✅ 빌드 성공 | 헤드리스 실행 미검증 |
| 3. attacker 결합 | ✅ 빌드 성공 | 헤드리스 실행 미검증 |
| 4. TA-BRPL T_fwd MVP | ✅ 빌드 성공 | 동작 검증 필요 |
| 5. T_ctrl + T_hon | ✅ 빌드 성공 | 컴포넌트별 검증 필요 |
| 6. EWMA + blacklist | ✅ 빌드 성공 | blacklist 정책 확정 완료 |
| 7. 로그 보강 | ⬜ 미완 | PARENT_CHANGE 등 추가 필요 |
| 8. SMTrust 안정화 | ✅ 빌드 성공 | 동작 검증 필요 |
| 9. 본실험 30회 | ⬜ 미완 | |
