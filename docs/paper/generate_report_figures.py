#!/usr/bin/env python3
r"""Generate a large report-oriented figure set for main.tex."""

from __future__ import annotations

import csv
import math
import os
import re
from collections import defaultdict
from pathlib import Path

if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "docs" / "paper" / "figures" / "report"
OUT_DIR = ROOT / "docs" / "paper" / "generated" / "report"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(row: dict, key: str, default: float = float("nan")) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def safe_mean(xs: list[float]) -> float:
    vals = [x for x in xs if not math.isnan(x)]
    if not vals:
        return float("nan")
    return float(sum(vals) / len(vals))


def version_sort_key(name: str) -> tuple:
    if name == "sinkhole_sweep":
        return (1, 0, 0, name)
    if name == "sinkhole_sweep_policy_v2":
        return (2, 0, 0, name)
    if name == "sinkhole_sweep_policy_v3":
        return (3, 0, 0, name)
    if name == "sinkhole_sweep_policy_v4_tj510":
        return (4, 10, 0, name)
    if name == "sinkhole_sweep_policy_v5_ctrl_escape":
        return (5, 0, 0, name)
    if name == "sinkhole_sweep_policy_v6_cond_evict":
        return (6, 0, 0, name)
    if name == "sinkhole_sweep_policy_v7_soft_release":
        return (7, 0, 0, name)
    if name == "sinkhole_sweep_policy_v8a":
        return (8, 1, 0, name)
    if name == "sinkhole_sweep_policy_v8b":
        return (8, 2, 0, name)
    if name == "sinkhole_sweep_policy_v9":
        return (9, 0, 0, name)
    if name == "sinkhole_sweep_policy_v10":
        return (10, 0, 0, name)
    if name == "sinkhole_sweep_policy_v11_grid5":
        return (11, 0, 0, name)
    if name == "sinkhole_sweep_policy_v12_grid5":
        return (12, 0, 0, name)
    if name == "sinkhole_sweep_policy_v13_8_lossgate_full40":
        return (13, 8, 0, name)
    if name == "sinkhole_sweep_policy_v13_12_escapecool360_full40":
        return (13, 12, 0, name)

    m = re.search(r"v(\d+)(?:_(\d+))?", name)
    if m:
        major = int(m.group(1))
        minor = int(m.group(2)) if m.group(2) else 0
        return (major, minor, 1, name)
    return (999, 0, 0, name)


def pretty_name(name: str) -> str:
    mapping = {
        "sinkhole_sweep": "v1",
        "sinkhole_sweep_policy_v2": "v2",
        "sinkhole_sweep_policy_v3": "v3",
        "sinkhole_sweep_policy_v4_tj510": "v4(tj510)",
        "sinkhole_sweep_policy_v5_ctrl_escape": "v5",
        "sinkhole_sweep_policy_v6_cond_evict": "v6",
        "sinkhole_sweep_policy_v7_soft_release": "v7",
        "sinkhole_sweep_policy_v8a": "v8a",
        "sinkhole_sweep_policy_v8b": "v8b",
        "sinkhole_sweep_policy_v9": "v9",
        "sinkhole_sweep_policy_v10": "v10",
        "sinkhole_sweep_policy_v11_grid5": "v11(grid5)",
        "sinkhole_sweep_policy_v12_grid5": "v12(grid5)",
        "sinkhole_sweep_policy_v13_8_lossgate_full40": "v13.8(full40)",
        "sinkhole_sweep_policy_v13_12_escapecool360_full40": "v13.12(full40)",
    }
    return mapping.get(name, name.replace("sinkhole_sweep_policy_", ""))


