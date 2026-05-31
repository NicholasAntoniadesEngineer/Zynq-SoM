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
            best = None
            best_clashes = None
            # Try a few lane counts; keep whichever places this edge with the
            # fewest clashes against the current page (render-is-judge). A
            # single straight outboard column (lanes=1) is always a candidate,
            # so multi-lane can only ever help, never regress.
            for lanes in (1, 2, 3, 4):
                trial = _place_edge(side, grp, ext_dir, occupied, lanes)
                clashes = _count_clashes(trial, occupied)
                if best is None or clashes < best_clashes:
                    best, best_clashes = trial, clashes
                if best_clashes == 0:
                    break
            for obj, bb, stub in best:
                occupied.append(bb)
                if stub is not None:
                    wires.append(stub)
                    occupied.append(wire_bbox(stub.start, stub.end, owner_id="stub"))
                if isinstance(obj, PlacedHierarchicalLabel):
                    hlabels.append(obj)
                else:
                    labels.append(obj)
    return labels, hlabels, wires


def _count_clashes(trial, occupied):
    """How many placed (label box, stub box) collide with the page or peers."""
    boxes = []
    n = 0
    for obj, bb, stub in trial:
        probe = [bb] + ([wire_bbox(stub.start, stub.end, owner_id="s")] if stub else [])
        for pb in probe:
            if any(pb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM) for o in occupied):
                n += 1
            elif any(pb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM) for o in boxes):
                n += 1
        boxes.extend(probe)
    return n


def _place_edge(side, grp, ext_dir, occupied, lanes):
    """Return [(label_obj, bbox, stub_or_None)] for one edge with ``lanes``
    interleaved outboard columns. Does NOT mutate occupied (caller commits)."""
    horizontal = side in ("left", "right")
    # Coordinate ALONG the edge (the axis pins march down): y for left/right
    # columns, x for top/bottom rows.
    coord_of = (lambda p: p.y) if horizontal else (lambda p: p.x)
    grp = sorted(grp, key=lambda tn: coord_of(tn[0]))

    distinct = sorted({coord_of(t) for t, _ in grp})
    max_w = max(_decorated_width(net, net in ext_dir) for _t, net in grp)
    lane_w = max_w + VISUAL_CLEARANCE_MM
    coord_lane = {c: i % lanes for i, c in enumerate(distinct)}

    rots = _SIDE_ROTS[side]
    out: list = []
    local: list = []  # bboxes placed so far this edge, for self-clearance
    for tip, net in grp:
        is_ext = net in ext_dir
        direction = ext_dir.get(net, "passive")
        base_lane = coord_lane[coord_of(tip)]
        chosen = None
        fallback = None
        # Walk the assigned lane outward; also try one and two extra base grids
        # so a label can clear inboard obstacles (e.g. the connector's own
        # pin-number text on the dual-row right edge) without changing lane.
        for extra in range(0, 8):
            dist = _BASE_OUT + extra * _GRID + (base_lane + (extra // 2) * lanes) * lane_w
            anchor = _outboard_anchor(tip, side, dist)
            for rot in rots:
                obj, bb = _make(net, anchor, is_ext, direction, rot)
                if not _is_outboard(bb, tip, side):
                    continue
                stub = None if obj.position == tip else PlacedWire(tip, obj.position)
                probe = [bb] + (
                    [wire_bbox(stub.start, stub.end, owner_id="s")] if stub else []
                )
                if fallback is None:
                    fallback = (obj, bb, stub)
                clash = any(
                    pb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM)
                    for pb in probe for o in occupied + local
                )
                if not clash:
                    chosen = (obj, bb, stub)
                    break
            if chosen is not None:
                break
        pick = chosen or fallback
        if pick is None:
            continue
        out.append(pick)
        local.append(pick[1])
        if pick[2] is not None:
            local.append(wire_bbox(pick[2].start, pick[2].end, owner_id="s"))
    return out
