#!/usr/bin/env python3
"""
Cooja JVM Crash Analysis and Mitigation Tool
분석된 크래시 원인과 해결 방법을 제공
"""

import sys
import re
from pathlib import Path

def analyze_crash_log(log_path):
    """JVM 크래시 로그 분석"""
    print("=" * 80)
    print("Cooja JVM Crash Analysis")
    print("=" * 80)
    
    if not Path(log_path).exists():
        print(f"Error: Log file not found: {log_path}")
        return None
    
    with open(log_path, 'r') as f:
        content = f.read()
    
    results = {
        'crash_type': None,
        'problematic_frame': None,
        'signal': None,
        'thread': None,
        'recommendations': []
    }
    
    # Extract crash information
    signal_match = re.search(r'(SIGSEGV|SIGABRT|SIGILL)\s+\(0x[0-9a-f]+\)', content)
    if signal_match:
        results['signal'] = signal_match.group(1)
    
    frame_match = re.search(r'Problematic frame:\s*\n#\s*([^\n]+)', content)
    if frame_match:
        results['problematic_frame'] = frame_match.group(1).strip()
    
    thread_match = re.search(r'Current thread.*?JavaThread "([^"]+)"', content)
    if thread_match:
        results['thread'] = thread_match.group(1)
    
    # Analyze specific issues
    print(f"\n[1] Crash Summary:")
    print(f"  Signal: {results['signal']}")
    print(f"  Thread: {results['thread']}")
    print(f"  Frame:  {results['problematic_frame']}")
    
    print(f"\n[2] Root Cause Analysis:")
    
    if 'doInterfaceActionsBeforeTick' in content:
        print(f"  ⚠️  Crash in doInterfaceActionsBeforeTick()")
        print(f"     This is a known issue in Contiki-NG mote interface handling")
        results['crash_type'] = 'interface_action'
        results['recommendations'].extend([
            "Reduce number of active mote interfaces",
            "Disable unused plugins (e.g., SerialSocketServer)",
            "Use --enable-native-access=ALL-UNNAMED flag",
            "Update to latest Contiki-NG version"
        ])
    
    if 'OutOfMemory' in content or 'GC overhead' in content:
        print(f"  ⚠️  Memory exhaustion detected")
        results['crash_type'] = 'memory'
        results['recommendations'].extend([
            "Increase JVM heap size: -Xmx4G or higher",
            "Reduce simulation time or number of nodes",
            "Enable GC logging: -Xlog:gc*"
        ])
    
    if 'SEGV_ACCERR' in content:
        print(f"  ⚠️  Memory access violation (SEGV_ACCERR)")
        print(f"     Native code tried to access protected memory")
        results['recommendations'].extend([
            "Check for corrupted .cooja binaries (rebuild motes)",
            "Verify simulation configuration for invalid parameters"
        ])
    
    if results['crash_type'] == 'interface_action':
        print(f"\n     Known Issue Details:")
        print(f"     - Contiki-NG's native library may have race conditions")
        print(f"     - More frequent with multiple mote types or interfaces")
        print(f"     - SerialSocketServer plugin can cause instability in headless mode")
    
    return results

def generate_mitigation_script(results):
    """크래시 완화를 위한 스크립트 생성"""
    print(f"\n[3] Mitigation Strategies:")
    
    for i, rec in enumerate(results['recommendations'], 1):
        print(f"  {i}. {rec}")
    
    print(f"\n[4] Recommended Configuration Changes:")
    print(f"\n  A) Update run_simulation.sh to disable SerialSocketServer:")
    print(f"     export SERIAL_SOCKET_DISABLE=1")
    print(f"     ./scripts/run_simulation.sh")
    
    print(f"\n  B) Increase JVM heap size:")
    print(f"     Edit run_simulation.sh, add before java command:")
    print(f"     export JAVA_OPTS=\"-Xmx4G -Xms2G\"")
    print(f"     java $JAVA_OPTS --enable-preview ...")
    
    print(f"\n  C) Enable native access warnings suppression:")
    print(f"     java --enable-preview --enable-native-access=ALL-UNNAMED ...")
    
    print(f"\n  D) Rebuild mote binaries:")
    print(f"     make -C motes clean")
    print(f"     make -C motes -f Makefile.receiver TARGET=cooja")
    print(f"     make -C motes -f Makefile.sender TARGET=cooja")
    print(f"     make -C motes -f Makefile.attacker TARGET=cooja")
    
    print(f"\n[5] Workaround for Immediate Use:")
    print(f"  - Run simulations with shorter duration (e.g., 300s instead of 600s)")
    print(f"  - Reduce number of nodes in topology")
    print(f"  - Split batch runs into smaller chunks")
    print(f"  - Use --nologfile option if log files are too large")

def create_fixed_run_script():
    """크래시 완화가 적용된 run 스크립트 생성"""
    script_content = """#!/bin/bash
# Cooja 시뮬레이션 (JVM 크래시 완화 버전)
set -e

# JVM 메모리 설정
export JAVA_OPTS="-Xmx4G -Xms2G"

# SerialSocketServer 비활성화 (headless 모드 안정성)
export SERIAL_SOCKET_DISABLE=1

# Native access 경고 억제
JAVA_NATIVE_ACCESS="--enable-native-access=ALL-UNNAMED"

# 기존 run_simulation.sh 호출
exec "$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/run_simulation.sh" "$@"
"""
    
    output_path = Path("scripts/run_simulation_stable.sh")
    output_path.write_text(script_content)
    output_path.chmod(0o755)
    
    print(f"\n[6] Generated Stable Script:")
    print(f"  Created: {output_path}")
    print(f"  Usage: ./scripts/run_simulation_stable.sh [sim_time] [csc_file]")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_cooja_crash.py <hs_err_pid*.log or cooja_output.log>")
        print("\nSearching for recent crash logs...")
        
        # Search for recent crash logs
        tmp_logs = list(Path("/tmp").glob("hs_err_pid*.log"))
        if tmp_logs:
            latest = max(tmp_logs, key=lambda p: p.stat().st_mtime)
            print(f"Found: {latest}")
            log_path = latest
        else:
            print("No crash logs found in /tmp")
            print("Check logs/cooja_output.log for errors")
            sys.exit(1)
    else:
        log_path = sys.argv[1]
    
    results = analyze_crash_log(log_path)
    
    if results:
        generate_mitigation_script(results)
        
        # Generate fixed script
        if results['crash_type'] == 'interface_action':
            create_fixed_run_script()
        
        print(f"\n" + "=" * 80)
        print(f"Analysis complete. Apply recommended changes to reduce crash frequency.")
        print(f"=" * 80)

if __name__ == "__main__":
    main()
