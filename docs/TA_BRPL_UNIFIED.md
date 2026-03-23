# TA-BRPL 통합 문서

이 문서는 `docs/` 하위 기존 분산 문서(아키텍처, 실험 계획, 구현 계획, 리스크, 검증 계획, 튜닝 TODO)를 하나로 통합한 단일 기준 문서다.

## 1. 프로젝트 개요

TA-BRPL은 Contiki-NG/Cooja 기반 LLN 환경에서, BRPL(Backpressure RPL)에 신뢰 모델을 결합해 blackhole/sinkhole 공격에 대한 복원력을 높이는 연구 플랫폼이다.

핵심 목표:
- 공격자 경유율 감소
- 공격 구간(during) 및 회복 구간(recovery) PDR 개선
- 혼잡 인식(BRPL 장점) 유지
- 계산 복잡도 O(1) 유지

---

## 2. 시스템 구성

주요 코드:
- `motes/sender.c`: 송신 노드 애플리케이션/로그
- `motes/receiver_root.c`: 루트 수신/집계
- `motes/attacker.c`: blackhole 공격자
- `motes/sinkhole_attacker.c`: sinkhole 공격자
- `motes/ta-brpl-trust.c`: TA-BRPL 신뢰/검증 엔진
- `motes/smtrust.c`: SMTrust 엔진
- `contiki-ng-brpl/os/net/routing/rpl-classic/rpl-brpl.c`: BRPL OF(parent 선택 핵심)
- `project-conf.h`: 실험/프로토콜 상수 단일 설정점
- `scripts/run_sweep.sh`: 대량 재실험(병렬 worker)
- `scripts/parse_results.py`: 결과 파싱(`pdr_summary.csv`, `route_trace.csv`, `parent_churn.csv` 등)

---

## 3. 프로토콜 모델 상세

### 3.1 RPL (Baseline)

- Objective Function: MRHOF
- 신뢰 모델 없음
- 부모 선택은 경로/링크 메트릭 중심

특징:
- 구조가 단순해 churn이 낮은 편
- 공격자 우회 메커니즘이 없어 공격 경로에 걸리면 PDR 하락

### 3.2 BRPL

- Objective Function: `rpl_brpl`
- 큐 기반 backpressure를 이용해 혼잡 회피
- 기본적으로 신뢰 훅은 weak symbol로 비활성(중립값)

기본 가중치(개념):
- `weight_base = f(path_cost, queue_gradient, theta)`
- 낮은 weight가 더 좋은 후보

### 3.3 SMTrust

가중합 TrustIndex:
- `TrustIndex = w1*TMSR + w2*TM(H0) + w3*TMEL + w4*TMLLS + w5*TMMobility + w6*TMRT`

주요 파라미터(코드 기준):
- `SMTRUST_W1..W6` (합 1.0)
- `SMTRUST_THRESHOLD`
- `SMTRUST_SUCCESS_THRESHOLD`

특징:
- 신뢰 성분이 풍부하지만 계산/모델링 복잡성 큼
- 본 프로젝트 비교군으로 유지

### 3.4 TA-BRPL (핵심)

TA-BRPL은 BRPL 선택식에 trust penalty를 결합한다.

#### (A) 신뢰 모델(Trust Model)

성분:
- `T_fwd`: 데이터 평면 포워딩 신뢰
- `T_ctrl`: 제어 평면 일관성 신뢰
- `T_hon`: 큐/행동 정직성 신뢰

결합:
- `T_agg = T_fwd^(w_fwd) * T_ctrl^(w_ctrl) * T_hon^(w_hon)`
- 현재 가중치: `w_fwd=0.5, w_ctrl=0.3, w_hon=0.2`

EWMA:
- `T(t+1)=lambda*T(t)+(1-lambda)*T_obs`
- 하락 시 더 빠른 람다(비대칭)로 반응

현재 주요 임계값(`project-conf.h` 우선):
- `TA_TRUST_TAU_WARN=600`
- `TA_TRUST_TAU_JOIN=350`
- `TA_TRUST_TAU_BLACK=200`
- `TA_TRUST_UPDATE_INTERVAL=60s`

#### (B) 검증 모델(Validation Model)

역할:
- 하드 블랙리스트(배제) 결정을 신중하게 수행
- 신뢰모델과 분리된 보수적 판정 계층

현재 구현 포인트:
- review score / bad window 누적
- 최소 관측 조건 충족 시에만 승급
- 블랙리스트는 검증 증거 또는 강한 `trust_fwd` 연속 저하에서 발동

#### (C) BRPL 결합

`rpl-brpl.c`에서 parent별 최종 score 계산 시 trust penalty 반영:
- `score = apply_trust_penalty(weight_base, parent)`
- validation 상태 훅(`brpl_validation_penalty_scale_get`) 반영 가능

하드 제외:
- `brpl_trust_parent_allowed(node_id)==0`이면 후보 제외
- 단, 후보 전부 제외 시 dead-end 방지를 위한 fallback 유지

