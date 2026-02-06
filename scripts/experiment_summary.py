#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict


RUN_RE = re.compile(
    r"^(?P<topo>[^_]+)_(?P<scenario>[^_]+)_atk(?P<attack>\d+)_trust(?P<trust>[01])_"
    r"lam(?P<lam>[^_]+)_gam(?P<gam>[^_]+)_s(?P<seed>\d+)$"
)


def parse_run_name(name):
    match = RUN_RE.match(name)
    if not match:
        return None
    data = match.groupdict()
    attack_rate = int(data["attack"])
    trust = int(data["trust"])
    seed = int(data["seed"])
    lam = None if data["lam"] == "NA" else int(data["lam"])
    gam = None if data["gam"] == "NA" else int(data["gam"])
    return {
        "topology": data["topo"],
        "scenario": data["scenario"],
        "attack_rate": attack_rate,
        "trust": trust,
        "lambda": lam,
        "gamma": gam,
        "seed": seed,
    }


def parse_log(log_path):
    tx = set()
    rx = set()
    delays = []
    routing_timeout = False
    routing_wait = False
    with open(log_path, errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("CSV,TX,"):
                parts = line.split(",")
                if len(parts) >= 4:
                    try:
                        node = int(parts[2])
                        seq = int(parts[3])
                        tx.add((node, seq))
                    except ValueError:
                        pass
            elif line.startswith("CSV,RX,"):
                parts = line.split(",")
                if "node=1" in parts:
                    try:
                        node_index = parts.index("node=1")
                        src = parts[node_index + 1]
                        seq = parts[node_index + 2]
                        rx.add((src, int(seq)))
                    except (ValueError, IndexError):
                        pass
                elif len(parts) >= 4:
                    # Fallback when node=1 is not explicitly logged.
                    src = parts[2]
                    try:
                        seq = int(parts[3])
                        rx.add((src, seq))
                    except ValueError:
                        pass
            elif line.startswith("CSV,DELAY,"):
                parts = line.split(",")
                if len(parts) >= 3:
                    try:
                        delays.append(int(parts[2]))
                    except ValueError:
                        pass
            elif "ROUTING_WAIT_TIMEOUT" in line:
                routing_timeout = True
            elif "ROUTING_WAIT joined=0 reachable=0" in line:
                routing_wait = True
    tx_count = len(tx)
    rx_count = len(rx)
    pdr = (rx_count * 100 / tx_count) if tx_count > 0 else None
    avg_delay = (sum(delays) / len(delays)) if delays else None
    return {
        "tx": tx_count,
        "rx": rx_count,
        "pdr": pdr,
        "avg_delay_ms": avg_delay,
        "routing_timeout": routing_timeout,
        "routing_wait": routing_wait,
    }


def read_last_row(csv_path):
    last = None
    with open(csv_path, errors="ignore") as handle:
        for row in csv.reader(handle):
            if row and not row[0].startswith("#"):
                last = row
    return last


def read_parent_switch_avg(csv_path):
    rates = []
    with open(csv_path, errors="ignore") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                rates.append(float(row["switch_rate"]))
            except (ValueError, KeyError):
                pass
    return sum(rates) / len(rates) if rates else None


def read_stats_last_switch(stats_path):
    last = None
    with open(stats_path, errors="ignore") as handle:
        for row in csv.reader(handle):
            if row and row[0] != "line":
                last = row
    if last and len(last) >= 8:
        try:
            return float(last[7])
        except ValueError:
            return None
    return None


def mean(values):
    return sum(values) / len(values) if values else None


def stddev(values):
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def ci95(values):
    if len(values) < 2:
        return 0.0
    return 1.96 * stddev(values) / math.sqrt(len(values))


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", help="results/experiments-...")
    parser.add_argument("--matrix", help="Optional sweep_matrix.csv to update")
    args = parser.parse_args()

    summary_rows = []
    invalid_rows = []
    run_entries = []
    for name in os.listdir(args.results_dir):
        run_dir = os.path.join(args.results_dir, name)
        if not os.path.isdir(run_dir):
            continue
        run_info = parse_run_name(name)
        if not run_info:
            continue
        run_entries.append(name)
        log_path = os.path.join(run_dir, "logs", "COOJA.testlog")
        if not os.path.exists(log_path):
            invalid_rows.append(
                {
                    **run_info,
                    "run": name,
                    "reason": "missing_log",
                }
            )
            continue

        log_stats = parse_log(log_path)
        exposure_path = os.path.join(run_dir, "exposure.csv")
        parent_path = os.path.join(run_dir, "parent_switch.csv")
        stats_path = os.path.join(run_dir, "stats.csv")

        e1 = None
        e3 = None
        if os.path.exists(exposure_path):
            last = read_last_row(exposure_path)
            if last and len(last) >= 7:
                try:
                    e1 = float(last[5])
                    e3 = float(last[6])
                except ValueError:
                    pass

        parent_switch = None
        if os.path.exists(parent_path):
            parent_switch = read_parent_switch_avg(parent_path)
        if parent_switch is None and os.path.exists(stats_path):
            parent_switch = read_stats_last_switch(stats_path)

        reasons = []
        if log_stats["tx"] == 0:
            reasons.append("tx=0")
        if log_stats["rx"] == 0:
            reasons.append("rx=0")
        if (log_stats["tx"] == 0 or log_stats["rx"] == 0) and (
            log_stats["routing_timeout"] or log_stats["routing_wait"]
        ):
            reasons.append("routing_not_ready")
        if log_stats["pdr"] is None or log_stats["avg_delay_ms"] is None:
            reasons.append("missing_core_metrics")
        if run_info["trust"] == 1 and (
            e1 is None or e3 is None or parent_switch is None
        ):
            reasons.append("missing_trust_metrics")

        if reasons:
            invalid_rows.append(
                {
                    **run_info,
                    "run": name,
                    "reason": ";".join(sorted(set(reasons))),
                }
            )
            continue

        summary_rows.append(
            {
                "run": name,
                "topology": run_info["topology"],
                "attack_rate": run_info["attack_rate"],
                "trust": run_info["trust"],
                "lambda": run_info["lambda"] if run_info["lambda"] is not None else "NA",
                "gamma": run_info["gamma"] if run_info["gamma"] is not None else "NA",
                "seed": run_info["seed"],
                "pdr": f"{log_stats['pdr']:.2f}",
                "avg_delay_ms": f"{log_stats['avg_delay_ms']:.2f}",
                "tx": log_stats["tx"],
                "rx": log_stats["rx"],
                "lost": log_stats["tx"] - log_stats["rx"],
                "e1": f"{e1:.4f}" if e1 is not None else "",
                "e3": f"{e3:.4f}" if e3 is not None else "",
                "parent_switch_rate": f"{parent_switch:.4f}" if parent_switch is not None else "",
            }
        )

    summary_rows_sorted = sorted(summary_rows, key=lambda r: r["run"])
    invalid_rows_sorted = sorted(invalid_rows, key=lambda r: r["run"])
    summary_path = os.path.join(args.results_dir, "experiment_summary.csv")
    invalid_path = os.path.join(args.results_dir, "invalid_runs.csv")

    write_csv(
        summary_path,
        [
            "run",
            "topology",
            "attack_rate",
            "trust",
            "lambda",
            "gamma",
            "seed",
            "pdr",
            "avg_delay_ms",
            "tx",
            "rx",
            "lost",
            "e1",
            "e3",
            "parent_switch_rate",
        ],
        summary_rows_sorted,
    )
    write_csv(
        invalid_path,
        [
            "run",
            "topology",
            "attack_rate",
            "trust",
            "lambda",
            "gamma",
            "seed",
            "reason",
        ],
        invalid_rows_sorted,
    )

    if args.matrix and os.path.exists(args.matrix):
        matrix_rows = []
        with open(args.matrix, errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = row.get("status", "planned")
                if row.get("run") in run_entries:
                    status = "completed"
                row["status"] = status
                matrix_rows.append(row)
        if matrix_rows:
            write_csv(args.matrix, list(matrix_rows[0].keys()), matrix_rows)
    else:
        matrix_path = os.path.join(args.results_dir, "sweep_matrix.csv")
        matrix_rows = []
        for name in sorted(run_entries):
            info = parse_run_name(name)
            matrix_rows.append(
                {
                    "run": name,
                    "topology": info["topology"],
                    "scenario": info["scenario"],
                    "attack_rate": info["attack_rate"],
                    "trust": info["trust"],
                    "lambda": info["lambda"] if info["lambda"] is not None else "NA",
                    "gamma": info["gamma"] if info["gamma"] is not None else "NA",
                    "seed": info["seed"],
                    "status": "completed",
                }
            )
        if matrix_rows:
            write_csv(
                matrix_path,
                [
                    "run",
                    "topology",
                    "scenario",
                    "attack_rate",
                    "trust",
                    "lambda",
                    "gamma",
                    "seed",
                    "status",
                ],
                matrix_rows,
            )

    grouped = defaultdict(list)
    for row in summary_rows_sorted:
        key = (
            row["topology"],
            int(row["attack_rate"]),
            int(row["trust"]),
            row["lambda"],
            row["gamma"],
        )
        grouped[key].append(row)

    aggregate_rows = []
    for key, rows in sorted(grouped.items()):
        pdr_values = [float(r["pdr"]) for r in rows]
        e1_values = [float(r["e1"]) for r in rows if r["e1"] != ""]
        ps_values = [
            float(r["parent_switch_rate"])
            for r in rows
            if r["parent_switch_rate"] != ""
        ]
        aggregate_rows.append(
            {
                "topology": key[0],
                "attack_rate": key[1],
                "trust": key[2],
                "lambda": key[3],
                "gamma": key[4],
                "n": len(rows),
                "mean_pdr": f"{mean(pdr_values):.2f}" if pdr_values else "",
                "std_pdr": f"{stddev(pdr_values):.2f}" if pdr_values else "",
                "ci95_pdr": f"{ci95(pdr_values):.2f}" if pdr_values else "",
                "mean_e1": f"{mean(e1_values):.4f}" if e1_values else "",
                "std_e1": f"{stddev(e1_values):.4f}" if e1_values else "",
                "ci95_e1": f"{ci95(e1_values):.4f}" if e1_values else "",
                "mean_parent_switch": f"{mean(ps_values):.4f}" if ps_values else "",
                "std_parent_switch": f"{stddev(ps_values):.4f}" if ps_values else "",
                "ci95_parent_switch": f"{ci95(ps_values):.4f}" if ps_values else "",
            }
        )

    aggregate_path = os.path.join(args.results_dir, "aggregate_by_group.csv")
    if aggregate_rows:
        write_csv(
            aggregate_path,
            [
                "topology",
                "attack_rate",
                "trust",
                "lambda",
                "gamma",
                "n",
                "mean_pdr",
                "std_pdr",
                "ci95_pdr",
                "mean_e1",
                "std_e1",
                "ci95_e1",
                "mean_parent_switch",
                "std_parent_switch",
                "ci95_parent_switch",
            ],
            aggregate_rows,
        )

    invalid_reasons = Counter(row["reason"] for row in invalid_rows_sorted)
    top_reasons = invalid_reasons.most_common(3)

    report_path = os.path.join(args.results_dir, "report.md")
    with open(report_path, "w") as handle:
        handle.write("# Trust-Aware BRPL Sweep Report\n\n")
        handle.write("## Experiment Scope\n")
        handle.write(
            "- Swept lambda/gamma on trust-enabled runs (attack scenarios), with trust-off baselines.\n"
        )
        handle.write("- Summary generated from COOJA logs and trust_engine outputs.\n\n")
        handle.write("## Invalid Runs\n")
        handle.write(f"- Invalid runs: {len(invalid_rows_sorted)}\n")
        if top_reasons:
            handle.write("- Top reasons:\n")
            for reason, count in top_reasons:
                handle.write(f"  - {reason}: {count}\n")
        handle.write("\n")
        handle.write("## Key Results (T3, attack=50)\n")

        t3_rows = [
            row
            for row in aggregate_rows
            if row["topology"] == "T3" and row["attack_rate"] == 50
        ]
        if t3_rows:
            handle.write("| lambda | gamma | mean_e1 | mean_parent_switch | mean_pdr |\n")
            handle.write("|---|---|---|---|---|\n")
            for row in sorted(t3_rows, key=lambda r: (r["lambda"], r["gamma"])):
                handle.write(
                    f"| {row['lambda']} | {row['gamma']} | {row['mean_e1']} | "
                    f"{row['mean_parent_switch']} | {row['mean_pdr']} |\n"
                )
        else:
            handle.write("No valid T3 attack=50 results to summarize.\n")

        if t3_rows:
            best = None
            for row in t3_rows:
                if row["mean_e1"] == "":
                    continue
                val = float(row["mean_e1"])
                if best is None or val < best[0]:
                    best = (val, row)
            if best:
                handle.write("\n")
                handle.write(
                    f"Best E1 reduction at lambda={best[1]['lambda']} gamma={best[1]['gamma']} "
                    f"(mean_e1={best[1]['mean_e1']}, mean_pdr={best[1]['mean_pdr']}).\n"
                )

    baseline_groups = defaultdict(list)
    for row in summary_rows_sorted:
        if int(row["trust"]) == 0:
            baseline_groups[(row["topology"], int(row["attack_rate"]))].append(float(row["pdr"]))
    for topology in sorted({k[0] for k in baseline_groups}):
        attack_rates = sorted({k[1] for k in baseline_groups if k[0] == topology})
        if len(attack_rates) < 2:
            continue
        means = [mean(baseline_groups[(topology, rate)]) for rate in attack_rates]
        if any(means[i] < means[i + 1] for i in range(len(means) - 1)):
            print(
                f"[WARN] Baseline PDR not decreasing with attack rate for {topology}: "
                f"{list(zip(attack_rates, means))}"
            )

    low_exposure = [
        row
        for row in summary_rows_sorted
        if row["topology"] == "T2_random_15_seed1" and int(row["attack_rate"]) > 0
    ]
    if low_exposure:
        pdr_vals = [float(row["pdr"]) for row in low_exposure]
        e1_vals = [float(row["e1"]) for row in low_exposure if row["e1"] != ""]
        if mean(pdr_vals) >= 95 and (not e1_vals or mean(e1_vals) <= 0.01):
            print("[INFO] low-exposure confirmed for T2_random_15_seed1")

    for topo in ["T3", "T1_S"]:
        trust_rows = [
            row
            for row in summary_rows_sorted
            if row["topology"] == topo and int(row["trust"]) == 1 and int(row["attack_rate"]) > 0
        ]
        if trust_rows:
            e1_vals = [float(row["e1"]) for row in trust_rows if row["e1"] != ""]
            if e1_vals and (max(e1_vals) - min(e1_vals)) < 0.01:
                print(f"[WARN] trust penalty not affecting parent ranking on {topo} (E1 flat)")

    summary_outputs = {
        "summary": summary_path,
        "invalid": invalid_path,
        "aggregate": aggregate_path,
        "report": report_path,
    }
    print(json.dumps(summary_outputs, indent=2))


if __name__ == "__main__":
    main()
