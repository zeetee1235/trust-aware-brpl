#!/usr/bin/env python3
"""
Generate fixed 100x100m topologies for TA-BRPL experiments.

Topology mapping:
  - CLUSTER_{S,M,L}: Chokepoint 2-Cluster (N=20/40/60)
  - GRID_{S,M,L}:    Depth Gradient (N=20/40/60)
  - RING_{S,M,L}:    Ring (N=20/40/60)

Node IDs are normalized as:
  1 = root, 2 = attacker, 3..N = relay/sender.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import math
from collections import deque


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOPO_DIR = PROJECT_ROOT / "configs" / "topologies"

TX_RANGE = 21.0
INT_RANGE = 42.0
MAX_ROOT_DIRECT_RATIO = 0.30
SEND_INTERVAL = 30
WARMUP = 120
ATTACK_DROP = 50


@dataclass
class TopologySpec:
    name: str
    root: Tuple[float, float]
    attacker: Tuple[float, float]
    relays: Sequence[Tuple[float, float]]
    senders: Sequence[Tuple[float, float]]
    expected_nodes: int
    title: str


def build_nodes(spec: TopologySpec) -> List[Tuple[int, float, float, str]]:
    nodes: List[Tuple[int, float, float, str]] = []
    nodes.append((1, spec.root[0], spec.root[1], "root"))
    nodes.append((2, spec.attacker[0], spec.attacker[1], "attacker"))
    next_id = 3

    for x, y in spec.relays:
        nodes.append((next_id, x, y, "relay"))
        next_id += 1

    for x, y in spec.senders:
        nodes.append((next_id, x, y, "sender"))
        next_id += 1

    if len(nodes) != spec.expected_nodes:
        raise ValueError(
            f"{spec.name}: expected {spec.expected_nodes} nodes, got {len(nodes)}"
        )
    return nodes


def validate_topology_connectivity_and_depth(spec: TopologySpec, nodes: Sequence[Tuple[int, float, float, str]]) -> None:
    pos = {node_id: (x, y) for node_id, x, y, _ in nodes}
    node_ids = sorted(pos.keys())

    graph: Dict[int, List[int]] = {nid: [] for nid in node_ids}
    for i, a in enumerate(node_ids):
        ax, ay = pos[a]
        for b in node_ids[i + 1:]:
            bx, by = pos[b]
            if math.hypot(ax - bx, ay - by) <= TX_RANGE:
                graph[a].append(b)
                graph[b].append(a)

    # Connectivity from root (node 1)
    visited = {1}
    q = deque([1])
    while q:
        u = q.popleft()
        for v in graph[u]:
            if v not in visited:
                visited.add(v)
                q.append(v)
    if len(visited) != len(node_ids):
        raise ValueError(f"{spec.name}: disconnected topology for TX_RANGE={TX_RANGE}")

    # Direct-to-root ratio among non-root motes
    root_x, root_y = pos[1]
    direct = 0
    for nid in node_ids:
        if nid == 1:
            continue
        x, y = pos[nid]
        if math.hypot(x - root_x, y - root_y) <= TX_RANGE:
            direct += 1
    ratio = direct / (len(node_ids) - 1)
    if ratio > MAX_ROOT_DIRECT_RATIO:
        raise ValueError(
            f"{spec.name}: too many direct-root neighbors "
            f"({direct}/{len(node_ids)-1}={ratio:.1%}) > {MAX_ROOT_DIRECT_RATIO:.0%}"
        )


def write_csv(path: Path, nodes: Sequence[Tuple[int, float, float, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("node_id,x,y,role\n")
        for node_id, x, y, role in nodes:
            f.write(f"{node_id},{x:.2f},{y:.2f},{role}\n")


def motetype_commands() -> Tuple[str, str, str, str]:
    root_cmd = (
        "/usr/bin/make -C ../motes -f Makefile.receiver -j receiver_root.cooja TARGET=cooja WERROR=0 "
        "DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        "TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,PROJECT_CONF_PATH=../project-conf.h"
    )
    sender_cmd = (
        "/usr/bin/make -C ../motes -f Makefile.sender -j sender.cooja TARGET=cooja WERROR=0 "
        f"DEFINES=BRPL_MODE=1,TRUST_ENABLED=0,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        f"TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        f"SEND_INTERVAL_SECONDS={SEND_INTERVAL},WARMUP_SECONDS={WARMUP}"
    )
    attacker_cmd = (
        "/usr/bin/make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 "
        f"DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        f"TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        f"ATTACK_DROP_PCT={ATTACK_DROP},WARMUP_SECONDS={WARMUP}"
    )
    relay_cmd = (
        "/usr/bin/make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 "
        "DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        "TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        "ATTACK_DROP_PCT=0,WARMUP_SECONDS=0,ATTACK_WARMUP_SECONDS=0"
    )
    return root_cmd, sender_cmd, attacker_cmd, relay_cmd


def mote_block(node_id: int, x: float, y: float, mote_type: str) -> str:
    return f"""    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>{x:.2f}</x>
        <y>{y:.2f}</y>
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


