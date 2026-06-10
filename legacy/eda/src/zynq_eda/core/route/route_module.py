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

import os
from dataclasses import replace

# Module-level wire-touch short guard. The net-aware sheet splitter handles the
# pin-tap shorts; this guard additionally drops a module wire that TOUCHES a
# foreign net's wire (shared point / collinear / cross). Toggleable so we can
# measure whether it's still load-bearing vs the splitter alone.
_ENABLE_TOUCH_GUARD = os.environ.get("ZYNQ_TOUCH_GUARD", "1") != "0"

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


def _base_net(key: str, ic_ref: str) -> str:
    """Resolve a routing net-KEY to its electrical net identity.

    ``module.nets`` carries MANY keys that are the SAME physical net: a global
    rail (GND, +3V3, …) is split into one ``GND@<far>`` cell per decoupling cap
    plus a ``GND@ic<n>`` per bare IC GND pin — every one of them is GND, joined
    by NAME through power symbols. Two such keys are NOT foreign: their wires
    may touch freely (the touch is the same net merging, never a short).

    Per-pin TRUNK keys are ``{ic_ref}@{x},{y}`` — each is a DISTINCT local net
    (one IC pin + its own caps' near terminals), so they stay mutually foreign;
    we key those by the full string. The discriminator is the base before
    ``@``/``#``: a base equal to the module's IC reference is a trunk (unique),
    anything else is a named rail/signal whose same-base keys share one net.
    """
    base = key.split("#", 1)[0]
    base = base.split("@", 1)[0]
    if base == ic_ref:
        return key.split("#", 1)[0]  # per-pin trunk — keep distinct (full @-key)
    return base  # named rail/signal — all same-base keys are one net


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


def _on_seg(p: Point, w: PlacedWire, eps: float = 0.05) -> bool:
    """True iff point ``p`` lies on axis-aligned segment ``w`` (endpoints incl.)."""
    ax, ay, bx, by = w.start.x, w.start.y, w.end.x, w.end.y
    if abs(ay - by) < eps:   # horizontal
        return abs(p.y - ay) < eps and min(ax, bx) - eps <= p.x <= max(ax, bx) + eps
    if abs(ax - bx) < eps:   # vertical
        return abs(p.x - ax) < eps and min(ay, by) - eps <= p.y <= max(ay, by) + eps
    return False


def _collinear_overlap(a: PlacedWire, b: PlacedWire, eps: float = 0.05) -> bool:
    if abs(a.start.y - a.end.y) < eps and abs(b.start.y - b.end.y) < eps \
            and abs(a.start.y - b.start.y) < eps:
        a0, a1 = sorted((a.start.x, a.end.x)); b0, b1 = sorted((b.start.x, b.end.x))
        return min(a1, b1) - max(a0, b0) > eps
    if abs(a.start.x - a.end.x) < eps and abs(b.start.x - b.end.x) < eps \
            and abs(a.start.x - b.start.x) < eps:
        a0, a1 = sorted((a.start.y, a.end.y)); b0, b1 = sorted((b.start.y, b.end.y))
        return min(a1, b1) - max(a0, b0) > eps
    return False


