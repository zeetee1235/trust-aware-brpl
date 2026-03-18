#!/usr/bin/env python3
"""Extended paper-ready analysis for TA-BRPL result logs.

This script extracts currently-available metrics from existing Cooja logs:
  - no-attack stability metrics
  - attacker vs benign trust separability
  - route-level exposure metrics
  - seed-dependence / failure-pattern correlations

Outputs are written under results/summaries/.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import sys

import math
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.parse_results as pr

RESULTS = ROOT / "results"
SUMMARIES = RESULTS / "summaries"
FIGURES = ROOT / "figures"

PHASES = ["pre_attack", "during_attack", "recovery"]
ATTACK_START = 350_000
RECOVERY_START = 650_000
SIM_END = 900_000
TAU_WARN = 700
TAU_JOIN = 450
TAU_BLACK = 250
ATTACKERS = {2, 3, 4, 18}
BLACKHOLES = {2, 3, 4}
SINKHOLES = {18}


@dataclass
class RouteRow:
    self_id: int
    tick: int
    parent: int
    rank: int
    hop: int
    switch_count: int
    parent_is_sink: int
    parent_is_attacker: int
    joined: int


def phase_of_tick(tick: int) -> str:
    if tick < ATTACK_START:
        return "pre_attack"
    if tick < RECOVERY_START:
        return "during_attack"
    if tick <= SIM_END:
        return "recovery"
    return "post"


def mean_or_nan(xs: Iterable[float]) -> float:
    xs = list(xs)
    return float(statistics.mean(xs)) if xs else float("nan")


def safe_corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(ys) < 2:
        return float("nan")
    xa = np.array(xs, dtype=float)
    ya = np.array(ys, dtype=float)
    if np.allclose(xa, xa[0]) or np.allclose(ya, ya[0]):
        return float("nan")
    return float(np.corrcoef(xa, ya)[0, 1])


def overlap_coeff(a: list[int], b: list[int], bins: int = 20) -> float:
    if not a or not b:
        return float("nan")
    hist_a, edges = np.histogram(a, bins=bins, range=(0, 1000), density=True)
    hist_b, _ = np.histogram(b, bins=edges, density=True)
    widths = np.diff(edges)
    return float(np.sum(np.minimum(hist_a, hist_b) * widths))


def parse_route_rows(path: Path) -> list[RouteRow]:
    rows: list[RouteRow] = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return rows
    for raw in lines:
        line = raw.strip()
        colon = line.find(":")
        if colon < 1:
            continue
        rest = line[colon + 1 :]
        if not rest.startswith("CSV,ROUTE,"):
            continue
        parts = rest.split(",")
        if len(parts) < 10:
            continue
        try:
            rows.append(
                RouteRow(
                    self_id=int(parts[2]),
                    tick=int(parts[3]),
                    parent=int(parts[4]),
                    rank=int(parts[5]),
                    hop=int(parts[6]),
                    switch_count=int(parts[7]),
                    parent_is_sink=int(parts[8]),
                    parent_is_attacker=int(parts[9]),
                    joined=int(parts[10]) if len(parts) > 10 else 0,
                )
            )
        except ValueError:
            continue
    return rows


def parse_event_counts(path: Path) -> dict[str, list[int]]:
    counts = {
        "blacklist": [0, 0, 0],
        "escape": [0, 0, 0],
        "trust_parent": [0, 0, 0],
        "cand_allowed_sum": [0, 0, 0],
        "cand_total_sum": [0, 0, 0],
        "cand_rows": [0, 0, 0],
    }
    lines = path.read_text(errors="replace").splitlines()
    for raw in lines:
        line = raw.strip()
        colon = line.find(":")
        if colon < 1:
            continue
        rest = line[colon + 1 :]
        parts = rest.split(",")
        if rest.startswith("CSV,TRUST_BLACKLIST,") and len(parts) >= 5:
            tick = int(parts[4])
            idx = PHASES.index(phase_of_tick(tick))
            counts["blacklist"][idx] += 1
        elif rest.startswith("CSV,TRUST_ESCAPE,") and len(parts) >= 5:
            tick = int(parts[4])
            idx = PHASES.index(phase_of_tick(tick))
            counts["escape"][idx] += 1
        elif rest.startswith("CSV,TRUST_PARENT,") and len(parts) >= 5:
            tick = int(parts[4])
            phase = phase_of_tick(tick)
            if phase in PHASES:
                counts["trust_parent"][PHASES.index(phase)] += 1
        elif rest.startswith("CSV,TRUST_CANDIDATES,") and len(parts) >= 7:
            tick = int(parts[3])
            phase = phase_of_tick(tick)
            if phase in PHASES:
                idx = PHASES.index(phase)
                counts["cand_allowed_sum"][idx] += int(parts[4])
                counts["cand_total_sum"][idx] += int(parts[5])
                counts["cand_rows"][idx] += 1
    return counts


def pdr_by_phase(tx_records, rx_records) -> dict[str, float]:
    out = {}
    for phase in PHASES:
        txs = {(r["node_id"], r["seq"]) for r in tx_records if r["phase"] == phase}
        rxs = {(r["src_node"], r["seq"]) for r in rx_records if r["phase"] == phase}
        out[phase] = (len(txs & rxs) / len(txs)) if txs else float("nan")
    return out


def trust_tier(t: int) -> str:
    if t < TAU_BLACK:
        return "black"
    if t < TAU_JOIN:
        return "untrusted"
    if t < TAU_WARN:
        return "suspect"
    return "normal"


def analyze_noattack() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = RESULTS / "TABRPL_NOATTACK"
    seed_rows = []
    phase_rows = []
    for seed_dir in sorted([p for p in base.iterdir() if p.is_dir() and p.name.isdigit()], key=lambda p: int(p.name)):
        seed = int(seed_dir.name)
        log = seed_dir / "sim.log"
        tx, rx, _, parent_events, trust_records, _ = pr.parse_log(log)
        pdr = pdr_by_phase(tx, rx)
        counts = parse_event_counts(log)
        # churn from parent events
        events_by_node = defaultdict(list)
        for node_id, parent_ip, approx_tick in parent_events:
            events_by_node[node_id].append((parent_ip, approx_tick))
        churn_phase = {phase: 0 for phase in PHASES}
        for evs in events_by_node.values():
            for phase in PHASES:
                churn_phase[phase] += pr._churn_for_node(evs, phase)

        for phase in PHASES:
            phase_trust = [r for r in trust_records if r["phase"] == phase] if trust_records and "phase" in trust_records[0] else [
                r for r in trust_records if phase_of_tick(r["approx_tick"]) == phase
            ]
            t_fwd = [r["t_fwd"] for r in phase_trust]
            t_hon = [r["t_hon"] for r in phase_trust]
            t_ewma = [r["t_ewma"] for r in phase_trust]
            tier_counts = Counter(trust_tier(r["t_ewma"]) for r in phase_trust)
            suspect_or_worse = sum(1 for r in phase_trust if r["t_ewma"] < TAU_WARN)
            rows = counts["cand_rows"][PHASES.index(phase)]
            allowed_mean = counts["cand_allowed_sum"][PHASES.index(phase)] / rows if rows else float("nan")
            total_mean = counts["cand_total_sum"][PHASES.index(phase)] / rows if rows else float("nan")
            excluded_ratio = 1.0 - (allowed_mean / total_mean) if rows and total_mean > 0 else float("nan")
            phase_rows.append(
                {
                    "seed": seed,
                    "phase": phase,
                    "pdr": pdr[phase],
                    "false_blacklist_count": counts["blacklist"][PHASES.index(phase)],
                    "escape_count": counts["escape"][PHASES.index(phase)],
                    "trust_parent_count": counts["trust_parent"][PHASES.index(phase)],
                    "parent_churn_count": churn_phase[phase],
                    "allowed_candidates_mean": allowed_mean,
                    "excluded_parent_ratio": excluded_ratio,
                    "false_suspect_samples": suspect_or_worse,
                    "tier_normal_frac": tier_counts["normal"] / len(phase_trust) if phase_trust else float("nan"),
                    "tier_suspect_frac": tier_counts["suspect"] / len(phase_trust) if phase_trust else float("nan"),
                    "tier_untrusted_frac": tier_counts["untrusted"] / len(phase_trust) if phase_trust else float("nan"),
                    "tier_black_frac": tier_counts["black"] / len(phase_trust) if phase_trust else float("nan"),
                    "t_fwd_mean": mean_or_nan(t_fwd),
                    "t_hon_mean": mean_or_nan(t_hon),
                    "t_ewma_mean": mean_or_nan(t_ewma),
                }
            )
        seed_rows.append({"seed": seed, **{f"{ph}_pdr": pdr[ph] for ph in PHASES}})
    return pd.DataFrame(seed_rows), pd.DataFrame(phase_rows)


def analyze_baseline_seeds() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = RESULTS / "TABRPL"
    seed_rows = []
    trust_sep_rows = []
    route_rows = []
    for seed_dir in sorted([p for p in base.iterdir() if p.is_dir() and p.name.isdigit()], key=lambda p: int(p.name)):
        seed = int(seed_dir.name)
        log = seed_dir / "sim.log"
        tx, rx, _, parent_events, trust_records, attacker_ids = pr.parse_log(log)
        route_records = parse_route_rows(log)
        counts = parse_event_counts(log)
        pdr = pdr_by_phase(tx, rx)

        # route-level metrics by phase
        for phase in PHASES:
            rows = [r for r in route_records if phase_of_tick(r.tick) == phase and r.parent < 65535]
            if rows:
                parents = [r.parent for r in rows]
                c = Counter(parents)
                probs = np.array(list(c.values()), dtype=float) / len(parents)
                entropy = float(-(probs * np.log2(probs)).sum())
                top_parent, top_ct = c.most_common(1)[0]
                route_rows.append(
                    {
                        "seed": seed,
                        "phase": phase,
                        "attacker_route_share": sum(1 for r in rows if r.parent in ATTACKERS) / len(rows),
                        "sinkhole_route_share": sum(1 for r in rows if r.parent in SINKHOLES) / len(rows),
                        "blackhole_route_share": sum(1 for r in rows if r.parent in BLACKHOLES) / len(rows),
                        "node2_share": sum(1 for r in rows if r.parent == 2) / len(rows),
                        "node3_share": sum(1 for r in rows if r.parent == 3) / len(rows),
                        "node4_share": sum(1 for r in rows if r.parent == 4) / len(rows),
                        "node18_share": sum(1 for r in rows if r.parent == 18) / len(rows),
                        "avg_hop": mean_or_nan([r.hop for r in rows]),
                        "top_parent_share": top_ct / len(rows),
                        "top_parent_id": top_parent,
                        "parent_entropy": entropy,
                        "unique_parents": len(c),
                    }
                )

        # trust separation
        for phase in PHASES:
            rows = [r for r in trust_records if phase_of_tick(r["approx_tick"]) == phase]
            att = [r for r in rows if r["nbr_id"] in attacker_ids]
            ben = [r for r in rows if r["nbr_id"] not in attacker_ids]
            for metric in ["t_fwd", "t_ctrl", "t_hon", "t_agg", "t_ewma"]:
                att_vals = [r[metric] for r in att]
                ben_vals = [r[metric] for r in ben]
                trust_sep_rows.append(
                    {
                        "seed": seed,
                        "phase": phase,
                        "metric": metric,
                        "attacker_mean": mean_or_nan(att_vals),
                        "benign_mean": mean_or_nan(ben_vals),
                        "attacker_std": float(np.std(att_vals)) if att_vals else float("nan"),
                        "benign_std": float(np.std(ben_vals)) if ben_vals else float("nan"),
                        "overlap_coeff": overlap_coeff(att_vals, ben_vals),
                    }
                )

        # seed summary
        rec_route = next((r for r in route_rows if r["seed"] == seed and r["phase"] == "recovery"), None)
        dur_route = next((r for r in route_rows if r["seed"] == seed and r["phase"] == "during_attack"), None)
        phase_trust = defaultdict(list)
        for r in trust_records:
            ph = phase_of_tick(r["approx_tick"])
            if ph in PHASES:
                phase_trust[ph].append(r)
        def attacker_mean(phase: str, attacker_id: int | None = None) -> float:
            xs = []
            for r in phase_trust[phase]:
                if r["nbr_id"] in ATTACKERS and (attacker_id is None or r["nbr_id"] == attacker_id):
                    xs.append(r["t_ewma"])
            return mean_or_nan(xs)
        rows = counts["cand_rows"][PHASES.index("recovery")]
        allowed_recovery = counts["cand_allowed_sum"][PHASES.index("recovery")] / rows if rows else float("nan")
        rows_d = counts["cand_rows"][PHASES.index("during_attack")]
        allowed_during = counts["cand_allowed_sum"][PHASES.index("during_attack")] / rows_d if rows_d else float("nan")
        seed_rows.append(
            {
                "seed": seed,
                "pre_pdr": pdr["pre_attack"],
                "during_pdr": pdr["during_attack"],
                "recovery_pdr": pdr["recovery"],
                "during_allowed_candidates": allowed_during,
                "recovery_allowed_candidates": allowed_recovery,
                "during_blacklists": counts["blacklist"][PHASES.index("during_attack")],
                "recovery_blacklists": counts["blacklist"][PHASES.index("recovery")],
                "during_escapes": counts["escape"][PHASES.index("during_attack")],
                "recovery_escapes": counts["escape"][PHASES.index("recovery")],
                "during_attacker_share": dur_route["attacker_route_share"] if dur_route else float("nan"),
                "recovery_attacker_share": rec_route["attacker_route_share"] if rec_route else float("nan"),
                "recovery_top_parent_share": rec_route["top_parent_share"] if rec_route else float("nan"),
                "recovery_parent_entropy": rec_route["parent_entropy"] if rec_route else float("nan"),
                "recovery_att18_tewma": attacker_mean("recovery", 18),
                "during_att18_tewma": attacker_mean("during_attack", 18),
                "recovery_attacker_tewma_mean": attacker_mean("recovery"),
                "during_attacker_tewma_mean": attacker_mean("during_attack"),
            }
        )
    seed_df = pd.DataFrame(seed_rows)
    sep_df = pd.DataFrame(trust_sep_rows)
    route_df = pd.DataFrame(route_rows)
    return seed_df, sep_df, route_df


def threshold_times() -> pd.DataFrame:
    base = RESULTS / "TABRPL"
    rows = []
    for seed_dir in sorted([p for p in base.iterdir() if p.is_dir() and p.name.isdigit()], key=lambda p: int(p.name)):
        seed = int(seed_dir.name)
        _, _, _, _, trust_records, attacker_ids = pr.parse_log(seed_dir / "sim.log")
        grouped = defaultdict(list)
        for r in trust_records:
            if r["approx_tick"] >= ATTACK_START:
                grouped[(r["self_id"], r["nbr_id"])].append(r)
        for (self_id, nbr_id), records in grouped.items():
            records.sort(key=lambda r: r["approx_tick"])
            label = "attacker" if nbr_id in attacker_ids else "benign"
            for name, thr in [("tau_warn", TAU_WARN), ("tau_join", TAU_JOIN), ("tau_black", TAU_BLACK)]:
                cross = next((r["approx_tick"] for r in records if r["t_ewma"] < thr), None)
                rows.append(
                    {
                        "seed": seed,
                        "self_id": self_id,
                        "nbr_id": nbr_id,
                        "class": label,
                        "threshold": name,
                        "time_ms": cross if cross is not None else float("nan"),
                    }
                )
    return pd.DataFrame(rows)


def build_seed_dependence(seed_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    corr_rows = []
    for y in ["during_pdr", "recovery_pdr"]:
        for x in [
            "during_allowed_candidates",
            "recovery_allowed_candidates",
            "during_attacker_share",
            "recovery_attacker_share",
            "recovery_att18_tewma",
            "during_blacklists",
            "recovery_blacklists",
            "during_escapes",
            "recovery_escapes",
            "recovery_top_parent_share",
        ]:
            xs = seed_df[x].tolist()
            ys = seed_df[y].tolist()
            corr_rows.append({"x": x, "y": y, "pearson_r": safe_corr(xs, ys)})

    ranked = seed_df.assign(score=seed_df["during_pdr"] + seed_df["recovery_pdr"]).sort_values("score")
    worst5 = ranked.head(5)
    best5 = ranked.tail(5)
    compare_rows = []
    for col in [
        "during_pdr",
        "recovery_pdr",
        "during_allowed_candidates",
        "recovery_allowed_candidates",
        "during_attacker_share",
        "recovery_attacker_share",
        "recovery_att18_tewma",
        "during_blacklists",
        "recovery_blacklists",
        "during_escapes",
    ]:
        compare_rows.append(
            {
                "metric": col,
                "worst5_mean": mean_or_nan(worst5[col]),
                "best5_mean": mean_or_nan(best5[col]),
            }
        )
    return pd.DataFrame(corr_rows), pd.DataFrame(compare_rows)


def plot_noattack_seed_spread(seed_df: pd.DataFrame) -> None:
    out = FIGURES / "fig7_noattack_seed_spread.pdf"
    seeds = seed_df["seed"].tolist()
    plt.figure(figsize=(6.4, 3.8))
    for phase, color in [("pre_pdr", "#5c8f6b"), ("during_pdr", "#d88c3a"), ("recovery_pdr", "#b04b57")]:
        plt.plot(seeds, seed_df[phase], marker="o", label=phase.replace("_pdr", ""), color=color)
    plt.ylim(0.6, 1.02)
    plt.xlabel("Seed")
    plt.ylabel("PDR")
    plt.title("TA-BRPL no-attack seed variability")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(out)
    plt.close()


def plot_seed_failure_correlation(seed_df: pd.DataFrame) -> None:
    out = FIGURES / "fig8_seed_failure_correlation.pdf"
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4))
    axes[0].scatter(seed_df["recovery_allowed_candidates"], seed_df["recovery_pdr"], c="#3567a5")
    axes[0].set_xlabel("Recovery allowed candidates")
    axes[0].set_ylabel("Recovery PDR")
    axes[0].set_title("Candidate set vs recovery")
    axes[1].scatter(seed_df["recovery_att18_tewma"], seed_df["recovery_pdr"], c="#b04b57")
    axes[1].set_xlabel("Recovery attacker 18 T_ewma")
    axes[1].set_ylabel("Recovery PDR")
    axes[1].set_title("Attacker 18 trust vs recovery")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_noattack_diagnostics(phase_df: pd.DataFrame) -> None:
    out = FIGURES / "fig9_noattack_diagnostics.pdf"
    avg = phase_df.groupby("phase").mean(numeric_only=True).reindex(PHASES)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6))
    x = np.arange(len(PHASES))
    w = 0.24

    axes[0].bar(x - w, avg["false_blacklist_count"], width=w, label="False blacklist", color="#b04b57")
    axes[0].bar(x, avg["escape_count"], width=w, label="Escape", color="#d88c3a")
    axes[0].bar(x + w, avg["parent_churn_count"], width=w, label="Churn", color="#3567a5")
    axes[0].set_xticks(x, ["Pre", "During", "Recovery"])
    axes[0].set_title("No-attack control activity")
    axes[0].legend(frameon=False, fontsize=8)

    axes[1].plot(x, avg["allowed_candidates_mean"], marker="o", label="Allowed candidates", color="#3567a5")
    axes[1].plot(x, avg["excluded_parent_ratio"] * 100, marker="s", label="Excluded ratio (%)", color="#b04b57")
    axes[1].plot(x, avg["pdr"] * 100, marker="^", label="PDR (%)", color="#5c8f6b")
    axes[1].set_xticks(x, ["Pre", "During", "Recovery"])
    axes[1].set_title("No-attack stability profile")
    axes[1].legend(frameon=False, fontsize=8)

    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_trust_separability(sep_df: pd.DataFrame) -> None:
    out = FIGURES / "fig10_trust_separability.pdf"
    agg = (
        sep_df[sep_df["metric"].isin(["t_fwd", "t_ctrl", "t_ewma"])]
        .groupby(["phase", "metric"])[["attacker_mean", "benign_mean", "overlap_coeff"]]
        .mean()
        .reset_index()
    )
    phases = ["during_attack", "recovery"]
    metrics = ["t_fwd", "t_ctrl", "t_ewma"]
    labels = {"t_fwd": r"$T_{fwd}$", "t_ctrl": r"$T_{ctrl}$", "t_ewma": r"$T_{ewma}$"}

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6))
    for ax, phase, title in zip(axes, phases, ["During", "Recovery"]):
        sub = agg[agg["phase"] == phase].set_index("metric").loc[metrics]
        x = np.arange(len(metrics))
        w = 0.35
        ax.bar(x - w / 2, sub["attacker_mean"], width=w, label="Attacker", color="#b04b57")
        ax.bar(x + w / 2, sub["benign_mean"], width=w, label="Benign", color="#3567a5")
        ax.set_xticks(x, [labels[m] for m in metrics])
        ax.set_ylim(0, 1050)
        ax.set_title(title)
        for i, ov in enumerate(sub["overlap_coeff"]):
            ax.text(i, max(sub["attacker_mean"].iloc[i], sub["benign_mean"].iloc[i]) + 30, f"ov={ov:.2f}",
                    ha="center", va="bottom", fontsize=8)
    axes[0].set_ylabel("Trust value")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Attacker vs benign trust separability")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_route_phase_summary(route_df: pd.DataFrame) -> None:
    out = FIGURES / "fig11_route_phase_summary.pdf"
    avg = route_df.groupby("phase").mean(numeric_only=True).reindex(PHASES)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6))
    x = np.arange(len(PHASES))
    w = 0.25

    axes[0].bar(x - w, avg["node2_share"], width=w, label="node 2", color="#d88c3a")
    axes[0].bar(x, avg["node3_share"], width=w, label="node 3", color="#c95f4a")
    axes[0].bar(x + w, avg["node4_share"], width=w, label="node 4", color="#b04b57")
    axes[0].plot(x, avg["node18_share"], marker="o", label="node 18", color="#3567a5")
    axes[0].set_xticks(x, ["Pre", "During", "Recovery"])
    axes[0].set_title("Attacker parent adoption")
    axes[0].legend(frameon=False, fontsize=8)

    axes[1].plot(x, avg["avg_hop"], marker="o", label="Avg hop", color="#3567a5")
    axes[1].plot(x, avg["top_parent_share"] * 100, marker="s", label="Top parent share (%)", color="#b04b57")
    axes[1].plot(x, avg["unique_parents"], marker="^", label="Unique parents", color="#5c8f6b")
    axes[1].set_xticks(x, ["Pre", "During", "Recovery"])
    axes[1].set_title("Route diversity and path cost")
    axes[1].legend(frameon=False, fontsize=8)

    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_threshold_crossing(threshold_df: pd.DataFrame) -> None:
    out = FIGURES / "fig12_threshold_crossing.pdf"
    df = threshold_df.dropna(subset=["time_ms"]).copy()
    df = df[df["threshold"].isin(["tau_warn", "tau_join"])]
    summary = (
        df.groupby(["class", "threshold"])["time_ms"]
        .median()
        .unstack(0)
        .reindex(["tau_warn", "tau_join"])
    )
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    x = np.arange(len(summary.index))
    w = 0.35
    ax.bar(x - w / 2, summary["attacker"] / 1000.0, width=w, label="Attacker", color="#b04b57")
    ax.bar(x + w / 2, summary["benign"] / 1000.0, width=w, label="Benign", color="#3567a5")
    ax.set_xticks(x, [r"$\tau_{warn}$", r"$\tau_{join}$"])
    ax.set_ylabel("Median crossing time (s)")
    ax.set_title("Threshold crossing time")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    SUMMARIES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    noattack_seed_df, noattack_phase_df = analyze_noattack()
    noattack_seed_df.to_csv(SUMMARIES / "noattack_seed_pdr.csv", index=False)
    noattack_phase_df.to_csv(SUMMARIES / "noattack_stability_metrics.csv", index=False)

    baseline_seed_df, sep_df, route_df = analyze_baseline_seeds()
    baseline_seed_df.to_csv(SUMMARIES / "baseline_seed_metrics.csv", index=False)
    sep_df.to_csv(SUMMARIES / "trust_separability_metrics.csv", index=False)
    route_df.to_csv(SUMMARIES / "route_level_metrics.csv", index=False)

    thresholds_df = threshold_times()
    thresholds_df.to_csv(SUMMARIES / "threshold_times.csv", index=False)

    corr_df, bestworst_df = build_seed_dependence(baseline_seed_df)
    corr_df.to_csv(SUMMARIES / "seed_dependence_correlations.csv", index=False)
    bestworst_df.to_csv(SUMMARIES / "seed_dependence_bestworst.csv", index=False)

    plot_noattack_seed_spread(noattack_seed_df.rename(columns={
        "pre_attack_pdr": "pre_pdr",
        "during_attack_pdr": "during_pdr",
        "recovery_pdr": "recovery_pdr",
    }) if "pre_attack_pdr" in noattack_seed_df.columns else noattack_seed_df.rename(columns={
        "pre_attack": "pre_pdr"
    }))
    plot_noattack_diagnostics(noattack_phase_df)
    plot_trust_separability(sep_df)
    plot_route_phase_summary(route_df)
    plot_threshold_crossing(thresholds_df)
    plot_seed_failure_correlation(baseline_seed_df)

    print("wrote", SUMMARIES)
    print(
        "figures:",
        FIGURES / "fig7_noattack_seed_spread.pdf",
        FIGURES / "fig8_seed_failure_correlation.pdf",
        FIGURES / "fig9_noattack_diagnostics.pdf",
        FIGURES / "fig10_trust_separability.pdf",
        FIGURES / "fig11_route_phase_summary.pdf",
        FIGURES / "fig12_threshold_crossing.pdf",
    )


if __name__ == "__main__":
    main()
