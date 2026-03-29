# TA-BRPL SCI 보강 실행안 (main_ko 동기화판)

작성일: 2026-03-30

## 0. 한 줄 진단

지금 원고는 이미 “좋은 내부 보고서”를 넘었고, SCI 투고 가능한 구조를 갖췄다.
남은 과제는 **아이디어 추가**가 아니라 **검증 깊이와 증거 표현력 강화**다.

---

## 1. 현재 상태 (무엇이 이미 반영됐는가)

아래 항목은 `docs/paper/main_ko.tex`에 이미 반영되어 있다.

- 공격 개념도(Figure): pre-attack → route capture → selective drop → TA-BRPL 완화
- TA-BRPL 아키텍처(Figure): `T_fwd`, `T_ctrl`, `T_hon` → 집계 → EWMA → gate → BRPL penalty
- Main Claim 박스: “attacker dependency 감소 + PDR 비열세”
- 수식 정식화:
  - 가중 기하평균 집계
  - 비대칭 EWMA 갱신
  - BRPL 점수 반영식(신뢰 penalty)
- Algorithm 1(게이트 의사코드): admission/dwell/margin 순차 적용
- 공격 단계 시계열 Figure: “att_share가 PDR보다 먼저 반응”
- 4-way 파이프라인 스냅샷 표(RPL/BRPL/SMTRUST/TABRPL)
- 코드 기준 공격 스케줄 정정(650~900은 오프가 아니라 공격 후반 관측창)

즉, 핵심 뼈대는 갖춰졌다.

---

## 2. 아직 남은 SCI 리스크 (핵심 4개)

### R1. 4-way 비교가 아직 “완결”이 아님

- 현재 `results/random_topo_drop_sweep_baseline4/summary/snapshot.md` 기준으로 drop=0 일부만 진행됨
- 상태: `370 / 1500` (drop=0), 나머지 drop는 미진행

리뷰어 관점에서 이는 “프레임은 맞지만, 일반화 증거는 진행 중” 상태다.

### R2. 메커니즘 증거가 결과표 대비 약함

현재는 성능 지표 중심이다. 아래 분해 지표가 추가되어야 인과가 강해진다.

- `new_attacker_adoption_rate`
- `attacker_parent_retention_time`
- `escape_latency_after_attack`
- `attacker_reentry_count`

### R3. Robustness 축이 본문에서 충분히 닫히지 않음

최소 3축은 본문 본실험으로 반드시 닫아야 한다.

- drop sweep: 25/50/75/100
- loss sweep: 10/30/50/70
- attacker multiplicity: 1/2/3

### R4. 오버헤드 지표 부재

LLN/WSN 리뷰에서 거의 반드시 묻는 항목이다.

- control overhead(DIO/DAO/DIS)
- route repair frequency
- parent-switch overhead

---

## 3. Figure/Table 임팩트 패키지 (최종 제출용)

아래 5개는 본문 임팩트 최소 세트다.

### F1. 공격 개념도 (필수)

메시지: “핵심은 탐지 강화가 아니라 route capture 억제다.”

### F2. TA-BRPL 파이프라인 (필수)

메시지: “신뢰 계산이 아니라 decision stabilization 설계다.”

### F3. 공격 단계 시계열 (필수)

메시지: “att_share 선행 상승 → PDR 후행 하락”

### F4. 메인 결과 분포(Box/Violin) (필수)

패널: `Δatt_share`, `Δhit_ratio`, `ΔPDR_dur`, `Δchurn`

메시지: 평균이 아니라 분포 전체 이동을 보여준다.

### F5. 밀도별 층화 결과 (권장)

메시지: “중밀도에서 효과 극대, 저밀도는 비용 hotspot.”

---

## 4. 방법론 엄밀화 템플릿 (본문 수식 고정본)

### 4.1 Trust aggregation

$$
T_{agg}(v,t)=T_{fwd}(v,t)^{w_f}\cdot T_{ctrl}(v,t)^{w_c}\cdot T_{hon}(v,t)^{w_h},\quad
w_f+w_c+w_h=1
$$

권장 본문 문장:

> 기하평균은 단일 신호의 과대값으로 전체 점수가 왜곡되는 문제를 줄여, 단일 신호 gaming에 대해 산술평균보다 보수적이다.

### 4.2 Asymmetric EWMA