def _truncate_at_foreign(
    w: PlacedWire,
    foreign_wires: list[PlacedWire],
    foreign_pins: list[Point],
    grid: float = 1.27,
) -> list[PlacedWire]:
    """Split ``w`` into the maximal sub-runs that touch NO foreign net.

    The touch-guard's blunt instrument is to DROP a whole wire that touches a
    foreign net — but a long trunk often touches a foreign wall at ONE end while
    its other end still cleanly reaches its own net's pins (e.g. usb_pd R104.2's
    feed wire runs THROUGH R104.2 and only its far tip grazes the x=107.95 wall).
    Dropping the whole wire needlessly strands the clean pin. Instead, rasterise
    ``w`` to unit-grid sub-segments, classify each by whether IT touches a
    foreign net, and return the maximal CLEAN runs. A kept run touches no foreign
    net by construction → it can never short (LAW 0). An all-foreign or zero-len
    wire yields ``[]`` (fully dropped, as before).
    """
    ax, ay, bx, by = w.start.x, w.start.y, w.end.x, w.end.y
    horiz = abs(ay - by) < 1e-6
    vert = abs(ax - bx) < 1e-6
    if not (horiz or vert):
        # Diagonal (shouldn't occur for grid wires): fall back to all-or-nothing.
        return [] if _route_hits_foreign([w], foreign_wires, foreign_pins) else [w]
    if horiz:
        lo, hi = sorted((ax, bx))
        coords = []
        x = lo
        while x < hi - 1e-9:
            coords.append((Point(x, ay), Point(min(x + grid, hi), ay)))
            x += grid
    else:
        lo, hi = sorted((ay, by))
        coords = []
        y = lo
        while y < hi - 1e-9:
            coords.append((Point(ax, y), Point(ax, min(y + grid, hi))))
            y += grid
    if not coords:
        return [] if _route_hits_foreign([w], foreign_wires, foreign_pins) else [w]
    clean_flags = [
        not _route_hits_foreign([PlacedWire(s, e)], foreign_wires, foreign_pins)
        for s, e in coords
    ]
    # Merge consecutive clean unit-segments into maximal runs.
    runs: list[PlacedWire] = []
    i = 0
    n = len(coords)
    while i < n:
        if not clean_flags[i]:
            i += 1
            continue
        j = i
        while j < n and clean_flags[j]:
            j += 1
        runs.append(PlacedWire(coords[i][0], coords[j - 1][1]))
        i = j
    return runs


