#!/usr/bin/env python3
"""Generate controlled-random Cooja scenarios from GRID6x6 templates.

Design aligned with docs/random_topo.md:
- density-grouped random placement (sparse/medium/dense)
- root fixed by rule (center)
- connectivity + degree-range acceptance filter
- topology seed separated from run seed (run seed is patched at runtime)
- attacker placement: conditional random from high-centrality candidate pool
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = ROOT / "configs" / "scenarios"

DEFAULT_PROTOCOLS = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
DEFAULT_DENSITIES = ["sparse", "medium", "dense"]
DEFAULT_ATTACK_PROFILE = "sinkhole_drop"
DEFAULT_ATTACK_DROP_PCT = 50

DENSITY_PROFILES = {
    "sparse": {
        "width": 220.0,
        "height": 220.0,
        "degree_min": 2.0,
        "degree_max": 4.6,
    },
    "medium": {
        "width": 180.0,
        "height": 180.0,
        "degree_min": 3.6,
        "degree_max": 6.8,
    },
    "dense": {
        "width": 145.0,
        "height": 145.0,
        "degree_min": 5.0,
        "degree_max": 9.8,
    },
}

ATTACK_PROFILE_TO_MOTETYPE = {
    "drop": "attacker_type",
    "sinkhole": "sinkhole_type",
    "sinkhole_drop": "sinkhole_type",
}

SINKHOLE_DROP_MAKEFILE_BY_PROTOCOL = {
    "RPL": "Makefile.sinkhole_drop_rpl",
    "SMTRUST": "Makefile.sinkhole_drop_rpl",
    "BRPL": "Makefile.sinkhole_drop_brpl",
    "TABRPL": "Makefile.sinkhole_drop_tabrpl",
    # Ablation variants share the same sinkhole attacker build.
    "TABRPL_FWD": "Makefile.sinkhole_drop_tabrpl",
    "TABRPL_FWDCTRL": "Makefile.sinkhole_drop_tabrpl",
}


def parse_spec(spec: str) -> List[int]:
    values: List[int] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                start, end = end, start
            values.extend(range(start, end + 1))
        else:
            values.append(int(token))
    uniq = sorted(set(values))
    if not uniq:
        raise ValueError(f"empty spec: {spec!r}")
    return uniq


def pick_attack_count(template_info: dict, attack_profile: str) -> int:
    if attack_profile == "drop":
        return int(template_info["attacker_count"])
    return int(template_info["sinkhole_count"])


def configure_sinkhole_motetype_for_drop(
    *,
    sim: ET.Element,
    proto: str,
    rel_to_motes: str,
    attack_drop_pct: int,
) -> None:
    makefile = SINKHOLE_DROP_MAKEFILE_BY_PROTOCOL.get(proto)
    if makefile is None:
        raise RuntimeError(f"unsupported protocol for sinkhole_drop profile: {proto}")

    for motetype in sim.findall("motetype"):
        ident = motetype.findtext("identifier")
        if ident != "sinkhole_type":
            continue
        desc = motetype.find("description")
        src = motetype.find("source")
        cmd = motetype.find("commands")
        if desc is not None:
            desc.text = f"Sinkhole+Drop Attacker ({proto})"
        if src is not None:
            src.text = f"[CONFIG_DIR]/{rel_to_motes}/sinkhole_drop_attacker.c"
        if cmd is not None:
            cmd.text = (
                f"$(MAKE) -f {makefile} TARGET=cooja ATTACK_DROP_PCT={attack_drop_pct} clean\n"
                f"      $(MAKE) -f {makefile} TARGET=cooja ATTACK_DROP_PCT={attack_drop_pct} "
                f"WERROR=0 sinkhole_drop_attacker.cooja"
            )
        return

    raise RuntimeError("sinkhole_type motetype not found in template")


def text_has(elem: ET.Element, needle: str) -> bool:
    return needle in (elem.text or "")


def extract_mote_id(mote: ET.Element) -> int:
    for iface in mote.findall("interface_config"):
        if text_has(iface, "ContikiMoteID"):
            node_id = iface.findtext("id")
            if node_id is None:
                break
            return int(node_id.strip())
    raise RuntimeError("mote without ContikiMoteID")


def find_position_iface(mote: ET.Element) -> ET.Element:
    for iface in mote.findall("interface_config"):
        if text_has(iface, "interfaces.Position"):
            return iface
    raise RuntimeError("mote without Position interface")


def parse_template_info(path: Path) -> dict:
    root = ET.parse(path).getroot()
    sim = root.find("simulation")
    if sim is None:
        raise RuntimeError(f"invalid csc (no simulation): {path}")

    motes = sim.findall("mote")
    if not motes:
        raise RuntimeError(f"invalid csc (no motes): {path}")

    tx_txt = sim.findtext("radiomedium/transmitting_range")
    tx_range = float(tx_txt) if tx_txt else 50.0

    root_ids: List[int] = []
    attacker_ids: List[int] = []
    sender_ids: List[int] = []
    sinkhole_ids: List[int] = []

    for mote in motes:
        node_id = extract_mote_id(mote)
        typ = (mote.findtext("motetype_identifier") or "").strip()
        if typ == "root_type":
            root_ids.append(node_id)
        elif typ == "attacker_type":
            attacker_ids.append(node_id)
        elif typ == "sender_type":
            sender_ids.append(node_id)
        elif typ == "sinkhole_type":
            sinkhole_ids.append(node_id)

    if len(root_ids) != 1:
        raise RuntimeError(f"expected exactly one root_type in {path}, got {len(root_ids)}")

    return {
        "num_nodes": len(motes),
        "root_id": root_ids[0],
        "attacker_count": len(attacker_ids),
        "sender_count": len(sender_ids),
        "sinkhole_count": len(sinkhole_ids),
        "tx_range": tx_range,
    }


def euclid(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def build_adj(coords: Dict[int, Tuple[float, float]], tx_range: float) -> Dict[int, List[int]]:
    ids = sorted(coords.keys())
    adj: Dict[int, List[int]] = {i: [] for i in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if euclid(coords[a], coords[b]) <= tx_range:
                adj[a].append(b)
                adj[b].append(a)
    return adj


def bfs_dist(adj: Dict[int, List[int]], start: int) -> Dict[int, int]:
    d = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj[cur]:
            if nxt not in d:
                d[nxt] = d[cur] + 1
                q.append(nxt)
    return d


def connected(adj: Dict[int, List[int]], root_id: int, num_nodes: int) -> bool:
    return len(bfs_dist(adj, root_id)) == num_nodes


def avg_degree(adj: Dict[int, List[int]]) -> float:
    return statistics.mean(len(v) for v in adj.values())


def avg_hop_from_root(adj: Dict[int, List[int]], root_id: int) -> float:
    d = bfs_dist(adj, root_id)
    vals = [hop for node, hop in d.items() if node != root_id]
    return statistics.mean(vals) if vals else 0.0


def centrality_scores(adj: Dict[int, List[int]], ids: Sequence[int]) -> Dict[int, float]:
    scores: Dict[int, float] = {}
    for node in ids:
        d = bfs_dist(adj, node)
        if len(d) < len(adj):
            scores[node] = -1.0
            continue
        total = sum(d.values())
        if total <= 0:
            scores[node] = 0.0
        else:
            scores[node] = (len(adj) - 1) / total
    return scores


def sample_layout(
    *,
    num_nodes: int,
    root_id: int,
    attacker_count: int,
    tx_range: float,
    width: float,
    height: float,
    degree_min: float,
    degree_max: float,
    min_distance: float,
    candidate_frac: float,
    max_attempts: int,
    rng: random.Random,
) -> dict:
    ids = list(range(1, num_nodes + 1))
    non_root = [i for i in ids if i != root_id]

    for _ in range(max_attempts):
        coords: Dict[int, Tuple[float, float]] = {}
        coords[root_id] = (width / 2.0, height / 2.0)

        ok = True
        for node in non_root:
            placed = False
            for _ in range(500):
                x = rng.uniform(0.0, width)
                y = rng.uniform(0.0, height)
                if all(euclid((x, y), p) >= min_distance for p in coords.values()):
                    coords[node] = (x, y)
                    placed = True
                    break
            if not placed:
                ok = False
                break
        if not ok:
            continue

        adj = build_adj(coords, tx_range)
        if not connected(adj, root_id, num_nodes):
            continue

        deg = avg_degree(adj)
        if deg < degree_min or deg > degree_max:
            continue

        candidates = non_root
        c_scores = centrality_scores(adj, candidates)
        ranked = sorted(candidates, key=lambda n: (c_scores[n], len(adj[n])), reverse=True)
        pool_n = max(attacker_count, int(len(ranked) * candidate_frac))
        pool = ranked[:pool_n]
        attackers = sorted(rng.sample(pool, attacker_count)) if attacker_count > 0 else []

        return {
            "coords": coords,
            "adj": adj,
            "avg_degree": deg,
            "avg_hop_root": avg_hop_from_root(adj, root_id),
            "attackers": attackers,
        }

    raise RuntimeError(
        f"failed to sample topology after {max_attempts} attempts "
        f"(nodes={num_nodes}, area={width}x{height}, tx={tx_range})"
    )


def write_csc_from_template(
    *,
    template: Path,
    output: Path,
    coords: Dict[int, Tuple[float, float]],
    attackers: Sequence[int],
    root_id: int,
    topo_seed: int,
    density: str,
    topo_index: int,
    attack_profile: str,
    attack_drop_pct: int,
) -> None:
    tree = ET.parse(template)
    sim = tree.getroot().find("simulation")
    if sim is None:
        raise RuntimeError(f"invalid csc: {template}")

    title = sim.find("title")
    proto = template.stem.replace("GRID6x6_", "")
    attack_motetype = ATTACK_PROFILE_TO_MOTETYPE[attack_profile]
    if title is not None:
        title.text = (
            f"TA-BRPL RandomTopo {proto} density={density} "
            f"topo={topo_index:03d} attack={attack_profile}"
        )

    seed_elem = sim.find("randomseed")
    if seed_elem is not None:
        seed_elem.text = str(topo_seed)

    attackers_set = set(attackers)
    rel_to_motes = Path(
        os.path.relpath(ROOT / "motes", start=output.parent)
    ).as_posix()

    # Keep build/source references valid regardless of output folder depth.
    for src_elem in sim.findall(".//motetype/source"):
        src_txt = (src_elem.text or "").strip()
        if not src_txt:
            continue
        src_name = Path(src_txt).name
        src_elem.text = f"[CONFIG_DIR]/{rel_to_motes}/{src_name}"

    if attack_profile == "sinkhole_drop":
        configure_sinkhole_motetype_for_drop(
            sim=sim,
            proto=proto,
            rel_to_motes=rel_to_motes,
            attack_drop_pct=attack_drop_pct,
        )

    for mote in sim.findall("mote"):
        node_id = extract_mote_id(mote)
        pos_iface = find_position_iface(mote)
        x, y = coords[node_id]
        x_elem = pos_iface.find("x")
        y_elem = pos_iface.find("y")
        z_elem = pos_iface.find("z")
        if x_elem is not None:
            x_elem.text = f"{x:.3f}"
        if y_elem is not None:
            y_elem.text = f"{y:.3f}"
        if z_elem is not None:
            z_elem.text = "0.0"

        mt = mote.find("motetype_identifier")
        if mt is not None:
            if node_id == root_id:
                mt.text = "root_type"
            elif node_id in attackers_set:
                mt.text = attack_motetype
            else:
                mt.text = "sender_type"

    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="UTF-8", xml_declaration=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate controlled random topology scenarios")
    ap.add_argument("--protocols", default=",".join(DEFAULT_PROTOCOLS), help="Comma-separated protocols")
    ap.add_argument("--densities", default=",".join(DEFAULT_DENSITIES), help="Comma-separated density groups")
    ap.add_argument("--topology-seeds", default="1-80", help="Topology seed range/list (e.g., 1-25 or 1,3,7)")
    ap.add_argument(
        "--attack-profile",
        default=DEFAULT_ATTACK_PROFILE,
        choices=sorted(ATTACK_PROFILE_TO_MOTETYPE.keys()),
        help="Attack profile for attacker nodes: drop | sinkhole | sinkhole_drop",
    )
    ap.add_argument(
        "--attack-drop-pct",
        type=int,
        default=DEFAULT_ATTACK_DROP_PCT,
        help="Selective forwarding drop percentage for sinkhole_drop profile (0..100).",
    )
    ap.add_argument("--out-dir", default=str(SCENARIOS_DIR / "random_topo"))
    ap.add_argument("--manifest", default=str(SCENARIOS_DIR / "random_topo" / "manifest.json"))
    ap.add_argument("--min-distance", type=float, default=8.0)
    ap.add_argument("--candidate-frac", type=float, default=0.40)
    ap.add_argument("--max-attempts", type=int, default=4000)
    ap.add_argument("--tx-range", type=float, default=None, help="Override tx range (default: template value)")
    args = ap.parse_args()

    protocols = [p.strip().upper() for p in args.protocols.split(",") if p.strip()]
    densities = [d.strip().lower() for d in args.densities.split(",") if d.strip()]
    topo_seeds = parse_spec(args.topology_seeds)

    for d in densities:
        if d not in DENSITY_PROFILES:
            raise SystemExit(f"Unknown density {d!r}. Available: {', '.join(sorted(DENSITY_PROFILES))}")
    if not (0 <= args.attack_drop_pct <= 100):
        raise SystemExit(f"--attack-drop-pct must be in [0,100], got {args.attack_drop_pct}")

    template_info = parse_template_info(SCENARIOS_DIR / f"GRID6x6_{protocols[0]}.csc")
    for p in protocols[1:]:
        info = parse_template_info(SCENARIOS_DIR / f"GRID6x6_{p}.csc")
        if info["num_nodes"] != template_info["num_nodes"]:
            raise SystemExit(f"Template mismatch: {p} num_nodes={info['num_nodes']} != {template_info['num_nodes']}")

    num_nodes = template_info["num_nodes"]
    root_id = template_info["root_id"]
    attacker_count = pick_attack_count(template_info, args.attack_profile)
    if attacker_count <= 0:
        raise SystemExit(
            f"attack profile '{args.attack_profile}' selected but matching attacker count is 0 in templates"
        )
    tx_range = args.tx_range if args.tx_range is not None else template_info["tx_range"]

    out_dir = Path(args.out_dir).resolve()
    manifest_path = Path(args.manifest).resolve()

    manifest = {
        "version": 1,
        "generator": "scripts/generate_random_topologies.py",
        "num_nodes": num_nodes,
        "root_id": root_id,
        "attacker_count": attacker_count,
        "attack_profile": args.attack_profile,
        "attack_drop_pct": args.attack_drop_pct if args.attack_profile == "sinkhole_drop" else None,
        "tx_range": tx_range,
        "protocols": protocols,
        "densities": densities,
        "topology_seeds": topo_seeds,
        "topologies": [],
    }

    for density in densities:
        prof = DENSITY_PROFILES[density]
        for topo_seed in topo_seeds:
            rng = random.Random((topo_seed * 7919) + (sum(ord(c) for c in density) * 97))
            layout = sample_layout(
                num_nodes=num_nodes,
                root_id=root_id,
                attacker_count=attacker_count,
                tx_range=tx_range,
                width=prof["width"],
                height=prof["height"],
                degree_min=prof["degree_min"],
                degree_max=prof["degree_max"],
                min_distance=args.min_distance,
                candidate_frac=args.candidate_frac,
                max_attempts=args.max_attempts,
                rng=rng,
            )

            topo_name = f"topo_{topo_seed:03d}"
            record = {
                "density": density,
                "topology_seed": topo_seed,
                "topology_name": topo_name,
                "width": prof["width"],
                "height": prof["height"],
                "avg_degree": round(layout["avg_degree"], 4),
                "avg_hop_root": round(layout["avg_hop_root"], 4),
                "attacker_ids": layout["attackers"],
                "scenarios": {},
            }

            for proto in protocols:
                template = SCENARIOS_DIR / f"GRID6x6_{proto}.csc"
                out = out_dir / density / topo_name / f"RT_{proto}_{density}_{topo_name}.csc"
                write_csc_from_template(
                    template=template,
                    output=out,
                    coords=layout["coords"],
                    attackers=layout["attackers"],
                    root_id=root_id,
                    topo_seed=topo_seed,
                    density=density,
                    topo_index=topo_seed,
                    attack_profile=args.attack_profile,
                    attack_drop_pct=args.attack_drop_pct,
                )
                record["scenarios"][proto] = str(out.relative_to(ROOT))

            manifest["topologies"].append(record)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[OK] generated topologies: {len(manifest['topologies'])}")
    print(f"[OK] manifest: {manifest_path}")


if __name__ == "__main__":
    main()
