"""Overlap validator: AABB collision detection on placed primitives.

This validator runs *after* a :class:`Sheet` is fully laid out (and
before emission), so it sees every symbol, wire, label, junction, and
hierarchical label in their final page coordinates. For each placed
primitive it reconstructs a bounding box via the helpers in
:mod:`zynq_eda.core.layout.bbox`, then scans for overlapping pairs in a
fixed order of categories.

Checks (in order):

  1. ``symbol×symbol`` — symbol bodies cannot overlap (power symbols
     are exempt; multiple ``#PWR…`` GND symbols legitimately stack on
     the same anchor).
  2. ``symbol×label`` — a label's text box cannot overlap a symbol's body.
  3. ``label×label`` — two text boxes cannot overlap each other; both
     local and hierarchical labels participate.
  4. ``wire×label`` — a label cannot sit on (or immediately adjacent to)
     a wire — that's the classic "VBUS_J3" floating on top of a power
     wire that the new spatial-awareness work is designed to eliminate.
  5. ``wire×symbol`` — a wire cannot cross through a symbol body
     mid-route. Wires endpoints that touch a symbol's pin are NOT
     reported (that's the whole point of pins); only wires whose
     bbox overlaps the symbol body more than a pin-stub length count.
  6. ``wire×wire`` — two wires whose bboxes overlap and share an axis
     (both horizontal at the same y, or both vertical at the same x)
     are flagged. KiCad merges electrically-equivalent overlapping
     wires into one net, but visually this is still wrong.

Power-symbol clusters (``#PWR…`` references) are allowed to coincide
because multiple GND symbols legitimately share a position when each
decoupling cap drops its own GND drop. We exempt them from symbol×symbol
only — the labels above them still must be visible.

Severity is controlled by ``strict``:

  * ``strict=True``  — every overlap is reported as ``"error"`` (gates emission).
  * ``strict=False`` — every overlap is reported as ``"warning"`` (advisory).

Wave A keeps the default at ``strict=False`` so the carrier can still
generate while the placement engine is being upgraded; Wave B will flip
the default to ``True`` once the router lands and the count drops to zero.
"""

from __future__ import annotations

from typing import Iterable

from zynq_eda.core.layout.bbox import (
    BBox,
    BBoxKind,
    placeholder_symbol_bbox,
    symbol_bbox,
    text_bbox,
    wire_bbox,
)
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedSheet,
    PlacedSymbol,
    PlacedWire,
    Sheet,
)
from zynq_eda.core.validate.report import Severity, ValidationResult


# ---- Tolerances ------------------------------------------------------------

OVERLAP_MIN_DIMENSION_MM: float = 0.1
"""Minimum overlap dimension (mm) before a collision is reported.

Bboxes whose intersection rectangle is thinner than this on *both* axes
are treated as numerical noise and ignored. Picked at 0.1 mm so we
filter floating-point rounding without missing real visual overlaps
(KiCad's smallest visible glyph stroke is 0.10–0.12 mm at typical
zoom levels).
"""

LABEL_WIRE_PADDING_MM: float = 0.0
"""Extra padding applied to label×wire checks.

The wire bbox already includes :data:`~zynq_eda.core.layout.bbox.DEFAULT_WIRE_CLEARANCE_MM`
on every side, so we don't need additional padding here.
"""

WIRE_SYMBOL_PADDING_MM: float = 0.0
"""Extra padding applied to wire×symbol checks.

Symbol bboxes already include pin-stub padding from
:meth:`SymbolGeometryCache.bounding_box`. Anything extra would cause
every wire that legitimately connects to a pin to flag.
"""


# ---- Helpers ---------------------------------------------------------------

def _is_power_symbol_reference(reference: str) -> bool:
    """True for KiCad power-flag references (``#PWR001`` etc.)."""
    return reference.startswith("#PWR") or reference.startswith("#FLG")


def _format_point(p) -> str:
    """Render a Point as ``(x.x, y.y)`` for messages."""
    return f"({p.x:.1f}, {p.y:.1f})"


def _label_text_bbox(label: PlacedLabel) -> BBox:
    """Bbox for a local-scope ``PlacedLabel``.

    KiCad renders local labels with the text starting at the anchor and
    extending to the right (justify="left") at the label's rotation.
    """
    return text_bbox(
        text=label.net_name,
        anchor=label.position,
        rotation=label.rotation,
        justify="left",
        owner_id=f"label:{label.net_name}@{label.position.x:.1f},{label.position.y:.1f}",
        kind="label",
    )


