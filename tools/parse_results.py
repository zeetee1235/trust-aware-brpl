#!/usr/bin/env python3
"""
parse_results.py — TA-BRPL simulation result parser
=====================================================
Reads results/<PROTOCOL>/<seed>/sim.log for all protocols and seeds,
produces aggregate CSV files in results/.

Output files
------------
  results/pdr_summary.csv
  results/delay_summary.csv
  results/trust_trace.csv       (TABRPL only)
  results/attack_stats.csv
  results/parent_churn.csv

Timing notes
------------
  CLOCK_SECOND = 1000  (Contiki-NG Cooja platform: simCurrentTime / 1000)
  All t0 / t_recv values in log files are in milliseconds.

  Phase boundaries (ms):
    warmup       :     0 – 150 000
    pre_attack   : 150 000 – 350 000
    during_attack: 350 000 – 650 000
    recovery     : 650 000 – 900 000
"""

import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
PROTOCOLS   = ["RPL", "BRPL", "SMTRUST", "TABRPL",
               "TABRPL_FWD", "TABRPL_FWDCTRL",
               "RPL_LOSS90", "BRPL_LOSS90", "TABRPL_LOSS90",
               "RPL_LOSS80", "BRPL_LOSS80", "TABRPL_LOSS80",
               # V5: EWMA lambda sensitivity
               "TABRPL_LAMBDA_FAST", "TABRPL_LAMBDA_SLOW",
               "TABRPL_LAMBDA_FAST_RECOVERY", "TABRPL_LAMBDA_SLOW_RECOVERY",
               # V6: threshold sensitivity
               "TABRPL_THRESH_STRICT", "TABRPL_THRESH_RELAXED", "TABRPL_THRESH_JOINLOW",
               # V2: no-attack FPR experiments
               "RPL_NOATTACK", "BRPL_NOATTACK", "TABRPL_NOATTACK",
               # V3: congestion vs attack separation
               "V3_C1_TABRPL", "V3_C2_TABRPL", "V3_C3_TABRPL", "V3_C4_TABRPL"]
SEEDS       = list(range(1, 31))

# Tick (ms) phase boundaries
WARMUP_START    =      0
PRE_START       = 150_000
ATTACK_START    = 350_000
RECOVERY_START  = 650_000
SIM_END         = 900_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def phase_of(tick: int) -> str:
    """Return the phase name for a given millisecond tick value."""
    if tick < PRE_START:
        return "warmup"
    elif tick < ATTACK_START:
        return "pre_attack"
    elif tick < RECOVERY_START:
        return "during_attack"
    elif tick <= SIM_END:
        return "recovery"
    else:
        return "post"


def _node_from_ip(ip: str) -> int:
    """
    Extract node_id from an IPv6 address like aaaa::205:5:5:5 or fe80::201:1:1:1.
    Returns the last hex octet of the last colon-separated group converted to int.
    Example: aaaa::205:5:5:5  -> last group "5" -> 5
             aaaa::21d:1d:1d:1d -> last group "1d" -> 29 (node 29 = 0x1d)
    Returns -1 on failure.
    """
    try:
        last_group = ip.rstrip().split(":")[-1]
        return int(last_group, 16)
    except (ValueError, IndexError):
        return -1


