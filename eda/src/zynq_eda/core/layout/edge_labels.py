"""Stage E — the electrical contract: no-connects on every unused pin.

After Stages A–D every sheet is visually clean (overlap=0), but KiCad ERC fires
``pin_not_connected`` on every pin that carries no net and no marker. A spare pin
on a 168-position SoM mezzanine connector, or an unused IC pin, is intentional —
it must be marked with an explicit No-Connect flag, exactly as a human would.

:func:`no_connect_markers` returns a :class:`PlacedNoConnect` for every pin that
is NOT otherwise connected:
  * a connector pin whose id is absent from ``pin_to_net`` (genuinely spare), and
  * an IC pin the planner classifies ``role="NC"`` (no mapping at all).

It reuses the proven classifier :func:`zynq_eda.core.layout.plan.plan_pin_specs`
for IC pins (so the NC set matches the legacy planner exactly), and resolves
connector spares directly from symbol geometry. Pins that DO carry a net are
left for the labeler / module wiring — never double-marked.
"""

from __future__ import annotations

from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS, VISUAL_CLEARANCE_MM
from zynq_eda.core.layout.bbox import BBox, symbol_bbox, text_bbox, wire_bbox
from zynq_eda.core.layout.cluster import _outward_power_symbol_rotation
from zynq_eda.core.layout.geometry import SymbolGeometryCache, page_side_from_pin
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedNoConnect,
    PlacedSymbol,
    PlacedWire,
)

# Outboard unit step per page side (page +Y down).
_OUT = {"left": (-1.0, 0.0), "right": (1.0, 0.0), "top": (0.0, -1.0), "bottom": (0.0, 1.0)}


def no_connect_markers(
    block: Block,
    connectors: list[tuple],
    geometry: SymbolGeometryCache,
    ic_symbols: dict[str, PlacedSymbol] | None = None,
) -> list[PlacedNoConnect]:
    """Return a No-Connect marker for every unused connector / IC pin.

    ``connectors`` is the list of ``(ConnectorInstance, PlacedSymbol)`` pairs as
    placed by Stage B (so the markers land at the connector's final position).
    ``ic_symbols`` maps each IC reference to its placed symbol (from the frozen
    modules) so NC IC pins resolve to their final page position.
    """
    ic_symbols = ic_symbols or {}
    markers: dict[tuple[float, float], PlacedNoConnect] = {}

    # ---- Connector spares: any pin id not in pin_to_net ---------------------
    for inst, sym in connectors:
        mapped: set[str] = set()
        for pin_id, _net in inst.pin_to_net:
            mapped.add(pin_id)
        for pin in geometry.all_pins(inst.lib_id, inst.rotation):
            number = str(pin.get("number", ""))
            name = str(pin.get("name", ""))
            if number in mapped or name in mapped:
                continue  # carries a net → labeler handles it
            pos = _abs_pin(sym, number or name, geometry)
            if pos is not None:
                markers[(round(pos.x, 3), round(pos.y, 3))] = PlacedNoConnect(position=pos)

    # ---- IC NC pins: reuse the planner's classifier -------------------------
    # plan_pin_specs classifies every IC/connector pin into one role; role="NC"
    # is exactly a pin with no net mapping at all. Resolve each to its absolute
    # position via the IC's placed symbol.
    try:
        from zynq_eda.core.layout.plan import plan_pin_specs
        specs = plan_pin_specs(block, geometry)
    except Exception:
        specs = []
    for spec in specs:
        if spec.role != "NC":
            continue
        if spec.owner_kind == "connector":
            continue  # handled above from geometry (covers spare pads too)
        sym = ic_symbols.get(spec.owner_ref)
        if sym is None:
            continue
        pos = _abs_pin(sym, spec.pin_number or spec.pin_name, geometry)
        if pos is not None:
            markers[(round(pos.x, 3), round(pos.y, 3))] = PlacedNoConnect(position=pos)

    return list(markers.values())


