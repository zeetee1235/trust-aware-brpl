#!/usr/bin/env python3
"""Generate TA-BRPL threshold-sweep Makefiles and Cooja scenarios.

This sweep keeps the Phase 3 forwarding / escape logic fixed and varies:
  - tau_join in {520, 540, 560, 580, 600}
  - tau_warn = tau_join + {30, 50, 70}

Generated protocol names look like:
  TABRPL_J520_W550
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTES = ROOT / "motes"
SCENARIOS = ROOT / "configs" / "scenarios"

JOINS = [520, 540, 560, 580, 600]
WARN_DELTAS = [30, 50, 70]
LOSSES = ["LOSS90", "LOSS70", "LOSS50"]

BASE_MAKEFILE = """# Auto-generated threshold sweep variant
# Phase 3 trust/escape logic with retuned tau_join / tau_warn.

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
CFLAGS += -DTA_TFWD_SHARPEN_SCALE=1400
CFLAGS += -DTA_TRUST_TAU_WARN={tau_warn}
CFLAGS += -DTA_TRUST_TAU_JOIN={tau_join}
CFLAGS += -DTA_TRUST_TAU_BLACK=350
CFLAGS += -DTRUST_MIN={tau_join}
CFLAGS += -DTA_TRUST_RESTORE_ON_RELEASE={tau_join}
CFLAGS += -DTA_TRUST_ESCAPE_TRUST_THRESHOLD={tau_warn}
CFLAGS += -DTA_TRUST_ESCAPE_CONSECUTIVE_UPDATES=2
CFLAGS += -DTA_TRUST_ESCAPE_COOLDOWN_SECONDS=180
CFLAGS += -DTA_TRUST_ESCAPE_REQUIRE_BETTER_PARENT=1
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_TRUST_MARGIN=50
CFLAGS += -DTA_TRUST_ESCAPE_BETTER_PATH_MARGIN=256
LDLIBS += -lm

include $(CONTIKI)/Makefile.include
"""


def protocol_name(tau_join: int, tau_warn: int) -> str:
    return f"TABRPL_J{tau_join}_W{tau_warn}"


def makefile_name(tau_join: int, tau_warn: int) -> str:
    return f"Makefile.tabrpl_j{tau_join}_w{tau_warn}"


def write_makefiles() -> list[str]:
    protocols = []
    for tau_join in JOINS:
        for delta in WARN_DELTAS:
            tau_warn = tau_join + delta
            proto = protocol_name(tau_join, tau_warn)
            makefile = MOTES / makefile_name(tau_join, tau_warn)
            makefile.write_text(
                BASE_MAKEFILE.format(tau_join=tau_join, tau_warn=tau_warn),
                encoding="ascii",
            )
            protocols.append(proto)
    return protocols


def write_scenarios(protocols: list[str]) -> None:
    for proto in protocols:
        parts = proto.split("_")
        tau_join = int(parts[1][1:])
        tau_warn = int(parts[2][1:])
        makefile = makefile_name(tau_join, tau_warn)
        for loss in LOSSES:
            src = SCENARIOS / f"GRID6x6_TABRPL_{loss}.csc"
            dst = SCENARIOS / f"GRID6x6_{proto}_{loss}.csc"
            text = src.read_text(encoding="utf-8")
            text = text.replace("GRID6x6_TABRPL_", f"GRID6x6_{proto}_")
            text = text.replace("Makefile.tabrpl", makefile)
            text = text.replace("— TABRPL ", f"— {proto} ")
            dst.write_text(text, encoding="utf-8")


def main() -> None:
    protocols = write_makefiles()
    write_scenarios(protocols)
    print(",".join(protocols))


if __name__ == "__main__":
    main()
