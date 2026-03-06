<?xml version="1.0" encoding="UTF-8"?>
<simconf>
  <simulation>
    <title>CHOKEPOINT 2-CLUSTER S (N=20)</title>
    <randomseed>345678</randomseed>
    <motedelay_us>1000000</motedelay_us>
    <radiomedium>
      org.contikios.cooja.radiomediums.UDGM
      <transmitting_range>21.0</transmitting_range>
      <interference_range>42.0</interference_range>
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
      <commands>/usr/bin/make -C ../motes CONTIKI=/home/research/TA-BRPL/contiki-ng-brpl -f Makefile.receiver -j receiver_root.cooja TARGET=cooja WERROR=0 DEFINES=BRPL_MODE=1,TRUST_LAMBDA=6,TRUST_GAMMA=4,TRUST_PENALTY_GAMMA=4,TRUST_LAMBDA_CONF=6,TRUST_PENALTY_GAMMA_CONF=4,ATTACK_MODE=2,ATTACKER_NODE_ID=2,TRUST_ENABLED=1,BLACKLIST_TRUST_THRESHOLD_NORM=0.80,BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=0.95,RPL_BASELINE_MODE=0</commands>
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
      <commands>/usr/bin/make -C ../motes CONTIKI=/home/research/TA-BRPL/contiki-ng-brpl -f Makefile.sender -j sender.cooja TARGET=cooja WERROR=0 DEFINES=BRPL_MODE=1,TRUST_ENABLED=1,TRUST_LAMBDA=6,TRUST_GAMMA=4,TRUST_PENALTY_GAMMA=4,TRUST_LAMBDA_CONF=6,TRUST_PENALTY_GAMMA_CONF=4,SEND_INTERVAL_SECONDS=30,WARMUP_SECONDS=120,ATTACK_MODE=2,ATTACKER_NODE_ID=2,BLACKLIST_TRUST_THRESHOLD_NORM=0.80,BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=0.95,RPL_BASELINE_MODE=0</commands>
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
      <commands>/usr/bin/make -C ../motes CONTIKI=/home/research/TA-BRPL/contiki-ng-brpl -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 DEFINES=BRPL_MODE=1,TRUST_LAMBDA=6,TRUST_GAMMA=4,TRUST_PENALTY_GAMMA=4,TRUST_LAMBDA_CONF=6,TRUST_PENALTY_GAMMA_CONF=4,ATTACK_DROP_PCT=45,ATTACK_MODE=2,WARMUP_SECONDS=120,ATTACKER_NODE_ID=2,TRUST_ENABLED=1,BLACKLIST_TRUST_THRESHOLD_NORM=0.80,BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=0.95,RPL_BASELINE_MODE=0</commands>
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
      <identifier>relay_type</identifier>
      <description>Relay Node (No Attack)</description>
      <source>[CONFIG_DIR]/../motes/attacker.c</source>
      <commands>/usr/bin/make -C ../motes CONTIKI=/home/research/TA-BRPL/contiki-ng-brpl -f Makefile.attacker -j attacker.cooja TARGET=cooja WERROR=0 DEFINES=BRPL_MODE=1,TRUST_LAMBDA=6,TRUST_GAMMA=4,TRUST_PENALTY_GAMMA=4,TRUST_LAMBDA_CONF=6,TRUST_PENALTY_GAMMA_CONF=4,ATTACK_DROP_PCT=45,ATTACK_MODE=2,WARMUP_SECONDS=120,ATTACK_WARMUP_SECONDS=120,ATTACKER_NODE_ID=2,TRUST_ENABLED=1,BLACKLIST_TRUST_THRESHOLD_NORM=0.80,BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=0.95,RPL_BASELINE_MODE=0</commands>
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
    <!-- Node 1: Root -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>10.00</x>
        <y>50.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>1</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>root_type</motetype_identifier>
    </mote>
    <!-- Node 2: Attacker -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>44.00</x>
        <y>50.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>2</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>attacker_type</motetype_identifier>
    </mote>
    <!-- Node 3: Relay -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>52.00</x>
        <y>42.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>3</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>relay_type</motetype_identifier>
    </mote>
    <!-- Node 4: Relay -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>52.00</x>
        <y>58.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>4</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>relay_type</motetype_identifier>
    </mote>
    <!-- Node 5: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>20.00</x>
        <y>40.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>5</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 6: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>20.00</x>
        <y>50.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>6</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 7: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>20.00</x>
        <y>60.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>7</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 8: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>30.00</x>
        <y>45.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>8</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 9: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>30.00</x>
        <y>55.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>9</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 10: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>25.00</x>
        <y>35.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>10</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 11: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>25.00</x>
        <y>65.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>11</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 12: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>58.00</x>
        <y>44.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>12</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 13: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>58.00</x>
        <y>56.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>13</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 14: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>66.00</x>
        <y>50.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>14</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 15: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>72.00</x>
        <y>40.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>15</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 16: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>72.00</x>
        <y>60.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>16</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 17: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>80.00</x>
        <y>45.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>17</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 18: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>80.00</x>
        <y>55.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>18</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 19: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>88.00</x>
        <y>40.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>19</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 20: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>88.00</x>
        <y>60.00</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>20</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
  </simulation>
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
      <script><![CDATA[
// Auto-generated Cooja script
TIMEOUT(600000, log.log("SIMULATION_FINISHED\n"); log.testOK(); );
log.log("Headless simulation started\n");
log.log("Duration: 600s\n");
log.log("Nodes: " + sim.getMotesCount() + "\n");
var trustFile = "/home/research/TA-BRPL/results/experiments-20260306-130702/CLUSTER_S_6_brpl_attack_trust_p45_mode2_d1_a1.0_lam6_gam4_bl0.80_blc0.95_s345678/trust_feedback.txt";
var lastCheckMs = 0;
var lastPos = 0;
function pollTrust() {
  try {
    var file = new java.io.File(trustFile);
    if(!file.exists()) {
      return;
    }
    var raf = new java.io.RandomAccessFile(file, "r");
    raf.seek(lastPos);
    var line;
    while((line = raf.readLine()) != null) {
      line = String(line).trim();
      if(line.length() == 0) {
        continue;
      }
      var parts = line.split(",");
      if(parts.length < 3) {
        continue;
      }
      if(parts[0] != "TRUST") {
        continue;
      }
      var node = parts[1];
      var trust = parts[2];
      var cmd = "TRUST," + node + "," + trust + "\n";
      for(var i = 0; i < sim.getMotesCount(); i++) {
        var mote = sim.getMote(i);
        try {
          mote.getInterfaces().getLog().writeString(cmd);
        } catch (e) {
        }
      }
      log.log("INJECT " + cmd);
    }
    lastPos = raf.getFilePointer();
    raf.close();
  } catch (e) {
  }
}
while(true) {
  YIELD();
  if(msg != null) {
    log.log(msg + "\n");
  }
  var now = java.lang.System.currentTimeMillis();
  if(now - lastCheckMs > 200) {
    pollTrust();
    lastCheckMs = now;
  }
}
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
