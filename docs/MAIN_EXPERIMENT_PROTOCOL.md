# TA-BRPL 메인실험 프로토콜 (Locked Endpoints)

작성일: 2026-03-28  
목적: 메인실험 전에 "무엇을 성공으로 볼 것인지"를 고정해, 실험 후 해석 흔들림을 방지한다.

---

## 1) 논문 핵심 메시지 (고정)

본 연구의 메인 메시지는 다음으로 고정한다.

- TA-BRPL은 **attacker isolation**을 전 토폴로지에서 일관되게 달성한다.
- 그 과정에서 발생하는 churn 비용은 존재하나, 정책 조정(cooldown 등)으로 **bounded stability cost**로 관리한다.

즉 본 논문의 목표는

- `PDR 절대 우위`가 아니라
- `isolation-with-bounded-cost`이다.

---

## 2) 연구 목표 정의 (Primary Objective)

Primary Objective:
- 공격 상황에서 TA-BRPL이 BRPL 대비 공격자 의존도를 낮춘다.

Secondary Objective:
- isolation 개선이 과도한 churn/전달 손실로 붕괴하지 않도록 안정성 비용을 제한한다.

---

## 3) Endpoint 우선순위 (고정)

## 1순위 (Primary Endpoints)

- `att_share` (공격자 부모 경유 비율)
- `attacker exposure / hit_ratio` (공격자 의존 폭)

## 2순위 (Secondary Endpoint)

- `churn` (부모 교체 안정성 비용)

## 3순위 (Tertiary Endpoint)

- `PDR_dur` (공격 구간 전달 성능)

---

## 4) 시나리오별 해석 규칙 (고정)

## SINK_ONLY

- 해석 우선순위: `isolation > churn > PDR`
- 이유: drop이 없는 환경에서는 route capture 억제가 핵심.

## SINK_DROP50

- 해석 우선순위: `isolation + PDR` 동시 확인, 그 다음 churn
- 이유: capture가 availability 손실로 직접 연결되므로 PDR 방어를 함께 본다.

---

## 5) 성공 판정 기준 (메인실험)

메인실험에서는 아래를 동시에 본다.

- 필수 조건 A
- `att_share(TA-BRPL) < att_share(BRPL)`가 각 토폴로지/시나리오 셀에서 재현될 것.

- 필수 조건 B
- `hit_ratio` 또는 `exposure`가 BRPL 대비 악화되지 않을 것(최소 non-inferior).

- 비용 조건 C
- `churn`은 BRPL 대비 증가 가능하나, 정책 버전 간 비교에서 **단조 악화하지 않아야 함**.
- 동일 isolation 수준에서 churn이 낮아지는 방향을 우선 채택.

- 비용 조건 D
- `PDR_dur`는 SINK_DROP50에서 비열세(non-inferior) 또는 개선을 우선 채택.
- SINK_ONLY에서는 isolation 개선의 대가가 과도하지 않은지(큰 급락 없음) 확인.

---

## 6) 통계/리포팅 규칙

- 결과는 반드시 `절대값 + Δ(TA-BRPL - BRPL)` 동시 보고.
- 토폴로지/시나리오별 셀 결과를 먼저 제시하고, 그 다음 평균을 제시.
- 평균값만으로 주장하지 않는다.
- 가능하면 effect size와 seed 분산(`sd_*`)을 함께 보고한다.

---

## 7) 메인실험 실행 템플릿

- 매트릭스: `2 topo × 2 proto × 2 scenario × 5+ seeds`
- 실행: `scripts/run_sinkhole_sweep.sh`
- 파싱:
- `scripts/analyze_sinkhole_sweep.py`
- `scripts/analyze_admission_retention.py`
- `scripts/analyze_admission_gate.py`

---

## 8) 채택/기각 규칙 (버전 선택)

- 채택:
- Primary endpoint(`att_share`, `hit_ratio/exposure`) 개선이 토폴로지 전반에서 유지되고,
- churn/PDR 비용이 이전 후보보다 명확히 완화된 버전.

- 기각:
- isolation 개선이 불일관하거나,
- churn 감소를 위해 isolation을 잃는 버전.

---

## 9) 현재 기준 버전

