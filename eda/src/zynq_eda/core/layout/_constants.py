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

PASSIVE_OFFSET_MM = snap_to_grid(17.78)
"""Distance from an IC pin to its nearest passive's anchor.

Sized so the cluster's far-terminal label (which can be ~16 chars,
e.g. ``ZYNQ_PS_JTAG_TCK`` or ``LVDS_DATA0_N``) doesn't collide with
the connector pin's hier label sitting at the pin's stub-end on the
same Y row. Math:

  hier label bbox extends from (pin - NET_LABEL_STUB) to
    (pin - NET_LABEL_STUB - text_width) — i.e. ~14 mm leftward
  cluster far label sits at (pin - PASSIVE_OFFSET - PASSIVE_PIN_HALF)
    = (pin - 17.78 - 3.81) = (pin - 21.59) extending leftward
  gap between them = (pin - 14.54) - (pin - 21.59) = 7 mm clear.

The previous 10.16 mm gave only 0.6 mm clear — labels visually
touched on dense connectors (JTAG header, LVDS pair termination).
"""

PASSIVE_ADJACENT_PIN_STAGGER_MM = snap_to_grid(10.16)
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

PASSIVE_PIN_HALF = 3.81
"""Half the 7.62 mm pin-to-pin separation on Device:R/Device:C.

Pin 1 of a non-rotated Device:R is at (0, +3.81); pin 2 at (0, -3.81).
"""

CAP_VERTICAL_OFFSET_MM = snap_to_grid(5.08)
"""Distance from IC pin row to cap's NEAR pin (LEFT/RIGHT side).

For LEFT/RIGHT-side IC pins, the cap body sits in a Y-band that is
ABOVE the pin row (smaller Y on page) by enough margin that the cap
body's bbox + 2 mm visual clearance does not intersect the adjacent
pin row's wire. With 2.54 mm KiCad pin pitch + 2 mm clearance + cap
body half-height (~1.25 mm), the cap's near pin must sit at least
~5 mm above pin row. 5.08 mm = 2 × KiCad grid keeps the layout on
the canonical grid AND leaves the cap body in a band that doesn't
collide with any neighbouring pin row.
"""

POWER_SYMBOL_OFFSET_MM = snap_to_grid(7.62)
"""Distance from a passive's far terminal to its attached power symbol.

Must be large enough that the cluster passive's Reference text (rendered
~2.03 mm to one side of the body, ~3.3 mm wide for "R100"-style refs)
and the power symbol's Value text (rendered ~3.56 mm above the symbol
anchor, ~3.3 mm wide for "+3V3") don't overlap. Geometry:

  R Reference bbox X span: [R.x + 0.38, R.x + 3.68]
  PWR  Value     bbox X span: [(R.x + offset) - 1.65, (R.x + offset) + 1.65]

For no overlap with a 0.1 mm noise floor: offset >= 3.68 + 1.65 + 0.1
= 5.43 mm. 5.08 mm gave 0.25 mm overlap (above the noise floor); 7.62 mm
(3 × KiCad grid) clears with 2.5 mm of margin and still keeps clusters
visually tight.
"""

INTERIOR_MARGIN_MM = snap_to_grid(15.24)
"""Minimum distance from a sheet edge to any placed item."""


# ---- Routing & label-placement constants -----------------------------------

KICAD_GRID_MM: float = snap_to_grid(2.54)
"""KiCad's canonical schematic grid step. All routing coordinates are
on multiples of this value. Used as the per-step Y-offset for the
hier-label candidate ladder, the cluster's per-pin trunk-end Y offset,
and the router's Z-bend / exit-detour DH / DY enumeration."""

OVERLAP_NOISE_FLOOR_MM: float = 0.15
"""Validator's noise floor — intersections smaller than this on EITHER
axis are not flagged as overlaps. The router uses the same value as
its collision tolerance so the two passes agree on what counts as an
overlap. SOURCE OF TRUTH lives here; ``_overlap_is_significant`` and
``_ROUTER_NOISE_FLOOR_MM`` both reference this value."""

from zynq_eda.core.layout.bbox import DEFAULT_WIRE_THICKNESS_MM
WIRE_THICKNESS_MM: float = DEFAULT_WIRE_THICKNESS_MM
"""KiCad's default schematic wire stroke thickness. Used to compute
wire bbox padding (half-thickness on each side perpendicular to the
wire's axis). The validator and router must agree on this value or
near-miss collisions will mis-classify. SOURCE OF TRUTH lives in
``bbox.py:DEFAULT_WIRE_THICKNESS_MM`` (the wire_bbox helper's default);
this module re-exports for layout-engine consumers."""

WIRE_VS_WIRE_CLEARANCE_MM: float = 0.3
"""Wire-to-wire clearance. KiCad's pin pitch is 2.54 mm; a 2 mm
clearance would false-collide adjacent pin pitch routing. 0.3 mm is
enough that distinct same-direction wires render as separate strokes
without merging visually."""

# NOTE: there is no separate WIRE_VS_INTRINSIC_TEXT_CLEARANCE_MM.
# Intrinsic pin text uses the same VISUAL_CLEARANCE_MM (2 mm) as
# every other visible primitive. A router 0 mm pass was attempted
# during the thrashing era and removed in Part III — it softened
# the visual-touch rule the user has set in stone.

# ---- Predictive planner lane reservation -----------------------------------

