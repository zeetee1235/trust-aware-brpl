#!/usr/bin/env python3
"""Generate additional TA-BRPL figures requested for final paper package."""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from parse_results import parse_simlog, compute_pdr, compute_churn

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

ATTACKER_IDS = {2, 3, 4, 18}

COL = {
    "TABRPL": "#d62728",
    "TABRPL_LEGACY": "#1f77b4",
    "HONEST": "#16a34a",
    "ATTACK": "#dc2626",
    "LOSS100": "#1f77b4",
    "LOSS90": "#f59e0b",
    "LOSS80": "#dc2626",
    "FWD": "#f97316",
    "FULL": "#2563eb",
}


def _save(fig: plt.Figure, name: str) -> None:
    out = FIGURES / name
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _iter_seed_logs(proto: str, max_seed: int | None = None):
    pdir = RESULTS / proto
    if not pdir.exists():
        return
    for d in sorted(pdir.iterdir(), key=lambda x: int(x.name) if x.name.isdigit() else 10**9):
        if not d.is_dir() or not d.name.isdigit():
            continue
        seed = int(d.name)
        if max_seed is not None and seed > max_seed:
            continue
        log = d / "sim.log"
        if log.exists():
            yield seed, log


def _load_trust_by_update(proto: str, max_seed: int | None = None):
    # rows: (seed, update_idx, cls, t_fwd)
    rows = []
    for seed, log in _iter_seed_logs(proto, max_seed=max_seed):
        pair_idx = defaultdict(int)
        with open(log, errors="replace") as f:
            for line in f:
                k = line.find(":")
                if k < 0:
                    continue
                rest = line[k + 1 :].strip()
                if not rest.startswith("CSV,TRUST,") or rest.startswith("CSV,TRUST_"):
                    continue
                parts = rest.split(",")
                if len(parts) < 9:
                    continue
                try:
                    self_id = int(parts[2])
                    nbr_id = int(parts[3])
                    t_fwd = int(parts[4])
                except ValueError:
                    continue
                idx_key = (self_id, nbr_id)
                pair_idx[idx_key] += 1
                update_idx = pair_idx[idx_key]
                cls = "attacker" if nbr_id in ATTACKER_IDS else "honest"
                rows.append((seed, update_idx, cls, t_fwd))
    return rows


def fig_arch():
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.axis("off")
    boxes = [
        (0.03, 0.40, 0.18, 0.30, "Sender\nCSV,TX"),
        (0.27, 0.40, 0.18, 0.30, "Forwarders\nobserve next-hop"),
        (0.51, 0.40, 0.18, 0.30, "Root\nCSV,RX + echo reply"),
        (0.75, 0.40, 0.22, 0.30, "Trust Update\nT_fwd/T_ewma\nCSV,TRUST"),
    ]
    for x, y, w, h, txt in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, facecolor="#f8fafc", edgecolor="#334155", linewidth=1.4))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=10)
    arrows = [((0.21, 0.55), (0.27, 0.55)), ((0.45, 0.55), (0.51, 0.55)), ((0.69, 0.55), (0.75, 0.55))]
    for (x1, y1), (x2, y2) in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", lw=1.6, color="#0f172a"))
    ax.annotate("", xy=(0.58, 0.38), xytext=(0.84, 0.38), arrowprops=dict(arrowstyle="->", lw=1.4, color="#64748b"))
    ax.text(0.71, 0.33, "echo RTT / forwarding evidence", ha="center", va="center", fontsize=9, color="#475569")
    ax.set_title("fig_arch: T_fwd Echo-Based Measurement Pipeline", fontsize=13, fontweight="bold")
    _save(fig, "fig_arch_system_flow.pdf")


def fig_bootstrap():
    # "Before": legacy proxy from old setting folder
    before_rows = _load_trust_by_update("TABRPL_W811_U150_L500", max_seed=5)
    after_rows = _load_trust_by_update("TABRPL", max_seed=5)
    if not before_rows or not after_rows:
        print("Skip fig_bootstrap (missing trust rows)")
        return

    def summarize(rows):
        by_u = defaultdict(list)
        for _seed, u, cls, tf in rows:
            if cls == "honest":
                by_u[u].append(tf)
        xs = sorted(by_u)
        ys = [statistics.median(by_u[u]) for u in xs]
        return xs, ys

    x0, y0 = summarize(before_rows)
    x1, y1 = summarize(after_rows)

    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    ax.plot(x0, y0, marker="o", lw=2.0, color=COL["TABRPL_LEGACY"], label="Before fix (legacy run)")
    ax.plot(x1, y1, marker="o", lw=2.0, color=COL["TABRPL"], label="After fix (PRR fallback)")
    ax.axvline(3, color="#64748b", ls="--", lw=1.2)
    ax.text(3.05, 80, "phase switch (fallback -> echo)", fontsize=8.5, color="#334155")
    ax.set_xlabel("Trust update index (per neighbor)")
    ax.set_ylabel("Median T_fwd")
    ax.set_ylim(0, 1050)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("fig_bootstrap: T_fwd Before/After Bootstrap Fix", fontweight="bold")
    _save(fig, "fig_bootstrap_before_after.pdf")


