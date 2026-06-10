"""Carrier LVDS LCD — bank A: data + clock + backlight control signals.

Sister to ``lvds_lcd_power``. Together the two banks cover the 40-pin
0.5 mm FFC connector that carries a single-link LVDS panel interface.
This bank carries the LVDS data + clock pairs, the EDID I2C, backlight
control signals, and the panel reset/standby.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FFC_40P_LVDS_SIGNALS``) carved out of the parent
``FFC_40P`` pin list. See ``som_j1_mio.py`` for the full mechanism
description; this file uses pins 4..26.
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


def build_lvds_lcd_signals() -> Block:
    return Block(
        name="lvds_lcd_signals",
        title="LVDS LCD bank A (data + clock + backlight ctrl)",
        paper_size="A3",
        description=(
            "Bank A of the 40-pin 0.5 mm LVDS LCD FFC connector. Carries "
            "the LVDS data pairs (DA0..DA3 ±), LVDS clock pair (CLK ±), "
            "EDID I2C, backlight enable + PWM, and the panel reset/standby. "
            "Pin map: parent FFC_40P pins 4..26."
        ),
        connectors=(
            ConnectorInstance(
                reference="J5A",
                refcircuit=REFCIRCUITS["FPC-05F-40PH20"],
                lib_id="FFC_40P_LVDS_SIGNALS:FFC_40P_LVDS_SIGNALS",
                edge=SheetEdge.RIGHT,
                pin_to_net=_lvds_lcd_signals_pin_to_net(),
            ),
        ),
        external_nets=tuple(_lvds_lcd_signals_external_nets()),
    )


def _lvds_lcd_signals_external_nets():
    yield GroundNet("GND",      edge=SheetEdge.LEFT)
    for lane in range(4):
        yield SignalNet(f"ZYNQ_LCD_LVDS_DA{lane}_P", "output", edge=SheetEdge.LEFT)
        yield SignalNet(f"ZYNQ_LCD_LVDS_DA{lane}_N", "output", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_LVDS_CLK_P", "output", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_LVDS_CLK_N", "output", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_EDID_SCL",   "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_EDID_SDA",   "bidirectional", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_RESET_N",    "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_STBY_N",     "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_PWM",        "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_LCD_BL_EN",      "output",        edge=SheetEdge.LEFT)


def _lvds_lcd_signals_pin_to_net() -> tuple[tuple[str, str], ...]:
    return (
        ("4",  "ZYNQ_LCD_EDID_SDA"),
        ("5",  "ZYNQ_LCD_EDID_SCL"),
        ("6",  "GND"),
        ("7",  "ZYNQ_LCD_LVDS_CLK_N"),
        ("8",  "ZYNQ_LCD_LVDS_CLK_P"),
        ("9",  "GND"),
        ("10", "ZYNQ_LCD_LVDS_DA0_N"),
        ("11", "ZYNQ_LCD_LVDS_DA0_P"),
        ("12", "GND"),
        ("13", "ZYNQ_LCD_LVDS_DA1_N"),
        ("14", "ZYNQ_LCD_LVDS_DA1_P"),
        ("15", "GND"),
        ("16", "ZYNQ_LCD_LVDS_DA2_N"),
        ("17", "ZYNQ_LCD_LVDS_DA2_P"),
        ("18", "GND"),
        ("19", "ZYNQ_LCD_LVDS_DA3_N"),
        ("20", "ZYNQ_LCD_LVDS_DA3_P"),
        ("21", "GND"),
        ("22", "ZYNQ_LCD_RESET_N"),
        ("23", "GND"),
        ("24", "ZYNQ_LCD_STBY_N"),
        ("25", "ZYNQ_LCD_PWM"),
        ("26", "ZYNQ_LCD_BL_EN"),
    )
