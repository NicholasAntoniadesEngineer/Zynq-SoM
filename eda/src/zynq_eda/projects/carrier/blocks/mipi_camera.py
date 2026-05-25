"""Carrier MIPI Camera block: 15-pin 1 mm FFC for an OV5640-class CSI-2 sensor.

The pinout mirrors the Raspberry Pi CM4 / Pi Zero camera connector
(15-pin 1.0 mm pitch FFC), which is the de-facto standard for hobby-
grade MIPI CSI-2 modules:

  * 2× MIPI data lanes (D0±, D1±) — 2-lane CSI-2 receive.
  * 1× MIPI clock pair (CLK±).
  * I2C control (SCL/SDA) for the sensor's register file.
  * Camera enable + main clock (24 MHz crystal driven by Zynq or local).
  * +3V3 + GND.

The Zynq receives the MIPI on PL bank 35 differential inputs at
LVDS_25 / TMDS_33 levels (no external MIPI PHY required for slow CSI-2
classes; faster sensors need a discrete MIPI receiver IC).
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_mipi_camera() -> Block:
    return Block(
        name="mipi_camera",
        title="MIPI Camera (15-pin 1 mm FFC, Pi-camera pinout)",
        paper_size="A4",
        description=(
            "Raspberry-Pi-compatible 15-pin MIPI CSI-2 camera connector. "
            "2-lane CSI-2 + clock at LVDS_25 to Zynq PL bank 35. I2C for "
            "sensor control, MCLK from carrier clock source."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["1.0-15P"],
                lib_id="zynq_eda:FFC_15P",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    ("1",  "GND"),
                    ("2",  "ZYNQ_CAM_MIPI_D0_N"),
                    ("3",  "ZYNQ_CAM_MIPI_D0_P"),
                    ("4",  "GND"),
                    ("5",  "ZYNQ_CAM_MIPI_D1_N"),
                    ("6",  "ZYNQ_CAM_MIPI_D1_P"),
                    ("7",  "GND"),
                    ("8",  "ZYNQ_CAM_MIPI_CLK_N"),
                    ("9",  "ZYNQ_CAM_MIPI_CLK_P"),
                    ("10", "GND"),
                    ("11", "ZYNQ_CAM_GPIO0"),       # camera reset / shutter
                    ("12", "ZYNQ_CAM_GPIO1"),       # power-down / strobe
                    ("13", "ZYNQ_CAM_SCL"),
                    ("14", "ZYNQ_CAM_SDA"),
                    ("15", "+3V3"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND",      edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_D0_P",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_D0_N",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_D1_P",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_D1_N",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_CLK_P", "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_MIPI_CLK_N", "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_GPIO0",      "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_GPIO1",      "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_SCL",        "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_CAM_SDA",        "bidirectional", edge=SheetEdge.LEFT),
        ),
    )