MAX_LANE_ROWS: int = 3
"""Maximum number of label-stack rows the planner will allocate per
edge of an owner (IC / connector). The greedy lane packer in Phase 3
(``plan_edge_stacks``) fills row 0 first, then row 1, then row 2, and
hard-fails when a lane won't fit in any of the first ``MAX_LANE_ROWS``.

3 rows is the design ceiling — beyond that, the connector body and the
hier-label rows visually compete for the page and the user is better
served splitting the block. The diagnostic on overflow names the
specific block.py edit (toggle ExternalNet.edge, split block, A2 paper).
"""

LANE_ROW_PITCH_MM: float = snap_to_grid(20.32)
"""Outboard X step between successive lane rows on the same edge.

Each row sits this far further OUT from the previous row (which
contains the inboard lanes). 20.32 mm = 8 grid units = enough for
one hier-label's text bbox (1.27 mm × 25 chars ≈ 21 mm) + 2 mm clearance
on the inboard side."""

GND_SYMBOL_HALF_EXTENT_MM: float = 3.81
"""Half-width of the ``power:GND`` symbol's visible body (excluding pin).
Used by Phase 2 to size GND lanes for non-cluster GND-role pins."""

FLG_BODY_EXTENT_MM: float = 2.54
"""Half-extent of the ``power:PWR_FLAG`` symbol's body in the direction
parallel to its attached wire. Used by Phase 2 to size PWR_FLAG lanes."""

HLABEL_ANCHOR_OFFSET_MM: float = snap_to_grid(2.54)
"""Minimum X distance between the pin's outermost cluster passive (or
the pin tip if no cluster) and the hier-label's anchor. Provides
visual breathing room between the cluster's last drop wire and the
hier-label text bbox."""


VISUAL_CLEARANCE_MM: float = 2.0
"""Minimum gap (mm) between any two visible primitives.

Drives EVERY placement helper that probes occupancy for a free slot:
cluster passive shifts, dynamic Value-text positions, outboard label
positions, and the post-placement validator's "everything must breathe"
rule. Bboxes whose edges sit closer than this are treated as colliding
even when their geometry does not actually overlap — the user has
ruled that elements appearing to touch (text against text, text
against body, body against wire) is the same as overlapping for
visual purposes.

2 mm = 0.79 × the KiCad grid pitch (2.54 mm). Smaller than one full
grid step but large enough that adjacent property labels read as
separate elements.
"""


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


# ---- Root sheet (block index) layout ---------------------------------------

ROOT_PAPER_SIZE = "A3"
"""Root index page size: A3 portrait (297 mm × 420 mm).

Reference designs (PYNQ-Z2, Arty Z7, MicroZed I/O Carrier, BeagleBone
Black) use a clean A3 portrait root sheet showing block symbols by
NAME ONLY. This carrier uses a 4-column × 7-row grid that comfortably
fits up to 28 blocks.

NOTE: A3 in KiCad is defined as 420 × 297 (landscape). KiCad sets
portrait via :data:`schematic.set_paper_size("A3", portrait=True)`.
The :class:`Sheet` model treats the *paper_size* string as the named
KiCad size; the orientation is implicit (portrait for the root
index, landscape for everything else)."""

ROOT_GRID_COLS = 4
"""Columns of block rectangles in the root index grid."""

ROOT_GRID_ROWS = 7
"""Rows of block rectangles in the root index grid (4×7 = 28 cells)."""

ROOT_GRID_ROW_PITCH_MM = snap_to_grid(50.8)
"""Vertical pitch between adjacent grid rows on the root index.

50.8 mm (20 grid steps) × 7 rows = 355.6 mm of grid content. A3
portrait height is 420 mm; subtracting ~20 mm top margin + ~45 mm
bottom title-block area leaves ~355 mm for the 7-row stack — fits
exactly."""

ROOT_GRID_COL_PITCH_MM = snap_to_grid(66.04)
"""Horizontal pitch between adjacent grid columns on the root index.

66.04 mm (52 grid steps) × 4 cols = 264.16 mm of grid content. A3
portrait width is 297 mm; subtracting ~15 mm left margin leaves
~282 mm. 264.16 mm of grid content keeps the right column ~15 mm
from the right edge — symmetric margins."""

ROOT_SHEET_SYMBOL_WIDTH_MM = snap_to_grid(50.8)
"""Width of each block rectangle on the root index.

50.8 mm × 50 grid steps wide is enough to fit the block name as a
single line at standard KiCad text size (1.27 mm) for names up to
~30 chars."""

ROOT_SHEET_SYMBOL_HEIGHT_MM = snap_to_grid(20.32)
"""Height of each block rectangle on the root index.

20.32 mm is the minimum-acceptable sheet symbol height in KiCad and
keeps the rectangles visually compact. No sheet pins are exposed on
the root, so the symbol only needs to hold the block name."""

ROOT_MARGIN_TOP_MM = snap_to_grid(25.4)
"""Top margin (header text + first grid row's anchor offset)."""

ROOT_MARGIN_LEFT_MM = snap_to_grid(15.24)
"""Left margin (first column's anchor offset)."""

ROOT_TITLE_TEXT = "Zynq SoM Carrier - Block Index"
"""Short header rendered at the top of the root index."""

ROOT_REVISION = "A1"
"""Revision tag rendered in the bottom-right title block."""
