"""Carrier LVDS LCD block: 40-pin 0.5 mm FFC connector for an LVDS display.

Standard 4-lane single-channel LVDS panel interface (1024×768 up to
1366×768 at single-link rates). The 40-pin FFC carries:

  * 4× LVDS pairs (DA0..3 ±) — pixel data + sync.
  * 1× LVDS clock pair (CLK ±).
  * Backlight enable + PWM dimming.
  * I2C for EDID and DDC.
  * +5V / +3V3 / GND power.

The Zynq drives the LVDS via PL bank 13 SelectIO at 350 mV LVDS_25 levels.
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


def build_lvds_lcd() -> Block:
    return Block(
        name="lvds_lcd",
        title="LVDS LCD (40-pin 0.5 mm FFC)",
        paper_size="A4",
        description=(
            "Single-link LVDS panel interface on a 40-pin 0.5 mm FFC. "
            "4 data lanes + clock at 350 mV LVDS_25 from Zynq PL bank 13. "
            "Backlight enable + PWM + EDID I2C exposed to PS firmware."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["FPC-05F-40PH20"],
                lib_id="zynq_eda:FFC_40P",
                edge=SheetEdge.RIGHT,
                pin_to_net=_lvds_lcd_pin_to_net(),
            ),
        ),
        external_nets=tuple(_lvds_lcd_external_nets()),
    )


def _lvds_lcd_pin_to_net() -> tuple[tuple[str, str], ...]:
    """Common single-link LVDS LCD pinout (panel-specific variations exist)."""
    return (
        ("1",  "GND"),
        ("2",  "+3V3"),  # panel logic supply
        ("3",  "+3V3"),
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
        # Pins 27-34: backlight power (+12V), aggregated grounds.
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


def _lvds_lcd_external_nets():
    yield PowerInputNet("+3V3", edge=SheetEdge.LEFT)
    yield PowerInputNet("+12V", edge=SheetEdge.LEFT)
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
