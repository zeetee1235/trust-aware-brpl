#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import csv
import math

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "docs" / "paper"
FIG = PAPER / "figures"
TOPO = ROOT / "configs" / "topologies"

FIG.mkdir(parents=True, exist_ok=True)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"generated: {path}")


def fig1_system_architecture() -> str:
    # High-end academic style: layered cards + directional flow + side channels
    return """<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='760' viewBox='0 0 1280 760'>
  <defs>
    <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#f8fafc'/>
      <stop offset='100%' stop-color='#e2e8f0'/>
    </linearGradient>
    <linearGradient id='card' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#ffffff'/>
      <stop offset='100%' stop-color='#f1f5f9'/>
    </linearGradient>
    <filter id='shadow' x='-20%' y='-20%' width='140%' height='140%'>
      <feDropShadow dx='0' dy='6' stdDeviation='10' flood-color='#0f172a' flood-opacity='0.12'/>
    </filter>
    <marker id='arrow' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>
      <path d='M0,0 L10,5 L0,10 z' fill='#0f766e'/>
    </marker>
    <marker id='arrow2' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>
      <path d='M0,0 L10,5 L0,10 z' fill='#334155'/>
    </marker>
  </defs>

  <rect x='0' y='0' width='1280' height='760' fill='url(#bg)'/>
  <text x='54' y='62' font-size='34' font-weight='700' fill='#0f172a'>Figure 1. TA-BRPL System Architecture</text>
  <text x='54' y='92' font-size='18' fill='#334155'>Trust-aware routing pipeline integrating BRPL metric penalty and blacklist gating</text>

  <!-- Main pipeline cards -->
  <g filter='url(#shadow)'>
    <rect x='70' y='150' rx='18' ry='18' width='190' height='108' fill='url(#card)' stroke='#cbd5e1' stroke-width='1.2'/>
    <rect x='300' y='150' rx='18' ry='18' width='190' height='108' fill='url(#card)' stroke='#cbd5e1' stroke-width='1.2'/>
    <rect x='530' y='150' rx='18' ry='18' width='190' height='108' fill='url(#card)' stroke='#cbd5e1' stroke-width='1.2'/>
    <rect x='760' y='150' rx='18' ry='18' width='210' height='108' fill='url(#card)' stroke='#cbd5e1' stroke-width='1.2'/>
    <rect x='1010' y='150' rx='18' ry='18' width='200' height='108' fill='url(#card)' stroke='#cbd5e1' stroke-width='1.2'/>
  </g>

  <text x='95' y='190' font-size='18' font-weight='700' fill='#0f172a'>Packet</text>
  <text x='95' y='214' font-size='18' font-weight='700' fill='#0f172a'>Forwarding</text>
  <text x='95' y='238' font-size='14' fill='#475569'>Data-plane events</text>

  <text x='325' y='190' font-size='18' font-weight='700' fill='#0f172a'>Trust</text>
  <text x='325' y='214' font-size='18' font-weight='700' fill='#0f172a'>Observation</text>
  <text x='325' y='238' font-size='14' fill='#475569'>RX/TX/FWD traces</text>

  <text x='555' y='190' font-size='18' font-weight='700' fill='#0f172a'>Trust</text>
  <text x='555' y='214' font-size='18' font-weight='700' fill='#0f172a'>Calculation</text>
  <text x='555' y='238' font-size='14' fill='#475569'>EWMA + sink signals</text>

  <text x='784' y='190' font-size='18' font-weight='700' fill='#0f172a'>Trust Penalty</text>
  <text x='784' y='214' font-size='18' font-weight='700' fill='#0f172a'>in BRPL Metric</text>
  <text x='784' y='238' font-size='14' fill='#475569'>score attenuation</text>

  <text x='1036' y='190' font-size='18' font-weight='700' fill='#0f172a'>Parent Selection</text>
  <text x='1036' y='214' font-size='18' font-weight='700' fill='#0f172a'>&amp; Forwarding</text>
  <text x='1036' y='238' font-size='14' fill='#475569'>next-hop decision</text>

  <!-- flow arrows -->
  <path d='M260 205 L300 205' stroke='#0f766e' stroke-width='3' marker-end='url(#arrow)'/>
  <path d='M490 205 L530 205' stroke='#0f766e' stroke-width='3' marker-end='url(#arrow)'/>
  <path d='M720 205 L760 205' stroke='#0f766e' stroke-width='3' marker-end='url(#arrow)'/>
  <path d='M970 205 L1010 205' stroke='#0f766e' stroke-width='3' marker-end='url(#arrow)'/>

  <!-- Trust engine panel -->
  <g filter='url(#shadow)'>
    <rect x='120' y='330' width='520' height='300' rx='20' ry='20' fill='#ffffff' stroke='#cbd5e1' stroke-width='1.3'/>
  </g>
  <text x='150' y='372' font-size='26' font-weight='700' fill='#0f172a'>External Trust Engine</text>
  <text x='150' y='402' font-size='16' fill='#475569'>Observes simulation logs and emits trust updates</text>

  <rect x='160' y='430' width='210' height='70' rx='12' fill='#ecfeff' stroke='#22d3ee'/>
  <text x='175' y='457' font-size='16' font-weight='700' fill='#0f172a'>Input Stream</text>
  <text x='175' y='480' font-size='14' fill='#155e75'>COOJA.testlog</text>

  <rect x='390' y='430' width='210' height='70' rx='12' fill='#f0fdf4' stroke='#4ade80'/>
  <text x='405' y='457' font-size='16' font-weight='700' fill='#0f172a'>Output Stream</text>
  <text x='405' y='480' font-size='14' fill='#166534'>TRUST,node_id,value</text>

  <rect x='160' y='520' width='440' height='84' rx='12' fill='#f8fafc' stroke='#94a3b8'/>
  <text x='178' y='548' font-size='15' fill='#334155'>Artifacts: trust_metrics.csv, exposure.csv, parent_switch.csv, stats.csv, blacklist.csv</text>
  <text x='178' y='575' font-size='15' fill='#334155'>Metric core: EWMA(grayhole) + sinkhole signals + attacker exposure indicators</text>

  <path d='M395 258 C395 295 380 330 380 430' stroke='#334155' stroke-width='2.6' fill='none' marker-end='url(#arrow2)'/>
  <text x='408' y='315' font-size='13' fill='#334155'>trust observation feed</text>

  <!-- Blacklist branch -->
  <g filter='url(#shadow)'>
    <rect x='730' y='350' width='460' height='220' rx='20' fill='#ffffff' stroke='#cbd5e1' stroke-width='1.3'/>
  </g>
  <text x='760' y='392' font-size='26' font-weight='700' fill='#0f172a'>Blacklist Policy Layer</text>
  <text x='760' y='422' font-size='15' fill='#475569'>Threshold + hysteresis gate for packet filtering and parent avoidance</text>

  <rect x='770' y='450' width='200' height='86' rx='12' fill='#fff7ed' stroke='#fb923c'/>
  <text x='790' y='478' font-size='15' font-weight='700' fill='#7c2d12'>Trigger</text>
  <text x='790' y='501' font-size='14' fill='#9a3412'>trust &lt; T_blacklist</text>

  <rect x='990' y='450' width='170' height='86' rx='12' fill='#f0fdf4' stroke='#4ade80'/>
  <text x='1010' y='478' font-size='15' font-weight='700' fill='#14532d'>Recovery</text>
  <text x='1010' y='501' font-size='14' fill='#166534'>trust ≥ T_clear</text>

  <path d='M820 258 C820 295 860 330 860 450' stroke='#334155' stroke-width='2.6' fill='none' marker-end='url(#arrow2)'/>
  <text x='872' y='320' font-size='13' fill='#334155'>penalized trust score</text>

  <path d='M960 560 C1010 600 1090 600 1120 258' stroke='#0f766e' stroke-width='2.4' fill='none' marker-end='url(#arrow)'/>
  <text x='960' y='590' font-size='13' fill='#0f766e'>filtered parent candidate set</text>
</svg>
"""


