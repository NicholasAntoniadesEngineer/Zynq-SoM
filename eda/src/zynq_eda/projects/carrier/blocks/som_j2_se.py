"""Carrier SoM J2 mate — bank B: PL bank 13 single-ended signals.

Sister to ``som_j2_diff_pairs`` and ``som_j2_power``. This bank carries
the remaining FMC LA pairs (LA13..LA33), the FMC differential clocks,
and the remaining single-ended HDMI control signals.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J2_SE``) carved out of the parent
``FX10A_168P`` pin list. Uses pins A28..A54 + B28..B54.
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


def build_som_j2_se() -> Block:
    return Block(
        name="som_j2_se",
        title="SoM Mate J2 bank B (PL bank 13 single-ended)",
        paper_size="A3",
        description=(
            "Bank B of the J2 FX10A 168-pin SoM mate. Carries remaining "
            "FMC LA pairs (LA13..LA33), FMC differential clocks "
            "(CLK0_M2C, CLK1_M2C), and HDMI control signals. "
            "Pin map: parent FX10A pins A28..A54 + B28..B54."
        ),
        connectors=(
            ConnectorInstance(
                reference="J2B",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J2_SE:FX10A_168P_J2_SE",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j2_se_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j2_se_external_nets()),
    )


def _som_j2_se_external_nets():
    yield PowerInputNet("+VCCO_13", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    for index in range(13, 34):
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_P", "bidirectional", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_N", "bidirectional", edge=SheetEdge.RIGHT)
    for label in ("CLK0_M2C_P", "CLK0_M2C_N", "CLK1_M2C_P", "CLK1_M2C_N"):
        yield SignalNet(f"ZYNQ_FMC_{label}", "input", edge=SheetEdge.RIGHT)


def _som_j2_se_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [
        ("A28", "+VCCO_13"), ("A29", "+VCCO_13"),
        ("A30", "GND"),      ("A31", "GND"),
    ]
    pin_idx = 32
    for index in range(13, 34):
        pairs.append((f"A{pin_idx}", f"ZYNQ_FMC_LA{index:02d}_P"))
        pairs.append((f"B{pin_idx}", f"ZYNQ_FMC_LA{index:02d}_N"))
        pin_idx += 1
    # FMC clock pairs (within the remaining A28..A54 range)
    pairs.extend((
        ("B53", "ZYNQ_FMC_CLK0_M2C_P"),
        ("B54", "ZYNQ_FMC_CLK0_M2C_N"),
        ("A53", "ZYNQ_FMC_CLK1_M2C_P"),
        ("A54", "ZYNQ_FMC_CLK1_M2C_N"),
    ))
    return tuple(pairs)
