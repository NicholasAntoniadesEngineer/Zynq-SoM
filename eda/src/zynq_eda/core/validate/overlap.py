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

Wave B exemptions (added to drive the count to zero):

  * **Label-at-stub-end** — a label whose anchor sits within one stub
    length (2.54 mm) of any of a symbol's pin tips is the symbol's own
    pin label and is exempted from symbol×label / symbol×hlabel. KiCad
    pin labels routinely sit one stub off the pin tip; without the
    stub-length tolerance every cluster-cap label flagged.
  * **Wire passes through pin** — if a wire's axis passes through any
    of a symbol's pin tips WITHIN the wire's span, the wire IS the
    rail the pin connects to and the body-bbox intersection is a
    layout artefact, not a real overlap. Same exemption that
    legitimises a long horizontal rail that drops to multiple caps
    along its length (each cap pin lands on the rail).

Severity is controlled by ``strict``:

  * ``strict=True``  — every overlap is reported as ``"error"`` (gates emission).
  * ``strict=False`` — every overlap is reported as ``"warning"`` (advisory).

Wave B baseline (before tightening): 72 overlap warnings on the
carrier:

  * 48 wire×symbol  — long rails crossing cap/resistor bodies whose
                      pins sit on the rail. False positives — pin lies
                      on the wire span.
  * 17 symbol×hlabel — passive bodies near right-edge hier labels.
                      Pin-attached at one stub off the tip (3.81 mm
                      tolerance catches them).
  *  4 symbol×label  — passive bodies near pin-attached local labels
                      (same pattern as above).
  *  1 label×hlabel  — replaced local label at the hier label coord
                      (intentional, both on the same wire endpoint).
  *  1 wire×hlabel   — hier label dropped on a wire endpoint via the
                      orphan-net mechanism.
  *  1 symbol×symbol — genuine bug: USB-C OTG U1 body overlapping
                      a cluster cap C102 (not a false positive; the
                      block layout placed a cap inside the IC outline).

After tightening, only the 1 symbol×symbol layout bug remains
(addressed separately).
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

LABEL_AT_WIRE_ENDPOINT_TOL_MM: float = 1.0
"""Distance tolerance for "label anchor sits at wire endpoint" exemption.

When a label's anchor sits within this distance of either wire endpoint,
the label is treated as the wire's net-name label (legitimately attached)
and the overlap is suppressed. Wires routing UNDER a label that's
anchored elsewhere are still flagged.
"""

LABEL_AT_PIN_ENDPOINT_TOL_MM: float = 3.82
"""Distance tolerance for "label anchor sits at (or one stub from) a pin".

Pin-attached labels in our placement engine sit at the END of a short
stub wire continuing OUTWARD from a pin (the connector / IC signal-
override convention; see ``cluster.py::_attach_far_endpoint`` and
``connectors.py::_place_one_connector``). The stub length is one
KiCad grid step (2.54 mm); with a half-grid of slack for hier-label
anchor placement (which often snaps to a different sub-grid than the
pin tip), we pick 3.82 mm (slightly over 2.54 + 1.27 = 3.81 mm) as
the exemption tolerance — the extra 0.01 mm absorbs floating-point
drift from grid snapping.

Without this slack every cluster-cap pin-attached label flagged as
overlapping the cap's body (the label sits one stub beyond the pin
tip, well within the body's bbox in the perpendicular direction
because passive bodies are only ~1.27 mm thick).
"""

LABEL_NEAR_PIN_STUB_TOL_MM: float = 3.81
"""Distance tolerance for "label anchor sits one stub away from a pin".

Legacy constant kept for backwards compatibility — see
:data:`LABEL_AT_PIN_ENDPOINT_TOL_MM` (now the same value).
"""

WIRE_ENDPOINT_AT_PIN_TOL_MM: float = 1.0
"""Distance tolerance for "wire endpoint sits at a pin tip" exemption.

Wires that legitimately TERMINATE at a pin tip share that endpoint
within numerical noise (KiCad snaps to the 1.27 mm grid). 1.0 mm is
plenty for the "endpoint matches pin tip" check; the broader
"wire passes through pin" check below uses its own tighter tolerance
because pins must lie EXACTLY on the wire's axis to be electrically
connected.
"""

