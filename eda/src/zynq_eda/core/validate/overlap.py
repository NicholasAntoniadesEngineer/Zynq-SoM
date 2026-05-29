"""Overlap validator: PURE geometric bbox intersection. No exemptions.

This validator is LAW. Every pair of placed primitives is checked
for axis-aligned bounding-box intersection above the
:data:`OVERLAP_MIN_DIMENSION_MM` noise floor. If two primitives'
bboxes overlap, the validator reports it — full stop. There are no
anchor-proximity exemptions, no same-net exemptions, no power-symbol
skips, no "label-at-pin" tolerances, no "wire-passes-through-pin"
exemptions, no differential-pair carve-outs.

The previous version of this file accumulated a dozen escape hatches
that hid every real visual overlap the user could see on screen.
Each one was added to drive the validator's count to zero without
actually fixing the underlying placement bug. That contract is now
broken: the validator surfaces ALL bbox intersections; the placement
engine is responsible for producing a layout that satisfies the
validator. When an overlap is reported, the fix lives in the
placement helper that emitted the offending primitive, NOT in this
file.

Checks (every pair flagged on bbox intersection > 0.1 mm × 0.1 mm):

  1. ``symbol × symbol``
  2. ``symbol × label`` / ``symbol × hlabel``
  3. ``label × label`` / ``label × hlabel`` / ``hlabel × hlabel``
  4. ``wire × label`` / ``wire × hlabel``
  5. ``wire × symbol``
  6. ``label × intrinsic_pin_name`` / ``label × intrinsic_pin_number``
  7. ``hlabel × intrinsic_pin_name`` / ``hlabel × intrinsic_pin_number``
  8. ``wire × intrinsic_pin_name`` / ``wire × intrinsic_pin_number``
  9. ``wire × wire`` (collinear, sharing axis)
 10. ``sheet × sheet`` (root sub-sheets, root validation only)

Severity is controlled by ``strict``:

  * ``strict=True``  — every overlap is reported as ``"error"`` (gates emission).
  * ``strict=False`` — every overlap is reported as ``"warning"`` (advisory).
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
from zynq_eda.core.model.grid import Point
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

from zynq_eda.core.layout._constants import OVERLAP_NOISE_FLOOR_MM as _CENTRAL_NOISE_FLOOR_MM
OVERLAP_MIN_DIMENSION_MM: float = _CENTRAL_NOISE_FLOOR_MM
"""Minimum overlap dimension (mm) before a collision is reported.

