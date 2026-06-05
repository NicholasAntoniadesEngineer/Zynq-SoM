"""Module solve — one IC + its supporting passives, solved clean and frozen.

This is Stage A of the convergent layout engine (see the approved plan
``this-has-been-consistently-serialized-petal.md``). A *module* is one IC
together with every passive its reference circuit requires (decoupling caps,
pull-ups), each passive's far-end power-symbol or net label, and the wires
that connect them. The module is solved ONCE in isolation and then frozen:
thereafter the global placer (Stage B) only ever moves it by RIGID
TRANSLATION, which cannot change its interior clearance. That is what makes
the whole engine converge — a frozen module can never re-crowd.

The solve is built around the exact feasibility projector
:func:`zynq_eda.core.layout.separate.remove_overlaps`. Each passive (with its
far symbol/label + all text) becomes one rigid *cell* :class:`Rect`; the IC
body is a fixed rect; the projector spreads the cells to ``>= gap`` (the Laws'
breathing room) over the SAME body+text footprints the overlap validator
measures (:func:`zynq_eda.core.layout.footprint.symbol_footprint`). Therefore
a solved module is, by construction, validator-clean — no measure-then-nudge.

What this module deliberately does NOT do (later stages own it):
  * spread the modules across the page (Stage B, ``arrange.py``);
  * route inter-module / sheet-edge nets (Stage C, ``route_sheet``);
  * point-feature label placement / staggering (Stage D, ``labeler.py``).

Intra-module wiring here is a small trunk-and-drop per IC pin — the geometry
is tiny and clean after projection, so a literal orthogonal trunk + drops is
both correct and readable; the render is the judge.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Literal

from zynq_eda.core.layout._constants import (
    CAP_VERTICAL_OFFSET_MM,
    PASSIVE_OFFSET_MM,
    PASSIVE_PIN_HALF,
    PASSIVE_PITCH_MM,
    POWER_SYMBOL_LIB_IDS,
    VISUAL_CLEARANCE_MM,
)
from zynq_eda.core.layout.bbox import BBox, text_bbox, wire_bbox
from zynq_eda.core.layout.cluster import (
    _outward_power_symbol_rotation,
    passive_footprint,
    passive_lib_id,
    passive_ref_prefix,
    passive_value,
)
from zynq_eda.core.layout.footprint import bbox_to_rect, symbol_footprint
from zynq_eda.core.layout.geometry import (
    SymbolGeometryCache,
    page_side_from_pin,
)
from zynq_eda.core.route.grid import route_terminals
from zynq_eda.core.layout.separate import Rect, remove_overlaps
from zynq_eda.core.model.block import IcInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PlacedJunction,
    PlacedLabel,
    PlacedSymbol,
    PlacedWire,
)

PageSide = Literal["left", "right", "top", "bottom"]

# GND-family pin/net names that resolve to the power:GND symbol.
_GND_NAMES = frozenset({"GND", "GNDA", "AGND", "DGND", "PGND", "GND_1", "VSS"})

# A non-power net with >= this many taps is a high-fan-in MERGE node (ethernet
# BS_COMMON has 8). Such a bus is routed off the IC's signal-label edge.
_MERGE_FANIN = 3

# Cell footprints' centres sit off-grid (text-asymmetric), but symbol anchors
# must stay on the 1.27 mm grid; snapping each projected displacement back to
# grid can leave a pair up to ~one grid short of the LAW's 2.54 mm clearance.
# So the projector TARGETS clearance + one grid of margin: quantisation then
# always lands at >= 2.54 mm, and the extra breathing room is itself desirable.
# Validation still uses the strict 2.54 mm — this only over-satisfies it.
_PROJECT_GAP = VISUAL_CLEARANCE_MM + 1.27


# ---------------------------------------------------------------------------
# Frozen module result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModulePort:
    """One net leaving the module — where it exits + which way it faces.

    Stage B/C use ports to wire modules together and to the sheet edge:
    ``position`` is the exact grid point the net is exposed at (a far
    terminal / label anchor), ``side`` the outboard direction, ``kind``
    distinguishes a power-rail tap, a ground, or a routable signal.
    """

    net_name: str
    position: Point
    side: PageSide
    kind: Literal["power", "gnd", "signal"]


@dataclass(frozen=True)
class Module:
    """A solved, frozen IC sub-layout. Moved later only by rigid translation."""

    ic_ref: str
    anchor: Point
    symbols: tuple[PlacedSymbol, ...]
    wires: tuple[PlacedWire, ...]
    junctions: tuple[PlacedJunction, ...]
    labels: tuple[PlacedLabel, ...]
    ports: tuple[ModulePort, ...]
    bbox: BBox
    # Net topology for the connectivity-correct router: each entry is
    # (net_label, terminal_points_that_must_be_joined). The router connects
    # each net's terminals into an orthogonal tree with EXACT on-pin endpoints.
    # This is the ground truth the grid routers lacked — it says WHICH pins
    # share a net, so every pin is wired (no silent drops, no cap-only model).
    nets: tuple[tuple[str, tuple[Point, ...]], ...] = ()

    def translated(self, dx: float, dy: float) -> "Module":
        """Return a copy shifted by ``(dx, dy)`` — the ONLY motion Stage B
        applies. Pure rigid translation, so interior clearance is invariant."""
        dx = snap_to_grid(dx)
        dy = snap_to_grid(dy)
        return Module(
            ic_ref=self.ic_ref,
            anchor=Point(self.anchor.x + dx, self.anchor.y + dy),
            symbols=tuple(_shift_symbol(s, dx, dy) for s in self.symbols),
            wires=tuple(
                PlacedWire(
                    start=Point(w.start.x + dx, w.start.y + dy),
                    end=Point(w.end.x + dx, w.end.y + dy),
                )
                for w in self.wires
            ),
            junctions=tuple(
                PlacedJunction(Point(j.position.x + dx, j.position.y + dy))
                for j in self.junctions
            ),
            labels=tuple(
                PlacedLabel(
                    net_name=l.net_name,
                    position=Point(l.position.x + dx, l.position.y + dy),
                    rotation=l.rotation,
                )
                for l in self.labels
            ),
            ports=tuple(
                ModulePort(
                    net_name=p.net_name,
                    position=Point(p.position.x + dx, p.position.y + dy),
                    side=p.side,
                    kind=p.kind,
                )
                for p in self.ports
            ),
            bbox=self.bbox.translate(dx, dy),
            nets=tuple(
                (name, tuple(Point(p.x + dx, p.y + dy) for p in pts))
                for name, pts in self.nets
            ),
        )


def _shift_symbol(sym: PlacedSymbol, dx: float, dy: float) -> PlacedSymbol:
    return PlacedSymbol(
        lib_id=sym.lib_id,
        reference=sym.reference,
        value=sym.value,
        position=Point(sym.position.x + dx, sym.position.y + dy),
        footprint=sym.footprint,
        rotation=sym.rotation,
        properties=sym.properties,
        value_shift=sym.value_shift,
        reference_shift=sym.reference_shift,
    )


# ---------------------------------------------------------------------------
# Cell = one passive + its far symbol/label, as a rigid unit during solve
# ---------------------------------------------------------------------------

@dataclass
class _Cell:
    """A passive and its far-end attachment, tracked together through the solve.

    Mutable during the solve (the projector moves it); converted to frozen
    primitives once positions are final.
    """

    pin: Point                  # the IC pin this cell hangs off
    side: PageSide              # page side that pin is on
    to_net: str                 # destination net of the passive's far end
    far_kind: Literal["power", "gnd", "signal"]
    passive: PlacedSymbol       # the cap/resistor body
    far_symbol: PlacedSymbol | None  # power symbol at the far terminal, if any
    emit_label: bool = True     # False for the 2nd+ tap of a merge net (one
                                # shared label per net; the bus trunk is Stage C)
    merge: bool = False         # tap of a high-fan-in non-power merge bus routed
                                # BELOW the IC (exempt from pull-in)

    def members(self) -> list[PlacedSymbol]:
        return [self.passive] + ([self.far_symbol] if self.far_symbol else [])


def _classify_far(to_net: str) -> tuple[Literal["power", "gnd", "signal"], str | None]:
    """Classify a passive's far destination → (kind, power-symbol lib_id|None)."""
    if to_net in _GND_NAMES:
        return "gnd", POWER_SYMBOL_LIB_IDS.get("GND", "power:GND")
    lib = POWER_SYMBOL_LIB_IDS.get(to_net)
    if lib is not None:
        return "power", lib
    return "signal", None


