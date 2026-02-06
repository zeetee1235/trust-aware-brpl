<?xml version="1.0" encoding="UTF-8"?>
<simconf>
  <simulation>
    <title>Trust-Aware BRPL Simulation (Random)</title>
    <randomseed>234567</randomseed>
    <motedelay_us>1000000</motedelay_us>
    <radiomedium>
      org.contikios.cooja.radiomediums.UDGM
      <transmitting_range>40.0</transmitting_range>
      <interference_range>80.0</interference_range>
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
      <commands>make -C ../motes -f Makefile.receiver -j receiver_root.cooja TARGET=cooja DEFINES=BRPL_MODE=1</commands>
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
      <commands>make -C ../motes -f Makefile.sender -j sender.cooja TARGET=cooja DEFINES=BRPL_MODE=1,SEND_INTERVAL_SECONDS=30,WARMUP_SECONDS=120</commands>
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
      <commands>make -C ../motes -f Makefile.attacker -j attacker.cooja TARGET=cooja DEFINES=BRPL_MODE=1,ATTACK_DROP_PCT=50,WARMUP_SECONDS=120</commands>
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
        <x>0.00</x>
        <y>0.00</y>
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
    <!-- Node 2: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>-12.24</x>
        <y>-10.02</y>
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
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 3: Attacker -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>33.72</x>
        <y>-0.96</y>
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
      <motetype_identifier>attacker_type</motetype_identifier>
    </mote>
    <!-- Node 4: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>20.41</x>
        <y>19.48</y>
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
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 5: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>64.33</x>
        <y>-17.84</y>
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
        <x>38.39</x>
        <y>12.40</y>
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
        <x>92.15</x>
        <y>-23.02</y>
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
        <x>35.75</x>
        <y>39.89</y>
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
        <x>-45.80</x>
        <y>-2.38</y>
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
        <x>51.08</x>
        <y>24.86</y>
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
        <x>22.37</x>
        <y>28.43</y>
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
        <x>66.91</x>
        <y>13.41</y>
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
        <x>-10.05</x>
        <y>31.76</y>
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
        <x>72.47</x>
        <y>39.03</y>
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
        <x>29.42</x>
        <y>-21.13</y>
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
        <x>40.11</x>
        <y>78.84</y>
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
        <x>110.12</x>
        <y>-19.49</y>
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
        <x>56.47</x>
        <y>39.25</y>
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
        <x>29.85</x>
        <y>-37.93</y>
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
        <x>76.12</x>
        <y>-24.82</y>
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
    <!-- Node 21: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>18.66</x>
        <y>86.07</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>21</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 22: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>39.67</x>
        <y>64.59</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>22</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 23: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>50.79</x>
        <y>67.37</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>23</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 24: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>-3.38</x>
        <y>-57.58</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>24</id>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiRadio
        <bitrate>250.0</bitrate>
      </interface_config>
      <motetype_identifier>sender_type</motetype_identifier>
    </mote>
    <!-- Node 25: Sender -->
    <mote>
      <interface_config>
        org.contikios.cooja.interfaces.Position
        <x>106.28</x>
        <y>-2.95</y>
        <z>0.0</z>
      </interface_config>
      <interface_config>
        org.contikios.cooja.contikimote.interfaces.ContikiMoteID
        <id>25</id>
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
TIMEOUT(@SIM_TIME_MS@, log.log("SIMULATION_FINISHED\n"); log.testOK(); );
log.log("Headless simulation started\n");
log.log("Duration: @SIM_TIME_SEC@s\n");
log.log("Nodes: " + sim.getMotesCount() + "\n");
var trustFile = "@TRUST_FEEDBACK_PATH@";
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
