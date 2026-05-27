"""Per-IC passive clustering: derive each external part's anchor + wires.

Given an IC's :class:`ReferenceCircuit` and the IC's already-placed anchor,
this module:

  1. Classifies each ``ExternalPart`` (cap / res / diode / other).
  2. Picks the appropriate ``Device:R`` / ``Device:C`` / ``Device:D_Schottky``
     symbol + footprint.
  3. Places the passive at the right offset + rotation so its near pin
     lands on the IC-pin axis.
  4. Wires the passive's near terminal to the IC pin and the far terminal
     to the destination net (power symbol or local label).

The placement transform handles all four sides of the IC body (left/right/
top/bottom) and the four KiCad-canonical rotations (0/90/180/270) per the
empirically-verified "Y-flip then rotate CW" rule documented in
:mod:`zynq_eda.core.layout.geometry`.
"""

from __future__ import annotations

from typing import Literal

from zynq_eda.core.layout._builder import BlockLayoutBuilder
from zynq_eda.core.layout._constants import (
    DENSE_HORIZONTAL_SWARM_PITCH_MM,
    HORIZONTAL_SWARM_PITCH_MM,
    PASSIVE_ADJACENT_PIN_STAGGER_MM,
    PASSIVE_OFFSET_MM,
    PASSIVE_PIN_HALF,
    PASSIVE_PITCH_MM,
    POWER_SYMBOL_LIB_IDS,
    POWER_SYMBOL_OFFSET_MM,
    VISUAL_CLEARANCE_MM,
)
from zynq_eda.core.layout.geometry import page_side_from_pin
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.block import IcInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.refcircuit import ExternalPart
from zynq_eda.core.model.sheet import PlacedSymbol, PlacedWire, PlacedLabel


PassiveKind = Literal["cap", "res", "diode", "other"]


def passive_kind(part_token: str) -> PassiveKind:
    """Classify a registry part token as ``cap`` / ``res`` / ``diode`` / ``other``."""
    lowered = part_token.lower()
    if "schottky" in lowered or lowered.startswith("ss"):
        return "diode"
    cap_markers = (
        "n_0402", "n_0603", "u_0402", "u_0603", "u_1206", "p_0402",
        "_x7r", "_x5r", "_c0g",
    )
    if any(marker in lowered for marker in cap_markers):
        return "cap"
    res_markers = ("k_0402", "k_0603", "r_0402", "r_0603", "_1%")
    if any(marker in lowered for marker in res_markers):
        return "res"
    return "other"


def passive_lib_id(part_token: str) -> str:
    """Return the KiCad ``lib_id`` for a passive given its part token."""
    kind = passive_kind(part_token)
    return {
        "cap":   "Device:C",
        "res":   "Device:R",
        "diode": "Device:D_Schottky",
        "other": "Device:R",
    }[kind]


def passive_value(part_token: str) -> str:
    """Extract the symbol's ``Value`` field text from a part token.

    Prefers the canonical ``BOMPart.value`` from the parts registry when
    the token is registered (e.g. ``R_SENSE_10mR_2010_1%`` -> ``0R01``
    rather than the heuristic-derived ``R``). Falls back to a
    split-on-underscore heuristic for tokens that aren't in the registry
    yet — useful during incremental authoring.

    Examples:
        "100n_0402_X7R"          -> "100n"
        "10k_0402_1%"            -> "10k"
        "R_SENSE_10mR_2010_1%"   -> "0R01"  (via registry)
        "schottky_SS14"          -> "SS14"
    """
    try:
        from zynq_eda.catalog.registry.parts_registry import get_part
        return get_part(part_token).value
    except (KeyError, ImportError):
        pass
    parts = part_token.split("_")
    if not parts:
        return part_token
    if parts[0].lower() == "schottky":
        return parts[-1] if len(parts) > 1 else parts[0]
    return parts[0]


def passive_footprint(part_token: str) -> str:
    """Best-effort KiCad footprint for the part token.

    Prefers the registry's ``BOMPart.footprint`` so wide-package shunts
    (e.g. ``R_SENSE_10mR_2010_1%`` -> 2010 / 5025Metric) and other
    non-default packages emit correct footprints. Falls back to a
    per-passive-kind default for tokens missing from the registry.
    """
    try:
        from zynq_eda.catalog.registry.parts_registry import get_part
        return get_part(part_token).footprint
    except (KeyError, ImportError):
        pass
    kind = passive_kind(part_token)
    if kind == "cap":
        return "Capacitor_SMD:C_0402_1005Metric"
    if kind == "diode":
        return "Diode_SMD:D_SMA"
    return "Resistor_SMD:R_0402_1005Metric"


def passive_ref_prefix(part_token: str) -> str:
    """Return the designator prefix (``C`` / ``R`` / ``D``) for a part token."""
    kind = passive_kind(part_token)
    return {"cap": "C", "res": "R", "diode": "D", "other": "R"}[kind]


def pin_side(
    pin_relative: Point,
    *,
    pin_rotation: float | None = None,
    symbol_rotation: float = 0.0,
) -> Literal["left", "right", "top", "bottom"]:
    """Determine which side of the IC body a pin emerges from on the *page*.

    The correct way to determine a pin's edge is from its KiCad pin
    ``rotation`` (the body-direction relative to the tip), combined with
    the placed symbol's own rotation and the symbol-to-page Y-flip. See
    :func:`zynq_eda.core.layout.geometry.page_side_from_pin` for the
    derivation.

    A historical fallback heuristic — comparing ``abs(pin.x)`` vs
    ``abs(pin.y)`` — mis-classifies pins on ICs whose pin columns span a
    larger y-range than the body width (e.g. FUSB302's 7 left-edge pins
    spanning ±7.62 mm). When ``pin_rotation`` is supplied (preferred), we
    use the rotation-derived result; otherwise we fall back to the legacy
    heuristic for backwards compatibility.
    """
    if pin_rotation is not None:
        return page_side_from_pin(
            pin_rotation=pin_rotation,
            symbol_rotation=symbol_rotation,
        )  # type: ignore[return-value]

    # Legacy heuristic for callers that don't yet supply pin_rotation.
    page_local_y = -pin_relative.y  # symbol +Y → page -Y
    if abs(pin_relative.x) >= abs(page_local_y):
        return "right" if pin_relative.x > 0 else "left"
    return "bottom" if page_local_y > 0 else "top"


