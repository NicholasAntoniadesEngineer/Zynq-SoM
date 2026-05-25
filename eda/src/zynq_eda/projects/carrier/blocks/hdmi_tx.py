"""Carrier HDMI Transmitter block: Zynq → TPD12S016 (ESD) → HDMI-A connector.

A standard HDMI 1.4 source path:

  * TPD12S016PWR provides ESD + level translation on the HDMI side
    (TMDS data 0..2 + clock, DDC SDA/SCL, CEC, +5V sense, HPD detect).
  * HDMI Type-A receptacle exposes the four TMDS pairs + auxiliary
    DDC/CEC/HPD/+5V to the host.
  * A 24LC256 EEPROM holds the EDID descriptor on the DDC bus (HDMI
    sources must respond to EDID reads even though the sink usually
    provides them — this carrier acts as a passthrough/source).

External nets the parent sheet supplies / consumes:

  * ``+3V3``, ``+5V``, ``GND`` — supplies.
  * ``ZYNQ_HDMI_TX_TMDS_{0,1,2}_{P,N}`` — TMDS data lanes (LVDS pairs).
  * ``ZYNQ_HDMI_TX_TMDS_CLK_{P,N}``       — TMDS pixel clock pair.
  * ``ZYNQ_HDMI_TX_CEC``, ``ZYNQ_HDMI_TX_HPD``, ``ZYNQ_HDMI_TX_SCL/SDA``.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_hdmi_tx() -> Block:
    return Block(
        name="hdmi_tx",
        title="HDMI Transmitter (Zynq → TPD12S016 → HDMI-A)",
        paper_size="A4",
        description=(
            "Zynq HDMI source via TPD12S016PWR ESD/level-translator and an "
            "HDMI Type-A receptacle. 24LC256 EEPROM holds the EDID payload "
            "on the DDC bus (per HDMI 1.4 Sec 8.1 / TPD12S016 DS Fig 13)."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["TPD12S016PWR_TX"],
                lib_id="zynq_eda:TPD12S016PWR",
                power_input_net="+3V3",
            ),
            IcInstance(
                reference="U2",
                refcircuit=REFCIRCUITS["24LC256T-I/SN_EDID"],
                lib_id="Memory_EEPROM:24LC256",
                power_input_net="+3V3",
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["HDMI_A"],
                lib_id="Connector_Generic:Conn_01x19",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    ("1",  "ZYNQ_HDMI_TX_TMDS_2_P"),
                    ("2",  "GND"),
                    ("3",  "ZYNQ_HDMI_TX_TMDS_2_N"),
                    ("4",  "ZYNQ_HDMI_TX_TMDS_1_P"),
                    ("5",  "GND"),
                    ("6",  "ZYNQ_HDMI_TX_TMDS_1_N"),
                    ("7",  "ZYNQ_HDMI_TX_TMDS_0_P"),
                    ("8",  "GND"),
                    ("9",  "ZYNQ_HDMI_TX_TMDS_0_N"),
                    ("10", "ZYNQ_HDMI_TX_TMDS_CLK_P"),
                    ("11", "GND"),
                    ("12", "ZYNQ_HDMI_TX_TMDS_CLK_N"),
                    ("13", "ZYNQ_HDMI_TX_CEC"),
                    ("14", "GND"),
                    ("15", "ZYNQ_HDMI_TX_SCL"),
                    ("16", "ZYNQ_HDMI_TX_SDA"),
                    ("17", "GND"),
                    ("18", "+5V"),
                    ("19", "ZYNQ_HDMI_TX_HPD"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            PowerInputNet("+5V",  edge=SheetEdge.LEFT),
            GroundNet("GND",      edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_0_P",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_0_N",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_1_P",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_1_N",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_2_P",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_2_N",    "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_CLK_P",  "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_TMDS_CLK_N",  "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_CEC",         "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_HPD",         "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_SCL",         "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_TX_SDA",         "bidirectional", edge=SheetEdge.LEFT),
        ),
    )
