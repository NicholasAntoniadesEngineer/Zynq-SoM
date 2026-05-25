"""Sheet model: the engine's output, an emitter's input.

A :class:`Sheet` is what the layout + routing engines produce. The emitter
takes a Sheet and writes a ``.kicad_sch``. Every coordinate is grid-snapped
and absolute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from zynq_eda.core.model.grid import Point, assert_on_grid
from zynq_eda.core.model.interface import HierarchicalPin


PaperSize = Literal["A4", "A3", "A2", "A1", "A0"]


# KiCad-canonical paper dimensions in millimetres.
PAPER_DIMENSIONS_MM: dict[PaperSize, tuple[float, float]] = {
    "A0": (1189.0, 841.0),
    "A1": (841.0, 594.0),
    "A2": (594.0, 420.0),
    "A3": (420.0, 297.0),
    "A4": (297.0, 210.0),
}


@dataclass(frozen=True)
class PlacedSymbol:
    """A single placed symbol on the sheet (ic / passive / connector)."""

    lib_id: str
    reference: str
    value: str
    position: Point
    footprint: str
    rotation: float = 0.0
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.lib_id or ":" not in self.lib_id:
            raise ValueError(
                f"PlacedSymbol.lib_id must be 'Library:Name', got {self.lib_id!r}"
            )
        if not self.reference:
            raise ValueError("PlacedSymbol.reference must be non-empty")
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                f"PlacedSymbol.rotation must be 0/90/180/270, got {self.rotation}"
            )
        assert_on_grid(self.position)


@dataclass(frozen=True)
class PlacedWire:
    """A straight wire segment between two grid-aligned points."""

    start: Point
    end: Point

    def __post_init__(self) -> None:
        assert_on_grid(self.start)
        assert_on_grid(self.end)
        if self.start == self.end:
            raise ValueError(f"PlacedWire start == end ({self.start}); zero-length wire")


@dataclass(frozen=True)
class PlacedLabel:
    """A local-scope net label."""

    net_name: str
    position: Point
    rotation: float = 0.0

    def __post_init__(self) -> None:
        if not self.net_name:
            raise ValueError("PlacedLabel.net_name must be non-empty")
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(f"PlacedLabel.rotation invalid: {self.rotation}")
        assert_on_grid(self.position)


@dataclass(frozen=True)
class PlacedJunction:
    """A junction marker where 3+ wires meet."""

    position: Point

    def __post_init__(self) -> None:
        assert_on_grid(self.position)


@dataclass(frozen=True)
class PlacedNoConnect:
    """A no-connect (NC) marker on an unused IC pin."""

    position: Point

    def __post_init__(self) -> None:
        assert_on_grid(self.position)


@dataclass(frozen=True)
class PlacedHierarchicalLabel:
    """A hierarchical label on a sheet edge (sheet-to-parent contract)."""

    net_name: str
    position: Point
    direction: Literal["input", "output", "bidirectional", "passive", "tri_state"]
    rotation: float = 0.0

    def __post_init__(self) -> None:
        if not self.net_name:
            raise ValueError("PlacedHierarchicalLabel.net_name must be non-empty")
        if self.direction not in {
            "input", "output", "bidirectional", "passive", "tri_state",
        }:
            raise ValueError(
                f"PlacedHierarchicalLabel.direction invalid: {self.direction!r}"
            )
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                f"PlacedHierarchicalLabel.rotation invalid: {self.rotation}"
            )
        assert_on_grid(self.position)


@dataclass(frozen=True)
class Sheet:
    """One A4 (or other-size) page of placed primitives."""

    name: str
    title: str
    paper_size: PaperSize
    symbols: tuple[PlacedSymbol, ...] = field(default_factory=tuple)
    wires: tuple[PlacedWire, ...] = field(default_factory=tuple)
    labels: tuple[PlacedLabel, ...] = field(default_factory=tuple)
    junctions: tuple[PlacedJunction, ...] = field(default_factory=tuple)
    no_connects: tuple[PlacedNoConnect, ...] = field(default_factory=tuple)
    hierarchical_labels: tuple[PlacedHierarchicalLabel, ...] = field(default_factory=tuple)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Sheet.name must be non-empty")
        if not self.title:
            raise ValueError("Sheet.title must be non-empty")
        if self.paper_size not in PAPER_DIMENSIONS_MM:
            raise ValueError(f"Sheet.paper_size invalid: {self.paper_size!r}")

    @property
    def paper_dimensions(self) -> tuple[float, float]:
        return PAPER_DIMENSIONS_MM[self.paper_size]

    @property
    def paper_width_mm(self) -> float:
        return self.paper_dimensions[0]

    @property
    def paper_height_mm(self) -> float:
        return self.paper_dimensions[1]

    def to_hierarchical_pins(self) -> tuple[HierarchicalPin, ...]:
        """Convert hierarchical labels to HierarchicalPin (parent-sheet contract)."""
        from zynq_eda.core.model.interface import PinDirection, SheetEdge

        pins: list[HierarchicalPin] = []
        for label in self.hierarchical_labels:
            # Edge derivation: x near 0 → LEFT, x near paper_width → RIGHT
            if label.position.x < self.paper_width_mm / 2:
                edge = SheetEdge.LEFT
            else:
                edge = SheetEdge.RIGHT
            pins.append(HierarchicalPin(
                net_name=label.net_name,
                direction=PinDirection(label.direction),
                edge=edge,
                position_along_edge=label.position.y,
                label_position=label.position,
            ))
        return tuple(pins)