def _hierarchical_label_text_bbox(label: PlacedHierarchicalLabel) -> BBox:
    """Bbox for a ``PlacedHierarchicalLabel``.

    Hierarchical labels include a directional arrow glyph that adds ~1.5×
    the text height on the leading edge — we approximate with a slightly
    wider character count to keep the bbox conservative.
    """
    # Hierarchical labels are typically left-justified at their anchor when
    # placed on the LEFT edge of a sheet and right-justified on the RIGHT.
    # The actual justify depends on rotation — KiCad's emitter uses
    # rotation=0 for "text reads right" and rotation=180 for "text reads
    # left". We treat rotation=180 as right-justified.
    justify = "right" if label.rotation == 180.0 else "left"
    # Reserve room for the arrow glyph (~1 character wide).
    decorated_text = label.net_name + " "
    return text_bbox(
        text=decorated_text,
        anchor=label.position,
        rotation=label.rotation,
        justify=justify,
        owner_id=f"hlabel:{label.net_name}@{label.position.x:.1f},{label.position.y:.1f}",
        kind="hierarchical_label",
    )


def _symbol_body_bbox(
    placed: PlacedSymbol,
    geometry: SymbolGeometryCache | None,
) -> BBox:
    """Bbox for a ``PlacedSymbol``.

    Uses the real symbol geometry when ``geometry`` is provided;
    otherwise falls back to a 12.7 × 12.7 mm placeholder so unit tests
    that don't register libraries still get sensible output.
    """
    owner_id = f"symbol:{placed.reference}"
    if geometry is None:
        return placeholder_symbol_bbox(placed.position, owner_id=owner_id)
    try:
        return symbol_bbox(
            lib_id=placed.lib_id,
            anchor=placed.position,
            rotation=placed.rotation,
            cache=geometry,
            owner_id=owner_id,
        )
    except Exception:
        # If the library isn't registered, fall back to the placeholder
        # so the validator still produces useful output.
        return placeholder_symbol_bbox(placed.position, owner_id=owner_id)


def _sheet_symbol_bbox(placed: PlacedSheet) -> BBox:
    """Bbox for a root-sheet ``PlacedSheet`` (sub-sheet rectangle)."""
    from zynq_eda.core.layout.bbox import BBox as _BBox
    from zynq_eda.core.model.grid import Point as _Point

    width, height = placed.size
    return _BBox(
        min=_Point(placed.position.x, placed.position.y),
        max=_Point(placed.position.x + width, placed.position.y + height),
        kind="sheet",
        owner_id=f"sheet:{placed.name}",
    )


def _wire_segment_bbox(index: int, wire: PlacedWire) -> BBox:
    """Bbox for a ``PlacedWire`` segment. Owner id includes the wire index."""
    return wire_bbox(
        start=wire.start,
        end=wire.end,
        owner_id=f"wire_{index}",
    )


def _overlap_is_significant(a: BBox, b: BBox) -> bool:
    """True iff the bboxes overlap by more than the noise tolerance.

    Computes the intersection rectangle and requires that BOTH its
    width and its height exceed :data:`OVERLAP_MIN_DIMENSION_MM`.
    Thin slivers caused by floating-point rounding (e.g. a wire bbox
    grazing a perpendicular wire's clearance) are filtered out.
    """
    intersection = a.intersection(b)
    if intersection is None:
        return False
    return (
        intersection.width >= OVERLAP_MIN_DIMENSION_MM
        and intersection.height >= OVERLAP_MIN_DIMENSION_MM
    )


def _result_from_overlap(
    sheet: Sheet,
    rule_id: str,
    severity: Severity,
    left: BBox,
    right: BBox,
    strict: bool,
    description_left: str,
    description_right: str,
) -> ValidationResult:
    """Build a :class:`ValidationResult` describing an overlapping pair.

    The message includes both owner ids, both kinds, and the approximate
    centre point of each bbox so the user can pop straight to the
    offending coordinate in KiCad.
    """
    suffix = " [strict=True]" if strict else " [strict=False]"
    message = (
        f"{description_left} @ {_format_point(left.center)} "
        f"overlaps {description_right} @ {_format_point(right.center)}{suffix}"
    )
    return ValidationResult(
        rule_id=rule_id,
        severity=severity,
        message=message,
        location=f"{sheet.name}.kicad_sch",
    )


