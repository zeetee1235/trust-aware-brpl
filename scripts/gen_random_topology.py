#!/usr/bin/env python3
"""
Generate a random Cooja .csc topology with 1 root, 1 attacker, N-2 senders.
Ensures each non-root node is within TX range of at least one earlier node.
"""

import argparse
import random
import sys


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outfile", required=True, help="Output .csc path")
    ap.add_argument("--mode", choices=["brpl", "mrhof"], default="brpl")
    ap.add_argument("--nodes", type=int, default=31, help="Total nodes (>=3)")
    ap.add_argument("--seed", type=int, default=123456)
    ap.add_argument("--area", type=float, default=200.0, help="Square side length (meters)")
    ap.add_argument("--root-x", type=float, default=0.0)
    ap.add_argument("--root-y", type=float, default=0.0)
    ap.add_argument("--tx-range", type=float, default=45.0)
    ap.add_argument("--int-range", type=float, default=90.0)
    ap.add_argument("--min-dist", type=float, default=5.0, help="Minimum distance between nodes")
    ap.add_argument("--attacker-id", type=int, default=3)
    ap.add_argument("--send-interval", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=120)
    ap.add_argument("--attack-drop", type=int, default=50)
    ap.add_argument("--attacker-x", type=float, default=None)
    ap.add_argument("--attacker-y", type=float, default=None)
    return ap.parse_args()


