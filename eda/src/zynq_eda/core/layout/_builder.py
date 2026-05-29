"""Mutable accumulator used by every placement subroutine.

The placement engine is structured as a set of small helpers that each
take a :class:`_BlockLayoutBuilder` and append to its collections. At the
end, :meth:`_BlockLayoutBuilder.finalize` freezes the accumulator into a
:class:`Sheet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from zynq_eda.core.layout.bbox import (
    BBox,
    placeholder_symbol_bbox,
    symbol_bbox,
    text_bbox,
    wire_bbox,
)
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import (
    PlacedGlobalLabel,
    PlacedHierarchicalLabel,
    PlacedJunction,
    PlacedLabel,
    PlacedNoConnect,
    PlacedSheet,
    PlacedSymbol,
    PlacedWire,
    Sheet,
)


@dataclass(frozen=True)
class PinGeometryAbs:
    """Subset of :class:`PinGeometry` retained while a block is being built.

    Stores absolute schematic-page coordinates (after Y-flip + rotation) so
    downstream wiring code doesn't have to re-derive them.

    ``pin_rotation`` and ``symbol_rotation`` are preserved verbatim from the
    :class:`PinGeometry` they were copied from, so the cluster / connector
    code can determine the pin's page-side from the canonical
    rotation-derived rule rather than the legacy position-axis heuristic.

    ``cluster_trunk_end`` is the OUTWARD endpoint of this pin's cluster
    trunk wire (LEFT/RIGHT only) — i.e. the X column of the furthest
    slot's drop. Downstream code (e.g. connector pin-to-net labels)
    uses it to place the source-net label at the trunk's far end so
    the label text doesn't sit on the trunk wire's centerline.
    ``None`` for pins without a LEFT/RIGHT cluster.
    """

    anchor: Point
    connection: Point
    relative: Point
    pin_rotation: float = 0.0
    symbol_rotation: float = 0.0
    cluster_trunk_end: Point | None = None


@dataclass
class BlockLayoutBuilder:
    """Mutable accumulator of placed primitives while building a block.

    ``occupancy`` is a live spatial index that placement helpers populate
    in lockstep with ``symbols``/``wires``/``labels``. Wave B will add
    ``occupancy.add(...)`` calls inside each helper so collision checks
    happen *during* placement instead of only after the fact.
    """

    symbols: list[PlacedSymbol] = field(default_factory=list)
    wires: list[PlacedWire] = field(default_factory=list)
    labels: list[PlacedLabel] = field(default_factory=list)
    junctions: list[PlacedJunction] = field(default_factory=list)
    no_connects: list[PlacedNoConnect] = field(default_factory=list)
    hierarchical_labels: list[PlacedHierarchicalLabel] = field(default_factory=list)
    global_labels: list[PlacedGlobalLabel] = field(default_factory=list)
    sheets: list[PlacedSheet] = field(default_factory=list)
    occupancy: Occupancy = field(default_factory=Occupancy)
    _ref_counters: dict[str, int] = field(
        default_factory=lambda: {"C": 100, "R": 100, "D": 100, "PWR": 100, "FLG": 100}
    )

    def next_ref(self, prefix: str) -> str:
        """Return a fresh designator for the given prefix (e.g. ``C103``)."""
        index = self._ref_counters.setdefault(prefix, 100)
        self._ref_counters[prefix] = index + 1
        return f"{prefix}{index}"

    # ---- Occupancy-registering helpers --------------------------------
    # These methods keep the live spatial index in lockstep with the
    # placement collections. Call them from placement subroutines
    # instead of appending directly. Old `builder.X.append(...)` call
    # sites still work; they just skip the index update and miss out
    # on the router's collision-avoidance.

    def add_symbol(self, sym: PlacedSymbol, geometry=None) -> None:
        """Append a placed symbol AND register every bbox it contributes.

        Registers the symbol's body bbox AND every intrinsic pin-name +
        pin-number text bbox so the router treats pin-name text as an
        obstacle. Without this, the cluster L-bend routes happily lay
        wires across the pin-name text of OTHER pins on the same IC
        (the validator flags it after the fact; the user wants ZERO
        post-hoc overlap fixes).
        """
        self.symbols.append(sym)
        owner_id = f"symbol:{sym.reference}"
        try:
            if geometry is not None:
                body_bbox = symbol_bbox(
                    lib_id=sym.lib_id,
                    anchor=sym.position,
                    rotation=sym.rotation,
                    cache=geometry,
                    owner_id=owner_id,
                )
            else:
                body_bbox = placeholder_symbol_bbox(
                    sym.position, owner_id=owner_id,
                )
        except Exception:
            body_bbox = placeholder_symbol_bbox(
                sym.position, owner_id=owner_id,
            )
        self.occupancy.add(body_bbox)

        # Register intrinsic pin-name + pin-number bboxes too, owned by
        # the IC's symbol so routers + downstream collision checks can
        # ignore them via avoid_owners when routing FROM this IC's own
        # pins (the source pin's name text legitimately sits next to
        # the wire's start point). Owner ids are prefixed
        # ``intrinsic:symbol:REF:...`` — distinct from the body's
        # ``symbol:REF`` so callers can target either or both.
        if geometry is None:
            return
        try:
            label_bboxes = geometry.intrinsic_pin_label_bboxes(
                sym.lib_id,
                sym.position,
                rotation=sym.rotation,
                owner_id=owner_id,
            )
            number_bboxes = geometry.intrinsic_pin_number_bboxes(
                sym.lib_id,
                sym.position,
                rotation=sym.rotation,
                owner_id=owner_id,
            )
            # Pass the per-instance value_shift so the registered Value
            # bbox matches the position the emitter will actually write
            # to the .kicad_sch. Without this, occupancy holds the LIB-
            # default Value position while the schematic renders at the
            # shifted position — subsequent placements then collide with
            # the rendered text because they avoided the wrong spot.
            property_bboxes = geometry.property_text_bboxes(
                sym.lib_id,
                sym.position,
                rotation=sym.rotation,
                owner_id=owner_id,
                reference_override=sym.reference,
                value_override=sym.value,
                value_shift=sym.value_shift,
                reference_shift=sym.reference_shift,
            )
        except Exception:
            return
        for b in label_bboxes:
            self.occupancy.add(b)
        for b in number_bboxes:
            self.occupancy.add(b)
        for b in property_bboxes:
            # Skip Value / Reference property bboxes for symbols where
            # those props are flagged hidden (e.g. duplicate cluster
            # power symbols on sub-slots): the emitter writes
            # (hide yes) and the validator's bbox check would otherwise
            # report overlaps with sibling power symbols that share
            # the same X column.
            oid = b.owner_id
            if sym.value_hidden and oid.endswith(":property:Value"):
                continue
            if sym.reference_hidden and oid.endswith(":property:Reference"):
                continue
            self.occupancy.add(b)

    def add_wire(self, wire: PlacedWire) -> None:
        """Append a wire segment AND register its bbox in occupancy.

        Pass 7 of the overlap-free plan: rejects duplicate wires (same
        endpoints in either order). A duplicate emission ALWAYS
        indicates a bug in the contributing code path — two helpers
        are routing the same connection — and the user has ruled this
        a hard error. Silently dropping the duplicate would mask the
        bug; raising surfaces it.

        Zero-length wires (start == end) are silently dropped as a
        no-op (the router can produce these for degenerate routes).

        When ``ZYNQ_EDA_WIRE_DEBUG`` is set, every wire that would
        cross an existing wire (perpendicular intersection, not at a
        shared endpoint) is logged so the offending caller can be
        identified.
        """
        if (
            abs(wire.start.x - wire.end.x) < 1e-6
            and abs(wire.start.y - wire.end.y) < 1e-6
        ):
            # Zero-length wire — no-op.
            return
        for existing in self.wires:
            same_dir = (
                abs(existing.start.x - wire.start.x) < 1e-6
                and abs(existing.start.y - wire.start.y) < 1e-6
                and abs(existing.end.x - wire.end.x) < 1e-6
                and abs(existing.end.y - wire.end.y) < 1e-6
            )
            reversed_dir = (
                abs(existing.start.x - wire.end.x) < 1e-6
                and abs(existing.start.y - wire.end.y) < 1e-6
                and abs(existing.end.x - wire.start.x) < 1e-6
                and abs(existing.end.y - wire.start.y) < 1e-6
            )
            if same_dir or reversed_dir:
                raise RuntimeError(
                    f"add_wire: duplicate wire {wire.start} → {wire.end} — "
                    f"two code paths are routing the same connection. "
                    f"Fix the upstream emitter. Existing wire at index "
                    f"{self.wires.index(existing)}."
                )
        import os as _os
        if _os.environ.get("ZYNQ_EDA_WIRE_DEBUG"):
            from traceback import extract_stack
            self._log_crossings(wire, extract_stack())
        self.wires.append(wire)
        index = len(self.wires) - 1
        bbox = wire_bbox(
            start=wire.start,
            end=wire.end,
            owner_id=f"wire_{index}",
        )
        self.occupancy.add(bbox)

    def _log_crossings(self, new_wire: PlacedWire, stack) -> None:
        tol = 0.1
        new_h = abs(new_wire.start.y - new_wire.end.y) < tol
        new_v = abs(new_wire.start.x - new_wire.end.x) < tol
        for idx, existing in enumerate(self.wires):
            ex_h = abs(existing.start.y - existing.end.y) < tol
            ex_v = abs(existing.start.x - existing.end.x) < tol
            if new_h and ex_v:
                h, v = new_wire, existing
            elif new_v and ex_h:
                h, v = existing, new_wire
            else:
                continue
            h_y = h.start.y
            v_x = v.start.x
            h_x_lo = min(h.start.x, h.end.x)
            h_x_hi = max(h.start.x, h.end.x)
            v_y_lo = min(v.start.y, v.end.y)
            v_y_hi = max(v.start.y, v.end.y)
            if h_x_lo + tol < v_x < h_x_hi - tol and v_y_lo + tol < h_y < v_y_hi - tol:
                caller_frames = [
                    f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}"
                    for frame in stack[-5:-1]
                ]
                print(
                    f"[wire_cross] new wire {new_wire.start}→{new_wire.end} "
                    f"crosses #{idx} {existing.start}→{existing.end} from "
                    f"{' / '.join(caller_frames)}"
                )

    def add_label(self, label: PlacedLabel) -> None:
        """Append a local label AND register its text bbox."""
        self.labels.append(label)
        bbox = _label_bbox(label)
        self.occupancy.add(bbox)

    def add_hierarchical_label(self, hlabel: PlacedHierarchicalLabel) -> None:
        """Append a hierarchical label AND register its text bbox."""
        self.hierarchical_labels.append(hlabel)
        bbox = _hierarchical_label_bbox(hlabel)
        self.occupancy.add(bbox)

    def add_global_label(self, glabel: PlacedGlobalLabel) -> None:
        """Append a global label AND register its text bbox.

        Global labels render visually similar to hier labels (with a
        different glyph), so we reuse the hier-label bbox helper.
        """
        self.global_labels.append(glabel)
        # Build a hier-equivalent for bbox computation.
        as_hier = PlacedHierarchicalLabel(
            net_name=glabel.net_name,
            position=glabel.position,
            direction=glabel.direction,
            rotation=glabel.rotation,
        )
        bbox = _hierarchical_label_bbox(as_hier)
        # Mark the bbox owner so ignore_owners can target it explicitly.
        from dataclasses import replace as _dc_replace
        bbox = _dc_replace(
            bbox,
            owner_id=f"glabel:{glabel.net_name}@{glabel.position.x:.1f},{glabel.position.y:.1f}",
        )
        self.occupancy.add(bbox)

    def finalize(self, block: Block, *, geometry_cache=None) -> Sheet:
        """Freeze the accumulator into a :class:`Sheet`.

        Wires are passed through :func:`dedup_collinear_contained_wires`
        to merge overlapping collinear segments (the cluster + signal-
        override + edge-label passes routinely emit multiple short
        wires that share the same axis and overlap with one long
        net-spanning wire — KiCad merges them electrically but the
        redundant segments show as ``overlap.wire_wire`` validator
        hits and visually clutter the schematic).

        After dedup, intermediate symbol-pin tips that fell on the
        original short wires would otherwise lose their connection
        (KiCad treats "wire passing through pin mid-span" as
        unconnected — needs an explicit junction at the crossing).
        We auto-inject junctions at every symbol pin tip that lands
        strictly on the interior of a deduped wire so the long
        merged rail electrically connects every passive in its span.
        """
        deduped_wires = list(self.wires)  # dedup off for debug
        junctions = list(self.junctions)
        if geometry_cache is not None:
            junctions = _inject_junctions_for_passthrough_pins(
                deduped_wires=deduped_wires,
                symbols=self.symbols,
                existing_junctions=junctions,
                geometry_cache=geometry_cache,
            )
        return Sheet(
            name=block.name,
            title=block.title,
            paper_size=block.paper_size,
            symbols=tuple(self.symbols),
            wires=tuple(deduped_wires),
            labels=tuple(self.labels),
            junctions=tuple(junctions),
            no_connects=tuple(self.no_connects),
            hierarchical_labels=tuple(self.hierarchical_labels),
            global_labels=tuple(self.global_labels),
            sheets=tuple(self.sheets),
            description=block.description,
        )


def dedup_collinear_contained_wires(wires: list[PlacedWire]) -> list[PlacedWire]:
    """Drop wires that are fully covered by a longer collinear wire.

    Two wires that share an axis (both horizontal at the same y, or
    both vertical at the same x) AND where one is fully contained
    inside the other are electrically equivalent: KiCad merges them
    into the same net regardless. We drop the shorter (contained)
    wire to keep the schematic free of redundant overlapping
    segments — those would otherwise show as ``overlap.wire_wire``
    validator hits even though they're functionally a single net.

    Why this is safe (no endpoint-sharing requirement): two collinear
    overlapping wires on the same horizontal line always share the
    contained wire's full span with the containing wire. Any
    component pin attached to a coordinate inside the contained wire
    is also coincident with the containing wire — same net.

    Original strict variant kept as :func:`_unused_dedup_shared_endpoint_wires`
    for callers that need endpoint-only dedup.
    """
    # Bucket horizontal wires by Y, vertical wires by X.
    horiz: dict[float, list[PlacedWire]] = {}
    vert: dict[float, list[PlacedWire]] = {}
    other: list[PlacedWire] = []
    for w in wires:
        if abs(w.start.y - w.end.y) < 1e-6:
            horiz.setdefault(round(w.start.y, 4), []).append(w)
        elif abs(w.start.x - w.end.x) < 1e-6:
            vert.setdefault(round(w.start.x, 4), []).append(w)
        else:
            other.append(w)

    def length(w: PlacedWire) -> float:
        return abs(w.end.x - w.start.x) + abs(w.end.y - w.start.y)

    def filter_bucket(bucket: list[PlacedWire], horizontal: bool) -> list[PlacedWire]:
        """Merge overlapping collinear wires into the union spans.

        Two wires overlap iff their (lo, hi) intervals overlap on the
        shared axis. We compute the union of all overlapping wires in
        the bucket and emit ONE wire per disjoint union interval.
        """
        if not bucket:
            return []
        axis_lookup_y = horizontal  # if horizontal, axis value is y (shared)
        # The shared-axis value is identical for every wire in the bucket
        # (it's the bucket key). Pick it from the first wire.
        sample = bucket[0]
        shared_value = sample.start.y if horizontal else sample.start.x

        intervals: list[tuple[float, float]] = []
        for w in bucket:
            if horizontal:
                lo = min(w.start.x, w.end.x)
                hi = max(w.start.x, w.end.x)
            else:
                lo = min(w.start.y, w.end.y)
                hi = max(w.start.y, w.end.y)
            intervals.append((lo, hi))
        # Merge overlapping intervals: sort by lo, then walk.
        intervals.sort()
        merged: list[tuple[float, float]] = []
        for lo, hi in intervals:
            if merged and lo <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))

        result_wires: list[PlacedWire] = []
        from zynq_eda.core.model.grid import Point as _Pt
        for lo, hi in merged:
            if horizontal:
                start = _Pt(lo, shared_value)
                end = _Pt(hi, shared_value)
            else:
                start = _Pt(shared_value, lo)
                end = _Pt(shared_value, hi)
            # Skip zero-length wires (numerical noise).
            if abs(start.x - end.x) < 1e-6 and abs(start.y - end.y) < 1e-6:
                continue
            result_wires.append(PlacedWire(start=start, end=end))
        return result_wires

    result: list[PlacedWire] = list(other)
    for bucket in horiz.values():
        result.extend(filter_bucket(bucket, horizontal=True))
    for bucket in vert.values():
        result.extend(filter_bucket(bucket, horizontal=False))
    return result


# Backward-compat alias
_unused_dedup_shared_endpoint_wires = dedup_collinear_contained_wires


def _inject_junctions_for_passthrough_pins(
    *,
    deduped_wires: list[PlacedWire],
    symbols: list[PlacedSymbol],
    existing_junctions: list[PlacedJunction],
    geometry_cache,
) -> list[PlacedJunction]:
    """Add junctions where a symbol pin tip lands on a wire's interior.

    KiCad ERC treats "wire passes through pin mid-span" as UNCONNECTED
    unless a junction marks the crossing. When ``dedup_collinear_contained_wires``
    merges several short cluster wires into one long rail, the
    intermediate passive-pin endpoints become mid-span crossings on the
    merged wire. Without junctions, those passives flag as
    ``pin_not_connected`` despite being visually on the rail.

    We scan every (wire, symbol) pair: for each pin tip on the wire's
    interior (strict, not equal to the wire's endpoints), inject a
    junction at the pin coordinate so KiCad recognises the connection.
    """
    PINS_GRID_TOL = 0.01  # mm — KiCad-grid tolerance

    existing = {(round(j.position.x, 3), round(j.position.y, 3))
                for j in existing_junctions}
    new_junctions = list(existing_junctions)

    # Pre-compute pin tip positions per symbol.
    symbol_pin_tips: list[Point] = []
    for sym in symbols:
        if sym.reference.startswith("#PWR"):
            # Power symbols have one pin; include it.
            pass
        try:
            positions = geometry_cache.absolute_pin_positions(
                sym.lib_id,
                sym.position,
                rotation=getattr(sym, "rotation", 0.0),
            )
        except Exception:
            continue
        symbol_pin_tips.extend(positions.values())

    def _on_wire_interior(point: Point, wire: PlacedWire) -> bool:
        """True iff `point` is on the wire's open interior (strict)."""
        x1, y1 = wire.start.x, wire.start.y
        x2, y2 = wire.end.x, wire.end.y
        if abs(y1 - y2) < PINS_GRID_TOL:
            # Horizontal wire — y must match, x must be strictly between
            if abs(point.y - y1) > PINS_GRID_TOL:
                return False
            lo, hi = (min(x1, x2), max(x1, x2))
            return lo + PINS_GRID_TOL < point.x < hi - PINS_GRID_TOL
        elif abs(x1 - x2) < PINS_GRID_TOL:
            # Vertical wire
            if abs(point.x - x1) > PINS_GRID_TOL:
                return False
            lo, hi = (min(y1, y2), max(y1, y2))
            return lo + PINS_GRID_TOL < point.y < hi - PINS_GRID_TOL
        return False  # diagonal — shouldn't happen

    for wire in deduped_wires:
        for tip in symbol_pin_tips:
            if not _on_wire_interior(tip, wire):
                continue
            key = (round(tip.x, 3), round(tip.y, 3))
            if key in existing:
                continue
            new_junctions.append(PlacedJunction(position=tip))
            existing.add(key)

    return new_junctions


def symbol_owner_id(reference: str) -> str:
    """Return the body-bbox owner id for a placed symbol."""
    return f"symbol:{reference}"


def pin_intrinsic_owner_ids(
    reference: str,
    pin_numbers: Iterable[str],
) -> frozenset[str]:
    """Return the set of intrinsic-text owner ids for given source pins.

    Used to exempt a routing wire's source-pin own pin-name + pin-number
    text bboxes from collision checks. Without the exemption, the wire
    bbox's endpoint clearance grazes the pin's own intrinsic text (text
    sits ~1 mm INTO the body from the pin tip) and EVERY route from a
    pin would falsely block. We still want OTHER pins' intrinsic text
    on the same IC to act as obstacles so the router picks an L-bend
    that avoids them.

    Owner-id scheme (matches the strings produced by
    :meth:`SymbolGeometryCache.intrinsic_pin_label_bboxes` and
    :meth:`intrinsic_pin_number_bboxes` when called with
    ``owner_id="symbol:{ref}"``):

      * pin-name bbox owner: ``symbol:{ref}:pin_name:{pin_number}``
      * pin-number bbox owner: ``symbol:{ref}:pin_number:{pin_number}``
    """
    owners: set[str] = set()
    base = symbol_owner_id(reference)
    for n in pin_numbers:
        owners.add(f"{base}:pin_name:{n}")
        owners.add(f"{base}:pin_number:{n}")
    return frozenset(owners)


# ---- Label-bbox helpers (mirror the validator's) ---------------------------

def _label_bbox(label: PlacedLabel) -> BBox:
    """Bbox for a PlacedLabel, mirroring the validator's logic.

    See :func:`zynq_eda.core.validate.overlap._label_text_bbox` for the
    rotation convention. The two implementations must stay in sync —
    the round-trip tests in
    ``eda/tests/unit/test_label_bbox_rotation.py`` assert this.
    """
    owner_id = f"label:{label.net_name}@{label.position.x:.1f},{label.position.y:.1f}"
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


def _hierarchical_label_bbox(label: PlacedHierarchicalLabel) -> BBox:
    """Bbox for a PlacedHierarchicalLabel, mirroring the validator."""
    decorated_text = label.net_name + " "
    owner_id = f"hlabel:{label.net_name}@{label.position.x:.1f},{label.position.y:.1f}"
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
