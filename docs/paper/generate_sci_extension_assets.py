#!/usr/bin/env python3
"""Generate SCI-oriented extension assets for TA-BRPL paper.

This script adds three evidence bundles:
1) 4-baseline comparison on the same 75-topology set used by Main v2.
2) Robustness matrix summary from pre-parsed LOSS x ATTACK results.
3) Mechanism-level admission/retention/re-entry evidence from Main v2 logs.
"""

from __future__ import annotations

import argparse
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, wilcoxon


PHASE_DURING = (350_000, 650_000)
NI_MARGIN_DEFAULT = -0.02
PROTOCOLS_4WAY = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
BASELINES = ["BRPL", "RPL", "SMTRUST"]


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


def fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "nan"
    if p < 1e-4:
        return "<1e-4"
    return f"{p:.4f}"


def rank_biserial_from_diffs(d: np.ndarray) -> float:
    nz = d[np.isfinite(d)]
    nz = nz[nz != 0]
    if len(nz) == 0:
        return 0.0
    ranks = rankdata(np.abs(nz), method="average")
    w_plus = float(np.sum(ranks[nz > 0]))
    w_minus = float(np.sum(ranks[nz < 0]))
    denom = w_plus + w_minus
    if denom <= 0:
        return 0.0
    return (w_plus - w_minus) / denom


def signed_rank_pvalue(d: np.ndarray, better: str) -> tuple[float, float]:
    vals = d[np.isfinite(d)]
    vals = vals[vals != 0]
    if len(vals) == 0:
        return 0.0, 1.0
    if better == "lower":
        alt = "less"
    elif better == "higher":
        alt = "greater"
    else:
        raise ValueError(f"invalid better={better}")
    stat, p = wilcoxon(
        vals,
        alternative=alt,
        zero_method="wilcox",
        correction=False,
        mode="auto",
    )
    return float(stat), float(p)


