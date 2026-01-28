#!/usr/bin/env python3
"""
Trust-based Parent Selection Validation Script
Verifies that nodes with trust < TRUST_PARENT_MIN are not selected as parents
"""

import sys
import re
from collections import defaultdict

def parse_trust_log(log_file, trust_min=700):
    """Parse trust values from log and identify low-trust nodes"""
    trust_values = defaultdict(list)
    low_trust_periods = defaultdict(list)
    
    with open(log_file, 'r') as f:
        for line in f:
            # Parse: CSV,TRUST,<node>,<seq>,<missed>,<trust>
            match = re.search(r'CSV,TRUST,(\d+),(\d+),(\d+),(\d+)', line)
            if match:
                node_id = int(match.group(1))
                seq = int(match.group(2))
                trust = int(match.group(4))
                trust_values[node_id].append((seq, trust))
                
                if trust < trust_min:
                    low_trust_periods[node_id].append((seq, trust))
    
    return trust_values, low_trust_periods

def parse_parent_selection(log_file):
    """Parse parent selection from log"""
    parent_selections = []
    
    with open(log_file, 'r') as f:
        for line in f:
            # Parse: CSV,PARENT,<node>,<parent_ip>
            match = re.search(r'CSV,PARENT,(\d+),(fe80::201:1:1:(\w+)|none)', line)
            if match:
                node_id = int(match.group(1))
                parent_ip = match.group(2)
                
                if parent_ip != 'none':
                    # Extract last byte of IPv6 address (node ID in hex)
                    parent_hex = match.group(3)
                    parent_node_id = int(parent_hex, 16)
                    parent_selections.append((node_id, parent_node_id))
    
    return parent_selections

def validate_trust_parent_exclusion(log_file, trust_min=700):
    """Validate that low-trust nodes are not selected as parents"""
    print(f"=" * 80)
    print(f"Trust-based Parent Selection Validation")
    print(f"Log file: {log_file}")
    print(f"TRUST_PARENT_MIN: {trust_min}")
    print(f"=" * 80)
    
    # Parse trust values
    trust_values, low_trust_periods = parse_trust_log(log_file, trust_min)
    
    print(f"\n[1] Trust Statistics:")
    print(f"  - Total nodes with trust values: {len(trust_values)}")
    print(f"  - Nodes with low trust (<{trust_min}): {len(low_trust_periods)}")
    
    if low_trust_periods:
        print(f"\n[2] Low Trust Nodes:")
        for node_id in sorted(low_trust_periods.keys()):
            periods = low_trust_periods[node_id]
            min_trust = min(t for _, t in periods)
            print(f"  - Node {node_id}: {len(periods)} occurrences, min trust = {min_trust}")
            # Show first and last few occurrences
            if len(periods) <= 5:
                for seq, trust in periods:
                    print(f"      seq {seq}: trust = {trust}")
            else:
                for seq, trust in periods[:3]:
                    print(f"      seq {seq}: trust = {trust}")
                print(f"      ... ({len(periods) - 5} more)")
                for seq, trust in periods[-2:]:
                    print(f"      seq {seq}: trust = {trust}")
    
    # Parse parent selections
    parent_selections = parse_parent_selection(log_file)
    
    print(f"\n[3] Parent Selection Analysis:")
    print(f"  - Total parent selections logged: {len(parent_selections)}")
    
    # Check if any low-trust node was selected as parent
    violations = []
    low_trust_nodes = set(low_trust_periods.keys())
    
    for child_node, parent_node in parent_selections:
        if parent_node in low_trust_nodes:
            violations.append((child_node, parent_node))
    
    if violations:
        print(f"\n[4] ⚠️  VIOLATIONS FOUND: {len(violations)}")
        print(f"  Low-trust nodes were selected as parents:")
        violation_summary = defaultdict(int)
        for child, parent in violations:
            violation_summary[parent] += 1
        
        for parent_node in sorted(violation_summary.keys()):
            count = violation_summary[parent_node]
            min_trust = min(t for _, t in low_trust_periods[parent_node])
            print(f"  - Node {parent_node} (min trust={min_trust}): selected {count} times")
    else:
        print(f"\n[4] ✅ VALIDATION PASSED")
        print(f"  No low-trust nodes were selected as parents!")
    
    # Additional analysis: show trust distribution
    print(f"\n[5] Trust Value Distribution:")
    all_trust_values = []
    for node_id, values in trust_values.items():
        for seq, trust in values:
            all_trust_values.append(trust)
    
    if all_trust_values:
        all_trust_values.sort()
        print(f"  - Min: {min(all_trust_values)}")
        print(f"  - 25th percentile: {all_trust_values[len(all_trust_values)//4]}")
        print(f"  - Median: {all_trust_values[len(all_trust_values)//2]}")
        print(f"  - 75th percentile: {all_trust_values[3*len(all_trust_values)//4]}")
        print(f"  - Max: {max(all_trust_values)}")
        print(f"  - Below {trust_min}: {sum(1 for t in all_trust_values if t < trust_min)} / {len(all_trust_values)}")
    
    print(f"\n" + "=" * 80)
    return len(violations) == 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <COOJA.testlog> [trust_min]")
        print(f"Example: {sys.argv[0]} results/run-*/COOJA.testlog 700")
        sys.exit(1)
    
    log_file = sys.argv[1]
    trust_min = int(sys.argv[2]) if len(sys.argv) > 2 else 700
    
    passed = validate_trust_parent_exclusion(log_file, trust_min)
    sys.exit(0 if passed else 1)
