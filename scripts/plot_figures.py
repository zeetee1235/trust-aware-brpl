#!/usr/bin/env python3
"""
plot_figures.py — TA-BRPL publication-quality figure generator
===============================================================
Reads CSV files from results/ (produced by tools/parse_results.py) and
writes five PDF figures to figures/.

Figures produced
----------------
  fig1_pdr_phases.pdf      PDR distribution by protocol × phase
  fig2_pdr_timeseries.pdf  Actual route-exposure time series from route_trace.csv
  fig3_delay_cdf.pdf       CDF of E2E delay during attack phase
  fig4_trust_trace.pdf     TABRPL trust evolution for adversarial neighbours
  fig5_parent_churn.pdf    Parent-churn distribution plus non-zero fraction

Timing assumptions (ms)
-----------------------
  pre_attack   : 150 000 – 350 000
  during_attack: 350 000 – 650 000
  recovery     : 650 000 – 900 000
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Suppress matplotlib / pandas minor warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import seaborn as sns
    sns.set_theme(style="whitegrid", font_scale=1.1)
    _SEABORN = True
except ImportError:
    _SEABORN = False
    plt.style.use("seaborn-v0_8-whitegrid")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE        = Path(__file__).resolve().parent
RESULTS_DIR  = _HERE.parent / "results"
FIGURES_DIR  = _HERE.parent / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

PROTOCOLS    = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
PROTO_COLOR  = {
    "RPL":     "#1f77b4",   # blue
    "BRPL":    "#ff7f0e",   # orange
    "SMTRUST": "#2ca02c",   # green
    "TABRPL":  "#d62728",   # red
}
PROTO_MARKER = {"RPL": "o", "BRPL": "s", "SMTRUST": "^", "TABRPL": "D"}

PHASE_LABELS = {
    "pre_attack":    "Pre-attack",
    "during_attack": "During attack",
    "recovery":      "Recovery",
}
PHASE_ORDER  = ["pre_attack", "during_attack", "recovery"]

FIG_W, FIG_H = 6, 4        # inches
DPI          = 150

ATTACK_START_S  = 350       # seconds
ATTACK_END_S    = 650       # seconds


def _savefig(fig, name: str):
    out = FIGURES_DIR / name
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def _load(filename: str) -> pd.DataFrame | None:
    path = RESULTS_DIR / filename
    if not path.exists():
        print(f"  [SKIP] {path} not found")
        return None
    df = pd.read_csv(path)
    if df.empty:
        print(f"  [SKIP] {path} is empty")
        return None
    return df


def _ci95(values: np.ndarray) -> float:
    """95 % confidence interval half-width (normal approximation)."""
    n = len(values)
    if n < 2:
        return 0.0
    return 1.96 * float(np.std(values, ddof=1)) / np.sqrt(n)


# ---------------------------------------------------------------------------
# Figure 1 — PDR by protocol × phase  (box plot)
# ---------------------------------------------------------------------------

def fig1_pdr_phases():
    print("\nFigure 1: PDR phases box plot")
    df = _load("pdr_summary.csv")
    if df is None:
        return

    # Melt to long form: one row per (protocol, seed, phase)
    id_vars    = ["protocol", "seed"]
    value_vars = {
        "pre_attack":    "pdr_pre_attack",
        "during_attack": "pdr_during_attack",
        "recovery":      "pdr_recovery",
    }
    rows = []
    for phase_key, col in value_vars.items():
        if col not in df.columns:
            continue
        sub = df[["protocol", "seed", col]].copy()
        sub["phase"] = phase_key
        sub = sub.rename(columns={col: "pdr"})
        rows.append(sub)
    if not rows:
        print("  [SKIP] No PDR phase columns found")
        return
    long_df = pd.concat(rows, ignore_index=True)
    long_df["pdr_pct"] = long_df["pdr"] * 100.0
    long_df = long_df[long_df["protocol"].isin(PROTOCOLS)]
    long_df["phase"] = pd.Categorical(long_df["phase"], categories=PHASE_ORDER, ordered=True)

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    if _SEABORN:
        sns.boxplot(
            data=long_df,
            x="phase",
            y="pdr_pct",
            hue="protocol",
            order=PHASE_ORDER,
            hue_order=PROTOCOLS,
            palette=PROTO_COLOR,
            showfliers=False,
            width=0.72,
            ax=ax,
        )
        sns.stripplot(
            data=long_df,
            x="phase",
            y="pdr_pct",
            hue="protocol",
            order=PHASE_ORDER,
            hue_order=PROTOCOLS,
            dodge=True,
            palette=PROTO_COLOR,
            alpha=0.18,
            size=2.2,
            ax=ax,
        )
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles[:len(PROTOCOLS)], PROTOCOLS, title="Protocol",
                  loc="lower left", fontsize=9)
    else:
        n_phases = len(PHASE_ORDER)
        n_proto = len(PROTOCOLS)
        group_width = 0.8
        box_width = group_width / n_proto
        x_positions = np.arange(n_phases)
        for i, proto in enumerate(PROTOCOLS):
            offset = (i - (n_proto - 1) / 2.0) * box_width
            phase_vals = []
            for phase in PHASE_ORDER:
                mask = (long_df["protocol"] == proto) & (long_df["phase"] == phase)
                phase_vals.append(long_df.loc[mask, "pdr_pct"].dropna().values)
            positions = x_positions + offset
            ax.boxplot(
                phase_vals,
                positions=positions,
                widths=box_width * 0.85,
                patch_artist=True,
                notch=False,
                medianprops=dict(color="black", linewidth=1.5),
                whiskerprops=dict(linewidth=1.2),
                capprops=dict(linewidth=1.2),
                flierprops=dict(marker=".", markersize=4, alpha=0.5),
                boxprops=dict(facecolor=PROTO_COLOR[proto], alpha=0.75),
            )
            ax.plot([], [], color=PROTO_COLOR[proto], linewidth=6,
                    alpha=0.75, label=proto)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([PHASE_LABELS[p] for p in PHASE_ORDER])
        ax.legend(title="Protocol", loc="lower left", fontsize=9)

    ax.set_xticklabels([PHASE_LABELS[p] for p in PHASE_ORDER])
    ax.set_ylabel("PDR (%)")
    ax.set_xlabel("Simulation phase")
    ax.set_title("Packet Delivery Ratio by Protocol and Phase")
    ax.set_ylim(60, 101)
    ax.grid(axis="y", alpha=0.4)

    _savefig(fig, "fig1_pdr_phases.pdf")


# ---------------------------------------------------------------------------
# Figure 2 — PDR time-series  (sliding-window median)
# ---------------------------------------------------------------------------

def fig2_pdr_timeseries():
    print("\nFigure 2: Route exposure time-series")
    df = _load("route_trace.csv")
    if df is None:
        return

    if "tick" not in df.columns or "parent_is_sink" not in df.columns or "parent_is_attacker" not in df.columns:
        print("  [SKIP] route_trace.csv missing exposure columns")
        return

    df = df[df["protocol"].isin(PROTOCOLS)].copy()
    df["time_s"] = df["tick"] / 1000.0
    df["time_bin"] = (df["time_s"] // 30) * 30 + 15
    df["exposed"] = ((df["parent_is_sink"] > 0) | (df["parent_is_attacker"] > 0)).astype(float)

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    for proto in PROTOCOLS:
        sub = df[df["protocol"] == proto]
        if sub.empty:
            continue
        grp = sub.groupby("time_bin")["exposed"]
        xs = grp.mean().index.values
        ys = grp.mean().values * 100.0
        errs = grp.apply(lambda v: _ci95(v.values) * 100.0).values
        if len(xs) == 0:
            continue

        ax.plot(xs, ys,
                color=PROTO_COLOR[proto],
                marker=PROTO_MARKER[proto],
                linewidth=1.8,
                markersize=6,
                label=proto,
                zorder=3)
        ax.fill_between(xs,
                        np.clip(ys - errs, 0, 100),
                        np.clip(ys + errs, 0, 100),
                        color=PROTO_COLOR[proto],
                        alpha=0.15,
                        zorder=2)

    ax.axvline(ATTACK_START_S, color="gray", linestyle="--",
               linewidth=1.2, zorder=1, label="Attack start")
    ax.axvline(ATTACK_END_S,   color="gray", linestyle=":",
               linewidth=1.2, zorder=1, label="Attack end")
    ax.axvspan(ATTACK_START_S, ATTACK_END_S,
               color="red", alpha=0.05, zorder=0)
    ax.text(ATTACK_START_S + 5, 3, "Attack\nphase",
            fontsize=8, color="darkred", va="bottom")

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Nodes with attacker/sink parent (%)")
    ax.set_title("Attacker-Parent Exposure Over Time")
    ax.set_xlim(0, 930)
    ax.set_ylim(0, 40)
    ax.legend(title="Protocol", loc="lower right", fontsize=9,
              ncol=2)
    ax.grid(alpha=0.4)

    _savefig(fig, "fig2_pdr_timeseries.pdf")


# ---------------------------------------------------------------------------
# Figure 3 — Delay CDF during attack phase
# ---------------------------------------------------------------------------

def fig3_delay_cdf():
    print("\nFigure 3: Delay CDF (during attack)")
    # We need per-packet delay data; the delay_summary.csv only has aggregates.
    # Re-read the raw sim.log files to get individual delay samples for the
    # during_attack phase.  Fall back to delay_summary.csv if logs absent.

    ATTACK_START_MS = 350_000
    ATTACK_END_MS   = 650_000

    delay_by_proto: dict[str, list[float]] = {p: [] for p in PROTOCOLS}
    found_raw = False

    for proto in PROTOCOLS:
        proto_dir = RESULTS_DIR / proto
        if not proto_dir.is_dir():
            continue
        for seed_dir in sorted(proto_dir.iterdir()):
            if not seed_dir.is_dir():
                continue
            log = seed_dir / "sim.log"
            if not log.exists():
                continue
            found_raw = True
            try:
                text = log.read_text(errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "CSV,RX," not in line:
                    continue
                colon = line.find(":")
                if colon < 1:
                    continue
                rest = line[colon + 1:]
                parts = rest.split(",")
                if len(parts) < 7:
                    continue
                try:
                    # Format: rest = "CSV,RX,node=1,src_ip,seq,t_recv,t0,datalen"
                    # parts: [0]CSV [1]RX [2]node=1 [3]src_ip [4]seq [5]t_recv [6]t0
                    if parts[2].startswith("node="):
                        t_recv = int(parts[5])
                        t0     = int(parts[6])
                    else:
                        # Fallback: no node= tag
                        t_recv = int(parts[4])
                        t0     = int(parts[5])
                    if ATTACK_START_MS <= t0 < ATTACK_END_MS:
                        delay_ms = t_recv - t0
                        if delay_ms > 0:
                            delay_by_proto[proto].append(delay_ms / 1000.0)
                except (ValueError, IndexError):
                    continue

    if not found_raw:
        # Fallback: use delay_summary.csv mean as point estimate
        print("  [FALLBACK] Raw logs not available; using delay_summary.csv")
        df = _load("delay_summary.csv")
        if df is None:
            return
        for proto in PROTOCOLS:
            sub = df[df["protocol"] == proto]["delay_during_attack"].dropna()
            delay_by_proto[proto] = list(sub.values)

    # Plot CDFs
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    plotted = False
    for proto in PROTOCOLS:
        vals = np.array(delay_by_proto[proto])
        if vals.size == 0:
            continue
        vals_sorted = np.sort(vals)
        cdf = np.arange(1, len(vals_sorted) + 1) / len(vals_sorted)
        ax.plot(vals_sorted, cdf,
                color=PROTO_COLOR[proto],
                linewidth=1.8,
                label=f"{proto} (n={len(vals_sorted)})")
        plotted = True

    if not plotted:
        print("  [SKIP] No delay data available for CDF")
        plt.close(fig)
        return

    ax.set_xlabel("End-to-end delay (s)")
    ax.set_ylabel("CDF")
    ax.set_title("CDF of E2E Delay — Attack Phase (350–650 s)")
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1.05)
    ax.legend(title="Protocol", fontsize=9)
    ax.grid(alpha=0.4)

    _savefig(fig, "fig3_delay_cdf.pdf")


# ---------------------------------------------------------------------------
# Figure 4 — Trust component trace (TABRPL, attacker neighbours)
# ---------------------------------------------------------------------------

def fig4_trust_trace():
    print("\nFigure 4: Trust trace (TABRPL adversarial neighbours)")
    df = _load("trust_trace.csv")
    if df is None:
        return

    ADV_IDS = [2, 3, 4, 18]
    ADV_LABELS = {2: "Blackhole 2", 3: "Blackhole 3", 4: "Blackhole 4", 18: "Sinkhole 18"}
    COMPONENTS = ["t_fwd", "t_ctrl", "t_hon", "t_ewma"]
    COMP_COLORS = {
        "t_fwd": "#1f77b4",
        "t_ctrl": "#ff7f0e",
        "t_hon": "#2ca02c",
        "t_ewma": "#d62728",
    }
    COMP_LABELS = {
        "t_fwd": "T_fwd",
        "t_ctrl": "T_ctrl",
        "t_hon": "T_hon",
        "t_ewma": "T_EWMA",
    }

    df_att = df[(df["protocol"] == "TABRPL") & (df["nbr_id"].isin(ADV_IDS))].copy()
    if df_att.empty:
        print("  [SKIP] No trust records for attacker neighbours")
        return

    df_att = df_att[df_att["tick"] >= 0].copy()
    df_att["time_s"] = df_att["tick"] / 1000.0
    BIN_S = 30
    df_att["time_bin"] = (df_att["time_s"] // BIN_S) * BIN_S + BIN_S / 2

    fig, axes = plt.subplots(
        2, 2,
        figsize=(FIG_W * 1.8, FIG_H * 1.7),
        sharey=True
    )
    axes = np.array(axes).reshape(-1)

    for ax, att_id in zip(axes, ADV_IDS):
        sub = df_att[df_att["nbr_id"] == att_id]
        if sub.empty:
            ax.set_title(f"{ADV_LABELS[att_id]} (no data)")
            continue

        grp = sub.groupby("time_bin")

        for comp in COMPONENTS:
            if comp not in sub.columns:
                continue
            med   = grp[comp].median()
            q25   = grp[comp].quantile(0.25)
            q75   = grp[comp].quantile(0.75)
            times = med.index.values

            ax.plot(times, med.values,
                    color=COMP_COLORS[comp],
                    linewidth=1.6,
                    label=COMP_LABELS[comp])
            ax.fill_between(times, q25.values, q75.values,
                            color=COMP_COLORS[comp], alpha=0.15)

        ax.axvline(ATTACK_START_S, color="gray", linestyle="--",
                   linewidth=1.0, zorder=1)
        ax.axvline(ATTACK_END_S,   color="gray", linestyle=":",
                   linewidth=1.0, zorder=1)
        ax.axvspan(ATTACK_START_S, ATTACK_END_S,
                   color="red", alpha=0.05, zorder=0)

        ax.set_xlabel("Simulation time (s)")
        ax.set_title(ADV_LABELS[att_id])
        ax.set_ylim(0, 1050)
        ax.grid(alpha=0.4)

    axes[0].set_ylabel("Trust value (0–1000)")
    axes[2].set_ylabel("Trust value (0–1000)")

    handles = [mpatches.Patch(color=COMP_COLORS[c],
                               label=COMP_LABELS[c])
               for c in COMPONENTS if c in df_att.columns]
    fig.legend(handles=handles, title="Component",
               loc="upper center", fontsize=9, ncol=4,
               bbox_to_anchor=(0.5, 0.99))
    fig.suptitle("TABRPL Trust Components for Adversarial Neighbours\n"
                 "Median across seeds and observing nodes; shading = IQR",
                 fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])

    _savefig(fig, "fig4_trust_trace.pdf")


# ---------------------------------------------------------------------------
# Figure 5 — Parent churn bar chart
# ---------------------------------------------------------------------------

def fig5_parent_churn():
    print("\nFigure 5: Parent churn")
    df = _load("parent_churn.csv")
    if df is None:
        return

    churn_cols = {
        "pre_attack":    "churn_pre_attack",
        "during_attack": "churn_during_attack",
        "recovery":      "churn_recovery",
    }

    rows = []
    for phase, col in churn_cols.items():
        if col not in df.columns:
            continue
        sub = df[["protocol", "seed", "node_id", col]].copy()
        sub = sub.rename(columns={col: "churn"})
        sub["phase"] = phase
        rows.append(sub)

    if not rows:
        print("  [SKIP] No churn data")
        return

    churn_df = pd.concat(rows, ignore_index=True)
    churn_df = churn_df[churn_df["protocol"].isin(PROTOCOLS)].copy()
    churn_df["phase"] = pd.Categorical(churn_df["phase"], categories=PHASE_ORDER, ordered=True)

    phase_palette = {
        "pre_attack": "#94a3b8",
        "during_attack": "#f97316",
        "recovery": "#22c55e",
    }

    frac_rows = []
    for proto in PROTOCOLS:
        sub = churn_df[churn_df["protocol"] == proto]
        for phase in PHASE_ORDER:
            vals = sub.loc[sub["phase"] == phase, "churn"].dropna().values
            if vals.size == 0:
                continue
            frac_rows.append({
                "protocol": proto,
                "phase": phase,
                "nonzero_frac": float(np.mean(vals > 0)),
            })
    frac_df = pd.DataFrame(frac_rows)

    fig, axes = plt.subplots(
        1, 2, figsize=(FIG_W * 2.2, FIG_H), gridspec_kw={"width_ratios": [2.0, 1.0]}
    )
    ax0, ax1 = axes

    if _SEABORN:
        sns.boxplot(
            data=churn_df,
            x="protocol",
            y="churn",
            hue="phase",
            order=PROTOCOLS,
            hue_order=PHASE_ORDER,
            palette=phase_palette,
            showfliers=False,
            width=0.7,
            ax=ax0,
        )
        sns.stripplot(
            data=churn_df.sample(min(len(churn_df), 2500), random_state=7),
            x="protocol",
            y="churn",
            hue="phase",
            order=PROTOCOLS,
            hue_order=PHASE_ORDER,
            dodge=True,
            palette=phase_palette,
            alpha=0.18,
            size=2,
            ax=ax0,
        )
        handles, labels = ax0.get_legend_handles_labels()
        ax0.legend(handles[:len(PHASE_ORDER)], [PHASE_LABELS[p] for p in PHASE_ORDER],
                   title="Phase", fontsize=9)
    else:
        for j, phase in enumerate(PHASE_ORDER):
            phase_sub = churn_df[churn_df["phase"] == phase]
            series = [phase_sub.loc[phase_sub["protocol"] == proto, "churn"].values
                      for proto in PROTOCOLS]
            pos = np.arange(len(PROTOCOLS)) + (j - 1) * 0.22
            bp = ax0.boxplot(
                series,
                positions=pos,
                widths=0.18,
                patch_artist=True,
                showfliers=False,
                boxprops=dict(facecolor=phase_palette[phase], alpha=0.7),
                medianprops=dict(color="black", linewidth=1.2),
            )
        ax0.set_xticks(np.arange(len(PROTOCOLS)))
        ax0.set_xticklabels(PROTOCOLS)

    ax0.set_xlabel("Protocol")
    ax0.set_ylabel("Parent changes per node")
    ax0.set_title("Parent Churn Distribution by Protocol and Phase")
    ax0.grid(axis="y", alpha=0.35)
    ax0.set_ylim(bottom=0)

    if not frac_df.empty:
        heat = (
            frac_df.pivot(index="phase", columns="protocol", values="nonzero_frac")
            .reindex(index=PHASE_ORDER, columns=PROTOCOLS)
        )
        heat_vals = heat.values.astype(float)
        finite_vals = heat_vals[np.isfinite(heat_vals)]
        if finite_vals.size > 0:
            vmin = max(0.0, float(finite_vals.min()) - 0.05)
            vmax = min(1.0, float(finite_vals.max()) + 0.05)
            if vmax <= vmin:
                vmax = min(1.0, vmin + 0.1)
        else:
            vmin, vmax = 0.0, 1.0

        im = ax1.imshow(heat_vals, cmap="YlOrRd", aspect="auto", vmin=vmin, vmax=vmax)
        ax1.set_xticks(np.arange(len(PROTOCOLS)))
        ax1.set_xticklabels(PROTOCOLS, rotation=30, ha="right")
        ax1.set_yticks(np.arange(len(PHASE_ORDER)))
        ax1.set_yticklabels([PHASE_LABELS[p] for p in PHASE_ORDER])
        ax1.set_title("Fraction of Nodes with Non-zero Churn")

        ax1.set_xticks(np.arange(-0.5, len(PROTOCOLS), 1), minor=True)
        ax1.set_yticks(np.arange(-0.5, len(PHASE_ORDER), 1), minor=True)
        ax1.grid(which="minor", color="white", linestyle="-", linewidth=1.2)
        ax1.tick_params(which="minor", bottom=False, left=False)

        for i in range(len(PHASE_ORDER)):
            for j in range(len(PROTOCOLS)):
                val = heat_vals[i, j]
                if np.isnan(val):
                    continue
                txt_color = "white" if val >= (vmin + vmax) / 2.0 else "black"
                ax1.text(j, i, f"{val:.2f}", ha="center", va="center",
                         color=txt_color, fontsize=9, fontweight="bold")
        fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)

    fig.suptitle("Parent Churn Overview", fontsize=11)
    fig.tight_layout()
    _savefig(fig, "fig5_parent_churn.pdf")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 62)
    print("TA-BRPL figure generator")
    print(f"Reading from : {RESULTS_DIR}")
    print(f"Writing to   : {FIGURES_DIR}")
    print("=" * 62)

    fig1_pdr_phases()
    fig2_pdr_timeseries()
    fig3_delay_cdf()
    fig4_trust_trace()
    fig5_parent_churn()

    print("\nAll figures complete.")


if __name__ == "__main__":
    main()
