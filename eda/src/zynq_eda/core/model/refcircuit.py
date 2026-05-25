"""Data structures that describe an IC's manufacturer reference circuit.

Every IC on the carrier has its TYPICAL APPLICATION CIRCUIT encoded as a
:class:`ReferenceCircuit` instance. The schematic generator consumes these
specs when placing the IC, so every supporting cap, pull-up, strap, and
layout rule is traceable back to its datasheet section.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zynq_eda.core.model.templates import IcBlockTemplate


@dataclass(frozen=True)
class ExternalPart:
    """A single external part required by an IC's reference circuit."""

    from_pin: str
    to_net: str
    part_token: str
    quantity: int = 1
    justification: str = ""

    def __post_init__(self) -> None:
        if not self.from_pin:
            raise ValueError("ExternalPart.from_pin must be non-empty")
        if not self.to_net:
            raise ValueError("ExternalPart.to_net must be non-empty")
        if not self.part_token:
            raise ValueError("ExternalPart.part_token must be non-empty")
        if self.quantity < 1:
            raise ValueError("ExternalPart.quantity must be >= 1")


@dataclass(frozen=True)
class StrapPin:
    """A pin tied to a specific net to configure the IC (e.g. I2C address)."""

    pin: str
    tied_to: str
    purpose: str
    justification: str = ""


@dataclass(frozen=True)
class LayoutNote:
    """A PCB-layout-time requirement captured at schematic time."""

    text: str
    severity: str = "rule"  # "rule" | "guideline" | "info"
    justification: str = ""


@dataclass(frozen=True)
class ReferenceCircuit:
    """Manufacturer-derived supporting-circuit specification for one IC."""

    part_mpn: str
    lcsc: str
    datasheet_url: str
    datasheet_revision: str
    app_circuit_figure: str
    symbol_token: str
    footprint: str
    local_datasheet_path: str = ""
    app_circuit_page: str = ""
    minimum_circuit_verified: bool = False
    external_parts: tuple[ExternalPart, ...] = field(default_factory=tuple)
    strap_pins: tuple[StrapPin, ...] = field(default_factory=tuple)
    no_external_required: frozenset[str] = field(default_factory=frozenset)
    layout_notes: tuple[LayoutNote, ...] = field(default_factory=tuple)
    description: str = ""
    supply_rail: str = ""
    pin_net_overrides: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    layout_template: IcBlockTemplate | None = None
    """Legacy per-IC placement template. Retained for the existing 28 refcircuit
    specs that set this field; the new layout engine ignores it and derives
    placement from real symbol pin geometry instead."""

    def __post_init__(self) -> None:
        if not self.part_mpn:
            raise ValueError("ReferenceCircuit.part_mpn must be non-empty")
        if not self.lcsc.startswith("C") or not self.lcsc[1:].isdigit():
            raise ValueError(
                f"ReferenceCircuit.lcsc must match ^C\\d+$, got {self.lcsc!r}"
            )
        if not self.datasheet_url:
            raise ValueError("ReferenceCircuit.datasheet_url must be non-empty")
        if self.minimum_circuit_verified and not self.local_datasheet_path:
            raise ValueError(
                f"ReferenceCircuit {self.part_mpn!r} is verified but "
                "local_datasheet_path is empty"
            )
        if self.local_datasheet_path and not self.app_circuit_page:
            raise ValueError(
                f"ReferenceCircuit {self.part_mpn!r} has local_datasheet_path "
                "but app_circuit_page is empty"
            )
        if not self.symbol_token:
            raise ValueError("ReferenceCircuit.symbol_token must be non-empty")
        if not self.footprint:
            raise ValueError("ReferenceCircuit.footprint must be non-empty")

    def expand_parts(self) -> list[ExternalPart]:
        """Return all external parts flattened (respecting quantity)."""
        expanded: list[ExternalPart] = []
        for part in self.external_parts:
            for _ in range(part.quantity):
                expanded.append(part)
        return expanded

    def total_external_count(self) -> int:
        return sum(part.quantity for part in self.external_parts)