def write_csc(path: Path, spec: TopologySpec, nodes: Sequence[Tuple[int, float, float, str]]) -> None:
    root_cmd, sender_cmd, attacker_cmd, relay_cmd = motetype_commands()
    has_relay = any(role == "relay" for _, _, _, role in nodes)

    relay_motetype = ""
    if has_relay:
        relay_motetype = f"""    <motetype>
      org.contikios.cooja.contikimote.ContikiMoteType
      <identifier>relay_type</identifier>
      <description>Relay Node (No Attack)</description>
      <source>[CONFIG_DIR]/../motes/attacker.c</source>
      <commands>{relay_cmd}</commands>
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
"""

    mote_xml: List[str] = []
    for node_id, x, y, role in nodes:
        if role == "root":
            mote_xml.append(f"    <!-- Node {node_id}: Root -->\n" + mote_block(node_id, x, y, "root_type"))
        elif role == "attacker":
            mote_xml.append(f"    <!-- Node {node_id}: Attacker -->\n" + mote_block(node_id, x, y, "attacker_type"))
        elif role == "relay":
            mote_xml.append(f"    <!-- Node {node_id}: Relay -->\n" + mote_block(node_id, x, y, "relay_type"))
        else:
            mote_xml.append(f"    <!-- Node {node_id}: Sender -->\n" + mote_block(node_id, x, y, "sender_type"))

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<simconf>
  <simulation>
    <title>{spec.title}</title>
    <randomseed>123456</randomseed>
    <motedelay_us>1000000</motedelay_us>
    <radiomedium>
      org.contikios.cooja.radiomediums.UDGM
      <transmitting_range>{TX_RANGE:.1f}</transmitting_range>
      <interference_range>{INT_RANGE:.1f}</interference_range>
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
{relay_motetype}{''.join(mote_xml)}  </simulation>
  <plugin>
    org.contikios.cooja.plugins.SimControl
    <width>280</width>
    <z>4</z>
    <height>160</height>
    <location_x>400</location_x>
    <location_y>0</location_y>
  </plugin>
  <plugin>
    org.contikios.cooja.serialsocket.SerialSocketServer
    <mote_arg>0</mote_arg>
    <plugin_config>
      <port>60001</port>
      <bound>true</bound>
    </plugin_config>
    <width>360</width>
    <z>3</z>
    <height>120</height>
    <location_x>20</location_x>
    <location_y>400</location_y>
  </plugin>
  <plugin>
    org.contikios.cooja.plugins.ScriptRunner
    <plugin_config>
      <script><![CDATA[
// Auto-generated Cooja script
TIMEOUT(@SIM_TIME_MS@, log.log("SIMULATION_FINISHED\\n"); log.testOK(); );
log.log("Headless simulation started\\n");
log.log("Duration: @SIM_TIME_SEC@s\\n");
log.log("Nodes: " + sim.getMotesCount() + "\\n");
var trustFile = "@TRUST_FEEDBACK_PATH@";
var lastCheckMs = 0;
var lastPos = 0;
function pollTrust() {{
  try {{
    var file = new java.io.File(trustFile);
    if(!file.exists()) {{
      return;
    }}
    var raf = new java.io.RandomAccessFile(file, "r");
    raf.seek(lastPos);
    var line;
    while((line = raf.readLine()) != null) {{
      line = String(line).trim();
      if(line.length() == 0) {{
        continue;
      }}
      var parts = line.split(",");
      if(parts.length < 3) {{
        continue;
      }}
      if(parts[0] != "TRUST") {{
        continue;
      }}
      var node = parts[1];
      var trust = parts[2];
      var cmd = "TRUST," + node + "," + trust + "\\n";
      for(var i = 0; i < sim.getMotesCount(); i++) {{
        var mote = sim.getMote(i);
        try {{
          mote.getInterfaces().getLog().writeString(cmd);
        }} catch (e) {{
        }}
      }}
      log.log("INJECT " + cmd);
    }}
    lastPos = raf.getFilePointer();
    raf.close();
  }} catch (e) {{
  }}
}}
while(true) {{
  YIELD();
  if(msg != null) {{
    log.log(msg + "\\n");
  }}
  var now = java.lang.System.currentTimeMillis();
  if(now - lastCheckMs > 200) {{
    pollTrust();
    lastCheckMs = now;
  }}
}}
]]></script>
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
    path.write_text(xml, encoding="utf-8")


