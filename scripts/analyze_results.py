#!/usr/bin/env python3
"""analyze_results.py — Statistical summary and Wilcoxon tests for TA-BRPL paper.

Reads pdr_summary.csv and prints:
  - Mean ± 95%CI per protocol × phase
  - Wilcoxon rank-sum test: TABRPL vs each other protocol (attack phase)
  - Effect size (rank-biserial correlation)
"""

from pathlib import Path
import csv
import statistics
import math

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
PROTOCOLS   = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
PHASES      = ["pre_attack", "during_attack", "recovery"]

try:
    from scipy.stats import ranksums
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("[WARNING] scipy not available — skipping Wilcoxon tests")


def ci95(vals: list) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    return 1.96 * statistics.stdev(vals) / math.sqrt(n)


def rank_biserial(x: list, y: list) -> float:
    """Rank-biserial correlation as effect size for Wilcoxon rank-sum."""
    nx, ny = len(x), len(y)
    # U statistic via counting
    u = sum(1 for xi in x for yi in y if xi > yi) + \
        0.5 * sum(1 for xi in x for yi in y if xi == yi)
    return 1 - 2 * u / (nx * ny)


def load_pdr() -> dict:
    path = RESULTS_DIR / "pdr_summary.csv"
    data = {p: {ph: [] for ph in PHASES} for p in PROTOCOLS}
    with open(path) as f:
        for row in csv.DictReader(f):
            proto = row["protocol"]
            if proto not in data:
                continue
            for ph in PHASES:
                col = f"pdr_{ph}"
                if col in row and row[col]:
                    try:
                        data[proto][ph].append(float(row[col]))
                    except ValueError:
                        pass
    return data


def main():
    print("=" * 72)
    print("TA-BRPL Statistical Analysis")
    print("=" * 72)

    data = load_pdr()

    # Table: Mean ± 95%CI
    print("\nTable 1: PDR by protocol and phase (mean ± 95% CI)")
    print(f"{'Protocol':<10} {'N':>4}  "
          f"{'Pre-attack':>16}  {'During attack':>16}  {'Recovery':>16}")
    print("-" * 72)
    for proto in PROTOCOLS:
        n = len(data[proto]["during_attack"])
        cells = []
        for ph in PHASES:
            vals = data[proto][ph]
            if vals:
                m = statistics.mean(vals) * 100
                e = ci95(vals) * 100
                cells.append(f"{m:5.2f} ± {e:4.2f}%")
            else:
                cells.append("      n/a      ")
        print(f"{proto:<10} {n:>4}  {'  '.join(cells)}")

    # Wilcoxon tests: TABRPL vs others (during_attack)
    print("\n\nTable 2: Wilcoxon rank-sum test — TABRPL vs others (during attack phase)")
    print(f"{'Comparison':<20}  {'n_A':>5}  {'n_B':>5}  {'W-stat':>10}  {'p-value':>10}  {'r_rb':>8}  {'Sig?':>6}")
    print("-" * 72)

    tabrpl_vals = data["TABRPL"]["during_attack"]
    for other in ["RPL", "BRPL", "SMTRUST"]:
        other_vals = data[other]["during_attack"]
        if not tabrpl_vals or not other_vals:
            print(f"TABRPL vs {other:<10}  — insufficient data")
            continue
        label = f"TABRPL vs {other}"
        if HAS_SCIPY:
            stat, pval = ranksums(tabrpl_vals, other_vals)
            rb = rank_biserial(tabrpl_vals, other_vals)
            sig = "***" if pval < 0.001 else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "n.s."))
            print(f"{label:<20}  {len(tabrpl_vals):>5}  {len(other_vals):>5}  {stat:>10.3f}  {pval:>10.4f}  {rb:>8.3f}  {sig:>6}")
        else:
            print(f"{label:<20}  {len(tabrpl_vals):>5}  {len(other_vals):>5}  (scipy required)")

    # Quick summary
    print("\n\nSummary — mean PDR during attack:")
    for proto in PROTOCOLS:
        vals = data[proto]["during_attack"]
        if vals:
            print(f"  {proto:<9}: {statistics.mean(vals)*100:.2f}% (n={len(vals)})")

    # Check if TABRPL > BRPL
    tb = data["TABRPL"]["during_attack"]
    br = data["BRPL"]["during_attack"]
    if tb and br:
        delta = (statistics.mean(tb) - statistics.mean(br)) * 100
        print(f"\n  TABRPL - BRPL improvement: {delta:+.2f} percentage points during attack")
        delta_r = (statistics.mean(tb) - statistics.mean(data["RPL"]["during_attack"])) * 100
        print(f"  TABRPL - RPL  improvement: {delta_r:+.2f} percentage points during attack")


if __name__ == "__main__":
    main()
