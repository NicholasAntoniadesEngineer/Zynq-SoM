"""Symbol geometry: pin positions + bounding boxes from ``.kicad_sym`` files.

The layout engine reads pin coordinates from real symbol definitions instead
of hand-coded offsets. This module wraps ``kicad-sch-api``'s symbol cache and
exposes:

    - :meth:`SymbolGeometryCache.register_libraries` — register ``.kicad_sym``
      paths (idempotent; safe to call repeatedly).
    - :meth:`SymbolGeometryCache.absolute_pin_by_name` — resolve a named pin
      to its absolute wire-attachment coordinate when the symbol is placed
      at a given anchor with a given rotation.
    - :meth:`SymbolGeometryCache.bounding_box` — compute the symbol's
      bounding box (min/max x/y) relative to its anchor.
    - :meth:`SymbolGeometryCache.all_pins` — enumerate every pin on a symbol
      (name, number, position relative to anchor).

Implementation: ``kicad-sch-api`` exposes pin positions only via a *placed*
component on a *schematic*. We create a throw-away in-memory schematic per
query (the schematic is never saved). Results are cached by
``(lib_id, rotation)`` so repeated lookups for the same symbol are cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import kicad_sch_api as ksa

from zynq_eda.core.model.grid import KICAD_GRID_MM, Point, snap_to_grid


DEFAULT_PIN_LENGTH_MM = KICAD_GRID_MM
"""Length of the visible pin stub outside the symbol body (KiCad default: 1.27 mm)."""


# Per-lib_id Value-property shift applied by the post-emit patch
# (:func:`zynq_eda.core.emit.schematic._shift_passive_value_off_body`).
# The validator MUST mirror this shift so its bbox prediction matches
# what KiCad actually renders. Each tuple is
# ``(dx, dy, text_rotation_override)`` in PAGE coords at symbol
# rotation 0; the symbol rotation is applied on top.
VALUE_SHIFT_BY_LIB_ID: dict[str, tuple[float, float, float | None]] = {
    "Device:R":           (-2.032, 0.0, 90.0),
    "Device:R_Small":     (-2.032, 0.0, 90.0),
    "Device:C":           (-2.54, 0.0, 90.0),
    "Device:C_Small":     (-2.54, 0.0, 90.0),
    "Device:C_Polarized": (-2.54, 0.0, 90.0),
    "Device:D":           (-2.54, 0.0, 90.0),
    "Device:D_Schottky":  (-2.54, 0.0, 90.0),
    "Device:D_Zener":     (-2.54, 0.0, 90.0),
    "Device:LED":         (-2.54, 0.0, 90.0),
}


def pick_dynamic_reference_shift(
    *,
    lib_id: str,
    anchor: "Point",
    symbol_rotation: float,
    occupancy,
    geometry_cache,
    owner_id: str = "",
    reference_text: str = "C100",
    consider_wires: bool = False,
    padding_mm: float | None = None,
) -> "tuple[float, float, float | None] | None":
    """Pick a Reference-property displacement that doesn't collide.

    Mirror of :func:`pick_dynamic_value_shift` but for Reference text.
    Tries the same 26-candidate ladder, returning the first whose
    rendered text bbox is clear of the cap's own body and of every
    primitive currently in ``occupancy``.

    Returns ``None`` if no candidate fits — caller then falls back to
    the KiCad lib-default Reference position.
    """
    from zynq_eda.core.layout.bbox import (
        DEFAULT_TEXT_SIZE_MM,
        symbol_bbox,
        text_bbox,
    )

    # Only apply for known passive lib_ids (Device:R/C family).
    if lib_id not in VALUE_SHIFT_BY_LIB_ID:
        return None

    try:
        own_body = symbol_bbox(
            lib_id=lib_id,
            anchor=anchor,
            rotation=symbol_rotation,
            cache=geometry_cache,
            owner_id=f"{owner_id}:own_body_probe",
        )
    except Exception:
        own_body = None

    # Reference defaults to OPPOSITE side from Value. For Device:R/C
    # whose Value shift is (-2.54, 0, 90), Reference goes to (+2.54, 0, 90).
    value_default = VALUE_SHIFT_BY_LIB_ID[lib_id]
    dx0 = -value_default[0]
    dy0 = value_default[1]
    rot0 = value_default[2]

    rad = 2.54  # one grid pitch
    candidates: list[tuple[float, float, float | None]] = [
        (dx0, dy0, rot0),                       # baseline opposite-Value
        (dx0 + rad, dy0, rot0),                 # farther out
        (dx0 + 2 * rad, dy0, rot0),
        (dx0, dy0 - 2 * rad, 0.0),              # above
        (dx0, dy0 + 2 * rad, 0.0),              # below
        (dx0 + rad, dy0 - 2 * rad, 0.0),        # diag upper
        (dx0 + rad, dy0 + 2 * rad, 0.0),        # diag lower
        (dx0, dy0 - 3 * rad, 0.0),              # further above
        (dx0, dy0 + 3 * rad, 0.0),              # further below
        (0.0, dy0 - 4 * rad, 0.0),              # on body axis above
        (0.0, dy0 + 4 * rad, 0.0),              # on body axis below
    ]

    from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM

    for dx, dy, text_rot in candidates:
        sym_rot = int(symbol_rotation) % 360
        if sym_rot == 0:
            rdx, rdy = dx, dy
        elif sym_rot == 90:
            rdx, rdy = dy, -dx
        elif sym_rot == 180:
            rdx, rdy = -dx, -dy
        elif sym_rot == 270:
            rdx, rdy = -dy, dx
        else:
            rdx, rdy = dx, dy
        from zynq_eda.core.model.grid import Point as _Pt
        text_anchor = _Pt(anchor.x + rdx, anchor.y + rdy)
        candidate_bbox = text_bbox(
            text=reference_text,
            anchor=text_anchor,
            size_mm=DEFAULT_TEXT_SIZE_MM,
            rotation=0.0,
            justify="center",
            owner_id=f"{owner_id}:ref_probe",
            kind="symbol",
        )
        if own_body is not None and candidate_bbox.intersects(
            own_body, padding_mm=VISUAL_CLEARANCE_MM,
        ):
            continue
        ignore_kinds_set: set = {"junction", "no_connect"}
        if not consider_wires:
            ignore_kinds_set.add("wire")
        effective_padding = (
            VISUAL_CLEARANCE_MM if padding_mm is None else padding_mm
        )
        hits = occupancy.collides(
            candidate_bbox,
            ignore_kinds=frozenset(ignore_kinds_set),
            padding_mm=effective_padding,
        )
        if not hits:
            return (dx, dy, text_rot)
    return None


REFERENCE_SHIFT_BY_LIB_ID: dict[str, tuple[float, float, float | None]] = {}
"""Opt-in Reference-text displacement per passive lib_id.

