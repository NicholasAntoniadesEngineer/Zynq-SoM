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
    """A single placed symbol on the sheet (ic / passive / connector).

    ``value_shift`` is an optional override of the Value property's
    rendered position relative to the symbol anchor at rotation 0.
    Set by the cluster passive placer (which probes for a clear slot
    around the body) and consumed by both the emitter (writes the
    shifted position into the .kicad_sch) and the validator (rebuilds
    the Value bbox at the shifted anchor). Tuple format:
    ``(dx_mm, dy_mm, text_rotation_override_or_None)``.
    """

    lib_id: str
    reference: str
    value: str
    position: Point
    footprint: str
    rotation: float = 0.0
    properties: tuple[tuple[str, str], ...] = ()
    value_shift: tuple[float, float, float | None] | None = None
    reference_shift: tuple[float, float, float | None] | None = None
    """Optional override of the Reference property's rendered position
    relative to the symbol anchor at rotation 0. Mirrors ``value_shift``
    semantics. When set, the emitter writes the shifted position into
    the .kicad_sch and the validator rebuilds the Reference bbox at the
    shifted anchor. Tuple format: ``(dx_mm, dy_mm, text_rotation_override
    _or_None)``."""
    value_hidden: bool = False
    """When True, the Value property is emitted with ``(hide yes)``: the
    text doesn't render and the validator skips its bbox. Used for
    duplicate power symbols on cluster sub-slots (slots N≥1 sharing
    the same destination as slot 0) — the FIRST slot's symbol shows
    the net name; subsequent slots' symbols still merge by Value field
    in KiCad's netlist but contribute no visible text. Eliminates the
    duplicate-text overlap without losing electrical connectivity."""
    reference_hidden: bool = False
    """Mirrors ``value_hidden`` for the Reference property. Used for
    cluster sub-slot power symbols where the Reference designator
    (e.g. #PWR301, #PWR302) would otherwise stack on top of slot 0's
    Reference text."""

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
class PlacedGlobalLabel:
    """A global-scope net label.

    KiCad's `(global_label ...)` primitive: any two global labels with
    the same ``net_name`` merge into the SAME net across the whole
    project, irrespective of which sheet they're on. We use this for
    cross-block signal nets so the root sheet doesn't need explicit
    sheet pins / connecting wires for every signal — pasting the
    signal name at each sub-sheet endpoint is enough.

    The ``direction`` (KiCad calls it "shape") drives the arrow glyph
    rendered next to the label; it doesn't change the electrical
    behaviour.
    """

    net_name: str
    position: Point
    direction: Literal["input", "output", "bidirectional", "passive", "tri_state"] = "bidirectional"
    rotation: float = 0.0

    def __post_init__(self) -> None:
        if not self.net_name:
            raise ValueError("PlacedGlobalLabel.net_name must be non-empty")
        if self.direction not in {
            "input", "output", "bidirectional", "passive", "tri_state",
        }:
            raise ValueError(
                f"PlacedGlobalLabel.direction invalid: {self.direction!r}"
            )
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                f"PlacedGlobalLabel.rotation invalid: {self.rotation}"
            )
        assert_on_grid(self.position)


@dataclass(frozen=True)
class PlacedSheetPin:
    """One sheet pin on a root-level :class:`PlacedSheet` symbol.

    The pin lives on one edge of the sheet symbol's rectangle. The exact
    page coordinate is derived at emission time from
    ``parent_sheet.position`` + ``edge`` + ``position_along_edge``.
    """

    name: str
    direction: Literal["input", "output", "bidirectional", "passive", "tri_state"]
    edge: Literal["left", "right", "top", "bottom"]
    position_along_edge: float  # mm from the edge's reference corner

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PlacedSheetPin.name must be non-empty")
        if self.direction not in {
            "input", "output", "bidirectional", "passive", "tri_state",
        }:
            raise ValueError(f"PlacedSheetPin.direction invalid: {self.direction!r}")
        if self.edge not in {"left", "right", "top", "bottom"}:
            raise ValueError(f"PlacedSheetPin.edge invalid: {self.edge!r}")
        if self.position_along_edge < 0:
            raise ValueError(
                "PlacedSheetPin.position_along_edge must be >= 0, got "
                f"{self.position_along_edge}"
            )


@dataclass(frozen=True)
class PlacedSheet:
    """A hierarchical sheet symbol on the root sheet (a "block box").

    Each :class:`PlacedSheet` becomes one ``(sheet ...)`` s-expression in
    the emitted root ``.kicad_sch``. Its ``filename`` points at the
    sub-sheet (e.g. ``"sheets/power.kicad_sch"``); ``pins`` lists the
    edge connections that mirror the sub-sheet's hierarchical labels.
    """

    name: str
    filename: str
    position: Point
    size: tuple[float, float]
    pins: tuple[PlacedSheetPin, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PlacedSheet.name must be non-empty")
        if not self.filename:
            raise ValueError("PlacedSheet.filename must be non-empty")
        if len(self.size) != 2 or self.size[0] <= 0 or self.size[1] <= 0:
            raise ValueError(f"PlacedSheet.size must be positive (w, h), got {self.size!r}")
        assert_on_grid(self.position)
        seen_pin_names: set[str] = set()
        for pin in self.pins:
            if pin.name in seen_pin_names:
                raise ValueError(
                    f"PlacedSheet {self.name!r}: duplicate pin name {pin.name!r}"
                )
            seen_pin_names.add(pin.name)


@dataclass(frozen=True)
class Sheet:
    """One A4 (or other-size) page of placed primitives.

    ``paper_portrait`` swaps width/height for the named paper size. KiCad
    natively writes A0–A4 in landscape; setting ``paper_portrait=True``
    flips the page orientation and the :class:`Sheet`'s reported
    ``paper_width_mm`` / ``paper_height_mm``. Used by the root index
    page (A3 portrait, 297 wide × 420 tall) so its block grid stacks
    naturally vertical. The emitter rewrites the ``(paper "A3")``
    s-expression to ``(paper "A3" portrait)`` at save time.
    """

    name: str
    title: str
    paper_size: PaperSize
    symbols: tuple[PlacedSymbol, ...] = field(default_factory=tuple)
    wires: tuple[PlacedWire, ...] = field(default_factory=tuple)
    labels: tuple[PlacedLabel, ...] = field(default_factory=tuple)
    junctions: tuple[PlacedJunction, ...] = field(default_factory=tuple)
    no_connects: tuple[PlacedNoConnect, ...] = field(default_factory=tuple)
    hierarchical_labels: tuple[PlacedHierarchicalLabel, ...] = field(default_factory=tuple)
    global_labels: tuple[PlacedGlobalLabel, ...] = field(default_factory=tuple)
    sheets: tuple[PlacedSheet, ...] = field(default_factory=tuple)
    description: str = ""
    paper_portrait: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Sheet.name must be non-empty")
        if not self.title:
            raise ValueError("Sheet.title must be non-empty")
        if self.paper_size not in PAPER_DIMENSIONS_MM:
            raise ValueError(f"Sheet.paper_size invalid: {self.paper_size!r}")

    @property
    def paper_dimensions(self) -> tuple[float, float]:
        landscape = PAPER_DIMENSIONS_MM[self.paper_size]
        if self.paper_portrait:
            return (landscape[1], landscape[0])
        return landscape

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
