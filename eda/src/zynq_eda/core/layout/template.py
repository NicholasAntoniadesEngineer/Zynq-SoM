"""Carrier-wide layout template — the SINGLE SOURCE OF TRUTH.

Every symbol, every cluster, every label position derives from the
constants in this module. The intent is a scalable system with clear
rules where:

  1. **Every label is visible** — nothing hidden, no ``(hide yes)``
     on pin names or pin numbers anywhere.
  2. **No text overlaps anything** — pin name, pin number, our net
     label, wire, symbol body. Bbox-based collision detection at
     emit time enforces this, and the placement engine uses the
     same template numbers to lay things out so collisions don't
     happen in the first place.
  3. **All parts share the same base** — every custom symbol uses
     the same pin pitch, same pin-name offset, same text size, same
     stub length. Generators (the bank-symbol extractor, future
     synthesised symbols) read from this module too.

Why the values are what they are:

  * Pin pitch 5.08 mm = 2 × KiCad grid: at the default 1.27 mm font
    height (~1.9 mm text bbox including descender) this leaves
    ≥3.18 mm clear gap between adjacent rows. Pin name + pin number
    + our PlacedLabel all fit on the row without their bboxes
    touching the next row's text.
  * Pin name offset 1.016 mm = KiCad default. Smaller offsets push
    the pin name onto the pin stub; larger offsets push it past the
    body edge.
  * Stub length 2.54 mm: the gap between a connector pin's tip and
    our net label's anchor. Long enough for the intrinsic pin
    number (~1.5 mm bbox) to fit between the tip and the body edge
    without overlapping our outboard label.
  * Body half-width 12.7 mm: the typical IC body holds the pin-name
    text plus ~3 mm padding inside the rectangle. A connector pin
    name like ``FMC_LA00_P`` (10 chars × 0.76 mm ≈ 7.6 mm wide)
    fits with margin.
  * Cap chain clearance 29.21 mm: PASSIVE_OFFSET (10.16) + parity
    stagger (5.08) + cap body half (3.81) + power-symbol stub
    (5.08) + 5.08 safety = the maximum vertical extent a TOP-side
    decoupling cap chain reaches above its parent IC's anchor.
"""

from __future__ import annotations

from zynq_eda.core.model.grid import snap_to_grid


# ---------------------------------------------------------------------------
# 1. Pin geometry — every symbol uses these.
# ---------------------------------------------------------------------------

PIN_PITCH_MM: float = snap_to_grid(5.08)
"""Vertical spacing between adjacent pins on a column.

All custom carrier symbols MUST use this pitch. KiCad's default is
2.54 mm but at the default 1.27 mm font that crowds pin-name text
into adjacent rows on dense connectors (USB-C, FX10A, FFC). 5.08 mm
gives clear vertical separation.
"""

PIN_LENGTH_MM: float = snap_to_grid(2.54)
"""Length of the visible pin stub from body edge to pin tip."""

PIN_NAME_OFFSET_MM: float = 1.016
"""Distance from pin tip into the body where the pin NAME text anchors.

KiCad's stock default; set explicitly in every symbol's
``(pin_names (offset 1.016) ...)`` directive so the rendering is
identical across symbols regardless of who authored them.
"""

# ---------------------------------------------------------------------------
# 2. Text rendering — what KiCad will paint.
# ---------------------------------------------------------------------------

TEXT_SIZE_MM: float = 1.27
"""Default text height for ALL labels: pin names, pin numbers,
PlacedLabel, PlacedHierarchicalLabel, value/reference fields.
"""

TEXT_WIDTH_PER_CHAR_RATIO: float = 0.6
"""Approximate character width as fraction of text height (KiCad's
default stroke font). Used by the bbox computation to size the text
collision box. Slight over-estimate is preferred (catches near-misses)
to under-estimate (misses real visual overlaps).
"""

TEXT_HEIGHT_RATIO: float = 1.5
"""Total text-box vertical extent as fraction of nominal size (cap +
descender)."""