Empty by default — Reference text uses the KiCad-library default
position unless a per-instance ``reference_shift`` is set on the
PlacedSymbol. Future work (pick_dynamic_reference_shift) will populate
this table for clusters where the default position causes overlaps.
"""
"""DEFAULT shift candidates per lib_id. Used as the FIRST attempt at
placement time; if that anchor collides, the placement engine probes a
ladder of alternate shifts (perpendicular, opposite-side, larger offset)
and picks the first one whose Value bbox is clear of all existing
primitives. See :func:`pick_dynamic_value_shift`.
"""


def pick_dynamic_value_shift(
    *,
    lib_id: str,
    anchor: "Point",
    symbol_rotation: float,
    occupancy,
    geometry_cache,
    owner_id: str = "",
    value_text: str = "00000",
    consider_wires: bool = False,
    padding_mm: float | None = None,
) -> "tuple[float, float, float | None] | None":
    """Pick a Value-property displacement that doesn't collide with anything.

    Walks a ladder of candidate offsets (the default for the lib_id, then
    perpendicular and farther positions) and returns the first whose
    rendered text bbox is clear of every primitive currently in
    ``occupancy`` AND of the cap's own body. Returns ``None`` if no
    candidate fits — caller should accept the default and let the
    validator surface the resulting overlap.

    The cap's own body is checked SEPARATELY (not from occupancy) because
    the cap is typically added to occupancy AFTER its property positions
    are resolved — so occupancy doesn't yet contain the body. Passing
    the body through the same clearance gate ensures Value text never
    sits on top of its own component, which is the most visible failure
    mode on dense cluster stacks.

    The returned tuple matches :data:`VALUE_SHIFT_BY_LIB_ID` — ``(dx, dy,
    text_rotation_override)`` — so callers can store it for both the
    emit pass and the validator. Coordinates are PAGE-relative at symbol
    rotation 0; ``symbol_rotation`` is applied here so the returned
    displacement is already in absolute PAGE-rotated form.
    """
    from zynq_eda.core.layout.bbox import (
        DEFAULT_TEXT_SIZE_MM,
        symbol_bbox,
        text_bbox,
    )

    if lib_id not in VALUE_SHIFT_BY_LIB_ID:
        return None

    # Compute the cap's own body bbox so the probe can avoid it.
    try:
        own_body = symbol_bbox(
            lib_id=lib_id,
            anchor=anchor,
            rotation=symbol_rotation,
            cache=geometry_cache,
            owner_id=f"{owner_id}:own_body_probe",
        )
    except Exception:
        own_body = None

    default_shift = VALUE_SHIFT_BY_LIB_ID[lib_id]
    dx0, dy0, rot0 = default_shift

    rad = 2.54  # one grid pitch
    candidates: list[tuple[float, float, float | None]] = [
        default_shift,                          # default per lib_id
        (dx0 - rad, dy0, rot0),                 # farther same side
        (dx0 - 2 * rad, dy0, rot0),             # even farther same side
        (-dx0, dy0, rot0),                      # mirror in X
        (-dx0 + rad, dy0, rot0),                # farther mirror
        (-dx0 + 2 * rad, dy0, rot0),            # even farther mirror
        (dx0, dy0 - 2 * rad, 0.0),              # above body (perpendicular)
        (dx0, dy0 + 2 * rad, 0.0),              # below body
        (-dx0, dy0 - 2 * rad, 0.0),             # mirror above
        (-dx0, dy0 + 2 * rad, 0.0),             # mirror below
        (dx0, dy0 - 3 * rad, 0.0),              # further above
        (dx0, dy0 + 3 * rad, 0.0),              # further below
        (0.0, dy0 - 4 * rad, 0.0),              # well above on body axis
        (0.0, dy0 + 4 * rad, 0.0),              # well below on body axis
        # Extended ladder: combine X and Y shifts for tight cluster
        # cases where simple X-or-Y moves all collide.
        (dx0 - rad, dy0 - 2 * rad, 0.0),        # diagonal upper-far same
        (dx0 - rad, dy0 + 2 * rad, 0.0),        # diagonal lower-far same
        (-dx0 + rad, dy0 - 2 * rad, 0.0),       # diagonal upper-far mirror
        (-dx0 + rad, dy0 + 2 * rad, 0.0),       # diagonal lower-far mirror
        (dx0 - 2 * rad, dy0 - 2 * rad, 0.0),    # diag upper x2 same
        (dx0 - 2 * rad, dy0 + 2 * rad, 0.0),    # diag lower x2 same
        (-dx0 + 2 * rad, dy0 - 2 * rad, 0.0),   # diag upper x2 mirror
        (-dx0 + 2 * rad, dy0 + 2 * rad, 0.0),   # diag lower x2 mirror
        (0.0, dy0 - 5 * rad, 0.0),              # well above further
        (0.0, dy0 + 5 * rad, 0.0),              # well below further
        (dx0 - 3 * rad, dy0, rot0),             # extra-far same side
        (-dx0 + 3 * rad, dy0, rot0),            # extra-far mirror
    ]

    for dx, dy, text_rot in candidates:
        sym_rot = int(symbol_rotation) % 360
        if sym_rot == 0:
            rdx, rdy = dx, dy
        elif sym_rot == 90:
            rdx, rdy = dy, -dx
        elif sym_rot == 180:
            rdx, rdy = -dx, -dy
        elif sym_rot == 270:
            rdx, rdy = -dy, dx
        else:
            rdx, rdy = dx, dy
        from zynq_eda.core.model.grid import Point as _Pt
        text_anchor = _Pt(anchor.x + rdx, anchor.y + rdy)
        candidate_bbox = text_bbox(
            text=value_text,
            anchor=text_anchor,
            size_mm=DEFAULT_TEXT_SIZE_MM,
            rotation=0.0,
            justify="center",
            owner_id=f"{owner_id}:value_probe",
            kind="symbol",
        )
        from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM
        # Reject candidates that intersect the cap's OWN body (with
        # the 2 mm clearance gate). Without this, the probe accepts a
        # shift like (-2.54, 0) for Device:C whose 4 mm-wide Value
        # text still grazes the body bbox by ~0.5 mm.
        if own_body is not None and candidate_bbox.intersects(own_body, padding_mm=VISUAL_CLEARANCE_MM):
            continue
        ignore_kinds_set: set = {"junction", "no_connect"}
        if not consider_wires:
            ignore_kinds_set.add("wire")
        effective_padding = (
            VISUAL_CLEARANCE_MM if padding_mm is None else padding_mm
        )
        hits = occupancy.collides(
            candidate_bbox,
            ignore_kinds=frozenset(ignore_kinds_set),
            padding_mm=effective_padding,
        )
        if not hits:
            return (dx, dy, text_rot)

    return None


@dataclass(frozen=True)
class PinGeometry:
    """Resolved geometry for a single pin instance.

    Attributes:
        anchor: Absolute coordinate where the pin's electrical endpoint sits
            (where wires terminate). On the schematic this is the "tip" of
            the visible pin stub.
        connection: Same as ``anchor`` for KiCad; kept distinct in case future
            engines want to differentiate (e.g. an off-symbol "via" point).
        relative: Position of the pin relative to the symbol's anchor (before
            rotation/translation). Used to determine which side of the body
            the pin is on (left/right/top/bottom).
        pin_rotation: The pin's intrinsic rotation in the KiCad symbol library
            (0/90/180/270 degrees). Per KiCad convention, this rotation
            indicates the direction from the pin's wire-end (tip) INTO the
            symbol body — so a pin with rotation=0 sits on the LEFT edge of
            the body (tip on the left, body extends to the right).
        symbol_rotation: The placement rotation of the parent symbol on the
            schematic page (0/90/180/270 degrees). Combined with
            ``pin_rotation`` and the symbol-to-page Y-flip, this determines
            the page-side a pin sits on.
    """

    anchor: Point
    connection: Point
    relative: Point
    pin_rotation: float = 0.0
    symbol_rotation: float = 0.0


@dataclass(frozen=True)
class SymbolBoundingBox:
    """Bounding box of a symbol, derived from its pin extents + body padding.

    All coordinates are relative to the symbol's anchor (centre/origin in
    KiCad's symbol model).
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def shift_by(self, anchor: Point) -> "SymbolBoundingBox":
        """Translate from anchor-relative to absolute coordinates."""
        return SymbolBoundingBox(
            min_x=self.min_x + anchor.x,
            min_y=self.min_y + anchor.y,
            max_x=self.max_x + anchor.x,
            max_y=self.max_y + anchor.y,
        )


