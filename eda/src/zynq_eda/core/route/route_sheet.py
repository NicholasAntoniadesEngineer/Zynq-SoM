"""Stage C — assemble the fully wired sheet from a Stage B arrangement.

Stage B (:mod:`zynq_eda.core.layout.arrange`) froze every module and spread the
units with zero symbol+label overlap. Each :class:`~zynq_eda.core.layout.module.Module`
already carries its intra-module wiring (trunk/drop + far stubs). This stage
assembles the complete sheet — symbols + labels + wires + junctions — and is the
seam where dense modules get their wiring re-routed cleanly (A*).

Empirically, after Stage B the naive intra-module wiring is already clean on
every sheet EXCEPT the three densest IC modules (ethernet's 9-tap Bob-Smith,
the 14-part FUSB302, the 8-part CP2102N), where trunk/drop wires cross bodies,
pin text, and each other. :func:`route_sheet` re-routes exactly those modules
with the bounded grid A* (:mod:`zynq_eda.core.route.astar`) against a per-symbol
obstacle set; clean-routing modules keep their (already clean) naive wires.
"""

from __future__ import annotations

from dataclasses import replace

from zynq_eda.core.layout.arrange import Arrangement, arrange_block
from zynq_eda.core.layout.footprint import symbol_footprint
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.layout.labeler import label_connectors
from zynq_eda.core.layout.edge_labels import (
    expose_ic_pin_nets,
    no_connect_markers,
    power_drive_stamps,
)
from zynq_eda.core.layout.module import Module
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire, Sheet
from zynq_eda.core.layout.bbox import wire_bbox
from zynq_eda.core.route.route_module import _obstacles, reroute_module


def _strictly_interior(p: Point, a: Point, b: Point, eps: float = 0.05) -> bool:
    """True iff ``p`` lies strictly inside the axis-aligned segment ``a``-``b``
    (on it, but not at either endpoint)."""
    if abs(a.x - b.x) < eps and abs(p.x - a.x) < eps:  # vertical
        lo, hi = sorted((a.y, b.y))
        return lo + eps < p.y < hi - eps
    if abs(a.y - b.y) < eps and abs(p.y - a.y) < eps:  # horizontal
        lo, hi = sorted((a.x, b.x))
        return lo + eps < p.x < hi - eps
    return False


def _split_wires_at_pins(
    wires: list[PlacedWire], pin_points: list[Point], eps: float = 0.05
) -> list[PlacedWire]:
    """Split every wire at each pin that lies on its INTERIOR.

    KiCad does not connect a pin a wire merely passes over (it must end on
    the pin, or carry a junction). Trunk/overshoot wires routinely run THROUGH
    their own net's pins, leaving them on a wire interior → ``pin_not_connected``.
    Cutting each such wire at the pin turns the pin into a wire ENDPOINT, which
    KiCad connects. The router blocks foreign pins, so a wire only ever crosses
    its OWN net's pins; splitting there is always electrically correct.
    """
    out: list[PlacedWire] = []
    for w in wires:
        cuts = [p for p in pin_points if _strictly_interior(p, w.start, w.end, eps)]
        if not cuts:
            out.append(w)
            continue
        vertical = abs(w.start.x - w.end.x) < eps
        pts = [w.start, w.end] + cuts
        pts.sort(key=(lambda q: q.y) if vertical else (lambda q: q.x))
        uniq: list[Point] = [pts[0]]
        for q in pts[1:]:
            if abs(q.x - uniq[-1].x) > eps or abs(q.y - uniq[-1].y) > eps:
                uniq.append(q)
        for a, b in zip(uniq, uniq[1:]):
            out.append(PlacedWire(a, b))
    return out


