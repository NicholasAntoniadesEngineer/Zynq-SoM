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


def _seed_anchor(pin: Point, side: PageSide, slot: int) -> Point:
    """Initial passive anchor: outboard from the pin (datasheet intent).

    Only a SEED — the projector + pull-in produce the final position. Slots
    fan outboard so the projector starts from a sane, near-feasible state."""
    outboard = PASSIVE_OFFSET_MM + slot * PASSIVE_PITCH_MM
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
        slot = edge_slot.get(side, 0)
        edge_slot[side] = slot + 1

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
        if far_lib is not None:
            far_symbol, _tip = _place_far_symbol(
                far, side, far_lib, to_net, f"#PWR{p_ref}", geometry,
            )
            p_ref += 1

        cells.append(_Cell(pin, side, to_net, far_kind, passive, far_symbol))

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
            [ic_rect, *cell_rects], gap=VISUAL_CLEARANCE_MM, movable=movable
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
    return _finalize(ic, anchor, ic_sym, cells, geometry)


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
    if cell.far_symbol is None:
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
) -> Module:
    symbols: list[PlacedSymbol] = [ic_sym]
    wires: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []
    labels: list[PlacedLabel] = []
    ports: list[ModulePort] = []

    # Group cells by the pin they hang off so co-pin passives share a trunk.
    by_pin: dict[tuple[float, float], list[_Cell]] = {}
    for cell in cells:
        by_pin.setdefault((round(cell.pin.x, 3), round(cell.pin.y, 3)), []).append(cell)

    for group in by_pin.values():
        side = group[0].side
        pin = group[0].pin
        _wire_group(pin, side, group, geometry, wires, junctions, labels, ports, symbols)

    bbox = _module_bbox(symbols, wires, labels, geometry)
    return Module(
        ic_ref=ic.reference,
        anchor=anchor,
        symbols=tuple(symbols),
        wires=tuple(wires),
        junctions=tuple(junctions),
        labels=tuple(labels),
        ports=tuple(ports),
        bbox=bbox,
    )


def _wire_group(
    pin: Point,
    side: PageSide,
    group: list[_Cell],
    geometry: SymbolGeometryCache,
    wires: list[PlacedWire],
    junctions: list[PlacedJunction],
    labels: list[PlacedLabel],
    ports: list[ModulePort],
    symbols: list[PlacedSymbol],
) -> None:
    """Emit a trunk from the IC pin out to the farthest co-pin passive, a
    drop to each passive's near terminal, junctions at mid-trunk taps, and the
    far-end stub + power-symbol/label for each passive."""
    horizontal = side in ("left", "right")
    nears: list[tuple[_Cell, Point, Point]] = []  # (cell, near, far)
    for cell in group:
        near, far = _passive_pins(cell.passive.position, side)
        nears.append((cell, near, far))

    # Trunk extent along the outboard axis (at the pin's cross-coord).
    if horizontal:
        outs = [near.x for _c, near, _f in nears]
        trunk_end = max(outs, key=lambda x: abs(x - pin.x))
        if trunk_end != pin.x:
            wires.append(PlacedWire(pin, Point(trunk_end, pin.y)))
    else:
        outs = [near.y for _c, near, _f in nears]
        trunk_end = max(outs, key=lambda y: abs(y - pin.y))
        if trunk_end != pin.y:
            wires.append(PlacedWire(pin, Point(pin.x, trunk_end)))

    for cell, near, far in nears:
        # The passive body itself is a placed symbol on the sheet.
        symbols.append(cell.passive)
        # Drop from the trunk to the passive's near terminal.
        if horizontal:
            tap = Point(near.x, pin.y)
            if tap != near:
                wires.append(PlacedWire(tap, near))
            is_mid = abs(near.x - pin.x) < abs(trunk_end - pin.x)
        else:
            tap = Point(pin.x, near.y)
            if tap != near:
                wires.append(PlacedWire(tap, near))
            is_mid = abs(near.y - pin.y) < abs(trunk_end - pin.y)
        if is_mid and tap != pin:
            junctions.append(PlacedJunction(tap))

        # Far end: power symbol (with a short visible stub) or a net label.
        if cell.far_symbol is not None:
            symbols.append(cell.far_symbol)
            tip = _far_symbol_tip(far, side)
            if tip != far:
                wires.append(PlacedWire(far, tip))
            ports.append(ModulePort(cell.to_net, far, side, cell.far_kind))
        else:
            _far, tip, rot = _signal_far(cell)
            if tip != far:
                wires.append(PlacedWire(far, tip))
            labels.append(PlacedLabel(net_name=cell.to_net, position=tip, rotation=rot))
            ports.append(ModulePort(cell.to_net, tip, side, "signal"))


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
