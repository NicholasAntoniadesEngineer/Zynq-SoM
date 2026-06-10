"""Carrier SoM J3 mate — bank A: PL bank 35 differential pairs.

Sister to ``som_j3_se`` and ``som_j3_power``. Together the three banks
cover the FX10A 168-pin J3 SoM mate (PL bank 35). This bank carries the
MIPI camera differential pairs and XADC differential analog inputs.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J3_DIFF``) carved out of the parent
``FX10A_168P`` pin list. Uses pins A1..A27 + B1..B27.
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


def build_som_j3_diff_pairs() -> Block:
    return Block(
        name="som_j3_diff_pairs",
        title="SoM Mate J3 bank A (PL bank 35 differential pairs)",
        paper_size="A3",
        description=(
            "Bank A of the J3 FX10A 168-pin SoM mate. Carries the MIPI "
            "camera differential pairs (D0_P/N, D1_P/N, CLK_P/N), XADC "
            "VAUX differential pairs, and the user MRCC clock pair. "
            "Pin map: parent FX10A pins A1..A27 + B1..B27."
        ),
        connectors=(
            ConnectorInstance(
                reference="J3A",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J3_DIFF:FX10A_168P_J3_DIFF",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j3_diff_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j3_diff_external_nets()),
    )


def _som_j3_diff_external_nets():
    yield PowerInputNet("+VCCO_35", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    for label in ("D0_P", "D0_N", "D1_P", "D1_N", "CLK_P", "CLK_N"):
        yield SignalNet(f"ZYNQ_CAM_MIPI_{label}", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_XADC_VP", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_XADC_VN", "input", edge=SheetEdge.RIGHT)
    for vaux in range(4):
        yield SignalNet(f"ZYNQ_XADC_VAUX{vaux}_P", "input", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_XADC_VAUX{vaux}_N", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_USER_MRCC_P", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_USER_MRCC_N", "input", edge=SheetEdge.RIGHT)


def _som_j3_diff_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [
        ("A1", "+VCCO_35"), ("A2", "+VCCO_35"),
        ("A3", "GND"),      ("A4", "GND"),
    ]
    # MIPI pairs
    pairs.extend((
        ("A5",  "ZYNQ_CAM_MIPI_D0_P"),  ("B5",  "ZYNQ_CAM_MIPI_D0_N"),
        ("A6",  "ZYNQ_CAM_MIPI_D1_P"),  ("B6",  "ZYNQ_CAM_MIPI_D1_N"),
        ("A7",  "ZYNQ_CAM_MIPI_CLK_P"), ("B7",  "ZYNQ_CAM_MIPI_CLK_N"),
    ))
    # XADC VP/VN
    pairs.extend((
        ("A8",  "ZYNQ_XADC_VP"),
        ("B8",  "ZYNQ_XADC_VN"),
    ))
    # XADC VAUX pairs
    pin_idx = 9
    for vaux in range(4):
        pairs.append((f"A{pin_idx}", f"ZYNQ_XADC_VAUX{vaux}_P"))
        pairs.append((f"B{pin_idx}", f"ZYNQ_XADC_VAUX{vaux}_N"))
        pin_idx += 1
    # User MRCC clock pair
    pairs.append((f"A{pin_idx}", "ZYNQ_USER_MRCC_P"))
    pairs.append((f"B{pin_idx}", "ZYNQ_USER_MRCC_N"))
    return tuple(pairs)