def fig_twophase():
    rows = _load_trust_by_update("TABRPL", max_seed=5)
    if not rows:
        print("Skip fig_twophase (missing trust rows)")
        return
    by = defaultdict(list)
    for _seed, u, cls, tf in rows:
        by[(cls, u)].append(tf)
    x_h = sorted(u for (c, u) in by if c == "honest")
    x_a = sorted(u for (c, u) in by if c == "attacker")
    y_h = [statistics.median(by[("honest", u)]) for u in x_h]
    y_a = [statistics.median(by[("attacker", u)]) for u in x_a]

    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    ax.plot(x_h, y_h, marker="o", lw=2.0, color=COL["HONEST"], label="Honest neighbors")
    ax.plot(x_a, y_a, marker="o", lw=2.0, color=COL["ATTACK"], label="Attacker neighbors")
    ax.axvspan(0.8, 3.2, color="#94a3b8", alpha=0.15)
    ax.axvspan(3.2, max(max(x_h), max(x_a)) + 0.2, color="#fecaca", alpha=0.12)
    ax.text(1.25, 70, "Phase 1: PRR fallback", fontsize=8.5, color="#334155")
    ax.text(3.45, 70, "Phase 2: echo-based divergence", fontsize=8.5, color="#7f1d1d")
    ax.set_xlabel("Trust update index (per neighbor)")
    ax.set_ylabel("Median T_fwd")
    ax.set_ylim(0, 1050)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("fig_twophase: Two-Phase Detection Trajectory", fontweight="bold")
    _save(fig, "fig_twophase_detection.pdf")


def fig_loss():
    # Use first 5 seeds for fairness
    protos = [("TABRPL", "success_ratio=1.0", COL["LOSS100"]),
              ("TABRPL_LOSS90", "success_ratio=0.9", COL["LOSS90"]),
              ("TABRPL_LOSS80", "success_ratio=0.8", COL["LOSS80"])]
    data = []
    for proto, label, _c in protos:
        rows = _load_trust_by_update(proto, max_seed=5)
        for _seed, u, cls, tf in rows:
            if cls != "honest":
                continue
            if u < 3:
                continue
            data.append((label, tf))
    if not data:
        print("Skip fig_loss (no trust data)")
        return

    labels = [p[1] for p in protos]
    grouped = [[v for l, v in data if l == lab] for lab in labels]
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    bp = ax.boxplot(grouped, labels=labels, patch_artist=True, showfliers=False)
    for patch, (_p, _lab, col) in zip(bp["boxes"], protos):
        patch.set_facecolor(col)
        patch.set_alpha(0.35)
        patch.set_edgecolor(col)
    ax.set_ylabel("T_fwd (honest neighbors, update>=3)")
    ax.set_ylim(0, 1050)
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("fig_loss: Link Loss vs T_fwd Collapse", fontweight="bold")
    _save(fig, "fig_loss_t_fwd_collapse.pdf")


def fig3_v3():
    proto_labels = [
        ("V3_C1_TABRPL", "C1"),
        ("V3_C2_TABRPL", "C2"),
        ("V3_C3_TABRPL", "C3"),
        ("V3_C4_TABRPL", "C4"),
    ]
    per_proto = defaultdict(list)
    for proto, lab in proto_labels:
        for seed, log in _iter_seed_logs(proto, max_seed=5):
            d = parse_simlog(log)
            p = compute_pdr(d)
            v = p.get("pdr_during_attack", float("nan"))
            if not math.isnan(v):
                per_proto[lab].append(v * 100.0)
    if not per_proto:
        print("Skip fig3_v3 (no data)")
        return

    labs = [lab for _p, lab in proto_labels]
    means = [statistics.mean(per_proto[lab]) if per_proto[lab] else float("nan") for lab in labs]
    cis = []
    for lab in labs:
        vals = per_proto[lab]
        if len(vals) < 2:
            cis.append(0.0)
        else:
            cis.append(1.96 * statistics.stdev(vals) / math.sqrt(len(vals)))

    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    xs = np.arange(len(labs))
    bars = ax.bar(xs, means, yerr=cis, capsize=4, color=["#1d4ed8", "#16a34a", "#dc2626", "#7c3aed"], alpha=0.8)
    for i, lab in enumerate(labs):
        ys = per_proto[lab]
        jitter = np.linspace(-0.12, 0.12, len(ys)) if ys else []
        for j, y in enumerate(ys):
            ax.plot(xs[i] + jitter[j], y, "o", color="#111827", alpha=0.55, ms=4)
    ax.set_xticks(xs, labs)
    ax.set_ylim(55, 101)
    ax.set_ylabel("During-attack PDR (%)")
    ax.set_title("fig3: V3 Congestion vs Attack Separation (5 seeds)", fontweight="bold")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "fig3_v3_congestion_attack.pdf")