def _abs_pin(sym: PlacedSymbol, pin_id: str, geometry: SymbolGeometryCache) -> Point | None:
    try:
        return geometry.absolute_pin_by_name(sym.lib_id, sym.position, pin_id, sym.rotation)
    except Exception:
        return None


def _pin_rotation(sym: PlacedSymbol, spec, geometry: SymbolGeometryCache) -> float:
    """The pin's library rotation (tip→body direction) for page-side lookup."""
    from zynq_eda.core.layout.geometry import _pin_rotation_from_symbol
    try:
        return _pin_rotation_from_symbol(sym.lib_id, spec.pin_number or spec.pin_name)
    except Exception:
        return 0.0


def _body_center(sym: PlacedSymbol, geometry: SymbolGeometryCache) -> tuple[float, float]:
    try:
        bb = symbol_bbox(sym.lib_id, sym.position, sym.rotation, geometry, "c")
        return (bb.center.x, bb.center.y)
    except Exception:
        return (sym.position.x, sym.position.y)


def expose_ic_pin_nets(
    block: Block,
    ic_symbols: dict[str, PlacedSymbol],
    geometry: SymbolGeometryCache,
    occupied: list[BBox],
    already_connected: set[tuple[float, float]],
):
    """Attach a net-bearing primitive to every IC pin that still floats.

    For each IC pin that carries a net but has no wire/NC at its tip:
      * power/GND net  → a power symbol (power:GND / power:+3V3 / …) on a stub,
      * EDGE_LABEL net → a hierarchical label on a stub (sheet-edge contract),
      * everything else → a local label on a stub.

    Each primitive is placed OUTBOARD of the pin and walked out grid-by-grid
    until its bbox clears ``occupied`` (the same validator-true bboxes), so the
    sheet stays overlap-clean. Returns (symbols, labels, hlabels, wires); the
    caller appends them and extends ``occupied`` itself.
    """
    from zynq_eda.core.layout.plan import plan_pin_specs

    ext_dir = {n.name: n.direction for n in block.external_nets}
    try:
        specs = plan_pin_specs(block, geometry)
    except Exception:
        return [], [], [], []

    out_syms: list[PlacedSymbol] = []
    out_labels: list[PlacedLabel] = []
    out_hlabels: list[PlacedHierarchicalLabel] = []
    out_wires: list[PlacedWire] = []
    pwr_ref = 700

    for spec in specs:
        if spec.owner_kind != "ic":
            continue
        net = spec.net_name or spec.cluster_owner_net
        if not net:
            continue
        sym = ic_symbols.get(spec.owner_ref)
        if sym is None:
            continue
        tip = _abs_pin(sym, spec.pin_number or spec.pin_name, geometry)
        if tip is None:
            continue
        key = (round(tip.x, 2), round(tip.y, 2))
        if key in already_connected:
            continue

        # Outboard side = the body edge this pin sits on, from its TRUE page
        # side (pin rotation + symbol rotation), not the anchor (which is not the
        # body centroid). This sends a right-edge pin's stub OUT to the right
        # rather than down across the pin below it.
        side = page_side_from_pin(_pin_rotation(sym, spec, geometry), sym.rotation)
        if side not in _OUT:
            # Fallback: away from the real body centre.
            cx, cy = _body_center(sym, geometry)
            if abs(tip.x - cx) >= abs(tip.y - cy):
                side = "right" if tip.x >= cx else "left"
            else:
                side = "bottom" if tip.y >= cy else "top"
        ux, uy = _OUT[side]

        lib = POWER_SYMBOL_LIB_IDS.get(net)
        placed = _place_ic_pin_primitive(
            net, tip, side, ux, uy, lib, ext_dir, sym, geometry, occupied,
            f"#PWR{pwr_ref}",
        )
        if placed is None:
            continue
        prim, bb, stub = placed
        occupied.append(bb)
        if stub is not None:
            out_wires.append(stub)
            occupied.append(wire_bbox(stub.start, stub.end, owner_id="ic_stub"))
        already_connected.add(key)
        if isinstance(prim, PlacedSymbol):
            out_syms.append(prim); pwr_ref += 1
        elif isinstance(prim, PlacedHierarchicalLabel):
            out_hlabels.append(prim)
        else:
            out_labels.append(prim)

    return out_syms, out_labels, out_hlabels, out_wires


