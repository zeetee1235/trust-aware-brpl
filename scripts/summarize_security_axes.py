#!/usr/bin/env python3
"""Summarize security evaluation axes from random_topo sim logs.

Axes:
1) Absolute PDR (pre/during/recovery)
2) Attack degradation (during - pre, recovery - pre)
3) Attacker dependency (route attacker share, run-level hit ratio)
4) Stability/Cost (parent churn, TX overhead)

Expected tree:
  <results_dir>/<density>/<topo>/<protocol>/<seed>/sim.log
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

PHASE_BOUNDS = {
    "pre": (150_000, 350_000),
    "during": (350_000, 650_000),
    "recovery": (650_000, 900_000),
}


def phase_of_tick(tick: int) -> str | None:
    for name, (lo, hi) in PHASE_BOUNDS.items():
        if lo <= tick < hi:
            return name
    return None


def safe_mean(vals: list[float]) -> float:
    return statistics.mean(vals) if vals else float("nan")


def parse_one_log(path: Path) -> dict:
    tx = defaultdict(int)
    rx = defaultdict(int)
    route_total = defaultdict(int)
    route_att = defaultdict(int)
    route_node_att = defaultdict(lambda: defaultdict(bool))  # phase->node->hit
    route_nodes_seen = defaultdict(set)  # phase->nodes
    switch_state = {}  # node -> last switch_count
    churn = defaultdict(int)

    for raw in path.open(errors="replace"):
        i = raw.find("CSV,")
        if i < 0:
            continue
        parts = raw[i:].strip().split(",")
        if len(parts) < 2:
            continue
        tag = parts[1]

        if tag == "TX" and len(parts) >= 6:
            try:
                t0 = int(parts[4])
            except ValueError:
                continue
            ph = phase_of_tick(t0)
            if ph:
                tx[ph] += 1

        elif tag == "RX" and len(parts) >= 8:
            try:
                t0 = int(parts[6])
            except ValueError:
                continue
            ph = phase_of_tick(t0)
            if ph:
                rx[ph] += 1

        elif tag == "ROUTE" and len(parts) >= 11:
            try:
                node_id = int(parts[2])
                tick = int(parts[3])
                sw = int(parts[7])
                is_att = int(parts[9])
            except ValueError:
                continue
            ph = phase_of_tick(tick)
            if not ph:
                continue
            route_total[ph] += 1
            route_att[ph] += 1 if is_att == 1 else 0
            route_nodes_seen[ph].add(node_id)
            if is_att == 1:
                route_node_att[ph][node_id] = True

            prev = switch_state.get(node_id)
            if prev is not None and sw > prev:
                churn[ph] += (sw - prev)
            switch_state[node_id] = sw

    out = {}
    for ph in ("pre", "during", "recovery"):
        out[f"tx_{ph}"] = tx[ph]
        out[f"rx_{ph}"] = rx[ph]
        out[f"pdr_{ph}"] = (rx[ph] / tx[ph]) if tx[ph] > 0 else float("nan")
        out[f"route_att_share_{ph}"] = (
            route_att[ph] / route_total[ph] if route_total[ph] > 0 else float("nan")
        )
        seen_nodes = route_nodes_seen[ph]
        hit_nodes = route_node_att[ph]
        out[f"run_hit_ratio_{ph}"] = (
            sum(1 for n in seen_nodes if hit_nodes.get(n, False)) / len(seen_nodes)
            if seen_nodes
            else float("nan")
        )
        out[f"churn_{ph}"] = churn[ph]
    return out


def summarize(results_dir: Path) -> tuple[list[dict], list[dict]]:
    run_rows = []
    for simlog in sorted(results_dir.glob("*/*/*/*/sim.log")):
        density = simlog.parent.parent.parent.parent.name
        topo = simlog.parent.parent.parent.name
        proto = simlog.parent.parent.name
        seed = simlog.parent.name
        metrics = parse_one_log(simlog)
        run_rows.append(
            {
                "density": density,
                "topology": topo,
                "protocol": proto,
                "seed": seed,
                **metrics,
            }
        )

    by_proto = defaultdict(list)
    for row in run_rows:
        by_proto[row["protocol"]].append(row)

    proto_rows = []
    for proto, rows in sorted(by_proto.items()):
        p_pre = [r["pdr_pre"] for r in rows if not math.isnan(r["pdr_pre"])]
        p_dur = [r["pdr_during"] for r in rows if not math.isnan(r["pdr_during"])]
        p_rec = [r["pdr_recovery"] for r in rows if not math.isnan(r["pdr_recovery"])]
        tx_pre = [r["tx_pre"] for r in rows]
        tx_dur = [r["tx_during"] for r in rows]
        att_dur = [
            r["route_att_share_during"]
            for r in rows
            if not math.isnan(r["route_att_share_during"])
        ]
        hit_dur = [
            r["run_hit_ratio_during"]
            for r in rows
            if not math.isnan(r["run_hit_ratio_during"])
        ]
        churn_dur = [r["churn_during"] for r in rows]
        proto_rows.append(
            {
                "protocol": proto,
                "runs": len(rows),
                "pdr_pre_mean": safe_mean(p_pre),
                "pdr_during_mean": safe_mean(p_dur),
                "pdr_recovery_mean": safe_mean(p_rec),
                "delta_during_minus_pre": safe_mean(p_dur) - safe_mean(p_pre),
                "delta_recovery_minus_pre": safe_mean(p_rec) - safe_mean(p_pre),
                "route_att_share_during_mean": safe_mean(att_dur),
                "run_hit_ratio_during_mean": safe_mean(hit_dur),
                "churn_during_mean": safe_mean(churn_dur),
                "tx_pre_mean": safe_mean(tx_pre),
                "tx_during_mean": safe_mean(tx_dur),
                "tx_overhead_during_vs_pre": safe_mean(tx_dur) - safe_mean(tx_pre),
            }
        )
    return run_rows, proto_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize security evaluation axes.")
    ap.add_argument("--results-dir", required=True, help="Root directory for random_topo results.")
    ap.add_argument(
        "--out-prefix",
        default=None,
        help="Output prefix path (without suffix). Default: <results-dir>/security_axes",
    )
    args = ap.parse_args()

    results_dir = Path(args.results_dir).resolve()
    out_prefix = (
        Path(args.out_prefix).resolve() if args.out_prefix else results_dir / "security_axes"
    )

    run_rows, proto_rows = summarize(results_dir)
    write_csv(Path(str(out_prefix) + "_by_run.csv"), run_rows)
    write_csv(Path(str(out_prefix) + "_by_protocol.csv"), proto_rows)

    print(f"runs={len(run_rows)}")
    for row in proto_rows:
        print(
            f"{row['protocol']}: "
            f"PDR(pre/dur/rec)=({row['pdr_pre_mean']:.4f}/{row['pdr_during_mean']:.4f}/{row['pdr_recovery_mean']:.4f}), "
            f"att_share_dur={row['route_att_share_during_mean']:.4f}, "
            f"hit_ratio_dur={row['run_hit_ratio_during_mean']:.4f}, "
            f"churn_dur={row['churn_during_mean']:.2f}, "
            f"tx_overhead={row['tx_overhead_during_vs_pre']:+.2f}"
        )
    print(f"wrote: {out_prefix}_by_run.csv")
    print(f"wrote: {out_prefix}_by_protocol.csv")


if __name__ == "__main__":
    main()
