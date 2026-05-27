"""Minimal occupancy-aware orthogonal wire router.

This module produces a sequence of one to three axis-aligned wire
segments connecting two grid-aligned points, attempting to avoid
colliding with bboxes already registered in an
:class:`~zynq_eda.core.layout.occupancy.Occupancy` index. The router
is deliberately simple: it tries a fixed ladder of routing shapes
(direct → single-L → double-L) and returns the first that doesn't
collide. There is no A* search and no rip-up; if every candidate
collides, the router returns a best-effort single-L route and a flag
the caller can log.

Why this design:

  * The cross-cluster wires Wave B targets (power-symbol stubs,
    signal-override stubs, the few GND attachments routed BETWEEN
    clusters rather than INSIDE them) are short. Most fit a direct
    H or V segment; nearly all fit a single L-bend.
  * The occupancy index already classifies bboxes by kind, so the
    router can ignore junctions / labels and only collide-check
    against symbol bodies + other wires.
  * A real router (A*, channel routing) would belong in a separate
    Wave; the current goal is just to stop routing THROUGH symbol
    bodies, not to optimise routing topology.

Public API: :func:`route_orthogonal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from zynq_eda.core.layout.bbox import BBox, BBoxKind, wire_bbox
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedWire


# ---- Defaults --------------------------------------------------------------

DEFAULT_AVOID_KINDS: frozenset[BBoxKind] = frozenset(
    {"symbol", "label", "hierarchical_label", "sheet",
     "intrinsic_pin_name", "intrinsic_pin_number",
     "wire"}
)
"""Bbox kinds the router avoids by default.

WIRES ARE OBSTACLES — the project's hard rule says no two wires may
cross, regardless of whether they're the same net or not. Crossing
wires create visual ambiguity (KiCad's net merge rules depend on
junction dots, which a reader can miss) and the user has ruled this
out for every schematic this engine emits.

Junctions / no-connects / sheet pins are tiny markers that don't
participate in collision checks.
"""

DEFAULT_CLEARANCE_MM: float = 2.0
"""Default clearance margin when collide-checking each candidate segment.

Set to :data:`VISUAL_CLEARANCE_MM` so the router cannot pick a route
that runs CLOSER than 2 mm to any symbol body, label, or pin text.
Without this, the router would emit wires that brushed against
component edges — visually they appear to touch even though the
strict bbox intersection is zero, which the user has ruled
unacceptable.

The validator's overlap check stays at zero clearance (the painted
stroke vs the painted bbox); the router's wider clearance is a
PLACEMENT constraint that gives the schematic room to breathe.
"""


# ---- Result type -----------------------------------------------------------

@dataclass(frozen=True)
class RouteResult:
    """Outcome of a routing attempt.

    Attributes:
        segments: Ordered list of placed wires forming the route.
            Always non-empty; even a giveup returns the best-effort
            single-L attempt.
        gave_up: True iff every candidate shape collided with the
            occupancy index and the router returned a best-effort
            fallback. The caller may want to log this for diagnostics.
        shape: Human-readable name of the shape that was picked:
            ``"direct"``, ``"single_l_h"``, ``"single_l_v"``,
            ``"double_l_h"``, ``"double_l_v"``, or ``"giveup"``.
    """

    segments: tuple[PlacedWire, ...]
    gave_up: bool
    shape: str


# ---- Internal helpers ------------------------------------------------------

def _make_wire(start: Point, end: Point) -> PlacedWire | None:
    """Return a PlacedWire iff start != end (filters zero-length segments)."""
    if start.x == end.x and start.y == end.y:
        return None
    return PlacedWire(start=start, end=end)


_ROUTER_NOISE_FLOOR_MM: float = 0.15
"""Match the validator's :data:`~zynq_eda.core.validate.overlap.OVERLAP_MIN_DIMENSION_MM`.

