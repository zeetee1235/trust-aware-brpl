#!/usr/bin/env python3
"""Generate better-parent margin sweep variants on top of J580/W630 + PRR_BASE."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"
LOSSES = ["LOSS90", "LOSS70", "LOSS50"]

VARIANTS = [
    {
        "proto": "TABRPL_MGN_BASE",
        "comment": "Baseline better-parent trust margin.",
        "trust_margin": 50,
        "path_margin": 256,
    },
    {
        "proto": "TABRPL_MGN_RELAX1",
        "comment": "Slightly relaxed trust margin.",
        "trust_margin": 30,
        "path_margin": 256,
    },
    {
        "proto": "TABRPL_MGN_RELAX2",
        "comment": "Moderately relaxed trust margin.",
        "trust_margin": 15,
        "path_margin": 256,
    },
    {
        "proto": "TABRPL_MGN_RELAX3",
        "comment": "Aggressively relaxed trust margin.",
        "trust_margin": 0,
        "path_margin": 256,
    },
]

MAKEFILE_TEMPLATE = """# Auto-generated margin sweep variant
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
CFLAGS += -DTA_PRR_MIN=300
CFLAGS += -DTA_PRR_BLEND_WEIGHT=700
CFLAGS += -DTA_PRR_MAX=1000
CFLAGS += -DTA_TFWD_SHARPEN_SCALE=1400
CFLAGS += -DTA_TRUST_TAU_WARN=630
CFLAGS += -DTA_TRUST_TAU_JOIN=580
CFLAGS += -DTA_TRUST_TAU_BLACK=350
CFLAGS += -DTRUST_MIN=580
CFLAGS += -DTA_TRUST_RESTORE_ON_RELEASE=580
CFLAGS += -DTA_TRUST_ESCAPE_TRUST_THRESHOLD=630
CFLAGS += -DTA_TRUST_ESCAPE_CONSECUTIVE_UPDATES=2
CFLAGS += -DTA_TRUST_ESCAPE_COOLDOWN_SECONDS=180
CFLAGS += -DTA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT=1
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_TRUST_MARGIN={trust_margin}
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_PATH_MARGIN={path_margin}
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