def collect_version_rows() -> list[dict]:
    rows = []
    for summary in sorted((ROOT / "results").glob("sinkhole_sweep*/summary.csv")):
        label = summary.parent.name
        csv_rows = read_csv(summary)
        idx = {(r["topo"], r["proto"], r["scenario"]): r for r in csv_rows}
        keys = sorted({(r["topo"], r["scenario"]) for r in csv_rows})
        deltas = []
        for topo, scenario in keys:
            b = idx.get((topo, "BRPL", scenario))
            t = idx.get((topo, "TABRPL", scenario))
            if not b or not t:
                continue
            deltas.append(
                {
                    "topo": topo,
                    "scenario": scenario,
                    "d_pdr": to_float(t, "pdr_dur") - to_float(b, "pdr_dur"),
                    "d_att": to_float(t, "att_share") - to_float(b, "att_share"),
                    "d_hit": to_float(t, "hit_ratio") - to_float(b, "hit_ratio"),
                    "d_churn": to_float(t, "churn") - to_float(b, "churn"),
                }
            )
        if not deltas:
            continue
        rows.append(
            {
                "label": label,
                "label_pretty": pretty_name(label),
                "n_cells": len(deltas),
                "d_pdr": safe_mean([d["d_pdr"] for d in deltas]),
                "d_att": safe_mean([d["d_att"] for d in deltas]),
                "d_hit": safe_mean([d["d_hit"] for d in deltas]),
                "d_churn": safe_mean([d["d_churn"] for d in deltas]),
            }
        )
    rows.sort(key=lambda r: version_sort_key(r["label"]))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

def tex_escape(s: str) -> str:
    """Escape a minimal set of LaTeX special characters for table text."""
    return (
        s.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def fig_r01_version_heatmap(version_rows: list[dict]) -> None:
    selected = [
        "sinkhole_sweep",
        "sinkhole_sweep_policy_v2",
        "sinkhole_sweep_policy_v3",
        "sinkhole_sweep_policy_v4_tj510",
        "sinkhole_sweep_policy_v5_ctrl_escape",
        "sinkhole_sweep_policy_v6_cond_evict",
        "sinkhole_sweep_policy_v7_soft_release",
        "sinkhole_sweep_policy_v8a",
        "sinkhole_sweep_policy_v9",
        "sinkhole_sweep_policy_v10",
        "sinkhole_sweep_policy_v11_grid5",
        "sinkhole_sweep_policy_v12_grid5",
        "sinkhole_sweep_policy_v13_8_lossgate_full40",
        "sinkhole_sweep_policy_v13_12_escapecool360_full40",
    ]
    idx = {r["label"]: r for r in version_rows}
    kept = [idx[s] for s in selected if s in idx]
    if not kept:
        return

    mat = np.array(
        [[r["d_att"], r["d_hit"], r["d_churn"], r["d_pdr"]] for r in kept],
        dtype=float,
    )
    names = [r["label_pretty"] for r in kept]
    cols = ["Δatt_share", "Δhit_ratio", "Δchurn", "ΔPDR_dur"]

    fig, ax = plt.subplots(figsize=(10.0, 6.5))
    im = ax.imshow(mat, cmap="RdYlGn_r", aspect="auto")
    ax.set_yticks(np.arange(len(names)))
    ax.set_yticklabels(names)
    ax.set_xticks(np.arange(len(cols)))
    ax.set_xticklabels(cols)
    ax.set_title("v1~v13 average gap heatmap (TA-BRPL - BRPL)")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i, j]:+.3f}", ha="center", va="center", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Gap value")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r01_version_delta_heatmap.pdf")
    plt.close(fig)


def fig_r02_version_trends(version_rows: list[dict]) -> None:
    selected = [
        r for r in version_rows
        if r["label"] in {
            "sinkhole_sweep",
            "sinkhole_sweep_policy_v2",
            "sinkhole_sweep_policy_v3",
            "sinkhole_sweep_policy_v4_tj510",
            "sinkhole_sweep_policy_v5_ctrl_escape",
            "sinkhole_sweep_policy_v6_cond_evict",
            "sinkhole_sweep_policy_v7_soft_release",
            "sinkhole_sweep_policy_v8a",
            "sinkhole_sweep_policy_v9",
            "sinkhole_sweep_policy_v10",
            "sinkhole_sweep_policy_v11_grid5",
            "sinkhole_sweep_policy_v12_grid5",
            "sinkhole_sweep_policy_v13_8_lossgate_full40",
            "sinkhole_sweep_policy_v13_12_escapecool360_full40",
        }
    ]
    if not selected:
        return
    x = np.arange(len(selected))
    labels = [r["label_pretty"] for r in selected]
    fig, ax = plt.subplots(figsize=(11.0, 4.8))
    ax.plot(x, [r["d_att"] for r in selected], marker="o", label="Δatt_share")
    ax.plot(x, [r["d_hit"] for r in selected], marker="o", label="Δhit_ratio")
    ax.plot(x, [r["d_churn"] for r in selected], marker="o", label="Δchurn")
    ax.plot(x, [r["d_pdr"] for r in selected], marker="o", label="ΔPDR_dur")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_title("Average gap trend by version (v1 -> v13.12)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r02_version_delta_trends.pdf")
    plt.close(fig)