def _remap_to_net(ic: IcInstance, to_net: str) -> str:
    """Apply the IC's catalog→block net renames to a passive destination."""
    for catalog_net, block_net in ic.external_part_net_remap:
        if to_net == catalog_net:
            return block_net
    return to_net


def _passive_pins(anchor: Point, side: PageSide) -> tuple[Point, Point]:
    """Return (near, far) terminals of a passive at ``anchor`` on ``side``.

    near = the terminal closest to the IC pin trunk; far = the terminal the
    power-symbol / label attaches to. Mirrors the proven cluster convention
    (LEFT/RIGHT caps stand vertical; TOP/BOTTOM lie horizontal)."""
    if side in ("left", "right"):
        near = Point(anchor.x, snap_to_grid(anchor.y + PASSIVE_PIN_HALF))
        far = Point(anchor.x, snap_to_grid(anchor.y - PASSIVE_PIN_HALF))
        return near, far
    near = Point(snap_to_grid(anchor.x - PASSIVE_PIN_HALF), anchor.y)
    far = Point(snap_to_grid(anchor.x + PASSIVE_PIN_HALF), anchor.y)
    return near, far


def _passive_rotation(side: PageSide) -> float:
    return 0.0 if side in ("left", "right") else 90.0


def _seed_anchor(pin: Point, side: PageSide, slot: int, extra_out: float = 0.0) -> Point:
    """Initial passive anchor: outboard from the pin (datasheet intent).

    Only a SEED — the projector + pull-in produce the final position. Slots
    fan outboard so the projector starts from a sane, near-feasible state.
    ``extra_out`` pushes the seed further outboard (a merge bus routed below the
    IC, to clear the body before the projector spreads it sideways)."""
    outboard = PASSIVE_OFFSET_MM + slot * PASSIVE_PITCH_MM + extra_out
    if side == "left":
        return Point(snap_to_grid(pin.x - outboard), snap_to_grid(pin.y - CAP_VERTICAL_OFFSET_MM))
    if side == "right":
        return Point(snap_to_grid(pin.x + outboard), snap_to_grid(pin.y - CAP_VERTICAL_OFFSET_MM))
    if side == "top":
        return Point(snap_to_grid(pin.x + CAP_VERTICAL_OFFSET_MM), snap_to_grid(pin.y - outboard))
    return Point(snap_to_grid(pin.x + CAP_VERTICAL_OFFSET_MM), snap_to_grid(pin.y + outboard))


