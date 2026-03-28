#!/usr/bin/env python3
r"""Generate paper-ready artifacts from random-topology experiment results.

Input tree:
  <results-dir>/<density>/<topology>/<protocol>/<run-seed>/sim.log

Outputs:
  - CSV summaries (run/topology/paired/summary)
  - Main figures (PDF)
  - LaTeX snippet ready to `\input{generated/main/main_results_auto.tex}`
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
from collections import defaultdict
from pathlib import Path

if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PHASE_PRE = (150_000, 350_000)
PHASE_DURING = (350_000, 650_000)


def phase_of_tick(tick: int) -> str | None:
    if PHASE_PRE[0] <= tick < PHASE_PRE[1]:
        return "pre"
    if PHASE_DURING[0] <= tick < PHASE_DURING[1]:
        return "during"
    return None


def safe_mean(vals: list[float]) -> float:
    vals = [v for v in vals if not math.isnan(v)]
    return float(statistics.mean(vals)) if vals else float("nan")


def safe_sd(vals: list[float]) -> float:
    vals = [v for v in vals if not math.isnan(v)]
    if len(vals) < 2:
        return 0.0
    return float(statistics.stdev(vals))


def fmt(x: float, nd: int = 4) -> str:
    if x is None or math.isnan(x):
        return "nan"
    return f"{x:.{nd}f}"


def bootstrap_mean_ci(
    values: list[float],
    *,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float]:
    xs = [v for v in values if not math.isnan(v)]
    if not xs:
        return float("nan"), float("nan"), float("nan")
    if len(xs) == 1:
        x = float(xs[0])
        return x, x, x
    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(n_resamples):
        sample = [xs[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()
    lo_idx = int((alpha / 2.0) * len(means))
    hi_idx = int((1.0 - alpha / 2.0) * len(means)) - 1
    lo_idx = max(0, min(lo_idx, len(means) - 1))
    hi_idx = max(0, min(hi_idx, len(means) - 1))
    return statistics.mean(xs), means[lo_idx], means[hi_idx]


def parse_src_node(src_ip: str) -> int | None:
    try:
        return int(src_ip.rsplit(":", 1)[-1], 16)
    except ValueError:
        return None


def parse_simlog(path: Path) -> dict[str, float]:
    root_id = 1
    attackers: set[int] = set()

    tx_keys: dict[str, set[tuple[int, int]]] = {"pre": set(), "during": set()}
    rx_keys: dict[str, set[tuple[int, int]]] = {"pre": set(), "during": set()}
    route_total_during = 0
    route_att_during = 0
    nodes_seen_during: set[int] = set()
    nodes_hit_during: set[int] = set()
    switch_state: dict[int, int] = {}
    churn_increase_during = 0

    with path.open(errors="replace") as f:
        for raw in f:
            i = raw.find("CSV,")
            if i < 0:
                continue
            parts = raw[i:].strip().split(",")
            if len(parts) < 2:
                continue

            tag = parts[1]

            if tag == "PROTOCOL" and len(parts) >= 4:
                proto_name = parts[3].strip().upper()
                if proto_name.startswith("ATTACKER") or proto_name.startswith("SINKHOLE"):
                    try:
                        attackers.add(int(parts[2]))
                    except ValueError:
                        pass
                continue

            if tag == "TX" and len(parts) >= 6:
                try:
                    node_id = int(parts[2])
                    seq = int(parts[3])
                    tick = int(parts[4])
                except ValueError:
                    continue
                phase = phase_of_tick(tick)
                if phase and node_id != root_id and node_id not in attackers:
                    tx_keys[phase].add((node_id, seq))
                continue

            if tag == "RX" and len(parts) >= 7:
                try:
                    seq = int(parts[4])
                    tx_tick = int(parts[5])
                except ValueError:
                    continue
                src_node = parse_src_node(parts[3])
                if src_node is None:
                    continue
                phase = phase_of_tick(tx_tick)
                if phase and src_node != root_id and src_node not in attackers:
                    rx_keys[phase].add((src_node, seq))
                continue

            if tag == "ROUTE" and len(parts) >= 11:
                try:
                    node_id = int(parts[2])
                    tick = int(parts[3])
                    parent_id = int(parts[4])
                    switch_count = int(parts[7])
                    parent_is_attacker = int(parts[9])
                except ValueError:
                    continue

                phase = phase_of_tick(tick)
                if node_id == root_id or node_id in attackers:
                    switch_state[node_id] = switch_count
                    continue

                if phase == "during":
                    route_total_during += 1
                    nodes_seen_during.add(node_id)
                    if parent_is_attacker == 1 or parent_id in attackers:
                        route_att_during += 1
                        nodes_hit_during.add(node_id)

                prev = switch_state.get(node_id)
                if prev is not None and phase == "during" and switch_count > prev:
                    churn_increase_during += (switch_count - prev)
                switch_state[node_id] = switch_count

    tx_pre = len(tx_keys["pre"])
    tx_dur = len(tx_keys["during"])
    rx_pre = len(tx_keys["pre"] & rx_keys["pre"])
    rx_dur = len(tx_keys["during"] & rx_keys["during"])

    pdr_pre = (rx_pre / tx_pre) if tx_pre > 0 else float("nan")
    pdr_dur = (rx_dur / tx_dur) if tx_dur > 0 else float("nan")

    att_share = (
        route_att_during / route_total_during if route_total_during > 0 else float("nan")
    )
    hit_ratio = (
        len(nodes_hit_during) / len(nodes_seen_during)
        if nodes_seen_during
        else float("nan")
    )
    churn = (
        churn_increase_during / len(nodes_seen_during)
        if nodes_seen_during
        else float("nan")
    )

    return {
        "pdr_pre": pdr_pre,
        "pdr_dur": pdr_dur,
        "att_share": att_share,
        "hit_ratio": hit_ratio,
        "churn": churn,
        "n_attackers": float(len(attackers)),
        "n_senders_seen": float(len(nodes_seen_during)),
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        if fieldnames is None:
            fieldnames = []
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if fieldnames:
                w.writeheader()
        return

    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def build_topology_rows(run_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in run_rows:
        grouped[(r["density"], r["topology"], r["protocol"])].append(r)

    out = []
    for (density, topology, protocol), rows in sorted(grouped.items()):
        out.append(
            {
                "density": density,
                "topology": topology,
                "protocol": protocol,
                "n_runs": len(rows),
                "pdr_pre": safe_mean([x["pdr_pre"] for x in rows]),
                "pdr_dur": safe_mean([x["pdr_dur"] for x in rows]),
                "att_share": safe_mean([x["att_share"] for x in rows]),
                "hit_ratio": safe_mean([x["hit_ratio"] for x in rows]),
                "churn": safe_mean([x["churn"] for x in rows]),
            }
        )
    return out


def build_paired_rows(topo_rows: list[dict], proto_a: str, proto_b: str) -> list[dict]:
    idx = {
        (r["density"], r["topology"], r["protocol"]): r
        for r in topo_rows
    }
    keys = sorted({(r["density"], r["topology"]) for r in topo_rows})
    out = []
    for density, topology in keys:
        a = idx.get((density, topology, proto_a))
        b = idx.get((density, topology, proto_b))
        if a is None or b is None:
            continue
        out.append(
            {
                "density": density,
                "topology": topology,
                "a_protocol": proto_a,
                "b_protocol": proto_b,
                "a_pdr_dur": a["pdr_dur"],
                "b_pdr_dur": b["pdr_dur"],
                "a_att_share": a["att_share"],
                "b_att_share": b["att_share"],
                "a_hit_ratio": a["hit_ratio"],
                "b_hit_ratio": b["hit_ratio"],
                "a_churn": a["churn"],
                "b_churn": b["churn"],
                "delta_pdr_dur": a["pdr_dur"] - b["pdr_dur"],
                "delta_att_share": a["att_share"] - b["att_share"],
                "delta_hit_ratio": a["hit_ratio"] - b["hit_ratio"],
                "delta_churn": a["churn"] - b["churn"],
            }
        )
    return out


def summarize_pairs(
    rows: list[dict],
    pdr_margin: float,
    *,
    bootstrap_resamples: int,
) -> list[dict]:
    densities = sorted({r["density"] for r in rows})
    scopes = densities + ["overall"]
    out = []
    for scope in scopes:
        scoped = rows if scope == "overall" else [r for r in rows if r["density"] == scope]
        if not scoped:
            continue

        d_att = [r["delta_att_share"] for r in scoped]
        d_hit = [r["delta_hit_ratio"] for r in scoped]
        d_churn = [r["delta_churn"] for r in scoped]
        d_pdr = [r["delta_pdr_dur"] for r in scoped]

        m_att, lo_att, hi_att = bootstrap_mean_ci(d_att, n_resamples=bootstrap_resamples)
        m_hit, lo_hit, hi_hit = bootstrap_mean_ci(d_hit, n_resamples=bootstrap_resamples)
        m_ch, lo_ch, hi_ch = bootstrap_mean_ci(d_churn, n_resamples=bootstrap_resamples)
        m_pdr, lo_pdr, hi_pdr = bootstrap_mean_ci(d_pdr, n_resamples=bootstrap_resamples)

        n = len(scoped)
        out.append(
            {
                "scope": scope,
                "n_topologies": n,
                "mean_att_share_a": safe_mean([r["a_att_share"] for r in scoped]),
                "mean_att_share_b": safe_mean([r["b_att_share"] for r in scoped]),
                "delta_att_share_mean": m_att,
                "delta_att_share_ci_lo": lo_att,
                "delta_att_share_ci_hi": hi_att,
                "mean_hit_ratio_a": safe_mean([r["a_hit_ratio"] for r in scoped]),
                "mean_hit_ratio_b": safe_mean([r["b_hit_ratio"] for r in scoped]),
                "delta_hit_ratio_mean": m_hit,
                "delta_hit_ratio_ci_lo": lo_hit,
                "delta_hit_ratio_ci_hi": hi_hit,
                "mean_churn_a": safe_mean([r["a_churn"] for r in scoped]),
                "mean_churn_b": safe_mean([r["b_churn"] for r in scoped]),
                "delta_churn_mean": m_ch,
                "delta_churn_ci_lo": lo_ch,
                "delta_churn_ci_hi": hi_ch,
                "mean_pdr_dur_a": safe_mean([r["a_pdr_dur"] for r in scoped]),
                "mean_pdr_dur_b": safe_mean([r["b_pdr_dur"] for r in scoped]),
                "delta_pdr_dur_mean": m_pdr,
                "delta_pdr_dur_ci_lo": lo_pdr,
                "delta_pdr_dur_ci_hi": hi_pdr,
                "win_rate_att_share": sum(1 for x in d_att if x < 0.0) / n,
                "win_rate_hit_ratio": sum(1 for x in d_hit if x <= 0.0) / n,
                "win_rate_churn": sum(1 for x in d_churn if x < 0.0) / n,
                "win_rate_pdr_dur": sum(1 for x in d_pdr if x > 0.0) / n,
                "pdr_noninferior_rate": sum(1 for x in d_pdr if x >= pdr_margin) / n,
                "pdr_noninferior_by_ci": 1.0 if lo_pdr > pdr_margin else 0.0,
            }
        )
    return out


def make_fig_att_share_box(
    paired_rows: list[dict], fig_path: Path, proto_a: str, proto_b: str
) -> None:
    densities = sorted({r["density"] for r in paired_rows})
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    width = 0.28

    for i, density in enumerate(densities):
        scoped = [r for r in paired_rows if r["density"] == density]
        b_vals = [r["b_att_share"] for r in scoped]
        a_vals = [r["a_att_share"] for r in scoped]

        pos_b = i - width / 2
        pos_a = i + width / 2
        bp_b = ax.boxplot(
            [b_vals],
            positions=[pos_b],
            widths=width * 0.9,
            patch_artist=True,
            showfliers=False,
        )
        bp_a = ax.boxplot(
            [a_vals],
            positions=[pos_a],
            widths=width * 0.9,
            patch_artist=True,
            showfliers=False,
        )
        for box in bp_b["boxes"]:
            box.set(facecolor="#f97316", alpha=0.65)
        for box in bp_a["boxes"]:
            box.set(facecolor="#2563eb", alpha=0.65)

    ax.set_xticks(range(len(densities)))
    ax.set_xticklabels(densities)
    ax.set_ylabel("att_share (topology mean)")
    ax.set_title(f"att_share by density ({proto_a} vs {proto_b})")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(
        handles=[
            plt.Line2D([0], [0], color="#2563eb", lw=10, alpha=0.65),
            plt.Line2D([0], [0], color="#f97316", lw=10, alpha=0.65),
        ],
        labels=[proto_a, proto_b],
        frameon=False,
        loc="upper right",
    )
    fig.tight_layout()
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_path)
    plt.close(fig)


def make_fig_delta_ci(summary_rows: list[dict], fig_path: Path) -> None:
    scopes = [r["scope"] for r in summary_rows]
    x = np.arange(len(scopes))
    fig, ax = plt.subplots(figsize=(10.2, 5.0))

    specs = [
        ("delta_att_share", "#2563eb", "att_share Δ"),
        ("delta_hit_ratio", "#16a34a", "hit_ratio Δ"),
        ("delta_churn", "#dc2626", "churn Δ"),
    ]
    offsets = [-0.2, 0.0, 0.2]
    for (base, color, label), off in zip(specs, offsets):
        y = [r[f"{base}_mean"] for r in summary_rows]
        lo = [r[f"{base}_ci_lo"] for r in summary_rows]
        hi = [r[f"{base}_ci_hi"] for r in summary_rows]
        yerr = np.vstack([np.array(y) - np.array(lo), np.array(hi) - np.array(y)])
        ax.errorbar(
            x + off,
            y,
            yerr=yerr,
            fmt="o",
            color=color,
            capsize=3,
            label=label,
        )

    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(scopes)
    ax.set_ylabel("Delta (A - B)")
    ax.set_title("Topology-paired delta with bootstrap 95% CI")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=3, loc="upper right")
    fig.tight_layout()
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_path)
    plt.close(fig)


def make_fig_pdr_noninferiority(
    summary_rows: list[dict], fig_path: Path, pdr_margin: float
) -> None:
    scopes = [r["scope"] for r in summary_rows]
    x = np.arange(len(scopes))
    y = [r["delta_pdr_dur_mean"] for r in summary_rows]
    lo = [r["delta_pdr_dur_ci_lo"] for r in summary_rows]
    hi = [r["delta_pdr_dur_ci_hi"] for r in summary_rows]
    yerr = np.vstack([np.array(y) - np.array(lo), np.array(hi) - np.array(y)])

    fig, ax = plt.subplots(figsize=(9.8, 4.8))
    ax.errorbar(x, y, yerr=yerr, fmt="o", capsize=4, color="#7c3aed")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.axhline(pdr_margin, color="#ef4444", linewidth=1.0, linestyle="--")
    ax.text(
        len(scopes) - 0.05,
        pdr_margin + 0.001,
        f"non-inferiority margin ({pdr_margin:+.2f})",
        ha="right",
        va="bottom",
        fontsize=9,
        color="#ef4444",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(scopes)
    ax.set_ylabel("ΔPDR_dur (A - B)")
    ax.set_title("PDR_dur non-inferiority check")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_path)
    plt.close(fig)


def make_fig_winrate_heatmap(summary_rows: list[dict], fig_path: Path) -> None:
    scopes = [r["scope"] for r in summary_rows]
    metrics = [
        ("win_rate_att_share", "att_share (lower better)"),
        ("win_rate_hit_ratio", "hit_ratio (lower better)"),
        ("win_rate_churn", "churn (lower better)"),
        ("win_rate_pdr_dur", "PDR_dur (higher better)"),
        ("pdr_noninferior_rate", "PDR non-inferior"),
    ]
    mat = np.array([[r[k] for r in summary_rows] for k, _ in metrics], dtype=float)

    fig, ax = plt.subplots(figsize=(10.0, 4.7))
    im = ax.imshow(mat, vmin=0.0, vmax=1.0, cmap="YlGn")
    ax.set_xticks(np.arange(len(scopes)))
    ax.set_xticklabels(scopes)
    ax.set_yticks(np.arange(len(metrics)))
    ax.set_yticklabels([label for _, label in metrics])
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i, j]*100:.0f}%", ha="center", va="center", fontsize=9)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.03)
    cbar.set_label("Win-rate")
    ax.set_title("Topology win-rate heatmap")
    fig.tight_layout()
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_path)
    plt.close(fig)


def write_latex_snippet(
    path: Path,
    summary_rows: list[dict],
    fig_rel_dir: str,
    proto_a: str,
    proto_b: str,
) -> None:
    idx = {r["scope"]: r for r in summary_rows}
    overall = idx.get("overall")

    lines = []
    lines.append("% Auto-generated by docs/paper/generate_main_experiment_artifacts.py")
    lines.append("\\subsection{Main Experiment Snapshot (Auto-generated)}")
    if overall is not None:
        lines.append(
            "Primary summary (overall): "
            f"$\\Delta$att\\_share={fmt(overall['delta_att_share_mean'], 4)} "
            f"[{fmt(overall['delta_att_share_ci_lo'], 4)}, {fmt(overall['delta_att_share_ci_hi'], 4)}], "
            f"$\\Delta$hit\\_ratio={fmt(overall['delta_hit_ratio_mean'], 4)} "
            f"[{fmt(overall['delta_hit_ratio_ci_lo'], 4)}, {fmt(overall['delta_hit_ratio_ci_hi'], 4)}]. "
            f"Win-rate(att\\_share)={overall['win_rate_att_share']*100:.1f}\\%."
        )
        lines.append("")

    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append(
        "\\caption{Topology-paired summary by density "
        + f"($\\Delta = {proto_a} - {proto_b}$)"
        + "}"
    )
    lines.append("\\label{tab:main_auto_summary}")
    lines.append("\\begin{tabular}{lcccc}")
    lines.append("\\toprule")
    lines.append("Scope & $\\Delta$att\\_share & $\\Delta$hit\\_ratio & $\\Delta$churn & $\\Delta$PDR\\_dur \\\\")
    lines.append("\\midrule")
    for r in summary_rows:
        lines.append(
            f"{r['scope']} & "
            f"{fmt(r['delta_att_share_mean'], 4)} & "
            f"{fmt(r['delta_hit_ratio_mean'], 4)} & "
            f"{fmt(r['delta_churn_mean'], 3)} & "
            f"{fmt(r['delta_pdr_dur_mean'], 4)} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    lines.append("")

    fig_map = [
        ("fig3_att_share_box_by_density.pdf", "att\\_share boxplot by density."),
        ("fig4_delta_ci.pdf", "Primary/secondary deltas with bootstrap 95\\% CI."),
        ("fig5_pdr_noninferiority.pdf", "PDR\\_dur non-inferiority check."),
        ("fig6_winrate_heatmap.pdf", "Win-rate heatmap across densities."),
    ]
    for fname, cap in fig_map:
        lines.append("\\begin{figure}[t]")
        lines.append("\\centering")
        lines.append(f"\\includegraphics[width=0.92\\linewidth]{{{fig_rel_dir}/{fname}}}")
        lines.append(f"\\caption{{{cap}}}")
        lines.append("\\end{figure}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def collect_run_rows(results_dir: Path, protocols: set[str]) -> list[dict]:
    rows = []
    for simlog in sorted(results_dir.glob("*/*/*/*/sim.log")):
        density = simlog.parents[3].name
        topology = simlog.parents[2].name
        protocol = simlog.parents[1].name.upper()
        run_seed = simlog.parents[0].name
        if protocol not in protocols:
            continue
        if not (simlog.parent / "done").exists():
            continue

        m = parse_simlog(simlog)
        rows.append(
            {
                "density": density,
                "topology": topology,
                "protocol": protocol,
                "run_seed": run_seed,
                **m,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate main-experiment paper artifacts")
    ap.add_argument("--results-dir", default="results/random_topo")
    ap.add_argument("--proto-a", default="TABRPL")
    ap.add_argument("--proto-b", default="BRPL")
    ap.add_argument("--fig-dir", default="docs/paper/figures/new/main")
    ap.add_argument("--out-dir", default="docs/paper/generated/main")
    ap.add_argument("--pdr-ni-margin", type=float, default=-0.02)
    ap.add_argument("--bootstrap-resamples", type=int, default=10_000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    results_dir = (root / args.results_dir).resolve()
    fig_dir = (root / args.fig_dir).resolve()
    out_dir = (root / args.out_dir).resolve()

    proto_a = args.proto_a.upper()
    proto_b = args.proto_b.upper()

    run_rows = collect_run_rows(results_dir, {proto_a, proto_b})
    if not run_rows:
        raise SystemExit(f"No completed runs found under: {results_dir}")

    topo_rows = build_topology_rows(run_rows)
    paired_rows = build_paired_rows(topo_rows, proto_a, proto_b)
    summary_rows = summarize_pairs(
        paired_rows,
        args.pdr_ni_margin,
        bootstrap_resamples=args.bootstrap_resamples,
    )

    write_csv(out_dir / "metrics_by_run.csv", run_rows)
    write_csv(out_dir / "metrics_by_topology.csv", topo_rows)
    write_csv(out_dir / "paired_deltas_by_topology.csv", paired_rows)
    write_csv(out_dir / "summary_by_density.csv", summary_rows)

    make_fig_att_share_box(
        paired_rows, fig_dir / "fig3_att_share_box_by_density.pdf", proto_a, proto_b
    )
    make_fig_delta_ci(summary_rows, fig_dir / "fig4_delta_ci.pdf")
    make_fig_pdr_noninferiority(
        summary_rows, fig_dir / "fig5_pdr_noninferiority.pdf", args.pdr_ni_margin
    )
    make_fig_winrate_heatmap(summary_rows, fig_dir / "fig6_winrate_heatmap.pdf")

    # `paper.tex` uses \graphicspath{{figures/new/}...}, so use "main/<file>" here.
    write_latex_snippet(
        out_dir / "main_results_auto.tex",
        summary_rows,
        "main",
        proto_a,
        proto_b,
    )

    print(f"[OK] results-dir : {results_dir}")
    print(f"[OK] out-dir     : {out_dir}")
    print(f"[OK] fig-dir     : {fig_dir}")
    print(f"[OK] pairs       : {len(paired_rows)} topology pairs")

    overall = next((r for r in summary_rows if r["scope"] == "overall"), None)
    if overall:
        print(
            "[SUMMARY] "
            f"Delta(att_share)={overall['delta_att_share_mean']:+.4f} "
            f"[{overall['delta_att_share_ci_lo']:+.4f}, {overall['delta_att_share_ci_hi']:+.4f}], "
            f"Delta(hit_ratio)={overall['delta_hit_ratio_mean']:+.4f}, "
            f"Delta(churn)={overall['delta_churn_mean']:+.3f}, "
            f"Delta(PDR_dur)={overall['delta_pdr_dur_mean']:+.4f}"
        )


if __name__ == "__main__":
    main()
