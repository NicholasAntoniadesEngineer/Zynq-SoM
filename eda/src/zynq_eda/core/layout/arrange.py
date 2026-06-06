"""Global placement — spread frozen modules + connectors across the page.

Stage B of the convergent layout engine. Stage A (:mod:`module`) solved each IC
into a clean, frozen :class:`~zynq_eda.core.layout.module.Module`. Here every
module and every connector becomes ONE rigid rectangle; they are spread to fill
the A3 page via :func:`regions.partition_and_assign` and then PROJECTED to zero
mutual overlap with the exact projector :func:`separate.remove_overlaps`.

Why this meets the make-or-break gate (symbols+labels overlap=0 on all sheets)
by construction:

  * A module is internally clean (Stage A) and is moved here ONLY by rigid
    translation — which cannot change its interior clearance.
  * Units are placed in non-overlapping regions each sized >= the largest unit
    footprint, so they already don't overlap; the projector is an exact safety
    net that guarantees >= 2.54 mm between any two units' footprints (the same
    body+text footprints the overlap validator measures).

Therefore "no two units overlap" + "no module self-overlaps" ⇒ the whole sheet
is overlap-free on symbols+labels. Wires are NOT emitted here — routing is
Stage C (the plan's gate is explicitly "symbols+labels, no wires").
"""

from __future__ import annotations

from dataclasses import dataclass

from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM, VISUAL_CLEARANCE_MM
from zynq_eda.core.layout.footprint import bbox_to_rect, symbol_footprint
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.layout.module import Module, ModulePort, solve_module
from zynq_eda.core.layout.regions import Region, Unit, partition_and_assign
from zynq_eda.core.layout.separate import remove_overlaps
from zynq_eda.core.model.block import Block, ConnectorInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM, PlacedLabel, PlacedSymbol, Sheet


# Unit anchors snap to the grid, so projecting at exactly the 2.54 mm clearance
# can leave a pair up to ~one grid short after snapping. Target clearance + one
# grid of margin so quantisation always lands >= 2.54 mm (validation stays
# strict at 2.54; this only over-satisfies it). Mirrors module._PROJECT_GAP.
_PROJECT_GAP = VISUAL_CLEARANCE_MM + 1.27


@dataclass(frozen=True)
class PlacedConnector:
    """A connector placed as a rigid body (its pins are wired in Stage C)."""

    instance: ConnectorInstance
    symbol: PlacedSymbol
    edge: str  # "left" / "right" / "middle"


@dataclass(frozen=True)
class Arrangement:
    """Result of Stage B: every unit placed, spread, projected feasible.

    Carries the frozen modules and placed connectors (with their net info) so
    Stage C can route between them; ``sheet`` is the symbols+labels-only view
    used for the make-or-break overlap gate and the render review.
    """

    block_name: str
    modules: tuple[Module, ...]
    connectors: tuple[PlacedConnector, ...]
    sheet: Sheet


def _edge_str(connector: ConnectorInstance) -> str:
    """Map a connector's declared SheetEdge to the regions edge bias string."""
    name = getattr(connector.edge, "name", str(connector.edge)).lower()
    if "left" in name:
        return "left"
    if "right" in name:
        return "right"
    return "middle"


def _connector_symbol(
    connector: ConnectorInstance,
    anchor: Point,
    geometry: SymbolGeometryCache | None = None,
) -> PlacedSymbol:
    rc = connector.refcircuit
    # A connector's wide part-name Value text (e.g. "HX-PZ1.27-2x5P-TP", ~21 mm)
    # defaults to a position that can sit ON a pin row, where a pin's outboard
    # label stub then crosses it. Shift Value BELOW the body, clear of every pin
    # row, so the pin-label lanes stay free. Shift is in symbol-local coords at
    # rotation 0 (page +Y down); we place it one clearance below the body bottom.
    value_shift = None
    if geometry is not None:
        try:
            bb = geometry.bounding_box(connector.lib_id, rotation=0.0)
            below = bb.max_y + VISUAL_CLEARANCE_MM + 1.27  # body bottom + gap
            value_shift = (0.0, below, None)
        except Exception:
            value_shift = None
    return PlacedSymbol(
        lib_id=connector.lib_id,
        reference=connector.reference,
        value=getattr(rc, "part_mpn", connector.reference),
        position=Point(snap_to_grid(anchor.x), snap_to_grid(anchor.y)),
        footprint=getattr(rc, "footprint", ""),
        rotation=connector.rotation,
        value_shift=value_shift,
    )


def _center_symbol_in_region(
    connector: ConnectorInstance, region: Region, geometry: SymbolGeometryCache
) -> PlacedSymbol:
    """Place a connector so its full footprint centre lands at the region centre."""
    probe = _connector_symbol(connector, Point(0.0, 0.0), geometry)
    foot = symbol_footprint(probe, geometry)
    anchor = Point(
        snap_to_grid(region.cx - foot.center.x),
        snap_to_grid(region.cy - foot.center.y),
    )
    return _connector_symbol(connector, anchor, geometry)


def _signal_sides_by_ic(
    block: Block, geometry: SymbolGeometryCache
) -> dict[str, frozenset[str]]:
    """Map each IC reference to the set of body edges carrying a SIGNAL pin.

    A signal pin = a planner ``EDGE_LABEL`` / ``LOCAL_LABEL`` pin with a net —
    exactly the pins :func:`expose_ic_pin_nets` must drop a hier/local label on,
    whose outboard lane therefore must stay clear of decoupling caps. ``page_side``
    is the planner's own per-pin edge (its label-justify uses the same), so the
    offload edge and the exposer's placement edge always agree."""
    try:
        from zynq_eda.core.layout.plan import plan_pin_specs
        specs = plan_pin_specs(block, geometry)
    except Exception:  # noqa: BLE001 — no planner ⇒ legacy (no offload)
        return {}
    out: dict[str, set[str]] = {}
    for sp in specs:
        if sp.owner_kind != "ic" or sp.role not in ("EDGE_LABEL", "LOCAL_LABEL"):
            continue
        if not (sp.net_name or sp.cluster_owner_net):
            continue
        out.setdefault(sp.owner_ref, set()).add(sp.page_side)
    return {ref: frozenset(sides) for ref, sides in out.items()}