def _place_far_symbol(
    far: Point,
    side: PageSide,
    lib_id: str,
    net: str,
    reference: str,
    geometry: SymbolGeometryCache,
) -> tuple[PlacedSymbol, Point]:
    """Place a power symbol so its pin tip sits one grid outboard of ``far``.

    Returns the placed symbol and the pin-tip point (the wire endpoint that
    connects to the passive's far terminal via a short visible stub)."""
    # Outboard direction from the cap's far terminal: vertical caps put the
    # symbol above; horizontal caps put it to the side.
    if side in ("left", "right"):
        sym_side: PageSide = "top"
        tip = Point(far.x, snap_to_grid(far.y - VISUAL_CLEARANCE_MM))
    else:
        sym_side = "right"
        tip = Point(snap_to_grid(far.x + VISUAL_CLEARANCE_MM), far.y)
    rotation = _outward_power_symbol_rotation(
        lib_id=lib_id, pin_side=sym_side, geometry_cache=geometry,
    )
    # Anchor the symbol so its (single) pin's connection point lands on ``tip``.
    rel = geometry.absolute_pin_positions(lib_id, Point(0.0, 0.0), rotation)
    pin_rel = next(iter(rel.values())) if rel else Point(0.0, 0.0)
    anchor = Point(snap_to_grid(tip.x - pin_rel.x), snap_to_grid(tip.y - pin_rel.y))
    sym = PlacedSymbol(
        lib_id=lib_id,
        reference=reference,
        value=net,
        position=anchor,
        footprint="",
        rotation=rotation,
    )
    return sym, tip


def _place_pin_power_symbol(
    pin: Point,
    side: PageSide,
    lib_id: str,
    net: str,
    reference: str,
    geometry: SymbolGeometryCache,
    obstacles: list[BBox],
    max_steps: int = 1,
) -> tuple[PlacedSymbol, Point] | None:
    """Place a LOCAL power symbol just outboard of a bare IC power/GND pin.

    Returns ``(symbol, pin_tip)`` where ``pin_tip`` is the symbol's pin
    connection point — the module then wires the IC pin to ``pin_tip`` with a
    short stub. The symbol is walked outboard (1 … ``max_steps`` grid) until its
    footprint clears every obstacle (the IC body + every placed symbol/wire/
    label). A local symbol joins the GLOBAL rail without a long trunk across the
    IC's other pins — the cross-net wire a net-blind junction would otherwise
    weld into a short (e.g. the INA226 GND trunk over SDA/SCL/Alert). Capped at
    ``max_steps`` so it is used ONLY on a genuinely OPEN pin edge (default 1 grid
    clear); a congested edge returns ``None`` and the caller keeps the proven
    far-symbol trunk — no regression on dense power ICs. Returns ``None`` if no
    clear outboard spot exists within reach."""
    ux, uy = {"left": (-1.0, 0.0), "right": (1.0, 0.0),
              "top": (0.0, -1.0), "bottom": (0.0, 1.0)}[side]
    rotation = _outward_power_symbol_rotation(
        lib_id=lib_id, pin_side=side, geometry_cache=geometry,
    )
    try:
        rel = geometry.absolute_pin_positions(lib_id, Point(0.0, 0.0), rotation)
    except Exception:  # noqa: BLE001
        return None
    pin_rel = next(iter(rel.values())) if rel else Point(0.0, 0.0)
    for step in range(1, max_steps + 1):
        dist = snap_to_grid(step * VISUAL_CLEARANCE_MM)
        tip = Point(snap_to_grid(pin.x + ux * dist), snap_to_grid(pin.y + uy * dist))
        anchor = Point(snap_to_grid(tip.x - pin_rel.x), snap_to_grid(tip.y - pin_rel.y))
        sym = PlacedSymbol(lib_id=lib_id, reference=reference, value=net,
                           position=anchor, footprint="", rotation=rotation)
        try:
            sbox = symbol_footprint(sym, geometry)
        except Exception:  # noqa: BLE001
            continue
        if all(not sbox.intersects(o, padding_mm=VISUAL_CLEARANCE_MM)
               for o in obstacles):
            return sym, tip
    return None