def selected_topologies(main_v2_results_dir: Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for density_dir in sorted(main_v2_results_dir.iterdir()):
        if not density_dir.is_dir():
            continue
        density = density_dir.name
        for topo_dir in sorted(density_dir.iterdir()):
            if not topo_dir.is_dir():
                continue
            out.add((density, topo_dir.name))
    return out


def _prepare_random_topo_run_df(
    random_topo_by_run_csv: Path,
    main_v2_results_dir: Path,
) -> pd.DataFrame:
    df = pd.read_csv(random_topo_by_run_csv)
    selected = selected_topologies(main_v2_results_dir)
    df["key"] = list(zip(df["density"].astype(str), df["topology"].astype(str)))
    df = df[df["key"].isin(selected)].copy()
    df = df[df["protocol"].isin(PROTOCOLS_4WAY)].copy()
    # Keep only metrics used in paper-level comparisons.
    keep_cols = [
        "density",
        "topology",
        "protocol",
        "seed",
        "pdr_during",
        "route_att_share_during",
        "run_hit_ratio_during",
        "churn_during",
    ]
    df = df[keep_cols].rename(
        columns={
            "pdr_during": "pdr_dur",
            "route_att_share_during": "att_share",
            "run_hit_ratio_during": "hit_ratio",
            "churn_during": "churn",
        }
    )
    return df


def analyze_baseline_4way(
    random_topo_by_run_csv: Path,
    main_v2_results_dir: Path,
    out_dir: Path,
    ni_margin: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_df = _prepare_random_topo_run_df(random_topo_by_run_csv, main_v2_results_dir)
    run_df.to_csv(out_dir / "baseline75_metrics_by_run.csv", index=False)

    topo_df = (
        run_df.groupby(["density", "topology", "protocol"], as_index=False)[
            ["att_share", "hit_ratio", "pdr_dur", "churn"]
        ]
        .mean(numeric_only=True)
    )
    topo_df.to_csv(out_dir / "baseline75_metrics_by_topology.csv", index=False)

    proto_summary = (
        topo_df.groupby("protocol", as_index=False)[["att_share", "hit_ratio", "pdr_dur", "churn"]]
        .mean(numeric_only=True)
        .copy()
    )
    proto_summary["n_topologies"] = (
        topo_df.groupby("protocol")["topology"].count().reindex(proto_summary["protocol"]).values
    )
    proto_summary = proto_summary[["protocol", "n_topologies", "att_share", "hit_ratio", "pdr_dur", "churn"]]
    proto_summary.to_csv(out_dir / "baseline75_protocol_summary.csv", index=False)

    # Paired topology-level tests: TABRPL vs each baseline.
    metric_specs = [
        ("att_share", "lower"),
        ("hit_ratio", "lower"),
        ("pdr_dur", "higher"),
        ("churn", "lower"),
    ]
    rows: list[dict] = []
    tab = topo_df[topo_df["protocol"] == "TABRPL"].copy()
    for base in BASELINES:
        b = topo_df[topo_df["protocol"] == base].copy()
        merged = tab.merge(
            b,
            on=["density", "topology"],
            suffixes=("_tabrpl", "_base"),
            how="inner",
        )
        for metric, better in metric_specs:
            d = merged[f"{metric}_tabrpl"].to_numpy(dtype=float) - merged[f"{metric}_base"].to_numpy(dtype=float)
            stat, p = signed_rank_pvalue(d, better)
            rb_raw = rank_biserial_from_diffs(d)
            rb_aligned = rb_raw if better == "higher" else -rb_raw
            rows.append(
                {
                    "baseline": base,
                    "metric": metric,
                    "n_topologies": int(len(d)),
                    "mean_delta": float(np.nanmean(d)),
                    "median_delta": float(np.nanmedian(d)),
                    "wilcoxon_stat": stat,
                    "p_value": p,
                    "rank_biserial_aligned": rb_aligned,
                }
            )

        # Non-inferiority for PDR
        d_pdr = merged["pdr_dur_tabrpl"].to_numpy(dtype=float) - merged["pdr_dur_base"].to_numpy(dtype=float)
        shifted = d_pdr - ni_margin
        stat_ni, p_ni = signed_rank_pvalue(shifted, "higher")
        rows.append(
            {
                "baseline": base,
                "metric": "pdr_noninferiority",
                "n_topologies": int(len(d_pdr)),
                "mean_delta": float(np.nanmean(d_pdr)),
                "median_delta": float(np.nanmedian(d_pdr)),
                "wilcoxon_stat": stat_ni,
                "p_value": p_ni,
                "rank_biserial_aligned": rank_biserial_from_diffs(shifted),
                "ni_margin": ni_margin,
                "ni_pass_0_05": bool(p_ni < 0.05),
            }
        )

    pair_df = pd.DataFrame(rows)
    pair_df.to_csv(out_dir / "baseline75_tabrpl_vs_baselines.csv", index=False)

    # TeX: protocol means
    lines = []
    lines.append("% Auto-generated by generate_sci_extension_assets.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{4-baseline overall means on the Main-v2 75-topology set}")
    lines.append("\\label{tab:baseline75_protocol_means}")
    lines.append("\\begin{tabular}{lrrrrr}")
    lines.append("\\toprule")
    lines.append("Protocol & $n_{topo}$ & att\\_share & hit\\_ratio & PDR$_{dur}$ & churn \\\\")
    lines.append("\\midrule")
    order = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
    s = proto_summary.copy()
    s["protocol"] = pd.Categorical(s["protocol"], order, ordered=True)
    s = s.sort_values("protocol")
    for _, r in s.iterrows():
        lines.append(
            f"{tex_escape(r['protocol'])} & {int(r['n_topologies'])} & "
            f"{float(r['att_share']):.4f} & {float(r['hit_ratio']):.4f} & "
            f"{float(r['pdr_dur']):.4f} & {float(r['churn']):.4f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    (out_dir / "table_baseline75_protocol_means.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # TeX: TABRPL vs baselines
    metric_order = ["att_share", "hit_ratio", "pdr_dur", "churn", "pdr_noninferiority"]
    p = pair_df.copy()
    p["metric"] = pd.Categorical(p["metric"], metric_order, ordered=True)
    p = p.sort_values(["baseline", "metric"])

    lines = []
    lines.append("% Auto-generated by generate_sci_extension_assets.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Paired topology tests: TA-BRPL vs baselines (75-topology set)}")
    lines.append("\\label{tab:baseline75_tabrpl_vs_baselines}")
    lines.append("\\begin{tabular}{llrrrr}")
    lines.append("\\toprule")
    lines.append("Baseline & Metric & Mean $\\Delta$ & Median $\\Delta$ & $p$ & $r_{rb}$ (aligned) \\\\")
    lines.append("\\midrule")
    for _, r in p.iterrows():
        metric = "PDR-NI" if r["metric"] == "pdr_noninferiority" else tex_escape(str(r["metric"]))
        lines.append(
            f"{tex_escape(r['baseline'])} & {metric} & "
            f"{float(r['mean_delta']):+.4f} & {float(r['median_delta']):+.4f} & "
            f"{fmt_p(float(r['p_value']))} & {float(r['rank_biserial_aligned']):+.3f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    (out_dir / "table_baseline75_tabrpl_vs_baselines.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scenario_name_to_axes(name: str) -> tuple[int, int]:
    # results_L10_A070 -> (10, 70)
    m = re.match(r"results_L(\d{2})_A(\d{3})$", name)
    if m is None:
        raise ValueError(f"invalid scenario name: {name}")
    return int(m.group(1)), int(m.group(2))


def _analyze_single_loss_attack_scenario(
    scenario_dir: Path,
    ni_margin: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pdr = pd.read_csv(scenario_dir / "pdr_summary.csv")
    route = pd.read_csv(
        scenario_dir / "route_trace.csv",
        usecols=["protocol", "seed", "node_id", "tick", "parent_is_attacker"],
    )
    churn = pd.read_csv(
        scenario_dir / "parent_churn.csv",
        usecols=["protocol", "seed", "node_id", "churn_during_attack"],
    )

    lo, hi = PHASE_DURING
    rd = route[(route["tick"] >= lo) & (route["tick"] < hi)].copy()

    g_route = rd.groupby(["protocol", "seed"], as_index=False).agg(
        route_total=("parent_is_attacker", "size"),
        route_att=("parent_is_attacker", "sum"),
        nodes_seen=("node_id", "nunique"),
    )
    hit = (
        rd[rd["parent_is_attacker"] == 1]
        .groupby(["protocol", "seed"], as_index=False)["node_id"]
        .nunique()
        .rename(columns={"node_id": "nodes_hit"})
    )
    g_route = g_route.merge(hit, on=["protocol", "seed"], how="left")
    g_route["nodes_hit"] = g_route["nodes_hit"].fillna(0)
    g_route["att_share"] = np.where(g_route["route_total"] > 0, g_route["route_att"] / g_route["route_total"], np.nan)
    g_route["hit_ratio"] = np.where(g_route["nodes_seen"] > 0, g_route["nodes_hit"] / g_route["nodes_seen"], np.nan)
    g_route = g_route[["protocol", "seed", "att_share", "hit_ratio"]]

    g_churn = churn.groupby(["protocol", "seed"], as_index=False).agg(
        churn_sum=("churn_during_attack", "sum"),
        n_nodes=("node_id", "nunique"),
    )
    g_churn["churn"] = np.where(g_churn["n_nodes"] > 0, g_churn["churn_sum"] / g_churn["n_nodes"], np.nan)
    g_churn = g_churn[["protocol", "seed", "churn"]]

    pdr_s = pdr[["protocol", "seed", "pdr_during_attack"]].rename(columns={"pdr_during_attack": "pdr_dur"})
    run = pdr_s.merge(g_route, on=["protocol", "seed"], how="inner").merge(g_churn, on=["protocol", "seed"], how="inner")

    proto_summary = (
        run.groupby("protocol", as_index=False)[["att_share", "hit_ratio", "pdr_dur", "churn"]]
        .mean(numeric_only=True)
    )
    proto_summary["n_runs"] = run.groupby("protocol")["seed"].count().reindex(proto_summary["protocol"]).values

    tab = run[run["protocol"] == "TABRPL"].copy()
    brp = run[run["protocol"] == "BRPL"].copy()
    paired = tab.merge(brp, on="seed", suffixes=("_tabrpl", "_brpl"), how="inner")
    for m in ["att_share", "hit_ratio", "pdr_dur", "churn"]:
        paired[f"delta_{m}"] = paired[f"{m}_tabrpl"] - paired[f"{m}_brpl"]

    stat_rows = []
    for m, better in [("att_share", "lower"), ("hit_ratio", "lower"), ("pdr_dur", "higher"), ("churn", "lower")]:
        d = paired[f"delta_{m}"].to_numpy(dtype=float)
        stat, p = signed_rank_pvalue(d, better)
        rb_raw = rank_biserial_from_diffs(d)
        rb_aligned = rb_raw if better == "higher" else -rb_raw
        stat_rows.append(
            {
                "metric": m,
                "n": int(len(d)),
                "mean_delta": float(np.nanmean(d)),
                "median_delta": float(np.nanmedian(d)),
                "wilcoxon_stat": stat,
                "p_value": p,
                "rank_biserial_aligned": rb_aligned,
            }
        )

    d_pdr = paired["delta_pdr_dur"].to_numpy(dtype=float)
    shifted = d_pdr - ni_margin
    stat_ni, p_ni = signed_rank_pvalue(shifted, "higher")
    stat_rows.append(
        {
            "metric": "pdr_noninferiority",
            "n": int(len(d_pdr)),
            "mean_delta": float(np.nanmean(d_pdr)),
            "median_delta": float(np.nanmedian(d_pdr)),
            "wilcoxon_stat": stat_ni,
            "p_value": p_ni,
            "rank_biserial_aligned": rank_biserial_from_diffs(shifted),
            "ni_margin": ni_margin,
            "ni_pass_0_05": bool(p_ni < 0.05),
        }
    )
    return run, pd.DataFrame(stat_rows)


def analyze_robustness_matrix(
    results_root: Path,
    out_dir: Path,
    ni_margin: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario_dirs = sorted(
        [
            p
            for p in results_root.iterdir()
            if p.is_dir() and re.match(r"results_L\d{2}_A\d{3}$", p.name)
        ]
    )

    scenario_rows: list[dict] = []
    all_stats_rows: list[dict] = []
    all_runs: list[pd.DataFrame] = []
    for scen in scenario_dirs:
        loss_pct, attack_pct = _scenario_name_to_axes(scen.name)
        run_df, stat_df = _analyze_single_loss_attack_scenario(scen, ni_margin)
        run_df["scenario"] = scen.name
        run_df["loss_pct"] = loss_pct
        run_df["attack_pct"] = attack_pct
        all_runs.append(run_df)

        stat_df["scenario"] = scen.name
        stat_df["loss_pct"] = loss_pct
        stat_df["attack_pct"] = attack_pct
        all_stats_rows.append(stat_df)

        get = lambda metric: stat_df.loc[stat_df["metric"] == metric].iloc[0]
        r_att = get("att_share")
        r_hit = get("hit_ratio")
        r_pdr = get("pdr_dur")
        r_churn = get("churn")
        r_ni = get("pdr_noninferiority")
        scenario_rows.append(
            {
                "scenario": scen.name,
                "loss_pct": loss_pct,
                "attack_pct": attack_pct,
                "delta_att_share": float(r_att["mean_delta"]),
                "delta_hit_ratio": float(r_hit["mean_delta"]),
                "delta_pdr_dur": float(r_pdr["mean_delta"]),
                "delta_churn": float(r_churn["mean_delta"]),
                "p_att": float(r_att["p_value"]),
                "p_hit": float(r_hit["p_value"]),
                "p_pdr": float(r_pdr["p_value"]),
                "p_pdr_ni": float(r_ni["p_value"]),
                "ni_pass_0_05": bool(r_ni.get("ni_pass_0_05", False)),
            }
        )

    run_all = pd.concat(all_runs, ignore_index=True) if all_runs else pd.DataFrame()
    stat_all = pd.concat(all_stats_rows, ignore_index=True) if all_stats_rows else pd.DataFrame()
    scen_df = pd.DataFrame(scenario_rows).sort_values(["loss_pct", "attack_pct"])

    run_all.to_csv(out_dir / "robustness_loss_attack_by_run.csv", index=False)
    stat_all.to_csv(out_dir / "robustness_loss_attack_stats_by_scenario.csv", index=False)
    scen_df.to_csv(out_dir / "robustness_loss_attack_tabrpl_vs_brpl.csv", index=False)

    # Axis summaries.
    by_loss = (
        scen_df.groupby("loss_pct", as_index=False)[
            ["delta_att_share", "delta_hit_ratio", "delta_pdr_dur", "delta_churn", "ni_pass_0_05"]
        ]
        .mean(numeric_only=True)
        .rename(columns={"ni_pass_0_05": "ni_pass_rate"})
    )
    by_attack = (
        scen_df.groupby("attack_pct", as_index=False)[
            ["delta_att_share", "delta_hit_ratio", "delta_pdr_dur", "delta_churn", "ni_pass_0_05"]
        ]
        .mean(numeric_only=True)
        .rename(columns={"ni_pass_0_05": "ni_pass_rate"})
    )
    by_loss.to_csv(out_dir / "robustness_axis_by_loss.csv", index=False)
    by_attack.to_csv(out_dir / "robustness_axis_by_attack.csv", index=False)

    # Compact summary table.
    summary = {
        "n_scenarios": int(len(scen_df)),
        "att_share_win_scenarios": int((scen_df["delta_att_share"] < 0).sum()) if len(scen_df) else 0,
        "hit_ratio_win_scenarios": int((scen_df["delta_hit_ratio"] < 0).sum()) if len(scen_df) else 0,
        "pdr_noninferior_scenarios": int(scen_df["ni_pass_0_05"].sum()) if len(scen_df) else 0,
    }
    pd.DataFrame([summary]).to_csv(out_dir / "robustness_scenario_win_counts.csv", index=False)

    lines = []
    lines.append("% Auto-generated by generate_sci_extension_assets.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Robustness summary by link-loss axis (TA-BRPL - BRPL)}")
    lines.append("\\label{tab:robustness_axis_loss}")
    lines.append("\\begin{tabular}{rrrrrr}")
    lines.append("\\toprule")
    lines.append("Loss(\\%) & $\\Delta$att\\_share & $\\Delta$hit\\_ratio & $\\Delta$PDR$_{dur}$ & $\\Delta$churn & NI pass rate \\\\")
    lines.append("\\midrule")
    for _, r in by_loss.sort_values("loss_pct").iterrows():
        lines.append(
            f"{int(r['loss_pct'])} & {float(r['delta_att_share']):+.4f} & {float(r['delta_hit_ratio']):+.4f} & "
            f"{float(r['delta_pdr_dur']):+.4f} & {float(r['delta_churn']):+.4f} & {float(r['ni_pass_rate']):.2f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    (out_dir / "table_robustness_axis_by_loss.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = []
    lines.append("% Auto-generated by generate_sci_extension_assets.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Robustness summary by attack-drop axis (TA-BRPL - BRPL)}")
    lines.append("\\label{tab:robustness_axis_attack}")
    lines.append("\\begin{tabular}{rrrrrr}")
    lines.append("\\toprule")
    lines.append("Attack drop(\\%) & $\\Delta$att\\_share & $\\Delta$hit\\_ratio & $\\Delta$PDR$_{dur}$ & $\\Delta$churn & NI pass rate \\\\")
    lines.append("\\midrule")
    for _, r in by_attack.sort_values("attack_pct").iterrows():
        lines.append(
            f"{int(r['attack_pct'])} & {float(r['delta_att_share']):+.4f} & {float(r['delta_hit_ratio']):+.4f} & "
            f"{float(r['delta_pdr_dur']):+.4f} & {float(r['delta_churn']):+.4f} & {float(r['ni_pass_rate']):.2f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    (out_dir / "table_robustness_axis_by_attack.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_route_samples_and_attackers(sim_log: Path) -> tuple[set[int], dict[int, list[tuple[int, int, int]]]]:
    attackers: set[int] = set()
    by_node: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    if not sim_log.exists():
        return attackers, by_node

    for raw in sim_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        i = raw.find("CSV,")
        if i < 0:
            continue
        s = raw[i:].strip()
        parts = s.split(",")
        if len(parts) < 2:
            continue
        tag = parts[1]

        if tag == "PROTOCOL" and len(parts) >= 4:
            try:
                node_id = int(parts[2])
            except ValueError:
                continue
            proto_name = parts[3].strip().upper()
            if proto_name.startswith("ATTACKER") or proto_name.startswith("SINKHOLE"):
                attackers.add(node_id)
            continue

        if tag == "ROUTE" and len(parts) >= 11:
            try:
                node_id = int(parts[2])
                tick = int(parts[3])
                parent = int(parts[4])
                parent_is_att = int(parts[9])
            except ValueError:
                continue
            by_node[node_id].append((tick, parent, parent_is_att))
    return attackers, by_node


def _mechanism_from_route_samples(
    by_node: dict[int, list[tuple[int, int, int]]],
    attackers: set[int],
    *,
    root_id: int = 1,
    attack_start: int = PHASE_DURING[0],
    attack_end: int = PHASE_DURING[1],
) -> dict[str, float]:
    node_count = 0
    adoption = 0
    reentry = 0
    dwell_sum_ms = 0.0
    dwell_n = 0
    esc_latency_sum_ms = 0.0
    esc_latency_n = 0

    for node, samples in by_node.items():
        if node == root_id or node in attackers:
            continue
        if not samples:
            continue
        samples = sorted(samples, key=lambda x: x[0])
        state_before = None
        during: list[tuple[int, bool]] = []
        for tick, parent, parent_is_att in samples:
            is_att = bool(parent_is_att == 1 or parent in attackers)
            if tick <= attack_start:
                state_before = is_att
            elif tick <= attack_end:
                during.append((tick, is_att))
            elif tick > attack_end:
                break

        if state_before is None and not during:
            continue
        node_count += 1

        prev_att = state_before
        current_att_start = attack_start if (state_before is True) else None
        escaped_once = False
        pending_adopt_tick = None

        for tick, now_att in during:
            if prev_att is None:
                prev_att = now_att
                if now_att and current_att_start is None:
                    current_att_start = tick
                continue

            if now_att != prev_att:
                if (not prev_att) and now_att:
                    adoption += 1
                    if escaped_once:
                        reentry += 1
                    pending_adopt_tick = tick
                    current_att_start = tick
                elif prev_att and (not now_att):
                    if current_att_start is not None:
                        dwell_sum_ms += max(0, tick - current_att_start)
                        dwell_n += 1
                        current_att_start = None
                    escaped_once = True
                    if pending_adopt_tick is not None:
                        esc_latency_sum_ms += max(0, tick - pending_adopt_tick)
                        esc_latency_n += 1
                        pending_adopt_tick = None
            prev_att = now_att

        if prev_att is True:
            start_tick = current_att_start if current_att_start is not None else attack_start
            if attack_end > start_tick:
                dwell_sum_ms += float(attack_end - start_tick)
                dwell_n += 1

    return {
        "node_count": float(node_count),
        "new_attacker_adoption_rate": (adoption / node_count) if node_count > 0 else np.nan,
        "attacker_reentry_count_per_node": (reentry / node_count) if node_count > 0 else np.nan,
        "attacker_parent_retention_time_s": (dwell_sum_ms / dwell_n / 1000.0) if dwell_n > 0 else np.nan,
        "escape_latency_after_attack_s": (esc_latency_sum_ms / esc_latency_n / 1000.0) if esc_latency_n > 0 else np.nan,
    }


def analyze_mechanism_main_v2(main_v2_results_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for density_dir in sorted(main_v2_results_dir.iterdir()):
        if not density_dir.is_dir():
            continue
        density = density_dir.name
        for topo_dir in sorted(density_dir.iterdir()):
            if not topo_dir.is_dir():
                continue
            topology = topo_dir.name
            for proto_dir in sorted(topo_dir.iterdir()):
                if not proto_dir.is_dir():
                    continue
                proto = proto_dir.name
                if proto not in {"BRPL", "TABRPL"}:
                    continue
                for seed_dir in sorted(proto_dir.iterdir()):
                    if not seed_dir.is_dir():
                        continue
                    sim_log = seed_dir / "sim.log"
                    attackers, by_node = _parse_route_samples_and_attackers(sim_log)
                    m = _mechanism_from_route_samples(by_node, attackers)
                    rows.append(
                        {
                            "density": density,
                            "topology": topology,
                            "protocol": proto,
                            "run_seed": int(seed_dir.name),
                            **m,
                        }
                    )

    run_df = pd.DataFrame(rows)
    run_df.to_csv(out_dir / "mechanism_main_v2_by_run.csv", index=False)

    topo_df = (
        run_df.groupby(["density", "topology", "protocol"], as_index=False)[
            [
                "new_attacker_adoption_rate",
                "attacker_reentry_count_per_node",
                "attacker_parent_retention_time_s",
                "escape_latency_after_attack_s",
            ]
        ]
        .mean(numeric_only=True)
    )
    topo_df.to_csv(out_dir / "mechanism_main_v2_by_topology.csv", index=False)

    sum_df = (
        topo_df.groupby("protocol", as_index=False)[
            [
                "new_attacker_adoption_rate",
                "attacker_reentry_count_per_node",
                "attacker_parent_retention_time_s",
                "escape_latency_after_attack_s",
            ]
        ]
        .mean(numeric_only=True)
    )
    sum_df.to_csv(out_dir / "mechanism_main_v2_protocol_summary.csv", index=False)

    # Paired topology-level TABRPL-BRPL deltas for mechanism metrics.
    tab = topo_df[topo_df["protocol"] == "TABRPL"].copy()
    brp = topo_df[topo_df["protocol"] == "BRPL"].copy()
    pair = tab.merge(brp, on=["density", "topology"], suffixes=("_tabrpl", "_brpl"), how="inner")

    specs = [
        "new_attacker_adoption_rate",
        "attacker_reentry_count_per_node",
        "attacker_parent_retention_time_s",
        "escape_latency_after_attack_s",
    ]
    rows = []
    for m in specs:
        d = pair[f"{m}_tabrpl"].to_numpy(dtype=float) - pair[f"{m}_brpl"].to_numpy(dtype=float)
        stat, p = signed_rank_pvalue(d, "lower")
        rows.append(
            {
                "metric": m,
                "n_topologies": int(len(d)),
                "mean_delta": float(np.nanmean(d)),
                "median_delta": float(np.nanmedian(d)),
                "wilcoxon_stat": stat,
                "p_value": p,
                "rank_biserial_aligned": -rank_biserial_from_diffs(d),
            }
        )
    mech_test_df = pd.DataFrame(rows)
    mech_test_df.to_csv(out_dir / "mechanism_main_v2_tabrpl_vs_brpl.csv", index=False)

    # TeX table: absolute means + deltas.
    idx = sum_df.set_index("protocol")
    lines = []
    lines.append("% Auto-generated by generate_sci_extension_assets.py")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Mechanism evidence (admission/retention/re-entry, Main v2)}")
    lines.append("\\label{tab:mechanism_main_v2_admission_retention}")
    lines.append("\\begin{tabular}{lrrr}")
    lines.append("\\toprule")
    lines.append("Metric & BRPL mean & TA-BRPL mean & $\\Delta$(TA-BRPL-BRPL) \\\\")
    lines.append("\\midrule")

    label_map = {
        "new_attacker_adoption_rate": "new\\_attacker\\_adoption\\_rate",
        "attacker_reentry_count_per_node": "attacker\\_reentry\\_count",
        "attacker_parent_retention_time_s": "attacker\\_parent\\_retention\\_time (s)",
        "escape_latency_after_attack_s": "escape\\_latency\\_after\\_attack (s)",
    }
    for m in specs:
        b = float(idx.loc["BRPL", m]) if "BRPL" in idx.index else np.nan
        t = float(idx.loc["TABRPL", m]) if "TABRPL" in idx.index else np.nan
        lines.append(
            f"{label_map[m]} & {b:.4f} & {t:.4f} & {t - b:+.4f} \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    (out_dir / "table_mechanism_main_v2_admission_retention.tex").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--main-v2-results-dir",
        type=Path,
        default=Path("results/random_topo_main_v2"),
    )
    ap.add_argument(
        "--random-topo-by-run-csv",
        type=Path,
        default=Path("results/random_topo_by_run.csv"),
    )
    ap.add_argument(
        "--results-root",
        type=Path,
        default=Path("results"),
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("docs/paper/generated/sci"),
    )
    ap.add_argument("--ni-margin", type=float, default=NI_MARGIN_DEFAULT)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    analyze_baseline_4way(
        random_topo_by_run_csv=args.random_topo_by_run_csv,
        main_v2_results_dir=args.main_v2_results_dir,
        out_dir=out_dir,
        ni_margin=args.ni_margin,
    )
    analyze_robustness_matrix(
        results_root=args.results_root,
        out_dir=out_dir,
        ni_margin=args.ni_margin,
    )
    analyze_mechanism_main_v2(
        main_v2_results_dir=args.main_v2_results_dir,
        out_dir=out_dir,
    )

    print(f"[OK] SCI extension assets generated in {out_dir}")


if __name__ == "__main__":
    main()

