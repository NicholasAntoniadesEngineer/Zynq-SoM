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


CONNECTOR_EDGE_INSET_MM = snap_to_grid(81.28)
"""Distance from the sheet edge to a connector's column_x.

This must be large enough that a connector placed at the right edge
still leaves room for its cluster passive swarm AND the
``power:Earth`` / ``CHASSIS_GND`` symbol attached to the chassis pin
(whose body extends ~1.27 mm past the symbol's anchor). 76.2 mm left
0.37 mm of overflow on USB-C right-edge connectors; 81.28 mm
clears it with a margin."""
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
        # so dense connectors get more vertical room. The connector's
        # anchor is the symbol body's CENTROID, so for tall single-column
        # symbols (e.g. FFC_40P with 40 pins ≈ 100 mm tall) we have to
        # offset the anchor by half the symbol height -- otherwise the
        # top pins land off the top of the page.
        y_cursor = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
        for connector in connectors:
            symbol_half_height = _connector_symbol_half_height(
                connector, geometry_cache
            )
            anchor_y = snap_to_grid(y_cursor + symbol_half_height)
            anchor = Point(column_x, anchor_y)
            _place_one_connector(
                builder,
                connector=connector,
                anchor=anchor,
                geometry_cache=geometry_cache,
            )
            # Advance cursor past the placed symbol's full height + gap.
            y_cursor = snap_to_grid(anchor_y + symbol_half_height + 20.32)


def _connector_pin_count(
    connector: ConnectorInstance,
    geometry_cache: SymbolGeometryCache,
) -> int:
    try:
        return sum(1 for _ in geometry_cache.all_pins(connector.lib_id))
    except Exception:
        return 4


def _connector_symbol_half_height(
    connector: ConnectorInstance,
    geometry_cache: SymbolGeometryCache,
) -> float:
    """Return half the connector symbol's actual page-frame height.

    Uses the real bounding box (from the .kicad_sym pin coordinates,
    rotated by the symbol's placement rotation) instead of the previous
    pin-count heuristic. The heuristic assumed all pins on one side and
    doubled the height for two-column connectors like FX10A_168P /
    FMC_LPC, causing 168-pin SoM-mate symbols to overflow the page.
    """
    try:
        bbox = geometry_cache.bounding_box(
            connector.lib_id,
            rotation=connector.rotation,
        )
    except Exception:
        # Fall back to the pin-count heuristic for symbols whose
        # bounding box can't be resolved (e.g. unregistered libraries).
        pin_count = _connector_pin_count(connector, geometry_cache)
        return max(20.32, (pin_count * 2.54) / 2.0 + 2.54)
    return max(20.32, bbox.height / 2.0 + 2.54)


def _place_one_connector(
    builder: BlockLayoutBuilder,
    *,
    connector: ConnectorInstance,
    anchor: Point,
    geometry_cache: SymbolGeometryCache,
) -> None:
    from zynq_eda.core.layout.cluster import cluster_ic_externals

    builder.add_symbol(PlacedSymbol(
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
    ), geometry=geometry_cache)

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
        geometry_cache=geometry_cache,
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
    #
    # Stub direction MUST be ALONG the pin's natural extension direction
    # (continuing OUTWARD from the connector body), NOT perpendicular to
    # the pin row. Perpendicular stubs of length >= pin pitch (5.08 mm
    # is two USB-C pin pitches) span adjacent pin Y rows, creating a
    # vertical wire that connects every pin's stub into one giant short
    # — historically this shorted GND with USBOTG_DP, VBUS_OTG, EDID
    # I2C, HDMI TMDS pairs, and every other connector signal that
    # shared a column with a GND pin. The fix uses the pin's page-side
    # (derived from pin_rotation + symbol_rotation) to pick the OUTWARD
    # direction, so the stub always extends past the pin tip and
    # never crosses another pin's row.
    from zynq_eda.core.layout.geometry import page_side_from_pin

    # Build a pin_number → pin_name map so we can correlate
    # ``pin_to_net`` entries (keyed by pin NUMBER in the connector's
    # decl) with the cluster's ``pin_geoms`` dict (keyed by pin NAME).
    _number_to_name: dict[str, str] = {}
    try:
        for pi in geometry_cache.all_pins(connector.lib_id, rotation=connector.rotation):
            _number_to_name[str(pi["number"])] = str(pi["name"])
    except Exception:
        pass

    for pin_id, net_name in connector.pin_to_net:
        pin_geom = _resolve_pin(pin_id)
        if pin_geom is None:
            continue

        side = page_side_from_pin(
            pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
            symbol_rotation=getattr(pin_geom, "symbol_rotation", connector.rotation),
        )
        # Label rotation places the TEXT extending outward (away from
        # the body) so it never crosses the body or the intrinsic
        # pin name text inside the body.
        if side == "left":
            label_rotation = 180.0  # text reads leftward (away from body)
        elif side == "right":
            label_rotation = 0.0    # text reads rightward (away from body)
        elif side == "top":
            label_rotation = 90.0   # text reads upward (away from body)
        else:  # bottom
            label_rotation = 270.0  # text reads downward (away from body)

        # If this connector pin has a CLUSTER cap on it (pin_geoms is
        # the per-pin geometry map returned by ``cluster_ic_externals``),
        # the cluster has already emitted a trunk wire from the pin tip
        # outward to the cap. Placing the label at the pin tip would
        # put the label text on top of the trunk wire's centerline,
        # violating the project's no-overlap rule. Instead, anchor the
        # label at the cluster trunk's OUTWARD ENDPOINT — the text
        # then extends past the trunk into open space.
        #
        # ``pin_geoms`` is keyed by pin NAME (from refcircuit
        # external_parts.from_pin), while ``pin_to_net`` is keyed by
        # pin NUMBER. Look up by number → name first; fall back to
        # the pin_id verbatim in case the refcircuit used names too.
        _resolved_name = _number_to_name.get(str(pin_id), str(pin_id))
        cluster_pg = pin_geoms.get(_resolved_name) or pin_geoms.get(str(pin_id))
        if cluster_pg is not None and cluster_pg.cluster_trunk_end is not None:
            label_position = cluster_pg.cluster_trunk_end
        else:
            label_position = pin_geom.connection

        # Dedup: USB-C-style connectors expose multiple physical pads
        # for the same net (4×VBUS, 4×GND) collapsed into a few
        # symbol pins. With the trunk-end label anchor, two of those
        # pins can resolve to the EXACT same label position — often
        # one from a LEFT-side pin (rot=180) and one from a RIGHT-side
        # pin (rot=0) that happen to converge at the connector's body
        # midline. Skip duplicates by (net, position) regardless of
        # rotation — KiCad merges labels by name, so one label suffices
        # for net identification.
        _label_key = (
            net_name,
            round(label_position.x, 3),
            round(label_position.y, 3),
        )
        _existing_keys = {
            (
                lbl.net_name,
                round(lbl.position.x, 3),
                round(lbl.position.y, 3),
            )
            for lbl in builder.labels
        }
        if _label_key in _existing_keys:
            continue

        builder.add_label(PlacedLabel(
            net_name=net_name,
            position=label_position,
            rotation=label_rotation,
        ))