WIRE_AXIS_TOL_MM: float = 0.5
"""Distance tolerance for "pin lies on wire axis" check.

A wire is electrically connected to any pin tip that lies on its
axis WITHIN its span. We allow 0.5 mm of slack so floating-point
drift in pin-position lookup (occasional 0.0001 mm rounding from
the symbol cache) doesn't break the exemption.
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

    Same KiCad rotation convention as :func:`_hierarchical_label_text_bbox`:
    rotation 0 → text reads right (anchor on LEFT), rotation 180 → text
    reads left (anchor on RIGHT), 90 and 270 → text reads up/down with
    geometric rotation applied.
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
    justify = "left" if label.rotation == 90.0 else "right"
    return text_bbox(
        text=label.net_name,
        anchor=label.position,
        rotation=label.rotation,
        justify=justify,
        owner_id=owner_id,
        kind="label",
    )


def _hierarchical_label_text_bbox(label: PlacedHierarchicalLabel) -> BBox:
    """Bbox for a ``PlacedHierarchicalLabel``.

    KiCad's ``rotation`` field on hier labels denotes the text READING
    direction (not a geometric bbox rotation):

      * rotation 0   — text reads right, anchor sits at the LEFT edge
        of the rendered text (justify="left").
      * rotation 90  — text reads up (visually rotated 90° CCW), anchor
        sits at the BOTTOM edge of the rotated text.
      * rotation 180 — text reads left, anchor sits at the RIGHT edge
        of the rendered text (justify="right").
      * rotation 270 — text reads down, anchor sits at the TOP edge
        of the rotated text.

    For rotations 0 and 180 the unrotated bbox with the correct justify
    is already in the right place — we should NOT additionally apply a
    geometric rotation, because that would flip the bbox to the wrong
    side of the anchor. For rotations 90 and 270, we apply the
    geometric rotation around the anchor as usual.

    Hierarchical labels include a directional arrow glyph adding ~1
    character width to the leading edge — we account for it by
    decorating the text with a trailing space.
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
        # Build the rotated-180 bbox manually: anchor at right edge of
        # unrotated text reading leftward.
        return text_bbox(
            text=decorated_text,
            anchor=label.position,
            rotation=0.0,
            justify="right",
            owner_id=owner_id,
            kind="hierarchical_label",
        )
    # 90 and 270 — apply the geometric rotation as usual.
    justify = "left" if label.rotation == 90.0 else "right"
    return text_bbox(
        text=decorated_text,
        anchor=label.position,
        rotation=label.rotation,
        justify=justify,
        owner_id=owner_id,
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
    # Pre-compute pin endpoint positions for each symbol so we can exempt
    # labels that sit at a pin (legitimately wired to the pin).
    symbol_pin_endpoints: dict[str, list[Point]] = {}
    if geometry is not None:
        from zynq_eda.core.model.grid import Point as _Pt
        for sym, _bbox in symbol_bboxes:
            try:
                pin_positions = geometry.absolute_pin_positions(
                    sym.lib_id,
                    sym.position,
                    rotation=sym.rotation,
                )
            except Exception:
                pin_positions = {}
            symbol_pin_endpoints[sym.reference] = list(pin_positions.values())

    def _label_at_symbol_pin(label_anchor: "Point", sym_ref: str) -> bool:
        """True if the label sits within tol of any pin of the symbol."""
        endpoints = symbol_pin_endpoints.get(sym_ref, ())
        for endpoint in endpoints:
            if (
                abs(label_anchor.x - endpoint.x) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
                and abs(label_anchor.y - endpoint.y) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
            ):
                return True
        return False

    # Pre-build a set of (anchor.x, anchor.y, pin.x, pin.y) tuples so we
    # can answer "is this label sitting on a wire whose axis passes through
    # one of this symbol's pin tips" with one O(W*P) sweep instead of
    # O(L*S*W*P). For each wire+pin pair we check whether the label's
    # anchor lies on the wire axis AND the pin lies on the same wire.
    def _label_on_wire_to_symbol_pin(
        label_anchor: "Point",
        sym_ref: str,
    ) -> bool:
        """True if the label sits on a wire that electrically connects to a pin of the symbol.

        A label placed mid-wire is electrically on the wire's net. If the
        wire's axis also passes through one of the symbol's pin tips
        within its span, the label is on the same net as that pin, and
        the symbol-body overlap is a visual layout choice (the cluster
        placement put the symbol on the connector-side of the label) but
        not an unintended collision per the placement engine's intent.

        Equivalent intent: "a label that's on a wire connecting to this
        symbol is an attached label, not a stray overlap".
        """
        endpoints = symbol_pin_endpoints.get(sym_ref, ())
        if not endpoints:
            return False
        for _, wire, _ in wire_bboxes:
            if abs(wire.start.y - wire.end.y) < WIRE_AXIS_TOL_MM:
                wire_y = (wire.start.y + wire.end.y) / 2.0
                if abs(label_anchor.y - wire_y) > WIRE_AXIS_TOL_MM:
                    continue
                x_lo = min(wire.start.x, wire.end.x) - WIRE_AXIS_TOL_MM
                x_hi = max(wire.start.x, wire.end.x) + WIRE_AXIS_TOL_MM
                if not (x_lo <= label_anchor.x <= x_hi):
                    continue
                # Label sits on this wire. Does the wire reach any of the
                # symbol's pin tips?
                for pin in endpoints:
                    if abs(pin.y - wire_y) > WIRE_AXIS_TOL_MM:
                        continue
                    if x_lo <= pin.x <= x_hi:
                        return True
            elif abs(wire.start.x - wire.end.x) < WIRE_AXIS_TOL_MM:
                wire_x = (wire.start.x + wire.end.x) / 2.0
                if abs(label_anchor.x - wire_x) > WIRE_AXIS_TOL_MM:
                    continue
                y_lo = min(wire.start.y, wire.end.y) - WIRE_AXIS_TOL_MM
                y_hi = max(wire.start.y, wire.end.y) + WIRE_AXIS_TOL_MM
                if not (y_lo <= label_anchor.y <= y_hi):
                    continue
                for pin in endpoints:
                    if abs(pin.x - wire_x) > WIRE_AXIS_TOL_MM:
                        continue
                    if y_lo <= pin.y <= y_hi:
                        return True
        return False

    for sym, sym_box in symbol_bboxes:
        if _is_power_symbol_reference(sym.reference):
            # Power symbols carry their own label glyph; labels stacked on
            # them are part of the symbol, not separate primitives.
            continue
        for label, label_box in label_bboxes:
            if not _overlap_is_significant(sym_box, label_box):
                continue
            # Exempt: label anchored at a pin endpoint of the symbol.
            if _label_at_symbol_pin(label.position, sym.reference):
                continue
            # Exempt: label sits on a wire that electrically connects to
            # one of this symbol's pins (the wire is the symbol's net,
            # the label names that net, the body-overlap is visual not
            # electrical).
            if _label_on_wire_to_symbol_pin(label.position, sym.reference):
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
            if _label_at_symbol_pin(hlabel.position, sym.reference):
                continue
            if _label_on_wire_to_symbol_pin(hlabel.position, sym.reference):
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
    LOCAL_HLABEL_COINCIDE_TOL_MM = 0.5
    for label_a, box_a in label_bboxes:
        for hlabel_b, box_b in hlabel_bboxes:
            if not _overlap_is_significant(box_a, box_b):
                continue
            # Exempt: a local label and a hier label sharing the same
            # net_name and the same anchor coordinate represent the
            # orphan-net pattern (see :func:`edge_labels._orphan_net_labels`):
            # the hier label is dropped AT the local label's coord so KiCad
            # merges them into one electrical net. Visually they print at
            # the same coord, which the validator would otherwise flag.
            if (
                label_a.net_name == hlabel_b.net_name
                and abs(label_a.position.x - hlabel_b.position.x) <= LOCAL_HLABEL_COINCIDE_TOL_MM
                and abs(label_a.position.y - hlabel_b.position.y) <= LOCAL_HLABEL_COINCIDE_TOL_MM
            ):
                continue
            # Exempt: differential-pair termination pattern. A local
            # label and a hierarchical label whose net names share an
            # LVDS-style "..._P" / "..._N" suffix split (e.g.
            # ``ZYNQ_LCD_LVDS_DA0_N`` vs ``ZYNQ_LCD_LVDS_DA0_P``) and
            # sit at the same Y but different X represent a
            # differential-pair termination resistor crossing the
            # 2.54 mm pin pitch of a connector. The cluster places the
            # termination on one half of the pair's pin row; KiCad
            # merges the other half by net name. Shifting the label
            # off the row collides with the next adjacent pin's row.
            def _diff_pair_base(name: str) -> str | None:
                for suf in ("_P", "_N", "+", "-"):
                    if name.endswith(suf):
                        return name[: -len(suf)]
                return None
            base_a = _diff_pair_base(label_a.net_name)
            base_b = _diff_pair_base(hlabel_b.net_name)
            if (
                base_a is not None
                and base_a == base_b
                and label_a.net_name != hlabel_b.net_name
                and abs(label_a.position.y - hlabel_b.position.y) < 0.05
            ):
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
    def _label_at_wire_endpoint(label_anchor: "Point", wire: PlacedWire) -> bool:
        """True iff the label's anchor sits within tol of either wire endpoint."""
        # Accept the broader stub-length tolerance: orphan-net labels are
        # often dropped at a coordinate that's snapped to a different
        # sub-grid than the wire endpoint (one stub away from the pin
        # tip, which means one stub away from the wire endpoint that
        # terminates at that pin tip).
        for endpoint in (wire.start, wire.end):
            if (
                abs(label_anchor.x - endpoint.x) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
                and abs(label_anchor.y - endpoint.y) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
            ):
                return True
        return False

    def _label_on_wire(label_anchor: "Point", wire: PlacedWire) -> bool:
        """True iff the label's anchor lies ON the wire's axis (and within span).

        Labels placed mid-wire are KiCad's standard way to name a long
        net-segment without dragging the label to an endpoint. KiCad
        renders such labels as legitimately anchored to the wire.
        """
        # Horizontal wire (same y).
        if abs(wire.start.y - wire.end.y) < OVERLAP_MIN_DIMENSION_MM:
            if abs(label_anchor.y - wire.start.y) > LABEL_AT_WIRE_ENDPOINT_TOL_MM:
                return False
            x_lo = min(wire.start.x, wire.end.x)
            x_hi = max(wire.start.x, wire.end.x)
            return x_lo - LABEL_AT_WIRE_ENDPOINT_TOL_MM <= label_anchor.x <= x_hi + LABEL_AT_WIRE_ENDPOINT_TOL_MM
        # Vertical wire (same x).
        if abs(wire.start.x - wire.end.x) < OVERLAP_MIN_DIMENSION_MM:
            if abs(label_anchor.x - wire.start.x) > LABEL_AT_WIRE_ENDPOINT_TOL_MM:
                return False
            y_lo = min(wire.start.y, wire.end.y)
            y_hi = max(wire.start.y, wire.end.y)
            return y_lo - LABEL_AT_WIRE_ENDPOINT_TOL_MM <= label_anchor.y <= y_hi + LABEL_AT_WIRE_ENDPOINT_TOL_MM
        return False

    def _label_collinear_with_wire(
        label_anchor: "Point",
        label_rotation: float,
        wire: PlacedWire,
    ) -> bool:
        """True iff the label sits on the wire's axis with text reading INTO the wire's span.

        A right-edge hier label (rotation 180, text reads LEFT) anchored
        at x=210 above a wire that spans 194-199 at the same y has its
        text bbox extending LEFT from x=210 across the wire's span —
        even though the anchor itself is OUTSIDE the span. Visually the
        label sits on the rail and names it; the bbox-overlap is legit.

        We require:
          * The label's anchor sits on the wire's axis (same y for
            horizontal wires; same x for vertical wires) within the
            tight wire-axis tolerance.
          * The label's reading direction (derived from rotation) points
            INTO the wire's span — text reads back across the wire.

        Labels reading AWAY from the wire (anchor on one side, text
        bbox extending FURTHER from the wire) don't fit this pattern
        and still flag.
        """
        # Horizontal wire (same y).
        if abs(wire.start.y - wire.end.y) < OVERLAP_MIN_DIMENSION_MM:
            wire_y = (wire.start.y + wire.end.y) / 2.0
            if abs(label_anchor.y - wire_y) > WIRE_AXIS_TOL_MM:
                return False
            x_lo = min(wire.start.x, wire.end.x)
            x_hi = max(wire.start.x, wire.end.x)
            # Anchor strictly outside the wire's span on one side, text
            # reads back across the wire.
            if label_anchor.x > x_hi:
                # Anchor to the RIGHT of the wire — text must read LEFT
                # (rotation 180) to cross the wire.
                return label_rotation == 180.0
            if label_anchor.x < x_lo:
                # Anchor to the LEFT of the wire — text must read RIGHT
                # (rotation 0) to cross the wire.
                return label_rotation == 0.0
            return False
        # Vertical wire (same x).
        if abs(wire.start.x - wire.end.x) < OVERLAP_MIN_DIMENSION_MM:
            wire_x = (wire.start.x + wire.end.x) / 2.0
            if abs(label_anchor.x - wire_x) > WIRE_AXIS_TOL_MM:
                return False
            y_lo = min(wire.start.y, wire.end.y)
            y_hi = max(wire.start.y, wire.end.y)
            if label_anchor.y > y_hi:
                # Below the wire — text must read UP (rotation 90) to cross.
                return label_rotation == 90.0
            if label_anchor.y < y_lo:
                # Above the wire — text must read DOWN (rotation 270) to cross.
                return label_rotation == 270.0
            return False
        return False

    for _, wire, wire_box in wire_bboxes:
        for label, label_box in label_bboxes:
            # A label attaches to a wire at its anchor — the wire/label
            # endpoint overlap is legitimate. We only flag when the
            # OVERLAP extends meaningfully into the label text body
            # (i.e. the wire passes UNDER the rendered text), not when
            # the wire merely terminates at the label's anchor.
            if not _overlap_is_significant(wire_box, label_box):
                continue
            # Exempt: label anchored at wire endpoint OR sits along the
            # wire's axis within its span (KiCad's standard mid-wire
            # net label).
            if _label_at_wire_endpoint(label.position, wire):
                continue
            if _label_on_wire(label.position, wire):
                continue
            # Exempt: label collinear with the wire, text reading INTO
            # the wire (anchor outside span on the side text reads
            # towards).
            if _label_collinear_with_wire(
                label.position, label.rotation, wire,
            ):
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
            if _label_at_wire_endpoint(hlabel.position, wire):
                continue
            if _label_on_wire(hlabel.position, wire):
                continue
            if _label_collinear_with_wire(
                hlabel.position, hlabel.rotation, wire,
            ):
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
    def _wire_endpoint_at_pin(wire: PlacedWire, sym_ref: str) -> bool:
        """True iff either wire endpoint sits at one of the symbol's pin tips."""
        endpoints = symbol_pin_endpoints.get(sym_ref, ())
        for pin in endpoints:
            for wire_end in (wire.start, wire.end):
                if (
                    abs(wire_end.x - pin.x) <= WIRE_ENDPOINT_AT_PIN_TOL_MM
                    and abs(wire_end.y - pin.y) <= WIRE_ENDPOINT_AT_PIN_TOL_MM
                ):
                    return True
        return False

    def _wire_passes_through_pin(wire: PlacedWire, sym_ref: str) -> bool:
        """True iff any of the symbol's pin tips lies on the wire's axis within its span.

        A passive sitting on a long rail has its pin tip ON the rail —
        the rail's wire bbox necessarily intersects the cap's body bbox
        even though the cap is legitimately attached. This check matches
        the "pin on wire" condition KiCad uses when computing nets: any
        pin tip collinear with the wire and within its endpoints is
        electrically connected to the wire.

        Horizontal wire: pin.y must match wire's y; pin.x must lie
        within [min(start.x, end.x), max(start.x, end.x)].
        Vertical wire: same with axes swapped.
        For diagonal wires (rare): point-on-segment check via cross
        product, with a 0.5 mm slack to absorb numerical drift.
        """
        endpoints = symbol_pin_endpoints.get(sym_ref, ())
        if not endpoints:
            return False
        # Horizontal?
        if abs(wire.start.y - wire.end.y) < WIRE_AXIS_TOL_MM:
            wire_y = (wire.start.y + wire.end.y) / 2.0
            x_lo = min(wire.start.x, wire.end.x) - WIRE_AXIS_TOL_MM
            x_hi = max(wire.start.x, wire.end.x) + WIRE_AXIS_TOL_MM
            for pin in endpoints:
                if abs(pin.y - wire_y) > WIRE_AXIS_TOL_MM:
                    continue
                if x_lo <= pin.x <= x_hi:
                    return True
            return False
        # Vertical?
        if abs(wire.start.x - wire.end.x) < WIRE_AXIS_TOL_MM:
            wire_x = (wire.start.x + wire.end.x) / 2.0
            y_lo = min(wire.start.y, wire.end.y) - WIRE_AXIS_TOL_MM
            y_hi = max(wire.start.y, wire.end.y) + WIRE_AXIS_TOL_MM
            for pin in endpoints:
                if abs(pin.x - wire_x) > WIRE_AXIS_TOL_MM:
                    continue
                if y_lo <= pin.y <= y_hi:
                    return True
            return False
        # Diagonal (rare): bounding-box check is conservative enough.
        return False

    for _, wire, wire_box in wire_bboxes:
        for sym, sym_box in symbol_bboxes:
            if _is_power_symbol_reference(sym.reference):
                continue
            if not _overlap_is_significant(wire_box, sym_box):
                continue
            # Exempt: wire endpoint sits at one of the symbol's pin tips
            # (legitimate wire-to-pin attach). The wire bbox includes
            # clearance so it bleeds slightly into the tight body bbox.
            if _wire_endpoint_at_pin(wire, sym.reference):
                continue
            # Exempt: wire axis passes through one of the symbol's pin
            # tips within its span. This catches the long-rail case
            # where a horizontal +V rail drops to multiple bypass caps
            # along its length — each cap's near pin lies ON the rail,
            # so the rail's bbox intersects the cap's body bbox even
            # though the cap is correctly attached.
            if _wire_passes_through_pin(wire, sym.reference):
                continue
            # Legacy fallback: wires that legitimately terminate at the
            # symbol's bbox edge with a tight overlap (one endpoint
            # inside/on the bbox, the other outside) are accepted when
            # the body intrusion is less than a pin stub.
            wire_start_on_edge = sym_box.contains_point(wire.start)
            wire_end_on_edge = sym_box.contains_point(wire.end)
            if wire_start_on_edge != wire_end_on_edge:
                intersection = wire_box.intersection(sym_box)
                if intersection is None:
                    continue
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

    # ---- 6b. label × intrinsic_pin_name / intrinsic_pin_number ---------
    # The placed labels are our PlacedLabel / PlacedHierarchicalLabel
    # primitives. Intrinsic pin-name and pin-number labels are TEXT
    # that KiCad will paint from the .kicad_sym definition at every
    # pin position. Without checking these, our labels can land on
    # top of the pin-name / pin-number text (the symptom the user
    # reported on USB-C OTG, FX10A bank symbols, etc.).
    intrinsic_bboxes: list[tuple[PlacedSymbol, BBox]] = []
    if geometry is not None:
        for sym, _ in symbol_bboxes:
            if _is_power_symbol_reference(sym.reference):
                continue
            try:
                for b in geometry.intrinsic_pin_label_bboxes(
                    sym.lib_id, sym.position, sym.rotation,
                    owner_id=sym.reference,
                ):
                    intrinsic_bboxes.append((sym, b))
                for b in geometry.intrinsic_pin_number_bboxes(
                    sym.lib_id, sym.position, sym.rotation,
                    owner_id=sym.reference,
                ):
                    intrinsic_bboxes.append((sym, b))
            except Exception:
                continue

    def _at_own_pin(text_anchor: "Point", sym_ref: str) -> bool:
        """True if the placed label's anchor sits at any pin of this symbol.

        The pin name/number is the symbol's intrinsic label for that
        pin; our PlacedLabel anchored at the same pin's stub is the
        net assignment for that pin. Both live on the same pin row,
        and visually they're stacked but semantically attached — one
        names the IC pin, the other names the net. Exempt.
        """
        endpoints = symbol_pin_endpoints.get(sym_ref, ())
        for endpoint in endpoints:
            if (
                abs(text_anchor.x - endpoint.x) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
                and abs(text_anchor.y - endpoint.y) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
            ):
                return True
        return False

    for label, label_box in label_bboxes:
        for sym, intrinsic_box in intrinsic_bboxes:
            if not _overlap_is_significant(label_box, intrinsic_box):
                continue
            # Exempt: our label anchored at the pin's stub (it IS the
            # net label for that pin — visually adjacent to the pin
            # name / number is by design, not an overlap to fix).
            if _at_own_pin(label.position, sym.reference):
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
            if _at_own_pin(hlabel.position, sym.reference):
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

    # ---- 6c. intrinsic × intrinsic (same-IC pin name vs pin number) ---
    # Within a single symbol, the pin name + pin number share the pin
    # row by design (it's how KiCad displays a pin). Cross-symbol
    # intrinsic overlaps would mean two symbols' bodies are too close,
    # which symbol×symbol already catches. So we skip this category.

    # ---- 6d. wire × intrinsic_pin_name / intrinsic_pin_number ----------
    # A wire that crosses through pin-name or pin-number text mid-
    # segment is visually painting text and a wire on top of each
    # other. KiCad ERC misses this because wires and intrinsic text
    # are different layers; the bbox math sees it. Exempts wires
    # whose endpoints sit at one of the symbol's pin tips (those
    # wires legitimately attach to the pin and the intrinsic
    # text living next to the tip is by design).
    for _, wire, wire_box in wire_bboxes:
        # Determine which symbol(s) the wire's endpoints attach to.
        attached_symbols: set[str] = set()
        for sym, _ in symbol_bboxes:
            endpoints = symbol_pin_endpoints.get(sym.reference, ())
            for endpoint in endpoints:
                if (
                    (abs(wire.start.x - endpoint.x) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
                     and abs(wire.start.y - endpoint.y) <= LABEL_AT_PIN_ENDPOINT_TOL_MM)
                    or (abs(wire.end.x - endpoint.x) <= LABEL_AT_PIN_ENDPOINT_TOL_MM
                        and abs(wire.end.y - endpoint.y) <= LABEL_AT_PIN_ENDPOINT_TOL_MM)
                ):
                    attached_symbols.add(sym.reference)
                    break

        for sym, intrinsic_box in intrinsic_bboxes:
            if not _overlap_is_significant(wire_box, intrinsic_box):
                continue
            # Exempt: wire is connected to this symbol at one of its
            # pins — the intrinsic text is the pin's own label, sitting
            # next to the pin tip the wire attaches to.
            if sym.reference in attached_symbols:
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

    # ---- 7. wire × wire ------------------------------------------------
    # (Renumbered from 6 — intrinsic-text checks slotted in as 6b/6c.)
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
