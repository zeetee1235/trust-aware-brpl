#!/usr/bin/env python3
"""parse_results.py — Parse TA-BRPL sim.log files into summary CSVs.

Usage:
    python3 scripts/parse_results.py

Outputs (in results/):
    pdr_summary.csv     — (protocol, seed, pdr_pre_attack, pdr_during_attack, pdr_recovery)
    delay_summary.csv   — (protocol, seed, delay_{phase}_mean, delay_{phase}_p50)
    trust_trace.csv     — (protocol, seed, self_id, nbr_id, tick, t_fwd, t_ctrl, t_hon, t_agg, t_ewma)
    parent_churn.csv    — (protocol, seed, node_id, churn_pre_attack, churn_during_attack, churn_recovery)
    route_trace.csv     — (protocol, seed, node_id, tick, parent_id, rank, hop_est, parent_switch_count, parent_is_sink, parent_is_attacker, joined)
"""

from pathlib import Path
from collections import defaultdict
import argparse
import csv
import statistics

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
PROTOCOLS   = ["RPL", "BRPL", "SMTRUST", "TABRPL"]

# Phase boundaries in ms (= Cooja ticks; CLOCK_SECOND=1000 so ticks == ms)
PHASES = {
    "pre_attack":    (150_000, 350_000),
    "during_attack": (350_000, 650_000),
    "recovery":      (650_000, 900_000),
}

# TA-BRPL trust update interval (seconds * CLOCK_SECOND = ms)
TRUST_INTERVAL_MS = 60 * 1000


def classify_phase(t0_ms: int):
    for name, (lo, hi) in PHASES.items():
        if lo <= t0_ms < hi:
            return name
    return None


