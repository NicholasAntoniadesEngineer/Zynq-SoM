"""Carrier SoM J2 mate — bank A: PL bank 13 differential pairs.

Sister to ``som_j2_se`` and ``som_j2_power``. Together the three banks
cover the FX10A 168-pin J2 SoM mate (PL bank 13). This bank carries the
high-speed differential pairs: FMC LA P/N pairs, HDMI TMDS, LVDS.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J2_DIFF``) carved out of the parent
``FX10A_168P`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses pins A1..A27 + B1..B27.
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


def build_som_j2_diff_pairs() -> Block:
    return Block(
        name="som_j2_diff_pairs",
        title="SoM Mate J2 bank A (PL bank 13 differential pairs)",
        paper_size="A3",
        description=(
            "Bank A of the J2 FX10A 168-pin SoM mate. Carries the high-"
            "speed differential pairs (LVDS_25 SelectIO) from PL bank 13: "
            "FMC LA P/N pairs (LA00..LA12), HDMI TX/RX TMDS pairs, "
            "LVDS LCD pairs. "
            "Pin map: parent FX10A pins A1..A27 + B1..B27."
        ),
        connectors=(
            ConnectorInstance(
                reference="J2A",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J2_DIFF:FX10A_168P_J2_DIFF",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j2_diff_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j2_diff_external_nets()),
    )


def _som_j2_diff_external_nets():
    yield PowerInputNet("+VCCO_13", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    # First 13 FMC LA diff pairs on this bank
    for index in range(13):
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_P", "bidirectional", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_N", "bidirectional", edge=SheetEdge.RIGHT)


def _som_j2_diff_pin_to_net() -> tuple[tuple[str, str], ...]:
    """First 13 FMC LA pairs on bank A (P pins on A column, N pins on B column)."""
    pairs: list[tuple[str, str]] = [
        ("A1", "+VCCO_13"), ("A2", "+VCCO_13"),
    ]
    pin_idx = 3
    for index in range(13):
        pairs.append((f"A{pin_idx}",   f"ZYNQ_FMC_LA{index:02d}_P"))
        pairs.append((f"B{pin_idx}",   f"ZYNQ_FMC_LA{index:02d}_N"))
        pin_idx += 1
    return tuple(pairs)
