"""Stage D — label every connector pin, conflict-free, via lane interleaving.

After Stage B/C, connectors sit on the page as bodies only; their per-pin
connectivity (nets crossing to other sheets) is unplaced. This module gives
each declared connector pin a label just outboard of its tip — a hierarchical
label for declared sheet-edge nets, a local label otherwise — with a stub wire
from pin to label.

THE HARD CASE (and the fix). Connector pins sit at 2.54 mm pitch, but a label
is ~1.3 mm tall and the Laws demand 2.54 mm breathing room, so two labels on
vertically-adjacent pins cannot BOTH read horizontally at pin pitch. The
principled answer (from the plan: "stagger connector hier-labels; pins never
move") is LANE INTERLEAVING: pins on an edge are assigned round-robin to L
outboard lanes, where L is the smallest count making the per-lane pitch
(L x pin-pitch) clear the label height + clearance, and successive lanes are
one label-width apart so lanes never overlap horizontally. Each pin's stub runs
out to its lane. This is point-feature placement with structured candidate
slots; a per-candidate validator-true bbox check (the SAME bboxes the overlap
validator measures) plus an extra-lane fallback guarantees clearance for
non-uniform edges too. Pins never move.
"""

from __future__ import annotations

import collections
from math import ceil

from zynq_eda.core.layout._builder import _hierarchical_label_bbox, _label_bbox
from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM
from zynq_eda.core.layout.bbox import BBox, text_width, wire_bbox
from zynq_eda.core.layout.geometry import SymbolGeometryCache, page_side_from_pin
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedWire,
)

_GRID = snap_to_grid(2.54)
_LABEL_HEIGHT_MM = 1.6  # label text box height with a little margin
_BASE_OUT = 2.0 * _GRID  # first lane's outboard distance (clears pin-number text)

# Primary outboard-reading rotation per side, then the alternate.
_SIDE_ROTS = {
    "left": (180.0, 0.0),
    "right": (0.0, 180.0),
    "top": (90.0, 270.0),
    "bottom": (270.0, 90.0),
}


def _decorated_width(net: str, is_ext: bool) -> float:
    return text_width(net + " " if is_ext else net)


def _outboard_anchor(tip: Point, side: str, dist: float) -> Point:
    if side == "left":
        return Point(snap_to_grid(tip.x - dist), tip.y)
    if side == "right":
        return Point(snap_to_grid(tip.x + dist), tip.y)
    if side == "top":
        return Point(tip.x, snap_to_grid(tip.y - dist))
    return Point(tip.x, snap_to_grid(tip.y + dist))


def _is_outboard(bb: BBox, tip: Point, side: str) -> bool:
    eps = 0.1
    if side == "left":
        return bb.max.x <= tip.x + eps
    if side == "right":
        return bb.min.x >= tip.x - eps
    if side == "top":
        return bb.max.y <= tip.y + eps
    return bb.min.y >= tip.y - eps


def _make(net, anchor, is_ext, direction, rot):
    if is_ext:
        obj = PlacedHierarchicalLabel(
            net_name=net, position=anchor, direction=direction, rotation=rot
        )
        return obj, _hierarchical_label_bbox(obj)
    obj = PlacedLabel(net_name=net, position=anchor, rotation=rot)
    return obj, _label_bbox(obj)


def label_connectors(
    block: Block,
    connectors,
    geometry: SymbolGeometryCache,
    occupied: list[BBox],
):
    """Return (labels, hlabels, wires) for every declared connector pin."""
    ext_dir = {n.name: n.direction for n in block.external_nets}
    labels: list[PlacedLabel] = []
    hlabels: list[PlacedHierarchicalLabel] = []
    wires: list[PlacedWire] = []

    for conn, sym in connectors:
        # Gather declared pins with resolved geometry, grouped by page edge.
        by_edge: dict[str, list[tuple[Point, str]]] = collections.defaultdict(list)
        for pin_id, net in conn.pin_to_net:
            try:
                pg = geometry.pin_geometry_by_name(
                    conn.lib_id, sym.position, pin_id, conn.rotation
                )
            except KeyError:
                continue
            side = page_side_from_pin(pg.pin_rotation, conn.rotation)
            by_edge[side].append((pg.connection, net))

        for side, grp in by_edge.items():
            _place_edge(
                side, grp, ext_dir, occupied, labels, hlabels, wires
            )
    return labels, hlabels, wires


def _place_edge(side, grp, ext_dir, occupied, labels, hlabels, wires):
    """Lane-interleave one connector edge's labels."""
    horizontal = side in ("left", "right")
    along = (lambda tn: tn[0].y) if horizontal else (lambda tn: tn[0].x)
    grp = sorted(grp, key=along)

    distinct = sorted({along(tn) for tn in grp})
    pitch = min(
        (distinct[i + 1] - distinct[i] for i in range(len(distinct) - 1)),
        default=5.08,
    )
    pitch = max(pitch, _GRID)
    lanes = max(1, ceil((_LABEL_HEIGHT_MM + VISUAL_CLEARANCE_MM) / pitch))
    max_w = max(_decorated_width(net, net in ext_dir) for _t, net in grp)
    lane_w = max_w + VISUAL_CLEARANCE_MM
    # Round-robin lane per distinct along-edge coordinate, so vertically
    # adjacent rows fall in different lanes (per-lane pitch = lanes * pitch).
    coord_lane = {c: i % lanes for i, c in enumerate(distinct)}

    rots = _SIDE_ROTS[side]
    for tip, net in grp:
        is_ext = net in ext_dir
        direction = ext_dir.get(net, "passive")
        base_lane = coord_lane[along(tip)]
        placed = None
        # Try the assigned lane first, then push further out (extra lanes).
        for extra in range(0, 6):
            dist = _BASE_OUT + (base_lane + extra * lanes) * lane_w
            anchor = _outboard_anchor(tip, side, dist)
            for rot in rots:
                obj, bb = _make(net, anchor, is_ext, direction, rot)
                if not _is_outboard(bb, tip, side):
                    continue
                if placed is None:
                    placed = (obj, bb)  # first outboard candidate = fallback
                if not any(
                    bb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM) for o in occupied
                ):
                    placed = (obj, bb)
                    break
            else:
                continue
            break
        if placed is None:
            continue
        obj, bb = placed
        occupied.append(bb)
        if obj.position != tip:
            stub = PlacedWire(tip, obj.position)
            wires.append(stub)
            occupied.append(wire_bbox(stub.start, stub.end, owner_id="stub"))
        if is_ext:
            hlabels.append(obj)
        else:
            labels.append(obj)