def resolve_destination_net(
    *,
    raw_destination: str,
    ic,
    overrides_for_pin: dict[str, str],
) -> str:
    """Translate an ``ExternalPart.to_net`` into the actual schematic net.

    Special handling:
      * ``"IN"``  → ``ic.power_input_net`` when set.
      * ``"OUT"`` → ``ic.power_output_net`` when set.
      * If the raw value names a pin on the same IC, use that pin's
        override net.
      * Otherwise return the raw value (handled as a power symbol or
        local label).

    Finally, the resolved destination is passed through
    ``ic.external_part_net_remap`` so the project can rewrite catalog-level
    rail names (e.g. ``+3V3_SC`` → ``+3V3``) onto the block's actual
    rails. The remap runs LAST so it applies regardless of which branch
    above produced the destination.
    """
    if raw_destination == "IN" and getattr(ic, "power_input_net", ""):
        destination = ic.power_input_net
    elif raw_destination == "OUT" and getattr(ic, "power_output_net", ""):
        destination = ic.power_output_net
    elif raw_destination in overrides_for_pin:
        destination = overrides_for_pin[raw_destination]
    else:
        destination = raw_destination

    remap = dict(getattr(ic, "external_part_net_remap", ()) or ())
    if destination in remap:
        destination = remap[destination]
    return destination


_MAX_PASSIVE_SHIFT_STEPS = 30
"""Maximum lateral shift attempts before declaring a cluster unroutable.

Each step moves the passive one :data:`PASSIVE_PITCH_MM` (5.08 mm) further
outward along the relevant lateral axis. 30 steps = 152 mm of headroom,
covers the full half-width of an A3 landscape page so the placer can
search the entire viable region before failing.
"""


def _pin_count_on_side(
    ic_lib_id: str,
    side: Literal["left", "right", "top", "bottom"],
    geometry_cache,
    symbol_rotation: float = 0.0,
) -> int:
    """Count how many pins on the given page-side of the IC body.

    Used to size the cluster's INITIAL outboard distance: a fat IC with
    many pins on one side needs more channel space than a 4-pin SOT-23.
    Scaling the starting offset by pin count means the cluster doesn't
    crowd the IC body even when many pins need their own caps.
    """
    if geometry_cache is None:
        return 0
    try:
        from zynq_eda.core.layout.geometry import page_side_from_pin, _pin_rotation_from_symbol
        count = 0
        for pin_info in geometry_cache.all_pins(ic_lib_id, rotation=symbol_rotation):
            pin_number = str(pin_info["number"])
            pin_rot = _pin_rotation_from_symbol(ic_lib_id, pin_number)
            pin_side = page_side_from_pin(
                pin_rotation=pin_rot,
                symbol_rotation=symbol_rotation,
            )
            if pin_side == side:
                count += 1
        return count
    except Exception:
        return 0


class PassivePlacementError(Exception):
    """Raised when no collision-free slot exists for a cluster passive.

    Wraps the offending passive's intended anchor and the bboxes it
    couldn't avoid so the caller can surface a precise placement error.
    Treat this as fatal: the layout engine cannot produce an overlap-free
    schematic if a passive has nowhere clean to land, and the user must
    either move the upstream IC, drop the offending refcircuit entry, or
    expand the sheet.
    """