def pin_connection_from_anchor(
    anchor: Point,
    relative: Point,
    pin_length: float = DEFAULT_PIN_LENGTH_MM,
) -> Point:
    """Compatibility alias: with the corrected geometry, the connection IS
    the anchor (no extra pin-length offset). Kept for any external callers."""
    return anchor


def _flip_y_then_rotate(symbol_relative: Point, rotation_deg: float) -> Point:
    """Convert a symbol-local pin offset to a page-local offset.

    KiCad symbols use +Y up (math convention); schematic pages use +Y down.
    The placement transform is (verified empirically against the
    netlist KiCad produces from ``connect_pins_with_wire`` + power symbols):

        1. Y-flip in symbol coords: (x, y) → (x, -y)
        2. Rotate by ``rotation_deg`` *clockwise* in page coords:
             90  CW: (x, y) → (y, -x)
             180:    (x, y) → (-x, -y)
             270 CW: (x, y) → (-y, x)

    The CW direction matches what you see in the schematic editor (where
    +Y is down) when you press R to rotate. Counterintuitively, this is
    different from what ``kicad-sch-api.get_pin_position()`` returns —
    that API has its own bug where it returns symbol-frame coords without
    the flip.

    Rotation values are KiCad-canonical: 0, 90, 180, 270.
    """
    flipped_x = symbol_relative.x
    flipped_y = -symbol_relative.y
    if rotation_deg == 0.0:
        rotated_x, rotated_y = flipped_x, flipped_y
    elif rotation_deg == 90.0:
        rotated_x, rotated_y = flipped_y, -flipped_x
    elif rotation_deg == 180.0:
        rotated_x, rotated_y = -flipped_x, -flipped_y
    elif rotation_deg == 270.0:
        rotated_x, rotated_y = -flipped_y, flipped_x
    else:
        raise ValueError(
            f"Unsupported rotation {rotation_deg!r}; KiCad allows 0/90/180/270 only"
        )
    return Point(rotated_x, rotated_y)


# Backward-compatible alias kept for any external imports.
_rotate_then_flip_y = _flip_y_then_rotate


def _visible_body_bbox_from_graphics(
    lib_id: str,
    rotation: float,
) -> "SymbolBoundingBox | None":
    """Return the bbox of the symbol's VISIBLE graphics (rectangle /
    polyline / circle / arc) in page coords relative to anchor (0, 0).

    Walks every graphics primitive defined in the symbol's
    ``.kicad_sym`` block — including the per-unit ``(symbol "X_0_1"
    ...)`` and ``(symbol "X_1_1" ...)`` sub-blocks — and aggregates
    their min/max into a single AABB. Applies the standard
    ``_flip_y_then_rotate`` transform so the returned coords match
    page space.

    Returns ``None`` when the symbol has no graphics blocks (e.g.
    pure-pin connector wrappers). Callers should fall back to
    pin-tip extents in that case.
    """
    symbol_def = ksa.get_symbol_cache().get_symbol(lib_id)
    if symbol_def is None:
        return None
    raw = getattr(symbol_def, "raw_kicad_data", None) or ()
    extents: list[tuple[float, float, float, float]] = []
    _gather_graphics_extents(raw, extents)
    if not extents:
        return None
    sym_min_x = min(e[0] for e in extents)
    sym_min_y = min(e[1] for e in extents)
    sym_max_x = max(e[2] for e in extents)
    sym_max_y = max(e[3] for e in extents)
    # Transform the four corners through the standard flip-then-rotate
    # so the bbox is in PAGE coords. Then re-derive min/max from the
    # rotated corners.
    corners = [
        _flip_y_then_rotate(Point(sym_min_x, sym_min_y), rotation),
        _flip_y_then_rotate(Point(sym_max_x, sym_min_y), rotation),
        _flip_y_then_rotate(Point(sym_min_x, sym_max_y), rotation),
        _flip_y_then_rotate(Point(sym_max_x, sym_max_y), rotation),
    ]
    return SymbolBoundingBox(
        min_x=min(c.x for c in corners),
        min_y=min(c.y for c in corners),
        max_x=max(c.x for c in corners),
        max_y=max(c.y for c in corners),
    )


