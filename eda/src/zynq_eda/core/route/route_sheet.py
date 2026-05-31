"""Stage C — assemble the fully wired sheet from a Stage B arrangement.

Stage B (:mod:`zynq_eda.core.layout.arrange`) froze every module and spread the
units with zero symbol+label overlap. Each :class:`~zynq_eda.core.layout.module.Module`
already carries its intra-module wiring (trunk/drop + far stubs). This stage
assembles the complete sheet — symbols + labels + wires + junctions — and is the
seam where dense modules get their wiring re-routed cleanly (A*).

Empirically, after Stage B the naive intra-module wiring is already clean on
every sheet EXCEPT the three densest IC modules (ethernet's 9-tap Bob-Smith,
the 14-part FUSB302, the 8-part CP2102N), where trunk/drop wires cross bodies,
pin text, and each other. :func:`route_sheet` re-routes exactly those modules
with the bounded grid A* (:mod:`zynq_eda.core.route.astar`) against a per-symbol
obstacle set; clean-routing modules keep their (already clean) naive wires.
"""

from __future__ import annotations

from zynq_eda.core.layout.arrange import Arrangement, arrange_block
from zynq_eda.core.layout.footprint import symbol_footprint
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.layout.labeler import label_connectors
from zynq_eda.core.layout.module import Module
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire, Sheet
from zynq_eda.core.layout.bbox import wire_bbox
from zynq_eda.core.route.route_module import reroute_module


def route_sheet(
    block: Block,
    geometry: SymbolGeometryCache,
    *,
    reroute: bool = True,
) -> Sheet:
    """Return the complete wired :class:`Sheet` for ``block``.

    Runs Stage B placement, optionally re-routes dense modules with A*, then
    assembles symbols + labels + wires + junctions. Connectors are bodies only
    (their pin nets become edge hier-labels in Stage D).
    """
    arr = arrange_block(block, geometry)
    return assemble_sheet(arr, geometry, block, reroute=reroute)


def assemble_sheet(
    arr: Arrangement,
    geometry: SymbolGeometryCache,
    block: Block,
    *,
    reroute: bool = True,
) -> Sheet:
    symbols = list(arr.sheet.symbols)
    labels = list(arr.sheet.labels)
    wires: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []

    for module in arr.modules:
        routed: Module = reroute_module(module, geometry) if reroute else module
        wires.extend(routed.wires)
        junctions.extend(routed.junctions)

    # Stage D: label every connector pin, clearing the placed symbols + wires.
    occupied = [symbol_footprint(s, geometry) for s in symbols]
    for w in wires:
        occupied.append(wire_bbox(w.start, w.end, owner_id="routed"))
    conns = [(c.instance, c.symbol) for c in arr.connectors]
    clabels, chlabels, cwires = label_connectors(block, conns, geometry, occupied)
    wires.extend(cwires)

    return Sheet(
        name=arr.sheet.name,
        title=arr.sheet.title,
        paper_size=arr.sheet.paper_size,
        symbols=tuple(symbols),
        labels=tuple(labels + clabels),
        hierarchical_labels=tuple(chlabels),
        wires=tuple(wires),
        junctions=tuple(junctions),
    )
