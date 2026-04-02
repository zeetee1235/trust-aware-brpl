"""
한국콘텐츠학회 투고용 figure 생성 (단/2단 컬럼 width 기준)
- fig_jkcs_delta_ci.pdf    : Δ + 95%CI 수평 그래프 (단컬럼)
- fig_jkcs_box_density.pdf : 밀도별 att_share boxplot (2컬럼 span)
- fig_jkcs_pdr_noninf.pdf  : PDR 비열세 pass/fail (단컬럼)
- fig_jkcs_density_bar.pdf : 밀도별 Δatt + ΔPDR 막대 (2컬럼 span)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

# ── 한글 폰트 ────────────────────────────────────────────────
_ko_candidates = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    "/usr/share/fonts/truetype/unfonts-core/UnBatang.ttf",
    "/usr/share/fonts/truetype/baekmuk/batang.ttf",
]
for _f in _ko_candidates:
    if Path(_f).exists():
        fm.fontManager.addfont(_f)
        _prop = fm.FontProperties(fname=_f)
        matplotlib.rcParams["font.family"] = _prop.get_name()
        break
matplotlib.rcParams["axes.unicode_minus"] = False

BASE = Path(__file__).parent
DATA = BASE.parent / "generated/main_v2_final"
OUT  = BASE / "figures"
OUT.mkdir(parents=True, exist_ok=True)

metrics = pd.read_csv(DATA / "metrics_by_topology.csv")
deltas  = pd.read_csv(DATA / "paired_deltas_by_topology.csv")
summary = pd.read_csv(DATA / "summary_by_density.csv")

COLORS = {"dense": "#1f77b4", "medium": "#ff7f0e", "sparse": "#2ca02c"}
LABELS = {"dense": "고밀도", "medium": "중밀도", "sparse": "저밀도"}

# ══════════════════════════════════════════════════════════
# Figure 1: Δ 및 95% CI 수평 점-구간 도표 (단컬럼 3.5인치)
# ══════════════════════════════════════════════════════════
ov = summary[summary.scope == "overall"].iloc[0]

metrics_info = [
    ("att\_share (↓)",  ov.delta_att_share_mean,  ov.delta_att_share_ci_lo,  ov.delta_att_share_ci_hi,  "#d62728"),
    ("hit\_ratio (↓)",  ov.delta_hit_ratio_mean,   ov.delta_hit_ratio_ci_lo,   ov.delta_hit_ratio_ci_hi,   "#d62728"),
    ("PDR\_dur (↑)",    ov.delta_pdr_dur_mean,     ov.delta_pdr_dur_ci_lo,     ov.delta_pdr_dur_ci_hi,     "#2ca02c"),
    ("churn (상한)",    ov.delta_churn_mean,       ov.delta_churn_ci_lo,       ov.delta_churn_ci_hi,       "#7f7f7f"),
]

fig, ax = plt.subplots(figsize=(3.6, 2.8))

for i, (label, mean, lo, hi, color) in enumerate(metrics_info):
    ax.errorbar(mean, i,
                xerr=[[mean - lo], [hi - mean]],
                fmt="o", color=color, capsize=4, capthick=1.5,
                elinewidth=1.5, markersize=6, zorder=3)
    ax.text(hi + 0.0008, i, f"{mean:+.4f}", va="center", ha="left",
            fontsize=7.5, color=color)

ax.axvline(0, color="black", lw=0.8, linestyle="--")
ax.set_yticks(range(len(metrics_info)))
ax.set_yticklabels([m[0] for m in metrics_info], fontsize=8.5)
ax.set_xlabel("Δ (TA-BRPL − BRPL)", fontsize=9)
ax.set_title("주요 지표 쌍체 평균 Δ 및 95% CI\n(75개 토폴로지 쌍)", fontsize=9)
ax.grid(True, axis="x", alpha=0.3)
ax.invert_yaxis()

# H3 churn 상한 마킹
ax.axvline(0.1, color="gray", lw=0.8, linestyle=":", alpha=0.7)
ax.text(0.1, len(metrics_info) - 0.8, "상한\n0.1", ha="center",
        fontsize=6.5, color="gray")

plt.tight_layout(pad=0.6)
plt.savefig(OUT / "fig_jkcs_delta_ci.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_jkcs_delta_ci.pdf")


# ══════════════════════════════════════════════════════════
# Figure 2: 밀도별 att_share boxplot BRPL vs TA-BRPL (2컬럼 5.5인치)
# ══════════════════════════════════════════════════════════
brpl_data = metrics[metrics.protocol == "BRPL"].copy()
ta_data   = metrics[metrics.protocol == "TABRPL"].copy()
densities = ["sparse", "medium", "dense"]
den_labels = ["저밀도", "중밀도", "고밀도"]

fig, axes = plt.subplots(1, 3, figsize=(5.5, 3.0), sharey=True)

for ax, dens, dlbl in zip(axes, densities, den_labels):
    b_vals = brpl_data[brpl_data.density == dens]["att_share"].values
    t_vals = ta_data[ta_data.density == dens]["att_share"].values

    bp = ax.boxplot(
        [b_vals, t_vals],
        labels=["BRPL", "TA-BRPL"],
        patch_artist=True,
        medianprops=dict(color="black", linewidth=1.5),
        whiskerprops=dict(linewidth=1.0),
        capprops=dict(linewidth=1.0),
        flierprops=dict(marker=".", markersize=3, alpha=0.5),
        widths=0.5,
    )
    bp["boxes"][0].set_facecolor("#f4a7a7")
    bp["boxes"][1].set_facecolor("#a7c8f4")

    delta = np.median(t_vals) - np.median(b_vals)
    ax.set_title(f"{dlbl}\nΔmed={delta:+.3f}", fontsize=8.5)
    ax.set_xlabel("프로토콜", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

axes[0].set_ylabel("공격자 경유율 (att\_share)", fontsize=8)

plt.suptitle("BRPL vs TA-BRPL: 밀도별 공격자 경유율 분포", fontsize=9, y=1.02)
plt.tight_layout(pad=0.5)
plt.savefig(OUT / "fig_jkcs_box_density.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_jkcs_box_density.pdf")


# ══════════════════════════════════════════════════════════
# Figure 3: PDR 비열세 pass/fail (단컬럼 3.5인치)
# ══════════════════════════════════════════════════════════
MARGIN = -0.02
pdr_delta = deltas.copy()
pdr_delta["pass"] = pdr_delta["delta_pdr_dur"] >= MARGIN

fig, ax = plt.subplots(figsize=(3.5, 2.8))

for dens, color in COLORS.items():
    d = pdr_delta[pdr_delta.density == dens]
    ax.scatter(
        d["delta_pdr_dur"], [dens] * len(d),
        c=[color if p else "red" for p in d["pass"]],
        s=25, alpha=0.75, zorder=3,
        marker="o"
    )

ax.axvline(MARGIN, color="black", lw=1.0, linestyle="--", label=f"비열세 마진 {MARGIN}")
ax.axvline(0, color="gray", lw=0.6, linestyle=":")

pass_pct = pdr_delta["pass"].mean() * 100
ax.set_title(f"토폴로지별 PDR 비열세 검증\n통과율: {pass_pct:.1f}%", fontsize=9)
ax.set_xlabel("ΔPDR\_dur (TA-BRPL − BRPL)", fontsize=8.5)
ax.set_yticks(list(COLORS.keys()))
ax.set_yticklabels([LABELS[d] for d in COLORS.keys()], fontsize=8.5)
ax.legend(fontsize=7.5, loc="lower right")
ax.grid(True, axis="x", alpha=0.3)

# pass/fail 범례 추가
from matplotlib.lines import Line2D
legend_els = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ca02c", markersize=6, label="통과"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="red",     markersize=6, label="실패"),
]
ax.legend(handles=legend_els + [
    Line2D([0], [0], color="black", lw=1, linestyle="--", label=f"마진 {MARGIN}")
], fontsize=7.5, loc="lower right")

plt.tight_layout(pad=0.6)
plt.savefig(OUT / "fig_jkcs_pdr_noninf.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_jkcs_pdr_noninf.pdf")


# ══════════════════════════════════════════════════════════
# Figure 4: 밀도별 Δatt + ΔPDR 막대 (2컬럼 5.5인치)
# ══════════════════════════════════════════════════════════
scope_order  = ["sparse", "medium", "dense", "overall"]
scope_labels = ["저밀도", "중밀도", "고밀도", "전체"]
x = np.arange(len(scope_order))
w = 0.55

fig, axes = plt.subplots(1, 2, figsize=(5.5, 3.2))

for ax, (mcol, lo_col, hi_col), ylabel, title in zip(
    axes,
    [
        ("delta_att_share_mean", "delta_att_share_ci_lo", "delta_att_share_ci_hi"),
        ("delta_pdr_dur_mean",   "delta_pdr_dur_ci_lo",   "delta_pdr_dur_ci_hi"),
    ],
    ["Δatt\_share", "ΔPDR\_dur"],
    ["공격자 경유율 감소", "PDR 개선"],
):
    means  = [summary[summary.scope == s][mcol].values[0]   for s in scope_order]
    ci_lo  = [summary[summary.scope == s][lo_col].values[0] for s in scope_order]
    ci_hi  = [summary[summary.scope == s][hi_col].values[0] for s in scope_order]
    yerr_lo = [m - l for m, l in zip(means, ci_lo)]
    yerr_hi = [h - m for m, h in zip(means, ci_hi)]

    bar_colors = [COLORS.get(s, "#555555") for s in scope_order]
    bar_colors[-1] = "#555555"

    ax.bar(x, means, width=w, color=bar_colors, alpha=0.8,
           yerr=[yerr_lo, yerr_hi], capsize=3,
           error_kw={"elinewidth": 1.2, "ecolor": "black"})
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(scope_labels, fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.set_title(title, fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)

    for i, m in enumerate(means):
        ax.text(i, m + (0.0005 if m >= 0 else -0.0005),
                f"{m:+.3f}", ha="center",
                va="bottom" if m >= 0 else "top", fontsize=7)

plt.suptitle("밀도별 평균 개선량 및 95% 신뢰구간 (75개 토폴로지 쌍)", fontsize=9)
plt.tight_layout(pad=0.5)
plt.savefig(OUT / "fig_jkcs_density_bar.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_jkcs_density_bar.pdf")

print("\n모든 JKCS figure 생성 완료 →", OUT)