def parse_log(path: Path):
    """
    Parse a single sim.log file.

    Returns
    -------
    tx_records      : list[dict]   {node_id, seq, t0, phase}
    rx_records      : list[dict]   {src_node, seq, t_recv, t0, delay_ms, phase}
    fwd_records     : list[dict]   {node_id, total_fwd, udp_to_root, dropped}
    parent_events   : list[tuple]  (node_id, parent_ip, approx_tick)
    trust_records   : list[dict]   {self_id, nbr_id, t_fwd, t_ctrl, t_hon,
                                    t_agg, t_ewma, approx_tick}
    attacker_ids    : set[int]
    """
    tx_records    = []
    rx_records    = []
    fwd_records   = []
    parent_events = []
    trust_records = []
    attacker_ids  = set()

    # Per-node most-recent t0 — used to timestamp PARENT/TRUST lines which
    # carry no explicit timestamp; pattern is PARENT -> ROUTING -> TX per round.
    last_tick: dict[int, int] = {}

    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        print(f"  [WARN] Cannot read {path}: {exc}")
        return [], [], [], [], [], set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # All log lines start with "node_id:..."
        colon_pos = line.find(":")
        if colon_pos < 1:
            continue
        try:
            node_id = int(line[:colon_pos])
        except ValueError:
            continue
        rest = line[colon_pos + 1:]

        # ---- Identify attacker nodes via PROTOCOL tag ----------------------
        if rest.startswith("CSV,PROTOCOL,"):
            parts = rest.split(",")
            if len(parts) >= 4 and parts[3].strip().upper() == "ATTACKER":
                attacker_ids.add(node_id)
            continue

        # ---- TX  -----------------------------------------------------------
        # CSV,TX,<node>,<seq>,<t0_ms>,<dag_joined>
        if rest.startswith("CSV,TX,"):
            parts = rest.split(",")
            if len(parts) >= 5:
                try:
                    n   = int(parts[2])
                    seq = int(parts[3])
                    t0  = int(parts[4])
                    last_tick[n] = t0
                    tx_records.append({
                        "node_id": n,
                        "seq":     seq,
                        "t0":      t0,
                        "phase":   phase_of(t0),
                    })
                except ValueError:
                    pass
            continue

        # ---- RX  -----------------------------------------------------------
        # CSV,RX,node=1,<src_ip>,<seq>,<t_recv_ms>,<t0_ms>,<len>
        # parts: [0]=CSV [1]=RX [2]=node=X|src_ip [3]=src_ip|seq ...
        if rest.startswith("CSV,RX,"):
            parts = rest.split(",")
            if len(parts) >= 7:
                try:
                    # Optional "node=X" field at parts[2]
                    offset = 1 if parts[2].startswith("node=") else 0
                    src_ip = parts[2 + offset]
                    seq    = int(parts[3 + offset])
                    t_recv = int(parts[4 + offset])
                    t0     = int(parts[5 + offset])
                    src_node  = _node_from_ip(src_ip)
                    delay_ms  = t_recv - t0          # ms; may be slightly negative due to clock skew
                    rx_records.append({
                        "src_node":  src_node,
                        "seq":       seq,
                        "t_recv":    t_recv,
                        "t0":        t0,
                        "delay_ms":  delay_ms,
                        "phase":     phase_of(t0),   # use sender's send-time for phase
                    })
                except (ValueError, IndexError):
                    pass
            continue

        # ---- FWD  ----------------------------------------------------------
        # CSV,FWD,<node>,<total_fwd>,<udp_to_root>,<dropped>
        if rest.startswith("CSV,FWD,"):
            parts = rest.split(",")
            if len(parts) >= 6:
                try:
                    fwd_records.append({
                        "node_id":    int(parts[2]),
                        "total_fwd":  int(parts[3]),
                        "udp_to_root":int(parts[4]),
                        "dropped":    int(parts[5]),
                    })
                except ValueError:
                    pass
            continue

        # ---- PARENT  -------------------------------------------------------
        # CSV,PARENT,<node>,<parent_ip_or_none>
        if rest.startswith("CSV,PARENT,"):
            parts = rest.split(",")
            if len(parts) >= 4:
                try:
                    n         = int(parts[2])
                    parent_ip = parts[3].strip()
                    parent_events.append((n, parent_ip, last_tick.get(n, -1)))
                except ValueError:
                    pass
            continue

        # ---- TRUST (TABRPL only)  ------------------------------------------
        # CSV,TRUST,<self>,<nbr>,<t_fwd>,<t_ctrl>,<t_hon>,<t_agg>,<t_ewma>
        if rest.startswith("CSV,TRUST,") and not rest.startswith("CSV,TRUST_"):
            parts = rest.split(",")
            if len(parts) >= 9:
                try:
                    self_id = int(parts[2])
                    trust_records.append({
                        "self_id":    self_id,
                        "nbr_id":     int(parts[3]),
                        "t_fwd":      int(parts[4]),
                        "t_ctrl":     int(parts[5]),
                        "t_hon":      int(parts[6]),
                        "t_agg":      int(parts[7]),
                        "t_ewma":     int(parts[8]),
                        "approx_tick": last_tick.get(self_id, -1),
                    })
                except ValueError:
                    pass
            continue

    return (tx_records, rx_records, fwd_records,
            parent_events, trust_records, attacker_ids)


