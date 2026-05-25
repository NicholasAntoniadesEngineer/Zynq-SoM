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
    HORIZONTAL_SWARM_PITCH_MM,
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

    Examples:
        "100n_0402_X7R" → "100n"
        "10k_0402_1%"   → "10k"
        "schottky_SS14" → "SS14"
    """
    parts = part_token.split("_")
    if not parts:
        return part_token
    if parts[0].lower() == "schottky":
        return parts[-1] if len(parts) > 1 else parts[0]
    return parts[0]


def passive_footprint(part_token: str) -> str:
    """Best-effort KiCad footprint for the part token."""
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
        builder.labels.append(PlacedLabel(
            net_name=destination_net,
            position=far_point,
            rotation=0.0,
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
        builder.wires.append(PlacedWire(start=far_point, end=symbol_position))
    else:
        builder.wires.append(PlacedWire(start=symbol_position, end=far_point))

    builder.symbols.append(PlacedSymbol(
        lib_id=power_lib_id,
        reference=builder.next_ref("#PWR"),
        value=destination_net,
        position=symbol_position,
        footprint="",
        rotation=0.0,
    ))


def place_one_passive_for_pin(
    builder: BlockLayoutBuilder,
    *,
    external: ExternalPart,
    resolved_destination: str,
    ic_pin_geometry,
    slot_index: int,
    ic_reference: str,
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
            :data:`HORIZONTAL_SWARM_PITCH_MM`; TOP/BOTTOM use
            :data:`PASSIVE_PITCH_MM`).
        ic_reference: The IC's reference designator (currently unused; kept
            for future per-IC accounting).
    """
    side = pin_side(
        ic_pin_geometry.relative,
        pin_rotation=getattr(ic_pin_geometry, "pin_rotation", 0.0),
        symbol_rotation=getattr(ic_pin_geometry, "symbol_rotation", 0.0),
    )
    pin_connection = ic_pin_geometry.connection

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
        primary_offset = PASSIVE_OFFSET_MM + slot_index * HORIZONTAL_SWARM_PITCH_MM
        passive_anchor = Point(
            snap_to_grid(pin_connection.x - primary_offset),
            pin_connection.y,
        )
        passive_rotation = 270.0
        near_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "right":
        primary_offset = PASSIVE_OFFSET_MM + slot_index * HORIZONTAL_SWARM_PITCH_MM
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + primary_offset),
            pin_connection.y,
        )
        passive_rotation = 90.0
        near_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "top":
        # Each slot occupies its own X column (fan laterally) so the
        # vertical wire from the IC pin to slot N's near pin doesn't
        # cross slot 0..N-1's far pins, which would short different nets.
        lateral_offset = slot_index * PASSIVE_PITCH_MM
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y - PASSIVE_OFFSET_MM),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
    else:  # bottom
        lateral_offset = slot_index * PASSIVE_PITCH_MM
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + lateral_offset),
            snap_to_grid(pin_connection.y + PASSIVE_OFFSET_MM),
        )
        passive_rotation = 180.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))

    ref_prefix = passive_ref_prefix(external.part_token)
    builder.symbols.append(PlacedSymbol(
        lib_id=passive_lib_id(external.part_token),
        reference=builder.next_ref(ref_prefix),
        value=passive_value(external.part_token),
        position=passive_anchor,
        footprint=passive_footprint(external.part_token),
        rotation=passive_rotation,
    ))

    # For non-zero-swarm-slot top/bottom passives, the near pin is not on
    # the IC pin's column — L-route to land cleanly without crossing other
    # passives' far pins.
    if pin_connection == near_point:
        pass
    elif pin_connection.x == near_point.x or pin_connection.y == near_point.y:
        builder.wires.append(PlacedWire(start=pin_connection, end=near_point))
    else:
        corner = Point(pin_connection.x, near_point.y)
        builder.wires.append(PlacedWire(start=pin_connection, end=corner))
        builder.wires.append(PlacedWire(start=corner, end=near_point))

    _attach_far_endpoint(
        builder,
        far_point=far_point,
        destination_net=resolved_destination,
        passive_rotation=passive_rotation,
        pin_side=side,
    )


def cluster_ic_externals(
    builder: BlockLayoutBuilder,
    *,
    ic,
    pin_geom_resolver,
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
    overrides_for_pin |= dict(getattr(ic, "pin_to_net", ()) or ())

    if getattr(ic, "power_input_net", ""):
        overrides_for_pin.setdefault("IN", ic.power_input_net)
    if getattr(ic, "power_output_net", ""):
        overrides_for_pin.setdefault("OUT", ic.power_output_net)

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
            place_one_passive_for_pin(
                builder,
                external=external,
                resolved_destination=resolved_destination,
                ic_pin_geometry=pin_geom,
                slot_index=slot_index,
                ic_reference=ic.reference,
            )
    return pin_geom_map
