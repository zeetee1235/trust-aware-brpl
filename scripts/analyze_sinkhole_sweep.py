#!/usr/bin/env python3
"""
analyze_sinkhole_sweep.py
RQ-structured analysis for the sinkhole sweep experiment.

Experiment matrix: 2 topologies × 2 protocols × 2 scenarios × 5 seeds = 40 runs
Results in: results/sinkhole_sweep/{LABEL}/seed{N}/sim.log

RQ1: Does sinkhole attack cause meaningful route capture even without packet drop?
RQ2: Does TA-BRPL reduce attacker dependency vs BRPL?
RQ3: Does TA-BRPL limit PDR damage when drop is added (SINK_DROP50)?
RQ4: What are the trade-offs (churn, overhead)?

Log formats:
  TX:    {node_id}:CSV,TX,{node_id},{seq},{tick},{joined}
  RX:    1:CSV,RX,node=1,{src_ip},{seq},{tx_tick},{rx_tick},{hops}
  ROUTE: {node_id}:CSV,ROUTE,{node_id},{tick},{parent},{rank},{hop},{sw_cnt},{is_sink},{is_att},{joined}
  PROTO: {node_id}:CSV,PROTOCOL,{node_id},{proto}   (BRPL|TABRPL|SINKHOLE|SINKHOLE_DROP)
"""

import os
import sys
import re
import math
from collections import defaultdict
from pathlib import Path

ATTACK_WARMUP_MS = 350_000  # ms — all scenarios use warmup=350s

# ── helpers ──────────────────────────────────────────────────────────────────

def parse_log(path):
    """Parse a sim.log file; return dict of lists keyed by CSV type."""
    data = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip()
            # format: {prefix}:{rest}
            m = re.match(r'^(\d+):(.*)', line)
            if not m:
                continue
            prefix = int(m.group(1))
            rest = m.group(2)
            if rest.startswith('CSV,'):
                parts = rest.split(',')
                key = parts[1]
                data[key].append((prefix, parts))
            elif rest.startswith('ROUTING_READY'):
                data['ROUTING_READY'].append((prefix, rest))
            elif rest.startswith('SIMULATION_DONE'):
                data['SIMULATION_DONE'].append((prefix, rest))
    return data


def get_attacker_ids(data):
    """Return set of node IDs whose protocol is SINKHOLE or SINKHOLE_DROP."""
    attackers = set()
    for prefix, parts in data.get('PROTOCOL', []):
        # parts: [CSV, PROTOCOL, node_id, proto]
        if len(parts) >= 4 and parts[3].startswith('SINKHOLE'):
            try:
                attackers.add(int(parts[2]))
            except ValueError:
                pass
    return attackers


def compute_pdr(data, attacker_ids, root_id=1):
    """
    PDR pre-attack and during-attack.

    TX: prefix=node_id, parts=[CSV, TX, node_id, seq, tick, joined]
    RX: prefix=root_id, parts=[CSV, RX, node=1, src_ip, seq, tx_tick, rx_tick, hops]
    """
    # collect TX per node per period
    tx_pre = defaultdict(int)
    tx_dur = defaultdict(int)
    for prefix, parts in data.get('TX', []):
        node_id = prefix
        if node_id == root_id or node_id in attacker_ids:
            continue
        try:
            tick = int(parts[4])
            if tick < ATTACK_WARMUP_MS:
                tx_pre[node_id] += 1
            else:
                tx_dur[node_id] += 1
        except (IndexError, ValueError):
            pass

    # collect RX per (src_node, seq) per period — dedup by seq
    # RX parts: [CSV, RX, node=1, src_ip, seq, tx_tick, rx_tick, hops]
    rx_pre = defaultdict(set)
    rx_dur = defaultdict(set)
    for prefix, parts in data.get('RX', []):
        if prefix != root_id:
            continue
        try:
            src_ip = parts[3]  # e.g. aaaa::205:5:5:5
            seq = int(parts[4])
            tx_tick = int(parts[5])
            # extract node id from last octet of IP
            # aaaa::2xx:xx:xx:xx → node_id = last octet parsed as hex
            ip_parts = src_ip.split(':')
            node_id = int(ip_parts[-1], 16)
            if node_id == root_id or node_id in attacker_ids:
                continue
            if tx_tick < ATTACK_WARMUP_MS:
                rx_pre[node_id].add(seq)
            else:
                rx_dur[node_id].add(seq)
        except (IndexError, ValueError):
            pass

    total_tx_pre = sum(tx_pre.values())
    total_rx_pre = sum(len(s) for s in rx_pre.values())
    total_tx_dur = sum(tx_dur.values())
    total_rx_dur = sum(len(s) for s in rx_dur.values())

    pdr_pre = total_rx_pre / total_tx_pre if total_tx_pre > 0 else float('nan')
    pdr_dur = total_rx_dur / total_tx_dur if total_tx_dur > 0 else float('nan')
    return pdr_pre, pdr_dur, total_tx_pre, total_tx_dur


