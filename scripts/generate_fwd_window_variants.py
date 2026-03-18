#!/usr/bin/env python3
"""Generate sliding-window T_fwd variants for TA-BRPL."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"
LOSSES = ["LOSS100", "LOSS90", "LOSS70", "LOSS50"]

VARIANTS = [
    {
        "proto": "TABRPL_FWDW05",
        "comment": "TA-BRPL with sliding-window forwarding trust, window=5 sends.",
        "window": 5,
    },
    {
        "proto": "TABRPL_FWDW08",
        "comment": "TA-BRPL with sliding-window forwarding trust, window=8 sends.",
        "window": 8,
    },
    {
        "proto": "TABRPL_FWDW10",
        "comment": "TA-BRPL with sliding-window forwarding trust, window=10 sends.",
        "window": 10,
    },
]

MAKEFILE_TEMPLATE = """# Auto-generated sliding-window T_fwd variant
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
CFLAGS += -DTA_TRUST_FWD_WINDOW_ENABLE=1
CFLAGS += -DTA_TRUST_FWD_WINDOW_SIZE={window}
LDLIBS += -lm

include $(CONTIKI)/Makefile.include
"""


def main() -> None:
    for variant in VARIANTS:
        proto = variant["proto"]
        makefile = MOTES / f"Makefile.{proto.lower()}"
        makefile.write_text(MAKEFILE_TEMPLATE.format(**variant), encoding="ascii")

        for loss in LOSSES:
            src = SCENARIOS / f"GRID6x6_TABRPL_{loss}.csc"
            dst = SCENARIOS / f"GRID6x6_{proto}_{loss}.csc"
            text = src.read_text(encoding="utf-8")
            text = text.replace("GRID6x6_TABRPL_", f"GRID6x6_{proto}_")
            text = text.replace("Makefile.tabrpl", f"Makefile.{proto.lower()}")
            text = text.replace("— TABRPL ", f"— {proto} ")
            text = text.replace("Sender (TABRPL)", f"Sender ({proto})")
            dst.write_text(text, encoding="utf-8")

    print(",".join(v["proto"] for v in VARIANTS))


if __name__ == "__main__":
    main()
