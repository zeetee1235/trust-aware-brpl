#!/usr/bin/env python3
"""Generate relative-filter sweep variants on top of J580/W630 + baseline PRR."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"
LOSSES = ["LOSS90", "LOSS70", "LOSS50"]

VARIANTS = [
    {"proto": "TABRPL_REL_010", "comment": "Relative filter margin 10.", "rel_margin": 10},
    {"proto": "TABRPL_REL_020", "comment": "Relative filter margin 20.", "rel_margin": 20},
    {"proto": "TABRPL_REL_030", "comment": "Relative filter margin 30.", "rel_margin": 30},
    {"proto": "TABRPL_REL_040", "comment": "Relative filter margin 40.", "rel_margin": 40},
    {"proto": "TABRPL_REL_050", "comment": "Relative filter margin 50.", "rel_margin": 50},
    {"proto": "TABRPL_REL_075", "comment": "Relative filter margin 75.", "rel_margin": 75},
    {"proto": "TABRPL_REL_100", "comment": "Relative filter margin 100.", "rel_margin": 100},
]

MAKEFILE_TEMPLATE = """# Auto-generated relative-filter sweep variant
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
CFLAGS += -DTA_TFWD_SHARPEN_SCALE=1000
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
CFLAGS += -DBRPL_CONF_TRUST_LAMBDA_PENALTY=450
CFLAGS += -DTRUST_PENALTY_GAMMA_CONF=1
CFLAGS += -DBRPL_CONF_CURRENT_PARENT_PENALTY_SCALE=700
CFLAGS += -DTA_TRUST_RELATIVE_FILTER_ENABLE=1
CFLAGS += -DTA_TRUST_RELATIVE_PENALTY_ENABLE=1
CFLAGS += -DTA_TRUST_REL_MARGIN={rel_margin}
CFLAGS += -DTA_TRUST_REL_PENALTY_SCALE=1000
CFLAGS += -DTA_TRUST_REL_MAX_SOFT_PENALTY=400
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