# ---------------------------------------------------------------------------
# The solve
# ---------------------------------------------------------------------------

def solve_module(
    ic: IcInstance,
    geometry: SymbolGeometryCache,
    *,
    anchor: Point = Point(100.0, 100.0),
    ref_start: int = 100,
    pull_in: bool = True,
) -> Module:
    """Solve one IC's module: place + spread + freeze. Returns a clean Module.

    ``anchor`` is where the IC body is dropped (arbitrary; Stage B relocates
    the whole module). ``ref_start`` seeds the passive/power designator
    counter; Stage E wires this to the project's real reference allocator.
    """
    anchor = Point(snap_to_grid(anchor.x), snap_to_grid(anchor.y))
    rc = ic.refcircuit

    ic_sym = PlacedSymbol(
        lib_id=ic.lib_id,
        reference=ic.reference,
        value=rc.part_mpn,
        position=anchor,
        footprint=rc.footprint,
        rotation=0.0,
    )
    ic_rect = bbox_to_rect(symbol_footprint(ic_sym, geometry))

    # ---- Build one cell per external part, seeded near its from_pin -------
    # Per-EDGE running slot index: every passive on a side seeds in its own
    # outboard column, so adjacent-pin cells (e.g. IN + EN, 2.54 mm apart)
    # start in DISTINCT columns and the projector fans them in X rather than
    # stacking them in Y. The projector then guarantees clearance and the
    # pull-in compacts; co-pin passives still share a trunk in _wire_group.
    # Count destinations so a net hit by >= 2 parts (a MERGE node, e.g.
    # ethernet's BS_COMMON) that isn't a power rail gets ONE shared label, not
    # one per tap. The drawn bus trunk joining the taps is Stage C (router).
    net_count: collections.Counter = collections.Counter()
    for ep in rc.expand_parts():
        net_count[_remap_to_net(ic, ep.to_net)] += 1
    labeled_merge_nets: set[str] = set()

    edge_slot: dict[str, int] = {}
    cells: list[_Cell] = []
    c_ref = ref_start
    p_ref = ref_start
    unresolved: list[str] = []

    for ep in rc.expand_parts():
        to_net = _remap_to_net(ic, ep.to_net)
        try:
            pg = geometry.pin_geometry_by_name(ic.lib_id, anchor, ep.from_pin)
        except KeyError:
            unresolved.append(f"{ic.reference}.{ep.from_pin}")
            continue
        pin = pg.connection
        side = page_side_from_pin(pg.pin_rotation, 0.0)
        # A high-fan-in NON-power merge bus (ethernet BS_COMMON: 8 Bob-Smith
        # taps) on a vertical edge shares that edge with bare SIGNAL pins whose
        # long edge labels need the whole outboard lane (T1's PHY MDI labels).
        # Route its taps BELOW the IC instead so the bus never crowds those
        # lanes — the merge taps are interchangeable (all on one node), so the
        # extra L from the pin is electrically free. Only fires for such a bus.
        is_merge = (net_count[to_net] >= _MERGE_FANIN
                    and _classify_far(to_net)[1] is None and side in ("left", "right"))
        if is_merge:
            side = "bottom"
        slot = edge_slot.get(side, 0)
        edge_slot[side] = slot + 1

        if is_merge:
            # Seed the bus as a horizontal ROW just below the IC body, fanning
            # AWAY from the pin column (so the projector keeps it compact and
            # clear of the body + the other-edge label lanes), then drop each
            # tap straight down from its pin. Skips pull-in (would tug it back up).
            body_bottom = ic_rect.cy + ic_rect.h / 2.0
            seed = Point(snap_to_grid(pin.x - slot * PASSIVE_PITCH_MM),
                         snap_to_grid(body_bottom + PASSIVE_OFFSET_MM))
        else:
            seed = _seed_anchor(pin, side, slot)
        lib = passive_lib_id(ep.part_token)
        prefix = passive_ref_prefix(ep.part_token)
        passive = PlacedSymbol(
            lib_id=lib,
            reference=f"{prefix}{c_ref}",
            value=passive_value(ep.part_token),
            position=seed,
            footprint=passive_footprint(ep.part_token),
            rotation=_passive_rotation(side),
        )
        c_ref += 1

        far_kind, far_lib = _classify_far(to_net)
        _, far = _passive_pins(seed, side)
        far_symbol: PlacedSymbol | None = None
        emit_label = True
        if far_lib is not None:
            far_symbol, _tip = _place_far_symbol(
                far, side, far_lib, to_net, f"#PWR{p_ref}", geometry,
            )
            p_ref += 1
        elif net_count[to_net] >= 2:
            # Merge net: label it once; later taps carry the net via their port.
            if to_net in labeled_merge_nets:
                emit_label = False
            else:
                labeled_merge_nets.add(to_net)

        cells.append(
            _Cell(pin, side, to_net, far_kind, passive, far_symbol, emit_label,
                  merge=is_merge)
        )

    if unresolved:
        raise ValueError(
            f"solve_module({ic.reference}): unresolved from_pins "
            f"{unresolved} on {ic.lib_id} — no silent drops (the Laws)."
        )

    # ---- Project to feasibility: IC fixed, cells spread to >= clearance ---
    # remove_overlaps is a single X-then-Y sweep; on dense 2D clusters one
    # sweep can leave residual overlaps (resolving X reintroduces a Y overlap
    # and vice-versa). Iterate to a fixed point: each sweep is monotone and the
    # IC is fixed so the frame can't drift, so this converges to the true
    # feasibility the validator measures — never softened, only spread further.
    movable = [False] + [True] * len(cells)
    for _ in range(40):
        cell_rects = [_cell_rect(c, geometry) for c in cells]
        centers = remove_overlaps(
            [ic_rect, *cell_rects], gap=_PROJECT_GAP, movable=movable
        )
        moved = False
        for cell, rect, (ncx, ncy) in zip(cells, cell_rects, centers[1:]):
            dx = snap_to_grid(ncx - rect.cx)
            dy = snap_to_grid(ncy - rect.cy)
            if dx or dy:
                _translate_cell(cell, dx, dy)
                moved = True
        if not moved:
            break

    # ---- Pull-in: recover wirelength back toward the pin, stop at clearance.
    if pull_in:
        _pull_in_cells(cells, ic_rect, geometry)

    # ---- Emit wires / junctions / labels / ports from the final geometry --
    return _finalize(ic, anchor, ic_sym, cells, geometry, p_ref)


