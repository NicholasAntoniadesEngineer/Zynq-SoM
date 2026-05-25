"""Carrier SoM J1 mate: PS-side MIO + system rails.

J1 of the Zynq SoM (per the hand-authored SoM schematic at
``boards/som/Zynq_SoM.kicad_sch``) carries the Zynq PS MIO bank
plus the carrier's main power inlet (+VIN) and the system reset.

This block is the CARRIER-side mate (FX10A-168P-SV-91 connector). Pins
route to:

  * +VIN, +3V3, GND
  * Zynq PS UART0 (TXD/RXD to the CP2102 USB-UART bridge)
  * Zynq PS USB0 D±, OTG_ID  → USB-PD / USB-OTG sheets
  * Zynq PS I2C1 (SCL/SDA) → INA226 power monitor + FUSB302 I2C2
  * Zynq PS SD1 → microSD sheet
  * Zynq PS GPIO_0/1/2 → boot mode + reset
  * PS_SRST_N (system reset)

The exhaustive pin-by-pin map needs a parallel-sheet IO-assignment
pass derived from the SoM schematic; this block declares the contract
and a representative subset to validate sheet emission. Stage 8's
``io_assignment.csv`` is the authoritative source for the full map.
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
    PowerOutputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_som_j1() -> Block:
    return Block(
        name="som_j1",
        title="SoM Mate J1 (PS MIO + system rails)",
        paper_size="A4",
        description=(
            "Carrier-side mate to the Zynq SoM J1 connector "
            "(FX10A-168P-SV-91). Routes Zynq PS MIO + system rails + "
            "PS_SRST_N. Full pin map driven by io_assignment.csv."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="zynq_eda:FMC_LPC",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j1_pin_to_net(),
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


def _som_j1_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Representative subset; full map lives in io_assignment.csv."""
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