def fig2_attack_model() -> str:
    return """<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='760' viewBox='0 0 1280 760'>
  <defs>
    <linearGradient id='bg2' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#f8fafc'/>
      <stop offset='100%' stop-color='#e2e8f0'/>
    </linearGradient>
    <filter id='shadow2' x='-20%' y='-20%' width='140%' height='140%'>
      <feDropShadow dx='0' dy='6' stdDeviation='10' flood-color='#0f172a' flood-opacity='0.14'/>
    </filter>
    <marker id='arrA' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>
      <path d='M0,0 L10,5 L0,10 z' fill='#0ea5e9'/>
    </marker>
    <marker id='arrD' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>
      <path d='M0,0 L10,5 L0,10 z' fill='#ef4444'/>
    </marker>
  </defs>

  <rect x='0' y='0' width='1280' height='760' fill='url(#bg2)'/>
  <text x='54' y='62' font-size='34' font-weight='700' fill='#0f172a'>Figure 2. Combined Attack Model (Sinkhole + Grayhole)</text>
  <text x='54' y='92' font-size='18' fill='#334155'>Traffic attraction via control-plane manipulation and selective drop on data-plane forwarding</text>

  <g filter='url(#shadow2)'>
    <rect x='70' y='150' width='1140' height='520' rx='24' fill='#ffffff' stroke='#cbd5e1' stroke-width='1.3'/>
  </g>

  <!-- network nodes -->
  <circle cx='190' cy='260' r='34' fill='#60a5fa' stroke='#1d4ed8' stroke-width='2.2'/>
  <text x='160' y='267' font-size='16' font-weight='700' fill='white'>N1..Nk</text>
  <text x='148' y='300' font-size='14' fill='#334155'>normal nodes</text>

  <circle cx='560' cy='260' r='42' fill='#f59e0b' stroke='#b45309' stroke-width='2.4'/>
  <text x='526' y='267' font-size='17' font-weight='700' fill='white'>Attacker</text>
  <text x='542' y='300' font-size='14' fill='#7c2d12'>A</text>

  <circle cx='960' cy='260' r='38' fill='#ef4444' stroke='#991b1b' stroke-width='2.4'/>
  <text x='941' y='267' font-size='18' font-weight='700' fill='white'>Root</text>
  <text x='920' y='300' font-size='14' fill='#7f1d1d'>RPL root</text>

  <path d='M226 260 L518 260' stroke='#0ea5e9' stroke-width='4.2' marker-end='url(#arrA)'/>
  <text x='310' y='240' font-size='15' fill='#0369a1'>forward</text>

  <path d='M602 246 L920 246' stroke='#0ea5e9' stroke-width='4.2' marker-end='url(#arrA)'/>
  <text x='700' y='226' font-size='15' fill='#0369a1'>forward</text>

  <path d='M602 278 L850 278' stroke='#ef4444' stroke-width='4.2' stroke-dasharray='12 10' marker-end='url(#arrD)'/>
  <text x='700' y='315' font-size='15' fill='#991b1b'>drop (grayhole)</text>

  <!-- sinkhole panel -->
  <rect x='140' y='380' width='480' height='230' rx='16' fill='#eff6ff' stroke='#93c5fd' stroke-width='1.6'/>
  <text x='168' y='420' font-size='24' font-weight='700' fill='#1e3a8a'>Sinkhole Behavior</text>

  <rect x='170' y='445' width='420' height='62' rx='10' fill='white' stroke='#bfdbfe'/>
  <text x='192' y='471' font-size='16' fill='#1e293b'>DIO Rank Manipulation</text>
  <text x='192' y='492' font-size='14' fill='#334155'>Advertise near-root rank: rank = root + 1</text>

  <rect x='170' y='523' width='420' height='62' rx='10' fill='white' stroke='#bfdbfe'/>
  <text x='192' y='549' font-size='16' fill='#1e293b'>ETX Metric Manipulation</text>
  <text x='192' y='570' font-size='14' fill='#334155'>Advertise optimistic ETX: mc.obj.etx × 0.5</text>

  <!-- grayhole panel -->
  <rect x='660' y='380' width='500' height='230' rx='16' fill='#fff7ed' stroke='#fdba74' stroke-width='1.6'/>
  <text x='688' y='420' font-size='24' font-weight='700' fill='#9a3412'>Grayhole Behavior</text>

  <rect x='690' y='445' width='440' height='62' rx='10' fill='white' stroke='#fed7aa'/>
  <text x='712' y='471' font-size='16' fill='#1e293b'>Selective Packet Drop</text>
  <text x='712' y='492' font-size='14' fill='#334155'>Drop forwarded UDP packets with configured probability</text>

  <rect x='690' y='523' width='440' height='62' rx='10' fill='white' stroke='#fed7aa'/>
  <text x='712' y='549' font-size='16' fill='#1e293b'>Forward / Drop Mixed Pattern</text>
  <text x='712' y='570' font-size='14' fill='#334155'>Maintains partial liveness while degrading end-to-end delivery</text>
</svg>
"""


