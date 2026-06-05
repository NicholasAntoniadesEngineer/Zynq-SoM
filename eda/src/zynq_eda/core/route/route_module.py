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
from zynq_eda.core.route.grid import route_terminals

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


def _dedupe_points(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if not any(abs(p.x - q.x) < 1e-6 and abs(p.y - q.y) < 1e-6 for q in out):
            out.append(p)
    return out


def _net_span(pts: tuple[Point, ...]) -> float:
    if len(pts) < 2:
        return 0.0
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def _mst_edges(points: list[Point]) -> list[tuple[Point, Point]]:
    """Manhattan minimum spanning tree edges (Prim's, O(n^2) — n is tiny)."""
    n = len(points)
    if n < 2:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    edges: list[tuple[Point, Point]] = []
    for _ in range(n - 1):
        best = None
        for i in range(n):
            if not in_tree[i]:
                continue
            for j in range(n):
                if in_tree[j]:
                    continue
                d = abs(points[i].x - points[j].x) + abs(points[i].y - points[j].y)
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        in_tree[j] = True
        edges.append((points[i], points[j]))
    return edges


def _seg_crosses_body(seg: PlacedWire, ob: BBox, margin: float = 0.6) -> bool:
    """True iff the axis-aligned ``seg`` runs THROUGH ``ob``'s interior.

    ``margin`` insets the body so a wire grazing the body edge (e.g. starting
    at a pin ON that edge) doesn't count — only a wire crossing the interior
    does. This avoids the false positives an endpoint-exclusion scheme needs.
    """
    ax, ay, bx, by = seg.start.x, seg.start.y, seg.end.x, seg.end.y
    if abs(ay - by) < 1e-6:  # horizontal
        if ob.min.y + margin < ay < ob.max.y - margin:
            lo, hi = sorted((ax, bx))
            return lo < ob.max.x - margin and hi > ob.min.x + margin
        return False
    if abs(ax - bx) < 1e-6:  # vertical
        if ob.min.x + margin < ax < ob.max.x - margin:
            lo, hi = sorted((ay, by))
            return lo < ob.max.y - margin and hi > ob.min.y + margin
        return False
    return False


def _l_hits(segs: list[PlacedWire], obstacles: list[BBox]) -> bool:
    for seg in segs:
        for ob in obstacles:
            if ob.kind == "wire":
                continue
            if _seg_crosses_body(seg, ob):
                return True
    return False


def _l_route(a: Point, b: Point, obstacles: list[BBox]) -> list[PlacedWire]:
    """Connect ``a``-``b`` with an orthogonal route whose endpoints are EXACTLY
    a and b. Prefer the L-orientation that crosses no body; else A*; else the
    direct L (accept an overlap rather than ever leave the pin unwired — the
    Laws: spread/route better, never silently drop)."""
    if abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6:
        return []
    if abs(a.x - b.x) < 1e-6 or abs(a.y - b.y) < 1e-6:
        return [PlacedWire(a, b)]
    c1 = Point(b.x, a.y)
    c2 = Point(a.x, b.y)
    for corner in (c1, c2):
        segs = [PlacedWire(a, corner), PlacedWire(corner, b)]
        if not _l_hits(segs, obstacles):
            return segs
    seg = route_astar(a, b, obstacles, avoid_kinds=_AVOID_KINDS,
                      clearance_mm=VISUAL_CLEARANCE_MM)
    if seg:
        return list(seg)
    return [PlacedWire(a, c1), PlacedWire(c1, b)]


def _route_net_tree(points: list[Point], obstacles: list[BBox]) -> list[PlacedWire]:
    wires: list[PlacedWire] = []
    for a, b in _mst_edges(points):
        wires.extend(_l_route(a, b, obstacles))
    return _dedupe_overlaps(wires)


def reroute_module(module: Module, geometry: SymbolGeometryCache) -> Module:
    """Wire every module net into an orthogonal tree with EXACT on-pin endpoints.

    Connectivity-correct BY CONSTRUCTION: ``module.nets`` declares which pins
    share a net; each net's terminals are joined by a Manhattan MST, every edge
    an obstacle-aware L-route (A* / direct-L fallback). No pin is left unwired
    and no wire ends short of a pin — the failures of the old overlap-only
    reroute (it returned early when overlap was 0, silently dropped failed
    route_astar tasks, modelled only caps, and could not express a merge bus
    like ethernet's BS_COMMON). Longest nets route first so the big buses claim
    clear channels before the short drops fill in. Wires that pass through a pin
    are split at it downstream (route_sheet) so every tap lands on a pin tip.
    """
    if not module.nets:
        return module

    # Route against the SAME bboxes the overlap validator measures — symbol
    # bodies + intrinsic pin text (via _obstacles) PLUS property text
    # (Reference/Value) and the module's own labels — so any route the grid
    # router finds is overlap-clean by construction (no wire×text / wire×label).
    obstacles = _obstacles(module.symbols, geometry)
    for s in module.symbols:
        try:
            obstacles.extend(geometry.property_text_bboxes(
                s.lib_id, s.position, s.rotation,
                owner_id=f"symbol:{s.reference}",
                reference_override=s.reference, value_override=s.value,
                value_shift=s.value_shift, reference_shift=s.reference_shift))
        except Exception:  # noqa: BLE001
            pass
    from zynq_eda.core.validate.overlap import _label_text_bbox
    for lbl in module.labels:
        try:
            obstacles.append(_label_text_bbox(lbl))
        except Exception:  # noqa: BLE001
            pass

    # Per-symbol body centre, so each terminal's ESCAPE direction can point
    # OUTBOARD from the body it sits on. Without this, route_terminals' fallback
    # ("away from the net centroid") sends a left-edge IC pin whose caps are
    # further left to escape RIGHT — into the IC body — and the net fails.
    sym_info: list[tuple] = []
    for s in module.symbols:
        try:
            c = symbol_bbox(s.lib_id, s.position, s.rotation, geometry,
                            f"symbol:{s.reference}").center
        except Exception:  # noqa: BLE001
            c = s.position
        sym_info.append((s, _pins(s, geometry), c))

    def _term_dir(pt: Point) -> tuple[int, int]:
        for _s, sp, c in sym_info:
            if any(abs(pt.x - q.x) < 0.05 and abs(pt.y - q.y) < 0.05 for q in sp):
                ddx, ddy = pt.x - c.x, pt.y - c.y
                if abs(ddx) >= abs(ddy):
                    return (1 if ddx >= 0 else -1, 0)
                return (0, 1 if ddy >= 0 else -1)
        return (0, 0)

    nets: dict[str, list[Point]] = {}
    escape_dirs: dict[str, list[tuple[int, int]]] = {}
    for i, (name, terms) in enumerate(module.nets):
        pts = _dedupe_points(list(terms))
        if len(pts) >= 2:
            key = f"{name}#{i}"
            nets[key] = pts
            escape_dirs[key] = [_term_dir(p) for p in pts]
    if not nets:
        return module

    # Grid A* multi-terminal tree router: avoids every body, text box, and
    # foreign net's wires (no crossings), connects each net into a tree with
    # junction dots at taps, and lands endpoints on the 1.27 mm pin grid. Any
    # net it genuinely cannot route is reported in ``failures`` (never silently
    # dropped); the connectivity validator surfaces the residual so placement
    # can open a wider channel rather than the wire crossing a body.
    wires, junctions, failures = route_terminals(
        obstacles, nets, escape_dirs=escape_dirs
    )
    if failures:
        import sys
        fset = sorted({n for n, _ in failures})
        print(f"      reroute_module({module.ic_ref}): {len(failures)} unrouted "
              f"terminal(s) on nets {fset[:6]}", file=sys.stderr)
    return replace(module, wires=tuple(wires), junctions=tuple(junctions))


def _dedupe_overlaps(wires: list[PlacedWire]) -> list[PlacedWire]:
    """Union all wires into NON-OVERLAPPING maximal axis runs.

    Independent A* drops on the SAME merge net (e.g. ethernet's BS_COMMON) can
    lay segments that overlap or overshoot one another — a wire×wire overlap the
    validator flags even within one net. Rasterise every segment to unit grid
    edges, dedupe, then re-merge collinear adjacent edges into maximal runs, so
    each grid edge is covered exactly once and overshoots collapse away."""
    from zynq_eda.core.model.grid import snap_to_grid as _snap

    GRID = 1.27
    h_by_y: dict[float, set[float]] = {}
    v_by_x: dict[float, set[float]] = {}
    for w in wires:
        a, b = w.start, w.end
        if abs(a.x - b.x) < 1e-6:  # vertical
            x = a.x
            lo, hi = sorted((a.y, b.y))
            cells = v_by_x.setdefault(x, set())
            y = lo
            while y < hi - 1e-9:
                cells.add(round(y, 4)); y = _snap(y + GRID)
        elif abs(a.y - b.y) < 1e-6:  # horizontal
            y = a.y
            lo, hi = sorted((a.x, b.x))
            cells = h_by_y.setdefault(y, set())
            x = lo
            while x < hi - 1e-9:
                cells.add(round(x, 4)); x = _snap(x + GRID)
    out: list[PlacedWire] = []
    for y, xs in h_by_y.items():
        for s, e in _runs(sorted(xs), GRID):
            out.append(PlacedWire(Point(s, y), Point(_snap(e + GRID), y)))
    for x, ys in v_by_x.items():
        for s, e in _runs(sorted(ys), GRID):
            out.append(PlacedWire(Point(x, s), Point(x, _snap(e + GRID))))
    return out


def _runs(coords: list[float], grid: float):
    """Yield (start, last_cell_start) maximal runs of grid-adjacent coords."""
    if not coords:
        return
    cs = ce = coords[0]
    for c in coords[1:]:
        if c <= ce + grid + 1e-9:
            ce = c
        else:
            yield (cs, ce); cs = ce = c
    yield (cs, ce)


def _junctions(wires: list[PlacedWire]) -> list[PlacedJunction]:
    """Junction at every real merge: >= 3 wire ends coincide OR a wire end
    lands strictly inside another wire's span (a T-tap)."""
    from collections import Counter

    ends: Counter = Counter()
    for w in wires:
        ends[(w.start.x, w.start.y)] += 1
        ends[(w.end.x, w.end.y)] += 1
    juncs: set[tuple[float, float]] = set()
    for (x, y), n in ends.items():
        deg = n
        p = Point(x, y)
        for w in wires:
            if _strict_interior(p, w.start, w.end):
                deg += 2
        if deg >= 3:
            juncs.add((x, y))
    return [PlacedJunction(Point(x, y)) for x, y in juncs]


def _strict_interior(p: Point, a: Point, b: Point) -> bool:
    if abs(a.x - b.x) < 1e-6 and abs(p.x - a.x) < 1e-6:
        lo, hi = sorted((a.y, b.y))
        return lo + 1e-6 < p.y < hi - 1e-6
    if abs(a.y - b.y) < 1e-6 and abs(p.y - a.y) < 1e-6:
        lo, hi = sorted((a.x, b.x))
        return lo + 1e-6 < p.x < hi - 1e-6
    return False