def arrange_block(
    block: Block,
    geometry: SymbolGeometryCache,
    *,
    margin: float = INTERIOR_MARGIN_MM,
) -> Arrangement:
    """Place every module + connector on ``block``'s page, spread + projected.

    Returns an :class:`Arrangement`; its ``sheet`` has symbols+labels only and
    is overlap-free at 2.54 mm by construction.
    """
    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]

    # ---- Per-IC SIGNAL edges (Stage-D2): which body edges carry a sheet-edge /
    # local-label signal pin whose outboard lane the exposer needs CLEAR. A
    # decoupling cap seeding on such an edge boxes that pin's label → an OPEN;
    # solve_module offloads those caps below the IC. Computed once from the
    # planner (the SAME classifier the exposer dispatches on) and threaded in.
    signal_sides_by_ic = _signal_sides_by_ic(block, geometry)

    # ---- Solve each IC into a frozen module (Stage A); place each connector --
    modules: list[Module] = []
    for i, ic in enumerate(block.ics):
        # Disjoint reference ranges per IC so designators never collide.
        modules.append(solve_module(
            ic, geometry, ref_start=100 + 100 * i,
            signal_sides=signal_sides_by_ic.get(ic.reference, frozenset()),
        ))

    placed_conns: list[tuple[ConnectorInstance, PlacedSymbol]] = []
    for connector in block.connectors:
        placed_conns.append((connector, _connector_symbol(connector, Point(0.0, 0.0), geometry)))

    # ---- Footprint per unit → regions → centre each unit in its region -------
    units: list[Unit] = []
    foot_by_ref: dict[str, object] = {}
    for m in modules:
        units.append(Unit(ref=m.ic_ref, w=m.bbox.width, h=m.bbox.height, edge=None))
        foot_by_ref[m.ic_ref] = m.bbox
    for connector, sym in placed_conns:
        foot = symbol_footprint(sym, geometry)
        foot_by_ref[connector.reference] = foot
        units.append(
            Unit(ref=connector.reference, w=foot.width, h=foot.height,
                 edge=_edge_str(connector))
        )

    if not units:
        return Arrangement(block.name, (), (), _empty_sheet(block))

    regions = partition_and_assign(units, paper_w, paper_h, margin)

    # Centre each module in its region (rigid translate).
    centered_modules: list[Module] = []
    for m in modules:
        reg = regions[m.ic_ref]
        centered_modules.append(
            m.translated(reg.cx - m.bbox.center.x, reg.cy - m.bbox.center.y)
        )
    # Centre each connector in its region.
    centered_conns: list[tuple[ConnectorInstance, PlacedSymbol]] = []
    for connector, _sym in placed_conns:
        centered_conns.append(
            (connector, _center_symbol_in_region(connector, regions[connector.reference], geometry))
        )

    # ---- Project: exact >= 2.54 mm between every pair of unit footprints -----
    order: list[str] = [m.ic_ref for m in centered_modules] + [
        c.reference for c, _ in centered_conns
    ]
    rects = [bbox_to_rect(m.bbox) for m in centered_modules] + [
        bbox_to_rect(symbol_footprint(s, geometry)) for _c, s in centered_conns
    ]
    new_centers = remove_overlaps(rects, gap=_PROJECT_GAP)

    final_modules: list[Module] = []
    for m, rect, (ncx, ncy) in zip(centered_modules, rects, new_centers[: len(centered_modules)]):
        final_modules.append(m.translated(ncx - rect.cx, ncy - rect.cy))

    final_conns: list[PlacedConnector] = []
    conn_rects = rects[len(centered_modules):]
    conn_centers = new_centers[len(centered_modules):]
    for (connector, sym), rect, (ncx, ncy) in zip(centered_conns, conn_rects, conn_centers):
        dx = snap_to_grid(ncx - rect.cx)
        dy = snap_to_grid(ncy - rect.cy)
        moved = PlacedSymbol(
            lib_id=sym.lib_id, reference=sym.reference, value=sym.value,
            position=Point(sym.position.x + dx, sym.position.y + dy),
            footprint=sym.footprint, rotation=sym.rotation,
            properties=sym.properties, value_shift=sym.value_shift,
            reference_shift=sym.reference_shift,
        )
        final_conns.append(PlacedConnector(connector, moved, _edge_str(connector)))

    sheet = _assemble_sheet(block, final_modules, final_conns)
    return Arrangement(block.name, tuple(final_modules), tuple(final_conns), sheet)


def _assemble_sheet(
    block: Block, modules: list[Module], connectors: list[PlacedConnector]
) -> Sheet:
    """Symbols+labels-only sheet (no wires) — the Stage B gate + render view."""
    symbols: list[PlacedSymbol] = []
    labels: list[PlacedLabel] = []
    for m in modules:
        symbols.extend(m.symbols)
        labels.extend(m.labels)
    for c in connectors:
        symbols.append(c.symbol)
    return Sheet(
        name=block.name,
        title=block.title,
        paper_size=block.paper_size,
        symbols=tuple(symbols),
        labels=tuple(labels),
    )


def _empty_sheet(block: Block) -> Sheet:
    return Sheet(name=block.name, title=block.title, paper_size=block.paper_size)
