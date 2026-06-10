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
    wires: list[PlacedWire],
    pin_points: list[Point],
    eps: float = 0.05,
    point_net: dict[tuple[float, float], str] | None = None,
) -> list[PlacedWire]:
    """Split every wire at each SAME-NET pin that lies on its INTERIOR.

    KiCad does not connect a pin a wire merely passes over (it must end on
    the pin, or carry a junction). Trunk/overshoot wires routinely run THROUGH
    their own net's pins, leaving them on a wire interior → ``pin_not_connected``.
    Cutting each such wire at the pin turns the pin into a wire ENDPOINT, which
    KiCad connects.

    CRITICAL (LAW 0): splitting at a FOREIGN pin would tap it onto this wire's
    net = a SHORT. So when ``point_net`` (a point→intended-net map covering pins,
    labels and power symbols) is given, a wire is cut at an interior pin ONLY if
    that pin's net matches the wire's net — the net carried by a pin/label/power
    anchor at EITHER wire endpoint. A wire with no anchored endpoint (a mid-net
    bend) carries no provable net, so it is never cut at a bare pin (the pin
    floats honestly for the exposer rather than risking a short).
    """
    def _wire_nets(w: PlacedWire) -> set[str]:
        if point_net is None:
            return set()
        nets: set[str] = set()
        for e in (w.start, w.end):
            n = point_net.get((round(e.x, 2), round(e.y, 2)))
            if n:
                nets.add(n)
        return nets

    out: list[PlacedWire] = []
    for w in wires:
        cuts = [p for p in pin_points if _strictly_interior(p, w.start, w.end, eps)]
        if point_net is not None and cuts:
            wnets = _wire_nets(w)
            cuts = [p for p in cuts
                    if point_net.get((round(p.x, 2), round(p.y, 2))) in wnets]
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


def _propagate_wire_net_tokens(
    wires: list[PlacedWire],
    point_net: dict[tuple[float, float], str],
) -> None:
    """Spread known net tokens across connected wire chains (in place).

    Builds an adjacency over wire endpoints (a wire is an edge between its two
    rounded endpoints) and BFS-floods each already-known token to every endpoint
    reachable through same-wire connections. Endpoints that already carry a token
    are NOT overwritten (the seed wins; a clash would be a same-rail merge, whose
    members are one net by name anyway). The result lets the splitter recognise
    the net at a wire's bare-bend endpoints, so it can legally cut that wire at an
    interior SAME-net pin. Only physically-wired endpoints share a token, so this
    never invents a cross-net identity (LAW 0).
    """
    from collections import deque

    adj: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for w in wires:
        a = (round(w.start.x, 2), round(w.start.y, 2))
        b = (round(w.end.x, 2), round(w.end.y, 2))
        if a == b:
            continue
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    # Flood from every seeded node; first token to reach a node sticks. A node
    # that already carries a token is a stop (the seed that set it floods its own
    # side), so the only writes are to previously-unknown bend endpoints.
    seeds = [n for n in adj if n in point_net]
    for seed in seeds:
        token = point_net[seed]
        q = deque([seed])
        while q:
            node = q.popleft()
            for nb in adj.get(node, ()):
                if nb not in point_net:
                    point_net[nb] = token
                    q.append(nb)


