"""Declarative block model.

A ``Block`` describes one hierarchical sub-sheet *functionally* — what ICs
are on it, what connectors, what external nets it exposes — without naming
coordinates. The layout engine takes a ``Block`` and produces a
:class:`Sheet` of placed primitives.

This is the contract block builders write against::

    def build_power() -> Block:
        return Block(
            name="power",
            title="Power Architecture (USB-C 5V → 3V3 / 2V5 / 1V8 LDOs)",
            ics=(
                IcInstance(reference="U1", refcircuit=POWER_INPUT_REFCIRCUIT,
                           lib_id="Device:D_Schottky"),
                IcInstance(reference="U2", refcircuit=TLV75733_REFCIRCUIT,
                           lib_id="Regulator_Linear:TLV75733PDBV",
                           power_input_net="+VIN", power_output_net="+3V3"),
                ...
            ),
            external_nets=(
                PowerInputNet("+VIN_IN", edge=SheetEdge.LEFT),
                PowerOutputNet("+3V3",   edge=SheetEdge.RIGHT),
                ...
            ),
        )

The layout engine reads ``ics[i].refcircuit.external_parts`` to lay out
decoupling/pull-ups around each IC, and ``external_nets`` to place
hierarchical labels at sheet edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from zynq_eda.core.model.interface import SheetEdge
from zynq_eda.core.model.refcircuit import ReferenceCircuit


PaperSize = Literal["A4", "A3", "A2", "A1", "A0"]


@dataclass(frozen=True)
class ConnectorInstance:
    """One connector placement on a block.

    Connectors differ from ICs in that they sit on a sheet edge (USB-C on
    the right, FMC on the left, etc.) and carry an explicit per-pin net
    map supplied by the project — not derived from a refcircuit's
    ``external_parts``.

    Attributes:
        reference: Designator (``J1``). Must be unique within the block.
        refcircuit: The connector's datasheet-derived
            :class:`ReferenceCircuit` (for BOM + datasheet hyperlinking).
        lib_id: KiCad ``Library:SymbolName`` ID for the connector symbol.
        edge: Which sheet edge to place the connector on
            (typically ``LEFT`` or ``RIGHT``).
        pin_to_net: Tuple of ``(pin_id, net_name)`` pairs. ``pin_id`` is
            either a KiCad pin number (``"1"``) or a pin name
            (``"VBUS"``) — both are tried in order.
        rotation: Symbol rotation (0/90/180/270 degrees).
    """

    reference: str
    refcircuit: "ReferenceCircuit"
    lib_id: str
    edge: "SheetEdge"
    pin_to_net: tuple[tuple[str, str], ...] = ()
    rotation: float = 0.0
    decoupling_array: bool = False
    """When True, this owner's ``external_parts`` are NOT clustered on
    their pins; instead they are placed as a tidy column of standalone
    passives in open page space, each terminal tied to its net by a LOCAL
    LABEL (KiCad merges by net name). Use for dense connectors/ICs where
    clustering many decoupling caps on adjacent pins overprints. The pins
    themselves classify normally (signal hier-label / power symbol)."""

    def __post_init__(self) -> None:
        if not self.reference:
            raise ValueError("ConnectorInstance.reference must be non-empty")
        if not self.lib_id or ":" not in self.lib_id:
            raise ValueError(
                "ConnectorInstance.lib_id must be 'Library:SymbolName', got "
                f"{self.lib_id!r}"
            )
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                "ConnectorInstance.rotation must be 0/90/180/270, got "
                f"{self.rotation}"
            )


@dataclass(frozen=True)
class IcInstance:
    """One IC placement on a block.

    Attributes:
        reference: Designator (e.g. ``"U1"``). Must be unique within the block.
        refcircuit: The IC's datasheet-derived :class:`ReferenceCircuit`.
        lib_id: KiCad library:symbol ID (e.g. ``"Regulator_Linear:TLV75733PDBV"``,
            ``"zynq_eda:FUSB302BMPX"``). The placement engine queries pin
            geometry from this.
        power_input_net: Net name the IC's power input pin (IN/VDD/VCC/...)
            should be tied to. Used by the cluster algorithm to label the
            decoupling-cap-to-IN side. Falls back to
            ``refcircuit.supply_rail`` when omitted.
        power_output_net: Net name the IC's power output pin (OUT) should be
            tied to. Used for LDOs and similar power-converter ICs only.
        net_overrides: Per-pin overrides on top of
            ``refcircuit.pin_net_overrides`` (block-specific connectivity).
        external_part_net_remap: Catalog-level net-name renames applied
            during cluster placement. Each ``(catalog_net, block_net)``
            pair rewrites the destination of any ``ExternalPart.to_net``
            referencing ``catalog_net`` to ``block_net``. Used when a
            shared refcircuit names an internal rail (e.g. FUSB302's
            ``+3V3_SC`` for its scoped I2C pull-ups) that the project
            wants merged onto the carrier's main rail (e.g. ``+3V3``).
    """

    reference: str
    refcircuit: ReferenceCircuit
    lib_id: str
    power_input_net: str = ""
    power_output_net: str = ""
    net_overrides: tuple[tuple[str, str], ...] = ()
    external_part_net_remap: tuple[tuple[str, str], ...] = ()
    decoupling_array: bool = False
    """When True, ``external_parts`` are placed as a labeled column of
    standalone passives in open space (net-label-merged) rather than
    clustered on their pins — see :class:`ConnectorInstance`."""

    def __post_init__(self) -> None:
        if not self.reference:
            raise ValueError("IcInstance.reference must be non-empty")
        if not self.lib_id or ":" not in self.lib_id:
            raise ValueError(
                "IcInstance.lib_id must be 'Library:SymbolName', got "
                f"{self.lib_id!r}"
            )


@dataclass(frozen=True)
class ExternalNet:
    """A hierarchical-label net the block exposes to its parent sheet.

    Attributes:
        name: Net name (e.g. ``"+3V3"``, ``"STM32_I2C2_SDA"``).
        direction: KiCad pin shape — ``"input"`` (incoming), ``"output"``
            (outgoing), ``"bidirectional"``, ``"passive"``, ``"tri_state"``.
        edge: Which sheet edge the label sits on (left/right).
        power_kind: ``"input"`` if this is a power rail flowing IN to the
            block (block consumes it), ``"output"`` if flowing OUT
            (block produces it), or ``"signal"`` for non-power nets.
            Determines which side the cluster algorithm wires power to.
    """

    name: str
    direction: Literal["input", "output", "bidirectional", "passive", "tri_state"]
    edge: SheetEdge
    power_kind: Literal["input", "output", "ground", "signal"] = "signal"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ExternalNet.name must be non-empty")
        if self.direction not in {
            "input", "output", "bidirectional", "passive", "tri_state",
        }:
            raise ValueError(
                f"ExternalNet.direction invalid: {self.direction!r}"
            )
        if self.power_kind not in {"input", "output", "ground", "signal"}:
            raise ValueError(
                f"ExternalNet.power_kind invalid: {self.power_kind!r}"
            )


def PowerInputNet(name: str, edge: SheetEdge = SheetEdge.LEFT) -> ExternalNet:
    """Helper: a power rail the block consumes (label on left by convention)."""
    return ExternalNet(name=name, direction="input", edge=edge, power_kind="input")


def PowerOutputNet(name: str, edge: SheetEdge = SheetEdge.RIGHT) -> ExternalNet:
    """Helper: a power rail the block produces (label on right by convention)."""
    return ExternalNet(name=name, direction="output", edge=edge, power_kind="output")


def GroundNet(name: str = "GND", edge: SheetEdge = SheetEdge.LEFT) -> ExternalNet:
    """Helper: ground reference (label on left by convention)."""
    return ExternalNet(name=name, direction="passive", edge=edge, power_kind="ground")


def SignalNet(
    name: str,
    direction: Literal["input", "output", "bidirectional"] = "bidirectional",
    edge: SheetEdge = SheetEdge.LEFT,
) -> ExternalNet:
    """Helper: a non-power signal net crossing the block boundary."""
    return ExternalNet(name=name, direction=direction, edge=edge, power_kind="signal")


@dataclass(frozen=True)
class Block:
    """One hierarchical sub-sheet's declarative description."""

    name: str
    title: str
    paper_size: PaperSize = "A4"
    ics: tuple[IcInstance, ...] = field(default_factory=tuple)
    connectors: tuple[ConnectorInstance, ...] = field(default_factory=tuple)
    external_nets: tuple[ExternalNet, ...] = field(default_factory=tuple)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Block.name must be non-empty")
        if not self.name.replace("_", "").isalnum():
            raise ValueError(
                f"Block.name must be alphanumeric/underscore, got {self.name!r}"
            )
        if not self.title:
            raise ValueError("Block.title must be non-empty")

        seen_refs: set[str] = set()
        for ic in self.ics:
            if ic.reference in seen_refs:
                raise ValueError(
                    f"Block {self.name!r}: duplicate IC reference {ic.reference!r}"
                )
            seen_refs.add(ic.reference)
        for connector in self.connectors:
            if connector.reference in seen_refs:
                raise ValueError(
                    f"Block {self.name!r}: duplicate connector reference "
                    f"{connector.reference!r}"
                )
            seen_refs.add(connector.reference)

        seen_net_names: set[str] = set()
        for net in self.external_nets:
            if net.name in seen_net_names:
                raise ValueError(
                    f"Block {self.name!r}: duplicate external net {net.name!r}"
                )
            seen_net_names.add(net.name)