def load_summary_idx(path: Path) -> dict:
    rows = read_csv(path)
    return {(r["topo"], r["proto"], r["scenario"]): r for r in rows}


def fig_r03_to_r05_v13_cell_comparison() -> None:
    v138 = ROOT / "results" / "sinkhole_sweep_policy_v13_8_lossgate_full40" / "summary.csv"
    v1312 = ROOT / "results" / "sinkhole_sweep_policy_v13_12_escapecool360_full40" / "summary.csv"
    if not v138.exists() or not v1312.exists():
        return

    i138 = load_summary_idx(v138)
    i1312 = load_summary_idx(v1312)
    cells = [("GRID", "SINK_ONLY"), ("GRID", "SINK_DROP50"), ("BOTTLE", "SINK_ONLY"), ("BOTTLE", "SINK_DROP50")]
    labels = [f"{t}-{s.replace('SINK_', '')}" for t, s in cells]

    def plot_metric(metric: str, out_name: str, title: str, ylab: str) -> None:
        x = np.arange(len(cells))
        w = 0.25
        brpl = [to_float(i1312[(t, "BRPL", s)], metric) for t, s in cells]
        v8 = [to_float(i138[(t, "TABRPL", s)], metric) for t, s in cells]
        v12 = [to_float(i1312[(t, "TABRPL", s)], metric) for t, s in cells]
        fig, ax = plt.subplots(figsize=(10.2, 4.4))
        ax.bar(x - w, brpl, width=w, label="BRPL", color="#f97316")
        ax.bar(x, v8, width=w, label="TA v13.8", color="#60a5fa")
        ax.bar(x + w, v12, width=w, label="TA v13.12", color="#2563eb")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel(ylab)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False, ncol=3)
        fig.tight_layout()
        fig.savefig(FIG_DIR / out_name)
        plt.close(fig)

    plot_metric("att_share", "fig_r03_v13_cell_att_share.pdf", "Cell-wise attacker parent share", "att_share")
    plot_metric("churn", "fig_r04_v13_cell_churn.pdf", "Cell-wise churn", "churn")
    plot_metric("pdr_dur", "fig_r05_v13_cell_pdr_dur.pdf", "Cell-wise PDR_dur", "PDR_dur")


def fig_r06_main_abs_by_density() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "summary_by_density.csv"
    if not path.exists():
        return
    rows = [r for r in read_csv(path) if r["scope"] in {"dense", "medium", "sparse"}]
    order = ["sparse", "medium", "dense"]
    rows.sort(key=lambda r: order.index(r["scope"]))

    x = np.arange(len(rows))
    w = 0.18
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.0))
    panels = [
        ("mean_att_share_a", "mean_att_share_b", "att_share"),
        ("mean_hit_ratio_a", "mean_hit_ratio_b", "hit_ratio"),
        ("mean_churn_a", "mean_churn_b", "churn"),
        ("mean_pdr_dur_a", "mean_pdr_dur_b", "PDR_dur"),
    ]
    for ax, (ka, kb, ttl) in zip(axes.flatten(), panels):
        a = [to_float(r, ka) for r in rows]
        b = [to_float(r, kb) for r in rows]
        ax.bar(x - w / 2, b, width=w, label="BRPL", color="#f97316")
        ax.bar(x + w / 2, a, width=w, label="TABRPL", color="#2563eb")
        ax.set_xticks(x)
        ax.set_xticklabels([r["scope"] for r in rows])
        ax.set_title(ttl)
        ax.grid(axis="y", alpha=0.25)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Main random-topology: absolute metrics by density")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r06_main_density_abs_metrics.pdf")
    plt.close(fig)