def load_nodes(name: str):
    path = TOPO / f"{name}.csv"
    out = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            out.append((int(row["node_id"]), float(row["x"]), float(row["y"]), row["role"]))
    return out


def map_xy(x: float, y: float, ox: float, oy: float, size: float = 260.0):
    return ox + x * size / 100.0, oy + (100.0 - y) * size / 100.0


def topo_panel(name: str, ox: float, oy: float) -> str:
    nodes = load_nodes(name)
    tx_range = 21.0
    lines = []
    for i, (_, ax, ay, _) in enumerate(nodes):
        x1, y1 = map_xy(ax, ay, ox, oy)
        for _, bx, by, _ in nodes[i + 1 :]:
            if math.hypot(ax - bx, ay - by) <= tx_range:
                x2, y2 = map_xy(bx, by, ox, oy)
                lines.append(
                    f"<line x1='{x1:.2f}' y1='{y1:.2f}' x2='{x2:.2f}' y2='{y2:.2f}' stroke='#cbd5e1' stroke-width='0.8' />"
                )

    colors = {
        "root": ("#ef4444", "#991b1b", 6.4),
        "attacker": ("#f59e0b", "#b45309", 6.2),
        "relay": ("#8b5cf6", "#5b21b6", 5.3),
        "sender": ("#3b82f6", "#1d4ed8", 4.2),
    }
    circles = []
    for nid, x, y, role in nodes:
        cx, cy = map_xy(x, y, ox, oy)
        fill, stroke, r = colors.get(role, ("#64748b", "#334155", 4))
        circles.append(
            f"<circle cx='{cx:.2f}' cy='{cy:.2f}' r='{r:.2f}' fill='{fill}' stroke='{stroke}' stroke-width='1.0' />"
        )
        if role in {"root", "attacker", "relay"}:
            circles.append(
                f"<text x='{cx + 6:.2f}' y='{cy - 6:.2f}' font-size='10' fill='#0f172a'>N{nid}</text>"
            )

    title = name.replace("_M", "")
    return (
        f"<g>"
        f"<rect x='{ox-16:.2f}' y='{oy-42:.2f}' width='300' height='336' rx='14' fill='#ffffff' stroke='#cbd5e1'/>"
        f"<text x='{ox-2:.2f}' y='{oy-15:.2f}' font-size='22' font-weight='700' fill='#0f172a'>{title}</text>"
        f"<rect x='{ox:.2f}' y='{oy:.2f}' width='260' height='260' fill='#f8fafc' stroke='#94a3b8'/>"
        + "".join(lines)
        + "".join(circles)
        + "</g>"
    )