---

## 4. Parent 선택식 구조 (최신)

검증모델은 유지하고, 선택식만 안정화한 변경이 반영되어 있다.

### 4.1 A1: Switch Margin Gate

의도:
- 현재 preferred parent에서 새 후보로 바꿀 때, 미세한 이득으로는 전환하지 않음

조건:
- 절대 개선폭: `BRPL_CONF_SWITCH_MARGIN_ABS=45`
- 상대 개선폭: `BRPL_CONF_SWITCH_MARGIN_PPM=110` (11%)
- 둘 중 하나를 만족해야 switch 허용

효과:
- 불필요한 parent flapping 감소
- 공격 구간에도 의미 있는 우회만 허용

### 4.2 A2/A3: Dwell Time Gate

의도:
- 방금 바꾼 parent를 즉시 다시 바꾸지 않도록 최소 유지시간 보장

현재 설정:
- `BRPL_CONF_PARENT_DWELL_SECONDS=75`

예외:
- preferred parent가 허용 불가(하드 배제 등)면 dwell 차단 완화

로그:
- `CSV,BRPL_SWITCH_GATE`
- `CSV,BRPL_DWELL_GATE`

---

## 5. 실험 설정

공통:
- 토폴로지: 6x6 GRID (36 nodes)
- 공격 시작: 350s
- phase:
  - pre: 150~350s
  - during: 350~650s
  - recovery: 650~900s
- 반복: seed sweep (빠른 검증 10, 본 검증 30)
- 병렬 실행: `run_sweep.sh --jobs 12`

파싱 산출:
- `pdr_summary.csv`
- `route_trace.csv`
- `parent_churn.csv`
- `trust_trace.csv`

---

## 6. 최신 성능 요약 (선택식 구조 개선 이후)

기준선(구성 변경 전 TA-BRPL, 30 seed):
- pre `0.9995`, during `0.8424`, recovery `0.8434`

A1+A2+A3 + 최신 튜닝(현재, 30 seed):
- pre `0.9999`
- during `0.8892`
- recovery `0.8809`
- during attacker ratio `0.1111`
- recovery attacker ratio `0.1174`
- during churn `0.1591`
- recovery churn `0.1978`

동일 재실험 비교군(평균 PDR):
- RPL `0.9997 / 0.8726 / 0.8690` (pre/during/recovery)
- BRPL `1.0000 / 0.8820 / 0.8702`
- SMTrust `1.0000 / 0.8693 / 0.8610` (유효 21 seed)

해석:
- 선택식 안정화(110/45 margin, dwell 75s)로 공격자 노출을 줄이면서 during PDR을 추가 개선
- 현재 `during`은 RPL/SMTrust 대비 우위(유효 seed 기준), `recovery`는 0.88대로 추가 개선 여지 존재

---

## 7. 계산 복잡도/O(1) 보장

핵심 원칙:
- parent 비교 및 패널티 적용은 상수 시간 연산만 수행
- trust 엔트리 조회는 direct-map 기반 O(1)
- per-packet 경로에서 선형 탐색/동적 할당 추가 금지

현재 추가된 게이트들:
- switch margin 비교: O(1)
- dwell 판정: O(1)

---

## 8. 리스크와 한계

1) 시뮬레이터 의존성:
- UDGM 환경은 실제 무선 손실/간섭을 단순화

2) 공격 범위 제한:
- 현재 blackhole/sinkhole 중심
- collusion, Sybil, version attack은 후속 확장 필요

3) 목표 미달 구간:
- 현재 0.88대까지 개선됐지만 0.9+ 달성을 위해 추가 결정 규칙 필요

---

## 9. 다음 단계 제안

우선순위 1:
- `recovery > 0.9` 목표를 위한 phase-aware switch margin/dwell 미세 튜닝
- 검증모델 게이트는 유지하고 선택식 파라미터만 조정

우선순위 2:
- sinkhole 인접 구간에서의 escape trigger 지연(오탐 억제) vs 우회 속도 균형점 탐색

우선순위 3:
- trust-adaptive switch margin

---

## 10. 재현 명령어

빌드:
```bash
make -C motes -f Makefile.tabrpl
```

빠른 검증(10 seed, 12 worker):
```bash
./scripts/run_sweep.sh --protocols TABRPL --seeds 1-10 --jobs 12 --rerun
python3 scripts/parse_results.py
```

본 검증(30 seed, 12 worker):
```bash
./scripts/run_sweep.sh --protocols TABRPL --seeds 1-30 --jobs 12 --rerun
python3 scripts/parse_results.py
```

---

## 11. 문서 관리 규칙

- 본 파일(`docs/TA_BRPL_UNIFIED.md`)을 단일 기준 문서로 사용
- 아키텍처/실험/리스크/검증/튜닝 이력은 이 문서에 지속 갱신
- `project-conf.h`를 상수의 단일 진실 소스로 유지
