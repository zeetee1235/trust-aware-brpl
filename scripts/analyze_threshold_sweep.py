#!/usr/bin/env python3
"""Summarize threshold-sweep results for TA-BRPL variants."""

from __future__ import annotations

import csv
import re
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
PROTO_RE = re.compile(r"^TABRPL_J(?P<join>\d+)_W(?P<warn>\d+)$")


def classify_window(tick: int) -> str | None:
    for name, (lo, hi) in WINDOWS.items():
        if lo <= tick < hi:
            return name
    return None


def resolve_result_dir(name: str) -> Path:
    new_path = RESULTS_ROOT / name
    if new_path.exists():
        return new_path
    return ROOT / name


def parse_dir(results_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    protocols = sorted(
        p.name for p in results_dir.iterdir()
        if p.is_dir() and PROTO_RE.match(p.name)
    )

    for proto in protocols:
        match = PROTO_RE.match(proto)
        assert match is not None
        tau_join = int(match.group("join"))
        tau_warn = int(match.group("warn"))
        seed_metrics: dict[str, list[float]] = defaultdict(list)

        for seed_dir in sorted((results_dir / proto).glob("*")):
            log_path = seed_dir / "sim.log"
            if not log_path.exists():
                continue

            tx = defaultdict(set)
            rx = defaultdict(set)
            route_total = defaultdict(int)
            route_attack = defaultdict(int)
            trust_parent = defaultdict(int)
            candidate_allowed = defaultdict(list)
            blacklist_events = defaultdict(int)

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
                        phase = classify_window(t0)
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
                        phase = classify_window(t0)
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
                        phase = classify_window(tick)
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
                        phase = classify_window(tick)
                        if phase:
                            trust_parent[phase] += 1

                    elif rest.startswith("CSV,TRUST_BLACKLIST,"):
                        parts = rest.split(",")
                        try:
                            tick = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = classify_window(tick)
                        if phase:
                            blacklist_events[phase] += 1

                    elif rest.startswith("CSV,TRUST_CANDIDATES,"):
                        parts = rest.split(",")
                        try:
                            tick = int(parts[3])
                            allowed = int(parts[4])
                        except (ValueError, IndexError):
                            continue
                        phase = classify_window(tick)
                        if phase:
                            candidate_allowed[phase].append(allowed)

            for phase in WINDOWS:
                if tx[phase]:
                    seed_metrics[f"pdr_{phase}"].append(len(rx[phase]) / len(tx[phase]))
                if route_total[phase]:
                    seed_metrics[f"attacker_share_{phase}"].append(
                        route_attack[phase] / route_total[phase]
                    )
                seed_metrics[f"parent_switch_{phase}"].append(trust_parent[phase])
                seed_metrics[f"blacklist_{phase}"].append(blacklist_events[phase])
                if candidate_allowed[phase]:
                    seed_metrics[f"candidates_{phase}"].append(
                        statistics.mean(candidate_allowed[phase])
                    )

        row: dict[str, object] = {
            "results_dir": results_dir.name,
            "protocol": proto,
            "tau_join": tau_join,
            "tau_warn": tau_warn,
        }
        for phase in WINDOWS:
            for metric in ("pdr", "attacker_share", "parent_switch", "blacklist", "candidates"):
                key = f"{metric}_{phase}"
                vals = seed_metrics.get(key, [])
                row[key] = statistics.mean(vals) if vals else float("nan")
        rows.append(row)

    return rows


def main() -> None:
    result_dirs = [resolve_result_dir(name) for name in ("results_LOSS90", "results_LOSS70", "results_LOSS50")]
    rows: list[dict[str, object]] = []
    for result_dir in result_dirs:
        rows.extend(parse_dir(result_dir))

    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = SUMMARY_ROOT / "threshold_sweep_summary.csv"
    fieldnames = [
        "results_dir", "protocol", "tau_join", "tau_warn",
        "pdr_during", "pdr_recovery",
        "attacker_share_during", "attacker_share_recovery",
        "candidates_during", "candidates_recovery",
        "blacklist_during", "blacklist_recovery",
        "parent_switch_during", "parent_switch_recovery",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(out_path)


if __name__ == "__main__":
    main()
