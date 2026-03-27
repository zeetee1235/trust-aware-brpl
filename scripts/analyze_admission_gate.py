#!/usr/bin/env python3
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


ATTACK_RE = re.compile(r"^(\d+):CSV,ATTACK_PARAMS,")


def parse_case(case_dir_name: str):
    parts = case_dir_name.split("_")
    if len(parts) < 3:
        return None
    return parts[0], parts[1], "_".join(parts[2:])


def parse_sim(sim_log: Path):
    attackers = set()
    # key=(self,cand) -> latest cumulative counters
    latest = {}
    with sim_log.open("r", errors="ignore") as f:
        for line in f:
            m = ATTACK_RE.match(line)
            if m:
                attackers.add(int(m.group(1)))
                continue
            if ":CSV,ADMISSION," not in line:
                continue
            payload = line.split(":CSV,ADMISSION,", 1)[1].strip()
            parts = payload.split(",")
            # backward/forward compatible:
            # old: 13 columns, new: 14 columns (trailing clock)
            if len(parts) < 13:
                continue
            self_id = int(parts[0])
            cand_id = int(parts[1])
            # a.group(3) is is_current: not used for accumulation
            latest[(self_id, cand_id)] = {
                "eval": int(parts[7]),
                "allow": int(parts[8]),
                "b_blacklist": int(parts[9]),
                "b_trust": int(parts[10]),
                "b_review": int(parts[11]),
                "b_severe": int(parts[12]),
            }
    return attackers, latest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.results_dir)
    rows = []

    for case_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        parsed = parse_case(case_dir.name)
        if not parsed:
            continue
        topo, proto, scenario = parsed

        for seed_dir in sorted([p for p in case_dir.iterdir() if p.is_dir()]):
            sim_log = seed_dir / "sim.log"
            if not sim_log.exists():
                continue
            attackers, latest = parse_sim(sim_log)
            if not latest:
                continue

            agg = defaultdict(int)
            for (_, cand), c in latest.items():
                group = "att" if cand in attackers else "norm"
                agg[f"{group}_eval"] += c["eval"]
                agg[f"{group}_allow"] += c["allow"]
                agg[f"{group}_b_blacklist"] += c["b_blacklist"]
                agg[f"{group}_b_trust"] += c["b_trust"]
                agg[f"{group}_b_review"] += c["b_review"]
                agg[f"{group}_b_severe"] += c["b_severe"]

            def ratio(n, d):
                return (n / d) if d > 0 else 0.0

            att_eval = agg["att_eval"]
            norm_eval = agg["norm_eval"]
            att_block = (
                agg["att_b_blacklist"]
                + agg["att_b_trust"]
                + agg["att_b_review"]
                + agg["att_b_severe"]
            )
            norm_block = (
                agg["norm_b_blacklist"]
                + agg["norm_b_trust"]
                + agg["norm_b_review"]
                + agg["norm_b_severe"]
            )

            rows.append(
                {
                    "topo": topo,
                    "proto": proto,
                    "scenario": scenario,
                    "seed": seed_dir.name.replace("seed", ""),
                    "att_eval": att_eval,
                    "att_allow": agg["att_allow"],
                    "att_block": att_block,
                    "att_block_rate": f"{ratio(att_block, att_eval):.6f}",
                    "norm_eval": norm_eval,
                    "norm_allow": agg["norm_allow"],
                    "norm_block": norm_block,
                    "norm_block_rate": f"{ratio(norm_block, norm_eval):.6f}",
                    "norm_block_severe": agg["norm_b_severe"],
                    "norm_severe_share": f"{ratio(agg['norm_b_severe'], norm_block):.6f}",
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "topo",
        "proto",
        "scenario",
        "seed",
        "att_eval",
        "att_allow",
        "att_block",
        "att_block_rate",
        "norm_eval",
        "norm_allow",
        "norm_block",
        "norm_block_rate",
        "norm_block_severe",
        "norm_severe_share",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    grouped = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(int)
    sum_fields = [
        "att_eval",
        "att_allow",
        "att_block",
        "norm_eval",
        "norm_allow",
        "norm_block",
        "norm_block_severe",
    ]
    for r in rows:
        k = (r["topo"], r["proto"], r["scenario"])
        counts[k] += 1
        for sf in sum_fields:
            grouped[k][sf] += float(r[sf])

    print(
        "topo,proto,scenario,n,att_block_rate,norm_block_rate,norm_severe_share,att_eval,norm_eval"
    )
    for k in sorted(grouped):
        g = grouped[k]
        att_eval = g["att_eval"]
        norm_eval = g["norm_eval"]
        att_block_rate = (g["att_block"] / att_eval) if att_eval > 0 else 0.0
        norm_block_rate = (g["norm_block"] / norm_eval) if norm_eval > 0 else 0.0
        norm_severe_share = (
            g["norm_block_severe"] / g["norm_block"] if g["norm_block"] > 0 else 0.0
        )
        print(
            f"{k[0]},{k[1]},{k[2]},{counts[k]},"
            f"{att_block_rate:.6f},{norm_block_rate:.6f},{norm_severe_share:.6f},"
            f"{int(att_eval)},{int(norm_eval)}"
        )


if __name__ == "__main__":
    main()