def _shift_passive_until_clear(
    *,
    builder: BlockLayoutBuilder,
    passive_anchor: Point,
    near_point: Point,
    far_point: Point,
    side: Literal["left", "right", "top", "bottom"],
    passive_rotation: float,
    passive_lib_id: str,
    geometry_cache,
    pin_connection: "Point | None" = None,
    avoid_owners: "frozenset[str]" = frozenset(),
) -> tuple[Point, Point, Point]:
    """Incrementally place the passive in the first slot whose BODY,
    TEXT, AND WIRE PATH are all clean.

    The previous version only checked body+property bbox collisions. With
    the project's hard rule that no two wires may cross AND no wire may
    pass through a component body, we must ALSO verify that the wire
    from ``pin_connection`` to ``candidate_near_point`` can actually be
    routed (without the router falling back to a colliding giveup) BEFORE
    accepting the slot. If the route can't be cleanly drawn from this
    candidate, we shift further out and try again — last placed
    passives may end up far from the IC, and that's correct: by then
    every closer slot has been claimed by earlier wires/passives.

    Returns ``(anchor, near, far)`` that survives every check, or raises
    :class:`PassivePlacementError` after exhausting the fanout ladder.
    """
    if geometry_cache is None:
        return passive_anchor, near_point, far_point

    from zynq_eda.core.route.router import route_orthogonal_detail

    # Outward unit for projecting the future power-symbol position when
    # probing the far → symbol route. Must match _attach_far_endpoint.
    if side == "left":
        outward_dx, outward_dy = -POWER_SYMBOL_OFFSET_MM, 0.0
    elif side == "right":
        outward_dx, outward_dy = POWER_SYMBOL_OFFSET_MM, 0.0
    elif side == "top":
        outward_dx, outward_dy = 0.0, -POWER_SYMBOL_OFFSET_MM
    else:
        outward_dx, outward_dy = 0.0, POWER_SYMBOL_OFFSET_MM

    for dx, dy in _fanout_offsets(side):
        candidate_anchor = Point(
            snap_to_grid(passive_anchor.x + dx),
            snap_to_grid(passive_anchor.y + dy),
        )
        candidate_near = Point(
            snap_to_grid(near_point.x + dx),
            snap_to_grid(near_point.y + dy),
        )
        candidate_far = Point(
            snap_to_grid(far_point.x + dx),
            snap_to_grid(far_point.y + dy),
        )
        # 1. Body + property text clearance.
        if _candidate_passive_collides(
            anchor=candidate_anchor,
            rotation=passive_rotation,
            lib_id=passive_lib_id,
            occupancy=builder.occupancy,
            geometry_cache=geometry_cache,
        ):
            continue
        # 2. Wire-route clearance: pin → cap.near route MUST be clean
        #    (no router giveup). If the router can't find a route from
        #    the source pin to this candidate's near-point without
        #    crossing anything, this slot is unusable.
        if pin_connection is not None and pin_connection != candidate_near:
            attempt = route_orthogonal_detail(
                pin_connection,
                candidate_near,
                builder.occupancy,
                avoid_owners=avoid_owners,
            )
            if attempt.gave_up:
                continue
        # 3. Power-symbol-side wire-route clearance: simulate the
        #    cap.far → future_power_symbol route. If the placement
        #    engine couldn't route it later, that slot is unusable now.
        candidate_symbol_position = Point(
            snap_to_grid(candidate_far.x + outward_dx),
            snap_to_grid(candidate_far.y + outward_dy),
        )
        if candidate_far != candidate_symbol_position:
            attempt = route_orthogonal_detail(
                candidate_far,
                candidate_symbol_position,
                builder.occupancy,
                avoid_owners=avoid_owners,
            )
            if attempt.gave_up:
                continue
        return candidate_anchor, candidate_near, candidate_far

    # Pass 5 of the overlap-free plan: NO body-only fallback. The
    # strict probe (body + property text + pin→near route + far→
    # power-symbol route) is the SOLE acceptance criterion. When it
    # rejects every candidate, hard-fail with a diagnostic. The fix
    # is upstream — widen PER_PIN_UNIT_MM (Pass 4) or move the IC
    # anchor so the cluster has more room.
    raise PassivePlacementError(
        f"No collision-free slot found for passive {passive_lib_id!r} on "
        f"side {side!r} after exhausting the fanout ladder starting from "
        f"{passive_anchor}. The strict probe rejected every candidate — "
        f"either the cap body collided with an existing primitive, or the "
        f"pin → cap.near / cap.far → power-symbol wire route was blocked. "
        f"Upstream fix: widen the cluster channel (Pass 4 stair-step "
        f"fanout) or relocate the IC anchor."
    )


def _fanout_offsets(
    side: Literal["left", "right", "top", "bottom"],
) -> "list[tuple[float, float]]":
    """Generate candidate (dx, dy) offsets for cluster-passive fanout.

    Ordered by escalating Manhattan distance — the closest viable slot
    is always preferred. For each side, candidates fan out along two
    axes:

      * **outward axis** (negative for LEFT/TOP, positive for RIGHT/BOTTOM)
        — moves the passive further from the IC body.
      * **perpendicular axis** (both ± directions) — slides the passive
        along the IC's pin row to a NEW column slot at the same outward
        distance.

    Step size is :data:`PASSIVE_PITCH_MM` (5.08 mm). We generate
    candidates out to :data:`_MAX_PASSIVE_SHIFT_STEPS` on each axis,
    interleaved so close slots are tried before distant ones.
    """
    if side == "left":
        outward_sign = -1
        outward_axis = "x"
    elif side == "right":
        outward_sign = 1
        outward_axis = "x"
    elif side == "top":
        outward_sign = -1
        outward_axis = "y"
    else:
        outward_sign = 1
        outward_axis = "y"

    pitch = PASSIVE_PITCH_MM
    candidates: list[tuple[float, float]] = [(0.0, 0.0)]
    # Iterate by Manhattan distance "rings" — at distance N, every
    # (outward_steps, perp_steps) pair where |outward| + |perp| == N
    # is a candidate. We allow outward in one direction (away from IC)
    # and perpendicular in both directions.
    for total in range(1, _MAX_PASSIVE_SHIFT_STEPS + 1):
        for outward_steps in range(total + 1):
            perp_steps = total - outward_steps
            outward_amount = outward_sign * outward_steps * pitch
            for perp_sign in (1, -1) if perp_steps > 0 else (0,):
                perp_amount = perp_sign * perp_steps * pitch
                if outward_axis == "x":
                    candidates.append((outward_amount, perp_amount))
                else:
                    candidates.append((perp_amount, outward_amount))
    return candidates


def _candidate_passive_collides(
    *,
    anchor: Point,
    rotation: float,
    lib_id: str,
    occupancy: Occupancy,
    geometry_cache,
) -> bool:
    """True iff a passive's body + property-text bboxes would overlap
    something already in occupancy.

    We probe THREE bboxes per candidate:

      1. The symbol body bbox (the visible rectangle).
      2. The Reference property text bbox (right of body, ~3 mm wide).
      3. The Value property text bbox (left of body, ~3 mm wide).

    All three must be clear or the candidate is rejected. Wires +
    junctions + no_connects are ignored — only symbols, labels, and
    intrinsic text count as obstacles.
    """
    from zynq_eda.core.layout.bbox import symbol_bbox

    ignore_kinds = frozenset({"wire", "junction", "no_connect"})
    try:
        body = symbol_bbox(
            lib_id=lib_id,
            anchor=anchor,
            rotation=rotation,
            cache=geometry_cache,
            owner_id="_passive_probe",
        )
    except Exception:
        return False  # can't probe — be permissive
    if occupancy.collides(body, ignore_kinds=ignore_kinds, padding_mm=VISUAL_CLEARANCE_MM):
        return True
    try:
        text_bboxes = geometry_cache.property_text_bboxes(
            lib_id,
            anchor,
            rotation=rotation,
            owner_id="_passive_probe",
        )
    except Exception:
        return False
    for text_box in text_bboxes:
        if occupancy.collides(text_box, ignore_kinds=ignore_kinds, padding_mm=VISUAL_CLEARANCE_MM):
            return True
    return False


