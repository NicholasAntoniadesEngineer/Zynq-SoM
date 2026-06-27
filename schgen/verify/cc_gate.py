"""Connected-components gate: a SECOND, INDEPENDENT electrical witness.

Every other electrical gate in schgen ultimately trusts ONE oracle:
``kicad-cli sch export netlist`` (schgen/verify/netlist_gate.py). If kicad-cli
ever has a parsing quirk or a version regression, EVERY gate can agree on a
wrong answer with no independent check. This gate is that check.

It NEVER calls kicad-cli. It reads only the emitted GEOMETRY primitives — the
SAME in-memory ``Placement`` + ``RoutedSheet`` the board build hands to
``emit`` — and rebuilds connectivity from scratch:

1. NODES: every pin page-position (from :func:`pin_page_position`, the one
   coordinate transform), every wire endpoint, every junction, every power-
   symbol pin, every hier/local label anchor.
2. UNION the nodes that connectivity REQUIRES — net-BLIND, so a short shows up:
   - geometrically coincident points (same xy within tolerance);
   - a node lying ON a wire segment (interior or endpoint), reusing the visual
     gate's :func:`_point_on_seg` incidence test — so a wire's two endpoints AND
     every node touching its body union together;
   - wire-to-wire incidence (an endpoint of one wire on ANY other wire — net
     blind, the LAW-0 T-touch / butt-join short);
   - same-pad jumper bonds (a part's duplicate pin NUMBERS are one physical
     pad — KiCad jumper-pin semantics, route.py's ``bonds``).
   The LEGAL cross-net merges — same-NAME labels, same-NAME power symbols — are
   unioned LAST and EXPLICITLY (a rail/port net merges by name across drawn
   islets); everything else must be merged by geometry alone.
3. COMPONENTS = union-find classes.
4. COMPARE to the DECLARED-net partition (from the Circuit, the same
   declared-net model netlist_gate.py uses): the declared net of each pin.
   - SHORT: two DIFFERENT declared nets share ONE component.
   - OPEN: ONE declared net's pins split across >= 2 components.

Deterministic. Model + geometry only. No subprocess, no file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core.model import Circuit, PinRef
from schgen.core.symbols import Library, pin_page_position
from schgen.verify.visual_gate import Seg, _point_on_seg

# Coincidence tolerance. The router lands every endpoint EXACTLY on a 1.27 mm
# grid point (route.snap_ok eps 1e-3); visual_gate._point_on_seg uses 1e-6.
# A node is "coincident" with another when their rounded keys match — we round
# to 3 dp (micron) so float noise from the transform cannot split a real
# contact, while two genuinely different grid points (>= 1.27 mm apart) never
# collapse.
_QUANT = 1000.0   # round to 1e-3 mm


def _key(x: float, y: float) -> tuple[int, int]:
    return (round(x * _QUANT), round(y * _QUANT))


@dataclass
class _Node:
    """One connectivity site, keyed by its quantised page position."""
    key: tuple[int, int]
    x: float
    y: float
    pins: set = field(default_factory=set)        # PinRef landing here
    labels: set = field(default_factory=set)      # label NAMEs anchored here
    powers: set = field(default_factory=set)      # power-symbol rail NAMEs here


class _UF:
    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, k: tuple[int, int]) -> tuple[int, int]:
        self.parent.setdefault(k, k)
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:        # path compression
            self.parent[k], k = root, self.parent[k]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic merge order (smaller key wins) so the same inputs
            # always yield the same root labels
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


# ---------------------------------------------------------------------------
#  geometry harvest — strictly from placed/routed primitives, net-blind
# ---------------------------------------------------------------------------

def _harvest_nodes(circuit: Circuit, placement, routed,
                   lib: Library) -> tuple[dict, _UF, list[Seg], list]:
    """Build the node table + seed coincidence unions. Returns
    (nodes-by-key, union-find, segs, jumper-bond point pairs)."""
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

    # 1. component pins (the electrical terminals). Net-BLIND: we record which
    #    PinRef lands here but DO NOT use its declared net to drive any union.
    #    Duplicate pin NUMBERS on one part are one physical pad -> jumper bond.
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

    # 2. power symbols: a node carrying the rail NAME (legal same-name merge
    #    applied later). The pin point IS the symbol anchor (route.py uses
    #    (pw.x, pw.y) as the connection cell).
    for pw in placement.powers:
        name = pw.net_name
        if name == "PWR_FLAG":
            # a PWR_FLAG drives its host net by name; route requires net=<rail>
            name = getattr(pw, "net", "") or pw.value
        node(pw.x, pw.y).powers.add(name)

    # 3. label anchors (hier + local) — KiCad connectivity anchors that merge
    #    a net by NAME.
    for h in placement.hlabels:
        node(h.x, h.y).labels.add(h.name)
    for ll in getattr(placement, "llabels", []):
        node(ll.x, ll.y).labels.add(ll.name)

    # 4. wire endpoints become nodes too (a corner with no terminal is still a
    #    connectivity vertex).
    segs: list[Seg] = list(routed.segs)
    for s in segs:
        node(s.x0, s.y0)
        node(s.x1, s.y1)
    for j in getattr(routed, "junctions", []):
        node(j[0], j[1])

    return nodes, uf, segs, bonds


def _seed_geometry_unions(nodes: dict, uf: _UF, segs: list[Seg],
                          bonds: list) -> None:
    """Net-BLIND unions from PURE geometry: node-on-wire incidence,
    wire-endpoint-on-wire incidence, and same-pad jumper bonds. NO net
    identity is consulted here — that is what lets a short surface."""
    node_list = list(nodes.values())

    # a wire connects its own two endpoints
    for s in segs:
        uf.union(_key(s.x0, s.y0), _key(s.x1, s.y1))

    # every node lying ON a wire (interior OR endpoint) unions with that
    # wire's endpoints. _point_on_seg(interior_only=False) reuses the visual
    # gate's incidence test (orthogonal segment, closed). This is the LAW-0
    # check: a foreign pin/wire that merely TOUCHES another net's wire shorts.
    for s in segs:
        ka = _key(s.x0, s.y0)
        for n in node_list:
            if n.key == ka or n.key == _key(s.x1, s.y1):
                continue
            if _point_on_seg(n.x, n.y, s, interior_only=False):
                uf.union(n.key, ka)

    # wire-endpoint-on-wire (T-touch / butt-join between two segments whose
    # shared point is not a registered node corner). Endpoints are already
    # nodes, so this is covered by the node-on-wire loop above; we additionally
    # check segment-endpoint vs every other segment to be airtight.
    eps_keys = {(_key(s.x0, s.y0), s) for s in segs} | \
               {(_key(s.x1, s.y1), s) for s in segs}
    for ek, owner in eps_keys:
        ex, ey = nodes[ek].x, nodes[ek].y
        for s in segs:
            if s is owner:
                continue
            if _point_on_seg(ex, ey, s, interior_only=False):
                uf.union(ek, _key(s.x0, s.y0))

    # same-pad jumper bonds (duplicate pin numbers == one physical pad)
    for a, b in bonds:
        uf.union(_key(*a), _key(*b))


def _legal_name_unions(nodes: dict, uf: _UF) -> None:
    """The ONLY cross-net merges allowed without geometric contact: same-NAME
    labels and same-NAME power symbols. KiCad merges a rail/port net across
    its drawn islets by name; this models exactly that, and ONLY that."""
    by_name: dict[str, list[tuple[int, int]]] = {}
    for n in nodes.values():
        for nm in (n.labels | n.powers):
            by_name.setdefault(nm, []).append(n.key)
    for keys in by_name.values():
        for k in keys[1:]:
            uf.union(keys[0], k)


# ---------------------------------------------------------------------------
#  declared-net partition (reuse netlist_gate's model: pin -> declared net)
# ---------------------------------------------------------------------------

def _declared_of(circuit: Circuit) -> dict:
    declared: dict[PinRef, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            declared[pr] = net.name
    return declared


# ---------------------------------------------------------------------------
#  the gate
# ---------------------------------------------------------------------------

def check(circuit: Circuit, placement, routed, lib: Library,
          sheet: str = "") -> CCResult:
    """Compare the GEOMETRY connected-components partition to the DECLARED-net
    partition. SHORT = two declared nets in one component; OPEN = one declared
    net split across components. Independent of kicad-cli."""
    nodes, uf, segs, bonds = _harvest_nodes(circuit, placement, routed, lib)
    _seed_geometry_unions(nodes, uf, segs, bonds)
    _legal_name_unions(nodes, uf)

    declared = _declared_of(circuit)

    # component (root) -> the declared nets + pins it carries
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
        # labels/power names also carry net identity into the component
        for nm in (n.labels | n.powers):
            if nm in circuit.nets:
                comp_nets.setdefault(root, set()).add(nm)

    res = CCResult(ok=True, sheet=sheet)
    res.n_components = len({uf.find(k) for k in nodes})
    res.n_declared = len(circuit.nets)

    # ---- SHORTS: a component carrying >= 2 declared nets --------------------
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

    # ---- OPENS: a declared net whose pins span >= 2 components --------------
    for net in circuit.nets.values():
        # power-symbol-only / label-only single-pin PORT nets: a net with < 2
        # PINS cannot "open" between pins; its connectivity to the rest of the
        # board is by NAME (proven by the name-union). Skip those for opens but
        # still require the (>=2-pin) electrical nets to be one component.
        netted = [pr for pr in net.pins if pr in pin_comp]
        roots = {pin_comp[pr] for pr in netted}
        if len(net.pins) >= 2 and len(roots) > 1:
            # legal multi-islet span: a POWER/GROUND net merges across islets
            # by its power symbols, a label-bridged net by its labels — the
            # name-union already FUSED those. If after the name-union the pins
            # STILL fall in different components, the net is genuinely OPEN.
            res.ok = False
            spans = {}
            for pr in netted:
                spans.setdefault(pin_comp[pr], []).append(str(pr))
            detail = " | ".join(
                f"comp{r}: {sorted(ps)}" for r, ps in sorted(spans.items()))
            res.opens.append(
                f"declared net {net.name!r} ({net.net_class.value}) split "
                f"across {len(roots)} components: {detail}")
        # a pin that landed on NO node at all (should never happen — every
        # placed pin is harvested) is a hard open.
        missing = [str(pr) for pr in net.pins if pr not in pin_comp]
        if missing:
            res.ok = False
            res.opens.append(
                f"declared net {net.name!r}: pin(s) {sorted(missing)} have no "
                f"geometry node (un-placed terminal)")

    return res


# ---------------------------------------------------------------------------
#  board-wide convenience: gate every sheet from in-memory placements
# ---------------------------------------------------------------------------

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
    """``prepared`` is a list of (sheet_name, circuit, placement, routed).
    Runs the per-sheet CC gate on each. Cross-sheet merges (same-name PORT /
    rail) are connectivity by NAME — the per-sheet name-union already models
    the intra-sheet case, and the board linker (schgen/link.py) proves the
    cross-sheet name graph independently; this gate's domain is the per-sheet
    geometry, where the kicad-cli oracle's blind spot would live."""
    board = BoardCCResult(ok=True)
    for name, circuit, placement, routed in prepared:
        r = check(circuit, placement, routed, lib, sheet=name)
        board.per_sheet.append(r)
        board.ok = board.ok and r.ok
    return board
