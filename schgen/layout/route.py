from __future__ import annotations

from dataclasses import asdict, dataclass, field

from schgen.core import native as _nat
from schgen.core.config import GRID
from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify.visual_gate import Seg

Point = tuple[float, float]
Cell = tuple[int, int]


class RouteError(ValueError):
    pass


def snap_ok(v: float) -> bool:
    return _nat.module().route_snap_ok(v, GRID)


def cell_of(p: Point) -> Cell:
    try:
        i, j = _nat.module().route_cell_of(p[0], p[1], GRID)
        return (int(i), int(j))
    except RuntimeError as exc:
        raise RouteError(f"point {p} is off the {GRID} mm grid") from exc


def point_of(c: Cell) -> Point:
    x, y = _nat.module().route_point_of(int(c[0]), int(c[1]), GRID)
    return (float(x), float(y))


def cells_between(a: Point, b: Point) -> list[Cell]:
    try:
        return [(int(i), int(j)) for i, j in
                _nat.module().route_cells_between(a[0], a[1], b[0], b[1], GRID)]
    except RuntimeError as exc:
        if "orthogonal" in str(exc):
            raise RouteError(f"segment {a}->{b} is not orthogonal") from exc
        raise RouteError(str(exc)) from exc


class Grid:
    def __init__(self) -> None:
        self._cpp = _nat.module().RouteGrid()

    @property
    def owner(self) -> dict[Cell, str]:
        """Read-only ownership snapshot for diagnostics."""
        return {(i, j): owner for i, j, owner in self._cpp.owners()}

    def claim(self, owner: str, cells: list[Cell], what: str = "") -> None:
        try:
            self._cpp.claim(owner, [(int(c[0]), int(c[1])) for c in cells], what)
        except RuntimeError as exc:
            raise RouteError(str(exc)) from exc

    def block_box(self, box: tuple[float, float, float, float]) -> None:
        self._cpp.block_box(box[0], box[1], box[2], box[3], GRID)

    def free_or(self, net: str, c: Cell) -> bool:
        return self._cpp.free_or(net, int(c[0]), int(c[1]))


@dataclass
class RoutedSheet:
    segs: list[Seg] = field(default_factory=list)
    junctions: list[Point] = field(default_factory=list)


@dataclass
class _NetGeom:
    """Compatibility record; connectivity is calculated by the native core."""
    legs: list[tuple[Point, Point]] = field(default_factory=list)
    pin_parts: dict[Point, set[str]] = field(default_factory=dict)
    power_pts: set[Point] = field(default_factory=set)
    label_pts: set[Point] = field(default_factory=set)
    bonds: list[tuple[Point, Point]] = field(default_factory=list)


def _leg_cells(a: Point, b: Point) -> list[Cell]:
    return cells_between(a, b)


def route(circuit: Circuit, placement, lib: Library) -> RoutedSheet:
    """Transport placed geometry to the complete native schematic router."""
    # Routing historically reads nets only, and supports intermediate circuits.
    # Do not serialize unrelated part fields/hints or add an electrical gate.
    circuit_ir = {"nets": [
        {"name": net.name, "net_class": net.net_class.value,
         "pins": [{"ref": pin.ref, "pin": pin.pin} for pin in net.pins]}
        for net in circuit.nets.values()
    ]}
    placed = {
        name: [asdict(item) for item in getattr(placement, name, [])]
        for name in ("parts", "powers", "hlabels", "llabels", "no_connects",
                     "boxes")
    }
    placed.update(plans=placement.plans,
                  label_bridged=list(getattr(placement, "label_bridged", ())))
    native = _nat.module()
    try:
        segs, junctions = native.schematic_route(circuit_ir, placed, lib.get)
    except native.SchematicRouteError as exc:
        raise RouteError(str(exc)) from exc
    return RoutedSheet([Seg(*row) for row in segs],
                       [tuple(point) for point in junctions])


def _stem_dir(pin_rot: int, part_rot: int) -> tuple[int, int]:
    return tuple(_nat.module().stem_dir(int(pin_rot), int(part_rot)))


def _components(g: _NetGeom) -> list[set[Point]]:
    native = _nat.module()
    try:
        comps = native.schematic_route_components(
            g.legs, list(g.pin_parts), list(g.power_pts), list(g.label_pts),
            g.bonds)
    except native.SchematicRouteError as exc:
        raise RouteError(str(exc)) from exc
    return [{tuple(point) for point in comp} for comp in comps]


def _bfs_join(grid: Grid, net: str, comp_a: set[Point],
              comp_b: set[Point]) -> list[Point]:
    native = _nat.module()
    try:
        return [tuple(point) for point in native.schematic_route_join(
            grid._cpp, net, list(comp_a), list(comp_b))]
    except native.SchematicRouteError as exc:
        raise RouteError(str(exc)) from exc
