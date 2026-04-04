"""
Generate a local weight-sensitivity heatmap from the 9-pair miniset.

This is intentionally a post-hoc local robustness check, not a held-out
optimality claim.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent.parent
FIG_DIR = BASE / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

SWEEP_DIR = ROOT / "results" / "weight_sensitivity_miniset"
BRPL_DIR = ROOT / "results" / "random_topo_ablation_minset_v1"
OUT_DIR = BASE.parent / "generated" / "weight_sensitivity_miniset"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def set_korean_font() -> None:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
        "/usr/share/fonts/truetype/unfonts-core/UnBatang.ttf",
    ]
    for font_path in candidates:
        p = Path(font_path)
        if p.exists():
            fm.fontManager.addfont(p)
            prop = fm.FontProperties(fname=p)
            matplotlib.rcParams["font.family"] = prop.get_name()
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def parse_one_log(path: Path) -> float:
    total = 0
    att = 0
    for raw in path.open(errors="replace"):
        i = raw.find("CSV,")
        if i < 0:
            continue
        parts = raw[i:].strip().split(",")
        if len(parts) < 11 or parts[1] != "ROUTE":
            continue
        try:
            tick = int(parts[3])
            is_att = int(parts[9])
        except ValueError:
            continue
        if 350_000 <= tick < 650_000:
            total += 1
            if is_att == 1:
                att += 1
    return (att / total) if total > 0 else float("nan")


def load_brpl_baseline() -> dict[tuple[str, str], float]:
    base = {}
    for simlog in BRPL_DIR.glob("*/*/BRPL/1/sim.log"):
        density = simlog.parents[3].name
        topo = simlog.parents[2].name
        base[(density, topo)] = parse_one_log(simlog)
    return base


def build_rows() -> pd.DataFrame:
    brpl = load_brpl_baseline()
    rows = []
    for variant_dir in sorted(SWEEP_DIR.glob("w*/")):
        tag = variant_dir.name
        wf, wc, wh = int(tag[1]), int(tag[2]), int(tag[3])
        deltas = []
        for simlog in variant_dir.glob("*/*/TABRPL/1/sim.log"):
            density = simlog.parents[3].name
            topo = simlog.parents[2].name
            att = parse_one_log(simlog)
            base = brpl[(density, topo)]
            deltas.append(att - base)
        if not deltas:
            continue
        rows.append(
            {
                "tag": tag,
                "wf": wf / 10.0,
                "wc": wc / 10.0,
                "wh": wh / 10.0,
                "delta_att_share_mean": float(np.mean(deltas)),
                "n_pairs": len(deltas),
            }
        )
    out = pd.DataFrame(rows).sort_values(["wf", "wc", "wh"])
    out.to_csv(OUT_DIR / "weight_sensitivity_summary.csv", index=False)
    return out


def plot_heatmap(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.3, 4.9))

    x = df["wf"].to_numpy()
    y = df["wc"].to_numpy()
    z = df["delta_att_share_mean"].to_numpy()

    tri = mtri.Triangulation(x, y)
    contour = ax.tricontourf(tri, z, levels=12, cmap="RdYlBu_r")
    ax.tricontour(tri, z, levels=8, colors="white", linewidths=0.4, alpha=0.6)

    ax.scatter(x, y, c=z, cmap="RdYlBu_r", edgecolors="black", s=52, linewidths=0.6)
    ax.scatter([0.5], [0.3], facecolors="none", edgecolors="white", s=300, linewidths=2.2, zorder=4)
    ax.scatter([0.5], [0.3], facecolors="none", edgecolors="#111827", s=110, linewidths=1.2, zorder=5)
    ax.scatter([0.5], [0.3], marker="*", s=240, color="#111827", zorder=6,
               label="현재값 (10개 조합 중 1개)")

    for row in df.itertuples(index=False):
        if abs(row.wf - 0.5) < 1e-9 and abs(row.wc - 0.3) < 1e-9:
            continue
        dx = -0.014 if row.wf >= 0.68 else 0.008
        dy = -0.012 if row.wc >= 0.38 else 0.007
        ha = "right" if dx < 0 else "left"
        ax.text(
            row.wf + dx,
            row.wc + dy,
            f"{row.wh:.1f}",
            fontsize=8.5,
            ha=ha,
            va="center",
            color="#111827",
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.72),
        )

    ax.set_xlabel(r"$w_f$", labelpad=4, fontsize=11)
    ax.set_ylabel(r"$w_c$", labelpad=4, fontsize=11)
    ax.set_title("가중치 sensitivity heatmap", pad=10, fontsize=13)
    ax.tick_params(axis="both", labelsize=10)
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper right", fontsize=9.5, framealpha=0.95)

    cbar = fig.colorbar(contour, ax=ax, shrink=0.92)
    cbar.set_label("Δatt_share vs BRPL", fontsize=10.5)
    cbar.ax.tick_params(labelsize=9.5)

    fig.text(
        0.11,
        0.04,
        r"각 점 옆 숫자: $w_h = 1 - w_f - w_c$",
        ha="left",
        va="center",
        fontsize=9.5,
        color="#374151",
    )

    fig.subplots_adjust(top=0.86, left=0.11, right=0.92, bottom=0.14)
    plt.savefig(FIG_DIR / "fig_jkcs_weight_sensitivity_heatmap.pdf")
    plt.close()


def main() -> None:
    set_korean_font()
    df = build_rows()
    if df.empty:
        raise SystemExit("No sweep results found under results/weight_sensitivity_miniset")
    plot_heatmap(df)
    print("Wrote:", OUT_DIR / "weight_sensitivity_summary.csv")
    print("Wrote:", FIG_DIR / "fig_jkcs_weight_sensitivity_heatmap.pdf")


if __name__ == "__main__":
    main()