def compute_route_metrics(data, attacker_ids, root_id=1):
    """
    att_share: fraction of ROUTE entries (during attack) where parent ∈ attacker_ids.
    hit_ratio: fraction of sender nodes that ever had attacker as parent (during attack).
    max_switch: max switch_count over all nodes at end of sim.
    mean_switch: mean switch_count (last value per node).

    ROUTE: parts=[CSV, ROUTE, node_id, tick, parent, rank, hop, sw_cnt, is_sink, is_att, joined]
    """
    sender_ids = set()
    last_switch = {}
    att_route_count = 0
    total_route_count = 0
    nodes_hit = set()

    for prefix, parts in data.get('ROUTE', []):
        node_id = prefix
        if node_id == root_id or node_id in attacker_ids:
            continue
        try:
            tick = int(parts[3])
            parent = int(parts[4])
            sw_cnt = int(parts[7])
        except (IndexError, ValueError):
            continue

        sender_ids.add(node_id)

        if tick >= ATTACK_WARMUP_MS:
            total_route_count += 1
            if parent in attacker_ids:
                att_route_count += 1
                nodes_hit.add(node_id)

        # track last switch count per node
        last_switch[node_id] = sw_cnt

    att_share = att_route_count / total_route_count if total_route_count > 0 else 0.0
    n_senders = len(sender_ids)
    hit_ratio = len(nodes_hit) / n_senders if n_senders > 0 else 0.0
    mean_churn = sum(last_switch.values()) / len(last_switch) if last_switch else 0.0

    return att_share, hit_ratio, mean_churn, n_senders


def analyze_run(log_path):
    """Return metrics dict for a single run."""
    data = parse_log(log_path)
    attacker_ids = get_attacker_ids(data)
    pdr_pre, pdr_dur, tx_pre, tx_dur = compute_pdr(data, attacker_ids)
    att_share, hit_ratio, mean_churn, n_senders = compute_route_metrics(data, attacker_ids)

    return {
        'pdr_pre': pdr_pre,
        'pdr_dur': pdr_dur,
        'delta_pdr': pdr_dur - pdr_pre,
        'att_share': att_share,
        'hit_ratio': hit_ratio,
        'churn': mean_churn,
        'n_senders': n_senders,
        'tx_pre': tx_pre,
        'tx_dur': tx_dur,
        'attacker_ids': attacker_ids,
    }


def mean(vals):
    v = [x for x in vals if not math.isnan(x)]
    return sum(v) / len(v) if v else float('nan')


def std(vals):
    v = [x for x in vals if not math.isnan(x)]
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--results-dir', default='results/sinkhole_sweep')
    parser.add_argument('--out', default='results/sinkhole_sweep/summary.csv')
    parser.add_argument('--rq', action='store_true', help='Print RQ analysis text')
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"ERROR: {results_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Collect all runs: label → list of metric dicts
    label_runs = defaultdict(list)
    missing = []
    for label_dir in sorted(results_dir.iterdir()):
        if not label_dir.is_dir():
            continue
        label = label_dir.name
        for seed_dir in sorted(label_dir.iterdir()):
            if not seed_dir.is_dir():
                continue
            log = seed_dir / 'sim.log'
            done = seed_dir / 'done'
            if not done.exists():
                missing.append(f"{label}/{seed_dir.name}")
                continue
            if not log.exists():
                missing.append(f"{label}/{seed_dir.name} (no sim.log)")
                continue
            try:
                metrics = analyze_run(log)
                label_runs[label].append(metrics)
            except Exception as e:
                print(f"WARN: {label}/{seed_dir.name}: {e}", file=sys.stderr)

    if missing:
        print(f"Missing/incomplete runs ({len(missing)}):", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)

    # Parse label → (topo, proto, scenario)
    # Label format: GRID_BRPL_SINK_ONLY or BOTTLE_TABRPL_SINK_DROP50
    def parse_label(label):
        parts = label.split('_')
        topo = parts[0]  # GRID or BOTTLE
        proto = parts[1]  # BRPL or TABRPL
        scenario = '_'.join(parts[2:])  # SINK_ONLY or SINK_DROP50
        return topo, proto, scenario

    # Build summary
    rows = []
    for label, runs in sorted(label_runs.items()):
        topo, proto, scenario = parse_label(label)
        n = len(runs)
        atk_ids = set()
        for r in runs:
            atk_ids |= r['attacker_ids']

        row = {
            'label': label,
            'topo': topo,
            'proto': proto,
            'scenario': scenario,
            'n': n,
            'pdr_pre':    mean([r['pdr_pre'] for r in runs]),
            'pdr_dur':    mean([r['pdr_dur'] for r in runs]),
            'delta_pdr':  mean([r['delta_pdr'] for r in runs]),
            'att_share':  mean([r['att_share'] for r in runs]),
            'hit_ratio':  mean([r['hit_ratio'] for r in runs]),
            'churn':      mean([r['churn'] for r in runs]),
            'n_senders':  mean([r['n_senders'] for r in runs]),
            'sd_pdr_dur': std([r['pdr_dur'] for r in runs]),
            'sd_att_share': std([r['att_share'] for r in runs]),
            'atk_ids': sorted(atk_ids),
        }
        rows.append(row)

    # Print table
    header = (f"{'Topo':<8} {'Proto':<8} {'Scenario':<14} {'N':>2}  "
              f"{'PDR_pre':>8} {'PDR_dur':>8} {'ΔPDR':>7}  "
              f"{'att_share':>10} {'hit_ratio':>10} {'churn':>7}  atk_ids")
    print(header)
    print('-' * len(header))
    for r in rows:
        print(f"{r['topo']:<8} {r['proto']:<8} {r['scenario']:<14} {r['n']:>2}  "
              f"{r['pdr_pre']:>8.3f} {r['pdr_dur']:>8.3f} {r['delta_pdr']:>7.3f}  "
              f"{r['att_share']:>10.3f} {r['hit_ratio']:>10.3f} {r['churn']:>7.1f}  "
              f"atk={r['atk_ids']}")

    # Save CSV
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        f.write('topo,proto,scenario,n,pdr_pre,pdr_dur,delta_pdr,'
                'att_share,sd_att_share,hit_ratio,churn,sd_pdr_dur\n')
        for r in rows:
            f.write(f"{r['topo']},{r['proto']},{r['scenario']},{r['n']},"
                    f"{r['pdr_pre']:.4f},{r['pdr_dur']:.4f},{r['delta_pdr']:.4f},"
                    f"{r['att_share']:.4f},{r['sd_att_share']:.4f},"
                    f"{r['hit_ratio']:.4f},{r['churn']:.2f},{r['sd_pdr_dur']:.4f}\n")
    print(f"\nSaved: {out_path}")

    if args.rq:
        print_rq_analysis(rows)


