"""Carrier SoM J3 mate — bank B: PL bank 35 single-ended GPIO.

Sister to ``som_j3_diff_pairs`` and ``som_j3_power``. This bank carries
the PMOD single-ended GPIOs and AUX GPIO breakout.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J3_SE``) carved out of the parent
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


def build_som_j3_se() -> Block:
    return Block(
        name="som_j3_se",
        title="SoM Mate J3 bank B (PL bank 35 single-ended GPIO)",
        paper_size="A3",
        description=(
            "Bank B of the J3 FX10A 168-pin SoM mate. Carries the PMOD "
            "GPIO pins (16 IOs across 2 slots) and the AUX GPIO breakout "
            "(16 IOs). "
            "Pin map: parent FX10A pins A28..A54 + B28..B54."
        ),
        connectors=(
            ConnectorInstance(
                reference="J3B",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J3_SE:FX10A_168P_J3_SE",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j3_se_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j3_se_external_nets()),
    )


def _som_j3_se_external_nets():
    yield PowerInputNet("+VCCO_35", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    for slot in range(2):
        for io in range(8):
            yield SignalNet(f"PMOD{slot}_IO{io}", "bidirectional", edge=SheetEdge.RIGHT)
    for index in range(16):
        yield SignalNet(f"AUX_IO_{index}", "bidirectional", edge=SheetEdge.RIGHT)


def _som_j3_se_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [
        ("A28", "+VCCO_35"), ("A29", "+VCCO_35"),
        ("A30", "GND"),      ("A31", "GND"),
    ]
    pin_idx = 32
    # PMOD IOs
    for slot in range(2):
        for io in range(8):
            pairs.append((f"A{pin_idx}", f"PMOD{slot}_IO{io}"))
            pin_idx += 1
    # AUX GPIO
    for index in range(16):
        pairs.append((f"B{pin_idx - 16 + index}", f"AUX_IO_{index}"))
    return tuple(pairs)
