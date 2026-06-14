"""Exclusive-ownership grid router (1.27 mm integer grid).

INVARIANTS (structural, enforced during construction — never patched after):
- A grid cell is owned by AT MOST ONE net, ever. Vertex-disjoint nets can
  neither touch nor cross; a junction can only ever merge ONE net (LAW 0).
- Every wire endpoint lands EXACTLY on a pin / label-anchor / power-pin grid
  point (no eps anywhere; off-grid is an error at intake, not a mis-land later).
- Junction dots only where the SAME net meets with degree >= 3.
- POWER/GROUND nets terminate at power symbols (pin-exact or short exclusive
  stubs); each drawn islet of such a net must carry a power symbol — KiCad
  merges them by name. SIGNAL/PORT nets must be ONE drawn component; a net
  that cannot be drawn raises RouteError so PLACEMENT expands — rules never
  relax, labels never substitute for internal wiring, NC is never a fallback.

Placement hands over explicit waypoint paths ("plans") for every connection
plus the blocked geometry (bodies, all text boxes). The router claims cells
for the plans, BFS-routes any residual connection over free cells only, and
proves coverage net-by-net.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import GRID, Library, pin_page_position
from schgen.verify.visual_gate import Seg

Point = tuple[float, float]
Cell = tuple[int, int]


class RouteError(ValueError):
    pass


def snap_ok(v: float) -> bool:
    return abs(v / GRID - round(v / GRID)) < 1e-3


def cell_of(p: Point) -> Cell:
    if not (snap_ok(p[0]) and snap_ok(p[1])):
        raise RouteError(f"point {p} is off the {GRID} mm grid")
    return (round(p[0] / GRID), round(p[1] / GRID))


def point_of(c: Cell) -> Point:
    return (round(c[0] * GRID, 3), round(c[1] * GRID, 3))


def cells_between(a: Point, b: Point) -> list[Cell]:
    """All grid cells on the orthogonal segment a->b, inclusive."""
    ca, cb = cell_of(a), cell_of(b)
    if ca[0] != cb[0] and ca[1] != cb[1]:
        raise RouteError(f"segment {a}->{b} is not orthogonal")
    if ca[0] == cb[0]:
        lo, hi = sorted((ca[1], cb[1]))
        return [(ca[0], j) for j in range(lo, hi + 1)]
    lo, hi = sorted((ca[0], cb[0]))
    return [(i, ca[1]) for i in range(lo, hi + 1)]


class Grid:
    """Cell -> owner map. Owners: net names, 'nc:<pin>', or '#blocked'."""

    def __init__(self) -> None:
        self.owner: dict[Cell, str] = {}

    def claim(self, owner: str, cells: list[Cell], what: str = "") -> None:
        for c in cells:
            cur = self.owner.get(c)
            if cur is not None and cur != owner:
                raise RouteError(
                    f"cell {point_of(c)} contested: {cur!r} vs {owner!r} ({what})")
            self.owner[c] = owner

    def block_box(self, box: tuple[float, float, float, float]) -> None:
        """Block all UNOWNED cells whose center lies strictly inside box."""
        x0, y0, x1, y1 = box
        i0, i1 = int(x0 / GRID) - 1, int(x1 / GRID) + 2
        j0, j1 = int(y0 / GRID) - 1, int(y1 / GRID) + 2
        eps = 1e-6
        for i in range(i0, i1):
            for j in range(j0, j1):
                x, y = i * GRID, j * GRID
                if x0 + eps < x < x1 - eps and y0 + eps < y < y1 - eps:
                    self.owner.setdefault((i, j), "#blocked")

    def free_or(self, net: str, c: Cell) -> bool:
        return self.owner.get(c) in (None, net)


@dataclass
class RoutedSheet:
    segs: list[Seg] = field(default_factory=list)
    junctions: list[Point] = field(default_factory=list)


@dataclass
class _NetGeom:
    legs: list[tuple[Point, Point]] = field(default_factory=list)
    # terminal points by flavor
    pin_parts: dict[Point, set[str]] = field(default_factory=dict)   # part refs
    power_pts: set[Point] = field(default_factory=set)
    label_pts: set[Point] = field(default_factory=set)
    # same-pad bonds: a symbol carrying DUPLICATE pin numbers (flow-through
    # parts, e.g. an inline ESD companion whose TMDS line enters one edge and
    # leaves the other) exposes ONE physical pad at several geometry points.
    # KiCad nets them as one pin (duplicate_pin_numbers_are_jumpers — proven
    # against kicad-cli netlist export); the connectivity proof must use the
    # same electrical truth. Bonds add adjacency only — no cells, no wires.
    bonds: list[tuple[Point, Point]] = field(default_factory=list)


def _leg_cells(a: Point, b: Point) -> list[Cell]:
    return cells_between(a, b)


def route(circuit: Circuit, placement, lib: Library) -> RoutedSheet:
    """``placement`` duck-type: .parts (PlacedPart), .powers (PlacedPower),
    .hlabels (HierLabel), .plans {net: [path,...]}, .boxes (visual Box list)."""
    grid = Grid()

    # ---- net lookup ---------------------------------------------------------
    net_of_pin: dict[str, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            net_of_pin[str(pr)] = net.name

    geoms: dict[str, _NetGeom] = {n: _NetGeom() for n in circuit.nets}

    # ---- 1. claim every component pin stem for its net (or NC owner) --------
    pad_tips: dict[tuple[str, str], list[Point]] = {}   # (ref, number) -> tips
    for part in placement.parts:
        sdef = lib.get(part.lib_id)
        for pin in sdef.pins:
            tip = pin_page_position(pin, part.x, part.y, part.rotation)
            key = f"{part.ref}.{pin.number}"
            net = net_of_pin.get(key)
            owner = net if net is not None else f"nc:{key}"
            # cells from the tip toward the body root, in grid steps
            steps = int(pin.length / GRID + 1e-6)
            cells = [cell_of(tip)]
            dx, dy = _stem_dir(pin.rotation, part.rotation)
            for k in range(1, steps + 1):
                cells.append(cell_of((round(tip[0] + dx * k * GRID, 3),
                                      round(tip[1] + dy * k * GRID, 3))))
            grid.claim(owner, cells, f"stem {key}")
            if net is not None:
                g = geoms[net]
                g.pin_parts.setdefault(tip, set()).add(part.ref)
                pad_tips.setdefault((part.ref, pin.number), []).append(tip)
    # duplicate pin numbers on one part = ONE physical pad (KiCad jumper-pin
    # semantics): bond their tips so connectivity is judged electrically
    for (_ref, _num), tips in pad_tips.items():
        for a, b in zip(tips, tips[1:]):
            geoms[net_of_pin[f"{_ref}.{_num}"]].bonds.append((a, b))

    # ---- 2. power symbol pins -----------------------------------------------
    for pw in placement.powers:
        net = pw.net_name
        if net == "PWR_FLAG":
            raise RouteError(f"{pw.ref}: PWR_FLAG must carry net=<rail>")
        if net not in geoms:
            raise RouteError(f"power symbol {pw.ref} on undeclared net {net!r}")
        pt = (round(pw.x, 3), round(pw.y, 3))
        grid.claim(net, [cell_of(pt)], f"power {pw.ref}")
        geoms[net].power_pts.add(pt)

    # ---- 3. label anchors (hierarchical AND local: both are KiCad
    #         connectivity anchors that merge a net by name) ------------------
    for h in placement.hlabels:
        if h.name not in geoms:
            raise RouteError(f"label {h.name!r} is not a declared net")
        pt = (round(h.x, 3), round(h.y, 3))
        grid.claim(h.name, [cell_of(pt)], f"label {h.name}")
        geoms[h.name].label_pts.add(pt)
    for ll in getattr(placement, "llabels", []):
        if ll.name not in geoms:
            raise RouteError(f"local label {ll.name!r} is not a declared net")
        pt = (round(ll.x, 3), round(ll.y, 3))
        grid.claim(ll.name, [cell_of(pt)], f"llabel {ll.name}")
        geoms[ll.name].label_pts.add(pt)

    # ---- 4. block all body/text geometry (never over an owned cell) ---------
    for box in placement.boxes:
        grid.block_box((box.x0, box.y0, box.x1, box.y1))

    # ---- 5. claim the planned wire paths -------------------------------------
    for net, paths in placement.plans.items():
        if net not in geoms:
            raise RouteError(f"plan for undeclared net {net!r}")
        for path in paths:
            for a, b in zip(path, path[1:]):
                a = (round(a[0], 3), round(a[1], 3))
                b = (round(b[0], 3), round(b[1], 3))
                if a == b:
                    continue
                grid.claim(net, _leg_cells(a, b), f"wire {net}")
                geoms[net].legs.append((a, b))

    # a label anchored mid-wire is electrically ON the wire: split the leg
    # at the anchor so the connectivity graph sees it
    for net, g in geoms.items():
        for lp in sorted(g.label_pts):          # sorted: deterministic split order
            out_legs: list[tuple[Point, Point]] = []
            for a, b in g.legs:
                if lp != a and lp != b and cell_of(lp) in _leg_cells(a, b):
                    out_legs.append((a, lp))
                    out_legs.append((lp, b))
                else:
                    out_legs.append((a, b))
            g.legs = out_legs

    # same-net discipline: leg interiors must be virgin (no double-draw,
    # no unsplit T — a tap point must be a shared LEG ENDPOINT)
    for net, g in geoms.items():
        seen_interior: set[Cell] = set()
        endpoints: set[Cell] = set()
        for a, b in g.legs:
            endpoints.add(cell_of(a)); endpoints.add(cell_of(b))
        for a, b in g.legs:
            interior = _leg_cells(a, b)[1:-1]
            for c in interior:
                if c in seen_interior or c in endpoints:
                    raise RouteError(
                        f"net {net}: leg {a}->{b} overlaps own geometry at "
                        f"{point_of(c)} (split legs at taps)")
                seen_interior.add(c)

    # ---- 6. connectivity proof + BFS completion ------------------------------
    for net_obj in circuit.nets.values():
        net = net_obj.name
        g = geoms[net]
        comps = _components(g)
        if net_obj.net_class in (NetClass.POWER, NetClass.GROUND):
            for comp in comps:
                if not comp & g.power_pts:
                    raise RouteError(
                        f"power net {net}: drawn islet {sorted(comp)[:3]}… has "
                        f"no {net} power symbol — opens forbidden")
        else:
            bridged = net in getattr(placement, "label_bridged", set()) or (
                # a PORT net whose every islet carries its hier label is
                # merged by NAME (cable-flip pads labeled on both sides);
                # the netlist gate proves the merge
                net_obj.net_class == NetClass.PORT and len(comps) > 1
                and all(comp & g.label_pts for comp in comps))
            if bridged:
                # placement chose the datasheet label idiom for this net
                # (shunt/ESD banks, pull-up ranks, demoted channels): every
                # drawn islet must carry a label anchor — KiCad merges the
                # islets by NAME, and the netlist gate proves the merge.
                for comp in comps:
                    if not comp & g.label_pts:
                        raise RouteError(
                            f"label-bridged net {net}: islet "
                            f"{sorted(comp)[:3]}… has no {net} label — "
                            f"opens forbidden")
            else:
                while len(comps) > 1:
                    # wire-heavy mandate: BFS-join the two nearest components
                    comps.sort(key=len, reverse=True)
                    path = _bfs_join(grid, net, comps[0], comps[1])
                    for a, b in zip(path, path[1:]):
                        grid.claim(net, _leg_cells(a, b), f"bfs {net}")
                        g.legs.append((a, b))
                    comps = _components(g)
            if net_obj.net_class == NetClass.PORT and not g.label_pts:
                raise RouteError(f"PORT net {net}: no label placed")
            if not bridged and comps and g.label_pts \
                    and not (comps[0] & g.label_pts):
                raise RouteError(f"PORT net {net}: label not on the drawn net")

    # ---- 7. junctions: same-net degree >= 3 ----------------------------------
    out = RoutedSheet()
    for net_obj in circuit.nets.values():
        g = geoms[net_obj.name]
        deg: dict[Point, int] = {}
        for a, b in g.legs:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
            out.segs.append(Seg(a[0], a[1], b[0], b[1], net_obj.name))
        for pt, parts in g.pin_parts.items():
            deg[pt] = deg.get(pt, 0) + len(parts)
        for pt in g.power_pts:
            deg[pt] = deg.get(pt, 0) + 1
        # sorted: junction EMIT order seeds the uuid ordinals (emit.py), so it
        # must not depend on dict/set iteration order — sort by coordinate so
        # output is byte-identical regardless of PYTHONHASHSEED (selftest gates
        # this with a cross-seed build).
        for pt, d in sorted(deg.items()):
            if d >= 3:
                out.junctions.append(pt)
    return out


def _stem_dir(pin_rot: int, part_rot: int) -> tuple[int, int]:
    """Unit grid direction from pin TIP toward the symbol body, page coords."""
    # pin rotation: direction the pin points (toward the body), symbol space
    sym = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[pin_rot % 360]
    import math
    r = math.radians(part_rot % 360)
    c, s = round(math.cos(r)), round(math.sin(r))
    return (sym[0] * c - sym[1] * s, -sym[0] * s - sym[1] * c)


def _components(g: _NetGeom) -> list[set[Point]]:
    """Connected components over leg endpoints + terminal points."""
    pts: set[Point] = set(g.pin_parts) | g.power_pts | g.label_pts
    adj: dict[Point, set[Point]] = {p: set() for p in pts}
    for a, b in list(g.legs) + list(g.bonds):
        adj.setdefault(a, set()); adj.setdefault(b, set())
        adj[a].add(b); adj[b].add(a)
    seen: set[Point] = set()
    comps: list[set[Point]] = []
    for p in adj:
        if p in seen:
            continue
        comp, todo = set(), [p]
        while todo:
            q = todo.pop()
            if q in seen:
                continue
            seen.add(q); comp.add(q)
            todo.extend(adj[q] - seen)
        comps.append(comp)
    return comps


def _bfs_join(grid: Grid, net: str, comp_a: set[Point],
              comp_b: set[Point]) -> list[Point]:
    """Shortest orthogonal path over free/own cells from comp_a to comp_b,
    returned as corner waypoints. RouteError if no path exists.

    The search is BOUNDED to the sheet's occupied extent plus a margin:
    the grid is an infinite free plane, so an enclosed component would
    otherwise flood outward forever instead of failing fast back to the
    placement feasibility loop."""
    starts = {cell_of(p) for p in comp_a}
    goals = {cell_of(p) for p in comp_b}
    occ = list(grid.owner) + list(starts) + list(goals)
    margin = 12
    i0 = min(c[0] for c in occ) - margin
    i1 = max(c[0] for c in occ) + margin
    j0 = min(c[1] for c in occ) - margin
    j1 = max(c[1] for c in occ) + margin
    prev: dict[Cell, Cell | None] = {c: None for c in starts}
    q: deque[Cell] = deque(starts)
    hit: Cell | None = None
    while q:
        c = q.popleft()
        if c in goals:
            hit = c
            break
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + d[0], c[1] + d[1])
            if not (i0 <= n[0] <= i1 and j0 <= n[1] <= j1):
                continue
            if n in prev or not grid.free_or(net, n):
                continue
            prev[n] = c
            q.append(n)
    if hit is None:
        raise RouteError(f"net {net}: no free corridor joins its parts "
                         f"— placement must expand")
    chain: list[Cell] = [hit]
    while prev[chain[-1]] is not None:
        chain.append(prev[chain[-1]])          # type: ignore[arg-type]
    chain.reverse()
    pts = [point_of(c) for c in chain]
    # compress collinear runs to corner waypoints
    way = [pts[0]]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        if not ((x0 == x1 == x2) or (y0 == y1 == y2)):
            way.append(pts[i])
    way.append(pts[-1])
    return way
