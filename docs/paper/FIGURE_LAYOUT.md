# Final Figure Layout (Paper Draft)

## Main 8 Figures

1. `fig1_ta_brpl_architecture.svg`
   - TA-BRPL architecture (BRPL + trust engine + trust penalty + blacklist)
2. `fig2_attack_model.svg`
   - Combined attack model (sinkhole rank/ETX manipulation + grayhole drop)
3. `fig3_topologies_medium.svg`
   - Cluster / Grid / Ring medium-scale topologies
4. `fig4_pdr_no_attack.png`
   - No-attack fairness (RPL, BRPL, TA-BRPL)
5. `fig5_pdr_vs_attack_cluster.png`
   - PDR vs attack rate (Cluster)
6. `fig6_pdr_vs_attack_grid.png`
   - PDR vs attack rate (Grid)
7. `fig7_pdr_vs_attack_ring.png`
   - PDR vs attack rate (Ring)
8. `fig8_attacker_exposure.png`
   - Attacker exposure (% nodes using attacker as parent), BRPL vs TA-BRPL

## Optional / Supplementary

- `fig6_alt_trust_effect_delta.png`
  - Trust ON/OFF delta: ΔPDR = PDR(TA-BRPL) - PDR(BRPL)
- `fig8_alt_trust_blacklist_dynamics.png`
  - Trust score trajectory and blacklist-threshold crossing
- `table_attack_pdr_summary.csv`
  - Attack-rate/topology/method summary table

## Regeneration

```bash
docs/paper/scripts/build_all.sh \
  results/experiments-20260305-174246/parsed_quick/runs_pdr.csv \
  docs/paper/figures
```