# ---------------------------------------------------------------------------
# Phase-based metrics helpers
# ---------------------------------------------------------------------------

def _pdr_for_phase(tx_df: pd.DataFrame, rx_df: pd.DataFrame,
                   phase: str) -> tuple[int, int, float]:
    """
    Compute PDR for a single phase.
    A (src_node, seq) pair is "delivered" if it appears in both tx and rx
    for that phase. Matching on (node, seq) is required because every sender
    resets its seq counter from 1, so bare seq numbers are not globally unique.
    Returns (tx_count, rx_matched, pdr_fraction).
    """
    tx_phase = tx_df[tx_df["phase"] == phase] if not tx_df.empty else pd.DataFrame()
    rx_phase = rx_df[rx_df["phase"] == phase] if not rx_df.empty else pd.DataFrame()

    if tx_phase.empty:
        return 0, 0, float("nan")

    tx_pairs = set(zip(tx_phase["node_id"], tx_phase["seq"]))
    rx_pairs = set(zip(rx_phase["src_node"], rx_phase["seq"])) if not rx_phase.empty else set()

    tx_count = len(tx_pairs)
    matched  = len(tx_pairs & rx_pairs)
    pdr      = matched / tx_count if tx_count > 0 else float("nan")
    return tx_count, matched, pdr


def _delay_stats(rx_df: pd.DataFrame, phase: str) -> tuple[float, float, float]:
    """
    Return (mean_s, median_s, p90_s) for delay in the given phase.
    Discards non-positive delays (clock-skew artefacts).
    """
    if rx_df.empty:
        return float("nan"), float("nan"), float("nan")
    mask = (rx_df["phase"] == phase) & (rx_df["delay_ms"] > 0)
    vals = rx_df.loc[mask, "delay_ms"].values.astype(float)
    if vals.size == 0:
        return float("nan"), float("nan"), float("nan")
    return (float(np.mean(vals))   / 1000.0,
            float(np.median(vals)) / 1000.0,
            float(np.percentile(vals, 90)) / 1000.0)


def _churn_for_node(events: list, phase: str) -> int:
    """
    Count parent-change events for a single node within a phase.
    `events` is a list of (parent_ip, approx_tick) tuples in log order.
    """
    prev  = None
    churn = 0
    for parent_ip, approx_tick in events:
        if phase_of(approx_tick) != phase:
            continue
        if prev is not None and parent_ip != prev:
            churn += 1
        prev = parent_ip
    return churn


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

