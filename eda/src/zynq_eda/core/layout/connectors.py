"""Connector placement: instances of mechanical connectors on a sheet.

Connectors differ from ICs in three ways:

  1. They sit on a sheet edge (USB-C on the right, FMC on the left, etc.)
     rather than in the IC column.
  2. Their pin-to-net mapping is data, not derived from a refcircuit's
     ``external_parts``. The carrier project supplies a ``pin_to_net``
     tuple on each :class:`ConnectorInstance`.
  3. They may have datasheet-required passives clustered around them
     (USB-C CC resistors, EDID EEPROM bypass) — those passives are
     materialised through the same cluster algorithm used for ICs.
"""

from __future__ import annotations

from zynq_eda.core.layout._builder import BlockLayoutBuilder, PinGeometryAbs
from zynq_eda.core.layout._constants import (
    INTERIOR_MARGIN_MM,
    POWER_SYMBOL_LIB_IDS,
    POWER_SYMBOL_OFFSET_MM,
)
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.block import Block, ConnectorInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.interface import SheetEdge
from zynq_eda.core.model.sheet import (
    PAPER_DIMENSIONS_MM,
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedSymbol,
    PlacedWire,
)


CONNECTOR_EDGE_INSET_MM = snap_to_grid(60.96)
"""Distance from a sheet edge to a connector's anchor.

Wide enough that two or three rows of passive stacks alongside the
connector's "off-edge" side (where ``pin_side`` says ``right`` for a
right-edge connector) still land inside the A4 right margin.
"""


def place_connectors(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    geometry_cache: SymbolGeometryCache,
    ic_anchors: dict[str, Point],
) -> None:
    """Place each :class:`ConnectorInstance` and wire its pins to declared nets.

    Connectors are arranged in a vertical column on their declared edge,
    spaced enough that their pin swarms don't overlap. Each pin listed in
    ``pin_to_net`` is wired to the corresponding net via a local label
    (or a power symbol when the net is a power rail).
    """
    if not block.connectors:
        return

    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]

    by_edge: dict[SheetEdge, list[ConnectorInstance]] = {
        SheetEdge.LEFT: [],
        SheetEdge.RIGHT: [],
    }
    for connector in block.connectors:
        if connector.edge in by_edge:
            by_edge[connector.edge].append(connector)

    for edge, connectors in by_edge.items():
        if not connectors:
            continue
        column_x = (
            snap_to_grid(CONNECTOR_EDGE_INSET_MM)
            if edge == SheetEdge.LEFT
            else snap_to_grid(paper_w - CONNECTOR_EDGE_INSET_MM)
        )
        # Place connectors vertically; first connector near the top, then
        # stack downward. Y spacing scales with the connector's pin count
        # so dense connectors get more vertical room.
        y_cursor = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
        for connector in connectors:
            anchor = Point(column_x, y_cursor)
            _place_one_connector(
                builder,
                connector=connector,
                anchor=anchor,
                geometry_cache=geometry_cache,
            )
            pin_count = _connector_pin_count(connector, geometry_cache)
            y_cursor = snap_to_grid(y_cursor + max(40.64, pin_count * 2.54 + 20.32))


def _connector_pin_count(
    connector: ConnectorInstance,
    geometry_cache: SymbolGeometryCache,
) -> int:
    try:
        return sum(1 for _ in geometry_cache.all_pins(connector.lib_id))
    except Exception:
        return 4