def _declutter_property_text(symbols, wires, geometry, labels=()):
    """Place each symbol's Value/Reference text clear of EVERYTHING visible.

    The overlap validator exempts a symbol's own Value/Reference text sitting on
    its own pin-name/number text, but the RENDER still shows that pile-up (the
    LDO "U1" stamped on "TLV75733PDBVR" on the GND pin). So this places each
    Value and Reference at the nearest grid offset that clears, with real visual
    clearance: its OWN pin text + the OTHER property text of the same symbol +
    every wire + every label, and (at the validator's 2.54 mm) every OTHER
    symbol's body+text footprint — so no new footprint overlap is introduced.
    Positions/pins are untouched, so connectivity holds.
    """
    from zynq_eda.core.validate.overlap import (
        _hierarchical_label_text_bbox,
        _label_text_bbox,
    )

    wbbs = [wire_bbox(w.start, w.end, owner_id="w") for w in wires]
    lbbs = []
    for l in labels:
        fn = _hierarchical_label_text_bbox if hasattr(l, "direction") else _label_text_bbox
        try:
            lbbs.append(fn(l))
        except Exception:  # noqa: BLE001
            pass
    foots: dict[str, object] = {}          # owner -> live footprint (validator 2.54)
    pintext: dict[str, list] = {}          # owner -> its pin-name/number boxes
    for s in symbols:
        oid = f"symbol:{s.reference}"
        try:
            foots[oid] = symbol_footprint(s, geometry)
        except Exception:  # noqa: BLE001
            pass
        try:
            pintext[oid] = list(geometry.intrinsic_pin_label_bboxes(
                s.lib_id, s.position, rotation=s.rotation, owner_id=oid))
        except Exception:  # noqa: BLE001
            pintext[oid] = []

    def _box(sym, kind, vs, rs):
        try:
            for b in geometry.property_text_bboxes(
                sym.lib_id, sym.position, sym.rotation,
                owner_id=f"symbol:{sym.reference}", reference_override=sym.reference,
                value_override=sym.value, value_shift=vs, reference_shift=rs,
                correct_property_pos=True):
                if b.owner_id.endswith(f":property:{kind}"):
                    return b
        except Exception:  # noqa: BLE001
            return None
        return None

    def _clear(box, own, other_prop):
        # Foreign things the overlap validator measures at 2.54 mm: every other
        # symbol's footprint, and every label (hier/local). Must clear those at
        # the SAME 2.54 mm or the move just trades one validator overlap for
        # another (uart RXD label vs a moved GND value).
        if any(box.intersects(lb, padding_mm=2.54) for lb in lbbs):
            return False
        for oid, ft in foots.items():
            if oid != own and box.intersects(ft, padding_mm=2.54):
                return False
        # Visual-only (validator-exempt) clearances — just don't touch:
        if any(box.intersects(wb, padding_mm=0.6) for wb in wbbs):
            return False
        if any(box.intersects(pb, padding_mm=0.6) for pb in pintext.get(own, ())):
            return False  # never on this symbol's own pin text (the visual pile-up)
        if other_prop is not None and box.intersects(other_prop, padding_mm=0.6):
            return False  # Value vs Reference of the same symbol
        return True

    out = []
    for sym in symbols:
        own = f"symbol:{sym.reference}"
        vs, rs = sym.value_shift, sym.reference_shift
        changed = False
        # Place Value first (usually the long text), then Reference clear of it.
        for kind in ("Value", "Reference"):
            box = _box(sym, kind, vs, rs)
            other = _box(sym, "Reference" if kind == "Value" else "Value", vs, rs)
            if box is None or _clear(box, own, other):
                continue
            base = (vs if kind == "Value" else rs) or (0.0, 0.0, None)
            found = None
            # Prefer BELOW the symbol, then above, then sides — the hand-drawn
            # convention — increasing distance until a clear slot is found.
            for d in range(1, 18):
                for dx, dy in ((0, d), (0, -d), (d, 0), (-d, 0),
                               (d, d), (-d, d), (d, -d), (-d, -d)):
                    cand = (base[0] + dx * 1.27, base[1] + dy * 1.27, base[2])
                    nb = _box(sym, kind, cand if kind == "Value" else vs,
                              cand if kind == "Reference" else rs)
                    if nb is not None and _clear(nb, own, other):
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
        new_sym = replace(sym, value_shift=vs, reference_shift=rs) if changed else sym
        out.append(new_sym)
        if changed:  # keep foots LIVE so the next symbol's text avoids this one's
            try:
                foots[own] = symbol_footprint(new_sym, geometry)
            except Exception:  # noqa: BLE001
                pass
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
    # Declutter: place every Value/Reference text clear of pin text, other text,
    # wires, and labels (positions/pins untouched, so connectivity holds).
    symbols = _declutter_property_text(
        symbols, wires, geometry,
        labels=labels + clabels + elabels + chlabels + ehlabels,
    )

    # Point -> intended-net map so the splitter only taps SAME-net pins (LAW 0:
    # cutting a wire at a FOREIGN pin shorts it). Covers IC/cluster pins
    # (plan_pin_specs), connector pins (pin_to_net), power symbols and labels.
    from zynq_eda.core.layout.plan import plan_pin_specs
    ref_pin_net: dict[tuple[str, str], str] = {}
    try:
        for sp in plan_pin_specs(block, geometry):
            net = sp.net_name or sp.cluster_owner_net
            if net:
                ref_pin_net[(sp.owner_ref, str(sp.pin_number))] = net
    except Exception:  # noqa: BLE001
        pass
    for c in getattr(block, "connectors", ()) or ():
        cref = getattr(c, "reference", None) or getattr(
            getattr(c, "instance", None), "reference", None)
        for pid, net in getattr(c, "pin_to_net", ()) or ():
            if cref and net:
                ref_pin_net[(cref, str(pid))] = net
    point_net: dict[tuple[float, float], str] = {}
    all_pin_pts: list[Point] = []
    # Seed the cut map from each module's OWN net topology FIRST: every terminal
    # of a module net (IC pin, each passive's near/far pin, the far power-symbol
    # pin) carries that net's identity. Passive pins are NOT in plan_pin_specs,
    # so without this a trunk wire that RUNS THROUGH an interior cap pin (e.g.
    # usb_pd C107 on the FUSB302 +VIN trunk) can never be cut there and the cap
    # floats. The token is the net's electrical identity (rails collapse to GND /
    # +3V3 / …; per-pin trunks stay distinct via _base_net), so a cut here only
    # ever taps a SAME-net pin — never a short (LAW 0). plan_pin_specs / power /
    # labels OVERRIDE below with the real net name where they know it; the
    # splitter matches by the token carried at the wire's ENDPOINTS, so the
    # endpoints and any interior cut of one trunk share one consistent token.
    from zynq_eda.core.route.route_module import _base_net
    # Coordinate -> real net for every IC pin, so a per-pin trunk's token equals
    # the SAME real net string plan_pin_specs assigns its IC-pin endpoint — the
    # endpoint and any interior cap-pin cut then carry one identical token (no
    # string mismatch that would block a legal same-net cut).
    coord_net: dict[tuple[float, float], str] = {}
    for ref, sym in ic_symbols.items():
        try:
            pp = geometry.absolute_pin_positions(sym.lib_id, sym.position, sym.rotation)
        except Exception:  # noqa: BLE001
            continue
        for num, pt in pp.items():
            n = ref_pin_net.get((ref, str(num)))
            if n:
                coord_net[(round(pt.x, 2), round(pt.y, 2))] = n
    for m in arr.modules:
        for key, terms in m.nets:
            # Prefer the real net name carried by any IC-pin terminal of this
            # net; fall back to _base_net (rails collapse to GND/+3V3; per-pin
            # trunks stay distinct). One token per module net keeps endpoint and
            # interior cuts consistent — a cut here only ever taps a SAME-net pin.
            token = next(
                (coord_net[(round(t.x, 2), round(t.y, 2))] for t in terms
                 if (round(t.x, 2), round(t.y, 2)) in coord_net),
                _base_net(key, m.ic_ref),
            )
            for t in terms:
                k = (round(t.x, 2), round(t.y, 2))
                all_pin_pts.append(t)
                point_net.setdefault(k, token)
    for s in symbols:
        try:
            pp = geometry.absolute_pin_positions(s.lib_id, s.position, s.rotation)
        except Exception:  # noqa: BLE001 — a symbol without resolvable pins isn't a cut site
            continue
        is_pwr = s.lib_id.startswith("power:")
        for num, pt in pp.items():
            all_pin_pts.append(pt)
            net = s.value if is_pwr else ref_pin_net.get((s.reference, str(num)))
            if net:
                point_net[(round(pt.x, 2), round(pt.y, 2))] = net
    for lb in labels + clabels + elabels:
        point_net[(round(lb.position.x, 2), round(lb.position.y, 2))] = lb.net_name
    for hl in chlabels + ehlabels:
        point_net[(round(hl.position.x, 2), round(hl.position.y, 2))] = hl.net_name
    # Propagate each known net token along PHYSICALLY-CONNECTED wire chains
    # (shared endpoints), so a wire whose endpoints are bare bends inherits the
    # net carried by a terminal/label/power anchor it is wired to. Without this,
    # the splitter cannot cut a wire that RUNS THROUGH an interior pin when both
    # its own endpoints are mid-net bends (e.g. usb_pd's +VIN feed runs through
    # R104.2 between two bends) — the pin then floats. Two wires share an
    # endpoint ONLY when the router (per-net) joined them, and the touch-guard
    # has already removed any foreign touch, so a propagated token is always the
    # endpoint's TRUE net — a cut it enables only ever taps a SAME-net pin (LAW 0).
    _propagate_wire_net_tokens(wires, point_net)
    wires = _split_wires_at_pins(wires, all_pin_pts, point_net=point_net)

    # Drop ORPHANED power symbols: a module can emit a GND/rail power symbol
    # whose only connecting wire the touch-guard later dropped (e.g. ethernet's
    # T1.14 GND, walled off by the BS_COMMON trunk). Power is a GLOBAL net joined
    # BY NAME, so a power symbol carries no electrical weight on its own — a
    # floating one is pure ERC noise (pin_not_connected + a stray glyph). The
    # exposer re-attaches the pin with a FRESH, routed power symbol; this removes
    # the now-redundant orphan so the sheet shows exactly one connected GND mark.
    # Only power symbols are eligible (signal symbols never float by design), and
    # only when their pin coincides with no wire-endpoint / pin / junction.
    symbols = _drop_orphan_power_symbols(symbols, wires, junctions, geometry)

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