def fig_r07_main_delta_ci() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "summary_by_density.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    order = ["sparse", "medium", "dense", "overall"]
    rows = [r for r in rows if r["scope"] in order]
    rows.sort(key=lambda r: order.index(r["scope"]))
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(10.8, 5.0))
    specs = [
        ("delta_att_share", "#2563eb"),
        ("delta_hit_ratio", "#16a34a"),
        ("delta_churn", "#dc2626"),
        ("delta_pdr_dur", "#7c3aed"),
    ]
    offs = [-0.24, -0.08, 0.08, 0.24]
    for (base, color), off in zip(specs, offs):
        y = [to_float(r, f"{base}_mean") for r in rows]
        lo = [to_float(r, f"{base}_ci_lo") for r in rows]
        hi = [to_float(r, f"{base}_ci_hi") for r in rows]
        yerr = np.vstack([np.array(y) - np.array(lo), np.array(hi) - np.array(y)])
        ax.errorbar(x + off, y, yerr=yerr, fmt="o", capsize=3, color=color, label=base)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([r["scope"] for r in rows])
    ax.set_title("Main random-topology: delta with 95% CI by density")
    ax.set_ylabel("Δ (TABRPL - BRPL)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r07_main_density_delta_ci.pdf")
    plt.close(fig)


def fig_r08_main_delta_cdf() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "paired_deltas_by_topology.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    metrics = [
        ("delta_att_share", "Δatt_share"),
        ("delta_hit_ratio", "Δhit_ratio"),
        ("delta_churn", "Δchurn"),
        ("delta_pdr_dur", "ΔPDR_dur"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.2))
    for ax, (k, ttl) in zip(axes.flatten(), metrics):
        vals = sorted([to_float(r, k) for r in rows])
        if not vals:
            continue
        y = np.arange(1, len(vals) + 1) / len(vals)
        ax.plot(vals, y, linewidth=2.0)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title(ttl)
        ax.grid(alpha=0.25)
        ax.set_ylim(0, 1.02)
    fig.suptitle("Topology-paired delta CDF")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r08_main_topology_delta_cdf.pdf")
    plt.close(fig)


def fig_r09_main_tradeoff_scatter() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "paired_deltas_by_topology.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    colors = {"sparse": "#16a34a", "medium": "#2563eb", "dense": "#dc2626"}
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    for d in ["sparse", "medium", "dense"]:
        scoped = [r for r in rows if r["density"] == d]
        x = [to_float(r, "delta_att_share") for r in scoped]
        y = [to_float(r, "delta_churn") for r in scoped]
        ax.scatter(x, y, label=d, alpha=0.75, s=40, color=colors[d])
    ax.axvline(0, color="black", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Δatt_share (lower better)")
    ax.set_ylabel("Δchurn (lower better)")
    ax.set_title("Isolation-cost trade-off by topology")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r09_main_tradeoff_scatter.pdf")
    plt.close(fig)


def fig_r10_main_winrate_heatmap() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "summary_by_density.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    order = ["sparse", "medium", "dense", "overall"]
    rows = [r for r in rows if r["scope"] in order]
    rows.sort(key=lambda r: order.index(r["scope"]))
    metrics = [
        ("win_rate_att_share", "att_share"),
        ("win_rate_hit_ratio", "hit_ratio"),
        ("win_rate_churn", "churn"),
        ("win_rate_pdr_dur", "pdr_dur"),
        ("pdr_noninferior_rate", "pdr NI"),
    ]
    mat = np.array([[to_float(r, m) for r in rows] for m, _ in metrics], dtype=float)
    fig, ax = plt.subplots(figsize=(9.8, 4.8))
    im = ax.imshow(mat, vmin=0, vmax=1, cmap="YlGn")
    ax.set_xticks(np.arange(len(rows)))
    ax.set_xticklabels([r["scope"] for r in rows])
    ax.set_yticks(np.arange(len(metrics)))
    ax.set_yticklabels([n for _, n in metrics])
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i,j]*100:.0f}%", ha="center", va="center", fontsize=9)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Win-rate")
    ax.set_title("Win-rate / non-inferiority by density")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r10_main_winrate_heatmap.pdf")
    plt.close(fig)


