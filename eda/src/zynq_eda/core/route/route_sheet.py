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
from zynq_eda.core.layout.edge_labels import (
    expose_ic_pin_nets,
    no_connect_markers,
    power_drive_stamps,
)
from zynq_eda.core.layout.module import Module
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire, Sheet
from zynq_eda.core.layout.bbox import wire_bbox
from zynq_eda.core.route.route_module import _obstacles, reroute_module


def route_sheet(
    block: Block,
    geometry: SymbolGeometryCache,
    *,
    reroute: bool = True,
    stamp_nets: set[str] | None = None,
) -> Sheet:
    """Return the complete wired :class:`Sheet` for ``block``.

    Runs Stage B placement, optionally re-routes dense modules with A*, then
    assembles symbols + labels + wires + junctions. Connectors are bodies only
    (their pin nets become edge hier-labels in Stage D).

    ``stamp_nets`` is the set of global power nets this sheet should emit a
    PWR_FLAG drive stamp for (the pipeline assigns each net to the first sheet
    that contains it, so each global net is driven exactly once).
    """
    arr = arrange_block(block, geometry)
    return assemble_sheet(arr, geometry, block, reroute=reroute, stamp_nets=stamp_nets)


def assemble_sheet(
    arr: Arrangement,
    geometry: SymbolGeometryCache,
    block: Block,
    *,
    reroute: bool = True,
    stamp_nets: set[str] | None = None,
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
    # Use PER-PRIMITIVE obstacles (body + each pin-name/number box) so a label
    # can sit in the gap between pin texts rather than being pushed clear of the
    # whole connector's merged footprint.
    occupied = _obstacles(symbols, geometry)
    for w in wires:
        occupied.append(wire_bbox(w.start, w.end, owner_id="routed"))
    # Module-emitted labels (e.g. a cluster pin's own-net local label) are real
    # obstacles too — include them so the connector labeler AND the IC-pin
    # exposer place clear of them (else two labels land on the same row).
    from zynq_eda.core.validate.overlap import _label_text_bbox
    for lbl in labels:
        occupied.append(_label_text_bbox(lbl))
    conns = [(c.instance, c.symbol) for c in arr.connectors]
    clabels, chlabels, cwires = label_connectors(block, conns, geometry, occupied)
    wires.extend(cwires)

    ic_symbols = {
        m.ic_ref: next(s for s in m.symbols if s.reference == m.ic_ref)
        for m in arr.modules
    }

    # Stage E.1: expose every still-floating IC pin's net — power symbol (GND /
    # rails), hier-label (sheet-edge nets), or local label — on a clearance-
    # checked outboard stub, so no IC pin is left electrically dangling.
    connected = {(round(w.start.x, 2), round(w.start.y, 2)) for w in wires}
    connected |= {(round(w.end.x, 2), round(w.end.y, 2)) for w in wires}
    esyms, elabels, ehlabels, ewires = expose_ic_pin_nets(
        block, ic_symbols, geometry, occupied, connected
    )
    symbols.extend(esyms)
    wires.extend(ewires)

    # Stage E.2: No-Connect markers on every still-unused pin (connector spares
    # + NC IC pins), so ERC stops firing pin_not_connected on unused pins.
    no_connects = no_connect_markers(block, conns, geometry, ic_symbols)

    # Stage E.3: PWR_FLAG drive stamps for the global power nets assigned to this
    # sheet, so ERC stops firing power_pin_not_driven (a power symbol is power-
    # INPUT; a PWR_FLAG marks the net externally driven). One flag per global
    # net drives it project-wide; the pipeline assigns each net once.
    if stamp_nets:
        ssyms, swires = power_drive_stamps(
            sorted(stamp_nets), arr.sheet.paper_size, geometry, occupied
        )
        symbols.extend(ssyms)
        wires.extend(swires)

    return Sheet(
        name=arr.sheet.name,
        title=arr.sheet.title,
        paper_size=arr.sheet.paper_size,
        symbols=tuple(symbols),
        labels=tuple(labels + clabels + elabels),
        hierarchical_labels=tuple(chlabels + ehlabels),
        wires=tuple(wires),
        junctions=tuple(junctions),
        no_connects=tuple(no_connects),
    )