$$
\hat{T}^{(t+1)}(v)=
\begin{cases}
\lambda_{down}\hat{T}^{(t)}(v)+(1-\lambda_{down})T_{agg}(v,t), & T_{agg}(v,t)<\hat{T}^{(t)}(v)\\
\lambda_{up}\hat{T}^{(t)}(v)+(1-\lambda_{up})T_{agg}(v,t), & \text{otherwise}
\end{cases}
$$

권장 해석 문장:

> 설계 의도는 “빠른 악화 반영, 느린 회복 확인”이며, 일시적 링크 변동에 대한 과잉 반응을 줄인다.

### 4.3 BRPL 통합 penalty

$$
S'_{TA}(v)=S_{BRPL}(v)\cdot\frac{t(v)}{1+\lambda_p(1-t(v))},\quad t(v)=\hat{T}(v)/1000
$$

$$
S_{TA}(v)=S'_{TA}(v)\cdot\eta_{val}(v)\cdot\eta_{policy}(v)\cdot\eta_{sticky}(v)
$$

권장 해석 문장:

> TA-BRPL은 신뢰를 별도 탐지 경보가 아닌 부모 선택 비용에 직접 결합해, 관찰-판단-전환의 지연 불일치를 줄인다.

---

## 5. Baseline 포지셔닝 고정 프레임

본문에서 baseline은 반드시 아래 3축으로 설명한다.

- Standard baseline: `RPL (MRHOF+ETX)`
- Congestion-aware baseline: `BRPL`
- Trust-aware/security baseline: `SMTRUST`(또는 동급 trust-RPL)

권장 주장 구조:

- RPL 대비: 공격자 의존도 저감
- BRPL 대비: route capture 억제
- SMTRUST 대비: 안정성/실용성 trade-off 우위

주의: 4-way 결과가 완결되기 전에는 “최종 우열” 표현 금지, “pipeline-verified ongoing”으로 제한.

---

## 6. 메인 실험 전 짧은 검증 게이트 (권장 운영안)

목적: 메인 전수 실행 전에 “파이프라인 이상 없음”만 빠르게 증명.

### Gate-A: 4-way 짧은 precheck

```bash
bash scripts/run_random_topo_drop_precheck.sh \
  --topology-seeds 1-3 \
  --run-seeds 1-2 \
  --drops 0,25,50,75,100 \
  --jobs 12 \
  --results-root results/random_topo_drop_precheck_short
```

PASS 조건:

- drop별 `done == expected`
- `sim.log` 존재율 100%
- log 내 `drop_pct` 태그 불일치 0건

### Gate-B: 스냅샷 보고서 자동 생성

```bash
python3 scripts/summarize_random_topo_drop_sweep.py \
  --results-root results/random_topo_drop_precheck_short \
  --expected-jobs 72 \
  --drops 0,25,50,75,100
```

### Gate-C: 본실험 착수

Gate-A/B 모두 PASS일 때만 메인 랜덤 토폴로지 전수 실행 시작.

---

## 7. Results 문장 톤 (SCI형 템플릿)

### 7.1 메인 주장 시작 문장

> Across topology-paired comparisons, TA-BRPL significantly reduced attacker dependency while preserving PDR non-inferiority under a pre-specified margin of \(-0.02\).

### 7.2 churn 해석 문장

`bounded churn` 대신 아래 표현 권장:

> controlled stability overhead relative to the achieved isolation gains

또는

> acceptable churn overhead under the prioritized isolation objective

### 7.3 메커니즘 결론 문장

> The primary gain arises from stabilizing trust-to-routing decisions (admission, retention, and re-entry control), rather than from merely increasing trust sensitivity.

---

## 8. 다음 작업 우선순위 (실행용)

### P1 (반드시)

- 4-way + drop sweep 완결
- Ablation 최소 5종
  - Full
  - w/o `T_ctrl`
  - w/o `T_hon`
  - w/o re-entry hold
  - w/o recent-switch control
- mechanism 지표 4종 추가

### P2 (강추)

- robustness 3축(loss/drop/attacker count)
- sparse 원인 분석(degree/path length/candidate parents vs churn)

### P3 (있으면 매우 강함)

- 오버헤드 지표(control packet, repair, switch overhead)
- artifact 공개 패키지(코드/로그/집계/재실행 스크립트)

---

## 9. 최종 결론

이 프로젝트는 “아이디어 부족” 단계가 아니다.
현재 병목은 **검증의 깊이**와 **증거의 시각적 전달력**이다.

따라서 지금의 최적 전략은 프로토콜을 더 복잡하게 만드는 것이 아니라,
**왜 좋아졌는지 / 어디까지 유지되는지 / 어디서 깨지는지**를 실험적으로 닫는 것이다.
