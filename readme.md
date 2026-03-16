# TA-BRPL

Reference repository for evaluating `TA-BRPL` against `RPL`, `BRPL`, and `SMTRUST` in Contiki-NG/Cooja under a combined `blackhole + sinkhole` attack setting.

## Overview

- Topology: `6 x 6` grid
- Protocols: `RPL`, `BRPL`, `SMTRUST`, `TABRPL`
- Attack setting: `3` blackholes + `1` sinkhole
- Seeds: `30`
- Main outputs: parsed CSV summaries and publication-style PDF figures

## Reproducibility

Run the full sweep:

```bash
./scripts/run_sweep.sh --jobs 8 --rerun
```

Parse the logs:

```bash
python3 scripts/parse_results.py
```

Generate the figures:

```bash
Rscript scripts/plot_main_figures.R
```

For a short sanity check:

```bash
./scripts/run_sweep.sh --protocols RPL,SMTRUST --seeds 1-5 --jobs 4 --rerun
python3 scripts/parse_results.py
```

## Repository Layout

- [configs/scenarios](/home/dev/TA-BRPL/configs/scenarios): Cooja scenarios
- [motes](/home/dev/TA-BRPL/motes): sender, receiver, attacker, and trust logic
- [scripts/run_sweep.sh](/home/dev/TA-BRPL/scripts/run_sweep.sh): queued parallel sweep runner
- [scripts/parse_results.py](/home/dev/TA-BRPL/scripts/parse_results.py): log parser
- [scripts/plot_main_figures.R](/home/dev/TA-BRPL/scripts/plot_main_figures.R): main paper figures
- [results](/home/dev/TA-BRPL/results): parsed result tables
- [figures](/home/dev/TA-BRPL/figures): rendered figures

## Main Result Files

- [pdr_summary.csv](/home/dev/TA-BRPL/results/pdr_summary.csv)
- [delay_summary.csv](/home/dev/TA-BRPL/results/delay_summary.csv)
- [trust_trace.csv](/home/dev/TA-BRPL/results/trust_trace.csv)
- [parent_churn.csv](/home/dev/TA-BRPL/results/parent_churn.csv)
- [route_trace.csv](/home/dev/TA-BRPL/results/route_trace.csv)

## Main Figures

- `fig1_pdr_distribution.pdf`
- `fig2_resilience_summary.pdf`
- `fig3_attack_tradeoff.pdf`
- `fig4_route_exposure_timeseries.pdf`
- `fig5_tabrpl_trust_adversaries.pdf`
- `fig6_churn_hotspots.pdf`

## Notes

- Attack start time: `350 s`
- Default workflow: `run_sweep -> parse_results -> plot_main_figures`
- The repository currently reflects the combined-attack experimental setup used in the paper workflow

## Documentation

- [agent/experiment.md](/home/dev/TA-BRPL/agent/experiment.md)
- [agent/model.md](/home/dev/TA-BRPL/agent/model.md)
- [agent/SMTrust.md](/home/dev/TA-BRPL/agent/SMTrust.md)
- [docs/ARCHITECTURE.md](/home/dev/TA-BRPL/docs/ARCHITECTURE.md)
