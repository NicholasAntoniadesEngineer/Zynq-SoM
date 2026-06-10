"""Carrier FMC LPC expansion — bank B: high LA pairs (LA16..LA33).

Sister to ``fmc_lpc_la_low`` and ``fmc_lpc_power_clk_jtag``. This bank
carries the high-index LA pairs (LA16..LA33) from rows 22..33 of
columns C/D/G/H.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FMC_LPC_LA_HIGH``) carved out of the parent
``FMC_LPC`` pin list. Uses rows 22..33 of columns C/D/G/H.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


# VITA 57.1 LPC LA16..LA33 pin pairs (P pin, N pin).
_LA_PAIR_PIN_NUMBERS: list[tuple[str, str]] = [
    ("G18", "G19"),   # LA16  (overlaps row 19 but standard FMC says so)
    ("D20", "D21"),   # LA17
    ("C22", "C23"),   # LA18
    ("H22", "H23"),   # LA19
    ("G21", "G22"),   # LA20
    ("H25", "H26"),   # LA21
    ("G24", "G25"),   # LA22
    ("D23", "D24"),   # LA23
    ("H28", "H29"),   # LA24
    ("G27", "G28"),   # LA25
    ("D26", "D27"),   # LA26
    ("C26", "C27"),   # LA27
    ("H31", "H32"),   # LA28
    ("G30", "G31"),   # LA29
    ("H34", "H35"),   # LA30  - actually row 34 but kept here per spec
    ("G33", "G34"),   # LA31
    ("H37", "H38"),   # LA32
    ("G36", "G37"),   # LA33
]


def build_fmc_lpc_la_high() -> Block:
    return Block(
        name="fmc_lpc_la_high",
        title="FMC LPC bank B (LA16..LA33 differential pairs)",
        paper_size="A3",
        description=(
            "Bank B of the VITA 57.1 LPC FMC connector. Carries the "
            "high-index LA differential pairs LA16..LA33 (18 pairs) plus "
            "the paired GND pins from rows 22..33 of columns C/D/G/H."
        ),
        connectors=(
            ConnectorInstance(
                reference="J4B",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FMC_LPC_LA_HIGH:FMC_LPC_LA_HIGH",
                edge=SheetEdge.RIGHT,
                pin_to_net=_fmc_lpc_la_high_pin_to_net(),
            ),
        ),
        external_nets=tuple(_fmc_la_high_external_nets()),
    )


def _fmc_la_high_external_nets():
    yield GroundNet("GND", edge=SheetEdge.LEFT)
    for index in range(16, 34):
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_P", "bidirectional", edge=SheetEdge.LEFT)
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_N", "bidirectional", edge=SheetEdge.LEFT)


def _fmc_lpc_la_high_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    claimed: set[str] = set()
    for index, (p_pin, n_pin) in enumerate(_LA_PAIR_PIN_NUMBERS, start=16):
        pairs.append((p_pin, f"ZYNQ_FMC_LA{index:02d}_P"))
        pairs.append((n_pin, f"ZYNQ_FMC_LA{index:02d}_N"))
        claimed.add(p_pin)
        claimed.add(n_pin)
    gnd_candidates = (
        "C23", "C26", "C29", "C32",
        "D23", "D26", "D29",
        "G22", "G25", "G28", "G31",
        "H22", "H25", "H28", "H31",
    )
    for gnd_pin in gnd_candidates:
        if gnd_pin in claimed:
            continue
        pairs.append((gnd_pin, "GND"))
    return tuple(pairs)