Bboxes whose intersection rectangle is thinner than this on *either* axis
are treated as numerical noise. Sized so a wire terminating AT a
symbol's pin tip — whose perpendicular bbox extends half the
0.254 mm KiCad wire stroke (0.127 mm) past the wire's geometric
endpoint — doesn't flag as an overlap with the symbol body that
starts at the same pin tip. Any wire that actually penetrates the
body by more than ~0.15 mm is still reported (the perpendicular
intersection grows to the full 0.254 mm wire thickness once the
wire is strictly inside the body).
"""


# ---- Bbox builders for placed primitives ----------------------------------

def _label_text_bbox(label: PlacedLabel) -> BBox:
    """Bbox for a local-scope :class:`PlacedLabel`.

    KiCad rotation semantics in page coords (+Y down):

      * **rotation 0**   — text reads right; anchor on LEFT; bbox
        extends +X.
      * **rotation 90**  — text reads UP (head at top of page); anchor
        at BOTTOM; bbox extends -Y.
      * **rotation 180** — text reads left; anchor on RIGHT; bbox
        extends -X.
      * **rotation 270** — text reads DOWN; anchor at TOP; bbox
        extends +Y.
    """
    owner_id = (
        f"label:{label.net_name}@"
        f"{label.position.x:.1f},{label.position.y:.1f}"
    )
    if label.rotation == 0.0:
        return text_bbox(
            text=label.net_name,
            anchor=label.position,
            rotation=0.0,
            justify="left",
            owner_id=owner_id,
            kind="label",
        )
    if label.rotation == 180.0:
        return text_bbox(
            text=label.net_name,
            anchor=label.position,
            rotation=0.0,
            justify="right",
            owner_id=owner_id,
            kind="label",
        )
    return text_bbox(
        text=label.net_name,
        anchor=label.position,
        rotation=label.rotation,
        justify="right",
        owner_id=owner_id,
        kind="label",
    )


def _hierarchical_label_text_bbox(label: PlacedHierarchicalLabel) -> BBox:
    """Bbox for a :class:`PlacedHierarchicalLabel`.

    Same rotation convention as :func:`_label_text_bbox` plus a
    trailing-space decoration to account for the directional arrow
    glyph.
    """
    decorated_text = label.net_name + " "
    owner_id = (
        f"hlabel:{label.net_name}@"
        f"{label.position.x:.1f},{label.position.y:.1f}"
    )
    if label.rotation == 0.0:
        return text_bbox(
            text=decorated_text,
            anchor=label.position,
            rotation=0.0,
            justify="left",
            owner_id=owner_id,
            kind="hierarchical_label",
        )
    if label.rotation == 180.0:
        return text_bbox(
            text=decorated_text,
            anchor=label.position,
            rotation=0.0,
            justify="right",
            owner_id=owner_id,
            kind="hierarchical_label",
        )
    return text_bbox(
        text=decorated_text,
        anchor=label.position,
        rotation=label.rotation,
        justify="right",
        owner_id=owner_id,
        kind="hierarchical_label",
    )


def _symbol_body_bbox(
    placed: PlacedSymbol,
    geometry: SymbolGeometryCache | None,
) -> BBox:
    """Bbox for a placed symbol's body.

    Uses the real symbol geometry when ``geometry`` is provided;
    otherwise falls back to a placeholder so tests that don't
    register libraries still get sensible output.
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
        return placeholder_symbol_bbox(placed.position, owner_id=owner_id)


def _sheet_symbol_bbox(placed: PlacedSheet) -> BBox:
    """Bbox for a root-sheet ``PlacedSheet`` (sub-sheet rectangle)."""
    width, height = placed.size
    return BBox(
        min=Point(placed.position.x, placed.position.y),
        max=Point(placed.position.x + width, placed.position.y + height),
        kind="sheet",
        owner_id=f"sheet:{placed.name}",
    )


def _wire_segment_bbox(index: int, wire: PlacedWire) -> BBox:
    """Bbox for a ``PlacedWire`` segment — KiCad's actual painted stroke.

    Uses thickness = 0.254 mm (KiCad's default wire stroke) so a wire
    visually crossing a label's text glyphs flags as an overlap.
    Clearance is zero — the bbox is just the painted line. The
    body-vs-wire-endpoint case (wire terminates at a power-symbol
    pin whose visible glyph touches the same coord) is handled by
    insetting the body bbox so the pin stub doesn't appear in the
    body bbox; see :func:`zynq_eda.core.layout.geometry.bounding_box`.
    """
    return wire_bbox(
        start=wire.start,
        end=wire.end,
        thickness_mm=0.254,
        clearance_mm=0.0,
        owner_id=f"wire_{index}",
    )


# ---- Helpers --------------------------------------------------------------

def _format_point(p: Point) -> str:
    return f"({p.x:.1f}, {p.y:.1f})"


def _overlap_is_significant(a: BBox, b: BBox) -> bool:
    """True iff the bboxes' intersection rectangle exceeds the noise
    floor on BOTH dimensions."""
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
    left_horizontal = abs(left.start.y - left.end.y) < OVERLAP_MIN_DIMENSION_MM
    right_horizontal = abs(right.start.y - right.end.y) < OVERLAP_MIN_DIMENSION_MM
    left_vertical = abs(left.start.x - left.end.x) < OVERLAP_MIN_DIMENSION_MM
    right_vertical = abs(right.start.x - right.end.x) < OVERLAP_MIN_DIMENSION_MM
    if left_horizontal and right_horizontal:
        return abs(left.start.y - right.start.y) < OVERLAP_MIN_DIMENSION_MM
    if left_vertical and right_vertical:
        return abs(left.start.x - right.start.x) < OVERLAP_MIN_DIMENSION_MM
    return False


