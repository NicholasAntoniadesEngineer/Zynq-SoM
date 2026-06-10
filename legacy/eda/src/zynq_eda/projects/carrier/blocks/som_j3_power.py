"""Carrier SoM J3 mate — bank C: PL bank 35 power + GND + camera ctrl.

Sister to ``som_j3_diff_pairs`` and ``som_j3_se``. This bank carries the
remaining VCCO_35 supply pins, the bulk of GND, and the MIPI camera
single-ended control signals (I2C, GPIOs).

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J3_POWER``) carved out of the parent
``FX10A_168P`` pin list. Uses pins A55..A84 + B55..B84.
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


def build_som_j3_power() -> Block:
    return Block(
        name="som_j3_power",
        title="SoM Mate J3 bank C (PL bank 35 power + camera ctrl)",
        paper_size="A3",
        description=(
            "Bank C of the J3 FX10A 168-pin SoM mate. Carries the bulk "
            "of VCCO_35 supply pins, GND, and the MIPI camera "
            "single-ended control signals (I2C SCL/SDA + GPIO0/GPIO1). "
            "Pin map: parent FX10A pins A55..A84 + B55..B84."
        ),
        connectors=(
            ConnectorInstance(
                reference="J3C",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J3_POWER:FX10A_168P_J3_POWER",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j3_power_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j3_power_external_nets()),
    )


def _som_j3_power_external_nets():
    yield PowerInputNet("+VCCO_35", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    for label in ("GPIO0", "GPIO1", "SCL", "SDA"):
        yield SignalNet(f"ZYNQ_CAM_{label}", "bidirectional", edge=SheetEdge.RIGHT)


def _som_j3_power_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [
        ("A55", "+VCCO_35"), ("A56", "+VCCO_35"),
        ("A57", "+VCCO_35"), ("A58", "+VCCO_35"),
        ("A59", "GND"),      ("A60", "GND"),
        ("A61", "GND"),      ("A62", "GND"),
        ("A63", "GND"),      ("A64", "GND"),
        # MIPI camera I2C + GPIO control
        ("B55", "ZYNQ_CAM_GPIO0"),
        ("B56", "ZYNQ_CAM_GPIO1"),
        ("B57", "ZYNQ_CAM_SCL"),
        ("B58", "ZYNQ_CAM_SDA"),
    ]
    return tuple(pairs)