def _signal_far(cell: _Cell) -> tuple[Point, Point, float]:
    """Far terminal, label anchor, and label rotation for a signal far-end.

    The label sits one stub OUTBOARD of the passive's far pin (like a power
    symbol's stub) so it clears the passive's OWN body + Reference/Value text
    by the full clearance, and reads away from the IC."""
    _, far = _passive_pins(cell.passive.position, cell.side)
    stub = snap_to_grid(2.0 * VISUAL_CLEARANCE_MM)
    if cell.side in ("left", "right"):
        tip = Point(far.x, snap_to_grid(far.y - stub))
    else:
        tip = Point(snap_to_grid(far.x + stub), far.y)
    rot = 180.0 if cell.side == "left" else 0.0
    return far, tip, rot


def _cell_rect(cell: _Cell, geometry: SymbolGeometryCache) -> Rect:
    boxes = [symbol_footprint(m, geometry) for m in cell.members()]
    if cell.far_symbol is None and cell.emit_label:
        # The far end is a net label, not a power symbol — reserve its text
        # box too, so the projector spreads neighbours clear of the LABEL and
        # not merely the passive body (the left-cluster crowding's root cause).
        _far, tip, rot = _signal_far(cell)
        boxes.append(text_bbox(
            cell.to_net, tip, rotation=rot, justify="left", kind="label",
            owner_id=f"label:{cell.to_net}",
        ))
    minx = min(b.min.x for b in boxes)
    miny = min(b.min.y for b in boxes)
    maxx = max(b.max.x for b in boxes)
    maxy = max(b.max.y for b in boxes)
    return Rect((minx + maxx) / 2.0, (miny + maxy) / 2.0, maxx - minx, maxy - miny)


def _translate_cell(cell: _Cell, dx: float, dy: float) -> None:
    cell.passive = _shift_symbol(cell.passive, dx, dy)
    if cell.far_symbol is not None:
        cell.far_symbol = _shift_symbol(cell.far_symbol, dx, dy)


