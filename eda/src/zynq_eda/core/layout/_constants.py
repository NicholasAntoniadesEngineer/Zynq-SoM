"""Shared layout-engine constants and mapping tables."""

from __future__ import annotations

from zynq_eda.core.model.grid import snap_to_grid


# ---- Passive cluster geometry -----------------------------------------------

PASSIVE_PITCH_MM = snap_to_grid(5.08)
"""Vertical distance between two stacked passives on the same IC pin."""

PASSIVE_OFFSET_MM = snap_to_grid(10.16)
"""Distance from an IC pin to its nearest passive's anchor."""

PIN_TO_PASSIVE_NEAR_MM = snap_to_grid(2.54)
"""Gap between an IC pin endpoint and the passive's near terminal."""

PASSIVE_PIN_HALF = 3.81
"""Half the 7.62 mm pin-to-pin separation on Device:R/Device:C.

Pin 1 of a non-rotated Device:R is at (0, +3.81); pin 2 at (0, -3.81).
"""

POWER_SYMBOL_OFFSET_MM = snap_to_grid(5.08)
"""Distance from a passive's far terminal to its attached power symbol."""

INTERIOR_MARGIN_MM = snap_to_grid(15.24)
"""Minimum distance from a sheet edge to any placed item."""


# ---- Power-symbol library mapping ------------------------------------------

POWER_SYMBOL_LIB_IDS: dict[str, str] = {
    "GND":         "power:GND",
    "+VIN":        "power:+5V",
    "+VIN_IN":     "power:+5V",
    "+5V":         "power:+5V",
    "+3V3":        "power:+3V3",
    "+3V3_SC":     "power:+3V3",
    "+2V5":        "power:+2V5",
    "+1V8":        "power:+1V8",
    "+1V2":        "power:+1V2",
    "CHASSIS_GND": "power:Earth",
}
"""Maps canonical net names to KiCad power-symbol ``lib_id``s.

A net name not in this map is rendered as a local label instead of a
power-symbol attachment.
"""
