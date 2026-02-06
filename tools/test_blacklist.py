#!/usr/bin/env python3
"""
Blacklist Functionality Test
Tests network-layer packet filtering based on trust values
"""

import sys
import re
from collections import defaultdict

def parse_blacklist_events(log_file):
    """Parse blacklist-related events from log"""
    events = {
        'blacklist_adds': [],
        'blacklist_removes': [],
        'packet_drops': [],
        'trust_updates': []
    }
    
    with open(log_file, 'r') as f:
        for line_no, line in enumerate(f, 1):
            # CSV,BLACKLIST_ADD,<node>,<count>
            match = re.search(r'CSV,BLACKLIST_ADD,(\d+),(\d+)', line)
            if match:
                events['blacklist_adds'].append({
                    'line': line_no,
                    'node_id': int(match.group(1)),
                    'count': int(match.group(2))
                })
            
            # CSV,BLACKLIST_REMOVE,<node>,<count>
            match = re.search(r'CSV,BLACKLIST_REMOVE,(\d+),(\d+)', line)
            if match:
                events['blacklist_removes'].append({
                    'line': line_no,
                    'node_id': int(match.group(1)),
                    'count': int(match.group(2))
                })
            
            # CSV,PKT_DROP_DEST or CSV,PKT_DROP_SRC
            match = re.search(r'CSV,PKT_DROP_(DEST|SRC),(\d+)', line)
            if match:
                events['packet_drops'].append({
                    'line': line_no,
                    'type': match.group(1),
                    'node_id': int(match.group(2))
                })
            
            # CSV,TRUST_IN,<self>,<node>,<trust>
            match = re.search(r'CSV,TRUST_IN,(\d+),(\d+),(\d+)', line)
            if match:
                events['trust_updates'].append({
                    'line': line_no,
                    'self_id': int(match.group(1)),
                    'node_id': int(match.group(2)),
                    'trust': int(match.group(3))
                })
    
    return events

