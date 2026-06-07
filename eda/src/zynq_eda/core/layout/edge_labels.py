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
        # NC = the planner's NC role OR any IC pin with NO net at all (e.g. the
        # FUSB302 VCONN_1/VCONN_2 — unused by design). Such a pin is wired by
        # nothing, so an explicit No-Connect is the correct mark; leaving it bare
        # is a false ERC pin_not_connected (a floating pin that is NOT a defect).
        no_net = not (spec.net_name or spec.cluster_owner_net)
        if spec.role != "NC" and not no_net:
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


def _body_up_rotation(lib: str, geometry: SymbolGeometryCache) -> float:
    """Rotation (0 or 180) that puts the symbol's body ABOVE its pin."""
    for rot in (0.0, 180.0):
        try:
            bb = geometry.bounding_box(lib, rotation=rot)
            rel = geometry.absolute_pin_positions(lib, Point(0.0, 0.0), rot)
            pin_y = next(iter(rel.values())).y if rel else 0.0
        except Exception:
            return 0.0
        if (bb.min_y + bb.max_y) / 2.0 < pin_y:  # body above pin (smaller y)
            return rot
    return 0.0


def _body_down_rotation(lib: str, geometry: SymbolGeometryCache) -> float:
    """Rotation (0 or 180) that puts the symbol's body BELOW its pin."""
    up = _body_up_rotation(lib, geometry)
    return 180.0 if up == 0.0 else 0.0


def power_drive_stamps(
    nets,
    paper_size: str,
    geometry: SymbolGeometryCache,
    occupied: list[BBox],
    flg_start: int = 800,
):
    """Emit one ``power:PWR_FLAG`` drive stamp per power ``net`` in clear space.

    A power symbol (power:GND / power:+3V3 / …) is power-INPUT; KiCad ERC fires
    ``power_pin_not_driven`` unless at least one PWR_FLAG marks the (global) net
    as externally driven. Each stamp is a PWR_FLAG joined to the rail's power
    symbol by a short wire, scanned into the first clear interior spot so it
    never overlaps anything (if no spot, the stamp is skipped → ERC surfaces a
    page-room problem rather than a silent overlap). Returns (symbols, wires).
    Caller is responsible for emitting each net only ONCE across the project
    (global nets: one flag drives the whole net)."""
    from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM, KICAD_GRID_MM
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM

    paper_w, paper_h = PAPER_DIMENSIONS_MM[paper_size]
    WIRE_LEN = 2 * KICAD_GRID_MM
    step = 4 * KICAD_GRID_MM
    out_syms: list[PlacedSymbol] = []
    out_wires: list[PlacedWire] = []
    flg = flg_start
    pwr = flg_start

    for net in nets:
        lib = POWER_SYMBOL_LIB_IDS.get(net)
        if lib is None:
            continue
        chosen = _scan_clear_stamp(
            net, lib, None, None, WIRE_LEN, step,
            paper_w, paper_h, INTERIOR_MARGIN_MM, geometry, occupied, flg, pwr,
        )
        if chosen is None:
            continue
        rail_sym, flag_sym, wire, boxes = chosen
        out_syms.append(rail_sym); out_syms.append(flag_sym)
        out_wires.append(wire)
        occupied.extend(boxes)
        flg += 1; pwr += 1
    return out_syms, out_wires


