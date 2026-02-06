#!/usr/bin/env python3
"""
CSV 로그 파서: Cooja 로그에서 성능 지표 추출
- PDR (Packet Delivery Ratio)
- End-to-End Delay
- Overhead (제어 패킷 수)
"""

import sys
import re
import ipaddress
from collections import defaultdict

def parse_cooja_log(filename):
    """Cooja 로그 파일에서 CSV 라인 추출 및 분석"""
    
    # 데이터 저장소
    tx_packets = defaultdict(list)  # {node_id: [seq1, seq2, ...]}
    rx_packets = defaultdict(list)  # {node_id: [seq1, seq2, ...]}
    delays = []  # [(seq, delay_ms), ...]
    pending_tx_seqs = []  # seqs without node id
    inferred_sender_id = None
    
    # 제어 패킷 카운터
    rpl_packets = 0
    attacker_id = 3
    parent_samples = 0
    parent_attacker = 0
    last_fwd_totals = defaultdict(lambda: {"udp": 0, "dropped": 0})
    attacker_udp_total = 0
    attacker_udp_dropped = 0
    
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                
                # CSV 라인 파싱
                if 'CSV,RX,' in line:
                    # CSV,RX,<src_ip>,<seq>,<t_recv>,<t0>,<len> (t0 optional)
                    parts = line.split('CSV,RX,')[1].split(',')
                    if len(parts) >= 2:
                        seq = int(parts[1])
                        # src_ip에서 노드 ID 추출 (IPv6 마지막 16비트)
                        src_ip = parts[0]
                        try:
                            ip_obj = ipaddress.ip_address(src_ip)
                            node_id = int(ip_obj) & 0xffff
                            rx_packets[node_id].append(seq)
                            if inferred_sender_id is None:
                                inferred_sender_id = node_id
                        except ValueError:
                            pass
                    # Do not compute delay from RX timestamps (different mote clocks).
                    pass
                
                elif 'CSV,RTT,' in line:
                    # CSV,RTT,<seq>,<t0>,<t_ack>,<rtt_ticks>,<len>
                    parts = line.split('CSV,RTT,')[1].split(',')
                    if len(parts) >= 4:
                        seq = int(parts[0])
                        rtt_ticks = int(parts[3])
                        # Cooja clock: 1 tick = 1ms (일반적)
                        delay_ms = rtt_ticks / 2.0  # RTT의 절반이 one-way delay
                        delays.append((seq, delay_ms))
                
                elif 'CSV,DELAY,' in line:
                    # Legacy delay line (kept for compatibility)
                    parts = line.split('CSV,DELAY,')[1].split(',')
                    if len(parts) >= 2:
                        seq = int(parts[0])
                        delay_ticks = int(parts[1])
                        delay_ms = delay_ticks  # 1 tick ~= 1ms in Cooja
                        delays.append((seq, delay_ms))
                
                # TX 로그 추출 (sender.c에서 출력)
                elif 'CSV,TX,' in line:
                    # CSV,TX,<node_id>,<seq>,<t0>,<joined>
                    parts = line.split('CSV,TX,')[1].split(',')
                    if len(parts) >= 2:
                        node_id = int(parts[0])
                        seq = int(parts[1])
                        tx_packets[node_id].append(seq)

                elif 'CSV,FWD,' in line:
                    # CSV,FWD,<node_id>,<fwd_total>,<udp_to_root>,<dropped>
                    parts = line.split('CSV,FWD,')[1].split(',')
                    if len(parts) >= 4:
                        node_id = int(parts[0])
                        udp_to_root = int(parts[2])
                        dropped = int(parts[3])
                        last = last_fwd_totals[node_id]
                        delta_udp = max(udp_to_root - last["udp"], 0)
                        delta_dropped = max(dropped - last["dropped"], 0)
                        last["udp"] = udp_to_root
                        last["dropped"] = dropped
                        if node_id == attacker_id:
                            attacker_udp_total += delta_udp
                            attacker_udp_dropped += delta_dropped

                elif 'CSV,PARENT,' in line:
                    # CSV,PARENT,<node_id>,<parent_ip|none|unknown>
                    parts = line.split('CSV,PARENT,')[1].split(',')
                    if len(parts) >= 2:
                        parent_samples += 1
                        parent_ip = parts[1]
                        try:
                            ip_obj = ipaddress.ip_address(parent_ip)
                            parent_id = int(ip_obj) & 0xffff
                            if parent_id == attacker_id:
                                parent_attacker += 1
                        except ValueError:
                            pass

                elif 'TX seq=' in line:
                    # [INFO: SENDER   ] TX id=<n> seq=<n> ...
                    match = re.search(r'TX seq=(\d+)', line)
                    if match:
                        seq = int(match.group(1))
                        node_match = re.search(r'TX id=(\d+)', line)
                        if node_match:
                            node_id = int(node_match.group(1))
                            tx_packets[node_id].append(seq)
                        elif inferred_sender_id is not None:
                            tx_packets[inferred_sender_id].append(seq)
                        else:
                            pending_tx_seqs.append(seq)
                
                # RPL 제어 패킷 카운터
                if 'RPL:' in line or 'DIO' in line or 'DAO' in line:
                    rpl_packets += 1
    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)

    if inferred_sender_id is not None and pending_tx_seqs:
        tx_packets[inferred_sender_id].extend(pending_tx_seqs)

    exposure = {
        "attacker_udp_total": attacker_udp_total,
        "attacker_udp_dropped": attacker_udp_dropped,
        "parent_samples": parent_samples,
        "parent_attacker": parent_attacker,
        "attacker_id": attacker_id,
    }

    return tx_packets, rx_packets, delays, rpl_packets, exposure


