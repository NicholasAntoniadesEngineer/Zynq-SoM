"""Carrier FMC LPC expansion — bank A: low LA pairs (LA00..LA15).

Sister to ``fmc_lpc_la_high`` and ``fmc_lpc_power_clk_jtag``. Together
the three banks cover the VITA 57.1 LPC FMC connector. This bank carries
the low-index LA pairs (LA00..LA15) plus the paired GND pins in their row
neighbourhood (rows 1..21 of columns C/D/G/H).

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FMC_LPC_LA_LOW``) carved out of the parent
``FMC_LPC`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses rows 1..21 of columns C/D/G/H.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


# VITA 57.1 LPC LA00..LA15 pin pairs (P pin, N pin).
_LA_PAIR_PIN_NUMBERS: list[tuple[str, str]] = [
    ("G6",  "G7"),    # LA00
    ("D8",  "D9"),    # LA01
    ("H7",  "H8"),    # LA02
    ("G9",  "G10"),   # LA03
    ("H10", "H11"),   # LA04
    ("D11", "D12"),   # LA05
    ("C10", "C11"),   # LA06
    ("H13", "H14"),   # LA07
    ("G12", "G13"),   # LA08
    ("D14", "D15"),   # LA09
    ("C14", "C15"),   # LA10
    ("H16", "H17"),   # LA11
    ("G15", "G16"),   # LA12
    ("D17", "D18"),   # LA13
    ("C18", "C19"),   # LA14
    ("H19", "H20"),   # LA15
]


def build_fmc_lpc_la_low() -> Block:
    return Block(
        name="fmc_lpc_la_low",
        title="FMC LPC bank A (LA00..LA15 differential pairs)",
        paper_size="A3",
        description=(
            "Bank A of the VITA 57.1 LPC FMC connector. Carries the "
            "low-index LA differential pairs LA00..LA15 (16 pairs) plus "
            "the paired GND pins from rows 1..21 of columns C/D/G/H."
        ),
        connectors=(
            ConnectorInstance(
                reference="J4A",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FMC_LPC_LA_LOW:FMC_LPC_LA_LOW",
                edge=SheetEdge.RIGHT,
                pin_to_net=_fmc_lpc_la_low_pin_to_net(),
            ),
        ),
        external_nets=tuple(_fmc_la_low_external_nets()),
    )


def _fmc_la_low_external_nets():
    yield GroundNet("GND", edge=SheetEdge.LEFT)
    for index in range(16):
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_P", "bidirectional", edge=SheetEdge.LEFT)
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_N", "bidirectional", edge=SheetEdge.LEFT)


def _fmc_lpc_la_low_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    claimed: set[str] = set()
    for index, (p_pin, n_pin) in enumerate(_LA_PAIR_PIN_NUMBERS):
        pairs.append((p_pin, f"ZYNQ_FMC_LA{index:02d}_P"))
        pairs.append((n_pin, f"ZYNQ_FMC_LA{index:02d}_N"))
        claimed.add(p_pin)
        claimed.add(n_pin)
    # GND candidates within rows 1..21 (per VITA 57.1) that aren't LA pair pins.
    gnd_candidates = (
        "C1", "C2", "C5", "C8", "C11", "C14", "C17", "C20",
        "D1", "D2", "D5", "D11", "D14", "D17", "D20",
        "G1", "G4", "G10", "G13", "G16", "G19",
        "H1", "H10", "H13", "H16", "H19",
    )
    for gnd_pin in gnd_candidates:
        if gnd_pin in claimed:
            continue
        pairs.append((gnd_pin, "GND"))
    return tuple(pairs)