def _scan_clear_stamp(
    net, lib, rail_pin, flag_pin, wire_len, step,
    paper_w, paper_h, margin, geometry, occupied, flg, pwr,
):
    """Scan the page interior for a clear spot to drop a (rail + PWR_FLAG)
    stamp. Returns (rail_sym, flag_sym, wire, [bboxes]) or None.

    Geometry: the two pins meet on a short vertical wire; each symbol is rotated
    so its BODY points AWAY from the wire (rail body up via rotation 0/180 to
    keep its body above its pin; PWR_FLAG rotated 180 so its body points DOWN).
    This keeps the connecting wire out of both bodies (the wire-through-body
    overlap)."""
    # Rail at TOP with body UP (away from the wire going down); PWR_FLAG at
    # BOTTOM with body DOWN (away from the wire going up). Pick each rotation so
    # the body sits on the far side of the pin from the wire.
    rail_rot = _body_up_rotation(lib, geometry)        # body above its pin
    flag_rot = _body_down_rotation("power:PWR_FLAG", geometry)  # body below its pin
    try:
        rr = geometry.absolute_pin_positions(lib, Point(0.0, 0.0), rail_rot)
        rp = next(iter(rr.values())) if rr else Point(0.0, 0.0)
        fr = geometry.absolute_pin_positions("power:PWR_FLAG", Point(0.0, 0.0), flag_rot)
        fp = next(iter(fr.values())) if fr else Point(0.0, 0.0)
    except Exception:
        return None
    y = snap_to_grid(margin + wire_len + step)
    while y < paper_h - margin:
        x = snap_to_grid(margin + step)
        while x < paper_w - margin:
            rail_tip = Point(x, snap_to_grid(y - wire_len))  # top of wire
            flag_tip = Point(x, y)                            # bottom of wire
            rail_anchor = Point(snap_to_grid(rail_tip.x - rp.x), snap_to_grid(rail_tip.y - rp.y))
            flag_anchor = Point(snap_to_grid(flag_tip.x - fp.x), snap_to_grid(flag_tip.y - fp.y))
            try:
                rb = symbol_bbox(lib, rail_anchor, rail_rot, geometry, f"stamp:{net}")
                fb = symbol_bbox("power:PWR_FLAG", flag_anchor, flag_rot, geometry, "stamp:flag")
            except Exception:
                x = snap_to_grid(x + step); continue
            wb = wire_bbox(rail_tip, flag_tip, owner_id="stamp:wire")
            boxes = [rb, fb, wb]
            if all(
                margin <= bb.min.x and bb.max.x <= paper_w - margin
                and margin <= bb.min.y and bb.max.y <= paper_h - margin
                and all(not bb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM) for o in occupied)
                for bb in boxes
            ):
                rail_sym = PlacedSymbol(lib_id=lib, reference=f"#PWR{pwr}", value=net,
                                        position=rail_anchor, footprint="", rotation=rail_rot)
                flag_sym = PlacedSymbol(lib_id="power:PWR_FLAG", reference=f"#FLG{flg}",
                                        value=net, position=flag_anchor, footprint="",
                                        rotation=flag_rot)
                return rail_sym, flag_sym, PlacedWire(rail_tip, flag_tip), boxes
            x = snap_to_grid(x + step)
        y = snap_to_grid(y + step)
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
        prim, bb, stubs = placed
        occupied.append(bb)
        for stub in stubs:
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

    # Match the OVERLAP VALIDATOR's per-kind tolerance (the keystone: placement-
    # clean == validator-clean). The validator measures wire×label / wire×symbol
    # as TRUE overlap (a wire legitimately abuts the label/pin it connects to),
    # NOT the 2.54 mm crowding clearance it applies to body/text/label pairs.
    # Checking a label against a parallel wire at 2.54 mm is therefore strictly
    # OVER-strict — it rejects placements the validator (and a human) accept,
    # which is exactly what stranded the dense signal-pin labels (CP2102N
    # RXD/TXD/RTS, FUSB302 CC) one row from a neighbouring trunk wire. Use the
    # validator's own significant-overlap test for wires; keep the breathing-room
    # clearance for everything visible (bodies, text, other labels).
    from zynq_eda.core.validate.overlap import _overlap_is_significant

    def _clear(probe_box, *, is_stub):
        for o in occupied:
            if is_stub and _stub_exempt(o):
                continue  # stub may touch ITS OWN pin's body/text
            if o.kind == "wire":
                if _overlap_is_significant(probe_box, o):
                    return False
                continue
            if probe_box.intersects(o, padding_mm=VISUAL_CLEARANCE_MM):
                return False
        return True

    def _make(anchor: Point):
        """Build the net-bearing primitive + its validator-true bbox at anchor."""
        if lib is not None:
            rotation = _outward_power_symbol_rotation(
                lib_id=lib, pin_side=side, geometry_cache=geometry,
            )
            rel = geometry.absolute_pin_positions(lib, Point(0.0, 0.0), rotation)
            pin_rel = next(iter(rel.values())) if rel else Point(0.0, 0.0)
            sym_anchor = Point(snap_to_grid(anchor.x - pin_rel.x),
                               snap_to_grid(anchor.y - pin_rel.y))
            prim = PlacedSymbol(lib_id=lib, reference=pwr_ref, value=net,
                                position=sym_anchor, footprint="", rotation=rotation)
            try:
                from zynq_eda.core.layout.footprint import symbol_footprint
                return prim, symbol_footprint(prim, geometry)
            except Exception:  # noqa: BLE001
                return None, None
        if is_ext:
            prim = PlacedHierarchicalLabel(
                net_name=net, position=anchor, direction=ext_dir[net], rotation=rot_label,
            )
            return prim, _hlabel_bb(prim)
        prim = PlacedLabel(net_name=net, position=anchor, rotation=rot_label)
        return prim, _label_bb(prim)

    px, py = -uy, ux  # perpendicular unit

    def _try(extra: int, poff: int):
        dist = snap_to_grid(extra * VISUAL_CLEARANCE_MM)
        elbow = Point(snap_to_grid(tip.x + ux * dist), snap_to_grid(tip.y + uy * dist))
        pd = snap_to_grid(poff * VISUAL_CLEARANCE_MM)
        anchor = Point(snap_to_grid(elbow.x + px * pd), snap_to_grid(elbow.y + py * pd))
        prim, bb = _make(anchor)
        if prim is None:
            return None
        stubs: list[PlacedWire] = []
        if elbow != tip:
            stubs.append(PlacedWire(tip, elbow))
        if anchor != elbow:
            stubs.append(PlacedWire(elbow, anchor))
        stub_boxes = [wire_bbox(s.start, s.end, owner_id="s") for s in stubs]
        if _clear(bb, is_stub=False) and all(
            _clear(sb, is_stub=True) for sb in stub_boxes
        ):
            return prim, bb, stubs
        return None

    # Pass 1a — STRAIGHT-OUT STAGGER (poff=0, all distances FIRST): keep the
    # label on the pin's OWN row and walk it outboard until its text clears any
    # neighbour label. This is the hand-drawn convention for a dense pin column
    # (CP2102N RXD/TXD/RTS at 2.54 mm pitch): adjacent labels can't coexist on
    # the SAME outboard distance (their 2.54 mm clearance overlaps), so they
    # STAGGER to different distances — never piling onto a neighbour's pin row
    # (which the old extra-outer/poff-inner order did, colliding with that pin's
    # own label). extra=0 is COINCIDENT (label pin on the IC pin), tightest first.
    for extra in range(0, 22):
        got = _try(extra, 0)
        if got is not None:
            return got
    # Pass 1b — PERPENDICULAR lane interleave: only when no straight-out stagger
    # fits (the row is genuinely walled by a body/text), fan into neighbour lanes.
    for extra in range(0, 16):
        for poff in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
            got = _try(extra, poff)
            if got is not None:
                return got

    # Pass 2 — STRATEGY A: SCOPED 2D-RING ESCAPE. The straight/L stub is walled
    # by the module's own passives + a FOREIGN net's trunk wrapping this pin (the
    # "boxed" pin). Sweep a BOUNDED ring of clear label slots (nearest first) and,
    # for the first one to which the grid tree router can lay a CLEAN multi-bend
    # stub around the obstacles, take it. "Clean" is the FULL validator contract,
    # not just crossing-free: every routed segment must (a) clear all non-wire
    # obstacles + the NEW label's own text box at VISUAL_CLEARANCE_MM (a routed
    # wire must not run under foreign text — the bug that put a stub through the
    # usbc EN label), (b) never significant-overlap a foreign wire, and (c) never
    # perpendicular-cross any wire. The router itself only avoids the static
    # bitmap, so we RE-VALIDATE its output here against the same boxes the overlap
    # validator uses → placement-clean == validator-clean (the keystone).
    #
    # This is the EXPENSIVE path, so it is reached ONLY for the handful of pins
    # the cheap straight/L stagger (Pass 1a/1b) could not seat. PERF: the
    # obstacle grid is rasterised ONCE here (EscapeRouter), then reused for every
    # ring probe — vs the old route_terminals-per-anchor which re-rasterised the
    # whole sheet ~200×/pin and blew the build past the time budget. We early-out
    # on the first clean slot and bound the ring radius to keep the per-sheet
    # build ~<60s.
    #
    # Handles BOTH labels and power symbols. _make builds the power symbol with
    # its pin AT the anchor and body pointing OUTBOARD, so the routed stub (which
    # docks at the anchor from the inboard side) never crosses the body — and the
    # body-crossing guard below re-checks it anyway (the gate measures every
    # routed segment against the placed primitive's own bbox).
    from zynq_eda.core.route.grid import EscapeRouter
    try:
        router = EscapeRouter(occupied, tip, (ux, uy))
    except Exception:  # noqa: BLE001
        return None
    # For a power symbol the "outboard / text" direction is the body direction
    # (body sits on the +outboard side of the pin); for a label it is the text
    # direction. Either way the docking segment must arrive from the NON-body /
    # NON-text side, and no other segment may run through the placed primitive's
    # bbox. (ux,uy) already points outboard, so it serves both.

    def _route_seg_clean(seg: PlacedWire, anchor: Point, prim_bb: BBox) -> bool:
        """True iff a routed segment is VALIDATOR-clean — measured by the SAME
        rule validate_overlap applies to a wire, not the crowding clearance.

        A wire legitimately runs right up to a body/pin/label edge (KiCad
        convention), so the validator flags wire×anything only at SIGNIFICANT
        (true, clearance-0) overlap — never at the 2.54 mm crowding clearance it
        uses between two text/body objects. Checking a routed wire at 2.54 mm is
        strictly over-strict (it rejected the hdmi SCL stub running 1.9 mm below
        a parallel SDA label, which the validator and a human accept). So:
          * wire × any obstacle  → significant overlap only,
          * wire × wire          → also reject a perpendicular crossing,
          * own-pin body/text     → exempt (the wire connects to that pin),
          * the NEW primitive bbox (label text / power-symbol body) → the docking
            segment (endpoint == anchor, arriving from the NON-outboard side) may
            touch it; any OTHER segment running THROUGH it is a wire-over-label /
            wire-through-body overlap → reject.
        """
        sb = wire_bbox(seg.start, seg.end, owner_id="s")
        for o in occupied:
            if _stub_exempt(o):
                continue
            # A wire must NEVER perpendicular-cross another wire (LAW 1: no
            # crossing, ever — not even "resolved" by a junction).
            if o.kind == "wire" and _seg_crosses_wire(seg, o):
                return False
            # Any SIGNIFICANT overlap with a foreign obstacle (wire body-stack,
            # symbol body, pin/value text, or another label) is a real overlap
            # the validator flags — measured at the wire's true-overlap rule.
            if _overlap_is_significant(sb, o):
                return False
        # The new primitive's own bbox: docking segment may touch from the
        # non-outboard side; any through-bbox run is rejected.
        at_s = abs(seg.start.x - anchor.x) < 1e-6 and abs(seg.start.y - anchor.y) < 1e-6
        at_e = abs(seg.end.x - anchor.x) < 1e-6 and abs(seg.end.y - anchor.y) < 1e-6
        docks = False
        if at_s or at_e:
            far = seg.end if at_s else seg.start
            along = (far.x - anchor.x) * ux + (far.y - anchor.y) * uy
            docks = along <= 1e-6  # arrives from opposite/perpendicular to body/text
        if not docks and _overlap_is_significant(sb, prim_bb):
            return False
        return True

    # Ring order: nearest outboard distance first, then nearest perpendicular
    # lane — the first clean+routable slot wins (early-out). Bounded radius.
    for extra in range(2, 18):
        dist = snap_to_grid(extra * VISUAL_CLEARANCE_MM)
        elbow = Point(snap_to_grid(tip.x + ux * dist), snap_to_grid(tip.y + uy * dist))
        for poff in (0, 1, -1, 2, -2, 3, -3, 4, -4, 6, -6, 8, -8):
            pd = snap_to_grid(poff * VISUAL_CLEARANCE_MM)
            anchor = Point(snap_to_grid(elbow.x + px * pd), snap_to_grid(elbow.y + py * pd))
            prim, bb = _make(anchor)
            if prim is None or not _clear(bb, is_stub=False):
                continue
            try:
                segs = router.route_to(anchor)
            except Exception:  # noqa: BLE001
                continue
            if not segs:
                continue
            rw = [PlacedWire(a, b) for a, b in segs if a != b]
            if not rw:
                continue
            # FULL clean-route gate: re-validate every routed segment against the
            # real overlap contract (the router only knew the static bitmap).
            if not all(_route_seg_clean(w, anchor, bb) for w in rw):
                continue
            return prim, bb, list(rw)
    return None