def dist2(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def place_nodes(n, rng, area, root_pos, tx_range, min_dist, fixed_positions):
    positions = {1: root_pos}
    if fixed_positions:
        positions.update(fixed_positions)
    tx2 = tx_range * tx_range
    min2 = min_dist * min_dist
    half = area / 2.0

    for node_id in range(2, n + 1):
        if node_id in positions:
            continue
        placed = False
        for _ in range(2000):
            x = root_pos[0] + rng.uniform(-half, half)
            y = root_pos[1] + rng.uniform(-half, half)
            cand = (x, y)

            # Keep min distance from all nodes
            if any(dist2(cand, p) < min2 for p in positions.values()):
                continue

            # Ensure connectivity to at least one existing node
            if any(dist2(cand, p) <= tx2 for p in positions.values()):
                positions[node_id] = cand
                placed = True
                break
        if not placed:
            return None
    return positions


def motetype_commands(mode, send_interval, warmup, attack_drop):
    if mode == "brpl":
        root_cmd = "make -C ../motes -f Makefile.receiver -j receiver_root.cooja TARGET=cooja DEFINES=BRPL_MODE=1"
        sender_cmd = (
            "make -C ../motes -f Makefile.sender -j sender.cooja TARGET=cooja "
            f"DEFINES=BRPL_MODE=1,SEND_INTERVAL_SECONDS={send_interval},WARMUP_SECONDS={warmup}"
        )
        attacker_cmd = (
            "make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja "
            f"DEFINES=BRPL_MODE=1,ATTACK_DROP_PCT={attack_drop},WARMUP_SECONDS={warmup}"
        )
    else:
        root_cmd = "make -C ../motes -f Makefile.receiver -j receiver_root.cooja TARGET=cooja"
        sender_cmd = (
            "make -C ../motes -f Makefile.sender -j sender.cooja TARGET=cooja "
            f"DEFINES=SEND_INTERVAL_SECONDS={send_interval},WARMUP_SECONDS={warmup}"
        )
        attacker_cmd = (
            "make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja "
            f"DEFINES=ATTACK_DROP_PCT={attack_drop},WARMUP_SECONDS={warmup}"
        )
    return root_cmd, sender_cmd, attacker_cmd


def write_csc(args, positions):
    title = "Trust-Aware BRPL Simulation (Random)" if args.mode == "brpl" else "RPL MRHOF Simulation (Random)"
    root_cmd, sender_cmd, attacker_cmd = motetype_commands(
        args.mode, args.send_interval, args.warmup, args.attack_drop
    )

    def mote_block(node_id, pos, mote_type):
        return f"""    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>{pos[0]:.2f}</x>
        <y>{pos[1]:.2f}</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>{node_id}</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>{mote_type}</motetype_identifier>
    </mote>
"""

    motes_xml = []
    for node_id in range(1, args.nodes + 1):
        pos = positions[node_id]
        if node_id == 1:
            motes_xml.append(f"    <!-- Node {node_id}: Root -->\n" + mote_block(node_id, pos, "root_type"))
        elif node_id == args.attacker_id:
            motes_xml.append(f"    <!-- Node {node_id}: Attacker -->\n" + mote_block(node_id, pos, "attacker_type"))
        else:
            motes_xml.append(f"    <!-- Node {node_id}: Sender -->\n" + mote_block(node_id, pos, "sender_type"))

    out = f"""<?xml version="1.0" encoding="UTF-8"?>
<simconf>
  <simulation>
    <title>{title}</title>
    <randomseed>{args.seed}</randomseed>
    <motedelay_us>1000000</motedelay_us>
    <radiomedium>
      org.contikios.cooja.radiomediums.UDGM
      <transmitting_range>{args.tx_range:.1f}</transmitting_range>
      <interference_range>{args.int_range:.1f}</interference_range>
      <success_ratio_tx>1.0</success_ratio_tx>
      <success_ratio_rx>1.0</success_ratio_rx>
    </radiomedium>
    <events>
      <logoutput>40000</logoutput>
    </events>
    <motetype>
      org.contikios.cooja.contikimote.ContikiMoteType
      <identifier>root_type</identifier>
      <description>Root Node</description>
      <source>[CONFIG_DIR]/../motes/receiver_root.c</source>
      <commands>{root_cmd}</commands>
      <moteinterface>org.contikios.cooja.interfaces.Position</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Battery</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiVib</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiMoteID</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRS232</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiBeeper</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.RimeAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiIPAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRadio</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiButton</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiPIR</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiClock</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiLED</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiCFS</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiEEPROM</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Mote2MoteRelations</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.MoteAttributes</moteinterface>
    </motetype>
    <motetype>
      org.contikios.cooja.contikimote.ContikiMoteType
      <identifier>sender_type</identifier>
      <description>Sender Node</description>
      <source>[CONFIG_DIR]/../motes/sender.c</source>
      <commands>{sender_cmd}</commands>
      <moteinterface>org.contikios.cooja.interfaces.Position</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Battery</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiVib</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiMoteID</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRS232</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiBeeper</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.RimeAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiIPAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRadio</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiButton</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiPIR</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiClock</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiLED</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiCFS</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiEEPROM</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Mote2MoteRelations</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.MoteAttributes</moteinterface>
    </motetype>
    <motetype>
      org.contikios.cooja.contikimote.ContikiMoteType
      <identifier>attacker_type</identifier>
      <description>Selective Forwarding Attacker</description>
      <source>[CONFIG_DIR]/../motes/attacker.c</source>
      <commands>{attacker_cmd}</commands>
      <moteinterface>org.contikios.cooja.interfaces.Position</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Battery</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiVib</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiMoteID</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRS232</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiBeeper</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.RimeAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiIPAddress</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiRadio</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiButton</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiPIR</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiClock</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiLED</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiCFS</moteinterface>
      <moteinterface>org.contikios.cooja.contikimote.interfaces.ContikiEEPROM</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.Mote2MoteRelations</moteinterface>
      <moteinterface>org.contikios.cooja.interfaces.MoteAttributes</moteinterface>
    </motetype>
{''.join(motes_xml)}  </simulation>
  <plugin>
    org.contikios.cooja.plugins.SimControl
    <width>280</width>
    <z>4</z>
    <height>160</height>
    <location_x>400</location_x>
    <location_y>0</location_y>
  </plugin>
  <plugin>
    org.contikios.cooja.plugins.ScriptRunner
    <plugin_config>
      <script>// Auto-generated Cooja script
TIMEOUT(@SIM_TIME_MS@, log.log("SIMULATION_FINISHED\\n"); log.testOK(); );
log.log("Headless simulation started\\n");
log.log("Duration: @SIM_TIME_SEC@s\\n");
log.log("Nodes: " + sim.getMotesCount() + "\\n");
while(true) {{
  YIELD();
  if(msg != null) {{
    log.log(msg + "\\n");
  }}
}}
</script>
    </plugin_config>
  </plugin>
  <plugin>
    org.contikios.cooja.plugins.LogListener
    <plugin_config>
      <filter />
      <formatted_time />
      <coloring />
    </plugin_config>
    <width>1179</width>
    <z>0</z>
    <height>704</height>
    <location_x>679</location_x>
    <location_y>0</location_y>
  </plugin>
</simconf>
"""

    with open(args.outfile, "w", encoding="utf-8") as f:
        f.write(out)


def main():
    args = parse_args()
    if args.nodes < 3:
        print("nodes must be >= 3", file=sys.stderr)
        sys.exit(1)
    if args.attacker_id == 1 or args.attacker_id > args.nodes:
        print("attacker-id must be between 2 and nodes", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    fixed_positions = {}
    if args.attacker_x is not None and args.attacker_y is not None:
        ax, ay = args.attacker_x, args.attacker_y
        if dist2((ax, ay), (args.root_x, args.root_y)) < (args.min_dist * args.min_dist):
            print("attacker too close to root (min-dist violation)", file=sys.stderr)
            sys.exit(1)
        fixed_positions[args.attacker_id] = (ax, ay)
        # Ensure attacker is within range of at least one existing node (root)
        if dist2((ax, ay), (args.root_x, args.root_y)) > (args.tx_range * args.tx_range):
            print("attacker is out of TX range from root; may create disconnected topology", file=sys.stderr)
            sys.exit(1)

    positions = place_nodes(
        args.nodes,
        rng,
        args.area,
        (args.root_x, args.root_y),
        args.tx_range,
        args.min_dist,
        fixed_positions,
    )
    if positions is None:
        print("Failed to place nodes with given constraints. Try larger area or smaller min-dist.", file=sys.stderr)
        sys.exit(1)

    write_csc(args, positions)


if __name__ == "__main__":
    main()
