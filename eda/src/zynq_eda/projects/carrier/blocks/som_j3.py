"""Carrier SoM J3 mate: PL bank 35 single-ended GPIO + auxiliary.

J3 of the Zynq SoM carries PL bank 35 GPIO. The carrier uses these for:

  * PMOD I/O (16 single-ended signals across 2 PMOD slots)
  * MIPI camera (2 lanes + clock — 6 differential signals)
  * AUX GPIO breakout (16 single-ended)
  * XADC analog inputs (VP/VN + 4 VAUX pairs)
  * User MRCC clock-capable pin (for an external clock source)

Bank 35 typically runs at +3V3 SelectIO (LVCMOS33) but can also do
LVDS_25 if VCCO_35 is dropped to +2V5 (for MIPI / LVDS inputs).
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


def build_som_j3() -> Block:
    return Block(
        name="som_j3",
        title="SoM Mate J3 (PL bank 35 single-ended + auxiliary)",
        paper_size="A3",
        description=(
            "Carrier-side mate to the Zynq SoM J3 connector "
            "(FX10A-168P-SV-91). PL bank 35 SelectIO routes to PMODs, "
            "MIPI camera, AUX GPIO, and XADC analog inputs."
        ),
        connectors=(
            ConnectorInstance(
                reference="J3",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="zynq_eda:FX10A_168P",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j3_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j3_external_nets()),
    )


def _som_j3_external_nets():
    yield PowerInputNet("+VCCO_35", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    # PMOD GPIO (2 slots × 8 IOs)
    for slot in range(2):
        for io in range(8):
            yield SignalNet(f"PMOD{slot}_IO{io}", "bidirectional", edge=SheetEdge.RIGHT)
    # MIPI camera differential pairs
    for label in ("D0_P", "D0_N", "D1_P", "D1_N", "CLK_P", "CLK_N"):
        yield SignalNet(f"ZYNQ_CAM_MIPI_{label}", "input", edge=SheetEdge.RIGHT)
    for label in ("GPIO0", "GPIO1", "SCL", "SDA"):
        yield SignalNet(f"ZYNQ_CAM_{label}", "bidirectional", edge=SheetEdge.RIGHT)
    # AUX GPIO breakout
    for index in range(16):
        yield SignalNet(f"AUX_IO_{index}", "bidirectional", edge=SheetEdge.RIGHT)
    # XADC analog
    yield SignalNet("ZYNQ_XADC_VP", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_XADC_VN", "input", edge=SheetEdge.RIGHT)
    for vaux in range(4):
        yield SignalNet(f"ZYNQ_XADC_VAUX{vaux}_P", "input", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_XADC_VAUX{vaux}_N", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_USER_MRCC_P", "input", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_USER_MRCC_N", "input", edge=SheetEdge.RIGHT)


def _som_j3_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Representative subset — full bank-35 pin schedule in io_assignment.csv."""
    pairs: list[tuple[str, str]] = [
        ("A1", "+VCCO_35"), ("A2", "+VCCO_35"),
        ("A3", "GND"),      ("A4", "GND"),
    ]
    pin_index = 5
    # PMOD IOs
    for slot in range(2):
        for io in range(8):
            pairs.append((f"A{pin_index}", f"PMOD{slot}_IO{io}"))
            pin_index += 1
    # XADC + MRCC
    for net in (
        "ZYNQ_XADC_VP", "ZYNQ_XADC_VN",
        "ZYNQ_USER_MRCC_P", "ZYNQ_USER_MRCC_N",
    ):
        pairs.append((f"A{pin_index}", net))
        pin_index += 1
    return tuple(pairs)
