#!/usr/bin/env python3
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


ATTACK_RE = re.compile(r"^(\d+):CSV,ATTACK_PARAMS,")
ROUTE_RE = re.compile(
    r"^\d+:CSV,ROUTE,(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)"
)


def parse_sim_log(path: Path):
    attacker_ids = set()
    route_by_node = defaultdict(list)  # node -> [(clock,parent)]
    with path.open("r", errors="ignore") as f:
        for line in f:
            m = ATTACK_RE.match(line)
            if m:
                attacker_ids.add(int(m.group(1)))
                continue
            r = ROUTE_RE.match(line)
            if not r:
                continue
            node_id = int(r.group(1))
            clock = int(r.group(2))
            parent = int(r.group(3))
            route_by_node[node_id].append((clock, parent))
    return attacker_ids, route_by_node


def node_metrics(samples, attacker_ids):
    # samples: list[(clock,parent)], assumed time-ordered.
    if len(samples) < 2:
        return {
            "att_join_count": 0,
            "att_escape_count": 0,
            "att_dwell_sum": 0,
            "att_dwell_count": 0,
            "obs_dur": 0,
            "att_obs_dur": 0,
        }

    att_join_count = 0
    att_escape_count = 0
    att_dwell_sum = 0
    att_dwell_count = 0
    obs_dur = 0
    att_obs_dur = 0

    prev_clock, prev_parent = samples[0]
    prev_att = prev_parent in attacker_ids
    att_run_start = prev_clock if prev_att else None

    for clock, parent in samples[1:]:
        dt = max(0, clock - prev_clock)
        obs_dur += dt
        if prev_att:
            att_obs_dur += dt

        now_att = parent in attacker_ids

        if (not prev_att) and now_att:
            att_join_count += 1
            att_run_start = clock
        elif prev_att and (not now_att):
            att_escape_count += 1
            if att_run_start is not None:
                att_dwell_sum += max(0, clock - att_run_start)
                att_dwell_count += 1
            att_run_start = None

        prev_clock, prev_parent, prev_att = clock, parent, now_att

    if prev_att and att_run_start is not None:
        att_dwell_sum += max(0, prev_clock - att_run_start)
        att_dwell_count += 1

    return {
        "att_join_count": att_join_count,
        "att_escape_count": att_escape_count,
        "att_dwell_sum": att_dwell_sum,
        "att_dwell_count": att_dwell_count,
        "obs_dur": obs_dur,
        "att_obs_dur": att_obs_dur,
    }


def parse_case_dir(case_dir: Path):
    # e.g., GRID_TABRPL_SINK_DROP50
    parts = case_dir.name.split("_")
    if len(parts) < 3:
        return None
    topo = parts[0]
    proto = parts[1]
    scenario = "_".join(parts[2:])
    return topo, proto, scenario


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.results_dir)
    rows = []

    for case_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        parsed = parse_case_dir(case_dir)
        if not parsed:
            continue
        topo, proto, scenario = parsed

        for seed_dir in sorted([p for p in case_dir.iterdir() if p.is_dir()]):
            sim_log = seed_dir / "sim.log"
            if not sim_log.exists():
                continue
            attacker_ids, route_by_node = parse_sim_log(sim_log)
            if not attacker_ids:
                continue

            agg = defaultdict(float)
            node_count = 0
            for _, samples in route_by_node.items():
                m = node_metrics(samples, attacker_ids)
                node_count += 1
                for k, v in m.items():
                    agg[k] += v

            if node_count == 0:
                continue

            att_exposure_ratio = (
                agg["att_obs_dur"] / agg["obs_dur"] if agg["obs_dur"] > 0 else 0.0
            )
            mean_att_joins_per_node = agg["att_join_count"] / node_count
            mean_att_escapes_per_node = agg["att_escape_count"] / node_count
            mean_att_dwell = (
                agg["att_dwell_sum"] / agg["att_dwell_count"]
                if agg["att_dwell_count"] > 0
                else 0.0
            )

            rows.append(
                {
                    "topo": topo,
                    "proto": proto,
                    "scenario": scenario,
                    "seed": seed_dir.name.replace("seed", ""),
                    "nodes": node_count,
                    "attackers": ";".join(str(x) for x in sorted(attacker_ids)),
                    "att_exposure_ratio": f"{att_exposure_ratio:.6f}",
                    "mean_att_joins_per_node": f"{mean_att_joins_per_node:.6f}",
                    "mean_att_escapes_per_node": f"{mean_att_escapes_per_node:.6f}",
                    "mean_att_dwell_clocks": f"{mean_att_dwell:.2f}",
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "topo",
        "proto",
        "scenario",
        "seed",
        "nodes",
        "attackers",
        "att_exposure_ratio",
        "mean_att_joins_per_node",
        "mean_att_escapes_per_node",
        "mean_att_dwell_clocks",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # grouped summary
    grouped = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(int)
    for r in rows:
        k = (r["topo"], r["proto"], r["scenario"])
        grouped[k]["att_exposure_ratio"] += float(r["att_exposure_ratio"])
        grouped[k]["mean_att_joins_per_node"] += float(r["mean_att_joins_per_node"])
        grouped[k]["mean_att_escapes_per_node"] += float(r["mean_att_escapes_per_node"])
        grouped[k]["mean_att_dwell_clocks"] += float(r["mean_att_dwell_clocks"])
        counts[k] += 1

    print(
        "topo,proto,scenario,n,att_exposure_ratio,mean_att_joins_per_node,mean_att_escapes_per_node,mean_att_dwell_clocks"
    )
    for k in sorted(grouped):
        n = counts[k]
        g = grouped[k]
        print(
            f"{k[0]},{k[1]},{k[2]},{n},"
            f"{g['att_exposure_ratio']/n:.6f},"
            f"{g['mean_att_joins_per_node']/n:.6f},"
            f"{g['mean_att_escapes_per_node']/n:.6f},"
            f"{g['mean_att_dwell_clocks']/n:.2f}"
        )


if __name__ == "__main__":
    main()