def _gather_graphics_extents(
    node,
    out: list[tuple[float, float, float, float]],
) -> None:
    """Walk an S-expression node and append ``(min_x, min_y, max_x, max_y)``
    extents for every visible graphics primitive found inside.

    Recurses into nested ``(symbol "..._N_M" ...)`` sub-blocks so the
    per-unit graphics (which is where rectangles typically live) are
    captured.
    """
    if not isinstance(node, list):
        return
    if not node:
        return
    head = node[0]
    head_name = getattr(head, "value", lambda: None)()
    if head_name == "rectangle":
        # (rectangle (start X Y) (end X Y) ...)
        start = _read_xy_child(node, "start")
        end = _read_xy_child(node, "end")
        if start is not None and end is not None:
            min_x = min(start[0], end[0])
            min_y = min(start[1], end[1])
            max_x = max(start[0], end[0])
            max_y = max(start[1], end[1])
            out.append((min_x, min_y, max_x, max_y))
        return
    if head_name == "polyline":
        # (polyline (pts (xy X Y) (xy X Y) ...) ...)
        # Exclude points at the symbol origin (0, 0) — those are
        # typically pin-stub anchors (e.g. power:GND's polyline starts
        # at the pin tip (0,0) before drawing the triangle below).
        # Including the origin makes the body bbox extend up to the
        # pin tip, so any wire connecting to the pin's tip overlaps
        # the body bbox by the wire's thickness. The VISIBLE glyph
        # excludes the pin stub; the bbox should too.
        ORIGIN_TOL = 0.01
        pts: list[tuple[float, float]] = []
        for child in node[1:]:
            if isinstance(child, list) and child and getattr(child[0], "value", lambda: None)() == "pts":
                for xy in child[1:]:
                    if isinstance(xy, list) and len(xy) >= 3 and getattr(xy[0], "value", lambda: None)() == "xy":
                        try:
                            px, py = float(xy[1]), float(xy[2])
                        except (TypeError, ValueError):
                            continue
                        if abs(px) < ORIGIN_TOL and abs(py) < ORIGIN_TOL:
                            continue  # skip pin-stub anchor
                        pts.append((px, py))
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            out.append((min(xs), min(ys), max(xs), max(ys)))
        return
    if head_name == "circle":
        # (circle (center X Y) (radius R) ...)
        center = _read_xy_child(node, "center")
        radius = None
        for child in node[1:]:
            if isinstance(child, list) and child and getattr(child[0], "value", lambda: None)() == "radius":
                if len(child) >= 2:
                    try:
                        radius = float(child[1])
                    except (TypeError, ValueError):
                        radius = None
                break
        if center is not None and radius is not None:
            out.append((
                center[0] - radius, center[1] - radius,
                center[0] + radius, center[1] + radius,
            ))
        return
    if head_name == "arc":
        # (arc (start X Y) (mid X Y) (end X Y) ...)  conservative bbox
        # over all three vertices (overestimates slightly but never
        # underestimates).
        pts2: list[tuple[float, float]] = []
        for tag in ("start", "mid", "end"):
            v = _read_xy_child(node, tag)
            if v is not None:
                pts2.append(v)
        if pts2:
            xs = [p[0] for p in pts2]
            ys = [p[1] for p in pts2]
            out.append((min(xs), min(ys), max(xs), max(ys)))
        return
    # Recurse into nested blocks (unit sub-symbols).
    for child in node[1:]:
        if isinstance(child, list):
            _gather_graphics_extents(child, out)


def _property_is_hidden(prop_node: list) -> bool:
    """True iff the symbol property's ``(effects … hide)`` is set
    (or legacy ``(hide yes)``)."""
    for child in prop_node[1:]:
        if not isinstance(child, list) or not child:
            continue
        head_name = getattr(child[0], "value", lambda: None)()
        if head_name == "hide":
            # (hide yes) — older format
            if len(child) >= 2:
                val = getattr(child[1], "value", lambda: None)()
                if val == "yes":
                    return True
        elif head_name == "effects":
            # (effects ... hide) — newer format: bare "hide" token
            # OR (hide yes) nested.
            for eff in child[1:]:
                if not isinstance(eff, list):
                    if getattr(eff, "value", lambda: None)() == "hide":
                        return True
                    continue
                if not eff:
                    continue
                eff_head = getattr(eff[0], "value", lambda: None)()
                if eff_head == "hide":
                    if len(eff) >= 2:
                        val = getattr(eff[1], "value", lambda: None)()
                        if val == "yes":
                            return True
                    else:
                        return True
    return False


def _read_property_at(
    prop_node: list,
) -> tuple[float, float, float] | None:
    """Find ``(at X Y R)`` inside a property block. Returns ``(X, Y, R)``."""
    for child in prop_node[1:]:
        if not isinstance(child, list) or len(child) < 3:
            continue
        head_name = getattr(child[0], "value", lambda: None)()
        if head_name != "at":
            continue
        try:
            x = float(child[1])
            y = float(child[2])
            r = float(child[3]) if len(child) >= 4 else 0.0
            return (x, y, r)
        except (TypeError, ValueError):
            return None
    return None


def _read_xy_child(
    parent: list,
    tag: str,
) -> tuple[float, float] | None:
    """Find ``(tag X Y …)`` inside ``parent`` and return ``(X, Y)``."""
    for child in parent[1:]:
        if not isinstance(child, list) or len(child) < 3:
            continue
        head_name = getattr(child[0], "value", lambda: None)()
        if head_name != tag:
            continue
        try:
            return (float(child[1]), float(child[2]))
        except (TypeError, ValueError):
            return None
    return None


def _pin_rotation_from_symbol(lib_id: str, pin_number: str) -> float:
    """Look up a pin's library-defined rotation (0/90/180/270)."""
    symbol_def = ksa.get_symbol_cache().get_symbol(lib_id)
    if symbol_def is None:
        return 0.0
    for pin in symbol_def.pins:
        if pin.number == pin_number:
            return float(pin.rotation)
    return 0.0


