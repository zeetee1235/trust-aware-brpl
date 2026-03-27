#!/usr/bin/env python3
"""
profile_stuck_state.py
Stuck-state profiling for TA-BRPL logs.

For each TABRPL sim.log, extract per-node evidence of:
  - How long the attacker was current parent
  - Trust signal levels during that period (T_fwd, T_ctrl, T_agg, trust_ema)
  - Whether escape was triggered (TRUST_ESCAPE)
  - Whether better candidates were available (BRPL_BEST alternatives)
  - routeguard escalation: penalty_scale levels over time

Log formats used:
  ROUTE:           {node}:CSV,ROUTE,{node},{tick},{parent},{rank},{hop},{sw_cnt},{is_sink},{is_att},{joined}
  TRUST:           {node}:CSV,TRUST,{node},{nbr},{T_fwd},{T_ctrl},{T_hon},{T_agg},{trust_ema},{trust_fwd_ema}
  TRUST_ROUTEGUARD:{node}:CSV,TRUST_ROUTEGUARD,{node},{nbr},{elapsed_s},{trust},{penalty_scale},{escape}
  TRUST_ESCAPE:    {node}:CSV,TRUST_ESCAPE,{node},{nbr},{clock_time},{trust}
  BRPL_BEST:       {node}:CSV,BRPL_BEST,{node},{best},{score},{second},{second_score},{joined}
  PROTOCOL:        {node}:CSV,PROTOCOL,{node},{proto}
"""

import os
import sys
import re
import math
from collections import defaultdict
from pathlib import Path

# ── Thresholds ────────────────────────────────────────────────────────────────
TAU_WARN  = 600   # τ_warn (project-conf.h current value)
TAU_JOIN  = 350   # τ_join
TAU_BLACK = 200   # τ_black
ATTACK_WARMUP_MS = 350_000

# ── Parser ────────────────────────────────────────────────────────────────────

def parse_log(path):
    data = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip()
            m = re.match(r'^(\d+):(.*)', line)
            if not m:
                continue
            prefix = int(m.group(1))
            rest = m.group(2)
            if rest.startswith('CSV,'):
                parts = rest.split(',')
                data[parts[1]].append((prefix, parts))
    return data


def get_attacker_ids(data):
    attackers = set()
    for prefix, parts in data.get('PROTOCOL', []):
        if len(parts) >= 4 and parts[3] not in ('BRPL', 'TABRPL', 'RPL'):
            try:
                attackers.add(int(parts[2]))
            except ValueError:
                pass
    return attackers


# ── Per-node stuck-state profiling ───────────────────────────────────────────