def _pull_in_cells(
    cells: list[_Cell],
    ic_rect: Rect,
    geometry: SymbolGeometryCache,
) -> None:
    """Monotonically slide each cell back toward its pin along the outboard
    axis, stopping one grid step before it would violate clearance against the
    IC or any other cell. Recovers wirelength without ever re-crowding (the
    projector's feasibility stays an invariant: we only ever reduce a gap to
    exactly the clearance boundary, never below)."""
    step = snap_to_grid(VISUAL_CLEARANCE_MM)
    for i, cell in enumerate(cells):
        if cell.merge:
            continue  # merge-bus row stays below the IC (clear of label lanes)
        # Outboard unit vector (cell sits outboard of pin; pull-in is -outboard).
        if cell.side == "left":
            ux, uy = 1.0, 0.0
        elif cell.side == "right":
            ux, uy = -1.0, 0.0
        elif cell.side == "top":
            ux, uy = 0.0, 1.0
        else:
            ux, uy = 0.0, -1.0
        others = [_cell_rect(c, geometry) for j, c in enumerate(cells) if j != i] + [ic_rect]
        moved = True
        # Hard bound: pull-in can advance at most the seed outboard distance
        # (~PASSIVE_OFFSET + a few slots) in `step` increments. This cap makes
        # the loop terminating-by-construction regardless of geometry quirks.
        max_steps = int((PASSIVE_OFFSET_MM + len(cells) * PASSIVE_PITCH_MM) / step) + 2
        guard = 0
        while moved and guard < max_steps:
            guard += 1
            moved = False
            trial_dx, trial_dy = snap_to_grid(ux * step), snap_to_grid(uy * step)
            probe = _shifted_cell_rect(cell, trial_dx, trial_dy, geometry)
            # Don't overshoot the pin (stay outboard of it).
            if cell.side == "left" and probe.cx >= cell.pin.x:
                break
            if cell.side == "right" and probe.cx <= cell.pin.x:
                break
            if cell.side == "top" and probe.cy >= cell.pin.y:
                break
            if cell.side == "bottom" and probe.cy <= cell.pin.y:
                break
            if all(not _rects_within(probe, o, VISUAL_CLEARANCE_MM) for o in others):
                _translate_cell(cell, trial_dx, trial_dy)
                moved = True


def _shifted_cell_rect(
    cell: _Cell, dx: float, dy: float, geometry: SymbolGeometryCache
) -> Rect:
    r = _cell_rect(cell, geometry)
    return Rect(r.cx + dx, r.cy + dy, r.w, r.h)


def _rects_within(a: Rect, b: Rect, gap: float) -> bool:
    """True iff rect ``a`` is within ``gap`` of rect ``b`` (would crowd)."""
    return (
        abs(a.cx - b.cx) < (a.w + b.w) / 2.0 + gap
        and abs(a.cy - b.cy) < (a.h + b.h) / 2.0 + gap
    )


# ---------------------------------------------------------------------------
# Finalize: wires + junctions + labels + ports + module bbox
# ---------------------------------------------------------------------------

