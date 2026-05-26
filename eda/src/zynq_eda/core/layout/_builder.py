"""Mutable accumulator used by every placement subroutine.

The placement engine is structured as a set of small helpers that each
take a :class:`_BlockLayoutBuilder` and append to its collections. At the
end, :meth:`_BlockLayoutBuilder.finalize` freezes the accumulator into a
:class:`Sheet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import (
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
    """Mutable accumulator of placed primitives while building a block."""

    symbols: list[PlacedSymbol] = field(default_factory=list)
    wires: list[PlacedWire] = field(default_factory=list)
    labels: list[PlacedLabel] = field(default_factory=list)
    junctions: list[PlacedJunction] = field(default_factory=list)
    no_connects: list[PlacedNoConnect] = field(default_factory=list)
    hierarchical_labels: list[PlacedHierarchicalLabel] = field(default_factory=list)
    sheets: list[PlacedSheet] = field(default_factory=list)
    _ref_counters: dict[str, int] = field(
        default_factory=lambda: {"C": 100, "R": 100, "D": 100, "PWR": 100, "FLG": 100}
    )

    def next_ref(self, prefix: str) -> str:
        """Return a fresh designator for the given prefix (e.g. ``C103``)."""
        index = self._ref_counters.setdefault(prefix, 100)
        self._ref_counters[prefix] = index + 1
        return f"{prefix}{index}"

    def finalize(self, block: Block) -> Sheet:
        """Freeze the accumulator into a :class:`Sheet`."""
        return Sheet(
            name=block.name,
            title=block.title,
            paper_size=block.paper_size,
            symbols=tuple(self.symbols),
            wires=tuple(self.wires),
            labels=tuple(self.labels),
            junctions=tuple(self.junctions),
            no_connects=tuple(self.no_connects),
            hierarchical_labels=tuple(self.hierarchical_labels),
            sheets=tuple(self.sheets),
            description=block.description,
        )


def _unused_dedup_shared_endpoint_wires(wires: list[PlacedWire]) -> list[PlacedWire]:
    """Drop wires that are fully covered by a longer collinear wire sharing a start/end point.

    Multi-slot clusters on LEFT/RIGHT-side IC pins emit one wire per
    slot from the IC pin to that slot's near-pin. All these wires
    share an endpoint (the IC pin) and are collinear along the pin's
    Y row. Slot 0's 6.35 mm wire and slot 1's 21.59 mm wire share
    their start (IC pin). KiCad's hierarchical-flatten ERC sees this
    as two overlapping wires and reports each pair as wire_dangling
    with sub-grid fragment lengths.

    The shorter wire is functionally redundant: the longer wire
    already passes through the shorter's endpoint, so KiCad nets the
    cap pin to the IC pin via the longer wire. Dropping the shorter
    one eliminates the false wire_dangling and preserves connectivity.

    Why we ONLY drop wires that share an endpoint (and not arbitrary
    contained segments): a cap-to-GND wire and a different pin's
    cluster pin-to-near wire might be collinear and overlap by mere
    coincidence, but they carry different nets. Dropping a wire that
    doesn't share an endpoint with the longer one would silently
    disconnect a component pin. Restricting to shared-endpoint pairs
    keeps the dedup safe.
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
        kept: list[PlacedWire] = []
        # Sort by length descending so we process longer wires first.
        sorted_wires = sorted(bucket, key=lambda w: -length(w))
        for w in sorted_wires:
            x1, y1 = w.start.x, w.start.y
            x2, y2 = w.end.x, w.end.y
            w_lo = min(x1, x2) if horizontal else min(y1, y2)
            w_hi = max(x1, x2) if horizontal else max(y1, y2)
            covered = False
            for k in kept:
                kx1, ky1 = k.start.x, k.start.y
                kx2, ky2 = k.end.x, k.end.y
                k_lo = min(kx1, kx2) if horizontal else min(ky1, ky2)
                k_hi = max(kx1, kx2) if horizontal else max(ky1, ky2)
                # Must share at least one endpoint with k AND be inside k's range.
                shares_endpoint = (
                    (abs(x1 - kx1) < 1e-6 and abs(y1 - ky1) < 1e-6)
                    or (abs(x1 - kx2) < 1e-6 and abs(y1 - ky2) < 1e-6)
                    or (abs(x2 - kx1) < 1e-6 and abs(y2 - ky1) < 1e-6)
                    or (abs(x2 - kx2) < 1e-6 and abs(y2 - ky2) < 1e-6)
                )
                contained = w_lo >= k_lo - 1e-6 and w_hi <= k_hi + 1e-6
                if shares_endpoint and contained:
                    covered = True
                    break
            if not covered:
                kept.append(w)
        return kept

    result: list[PlacedWire] = list(other)
    for bucket in horiz.values():
        result.extend(filter_bucket(bucket, horizontal=True))
    for bucket in vert.values():
        result.extend(filter_bucket(bucket, horizontal=False))
    return result