TEXT_CLEARANCE_MM: float = snap_to_grid(1.27)
"""Minimum clear distance between any two distinct text bboxes."""

# ---------------------------------------------------------------------------
# 3. Symbol body proportions.
# ---------------------------------------------------------------------------

BODY_HALF_WIDTH_MIN_MM: float = snap_to_grid(12.7)
"""Minimum horizontal half-width of a symbol body rectangle.

Sized to hold the longest typical pin name (~12 chars ≈ 9 mm at the
0.6×1.27 width-per-char) plus ~3 mm padding inside the rectangle.
Symbols with longer pin names should override with a larger half-
width; smaller symbols (passives, single-pin devices) ignore this
floor.
"""

BODY_HEIGHT_PADDING_MM: float = snap_to_grid(2.54)
"""Vertical padding added to the symbol body beyond the topmost and
bottom-most pin Y positions. Equals one KiCad grid unit so the body
rectangle visibly contains the pins."""

# ---------------------------------------------------------------------------
# 4. Cluster passive layout — every IC's decoupling/pull-up cluster
#    uses these numbers (already in _constants.py — re-exported here
#    so callers reading the template see all related values).
# ---------------------------------------------------------------------------

PASSIVE_OFFSET_MM: float = snap_to_grid(10.16)
"""Distance from an IC pin tip to its first passive's anchor."""

PASSIVE_SWARM_PITCH_MM: float = snap_to_grid(15.24)
"""Default lateral pitch between adjacent slots on a LEFT/RIGHT swarm."""

PASSIVE_DENSE_SWARM_PITCH_MM: float = snap_to_grid(20.32)
"""Wider lateral pitch for refcircuits opting into ``dense_swarm=True``."""

PASSIVE_PIN_HALF_MM: float = 3.81
"""Half the pin-to-pin distance on a standard Device:R/Device:C
(7.62 mm pin pitch on the stock KiCad passive)."""

CAP_CHAIN_CLEARANCE_MM: float = snap_to_grid(29.21)
"""Maximum vertical extent of a TOP-side decoupling-cap chain above
its parent IC's anchor.

= PASSIVE_OFFSET (10.16) + parity stagger (5.08) + cap body half (3.81)
  + power-symbol stub (5.08) + 5.08 mm safety margin.

Used by the dynamic IC row-pitch calculator in
:func:`~zynq_eda.core.layout.place._ic_anchors_for_block` to ensure
the next IC's TOP cap chain clears the previous IC's body.
"""

# ---------------------------------------------------------------------------
# 5. Stub + clearance — net label anchor positioning.
# ---------------------------------------------------------------------------

NET_LABEL_STUB_MM: float = snap_to_grid(2.54)
"""Distance from a connector pin tip to our PlacedLabel's anchor.

Beyond the pin number's text bbox (~1.5 mm wide at 1.27 mm height),
leaving ~1 mm of clear gap between pin number and our outboard net
label. Bumped per-connector via the dynamic STUB_LEN mechanism in
:mod:`connectors` when the intrinsic name+number text would otherwise
collide with the net label.
"""

POWER_SYMBOL_OFFSET_MM: float = snap_to_grid(5.08)
"""Distance from a passive's far terminal to its attached power
symbol (GND, +3V3, etc.)."""


# ---------------------------------------------------------------------------
# 6. Convenience accessors used by validators / unit tests.
# ---------------------------------------------------------------------------

def expected_pin_pitch_mm() -> float:
    """Return the canonical pin pitch every symbol must use."""
    return PIN_PITCH_MM


def expected_text_size_mm() -> float:
    """Return the canonical text height every visible label uses."""
    return TEXT_SIZE_MM


def expected_pin_name_offset_mm() -> float:
    """Return the canonical pin-name offset (distance from pin tip
    into the body where the pin name text anchors)."""
    return PIN_NAME_OFFSET_MM