def analyze_blacklist_behavior(log_file):
    """Analyze blacklist behavior"""
    print("=" * 80)
    print("Blacklist Functionality Analysis")
    print("=" * 80)
    print(f"Log file: {log_file}\n")
    
    events = parse_blacklist_events(log_file)
    
    print("[1] Blacklist Operations:")
    print(f"  - Nodes added to blacklist: {len(events['blacklist_adds'])}")
    print(f"  - Nodes removed from blacklist: {len(events['blacklist_removes'])}")
    print(f"  - Packets dropped: {len(events['packet_drops'])}")
    print(f"  - Trust updates received: {len(events['trust_updates'])}")
    
    if events['blacklist_adds']:
        print(f"\n[2] Blacklisted Nodes:")
        node_adds = defaultdict(int)
        for evt in events['blacklist_adds']:
            node_adds[evt['node_id']] += 1
        
        for node_id in sorted(node_adds.keys()):
            count = node_adds[node_id]
            print(f"  - Node {node_id}: blacklisted {count} time(s)")
            
            # Show related trust updates
            related_trust = [e for e in events['trust_updates'] 
                           if e['node_id'] == node_id]
            if related_trust:
                print(f"    Trust updates: {len(related_trust)}")
                for t in related_trust[:3]:
                    print(f"      Line {t['line']}: trust={t['trust']}")
                if len(related_trust) > 3:
                    print(f"      ... ({len(related_trust) - 3} more)")
    
    if events['blacklist_removes']:
        print(f"\n[3] Blacklist Removals:")
        for evt in events['blacklist_removes'][:10]:
            print(f"  - Line {evt['line']}: Node {evt['node_id']} removed")
    
    if events['packet_drops']:
        print(f"\n[4] Packet Filtering:")
        drop_summary = defaultdict(lambda: {'dest': 0, 'src': 0})
        for evt in events['packet_drops']:
            if evt['type'] == 'DEST':
                drop_summary[evt['node_id']]['dest'] += 1
            else:
                drop_summary[evt['node_id']]['src'] += 1
        
        print(f"  Packets dropped by node:")
        for node_id in sorted(drop_summary.keys()):
            stats = drop_summary[node_id]
            total = stats['dest'] + stats['src']
            print(f"    Node {node_id}: {total} packets "
                  f"(dest={stats['dest']}, src={stats['src']})")
    
    # Check correlation between trust and blacklist
    print(f"\n[5] Trust-Blacklist Correlation:")
    low_trust_threshold = 700
    low_trust_nodes = set()
    for evt in events['trust_updates']:
        if evt['trust'] < low_trust_threshold:
            low_trust_nodes.add(evt['node_id'])
    
    blacklisted_nodes = set(evt['node_id'] for evt in events['blacklist_adds'])
    
    if low_trust_nodes and blacklisted_nodes:
        overlap = low_trust_nodes & blacklisted_nodes
        print(f"  - Nodes with trust < {low_trust_threshold}: {len(low_trust_nodes)}")
        print(f"  - Nodes blacklisted: {len(blacklisted_nodes)}")
        print(f"  - Overlap: {len(overlap)} nodes")
        
        if overlap:
            print(f"  - Correctly blacklisted: {list(sorted(overlap))}")
        
        # False positives (blacklisted but not low trust)
        false_pos = blacklisted_nodes - low_trust_nodes
        if false_pos:
            print(f"  - False positives: {list(sorted(false_pos))}")
        
        # False negatives (low trust but not blacklisted)
        false_neg = low_trust_nodes - blacklisted_nodes
        if false_neg:
            print(f"  - False negatives: {list(sorted(false_neg))}")
    else:
        if not events['trust_updates']:
            print(f"  ⚠️  No trust updates found in log")
            print(f"     Blacklist may not be triggered without external trust engine")
        elif not low_trust_nodes:
            print(f"  ✓  No nodes below trust threshold")
        else:
            print(f"  ⚠️  No blacklist events despite low trust nodes")
    
    # Effectiveness analysis
    if events['packet_drops']:
        print(f"\n[6] Effectiveness Analysis:")
        print(f"  - Total packets filtered: {len(events['packet_drops'])}")
        print(f"  - Filtering started working as intended")
        print(f"  ✅ Blacklist packet filtering is ACTIVE")
    else:
        if events['blacklist_adds']:
            print(f"\n[6] Effectiveness Analysis:")
            print(f"  ⚠️  Nodes were blacklisted but no packets were dropped")
            print(f"     This could mean:")
            print(f"     - No packets were routed through blacklisted nodes")
            print(f"     - Filtering logic needs verification")
        else:
            print(f"\n[6] Effectiveness Analysis:")
            print(f"  ℹ️  No blacklist activity detected")
            print(f"     All nodes maintained sufficient trust levels")
    
    print(f"\n" + "=" * 80)
    return events

def generate_test_recommendations(events):
    """Generate testing recommendations"""
    print("\n[7] Testing Recommendations:")
    
    if not events['trust_updates']:
        print("  1. Enable external trust engine to inject trust updates")
        print("  2. Use trust_engine tool with --threshold 300")
        print("  3. Verify serial input is working (check TRUST_IN logs)")
    
    if not events['blacklist_adds']:
        print("  1. Lower BLACKLIST_TRUST_THRESHOLD in brpl-blacklist.h")
        print("  2. Increase attack drop rate (ATTACK_DROP_PCT)")
        print("  3. Run longer simulations to observe trust degradation")
    
    if events['blacklist_adds'] and not events['packet_drops']:
        print("  1. Verify ip_output() hook is registered correctly")
        print("  2. Check if blacklisted nodes are actually in routing paths")
        print("  3. Enable LOG_LEVEL_DBG in blacklist module")
    
    print("\n[8] Usage Example:")
    print("  # With external trust engine:")
    print("  ./tools/trust_engine/target/release/trust_engine \\")
    print("    --mode file \\")
    print("    --input logs/COOJA.testlog \\")
    print("    --output logs/trust_updates.txt \\")
    print("    --threshold 300")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_blacklist.py <COOJA.testlog>")
        print("Example: python3 test_blacklist.py results/run-*/COOJA.testlog")
        sys.exit(1)
    
    log_file = sys.argv[1]
    events = analyze_blacklist_behavior(log_file)
    generate_test_recommendations(events)
