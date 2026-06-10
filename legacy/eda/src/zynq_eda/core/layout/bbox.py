"""Axis-aligned bounding boxes for schematic primitives.

All bboxes live in PAGE coordinates (millimetres). KiCad schematic pages
use +Y pointing visually downward, so ``min.y`` is the *top* edge of the
box on screen and ``max.y`` is the *bottom*. The math is still standard
AABB intersection — the visual orientation only matters when interpreting
``min``/``max`` for human-facing diagnostics.

The primitives here are the foundation for:

  * the live :class:`~zynq_eda.core.layout.occupancy.Occupancy` index used
    during placement to avoid collisions;
  * the :func:`~zynq_eda.core.validate.overlap.validate_overlap` validator
    that gates emission once the placement finishes.

Bboxes are constructed via the helpers :func:`text_bbox`, :func:`wire_bbox`
and :func:`symbol_bbox` — never instantiate :class:`BBox` directly unless
you are reconstructing one from already-known min/max coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zynq_eda.core.model.grid import Point


# ---- Public type aliases ---------------------------------------------------

BBoxKind = Literal[
    "symbol",
    "label",
    "hierarchical_label",
    "sheet_pin",
    "wire",
    "no_connect",
    "junction",
    "sheet",
]
"""What kind of placed primitive a :class:`BBox` was derived from.

``"sheet"`` is included so root-sheet symbols (the box-shaped sub-sheet
placeholders that appear on the root page) can be checked too; the
per-sheet validator only sees the more granular kinds.
"""


# ---- Defaults --------------------------------------------------------------

DEFAULT_TEXT_SIZE_MM: float = 1.27
"""Default KiCad text height in millimetres (50 mil)."""

DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO: float = 1.0
"""Fallback per-character width (fraction of text size) for any glyph
not in :data:`KICAD_CHAR_WIDTH_RATIO`.

This is the FAITHFUL average. Width must NOT be under-estimated: a too-
small text box lets the strict validator pass renders that visually
overlap (the failure mode the user flagged — adjacent cap references
overprinting as "C102C101"). Per-glyph widths below are calibrated from
KiCad's own SVG export (``textLength`` is KiCad's authoritative rendered
width); use :func:`text_width`, not this flat fallback, wherever possible.
"""

# Per-character width as a fraction of the nominal text size, CALIBRATED
# from KiCad's stroke-font renderer. Fitted from 4869 ``<text textLength=…>``
# samples exported by ``kicad-cli sch export svg`` across all 28 carrier
# sheets (least-squares per-glyph solve). Summing these for a string
# reproduces KiCad's rendered string width to within ~2%, so the strict
# overlap/bounds validators see what KiCad actually draws — not a
# deliberately shrunk box. DO NOT lower these to silence overlap errors;
# that is the softening the project forbids. Re-derive them only from a
# fresh KiCad render if the font ever changes.
KICAD_CHAR_WIDTH_RATIO: dict[str, float] = {
    " ": 0.68, "!": 0.40, "#": 1.30, "%": 1.55, "(": 0.50, ")": 0.50,
    "*": 0.90, "+": 1.24, ",": 0.38, "-": 1.20, ".": 0.38, "/": 1.01,
    "0": 1.00, "1": 1.03, "2": 1.03, "3": 1.03, "4": 1.04, "5": 1.04,
    "6": 1.03, "7": 1.03, "8": 1.04, "9": 1.05, ":": 0.68, ";": 0.68,
    "<": 1.10, "=": 1.10, ">": 1.10, "?": 0.90,
    "A": 0.88, "B": 1.02, "C": 1.02, "D": 1.05, "E": 0.95, "F": 0.85,
    "G": 1.03, "H": 1.08, "I": 0.52, "J": 0.83, "K": 1.11, "L": 0.83,
    "M": 1.16, "N": 1.11, "O": 1.06, "P": 0.99, "Q": 0.95, "R": 0.97,
    "S": 0.98, "T": 0.79, "U": 1.12, "V": 0.87, "W": 1.20, "X": 0.95,
    "Y": 0.96, "Z": 0.96, "_": 0.71,
    "a": 0.85, "b": 1.03, "c": 0.84, "d": 0.91, "e": 0.83, "f": 0.50,
    "g": 0.90, "h": 0.89, "i": 0.63, "j": 0.64, "k": 0.83, "l": 0.61,
    "m": 1.36, "n": 0.91, "o": 0.93, "p": 0.94, "q": 0.92, "r": 0.61,
    "s": 0.75, "t": 0.63, "u": 0.96, "v": 0.82, "w": 1.10, "x": 0.83,
    "y": 0.82, "z": 0.82,
}

DEFAULT_TEXT_HEIGHT_RATIO: float = 1.0
"""Visible text-box height as a fraction of nominal size.

