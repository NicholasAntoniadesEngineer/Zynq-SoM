"""Carrier microSD block: Hirose DM3AT-SF-PEJM5 push-push socket on Zynq PS SD1.

A single microSD slot wired to the Zynq Processing System's SD1 controller
in 4-bit SDIO mode:

  * DAT0..DAT3 + CMD + CLK form the SDIO bus.
  * DAT3/CD doubles as the card-detect pin (DM3 pin 2). The dedicated
    mechanical card-detect switch on pins 9/10 (DET_A/DET_B) is brought
    out separately as ZYNQ_SD1_CD_N.
  * VDD is fed from +3V3 via the refcircuit's bulk + HF decoupling
    (4.7 µF + 100 nF) and DAT[0..3]/CMD are pulled up to VDD per the
    SD physical-layer spec.
  * SHIELD is tied to the carrier's main ground (chassis tie is handled
    by the USB-PD block).
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


def build_microsd() -> Block:
    """Return the microSD block (single DM3AT-SF-PEJM5 push-push socket)."""
    return Block(
        name="microsd",
        title="microSD Card Socket (DM3AT-SF-PEJM5 on Zynq PS SD1)",
        paper_size="A4",
        description=(
            "Hirose DM3AT push-push microSD socket wired to Zynq PS SD1 in "
            "4-bit SDIO mode. Card-detect uses the dedicated DET_A/DET_B "
            "mechanical switch (active-low to GND when card inserted). "
            "DAT[0..3]/CMD pull-ups and VDD decoupling come from the "
            "DM3AT refcircuit per SD Spec Part 1 Sec 6.3-6.5."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["DM3AT-SF-PEJM5"],
                lib_id="Connector:Micro_SD_Card_Det_Hirose_DM3AT",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    # SDIO bus pins (per Hirose DM3 pinout)
                    ("1", "ZYNQ_SD1_DAT2"),
                    ("2", "ZYNQ_SD1_DAT3"),    # DAT3/CD on DM3 — used as DAT3
                    ("3", "ZYNQ_SD1_CMD"),
                    ("4", "+3V3"),             # VDD
                    ("5", "ZYNQ_SD1_CLK"),
                    ("6", "GND"),              # VSS
                    ("7", "ZYNQ_SD1_DAT0"),
                    ("8", "ZYNQ_SD1_DAT1"),
                    # Mechanical card-detect switch (closes to GND when card in)
                    ("9", "ZYNQ_SD1_CD_N"),    # DET_B → host GPIO
                    ("10", "GND"),             # DET_A → GND
                    # Metal shield to GND
                    ("SH", "GND"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_DAT0", direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_DAT1", direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_DAT2", direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_DAT3", direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_CMD",  direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_CLK",  direction="output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_SD1_CD_N", direction="input",         edge=SheetEdge.LEFT),
        ),
    )
