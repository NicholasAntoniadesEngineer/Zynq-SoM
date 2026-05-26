"""Carrier LVDS LCD — bank B: panel power + backlight power + GND.

Sister to ``lvds_lcd_signals``. This bank carries the +3V3 panel logic
supply, +12V backlight power, and the aggregated GND pins (FFC pins 1-3
and 27-40).

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FFC_40P_LVDS_POWER``) carved out of the parent
``FFC_40P`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses pins 1-3 + 27-40.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_lvds_lcd_power() -> Block:
    return Block(
        name="lvds_lcd_power",
        title="LVDS LCD bank B (panel + backlight power)",
        paper_size="A4",
        description=(
            "Bank B of the 40-pin 0.5 mm LVDS LCD FFC connector. Carries "
            "the +3V3 panel logic supply, +12V backlight power, and the "
            "aggregated GND pins. "
            "Pin map: parent FFC_40P pins 1-3 + 27-40."
        ),
        connectors=(
            ConnectorInstance(
                reference="J5B",
                refcircuit=REFCIRCUITS["FPC-05F-40PH20"],
                lib_id="FFC_40P_LVDS_POWER:FFC_40P_LVDS_POWER",
                edge=SheetEdge.RIGHT,
                pin_to_net=_lvds_lcd_power_pin_to_net(),
            ),
        ),
        external_nets=tuple(_lvds_lcd_power_external_nets()),
    )


def _lvds_lcd_power_external_nets():
    yield PowerInputNet("+3V3", edge=SheetEdge.LEFT)
    yield PowerInputNet("+12V", edge=SheetEdge.LEFT)
    yield GroundNet("GND",      edge=SheetEdge.LEFT)


def _lvds_lcd_power_pin_to_net() -> tuple[tuple[str, str], ...]:
    return (
        ("1",  "GND"),
        ("2",  "+3V3"),
        ("3",  "+3V3"),
        ("27", "+12V"),
        ("28", "+12V"),
        ("29", "+12V"),
        ("30", "+12V"),
        ("31", "GND"),
        ("32", "GND"),
        ("33", "GND"),
        ("34", "GND"),
        ("35", "GND"),
        ("36", "GND"),
        ("37", "GND"),
        ("38", "GND"),
        ("39", "GND"),
        ("40", "GND"),
    )