def topology_specs() -> Dict[str, TopologySpec]:
    return {
        # 1) Chokepoint 2-Cluster
        "CLUSTER_S": TopologySpec(
            name="CLUSTER_S",
            root=(10, 50),
            attacker=(44, 50),
            relays=[(52, 42), (52, 58)],
            senders=[
                (20, 40), (20, 50), (20, 60), (30, 45), (30, 55), (25, 35), (25, 65),
                (58, 44), (58, 56), (66, 50), (72, 40), (72, 60), (80, 45), (80, 55), (88, 40), (88, 60),
            ],
            expected_nodes=20,
            title="CHOKEPOINT 2-CLUSTER S (N=20)",
        ),
        "CLUSTER_M": TopologySpec(
            name="CLUSTER_M",
            root=(10, 50),
            attacker=(44, 50),
            relays=[(52, 42), (52, 58)],
            senders=[
                (18, 35), (18, 45), (18, 55), (18, 65),
                (25, 30), (25, 40), (25, 50), (25, 60), (25, 70),
                (32, 35), (32, 45), (32, 55), (32, 65),
                (28, 20), (28, 80), (35, 50),
                (58, 38), (58, 50), (58, 62),
                (64, 30), (64, 40), (64, 50), (64, 60), (64, 70),
                (72, 25), (72, 35), (72, 45), (72, 55), (72, 65), (72, 75),
                (80, 30), (80, 40), (80, 50), (80, 60), (80, 70),
                (88, 50),
            ],
            expected_nodes=40,
            title="CHOKEPOINT 2-CLUSTER M (N=40)",
        ),
        "CLUSTER_L": TopologySpec(
            name="CLUSTER_L",
            root=(10, 50),
            attacker=(44, 50),
            relays=[(52, 42), (52, 58)],
            senders=[
                (16, 30), (16, 40), (16, 50), (16, 60), (16, 70),
                (22, 25), (22, 35), (22, 45), (22, 55), (22, 65), (22, 75),
                (28, 20), (28, 30), (28, 40), (28, 50), (28, 60), (28, 70), (28, 80),
                (34, 25), (34, 35), (34, 45), (34, 55), (34, 65), (34, 75),
                (30, 50), (35, 50),
                (58, 30), (58, 40), (58, 50), (58, 60), (58, 70),
                (64, 20), (64, 30), (64, 40), (64, 50), (64, 60), (64, 70), (64, 80),
                (72, 20), (72, 30), (72, 40), (72, 50), (72, 60), (72, 70), (72, 80),
                (80, 20), (80, 30), (80, 40), (80, 50), (80, 60), (80, 70), (80, 80),
                (88, 35), (88, 50), (88, 65), (92, 50),
            ],
            expected_nodes=60,
            title="CHOKEPOINT 2-CLUSTER L (N=60)",
        ),
        # 2) Depth Gradient
        "GRID_S": TopologySpec(
            name="GRID_S",
            root=(10, 50),
            attacker=(55, 50),
            relays=[],
            senders=[
                (25, 30), (25, 40), (25, 50), (25, 60), (25, 70),
                (40, 30), (40, 40), (40, 50), (40, 60), (40, 70),
                (55, 35), (55, 45), (55, 65),
                (70, 40), (70, 60), (70, 50),
                (85, 45), (85, 55),
            ],
            expected_nodes=20,
            title="DEPTH GRADIENT S (N=20)",
        ),
        "GRID_M": TopologySpec(
            name="GRID_M",
            root=(10, 50),
            attacker=(60, 50),
            relays=[],
            senders=[
                (22, 20), (22, 30), (22, 40), (22, 50), (22, 60), (22, 70), (22, 80), (22, 35),
                (35, 20), (35, 30), (35, 40), (35, 50), (35, 60), (35, 70), (35, 80), (35, 35), (35, 65),
                (48, 20), (48, 30), (48, 40), (48, 50), (48, 60), (48, 70), (48, 80), (48, 35), (48, 65),
                (60, 25), (60, 35), (60, 45), (60, 55), (60, 65), (60, 75),
                (72, 35), (72, 50), (72, 65), (72, 80),
                (85, 45), (85, 60),
            ],
            expected_nodes=40,
            title="DEPTH GRADIENT M (N=40)",
        ),
        "GRID_L": TopologySpec(
            name="GRID_L",
            root=(10, 50),
            attacker=(62, 50),
            relays=[],
            senders=[
                (20, 15), (20, 25), (20, 35), (20, 45), (20, 55), (20, 65), (20, 75), (20, 85),
                (20, 40), (20, 50), (20, 60), (20, 70),
                (32, 15), (32, 25), (32, 35), (32, 45), (32, 55), (32, 65), (32, 75), (32, 85),
                (32, 40), (32, 50), (32, 60), (32, 70),
                (44, 15), (44, 25), (44, 35), (44, 45), (44, 55), (44, 65), (44, 75), (44, 85),
                (44, 40), (44, 50), (44, 60), (44, 70),
                (56, 15), (56, 25), (56, 35), (56, 45), (56, 55), (56, 65), (56, 75), (56, 85),
                (56, 40), (56, 50), (56, 60), (56, 70),
                (62, 25), (62, 35), (62, 45), (62, 55), (62, 65), (62, 75),
                (74, 40), (74, 55), (74, 70),
                (86, 55),
            ],
            expected_nodes=60,
            title="DEPTH GRADIENT L (N=60)",
        ),
        # 3) Ring
        "RING_S": TopologySpec(
            name="RING_S",
            root=(85, 50),
            attacker=(15, 50),
            relays=[],
            senders=[
                (82, 63), (75, 75), (63, 82), (50, 85), (37, 82),
                (25, 75), (18, 63), (18, 37), (25, 25), (37, 18),
                (50, 15), (63, 18), (75, 25), (82, 37), (67, 50),
                (50, 50), (45, 55), (55, 45),
            ],
            expected_nodes=20,
            title="RING S (N=20)",
        ),
        "RING_M": TopologySpec(
            name="RING_M",
            root=(85, 50),
            attacker=(15, 50),
            relays=[],
            senders=[
                (82, 60), (78, 70), (70, 78), (60, 82), (50, 85), (40, 82), (30, 78),
                (22, 70), (18, 60), (18, 40), (22, 30), (30, 22), (40, 18), (50, 15),
                (60, 18), (70, 22), (78, 30), (82, 40), (67, 50), (75, 50), (63, 63),
                (63, 37), (37, 63), (37, 37), (55, 67), (45, 67), (55, 33), (45, 33),
                (50, 50), (45, 55), (55, 45), (55, 55), (45, 45),
                (50, 60), (50, 40), (40, 50), (60, 50), (50, 70),
            ],
            expected_nodes=40,
            title="RING M (N=40)",
        ),
        "RING_L": TopologySpec(
            name="RING_L",
            root=(85, 50),
            attacker=(15, 50),
            relays=[],
            senders=[
                (84, 56), (82, 63), (78, 70), (73, 76), (67, 80), (60, 82), (53, 84), (50, 85),
                (47, 84), (40, 82), (33, 80), (27, 76), (22, 70), (18, 63), (16, 56), (16, 44),
                (18, 37), (22, 30), (27, 24), (33, 20), (40, 18), (47, 16), (50, 15), (53, 16),
                (60, 18), (67, 20), (73, 24), (78, 30), (82, 37), (84, 44), (75, 55), (75, 45),
                (65, 65), (65, 35), (35, 65), (35, 35),
                (50, 50), (45, 55), (55, 45), (55, 55), (45, 45),
                (50, 60), (50, 40), (40, 50), (60, 50),
                (42, 60), (58, 60), (42, 40), (58, 40),
                (50, 70), (50, 30), (30, 50), (70, 50),
                (40, 65), (60, 65), (40, 35), (60, 35), (55, 65),
            ],
            expected_nodes=60,
            title="RING L (N=60)",
        ),
    }


def main() -> None:
    TOPO_DIR.mkdir(parents=True, exist_ok=True)
    specs = topology_specs()
    for name, spec in specs.items():
        nodes = build_nodes(spec)
        validate_topology_connectivity_and_depth(spec, nodes)
        write_csv(TOPO_DIR / f"{name}.csv", nodes)
        write_csc(TOPO_DIR / f"{name}.csc", spec, nodes)
        print(f"generated: {name} ({len(nodes)} nodes)")


if __name__ == "__main__":
    main()