def _outward_power_symbol_rotation(
    *,
    lib_id: str,
    pin_side: Literal["left", "right", "top", "bottom"],
    geometry_cache,
) -> float:
    """Pick the KiCad rotation that makes a power symbol's body extend OUTWARD.

    "Outward" means away from the cap/IC the symbol is attached to:
    for a TOP-side cap the body should point UP on the page, for a
    BOTTOM-side cap DOWN, etc. KiCad's stock power symbols come in two
    natural orientations:

      * **body-down** (e.g. ``power:GND``, ``power:Earth``) — the pin
        tip sits at the top of the symbol with the body extending
        DOWN on the page at rotation 0.
      * **body-up** (e.g. ``power:+3V3``, ``power:+5V``, ``power:+1V8``)
        — the pin tip sits at the bottom with the body extending UP
        at rotation 0.

    We detect which one we have by inspecting the symbol's bbox
    (returned by the geometry cache) — if the body's centre is below
    the anchor (positive page Y), the symbol is body-down; otherwise
    body-up. From there, the rotation that points the body outward is
    fully determined by ``pin_side``.

    Falls back to ``0.0`` when the geometry cache can't resolve the
    library symbol (the validator will then surface the resulting
    overlap; better that than a silent mis-placement).
    """
    if geometry_cache is None:
        return 0.0
    try:
        bbox = geometry_cache.bounding_box(lib_id, rotation=0.0)
    except Exception:
        return 0.0
    body_center_y = (bbox.min_y + bbox.max_y) / 2.0
    # Only rotate TOP/BOTTOM-side cases — those are where the wire goes
    # PERPENDICULAR through the body (real overlap > 1 mm). LEFT/RIGHT
    # wires only graze the body's edge by 0.127 mm (wire half-thickness)
    # at the pin tip; the validator's noise floor handles that. Rotating
    # power symbols on LEFT/RIGHT pushes the rotated body INTO the
    # adjacent passive's pin column on multi-pull-up clusters, so it
    # creates more overlaps than it prevents.
    if body_center_y > 0.0:
        # Body-down symbol (GND-style): default body extends to page +Y.
        return {
            "top":    180.0,  # +Y → -Y (body up, away from cap)
            "bottom": 0.0,    # default already correct
            "left":   0.0,    # accept the 0.127 mm graze
            "right":  0.0,    # accept the 0.127 mm graze
        }[pin_side]
    # Body-up symbol (+3V3-style): default body extends to page -Y.
    return {
        "top":    0.0,    # default already correct
        "bottom": 180.0,  # -Y → +Y (body down, away from cap)
        "left":   0.0,    # accept the 0.127 mm graze
        "right":  0.0,    # accept the 0.127 mm graze
    }[pin_side]


def _attach_far_endpoint(
    builder: BlockLayoutBuilder,
    *,
    far_point: Point,
    destination_net: str,
    passive_rotation: float,
    pin_side: str,
    geometry_cache=None,
    suppress_label: bool = False,
) -> None:
    """Connect a passive's far terminal to either a power symbol or a label.

    Power symbols are placed *outboard* of ``far_point`` (further away from
    the IC body) by :data:`POWER_SYMBOL_OFFSET_MM` and wired back to the
    passive's terminal. The outboard direction is derived from the
    passive's rotation + the IC-pin side it sits on, so dense pin packs
    (USB-C, FFC connectors) don't end up with power symbols landing on
    adjacent pins.

    For horizontal passives (rotation 90 / 270), "outboard" is purely
    lateral — extending further left or right of the IC body. For
    vertical passives (rotation 0 / 180), "outboard" is vertical.

    A net name that isn't in :data:`POWER_SYMBOL_LIB_IDS` becomes a local
    label at the terminal position.
    """
    power_lib_id = POWER_SYMBOL_LIB_IDS.get(destination_net)
    if power_lib_id is None:
        # Outward label rotation per pin_side so the text never reads
        # back across the IC body. Mirror the same rule used by the
        # connector + IC signal-override placers (left=180, right=0,
        # top=90, bottom=270).
        label_rotation = {
            "left": 180.0,
            "right": 0.0,
            "top": 90.0,
            "bottom": 270.0,
        }.get(pin_side, 0.0)
        existing_hier_names = {h.net_name for h in builder.hierarchical_labels}
        if destination_net not in existing_hier_names:
            # Pass 3: local label sits AT the cap's far_point — the
            # wire endpoint itself, no perpendicular stub. The label
            # rotation makes the text extend OUTWARD (away from the
            # IC body) along the pin axis. Adjacent caps' labels will
            # not collide because each cap's far_point is on its own
            # Y row (cluster shift enforces this).
            builder.add_label(PlacedLabel(
                net_name=destination_net,
                position=far_point,
                rotation=label_rotation,
            ))
        return

    # Outboard direction: continue from passive_anchor through far_point,
    # by another POWER_SYMBOL_OFFSET_MM.
    if pin_side == "left":
        symbol_position = Point(
            snap_to_grid(far_point.x - POWER_SYMBOL_OFFSET_MM),
            far_point.y,
        )
    elif pin_side == "right":
        symbol_position = Point(
            snap_to_grid(far_point.x + POWER_SYMBOL_OFFSET_MM),
            far_point.y,
        )
    elif pin_side == "top":
        symbol_position = Point(
            far_point.x,
            snap_to_grid(far_point.y - POWER_SYMBOL_OFFSET_MM),
        )
    else:  # bottom
        symbol_position = Point(
            far_point.x,
            snap_to_grid(far_point.y + POWER_SYMBOL_OFFSET_MM),
        )

    is_ground = "GND" in destination_net.upper() or destination_net.upper() == "CHASSIS_GND"
    # Route cap.far → power-symbol via the router (detail mode so we
    # can surface the failure cleanly). On giveup, raise — the
    # placement engine's strict probe should have already accepted
    # only positions where this route is clean.
    from zynq_eda.core.route.router import route_orthogonal_detail
    src, dst = (far_point, symbol_position) if is_ground else (symbol_position, far_point)
    far_to_power = route_orthogonal_detail(
        src, dst, builder.occupancy,
    )
    if far_to_power.gave_up:
        raise PassivePlacementError(
            f"_attach_far_endpoint: router gave up routing cap.far "
            f"{far_point} → power symbol {symbol_position} for net "
            f"{destination_net!r}. The strict probe should have "
            f"caught this — placement bug."
        )
    for seg in far_to_power.segments:
        builder.add_wire(seg)

    # Rotate the power symbol so its visible body extends AWAY from the
    # connecting wire (and from the cap). Without this, GND symbols
    # attached to top-side caps have their body pointing DOWN (the
    # default GND orientation) into the wire path, producing
    # wire×symbol overlaps every time. The library-default body
    # direction is detected by querying the symbol's bbox at rotation
    # 0 — symbols whose body sits at page-+Y (below anchor) like GND
    # rotate one way, symbols at page-−Y (above anchor) like +3V3
    # rotate the other.
    power_symbol_rotation = _outward_power_symbol_rotation(
        lib_id=power_lib_id,
        pin_side=pin_side,
        geometry_cache=geometry_cache,
    )

    builder.add_symbol(PlacedSymbol(
        lib_id=power_lib_id,
        reference=builder.next_ref("#PWR"),
        value=destination_net,
        position=symbol_position,
        footprint="",
        rotation=power_symbol_rotation,
    ), geometry=geometry_cache)


