from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.core.config import GRID
from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Seg

Point = tuple[float, float]
Cell = tuple[int, int]


class RouteError(ValueError):
    pass


def snap_ok(v: float) -> bool:
    if _nat.loaded():
        return _nat.module().route_snap_ok(v, GRID)
    return abs(v / GRID - round(v / GRID)) < 1e-3


def cell_of(p: Point) -> Cell:
    if _nat.loaded():
        try:
            i, j = _nat.module().route_cell_of(p[0], p[1], GRID)
            return (int(i), int(j))
        except RuntimeError as exc:
            raise RouteError(f"point {p} is off the {GRID} mm grid") from exc
    if not (snap_ok(p[0]) and snap_ok(p[1])):
        raise RouteError(f"point {p} is off the {GRID} mm grid")
    return (round(p[0] / GRID), round(p[1] / GRID))


def point_of(c: Cell) -> Point:
    if _nat.loaded():
        x, y = _nat.module().route_point_of(int(c[0]), int(c[1]), GRID)
        return (float(x), float(y))
    return (round(c[0] * GRID, 3), round(c[1] * GRID, 3))


def cells_between(a: Point, b: Point) -> list[Cell]:
    if _nat.loaded():
        try:
            return [(int(i), int(j)) for i, j in
                    _nat.module().route_cells_between(a[0], a[1], b[0], b[1],
                                                      GRID)]
        except RuntimeError as exc:
            if "orthogonal" in str(exc):
                raise RouteError(f"segment {a}->{b} is not orthogonal") from exc
            raise RouteError(str(exc)) from exc
    ca, cb = cell_of(a), cell_of(b)
    if ca[0] != cb[0] and ca[1] != cb[1]:
        raise RouteError(f"segment {a}->{b} is not orthogonal")
    if ca[0] == cb[0]:
        lo, hi = sorted((ca[1], cb[1]))
        return [(ca[0], j) for j in range(lo, hi + 1)]
    lo, hi = sorted((ca[0], cb[0]))
    return [(i, ca[1]) for i in range(lo, hi + 1)]


class Grid:
    def __init__(self) -> None:
        self.owner: dict[Cell, str] = {}
        self._cpp = _nat.module().RouteGrid() if _nat.loaded() else None

    def claim(self, owner: str, cells: list[Cell], what: str = "") -> None:
        if self._cpp is not None:
            try:
                self._cpp.claim(owner, [(int(c[0]), int(c[1])) for c in cells],
                                what)
            except RuntimeError as exc:
                raise RouteError(str(exc)) from exc
        for c in cells:
            cur = self.owner.get(c)
            if cur is not None and cur != owner:
                raise RouteError(
                    f"cell {point_of(c)} contested: {cur!r} vs {owner!r} ({what})")
            self.owner[c] = owner

    def block_box(self, box: tuple[float, float, float, float]) -> None:
        if self._cpp is not None:
            self._cpp.block_box(box[0], box[1], box[2], box[3], GRID)
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
        if self._cpp is not None:
            return self._cpp.free_or(net, int(c[0]), int(c[1]))
        return self.owner.get(c) in (None, net)


@dataclass
class RoutedSheet:
    segs: list[Seg] = field(default_factory=list)
    junctions: list[Point] = field(default_factory=list)


@dataclass
class _NetGeom:
    legs: list[tuple[Point, Point]] = field(default_factory=list)
    pin_parts: dict[Point, set[str]] = field(default_factory=dict)
    power_pts: set[Point] = field(default_factory=set)
    label_pts: set[Point] = field(default_factory=set)
    bonds: list[tuple[Point, Point]] = field(default_factory=list)


def _leg_cells(a: Point, b: Point) -> list[Cell]:
    return cells_between(a, b)


