"""Carrier SoM J1 mate — bank A: PS MIO + system rails.

This is one of three sub-sheets that together cover the FX10A 168-pin
J1 SoM mate. The connector is too dense (168 pins on 0.5 mm pitch) to
render legibly on a single A3 sheet, so we split it across three banks
that share the same physical connector reference (J1A / J1B / J1C in
KiCad annotation).

BANK SPLIT MECHANISM
====================
We use distinct sub-symbols (one per bank) carved out of the parent
``FX10A_168P`` symbol's pin list. Each bank's KiCad symbol has the
parent's pin names and numbers preserved (so the footprint mapping is
identical) but only this bank's pins are drawn. All bank sub-symbols
share the same Value (``FX10A-168P-SV(91)``) and Footprint, so the BOM
emitter — keyed on (value, footprint) — collapses them to one BOM line
per physical connector.

Bank A: PS MIO (A1..A27 + B1..B27) — UART, USB0, I2C, SD1, GPIO.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
    PowerOutputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_som_j1_mio() -> Block:
    return Block(
        name="som_j1_mio",
        title="SoM Mate J1 bank A (PS MIO + system rails)",
        paper_size="A3",
        description=(
            "Bank A of the J1 FX10A 168-pin SoM mate. Routes Zynq PS MIO "
            "(UART0, USB0, I2C1, SD1, GPIO) and system rails (+VIN, +3V3). "
            "Pin map: parent FX10A pins A1..A27 + B1..B27. "
            "Sister sheets som_j1_ps_aux and som_j1_pl_power_gnd carry "
            "the remaining J1 pins; all share the same physical connector J1."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1A",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J1_MIO:FX10A_168P_J1_MIO",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j1_mio_pin_to_net(),
            ),
        ),
        external_nets=(
            PowerInputNet("+VIN",  edge=SheetEdge.RIGHT),
            PowerOutputNet("+3V3", edge=SheetEdge.RIGHT),
            GroundNet("GND",       edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_UART0_TXD",  "output",        edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_UART0_RXD",  "input",         edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_USB0_DP",    "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_USB0_DM",    "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_USB0_OTG_ID", "input",        edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_I2C1_SCL",   "output",        edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_I2C1_SDA",   "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_CLK",    "output",        edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_CMD",    "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_DAT0",   "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_DAT1",   "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_DAT2",   "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_DAT3",   "bidirectional", edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SD1_CD_N",   "input",         edge=SheetEdge.RIGHT),
            SignalNet("ZYNQ_PS_SRST_N",     "input",         edge=SheetEdge.RIGHT),
        ),
    )


def _som_j1_mio_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Pin map for bank A (representative subset; full map → io_assignment.csv)."""
    return (
        ("A1",  "+VIN"),  ("A2",  "+VIN"),
        ("A3",  "GND"),   ("A4",  "GND"),
        ("A5",  "+3V3"),  ("A6",  "+3V3"),
        ("B1",  "ZYNQ_PS_UART0_TXD"),
        ("B2",  "ZYNQ_PS_UART0_RXD"),
        ("B3",  "ZYNQ_PS_USB0_DP"),
        ("B4",  "ZYNQ_PS_USB0_DM"),
        ("B5",  "ZYNQ_PS_USB0_OTG_ID"),
        ("B6",  "ZYNQ_PS_I2C1_SCL"),
        ("B7",  "ZYNQ_PS_I2C1_SDA"),
        ("B8",  "ZYNQ_PS_SD1_CLK"),
        ("B9",  "ZYNQ_PS_SD1_CMD"),
        ("B10", "ZYNQ_PS_SD1_DAT0"),
        ("B11", "ZYNQ_PS_SD1_DAT1"),
        ("B12", "ZYNQ_PS_SD1_DAT2"),
        ("B13", "ZYNQ_PS_SD1_DAT3"),
        ("B14", "ZYNQ_PS_SD1_CD_N"),
        ("B15", "ZYNQ_PS_SRST_N"),
    )