In KiCad the text ``size`` IS the cap height — a 1.27 mm field renders
1.27 mm-tall uppercase/digit glyphs. (KiCad's SVG export shows font-size
1.6933 mm only because SVG fonts express the full em, = capheight / 0.75;
the visible glyph height is still 1.27 mm.) So the faithful visible-height
ratio is 1.0. Over-estimating here (e.g. 1.4) inflates vertical clearance
and makes the validator fire on wires that pass cleanly beneath a pin-
number row — a different infidelity from the width under-estimate, and
equally wrong.
"""

DEFAULT_WIRE_THICKNESS_MM: float = 0.254
"""Default KiCad wire stroke width (10 mil)."""

DEFAULT_WIRE_CLEARANCE_MM: float = 0.5
"""Extra clearance around a wire when building its bbox.

Even after the router avoids landing labels on wires, we want a small
buffer so the bbox flags labels sitting *immediately adjacent* to a
wire (those still read as "label on wire" visually). The router's own
clearance grid is independent of this number.
"""


# ---- BBox dataclass --------------------------------------------------------

@dataclass(frozen=True)
class BBox:
    """An axis-aligned bounding box around a single placed primitive.

    ``min`` is the corner with the SMALLEST x and SMALLEST y (top-left on
    screen, since KiCad +Y points downward). ``max`` is the corner with
    the LARGEST x and LARGEST y (bottom-right on screen). Width and
    height are always non-negative.

    The class is frozen so bboxes can be hashed / stored in sets and
    used as dict keys; transformations always return a new instance.
    """

    min: Point
    max: Point
    kind: BBoxKind
    owner_id: str

    def __post_init__(self) -> None:
        if self.min.x > self.max.x:
            raise ValueError(
                f"BBox.min.x ({self.min.x}) must be <= max.x ({self.max.x})"
            )
        if self.min.y > self.max.y:
            raise ValueError(
                f"BBox.min.y ({self.min.y}) must be <= max.y ({self.max.y})"
            )

    @property
    def width(self) -> float:
        """Horizontal extent in millimetres (>= 0)."""
        return self.max.x - self.min.x

    @property
    def height(self) -> float:
        """Vertical extent in millimetres (>= 0)."""
        return self.max.y - self.min.y

    @property
    def center(self) -> Point:
        """Geometric centre of the box."""
        return Point(
            (self.min.x + self.max.x) / 2.0,
            (self.min.y + self.max.y) / 2.0,
        )

    @property
    def area(self) -> float:
        """Area in mm^2 (>= 0)."""
        return self.width * self.height

    def expand(self, margin_mm: float) -> "BBox":
        """Return a new box grown outward in every direction by ``margin_mm``.

        Negative margins shrink the box; the result is clamped so width
        and height never go below zero (a fully-collapsed box has its
        min/max set to its centre).
        """
        if margin_mm == 0.0:
            return self
        new_min = Point(self.min.x - margin_mm, self.min.y - margin_mm)
        new_max = Point(self.max.x + margin_mm, self.max.y + margin_mm)
        if new_min.x > new_max.x or new_min.y > new_max.y:
            # Shrinkage exceeded the box; collapse to the centre.
            cx, cy = self.center.x, self.center.y
            return BBox(
                min=Point(cx, cy),
                max=Point(cx, cy),
                kind=self.kind,
                owner_id=self.owner_id,
            )
        return BBox(min=new_min, max=new_max, kind=self.kind, owner_id=self.owner_id)

    def translate(self, dx: float, dy: float) -> "BBox":
        """Return a new box shifted by ``(dx, dy)``."""
        return BBox(
            min=Point(self.min.x + dx, self.min.y + dy),
            max=Point(self.max.x + dx, self.max.y + dy),
            kind=self.kind,
            owner_id=self.owner_id,
        )

    def intersects(self, other: "BBox", padding_mm: float = 0.0) -> bool:
        """Return True iff this box (expanded by ``padding_mm``) overlaps ``other``.

        Standard AABB overlap test: two boxes overlap iff they overlap on
        BOTH axes. ``padding_mm`` is added symmetrically to both boxes
        (effectively to the test thresholds), so passing ``padding_mm =
        0.5`` reports boxes whose edges sit within 0.5 mm of each other
        as overlapping.

        Edge-touching boxes (one's right edge equals the other's left
        edge) are reported as NOT intersecting unless ``padding_mm > 0``.
        This is the standard KiCad convention — wires that meet at a
        single endpoint share that point but do not "overlap".
        """
        if padding_mm > 0.0:
            return (
                self.min.x - padding_mm < other.max.x
                and self.max.x + padding_mm > other.min.x
                and self.min.y - padding_mm < other.max.y
                and self.max.y + padding_mm > other.min.y
            )
        return (
            self.min.x < other.max.x
            and self.max.x > other.min.x
            and self.min.y < other.max.y
            and self.max.y > other.min.y
        )

    def intersection(self, other: "BBox") -> "BBox | None":
        """Return the geometric intersection box, or ``None`` if disjoint.

        The result inherits this box's ``kind`` and ``owner_id`` (callers
        usually only care about its width/height for reporting). Returns
        ``None`` when the boxes are disjoint or only touch at an edge.
        """
        ix_min = max(self.min.x, other.min.x)
        iy_min = max(self.min.y, other.min.y)
        ix_max = min(self.max.x, other.max.x)
        iy_max = min(self.max.y, other.max.y)
        if ix_min >= ix_max or iy_min >= iy_max:
            return None
        return BBox(
            min=Point(ix_min, iy_min),
            max=Point(ix_max, iy_max),
            kind=self.kind,
            owner_id=self.owner_id,
        )

    def contains_point(self, p: Point) -> bool:
        """Return True iff ``p`` lies inside (or on the edge of) the box."""
        return (
            self.min.x <= p.x <= self.max.x
            and self.min.y <= p.y <= self.max.y
        )


# ---- Internal helpers ------------------------------------------------------

def _rotate_bbox(box: BBox, anchor: Point, rotation_deg: float) -> BBox:
    """Rotate a bbox 0/90/180/270 degrees clockwise around ``anchor``.

    The rotation matches KiCad's CW page rotation (the same convention
    used for symbol rotations and pin flips). Rotating an axis-aligned
    box by a quarter-turn produces another axis-aligned box, so we
    rotate the four corners and re-derive min/max.

    Raises ``ValueError`` for any rotation that is not a multiple of 90.
    """
    rotation_canonical = float(rotation_deg) % 360.0
    if rotation_canonical not in (0.0, 90.0, 180.0, 270.0):
        raise ValueError(
            f"_rotate_bbox: rotation must be 0/90/180/270, got {rotation_deg!r}"
        )
    if rotation_canonical == 0.0:
        return box

    # Translate corners to anchor-local coordinates.
    corners_local = (
        (box.min.x - anchor.x, box.min.y - anchor.y),
        (box.max.x - anchor.x, box.min.y - anchor.y),
        (box.min.x - anchor.x, box.max.y - anchor.y),
        (box.max.x - anchor.x, box.max.y - anchor.y),
    )

    rotated_corners: list[tuple[float, float]] = []
    for local_x, local_y in corners_local:
        if rotation_canonical == 90.0:
            # CW 90° in page coords (+Y down): (x, y) → (-y, x)
            rotated_corners.append((-local_y, local_x))
        elif rotation_canonical == 180.0:
            rotated_corners.append((-local_x, -local_y))
        else:  # 270.0
            rotated_corners.append((local_y, -local_x))

    xs = [c[0] for c in rotated_corners]
    ys = [c[1] for c in rotated_corners]
    return BBox(
        min=Point(anchor.x + min(xs), anchor.y + min(ys)),
        max=Point(anchor.x + max(xs), anchor.y + max(ys)),
        kind=box.kind,
        owner_id=box.owner_id,
    )


# ---- Public bbox factories -------------------------------------------------

def text_width(text: str, size_mm: float = DEFAULT_TEXT_SIZE_MM) -> float:
    """Return the rendered width (mm) of ``text`` at ``size_mm``.

    Sums KiCad's per-glyph advance widths (:data:`KICAD_CHAR_WIDTH_RATIO`,
    calibrated from KiCad's own SVG ``textLength`` export) so the result
    matches what KiCad actually draws — to within ~2%. Unknown glyphs use
    :data:`DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO`. This is the single source of
    truth for text width across the planner (lane reservation, label
    placement) and the validators (overlap, page bounds); keeping them on
    the SAME faithful model is what guarantees "validator-clean" == "looks
    clean in KiCad".
    """
    return size_mm * sum(
        KICAD_CHAR_WIDTH_RATIO.get(ch, DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO)
        for ch in text
    )


def text_bbox(
    text: str,
    anchor: Point,
    size_mm: float = DEFAULT_TEXT_SIZE_MM,
    rotation: float = 0.0,
    justify: Literal["left", "right", "center"] = "left",
    owner_id: str = "",
    kind: BBoxKind = "label",
) -> BBox:
    """Estimate the rendered text bounding box on the page.

    Width is KiCad's faithful per-glyph rendered width (:func:`text_width`);
    height is ``size_mm * DEFAULT_TEXT_HEIGHT_RATIO``. Both are calibrated
    to KiCad's actual stroke-font output so the strict validators flag what
    visually overlaps and nothing they pass overprints in KiCad.

    The ``justify`` parameter controls how the anchor relates to the
    unrotated text box:

      * ``"left"``   — anchor is the box's LEFT edge (text reads right).
      * ``"right"``  — anchor is the box's RIGHT edge (text reads left).
      * ``"center"`` — anchor is the box's horizontal centre.

    In all three cases the anchor sits on the vertical centre of the
    text height (the natural baseline + cap height midpoint). After
    placing the unrotated box, it is rotated 0/90/180/270 degrees
    clockwise around the anchor.

    An empty ``text`` produces a zero-width box centred on the anchor —
    callers can still use it as a placeholder; it will not intersect
    anything else.
    """
    if rotation not in (0.0, 90.0, 180.0, 270.0):
        raise ValueError(
            f"text_bbox: rotation must be 0/90/180/270, got {rotation!r}"
        )

    width = text_width(text, size_mm)
    height = size_mm * DEFAULT_TEXT_HEIGHT_RATIO

    # Build the unrotated box around the anchor according to ``justify``.
    half_height = height / 2.0
    if justify == "left":
        min_x = anchor.x
        max_x = anchor.x + width
    elif justify == "right":
        min_x = anchor.x - width
        max_x = anchor.x
    elif justify == "center":
        half_width = width / 2.0
        min_x = anchor.x - half_width
        max_x = anchor.x + half_width
    else:
        raise ValueError(
            f"text_bbox: justify must be left/right/center, got {justify!r}"
        )

    unrotated = BBox(
        min=Point(min_x, anchor.y - half_height),
        max=Point(max_x, anchor.y + half_height),
        kind=kind,
        owner_id=owner_id,
    )

    if rotation == 0.0:
        return unrotated
    return _rotate_bbox(unrotated, anchor, rotation)


def wire_bbox(
    start: Point,
    end: Point,
    thickness_mm: float = DEFAULT_WIRE_THICKNESS_MM,
    clearance_mm: float = DEFAULT_WIRE_CLEARANCE_MM,
    owner_id: str = "",
) -> BBox:
    """Return a thin rectangular bbox enclosing a straight wire segment.

    For axis-aligned wires (horizontal or vertical — the common case),
    the bbox pads ONLY in the perpendicular direction by
    ``thickness_mm / 2 + clearance_mm``. The parallel (along-axis)
    extent stays at the exact start/end coordinates — no half-thickness
    padding past the endpoints. This way a wire terminating at a label
    or symbol anchor doesn't show a phantom overlap from the wire's
    perpendicular stroke padding extending past the wire end into the
    attached primitive.

    For diagonal wires the AABB-with-margin fallback is used.
    """
    margin = (thickness_mm / 2.0) + clearance_mm
    horizontal = abs(start.y - end.y) < 1e-6
    vertical = abs(start.x - end.x) < 1e-6
    if horizontal and not vertical:
        min_x = min(start.x, end.x)
        max_x = max(start.x, end.x)
        min_y = min(start.y, end.y) - margin
        max_y = max(start.y, end.y) + margin
    elif vertical and not horizontal:
        min_x = min(start.x, end.x) - margin
        max_x = max(start.x, end.x) + margin
        min_y = min(start.y, end.y)
        max_y = max(start.y, end.y)
    else:
        # Zero-length (same point) OR diagonal — pad both directions.
        min_x = min(start.x, end.x) - margin
        max_x = max(start.x, end.x) + margin
        min_y = min(start.y, end.y) - margin
        max_y = max(start.y, end.y) + margin
    return BBox(
        min=Point(min_x, min_y),
        max=Point(max_x, max_y),
        kind="wire",
        owner_id=owner_id,
    )


def symbol_bbox(
    lib_id: str,
    anchor: Point,
    rotation: float,
    cache,
    owner_id: str,
) -> BBox:
    """Return the page-space bbox of a placed symbol.

    Wraps :meth:`SymbolGeometryCache.bounding_box` (which returns an
    anchor-relative :class:`SymbolBoundingBox`) and shifts it into page
    coordinates using the symbol's placed anchor. The ``rotation``
    argument is passed through to the cache; the underlying library
    already accounts for rotation when building the relative box.

    ``cache`` is typed as ``Any`` (loose) to avoid a hard import cycle
    with :mod:`zynq_eda.core.layout.geometry`; in practice every caller
    passes a :class:`SymbolGeometryCache`.
    """
    sym_box = cache.bounding_box(lib_id, rotation=rotation).shift_by(anchor)
    return BBox(
        min=Point(sym_box.min_x, sym_box.min_y),
        max=Point(sym_box.max_x, sym_box.max_y),
        kind="symbol",
        owner_id=owner_id,
    )


def placeholder_symbol_bbox(
    anchor: Point,
    owner_id: str,
    side_mm: float = 12.7,
) -> BBox:
    """Return a default-sized symbol bbox when no geometry cache is available.

    Used by the overlap validator's unit-test code path where library
    registration is too expensive. The box is centred on ``anchor`` with
    ``side_mm`` total width and height.
    """
    half = side_mm / 2.0
    return BBox(
        min=Point(anchor.x - half, anchor.y - half),
        max=Point(anchor.x + half, anchor.y + half),
        kind="symbol",
        owner_id=owner_id,
    )