def parse_simlog(log_path: Path) -> dict:
    """Parse one sim.log file and return structured data."""
    tx_by_node  = defaultdict(list)     # node_id -> [t0_ms, ...]
    tx_seq_time = {}                    # (node_id, seq) -> t0_ms
    rx_events   = []                    # [(src_node, seq, t_recv, t0)]
    trust_events = []                   # [(self_id, nbr_id, t_fwd, t_ctrl, t_hon, t_agg, t_ewma)]
    route_events = []                   # [(node_id, parent_id, rank, hop_est, parent_switch_count, parent_is_sink, parent_is_attacker, joined, tick)]
    # Parent tracking: detect changes relative to last TX time
    current_parent = {}                 # node_id -> parent_str
    parent_changes = defaultdict(list)  # node_id -> [(t0_est_ms, new_parent)]

    # We need to associate PARENT events with a time estimate.
    # PARENT is logged just before each TX from the same mote,
    # so we use the t0 of the NEXT TX from that mote.
    # Strategy: buffer PARENT events until a TX is seen, then assign t0.
    pending_parent = {}                 # node_id -> buffered parent str (not yet time-stamped)

    with open(log_path, errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            colon = line.find(':')
            if colon < 1:
                continue
            try:
                mote_id = int(line[:colon])
            except ValueError:
                continue
            rest = line[colon + 1:]

            # ---- CSV,TX,node_id,seq,t0_ms,joined ----
            if rest.startswith('CSV,TX,'):
                parts = rest.split(',')
                if len(parts) < 5:
                    continue
                try:
                    node_id = int(parts[2])
                    seq     = int(parts[3])
                    t0_ms   = int(parts[4])
                except ValueError:
                    continue
                tx_by_node[node_id].append(t0_ms)
                tx_seq_time[(node_id, seq)] = t0_ms
                # Assign any pending PARENT event for this node
                if node_id in pending_parent:
                    parent_str = pending_parent.pop(node_id)
                    prev = current_parent.get(node_id)
                    if prev != parent_str:
                        parent_changes[node_id].append((t0_ms, parent_str))
                        current_parent[node_id] = parent_str

            # ---- CSV,PARENT,node_id,parent_ip_or_none ----
            elif rest.startswith('CSV,PARENT,'):
                parts = rest.split(',', 3)
                if len(parts) < 4:
                    continue
                try:
                    node_id = int(parts[2])
                except ValueError:
                    continue
                parent_str = parts[3].strip()
                # Buffer until we see the next TX (which will have t0)
                pending_parent[node_id] = parent_str

            # ---- CSV,RX,node=1,src_ip,seq,t_recv_ms,t0_ms,datalen ----
            elif rest.startswith('CSV,RX,'):
                parts = rest.split(',')
                if len(parts) < 7:
                    continue
                # parts[2] = "node=1", parts[3] = src_ip
                src_ip = parts[3]
                try:
                    seq    = int(parts[4])
                    t_recv = int(parts[5])
                    t0     = int(parts[6])
                except ValueError:
                    continue
                # Extract node_id from last colon-group of IPv6 address
                try:
                    last_group = src_ip.rsplit(':', 1)[-1]
                    node_id = int(last_group, 16)
                except ValueError:
                    node_id = 0
                rx_events.append((node_id, seq, t_recv, t0))

            # ---- CSV,TRUST,self_id,nbr_id,t_fwd,t_ctrl,t_hon,t_agg,t_ewma ----
            elif rest.startswith('CSV,TRUST,') and not rest.startswith('CSV,TRUST_'):
                parts = rest.split(',')
                if len(parts) < 9:
                    continue
                try:
                    vals = [int(p) for p in parts[2:9]]
                except ValueError:
                    continue
                trust_events.append(tuple(vals))  # (self_id, nbr_id, t_fwd, t_ctrl, t_hon, t_agg, t_ewma)

            # ---- CSV,ROUTE,node_id,tick,parent_id,rank,hop_est,parent_switch_count,parent_is_sink,parent_is_attacker,joined ----
            # legacy: CSV,ROUTE,node_id,parent_id,rank,hop_est,parent_switch_count,parent_is_sink,parent_is_attacker,joined
            elif rest.startswith('CSV,ROUTE,'):
                parts = rest.split(',')
                if len(parts) < 10:
                    continue
                try:
                    node_id = int(parts[2])
                    if len(parts) >= 11:
                        tick = int(parts[3])
                        parent_id = int(parts[4])
                        rank = int(parts[5])
                        hop_est = int(parts[6])
                        parent_switch_count = int(parts[7])
                        parent_is_sink = int(parts[8])
                        parent_is_attacker = int(parts[9])
                        joined = int(parts[10])
                    else:
                        tick = None
                        parent_id = int(parts[3])
                        rank = int(parts[4])
                        hop_est = int(parts[5])
                        parent_switch_count = int(parts[6])
                        parent_is_sink = int(parts[7])
                        parent_is_attacker = int(parts[8])
                        joined = int(parts[9])
                except ValueError:
                    continue
                route_events.append((
                    node_id, parent_id, rank, hop_est,
                    parent_switch_count, parent_is_sink,
                    parent_is_attacker, joined, tick
                ))

    return {
        'tx_by_node':   dict(tx_by_node),
        'tx_seq_time':  tx_seq_time,
        'rx_events':    rx_events,
        'parent_changes': dict(parent_changes),
        'trust_events': trust_events,
        'route_events': route_events,
    }


def compute_pdr(data: dict) -> dict:
    """PDR per phase."""
    tx_phase = defaultdict(int)
    rx_phase = defaultdict(int)

    for node_id, t0_list in data['tx_by_node'].items():
        for t0 in t0_list:
            phase = classify_phase(t0)
            if phase:
                tx_phase[phase] += 1

    for (node_id, seq, t_recv, t0) in data['rx_events']:
        phase = classify_phase(t0)
        if phase:
            rx_phase[phase] += 1

    result = {}
    for phase in PHASES:
        total_tx = tx_phase[phase]
        total_rx = rx_phase[phase]
        result[f'pdr_{phase}']  = total_rx / total_tx if total_tx > 0 else float('nan')
        result[f'tx_{phase}']   = total_tx
        result[f'rx_{phase}']   = total_rx
    return result


def compute_delay(data: dict) -> dict:
    """Mean and median delay per phase (using t0 for phase classification)."""
    delays = defaultdict(list)
    for (node_id, seq, t_recv, t0) in data['rx_events']:
        if t_recv >= t0:
            delay_ms = t_recv - t0
            phase = classify_phase(t0)
            if phase:
                delays[phase].append(delay_ms)

    result = {}
    for phase in PHASES:
        vals = delays[phase]
        if vals:
            result[f'delay_{phase}_mean'] = statistics.mean(vals)
            result[f'delay_{phase}_p50']  = statistics.median(vals)
            result[f'delay_{phase}_p90']  = sorted(vals)[int(0.9 * len(vals))]
            result[f'delay_{phase}_n']    = len(vals)
        else:
            result[f'delay_{phase}_mean'] = float('nan')
            result[f'delay_{phase}_p50']  = float('nan')
            result[f'delay_{phase}_p90']  = float('nan')
            result[f'delay_{phase}_n']    = 0
    return result


def compute_churn(data: dict) -> list:
    """Parent-change count per node per phase."""
    rows = []
    for node_id, changes in data['parent_changes'].items():
        churn = defaultdict(int)
        for (t0_est, parent) in changes:
            phase = classify_phase(t0_est) or 'other'
            churn[phase] += 1
        rows.append({
            'node_id':             node_id,
            'churn_pre_attack':    churn.get('pre_attack', 0),
            'churn_during_attack': churn.get('during_attack', 0),
            'churn_recovery':      churn.get('recovery', 0),
            'churn_other':         churn.get('other', 0),
        })
    return rows


def compute_trust(data: dict, proto: str, seed: int) -> list:
    """Trust trace with approximate simulation time (update count × interval)."""
    trust_by_pair = defaultdict(list)
    for event in data['trust_events']:
        key = (event[0], event[1])  # (self_id, nbr_id)
        trust_by_pair[key].append(event)

    rows = []
    for (self_id, nbr_id), events in trust_by_pair.items():
        for idx, (s, n, t_fwd, t_ctrl, t_hon, t_agg, t_ewma) in enumerate(events):
            approx_tick = (idx + 1) * TRUST_INTERVAL_MS
            rows.append({
                'protocol': proto,
                'seed':     seed,
                'self_id':  self_id,
                'nbr_id':   nbr_id,
                'tick':     approx_tick,
                't_fwd':    t_fwd,
                't_ctrl':   t_ctrl,
                't_hon':    t_hon,
                't_agg':    t_agg,
                't_ewma':   t_ewma,
            })
    return rows


def compute_route_trace(data: dict, proto: str, seed: int) -> list:
    rows = []
    for (node_id, parent_id, rank, hop_est,
         parent_switch_count, parent_is_sink,
         parent_is_attacker, joined, tick) in data.get('route_events', []):
        rows.append({
            'protocol': proto,
            'seed': seed,
            'node_id': node_id,
            'tick': tick if tick is not None else '',
            'parent_id': parent_id,
            'rank': rank,
            'hop_est': hop_est,
            'parent_switch_count': parent_switch_count,
            'parent_is_sink': parent_is_sink,
            'parent_is_attacker': parent_is_attacker,
            'joined': joined,
        })
    return rows


def write_csv(path: Path, rows: list, fieldnames=None):
    if not rows:
        print(f"  [SKIP] {path.name} — no rows")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f"  {len(rows):>6} rows → {path.name}")