def _hlabel_bb(h: PlacedHierarchicalLabel) -> BBox:
    # Use the VALIDATOR's own bbox so placement-clean == validator-clean (the
    # keystone): the validator measures hier-labels via this exact function.
    from zynq_eda.core.validate.overlap import _hierarchical_label_text_bbox
    return _hierarchical_label_text_bbox(h)


def _label_bb(l: PlacedLabel) -> BBox:
    from zynq_eda.core.validate.overlap import _label_text_bbox
    return _label_text_bbox(l)


def _seg_crosses_wire(seg: PlacedWire, wo: BBox) -> bool:
    """True iff axis-aligned ``seg`` perpendicular-crosses the wire whose bbox
    is ``wo`` (orientation inferred from the thin bbox). Mirrors the overlap
    validator's no-crossing rule so a routed stub never lays a wire cross."""
    s_horiz = abs(seg.start.y - seg.end.y) < 1e-6
    w_horiz = (wo.max.x - wo.min.x) >= (wo.max.y - wo.min.y)
    if s_horiz == w_horiz:
        return False  # parallel — collinear overlap handled elsewhere
    if s_horiz:
        hy = seg.start.y
        hx_lo, hx_hi = sorted((seg.start.x, seg.end.x))
        vx = (wo.min.x + wo.max.x) / 2.0
        vy_lo, vy_hi = wo.min.y, wo.max.y
    else:
        vx = seg.start.x
        vy_lo, vy_hi = sorted((seg.start.y, seg.end.y))
        hy = (wo.min.y + wo.max.y) / 2.0
        hx_lo, hx_hi = wo.min.x, wo.max.x
    return hx_lo - 1e-6 < vx < hx_hi + 1e-6 and vy_lo - 1e-6 < hy < vy_hi + 1e-6
