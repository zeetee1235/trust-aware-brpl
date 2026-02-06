#!/usr/bin/env python3
"""
Generate a Cooja .csc topology from explicit node positions (no randomness).
Input file format (CSV):
  node_id,x,y,role
  1,0,0,root
  2,20,0,relay
  3,40,0,attacker
  4,60,0,sender

Roles: root, attacker, sender, relay (relay uses attacker code with drop=0)
Lines starting with # are ignored. Header line is optional.
"""

import argparse
import sys


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outfile", required=True, help="Output .csc path")
    ap.add_argument("--positions", required=True, help="CSV with node positions and roles")
    ap.add_argument("--mode", choices=["brpl"], default="brpl")
    ap.add_argument("--tx-range", type=float, default=45.0)
    ap.add_argument("--int-range", type=float, default=90.0)
    ap.add_argument("--send-interval", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=120)
    ap.add_argument("--attack-drop", type=int, default=50)
    ap.add_argument("--title", default=None)
    return ap.parse_args()


def motetype_commands(send_interval, warmup, attack_drop):
    root_cmd = (
        "make -C ../motes -f Makefile.receiver -j receiver_root.cooja TARGET=cooja WERROR=0 "
        "DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        "TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,PROJECT_CONF_PATH=../project-conf.h"
    )
    sender_cmd = (
        "make -C ../motes -f Makefile.sender -j sender.cooja TARGET=cooja WERROR=0 "
        f"DEFINES=BRPL_MODE=1,TRUST_ENABLED=0,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        f"TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        f"SEND_INTERVAL_SECONDS={send_interval},WARMUP_SECONDS={warmup}"
    )
    attacker_cmd = (
        "make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 "
        f"DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        f"TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        f"ATTACK_DROP_PCT={attack_drop},WARMUP_SECONDS={warmup}"
    )
    relay_cmd = (
        "make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 "
        "DEFINES=BRPL_MODE=1,TRUST_LAMBDA=0,TRUST_PENALTY_GAMMA=1,"
        "TRUST_LAMBDA_CONF=0,TRUST_PENALTY_GAMMA_CONF=1,"
        "ATTACK_DROP_PCT=0,WARMUP_SECONDS=0,ATTACK_WARMUP_SECONDS=0"
    )
    return root_cmd, sender_cmd, attacker_cmd, relay_cmd


def load_positions(path):
    nodes = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("node_id"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                raise ValueError(f"Invalid line (need id,x,y[,role]): {line}")
            node_id = int(parts[0])
            x = float(parts[1])
            y = float(parts[2])
            role = parts[3].lower() if len(parts) >= 4 else ""
            if not role:
                role = "root" if node_id == 1 else "sender"
            if role not in {"root", "attacker", "sender", "relay"}:
                raise ValueError(f"Invalid role '{role}' in line: {line}")
            if node_id in nodes:
                raise ValueError(f"Duplicate node_id {node_id}")
            nodes[node_id] = (x, y, role)
    if 1 not in nodes or nodes[1][2] != "root":
        raise ValueError("Node 1 must be role=root")
    return nodes


def write_csc(args, nodes):
    title = args.title
    if not title:
        title = "Trust-Aware BRPL Simulation (Manual)"
    root_cmd, sender_cmd, attacker_cmd, relay_cmd = motetype_commands(
        args.send_interval, args.warmup, args.attack_drop
    )

    has_relay = any(role == "relay" for _, _, role in nodes.values())

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
    for node_id in sorted(nodes.keys()):
        x, y, role = nodes[node_id]
        if role == "root":
            motes_xml.append(f"    <!-- Node {node_id}: Root -->\n" + mote_block(node_id, (x, y), "root_type"))
        elif role == "attacker":
            motes_xml.append(f"    <!-- Node {node_id}: Attacker -->\n" + mote_block(node_id, (x, y), "attacker_type"))
        elif role == "relay":
            motes_xml.append(f"    <!-- Node {node_id}: Relay -->\n" + mote_block(node_id, (x, y), "relay_type"))
        else:
            motes_xml.append(f"    <!-- Node {node_id}: Sender -->\n" + mote_block(node_id, (x, y), "sender_type"))

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

    out = f"""<?xml version="1.0" encoding="UTF-8"?>
<simconf>
  <simulation>
    <title>{title}</title>
    <randomseed>123456</randomseed>
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
{relay_motetype}{''.join(motes_xml)}  </simulation>
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

    with open(args.outfile, "w", encoding="utf-8") as f:
        f.write(out)


def main():
    args = parse_args()
    try:
        nodes = load_positions(args.positions)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    write_csc(args, nodes)


if __name__ == "__main__":
    main()