def main():
    print("=" * 60)
    print("TA-BRPL results parser")
    print(f"Reading from: {RESULTS_DIR}")
    print("=" * 60)

    pdr_rows   = []
    delay_rows = []
    churn_rows = []
    trust_rows = []
    route_rows = []

    for proto in PROTOCOLS:
        proto_dir = RESULTS_DIR / proto
        if not proto_dir.is_dir():
            print(f"[SKIP] {proto} — directory not found")
            continue

        seeds = sorted(
            int(d.name)
            for d in proto_dir.iterdir()
            if d.is_dir() and d.name.isdigit() and (d / 'sim.log').exists()
        )
        if not seeds:
            print(f"[SKIP] {proto} — no seed directories with sim.log")
            continue

        print(f"\n[{proto}] {len(seeds)} seeds: {seeds[:5]}{'...' if len(seeds) > 5 else ''}")

        for seed in seeds:
            log_path = proto_dir / str(seed) / 'sim.log'
            data = parse_simlog(log_path)

            pdr   = compute_pdr(data)
            delay = compute_delay(data)
            churn = compute_churn(data)
            trust = compute_trust(data, proto, seed) if proto == 'TABRPL' else []
            route = compute_route_trace(data, proto, seed)

            pdr_rows.append({'protocol': proto, 'seed': seed, **pdr})
            delay_rows.append({'protocol': proto, 'seed': seed, **delay})
            for row in churn:
                churn_rows.append({'protocol': proto, 'seed': seed, **row})
            trust_rows.extend(trust)
            route_rows.extend(route)

            tx_total = sum(pdr.get(f'tx_{p}', 0) for p in PHASES)
            rx_total = sum(pdr.get(f'rx_{p}', 0) for p in PHASES)
            pdr_atk  = pdr.get('pdr_during_attack', float('nan'))
            print(f"  seed={seed:>2}  TX={tx_total:>4}  RX={rx_total:>4}  "
                  f"PDR_attack={pdr_atk:.3f}")

    print("\nWriting CSVs...")
    write_csv(RESULTS_DIR / 'pdr_summary.csv',   pdr_rows)
    write_csv(RESULTS_DIR / 'delay_summary.csv',  delay_rows)
    write_csv(RESULTS_DIR / 'parent_churn.csv',   churn_rows)
    write_csv(RESULTS_DIR / 'trust_trace.csv',    trust_rows)
    write_csv(RESULTS_DIR / 'route_trace.csv',    route_rows)
    print("\nDone.")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Parse TA-BRPL sim.log files into summary CSVs.')
    ap.add_argument('--results-dir', default=None,
                    help='Override results directory (default: <repo>/results)')
    ap.add_argument('--protocols', default=None,
                    help='Comma-separated protocol list (default: RPL,BRPL,SMTRUST,TABRPL)')
    args = ap.parse_args()
    if args.results_dir:
        RESULTS_DIR = Path(args.results_dir)
    if args.protocols:
        PROTOCOLS = [p.strip() for p in args.protocols.split(',')]
    main()