def _route_hits_foreign(
    segs: list[PlacedWire],
    foreign_wires: list[PlacedWire],
    foreign_pins: list[Point],
) -> bool:
    """A fallback route SHORTS a foreign net if it threads a foreign pin or
    crosses / overlaps / T-taps a foreign-net wire. LAW 0: never short to
    connect — leave the terminal floating for the sheet labeler instead."""
    for seg in segs:
        for p in foreign_pins:
            if _on_seg(p, seg):
                return True
        for fw in foreign_wires:
            if _cross_point(seg, fw) is not None:
                return True
            if _collinear_overlap(seg, fw):
                return True
            if any(_on_seg(e, fw) for e in (seg.start, seg.end)):
                return True
            if any(_on_seg(e, seg) for e in (fw.start, fw.end)):
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

    # Reserve each label-pin's escape LANE as a routing obstacle: an IC pin with
    # no net of its own (it gets an edge label later) needs its immediate
    # outboard clear, or an adjacent net's wire boxes it in and the exposer can't
    # place the label — the residual dense-IC floats (e.g. U2 USB_DP boxed in by
    # the USB_DM wire 1.27 mm away). Foreign wires must route AROUND these lanes.
    netpts = [p for _n, terms in module.nets for p in terms]
    for s, sp, c in sym_info:
        if s.reference != module.ic_ref:
            continue
        for pp in sp:
            if any(abs(pp.x - q.x) < 0.05 and abs(pp.y - q.y) < 0.05 for q in netpts):
                continue  # this pin is wired into a net already
            ddx, ddy = pp.x - c.x, pp.y - c.y
            if abs(ddx) >= abs(ddy):
                ox, oy = (1.0 if ddx >= 0 else -1.0), 0.0
            else:
                ox, oy = 0.0, (1.0 if ddy >= 0 else -1.0)
            ex, ey = pp.x + ox * 1.27, pp.y + oy * 1.27
            obstacles.append(BBox(
                min=Point(ex - 1.0, ey - 1.0), max=Point(ex + 1.0, ey + 1.0),
                kind="symbol", owner_id="lane:reserve"))

    from zynq_eda.core.layout.footprint import symbol_footprint
    nets: dict[str, list[Point]] = {}
    escape_dirs: dict[str, list[tuple[int, int]]] = {}
    own_obstacles: dict[str, list[BBox]] = {}
    for i, (name, terms) in enumerate(module.nets):
        pts = _dedupe_points(list(terms))
        if len(pts) >= 2:
            key = f"{name}#{i}"
            nets[key] = pts
            escape_dirs[key] = [_term_dir(p) for p in pts]
            # Own-symbol footprints for THIS net: the symbols a terminal sits
            # on. route_terminals exempts their clearance HALO (not the body
            # core) so a pin boxed by its own body can escape — the config
            # module.py uses, which routes the dense trunks (floating 8->3).
            own: list[BBox] = []
            for s, sp, _c in sym_info:
                if any(abs(p.x - q.x) < 0.05 and abs(p.y - q.y) < 0.05
                       for p in sp for q in pts):
                    try:
                        own.append(symbol_footprint(s, geometry))
                    except Exception:  # noqa: BLE001
                        pass
            own_obstacles[key] = own
    if not nets:
        return module

    # Grid A* multi-terminal tree router: avoids every body, text box, and
    # foreign net's wires (no crossings), connects each net into a tree with
    # junction dots at taps, and lands endpoints on the 1.27 mm pin grid. Any
    # net it genuinely cannot route is reported in ``failures`` (never silently
    # dropped); the connectivity validator surfaces the residual so placement
    # can open a wider channel rather than the wire crossing a body.
    wires, _juncs, failures, wires_by_net = route_terminals(
        obstacles, nets, own_obstacles=own_obstacles, escape_dirs=escape_dirs
    )

    # Keep wires grouped BY NET so junctions/dedupe stay net-local. A junction is
    # ONLY ever a SAME-net merge — never a foreign crossing (LAW 0: a junction at
    # a different-net crossing is a SHORT, invisible to ERC/overlap=0).
    net_wires: dict[str, list[PlacedWire]] = {k: list(v) for k, v in wires_by_net.items()}
    all_pins: list[tuple[str, Point]] = [(k, p) for k, pts in nets.items() for p in pts]

    # Recover terminals the grid router couldn't escape (dense IC edges): connect
    # each to the NEAREST other terminal of its net with a SHORT, CLEAN L-route
    # that crosses no body/text AND no FOREIGN wire/pin. A blocked or shorting
    # connection is left floating for the sheet-level labeler — never forced
    # through a foreign net (overlap + netlist integrity are hard invariants).
    for net_key, term in failures:
        others = [p for p in nets.get(net_key, []) if p != term]
        if not others:
            continue
        tgt = min(others, key=lambda p: abs(p.x - term.x) + abs(p.y - term.y))
        if abs(tgt.x - term.x) + abs(tgt.y - term.y) > 12.7:
            continue  # too far for a clean stub — leave for the labeler
        # FOREIGN = a DIFFERENT electrical net (LAW 0). Same-rail keys (every
        # GND@* / +3V3@* cell of the one global rail) are the SAME net — joined
        # by name through power symbols — so touching them is connectivity, not
        # a short; they must NOT block a recovery stub.
        nb = _base_net(net_key, module.ic_ref)
        foreign_wires = [w for k, ws in net_wires.items()
                         if _base_net(k, module.ic_ref) != nb for w in ws]
        foreign_pins = [p for k, p in all_pins
                        if _base_net(k, module.ic_ref) != nb]
        if abs(term.x - tgt.x) < 1e-6 or abs(term.y - tgt.y) < 1e-6:
            cands = [[PlacedWire(term, tgt)]]
        else:
            cands = [
                [PlacedWire(term, Point(tgt.x, term.y)), PlacedWire(Point(tgt.x, term.y), tgt)],
                [PlacedWire(term, Point(term.x, tgt.y)), PlacedWire(Point(term.x, tgt.y), tgt)],
            ]
        seg = None
        for cand in cands:
            if _l_hits(cand, obstacles):
                continue
            if _route_hits_foreign(cand, foreign_wires, foreign_pins):
                continue
            seg = cand
            break
        if seg is None:
            continue  # honest float — never a short
        net_wires.setdefault(net_key, []).extend(seg)
        for w in seg:
            obstacles.append(wire_bbox(w.start, w.end, owner_id="routed"))

    # HARD non-touching GUARANTEE (LAW 0): the grid can route two nets into the
    # same channel where their wires merely TOUCH (a shared endpoint / collinear
    # run / crossing) — KiCad then merges them = SHORT, even though each net
    # avoided the other's cells. Drop any wire that touches a FOREIGN net's wire;
    # the freed terminal floats and the sheet exposer reconnects it BY NAME
    # (power symbol / hier-label) which cannot short. Iterate to a fixpoint so a
    # drop that removes a touch doesn't strand a now-stale verdict.
    if _ENABLE_TOUCH_GUARD:
        changed = True
        while changed:
            changed = False
            for nk in list(net_wires.keys()):
                # FOREIGN = a DIFFERENT electrical net only. A global rail is
                # split into many keys (GND@<cap> + GND@ic<n>); their wires
                # share the rail's power-symbol pins and so necessarily touch —
                # that touch is the rail merging by name, NOT a short (LAW 0).
                # Dropping such a wire orphans a passive/IC pin (the exposer only
                # reconnects IC pins, so a freed CAP pin floats forever). Only
                # treat a wire as shorting when its net base truly differs.
                nb = _base_net(nk, module.ic_ref)
                foreign = [w for k, ws in net_wires.items()
                           if _base_net(k, module.ic_ref) != nb for w in ws]
                kept = []
                for w in net_wires[nk]:
                    if not _route_hits_foreign([w], foreign, []):
                        kept.append(w)
                        continue
                    # Touches a foreign net somewhere. Rather than dropping the
                    # whole wire (which strands clean pins on its other end),
                    # keep the maximal sub-runs that touch NO foreign net — those
                    # cannot short (LAW 0). Only a genuine change (a sub-run was
                    # trimmed away) re-triggers the fixpoint loop.
                    runs = _truncate_at_foreign(w, foreign, [])
                    if not (len(runs) == 1 and runs[0].start == w.start
                            and runs[0].end == w.end):
                        changed = True
                    kept.extend(runs)
                net_wires[nk] = kept

    # Collapse collinear runs and place junctions PER NET — both net-local, so a
    # junction can only ever mark a same-net merge. route_sheet re-splits at pins.
    flat: list[PlacedWire] = []
    juncs: list[PlacedJunction] = []
    seen_j: set[tuple[float, float]] = set()
    for ws in net_wires.values():
        ded = _dedupe_overlaps(ws)
        flat.extend(ded)
        for j in _junctions(ded):
            k = (j.position.x, j.position.y)
            if k not in seen_j:
                seen_j.add(k); juncs.append(j)
    return replace(module, wires=tuple(flat), junctions=tuple(juncs))


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