def fig_r11_r12_run_boxplots() -> None:
    path = ROOT / "docs" / "paper" / "generated" / "main" / "metrics_by_run.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    densities = ["sparse", "medium", "dense"]

    def plot(metric: str, out_name: str, title: str) -> None:
        fig, ax = plt.subplots(figsize=(11.0, 4.8))
        positions = []
        data = []
        labels = []
        p = 0
        for d in densities:
            for proto in ["BRPL", "TABRPL"]:
                vals = [to_float(r, metric) for r in rows if r["density"] == d and r["protocol"] == proto]
                data.append(vals)
                positions.append(p)
                labels.append(f"{d}\n{proto}")
                p += 1
            p += 0.7
        bp = ax.boxplot(data, positions=positions, widths=0.55, patch_artist=True, showfliers=False)
        for i, box in enumerate(bp["boxes"]):
            if "BRPL" in labels[i]:
                box.set(facecolor="#f97316", alpha=0.6)
            else:
                box.set(facecolor="#2563eb", alpha=0.6)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIG_DIR / out_name)
        plt.close(fig)

    plot("att_share", "fig_r11_main_run_box_att_share.pdf", "Run-level att_share distribution (density x protocol)")
    plot("pdr_dur", "fig_r12_main_run_box_pdr_dur.pdf", "Run-level PDR_dur distribution (density x protocol)")


def fig_r13_quickcheck_vs_main() -> None:
    q = ROOT / "docs" / "paper" / "generated" / "main_quickcheck" / "summary_by_density.csv"
    m = ROOT / "docs" / "paper" / "generated" / "main" / "summary_by_density.csv"
    if not q.exists() or not m.exists():
        return
    qrow = next((r for r in read_csv(q) if r["scope"] == "overall"), None)
    mrow = next((r for r in read_csv(m) if r["scope"] == "overall"), None)
    if not qrow or not mrow:
        return
    metrics = ["delta_att_share_mean", "delta_hit_ratio_mean", "delta_churn_mean", "delta_pdr_dur_mean"]
    x = np.arange(len(metrics))
    w = 0.35
    qv = [to_float(qrow, k) for k in metrics]
    mv = [to_float(mrow, k) for k in metrics]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.bar(x - w / 2, qv, width=w, label="quickcheck", color="#94a3b8")
    ax.bar(x + w / 2, mv, width=w, label="main(750)", color="#2563eb")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(["Δatt", "Δhit", "Δchurn", "Δpdr"])
    ax.set_title("Quickcheck vs main experiment: overall average gap")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r13_quickcheck_vs_main.pdf")
    plt.close(fig)