def calculate_metrics(tx_packets, rx_packets, delays, rpl_packets, exposure):
    """성능 지표 계산"""
    
    print("\n" + "="*60)
    print("Performance Analysis Results")
    print("="*60)
    
    # 1. PDR (Packet Delivery Ratio)
    print("\n[1] PDR (Packet Delivery Ratio)")
    print("-" * 60)
    
    total_tx = 0
    total_rx = 0
    
    for node_id in sorted(set(list(tx_packets.keys()) + list(rx_packets.keys()))):
        tx_count = len(tx_packets.get(node_id, []))
        rx_count = len(rx_packets.get(node_id, []))
        
        total_tx += tx_count
        total_rx += rx_count
        
        if tx_count > 0:
            pdr = (rx_count / tx_count) * 100
            print(f"Node {node_id:2d}: TX={tx_count:4d}, RX={rx_count:4d}, PDR={pdr:6.2f}%")
        else:
            print(f"Node {node_id:2d}: No TX packets")
    
    if total_tx > 0:
        overall_pdr = (total_rx / total_tx) * 100
        print(f"\nOverall: TX={total_tx:4d}, RX={total_rx:4d}, PDR={overall_pdr:6.2f}%")
    else:
        print("\nNo TX packets detected")
    
    # 2. End-to-End Delay
    print("\n[2] End-to-End Delay (based on RTT)")
    print("-" * 60)
    
    if delays:
        delay_values = [d for _, d in delays]
        avg_delay = sum(delay_values) / len(delay_values)
        min_delay = min(delay_values)
        max_delay = max(delay_values)
        
        print(f"Sample count: {len(delays)}")
        print(f"Average:      {avg_delay:.2f} ms")
        print(f"Min:          {min_delay:.2f} ms")
        print(f"Max:          {max_delay:.2f} ms")
    else:
        print("No RTT data available")
    
    # 3. Overhead (RPL control packets)
    print("\n[3] Overhead (Control Packets)")
    print("-" * 60)
    print(f"RPL packets:  {rpl_packets}")
    
    if total_tx > 0:
        overhead_ratio = (rpl_packets / total_tx) * 100
        print(f"Control/Data: {overhead_ratio:.2f}%")

    # 4. Exposure (Attacker path inclusion)
    print("\n[4] Exposure (Attacker Path Inclusion)")
    print("-" * 60)
    attacker_id = exposure["attacker_id"]
    attacker_udp_total = exposure["attacker_udp_total"]
    attacker_udp_dropped = exposure["attacker_udp_dropped"]
    parent_samples = exposure["parent_samples"]
    parent_attacker = exposure["parent_attacker"]

    if total_tx > 0:
        exposure_ratio = (attacker_udp_total / total_tx) * 100
        print(f"E1 (via attacker {attacker_id}): {exposure_ratio:.2f}% (UDP to root)")
    else:
        print(f"E1 (via attacker {attacker_id}): N/A (no TX packets)")

    if parent_samples > 0:
        parent_ratio = (parent_attacker / parent_samples) * 100
        print(f"E3 (parent=attacker): {parent_ratio:.2f}% ({parent_attacker}/{parent_samples})")
    else:
        print("E3 (parent=attacker): N/A (no parent samples)")

    if attacker_udp_total > 0:
        drop_ratio = (attacker_udp_dropped / attacker_udp_total) * 100
        print(f"Attacker drop ratio: {drop_ratio:.2f}% ({attacker_udp_dropped}/{attacker_udp_total})")

    print("\n" + "="*60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/parse_results.py <cooja_log_file>")
        print("Example: python3 tools/parse_results.py logs/COOJA.testlog")
        sys.exit(1)
    
    log_file = sys.argv[1]
    
    print(f"Parsing log file: {log_file}")
    
    tx_packets, rx_packets, delays, rpl_packets, exposure = parse_cooja_log(log_file)
    
    calculate_metrics(tx_packets, rx_packets, delays, rpl_packets, exposure)


if __name__ == '__main__':
    main()