def route(circuit: Circuit, placement, lib: Library) -> RoutedSheet:
    grid = Grid()

    net_of_pin: dict[str, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            net_of_pin[str(pr)] = net.name

    geoms: dict[str, _NetGeom] = {n: _NetGeom() for n in circuit.nets}

    pad_tips: dict[tuple[str, str], list[Point]] = {}
    for part in placement.parts:
        sdef = lib.get(part.lib_id)
        for pin in sdef.pins:
            tip = pin_page_position(pin, part.x, part.y, part.rotation)
            key = f"{part.ref}.{pin.number}"
            net = net_of_pin.get(key)
            owner = net if net is not None else f"nc:{key}"
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
    for (_ref, _num), tips in pad_tips.items():
        for a, b in zip(tips, tips[1:], strict=False):
            geoms[net_of_pin[f"{_ref}.{_num}"]].bonds.append((a, b))

    for pw in placement.powers:
        net = pw.net_name
        if net == "PWR_FLAG":
            raise RouteError(f"{pw.ref}: PWR_FLAG must carry net=<rail>")
        if net not in geoms:
            raise RouteError(f"power symbol {pw.ref} on undeclared net {net!r}")
        pt = (round(pw.x, 3), round(pw.y, 3))
        grid.claim(net, [cell_of(pt)], f"power {pw.ref}")
        geoms[net].power_pts.add(pt)

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

    for box in placement.boxes:
        grid.block_box((box.x0, box.y0, box.x1, box.y1))

    for net, paths in placement.plans.items():
        if net not in geoms:
            raise RouteError(f"plan for undeclared net {net!r}")
        for path in paths:
            for a, b in zip(path, path[1:], strict=False):
                a = (round(a[0], 3), round(a[1], 3))
                b = (round(b[0], 3), round(b[1], 3))
                if a == b:
                    continue
                grid.claim(net, _leg_cells(a, b), f"wire {net}")
                geoms[net].legs.append((a, b))

    for _net, g in geoms.items():
        anchors: set[Cell] = {cell_of(p) for p in g.label_pts}
        for a, b in g.legs:
            anchors.add(cell_of(a))
            anchors.add(cell_of(b))
        for _ in range(64):
            changed = False
            endpts: set[Cell] = set(anchors)
            for a, b in g.legs:
                endpts.add(cell_of(a))
                endpts.add(cell_of(b))
            out_legs: list[tuple[Point, Point]] = []
            for a, b in g.legs:
                cells = _leg_cells(a, b)
                ca, cb = cells[0], cells[-1]
                cut: Cell | None = None
                interior = cells[1:-1]
                interior_set = set(interior)
                for c in interior:
                    if c in endpts:
                        cut = c
                        break
                if cut is None:
                    for a2, b2 in g.legs:
                        if (a2, b2) == (a, b):
                            continue
                        for c2 in _leg_cells(a2, b2):
                            if c2 in interior_set:
                                cut = c2
                                break
                        if cut is not None:
                            break
                if cut is not None and cut != ca and cut != cb:
                    mp = point_of(cut)
                    out_legs.append((a, mp))
                    out_legs.append((mp, b))
                    changed = True
                else:
                    out_legs.append((a, b))
            g.legs = out_legs
            if not changed:
                break
        uniq: list[tuple[Point, Point]] = []
        seen_seg: set[tuple[Point, Point]] = set()
        for a, b in g.legs:
            if a == b:
                continue
            key = (a, b) if a <= b else (b, a)
            if key in seen_seg:
                continue
            seen_seg.add(key)
            uniq.append((a, b))
        g.legs = uniq

    for net, g in geoms.items():
        seen_interior: set[Cell] = set()
        endpoints: set[Cell] = set()
        for a, b in g.legs:
            endpoints.add(cell_of(a))
            endpoints.add(cell_of(b))
        for a, b in g.legs:
            interior = _leg_cells(a, b)[1:-1]
            for c in interior:
                if c in seen_interior or c in endpoints:
                    raise RouteError(
                        f"net {net}: leg {a}->{b} overlaps own geometry at "
                        f"{point_of(c)} (split legs at taps)")
                seen_interior.add(c)

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
                net_obj.net_class == NetClass.PORT and len(comps) > 1
                and all(comp & g.label_pts for comp in comps))
            if bridged:
                for comp in comps:
                    if not comp & g.label_pts:
                        raise RouteError(
                            f"label-bridged net {net}: islet "
                            f"{sorted(comp)[:3]}… has no {net} label — "
                            f"opens forbidden")
            else:
                while len(comps) > 1:
                    comps.sort(key=len, reverse=True)
                    path = _bfs_join(grid, net, comps[0], comps[1])
                    for a, b in zip(path, path[1:], strict=False):
                        grid.claim(net, _leg_cells(a, b), f"bfs {net}")
                        g.legs.append((a, b))
                    comps = _components(g)
            if net_obj.net_class == NetClass.PORT and not g.label_pts:
                raise RouteError(f"PORT net {net}: no label placed")
            if not bridged and comps and g.label_pts \
                    and not (comps[0] & g.label_pts):
                raise RouteError(f"PORT net {net}: label not on the drawn net")

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
        for pt, d in sorted(deg.items()):
            if d >= 3:
                out.junctions.append(pt)
    return out


def _stem_dir_py(pin_rot: int, part_rot: int) -> tuple[int, int]:
    sym = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[pin_rot % 360]
    import math
    r = math.radians(part_rot % 360)
    c, s = round(math.cos(r)), round(math.sin(r))
    return (sym[0] * c - sym[1] * s, -sym[0] * s - sym[1] * c)


def _stem_dir(pin_rot: int, part_rot: int) -> tuple[int, int]:
    if _nat.loaded():
        got = tuple(_nat.module().stem_dir(int(pin_rot), int(part_rot)))
        if _nat.trace():
            ref = _stem_dir_py(pin_rot, part_rot)
            if got != ref:
                raise AssertionError(
                    f"native stem_dir DIVERGENCE: cpp={got} python={ref}")
        return got
    return _stem_dir_py(pin_rot, part_rot)


def _components(g: _NetGeom) -> list[set[Point]]:
    pts: set[Point] = set(g.pin_parts) | g.power_pts | g.label_pts
    adj: dict[Point, set[Point]] = {p: set() for p in pts}
    for a, b in list(g.legs) + list(g.bonds):
        adj.setdefault(a, set())
        adj.setdefault(b, set())
        adj[a].add(b)
        adj[b].add(a)
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
            seen.add(q)
            comp.add(q)
            todo.extend(adj[q] - seen)
        comps.append(comp)
    return comps


def _bfs_join(grid: Grid, net: str, comp_a: set[Point],
              comp_b: set[Point]) -> list[Point]:
    if _nat.loaded() and grid._cpp is not None:
        starts = {cell_of(p) for p in comp_a}
        goals = {cell_of(p) for p in comp_b}
        try:
            return [tuple(p) for p in _nat.module().route_bfs_join(
                grid._cpp, net,
                [point_of(c) for c in starts],
                [point_of(c) for c in goals], GRID)]
        except RuntimeError as exc:
            raise RouteError(f"net {net}: no free corridor joins its parts "
                             f"— placement must expand") from exc
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
    way = [pts[0]]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        if not ((x0 == x1 == x2) or (y0 == y1 == y2)):
            way.append(pts[i])
    way.append(pts[-1])
    return way
