"""
TA-BRPL 한국어 논문용 추가 figure 생성 스크립트
- fig_concept.pdf     : 2단계 공격 + TA-BRPL 방어 개념 타임라인
- fig_cdf.pdf         : BRPL vs TA-BRPL att_share CDF (밀도별)
- fig_scatter.pdf     : 토폴로지별 Δatt_share vs Δchurn 산점도 (밀도별 색상)
- fig_density_bar.pdf : 밀도별 Δatt_share / ΔPDR 막대 + CI
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from pathlib import Path
import matplotlib.font_manager as fm

# 한글 폰트 설정 (NanumGothic 또는 UnDotum 계열 사용)
_ko_candidates = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    "/usr/share/fonts/truetype/unfonts-core/UnBatang.ttf",
    "/usr/share/fonts/truetype/baekmuk/batang.ttf",
]
_ko_font = None
for _f in _ko_candidates:
    if Path(_f).exists():
        _ko_font = _f
        break
if _ko_font:
    fm.fontManager.addfont(_ko_font)
    _prop = fm.FontProperties(fname=_ko_font)
    matplotlib.rcParams["font.family"] = _prop.get_name()
matplotlib.rcParams["axes.unicode_minus"] = False

# ── 경로 설정 ─────────────────────────────────────────────
DATA = Path(__file__).parent / "generated/main_v2_final"
OUT  = Path(__file__).parent / "figures/new/ko"
OUT.mkdir(parents=True, exist_ok=True)

metrics   = pd.read_csv(DATA / "metrics_by_topology.csv")
deltas    = pd.read_csv(DATA / "paired_deltas_by_topology.csv")
summary   = pd.read_csv(DATA / "summary_by_density.csv")

# 색상/마커 통일
COLORS = {"dense": "#1f77b4", "medium": "#ff7f0e", "sparse": "#2ca02c"}
LABELS = {"dense": "고밀도", "medium": "중밀도", "sparse": "저밀도"}

# ══════════════════════════════════════════════════════════
# Figure 1: 공격 단계 타임라인 개념도
# ══════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 1, figsize=(8, 4.5), sharex=True)

t = np.array([0, 150, 350, 650, 900])

# 공격자 경유율 (개념적 값)
att_brpl  = np.array([0.02, 0.03, 0.14, 0.14, 0.04])
att_ta    = np.array([0.02, 0.03, 0.06, 0.06, 0.03])

# PDR (개념적 값)
pdr_brpl  = np.array([1.00, 0.99, 0.94, 0.94, 0.98])
pdr_ta    = np.array([1.00, 0.99, 0.96, 0.96, 0.99])

ax1, ax2 = axes

for ax in axes:
    ax.axvspan(0,   150, alpha=0.08, color="gray",   label="워밍업")
    ax.axvspan(150, 350, alpha=0.08, color="green",  label="공격 전")
    ax.axvspan(350, 650, alpha=0.12, color="red",    label="공격 활성")
    ax.axvspan(650, 900, alpha=0.08, color="blue",   label="복구")

ax1.plot(t, att_brpl, "o--", color="#e74c3c", lw=2, label="BRPL")
ax1.plot(t, att_ta,   "s-",  color="#2980b9", lw=2, label="TA-BRPL")
ax1.set_ylabel("공격자 경유율\n(att_share)", fontsize=10)
ax1.set_ylim(0, 0.20)
ax1.legend(loc="upper left", fontsize=8)
ax1.annotate("Phase 1\n경로 장악", xy=(500, 0.14), fontsize=8,
             color="red", ha="center",
             arrowprops=dict(arrowstyle="->", color="red"),
             xytext=(500, 0.17))

ax2.plot(t, pdr_brpl, "o--", color="#e74c3c", lw=2, label="BRPL")
ax2.plot(t, pdr_ta,   "s-",  color="#2980b9", lw=2, label="TA-BRPL")
ax2.set_ylabel("패킷 전달률 (PDR)", fontsize=10)
ax2.set_xlabel("시뮬레이션 시간 (초)", fontsize=10)
ax2.set_ylim(0.88, 1.02)
ax2.annotate("Phase 2\n가용성 저하", xy=(500, 0.94), fontsize=8,
             color="red", ha="center",
             arrowprops=dict(arrowstyle="->", color="red"),
             xytext=(500, 0.905))

# 단계 레이블
for ax in axes:
    for x, lbl in [(75,"워밍업"), (250,"공격 전"), (500,"공격 활성"), (775,"복구")]:
        ax.text(x, ax.get_ylim()[1]*0.99, lbl, ha="center", va="top",
                fontsize=7, color="gray")

plt.tight_layout()
plt.savefig(OUT / "fig_concept.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_concept.pdf")


# ══════════════════════════════════════════════════════════
# Figure 2: att_share CDF (BRPL vs TA-BRPL, 밀도별 패널)
# ══════════════════════════════════════════════════════════
brpl_data  = metrics[metrics.protocol == "BRPL"].copy()
ta_data    = metrics[metrics.protocol == "TABRPL"].copy()

fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), sharey=True)
densities = ["sparse", "medium", "dense"]

for ax, dens in zip(axes, densities):
    brpl_vals = sorted(brpl_data[brpl_data.density == dens]["att_share"].values)
    ta_vals   = sorted(ta_data[ta_data.density == dens]["att_share"].values)
    n = len(brpl_vals)
    y = np.linspace(0, 1, n)
    ax.plot(brpl_vals, y, "--", color="#e74c3c", lw=2, label="BRPL")
    ax.plot(ta_vals,   y, "-",  color="#2980b9", lw=2, label="TA-BRPL")
    ax.set_title(f"{LABELS[dens]}", fontsize=11)
    ax.set_xlabel("공격자 경유율", fontsize=9)
    ax.set_xlim(left=0)
    ax.grid(True, alpha=0.3)

    # 중앙값 표시
    bm = np.median(brpl_vals)
    tm = np.median(ta_vals)
    ax.axvline(bm, color="#e74c3c", alpha=0.4, lw=1, linestyle=":")
    ax.axvline(tm, color="#2980b9", alpha=0.4, lw=1, linestyle=":")

axes[0].set_ylabel("누적 확률", fontsize=9)
axes[0].legend(fontsize=9)

plt.suptitle("BRPL vs TA-BRPL: 공격자 경유율 누적분포 (각 밀도 25개 토폴로지)",
             fontsize=10)
plt.tight_layout()
plt.savefig(OUT / "fig_cdf.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_cdf.pdf")


# ══════════════════════════════════════════════════════════
# Figure 3: 토폴로지별 Δatt_share vs Δchurn 산점도
# ══════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 5))

for dens in ["sparse", "medium", "dense"]:
    d = deltas[deltas.density == dens]
    ax.scatter(d["delta_churn"], d["delta_att_share"],
               color=COLORS[dens], label=LABELS[dens],
               alpha=0.75, edgecolors="white", linewidths=0.4, s=55, zorder=3)

# 사분면 레이블
ax.axhline(0, color="gray", lw=0.8, linestyle="--")
ax.axvline(0, color="gray", lw=0.8, linestyle="--")

ax.text( 0.25,  0.04, "churn↑, att↑\n(최악)", fontsize=8,
        ha="center", color="gray")
ax.text(-0.12, -0.06, "churn↓, att↓\n(최선)", fontsize=8,
        ha="center", color="green")
ax.text(-0.12,  0.04, "churn↓, att↑",    fontsize=8, ha="center", color="gray")
ax.text( 0.25, -0.06, "churn↑, att↓\n(허용 범위)", fontsize=8,
        ha="center", color="#2980b9")

ax.set_xlabel("Δchurn (TA-BRPL − BRPL)", fontsize=11)
ax.set_ylabel("Δatt_share (TA-BRPL − BRPL)", fontsize=11)
ax.set_title("토폴로지별 격리 개선 vs. 안정성 비용\n(왼쪽 아래 = TA-BRPL 우세)",
             fontsize=10)
ax.legend(fontsize=9, loc="upper right")
ax.grid(True, alpha=0.25)

# 전체 평균 강조
ax.scatter([deltas["delta_churn"].mean()],
           [deltas["delta_att_share"].mean()],
           marker="D", color="black", s=100, zorder=5, label="전체 평균")
ax.annotate(f"평균\n({deltas['delta_churn'].mean():.3f}, {deltas['delta_att_share'].mean():.3f})",
            xy=(deltas["delta_churn"].mean(), deltas["delta_att_share"].mean()),
            xytext=(0.06, -0.04), fontsize=8,
            arrowprops=dict(arrowstyle="->", color="black"))

plt.tight_layout()
plt.savefig(OUT / "fig_scatter.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_scatter.pdf")


# ══════════════════════════════════════════════════════════
# Figure 4: 밀도별 개선량 + 95% CI 막대 그래프 (Δatt + ΔPDR)
# ══════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(9, 4))

scope_order = ["sparse", "medium", "dense", "overall"]
scope_labels = ["저밀도", "중밀도", "고밀도", "전체"]
x = np.arange(len(scope_order))
w = 0.55

for ax, metric, ylabel, title in zip(
    axes,
    [("delta_att_share_mean", "delta_att_share_ci_lo", "delta_att_share_ci_hi"),
     ("delta_pdr_dur_mean",   "delta_pdr_dur_ci_lo",   "delta_pdr_dur_ci_hi")],
    ["Δatt_share (TA-BRPL − BRPL)", "ΔPDR_dur (TA-BRPL − BRPL)"],
    ["공격자 경유율 감소\n(음수 = TA-BRPL 우세)", "PDR 개선\n(양수 = TA-BRPL 우세)"]
):
    means  = [summary[summary.scope == s][metric[0]].values[0] for s in scope_order]
    ci_lo  = [summary[summary.scope == s][metric[1]].values[0] for s in scope_order]
    ci_hi  = [summary[summary.scope == s][metric[2]].values[0] for s in scope_order]
    yerr_lo = [m - l for m, l in zip(means, ci_lo)]
    yerr_hi = [h - m for m, h in zip(means, ci_hi)]

    bar_colors = [COLORS.get(s, "#555555") for s in scope_order]
    bar_colors[-1] = "#555555"

    bars = ax.bar(x, means, width=w,
                  color=bar_colors, alpha=0.8,
                  yerr=[yerr_lo, yerr_hi], capsize=4,
                  error_kw={"elinewidth": 1.5, "ecolor": "black"})
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(scope_labels, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)

    for i, (m, lo, hi) in enumerate(zip(means, ci_lo, ci_hi)):
        sig = "*" if (metric[0].startswith("delta_att") and lo < 0 < hi == False) else ""
        ax.text(i, m + (0.001 if m >= 0 else -0.001),
                f"{m:+.3f}", ha="center", va="bottom" if m >= 0 else "top",
                fontsize=8)

plt.suptitle("밀도별 평균 개선량 및 95% 신뢰구간 (75개 토폴로지 쌍)",
             fontsize=10)
plt.tight_layout()
plt.savefig(OUT / "fig_density_bar.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_density_bar.pdf")


print("\n모든 figure 생성 완료 →", OUT)
