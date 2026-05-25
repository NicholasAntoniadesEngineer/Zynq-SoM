"""Data structures that describe an IC's manufacturer reference circuit.

Every IC on the carrier has its TYPICAL APPLICATION CIRCUIT encoded as a
ReferenceCircuit instance. The schematic generator consumes these specs
when placing the IC, so every supporting cap, pull-up, strap, and layout
rule is traceable back to its datasheet section.

Used by:
    scripts/carrier/refcircuits/<part>.py  - one spec per IC
    scripts/carrier/sheets/*.py            - sheet.place_ic(ref, REFCIRCUIT)
    scripts/carrier/rules.py               - rule C11 conformance check
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.carrier.model.templates import IcBlockTemplate


@dataclass(frozen=True)
class ExternalPart:
    """A single external part required by an IC's reference circuit.

    Attributes:
        from_pin: The IC pin (or named pin function) this part attaches to.
        to_net: The net (or pin on another part) on the other side.
        part_token: Canonical part token, resolved to an LCSC# via the BOM
            registry. Examples: "100n_0402_X7R", "1u_0402_X7R", "5.1k_0402_1%",
            "10k_0402_1%", "ferrite_600R_0402".
        quantity: Number of identical instances of this part (e.g., one cap
            per VCC pin where multiple VCC pins exist).
        justification: Free-text citation of the datasheet section/figure that
            requires this part. Example: "Fig 7, Sec 6.1 VBUS decoupling".
    """

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
    """A pin tied to a specific net to configure the IC (e.g. I2C address).

    Attributes:
        pin: IC pin name or number.
        tied_to: Net the pin must be tied to (e.g. "GND", "+3V3").
        purpose: Human-readable explanation. E.g. "I2C address bit A0 = 0".
        justification: Datasheet section citation.
    """

    pin: str
    tied_to: str
    purpose: str
    justification: str = ""


@dataclass(frozen=True)
class LayoutNote:
    """A PCB-layout-time requirement captured at schematic time.

    These are emitted into the schematic as text annotations and into the
    reference_circuits.md document so the PCB designer sees them.
    """

    text: str
    severity: str = "rule"  # "rule" | "guideline" | "info"
    justification: str = ""


@dataclass(frozen=True)
class ReferenceCircuit:
    """Manufacturer-derived supporting-circuit specification for one IC.

    Attributes:
        part_mpn: Manufacturer part number (e.g. "FUSB302BMPX").
        lcsc: LCSC part number (e.g. "C442699").
        datasheet_url: URL to the datasheet PDF.
        datasheet_revision: Revision and date (e.g. "Rev 6, May 2020").
        app_circuit_figure: Figure/section reference for the Typical Application
            Circuit (e.g. "Figure 7 - Typical Application").
        local_datasheet_path: Repo-relative path under ``scripts/carrier/`` to
            the saved datasheet PDF (e.g. ``"datasheets/FUSB302BMPX.pdf"``).
        app_circuit_page: Page and figure citation for the minimum circuit
            (e.g. ``"p.22, Figure 5"``).
        minimum_circuit_verified: True only after manual audit against the
            local PDF; block builders refuse to run when False.
        symbol_token: Canonical symbol name in scripts/carrier/symbols/
            (e.g. "FUSB302BMPX_QFN14").
        footprint: KiCad footprint reference (e.g. "fp:FUSB302BMPX_QFN14_2.5x2.5mm").
        external_parts: Tuple of ExternalPart instances - every part the
            datasheet requires.
        strap_pins: Tuple of StrapPin instances - pin configurations.
        no_external_required: Pins that the datasheet explicitly says need
            no external components (e.g. FUSB302 CC1/CC2 have internal Rd/Rp).
        layout_notes: Tuple of LayoutNote instances - PCB-layout constraints.
        description: Short human description (one line).
        supply_rail: Default supply net for VDD/VCC decoupling caps (e.g. "+3V3").
        pin_net_overrides: IC pin -> schematic net name for system connectivity
            (must match io_assignment.carrier_signal where applicable).
        layout_template: Optional hand-designed placement template for block
            factories (see ``model/templates.py``).
    """

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