def _place_ic_pin_primitive(
    net, tip, side, ux, uy, lib, ext_dir, ic_sym, geometry, occupied, pwr_ref,
):
    """Walk a primitive outboard from ``tip`` until it clears ``occupied``.

    The stub leaving the pin legitimately abuts the OWNING IC's body + its
    intrinsic pin-name/number text (a wire connects to that pin), so obstacles
    owned by ``ic_sym`` are ignored for the stub's clearance test — they are
    not real overlaps. The placed label/symbol bbox still clears everything."""
    is_ext = net in ext_dir
    own_oid = f"symbol:{ic_sym.reference}"
    rot_label = {"left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0}[side]
    # Stub-exempt ONLY the owning IC's obstacles whose box is within one pin
    # pitch of THIS pin tip — i.e. this pin's own body edge + its own name/number
    # text. A sibling pin's text two rows away stays an obstacle, so the stub
    # never crosses another pin's label.
    PIN_NEAR = 2.0 * VISUAL_CLEARANCE_MM

    def _stub_exempt(o) -> bool:
        if not o.owner_id.startswith(own_oid):
            return False
        return (
            o.min.x - PIN_NEAR <= tip.x <= o.max.x + PIN_NEAR
            and o.min.y - PIN_NEAR <= tip.y <= o.max.y + PIN_NEAR
        )

    def _clear(probe_box, *, is_stub):
        for o in occupied:
            if is_stub and _stub_exempt(o):
                continue  # stub may touch ITS OWN pin's body/text
            if probe_box.intersects(o, padding_mm=VISUAL_CLEARANCE_MM):
                return False
        return True

    for extra in range(1, 14):
        dist = snap_to_grid(extra * VISUAL_CLEARANCE_MM)
        anchor = Point(snap_to_grid(tip.x + ux * dist), snap_to_grid(tip.y + uy * dist))
        stub = None if anchor == tip else PlacedWire(tip, anchor)
        if lib is not None:
            rotation = _outward_power_symbol_rotation(
                lib_id=lib, pin_side=side, geometry_cache=geometry,
            )
            rel = geometry.absolute_pin_positions(lib, Point(0.0, 0.0), rotation)
            pin_rel = next(iter(rel.values())) if rel else Point(0.0, 0.0)
            sym_anchor = Point(snap_to_grid(anchor.x - pin_rel.x), snap_to_grid(anchor.y - pin_rel.y))
            prim = PlacedSymbol(lib_id=lib, reference=pwr_ref, value=net,
                                position=sym_anchor, footprint="", rotation=rotation)
            try:
                # Full footprint (body + Value text) so the power symbol's own
                # rail-name text is cleared too, not just its body.
                from zynq_eda.core.layout.footprint import symbol_footprint
                bb = symbol_footprint(prim, geometry)
            except Exception:
                continue
        elif is_ext:
            prim = PlacedHierarchicalLabel(
                net_name=net, position=anchor, direction=ext_dir[net], rotation=rot_label,
            )
            bb = _hlabel_bb(prim)
        else:
            prim = PlacedLabel(net_name=net, position=anchor, rotation=rot_label)
            bb = _label_bb(prim)
        stub_box = wire_bbox(stub.start, stub.end, owner_id="s") if stub else None
        if _clear(bb, is_stub=False) and (stub_box is None or _clear(stub_box, is_stub=True)):
            return prim, bb, stub
    return None


def _hlabel_bb(h: PlacedHierarchicalLabel) -> BBox:
    # Use the VALIDATOR's own bbox so placement-clean == validator-clean (the
    # keystone): the validator measures hier-labels via this exact function.
    from zynq_eda.core.validate.overlap import _hierarchical_label_text_bbox
    return _hierarchical_label_text_bbox(h)


def _label_bb(l: PlacedLabel) -> BBox:
    from zynq_eda.core.validate.overlap import _label_text_bbox
    return _label_text_bbox(l)