def fig3_topologies() -> str:
    left = topo_panel("CLUSTER_M", 80, 170)
    mid = topo_panel("GRID_M", 490, 170)
    right = topo_panel("RING_M", 900, 170)
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='760' viewBox='0 0 1280 760'>"
        "<rect x='0' y='0' width='1280' height='760' fill='#f8fafc'/>"
        "<text x='54' y='62' font-size='34' font-weight='700' fill='#0f172a'>Figure 3. Experimental Topologies (Medium Scale)</text>"
        "<text x='54' y='92' font-size='18' fill='#334155'>Three topology families used in attack-resilience evaluation (100m × 100m field)</text>"
        f"{left}{mid}{right}"
        "<g transform='translate(90,660)'>"
        "<circle cx='0' cy='0' r='6' fill='#ef4444'/><text x='12' y='4' font-size='14' fill='#1e293b'>root</text>"
        "<circle cx='120' cy='0' r='6' fill='#f59e0b'/><text x='132' y='4' font-size='14' fill='#1e293b'>attacker</text>"
        "<circle cx='260' cy='0' r='5' fill='#8b5cf6'/><text x='272' y='4' font-size='14' fill='#1e293b'>relay</text>"
        "<circle cx='360' cy='0' r='4' fill='#3b82f6'/><text x='372' y='4' font-size='14' fill='#1e293b'>normal node</text>"
        "</g>"
        "</svg>"
    )


def main() -> None:
    write(FIG / "fig1_ta_brpl_architecture.svg", fig1_system_architecture())
    write(FIG / "fig2_attack_model.svg", fig2_attack_model())
    write(FIG / "fig3_topologies_medium.svg", fig3_topologies())


if __name__ == "__main__":
    main()