def place_one_passive_for_pin(
    builder: BlockLayoutBuilder,
    *,
    external: ExternalPart,
    resolved_destination: str,
    ic_pin_geometry,
    slot_index: int,
    ic_reference: str,
    source_pin_number: str = "",
    horizontal_swarm_pitch_mm: float = HORIZONTAL_SWARM_PITCH_MM,
    geometry_cache=None,
    suppress_far_label: bool = False,
    ic_lib_id: str = "",
    side_pin_count: int = 1,
    pin_side_index: int = 0,
) -> None:
    """Place a single passive next to an IC pin and wire it up.

    Args:
        builder: The block-layout accumulator.
        external: The :class:`ExternalPart` to materialise.
        resolved_destination: Net the passive's far terminal connects to,
            already mapped through :func:`resolve_destination_net`.
        ic_pin_geometry: The :class:`PinGeometry` of the IC pin this passive
            attaches to (returned by ``SymbolGeometryCache.pin_geometry_by_name``).
        slot_index: 0-based index of this passive within the per-pin swarm.
            Used to derive the slot's geometric offset; the offset scale
            depends on which body side the IC pin sits on (LEFT/RIGHT use
            ``horizontal_swarm_pitch_mm``; TOP/BOTTOM use
            :data:`PASSIVE_PITCH_MM`).
        ic_reference: The IC's reference designator (currently unused; kept
            for future per-IC accounting).
        horizontal_swarm_pitch_mm: Slot pitch (mm) along the LEFT/RIGHT
            fan-out axis. Defaults to :data:`HORIZONTAL_SWARM_PITCH_MM`;
            callers pass :data:`DENSE_HORIZONTAL_SWARM_PITCH_MM` for
            refcircuits that opt into a wider pitch via
            ``ReferenceCircuit.dense_swarm``.
    """
    side = pin_side(
        ic_pin_geometry.relative,
        pin_rotation=getattr(ic_pin_geometry, "pin_rotation", 0.0),
        symbol_rotation=getattr(ic_pin_geometry, "symbol_rotation", 0.0),
    )
    pin_connection = ic_pin_geometry.connection

    # Adjacent-pin stagger: when two IC pins on the same body side are at
    # KiCad's 2.54 mm pin pitch (the common case for VCC pairs, VBUS+VDD,
    # etc.), each gets a cluster cap. Without intervention, both caps'
    # anchors share the same column (LEFT/RIGHT) or row (TOP/BOTTOM), and
    # the cap bodies + their Value/Reference text overlap at 2.54 mm
    # spacing. Staggering odd-parity pins by an extra
    # PASSIVE_ADJACENT_PIN_STAGGER_MM perpendicular to the body edge
    # places the two caps in two distinct columns/rows, restoring
    # readability while preserving the existing slot-fanning behaviour
    # for multi-cap-per-pin clusters.
    #
    # Parity is derived from the IC pin's absolute coordinate divided by
    # the KiCad pin pitch (2.54 mm). LEFT/RIGHT pins parity-stagger on Y;
    # TOP/BOTTOM pins parity-stagger on X. The result is a checker-board
    # pattern of cap positions that visually decongests dense pin packs.
    #
    # Use ``int(coord/2.54 + 0.5)`` (round-half-up) instead of
    # ``round()`` — Python's ``round`` uses banker's rounding which maps
    # half-pitch-offset pins like Y=46.99 (=18.5*2.54) and Y=49.53
    # (=19.5*2.54) to the same parity (both round to even), defeating
    # the stagger. The ``+0.5`` shift before truncation breaks the tie
    # consistently so adjacent half-pitch-offset rows land on opposite
    # parities.
    KICAD_PIN_PITCH = 2.54
    if side in ("left", "right"):
        parity = int(pin_connection.y / KICAD_PIN_PITCH + 0.5) & 1
    else:
        parity = int(pin_connection.x / KICAD_PIN_PITCH + 0.5) & 1
    pin_stagger = parity * PASSIVE_ADJACENT_PIN_STAGGER_MM

    # Pass 4 — stair-step fanout. Each pin gets its OWN outboard column
    # so caps for adjacent pins live in distinct lanes. Wires from each
    # pin to its cap (and from cap.far to power-symbol) then don't
    # share an X column with another pin's cap body, which is what was
    # causing wire×cap-body crossings before. The PER_PIN_UNIT_MM
    # (10.16 mm = 4 KiCad grid) is sized so adjacent pins' bodies have
    # the 2 mm visual clearance AND the wire from a further-out pin
    # can detour over/under the previous pin's body via the router's
    # Z-bend ladder.
    PER_PIN_UNIT_MM = 10.16
    pin_fanout_scale = pin_side_index * PER_PIN_UNIT_MM

    # Choose passive_anchor + rotation per side so the NEAR pin (toward the
    # IC) lands one PASSIVE_PIN_HALF from passive_anchor in the right
    # direction. Empirically, under KiCad's "flip-Y then rotate CW" placement
    # transform applied to Device:R / Device:C (pin 1 at (0, +3.81), pin 2
    # at (0, -3.81)):
    #
    #     rotation  0 : pin 1 → (0, -3.81), pin 2 → (0, +3.81)
    #     rotation 90 : pin 1 → (-3.81, 0), pin 2 → (+3.81, 0)
    #     rotation 180: pin 1 → (0, +3.81), pin 2 → (0, -3.81)
    #     rotation 270: pin 1 → (+3.81, 0), pin 2 → (-3.81, 0)
    #
    # Slot stacking pitch depends on the side: LEFT/RIGHT slots fan outward
    # along the perpendicular-to-edge axis (each slot is one passive-body +
    # one power-symbol-stub further out), so the pitch must clear
    # 2*PASSIVE_PIN_HALF + POWER_SYMBOL_OFFSET. TOP/BOTTOM slots fan
    # laterally along their own column (each slot has its own X column);
    # the lateral pitch only needs to keep adjacent caps visually separated.
    if side == "left":
        # Vertical passive (rotation 0): body + property text live
        # BELOW the rail Y, off the wire path. The pin_stagger for
        # adjacent IC pins shifts cap X (perpendicular to body's
        # long axis) so two caps at neighbouring pins don't end up
        # in the same column. Pin-count scale moves the WHOLE cluster
        # further outboard for fat ICs so every pin gets its own lane.
        lateral_offset = (
            PASSIVE_OFFSET_MM
            + pin_fanout_scale
            + slot_index * horizontal_swarm_pitch_mm
        )
        passive_anchor = Point(
            snap_to_grid(pin_connection.x - lateral_offset - pin_stagger),
            snap_to_grid(pin_connection.y + PASSIVE_PIN_HALF),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
    elif side == "right":
        lateral_offset = (
            PASSIVE_OFFSET_MM
            + pin_fanout_scale
            + slot_index * horizontal_swarm_pitch_mm
        )
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset + pin_stagger),
            snap_to_grid(pin_connection.y + PASSIVE_PIN_HALF),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
    elif side == "top":
        # TOP slots fan LATERALLY in X. Pin-count scale pushes the
        # cluster's primary offset higher so the channel above the IC
        # is sized to the pin density.
        lateral_offset = slot_index * horizontal_swarm_pitch_mm
        primary_offset = PASSIVE_OFFSET_MM + pin_fanout_scale + pin_stagger
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y - primary_offset),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
    else:  # bottom
        lateral_offset = slot_index * horizontal_swarm_pitch_mm
        primary_offset = PASSIVE_OFFSET_MM + pin_fanout_scale + pin_stagger
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y + primary_offset),
        )
        passive_rotation = 180.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))

    # Cross-cluster collision check + wire-routability probe: each
    # candidate slot is rejected unless (a) its body+text bbox is clear
    # of every primitive already in occupancy AND (b) the wire from the
    # source IC/connector pin to the candidate near-point can be routed
    # without the router giving up. Last items placed may end up far
    # from the source pin — that's correct: by then every closer slot
    # has been claimed.
    from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids as _pin_owners
    _probe_avoid_owners = {f"symbol:{ic_reference}"}
    if source_pin_number:
        _probe_avoid_owners |= set(
            _pin_owners(ic_reference, (source_pin_number,))
        )
    passive_lib = passive_lib_id(external.part_token)
    passive_anchor, near_point, far_point = _shift_passive_until_clear(
        builder=builder,
        passive_anchor=passive_anchor,
        near_point=near_point,
        far_point=far_point,
        side=side,
        passive_rotation=passive_rotation,
        passive_lib_id=passive_lib,
        geometry_cache=geometry_cache,
        pin_connection=pin_connection,
        avoid_owners=frozenset(_probe_avoid_owners),
    )

    ref_prefix = passive_ref_prefix(external.part_token)
    passive_ref = builder.next_ref(ref_prefix)

    # Dynamic Value-text placement: probe a ladder of offsets around
    # the body and pick the first slot whose bbox doesn't collide
    # with anything already in occupancy. Without this, the Value
    # text lands at the library default (often AT the body centre
    # for Device:R, just above the body for Device:C) — visually
    # readable in isolation but covering the body or running into
    # neighbouring wires when caps stack tightly.
    from zynq_eda.core.layout.geometry import pick_dynamic_value_shift
    value_shift = pick_dynamic_value_shift(
        lib_id=passive_lib,
        anchor=passive_anchor,
        symbol_rotation=passive_rotation,
        occupancy=builder.occupancy,
        geometry_cache=geometry_cache,
        owner_id=f"symbol:{passive_ref}",
        value_text=passive_value(external.part_token),
    )

    builder.add_symbol(PlacedSymbol(
        lib_id=passive_lib,
        reference=passive_ref,
        value=passive_value(external.part_token),
        position=passive_anchor,
        footprint=passive_footprint(external.part_token),
        rotation=passive_rotation,
        value_shift=value_shift,
    ), geometry=geometry_cache)

    # For non-zero-swarm-slot top/bottom passives, the near pin is not on
    # the IC pin's column — route via the occupancy-aware router so the
    # L-bend avoids crossing intermediate cap bodies that sit in a row
    # at the same Y as the lateral segment.
    #
    # avoid_owners exempts (1) the IC's body bbox, (2) the passive's
    # body bbox, AND (3) the SOURCE pin's own intrinsic pin-name +
    # pin-number text bboxes. Without (3), the wire bbox's endpoint
    # clearance grazes the source pin's name text (which sits ~1 mm
    # INTO the body from the tip) and EVERY L-bend variant would
    # falsely block. OTHER pins' intrinsic text on the same IC is NOT
    # exempted, so the router picks the L-bend that doesn't cross them
    # (e.g. V-first for top-edge slot ≥ 1 so the horizontal lateral
    # sits below pin row Y, not at it).
    if pin_connection != near_point:
        from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
        avoid_owners_set = {
            f"symbol:{ic_reference}",
            f"symbol:{passive_ref}",
        }
        if source_pin_number:
            avoid_owners_set |= set(
                pin_intrinsic_owner_ids(ic_reference, (source_pin_number,))
            )
        avoid_owners = frozenset(avoid_owners_set)

        # Use route_orthogonal_detail so we don't crash on giveup — the
        # strict probe in _shift_passive_until_clear is supposed to have
        # found a routable slot, but its check happens BEFORE the cap
        # body is added to occupancy. If the actual route now collides
        # (e.g. a same-pin slot 1 cap is in the way), surface a clear
        # PassivePlacementError instead of UnroutableError so the user
        # sees the upstream cause. Pass 5 will tighten this further.
        from zynq_eda.core.route.router import route_orthogonal_detail
        attempt = route_orthogonal_detail(
            pin_connection,
            near_point,
            builder.occupancy,
            avoid_owners=avoid_owners,
        )
        if attempt.gave_up:
            raise PassivePlacementError(
                f"Router gave up routing IC pin {pin_connection} → "
                f"cap near-pin {near_point} (passive {passive_ref!r}, "
                f"lib_id {passive_lib!r}). The cap's accepted slot has "
                f"no clean wire route to the source pin."
            )
        for seg in attempt.segments:
            builder.add_wire(seg)

    _attach_far_endpoint(
        builder,
        far_point=far_point,
        destination_net=resolved_destination,
        passive_rotation=passive_rotation,
        pin_side=side,
        geometry_cache=geometry_cache,
        suppress_label=suppress_far_label,
    )


