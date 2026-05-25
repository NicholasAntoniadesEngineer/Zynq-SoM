"""Carrier HDMI Receiver block: HDMI-A → TPD12S016 (ESD) → Zynq.

Mirrors :mod:`hdmi_tx` but in the sink direction. The DDC EEPROM lives
on the SOURCE side (the upstream device); the carrier's sink only
needs to drive EDID back via I2C if it wants to advertise capabilities
— for now we leave the SCL/SDA pins as bidirectional and let the Zynq
implement EDID in firmware if needed.

No +5V output: the sink uses the +5V coming IN from the source as a
detection signal only (TPD12S016 has a 5V sense pin).
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_hdmi_rx() -> Block:
    return Block(
        name="hdmi_rx",
        title="HDMI Receiver (HDMI-A → TPD12S016 → Zynq)",
        paper_size="A4",
        description=(
            "Zynq HDMI sink via TPD12S016PWR. The +5V coming in from the "
            "source is sensed but not consumed (TPD12S016 isolates it). "
            "Per HDMI 1.4 Sec 8 the sink advertises EDID via the DDC bus "
            "— the carrier can implement EDID in Zynq PS firmware."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["TPD12S016PWR_RX"],
                lib_id="zynq_eda:TPD12S016PWR",
                power_input_net="+3V3",
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["HDMI_A"],
                lib_id="Connector:HDMI_A_Receptacle",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    ("1",  "ZYNQ_HDMI_RX_TMDS_2_P"),
                    ("2",  "GND"),
                    ("3",  "ZYNQ_HDMI_RX_TMDS_2_N"),
                    ("4",  "ZYNQ_HDMI_RX_TMDS_1_P"),
                    ("5",  "GND"),
                    ("6",  "ZYNQ_HDMI_RX_TMDS_1_N"),
                    ("7",  "ZYNQ_HDMI_RX_TMDS_0_P"),
                    ("8",  "GND"),
                    ("9",  "ZYNQ_HDMI_RX_TMDS_0_N"),
                    ("10", "ZYNQ_HDMI_RX_TMDS_CLK_P"),
                    ("11", "GND"),
                    ("12", "ZYNQ_HDMI_RX_TMDS_CLK_N"),
                    ("13", "ZYNQ_HDMI_RX_CEC"),
                    ("14", "GND"),
                    ("15", "ZYNQ_HDMI_RX_SCL"),
                    ("16", "ZYNQ_HDMI_RX_SDA"),
                    ("17", "GND"),
                    ("18", "ZYNQ_HDMI_RX_5V_SENSE"),
                    ("19", "ZYNQ_HDMI_RX_HPD"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND",      edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_0_P",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_0_N",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_1_P",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_1_N",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_2_P",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_2_N",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_CLK_P",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_TMDS_CLK_N",  "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_CEC",         "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_HPD",         "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_5V_SENSE",    "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_SCL",         "input",         edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_HDMI_RX_SDA",         "bidirectional", edge=SheetEdge.LEFT),
        ),
    )