def fig6_churn_fwd_vs_full():
    variants = [("TABRPL_FWD", "FWD-only"), ("TABRPL", "Full TA-BRPL")]
    per = defaultdict(lambda: defaultdict(list))
    for proto, lab in variants:
        for seed, log in _iter_seed_logs(proto, max_seed=5):
            d = parse_simlog(log)
            rows = compute_churn(d)
            for r in rows:
                per[lab][r["node_id"]].append(r["churn_during_attack"])

    if not per:
        print("Skip fig6 (no churn data)")
        return

    nodes = sorted({nid for lab in per for nid in per[lab]})
    # Pick top 12 by max churn across both variants
    scored = []
    for nid in nodes:
        m = max(
            statistics.mean(per[lab][nid]) if per[lab][nid] else 0.0
            for lab in ("FWD-only", "Full TA-BRPL")
        )
        scored.append((m, nid))
    top_nodes = [nid for _m, nid in sorted(scored, reverse=True)[:12]]

    mat = np.zeros((len(top_nodes), 2), dtype=float)
    for i, nid in enumerate(top_nodes):
        for j, lab in enumerate(["FWD-only", "Full TA-BRPL"]):
            vals = per[lab].get(nid, [])
            mat[i, j] = statistics.mean(vals) if vals else 0.0

    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    im = ax.imshow(mat, cmap="YlOrRd")
    ax.set_xticks([0, 1], ["FWD-only", "Full TA-BRPL"])
    ax.set_yticks(range(len(top_nodes)), [str(n) for n in top_nodes])
    ax.set_xlabel("Variant")
    ax.set_ylabel("Node ID (hotspots)")
    ax.set_title("fig6: Parent Churn Hotspots (FWD-only vs Full TA-BRPL)", fontweight="bold")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                    color="white" if mat[i, j] > np.nanmax(mat) * 0.55 else "#111827", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Mean churn during attack")
    _save(fig, "fig6_churn_hotspots.pdf")


def _phase_from_ms(t_ms: int) -> str:
    if 150_000 <= t_ms < 350_000:
        return "pre"
    if 350_000 <= t_ms < 650_000:
        return "during"
    if 650_000 <= t_ms < 900_000:
        return "recovery"
    return "other"


def _load_validation_events(proto: str = "TABRPL", max_seed: int | None = None):
    # rows: (seed, phase, cls, event)
    # event in {"under","penalized","blacklist"}
    rows = []
    for seed, log in _iter_seed_logs(proto, max_seed=max_seed):
        with open(log, errors="replace") as f:
            for line in f:
                k = line.find(":")
                if k < 0:
                    continue
                rest = line[k + 1 :].strip()
                if rest.startswith("CSV,VAL_STATE,"):
                    p = rest.split(",")
                    if len(p) < 10:
                        continue
                    try:
                        t_ms = int(p[4])
                        nbr = int(p[2])
                        new_state = int(p[6])
                    except ValueError:
                        continue
                    phase = _phase_from_ms(t_ms)
                    cls = "attacker" if nbr in ATTACKER_IDS else "honest"
                    if new_state == 1:
                        rows.append((seed, phase, cls, "under"))
                    elif new_state == 2:
                        rows.append((seed, phase, cls, "penalized"))
                elif rest.startswith("CSV,TRUST_BLACKLIST,"):
                    p = rest.split(",")
                    if len(p) < 5:
                        continue
                    try:
                        t_ms = int(p[4])
                        nbr = int(p[3])
                    except ValueError:
                        continue
                    phase = _phase_from_ms(t_ms)
                    cls = "attacker" if nbr in ATTACKER_IDS else "honest"
                    rows.append((seed, phase, cls, "blacklist"))
    return rows