def main():
    print("=" * 62)
    print("TA-BRPL result parser")
    print(f"Results directory : {RESULTS_DIR}")
    print(f"Protocols         : {PROTOCOLS}")
    print("=" * 62)

    pdr_rows    = []
    delay_rows  = []
    trust_rows  = []
    attack_rows = []
    churn_rows  = []

    for protocol in PROTOCOLS:
        proto_dir = RESULTS_DIR / protocol
        if not proto_dir.is_dir():
            print(f"\n[SKIP] Protocol directory not found: {proto_dir}")
            continue

        available_seeds = sorted(
            int(d.name) for d in proto_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )
        if not available_seeds:
            print(f"\n[SKIP] No seed sub-directories in {proto_dir}")
            continue

        print(f"\n[{protocol}] Seeds available: {available_seeds}")

        for seed in available_seeds:
            log_path = proto_dir / str(seed) / "sim.log"
            if not log_path.exists():
                print(f"  seed {seed:2d}: sim.log missing — skipping")
                continue

            print(f"  seed {seed:2d}: {log_path} ...", end="  ", flush=True)

            (tx_records, rx_records, fwd_records,
             parent_events, trust_records,
             attacker_ids) = parse_log(log_path)

            print(f"TX={len(tx_records):4d}  RX={len(rx_records):4d}  "
                  f"FWD={len(fwd_records):4d}  TRUST={len(trust_records):4d}  "
                  f"attackers={sorted(attacker_ids)}")

            # Build DataFrames
            tx_df = (pd.DataFrame(tx_records)
                     if tx_records
                     else pd.DataFrame(columns=["node_id", "seq", "t0", "phase"]))
            rx_df = (pd.DataFrame(rx_records)
                     if rx_records
                     else pd.DataFrame(columns=["src_node", "seq", "t_recv",
                                                 "t0", "delay_ms", "phase"]))

            # Remove attacker transmissions and receptions
            if attacker_ids:
                if not tx_df.empty:
                    tx_df = tx_df[~tx_df["node_id"].isin(attacker_ids)].reset_index(drop=True)
                if not rx_df.empty:
                    rx_df = rx_df[~rx_df["src_node"].isin(attacker_ids)].reset_index(drop=True)

            # ----------------------------------------------------------------
            # PDR summary
            # ----------------------------------------------------------------
            tx_all_pairs = (set(zip(tx_df["node_id"], tx_df["seq"]))
                            if not tx_df.empty else set())
            rx_all_pairs = (set(zip(rx_df["src_node"], rx_df["seq"]))
                            if not rx_df.empty else set())
            pdr_overall = (len(tx_all_pairs & rx_all_pairs) / len(tx_all_pairs)
                           if tx_all_pairs else float("nan"))

            _, _, pdr_pre  = _pdr_for_phase(tx_df, rx_df, "pre_attack")
            _, _, pdr_att  = _pdr_for_phase(tx_df, rx_df, "during_attack")
            _, _, pdr_rec  = _pdr_for_phase(tx_df, rx_df, "recovery")

            pdr_rows.append({
                "protocol":          protocol,
                "seed":              seed,
                "pdr_overall":       round(pdr_overall, 6),
                "pdr_pre_attack":    round(pdr_pre,     6),
                "pdr_during_attack": round(pdr_att,     6),
                "pdr_recovery":      round(pdr_rec,     6),
                "tx_total":          len(tx_df),
                "rx_total":          len(rx_df),
            })

            # ----------------------------------------------------------------
            # Delay summary
            # ----------------------------------------------------------------
            # Overall (all valid phases combined)
            if not rx_df.empty:
                valid_delay = rx_df[rx_df["delay_ms"] > 0]["delay_ms"].values.astype(float)
                if valid_delay.size > 0:
                    dmean   = float(np.mean(valid_delay))   / 1000.0
                    dmedian = float(np.median(valid_delay)) / 1000.0
                    dp90    = float(np.percentile(valid_delay, 90)) / 1000.0
                else:
                    dmean = dmedian = dp90 = float("nan")
            else:
                dmean = dmedian = dp90 = float("nan")

            d_pre_mean,  _, _ = _delay_stats(rx_df, "pre_attack")
            d_att_mean,  _, _ = _delay_stats(rx_df, "during_attack")
            d_rec_mean,  _, _ = _delay_stats(rx_df, "recovery")

            delay_rows.append({
                "protocol":           protocol,
                "seed":               seed,
                "delay_mean_s":       round(dmean,        6),
                "delay_median_s":     round(dmedian,      6),
                "delay_p90_s":        round(dp90,         6),
                "delay_pre_attack":   round(d_pre_mean,   6),
                "delay_during_attack":round(d_att_mean,   6),
                "delay_recovery":     round(d_rec_mean,   6),
            })

            # ----------------------------------------------------------------
            # Trust trace (TABRPL and ablation variants)
            # ----------------------------------------------------------------
            for tr in trust_records:
                trust_rows.append({
                    "protocol":     protocol,
                    "seed":         seed,
                    "self_id":      tr["self_id"],
                    "nbr_id":       tr["nbr_id"],
                    "tick":         tr["approx_tick"],
                    "t_fwd":        tr["t_fwd"],
                    "t_ctrl":       tr["t_ctrl"],
                    "t_hon":        tr["t_hon"],
                    "t_agg":        tr["t_agg"],
                    "t_ewma":       tr["t_ewma"],
                })

            # ----------------------------------------------------------------
            # Attack stats — use last FWD record per attacker (cumulative)
            # ----------------------------------------------------------------
            if fwd_records and attacker_ids:
                fwd_df = pd.DataFrame(fwd_records)
                for att_id in attacker_ids:
                    att_rows = fwd_df[fwd_df["node_id"] == att_id]
                    if att_rows.empty:
                        continue
                    last = att_rows.iloc[-1]
                    total   = int(last["total_fwd"])
                    to_root = int(last["udp_to_root"])
                    dropped = int(last["dropped"])
                    attack_rows.append({
                        "protocol":    protocol,
                        "seed":        seed,
                        "attacker_id": att_id,
                        "total_fwd":   total,
                        "udp_to_root": to_root,
                        "dropped":     dropped,
                        "drop_rate":   round(dropped / total, 6) if total > 0 else float("nan"),
                    })

            # ----------------------------------------------------------------
            # Parent churn
            # ----------------------------------------------------------------
            node_parent: dict[int, list] = defaultdict(list)
            for (nid, pip, tick) in parent_events:
                node_parent[nid].append((pip, tick))

            for nid, events in node_parent.items():
                if nid in attacker_ids or nid == 1:
                    continue
                churn_rows.append({
                    "protocol":           protocol,
                    "seed":               seed,
                    "node_id":            nid,
                    "churn_pre_attack":   _churn_for_node(events, "pre_attack"),
                    "churn_during_attack":_churn_for_node(events, "during_attack"),
                    "churn_recovery":     _churn_for_node(events, "recovery"),
                })

    # -------------------------------------------------------------------------
    # Write output CSVs
    # -------------------------------------------------------------------------
    print("\n" + "=" * 62)
    print("Writing output CSVs ...")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def _write(rows, filename, columns):
        df  = (pd.DataFrame(rows, columns=columns)
               if rows else pd.DataFrame(columns=columns))
        out = RESULTS_DIR / filename
        df.to_csv(out, index=False)
        print(f"  {out}  ({len(df)} rows)")

    _write(pdr_rows,    "pdr_summary.csv", [
        "protocol", "seed",
        "pdr_overall", "pdr_pre_attack", "pdr_during_attack", "pdr_recovery",
        "tx_total", "rx_total",
    ])
    _write(delay_rows,  "delay_summary.csv", [
        "protocol", "seed",
        "delay_mean_s", "delay_median_s", "delay_p90_s",
        "delay_pre_attack", "delay_during_attack", "delay_recovery",
    ])
    _write(trust_rows,  "trust_trace.csv", [
        "protocol", "seed", "self_id", "nbr_id", "tick",
        "t_fwd", "t_ctrl", "t_hon", "t_agg", "t_ewma",
    ])
    _write(attack_rows, "attack_stats.csv", [
        "protocol", "seed", "attacker_id",
        "total_fwd", "udp_to_root", "dropped", "drop_rate",
    ])
    _write(churn_rows,  "parent_churn.csv", [
        "protocol", "seed", "node_id",
        "churn_pre_attack", "churn_during_attack", "churn_recovery",
    ])

    print("\nDone.")


if __name__ == "__main__":
    main()
