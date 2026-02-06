#!/usr/bin/env python3
import argparse
import csv
import os
from collections import defaultdict


def try_import_matplotlib():
    try:
        import matplotlib.pyplot as plt  # type: ignore
        return plt
    except Exception:
        return None


def load_rows(path):
    rows = []
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            if not r:
                continue
            rows.append(r)
    return rows


def to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def aggregate(rows):
    groups = defaultdict(lambda: {"n": 0, "pdr": 0.0, "e1": 0.0, "e3": 0.0, "switch": 0.0})
    for r in rows:
        key = (r["topology"], r["attack_rate"], r["trust"])
        pdr = to_float(r.get("pdr", ""))
        e1 = to_float(r.get("e1", ""))
        e3 = to_float(r.get("e3", ""))
        sw = to_float(r.get("parent_switch_rate", ""))
        if pdr is None or e1 is None or e3 is None:
            continue
        groups[key]["n"] += 1
        groups[key]["pdr"] += pdr
        groups[key]["e1"] += e1
        groups[key]["e3"] += e3
        groups[key]["switch"] += sw if sw is not None else 0.0
    out = []
    for (topo, attack, trust), v in groups.items():
        n = v["n"]
        if n == 0:
            continue
        out.append(
            {
                "topology": topo,
                "attack_rate": attack,
                "trust": trust,
                "n": n,
                "pdr": v["pdr"] / n,
                "e1": v["e1"] / n,
                "e3": v["e3"] / n,
                "parent_switch_rate": v["switch"] / n,
            }
        )
    return out


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        fieldnames = ["topology", "attack_rate", "trust", "n", "pdr", "e1", "e3", "parent_switch_rate"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["topology"], int(x["attack_rate"]), int(x["trust"]))):
            w.writerow(r)


def plot_series(plt, rows, metric, out_path):
    series = defaultdict(list)
    for r in rows:
        series[(r["topology"], r["trust"])].append((int(r["attack_rate"]), r[metric]))
    plt.figure(figsize=(6, 4))
    for (topo, trust), points in series.items():
        points = sorted(points, key=lambda x: x[0])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        label = f"{topo} trust={trust}"
        plt.plot(xs, ys, marker="o", label=label)
    plt.xlabel("Attack rate (%)")
    plt.ylabel(metric.upper())
    plt.title(f"{metric.upper()} vs attack rate")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir", help="results/experiments-...")
    ap.add_argument("--summary", default="summary_from_trust_engine.csv")
    ap.add_argument("--out", default="summary_agg.csv")
    args = ap.parse_args()

    summary_path = os.path.join(args.results_dir, args.summary)
    rows = load_rows(summary_path)
    agg = aggregate(rows)
    out_csv = os.path.join(args.results_dir, args.out)
    write_csv(agg, out_csv)

    plt = try_import_matplotlib()
    if plt is None:
        print(out_csv)
        print("matplotlib not available; plots skipped.")
        return

    plot_dir = os.path.join(args.results_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)
    for metric in ("pdr", "e1", "e3", "parent_switch_rate"):
        plot_series(plt, agg, metric, os.path.join(plot_dir, f"{metric}.png"))

    print(out_csv)


if __name__ == "__main__":
    main()