def cluster_ic_externals(
    builder: BlockLayoutBuilder,
    *,
    ic,
    pin_geom_resolver,
    geometry_cache=None,
) -> dict[str, "PinGeometryAbs"]:
    """Materialise every ``ExternalPart`` on ``ic.refcircuit``.

    Works for any object exposing ``refcircuit`` + ``lib_id`` plus optional
    ``power_input_net``, ``power_output_net``, ``net_overrides`` and a
    ``pin_to_net`` override. Both :class:`IcInstance` and
    :class:`ConnectorInstance` satisfy this duck-typed contract.

    ``pin_geom_resolver`` is a callable ``(pin_name) -> PinGeometry`` (the
    block-layout orchestrator binds it to a particular instance anchor +
    lib_id). Returns the per-pin geometry map for later inter-IC wiring.
    """
    by_pin: dict[str, list[ExternalPart]] = {}
    for external in ic.refcircuit.external_parts:
        by_pin.setdefault(external.from_pin, []).append(external)

    overrides_for_pin: dict[str, str] = dict(ic.refcircuit.pin_net_overrides)
    overrides_for_pin |= dict(getattr(ic, "net_overrides", ()) or ())
    # Connector pin_to_net is also an alias for "this pin is on net X" —
    # let it override pin_net_overrides too so passive clusters route to the
    # correct destination.
    pin_to_net = tuple(getattr(ic, "pin_to_net", ()) or ())
    overrides_for_pin |= dict(pin_to_net)
    # pin_to_net keys are PIN NUMBERS (e.g. "10"), but refcircuit external
    # parts often reference the destination by PIN NAME (e.g. "LVDS_DATA0-").
    # Map each pin number's net to that pin's NAME too so the cluster
    # resolver finds it whether the refcircuit referenced by number or name.
    # Without this, an LVDS 100Ω termination with to_net="LVDS_DATA0-" emits
    # a stray local label of that name instead of routing onto the carrier's
    # ZYNQ_LCD_LVDS_DA0_N net.
    if pin_to_net and geometry_cache is not None and getattr(ic, "lib_id", None):
        try:
            symbol_rotation = float(getattr(ic, "rotation", 0.0))
            number_to_name = {}
            for pin_info in geometry_cache.all_pins(ic.lib_id, rotation=symbol_rotation):
                number_to_name[str(pin_info["number"])] = str(pin_info["name"])
            for pin_number, net in pin_to_net:
                pin_name = number_to_name.get(str(pin_number))
                if pin_name and pin_name not in overrides_for_pin:
                    overrides_for_pin[pin_name] = net
        except Exception:
            # geometry cache may not have this symbol registered; skip
            # the name aliasing and rely on the numeric mapping.
            pass

    if getattr(ic, "power_input_net", ""):
        overrides_for_pin.setdefault("IN", ic.power_input_net)
    if getattr(ic, "power_output_net", ""):
        overrides_for_pin.setdefault("OUT", ic.power_output_net)

    # Pick LEFT/RIGHT slot pitch from refcircuit.dense_swarm. Most
    # refcircuits use the default 15.24 mm (which aligns with the
    # connector hier-pin row pitch on the root sheet). Dense networks
    # (HX5008 Bob-Smith) opt into 20.32 mm via ``dense_swarm = True``
    # to give the per-slot value labels enough room to read.
    horizontal_pitch_mm = (
        DENSE_HORIZONTAL_SWARM_PITCH_MM
        if getattr(ic.refcircuit, "dense_swarm", False)
        else HORIZONTAL_SWARM_PITCH_MM
    )

    # Pre-compute a pin NAME → pin NUMBER map so the cluster can pass
    # the source pin's number to ``place_one_passive_for_pin`` for the
    # intrinsic-text exemption. Falls back to empty if the geometry
    # cache can't resolve the symbol (e.g. unregistered library).
    name_to_number: dict[str, str] = {}
    if geometry_cache is not None and getattr(ic, "lib_id", None):
        try:
            symbol_rotation_for_lookup = float(getattr(ic, "rotation", 0.0))
            for pin_info in geometry_cache.all_pins(
                ic.lib_id, rotation=symbol_rotation_for_lookup,
            ):
                name_to_number[str(pin_info["name"])] = str(pin_info["number"])
        except Exception:
            pass

    # Build PER-SIDE ordered lists of pins WITH external_parts. Each
    # such pin gets a unique outboard COLUMN — so cap-of-pin-0 sits at
    # X = pin.x ± PASSIVE_OFFSET, cap-of-pin-1 at one swarm_pitch
    # further out, and so on. This guarantees every cap occupies its
    # own lane on the page; the wires from pins to their caps then
    # NEVER share an X (or Y for TOP/BOTTOM) column.
    ic_lib_id = getattr(ic, "lib_id", "")
    ic_symbol_rotation = float(getattr(ic, "rotation", 0.0))

    # Map each pin name to its (side, index_within_side). Side index
    # increments only for pins that have external_parts so caps fan
    # out tightly without wasting columns on no-cap pins.
    pins_with_caps_by_side: dict[str, list[str]] = {"left": [], "right": [], "top": [], "bottom": []}
    # Sort by pin Y (for L/R) or X (for T/B) so the fanout direction
    # is deterministic — pin closest to the top of a left-side row
    # gets column 0, next pin gets column 1, etc.
    pins_with_geom: list[tuple[str, "Point | None", str]] = []
    for pin_name in by_pin.keys():
        try:
            pg = pin_geom_resolver(pin_name)
        except Exception:
            pg = None
        if pg is None:
            continue
        side_str = pin_side(
            pg.relative,
            pin_rotation=getattr(pg, "pin_rotation", 0.0),
            symbol_rotation=getattr(pg, "symbol_rotation", 0.0),
        )
        pins_with_geom.append((pin_name, pg.connection, side_str))
    # Sort each side's pins by their position along the body edge.
    for side_str in ("left", "right", "top", "bottom"):
        pins_on_side = [(n, c) for (n, c, s) in pins_with_geom if s == side_str]
        if side_str in ("left", "right"):
            pins_on_side.sort(key=lambda nc: nc[1].y if nc[1] is not None else 0)
        else:
            pins_on_side.sort(key=lambda nc: nc[1].x if nc[1] is not None else 0)
        pins_with_caps_by_side[side_str] = [n for (n, _) in pins_on_side]

    pin_side_index_map: dict[str, int] = {}
    for side_str, pin_list in pins_with_caps_by_side.items():
        for idx, pin_name in enumerate(pin_list):
            pin_side_index_map[pin_name] = idx

    side_pin_counts: dict[str, int] = {
        side_str: len(pin_list)
        for side_str, pin_list in pins_with_caps_by_side.items()
    }

    pin_geom_map: dict[str, "PinGeometryAbs"] = {}
    placed_passive_pin_names: set[str] = set()
    for pin_name, externals in by_pin.items():
        pin_geom = pin_geom_resolver(pin_name)
        if pin_geom is None:
            # The refcircuit references a pin not present on the symbol
            # (e.g. NR_SS where KiCad labels the pin NC). Skip — the
            # canonical validator will surface this mismatch later.
            continue
        from zynq_eda.core.layout._builder import PinGeometryAbs
        pin_geom_map[pin_name] = PinGeometryAbs(
            anchor=pin_geom.anchor,
            connection=pin_geom.connection,
            relative=pin_geom.relative,
            pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
            symbol_rotation=getattr(pin_geom, "symbol_rotation", 0.0),
        )
        placed_passive_pin_names.add(pin_name)

        source_pin_number = name_to_number.get(pin_name, "")

        # Determine this pin's page side so the smart pin-count scale
        # uses the right side's count.
        this_pin_side = pin_side(
            pin_geom.relative,
            pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
            symbol_rotation=getattr(pin_geom, "symbol_rotation", 0.0),
        )
        side_count = side_pin_counts.get(this_pin_side, 1)

        for slot_index, external in enumerate(externals):
            resolved_destination = resolve_destination_net(
                raw_destination=external.to_net,
                ic=ic,
                overrides_for_pin=overrides_for_pin,
            )
            destination_via_connector_pin = resolved_destination in {
                net for _pin, net in pin_to_net
            } and resolved_destination != external.to_net
            place_one_passive_for_pin(
                builder,
                external=external,
                resolved_destination=resolved_destination,
                ic_pin_geometry=pin_geom,
                slot_index=slot_index,
                ic_reference=ic.reference,
                source_pin_number=source_pin_number,
                horizontal_swarm_pitch_mm=horizontal_pitch_mm,
                geometry_cache=geometry_cache,
                suppress_far_label=destination_via_connector_pin,
                ic_lib_id=ic_lib_id,
                side_pin_count=side_count,
                pin_side_index=pin_side_index_map.get(pin_name, 0),
            )
    return pin_geom_map
