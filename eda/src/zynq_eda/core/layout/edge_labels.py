"""Hierarchical-label placement at sheet edges.

Each :class:`ExternalNet` declared on a block becomes one or more
hierarchical labels on the configured edge of the sub-sheet. Power-input
nets also get one ``power:PWR_FLAG`` per net so ERC accepts the sub-sheet
standalone (without a populated parent sheet).

Ground nets share one bottom-edge label and a single PWR_FLAG.
"""

from __future__ import annotations

from zynq_eda.core.layout._builder import BlockLayoutBuilder, PinGeometryAbs
from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM, POWER_SYMBOL_OFFSET_MM
from zynq_eda.core.model.block import Block, ExternalNet, IcInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.interface import SheetEdge
from zynq_eda.core.model.sheet import (
    PAPER_DIMENSIONS_MM,
    PlacedHierarchicalLabel,
    PlacedSymbol,
    PlacedWire,
)


def place_external_nets(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    ic_anchors: dict[str, Point],
) -> set[tuple[str, str]]:
    """Place per-IC hierarchical labels + PWR_FLAGs.

    Returns the set of ``(ic_reference, pin_name)`` pairs that already
    received an edge-label wiring, so :func:`place._attach_ic_signal_overrides`
    can skip them and avoid creating duplicate connections.
    """
    paper_w, _paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    left_x = snap_to_grid(INTERIOR_MARGIN_MM)
    right_x = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)

    declared_nets: dict[str, ExternalNet] = {net.name: net for net in block.external_nets}

    seen_label_positions: set[tuple[float, float]] = set()
    edge_labeled: set[tuple[str, str]] = _per_ic_pin_labels(
        builder,
        block=block,
        declared_nets=declared_nets,
        ic_pin_geometries=ic_pin_geometries,
        left_x=left_x,
        right_x=right_x,
        seen_label_positions=seen_label_positions,
    )

    _input_pwr_flags(
        builder,
        block=block,
    )

    _ground_label_and_flag(
        builder,
        block=block,
        ic_anchors=ic_anchors,
        left_x=left_x,
        right_x=right_x,
        seen_label_positions=seen_label_positions,
    )

    return edge_labeled


def _per_ic_pin_labels(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    declared_nets: dict[str, ExternalNet],
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    left_x: float,
    right_x: float,
    seen_label_positions: set[tuple[float, float]],
) -> set[tuple[str, str]]:
    """Emit one hierarchical label per (IC, override-or-supply pin), aligned with pin Y.

    Returns the set of ``(ic_reference, pin_name)`` pairs that got an
    edge-label wire so the signal-override pass can skip them.
    """
    edge_labeled: set[tuple[str, str]] = set()

    for ic in block.ics:
        ic_geoms = ic_pin_geometries.get(ic.reference, {})

        # Build the candidate list: (pin_name, target_net). Sources:
        # 1. Refcircuit + per-instance pin_net_overrides — the IC's explicit
        #    "this pin is on net X" declarations. Highest priority.
        # 2. ic.power_input_net / power_output_net mapped to standard pin
        #    names. Lower priority — skipped when the same pin already has
        #    an explicit override.
        explicit_overrides: dict[str, str] = dict(ic.refcircuit.pin_net_overrides)
        explicit_overrides |= dict(getattr(ic, "net_overrides", ()) or ())

        candidates: list[tuple[str, str]] = []
        for pin_name, net_name in explicit_overrides.items():
            candidates.append((pin_name, net_name))

        if ic.power_input_net:
            for pin_name in ("IN", "VDD", "VCC", "VBUS", "AVDD", "DVDD", "PVIN", "ANODE"):
                if pin_name in explicit_overrides:
                    continue
                candidates.append((pin_name, ic.power_input_net))
        if ic.power_output_net:
            for pin_name in ("OUT", "VOUT", "CATHODE"):
                if pin_name in explicit_overrides:
                    continue
                candidates.append((pin_name, ic.power_output_net))

        for pin_role, net_name in candidates:
            if net_name not in declared_nets:
                # Pin's override doesn't match an external net — leave it
                # for the signal-override pass to handle as a local label.
                continue
            if pin_role not in ic_geoms:
                # Pin missing from the symbol (refcircuit name mismatch).
                continue
            net = declared_nets[net_name]
            pin_connection = ic_geoms[pin_role].connection
            label_x = left_x if net.edge == SheetEdge.LEFT else right_x
            label_position = Point(label_x, snap_to_grid(pin_connection.y))
            key = (label_position.x, label_position.y)
            if key in seen_label_positions:
                # Two IC pins want the same edge label slot — leave the
                # second one for signal-override (it'll get a local label).
                continue
            seen_label_positions.add(key)

            rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
            builder.hierarchical_labels.append(PlacedHierarchicalLabel(
                net_name=net_name,
                position=label_position,
                direction=net.direction,
                rotation=rotation,
            ))
            builder.wires.append(PlacedWire(
                start=pin_connection,
                end=label_position,
            ))
            edge_labeled.add((ic.reference, pin_role))

    return edge_labeled


