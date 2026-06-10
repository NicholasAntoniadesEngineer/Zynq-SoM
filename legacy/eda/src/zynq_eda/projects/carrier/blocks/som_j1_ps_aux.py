"""Carrier SoM J1 mate — bank B: PS DDR straps, clk, reset, JTAG.

Sister to ``som_j1_mio`` and ``som_j1_pl_power_gnd``. Together the three
banks cover the FX10A 168-pin J1 SoM mate; this bank carries the PS
DDR-strap signals, clock pins, JTAG, and the system reset.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J1_PS_AUX``) carved out of the parent
``FX10A_168P`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses pins A28..A54 + B28..B54.
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


def build_som_j1_ps_aux() -> Block:
    return Block(
        name="som_j1_ps_aux",
        title="SoM Mate J1 bank B (PS auxiliary: clk, JTAG, DDR straps)",
        paper_size="A3",
        description=(
            "Bank B of the J1 FX10A 168-pin SoM mate. Routes Zynq PS "
            "auxiliary signals: PS_CLK reference, DDR strap pins, JTAG "
            "passthrough, and configuration-mode pins. "
            "Pin map: parent FX10A pins A28..A54 + B28..B54. "
            "Sister sheets som_j1_mio and som_j1_pl_power_gnd carry "
            "the remaining J1 pins; all share physical connector J1."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1B",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J1_PS_AUX:FX10A_168P_J1_PS_AUX",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j1_ps_aux_pin_to_net(),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3",          edge=SheetEdge.RIGHT),
            GroundNet("GND",               edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_PS_CLK",    "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_POR_B_N",   "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_TCK",       "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_TDI",       "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_TDO",       "output", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_TMS",       "input",  edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_MIO_BOOT_0", "input", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_MIO_BOOT_1", "input", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_MIO_BOOT_2", "input", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_MIO_BOOT_3", "input", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_MIO_BOOT_4", "input", edge=SheetEdge.RIGHT),
        ),
    )


def _som_j1_ps_aux_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Pin map for bank B (representative subset; full map → io_assignment.csv)."""
    return (
        ("A28", "+3V3"),  ("A29", "+3V3"),
        ("A30", "GND"),   ("A31", "GND"),
        ("B28", "ZYNQ_PS_PS_CLK"),
        ("B29", "ZYNQ_PS_POR_B_N"),
        ("B30", "ZYNQ_PS_TCK"),
        ("B31", "ZYNQ_PS_TDI"),
        ("B32", "ZYNQ_PS_TDO"),
        ("B33", "ZYNQ_PS_TMS"),
        ("B34", "ZYNQ_PS_MIO_BOOT_0"),
        ("B35", "ZYNQ_PS_MIO_BOOT_1"),
        ("B36", "ZYNQ_PS_MIO_BOOT_2"),
        ("B37", "ZYNQ_PS_MIO_BOOT_3"),
        ("B38", "ZYNQ_PS_MIO_BOOT_4"),
    )