def profile_node(node_id, attacker_ids, data):
    """
    Returns dict describing the stuck-state profile for this node.
    """
    root_id = 1

    # ── ROUTE timeline ──
    # {tick → parent_id}
    route_timeline = {}
    for prefix, parts in data.get('ROUTE', []):
        if prefix != node_id:
            continue
        try:
            tick = int(parts[3])
            parent = int(parts[4])
            sw_cnt = int(parts[7])
            route_timeline[tick] = (parent, sw_cnt)
        except (IndexError, ValueError):
            pass

    if not route_timeline:
        return None

    # Identify attacker-parent periods (post attack_warmup)
    att_ticks = sorted([
        tick for tick, (parent, _) in route_timeline.items()
        if tick >= ATTACK_WARMUP_MS and parent in attacker_ids
    ])
    total_route_ticks = sum(
        1 for tick, (parent, _) in route_timeline.items()
        if tick >= ATTACK_WARMUP_MS
    )
    att_route_ticks = len(att_ticks)

    if att_route_ticks == 0:
        return None  # never stuck with attacker

    # Continuous stuck periods
    stuck_periods = []
    if att_ticks:
        period_start = att_ticks[0]
        period_end = att_ticks[0]
        for t in att_ticks[1:]:
            if t - period_end <= 60001:  # consecutive 30s reports
                period_end = t
            else:
                stuck_periods.append((period_start, period_end))
                period_start = t
                period_end = t
        stuck_periods.append((period_start, period_end))

    max_stuck_s = max((e - s) // 1000 for s, e in stuck_periods) if stuck_periods else 0
    total_stuck_s = sum((e - s) // 1000 for s, e in stuck_periods) if stuck_periods else 0

    # ── TRUST signals during stuck periods ──
    # Collect trust timeline per neighbor
    # TRUST: node,nbr,T_fwd,T_ctrl,T_hon,T_agg,trust_ema,trust_fwd_ema
    # (each is a snapshot at one update cycle)
    trust_updates = defaultdict(list)
    for prefix, parts in data.get('TRUST', []):
        if prefix != node_id:
            continue
        try:
            # format: CSV,TRUST,node_id,nbr,T_fwd,T_ctrl,T_hon,T_agg,trust_ema,trust_fwd_ema
            nbr = int(parts[3])
            t_fwd = int(parts[4])
            t_ctrl = int(parts[5])
            t_hon = int(parts[6])
            t_agg = int(parts[7])
            trust_ema = int(parts[8])
            trust_fwd_ema = int(parts[9])
            trust_updates[nbr].append({
                'T_fwd': t_fwd, 'T_ctrl': t_ctrl, 'T_hon': t_hon,
                'T_agg': t_agg, 'trust': trust_ema, 'trust_fwd': trust_fwd_ema
            })
        except (IndexError, ValueError):
            pass

    # Get last trust values for each attacker-parent encountered
    attacker_trust_profiles = {}
    for att_id in attacker_ids:
        updates = trust_updates.get(att_id, [])
        if updates:
            # Mean over all updates (shows average trust signal during observation)
            attacker_trust_profiles[att_id] = {
                'n_updates': len(updates),
                'mean_T_ctrl': sum(u['T_ctrl'] for u in updates) / len(updates),
                'mean_T_fwd': sum(u['T_fwd'] for u in updates) / len(updates),
                'mean_trust': sum(u['trust'] for u in updates) / len(updates),
                'mean_trust_fwd': sum(u['trust_fwd'] for u in updates) / len(updates),
                'min_trust': min(u['trust'] for u in updates),
                'min_T_ctrl': min(u['T_ctrl'] for u in updates),
                'min_trust_fwd': min(u['trust_fwd'] for u in updates),
                # How many updates had trust_fwd below TAU_JOIN? (escape gate condition)
                'n_below_tau_join': sum(1 for u in updates if u['trust_fwd'] < TAU_JOIN),
                # How many had T_ctrl below TAU_WARN? (sinkhole signal)
                'n_ctrl_below_tau_warn': sum(1 for u in updates if u['T_ctrl'] < TAU_WARN),
            }

    # ── TRUST_ROUTEGUARD ──
    # node,nbr,elapsed_s,trust,penalty_scale,escape
    routeguard_entries = []
    for prefix, parts in data.get('TRUST_ROUTEGUARD', []):
        if prefix != node_id:
            continue
        try:
            # format: CSV,TRUST_ROUTEGUARD,node_id,nbr,elapsed_s,trust,penalty_scale,escape
            nbr = int(parts[3])
            if nbr not in attacker_ids:
                continue
            elapsed_s = int(parts[4])
            trust = int(parts[5])
            penalty_scale = int(parts[6])
            escape = int(parts[7])
            routeguard_entries.append({
                'nbr': nbr, 'elapsed_s': elapsed_s,
                'trust': trust, 'penalty_scale': penalty_scale, 'escape': escape
            })
        except (IndexError, ValueError):
            pass

    escape_triggered = any(e['escape'] == 1 for e in routeguard_entries)
    max_penalty = max((e['penalty_scale'] for e in routeguard_entries), default=1000)
    max_elapsed = max((e['elapsed_s'] for e in routeguard_entries), default=0)

    # Escape log
    escape_events = []
    for prefix, parts in data.get('TRUST_ESCAPE', []):
        if prefix == node_id:
            escape_events.append(parts)

    # ── BRPL_BEST: alternative candidates ──
    # node,best_candidate,score,second_candidate,second_score,joined
    # When node had attacker as preferred, was there a better alternative?
    brpl_best_entries = []
    for prefix, parts in data.get('BRPL_BEST', []):
        if prefix != node_id:
            continue
        try:
            # format: CSV,BRPL_BEST,node_id,best,score,second,second_score,joined
            best = int(parts[3])
            best_score = int(parts[4])
            second = int(parts[5])
            second_score = int(parts[6])
            joined = int(parts[7])
            brpl_best_entries.append({
                'best': best, 'best_score': best_score,
                'second': second, 'second_score': second_score,
                'joined': joined
            })
        except (IndexError, ValueError):
            pass

    # When attacker was 'best', what was the alternative?
    att_was_best = [e for e in brpl_best_entries if e['best'] in attacker_ids]
    n_att_best = len(att_was_best)
    n_clean_alt_existed = sum(
        1 for e in att_was_best
        if e['second'] not in attacker_ids and e['second'] != 0
    )
    margin_when_clean_alt = [
        e['second_score'] - e['best_score']
        for e in att_was_best
        if e['second'] not in attacker_ids and e['second'] != 0
    ]
    mean_alt_margin = (sum(margin_when_clean_alt) / len(margin_when_clean_alt)
                       if margin_when_clean_alt else float('nan'))

    return {
        'node': node_id,
        'att_route_ticks': att_route_ticks,
        'total_route_ticks': total_route_ticks,
        'att_frac': att_route_ticks / total_route_ticks if total_route_ticks else 0,
        'max_stuck_s': max_stuck_s,
        'total_stuck_s': total_stuck_s,
        'n_stuck_periods': len(stuck_periods),
        'escape_triggered': escape_triggered,
        'n_escape_events': len(escape_events),
        'max_penalty_scale': max_penalty,
        'max_routeguard_elapsed_s': max_elapsed,
        'att_trust_profiles': attacker_trust_profiles,
        'n_att_was_best': n_att_best,
        'n_clean_alt_existed': n_clean_alt_existed,
        'mean_alt_score_margin': mean_alt_margin,
    }


def analyze_log(log_path, label=''):
    data = parse_log(log_path)
    attacker_ids = get_attacker_ids(data)
    if not attacker_ids:
        return None

    root_id = 1
    sender_ids = set()
    for prefix, parts in data.get('PROTOCOL', []):
        node = prefix
        if node != root_id and node not in attacker_ids:
            proto = parts[3] if len(parts) > 3 else ''
            if proto in ('BRPL', 'TABRPL', 'RPL'):
                sender_ids.add(node)

    node_profiles = []
    for node_id in sorted(sender_ids):
        p = profile_node(node_id, attacker_ids, data)
        if p:
            node_profiles.append(p)

    if not node_profiles:
        return None

    return {
        'label': label,
        'log_path': str(log_path),
        'attacker_ids': sorted(attacker_ids),
        'n_senders': len(sender_ids),
        'n_stuck_nodes': len(node_profiles),
        'profiles': node_profiles,
    }


def summarize_profiles(profiles):
    """Aggregate stuck-state statistics across all profiles in a result."""
    all_stuck = profiles['profiles']

    # Case A/B determination per node
    case_a = sum(1 for p in all_stuck if p['n_clean_alt_existed'] > 0)
    case_b = sum(1 for p in all_stuck if p['n_att_was_best'] > 0 and p['n_clean_alt_existed'] == 0)

    # T_ctrl below τ_warn for attacker nodes
    ctrl_below_warn_counts = []
    fwd_below_join_counts = []
    for p in all_stuck:
        for att_id, tp in p['att_trust_profiles'].items():
            ctrl_below_warn_counts.append(tp['n_ctrl_below_tau_warn'])
            fwd_below_join_counts.append(tp['n_below_tau_join'])

    def safe_mean(lst):
        return sum(lst) / len(lst) if lst else float('nan')

    return {
        'n_stuck_nodes': len(all_stuck),
        'case_a': case_a,   # good alt existed but didn't switch
        'case_b': case_b,   # no good alt
        'mean_max_stuck_s': safe_mean([p['max_stuck_s'] for p in all_stuck]),
        'mean_att_frac': safe_mean([p['att_frac'] for p in all_stuck]),
        'mean_n_escape_events': safe_mean([p['n_escape_events'] for p in all_stuck]),
        'n_escape_triggered': sum(1 for p in all_stuck if p['escape_triggered']),
        'mean_max_penalty': safe_mean([p['max_penalty_scale'] for p in all_stuck]),
        'mean_ctrl_below_warn': safe_mean(ctrl_below_warn_counts),
        'mean_fwd_below_join': safe_mean(fwd_below_join_counts),
        'mean_alt_score_margin': safe_mean([
            p['mean_alt_score_margin'] for p in all_stuck
            if not math.isnan(p['mean_alt_score_margin'])
        ]),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--results-dir', default='results/results_L00_A050/TABRPL',
                        help='Directory containing TABRPL sim.log files')
    parser.add_argument('--seeds', type=int, default=30,
                        help='Max seeds to analyze per protocol')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    logs = list(results_dir.glob('**/sim.log'))[:args.seeds]
    if not logs:
        print(f"No sim.log found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(logs)} logs from {results_dir}")
    print()

    all_summaries = []
    for log_path in sorted(logs):
        label = log_path.parent.name
        result = analyze_log(log_path, label)
        if result is None:
            continue
        summary = summarize_profiles(result)
        summary['label'] = label
        summary['attacker_ids'] = result['attacker_ids']
        all_summaries.append((result, summary))

    if not all_summaries:
        print("No stuck-state data found.")
        return

    # ── Print per-seed summary ──
    print(f"{'Seed':<8} {'Stuck':>6} {'CaseA':>6} {'CaseB':>6} "
          f"{'MaxStuck_s':>11} {'AttFrac':>8} {'Escape':>7} "
          f"{'MaxPenalty':>11} {'CtrlBelowWarn':>14} {'FwdBelowJoin':>13} "
          f"{'AltMargin':>10}")
    print('-' * 110)
    for result, s in all_summaries:
        print(f"{s['label']:<8} {s['n_stuck_nodes']:>6} {s['case_a']:>6} {s['case_b']:>6} "
              f"{s['mean_max_stuck_s']:>11.0f} {s['mean_att_frac']:>8.3f} "
              f"{s['n_escape_triggered']:>7} "
              f"{s['mean_max_penalty']:>11.0f} {s['mean_ctrl_below_warn']:>14.2f} "
              f"{s['mean_fwd_below_join']:>13.2f} {s['mean_alt_score_margin']:>10.1f}")

    # ── Aggregate across all seeds ──
    print()
    print("=== AGGREGATE ===")
    def agg_mean(key):
        vals = [s[key] for _, s in all_summaries
                if not (isinstance(s[key], float) and math.isnan(s[key]))]
        return sum(vals) / len(vals) if vals else float('nan')

    total_stuck = sum(s['n_stuck_nodes'] for _, s in all_summaries)
    total_case_a = sum(s['case_a'] for _, s in all_summaries)
    total_case_b = sum(s['case_b'] for _, s in all_summaries)
    total_escape = sum(s['n_escape_triggered'] for _, s in all_summaries)

    print(f"  Total stuck nodes (all seeds):  {total_stuck}")
    print(f"  Case A (good alt existed, no switch): {total_case_a}  ({100*total_case_a/total_stuck:.1f}%)" if total_stuck else "")
    print(f"  Case B (no good alt available):       {total_case_b}  ({100*total_case_b/total_stuck:.1f}%)" if total_stuck else "")
    print(f"  Escape triggered (any):               {total_escape}")
    print(f"  Mean max stuck duration (s):          {agg_mean('mean_max_stuck_s'):.0f}")
    print(f"  Mean attacker route fraction:         {agg_mean('mean_att_frac'):.3f}")
    print(f"  Mean max penalty_scale:               {agg_mean('mean_max_penalty'):.0f}")
    print(f"  Mean T_ctrl-below-τ_warn updates:     {agg_mean('mean_ctrl_below_warn'):.2f}")
    print(f"  Mean T_fwd-below-τ_join updates:      {agg_mean('mean_fwd_below_join'):.2f}")

    # ── Verbose: per-node detail for worst seeds ──
    if args.verbose:
        print()
        print("=== WORST STUCK NODES (per seed) ===")
        for result, s in all_summaries:
            worst = sorted(result['profiles'], key=lambda p: p['max_stuck_s'], reverse=True)[:3]
            for p in worst:
                print(f"  Seed {s['label']}  node={p['node']}  "
                      f"stuck={p['max_stuck_s']}s  att_frac={p['att_frac']:.3f}  "
                      f"escape={p['escape_triggered']}  n_esc={p['n_escape_events']}  "
                      f"penalty={p['max_penalty_scale']}")
                for att_id, tp in p['att_trust_profiles'].items():
                    print(f"    → attacker {att_id}: "
                          f"mean_T_ctrl={tp['mean_T_ctrl']:.0f}  "
                          f"min_T_ctrl={tp['min_T_ctrl']:.0f}  "
                          f"n_ctrl_below_warn={tp['n_ctrl_below_tau_warn']}  "
                          f"mean_trust_fwd={tp['mean_trust_fwd']:.0f}  "
                          f"n_fwd_below_join={tp['n_below_tau_join']}")
                print(f"    → alt: n_att_was_best={p['n_att_was_best']}  "
                      f"n_clean_alt={p['n_clean_alt_existed']}  "
                      f"mean_margin={p['mean_alt_score_margin']:.1f}")


if __name__ == '__main__':
    main()
