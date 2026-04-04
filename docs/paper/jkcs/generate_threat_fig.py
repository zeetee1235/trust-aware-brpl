"""
TA-BRPL JKCS — sinkhole 위협 모델 2단계 타임라인 그림
fig_jkcs_threat.pdf (단컬럼 3.5in, 2단 subplot)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from matplotlib.transforms import blended_transform_factory
from pathlib import Path

# 한글 폰트
for _f in [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
]:
    if Path(_f).exists():
        fm.fontManager.addfont(_f)
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_f).get_name()
        break
matplotlib.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)

# ── 개념적 시계열 값 ─────────────────────────────────────────
t_pts  = np.array([  0, 150, 280, 350, 480, 560, 650, 800, 900])

att_brpl = np.array([0.02, 0.03, 0.04, 0.06, 0.12, 0.13, 0.13, 0.05, 0.03])
att_ta   = np.array([0.02, 0.03, 0.03, 0.04, 0.07, 0.07, 0.07, 0.04, 0.03])

pdr_brpl = np.array([1.00, 1.00, 0.99, 0.98, 0.94, 0.93, 0.93, 0.98, 1.00])
pdr_ta   = np.array([1.00, 1.00, 1.00, 0.99, 0.97, 0.97, 0.97, 0.99, 1.00])

# ── Phase 경계 ───────────────────────────────────────────────
T_ATTACK = 350   # sinkhole 활성화 (rank 위조 시작)
T_DROP   = 480   # selective drop 시작 (Phase 2)
T_END    = 650   # 공격 종료

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(3.5, 4.2), sharex=True,
                                gridspec_kw={"hspace": 0.08})

# ── 배경 영역 ────────────────────────────────────────────────
for ax in (ax1, ax2):
    ax.axvspan(0,        T_ATTACK, alpha=0.06, color="#aaaaaa")   # 정상
    ax.axvspan(T_ATTACK, T_DROP,   alpha=0.14, color="#f4a460")   # Phase 1
    ax.axvspan(T_DROP,   T_END,    alpha=0.14, color="#e74c3c")   # Phase 2
    ax.axvspan(T_END,    900,      alpha=0.06, color="#5dade2")   # 복구
    ax.axvline(T_ATTACK, color="#f4a460", lw=0.9, linestyle="--", alpha=0.8)
    ax.axvline(T_DROP,   color="#e74c3c", lw=0.9, linestyle="--", alpha=0.8)
    ax.axvline(T_END,    color="#5dade2", lw=0.9, linestyle="--", alpha=0.8)

# ── 공격자 경유율 ────────────────────────────────────────────
ax1.plot(t_pts, att_brpl, "o--", color="#e74c3c", lw=1.8, ms=4,
         label="BRPL")
ax1.plot(t_pts, att_ta,   "s-",  color="#2980b9", lw=1.8, ms=4,
         label="TA-BRPL")
ax1.set_ylabel("공격자 경유율\n(att\_share)", fontsize=8)
ax1.set_ylim(-0.005, 0.18)
ax1.legend(loc="upper left", fontsize=7.5, framealpha=0.8)
ax1.yaxis.set_major_locator(plt.MultipleLocator(0.05))

# Phase 1 강조 callout
ax1.annotate(
    "경로 장악\n시작",
    xy=(T_ATTACK + 8, 0.058),
    xytext=(455, 0.092),
    fontsize=6.3,
    color="#8a5b18",
    ha="left",
    va="center",
    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#f4a460", alpha=0.92),
    arrowprops=dict(
        arrowstyle="-|>",
        color="#f4a460",
        lw=1.1,
        shrinkA=2,
        shrinkB=2,
        connectionstyle="arc3,rad=0.15",
    ),
)

# ── PDR ─────────────────────────────────────────────────────
ax2.plot(t_pts, pdr_brpl, "o--", color="#e74c3c", lw=1.8, ms=4)
ax2.plot(t_pts, pdr_ta,   "s-",  color="#2980b9", lw=1.8, ms=4)
ax2.set_ylabel("패킷 전달률\n(PDR)", fontsize=8)
ax2.set_xlabel("시뮬레이션 시간 (초)", fontsize=8)
ax2.set_ylim(0.88, 1.03)
ax2.yaxis.set_major_locator(plt.MultipleLocator(0.04))

# Phase 2 강조 callout
ax2.annotate(
    "PDR\n저하",
    xy=(T_DROP + 6, 0.940),
    xytext=(560, 0.920),
    fontsize=6.3,
    color="#b03024",
    ha="center",
    va="top",
    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#e74c3c", alpha=0.92),
    arrowprops=dict(
        arrowstyle="-|>",
        color="#e74c3c",
        lw=1.1,
        shrinkA=2,
        shrinkB=2,
        connectionstyle="arc3,rad=-0.12",
    ),
)

# ── 페이즈 레이블 (ax1 상단 가장자리) ─────────────────────────
phase_tf = blended_transform_factory(ax1.transData, ax1.transAxes)
phase_xs = [(175, "정상"), (415, "Phase 1\n경로 장악"), (555, "Phase 2\n드롭"), (775, "복구")]
for px, plbl in phase_xs:
    ax1.text(
        px,
        0.98,
        plbl,
        transform=phase_tf,
        ha="center",
        va="top",
        fontsize=5.8,
        color="gray",
        multialignment="center",
        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75),
        clip_on=False,
    )

ax1.set_xlim(0, 900)

plt.tight_layout(pad=0.5)
plt.savefig(OUT / "fig_jkcs_threat.pdf", bbox_inches="tight")
plt.close()
print("✓ fig_jkcs_threat.pdf")