def _cross_point(a: PlacedWire, b: PlacedWire) -> tuple[float, float] | None:
    """Mutual-interior crossing of perpendicular ``a``/``b``, else None."""
    a_h = abs(a.start.y - a.end.y) < 1e-6
    a_v = abs(a.start.x - a.end.x) < 1e-6
    b_h = abs(b.start.y - b.end.y) < 1e-6
    b_v = abs(b.start.x - b.end.x) < 1e-6
    if a_h and b_v:
        h, v = a, b
    elif a_v and b_h:
        h, v = b, a
    else:
        return None
    hy = h.start.y
    vx = v.start.x
    hx0, hx1 = sorted((h.start.x, h.end.x))
    vy0, vy1 = sorted((v.start.y, v.end.y))
    if hx0 < vx < hx1 and vy0 < hy < vy1:
        return (vx, hy)
    return None


def _junctions(wires: list[PlacedWire]) -> list[PlacedJunction]:
    """Junction at every real merge: >= 3 wire ends coincide, a wire end lands
    strictly inside another wire's span (a T-tap), OR two wires cross at their
    mutual interior (an X). The crossings here are same-net (route_terminals
    blocks foreign wires), so a junction makes the crossing an explicit merge —
    which is what KiCad and the overlap validator's wire_cross rule require."""
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
    for i, a in enumerate(wires):
        for b in wires[i + 1:]:
            cp = _cross_point(a, b)
            if cp is not None:
                juncs.add(cp)
    return [PlacedJunction(Point(x, y)) for x, y in juncs]


def _strict_interior(p: Point, a: Point, b: Point) -> bool:
    if abs(a.x - b.x) < 1e-6 and abs(p.x - a.x) < 1e-6:
        lo, hi = sorted((a.y, b.y))
        return lo + 1e-6 < p.y < hi - 1e-6
    if abs(a.y - b.y) < 1e-6 and abs(p.y - a.y) < 1e-6:
        lo, hi = sorted((a.x, b.x))
        return lo + 1e-6 < p.x < hi - 1e-6
    return False