def _declutter_property_text(symbols, wires, geometry):
    """Nudge a symbol's Value/Reference text off any wire that crosses it.

    Dense trunk/bus routing legitimately runs a wire past a component (e.g.
    ethernet's BS_COMMON bus past the Bob-Smith resistors); the component's
    property text ("75R", "R100") can land in the wire's path. Rather than
    relax the overlap rule, shift the text to the nearest grid position that
    clears every wire AND doesn't land on another symbol's footprint — render-
    clean by construction. Positions/pins are untouched, so connectivity holds.
    """
    wbbs = [wire_bbox(w.start, w.end, owner_id="w") for w in wires]
    foots = []
    for s in symbols:
        try:
            foots.append((f"symbol:{s.reference}", symbol_footprint(s, geometry)))
        except Exception:  # noqa: BLE001
            pass

    def _box(sym, kind, vs, rs):
        try:
            for b in geometry.property_text_bboxes(
                sym.lib_id, sym.position, sym.rotation,
                owner_id=f"symbol:{sym.reference}", reference_override=sym.reference,
                value_override=sym.value, value_shift=vs, reference_shift=rs):
                if b.owner_id.endswith(f":property:{kind}"):
                    return b
        except Exception:  # noqa: BLE001
            return None
        return None

    def _hits_wire(box):
        return any(box.intersects(wb, padding_mm=0.0) for wb in wbbs)

    def _hits_other(box, own):
        return any(oid != own and box.intersects(ft, padding_mm=0.5)
                   for oid, ft in foots)

    out = []
    for sym in symbols:
        own = f"symbol:{sym.reference}"
        vs, rs = sym.value_shift, sym.reference_shift
        changed = False
        for kind in ("Value", "Reference"):
            box = _box(sym, kind, vs, rs)
            if box is None or not _hits_wire(box):
                continue
            base = (vs if kind == "Value" else rs) or (0.0, 0.0, None)
            found = None
            for d in range(1, 9):
                for dx, dy in ((0, -d), (0, d), (-d, 0), (d, 0),
                               (-d, -d), (d, -d), (-d, d), (d, d)):
                    cand = (base[0] + dx * 1.27, base[1] + dy * 1.27, base[2])
                    nb = _box(sym, kind, cand if kind == "Value" else vs,
                              cand if kind == "Reference" else rs)
                    if nb is not None and not _hits_wire(nb) and not _hits_other(nb, own):
                        found = cand
                        break
                if found:
                    break
            if found is not None:
                if kind == "Value":
                    vs = found
                else:
                    rs = found
                changed = True
        out.append(replace(sym, value_shift=vs, reference_shift=rs) if changed else sym)
    return out


def route_sheet(
    block: Block,
    geometry: SymbolGeometryCache,
    *,
    reroute: bool = True,
    stamp_nets: set[str] | None = None,
) -> Sheet:
    """Return the complete wired :class:`Sheet` for ``block``.

    Runs Stage B placement, optionally re-routes dense modules with A*, then
    assembles symbols + labels + wires + junctions. Connectors are bodies only
    (their pin nets become edge hier-labels in Stage D).

    ``stamp_nets`` is the set of global power nets this sheet should emit a
    PWR_FLAG drive stamp for (the pipeline assigns each net to the first sheet
    that contains it, so each global net is driven exactly once).
    """
    arr = arrange_block(block, geometry)
    return assemble_sheet(arr, geometry, block, reroute=reroute, stamp_nets=stamp_nets)