def fig_validation_events():
    rows = _load_validation_events("TABRPL")
    if not rows:
        print("Skip fig_validation_events (no validation rows)")
        return

    metrics = ["under", "penalized", "blacklist"]
    by_seed = defaultdict(lambda: defaultdict(int))
    for seed, phase, cls, ev in rows:
        if phase not in ("during", "recovery"):
            continue
        by_seed[(seed, cls)][ev] += 1

    seeds = sorted({seed for seed, _phase, _cls, _ev in rows})
    means = {"attacker": [], "honest": []}
    cis = {"attacker": [], "honest": []}
    for cls in ("attacker", "honest"):
        for m in metrics:
            vals = [by_seed[(s, cls)][m] for s in seeds]
            mu = statistics.mean(vals) if vals else 0.0
            if len(vals) >= 2:
                ci = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
            else:
                ci = 0.0
            means[cls].append(mu)
            cis[cls].append(ci)

    x = np.arange(len(metrics))
    w = 0.35
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.bar(x - w / 2, means["attacker"], w, yerr=cis["attacker"], capsize=4,
           color=COL["ATTACK"], alpha=0.85, label="Attacker neighbors")
    ax.bar(x + w / 2, means["honest"], w, yerr=cis["honest"], capsize=4,
           color=COL["HONEST"], alpha=0.85, label="Honest neighbors")
    ax.set_xticks(x, ["UNDER", "PENALIZED", "BLACKLIST"])
    ax.set_ylabel("Mean event count per seed\n(during + recovery)")
    ax.set_title("Validation Model Escalation Events by Neighbor Class", fontweight="bold")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper right", fontsize=9)
    _save(fig, "fig_validation_events.pdf")


def fig_validation_cumulative():
    rows = _load_validation_events("TABRPL")
    if not rows:
        print("Skip fig_validation_cumulative (no validation rows)")
        return
    # cumulative blacklist events over time
    events = []
    for seed, log in _iter_seed_logs("TABRPL"):
        with open(log, errors="replace") as f:
            for line in f:
                k = line.find(":")
                if k < 0:
                    continue
                rest = line[k + 1 :].strip()
                if not rest.startswith("CSV,TRUST_BLACKLIST,"):
                    continue
                p = rest.split(",")
                if len(p) < 5:
                    continue
                try:
                    t_ms = int(p[4])
                    nbr = int(p[2])
                except ValueError:
                    continue
                cls = "attacker" if nbr in ATTACKER_IDS else "honest"
                events.append((t_ms / 1000.0, cls))

    if not events:
        print("Skip fig_validation_cumulative (no blacklist events)")
        return

    bins = np.arange(300, 901, 30)
    cum = {"attacker": [], "honest": []}
    counts = {"attacker": 0, "honest": 0}
    events_sorted = sorted(events, key=lambda x: x[0])
    idx = 0
    for b in bins:
        while idx < len(events_sorted) and events_sorted[idx][0] <= b:
            counts[events_sorted[idx][1]] += 1
            idx += 1
        cum["attacker"].append(counts["attacker"])
        cum["honest"].append(counts["honest"])

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.plot(bins, cum["attacker"], marker="o", lw=2.0, color=COL["ATTACK"], label="Attacker blacklist (cum.)")
    ax.plot(bins, cum["honest"], marker="o", lw=2.0, color=COL["HONEST"], label="Honest blacklist (cum.)")
    ax.axvline(350, color="#64748b", ls="--", lw=1.2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Cumulative blacklist events")
    ax.set_title("Validation Model Blacklist Accumulation Over Time", fontweight="bold")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    _save(fig, "fig_validation_cumulative.pdf")


def fig_validation_blacklist_nodes():
    counts = defaultdict(int)
    for _seed, log in _iter_seed_logs("TABRPL"):
        with open(log, errors="replace") as f:
            for line in f:
                k = line.find(":")
                if k < 0:
                    continue
                rest = line[k + 1 :].strip()
                if not rest.startswith("CSV,TRUST_BLACKLIST,"):
                    continue
                p = rest.split(",")
                if len(p) < 5:
                    continue
                try:
                    node_id = int(p[2])
                except ValueError:
                    continue
                counts[node_id] += 1

    if not counts:
        print("Skip fig_validation_blacklist_nodes (no blacklist rows)")
        return

    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    labels = [str(n) for n, _ in top]
    vals = [c for _, c in top]
    cols = [COL["ATTACK"] if n in ATTACKER_IDS else "#1d4ed8" for n, _ in top]

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.bar(labels, vals, color=cols, alpha=0.85)
    ax.set_xlabel("Blacklisted neighbor ID (top 10)")
    ax.set_ylabel("Blacklist event count")
    ax.set_title("Validation Model: Blacklist Event Distribution", fontweight="bold")
    ax.grid(axis="y", alpha=0.25)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.2, str(v), ha="center", va="bottom", fontsize=8)
    _save(fig, "fig_validation_blacklist_nodes.pdf")


def main():
    fig_arch()
    fig_bootstrap()
    fig_twophase()
    fig_loss()
    fig3_v3()
    fig6_churn_fwd_vs_full()
    fig_validation_events()
    fig_validation_cumulative()
    fig_validation_blacklist_nodes()


if __name__ == "__main__":
    main()
