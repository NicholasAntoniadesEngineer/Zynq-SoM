"""Shared layout-engine constants and mapping tables."""

from __future__ import annotations

from zynq_eda.core.model.grid import snap_to_grid


# ---- Passive cluster geometry -----------------------------------------------

PASSIVE_PITCH_MM = snap_to_grid(5.08)
"""Lateral pitch between adjacent passives in a TOP/BOTTOM swarm.

For passives placed above or below an IC pin, the swarm fans laterally
(each slot is one column wider in X). 5.08 mm = 2 × KiCad grid keeps
adjacent passives visually distinct without consuming too much sheet
real estate. This pitch is NOT used for LEFT/RIGHT swarms — those need
more clearance per slot to avoid collisions; see
:data:`HORIZONTAL_SWARM_PITCH_MM`.
"""

HORIZONTAL_SWARM_PITCH_MM = snap_to_grid(15.24)
"""Pitch between adjacent passives in a LEFT/RIGHT swarm.

Each slot must clear its predecessor's full footprint: the cap body
(2 × :data:`PASSIVE_PIN_HALF` = 7.62 mm pin-to-pin), plus the wire to
the destination's power symbol (:data:`POWER_SYMBOL_OFFSET_MM` =
5.08 mm), plus at least one grid unit of visual gap. 15.24 mm =
3 × 5.08 = 12 × grid leaves a 2.54 mm air gap between slot N-1's
power symbol and slot N's near pin — anything smaller and the
endpoints land on top of each other and KiCad merges them into one
net, shorting GND to whatever slot N's destination is.
"""

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