def _wires_share_axis(left: PlacedWire, right: PlacedWire) -> bool:
    """True iff two wires share an axis (both horizontal at same y, etc.).

    A wire is horizontal iff ``start.y == end.y`` and vertical iff
    ``start.x == end.x``. Two horizontal wires share an axis iff their
    y-coordinates match within :data:`OVERLAP_MIN_DIMENSION_MM`; same
    for vertical wires.
    """
    left_horizontal = abs(left.start.y - left.end.y) < OVERLAP_MIN_DIMENSION_MM
    right_horizontal = abs(right.start.y - right.end.y) < OVERLAP_MIN_DIMENSION_MM
    left_vertical = abs(left.start.x - left.end.x) < OVERLAP_MIN_DIMENSION_MM
    right_vertical = abs(right.start.x - right.end.x) < OVERLAP_MIN_DIMENSION_MM

    if left_horizontal and right_horizontal:
        return abs(left.start.y - right.start.y) < OVERLAP_MIN_DIMENSION_MM
    if left_vertical and right_vertical:
        return abs(left.start.x - right.start.x) < OVERLAP_MIN_DIMENSION_MM
    return False


def _wires_share_endpoint(left: PlacedWire, right: PlacedWire) -> bool:
    """True iff two wires share a start/end point (legitimate T or +)."""
    endpoints_left = (left.start, left.end)
    endpoints_right = (right.start, right.end)
    for p_left in endpoints_left:
        for p_right in endpoints_right:
            if (
                abs(p_left.x - p_right.x) < OVERLAP_MIN_DIMENSION_MM
                and abs(p_left.y - p_right.y) < OVERLAP_MIN_DIMENSION_MM
            ):
                return True
    return False


# ---- Public entry point ----------------------------------------------------