def assemble_sheet(
    arr: Arrangement,
    geometry: SymbolGeometryCache,
    block: Block,
    *,
    reroute: bool = True,
    stamp_nets: set[str] | None = None,
) -> Sheet:
    symbols = list(arr.sheet.symbols)
    labels = list(arr.sheet.labels)
    wires: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []

    for module in arr.modules:
        routed: Module = reroute_module(module, geometry) if reroute else module
        wires.extend(routed.wires)
        junctions.extend(routed.junctions)

    # Stage D: label every connector pin, clearing the placed symbols + wires.
    # Use PER-PRIMITIVE obstacles (body + each pin-name/number box) so a label
    # can sit in the gap between pin texts rather than being pushed clear of the
    # whole connector's merged footprint.
    occupied = _obstacles(symbols, geometry)
    # Property text (Reference/Value) too — so the connector labeler and the IC
    # exposer route their stubs clear of it (it's what the overlap validator
    # measures; omitting it let stubs cross "C101"/"100n" text).
    for s in symbols:
        try:
            occupied.extend(geometry.property_text_bboxes(
                s.lib_id, s.position, s.rotation,
                owner_id=f"symbol:{s.reference}",
                reference_override=s.reference, value_override=s.value,
                value_shift=s.value_shift, reference_shift=s.reference_shift))
        except Exception:  # noqa: BLE001
            pass
    for w in wires:
        occupied.append(wire_bbox(w.start, w.end, owner_id="routed"))
    # Module-emitted labels (e.g. a cluster pin's own-net local label) are real
    # obstacles too — include them so the connector labeler AND the IC-pin
    # exposer place clear of them (else two labels land on the same row).
    from zynq_eda.core.validate.overlap import (
        _hierarchical_label_text_bbox,
        _label_text_bbox,
    )
    for lbl in labels:
        occupied.append(_label_text_bbox(lbl))
    conns = [(c.instance, c.symbol) for c in arr.connectors]
    clabels, chlabels, cwires = label_connectors(block, conns, geometry, occupied)
    wires.extend(cwires)
    # Connector wires + labels are obstacles for the IC-pin exposer that runs
    # next, so its routed stubs don't cross them (wire×wire / wire×label).
    for w in cwires:
        occupied.append(wire_bbox(w.start, w.end, owner_id="conn_wire"))
    for lbl in clabels:
        occupied.append(_label_text_bbox(lbl))
    for hl in chlabels:
        occupied.append(_hierarchical_label_text_bbox(hl))

    ic_symbols = {
        m.ic_ref: next(s for s in m.symbols if s.reference == m.ic_ref)
        for m in arr.modules
    }

    # Stage E.1: expose every still-floating IC pin's net — power symbol (GND /
    # rails), hier-label (sheet-edge nets), or local label — on a clearance-
    # checked outboard stub, so no IC pin is left electrically dangling.
    connected = {(round(w.start.x, 2), round(w.start.y, 2)) for w in wires}
    connected |= {(round(w.end.x, 2), round(w.end.y, 2)) for w in wires}
    esyms, elabels, ehlabels, ewires = expose_ic_pin_nets(
        block, ic_symbols, geometry, occupied, connected
    )
    symbols.extend(esyms)
    wires.extend(ewires)

    # Stage E.2: No-Connect markers on every still-unused pin (connector spares
    # + NC IC pins), so ERC stops firing pin_not_connected on unused pins.
    no_connects = no_connect_markers(block, conns, geometry, ic_symbols)

    # Stage E.3: PWR_FLAG drive stamps for the global power nets assigned to this
    # sheet, so ERC stops firing power_pin_not_driven (a power symbol is power-
    # INPUT; a PWR_FLAG marks the net externally driven). One flag per global
    # net drives it project-wide; the pipeline assigns each net once.
    if stamp_nets:
        ssyms, swires = power_drive_stamps(
            sorted(stamp_nets), arr.sheet.paper_size, geometry, occupied
        )
        symbols.extend(ssyms)
        wires.extend(swires)

    # Final connectivity pass: split every wire at each pin that lies on its
    # interior, so a pin a trunk/overshoot wire passes THROUGH becomes a wire
    # ENDPOINT (which KiCad connects). This is the electrical closure that makes
    # validate_connectivity == 0 achievable without a router rewrite — the two
    # grid routers land wires near pins; this lands them ON pins.
    # Declutter: shift any Value/Reference text a wire crosses to clear space
    # (positions/pins untouched, so connectivity holds).
    symbols = _declutter_property_text(symbols, wires, geometry)

    all_pin_pts: list[Point] = []
    for s in symbols:
        try:
            all_pin_pts.extend(
                geometry.absolute_pin_positions(s.lib_id, s.position, s.rotation).values()
            )
        except Exception:  # noqa: BLE001 — a symbol without resolvable pins just isn't a cut site
            continue
    wires = _split_wires_at_pins(wires, all_pin_pts)

    return Sheet(
        name=arr.sheet.name,
        title=arr.sheet.title,
        paper_size=arr.sheet.paper_size,
        symbols=tuple(symbols),
        labels=tuple(labels + clabels + elabels),
        hierarchical_labels=tuple(chlabels + ehlabels),
        wires=tuple(wires),
        junctions=tuple(junctions),
        no_connects=tuple(no_connects),
    )
