#!/usr/bin/env python3
"""Generate link-loss x attack-drop sweep variants without touching core code.

- Link loss levels: 0%, 10%, 20%  -> success_ratio 1.0, 0.9, 0.8
- Attack drop levels: 0%, 30%, 50%, 70%, 100% -> ATTACK_DROP_PCT via attacker Makefile variants

This script only generates Makefile/scenario variants.
It does not modify TA-BRPL core implementation.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"

DEFAULT_PROTOCOLS = ["RPL", "BRPL", "SMTRUST", "TABRPL"]
LOSS_MAP = {
    0: 1.0,
    10: 0.9,
    20: 0.8,
}
DROP_LEVELS = [0, 30, 50, 70, 100]


def write_attacker_makefile(drop_pct: int) -> str:
    name = f"Makefile.attacker_d{drop_pct:03d}"
    path = MOTES / name
    text = f"""# Auto-generated attacker variant: ATTACK_DROP_PCT={drop_pct}

CONTIKI_PROJECT = attacker
all: $(CONTIKI_PROJECT)

CONTIKI = ../contiki-ng-brpl
MAKE_ROUTING = MAKE_ROUTING_RPL_CLASSIC

CFLAGS += -DPROJECT_CONF_PATH=\\\"../project-conf.h\\\"
CFLAGS += -DATTACK_DROP_PCT={drop_pct}
CFLAGS += -DATTACK_WARMUP_SECONDS=350
CFLAGS += -DCSV_VERBOSE_LOGGING=1

include $(CONTIKI)/Makefile.include
"""
    path.write_text(text, encoding="ascii")
    return name


def patch_scenario(proto: str, loss_pct: int, success_ratio: float, drop_pct: int, mk_attacker: str) -> Path:
    src = SCENARIOS / f"GRID6x6_{proto}.csc"
    if not src.exists():
        raise FileNotFoundError(src)

    dst = SCENARIOS / f"GRID6x6_{proto}_L{loss_pct:02d}_A{drop_pct:03d}.csc"
    tree = ET.parse(src)
    sim = tree.getroot().find("simulation")
    if sim is None:
        raise RuntimeError(f"invalid scenario: {src}")

    title = sim.find("title")
    if title is not None:
        base = (title.text or f"GRID6x6 {proto}").strip()
        title.text = f"{base} [L{loss_pct:02d} A{drop_pct:03d}]"

    tx = sim.find("radiomedium/success_ratio_tx")
    rx = sim.find("radiomedium/success_ratio_rx")
    if tx is not None:
        tx.text = f"{success_ratio:.1f}"
    if rx is not None:
        rx.text = f"{success_ratio:.1f}"

    for motetype in sim.findall("motetype"):
        ident = (motetype.findtext("identifier") or "").strip()
        if ident == "attacker_type":
            cmd = motetype.find("commands")
            if cmd is not None and cmd.text:
                cmd.text = cmd.text.replace("Makefile.attacker", mk_attacker)

    ET.indent(tree, space="  ")
    tree.write(dst, encoding="UTF-8", xml_declaration=True)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate LOSS x ATTACK_DROP scenario variants")
    ap.add_argument("--protocols", default=",".join(DEFAULT_PROTOCOLS), help="Comma-separated protocol list")
    ap.add_argument("--losses", default="0,10,20", help="Link loss percentages (comma-separated)")
    ap.add_argument("--drops", default="0,30,50,70,100", help="Attack drop percentages (comma-separated)")
    args = ap.parse_args()

    protocols = [p.strip().upper() for p in args.protocols.split(",") if p.strip()]
    losses = [int(x.strip()) for x in args.losses.split(",") if x.strip()]
    drops = [int(x.strip()) for x in args.drops.split(",") if x.strip()]

    for l in losses:
        if l not in LOSS_MAP:
            raise SystemExit(f"Unsupported loss {l}. Allowed: {sorted(LOSS_MAP.keys())}")
    for d in drops:
        if d < 0 or d > 100:
            raise SystemExit(f"Invalid drop {d}. Must be 0..100")

    created_mk = []
    created_scen = []
    for d in drops:
        mk = write_attacker_makefile(d)
        created_mk.append(mk)
        for l in losses:
            sr = LOSS_MAP[l]
            for p in protocols:
                out = patch_scenario(p, l, sr, d, mk)
                created_scen.append(out)

    print(f"[OK] makefiles: {len(created_mk)}")
    print(f"[OK] scenarios: {len(created_scen)}")


if __name__ == "__main__":
    main()
