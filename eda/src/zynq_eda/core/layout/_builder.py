"""Mutable accumulator used by every placement subroutine.

The placement engine is structured as a set of small helpers that each
take a :class:`_BlockLayoutBuilder` and append to its collections. At the
end, :meth:`_BlockLayoutBuilder.finalize` freezes the accumulator into a
:class:`Sheet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    """

    anchor: Point
    connection: Point
    relative: Point
    pin_rotation: float = 0.0
    symbol_rotation: float = 0.0


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
        """Append a placed symbol AND register its bbox in occupancy."""
        self.symbols.append(sym)
        try:
            if geometry is not None:
                bbox = symbol_bbox(
                    lib_id=sym.lib_id,
                    anchor=sym.position,
                    rotation=sym.rotation,
                    cache=geometry,
                    owner_id=f"symbol:{sym.reference}",
                )
            else:
                bbox = placeholder_symbol_bbox(
                    sym.position, owner_id=f"symbol:{sym.reference}",
                )
        except Exception:
            bbox = placeholder_symbol_bbox(
                sym.position, owner_id=f"symbol:{sym.reference}",
            )
        self.occupancy.add(bbox)

    def add_wire(self, wire: PlacedWire) -> None:
        """Append a wire segment AND register its bbox in occupancy.

        The owner id is derived from the wire's index so callers can
        later exclude it from collision checks via ignore_owners.
        """
        self.wires.append(wire)
        index = len(self.wires) - 1
        bbox = wire_bbox(
            start=wire.start,
            end=wire.end,
            owner_id=f"wire_{index}",
        )
        self.occupancy.add(bbox)

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

    def finalize(self, block: Block) -> Sheet:
        """Freeze the accumulator into a :class:`Sheet`.

        Wires are passed through :func:`dedup_collinear_contained_wires`
        to merge overlapping collinear segments (the cluster + signal-
        override + edge-label passes routinely emit multiple short
        wires that share the same axis and overlap with one long
        net-spanning wire — KiCad merges them electrically but the
        redundant segments show as ``overlap.wire_wire`` validator
        hits and visually clutter the schematic).
        """
        deduped_wires = dedup_collinear_contained_wires(list(self.wires))
        return Sheet(
            name=block.name,
            title=block.title,
            paper_size=block.paper_size,
            symbols=tuple(self.symbols),
            wires=tuple(deduped_wires),
            labels=tuple(self.labels),
            junctions=tuple(self.junctions),
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


# ---- Label-bbox helpers (mirror the validator's) ---------------------------

def _label_bbox(label: PlacedLabel) -> BBox:
    """Bbox for a PlacedLabel, mirroring the validator's logic.

    The validator's `_label_text_bbox` chooses justify based on rotation
    (0 → left, 180 → right, 90/270 → axis-aligned-after-rotation). We
    reproduce that here so the live occupancy index sees the same
    bboxes the validator does.
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
    justify = "left" if label.rotation == 90.0 else "right"
    return text_bbox(
        text=label.net_name,
        anchor=label.position,
        rotation=label.rotation,
        justify=justify,
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
    justify = "left" if label.rotation == 90.0 else "right"
    return text_bbox(
        text=decorated_text,
        anchor=label.position,
        rotation=label.rotation,
        justify=justify,
        owner_id=owner_id,
        kind="hierarchical_label",
    )
