"""Carrier Ethernet block: Zynq PHY → HX5008NLT magnetics → RJHSE5380 RJ45.

The Zynq-7000's GEM (Gigabit Ethernet MAC) drives a 1000BASE-T PHY on
the SoM; this block sits between the PHY's MDI pairs and the RJ45 jack:

    Zynq RGMII (on SoM) → PHY (on SoM) →
        4 differential pairs (MDI[0..3]±) →
            HX5008NLT magnetics + Bob-Smith termination →
                RJHSE5380 RJ45 (with integrated LEDs)

The magnetics + Bob-Smith network (75 Ω + 1 nF to chassis GND) are
mandatory per IEEE 802.3 Sec 40.7 / Pulse HX5008NLT DS.

External nets:
  * ``+3V3``, ``GND``, ``CHASSIS_GND`` — supplies; CHASSIS_GND is the
    isolated frame-ground island that the Bob-Smith network terminates.
  * ``ZYNQ_ETH_MDI_{0..3}_{P,N}`` — the four MDI differential pairs.
  * ``ZYNQ_ETH_LED_{LINK,ACT}`` — RJ45 indicator-LED drives from PHY.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    ExternalNet,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_ethernet() -> Block:
    return Block(
        name="ethernet",
        title="Ethernet (PHY MDI → HX5008 magnetics → RJ45)",
        paper_size="A4",
        description=(
            "1000BASE-T Ethernet port: HX5008NLT integrated magnetics + "
            "Bob-Smith termination network drive an RJHSE5380 RJ45 with "
            "integrated LEDs. PHY lives on the SoM; this sheet handles "
            "the MDI side: magnetics, Bob-Smith, RJ45 mount, LED drives."
        ),
        ics=(
            IcInstance(
                reference="T1",
                refcircuit=REFCIRCUITS["HX5008NLT"],
                lib_id="zynq_eda:HX5008NLT",
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["RJHSE5380"],
                lib_id="zynq_eda:RJHSE5380",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    # MDI pairs land on the magnetics' line side first;
                    # the RJ45 pinout is wired from magnetics secondary.
                    ("1", "ETH_LINE_MDI_0_P"),
                    ("2", "ETH_LINE_MDI_0_N"),
                    ("3", "ETH_LINE_MDI_1_P"),
                    ("4", "ETH_LINE_MDI_2_P"),
                    ("5", "ETH_LINE_MDI_2_N"),
                    ("6", "ETH_LINE_MDI_1_N"),
                    ("7", "ETH_LINE_MDI_3_P"),
                    ("8", "ETH_LINE_MDI_3_N"),
                    ("LEDL+", "+3V3"),
                    ("LEDL-", "ZYNQ_ETH_LED_LINK"),
                    ("LEDR+", "+3V3"),
                    ("LEDR-", "ZYNQ_ETH_LED_ACT"),
                    ("SH1", "CHASSIS_GND"),
                    ("SH2", "CHASSIS_GND"),
                    ("SH3", "CHASSIS_GND"),
                    ("SH4", "CHASSIS_GND"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND",      edge=SheetEdge.LEFT),
            ExternalNet(
                name="CHASSIS_GND",
                direction="passive",
                edge=SheetEdge.LEFT,
                power_kind="ground",
            ),
            # PHY-side MDI pairs from the SoM-mate connector.
            SignalNet("ZYNQ_ETH_MDI_0_P",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_0_N",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_1_P",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_1_N",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_2_P",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_2_N",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_3_P",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_MDI_3_N",   "bidirectional", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_LED_LINK",  "output",        edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_ETH_LED_ACT",   "output",        edge=SheetEdge.LEFT),
        ),
    )
