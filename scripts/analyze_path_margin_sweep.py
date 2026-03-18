#!/usr/bin/env python3
"""Summarize better-parent path-margin sweep results."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = ROOT / "results"
SUMMARY_ROOT = RESULTS_ROOT / "summaries"
ATTACKERS = {2, 3, 4, 18}
WINDOWS = {
    "during": (350_000, 650_000),
    "recovery": (650_000, 900_000),
}
PROTOCOLS = [
    "BRPL",
    "TABRPL",
    "TABRPL_PTH_064",
    "TABRPL_PTH_128",
    "TABRPL_PTH_256",
    "TABRPL_PTH_384",
]


def phase_of(tick: int) -> str | None:
    for name, (lo, hi) in WINDOWS.items():
        if lo <= tick < hi:
            return name
    return None


def resolve_result_dir(name: str) -> Path:
    new_path = RESULTS_ROOT / name
    if new_path.exists():
        return new_path
    return ROOT / name


def summarize_result_dir(results_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for proto in PROTOCOLS:
        proto_dir = results_dir / proto
        if not proto_dir.exists():
            continue

        metrics: dict[str, list[float]] = defaultdict(list)
        for seed_dir in sorted(proto_dir.glob("*")):
            log_path = seed_dir / "sim.log"
            if not log_path.exists():
                continue

            tx = defaultdict(set)
            rx = defaultdict(set)
            route_total = defaultdict(int)
            route_attack = defaultdict(int)
            trust_parent = defaultdict(int)
            candidate_allowed = defaultdict(list)
            escape_count = defaultdict(int)

            with log_path.open(errors="replace") as f:
                for raw in f:
                    if ":" not in raw:
                        continue
                    rest = raw.split(":", 1)[1].strip()

                    if rest.startswith("CSV,TX,"):
                        parts = rest.split(",")
                        try:
                            node = int(parts[2])
                            seq = int(parts[3])
                            t0 = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(t0)
                        if phase:
                            tx[phase].add((node, seq))

                    elif rest.startswith("CSV,RX,"):
                        parts = rest.split(",")
                        try:
                            node = int(parts[3].rsplit(":", 1)[-1], 16)
                            seq = int(parts[4])
                            t0 = int(parts[6])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(t0)
                        if phase:
                            rx[phase].add((node, seq))

                    elif rest.startswith("CSV,ROUTE,"):
                        parts = rest.split(",")
                        if len(parts) < 11:
                            continue
                        try:
                            tick = int(parts[3])
                            parent = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(tick)
                        if phase:
                            route_total[phase] += 1
                            if parent in ATTACKERS:
                                route_attack[phase] += 1

                    elif rest.startswith("CSV,TRUST_PARENT,"):
                        parts = rest.split(",")
                        try:
                            tick = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(tick)
                        if phase:
                            trust_parent[phase] += 1

                    elif rest.startswith("CSV,TRUST_ESCAPE,"):
                        parts = rest.split(",")
                        try:
                            tick = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(tick)
                        if phase:
                            escape_count[phase] += 1

                    elif rest.startswith("CSV,TRUST_CANDIDATES,"):
                        parts = rest.split(",")
                        try:
                            tick = int(parts[3])
                            allowed = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = phase_of(tick)
                        if phase:
                            candidate_allowed[phase].append(allowed)

            for phase in WINDOWS:
                if tx[phase]:
                    metrics[f"pdr_{phase}"].append(len(rx[phase]) / len(tx[phase]))
                if route_total[phase]:
                    metrics[f"attacker_share_{phase}"].append(route_attack[phase] / route_total[phase])
                metrics[f"parent_switch_{phase}"].append(trust_parent[phase])
                metrics[f"escape_{phase}"].append(escape_count[phase])
                if candidate_allowed[phase]:
                    metrics[f"usable_parents_{phase}"].append(statistics.mean(candidate_allowed[phase]))

        row: dict[str, object] = {"results_dir": results_dir.name, "protocol": proto}
        for key, vals in metrics.items():
            row[key] = statistics.mean(vals) if vals else float("nan")
        rows.append(row)

    return rows


def main() -> None:
    rows: list[dict[str, object]] = []
    for dirname in ("results_LOSS90", "results_LOSS70", "results_LOSS50"):
        rows.extend(summarize_result_dir(resolve_result_dir(dirname)))

    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = SUMMARY_ROOT / "path_margin_sweep_summary.csv"
    fieldnames = [
        "results_dir", "protocol",
        "pdr_during", "pdr_recovery",
        "attacker_share_during", "attacker_share_recovery",
        "usable_parents_during", "usable_parents_recovery",
        "parent_switch_during", "parent_switch_recovery",
        "escape_during", "escape_recovery",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(out_path)


if __name__ == "__main__":
    main()
