#!/usr/bin/env python3
"""Generate PRR-tuning variants on top of the J580/W630 baseline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"
LOSSES = ["LOSS90", "LOSS70", "LOSS50"]

VARIANTS = [
    {
        "proto": "TABRPL_PRR_BASE",
        "comment": "Baseline improved TA-BRPL (J580/W630).",
        "prr_min": 300,
        "prr_blend": 700,
        "prr_max": 1000,
        "sharpen": 1400,
    },
    {
        "proto": "TABRPL_PRR_RELAX",
        "comment": "Less aggressive PRR correction for low-loss recovery.",
        "prr_min": 260,
        "prr_blend": 600,
        "prr_max": 1000,
        "sharpen": 1250,
    },
    {
        "proto": "TABRPL_PRR_BAL",
        "comment": "Balanced blend with moderate cap.",
        "prr_min": 280,
        "prr_blend": 650,
        "prr_max": 950,
        "sharpen": 1350,
    },
    {
        "proto": "TABRPL_PRR_CAP",
        "comment": "Higher cap pressure to keep poor links from being over-excused.",
        "prr_min": 300,
        "prr_blend": 700,
        "prr_max": 920,
        "sharpen": 1450,
    },
    {
        "proto": "TABRPL_PRR_SEP",
        "comment": "Stronger separation bias for attacker-vs-normal T_fwd.",
        "prr_min": 320,
        "prr_blend": 750,
        "prr_max": 900,
        "sharpen": 1500,
    },
]

MAKEFILE_TEMPLATE = """# Auto-generated PRR sweep variant
# {comment}

CONTIKI_PROJECT = sender
all: $(CONTIKI_PROJECT)

CONTIKI = ../contiki-ng-brpl
MAKE_ROUTING = MAKE_ROUTING_RPL_CLASSIC

PROJECT_SOURCEFILES += ta-brpl-trust.c

CFLAGS += -DPROJECT_CONF_PATH=\\"../project-conf.h\\"
CFLAGS += -DBRPL_MODE=1
CFLAGS += -DTABRPL_MODE=1
CFLAGS += -DBRPL_CONF_TRUST_ENABLE=1
CFLAGS += -DCSV_VERBOSE_LOGGING=1
CFLAGS += -DTA_PRR_MIN={prr_min}
CFLAGS += -DTA_PRR_BLEND_WEIGHT={prr_blend}
CFLAGS += -DTA_PRR_MAX={prr_max}
CFLAGS += -DTA_TFWD_SHARPEN_SCALE={sharpen}
CFLAGS += -DTA_TRUST_TAU_WARN=630
CFLAGS += -DTA_TRUST_TAU_JOIN=580
CFLAGS += -DTA_TRUST_TAU_BLACK=350
CFLAGS += -DTRUST_MIN=580
CFLAGS += -DTA_TRUST_RESTORE_ON_RELEASE=580
CFLAGS += -DTA_TRUST_ESCAPE_TRUST_THRESHOLD=630
CFLAGS += -DTA_TRUST_ESCAPE_CONSECUTIVE_UPDATES=2
CFLAGS += -DTA_TRUST_ESCAPE_COOLDOWN_SECONDS=180
CFLAGS += -DTA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT=1
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_TRUST_MARGIN=50
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_PATH_MARGIN=256
LDLIBS += -lm

include $(CONTIKI)/Makefile.include
"""


def main() -> None:
    for variant in VARIANTS:
        proto = variant["proto"]
        makefile = MOTES / f"Makefile.{proto.lower()}"
        makefile.write_text(MAKEFILE_TEMPLATE.format(**variant), encoding="ascii")

        for loss in LOSSES:
            src = SCENARIOS / f"GRID6x6_TABRPL_LOSS{loss[4:]}.csc"
            dst = SCENARIOS / f"GRID6x6_{proto}_{loss}.csc"
            text = src.read_text(encoding="utf-8")
            text = text.replace("GRID6x6_TABRPL_", f"GRID6x6_{proto}_")
            text = text.replace("Makefile.tabrpl", f"Makefile.{proto.lower()}")
            text = text.replace("— TABRPL ", f"— {proto} ")
            dst.write_text(text, encoding="utf-8")

    print(",".join(v["proto"] for v in VARIANTS))


if __name__ == "__main__":
    main()
