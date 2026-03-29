#!/usr/bin/env python3
"""Summarize random-topology drop-sweep progress and partial metrics.

Expected directory layout:
  <results-root>/drop_000
  <results-root>/drop_025
  ...

For each drop directory, this script reports:
  - done/sim.log counts (progress)
  - protocol-level means (when logs exist), using summarize_security_axes.py logic
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from summarize_security_axes import summarize


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize random-topology drop sweep status/results.")
    ap.add_argument(
        "--results-root",
        required=True,
        help="Root directory containing drop_* result folders.",
    )
    ap.add_argument(
        "--expected-jobs",
        type=int,
        default=1500,
        help="Expected number of jobs per drop. Used for progress ratio.",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Default: <results-root>/summary",
    )
    ap.add_argument(
        "--drops",
        default="0,25,50,75,100",
        help="Comma-separated drop list to report even if directories are missing.",
    )
    args = ap.parse_args()

    results_root = Path(args.results_root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (results_root / "summary")
    out_dir.mkdir(parents=True, exist_ok=True)

    drop_values = []
    for token in args.drops.split(","):
        t = token.strip()
        if not t:
            continue
        drop_values.append(int(t))
    if not drop_values:
        raise SystemExit("--drops produced an empty list")

    progress_rows: list[dict] = []
    proto_rows_all: list[dict] = []

    for drop_pct in drop_values:
        ddir = results_root / f"drop_{drop_pct:03d}"
        done_count = sum(1 for _ in ddir.rglob("done"))
        sim_count = sum(1 for _ in ddir.rglob("sim.log"))
        progress = (done_count / args.expected_jobs) if args.expected_jobs > 0 else 0.0

        progress_rows.append(
            {
                "drop_pct": drop_pct,
                "drop_dir": str(ddir.relative_to(results_root)),
                "exists": int(ddir.is_dir()),
                "done_count": done_count,
                "sim_count": sim_count,
                "expected_jobs": args.expected_jobs,
                "progress_ratio": round(progress, 6),
            }
        )

        if sim_count == 0:
            continue

        _, proto_rows = summarize(ddir)
        for row in proto_rows:
            r = dict(row)
            r["drop_pct"] = drop_pct
            proto_rows_all.append(r)

    progress_rows.sort(key=lambda r: r["drop_pct"])
    proto_rows_all.sort(key=lambda r: (r["drop_pct"], r["protocol"]))

    write_csv(out_dir / "drop_progress.csv", progress_rows)
    write_csv(out_dir / "drop_by_protocol.csv", proto_rows_all)

    md = []
    md.append("# Drop Sweep Status Snapshot")
    md.append("")
    md.append(f"- results_root: `{results_root}`")
    md.append(f"- expected_jobs_per_drop: `{args.expected_jobs}`")
    md.append("")
    md.append("## Progress")
    md.append("")
    md.append("| drop_pct | done_count | sim_count | progress_ratio |")
    md.append("|---:|---:|---:|---:|")
    for r in progress_rows:
        md.append(
            f"| {r['drop_pct']} | {r['done_count']} | {r['sim_count']} | {r['progress_ratio']:.4f} |"
        )

    available_drops = sorted({r["drop_pct"] for r in proto_rows_all})
    if available_drops:
        md.append("")
        md.append("## Protocol Means (Available Drops)")
        md.append("")
        md.append("| drop_pct | protocol | pdr_during_mean | route_att_share_during_mean | run_hit_ratio_during_mean | churn_during_mean |")
        md.append("|---:|---|---:|---:|---:|---:|")
        for r in proto_rows_all:
            md.append(
                "| "
                f"{r['drop_pct']} | {r['protocol']} | "
                f"{r['pdr_during_mean']:.4f} | {r['route_att_share_during_mean']:.4f} | "
                f"{r['run_hit_ratio_during_mean']:.4f} | {r['churn_during_mean']:.2f} |"
            )

    (out_dir / "snapshot.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"[OK] wrote: {out_dir / 'drop_progress.csv'}")
    print(f"[OK] wrote: {out_dir / 'drop_by_protocol.csv'}")
    print(f"[OK] wrote: {out_dir / 'snapshot.md'}")


if __name__ == "__main__":
    main()
