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
)
from zynq_eda.core.layout.geometry import page_side_from_pin
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
        # Emit a local label at the far terminal so KiCad's same-name
        # net merging binds the resistor's far pin to the destination
        # net. For differential-partner cases (``suppress_label=True``,
        # e.g. LVDS pair termination whose to_net is the OTHER
        # connector pin's mapped net), the label still emits — but
        # the validator exempts the resulting label/hlabel-at-same-Y
        # pattern via the ``differential_pair_label`` exemption in
        # ``validate/overlap.py``, because shifting the label off the
        # pin row just lands on the next adjacent pin's row (LVDS pins
        # are 2.54 mm apart).
        existing_hier_names = {h.net_name for h in builder.hierarchical_labels}
        if destination_net not in existing_hier_names:
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
    if is_ground:
        builder.add_wire(PlacedWire(start=far_point, end=symbol_position))
    else:
        builder.add_wire(PlacedWire(start=symbol_position, end=far_point))

    builder.add_symbol(PlacedSymbol(
        lib_id=power_lib_id,
        reference=builder.next_ref("#PWR"),
        value=destination_net,
        position=symbol_position,
        footprint="",
        rotation=0.0,
    ), geometry=geometry_cache)


def place_one_passive_for_pin(
    builder: BlockLayoutBuilder,
    *,
    external: ExternalPart,
    resolved_destination: str,
    ic_pin_geometry,
    slot_index: int,
    ic_reference: str,
    horizontal_swarm_pitch_mm: float = HORIZONTAL_SWARM_PITCH_MM,
    geometry_cache=None,
    suppress_far_label: bool = False,
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
        primary_offset = (
            PASSIVE_OFFSET_MM
            + slot_index * horizontal_swarm_pitch_mm
            + pin_stagger
        )
        passive_anchor = Point(
            snap_to_grid(pin_connection.x - primary_offset),
            pin_connection.y,
        )
        passive_rotation = 270.0
        near_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "right":
        primary_offset = (
            PASSIVE_OFFSET_MM
            + slot_index * horizontal_swarm_pitch_mm
            + pin_stagger
        )
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + primary_offset),
            pin_connection.y,
        )
        passive_rotation = 90.0
        near_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "top":
        # Slot 0 sits directly above the IC pin. Slot N (N≥1) fans
        # LATERALLY but at HORIZONTAL_SWARM_PITCH_MM (15.24 mm = 6 grid
        # units), NOT PASSIVE_PITCH_MM (5.08 mm = 2 grid units). The
        # narrower 5.08 mm pitch matches exactly 2× the KiCad symbol
        # pin pitch — so slot 1 of pin A landed on top of slot 0 of pin
        # A+2 (e.g. CP2102N VREGIN slot-1 collided with VDD slot-0,
        # both at (132.08, 21.59)). 15.24 mm pushes slot 1 past the
        # next 5 pin positions, eliminating the collision regardless
        # of which adjacent pins also have clusters.
        lateral_offset = slot_index * horizontal_swarm_pitch_mm
        primary_offset = PASSIVE_OFFSET_MM + pin_stagger
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y - primary_offset),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
    else:  # bottom
        # Mirror of the top branch — see comment above for why we use
        # HORIZONTAL_SWARM_PITCH_MM instead of PASSIVE_PITCH_MM.
        lateral_offset = slot_index * horizontal_swarm_pitch_mm
        primary_offset = PASSIVE_OFFSET_MM + pin_stagger
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y + primary_offset),
        )
        passive_rotation = 180.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))

    ref_prefix = passive_ref_prefix(external.part_token)
    passive_ref = builder.next_ref(ref_prefix)
    builder.add_symbol(PlacedSymbol(
        lib_id=passive_lib_id(external.part_token),
        reference=passive_ref,
        value=passive_value(external.part_token),
        position=passive_anchor,
        footprint=passive_footprint(external.part_token),
        rotation=passive_rotation,
    ), geometry=geometry_cache)

    # For non-zero-swarm-slot top/bottom passives, the near pin is not on
    # the IC pin's column — route via the occupancy-aware router so the
    # L-bend avoids crossing intermediate cap bodies that sit in a row
    # at the same Y as the lateral segment.
    if pin_connection != near_point:
        if pin_connection.x == near_point.x or pin_connection.y == near_point.y:
            # Direct H or V — still go through the router so it can
            # detour if the path is blocked by another body.
            from zynq_eda.core.route.router import route_orthogonal
            segments = route_orthogonal(
                pin_connection,
                near_point,
                builder.occupancy,
                avoid_owners=frozenset({f"symbol:{ic_reference}", f"symbol:{passive_ref}"}),
            )
            for seg in segments:
                builder.add_wire(seg)
        else:
            # Diagonal — route via router (will try direct, single-L,
            # double-L variants in order).
            from zynq_eda.core.route.router import route_orthogonal
            segments = route_orthogonal(
                pin_connection,
                near_point,
                builder.occupancy,
                avoid_owners=frozenset({f"symbol:{ic_reference}", f"symbol:{passive_ref}"}),
            )
            for seg in segments:
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

        for slot_index, external in enumerate(externals):
            resolved_destination = resolve_destination_net(
                raw_destination=external.to_net,
                ic=ic,
                overrides_for_pin=overrides_for_pin,
            )
            # If the resolved destination is a net that another connector
            # pin on THIS same instance also routes to (e.g. the LVDS
            # termination going to ZYNQ_LCD_LVDS_DA0_N when connector
            # pin 10 already maps that same net), suppress the cluster's
            # far-terminal label. KiCad's hier-label-by-name merge binds
            # the nets electrically; the redundant label otherwise lands
            # at the wrong Y (the from_pin's Y, not the destination
            # pin's Y) and visually collides with the connector's own
            # hier label for the differential partner.
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
                horizontal_swarm_pitch_mm=horizontal_pitch_mm,
                geometry_cache=geometry_cache,
                suppress_far_label=destination_via_connector_pin,
            )
    return pin_geom_map