def _drop_orphan_power_symbols(symbols, wires, junctions, geometry):
    """Remove power-symbol bodies whose single pin is electrically dangling.

    A power symbol (``power:GND`` / ``power:+3V3`` / …) connects its net BY
    NAME, so it only earns its place on the sheet if its pin actually touches a
    wire (the local stub joining it to its IC/connector pin). When that stub was
    dropped upstream (a touch-guard short avoidance), the symbol floats — KiCad
    ERC fires ``pin_not_connected`` on it and the render shows a stray glyph.
    Such a symbol is redundant (the rail is still driven elsewhere by name), so
    it is removed. Non-power symbols and connected power symbols are untouched.
    """
    eps = 0.05
    ends: list[Point] = []
    for w in wires:
        ends.append(w.start)
        ends.append(w.end)
    for j in junctions:
        ends.append(j.position)
    # Other symbols' pins (a power symbol abutting a pin directly is connected).
    other_pins: list[Point] = []
    for s in symbols:
        if s.lib_id.startswith("power:"):
            continue
        try:
            other_pins.extend(
                geometry.absolute_pin_positions(s.lib_id, s.position, s.rotation).values()
            )
        except Exception:  # noqa: BLE001
            pass

    def _touches(p: Point) -> bool:
        for q in ends:
            if abs(p.x - q.x) < eps and abs(p.y - q.y) < eps:
                return True
        for q in other_pins:
            if abs(p.x - q.x) < eps and abs(p.y - q.y) < eps:
                return True
        return False

    kept = []
    for s in symbols:
        if s.lib_id.startswith("power:"):
            try:
                pins = list(geometry.absolute_pin_positions(
                    s.lib_id, s.position, s.rotation).values())
            except Exception:  # noqa: BLE001
                kept.append(s)
                continue
            if pins and not any(_touches(p) for p in pins):
                continue  # orphan — drop it
        kept.append(s)
    return kept