def validate_overlap(
    sheet: Sheet,
    *,
    geometry: SymbolGeometryCache | None = None,
    strict: bool = False,
) -> list[ValidationResult]:
    """Detect bounding-box overlaps among placed primitives on ``sheet``.

    For each pair of primitives the function builds an axis-aligned
    bounding box (via :mod:`zynq_eda.core.layout.bbox`) and reports an
    overlap when the boxes intersect by more than
    :data:`OVERLAP_MIN_DIMENSION_MM`. Power symbol bodies are exempted
    from the symbol×symbol check because multiple GND symbols
    legitimately stack on the same anchor.

    Args:
        sheet: The placed :class:`Sheet` to validate.
        geometry: Optional :class:`SymbolGeometryCache`. When provided,
            real symbol bounding boxes are used. When None, every symbol
            falls back to a 12.7 × 12.7 mm placeholder (useful in unit
            tests where library registration is too expensive).
        strict: Severity selector. ``True`` → every overlap is an
            ``"error"`` (gates emission); ``False`` → every overlap is
            a ``"warning"``.

    Returns:
        A list of :class:`ValidationResult`. Empty when the sheet is
        clean. Ordered to match the check order documented above.
    """
    severity: Severity = "error" if strict else "warning"
    results: list[ValidationResult] = []

    # ---- Reconstruct bboxes for every category --------------------------
    # PlacedSymbol bodies (excluding ones from PlacedSheet)
    symbol_bboxes: list[tuple[PlacedSymbol, BBox]] = []
    for placed in sheet.symbols:
        bbox = _symbol_body_bbox(placed, geometry=geometry)
        symbol_bboxes.append((placed, bbox))

    label_bboxes: list[tuple[PlacedLabel, BBox]] = [
        (label, _label_text_bbox(label)) for label in sheet.labels
    ]
    hlabel_bboxes: list[tuple[PlacedHierarchicalLabel, BBox]] = [
        (hlabel, _hierarchical_label_text_bbox(hlabel))
        for hlabel in sheet.hierarchical_labels
    ]
    wire_bboxes: list[tuple[int, PlacedWire, BBox]] = [
        (index, wire, _wire_segment_bbox(index, wire))
        for index, wire in enumerate(sheet.wires)
    ]
    sheet_bboxes: list[tuple[PlacedSheet, BBox]] = [
        (placed, _sheet_symbol_bbox(placed)) for placed in sheet.sheets
    ]

    # ---- 1. symbol × symbol --------------------------------------------
    for i, (sym_a, bbox_a) in enumerate(symbol_bboxes):
        if _is_power_symbol_reference(sym_a.reference):
            continue
        for sym_b, bbox_b in symbol_bboxes[i + 1:]:
            if _is_power_symbol_reference(sym_b.reference):
                continue
            if not _overlap_is_significant(bbox_a, bbox_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.symbol_symbol",
                severity=severity,
                left=bbox_a,
                right=bbox_b,
                strict=strict,
                description_left=f"symbol {sym_a.reference!r} body",
                description_right=f"symbol {sym_b.reference!r} body",
            ))

    # Sub-sheet symbols overlap with each other (root sheet only).
    for i, (sub_a, bbox_a) in enumerate(sheet_bboxes):
        for sub_b, bbox_b in sheet_bboxes[i + 1:]:
            if not _overlap_is_significant(bbox_a, bbox_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.sheet_sheet",
                severity=severity,
                left=bbox_a,
                right=bbox_b,
                strict=strict,
                description_left=f"sheet {sub_a.name!r}",
                description_right=f"sheet {sub_b.name!r}",
            ))

    # ---- 2. symbol × label ---------------------------------------------
    for sym, sym_box in symbol_bboxes:
        if _is_power_symbol_reference(sym.reference):
            # Power symbols carry their own label glyph; labels stacked on
            # them are part of the symbol, not separate primitives.
            continue
        for label, label_box in label_bboxes:
            if not _overlap_is_significant(sym_box, label_box):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.symbol_label",
                severity=severity,
                left=sym_box,
                right=label_box,
                strict=strict,
                description_left=f"symbol {sym.reference!r} body",
                description_right=f"label {label.net_name!r}",
            ))
        for hlabel, hlabel_box in hlabel_bboxes:
            if not _overlap_is_significant(sym_box, hlabel_box):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.symbol_hlabel",
                severity=severity,
                left=sym_box,
                right=hlabel_box,
                strict=strict,
                description_left=f"symbol {sym.reference!r} body",
                description_right=f"hierarchical label {hlabel.net_name!r}",
            ))

    # ---- 3. label × label ----------------------------------------------
    # Local × local
    for i, (label_a, box_a) in enumerate(label_bboxes):
        for label_b, box_b in label_bboxes[i + 1:]:
            if not _overlap_is_significant(box_a, box_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.label_label",
                severity=severity,
                left=box_a,
                right=box_b,
                strict=strict,
                description_left=f"label {label_a.net_name!r}",
                description_right=f"label {label_b.net_name!r}",
            ))

    # Local × hierarchical
    for label_a, box_a in label_bboxes:
        for hlabel_b, box_b in hlabel_bboxes:
            if not _overlap_is_significant(box_a, box_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.label_hlabel",
                severity=severity,
                left=box_a,
                right=box_b,
                strict=strict,
                description_left=f"label {label_a.net_name!r}",
                description_right=f"hierarchical label {hlabel_b.net_name!r}",
            ))

    # Hierarchical × hierarchical
    for i, (hlabel_a, box_a) in enumerate(hlabel_bboxes):
        for hlabel_b, box_b in hlabel_bboxes[i + 1:]:
            if not _overlap_is_significant(box_a, box_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.hlabel_hlabel",
                severity=severity,
                left=box_a,
                right=box_b,
                strict=strict,
                description_left=f"hierarchical label {hlabel_a.net_name!r}",
                description_right=f"hierarchical label {hlabel_b.net_name!r}",
            ))

    # ---- 4. wire × label -----------------------------------------------
    for _, wire, wire_box in wire_bboxes:
        for label, label_box in label_bboxes:
            # A label attaches to a wire at its anchor — the wire/label
            # endpoint overlap is legitimate. We only flag when the
            # OVERLAP extends meaningfully into the label text body
            # (i.e. the wire passes UNDER the rendered text), not when
            # the wire merely terminates at the label's anchor.
            if not _overlap_is_significant(wire_box, label_box):
                continue
            # Allow the anchor-touch case: if the wire endpoint lies
            # within the label bbox AND the overlap area is small
            # relative to the label box, it's just the attach point.
            if (
                label_box.contains_point(wire.start)
                or label_box.contains_point(wire.end)
            ):
                intersection = wire_box.intersection(label_box)
                if intersection is not None and intersection.area < label_box.area * 0.5:
                    continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.wire_label",
                severity=severity,
                left=wire_box,
                right=label_box,
                strict=strict,
                description_left=f"wire #{wire_box.owner_id.split('_')[-1]}",
                description_right=f"label {label.net_name!r}",
            ))
        for hlabel, hlabel_box in hlabel_bboxes:
            if not _overlap_is_significant(wire_box, hlabel_box):
                continue
            if (
                hlabel_box.contains_point(wire.start)
                or hlabel_box.contains_point(wire.end)
            ):
                intersection = wire_box.intersection(hlabel_box)
                if intersection is not None and intersection.area < hlabel_box.area * 0.5:
                    continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.wire_hlabel",
                severity=severity,
                left=wire_box,
                right=hlabel_box,
                strict=strict,
                description_left=f"wire #{wire_box.owner_id.split('_')[-1]}",
                description_right=f"hierarchical label {hlabel.net_name!r}",
            ))

    # ---- 5. wire × symbol ----------------------------------------------
    for _, wire, wire_box in wire_bboxes:
        for sym, sym_box in symbol_bboxes:
            if _is_power_symbol_reference(sym.reference):
                continue
            if not _overlap_is_significant(wire_box, sym_box):
                continue
            # Wires that legitimately terminate at one of the symbol's
            # pin endpoints will overlap the symbol's bbox at the pin
            # stub. Allow the case where both wire endpoints sit *on*
            # the symbol's bbox edge — that's the standard pin attach.
            wire_start_on_edge = sym_box.contains_point(wire.start)
            wire_end_on_edge = sym_box.contains_point(wire.end)
            if wire_start_on_edge != wire_end_on_edge:
                # Exactly one endpoint sits inside/on the symbol bbox —
                # this is the standard "wire terminates at pin" case.
                # Only report if the wire EXTENDS noticeably into the
                # symbol body (more than a pin-stub length).
                intersection = wire_box.intersection(sym_box)
                if intersection is None:
                    continue
                # Pin-stub length is typically 2.54 mm; require the
                # overlap to be at least one pin-stub deep in the
                # short direction before flagging.
                short_dim = min(intersection.width, intersection.height)
                if short_dim < 2.54:
                    continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.wire_symbol",
                severity=severity,
                left=wire_box,
                right=sym_box,
                strict=strict,
                description_left=f"wire #{wire_box.owner_id.split('_')[-1]}",
                description_right=f"symbol {sym.reference!r} body",
            ))

    # ---- 6. wire × wire ------------------------------------------------
    for i, (_, wire_a, box_a) in enumerate(wire_bboxes):
        for _, wire_b, box_b in wire_bboxes[i + 1:]:
            if not _overlap_is_significant(box_a, box_b):
                continue
            # Only flag wires that share an axis (both H or both V at
            # the same coordinate) — crossings at 90° are fine in KiCad.
            if not _wires_share_axis(wire_a, wire_b):
                continue
            # Skip if they merely share an endpoint (T-junction or +).
            if _wires_share_endpoint(wire_a, wire_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.wire_wire",
                severity=severity,
                left=box_a,
                right=box_b,
                strict=strict,
                description_left=f"wire #{box_a.owner_id.split('_')[-1]}",
                description_right=f"wire #{box_b.owner_id.split('_')[-1]}",
            ))

    return results


# ---- Convenience: build bboxes for an external Occupancy ------------------

def iter_sheet_bboxes(
    sheet: Sheet,
    *,
    geometry: SymbolGeometryCache | None = None,
) -> Iterable[BBox]:
    """Yield one :class:`BBox` per placed primitive on ``sheet``.

    Useful when seeding an :class:`~zynq_eda.core.layout.occupancy.Occupancy`
    from an already-finalised Sheet (e.g. seeding placement of one block
    with the surrounding sheet's primitives, or for diagnostic tools).
    """
    for placed in sheet.symbols:
        yield _symbol_body_bbox(placed, geometry=geometry)
    for label in sheet.labels:
        yield _label_text_bbox(label)
    for hlabel in sheet.hierarchical_labels:
        yield _hierarchical_label_text_bbox(hlabel)
    for index, wire in enumerate(sheet.wires):
        yield _wire_segment_bbox(index, wire)
    for placed_sheet in sheet.sheets:
        yield _sheet_symbol_bbox(placed_sheet)