def page_side_from_pin(
    pin_rotation: float,
    symbol_rotation: float = 0.0,
) -> str:
    """Determine which page-edge (left/right/top/bottom) a pin sits on.

    KiCad pin convention: ``pin.rotation`` indicates the direction from the
    pin's tip (electrical endpoint) INTO the symbol body. So:

        rotation   0 → body to the +X of tip → pin on LEFT edge of body
        rotation  90 → body to the +Y of tip → pin on BOTTOM edge of body
                       (in symbol coords where +Y is up; "bottom" means
                       smallest symbol-y; after Y-flip the pin still sits
                       at the body's bottom edge in PAGE coords since
                       smallest-symbol-y maps to largest-page-y, and on
                       the page +y is down → "bottom" visually).
        rotation 180 → body to the -X of tip → pin on RIGHT edge of body
        rotation 270 → body to the -Y of tip → pin on TOP edge of body

    The Y-flip just changes the SIGN of pin y-coordinates; it does NOT
    change which physical body edge a pin sits on. A pin at the "top"
    of the body in symbol frame (largest symbol-y) is still at the
    "top" of the body visually on the page (smallest page-y, i.e. above
    the anchor).

    If the placed symbol has its own rotation (0/90/180/270), the resulting
    page side rotates by that many CW quarter-turns on the page.

    Returns the page-relative side: ``"left"``, ``"right"``, ``"top"``,
    ``"bottom"``.
    """
    # Step 1: pin rotation → which body edge the pin sits on. The Y-flip
    # preserves edge identity (a top-edge pin is still a top-edge pin on
    # the page; the y SIGN flips but the body's edges keep their labels).
    pin_rotation_canonical = float(pin_rotation) % 360.0
    page_side_before_symrot = {
        0.0:   "left",    # pin tip on left edge, body to the right
        90.0:  "bottom",  # pin tip below body, body above
        180.0: "right",   # pin tip on right edge, body to the left
        270.0: "top",     # pin tip above body, body below
    }.get(pin_rotation_canonical, "left")

    # Step 2: rotate by symbol_rotation clockwise on the page.
    # A pin on "left" rotated 90° CW ends up on "top"; another 90° CW → "right"; etc.
    symbol_rotation_canonical = float(symbol_rotation) % 360.0
    cw_rotations = int(symbol_rotation_canonical // 90) % 4
    rotation_table = ["left", "top", "right", "bottom"]
    start_index = rotation_table.index(page_side_before_symrot)
    final_side = rotation_table[(start_index + cw_rotations) % 4]
    return final_side


# UUID constants for the ephemeral preview schematic kicad-sch-api requires.
_PREVIEW_PARENT_UUID = "00000000-0000-0000-0000-000000000001"
_PREVIEW_SHEET_UUID = "00000000-0000-0000-0000-000000000002"


@dataclass
class SymbolGeometryCache:
    """Resolve pin positions + bounding boxes by querying ``kicad-sch-api``.

    Workflow::

        cache = SymbolGeometryCache()
        cache.register_libraries((Path("shared/symbols/zynq_eda.kicad_sym"),))
        pin = cache.absolute_pin_by_name("zynq_eda:FUSB302BMPX",
                                          anchor=Point(100, 100),
                                          pin_name="VBUS")
        bbox = cache.bounding_box("zynq_eda:FUSB302BMPX")

    Library registration is idempotent. Pin-position lookups create a small
    throwaway schematic that is never saved.
    """

    _loaded_library_paths: set[Path] = field(default_factory=set)
    _bbox_cache: dict[tuple[str, float, bool], SymbolBoundingBox] = field(default_factory=dict)
    _pins_cache: dict[tuple[str, float], tuple[dict[str, object], ...]] = field(
        default_factory=dict,
    )

    def register_libraries(self, library_paths: tuple[Path, ...]) -> None:
        symbol_cache = ksa.get_symbol_cache()
        for library_path in library_paths:
            resolved_path = library_path.resolve()
            if resolved_path in self._loaded_library_paths:
                continue
            if not resolved_path.exists():
                raise FileNotFoundError(
                    f"SymbolGeometryCache: library not found: {resolved_path}"
                )
            symbol_cache.add_library_path(resolved_path)
            self._loaded_library_paths.add(resolved_path)

    # ----- private: preview-component construction --------------------------

    def _preview_component(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float,
    ):
        preview_schematic = ksa.create_schematic("_geometry_preview")
        preview_schematic.set_hierarchy_context(
            parent_uuid=_PREVIEW_PARENT_UUID,
            sheet_uuid=_PREVIEW_SHEET_UUID,
        )
        return preview_schematic.components.add(
            lib_id,
            reference="TP1",
            value="_PREVIEW",
            position=anchor.as_tuple(),
            rotation=rotation,
        )

    def _list_pin_infos(self, lib_id: str, rotation: float) -> tuple[dict[str, object], ...]:
        cache_key = (lib_id, rotation)
        cached = self._pins_cache.get(cache_key)
        if cached is not None:
            return cached
        # Pins are anchor-invariant under translation; query at origin.
        preview = self._preview_component(lib_id, Point(0.0, 0.0), rotation)
        infos = tuple(preview.list_pins())
        self._pins_cache[cache_key] = infos
        return infos

    def _resolve_pin_geometry(
        self,
        preview_component,
        pin_number: str,
    ) -> PinGeometry:
        """Return the pin's PAGE-coordinate position.

        ``kicad-sch-api``'s ``get_pin_position`` does NOT apply the Y-flip
        between symbol-local coords (+Y up, KiCad symbol editor convention)
        and schematic-page coords (+Y down). It returns
        ``component.position + symbol_relative_pin_position`` directly,
        which puts the pin on the wrong side of the symbol vertically.

        We recompute manually: use the placed component's position as the
        anchor, take the pin's symbol-relative position from ``list_pins``,
        and apply the symbol-to-page Y-flip ourselves. Rotation is currently
        passed through to kicad-sch-api (only rotation 0 confirmed affected;
        rotations 90/180/270 will be handled when the layout engine starts
        using non-zero rotations on ICs).

        The pin's own ``rotation`` (the direction the pin's tip-to-body
        stub extends in the KiCad symbol library) is also recovered from
        the underlying ``SchematicPin`` so callers can determine the
        page-side a pin sits on without resorting to position-axis
        heuristics. For ICs with densely-packed pins on a single edge
        (e.g. FUSB302's 7 left-column pins spanning ±7.62 mm in y), the
        axis-dominance heuristic mis-classifies the corner pins as top/
        bottom, which collapses unrelated nets onto the same coordinate.
        """
        component_position = preview_component.position
        component_rotation = float(getattr(preview_component, "rotation", 0.0))
        pin_info = next(
            item
            for item in preview_component.list_pins()
            if item["number"] == pin_number
        )
        symbol_relative = Point(
            float(pin_info["position"].x),
            float(pin_info["position"].y),
        )
        page_relative = _flip_y_then_rotate(symbol_relative, component_rotation)
        anchor = Point(
            snap_to_grid(component_position.x + page_relative.x),
            snap_to_grid(component_position.y + page_relative.y),
        )
        # Recover the pin's own (library-level) rotation. ``list_pins`` flattens
        # SchematicPin fields into a dict but currently omits ``rotation``,
        # so we read it directly from the cached SymbolDefinition.
        pin_rotation = _pin_rotation_from_symbol(
            preview_component.lib_id,
            pin_number,
        )
        return PinGeometry(
            anchor=anchor,
            connection=anchor,
            relative=symbol_relative,
            pin_rotation=pin_rotation,
            symbol_rotation=component_rotation,
        )

    # ----- public API -------------------------------------------------------

    def absolute_pin_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> Point:
        """Return the absolute wire-attachment point for the named pin.

        Pin matching tries ``pin_name`` against the symbol's pin *names* first,
        then its pin *numbers* (so callers can pass either).
        """
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            if pin_info["name"] == pin_name or pin_info["number"] == pin_name:
                return self._resolve_pin_geometry(
                    preview_component,
                    pin_info["number"],
                ).connection
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r}"
        )

    def pin_geometry_by_name(
        self,
        lib_id: str,
        anchor: Point,
        pin_name: str,
        rotation: float = 0.0,
    ) -> PinGeometry:
        """Full geometry (anchor + connection + relative) for the named pin."""
        preview_component = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview_component.list_pins():
            if pin_info["name"] == pin_name or pin_info["number"] == pin_name:
                return self._resolve_pin_geometry(
                    preview_component,
                    pin_info["number"],
                )
        raise KeyError(
            f"Symbol {lib_id!r} has no pin named {pin_name!r}"
        )

    def all_pins(
        self,
        lib_id: str,
        rotation: float = 0.0,
    ) -> Iterator[dict[str, object]]:
        """Yield every pin's info dict (name, number, position, ...)."""
        for pin_info in self._list_pin_infos(lib_id, rotation):
            yield pin_info

    def absolute_pin_positions(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
    ) -> dict[str, Point]:
        """Return pin-number → absolute wire connection point."""
        preview_component = self._preview_component(lib_id, anchor, rotation)
        positions: dict[str, Point] = {}
        for pin_info in preview_component.list_pins():
            positions[pin_info["number"]] = self._resolve_pin_geometry(
                preview_component,
                pin_info["number"],
            ).connection
        return positions

    def bounding_box(
        self,
        lib_id: str,
        rotation: float = 0.0,
        body_padding_mm: float = DEFAULT_PIN_LENGTH_MM,
        tight_body: bool = True,
    ) -> SymbolBoundingBox:
        """Return the symbol's VISIBLE body bbox in page coords.

        The body is the rectangle KiCad actually paints — derived from
        the ``(rectangle …)``, ``(polyline …)``, ``(circle …)``, and
        ``(arc …)`` graphics blocks in the symbol's ``.kicad_sym``
        definition. Pin stubs are NOT included; pin tips sit one
        ``length`` outboard of the visible body edge.

        Symbols without any graphics blocks (rare — most are pure-pin
        wrapper symbols like the generated bank symbols) fall back to
        the convex hull of pin TIPS inset by one pin length, which is
        a reasonable approximation of "where the body would be drawn".

        The ``body_padding_mm`` and ``tight_body`` parameters are kept
        for backwards compatibility but no longer affect behaviour —
        the bbox is always the visible body extent.
        """
        cache_key = (lib_id, rotation, "visible")
        cached = self._bbox_cache.get(cache_key)
        if cached is not None:
            return cached

        # First try the explicit graphics blocks. This gives the bbox
        # KiCad actually paints — independent of where pin tips sit.
        graphics_box = _visible_body_bbox_from_graphics(lib_id, rotation)
        if graphics_box is not None:
            self._bbox_cache[cache_key] = graphics_box
            return graphics_box

        # Fallback: convex hull of pin tips, inset by one pin length so
        # the box approximates where the body edge SHOULD be. This is
        # for graphics-less symbols (some custom wrappers).
        preview = self._preview_component(lib_id, Point(0.0, 0.0), rotation)
        pin_tips: list[Point] = []
        for pin_info in preview.list_pins():
            position = pin_info["position"]
            symbol_relative = Point(float(position.x), float(position.y))
            page_relative = _flip_y_then_rotate(symbol_relative, rotation)
            pin_tips.append(page_relative)

        if not pin_tips:
            box = SymbolBoundingBox(
                min_x=-body_padding_mm,
                min_y=-body_padding_mm,
                max_x=body_padding_mm,
                max_y=body_padding_mm,
            )
        else:
            min_x = min(p.x for p in pin_tips)
            max_x = max(p.x for p in pin_tips)
            min_y = min(p.y for p in pin_tips)
            max_y = max(p.y for p in pin_tips)
            inset = DEFAULT_PIN_LENGTH_MM
            x_inset = inset if (max_x - min_x) > 2.0 * inset else 0.0
            y_inset = inset if (max_y - min_y) > 2.0 * inset else 0.0
            box_min_x = min_x + x_inset
            box_min_y = min_y + y_inset
            box_max_x = max_x - x_inset
            box_max_y = max_y - y_inset
            # Symbols whose pins all sit on a single line (cap/resistor
            # with both pins on the same X column) collapse to a line
            # here. Give them a tiny 0.05 mm half-extent on the
            # collapsed axis so wires perpendicular to the body
            # register, but DON'T extend bbox in a way that grazes
            # labels anchored at the pin tip.
            COLLAPSED_HALF_EXTENT_MM = 0.05
            if (box_max_x - box_min_x) < 0.01:
                center_x = (box_min_x + box_max_x) / 2.0
                box_min_x = center_x - COLLAPSED_HALF_EXTENT_MM
                box_max_x = center_x + COLLAPSED_HALF_EXTENT_MM
            if (box_max_y - box_min_y) < 0.01:
                center_y = (box_min_y + box_max_y) / 2.0
                box_min_y = center_y - COLLAPSED_HALF_EXTENT_MM
                box_max_y = center_y + COLLAPSED_HALF_EXTENT_MM
            box = SymbolBoundingBox(
                min_x=box_min_x,
                min_y=box_min_y,
                max_x=box_max_x,
                max_y=box_max_y,
            )

        self._bbox_cache[cache_key] = box
        return box

    # ---------------------------------------------------------------------
    # Intrinsic text bbox helpers — pin NAME + pin NUMBER labels KiCad
    # renders from the .kicad_sym definition at emit time. These are NOT
    # PlacedLabel primitives the engine creates; they're painted by the
    # schematic editor based on each pin's (name "...") + (number "...")
    # fields and the symbol's (pin_names ...) / (pin_numbers ...)
    # directives. Without registering their bboxes in occupancy, our
    # PlacedLabels and cluster passives land on top of them on dense
    # connectors (USB-C, FX10A, FFC). See Wave D.
    # ---------------------------------------------------------------------

    def _read_pin_text_directives(
        self, lib_id: str
    ) -> tuple[tuple[float, bool], tuple[float, bool]]:
        """Return ((name_offset_mm, name_hidden), (number_offset_mm, number_hidden)).

        KiCad defaults when the directive is absent:
          pin_names   → offset 0.508 mm, hide no
          pin_numbers → offset 0      (no offset concept; numbers render
                                       above the pin line), hide no

        We use 0.508 as the default pin_name offset because that's KiCad's
        own default; an explicit ``(pin_names (offset N))`` overrides it.
        """
        import sexpdata as _sx

        cache_key = ("_pin_text_directives", lib_id)
        cached = self._bbox_cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        symbol_def = _ksa_get_symbol_cache().get_symbol(lib_id)
        name_offset, name_hidden = 0.508, False
        num_offset, num_hidden = 0.0, False
        if symbol_def is not None:
            raw = getattr(symbol_def, "raw_kicad_data", None) or ()
            for item in raw:
                if not isinstance(item, list) or not item:
                    continue
                head = item[0]
                head_name = getattr(head, "value", lambda: None)()
                if head_name == "pin_names":
                    name_offset, name_hidden = _parse_pin_text_directive(
                        item, default_offset=0.508
                    )
                elif head_name == "pin_numbers":
                    num_offset, num_hidden = _parse_pin_text_directive(
                        item, default_offset=0.0
                    )

        result = ((name_offset, name_hidden), (num_offset, num_hidden))
        self._bbox_cache[cache_key] = result  # type: ignore[assignment]
        return result

    def intrinsic_pin_label_bboxes(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
        *,
        owner_id: str = "",
    ):
        """Return PAGE-coord bboxes for every intrinsic pin-NAME label.

        When the symbol's ``(pin_names (hide yes))`` directive applies,
        returns an empty tuple (no labels are rendered).

        For each visible pin:
          - anchor at pin tip + ``pin_names_offset`` INTO the body
          - rotation derived from the pin's page-side (so text reads from
            the tip toward the body interior)
          - justify so the text grows AWAY from the pin tip

        The text width is conservatively over-estimated via :func:`text_bbox`.
        """
        from zynq_eda.core.layout.bbox import (
            BBox,
            DEFAULT_TEXT_SIZE_MM,
            text_bbox,
        )

        (name_offset, name_hidden), _ = self._read_pin_text_directives(lib_id)
        if name_hidden:
            return ()

        # Pre-fetch pin number → rotation map for page-side computation.
        # Reuse the existing _pin_rotation_from_symbol helper.
        bboxes = []
        preview = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview.list_pins():
            name = str(pin_info.get("name", "") or "")
            if not name or name == "~":
                continue
            pin_number = str(pin_info["number"])
            symbol_relative = Point(
                float(pin_info["position"].x),
                float(pin_info["position"].y),
            )
            page_relative = _flip_y_then_rotate(symbol_relative, rotation)
            pin_tip_abs = Point(
                anchor.x + page_relative.x,
                anchor.y + page_relative.y,
            )
            pin_rot = _pin_rotation_from_symbol(lib_id, pin_number)
            side = page_side_from_pin(pin_rot, rotation)

            # Position the name's text-anchor + justify per page-side.
            # Text grows INTO the symbol body (away from the pin tip).
            if side == "left":
                # Tip on left edge, body extends RIGHT.
                # Name text starts ``name_offset`` to the RIGHT of tip,
                # reads LEFT-to-RIGHT.
                text_anchor = Point(pin_tip_abs.x + name_offset, pin_tip_abs.y)
                text_justify: str = "left"
                text_rotation = 0.0
            elif side == "right":
                # Tip on right edge, body extends LEFT.
                text_anchor = Point(pin_tip_abs.x - name_offset, pin_tip_abs.y)
                text_justify = "right"
                text_rotation = 0.0
            elif side == "top":
                # Tip on top edge, body extends DOWN.
                # Text reads top-to-bottom from the body inward.
                text_anchor = Point(pin_tip_abs.x, pin_tip_abs.y + name_offset)
                text_justify = "left"
                text_rotation = 90.0
            else:  # bottom
                text_anchor = Point(pin_tip_abs.x, pin_tip_abs.y - name_offset)
                text_justify = "right"
                text_rotation = 90.0

            bbox = text_bbox(
                text=name,
                anchor=text_anchor,
                size_mm=DEFAULT_TEXT_SIZE_MM,
                rotation=text_rotation,
                justify=text_justify,  # type: ignore[arg-type]
                owner_id=f"{owner_id}:pin_name:{pin_number}" if owner_id else f"pin_name:{pin_number}",
                kind="intrinsic_pin_name",
            )
            bboxes.append(bbox)
        return tuple(bboxes)

    def intrinsic_pin_number_bboxes(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
        *,
        owner_id: str = "",
    ):
        """Return PAGE-coord bboxes for every intrinsic pin-NUMBER label.

        Pin numbers render PERPENDICULAR to the pin line, slightly above
        the line near the pin tip. KiCad's default offset is ~0.51 mm
        above the line; text size matches pin_name.

        When ``(pin_numbers (hide yes))`` applies, returns ().
        """
        from zynq_eda.core.layout.bbox import (
            BBox,
            DEFAULT_TEXT_SIZE_MM,
            text_bbox,
        )

        _, (_num_offset, num_hidden) = self._read_pin_text_directives(lib_id)
        if num_hidden:
            return ()

        # Pin number sits ABOVE the pin line, halfway along the stub
        # (between tip and body edge). Stub length is typically 2.54 mm.
        # For LEFT-edge pin: number text at (tip.x + 1.27, tip.y - 0.6 mm).
        # The slight vertical offset above the line is what makes the
        # text visible on dense connectors.
        OFFSET_ALONG_PIN = 1.27  # halfway along the 2.54 mm stub
        OFFSET_ABOVE_LINE = 0.6  # bumps text above the pin line

        bboxes = []
        preview = self._preview_component(lib_id, anchor, rotation)
        for pin_info in preview.list_pins():
            pin_number = str(pin_info["number"])
            if not pin_number:
                continue
            symbol_relative = Point(
                float(pin_info["position"].x),
                float(pin_info["position"].y),
            )
            page_relative = _flip_y_then_rotate(symbol_relative, rotation)
            pin_tip_abs = Point(
                anchor.x + page_relative.x,
                anchor.y + page_relative.y,
            )
            pin_rot = _pin_rotation_from_symbol(lib_id, pin_number)
            side = page_side_from_pin(pin_rot, rotation)

            if side == "left":
                # Number sits between tip and body, above the line.
                text_anchor = Point(
                    pin_tip_abs.x + OFFSET_ALONG_PIN,
                    pin_tip_abs.y - OFFSET_ABOVE_LINE,
                )
                text_justify: str = "center"
                text_rotation = 0.0
            elif side == "right":
                text_anchor = Point(
                    pin_tip_abs.x - OFFSET_ALONG_PIN,
                    pin_tip_abs.y - OFFSET_ABOVE_LINE,
                )
                text_justify = "center"
                text_rotation = 0.0
            elif side == "top":
                text_anchor = Point(
                    pin_tip_abs.x + OFFSET_ABOVE_LINE,
                    pin_tip_abs.y + OFFSET_ALONG_PIN,
                )
                text_justify = "center"
                text_rotation = 90.0
            else:  # bottom
                text_anchor = Point(
                    pin_tip_abs.x + OFFSET_ABOVE_LINE,
                    pin_tip_abs.y - OFFSET_ALONG_PIN,
                )
                text_justify = "center"
                text_rotation = 90.0

            bbox = text_bbox(
                text=pin_number,
                anchor=text_anchor,
                size_mm=DEFAULT_TEXT_SIZE_MM,
                rotation=text_rotation,
                justify=text_justify,  # type: ignore[arg-type]
                owner_id=f"{owner_id}:pin_number:{pin_number}" if owner_id else f"pin_number:{pin_number}",
                kind="intrinsic_pin_number",
            )
            bboxes.append(bbox)
        return tuple(bboxes)

    def property_text_bboxes(
        self,
        lib_id: str,
        anchor: Point,
        rotation: float = 0.0,
        *,
        owner_id: str = "",
        value_override: str | None = None,
        reference_override: str | None = None,
        value_shift: "tuple[float, float, float | None] | None" = None,
        reference_shift: "tuple[float, float, float | None] | None" = None,
    ):
        """Return PAGE-coord bboxes for every visible property text on a
        placed symbol.

        Inspects the ``(property "Reference" "..." (at PX PY R) (effects ...))``
        and ``(property "Value" ...)`` blocks in the symbol's library
        definition. Properties with ``(effects ... hide)`` (or
        ``(hide yes)``) are skipped — KiCad won't render them.

        ``value_override`` and ``reference_override`` substitute the
        actual text strings the placement engine will write into the
        emitted sheet (e.g. "C100" / "4u7" instead of the library
        defaults "C" / "C").
        """
        from zynq_eda.core.layout.bbox import (
            DEFAULT_TEXT_SIZE_MM,
            text_bbox,
        )

        symbol_def = _ksa_get_symbol_cache().get_symbol(lib_id)
        if symbol_def is None:
            return ()
        raw = getattr(symbol_def, "raw_kicad_data", None) or ()

        bboxes = []
        for item in raw:
            if not isinstance(item, list) or not item:
                continue
            head_name = getattr(item[0], "value", lambda: None)()
            if head_name != "property":
                continue
            if len(item) < 3:
                continue
            prop_name = item[1] if isinstance(item[1], str) else None
            prop_text = item[2] if isinstance(item[2], str) else None
            if prop_name not in ("Reference", "Value"):
                continue
            if _property_is_hidden(item):
                continue
            at_xy_rot = _read_property_at(item)
            if at_xy_rot is None:
                continue
            prop_x, prop_y, _prop_rot = at_xy_rot
            # Position relative to symbol anchor, in SYMBOL coords.
            sym_relative = Point(prop_x, prop_y)
            page_relative = _flip_y_then_rotate(sym_relative, rotation)
            text_anchor = Point(
                anchor.x + page_relative.x,
                anchor.y + page_relative.y,
            )
            # The post-emit patch shifts the Value property for known
            # passive lib_ids to keep its text off the body. Mirror that
            # shift here so the validator's bbox matches what KiCad
            # actually renders. Without this, the validator computes
            # the LIB-default position (body centre) while the .kicad_sch
            # has the property at the shifted position, producing both
            # false positives (validator flags non-overlap) and false
            # negatives (validator misses real shifted-property overlaps).
            if prop_name == "Value":
                # Prefer the per-instance shift (resolved at placement
                # time against occupancy); fall back to the static
                # default per lib_id.
                shift = value_shift or VALUE_SHIFT_BY_LIB_ID.get(lib_id)
                if shift is not None:
                    dx, dy, _text_rot_override = shift
                    sym_rot = int(rotation) % 360
                    if sym_rot == 0:
                        rdx, rdy = dx, dy
                    elif sym_rot == 90:
                        rdx, rdy = dy, -dx
                    elif sym_rot == 180:
                        rdx, rdy = -dx, -dy
                    elif sym_rot == 270:
                        rdx, rdy = -dy, dx
                    else:
                        rdx, rdy = dx, dy
                    text_anchor = Point(
                        anchor.x + rdx,
                        anchor.y + rdy,
                    )
            elif prop_name == "Reference":
                shift = reference_shift or REFERENCE_SHIFT_BY_LIB_ID.get(lib_id)
                if shift is not None:
                    dx, dy, _text_rot_override = shift
                    sym_rot = int(rotation) % 360
                    if sym_rot == 0:
                        rdx, rdy = dx, dy
                    elif sym_rot == 90:
                        rdx, rdy = dy, -dx
                    elif sym_rot == 180:
                        rdx, rdy = -dx, -dy
                    elif sym_rot == 270:
                        rdx, rdy = -dy, dx
                    else:
                        rdx, rdy = dx, dy
                    text_anchor = Point(
                        anchor.x + rdx,
                        anchor.y + rdy,
                    )
            # Substitute the actual text the engine will emit.
            display_text = prop_text or ""
            if prop_name == "Reference" and reference_override is not None:
                display_text = reference_override
            elif prop_name == "Value" and value_override is not None:
                display_text = value_override
            # Reference / Value render center-justified by default.
            bbox = text_bbox(
                text=display_text,
                anchor=text_anchor,
                size_mm=DEFAULT_TEXT_SIZE_MM,
                rotation=0.0,
                justify="center",
                owner_id=f"{owner_id}:property:{prop_name}" if owner_id else f"property:{prop_name}",
                kind="symbol",
            )
            bboxes.append(bbox)
        return tuple(bboxes)


def _ksa_get_symbol_cache():
    """Lazy import so the helper can live below the class definition."""
    import kicad_sch_api as _ksa
    return _ksa.get_symbol_cache()


def _parse_pin_text_directive(
    directive_sexp: list,
    *,
    default_offset: float,
) -> tuple[float, bool]:
    """Parse a ``(pin_names ...)`` or ``(pin_numbers ...)`` s-expression.

    Returns ``(offset_mm, hide_bool)``. Missing tokens default to
    ``(default_offset, False)``.
    """
    offset = default_offset
    hide = False
    for token in directive_sexp[1:]:
        if not isinstance(token, list) or not token:
            continue
        head_name = getattr(token[0], "value", lambda: None)()
        if head_name == "offset" and len(token) > 1:
            try:
                offset = float(token[1])
            except (TypeError, ValueError):
                pass
        elif head_name == "hide" and len(token) > 1:
            val = getattr(token[1], "value", lambda: None)()
            hide = (val == "yes")
    return offset, hide
