"""Carrier SoM J1 mate — bank C: PL power + GND + configuration.

Sister to ``som_j1_mio`` and ``som_j1_ps_aux``. Together the three banks
cover the FX10A 168-pin J1 SoM mate; this bank carries the PL-side power
rails (+VCCO_*), the bulk of the GND pins, and PL configuration straps.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J1_PL_POWER``) carved out of the parent
``FX10A_168P`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses pins A55..A84 + B55..B84.
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


def build_som_j1_pl_power_gnd() -> Block:
    return Block(
        name="som_j1_pl_power_gnd",
        title="SoM Mate J1 bank C (PL power + GND + config)",
        paper_size="A3",
        description=(
            "Bank C of the J1 FX10A 168-pin SoM mate. Carries the SoM's "
            "PL-side power rails (+VCCO_13, +VCCO_34, +VCCO_35), the bulk "
            "of GND, and PL configuration / DONE / INIT pins. "
            "Pin map: parent FX10A pins A55..A84 + B55..B84. "
            "Sister sheets som_j1_mio and som_j1_ps_aux carry the "
            "remaining J1 pins; all share physical connector J1."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1C",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J1_PL_POWER:FX10A_168P_J1_PL_POWER",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j1_pl_power_gnd_pin_to_net(),
            ),
        ),
        external_nets=(
            PowerInputNet("+VCCO_13",      edge=SheetEdge.RIGHT),
            PowerInputNet("+VCCO_34",      edge=SheetEdge.RIGHT),
            PowerInputNet("+VCCO_35",      edge=SheetEdge.RIGHT),
            GroundNet("GND",               edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PL_DONE",      "output", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PL_INIT_B_N",  "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PL_PROG_B_N",  "input",  edge=SheetEdge.RIGHT),
        ),
    )


def _som_j1_pl_power_gnd_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Pin map for bank C (representative subset; full map → io_assignment.csv)."""
    return (
        ("A55", "+VCCO_13"), ("A56", "+VCCO_13"),
        ("A57", "+VCCO_34"), ("A58", "+VCCO_34"),
        ("A59", "+VCCO_35"), ("A60", "+VCCO_35"),
        ("A61", "GND"),      ("A62", "GND"),
        ("A63", "GND"),      ("A64", "GND"),
        ("B55", "ZYNQ_PL_DONE"),
        ("B56", "ZYNQ_PL_INIT_B_N"),
        ("B57", "ZYNQ_PL_PROG_B_N"),
    )
