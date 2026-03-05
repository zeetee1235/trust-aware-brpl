#!/usr/bin/env python3
"""Attach PDR values to parsed runs.csv by parsing each run's COOJA.testlog.

Usage:
  python3 scripts/attach_pdr.py \
    --runs-csv results/experiments-20260305-104252/parsed/runs.csv \
    --output results/experiments-20260305-104252/parsed/runs_pdr.csv \
    --workers 8
"""

import argparse
import csv
import ipaddress
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Pool


def parse_cooja_log_for_pdr(filename):
    tx_packets = defaultdict(set)
    rx_packets = defaultdict(set)
    pending_tx_seqs = []
    inferred_sender_id = None
    rx_candidates = []  # (src_ip, seq, has_root_tag)
    seen_root_tagged_rx = False

    try:
        with open(filename, 'r', errors='ignore') as f:
            for line in f:
                line = line.strip()

                if 'CSV,RX,' in line:
                    parts = line.split('CSV,RX,', 1)[1].split(',')
                    if len(parts) >= 2:
                        has_root_tag = (parts[0].strip() == 'node=1')
                        if has_root_tag and len(parts) >= 3:
                            src_ip = parts[1]
                            try:
                                seq = int(parts[2])
                            except ValueError:
                                continue
                        else:
                            src_ip = parts[0]
                            try:
                                seq = int(parts[1])
                            except ValueError:
                                continue

                        if has_root_tag:
                            seen_root_tagged_rx = True
                        rx_candidates.append((src_ip, seq, has_root_tag))

                elif 'CSV,TX,' in line:
                    parts = line.split('CSV,TX,', 1)[1].split(',')
                    if len(parts) >= 2:
                        try:
                            node_id = int(parts[0])
                            seq = int(parts[1])
                        except ValueError:
                            continue
                        tx_packets[node_id].add(seq)

                elif 'TX seq=' in line:
                    # [INFO: SENDER   ] TX id=<n> seq=<n> ...
                    seq = None
                    node_id = None
                    token = 'TX seq='
                    pos = line.find(token)
                    if pos >= 0:
                        i = pos + len(token)
                        j = i
                        while j < len(line) and line[j].isdigit():
                            j += 1
                        if j > i:
                            seq = int(line[i:j])
                    token2 = 'TX id='
                    pos2 = line.find(token2)
                    if pos2 >= 0:
                        i = pos2 + len(token2)
                        j = i
                        while j < len(line) and line[j].isdigit():
                            j += 1
                        if j > i:
                            node_id = int(line[i:j])

                    if seq is not None:
                        if node_id is not None:
                            tx_packets[node_id].add(seq)
                        elif inferred_sender_id is not None:
                            tx_packets[inferred_sender_id].add(seq)
                        else:
                            pending_tx_seqs.append(seq)

    except FileNotFoundError:
        return None, None, None

    if inferred_sender_id is not None and pending_tx_seqs:
        for seq in pending_tx_seqs:
            tx_packets[inferred_sender_id].add(seq)

    if rx_candidates:
        for src_ip, seq, has_root_tag in rx_candidates:
            if seen_root_tagged_rx and not has_root_tag:
                continue
            try:
                ip_obj = ipaddress.ip_address(src_ip)
                node_id = int(ip_obj) & 0xFFFF
                rx_packets[node_id].add(seq)
                if inferred_sender_id is None:
                    inferred_sender_id = node_id
            except ValueError:
                pass

    total_tx = sum(len(v) for v in tx_packets.values())
    total_rx = sum(len(v) for v in rx_packets.values())
    if total_tx <= 0:
        return 0.0, total_tx, total_rx
    return (total_rx / total_tx) * 100.0, total_tx, total_rx


def _worker(item):
    idx, row = item
    run_dir = row.get('run_dir', '')
    log_path = os.path.join(run_dir, 'logs', 'COOJA.testlog')
    pdr, tx, rx = parse_cooja_log_for_pdr(log_path)
    return idx, pdr, tx, rx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs-csv', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--workers', type=int, default=max(1, os.cpu_count() or 1))
    ap.add_argument('--only-attack', action='store_true', help='Compute PDR only for traffic=attack rows')
    ap.add_argument('--limit', type=int, default=0, help='Compute at most N rows (0 means all)')
    ap.add_argument('--shard-id', type=int, default=0, help='Shard id (0-based)')
    ap.add_argument('--num-shards', type=int, default=1, help='Total number of shards')
    args = ap.parse_args()

    if args.num_shards < 1:
        raise ValueError('--num-shards must be >= 1')
    if args.shard_id < 0 or args.shard_id >= args.num_shards:
        raise ValueError('--shard-id must satisfy 0 <= shard-id < num-shards')

    with open(args.runs_csv, newline='') as f:
        rows = list(csv.DictReader(f))

    indexed = []
    for i, r in enumerate(rows):
        if (i % args.num_shards) != args.shard_id:
            continue
        if r.get('status') != 'ok':
            continue
        if r.get('has_testlog') not in ('1', 'true', 'True'):
            continue
        if args.only_attack and r.get('traffic') != 'attack':
            continue
        indexed.append((i, r))
        if args.limit > 0 and len(indexed) >= args.limit:
            break

    print(
        f'Loaded {len(rows)} rows, shard {args.shard_id}/{args.num_shards}, '
        f'computing PDR for {len(indexed)} rows with workers={args.workers}'
    )

    def _apply_result(idx, pdr, tx, rx):
        rows[idx]['pdr'] = '' if pdr is None else f'{pdr:.6f}'
        rows[idx]['pdr_tx_total'] = '' if tx is None else str(tx)
        rows[idx]['pdr_rx_total'] = '' if rx is None else str(rx)

    # Sandbox environments may deny multiprocessing semaphores.
    # Prefer lightweight threads for compatibility; fallback to process pool only if needed.
    if args.workers <= 1:
        for item in indexed:
            idx, pdr, tx, rx = _worker(item)
            _apply_result(idx, pdr, tx, rx)
    else:
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futures = [ex.submit(_worker, item) for item in indexed]
                for fut in as_completed(futures):
                    idx, pdr, tx, rx = fut.result()
                    _apply_result(idx, pdr, tx, rx)
        except Exception as e:
            print(f'Thread pool unavailable ({e}); trying process pool')
            try:
                with Pool(processes=args.workers) as pool:
                    for idx, pdr, tx, rx in pool.imap_unordered(_worker, indexed, chunksize=8):
                        _apply_result(idx, pdr, tx, rx)
            except (PermissionError, OSError) as e2:
                print(f'Process pool unavailable ({e2}); falling back to single-process mode')
                for item in indexed:
                    idx, pdr, tx, rx = _worker(item)
                    _apply_result(idx, pdr, tx, rx)

    # Ensure columns exist for all rows
    for r in rows:
        r.setdefault('pdr', '')
        r.setdefault('pdr_tx_total', '')
        r.setdefault('pdr_rx_total', '')

    fieldnames = list(rows[0].keys()) if rows else []
    # append columns at end if not present
    for c in ['pdr', 'pdr_tx_total', 'pdr_rx_total']:
        if c not in fieldnames:
            fieldnames.append(c)

    with open(args.output, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