- 현재 기준선(candidate): `v13.12`
- 근거:
- 전 셀 isolation 우위 유지
- v13.8 대비 BOTTLE churn 소폭 완화
- PDR_dur 소폭 개선

---

## 10) 랜덤 토폴로지 메인실험 설계

## 10.1 실험 단위

- 단위: `density × topology_seed × run_seed × protocol × scenario`
- protocol(메인): `BRPL`, `TABRPL`
- scenario(메인): `SINK_ONLY`, `SINK_DROP50`
- density: `sparse`, `medium`, `dense`

## 10.2 샘플링/반복 설계

- 파일럿 (빠른 검증)
- topology seed: 10개/density
- run seed: 3개/topology
- 총 실행: `3 density × 10 topo × 3 run × 2 proto × 2 scenario = 360 runs`

- 본실험 (메인)
- topology seed: 25개/density
- run seed: 5개/topology
- 총 실행: `3 × 25 × 5 × 2 × 2 = 1500 runs`

참고: 시간 제약이 크면 본실험을 `20×4`로 축소(960 runs)하되, 파일럿을 통해 분산 안정성을 먼저 확인한다.

## 10.3 통계 단위 (중요)

- 같은 topology에서 run seed 반복은 먼저 평균낸다.
- 통계 검정 단위는 run이 아니라 `topology 평균`이다.
- 즉 pseudo-replication을 피하기 위해 per-topology paired 비교를 사용한다.

## 10.4 성공 판정 (랜덤 토폴로지용)

- Primary 성공:
- density별/전체에서 `median(Δatt_share) < 0` 및 95% CI 상한 < 0
- density별/전체에서 `median(Δhit_ratio or exposure) <= 0`

- Secondary 성공:
- `Δchurn`은 양수 허용, 단 사전 상한(cap) 이하
- cap 기본값: `+1.0` (필요 시 파일럿 분산으로 조정)

- Tertiary 성공:
- `SINK_DROP50`에서 `ΔPDR_dur` non-inferior (기본 마진 -0.02)

## 10.5 리포팅 포맷 (필수)

- density별 표 + 전체 표를 분리
- `absolute + Δ(TA-BRPL - BRPL)` 동시 보고
- win-rate(토폴로지 승률) 보고
- 검정: paired Wilcoxon + bootstrap CI

## 10.6 실행 프로토콜

- 현재 구현으로 가능한 파일럿(단일 attack profile 랜덤 스윕):
```bash
scripts/run_random_topo_sweep.sh \
  --protocols BRPL,TABRPL \
  --densities sparse,medium,dense \
  --topology-seeds 1-10 \
  --run-seeds 1-3 \
  --jobs 12 \
  --results-dir results/random_topo_pilot_v1 \
  --rerun
```

- 메인실험 전 사전 작업(필수):
- 현재 `generate_random_topologies.py`는 `GRID6x6_<PROTO>.csc` 단일 템플릿 기반이므로,
  `SINK_ONLY/SINK_DROP50` 축을 포함한 scenario-aware random generator/runner로 확장해야 한다.
- 확장 후 본실험은 위 매트릭스(1500 runs)를 동일 방식으로 실행한다.

## 10.7 실험 직후 자동 산출물 생성

랜덤 토폴로지 실험이 끝나면, 아래 한 번으로
`CSV 요약 + Figure(4종) + 논문 삽입용 .tex snippet`을 생성한다.

```bash
python3 docs/paper/generate_main_experiment_artifacts.py \
  --results-dir results/random_topo_main_v1 \
  --proto-a TABRPL \
  --proto-b BRPL \
  --fig-dir docs/paper/figures/new/main \
  --out-dir docs/paper/generated/main
```

생성 파일:
- `docs/paper/generated/main/main_results_auto.tex`
- `docs/paper/generated/main/summary_by_density.csv`
- `docs/paper/figures/new/main/fig3_att_share_box_by_density.pdf`
- `docs/paper/figures/new/main/fig4_delta_ci.pdf`
- `docs/paper/figures/new/main/fig5_pdr_noninferiority.pdf`
- `docs/paper/figures/new/main/fig6_winrate_heatmap.pdf`

그 다음 논문 PDF 업데이트:

```bash
cd docs/paper
latexmk -pdf -interaction=nonstopmode paper.tex
```
