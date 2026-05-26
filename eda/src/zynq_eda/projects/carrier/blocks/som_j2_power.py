"""Carrier SoM J2 mate — bank C: PL bank 13 power + GND + LVDS pairs.

Sister to ``som_j2_diff_pairs`` and ``som_j2_se``. This bank carries the
remaining VCCO_13 supply pins, the bulk of GND, and the LVDS LCD pairs.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FX10A_168P_J2_POWER``) carved out of the parent
``FX10A_168P`` pin list. Uses pins A55..A84 + B55..B84.
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


def build_som_j2_power() -> Block:
    return Block(
        name="som_j2_power",
        title="SoM Mate J2 bank C (PL bank 13 power + GND + LVDS)",
        paper_size="A3",
        description=(
            "Bank C of the J2 FX10A 168-pin SoM mate. Carries the bulk of "
            "VCCO_13 supply pins, GND, and the LVDS LCD differential pairs. "
            "Pin map: parent FX10A pins A55..A84 + B55..B84."
        ),
        connectors=(
            ConnectorInstance(
                reference="J2C",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FX10A_168P_J2_POWER:FX10A_168P_J2_POWER",
                edge=SheetEdge.LEFT,
                pin_to_net=_som_j2_power_pin_to_net(),
            ),
        ),
        external_nets=tuple(_som_j2_power_external_nets()),
    )


def _som_j2_power_external_nets():
    yield PowerInputNet("+VCCO_13", edge=SheetEdge.RIGHT)
    yield GroundNet("GND",          edge=SheetEdge.RIGHT)
    # HDMI TMDS pairs (TX + RX)
    for direction in ("TX", "RX"):
        for lane in range(3):
            yield SignalNet(
                f"ZYNQ_HDMI_{direction}_TMDS_{lane}_P", "bidirectional",
                edge=SheetEdge.RIGHT,
            )
            yield SignalNet(
                f"ZYNQ_HDMI_{direction}_TMDS_{lane}_N", "bidirectional",
                edge=SheetEdge.RIGHT,
            )
        yield SignalNet(f"ZYNQ_HDMI_{direction}_TMDS_CLK_P", "bidirectional", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_HDMI_{direction}_TMDS_CLK_N", "bidirectional", edge=SheetEdge.RIGHT)
    # LVDS LCD pairs
    for lane in range(4):
        yield SignalNet(f"ZYNQ_LCD_LVDS_DA{lane}_P", "output", edge=SheetEdge.RIGHT)
        yield SignalNet(f"ZYNQ_LCD_LVDS_DA{lane}_N", "output", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_LCD_LVDS_CLK_P", "output", edge=SheetEdge.RIGHT)
    yield SignalNet("ZYNQ_LCD_LVDS_CLK_N", "output", edge=SheetEdge.RIGHT)


def _som_j2_power_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = [
        ("A55", "+VCCO_13"), ("A56", "+VCCO_13"),
        ("A57", "+VCCO_13"), ("A58", "+VCCO_13"),
        ("A59", "GND"),      ("A60", "GND"),
        ("A61", "GND"),      ("A62", "GND"),
    ]
    pin_idx = 63
    # HDMI TX TMDS
    for lane in range(3):
        pairs.append((f"A{pin_idx}", f"ZYNQ_HDMI_TX_TMDS_{lane}_P"))
        pairs.append((f"B{pin_idx}", f"ZYNQ_HDMI_TX_TMDS_{lane}_N"))
        pin_idx += 1
    pairs.append((f"A{pin_idx}", "ZYNQ_HDMI_TX_TMDS_CLK_P"))
    pairs.append((f"B{pin_idx}", "ZYNQ_HDMI_TX_TMDS_CLK_N"))
    pin_idx += 1
    # HDMI RX TMDS
    for lane in range(3):
        pairs.append((f"A{pin_idx}", f"ZYNQ_HDMI_RX_TMDS_{lane}_P"))
        pairs.append((f"B{pin_idx}", f"ZYNQ_HDMI_RX_TMDS_{lane}_N"))
        pin_idx += 1
    pairs.append((f"A{pin_idx}", "ZYNQ_HDMI_RX_TMDS_CLK_P"))
    pairs.append((f"B{pin_idx}", "ZYNQ_HDMI_RX_TMDS_CLK_N"))
    pin_idx += 1
    # LVDS LCD
    for lane in range(4):
        pairs.append((f"A{pin_idx}", f"ZYNQ_LCD_LVDS_DA{lane}_P"))
        pairs.append((f"B{pin_idx}", f"ZYNQ_LCD_LVDS_DA{lane}_N"))
        pin_idx += 1
    pairs.append((f"A{pin_idx}", "ZYNQ_LCD_LVDS_CLK_P"))
    pairs.append((f"B{pin_idx}", "ZYNQ_LCD_LVDS_CLK_N"))
    return tuple(pairs)
