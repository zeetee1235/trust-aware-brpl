## results_parser

Rust parser for TA-BRPL experiment outputs.

### Build

```bash
cd tools/results_parser
cargo build --release
```

### Run

```bash
tools/results_parser/target/release/results_parser \
  --input results/experiments-20260305-104252 \
  --output-dir results/experiments-20260305-104252/parsed
```

Outputs:
- `runs.csv`: one row per run directory (metadata + parsed metrics)
- `summary.csv`: grouped mean table for quick scans

### Plot figures (R)

```bash
Rscript scripts/plot_sweep_figures.R \
  results/experiments-20260305-104252/parsed/runs.csv \
  docs/report/sweep
```

### PDR-centered sweep figures

1) Attach PDR to `runs.csv` (this parses each `logs/COOJA.testlog`, so it can take time on large datasets):

```bash
python3 scripts/attach_pdr.py \
  --runs-csv results/experiments-20260305-104252/parsed/runs.csv \
  --output results/experiments-20260305-104252/parsed/runs_pdr.csv \
  --workers 1 \
  --only-attack
```

2) Generate PDR figures by trust on/off, topology, attack mode, and parameter sweeps:

```bash
Rscript scripts/plot_pdr_sweep_figures.R \
  results/experiments-20260305-104252/parsed/runs_pdr.csv \
  docs/report/pdr_sweep
```

Quick smoke test (small subset):

```bash
python3 scripts/attach_pdr.py \
  --runs-csv results/experiments-20260305-104252/parsed/runs.csv \
  --output results/experiments-20260305-104252/parsed/runs_pdr_sample.csv \
  --workers 1 --only-attack --limit 20

Rscript scripts/plot_pdr_sweep_figures.R \
  results/experiments-20260305-104252/parsed/runs_pdr_sample.csv \
  docs/report/pdr_sweep_sample
```
