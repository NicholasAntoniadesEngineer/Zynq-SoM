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
    PlacedSymbol,
    PlacedWire,
    Sheet,
)


@dataclass(frozen=True)
class PinGeometryAbs:
    """Subset of :class:`PinGeometry` retained while a block is being built.

    Stores absolute schematic-page coordinates (after Y-flip + rotation) so
    downstream wiring code doesn't have to re-derive them.
    """

    anchor: Point
    connection: Point
    relative: Point


@dataclass
class BlockLayoutBuilder:
    """Mutable accumulator of placed primitives while building a block."""

    symbols: list[PlacedSymbol] = field(default_factory=list)
    wires: list[PlacedWire] = field(default_factory=list)
    labels: list[PlacedLabel] = field(default_factory=list)
    junctions: list[PlacedJunction] = field(default_factory=list)
    no_connects: list[PlacedNoConnect] = field(default_factory=list)
    hierarchical_labels: list[PlacedHierarchicalLabel] = field(default_factory=list)
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
            description=block.description,
        )
