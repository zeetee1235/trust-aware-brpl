#!/usr/bin/env python3
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path('/home/dev/TA-BRPL')
FIGDIR = ROOT / 'docs/paper/figures'
FIGDIR.mkdir(parents=True, exist_ok=True)

SUM_FILES = {
    'v3_520': ROOT / 'results/sinkhole_sweep_policy_v3/summary.csv',
    'tj500': ROOT / 'results/sinkhole_sweep_policy_v4_tj500/summary.csv',
    'tj510': ROOT / 'results/sinkhole_sweep_policy_v4_tj510/summary.csv',
}
GATE_FILES = {
    'tau520': ROOT / 'results/sinkhole_sweep_policy_v4_diag/admission_gate.csv',
    'tau500': ROOT / 'results/sinkhole_sweep_policy_v4_tj500/admission_gate.csv',
    'tau510': ROOT / 'results/sinkhole_sweep_policy_v4_tj510/admission_gate.csv',
}


def read_csv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


summ = {k: read_csv(v) for k, v in SUM_FILES.items()}

def idx(rows):
    return {(r['topo'], r['proto'], r['scenario']): r for r in rows}

I = {k: idx(v) for k, v in summ.items()}

def mean_gap(name):
    vals = []
    for topo in ['GRID', 'BOTTLE']:
        for sc in ['SINK_ONLY', 'SINK_DROP50']:
            b = I[name][(topo, 'BRPL', sc)]
            t = I[name][(topo, 'TABRPL', sc)]
            vals.append((
                float(t['pdr_dur']) - float(b['pdr_dur']),
                float(t['att_share']) - float(b['att_share']),
                float(t['hit_ratio']) - float(b['hit_ratio']),
                float(t['churn']) - float(b['churn']),
            ))
    m = np.mean(np.array(vals), axis=0)
    return m

# Figure 1: mean gaps
labels = ['v3(520)', 'tj500', 'tj510']
metrics = ['PDR gap', 'att_share gap', 'hit_ratio gap', 'churn gap']
arr = np.vstack([mean_gap('v3_520'), mean_gap('tj500'), mean_gap('tj510')])

x = np.arange(len(metrics))
width = 0.24
fig, ax = plt.subplots(figsize=(8.8, 4.2))
for i, name in enumerate(labels):
    ax.bar(x + (i - 1) * width, arr[i], width=width, label=name)
ax.axhline(0, color='black', linewidth=0.8)
ax.set_xticks(x)
ax.set_xticklabels(metrics)
ax.set_title('Mean Gap (TA-BRPL - BRPL)')
ax.set_ylabel('Gap value')
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(FIGDIR / 'fig1_mean_gap.pdf')
plt.close(fig)

# Figure 2: per-cell PDR/att_share
cells = [('GRID','SINK_ONLY'), ('GRID','SINK_DROP50'), ('BOTTLE','SINK_ONLY'), ('BOTTLE','SINK_DROP50')]
cell_labels = ['GRID-ONLY','GRID-DROP50','BOTTLE-ONLY','BOTTLE-DROP50']

fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
for col, metric in enumerate(['pdr_dur', 'att_share']):
    ax = axes[col]
    x = np.arange(len(cells))
    w = 0.25
    brpl = [float(I['tj510'][(t,'BRPL',s)][metric]) for t,s in cells]
    ta_v3 = [float(I['v3_520'][(t,'TABRPL',s)][metric]) for t,s in cells]
    ta_v510 = [float(I['tj510'][(t,'TABRPL',s)][metric]) for t,s in cells]
    ax.bar(x - w, brpl, width=w, label='BRPL')
    ax.bar(x, ta_v3, width=w, label='TA v3(520)')
    ax.bar(x + w, ta_v510, width=w, label='TA tj510')
    ax.set_xticks(x)
    ax.set_xticklabels(cell_labels, rotation=15)
    ax.set_title('PDR_dur' if metric == 'pdr_dur' else 'att_share')
    ax.grid(axis='y', alpha=0.2)
    if col == 0:
        ax.legend(frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig(FIGDIR / 'fig2_cell_metrics.pdf')
plt.close(fig)

# Figure 3: admission block rates
gate = {k: read_csv(v) for k, v in GATE_FILES.items()}

def gate_idx(rows):
    d = {}
    for r in rows:
        d[(r['topo'], r['scenario'])] = r
    return d

G = {k: gate_idx(v) for k, v in gate.items()}

cells2 = [('GRID','SINK_ONLY'), ('GRID','SINK_DROP50'), ('BOTTLE','SINK_ONLY'), ('BOTTLE','SINK_DROP50')]
x = np.arange(len(cells2))
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
for ai, key in enumerate(['att_block_rate', 'norm_block_rate']):
    ax = axes[ai]
    w = 0.25
    y520 = [float(G['tau520'][(t,s)][key]) for t,s in cells2]
    y510 = [float(G['tau510'][(t,s)][key]) for t,s in cells2]
    y500 = [float(G['tau500'][(t,s)][key]) for t,s in cells2]
    ax.bar(x - w, y520, width=w, label='tau520')
    ax.bar(x, y510, width=w, label='tau510')
    ax.bar(x + w, y500, width=w, label='tau500')
    ax.set_xticks(x)
    ax.set_xticklabels([f'{t}-{s.replace("SINK_", "")}' for t,s in cells2], rotation=20)
    ax.set_title('attacker block rate' if key=='att_block_rate' else 'normal block rate')
    ax.grid(axis='y', alpha=0.2)
    if ai == 0:
        ax.legend(frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig(FIGDIR / 'fig3_admission_block_rate.pdf')
plt.close(fig)

# Figure 4: tradeoff scatter
fig, ax = plt.subplots(figsize=(6.5, 4.8))
for name, label in [('v3_520','v3(520)'), ('tj510','tj510'), ('tj500','tj500')]:
    m = mean_gap(name)
    ax.scatter(m[1], m[3], s=90)
    ax.text(m[1] + 0.0006, m[3] + 0.01, label, fontsize=9)
ax.axvline(0, color='black', linewidth=0.8)
ax.axhline(0, color='black', linewidth=0.8)
ax.set_xlabel('mean att_share gap (TA - BRPL)')
ax.set_ylabel('mean churn gap (TA - BRPL)')
ax.set_title('Trade-off map (lower-left is better)')
ax.grid(alpha=0.25)
fig.tight_layout()
fig.savefig(FIGDIR / 'fig4_tradeoff_map.pdf')
plt.close(fig)

print('Generated figures in', FIGDIR)