def print_rq_analysis(rows):
    """Print structured RQ analysis for paper."""
    # Index rows
    idx = {(r['topo'], r['proto'], r['scenario']): r for r in rows}

    print("\n" + "=" * 70)
    print("RQ ANALYSIS  (new.md two-phase sinkhole threat model)")
    print("=" * 70)

    # RQ1: Does sinkhole cause route capture without packet drop?
    print("\n── RQ1: Route Capture Without Packet Drop ──")
    for topo in ['GRID', 'BOTTLE']:
        for proto in ['BRPL', 'TABRPL']:
            k = (topo, proto, 'SINK_ONLY')
            if k in idx:
                r = idx[k]
                print(f"  {topo} {proto}: att_share={r['att_share']:.3f} "
                      f"hit_ratio={r['hit_ratio']:.3f}  "
                      f"PDR_pre={r['pdr_pre']:.3f} PDR_dur={r['pdr_dur']:.3f} "
                      f"ΔPDR={r['delta_pdr']:+.3f}")

    # RQ2: Does TA-BRPL reduce attacker dependency?
    print("\n── RQ2: Attacker Dependency Reduction (TA-BRPL vs BRPL) ──")
    for topo in ['GRID', 'BOTTLE']:
        for sc in ['SINK_ONLY', 'SINK_DROP50']:
            brpl = idx.get((topo, 'BRPL', sc))
            tabrpl = idx.get((topo, 'TABRPL', sc))
            if brpl and tabrpl:
                delta_as = tabrpl['att_share'] - brpl['att_share']
                delta_hr = tabrpl['hit_ratio'] - brpl['hit_ratio']
                print(f"  {topo} {sc}: ΔBRPL→TABRPL att_share={delta_as:+.3f} "
                      f"hit_ratio={delta_hr:+.3f}  churn: "
                      f"BRPL={brpl['churn']:.1f} → TABRPL={tabrpl['churn']:.1f}")

    # RQ3: PDR preservation when drop added
    print("\n── RQ3: PDR Degradation under Drop (SINK_ONLY → SINK_DROP50) ──")
    for topo in ['GRID', 'BOTTLE']:
        for proto in ['BRPL', 'TABRPL']:
            so = idx.get((topo, proto, 'SINK_ONLY'))
            sd = idx.get((topo, proto, 'SINK_DROP50'))
            if so and sd:
                print(f"  {topo} {proto}: "
                      f"SINK_ONLY PDR_dur={so['pdr_dur']:.3f}  "
                      f"SINK_DROP50 PDR_dur={sd['pdr_dur']:.3f}  "
                      f"Δ={sd['pdr_dur']-so['pdr_dur']:+.3f}")

    # RQ4: Trade-offs
    print("\n── RQ4: Trade-offs (churn, overhead) ──")
    for topo in ['GRID', 'BOTTLE']:
        for sc in ['SINK_ONLY', 'SINK_DROP50']:
            brpl = idx.get((topo, 'BRPL', sc))
            tabrpl = idx.get((topo, 'TABRPL', sc))
            if brpl and tabrpl:
                print(f"  {topo} {sc}: churn BRPL={brpl['churn']:.1f} "
                      f"TABRPL={tabrpl['churn']:.1f} "
                      f"(Δ={tabrpl['churn']-brpl['churn']:+.1f})")

    print()


if __name__ == '__main__':
    main()
