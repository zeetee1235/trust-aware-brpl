#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "docs" / "paper" / "figures" / "report"
MAIN_DIR = ROOT / "docs" / "paper" / "generated" / "main_v2_final"
REPORT_DIR = ROOT / "docs" / "paper" / "generated" / "report"
RESULTS_DIR = ROOT / "results" / "random_topo_main_v2"
MANIFEST_PATH = ROOT / "configs" / "scenarios" / "random_topo" / "manifest.json"


def load_main_frames():
    paired = pd.read_csv(MAIN_DIR / "paired_deltas_by_topology.csv")
    runs = pd.read_csv(MAIN_DIR / "metrics_by_run.csv")
    return paired, runs


def tex_escape(s: str) -> str:
    return (
        str(s).replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"manifest not found: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def parse_csc_positions(csc_path: Path) -> dict[int, tuple[float, float]]:
    root = ET.parse(csc_path).getroot()
    sim = root.find("simulation")
    if sim is None:
        return {}

    positions: dict[int, tuple[float, float]] = {}
    for mote in sim.findall("mote"):
        node_id = None
        x = y = None
        for iface in mote.findall("interface_config"):
            txt = iface.text or ""
            if "ContikiMoteID" in txt:
                i = iface.findtext("id")
                if i is not None:
                    node_id = int(i.strip())
            if "interfaces.Position" in txt:
                xs = iface.findtext("x")
                ys = iface.findtext("y")
                if xs is not None and ys is not None:
                    x = float(xs)
                    y = float(ys)
        if node_id is not None and x is not None and y is not None:
            positions[node_id] = (x, y)
    return positions


def euclid(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def build_adj(coords: dict[int, tuple[float, float]], tx_range: float) -> dict[int, list[int]]:
    ids = sorted(coords.keys())
    adj = {i: [] for i in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if euclid(coords[a], coords[b]) <= tx_range:
                adj[a].append(b)
                adj[b].append(a)
    return adj


def bfs_dist(adj: dict[int, list[int]], start: int) -> dict[int, int]:
    d = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in d:
                d[nxt] = d[cur] + 1
                q.append(nxt)
    return d


def closeness(adj: dict[int, list[int]], node: int) -> float:
    d = bfs_dist(adj, node)
    if len(d) < len(adj):
        return float("nan")
    total = sum(d.values())
    if total <= 0:
        return 0.0
    return (len(adj) - 1) / total


def topology_features(manifest: dict) -> pd.DataFrame:
    tx_range = float(manifest.get("tx_range", 50.0))
    root_id = int(manifest.get("root_id", 1))
    rows = []

    for t in manifest.get("topologies", []):
        density = t["density"]
        topology = t["topology_name"]
        attacker_ids = [int(x) for x in t.get("attacker_ids", [])]

        # Any protocol csc shares same coordinates.
        scenario_rel = t.get("scenarios", {}).get("BRPL")
        if scenario_rel is None:
            vals = list(t.get("scenarios", {}).values())
            scenario_rel = vals[0] if vals else None
        if scenario_rel is None:
            continue

        csc = ROOT / scenario_rel
        if not csc.exists():
            continue

        coords = parse_csc_positions(csc)
        if not coords:
            continue
        adj = build_adj(coords, tx_range)
        dist_root = bfs_dist(adj, root_id)

        deg_vals = [len(adj[n]) for n in adj]
        avg_degree = statistics.mean(deg_vals) if deg_vals else float("nan")

        # Parent-option diversity proxy:
        # number of neighbors with strictly shorter hop distance to root.
        parent_options = []
        shortest_options = []
        for n in adj:
            if n == root_id or n not in dist_root:
                continue
            dn = dist_root[n]
            if dn <= 0:
                continue
            lower = [nb for nb in adj[n] if dist_root.get(nb, 10**9) < dn]
            shortest = [nb for nb in adj[n] if dist_root.get(nb, 10**9) == dn - 1]
            parent_options.append(len(lower))
            shortest_options.append(len(shortest))

        attack_closeness = [closeness(adj, a) for a in attacker_ids if a in adj]
        attack_degrees = [len(adj[a]) for a in attacker_ids if a in adj]
        attack_root_hops = [dist_root.get(a, np.nan) for a in attacker_ids if a in adj]

        rows.append(
            {
                "density": density,
                "topology": topology,
                "attacker_ids": ",".join(str(x) for x in attacker_ids),
                "avg_degree_manifest": float(t.get("avg_degree", np.nan)),
                "avg_hop_root_manifest": float(t.get("avg_hop_root", np.nan)),
                "avg_degree_graph": float(avg_degree),
                "path_diversity_mean": float(np.nanmean(parent_options)) if parent_options else np.nan,
                "shortest_parent_options_mean": float(np.nanmean(shortest_options)) if shortest_options else np.nan,
                "attacker_closeness_mean": float(np.nanmean(attack_closeness)) if attack_closeness else np.nan,
                "attacker_degree_mean": float(np.nanmean(attack_degrees)) if attack_degrees else np.nan,
                "attacker_root_hop_mean": float(np.nanmean(attack_root_hops)) if attack_root_hops else np.nan,
                "n_nodes": len(coords),
            }
        )

    return pd.DataFrame(rows)


def fig_r14_corr_heatmap(paired: pd.DataFrame):
    cols = ["delta_att_share", "delta_hit_ratio", "delta_churn", "delta_pdr_dur"]
    c = paired[cols].corr().values
    names = ["Δatt", "Δhit", "Δchurn", "Δpdr"]
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    im = ax.imshow(c, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    for i in range(c.shape[0]):
        for j in range(c.shape[1]):
            ax.text(j, i, f"{c[i, j]:+.2f}", ha="center", va="center", fontsize=10)
    ax.set_title("Correlation among topology-paired deltas")
    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cb.set_label("Pearson r")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r14_delta_corr_matrix.pdf")
    plt.close(fig)


def fig_r15_att_vs_pdr_scatter(paired: pd.DataFrame):
    colors = {"sparse": "#16a34a", "medium": "#2563eb", "dense": "#dc2626"}
    fig, ax = plt.subplots(figsize=(7.4, 5.6))
    for d, g in paired.groupby("density"):
        ax.scatter(
            g["delta_att_share"],
            g["delta_pdr_dur"],
            s=34,
            alpha=0.75,
            color=colors.get(d, "#666"),
            label=d,
        )
    ax.axvline(0, color="black", linewidth=0.9)
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xlabel("Δatt_share (TA-BRPL - BRPL, lower better)")
    ax.set_ylabel("ΔPDR_dur (higher better)")
    ax.set_title("Topology-level trade-off: isolation vs delivery")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r15_att_vs_pdr_by_density.pdf")
    plt.close(fig)


def fig_r16_winloss_counts(paired: pd.DataFrame):
    metrics = [
        ("delta_att_share", "att"),
        ("delta_hit_ratio", "hit"),
        ("delta_churn", "churn"),
        ("delta_pdr_dur", "pdr"),
    ]
    densities = ["sparse", "medium", "dense"]
    wins = []
    losses = []
    for d in densities:
        g = paired[paired["density"] == d]
        w = []
        l = []
        for m, _ in metrics:
            if m == "delta_pdr_dur":
                w.append((g[m] > 0).sum())
                l.append((g[m] <= 0).sum())
            else:
                w.append((g[m] < 0).sum())
                l.append((g[m] >= 0).sum())
        wins.append(w)
        losses.append(l)

    fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.0), sharey=True)
    x = np.arange(len(metrics))
    for i, d in enumerate(densities):
        ax = axes[i]
        ax.bar(x, wins[i], label="wins", color="#2563eb")
        ax.bar(x, losses[i], bottom=wins[i], label="non-wins", color="#f97316")
        ax.set_xticks(x)
        ax.set_xticklabels([n for _, n in metrics])
        ax.set_title(d)
        ax.set_ylim(0, 25)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Topology count (n=25 per density)")
    axes[0].legend(frameon=False)
    fig.suptitle("Win/non-win count by density and metric")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r16_wins_losses_by_density.pdf")
    plt.close(fig)


def fig_r17_best_worst_att(paired: pd.DataFrame):
    s = paired[["topology", "density", "delta_att_share"]].copy()
    s["label"] = s["density"].str[:1].str.upper() + "-" + s["topology"]
    best = s.nsmallest(8, "delta_att_share")
    worst = s.nlargest(8, "delta_att_share")
    cat = pd.concat([best, worst], axis=0)
    cat = cat.sort_values("delta_att_share")

    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    colors = ["#2563eb" if v < 0 else "#dc2626" for v in cat["delta_att_share"]]
    ax.barh(cat["label"], cat["delta_att_share"], color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Δatt_share")
    ax.set_title("Topologies with best/worst attacker isolation gap")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r17_topology_best_worst_att.pdf")
    plt.close(fig)


def fig_r18_run_scatter_att_pdr(runs: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for proto, color in [("BRPL", "#f97316"), ("TABRPL", "#2563eb")]:
        g = runs[runs["protocol"] == proto]
        ax.scatter(g["att_share"], g["pdr_dur"], s=14, alpha=0.45, color=color, label=proto)
    ax.set_xlabel("att_share (run-level)")
    ax.set_ylabel("PDR_dur (run-level)")
    ax.set_title("Run-level relationship between attacker dependency and PDR")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r18_run_att_vs_pdr_scatter.pdf")
    plt.close(fig)


def fig_r19_run_hit_box(runs: pd.DataFrame):
    dens = ["sparse", "medium", "dense"]
    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    data = []
    pos = []
    labels = []
    p = 0
    for d in dens:
        for proto in ["BRPL", "TABRPL"]:
            g = runs[(runs["density"] == d) & (runs["protocol"] == proto)]
            data.append(g["hit_ratio"].values)
            pos.append(p)
            labels.append(f"{d}\n{proto}")
            p += 1
        p += 0.7
    bp = ax.boxplot(data, positions=pos, widths=0.55, patch_artist=True, showfliers=False)
    for i, b in enumerate(bp["boxes"]):
        b.set(facecolor=("#f97316" if "BRPL" in labels[i] else "#2563eb"), alpha=0.6)
    ax.set_xticks(pos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("hit_ratio")
    ax.set_title("Run-level hit_ratio distribution (density x protocol)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r19_main_run_box_hit_ratio.pdf")
    plt.close(fig)


def fig_r20_failure_mode_features(merged: pd.DataFrame):
    feats = [
        ("avg_degree_graph", "Avg degree"),
        ("path_diversity_mean", "Path diversity"),
        ("attacker_closeness_mean", "Attacker closeness"),
        ("attacker_root_hop_mean", "Attacker-root hop"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.8))
    axes = axes.flatten()
    for ax, (f, lbl) in zip(axes, feats):
        w = merged.loc[merged["att_win"] == 1, f].dropna().values
        l = merged.loc[merged["att_win"] == 0, f].dropna().values
        ax.boxplot([w, l], labels=["win", "loss"], showfliers=False)
        ax.set_title(lbl)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Failure-mode split by topology features (att_share win/loss)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r20_failure_mode_feature_boxplots.pdf")
    plt.close(fig)


def switch_counts_from_log(sim_log: Path, attackers: set[int]) -> dict[str, int]:
    # CSV,TRUST_PARENT,self,new_parent,time
    pat = re.compile(r"CSV,TRUST_PARENT,(\d+),(\d+),(\d+)")
    events_by_node: dict[int, list[tuple[int, int]]] = defaultdict(list)
    if not sim_log.exists():
        return {
            "switch_total": 0,
            "switch_nn": 0,
            "switch_na": 0,
            "switch_an": 0,
            "switch_aa": 0,
            "nodes_with_parent_events": 0,
        }

    for line in sim_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pat.search(line)
        if not m:
            continue
        node = int(m.group(1))
        new_parent = int(m.group(2))
        ts = int(m.group(3))
        arr = events_by_node[node]
        # logs may duplicate identical records back-to-back
        if arr and arr[-1] == (new_parent, ts):
            continue
        arr.append((new_parent, ts))

    out = {
        "switch_total": 0,
        "switch_nn": 0,  # non-att -> non-att
        "switch_na": 0,  # non-att -> att
        "switch_an": 0,  # att -> non-att
        "switch_aa": 0,  # att -> att
        "nodes_with_parent_events": sum(1 for v in events_by_node.values() if v),
    }

    for _, ev in events_by_node.items():
        prev_parent = None
        for new_parent, _ in ev:
            if prev_parent is None:
                prev_parent = new_parent
                continue
            if new_parent == prev_parent:
                continue
            out["switch_total"] += 1
            prev_att = prev_parent in attackers
            new_att = new_parent in attackers
            if not prev_att and not new_att:
                out["switch_nn"] += 1
            elif not prev_att and new_att:
                out["switch_na"] += 1
            elif prev_att and not new_att:
                out["switch_an"] += 1
            else:
                out["switch_aa"] += 1
            prev_parent = new_parent

    return out


def fig_r21_switch_composition_density(df: pd.DataFrame):
    sums = (
        df.groupby("density")[["switch_nn", "switch_na", "switch_an", "switch_aa"]]
        .sum()
        .reindex(["sparse", "medium", "dense"])
        .fillna(0)
    )
    labels = ["NN", "NA", "AN", "AA"]
    cols = ["switch_nn", "switch_na", "switch_an", "switch_aa"]
    colors = ["#2563eb", "#dc2626", "#16a34a", "#f59e0b"]

    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    bottom = np.zeros(len(sums))
    x = np.arange(len(sums))
    for c, lbl, col in zip(cols, labels, colors):
        vals = sums[c].values
        ax.bar(x, vals, bottom=bottom, label=lbl, color=col)
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(sums.index.tolist())
    ax.set_ylabel("Switch count (sum over TABRPL runs)")
    ax.set_title("TABRPL switch composition by density")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r21_switch_composition_by_density.pdf")
    plt.close(fig)


def fig_r22_switch_composition_winloss(df: pd.DataFrame):
    sums = (
        df.groupby("att_outcome")[["switch_nn", "switch_na", "switch_an", "switch_aa"]]
        .sum()
        .reindex(["win", "loss"])
        .fillna(0)
    )
    labels = ["NN", "NA", "AN", "AA"]
    cols = ["switch_nn", "switch_na", "switch_an", "switch_aa"]
    colors = ["#2563eb", "#dc2626", "#16a34a", "#f59e0b"]

    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    bottom = np.zeros(len(sums))
    x = np.arange(len(sums))
    for c, lbl, col in zip(cols, labels, colors):
        vals = sums[c].values
        ax.bar(x, vals, bottom=bottom, label=lbl, color=col)
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(sums.index.tolist())
    ax.set_ylabel("Switch count (sum over TABRPL runs)")
    ax.set_title("TABRPL switch composition by att_share win/loss topology")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=4)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r22_switch_composition_by_outcome.pdf")
    plt.close(fig)


def write_failure_mode_tex(stats_df: pd.DataFrame):
    lines = []
    lines.append("% Auto-generated by generate_extra_report_figures.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Failure-mode feature split (att\\_share 기준 win/loss)}")
    lines.append("\\label{tab:failure_mode_feature_split}")
    lines.append("\\begin{tabular}{lrrr}")
    lines.append("\\toprule")
    lines.append("Feature & Win mean & Loss mean & Corr(win, feature) \\\\")
    lines.append("\\midrule")
    for _, r in stats_df.iterrows():
        lines.append(
            f"{tex_escape(r['feature'])} & {r['win_mean']:.4f} & {r['loss_mean']:.4f} & {r['corr_win']:+.3f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "table_failure_mode_feature_split.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_switch_summary_tex(summary_density: pd.DataFrame):
    lines = []
    lines.append("% Auto-generated by generate_extra_report_figures.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{TABRPL switching decomposition by density}")
    lines.append("\\label{tab:switch_decomposition_density}")
    lines.append("\\begin{tabular}{lrrrr}")
    lines.append("\\toprule")
    lines.append("Density & NN ratio & NA ratio & AN ratio & Oscillation ratio(NN) \\\\")
    lines.append("\\midrule")
    for _, r in summary_density.iterrows():
        lines.append(
            f"{tex_escape(r['density'])} & {r['ratio_nn']:.3f} & {r['ratio_na']:.3f} & {r['ratio_an']:.3f} & {r['ratio_nn']:.3f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "table_switch_decomposition_density.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def failure_mode_and_switch_analysis(paired: pd.DataFrame, runs: pd.DataFrame):
    manifest = read_manifest()
    topo_feat = topology_features(manifest)
    merged = paired.merge(topo_feat, on=["density", "topology"], how="left")
    merged["att_win"] = (merged["delta_att_share"] < 0).astype(int)
    merged["att_outcome"] = np.where(merged["att_win"] == 1, "win", "loss")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(REPORT_DIR / "failure_mode_by_topology.csv", index=False)

    feat_cols = [
        "avg_degree_graph",
        "path_diversity_mean",
        "attacker_closeness_mean",
        "attacker_root_hop_mean",
        "attacker_degree_mean",
        "avg_hop_root_manifest",
    ]
    stats_rows = []
    for f in feat_cols:
        win_v = merged.loc[merged["att_win"] == 1, f].dropna().values
        loss_v = merged.loc[merged["att_win"] == 0, f].dropna().values
        corr = np.nan
        x = merged[f].to_numpy(dtype=float)
        y = merged["att_win"].to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() > 2 and np.std(x[ok]) > 0 and np.std(y[ok]) > 0:
            corr = float(np.corrcoef(y[ok], x[ok])[0, 1])
        stats_rows.append(
            {
                "feature": f,
                "win_mean": float(np.nanmean(win_v)) if len(win_v) else np.nan,
                "loss_mean": float(np.nanmean(loss_v)) if len(loss_v) else np.nan,
                "diff_loss_minus_win": (
                    float(np.nanmean(loss_v) - np.nanmean(win_v))
                    if len(win_v) and len(loss_v)
                    else np.nan
                ),
                "corr_win": corr,
            }
        )
    stats_df = pd.DataFrame(stats_rows)
    stats_df.to_csv(REPORT_DIR / "failure_mode_feature_stats.csv", index=False)
    write_failure_mode_tex(stats_df)
    fig_r20_failure_mode_features(merged)

    attacker_map: dict[tuple[str, str], set[int]] = {}
    for t in manifest.get("topologies", []):
        key = (str(t["density"]), str(t["topology_name"]))
        attacker_map[key] = set(int(x) for x in t.get("attacker_ids", []))

    run_rows = []
    ta_runs = runs[runs["protocol"] == "TABRPL"].copy()
    for _, rr in ta_runs.iterrows():
        density = str(rr["density"])
        topology = str(rr["topology"])
        run_seed = int(rr["run_seed"])
        log = RESULTS_DIR / density / topology / "TABRPL" / str(run_seed) / "sim.log"
        attackers = attacker_map.get((density, topology), set())
        cnt = switch_counts_from_log(log, attackers)
        total = cnt["switch_total"]
        run_rows.append(
            {
                "density": density,
                "topology": topology,
                "run_seed": run_seed,
                "switch_total": total,
                "switch_nn": cnt["switch_nn"],
                "switch_na": cnt["switch_na"],
                "switch_an": cnt["switch_an"],
                "switch_aa": cnt["switch_aa"],
                "ratio_nn": (cnt["switch_nn"] / total) if total > 0 else 0.0,
                "ratio_na": (cnt["switch_na"] / total) if total > 0 else 0.0,
                "ratio_an": (cnt["switch_an"] / total) if total > 0 else 0.0,
                "ratio_aa": (cnt["switch_aa"] / total) if total > 0 else 0.0,
                "churn_metric": float(rr["churn"]),
                "att_share": float(rr["att_share"]),
                "hit_ratio": float(rr["hit_ratio"]),
                "nodes_with_parent_events": cnt["nodes_with_parent_events"],
            }
        )

    sw = pd.DataFrame(run_rows)
    sw = sw.merge(
        merged[["density", "topology", "att_win", "att_outcome", "delta_att_share"]],
        on=["density", "topology"],
        how="left",
    )
    sw.to_csv(REPORT_DIR / "switch_type_by_run.csv", index=False)

    summary_density = (
        sw.groupby("density")[["switch_total", "switch_nn", "switch_na", "switch_an", "switch_aa"]]
        .sum()
        .reset_index()
    )
    for c in ["nn", "na", "an", "aa"]:
        summary_density[f"ratio_{c}"] = np.where(
            summary_density["switch_total"] > 0,
            summary_density[f"switch_{c}"] / summary_density["switch_total"],
            0.0,
        )
    summary_density.to_csv(REPORT_DIR / "switch_type_summary_by_density.csv", index=False)

    summary_outcome = (
        sw.groupby("att_outcome")[["switch_total", "switch_nn", "switch_na", "switch_an", "switch_aa"]]
        .sum()
        .reset_index()
    )
    for c in ["nn", "na", "an", "aa"]:
        summary_outcome[f"ratio_{c}"] = np.where(
            summary_outcome["switch_total"] > 0,
            summary_outcome[f"switch_{c}"] / summary_outcome["switch_total"],
            0.0,
        )
    summary_outcome.to_csv(REPORT_DIR / "switch_type_summary_by_outcome.csv", index=False)

    write_switch_summary_tex(summary_density)
    fig_r21_switch_composition_density(sw)
    fig_r22_switch_composition_winloss(sw)


def main():
    global FIG_DIR, MAIN_DIR, REPORT_DIR, RESULTS_DIR, MANIFEST_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-dir", type=Path, default=MAIN_DIR)
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    ap.add_argument("--fig-dir", type=Path, default=FIG_DIR)
    ap.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = ap.parse_args()

    MAIN_DIR = args.main_dir
    RESULTS_DIR = args.results_dir
    REPORT_DIR = args.report_dir
    FIG_DIR = args.fig_dir
    MANIFEST_PATH = args.manifest

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    paired, runs = load_main_frames()
    fig_r14_corr_heatmap(paired)
    fig_r15_att_vs_pdr_scatter(paired)
    fig_r16_winloss_counts(paired)
    fig_r17_best_worst_att(paired)
    fig_r18_run_scatter_att_pdr(runs)
    fig_r19_run_hit_box(runs)
    failure_mode_and_switch_analysis(paired, runs)
    print("[OK] extra report figures + failure-mode assets generated")


if __name__ == "__main__":
    main()