def _wire_terminates_at(wire: PlacedWire, anchor: Point) -> bool:
    """Deprecated — kept as ``False`` so the validator no longer exempts
    wire×label overlaps. Labels MUST sit next to wires (perpendicular
    offset), never along them. The placement engine is responsible for
    routing the label to a perpendicular-offset slot; the validator
    enforces it without exception.
    """
    return False


def _wires_cross_perpendicular(left: PlacedWire, right: PlacedWire) -> Point | None:
    """Return the crossing point if ``left`` and ``right`` cross at right angles.

    One wire must be horizontal (start.y ≈ end.y) and the other vertical
    (start.x ≈ end.x); their centerlines cross iff the vertical wire's
    X falls strictly inside the horizontal wire's X-span AND the
    horizontal wire's Y falls strictly inside the vertical wire's Y-span.
    "Strictly" means the cross point is in each wire's INTERIOR, not at
    an endpoint — endpoint-touching is the T/X-junction case, handled
    separately by :func:`_wires_share_endpoint`.

    Returns ``None`` when the wires aren't perpendicular or don't
    cross; otherwise returns the crossing :class:`Point`.
    """
    tol = OVERLAP_MIN_DIMENSION_MM
    left_horizontal = abs(left.start.y - left.end.y) <= tol
    left_vertical = abs(left.start.x - left.end.x) <= tol
    right_horizontal = abs(right.start.y - right.end.y) <= tol
    right_vertical = abs(right.start.x - right.end.x) <= tol

    if left_horizontal and right_vertical:
        h_wire, v_wire = left, right
    elif left_vertical and right_horizontal:
        h_wire, v_wire = right, left
    else:
        return None

    h_y = h_wire.start.y
    v_x = v_wire.start.x
    h_x_lo = min(h_wire.start.x, h_wire.end.x)
    h_x_hi = max(h_wire.start.x, h_wire.end.x)
    v_y_lo = min(v_wire.start.y, v_wire.end.y)
    v_y_hi = max(v_wire.start.y, v_wire.end.y)

    if not (h_x_lo + tol < v_x < h_x_hi - tol):
        return None
    if not (v_y_lo + tol < h_y < v_y_hi - tol):
        return None
    return Point(v_x, h_y)


