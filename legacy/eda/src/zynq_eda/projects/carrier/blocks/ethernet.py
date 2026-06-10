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
        paper_size="A3",
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
                # Without these the magnetics' signal pins have no net and
                # are auto-NC'd — the PHY<->line datapath is electrically
                # OPEN (ERC-clean but non-functional). PHY-side pairs go to
                # the SoM PHY (ZYNQ_ETH_MDI_*); line-side pairs (TD*) go to
                # the RJ45 via ETH_LINE_MDI_* (J1 pin_to_net below uses the
                # same nets). CT_PAIR*/BS_COMMON stay cluster (Bob-Smith).
                net_overrides=(
                    ("PHY0_P", "ZYNQ_ETH_MDI_0_P"),
                    ("PHY0_N", "ZYNQ_ETH_MDI_0_N"),
                    ("PHY1_P", "ZYNQ_ETH_MDI_1_P"),
                    ("PHY1_N", "ZYNQ_ETH_MDI_1_N"),
                    ("PHY2_P", "ZYNQ_ETH_MDI_2_P"),
                    ("PHY2_N", "ZYNQ_ETH_MDI_2_N"),
                    ("PHY3_P", "ZYNQ_ETH_MDI_3_P"),
                    ("PHY3_N", "ZYNQ_ETH_MDI_3_N"),
                    ("TD0_P", "ETH_LINE_MDI_0_P"),
                    ("TD0_N", "ETH_LINE_MDI_0_N"),
                    ("TD1_P", "ETH_LINE_MDI_1_P"),
                    ("TD1_N", "ETH_LINE_MDI_1_N"),
                    ("TD2_P", "ETH_LINE_MDI_2_P"),
                    ("TD2_N", "ETH_LINE_MDI_2_N"),
                    ("TD3_P", "ETH_LINE_MDI_3_P"),
                    ("TD3_N", "ETH_LINE_MDI_3_N"),
                ),
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
                    # The RJHSE5380 symbol exposes the LED ANODES (LED1_A,
                    # LED2_A) and a single SHIELD pin — not LEDL+/-/SH1..4.
                    # Each LED anode is current-limited to +3V3 by the rj45
                    # refcircuit (series R) and driven (sunk) by the PHY LED
                    # output net; the shell bonds to CHASSIS_GND.
                    ("LED1_A", "ZYNQ_ETH_LED_LINK"),
                    ("LED2_A", "ZYNQ_ETH_LED_ACT"),
                    ("SHIELD", "CHASSIS_GND"),
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