def write_tex_tables(version_rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selected_labels = {
        "sinkhole_sweep",
        "sinkhole_sweep_policy_v2",
        "sinkhole_sweep_policy_v3",
        "sinkhole_sweep_policy_v4_tj510",
        "sinkhole_sweep_policy_v5_ctrl_escape",
        "sinkhole_sweep_policy_v6_cond_evict",
        "sinkhole_sweep_policy_v7_soft_release",
        "sinkhole_sweep_policy_v8a",
        "sinkhole_sweep_policy_v9",
        "sinkhole_sweep_policy_v10",
        "sinkhole_sweep_policy_v11_grid5",
        "sinkhole_sweep_policy_v12_grid5",
        "sinkhole_sweep_policy_v13_8_lossgate_full40",
        "sinkhole_sweep_policy_v13_12_escapecool360_full40",
    }
    selected = [r for r in version_rows if r["label"] in selected_labels]

    t1 = []
    t1.append("% Auto-generated: key version delta table")
    t1.append("\\begin{table}[t]")
    t1.append("\\centering")
    t1.append("\\caption{주요 버전 평균 갭 요약 ($\\Delta$=TA-BRPL-BRPL)}")
    t1.append("\\label{tab:key_version_delta}")
    t1.append("\\begin{tabular}{lrrrrr}")
    t1.append("\\toprule")
    t1.append("Version & Cells & $\\Delta$att & $\\Delta$hit & $\\Delta$churn & $\\Delta$PDR \\\\")
    t1.append("\\midrule")
    for r in selected:
        label = tex_escape(r["label_pretty"])
        t1.append(
            f"{label} & {int(r['n_cells'])} & "
            f"{r['d_att']:+.4f} & {r['d_hit']:+.4f} & {r['d_churn']:+.2f} & {r['d_pdr']:+.4f} \\\\"
        )
    t1.append("\\bottomrule")
    t1.append("\\end{tabular}")
    t1.append("\\end{table}")
    (OUT_DIR / "table_key_versions.tex").write_text("\n".join(t1), encoding="utf-8")

    # all versions appendix table
    t2 = []
    t2.append("% Auto-generated: all version delta table")
    t2.append("\\begin{longtable}{lrrrrr}")
    t2.append("\\caption{전체 버전 평균 갭 목록 ($\\Delta$=TA-BRPL-BRPL)}\\label{tab:all_version_delta}\\\\")
    t2.append("\\toprule")
    t2.append("Version & Cells & $\\Delta$att & $\\Delta$hit & $\\Delta$churn & $\\Delta$PDR \\\\")
    t2.append("\\midrule")
    t2.append("\\endfirsthead")
    t2.append("\\toprule")
    t2.append("Version & Cells & $\\Delta$att & $\\Delta$hit & $\\Delta$churn & $\\Delta$PDR \\\\")
    t2.append("\\midrule")
    t2.append("\\endhead")
    t2.append("\\bottomrule")
    t2.append("\\endfoot")
    for r in version_rows:
        label = tex_escape(r["label_pretty"])
        t2.append(
            f"{label} & {int(r['n_cells'])} & "
            f"{r['d_att']:+.4f} & {r['d_hit']:+.4f} & {r['d_churn']:+.2f} & {r['d_pdr']:+.4f} \\\\"
        )
    t2.append("\\end{longtable}")
    (OUT_DIR / "table_all_versions.tex").write_text("\n".join(t2), encoding="utf-8")

    main_summary = ROOT / "docs" / "paper" / "generated" / "main" / "summary_by_density.csv"
    if main_summary.exists():
        rows = read_csv(main_summary)
        order = ["sparse", "medium", "dense", "overall"]
        rows = [r for r in rows if r["scope"] in order]
        rows.sort(key=lambda r: order.index(r["scope"]))
        t3 = []
        t3.append("% Auto-generated: random main summary table")
        t3.append("\\begin{table}[t]")
        t3.append("\\centering")
        t3.append("\\caption{랜덤 토폴로지 메인실험 요약 ($\\Delta$=TA-BRPL-BRPL)}")
        t3.append("\\label{tab:random_main_summary}")
        t3.append("\\begin{tabular}{lrrrr}")
        t3.append("\\toprule")
        t3.append("Scope & $\\Delta$att & $\\Delta$hit & $\\Delta$churn & $\\Delta$PDR \\\\")
        t3.append("\\midrule")
        for r in rows:
            t3.append(
                f"{r['scope']} & {to_float(r,'delta_att_share_mean'):+.4f} & "
                f"{to_float(r,'delta_hit_ratio_mean'):+.4f} & "
                f"{to_float(r,'delta_churn_mean'):+.3f} & "
                f"{to_float(r,'delta_pdr_dur_mean'):+.4f} \\\\"
            )
        t3.append("\\bottomrule")
        t3.append("\\end{tabular}")
        t3.append("\\end{table}")
        (OUT_DIR / "table_random_main.tex").write_text("\n".join(t3), encoding="utf-8")


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    version_rows = collect_version_rows()
    write_csv(OUT_DIR / "version_delta_summary.csv", version_rows)
    write_tex_tables(version_rows)

    fig_r01_version_heatmap(version_rows)
    fig_r02_version_trends(version_rows)
    fig_r03_to_r05_v13_cell_comparison()
    fig_r06_main_abs_by_density()
    fig_r07_main_delta_ci()
    fig_r08_main_delta_cdf()
    fig_r09_main_tradeoff_scatter()
    fig_r10_main_winrate_heatmap()
    fig_r11_r12_run_boxplots()
    fig_r13_quickcheck_vs_main()

    print(f"[OK] figures -> {FIG_DIR}")
    print(f"[OK] tables  -> {OUT_DIR}")


if __name__ == "__main__":
    main()
