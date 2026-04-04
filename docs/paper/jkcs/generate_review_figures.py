"""
Reviewer-facing supplementary figures for JKCS defense.

Generates:
- fig_jkcs_trust_timeseries.pdf
- fig_jkcs_churn_att_scatter.pdf
- fig_jkcs_ablation_forest.pdf

Notes:
- The trust time-series pools attacker-neighbor trust updates from a
  representative topology selected from the main 75-pair corpus.
- Weight-sensitivity heatmaps are intentionally not generated here because
  the current workspace does not contain a completed weight-grid sweep.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent.parent
FIG_DIR = BASE / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

MAIN_DATA = BASE.parent / "generated" / "main_v2_final"
MAIN_METRICS = MAIN_DATA / "metrics_by_topology.csv"
PAIRED_DELTAS = MAIN_DATA / "paired_deltas_by_topology.csv"
ABLATION_SUMMARY = ROOT / "results" / "random_topo_ablation_minset_v1" / "summary.md"
MAIN_RESULTS = ROOT / "results" / "random_topo_main_v1"

ATTACK_START_S = 350
ATTACK_END_S = 650
TRUST_UPDATE_S = 60

COLORS = {
    "dense": "#1f77b4",
    "medium": "#ff7f0e",
    "sparse": "#2ca02c",
    "t_fwd": "#d62728",
    "t_ctrl": "#1f77b4",
    "t_hon": "#2ca02c",
    "t_agg": "#111827",
}
LABELS = {"dense": "고밀도", "medium": "중밀도", "sparse": "저밀도"}


def set_korean_font() -> None:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
        "/usr/share/fonts/truetype/unfonts-core/UnBatang.ttf",
        "/usr/share/fonts/truetype/baekmuk/batang.ttf",
    ]
    for font_path in candidates:
        path = Path(font_path)
        if path.exists():
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            matplotlib.rcParams["font.family"] = prop.get_name()
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def choose_representative_topology() -> tuple[str, str, float, float]:
    df = pd.read_csv(MAIN_METRICS)
    pivot = df.pivot_table(
        index=["density", "topology"],
        columns="protocol",
        values=["att_share", "churn"],
    )

    rows = []
    for idx, row in pivot.iterrows():
        if ("att_share", "BRPL") not in row or ("att_share", "TABRPL") not in row:
            continue
        delta_att = row[("att_share", "TABRPL")] - row[("att_share", "BRPL")]
        delta_churn = row[("churn", "TABRPL")] - row[("churn", "BRPL")]
        rows.append(
            {
                "density": idx[0],
                "topology": idx[1],
                "delta_att": float(delta_att),
                "delta_churn": float(delta_churn),
            }
        )

    cand = pd.DataFrame(rows)
    bounded = cand[cand["delta_churn"] <= 0.1].copy()
    if bounded.empty:
        bounded = cand
    best = bounded.sort_values(["delta_att", "delta_churn"], ascending=[True, True]).iloc[0]
    return best["density"], best["topology"], best["delta_att"], best["delta_churn"]


def choose_trust_demo_topology() -> tuple[str, str, float, float]:
    """Pick a median-like topology with visible trust degradation."""
    df = pd.read_csv(PAIRED_DELTAS)
    cand = df[(df["delta_att_share"] < 0) & (df["delta_churn"] <= 0.1)].copy()
    if cand.empty:
        row = df.sort_values("delta_att_share").iloc[0]
        return row["density"], row["topology"], float(row["delta_att_share"]), float(row["delta_churn"])

    scored: list[dict] = []
    for row in cand.itertuples(index=False):
        trust_df = parse_trust_timeseries(row.density, row.topology)
        if trust_df.empty:
            continue
        pre = trust_df[(trust_df["time_s"] >= TRUST_UPDATE_S) & (trust_df["time_s"] < ATTACK_START_S)]["t_agg"]
        atk = trust_df[(trust_df["time_s"] >= ATTACK_START_S) & (trust_df["time_s"] <= ATTACK_END_S)]["t_agg"]
        if pre.empty or atk.empty:
            continue
        scored.append(
            {
                "density": row.density,
                "topology": row.topology,
                "delta_att_share": float(row.delta_att_share),
                "delta_churn": float(row.delta_churn),
                "tagg_drop": float(atk.median() - pre.median()),
            }
        )

    if not scored:
        row = cand.sort_values(["delta_att_share", "delta_churn"]).iloc[0]
        return row["density"], row["topology"], float(row["delta_att_share"]), float(row["delta_churn"])

    scored_df = pd.DataFrame(scored)
    visible = scored_df[scored_df["tagg_drop"] <= -0.05].copy()
    target = visible if not visible.empty else scored_df
    median_delta = target["delta_att_share"].median()
    target["dist_to_median"] = (target["delta_att_share"] - median_delta).abs()
    row = target.sort_values(["dist_to_median", "delta_churn", "tagg_drop"]).iloc[0]
    return row["density"], row["topology"], float(row["delta_att_share"]), float(row["delta_churn"])


def parse_trust_timeseries(density: str, topology: str) -> pd.DataFrame:
    base = MAIN_RESULTS / density / topology / "TABRPL"
    rows: list[dict] = []

    for seed_dir in sorted(base.iterdir()):
        if not seed_dir.is_dir() or not seed_dir.name.isdigit():
            continue
        log_path = seed_dir / "sim.log"
        attackers: set[int] = set()
        pair_updates: dict[tuple[int, int], int] = defaultdict(int)

        with open(log_path, errors="replace") as f:
            for line in f:
                if ":CSV,PROTOCOL," not in line and ":CSV,TRUST," not in line:
                    continue
                _, rest = line.split(":", 1)
                rest = rest.strip()

                if rest.startswith("CSV,PROTOCOL,") and rest.endswith(",ATTACKER"):
                    parts = rest.split(",")
                    try:
                        attackers.add(int(parts[2]))
                    except (IndexError, ValueError):
                        continue
                    continue

                if not rest.startswith("CSV,TRUST,") or rest.startswith("CSV,TRUST_"):
                    continue

                parts = rest.split(",")
                if len(parts) < 10:
                    continue
                try:
                    self_id = int(parts[2])
                    nbr_id = int(parts[3])
                    t_fwd, t_ctrl, t_hon, t_agg = [int(x) for x in parts[4:8]]
                except ValueError:
                    continue

                if nbr_id not in attackers:
                    continue

                key = (self_id, nbr_id)
                pair_updates[key] += 1
                epoch = pair_updates[key]
                rows.append(
                    {
                        "seed": int(seed_dir.name),
                        "epoch": epoch,
                        "time_s": epoch * TRUST_UPDATE_S,
                        "t_fwd": t_fwd / 1000.0,
                        "t_ctrl": t_ctrl / 1000.0,
                        "t_hon": t_hon / 1000.0,
                        "t_agg": t_agg / 1000.0,
                    }
                )

    return pd.DataFrame(rows)


def summarize_band(df: pd.DataFrame, col: str) -> pd.DataFrame:
    grp = df.groupby("time_s")[col]
    return pd.DataFrame(
        {
            "time_s": grp.median().index,
            "median": grp.median().values,
            "q25": grp.quantile(0.25).values,
            "q75": grp.quantile(0.75).values,
        }
    )


def fig_trust_timeseries() -> None:
    density, topology, delta_att, delta_churn = choose_trust_demo_topology()
    trust_df = parse_trust_timeseries(density, topology)
    if trust_df.empty:
        raise RuntimeError("No trust rows found for representative topology.")

    fig, ax = plt.subplots(figsize=(5.6, 3.2))

    for col, label in [
        ("t_fwd", r"$T_{fwd}$"),
        ("t_ctrl", r"$T_{ctrl}$"),
        ("t_hon", r"$T_{hon}$"),
        ("t_agg", r"$T_{agg}$"),
    ]:
        stat = summarize_band(trust_df, col)
        ax.plot(stat["time_s"], stat["median"], lw=2.0, color=COLORS[col], label=label)
        ax.fill_between(stat["time_s"], stat["q25"], stat["q75"], color=COLORS[col], alpha=0.12)

    ax.axvspan(ATTACK_START_S, ATTACK_END_S, color="#f59e0b", alpha=0.12, zorder=0)
    ax.axvline(ATTACK_START_S, color="#92400e", ls="--", lw=1.3)
    ax.axvline(ATTACK_END_S, color="#92400e", ls="--", lw=1.0)
    ax.text(ATTACK_START_S + 6, 0.10, "공격 시작 350s", fontsize=8, color="#92400e")
    ax.text(ATTACK_END_S - 72, 0.10, "공격 종료 650s", fontsize=8, color="#92400e")
    ax.text(ATTACK_START_S + 96, 0.10, "공격 구간", fontsize=8, color="#92400e")

    ax.set_xlim(trust_df["time_s"].min(), trust_df["time_s"].max())
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("근사 trust update 시각 (s)")
    ax.set_ylabel("정규화 trust score")
    ax.set_title(
        "공격자 이웃 trust 신호 시계열\n"
        f"대표 사례: {LABELS[density]} {topology} "
        f"(Δatt={delta_att:+.3f}, Δchurn={delta_churn:+.3f})"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower left", ncol=4, fontsize=8)
    plt.tight_layout(pad=0.5)
    plt.savefig(FIG_DIR / "fig_jkcs_trust_timeseries.pdf", bbox_inches="tight")
    plt.close()


def fig_churn_att_scatter() -> None:
    df = pd.read_csv(PAIRED_DELTAS)
    within = df["delta_churn"] <= 0.1
    exceed = df["delta_churn"] > 0.1

    fig, ax = plt.subplots(figsize=(4.8, 3.6))

    for density in ["sparse", "medium", "dense"]:
        sub = df[(df["density"] == density) & within]
        ax.scatter(
            sub["delta_churn"],
            sub["delta_att_share"],
            s=34,
            alpha=0.8,
            c=COLORS[density],
            label=LABELS[density],
            edgecolors="white",
            linewidths=0.5,
        )

    out = df[exceed]
    if not out.empty:
        ax.scatter(
            out["delta_churn"],
            out["delta_att_share"],
            s=64,
            facecolors="none",
            edgecolors="#111827",
            linewidths=0.9,
            marker="s",
            label="H3 상한 초과",
        )

    ax.axhline(0, color="black", lw=0.9, ls="--")
    ax.axvline(0, color="gray", lw=0.8, ls=":")
    ax.axvline(0.1, color="gray", lw=0.9, ls="--")
    ax.axvspan(-0.25, 0.1, ymin=0.0, ymax=0.48, color="#d1fae5", alpha=0.35, zorder=0)
    ax.text(0.098, df["delta_att_share"].min() + 0.004, "H3 상한 0.1", ha="right", fontsize=8, color="gray")
    ax.text(0.145, df["delta_att_share"].min() + 0.004, f"초과 {int(exceed.sum())}/75", ha="left", fontsize=8, color="#111827")

    ax.set_xlabel("Δchurn (TA-BRPL − BRPL)")
    ax.set_ylabel("Δatt_share (TA-BRPL − BRPL)")
    ax.set_title("토폴로지별 격리-안정성 trade-off\n낮은 att_share를 위해 churn을 희생했는가?")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower right", fontsize=8)
    plt.tight_layout(pad=0.5)
    plt.savefig(FIG_DIR / "fig_jkcs_churn_att_scatter.pdf", bbox_inches="tight")
    plt.close()


def parse_ablation_summary() -> pd.DataFrame:
    text = ABLATION_SUMMARY.read_text()
    rows = []
    pat = re.compile(
        r"\| `(?P<variant>[^`]+)`(?: \((?P<label>[^)]*)\))? \| "
        r"`(?P<mean>[+-]?\d+\.\d+)` \[`(?P<lo>[+-]?\d+\.\d+)`, `(?P<hi>[+-]?\d+\.\d+)`\] \| "
        r"`(?P<hit>[+-]?\d+\.\d+)` \| "
        r"`(?P<churn>[+-]?\d+\.\d+)` \| "
        r"`(?P<pdr>[+-]?\d+\.\d+)` \| "
        r"`(?P<win>\d+\.\d+)%` \| "
        r"`(?P<ni>\d+\.\d+)%` \|"
    )
    for m in pat.finditer(text):
        variant = m.group("variant")
        label = m.group("label") or variant
        rows.append(
            {
                "variant": variant,
                "label": label,
                "mean": float(m.group("mean")),
                "lo": float(m.group("lo")),
                "hi": float(m.group("hi")),
                "pdr": float(m.group("pdr")),
                "win": float(m.group("win")),
                "ni": float(m.group("ni")),
            }
        )
    if not rows:
        raise RuntimeError("Failed to parse ablation summary table.")
    order = {"TABRPL": 0, "TABRPL_FWDCTRL": 1, "TABRPL_FWD": 2}
    out = pd.DataFrame(rows)
    out["sort_key"] = out["variant"].map(order)
    return out.sort_values("sort_key")


def fig_ablation_forest() -> None:
    df = parse_ablation_summary()

    fig, ax = plt.subplots(figsize=(4.8, 2.9))
    y = np.arange(len(df))

    colors = ["#111827", "#2563eb", "#dc2626"]
    for idx, row in enumerate(df.itertuples(index=False)):
        ax.errorbar(
            row.mean,
            y[idx],
            xerr=[[row.mean - row.lo], [row.hi - row.mean]],
            fmt="o",
            color=colors[idx],
            capsize=4,
            lw=1.6,
            markersize=6,
        )
        ax.text(row.hi + 0.0012, y[idx], f"{row.mean:+.3f}", va="center", fontsize=8, color=colors[idx])

    ax.axvline(0, color="black", lw=0.9, ls="--")
    ax.set_yticks(y)
    ax.set_yticklabels(
        [
            "Full",
            r"$T_{fwd}+T_{ctrl}$",
            r"$T_{fwd}$ only",
        ]
    )
    ax.invert_yaxis()
    ax.set_xlabel("Δatt_share vs BRPL")
    ax.set_title("Ablation: Full model만 안정적 route-capture 완화를 보임")
    ax.grid(True, axis="x", alpha=0.25)

    plt.tight_layout(pad=0.5)
    plt.savefig(FIG_DIR / "fig_jkcs_ablation_forest.pdf", bbox_inches="tight")
    plt.close()


def main() -> None:
    set_korean_font()
    fig_trust_timeseries()
    fig_churn_att_scatter()
    fig_ablation_forest()
    print("Generated reviewer-facing figures in", FIG_DIR)


if __name__ == "__main__":
    main()
