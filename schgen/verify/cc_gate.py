from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core.model import Circuit, PinRef
from schgen.core.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Seg, _point_on_seg

_QUANT = 1000.0


def _key(x: float, y: float) -> tuple[int, int]:
    return (round(x * _QUANT), round(y * _QUANT))


@dataclass
class _Node:
    key: tuple[int, int]
    x: float
    y: float
    pins: set = field(default_factory=set)
    labels: set = field(default_factory=set)
    powers: set = field(default_factory=set)


class _UF:
    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, k: tuple[int, int]) -> tuple[int, int]:
        self.parent.setdefault(k, k)
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:
            self.parent[k], k = root, self.parent[k]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo


@dataclass
class CCResult:
    ok: bool
    sheet: str = ""
    shorts: list[str] = field(default_factory=list)
    opens: list[str] = field(default_factory=list)
    n_components: int = 0
    n_declared: int = 0

    def summary(self) -> str:
        tag = f"CC GATE [{self.sheet}]" if self.sheet else "CC GATE"
        if self.ok:
            return (f"{tag}: PASS ({self.n_declared} declared nets, "
                    f"{self.n_components} geometry components — agree)")
        lines = [f"{tag}: FAIL"]
        for s in self.shorts:
            lines.append(f"  SHORT: {s}")
        for o in self.opens:
            lines.append(f"  OPEN: {o}")
        return "\n".join(lines)


# NET-BLIND by construction: a declared net may never drive a union here
def _harvest_nodes(circuit: Circuit, placement, routed,
                   lib: Library) -> tuple[dict, _UF, list[Seg], list]:
    nodes: dict[tuple[int, int], _Node] = {}
    uf = _UF()

    def node(x: float, y: float) -> _Node:
        k = _key(x, y)
        n = nodes.get(k)
        if n is None:
            n = _Node(key=k, x=round(x, 4), y=round(y, 4))
            nodes[k] = n
            uf.find(k)
        return n

    pad_tips: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for part in placement.parts:
        sdef = lib.get(part.lib_id)
        for pin in sdef.pins:
            x, y = pin_page_position(pin, part.x, part.y, part.rotation)
            node(x, y).pins.add(PinRef(part.ref, pin.number))
            pad_tips.setdefault((part.ref, pin.number), []).append((x, y))
    bonds: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for tips in pad_tips.values():
        for a, b in zip(tips, tips[1:], strict=False):
            bonds.append((a, b))

    for pw in placement.powers:
        name = pw.net_name
        if name == "PWR_FLAG":
            name = getattr(pw, "net", "") or pw.value
        node(pw.x, pw.y).powers.add(name)

    for h in placement.hlabels:
        node(h.x, h.y).labels.add(h.name)
    for ll in getattr(placement, "llabels", []):
        node(ll.x, ll.y).labels.add(ll.name)

    segs: list[Seg] = list(routed.segs)
    for s in segs:
        node(s.x0, s.y0)
        node(s.x1, s.y1)
    for j in getattr(routed, "junctions", []):
        node(j[0], j[1])

    return nodes, uf, segs, bonds


def _seed_geometry_unions(nodes: dict, uf: _UF, segs: list[Seg],
                          bonds: list) -> None:
    node_list = list(nodes.values())

    for s in segs:
        uf.union(_key(s.x0, s.y0), _key(s.x1, s.y1))

    for s in segs:
        ka = _key(s.x0, s.y0)
        for n in node_list:
            if n.key == ka or n.key == _key(s.x1, s.y1):
                continue
            if _point_on_seg(n.x, n.y, s, interior_only=False):
                uf.union(n.key, ka)

    eps_keys = {(_key(s.x0, s.y0), s) for s in segs} | \
               {(_key(s.x1, s.y1), s) for s in segs}
    for ek, owner in eps_keys:
        ex, ey = nodes[ek].x, nodes[ek].y
        for s in segs:
            if s is owner:
                continue
            if _point_on_seg(ex, ey, s, interior_only=False):
                uf.union(ek, _key(s.x0, s.y0))

    for a, b in bonds:
        uf.union(_key(*a), _key(*b))