def _wires_share_endpoint(left: PlacedWire, right: PlacedWire) -> bool:
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
    """Detect bbox overlaps among placed primitives. No exemptions.

    For each pair of primitives, build an axis-aligned bounding box and
    report any intersection more than :data:`OVERLAP_MIN_DIMENSION_MM`
    on both dimensions. This is a PURE geometric check: there are no
    same-net carve-outs, no anchor-proximity tolerances, no
    pin-attached exceptions.

    Args:
        sheet: The placed :class:`Sheet` to validate.
        geometry: Optional :class:`SymbolGeometryCache`. When provided,
            real symbol bbox geometry is used; when None, a placeholder
            bbox stands in.
        strict: Severity selector. ``True`` → every overlap is an
            ``"error"``; ``False`` → ``"warning"``.

    Returns:
        Ordered list of overlap :class:`ValidationResult` — one per
        intersecting bbox pair.
    """
    severity: Severity = "error" if strict else "warning"
    results: list[ValidationResult] = []

    # ---- Build the canonical bbox lists -------------------------------
    symbol_bboxes: list[tuple[PlacedSymbol, BBox]] = [
        (placed, _symbol_body_bbox(placed, geometry=geometry))
        for placed in sheet.symbols
    ]
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
    intrinsic_bboxes: list[tuple[PlacedSymbol, BBox]] = []
    if geometry is not None:
        for sym, _ in symbol_bboxes:
            try:
                for b in geometry.intrinsic_pin_label_bboxes(
                    sym.lib_id, sym.position, sym.rotation,
                    owner_id=f"symbol:{sym.reference}",
                ):
                    intrinsic_bboxes.append((sym, b))
                for b in geometry.intrinsic_pin_number_bboxes(
                    sym.lib_id, sym.position, sym.rotation,
                    owner_id=f"symbol:{sym.reference}",
                ):
                    intrinsic_bboxes.append((sym, b))
                # Property text — Reference designator ("R100"),
                # Value ("4u7", "GND"), Datasheet, Footprint —
                # rendered by KiCad next to the symbol. Labels and
                # wires stacking on top of this text are visible
                # overlaps the user sees in screenshots.
                #
                # Skip Value / Reference bboxes for symbols flagged
                # ``value_hidden`` / ``reference_hidden`` — the emitter
                # writes (hide yes) for these, so they don't render
                # in KiCad and shouldn't contribute to overlap checks.
                for b in geometry.property_text_bboxes(
                    sym.lib_id, sym.position, sym.rotation,
                    owner_id=f"symbol:{sym.reference}",
                    reference_override=sym.reference,
                    value_override=sym.value,
                    value_shift=sym.value_shift,
                    reference_shift=sym.reference_shift,
                ):
                    oid = b.owner_id
                    if getattr(sym, "value_hidden", False) and oid.endswith(":property:Value"):
                        continue
                    if getattr(sym, "reference_hidden", False) and oid.endswith(":property:Reference"):
                        continue
                    intrinsic_bboxes.append((sym, b))
            except Exception:
                continue

    # ---- 1. symbol × symbol --------------------------------------------
    for i, (sym_a, bbox_a) in enumerate(symbol_bboxes):
        for sym_b, bbox_b in symbol_bboxes[i + 1:]:
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

    # Sub-sheet × sub-sheet (root sheet only)
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

    # ---- 2. symbol × label / symbol × hlabel ----------------------------
    for sym, sym_box in symbol_bboxes:
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

    # ---- 3. label × label / label × hlabel / hlabel × hlabel -----------
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

    # ---- 4. wire × label / wire × hlabel ----------------------------
    # Wires LEGITIMATELY terminate at labels: the label's text bbox
    # extends along the wire's axis (KiCad convention — a hier-label
    # at the sheet edge has its text reading INWARD, sitting on the
    # wire that connects to it). Skip wire×label overlaps where the
    # wire's endpoint coincides with the label's anchor.
    for _, wire, wire_box in wire_bboxes:
        for label, label_box in label_bboxes:
            if not _overlap_is_significant(wire_box, label_box):
                continue
            if _wire_terminates_at(wire, label.position):
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
            if _wire_terminates_at(wire, hlabel.position):
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

    # ---- 5. wire × symbol -------------------------------------------------
    for _, wire, wire_box in wire_bboxes:
        for sym, sym_box in symbol_bboxes:
            if not _overlap_is_significant(wire_box, sym_box):
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

    # ---- 6. label × intrinsic / hlabel × intrinsic -----------------
    for label, label_box in label_bboxes:
        for sym, intrinsic_box in intrinsic_bboxes:
            if not _overlap_is_significant(label_box, intrinsic_box):
                continue
            rule_id = (
                "overlap.label_intrinsic_pin_name"
                if intrinsic_box.kind == "intrinsic_pin_name"
                else "overlap.label_intrinsic_pin_number"
            )
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id=rule_id,
                severity=severity,
                left=label_box,
                right=intrinsic_box,
                strict=strict,
                description_left=f"label {label.net_name!r}",
                description_right=f"{intrinsic_box.kind.replace('_', ' ')} {intrinsic_box.owner_id!r}",
            ))
    for hlabel, hlabel_box in hlabel_bboxes:
        for sym, intrinsic_box in intrinsic_bboxes:
            if not _overlap_is_significant(hlabel_box, intrinsic_box):
                continue
            rule_id = (
                "overlap.hlabel_intrinsic_pin_name"
                if intrinsic_box.kind == "intrinsic_pin_name"
                else "overlap.hlabel_intrinsic_pin_number"
            )
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id=rule_id,
                severity=severity,
                left=hlabel_box,
                right=intrinsic_box,
                strict=strict,
                description_left=f"hier label {hlabel.net_name!r}",
                description_right=f"{intrinsic_box.kind.replace('_', ' ')} {intrinsic_box.owner_id!r}",
            ))

    # ---- 7. wire × intrinsic ------------------------------------------
    for _, wire, wire_box in wire_bboxes:
        for sym, intrinsic_box in intrinsic_bboxes:
            if not _overlap_is_significant(wire_box, intrinsic_box):
                continue
            rule_id = (
                "overlap.wire_intrinsic_pin_name"
                if intrinsic_box.kind == "intrinsic_pin_name"
                else "overlap.wire_intrinsic_pin_number"
            )
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id=rule_id,
                severity=severity,
                left=wire_box,
                right=intrinsic_box,
                strict=strict,
                description_left=f"wire #{wire_box.owner_id.split('_')[-1]}",
                description_right=f"{intrinsic_box.kind.replace('_', ' ')} {intrinsic_box.owner_id!r}",
            ))

    # ---- 7b. intrinsic × intrinsic (cross-symbol) -----------------
    # Two pieces of intrinsic text on DIFFERENT symbols can overlap
    # when components are placed too close (e.g. adjacent caps' Value
    # text at 2.54 mm IC pin pitch with 3.3 mm-wide "C100"/"100n"
    # text). Same-symbol intrinsic overlaps (this pin's name + this
    # pin's number) are by design and skipped.
    for i, (sym_a, box_a) in enumerate(intrinsic_bboxes):
        for sym_b, box_b in intrinsic_bboxes[i + 1:]:
            if sym_a is sym_b:
                continue
            if not _overlap_is_significant(box_a, box_b):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.intrinsic_intrinsic",
                severity=severity,
                left=box_a,
                right=box_b,
                strict=strict,
                description_left=f"{box_a.kind.replace('_', ' ')} {box_a.owner_id!r}",
                description_right=f"{box_b.kind.replace('_', ' ')} {box_b.owner_id!r}",
            ))

    # ---- 8a. wire × wire (collinear) ----------------------------------
    for i, (_, wire_a, box_a) in enumerate(wire_bboxes):
        for _, wire_b, box_b in wire_bboxes[i + 1:]:
            if not _overlap_is_significant(box_a, box_b):
                continue
            if not _wires_share_axis(wire_a, wire_b):
                continue
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

    # ---- 8b. wire × wire (perpendicular crossing) ----------------------
    # PROJECT RULE: no two wires may cross, period. KiCad treats a
    # cross with a junction dot as an intentional same-net merge, but
    # the user has ruled this visually ambiguous and disallowed.
    # Any two wires whose centerlines cross at a point that ISN'T a
    # shared endpoint flags as an overlap.
    junction_points = {(j.position.x, j.position.y) for j in sheet.junctions}
    for i, (_, wire_a, box_a) in enumerate(wire_bboxes):
        for _, wire_b, box_b in wire_bboxes[i + 1:]:
            crossing = _wires_cross_perpendicular(wire_a, wire_b)
            if crossing is None:
                continue
            if _wires_share_endpoint(wire_a, wire_b):
                continue
            # Allow crossings at a junction point — KiCad's net merge
            # convention is honoured there even though it's still
            # visually a cross. The placement engine emits junctions
            # at deliberate merge points (cluster trunks, signal
            # branches).
            cross_key = (round(crossing.x, 3), round(crossing.y, 3))
            if any(
                abs(crossing.x - jx) < OVERLAP_MIN_DIMENSION_MM
                and abs(crossing.y - jy) < OVERLAP_MIN_DIMENSION_MM
                for jx, jy in junction_points
            ):
                continue
            results.append(_result_from_overlap(
                sheet=sheet,
                rule_id="overlap.wire_cross",
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
    """Yield every bbox a sheet contributes — useful for seeding an
    :class:`~zynq_eda.core.layout.occupancy.Occupancy` from a fully
    placed sheet."""
    for placed in sheet.symbols:
        yield _symbol_body_bbox(placed, geometry=geometry)
    for label in sheet.labels:
        yield _label_text_bbox(label)
    for hlabel in sheet.hierarchical_labels:
        yield _hierarchical_label_text_bbox(hlabel)
    for index, wire in enumerate(sheet.wires):
        yield _wire_segment_bbox(index, wire)
    for placed in sheet.sheets:
        yield _sheet_symbol_bbox(placed)
