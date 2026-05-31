"""Re-route a module's intra-wiring cleanly with bounded grid A*.

Stage B leaves every module internally clean on symbols+labels, and the naive
trunk/drop wiring from Stage A is already clean on all but the three densest IC
modules (ethernet's Bob-Smith ladder, FUSB302, CP2102N), where drops cross
bodies, pin text and each other. :func:`reroute_module` re-routes exactly those
with A* (:func:`zynq_eda.core.route.astar.route_astar`) against a per-PRIMITIVE
obstacle set (body + each text box), so wires can thread between text.

Discipline (the Laws): a module is rerouted ONLY if its current wiring isn't
clean, and the rerouted result is kept ONLY if it is measurably cleaner — so a
clean module is never touched and a reroute can never regress a sheet.
"""

from __future__ import annotations

from dataclasses import replace

from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM
from zynq_eda.core.layout.bbox import BBox, symbol_bbox, wire_bbox
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.layout.module import Module
from zynq_eda.core.layout.text_obstacles import collect_text_bboxes
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import PlacedJunction, PlacedSymbol, PlacedWire, Sheet
from zynq_eda.core.route.astar import route_astar

_AVOID_KINDS = frozenset(
    {"symbol", "intrinsic_pin_name", "intrinsic_pin_number", "label", "wire"}
)


def _module_findings(module: Module, geometry: SymbolGeometryCache) -> int:
    """Count overlap/crowding findings for the module as a standalone sheet."""
    from zynq_eda.core.validate.overlap import validate_overlap

    sheet = Sheet(
        name="m", title="m", paper_size="A3",
        symbols=module.symbols, wires=module.wires,
        junctions=module.junctions, labels=module.labels,
    )
    return len(validate_overlap(sheet, geometry=geometry, strict=False))


def _obstacles(symbols, geometry: SymbolGeometryCache) -> list[BBox]:
    boxes: list[BBox] = []
    for s in symbols:
        oid = f"symbol:{s.reference}"
        try:
            boxes.append(symbol_bbox(s.lib_id, s.position, s.rotation, geometry, oid))
        except Exception:
            pass
        try:
            boxes.extend(collect_text_bboxes(s, geometry, owner_id=oid))
        except Exception:
            pass
    return boxes


def _pins(sym: PlacedSymbol, geometry: SymbolGeometryCache) -> list[Point]:
    try:
        return list(
            geometry.absolute_pin_positions(sym.lib_id, sym.position, sym.rotation).values()
        )
    except Exception:
        return []


def _nearest(p: Point, candidates: list[Point]) -> tuple[Point, float]:
    best = candidates[0]
    bestd = abs(best.x - p.x) + abs(best.y - p.y)
    for c in candidates[1:]:
        d = abs(c.x - p.x) + abs(c.y - p.y)
        if d < bestd:
            best, bestd = c, d
    return best, bestd


def reroute_module(module: Module, geometry: SymbolGeometryCache) -> Module:
    """Return ``module`` with clean A*-routed wiring if that helps, else as-is."""
    before = _module_findings(module, geometry)
    if before == 0:
        return module  # already clean — never touch it

    ic_syms = [s for s in module.symbols if s.reference == module.ic_ref]
    if not ic_syms:
        return module
    ic = ic_syms[0]
    ic_oid = f"symbol:{ic.reference}"
    ic_pins = _pins(ic, geometry)
    if not ic_pins:
        return module

    passives = [s for s in module.symbols if s.lib_id.startswith("Device:")]
    powers = [s for s in module.symbols if s.lib_id.startswith("power:")]
    # Far-end attachment targets: power-symbol pins + label anchors.
    targets: list[tuple[Point, str]] = []
    for pw in powers:
        for pt in _pins(pw, geometry):
            targets.append((pt, f"symbol:{pw.reference}"))
    for lbl in module.labels:
        targets.append((lbl.position, ""))

    obstacles = _obstacles(module.symbols, geometry)
    clr = VISUAL_CLEARANCE_MM

    # Build all routing tasks first: a DROP (IC pin -> cap near) and a STUB
    # (cap far -> nearest power pin / label) per passive.
    tasks: list[tuple[Point, Point, frozenset]] = []
    for cap in passives:
        cap_oid = f"symbol:{cap.reference}"
        cps = _pins(cap, geometry)
        if len(cps) < 2:
            continue
        d0 = _nearest(cps[0], ic_pins)[1]
        d1 = _nearest(cps[1], ic_pins)[1]
        near, far = (cps[0], cps[1]) if d0 <= d1 else (cps[1], cps[0])
        ic_pin = _nearest(near, ic_pins)[0]
        tasks.append((ic_pin, near, frozenset({ic_oid, cap_oid})))
        if targets:
            tgt, _d = _nearest(far, [t for t, _ in targets])
            tgt_oid = next((o for t, o in targets if t == tgt), "")
            ignore = {cap_oid} | ({tgt_oid} if tgt_oid else set())
            tasks.append((far, tgt, frozenset(ignore)))

    # Net-order shortest-first; stamp each routed wire into the obstacle set so
    # later routes avoid earlier ones (no wire-wire crossings).
    tasks.sort(key=lambda t: abs(t[0].x - t[1].x) + abs(t[0].y - t[1].y))
    new_wires: list[PlacedWire] = []
    for start, end, ignore in tasks:
        seg = route_astar(
            start, end, obstacles,
            avoid_owners=ignore, avoid_kinds=_AVOID_KINDS, clearance_mm=clr,
        )
        if not seg:
            continue
        new_wires.extend(seg)
        for w in seg:
            obstacles.append(wire_bbox(w.start, w.end, owner_id="routed"))

    if not new_wires:
        return module

    junctions = _junctions(new_wires)
    candidate = replace(module, wires=tuple(new_wires), junctions=tuple(junctions))
    after = _module_findings(candidate, geometry)
    # Keep the reroute ONLY if it is strictly better (no-regression Law).
    return candidate if after < before else module


def _junctions(wires: list[PlacedWire]) -> list[PlacedJunction]:
    """A junction wherever >= 3 wire endpoints coincide (a real merge tap)."""
    from collections import Counter

    ends: Counter = Counter()
    for w in wires:
        ends[(w.start.x, w.start.y)] += 1
        ends[(w.end.x, w.end.y)] += 1
    return [PlacedJunction(Point(x, y)) for (x, y), n in ends.items() if n >= 3]
