"""Block: the unit a hierarchical sub-sheet is built from.

A ``Block`` is the complete, sheet-ready description of one functional
sub-sheet (USB-PD subsystem, SoM connectors, power-monitoring section, ...).
It is pure data; the ``emit/kicad_sch.py`` adapter turns it into a real
``kicad-sch-api.Schematic`` and ``sheets/root.py`` consumes the
``hierarchical_pins`` to wire blocks together on the parent page.

Construction is done by block-factory modules under ``scripts/carrier/blocks/``
which read the ``ReferenceCircuit`` for each IC plus an ``IcBlockTemplate``
for placement geometry, then assemble the placed components, wires and
labels into a ``Block``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from scripts.carrier.model.grid import Point, assert_on_grid
from scripts.carrier.model.interface import HierarchicalPin


PaperSize = Literal["A4", "A3", "A2", "A1", "A0"]
"""KiCad-supported ISO paper sizes."""


@dataclass(frozen=True)
class BlockLayout:
    """Sheet-level geometry for a block.

    Attributes:
        paper_size: ISO paper size string accepted by
            ``kicad-sch-api.Schematic.set_paper_size``.
        width_mm: Physical paper width (matches paper_size; kept explicit so
            block builders can size hierarchical pins without re-deriving it).
        height_mm: Physical paper height (matches paper_size).
        interior_margin_mm: Distance from page edge inside which placement is
            forbidden. Hierarchical labels live just outside the right or
            left margin so they're aligned with the sheet edge.
    """

    paper_size: PaperSize
    width_mm: float
    height_mm: float
    interior_margin_mm: float

    def __post_init__(self) -> None:
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError(
                "BlockLayout dimensions must be positive: "
                f"width={self.width_mm}, height={self.height_mm}"
            )
        if self.interior_margin_mm < 0:
            raise ValueError(
                "BlockLayout.interior_margin_mm must be >= 0, got "
                f"{self.interior_margin_mm}"
            )


@dataclass(frozen=True)
class PlacedComponent:
    """A single symbol instance to add via ``schematic.components.add``.

    Attributes:
        lib_id: Library ID in ``Library:SymbolName`` form (e.g.
            ``"symbol_Zynq_SoM:Zynq_SoM_J1"`` or ``"Device:R"``).
        reference: Reference designator already annotated (no ``?``).
        value: Schematic ``Value`` field.
        position: Anchor position in millimetres.
        footprint: KiCad footprint, e.g.
            ``"Resistor_SMD:R_0402_1005Metric"``. Empty string is allowed
            only when no PCB is intended (not allowed for the carrier).
        rotation: Symbol rotation in degrees (0, 90, 180, 270).
        properties: Extra property fields to set on the placed instance.
    """

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
                "PlacedComponent.lib_id must be 'Library:SymbolName', got "
                f"{self.lib_id!r}"
            )
        if not self.reference:
            raise ValueError("PlacedComponent.reference must be non-empty")
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                "PlacedComponent.rotation must be 0/90/180/270, got "
                f"{self.rotation}"
            )
        assert_on_grid(self.position)


@dataclass(frozen=True)
class Wire:
    """A single straight wire segment between two grid-aligned points."""

    start: Point
    end: Point

    def __post_init__(self) -> None:
        assert_on_grid(self.start)
        assert_on_grid(self.end)
        if self.start == self.end:
            raise ValueError(
                f"Wire start == end ({self.start}); zero-length wires are invalid"
            )


@dataclass(frozen=True)
class LocalLabel:
    """A local net label (visible only on the owning sheet)."""

    net_name: str
    position: Point
    rotation: float = 0.0

    def __post_init__(self) -> None:
        if not self.net_name:
            raise ValueError("LocalLabel.net_name must be non-empty")
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                "LocalLabel.rotation must be 0/90/180/270, got "
                f"{self.rotation}"
            )
        assert_on_grid(self.position)


@dataclass(frozen=True)
class SheetText:
    """Free text annotation on a block sub-sheet."""

    text: str
    position: Point
    rotation: float = 0.0

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("SheetText.text must be non-empty")
        assert_on_grid(self.position)


@dataclass(frozen=True)
class Block:
    """Complete description of one hierarchical sub-sheet.

    Attributes:
        name: Lower-case identifier (e.g. ``"som"``, ``"usb_pd"``). Used as
            the sub-sheet filename stem and as the parent-side sheet symbol
            name.
        title: Human-readable sheet title shown in KiCad's title block.
        layout: Paper size + interior margin.
        components: Symbols placed on this sub-sheet.
        wires: Wire segments between component pins / labels.
        local_labels: Labels scoped to this sub-sheet.
        hierarchical_pins: The block's wiring contract with the parent
            sheet. Each entry maps 1:1 to a hierarchical label inside this
            sub-sheet AND a sheet-pin on the parent-side sheet symbol.
        sheet_texts: Optional text annotations (block title notes, layout
            rules) emitted as schematic text objects.
        symbol_library_paths: Extra ``.kicad_sym`` files this block needs
            loaded into the symbol cache before emission (e.g. the SoM
            connector library). Repo-relative paths.
    """

    name: str
    title: str
    layout: BlockLayout
    components: tuple[PlacedComponent, ...] = ()
    wires: tuple[Wire, ...] = ()
    local_labels: tuple[LocalLabel, ...] = ()
    hierarchical_pins: tuple[HierarchicalPin, ...] = ()
    sheet_texts: tuple[SheetText, ...] = ()
    symbol_library_paths: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Block.name must be non-empty")
        if not self.name.replace("_", "").isalnum():
            raise ValueError(
                f"Block.name must be alphanumeric/underscore, got {self.name!r}"
            )
        if not self.title:
            raise ValueError("Block.title must be non-empty")
        seen_references: set[str] = set()
        for placed in self.components:
            if placed.reference in seen_references:
                raise ValueError(
                    "Block.components has duplicate reference "
                    f"{placed.reference!r} in block {self.name!r}"
                )
            seen_references.add(placed.reference)
        seen_pin_names: set[str] = set()
        for hierarchical_pin in self.hierarchical_pins:
            if hierarchical_pin.net_name in seen_pin_names:
                raise ValueError(
                    "Block.hierarchical_pins has duplicate net_name "
                    f"{hierarchical_pin.net_name!r} in block {self.name!r}"
                )
            seen_pin_names.add(hierarchical_pin.net_name)