def _legal_name_unions(nodes: dict, uf: _UF) -> None:
    by_name: dict[str, list[tuple[int, int]]] = {}
    for n in nodes.values():
        for nm in (n.labels | n.powers):
            by_name.setdefault(nm, []).append(n.key)
    for keys in by_name.values():
        for k in keys[1:]:
            uf.union(keys[0], k)


def _declared_of(circuit: Circuit) -> dict:
    declared: dict[PinRef, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            declared[pr] = net.name
    return declared


def check(circuit: Circuit, placement, routed, lib: Library,
          sheet: str = "") -> CCResult:
    nodes, uf, segs, bonds = _harvest_nodes(circuit, placement, routed, lib)
    _seed_geometry_unions(nodes, uf, segs, bonds)
    _legal_name_unions(nodes, uf)

    declared = _declared_of(circuit)

    comp_nets: dict[tuple[int, int], set[str]] = {}
    comp_pins: dict[tuple[int, int], list[PinRef]] = {}
    pin_comp: dict[PinRef, tuple[int, int]] = {}
    for n in nodes.values():
        root = uf.find(n.key)
        for pr in n.pins:
            pin_comp[pr] = root
            comp_pins.setdefault(root, []).append(pr)
            dn = declared.get(pr)
            if dn is not None:
                comp_nets.setdefault(root, set()).add(dn)
        for nm in (n.labels | n.powers):
            if nm in circuit.nets:
                comp_nets.setdefault(root, set()).add(nm)

    res = CCResult(ok=True, sheet=sheet)
    res.n_components = len({uf.find(k) for k in nodes})
    res.n_declared = len(circuit.nets)

    for root, dnets in sorted(comp_nets.items()):
        if len(dnets) >= 2:
            res.ok = False
            pin_detail = ", ".join(
                f"{pr}={declared.get(pr, '?')}"
                for pr in sorted(comp_pins.get(root, []),
                                 key=lambda p: (p.ref, p.pin))
                if declared.get(pr) is not None)
            res.shorts.append(
                f"component @grid{root} merges declared nets "
                f"{sorted(dnets)} [{pin_detail}]")

    for net in circuit.nets.values():
        netted = [pr for pr in net.pins if pr in pin_comp]
        roots = {pin_comp[pr] for pr in netted}
        if len(net.pins) >= 2 and len(roots) > 1:
            res.ok = False
            spans = {}
            for pr in netted:
                spans.setdefault(pin_comp[pr], []).append(str(pr))
            detail = " | ".join(
                f"comp{r}: {sorted(ps)}" for r, ps in sorted(spans.items()))
            res.opens.append(
                f"declared net {net.name!r} ({net.net_class.value}) split "
                f"across {len(roots)} components: {detail}")
        missing = [str(pr) for pr in net.pins if pr not in pin_comp]
        if missing:
            res.ok = False
            res.opens.append(
                f"declared net {net.name!r}: pin(s) {sorted(missing)} have no "
                f"geometry node (un-placed terminal)")

    return res


@dataclass
class BoardCCResult:
    ok: bool
    per_sheet: list[CCResult] = field(default_factory=list)

    def summary(self) -> str:
        out = [s.summary() for s in self.per_sheet]
        out.append(f"CC GATE BOARD: {'PASS' if self.ok else 'FAIL'} "
                   f"({len(self.per_sheet)} sheets, "
                   f"{sum(len(s.shorts) for s in self.per_sheet)} shorts, "
                   f"{sum(len(s.opens) for s in self.per_sheet)} opens)")
        return "\n".join(out)


def check_board(prepared: list, lib: Library) -> BoardCCResult:
    board = BoardCCResult(ok=True)
    for name, circuit, placement, routed in prepared:
        r = check(circuit, placement, routed, lib, sheet=name)
        board.per_sheet.append(r)
        board.ok = board.ok and r.ok
    return board
