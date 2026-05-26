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

This is the GLOBAL default. Refcircuits that need more space (dense
multi-pin × multi-slot networks like the HX5008 Bob-Smith — 4 pins ×
2 slots each, value-label collisions visible at 15.24 mm) can opt into
:data:`DENSE_HORIZONTAL_SWARM_PITCH_MM` via
``ReferenceCircuit.dense_swarm = True``. Doing it per-refcircuit
instead of globally avoids shifting connector-pin label rows on
unrelated sheets (FMC LPC, SoM-mate) where the 15.24 mm slot pitch
aligns with the root-sheet hierarchical-pin layout.
"""

DENSE_HORIZONTAL_SWARM_PITCH_MM = snap_to_grid(20.32)
"""Wider LEFT/RIGHT swarm pitch for refcircuits with packed value labels.

Used when ``ReferenceCircuit.dense_swarm`` is ``True``. 20.32 mm =
4 × 5.08 = 16 × grid adds 7.62 mm of clearance between adjacent
passive slots — enough for two value-text fields (e.g. "75R" + "1n"
side by side) to render without overlap. Increases cluster footprint
by ~33 % so it's opt-in per refcircuit, not the default.
"""

PASSIVE_OFFSET_MM = snap_to_grid(10.16)
"""Distance from an IC pin to its nearest passive's anchor."""

PASSIVE_ADJACENT_PIN_STAGGER_MM = snap_to_grid(5.08)
"""Extra perpendicular offset for caps on alternating-parity IC pin rows/cols.

When two adjacent IC pins (e.g. VCCA at Y=46.99 and VCCB at Y=49.53, 2.54 mm
apart on the same body side) each get a cluster cap, the caps' anchors
otherwise share the same X column for LEFT/RIGHT pins (or same Y row for
TOP/BOTTOM pins). At 2.54 mm pin pitch this packs the cap bodies + their
"Value" / "Reference" text labels too tightly — adjacent labels collide
and the parallel-plate cap symbols visually merge into one blob.

Solution: stagger by the IC pin's coordinate parity. Pins whose
``pin.y // 2.54`` (LEFT/RIGHT) or ``pin.x // 2.54`` (TOP/BOTTOM) is odd
get an extra ``PASSIVE_ADJACENT_PIN_STAGGER_MM`` added to their primary
(perpendicular-to-edge) offset. This places even-row and odd-row caps in
two distinct columns/rows, opening up enough whitespace for both bodies
and labels to read cleanly. 5.08 mm = 2 × grid keeps the layout tight
while guaranteeing the alternating caps' bounding boxes don't overlap.
"""

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
    # NOTE: +VIN no longer aliases to power:+5V. Aliasing two distinct nets
    # (+VIN and +5V) into one KiCad power-rail symbol made the root
    # sheet's per-net PWR_FLAGs collide on a single global net, triggering
    # pin_to_pin Power-out x Power-out errors. Treat +VIN as its own
    # custom rail with a root-level PWR_FLAG; +5V keeps its global symbol.
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