def _input_pwr_flags(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
) -> None:
    """Emit exactly one ``power:PWR_FLAG`` per input-direction net.

    ERC requires every power_in pin to have an upstream power_out driver.
    The hierarchical label alone doesn't qualify, so we add a PWR_FLAG to
    every incoming power net. Output-direction nets (LDO OUT etc.) are
    driven by the IC's power_out pin and need no flag — adding one would
    create a pin_to_pin conflict with two competing power_out drivers.
    Ground nets are handled separately by :func:`_ground_label_and_flag`.
    """
    flag_emitted_for_net: set[str] = set()
    for net in block.external_nets:
        if net.power_kind not in ("input", "output"):
            continue
        # Output nets only need a PWR_FLAG when the block itself doesn't
        # contain a power_out pin to drive them. We detect this by checking
        # whether any IC declares this net as ``power_output_net``.
        if net.power_kind == "output":
            has_power_out_driver = any(
                ic.power_output_net == net.name for ic in block.ics
            )
            if has_power_out_driver:
                continue
        if net.name in flag_emitted_for_net:
            continue
        flag_emitted_for_net.add(net.name)

        anchor_label = next(
            (label for label in builder.hierarchical_labels if label.net_name == net.name),
            None,
        )
        if anchor_label is None:
            continue

        flag_offset = -3.81 if net.edge == SheetEdge.LEFT else 3.81
        flag_position = Point(
            snap_to_grid(anchor_label.position.x + flag_offset),
            anchor_label.position.y,
        )
        builder.wires.append(PlacedWire(
            start=anchor_label.position,
            end=flag_position,
        ))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value=net.name,
            position=flag_position,
            footprint="",
            rotation=0.0,
        ))


def _ground_label_and_flag(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    ic_anchors: dict[str, Point],
    left_x: float,
    right_x: float,
    seen_label_positions: set[tuple[float, float]],
) -> None:
    """Emit one bottom-of-edge GND hierarchical label + PWR_FLAG + power:GND."""
    for ground_net in block.external_nets:
        if ground_net.power_kind != "ground":
            continue
        label_x = left_x if ground_net.edge == SheetEdge.LEFT else right_x
        ic_y_values = [anchor.y for anchor in ic_anchors.values()]
        if ic_y_values:
            label_y = snap_to_grid(max(ic_y_values) + 38.1)
        else:
            label_y = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
        label_position = Point(label_x, label_y)
        key = (label_position.x, label_position.y)
        if key in seen_label_positions:
            continue
        seen_label_positions.add(key)

        rotation = 180.0 if ground_net.edge == SheetEdge.LEFT else 0.0
        builder.hierarchical_labels.append(PlacedHierarchicalLabel(
            net_name=ground_net.name,
            position=label_position,
            direction=ground_net.direction,
            rotation=rotation,
        ))

        # power:GND symbol that "drives" the hierarchical label from outside
        # the block's main column.
        gnd_symbol_position = Point(
            label_position.x,
            snap_to_grid(label_position.y + POWER_SYMBOL_OFFSET_MM),
        )
        builder.wires.append(PlacedWire(start=label_position, end=gnd_symbol_position))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:GND",
            reference=builder.next_ref("#PWR"),
            value="GND",
            position=gnd_symbol_position,
            footprint="",
            rotation=0.0,
        ))

        # PWR_FLAG on the same label so KiCad ERC sees GND driven.
        gnd_flag_position = Point(
            snap_to_grid(label_position.x + (-3.81 if ground_net.edge == SheetEdge.LEFT else 3.81)),
            label_position.y,
        )
        builder.wires.append(PlacedWire(
            start=label_position,
            end=gnd_flag_position,
        ))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value="GND",
            position=gnd_flag_position,
            footprint="",
            rotation=0.0,
        ))