def _place_one_connector(
    builder: BlockLayoutBuilder,
    *,
    connector: ConnectorInstance,
    anchor: Point,
    geometry_cache: SymbolGeometryCache,
) -> None:
    from zynq_eda.core.layout.cluster import cluster_ic_externals

    builder.symbols.append(PlacedSymbol(
        lib_id=connector.lib_id,
        reference=connector.reference,
        value=connector.refcircuit.part_mpn,
        position=anchor,
        footprint=connector.refcircuit.footprint,
        rotation=connector.rotation,
        properties=(
            ("LCSC", connector.refcircuit.lcsc),
            ("Datasheet", connector.refcircuit.datasheet_url),
        ),
    ))

    # 1. Materialise the connector's datasheet-required passives (VBUS bulk
    #    caps, shield discharge resistor, sink Rd, etc.) via the same
    #    cluster algorithm used for ICs.
    def _resolve_pin(pin_name: str):
        try:
            return geometry_cache.pin_geometry_by_name(
                connector.lib_id,
                anchor,
                pin_name,
                rotation=connector.rotation,
            )
        except KeyError:
            return None

    placed_pin_names: set[str] = set()
    pin_geoms = cluster_ic_externals(
        builder,
        ic=connector,
        pin_geom_resolver=_resolve_pin,
    )
    placed_pin_names.update(pin_geoms.keys())

    # 2. Mark unused pins (from refcircuit's no_external_required) and
    #    any pins not in pin_to_net as no-connect, so ERC stops complaining
    #    about floating connector pins (SBU1/SBU2 on USB 2.0-only links,
    #    USB 3.0 SS lanes, etc.).
    from zynq_eda.core.model.sheet import PlacedNoConnect

    declared_pins = set(placed_pin_names) | {pin for pin, _ in connector.pin_to_net}
    no_external = set(connector.refcircuit.no_external_required)
    for pin_info in geometry_cache.all_pins(connector.lib_id, rotation=connector.rotation):
        pin_name = str(pin_info["name"])
        pin_number = str(pin_info["number"])
        if pin_name in declared_pins or pin_number in declared_pins:
            continue
        if pin_name not in no_external:
            continue
        try:
            pin_geom = geometry_cache.pin_geometry_by_name(
                connector.lib_id,
                anchor,
                pin_number,
                rotation=connector.rotation,
            )
        except KeyError:
            continue
        builder.no_connects.append(PlacedNoConnect(position=pin_geom.connection))

    # 2b. Auto-NC EVERY remaining pin that no other pass touched. Mirrors
    # the IC-pin auto-NC in :func:`place._add_no_connects_for_unused_pins`.
    # Connectors expose declarative pin maps via :attr:`pin_to_net` (and
    # external_parts may add a few more via the cluster pass above);
    # anything left over is a pin the project chose not to use, so ERC's
    # ``pin_not_connected`` complaint would otherwise fire. Examples we
    # need to silence: SoM-mate connector GND/SHIELD power pins (treated as
    # ground references but not in pin_to_net), USB-B-micro shield pins,
    # tactile-switch second-pin (paired-pin device whose other pin shares
    # the same net via the symbol's internal short).
    claimed_pin_names: set[str] = set(placed_pin_names) | {
        pin for pin, _ in connector.pin_to_net
    }
    for pin_info in geometry_cache.all_pins(connector.lib_id, rotation=connector.rotation):
        pin_name = str(pin_info["name"])
        pin_number = str(pin_info["number"])
        if pin_name in claimed_pin_names or pin_number in claimed_pin_names:
            continue
        try:
            pin_geom = geometry_cache.pin_geometry_by_name(
                connector.lib_id,
                anchor,
                pin_number,
                rotation=connector.rotation,
            )
        except KeyError:
            continue
        builder.no_connects.append(PlacedNoConnect(position=pin_geom.connection))

    # 3. Wire each pin in ``pin_to_net`` to its declared net.
    #
    # We use *lateral* local-label stubs only — NEVER inline power symbols.
    # Connector pins are densely packed (USB-C has ~16 pins on 2.54 mm
    # pitch); a power symbol placed offset-Y from one pin would land on an
    # adjacent pin and short the two nets. A lateral stub + same-name local
    # label is safe: KiCad merges same-name labels across the sheet via
    # power symbols elsewhere (the cluster's cap-to-GND symbol satisfies
    # the GND driver requirement; PWR_FLAGs on input nets handle the rest).
    for pin_id, net_name in connector.pin_to_net:
        pin_geom = _resolve_pin(pin_id)
        if pin_geom is None:
            continue

        # Stub extends INTO the page from the pin (away from the
        # connector body) so labels don't overlap the body.
        # Choose direction from the pin's page-relative position vs the
        # connector anchor.
        page_dx = pin_geom.connection.x - anchor.x
        page_dy = pin_geom.connection.y - anchor.y
        if abs(page_dx) >= abs(page_dy):
            stub_end = Point(
                snap_to_grid(pin_geom.connection.x + (5.08 if page_dx > 0 else -5.08)),
                pin_geom.connection.y,
            )
        else:
            stub_end = Point(
                pin_geom.connection.x,
                snap_to_grid(pin_geom.connection.y + (5.08 if page_dy > 0 else -5.08)),
            )

        builder.wires.append(PlacedWire(
            start=pin_geom.connection,
            end=stub_end,
        ))
        builder.labels.append(PlacedLabel(
            net_name=net_name,
            position=stub_end,
            rotation=0.0,
        ))
