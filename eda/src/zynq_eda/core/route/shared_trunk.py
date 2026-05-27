"""Shared-trunk routing for multi-pin same-net groups (Wave F1).

When two or more pins of a single IC share the same target net AND share
a coordinate axis (all at the same Y, or all at the same X), the default
per-pin router emits one straight wire per pin and lets ``dedup`` merge
them into a single rail. That rail then crosses through every pin's
intrinsic pin-name text bbox because the rail Y equals every pin's Y.

The shared-trunk router replaces those parallel wires with a single
**trunk + stubs** topology — the canonical "bus rail" pattern used by
PYNQ-Z2, Arty Z7 and other professional schematic designs:

  * One vertical (or horizontal) **stub** drops from each pin to a clear
    trunk Y (or X) found via occupancy probing — typically 5-10 mm away
    from the pin row, on a row free of intrinsic text.
  * One **trunk** runs horizontally (or vertically) across the cluster
    at the clear coordinate.
  * The trunk extends to the **hier-label position** at the sheet edge,
    or to the centre between pins for an internal-only net.

Result: every pin sits at the END of its own short stub (no wire
crossing pin-name text), and the trunk sits on a clear row (no
collisions with anything else).

This is the simplest possible Steiner-tree topology — collinear
terminals collapse to a single backbone with N drops, no Hanan-grid
expansion needed. Full Steiner routing for non-collinear cases lands
in Phase F2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from zynq_eda.core.layout.bbox import (
    BBox,
    BBoxKind,
    wire_bbox,
)
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire


# Default kinds the trunk router treats as obstacles when picking a
# clear trunk Y/X. Same as the main router's default (symbol bodies,
# labels, intrinsic text). Wires are NOT obstacles (collinear same-net
# wires merge electrically; KiCad's net-name resolution handles it).
DEFAULT_AVOID_KINDS: frozenset[BBoxKind] = frozenset({
    "symbol",
    "label",
    "hierarchical_label",
    "sheet",
    "intrinsic_pin_name",
    "intrinsic_pin_number",
    "wire",  # project rule: no two wires may cross
})

# Trunk-Y (or trunk-X) candidate ladder, in mm. The trunk sits this far
# OFF the pin row, on the OUTWARD side of the body. Tried in ascending
# order; the first offset whose trunk path is collision-free wins.
TRUNK_OFFSET_LADDER_MM: tuple[float, ...] = (
    2.54, 5.08, 7.62, 10.16, 12.7, 15.24, 17.78, 20.32, 25.4, 30.48,
)


@dataclass(frozen=True)
class SharedTrunkRoute:
    """Result of a shared-trunk routing attempt.

    ``segments`` are PlacedWires in placement order: stub from each pin
    to the trunk, then the trunk itself, then optionally a connecting
    segment to the hier-label position.

    ``junctions`` are PlacedJunctions at every branch point — wherever
    a stub meets the trunk, we need a junction so KiCad's net solver
    recognises the merge.

    ``gave_up`` is True when no clear trunk offset was found in the
    ladder; in that case ``segments`` is empty and the caller should
    fall back to per-pin routing.

    ``trunk_axis`` is "y" when the trunk runs horizontal (pins share
    Y → trunk shifted in Y) and "x" when the trunk runs vertical.
    """

    segments: tuple[PlacedWire, ...]
    junctions: tuple[PlacedJunction, ...]
    trunk_axis: str  # "y" or "x"
    trunk_coord: float  # the chosen trunk Y or X
    gave_up: bool


def detect_collinear(
    pin_positions: Sequence[Point],
    tol_mm: float = 0.05,
) -> str | None:
    """Return "y" if all pins share Y, "x" if all share X, else None.

    Singletons return None (no shared trunk needed for one pin).
    """
    if len(pin_positions) < 2:
        return None
    ys = [p.y for p in pin_positions]
    xs = [p.x for p in pin_positions]
    if max(ys) - min(ys) <= tol_mm:
        return "y"
    if max(xs) - min(xs) <= tol_mm:
        return "x"
    return None


def route_shared_trunk(
    pin_positions: Sequence[Point],
    label_position: Point | None,
    occupancy: Occupancy,
    *,
    body_inside_direction: str,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[BBoxKind] = DEFAULT_AVOID_KINDS,
    clearance_mm: float = 0.5,
) -> SharedTrunkRoute:
    """Route a collinear multi-pin group as trunk + stubs.

    Args:
        pin_positions: Coordinates of every pin on the net. Must be
            collinear (all same Y or all same X). Caller should run
            :func:`detect_collinear` first.
        label_position: Where the hier-label sits. ``None`` for internal-
            only nets (the trunk just connects the pins). Otherwise the
            trunk extends from its midpoint to this point.
        occupancy: Live spatial index used to find a clear trunk
            coordinate.
        body_inside_direction: Which direction the IC body lies relative
            to the pin row — ``"up"``/``"down"`` when pins share Y (body
            below means top-edge pins, body above means bottom-edge),
            or ``"left"``/``"right"`` when pins share X. The trunk
            routes on the OPPOSITE side (away from the body) so it
            doesn't cross intrinsic text inside the body.
        avoid_owners: Bbox owners to skip during clearance checks.
        avoid_kinds: Bbox kinds to treat as obstacles.
        clearance_mm: Extra padding around each candidate wire segment.

    Returns:
        A :class:`SharedTrunkRoute`. ``gave_up=True`` if no clear trunk
        coordinate was found — caller should fall back.
    """
    axis = detect_collinear(pin_positions)
    if axis is None or not pin_positions:
        return SharedTrunkRoute(
            segments=(),
            junctions=(),
            trunk_axis="y",
            trunk_coord=0.0,
            gave_up=True,
        )

    if axis == "y":
        pin_row = pin_positions[0].y
        sign = -1 if body_inside_direction == "down" else +1
        trunk_y = _find_clear_trunk_coord(
            pin_row=pin_row,
            pin_xs=tuple(p.x for p in pin_positions),
            label_pos=label_position,
            occupancy=occupancy,
            sign=sign,
            horizontal_trunk=True,
            avoid_owners=avoid_owners,
            avoid_kinds=avoid_kinds,
            clearance_mm=clearance_mm,
        )
        if trunk_y is None:
            return SharedTrunkRoute(
                segments=(),
                junctions=(),
                trunk_axis="y",
                trunk_coord=pin_row,
                gave_up=True,
            )
        segments, junctions = _build_horizontal_trunk(
            pin_positions=pin_positions,
            label_position=label_position,
            trunk_y=trunk_y,
        )
        return SharedTrunkRoute(
            segments=tuple(segments),
            junctions=tuple(junctions),
            trunk_axis="y",
            trunk_coord=trunk_y,
            gave_up=False,
        )

    # axis == "x"
    pin_col = pin_positions[0].x
    sign = -1 if body_inside_direction == "right" else +1
    trunk_x = _find_clear_trunk_coord(
        pin_row=pin_col,
        pin_xs=tuple(p.y for p in pin_positions),
        label_pos=label_position,
        occupancy=occupancy,
        sign=sign,
        horizontal_trunk=False,
        avoid_owners=avoid_owners,
        avoid_kinds=avoid_kinds,
        clearance_mm=clearance_mm,
    )
    if trunk_x is None:
        return SharedTrunkRoute(
            segments=(),
            junctions=(),
            trunk_axis="x",
            trunk_coord=pin_col,
            gave_up=True,
        )
    segments, junctions = _build_vertical_trunk(
        pin_positions=pin_positions,
        label_position=label_position,
        trunk_x=trunk_x,
    )
    return SharedTrunkRoute(
        segments=tuple(segments),
        junctions=tuple(junctions),
        trunk_axis="x",
        trunk_coord=trunk_x,
        gave_up=False,
    )


def _find_clear_trunk_coord(
    *,
    pin_row: float,
    pin_xs: Sequence[float],
    label_pos: Point | None,
    occupancy: Occupancy,
    sign: int,
    horizontal_trunk: bool,
    avoid_owners: frozenset[str],
    avoid_kinds: frozenset[BBoxKind],
    clearance_mm: float,
) -> float | None:
    """Try offsets from pin_row in the given sign direction; return the
    first one where:

      - Each pin's stub wire (from pin to trunk) is collision-free
      - The trunk wire itself is collision-free

    Returns None if no offset in the ladder works.
    """
    x_lo = min(pin_xs)
    x_hi = max(pin_xs)
    if label_pos is not None:
        if horizontal_trunk:
            x_lo = min(x_lo, label_pos.x)
            x_hi = max(x_hi, label_pos.x)
        else:
            x_lo = min(x_lo, label_pos.y)
            x_hi = max(x_hi, label_pos.y)

    for offset in TRUNK_OFFSET_LADDER_MM:
        candidate = snap_to_grid(pin_row + sign * offset)

        # Check trunk segment is clear
        if horizontal_trunk:
            trunk_start = Point(x_lo, candidate)
            trunk_end = Point(x_hi, candidate)
        else:
            trunk_start = Point(candidate, x_lo)
            trunk_end = Point(candidate, x_hi)
        if _wire_collides(
            trunk_start, trunk_end, occupancy,
            avoid_owners=avoid_owners,
            avoid_kinds=avoid_kinds,
            clearance_mm=clearance_mm,
        ):
            continue

        # Check each stub is clear
        stubs_ok = True
        for x in pin_xs:
            if horizontal_trunk:
                stub_start = Point(x, pin_row)
                stub_end = Point(x, candidate)
            else:
                stub_start = Point(pin_row, x)
                stub_end = Point(candidate, x)
            if _wire_collides(
                stub_start, stub_end, occupancy,
                avoid_owners=avoid_owners,
                avoid_kinds=avoid_kinds,
                clearance_mm=clearance_mm,
            ):
                stubs_ok = False
                break
        if not stubs_ok:
            continue

        # Found a clear offset
        return candidate

    return None


def _wire_collides(
    start: Point,
    end: Point,
    occupancy: Occupancy,
    *,
    avoid_owners: frozenset[str],
    avoid_kinds: frozenset[BBoxKind],
    clearance_mm: float,
) -> bool:
    """True iff the wire from start to end collides with any bbox in
    occupancy that we care about (per ``avoid_kinds`` and not in
    ``avoid_owners``).

    Uses a TIGHT wire bbox (no extra clearance baked in) so near-miss
    intrinsic-text bboxes don't false-block the trunk router. The
    explicit ``clearance_mm`` argument is forwarded to the occupancy
    check as ``padding_mm`` so callers still control the safety margin.
    """
    if start.x == end.x and start.y == end.y:
        return False
    box = wire_bbox(start, end, clearance_mm=0.0, owner_id="_trunk_probe")
    # Build skip set: kinds NOT in avoid_kinds are skipped.
    skip_kinds = frozenset(
        kind for kind in (
            "symbol", "label", "hierarchical_label", "sheet_pin",
            "wire", "no_connect", "junction", "sheet",
            "intrinsic_pin_name", "intrinsic_pin_number",
        ) if kind not in avoid_kinds
    )
    hits = occupancy.collides(
        box,
        ignore_owners=avoid_owners,
        ignore_kinds=skip_kinds,
        padding_mm=clearance_mm,
    )
    return bool(hits)


def _build_horizontal_trunk(
    *,
    pin_positions: Sequence[Point],
    label_position: Point | None,
    trunk_y: float,
) -> tuple[list[PlacedWire], list[PlacedJunction]]:
    """Build wires + junctions for a horizontal trunk at ``trunk_y``.

    Pins share Y (the pin row). Stubs drop from each pin VERTICALLY to
    the trunk. The trunk runs HORIZONTALLY across all pin Xs (extended
    to the label X if a label is given).
    """
    segments: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []

    pin_xs = sorted({snap_to_grid(p.x) for p in pin_positions})
    pin_row = snap_to_grid(pin_positions[0].y)

    # Determine trunk extent in X
    if label_position is not None:
        label_x = snap_to_grid(label_position.x)
        trunk_x_lo = min(min(pin_xs), label_x)
        trunk_x_hi = max(max(pin_xs), label_x)
    else:
        trunk_x_lo = min(pin_xs)
        trunk_x_hi = max(pin_xs)

    # Vertical stubs from each pin to trunk
    for x in pin_xs:
        segments.append(PlacedWire(
            start=Point(x, pin_row),
            end=Point(x, trunk_y),
        ))
        # Junction at the trunk crossing — only if the trunk extends
        # past this pin in BOTH directions (interior crossing).
        if trunk_x_lo + 0.01 < x < trunk_x_hi - 0.01:
            junctions.append(PlacedJunction(position=Point(x, trunk_y)))

    # Horizontal trunk
    segments.append(PlacedWire(
        start=Point(trunk_x_lo, trunk_y),
        end=Point(trunk_x_hi, trunk_y),
    ))

    # Connect trunk to label if present and label not already on trunk
    if label_position is not None and abs(label_position.y - trunk_y) > 0.01:
        label_x = snap_to_grid(label_position.x)
        # Vertical from trunk end to label Y
        segments.append(PlacedWire(
            start=Point(label_x, trunk_y),
            end=Point(label_x, snap_to_grid(label_position.y)),
        ))

    return segments, junctions


def _build_vertical_trunk(
    *,
    pin_positions: Sequence[Point],
    label_position: Point | None,
    trunk_x: float,
) -> tuple[list[PlacedWire], list[PlacedJunction]]:
    """Build wires + junctions for a vertical trunk at ``trunk_x``.

    Mirror of :func:`_build_horizontal_trunk` for pins sharing X.
    """
    segments: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []

    pin_ys = sorted({snap_to_grid(p.y) for p in pin_positions})
    pin_col = snap_to_grid(pin_positions[0].x)

    if label_position is not None:
        label_y = snap_to_grid(label_position.y)
        trunk_y_lo = min(min(pin_ys), label_y)
        trunk_y_hi = max(max(pin_ys), label_y)
    else:
        trunk_y_lo = min(pin_ys)
        trunk_y_hi = max(pin_ys)

    for y in pin_ys:
        segments.append(PlacedWire(
            start=Point(pin_col, y),
            end=Point(trunk_x, y),
        ))
        if trunk_y_lo + 0.01 < y < trunk_y_hi - 0.01:
            junctions.append(PlacedJunction(position=Point(trunk_x, y)))

    segments.append(PlacedWire(
        start=Point(trunk_x, trunk_y_lo),
        end=Point(trunk_x, trunk_y_hi),
    ))

    if label_position is not None and abs(label_position.x - trunk_x) > 0.01:
        label_y = snap_to_grid(label_position.y)
        segments.append(PlacedWire(
            start=Point(trunk_x, label_y),
            end=Point(snap_to_grid(label_position.x), label_y),
        ))

    return segments, junctions