Two bboxes whose intersection is thinner than this on either axis
don't count as a collision — same rule the validator applies. Keeps
the router and validator in lock-step: anything the router approves
the validator accepts, and vice versa. Bumped from 0.1 mm to 0.15 mm
in lockstep with the validator's threshold tightening (the previous
0.1 mm flagged the wire's own half-thickness graze at pin tips).
"""


def _segments_collide(
    segments: Sequence[PlacedWire],
    occupancy: Occupancy,
    ignore_owners: frozenset[str],
    avoid_kinds: frozenset[BBoxKind],
    clearance_mm: float,
) -> bool:
    """True iff any segment's bbox has a SIGNIFICANT collision with the
    occupancy index — matching the validator's noise-floor filter.

    The probe bbox matches the post-hoc validator
    (:func:`zynq_eda.core.validate.overlap._wire_segment_bbox`): wire
    thickness 0.254 mm with directional padding only (perpendicular to
    the wire's axis, never past the endpoints). Intersections smaller
    than :data:`_ROUTER_NOISE_FLOOR_MM` on either axis are filtered as
    floating-point noise, so the router and validator agree on what
    counts as an overlap.

    ``clearance_mm`` is added on top via ``occupancy.collides``'s
    ``padding_mm``.
    """
    skip_kinds = frozenset(
        kind for kind in (
            "symbol", "label", "hierarchical_label", "sheet_pin",
            "wire", "no_connect", "junction", "sheet",
            "intrinsic_pin_name", "intrinsic_pin_number",
        ) if kind not in avoid_kinds
    )
    for segment in segments:
        bbox = wire_bbox(
            segment.start,
            segment.end,
            thickness_mm=0.254,
            clearance_mm=0.0,
            owner_id="_router_probe",
        )
        hits = occupancy.collides(
            bbox,
            ignore_owners=ignore_owners,
            ignore_kinds=skip_kinds,
            padding_mm=clearance_mm,
        )
        # Filter sub-noise-floor intersections so the router doesn't
        # reject what the validator accepts.
        for hit in hits:
            intersection = bbox.intersection(hit)
            if intersection is None:
                continue
            if (
                intersection.width >= _ROUTER_NOISE_FLOOR_MM
                and intersection.height >= _ROUTER_NOISE_FLOOR_MM
            ):
                return True
    return False


def _direct(start: Point, end: Point) -> tuple[PlacedWire, ...] | None:
    """Single straight segment if start and end share an axis."""
    if start.x == end.x or start.y == end.y:
        wire = _make_wire(start, end)
        if wire is None:
            return ()
        return (wire,)
    return None


def _single_l(
    start: Point, end: Point, horizontal_first: bool,
) -> tuple[PlacedWire, ...]:
    """Two-segment L-bend.

    ``horizontal_first=True`` → start → (end.x, start.y) → end
    ``horizontal_first=False`` → start → (start.x, end.y) → end
    """
    if horizontal_first:
        corner = Point(end.x, start.y)
    else:
        corner = Point(start.x, end.y)
    segments: list[PlacedWire] = []
    seg_a = _make_wire(start, corner)
    seg_b = _make_wire(corner, end)
    if seg_a is not None:
        segments.append(seg_a)
    if seg_b is not None:
        segments.append(seg_b)
    return tuple(segments)


def _double_l(
    start: Point, end: Point, horizontal_first: bool,
) -> tuple[PlacedWire, ...]:
    """Three-segment double-L (Z) detour through a midpoint.

    ``horizontal_first=True`` → goes H then V then H via mx = (start.x+end.x)/2.
    ``horizontal_first=False`` → goes V then H then V via my = (start.y+end.y)/2.
    """
    if horizontal_first:
        mx = snap_to_grid((start.x + end.x) / 2.0)
        c1 = Point(mx, start.y)
        c2 = Point(mx, end.y)
    else:
        my = snap_to_grid((start.y + end.y) / 2.0)
        c1 = Point(start.x, my)
        c2 = Point(end.x, my)
    segments: list[PlacedWire] = []
    for s, e in ((start, c1), (c1, c2), (c2, end)):
        wire = _make_wire(s, e)
        if wire is not None:
            segments.append(wire)
    return tuple(segments)


# ---- Public entry point ----------------------------------------------------

def route_orthogonal(
    start: Point,
    end: Point,
    occupancy: Occupancy,
    *,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[BBoxKind] = DEFAULT_AVOID_KINDS,
    clearance_mm: float = DEFAULT_CLEARANCE_MM,
) -> list[PlacedWire]:
    """Route ``start → end`` orthogonally avoiding bboxes in ``occupancy``.

    Strategy (first non-colliding shape wins):

      1. **Direct** — if ``start.x == end.x`` (vertical) or
         ``start.y == end.y`` (horizontal), emit one segment.
      2. **Single L-bend, horizontal-first** —
         ``start → (end.x, start.y) → end``.
      3. **Single L-bend, vertical-first** —
         ``start → (start.x, end.y) → end``.
      4. **Double L, horizontal-first** — detour through
         ``mx = (start.x + end.x) / 2``.
      5. **Double L, vertical-first** — detour through
         ``my = (start.y + end.y) / 2``.

    For each candidate shape, every segment's bbox is collide-checked
    against the occupancy index. The first shape whose segments are
    ALL collision-free is returned. If every shape collides, the
    function returns the vertical-first single-L as a best-effort
    fallback — the result is still electrically correct, it just may
    cross a symbol body. Callers wanting to know about giveups should
    use :func:`route_orthogonal_detail` instead.

    Args:
        start: Grid-aligned source point.
        end: Grid-aligned target point.
        occupancy: Live spatial index built up during placement.
        avoid_owners: Owner ids to ignore during collision checks
            (e.g. the source / destination symbol's own bbox — their
            pin stubs would otherwise collide with the new wire).
        avoid_kinds: Bbox kinds to treat as obstacles. Defaults to
            ``DEFAULT_AVOID_KINDS`` (symbols + labels + sheet symbols).
            Wires/junctions/no-connects are crossed freely.
        clearance_mm: Extra clearance applied around each candidate
            segment's bbox during collision checks.

    Returns:
        Ordered list of :class:`PlacedWire` segments forming the
        route. Always non-empty (a same-point query returns ``[]``
        which is treated as a no-op by callers).
    """
    result = route_orthogonal_detail(
        start, end, occupancy,
        avoid_owners=avoid_owners,
        avoid_kinds=avoid_kinds,
        clearance_mm=clearance_mm,
    )
    if result.gave_up:
        import os as _os
        if _os.environ.get("ZYNQ_EDA_ROUTER_DEBUG"):
            print(f"[router] giveup {start} → {end}")
    return result.segments_as_list()


def route_orthogonal_detail(
    start: Point,
    end: Point,
    occupancy: Occupancy,
    *,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[BBoxKind] = DEFAULT_AVOID_KINDS,
    clearance_mm: float = DEFAULT_CLEARANCE_MM,
) -> "RouteAttempt":
    """Same as :func:`route_orthogonal` but exposes the picked shape.

    Useful for diagnostics — the caller can log which shape was used
    or whether the router gave up. The wire segments are otherwise
    identical to what :func:`route_orthogonal` returns.
    """
    # Trivial: same point.
    if start.x == end.x and start.y == end.y:
        return RouteAttempt(
            segments=(),
            gave_up=False,
            shape="zero_length",
        )

    # Enumerate candidates in order of preference (fewer bends first).
    # For each candidate, the FIRST one whose segments are ALL
    # collision-free wins. The candidates are:
    #
    #   K=0: direct          (only when endpoints share an axis)
    #   K=1: single-L        (2 variants: H-first, V-first)
    #   K=2: Z-bend          (mid-X / mid-Y across an offset ladder)
    #   K=4: S-bend          (5 segments through two detour points)
    #
    # The Z-bend offset ladder includes the midpoint (0) AND positive +
    # negative offsets in 2.54 mm steps out to ±25.4 mm. This lets the
    # router detour AROUND cluster passives whose bodies sit at the
    # naive midpoint X/Y. Without this, the router gives up and the
    # placement engine emits a route through the body.
    for shape, segments in _enumerate_routes(start, end):
        if not segments:
            continue
        if not _segments_collide(
            segments, occupancy, avoid_owners, avoid_kinds, clearance_mm,
        ):
            return RouteAttempt(segments=segments, gave_up=False, shape=shape)

    # No clean route exists. The placement engine MUST treat
    # ``gave_up=True`` as a hard error and either rearrange placement or
    # surface the impossibility to the user. We return the best-effort
    # single-L fallback so the net stays electrically connected (KiCad
    # ERC would otherwise see a dangling pin), but the validator will
    # flag the resulting overlap and the build will hard-fail. The
    # downstream fix lives in the placement helper that's asking for
    # an impossible route, not here.
    fallback = _single_l(start, end, horizontal_first=False)
    if not fallback:
        fallback = _single_l(start, end, horizontal_first=True)
    return RouteAttempt(segments=fallback, gave_up=True, shape="giveup")


# ---- Route enumeration -----------------------------------------------------

_DETOUR_OFFSETS_MM = (
    0.0,
    2.54, -2.54,
    5.08, -5.08,
    7.62, -7.62,
    10.16, -10.16,
    12.7, -12.7,
    15.24, -15.24,
    17.78, -17.78,
    20.32, -20.32,
    22.86, -22.86,
    25.4, -25.4,
    30.48, -30.48,
    35.56, -35.56,
    40.64, -40.64,
    45.72, -45.72,
    50.8, -50.8,
    60.96, -60.96,
    76.2, -76.2,
)


def _enumerate_routes(
    start: Point,
    end: Point,
) -> "list[tuple[str, tuple[PlacedWire, ...]]]":
    """Generate route candidates in preference order (fewest bends first).

    The returned list grows large (the Z-bend ladder is ~20 offsets × 2
    directions × 2 axes = 80 candidates), but each one is O(1) to build.
    The caller's collision check is what dominates cost — and the first
    clean candidate short-circuits the rest.
    """
    candidates: list[tuple[str, tuple[PlacedWire, ...]]] = []

    # K=0: Direct (endpoints share an axis).
    direct = _direct(start, end)
    if direct is not None:
        candidates.append(("direct", direct))

    # K=1: Single-L bend (only when endpoints differ on BOTH axes).
    if abs(start.x - end.x) > 0.01 and abs(start.y - end.y) > 0.01:
        candidates.append(("single_l_h", _single_l(start, end, horizontal_first=True)))
        candidates.append(("single_l_v", _single_l(start, end, horizontal_first=False)))

    # K=2: Z-bend through varying mid-X (H-first) and mid-Y (V-first).
    # Includes the midpoint (offset 0.0) as the first candidate.
    base_mx = (start.x + end.x) / 2.0
    base_my = (start.y + end.y) / 2.0
    for offset in _DETOUR_OFFSETS_MM:
        mx = snap_to_grid(base_mx + offset)
        c1 = Point(mx, start.y)
        c2 = Point(mx, end.y)
        segs = tuple(filter(None, (
            _make_wire(start, c1),
            _make_wire(c1, c2),
            _make_wire(c2, end),
        )))
        if segs:
            candidates.append((f"z_x_{offset:+.2f}", segs))
    for offset in _DETOUR_OFFSETS_MM:
        my = snap_to_grid(base_my + offset)
        c1 = Point(start.x, my)
        c2 = Point(end.x, my)
        segs = tuple(filter(None, (
            _make_wire(start, c1),
            _make_wire(c1, c2),
            _make_wire(c2, end),
        )))
        if segs:
            candidates.append((f"z_y_{offset:+.2f}", segs))

    # K=2 axis-aligned detour: when endpoints share an axis the
    # midpoint of the Z-bend collapses onto that axis (no detour). Try
    # offset-only detours so we can step OFF the shared axis and back
    # to it.
    if abs(start.y - end.y) < 0.01:
        for offset in _DETOUR_OFFSETS_MM:
            if abs(offset) < 0.01:
                continue
            my = snap_to_grid(start.y + offset)
            c1 = Point(start.x, my)
            c2 = Point(end.x, my)
            segs = tuple(filter(None, (
                _make_wire(start, c1),
                _make_wire(c1, c2),
                _make_wire(c2, end),
            )))
            if segs:
                candidates.append((f"detour_y_{offset:+.2f}", segs))
    if abs(start.x - end.x) < 0.01:
        for offset in _DETOUR_OFFSETS_MM:
            if abs(offset) < 0.01:
                continue
            mx = snap_to_grid(start.x + offset)
            c1 = Point(mx, start.y)
            c2 = Point(mx, end.y)
            segs = tuple(filter(None, (
                _make_wire(start, c1),
                _make_wire(c1, c2),
                _make_wire(c2, end),
            )))
            if segs:
                candidates.append((f"detour_x_{offset:+.2f}", segs))

    # K=4: S-bend (5 segments) — route goes (start) → A → B → C → D →
    # (end), where A/B/C/D form a double-detour pattern. Useful when
    # both midpoint-X and midpoint-Y are blocked: the wire can dogleg
    # twice. Generate a small number of pre-baked S-bends so the
    # search space stays bounded.
    S_BEND_OFFSETS = (5.08, 7.62, 10.16, 12.7, 15.24, 20.32)
    for off1 in S_BEND_OFFSETS:
        for dir1 in (-1, +1):
            for off2 in S_BEND_OFFSETS:
                for dir2 in (-1, +1):
                    # H-first S: (start) → (mx1, start.y) → (mx1, my) → (mx2, my) → (mx2, end.y) → (end)
                    mx1 = snap_to_grid(start.x + dir1 * off1)
                    my = snap_to_grid((start.y + end.y) / 2.0)
                    mx2 = snap_to_grid(end.x + dir2 * off2)
                    pts = [start,
                           Point(mx1, start.y),
                           Point(mx1, my),
                           Point(mx2, my),
                           Point(mx2, end.y),
                           end]
                    segs = tuple(filter(None, (
                        _make_wire(pts[i], pts[i + 1]) for i in range(len(pts) - 1)
                    )))
                    if segs:
                        candidates.append(
                            (f"s_h_{dir1}{off1:.1f}_{dir2}{off2:.1f}", segs)
                        )
                    # V-first S
                    my1 = snap_to_grid(start.y + dir1 * off1)
                    mx = snap_to_grid((start.x + end.x) / 2.0)
                    my2 = snap_to_grid(end.y + dir2 * off2)
                    pts = [start,
                           Point(start.x, my1),
                           Point(mx, my1),
                           Point(mx, my2),
                           Point(end.x, my2),
                           end]
                    segs = tuple(filter(None, (
                        _make_wire(pts[i], pts[i + 1]) for i in range(len(pts) - 1)
                    )))
                    if segs:
                        candidates.append(
                            (f"s_v_{dir1}{off1:.1f}_{dir2}{off2:.1f}", segs)
                        )

    return candidates


@dataclass(frozen=True)
class RouteAttempt:
    """Detailed result of a routing attempt.

    Returned by :func:`route_orthogonal_detail` (the public alternative
    to :func:`route_orthogonal` that exposes which shape the router
    chose). For callers that only want the wires,
    :func:`route_orthogonal` returns the segments directly.
    """

    segments: tuple[PlacedWire, ...]
    gave_up: bool
    shape: str

    def segments_as_list(self) -> list[PlacedWire]:
        return list(self.segments)
