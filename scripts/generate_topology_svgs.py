#!/usr/bin/env python3
"""
Generate topology SVGs from configs/topologies/*.csv.

Outputs:
  - figures/topology_svgs/{CLUSTER,GRID,RING}_{S,M,L}.svg
  - figures/topology_svgs/all_topologies.svg
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOPO_DIR = PROJECT_ROOT / "configs" / "topologies"
OUT_DIR = PROJECT_ROOT / "figures" / "topology_svgs"

TOPOLOGIES = [
    "CLUSTER_S", "CLUSTER_M", "CLUSTER_L",
    "GRID_S", "GRID_M", "GRID_L",
    "RING_S", "RING_M", "RING_L",
]

ROLE_STYLE = {
    "root": {"fill": "#e74c3c", "stroke": "#b03a2e", "r": 6},
    "attacker": {"fill": "#f39c12", "stroke": "#9c640c", "r": 6},
    "relay": {"fill": "#9b59b6", "stroke": "#6c3483", "r": 5},
    "sender": {"fill": "#3498db", "stroke": "#21618c", "r": 4},
}


@dataclass
class Node:
    node_id: int
    x: float
    y: float
    role: str


def load_nodes(csv_path: Path) -> List[Node]:
    nodes: List[Node] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nodes.append(
                Node(
                    node_id=int(row["node_id"]),
                    x=float(row["x"]),
                    y=float(row["y"]),
                    role=row["role"].strip(),
                )
            )
    return nodes


def to_canvas(x: float, y: float, size: int = 100, margin: int = 20) -> Tuple[float, float]:
    scale = float(size)
    cx = margin + x * scale / 100.0
    cy = margin + (100.0 - y) * scale / 100.0
    return cx, cy


def svg_for_topology(name: str, nodes: List[Node], tx_range: float = 21.0) -> str:
    size = 100
    margin = 20
    w = size + 2 * margin
    h = size + 2 * margin + 18

    # Draw proximity links for quick visual multi-hop check
    lines: List[str] = []
    for i, a in enumerate(nodes):
        ax, ay = a.x, a.y
        x1, y1 = to_canvas(ax, ay, size=size, margin=margin)
        for b in nodes[i + 1:]:
            dx = ax - b.x
            dy = ay - b.y
            if (dx * dx + dy * dy) ** 0.5 <= tx_range:
                x2, y2 = to_canvas(b.x, b.y, size=size, margin=margin)
                lines.append(
                    f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                    'stroke="#cfd8dc" stroke-width="0.8" />'
                )

    circles: List[str] = []
    labels: List[str] = []
    for n in nodes:
        style = ROLE_STYLE[n.role]
        cx, cy = to_canvas(n.x, n.y, size=size, margin=margin)
        circles.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{style["r"]}" '
            f'fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="1.0" />'
        )
        if n.node_id <= 12 or n.role in {"root", "attacker", "relay"}:
            labels.append(
                f'<text x="{cx + 5:.2f}" y="{cy - 5:.2f}" font-size="7" fill="#263238">N{n.node_id}</text>'
            )

    legend = (
        '<g transform="translate(10,124)">'
        '<circle cx="8" cy="8" r="4" fill="#e74c3c"/><text x="16" y="10" font-size="8">root</text>'
        '<circle cx="50" cy="8" r="4" fill="#f39c12"/><text x="58" y="10" font-size="8">attacker</text>'
        '<circle cx="106" cy="8" r="4" fill="#9b59b6"/><text x="114" y="10" font-size="8">relay</text>'
        '<circle cx="150" cy="8" r="4" fill="#3498db"/><text x="158" y="10" font-size="8">sender</text>'
        '</g>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>\n'
        f'<text x="10" y="14" font-size="12" font-weight="700" fill="#263238">{name}</text>\n'
        f'<rect x="{margin}" y="{margin}" width="{size}" height="{size}" fill="#fafafa" stroke="#b0bec5" stroke-width="1"/>\n'
        + "\n".join(lines) + "\n"
        + "\n".join(circles) + "\n"
        + "\n".join(labels) + "\n"
        + legend + "\n"
        + "</svg>\n"
    )


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def make_all_topologies_grid(svgs: Dict[str, str]) -> str:
    # 3 columns x 3 rows
    cell_w = 170
    cell_h = 170
    cols = 3
    rows = 3
    margin = 20
    width = margin * 2 + cols * cell_w
    height = margin * 2 + rows * cell_h + 40

    order = [
        "CLUSTER_S", "GRID_S", "RING_S",
        "CLUSTER_M", "GRID_M", "RING_M",
        "CLUSTER_L", "GRID_L", "RING_L",
    ]

    def embed_cell(name: str, x: int, y: int) -> str:
        nodes = load_nodes(TOPO_DIR / f"{name}.csv")
        body = svg_for_topology(name, nodes, tx_range=21.0)
        # Strip outer svg wrapper and place in translated/scaled group
        inner = body.split(">", 1)[1].rsplit("</svg>", 1)[0]
        return (
            f'<g transform="translate({x},{y}) scale(1.15)">\n'
            f"{inner}\n"
            "</g>"
        )

    groups: List[str] = []
    for idx, name in enumerate(order):
        r = idx // cols
        c = idx % cols
        gx = margin + c * cell_w
        gy = margin + r * cell_h
        groups.append(embed_cell(name, gx, gy))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>\n'
        '<text x="20" y="18" font-size="14" font-weight="700" fill="#263238">Topology Layouts (Updated Fixed Coordinates)</text>\n'
        + "\n".join(groups)
        + "\n</svg>\n"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated: Dict[str, str] = {}
    for name in TOPOLOGIES:
        nodes = load_nodes(TOPO_DIR / f"{name}.csv")
        svg = svg_for_topology(name, nodes, tx_range=21.0)
        out_path = OUT_DIR / f"{name}.svg"
        write_file(out_path, svg)
        generated[name] = svg
        print(f"generated: {out_path}")

    all_svg = make_all_topologies_grid(generated)
    write_file(OUT_DIR / "all_topologies.svg", all_svg)
    print(f"generated: {OUT_DIR / 'all_topologies.svg'}")


if __name__ == "__main__":
    main()
