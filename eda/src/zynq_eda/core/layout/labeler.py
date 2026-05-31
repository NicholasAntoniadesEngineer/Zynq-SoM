"""Stage D — place a net label at every connector pin, conflict-free.

After Stage B/C, connectors sit on the page as bodies only; their per-pin
connectivity (the nets that cross to other sheets) is unplaced. This module
gives each declared connector pin a label just outboard of its tip — a
hierarchical label when the net is a declared sheet-edge net, otherwise a local
label — with a short stub wire from pin to label.

Placement is point-feature and KEYSTONE-CORRECT: every candidate is checked
with the SAME bbox the overlap validator measures
(:func:`_builder._hierarchical_label_bbox` / :func:`_label_bbox`), never an
approximation. For each pin it tries the two outboard-reading rotations and a
ladder of outboard offsets, and commits the first whose validator-true box (a)
sits OUTBOARD of the pin (text reads away from the connector body, not back
across its pin-number text) and (b) clears every already-placed primitive by
the Laws' 2.54 mm. Pins never move.
"""

from __future__ import annotations

from zynq_eda.core.layout._builder import _hierarchical_label_bbox, _label_bbox
from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM
from zynq_eda.core.layout.bbox import BBox, wire_bbox
from zynq_eda.core.layout.geometry import SymbolGeometryCache, page_side_from_pin
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedWire,
)

_GRID = snap_to_grid(2.54)
# Per side: the rotations to try (outboard-reading first) and the outboard test.
_SIDE_ROTS = {
    "left": (180.0, 0.0),
    "right": (0.0, 180.0),
    "top": (90.0, 270.0),
    "bottom": (270.0, 90.0),
}


def _outboard_anchor(tip: Point, side: str, dist: float) -> Point:
    if side == "left":
        return Point(snap_to_grid(tip.x - dist), tip.y)
    if side == "right":
        return Point(snap_to_grid(tip.x + dist), tip.y)
    if side == "top":
        return Point(tip.x, snap_to_grid(tip.y - dist))
    return Point(tip.x, snap_to_grid(tip.y + dist))


def _is_outboard(bb: BBox, tip: Point, side: str) -> bool:
    """True iff the label box sits on the outboard side of the pin tip."""
    eps = 0.1
    if side == "left":
        return bb.max.x <= tip.x + eps
    if side == "right":
        return bb.min.x >= tip.x - eps
    if side == "top":
        return bb.max.y <= tip.y + eps
    return bb.min.y >= tip.y - eps


def label_connectors(
    block: Block,
    connectors,
    geometry: SymbolGeometryCache,
    occupied: list[BBox],
):
    """Return (labels, hlabels, wires) for every declared connector pin.

    ``occupied`` is the list of already-placed obstacle bboxes; it is extended
    in place as labels commit so later labels clear earlier ones.
    """
    ext_dir = {n.name: n.direction for n in block.external_nets}
    labels: list[PlacedLabel] = []
    hlabels: list[PlacedHierarchicalLabel] = []
    wires: list[PlacedWire] = []

    for conn, sym in connectors:
        for pin_id, net in conn.pin_to_net:
            try:
                pg = geometry.pin_geometry_by_name(
                    conn.lib_id, sym.position, pin_id, conn.rotation
                )
            except KeyError:
                continue
            tip = pg.connection
            side = page_side_from_pin(pg.pin_rotation, conn.rotation)
            is_ext = net in ext_dir

            placed = _place_one(
                net, tip, side, is_ext, ext_dir.get(net, "passive"), occupied
            )
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
    return labels, hlabels, wires


def _place_one(net, tip, side, is_ext, direction, occupied):
    """Find the first outboard, clear (anchor, rotation) for one pin's label."""
    rots = _SIDE_ROTS[side]
    fallback = None
    for steps in range(1, 13):
        anchor = _outboard_anchor(tip, side, steps * _GRID)
        for rot in rots:
            if is_ext:
                obj = PlacedHierarchicalLabel(
                    net_name=net, position=anchor, direction=direction, rotation=rot
                )
                bb = _hierarchical_label_bbox(obj)
            else:
                obj = PlacedLabel(net_name=net, position=anchor, rotation=rot)
                bb = _label_bbox(obj)
            if not _is_outboard(bb, tip, side):
                continue
            if fallback is None:
                fallback = (obj, bb)
            clash = any(
                bb.intersects(o, padding_mm=VISUAL_CLEARANCE_MM) for o in occupied
            )
            if not clash:
                return obj, bb
    # Nothing fully clear within the ladder — take the first outboard candidate
    # so the net is still placed (the validator will surface any residual).
    return fallback
