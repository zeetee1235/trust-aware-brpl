# GRID5 Quick Sweep Summary (2026-03-28)

Condition: random-topology quick preview, `density=medium`, `topology-seeds=1-5`, `run-seeds=1-3`, protocols=`BRPL,TABRPL` (30 runs per setting).

## 1) Re-entry Hold Sweep (`TA_TRUST_ATT_REENTRY_HOLD_SECONDS`)

| hold | Δatt_share | Δhit_ratio | Δchurn | ΔPDR_dur | Δatt_entries/node | wins(att_entries) | ATT_REENTRY_HOLD_HIT | ATT_REENTRY_GUARD_BLOCK |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 300 | +0.0032 | +0.0167 | +0.162 | -0.1083 | +0.0083 | 0/5 | 6657 | 0 |
| 600 | +0.0032 | +0.0167 | +0.167 | -0.1022 | +0.0083 | 0/5 | 8034 | 0 |
| 900 | +0.0032 | +0.0167 | +0.167 | -0.1022 | +0.0083 | 0/5 | 8676 | 0 |

Observation: hold 변경만으로 attacker isolation 지표가 개선되지 않았고, `ATT_REENTRY_GUARD_BLOCK`은 전 설정에서 0회였다.

## 2) NN Margin Sweep (`TA_TRUST_NN_EXTRA_MARGIN`, ATT_HOLD=600)

| nn_margin | Δatt_share | Δhit_ratio | Δchurn | ΔPDR_dur | Δatt_entries/node | wins(att_entries) |
|---:|---:|---:|---:|---:|---:|---:|
| 260 | +0.0032 | +0.0167 | +0.167 | -0.1022 | +0.0083 | 0/5 |
| 350 | +0.0032 | +0.0167 | +0.167 | -0.1022 | +0.0083 | 0/5 |
| 450 | +0.0032 | +0.0167 | +0.167 | -0.1022 | +0.0083 | 0/5 |

Observation: NN margin sweep도 GRID5 preview에서는 isolation/churn 지표를 유의미하게 움직이지 못했다.

## 3) Immediate implication

- 현재 두 축(hold, nn_margin)은 **감도 부족** 또는 **의사결정 분기 미발동** 상태다.
- 다음 실험 타깃은 threshold sweep보다 `ATT_REENTRY_GUARD_BLOCK`이 실제 발동되도록 하는 조건식 점검(분기 조건/예외 경로)이다.