def _finalize(
    ic: IcInstance,
    anchor: Point,
    ic_sym: PlacedSymbol,
    cells: list[_Cell],
    geometry: SymbolGeometryCache,
    p_ref: int = 700,
) -> Module:
    symbols: list[PlacedSymbol] = [ic_sym]
    far_wires: list[PlacedWire] = []   # passive far → power-symbol/label stubs
    labels: list[PlacedLabel] = []
    ports: list[ModulePort] = []

    # Group cells by the pin they hang off so co-pin passives share a trunk net.
    by_pin: dict[tuple[float, float], list[_Cell]] = {}
    for cell in cells:
        by_pin.setdefault((round(cell.pin.x, 3), round(cell.pin.y, 3)), []).append(cell)

    # Build the per-pin TRUNK nets (IC pin + each passive's near terminal) and
    # the far-end stubs (clean short verticals into the power symbol / label).
    # Track each trunk net's OWN symbols (the IC body + that pin's passives +
    # their power symbols) so the router may traverse only ITS OWN halos — a
    # trunk wire treats a SIBLING net's passive as an obstacle (no plowing
    # through it), but may escape its own IC body / dock its own passives.
    trunk_nets: dict[str, list[Point]] = {}
    own_syms: dict[str, list[PlacedSymbol]] = {}
    escape_dirs: dict[str, list[tuple[int, int]]] = {}
    # Page side → outboard unit cell step (page +Y is down).
    _OUT = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}
    for group in by_pin.values():
        side = group[0].side
        pin = group[0].pin
        terminals: list[Point] = [pin]
        # IC pin escapes OUTBOARD (its page side); each passive near-pin escapes
        # back TOWARD the IC (opposite side) so it docks onto the trunk.
        dirs: list[tuple[int, int]] = [_OUT[side]]
        inboard = (-_OUT[side][0], -_OUT[side][1])
        net_key = f"{ic.reference}@{pin.x:.2f},{pin.y:.2f}"
        members: list[PlacedSymbol] = [ic_sym]
        for cell in group:
            symbols.append(cell.passive)
            members.append(cell.passive)
            near, far = _passive_pins(cell.passive.position, side)
            terminals.append(near)
            dirs.append(inboard)
            if cell.far_symbol is not None:
                symbols.append(cell.far_symbol)
                members.append(cell.far_symbol)
                tip = _far_symbol_tip(far, side)
                if tip != far:
                    far_wires.append(PlacedWire(far, tip))
                ports.append(ModulePort(cell.to_net, far, side, cell.far_kind))
            elif cell.emit_label:
                _far, tip, rot = _signal_far(cell)
                if tip != far:
                    far_wires.append(PlacedWire(far, tip))
                labels.append(PlacedLabel(net_name=cell.to_net, position=tip, rotation=rot))
                ports.append(ModulePort(cell.to_net, tip, side, "signal"))
            else:
                # Merge-net tap with no own label: expose the far pin as a port
                # so the sheet-level router joins it into the shared bus.
                ports.append(ModulePort(cell.to_net, far, side, "signal"))
        trunk_nets[net_key] = terminals
        own_syms[net_key] = members
        escape_dirs[net_key] = dirs

    # Route the trunks with the cached-grid A* router against the real obstacle
    # set (every body + text + the far stubs), so the trunk wires weave AROUND
    # bodies and pin text instead of crossing them (the Stage-A wire findings).
    obstacles = [symbol_footprint(s, geometry) for s in symbols]
    for l in labels:
        obstacles.append(
            text_bbox(l.net_name, l.position, rotation=l.rotation, justify="left",
                      kind="label", owner_id=f"label:{l.net_name}")
        )
    for w in far_wires:
        obstacles.append(wire_bbox(w.start, w.end))

    # Per-net own-symbol exempt: only the IC body the pin lives on + that pin's
    # own passives/power symbols are traversable for this trunk. The IC body is
    # shared by every trunk (each pin must escape it); sibling passives are NOT
    # exempt, so a trunk never plows through another net's cap.
    own_obstacles = {
        name: [symbol_footprint(s, geometry) for s in members]
        for name, members in own_syms.items()
    }
    trunk_wires, trunk_juncs, failures = route_terminals(
        obstacles, trunk_nets, own_obstacles=own_obstacles, escape_dirs=escape_dirs
    )
    if failures:
        nets = sorted({n for n, _ in failures})
        raise ValueError(
            f"solve_module({ic.reference}): router could not connect "
            f"{len(failures)} terminal(s) on nets {nets} — no silent drops "
            f"(the Laws). Placement must open a wider channel."
        )

    wires = far_wires + list(trunk_wires)

    # ---- Net topology for the connectivity-correct router -----------------
    # Trunk nets (near side): the IC pin + the NEAR pins of the caps hanging off
    # it. Far nets (far side): each cap's FAR pin joined to its power-symbol pin
    # (own 2-terminal net) or, for signal/merge destinations, grouped by net so
    # every tap of a merge node (ethernet's BS_COMMON) plus its shared label is
    # one net. reroute_module wires each net's terminals with exact on-pin
    # endpoints — the ground truth the grid routers never had.
    net_terms: list[tuple[str, tuple[Point, ...]]] = []
    for net_key, terms in trunk_nets.items():
        if len(terms) >= 2:
            net_terms.append((net_key, tuple(terms)))
    signal_groups: dict[str, list[Point]] = {}
    signal_label: dict[str, Point] = {}
    for cell in cells:
        _near, far = _passive_pins(cell.passive.position, cell.side)
        if cell.far_symbol is not None:
            try:
                sympins = list(geometry.absolute_pin_positions(
                    cell.far_symbol.lib_id, cell.far_symbol.position,
                    cell.far_symbol.rotation).values())
            except Exception:  # noqa: BLE001
                sympins = []
            net_terms.append(
                (f"{cell.to_net}@{far.x:.1f},{far.y:.1f}", tuple([far, *sympins]))
            )
        else:
            signal_groups.setdefault(cell.to_net, []).append(far)
            if cell.emit_label:
                _f, tip, _rot = _signal_far(cell)
                signal_label[cell.to_net] = tip
    for to_net, fars in signal_groups.items():
        pts = list(fars)
        if to_net in signal_label:
            pts.append(signal_label[to_net])
        if len(pts) >= 2:
            net_terms.append((to_net, tuple(pts)))

    # Bare IC power/GND pins (no decoupling cap of their own) need connecting.
    # PREFER a LOCAL power symbol when the pin's immediate outboard grid cell is
    # OPEN: a local GND/+3V3 flag at the pin joins the GLOBAL rail with a tiny
    # stub and NO trunk across the IC — which is what kills the long-trunk-over-
    # signal-pins short the net-blind junctioner welds (INA226 GND over
    # SDA/SCL/Alert). On a CONGESTED edge (no clear 1-grid spot) fall back to the
    # proven wire to the nearest existing far power symbol of the net, so dense
    # power ICs (FUSB302) keep their exact prior clean layout — no regression.
    sym_by_net: dict[str, list[Point]] = {}
    for cell in cells:
        if cell.far_symbol is not None:
            try:
                for pp in geometry.absolute_pin_positions(
                    cell.far_symbol.lib_id, cell.far_symbol.position,
                    cell.far_symbol.rotation).values():
                    sym_by_net.setdefault(cell.to_net, []).append(pp)
            except Exception:  # noqa: BLE001
                pass
    trunk_keys = {(round(t.x, 2), round(t.y, 2))
                  for terms in trunk_nets.values() for t in terms}
    try:
        ic_names = {str(pi["number"]): str(pi["name"])
                    for pi in geometry.all_pins(ic.lib_id, 0.0)}
        ic_pos = geometry.absolute_pin_positions(ic.lib_id, anchor, 0.0)
    except Exception:  # noqa: BLE001
        ic_names, ic_pos = {}, {}
    if ic_pos:
        # Obstacle set the local symbol must clear: IC body, every placed
        # symbol/passive/far-symbol, every wire, every label text.
        obs = [symbol_footprint(s, geometry) for s in symbols]
        for w in wires:
            obs.append(wire_bbox(w.start, w.end))
        for l in labels:
            obs.append(text_bbox(l.net_name, l.position, rotation=l.rotation,
                                 justify="left", kind="label",
                                 owner_id=f"label:{l.net_name}"))
        body = symbol_footprint(ic_sym, geometry)
        bcx, bcy = body.center.x, body.center.y
        for num, pt in sorted(ic_pos.items(), key=lambda kv: str(kv[0])):
            if (round(pt.x, 2), round(pt.y, 2)) in trunk_keys:
                continue  # already on a trunk
            nm = ic_names.get(str(num), "")
            # GND, GND_EP (exposed pad), GND_1 … all map to the GND symbol net.
            net = "GND" if (nm in _GND_NAMES or nm.startswith("GND")) else nm
            _kind, far_lib = _classify_far(net)
            if far_lib is None:
                continue  # not a power-symbol net — exposer handles signal pins
            # Outboard side = the body edge the pin sits on (away from centre).
            if abs(pt.x - bcx) >= abs(pt.y - bcy):
                side: PageSide = "right" if pt.x >= bcx else "left"
            else:
                side = "bottom" if pt.y >= bcy else "top"
            placed = _place_pin_power_symbol(
                pt, side, far_lib, net, f"#PWR{p_ref}", geometry, obs, max_steps=1,
            )
            if placed is None and net not in sym_by_net:
                # No clear 1-grid spot AND no existing far symbol of this net to
                # trunk to (e.g. T1's GND pin: ethernet has only BS_COMMON /
                # CHASSIS_GND symbols). Leaving the pin unwired lets the exposer
                # merge it onto the adjacent foreign trunk (T1 pin-14 GND was
                # captured by BS_COMMON). So walk a LOCAL symbol a few grids out
                # — the pin sits on an open module edge, so a short walk clears.
                placed = _place_pin_power_symbol(
                    pt, side, far_lib, net, f"#PWR{p_ref}", geometry, obs, max_steps=4,
                )
            if placed is not None:
                sym, tip = placed
                symbols.append(sym)
                obs.append(symbol_footprint(sym, geometry))
                net_terms.append((f"{net}@ic{num}", (pt, tip)))
                p_ref += 1
            elif net in sym_by_net:
                # Congested edge → keep the proven far-symbol trunk (old path).
                tgt = min(sym_by_net[net],
                          key=lambda q: abs(q.x - pt.x) + abs(q.y - pt.y))
                net_terms.append((f"{net}@ic{num}", (pt, tgt)))

    bbox = _module_bbox(symbols, wires, labels, geometry)
    return Module(
        ic_ref=ic.reference,
        anchor=anchor,
        symbols=tuple(symbols),
        wires=tuple(wires),
        junctions=tuple(trunk_juncs),
        labels=tuple(labels),
        ports=tuple(ports),
        bbox=bbox,
        nets=tuple(net_terms),
    )


def _far_symbol_tip(far: Point, side: PageSide) -> Point:
    if side in ("left", "right"):
        return Point(far.x, snap_to_grid(far.y - VISUAL_CLEARANCE_MM))
    return Point(snap_to_grid(far.x + VISUAL_CLEARANCE_MM), far.y)


def _module_bbox(
    symbols: list[PlacedSymbol],
    wires: list[PlacedWire],
    labels: list[PlacedLabel],
    geometry: SymbolGeometryCache,
) -> BBox:
    boxes: list[BBox] = [symbol_footprint(s, geometry) for s in symbols]
    for w in wires:
        boxes.append(wire_bbox(w.start, w.end))
    for l in labels:
        boxes.append(
            text_bbox(l.net_name, l.position, rotation=l.rotation, justify="left",
                      kind="label", owner_id=f"label:{l.net_name}")
        )
    return BBox(
        min=Point(min(b.min.x for b in boxes), min(b.min.y for b in boxes)),
        max=Point(max(b.max.x for b in boxes), max(b.max.y for b in boxes)),
        kind="symbol",
        owner_id="module",
    )
