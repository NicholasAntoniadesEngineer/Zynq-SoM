"""Predictive layout plan — computes every primitive's final position
BEFORE any of them is emitted.

The plan-then-emit architecture replaces the legacy reactive pipeline:

* Legacy: each phase modified ``BlockLayoutBuilder`` in place; downstream
  phases reacted to the partial state via candidate ladders. When a
  downstream phase couldn't escape a conflict it had to either soften
  a rule (exemption) or hard-fail. The frequent thrashing came from
  tactical patches added in one phase causing regressions in another.
* Predictive: a pure-functional ``plan_block(block, geometry_cache)``
  returns a ``LayoutPlan`` listing every prospective primitive. The
  planner's eight sub-phases (pin classification → lane widths →
  edge-stack row packing → anchors → realize lanes → symbols → routes
  → labels) each verify their additions against the partial plan and
  hard-fail with an actionable diagnostic when they cannot find a
  clean position. Once the plan is verified clean, ``emit_plan(plan,
  builder)`` walks the plan mechanically — no collision checks because
  the plan is already proven clean.

The core architectural insight is **per-pin lane reservation**: each
pin that needs outboard space (for a cluster of passives, a power
symbol, or a hier-label) gets a reserved X-lane wide enough for its
text bbox. Adjacent pins' lanes never overlap. This structurally
eliminates the ``wire_hlabel`` overlap class — the dominant remaining
failure mode of the reactive pipeline.

All primitive types are the existing :mod:`zynq_eda.core.model.sheet`
``PlacedX`` dataclasses — the plan is just a collection of ``PlacedX``
records plus per-pin / per-lane metadata used during planning.

See ``/Users/nicholasantoniades/.claude/plans/i-need-you-to-crystalline-fairy.md``
for the design document this module implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from zynq_eda.core.layout.bbox import BBox
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.block import Block, ConnectorInstance, IcInstance
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedJunction,
    PlacedLabel,
    PlacedNoConnect,
    PlacedSymbol,
    PlacedWire,
)


# ---------------------------------------------------------------------------
# Per-pin classification (Phase 1 output)
# ---------------------------------------------------------------------------

PinRole = Literal[
    "CLUSTER",       # has external_parts; cluster planner owns it
    "GND",           # pin name in GND-family
    "EDGE_LABEL",    # net is declared in block.external_nets
    "POWER_SYMBOL",  # net in POWER_SYMBOL_LIB_IDS but NOT in external_nets
    "LOCAL_LABEL",   # named net, not power, not declared external
    "NC",            # no mapping at all
]
"""Mutually exclusive per-pin role categories. Every IC/connector pin is
classified into EXACTLY ONE role at Phase 1; downstream phases dispatch
on role without re-classifying."""


PageSide = Literal["left", "right", "top", "bottom"]
"""Page-space side a pin extends from. Derived from
``(pin_rotation, symbol_rotation)`` in ``page_side_from_pin``."""


_ALLOWED_PIN_ROLES = frozenset(
    {"CLUSTER", "GND", "EDGE_LABEL", "POWER_SYMBOL", "LOCAL_LABEL", "NC"}
)
_ALLOWED_PAGE_SIDES = frozenset({"left", "right", "top", "bottom"})


@dataclass(frozen=True)
class PinSpec:
    """Resolved per-pin record produced by Phase 1 (``plan_pin_specs``).

    Every IC and connector pin on the block becomes one ``PinSpec`` with
    one ``role``. The classifier is pure — it does NOT require any
    anchors to be picked yet, because page side is derived from the
    pin's rotation + the symbol's rotation, both of which are constant
    in the block declaration.

    Cluster pins additionally carry their slot count and the per-slot
    destination nets so Phase 2 can compute lane widths from the
    longest destination name.
    """

    owner_kind: Literal["ic", "connector"]
    owner_ref: str
    owner_lib_id: str
    pin_name: str
    pin_number: str
    role: PinRole
    net_name: str
    page_side: PageSide
    pin_relative: Point
    cluster_slot_count: int = 0
    cluster_destinations: tuple[str, ...] = ()

    def __post_init__(self) -> None:  # pragma: no cover - simple guards
        if self.owner_kind not in ("ic", "connector"):
            raise ValueError(
                f"PinSpec.owner_kind must be 'ic' or 'connector', "
                f"got {self.owner_kind!r}"
            )
        if self.role not in _ALLOWED_PIN_ROLES:
            raise ValueError(
                f"PinSpec.role must be one of {sorted(_ALLOWED_PIN_ROLES)}, "
                f"got {self.role!r}"
            )
        if self.page_side not in _ALLOWED_PAGE_SIDES:
            raise ValueError(
                f"PinSpec.page_side must be one of {sorted(_ALLOWED_PAGE_SIDES)}, "
                f"got {self.page_side!r}"
            )
        if self.role == "NC" and self.net_name != "":
            raise ValueError(
                f"NC pins must have empty net_name, got {self.net_name!r} "
                f"for {self.owner_ref}/{self.pin_name}"
            )
        if self.role == "CLUSTER" and self.cluster_slot_count <= 0:
            raise ValueError(
                f"CLUSTER pins must have cluster_slot_count > 0, got "
                f"{self.cluster_slot_count} for {self.owner_ref}/{self.pin_name}"
            )
        if self.role == "CLUSTER" and len(self.cluster_destinations) != self.cluster_slot_count:
            raise ValueError(
                f"CLUSTER pin {self.owner_ref}/{self.pin_name}: "
                f"cluster_destinations has {len(self.cluster_destinations)} "
                f"entries but cluster_slot_count = {self.cluster_slot_count}"
            )
        if self.role != "CLUSTER" and self.cluster_slot_count != 0:
            raise ValueError(
                f"Non-CLUSTER pin {self.owner_ref}/{self.pin_name} must have "
                f"cluster_slot_count == 0, got {self.cluster_slot_count}"
            )


# ---------------------------------------------------------------------------
# Per-pin lane reservation (Phase 2 / Phase 5 output)
# ---------------------------------------------------------------------------

LaneKind = Literal[
    "cluster",        # cluster of passives + power-symbol/local-label
    "hier_label",     # sheet-edge hier-label
    "local_label",    # block-internal local label
    "pwr_flag",       # PWR_FLAG symbol + connecting wire
    "power_symbol",   # canonical power symbol (e.g. +3V3) at pin tip
    "gnd_symbol",     # power:GND symbol attached to a non-cluster GND pin
    "nc",             # NoConnect marker; zero-width lane
]
"""What primitive(s) the lane is reserved for. Drives the Phase 6
symbol-placement dispatch and the Phase 7 routing dispatch."""


_ALLOWED_LANE_KINDS = frozenset(
    {"cluster", "hier_label", "local_label", "pwr_flag", "power_symbol",
     "gnd_symbol", "nc"}
)


@dataclass(frozen=True)
class LaneAllocation:
    """One reserved lane on one edge of one symbol (IC or connector).

    Phase 2 produces lanes with ``(x_start, x_end, y_band_lo, y_band_hi,
    label_anchor)`` in ANCHOR-RELATIVE coordinates (``x_start`` is the
    distance OUTBOARD from the owner's anchor; ``y_band_*`` are
    relative to the pin's Y). Phase 5 (``plan_realize_lanes``) re-emits
    each lane with the same fields filled in PAGE COORDINATES once
    Phase 4 has chosen the owner's anchor.

    ``row_index`` is set by Phase 3 (``plan_edge_stacks``); -1 indicates
    "not yet packed". Within an owner+edge group, row 0 is the
    innermost (closest to the symbol body); higher rows are further
    outboard. The Y-band of every lane on the same row must be
    non-overlapping after Phase 5.
    """

    owner_ref: str
    pin_name: str
    edge: PageSide
    row_index: int
    x_start: float
    x_end: float
    y_band_lo: float
    y_band_hi: float
    lane_kind: LaneKind
    cluster_trunk_end_x: float | None = None
    label_anchor: Point | None = None
    label_rotation: float = 0.0
    label_text_extent_mm: float = 0.0
    pin_number: str = ""  # for disambiguating same-name pins (e.g.
                          # USB-C D+#A6 vs D+#B6 share pin_name "D+")

    def __post_init__(self) -> None:  # pragma: no cover - simple guards
        if self.edge not in _ALLOWED_PAGE_SIDES:
            raise ValueError(
                f"LaneAllocation.edge must be one of "
                f"{sorted(_ALLOWED_PAGE_SIDES)}, got {self.edge!r}"
            )
        if self.lane_kind not in _ALLOWED_LANE_KINDS:
            raise ValueError(
                f"LaneAllocation.lane_kind must be one of "
                f"{sorted(_ALLOWED_LANE_KINDS)}, got {self.lane_kind!r}"
            )
        if self.x_end < self.x_start:
            raise ValueError(
                f"LaneAllocation x_end ({self.x_end}) < x_start "
                f"({self.x_start}) for {self.owner_ref}/{self.pin_name}"
            )
        if self.y_band_hi < self.y_band_lo:
            raise ValueError(
                f"LaneAllocation y_band_hi ({self.y_band_hi}) < y_band_lo "
                f"({self.y_band_lo}) for {self.owner_ref}/{self.pin_name}"
            )
        if self.label_text_extent_mm < 0:
            raise ValueError(
                f"LaneAllocation.label_text_extent_mm must be >= 0, "
                f"got {self.label_text_extent_mm} for "
                f"{self.owner_ref}/{self.pin_name}"
            )

    @property
    def width_mm(self) -> float:
        """Lane's outboard X extent (anchor-relative or page-coord
        depending on phase)."""
        return self.x_end - self.x_start

    def with_row_index(self, row: int) -> "LaneAllocation":
        """Return a copy with ``row_index`` replaced. Used by Phase 3
        when packing lanes into rows."""
        from dataclasses import replace
        return replace(self, row_index=row)


# ---------------------------------------------------------------------------
# Per-edge row stack (Phase 3 output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeStack:
    """Lanes on one edge of one symbol, packed into rows.

    ``rows[r]`` is the ordered tuple of ``LaneAllocation`` records
    assigned to row ``r``. Row 0 is the innermost (closest to symbol
    body); subsequent rows sit ``LANE_ROW_PITCH_MM`` further outboard.

    ``total_outboard_extent_mm`` is the maximum ``x_end`` across all
    rows — used by Phase 4 to compute how far inboard from the page
    edge the owner's anchor must sit.
    """

    owner_ref: str
    edge: PageSide
    rows: tuple[tuple[LaneAllocation, ...], ...]
    total_outboard_extent_mm: float

    def __post_init__(self) -> None:  # pragma: no cover - simple guards
        if self.edge not in _ALLOWED_PAGE_SIDES:
            raise ValueError(
                f"EdgeStack.edge must be one of "
                f"{sorted(_ALLOWED_PAGE_SIDES)}, got {self.edge!r}"
            )
        if self.total_outboard_extent_mm < 0:
            raise ValueError(
                f"EdgeStack.total_outboard_extent_mm must be >= 0, got "
                f"{self.total_outboard_extent_mm} for "
                f"{self.owner_ref}/{self.edge}"
            )
        for r, row in enumerate(self.rows):
            for lane in row:
                if lane.owner_ref != self.owner_ref:
                    raise ValueError(
                        f"EdgeStack({self.owner_ref}/{self.edge}) contains "
                        f"lane belonging to {lane.owner_ref}"
                    )
                if lane.edge != self.edge:
                    raise ValueError(
                        f"EdgeStack({self.owner_ref}/{self.edge}) contains "
                        f"lane with edge {lane.edge}"
                    )
                if lane.row_index != r:
                    raise ValueError(
                        f"EdgeStack({self.owner_ref}/{self.edge}) row {r} "
                        f"contains lane with row_index {lane.row_index}"
                    )

    @property
    def num_rows(self) -> int:
        return len(self.rows)

    @property
    def num_lanes(self) -> int:
        return sum(len(row) for row in self.rows)


# ---------------------------------------------------------------------------
# Per-owner anchor (Phase 4 output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnchorPlan:
    """The page-coord placement of one IC or connector body.

    ``anchor`` is the symbol's reference point (matches what
    ``BlockLayoutBuilder.add_symbol`` consumes). ``rotation`` is
    0/90/180/270 (KiCad-valid). ``body_bbox_page`` is the symbol's
    visible body in page coordinates, used by Phase 5/6 to assert
    no body-body overlap and to derive lane positions.
    """

    owner_ref: str
    owner_kind: Literal["ic", "connector"]
    anchor: Point
    rotation: float
    body_bbox_page: BBox

    def __post_init__(self) -> None:  # pragma: no cover - simple guards
        if self.owner_kind not in ("ic", "connector"):
            raise ValueError(
                f"AnchorPlan.owner_kind must be 'ic' or 'connector', "
                f"got {self.owner_kind!r}"
            )
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                f"AnchorPlan.rotation must be 0/90/180/270, got "
                f"{self.rotation}"
            )


# ---------------------------------------------------------------------------
# Top-level plan accumulator
# ---------------------------------------------------------------------------


@dataclass
class LayoutPlan:
    """Mutable accumulator of every Phase's output.

    Phase outputs (set monotonically once, never mutated thereafter):
      - ``pin_specs`` — Phase 1
      - ``lane_allocations`` — Phase 2/5
      - ``edge_stacks`` — Phase 3
      - ``anchors`` — Phase 4

    Primitive lists (grown by Phase 6/7/8):
      - ``symbols`` — Phase 6
      - ``wires``, ``junctions`` — Phase 7
      - ``labels``, ``hierarchical_labels`` — Phase 8
      - ``no_connects`` — Phase 6 (for NC pins)

    Working state:
      - ``occupancy`` — Phase 6/7/8 maintain this in lockstep with the
        primitive lists so the router can probe against the partial
        plan as new primitives are added.
      - ``_anchor_by_ref`` — index built by Phase 4 for O(1) lookup.
      - ``_lane_by_owner_pin`` — index built by Phase 5 for O(1) lookup.

    After Phase 8 the plan is FROZEN — :func:`emit_plan` only reads
    from it.
    """

    pin_specs: tuple[PinSpec, ...] = ()
    lane_allocations: tuple[LaneAllocation, ...] = ()
    edge_stacks: tuple[EdgeStack, ...] = ()
    anchors: tuple[AnchorPlan, ...] = ()

    symbols: list[PlacedSymbol] = field(default_factory=list)
    wires: list[PlacedWire] = field(default_factory=list)
    labels: list[PlacedLabel] = field(default_factory=list)
    hierarchical_labels: list[PlacedHierarchicalLabel] = field(default_factory=list)
    junctions: list[PlacedJunction] = field(default_factory=list)
    no_connects: list[PlacedNoConnect] = field(default_factory=list)

    occupancy: Occupancy = field(default_factory=Occupancy)

    _anchor_by_ref: dict[str, AnchorPlan] = field(default_factory=dict)
    _lane_by_owner_pin: dict[tuple[str, str], LaneAllocation] = field(default_factory=dict)

    def __len__(self) -> int:
        return (
            len(self.symbols)
            + len(self.wires)
            + len(self.labels)
            + len(self.hierarchical_labels)
            + len(self.no_connects)
            + len(self.junctions)
        )

    def get_anchor(self, owner_ref: str) -> AnchorPlan:
        """Return the :class:`AnchorPlan` for ``owner_ref`` or raise.

        Hard-fails (KeyError) when the anchor hasn't been planned yet
        — phases must NOT silently swallow this; it's a planner bug
        if a downstream phase requests an anchor that Phase 4 didn't
        place.
        """
        try:
            return self._anchor_by_ref[owner_ref]
        except KeyError:
            raise KeyError(
                f"LayoutPlan: no AnchorPlan for owner_ref={owner_ref!r}. "
                f"Phase 4 (plan_anchors) must run before any caller "
                f"requests an anchor. Known anchors: "
                f"{sorted(self._anchor_by_ref)}"
            ) from None

    def get_lane(self, owner_ref: str, pin_name: str) -> LaneAllocation:
        """Return the :class:`LaneAllocation` for one pin or raise.

        Same contract as :meth:`get_anchor` — hard-fail rather than
        return None, because a missing lane indicates Phase 2/5
        didn't allocate space for a pin that Phase 6/7/8 expected
        to find.
        """
        key = (owner_ref, pin_name)
        try:
            return self._lane_by_owner_pin[key]
        except KeyError:
            raise KeyError(
                f"LayoutPlan: no LaneAllocation for {owner_ref!r}/{pin_name!r}. "
                f"Phase 2 (plan_lane_widths) + Phase 5 (plan_realize_lanes) "
                f"must run before any caller requests a lane."
            ) from None


# ---------------------------------------------------------------------------
# Phase 1 — plan_pin_specs: classify every pin on every IC and connector
# ---------------------------------------------------------------------------

_GND_PIN_NAME_PATTERNS = ("GND", "VSS", "GNDA", "AGND", "DGND")
_POWER_INPUT_PIN_NAMES = ("IN", "VDD", "VCC", "VBUS", "AVDD", "DVDD", "PVIN", "ANODE")
_POWER_OUTPUT_PIN_NAMES = ("OUT", "VOUT", "CATHODE")


def _is_gnd_pin_name(pin_name: str) -> bool:
    """True iff ``pin_name`` belongs to the GND-family naming convention.

    Matches plain ``GND``/``VSS``/``GNDA``/``AGND``/``DGND`` AND the
    ``<PATTERN>_*`` form (e.g. ``GND_EP``, ``GND_2``).

    Pure function; mirrors ``place.py:_is_gnd_pin_name`` exactly so the
    planner classification matches the reactive classifier's partition
    for the side-by-side assertion in PR 2.
    """
    name_upper = pin_name.upper()
    return (
        name_upper in _GND_PIN_NAME_PATTERNS
        or any(name_upper.startswith(p + "_") for p in _GND_PIN_NAME_PATTERNS)
    )


def _resolve_ic_pin_net(pin_name: str, ic: IcInstance) -> str:
    """Resolve which net an IC pin is on.

    Priority order: ``refcircuit.pin_net_overrides | net_overrides`` win
    first; then ``power_input_net`` for canonical input-pin names; then
    ``power_output_net`` for output names. Returns the empty string
    when no mapping applies (caller routes to NC).

    Mirrors ``place.py:_compute_pin_net`` exactly.
    """
    overrides = dict(ic.refcircuit.pin_net_overrides) | dict(
        getattr(ic, "net_overrides", ()) or ()
    )
    direct = overrides.get(pin_name, "")
    if direct:
        return direct
    if pin_name in _POWER_INPUT_PIN_NAMES and ic.power_input_net:
        return ic.power_input_net
    if pin_name in _POWER_OUTPUT_PIN_NAMES and ic.power_output_net:
        return ic.power_output_net
    return ""


def _remap_cluster_destination(to_net: str, ic: IcInstance) -> str:
    """Apply the IC's ``external_part_net_remap`` to a cluster destination."""
    remap = dict(getattr(ic, "external_part_net_remap", ()) or ())
    return remap.get(to_net, to_net)


def _classify_ic_pin(
    pin_name: str,
    ic: IcInstance,
    declared_nets: dict,
    *,
    in_cluster: bool,
) -> tuple[PinRole, str]:
    """Classify an IC pin into EXACTLY ONE role and return (role, net).

    Priority order matches ``place.py:_classify_pin``:
      1. CLUSTER — pin has external_parts attached.
      2. GND — name matches GND-family.
      3. EDGE_LABEL — net is in block.external_nets.
      4. POWER_SYMBOL — net in POWER_SYMBOL_LIB_IDS but not external.
      5. LOCAL_LABEL — named net, none of the above.
      6. NC — no net mapping at all.
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS as _PWR
    if in_cluster:
        return "CLUSTER", _resolve_ic_pin_net(pin_name, ic)
    if _is_gnd_pin_name(pin_name):
        return "GND", "GND"
    net = _resolve_ic_pin_net(pin_name, ic)
    if not net:
        return "NC", ""
    if net in declared_nets:
        return "EDGE_LABEL", net
    if net in _PWR:
        return "POWER_SYMBOL", net
    return "LOCAL_LABEL", net


def _build_pin_to_net_map(
    connector: ConnectorInstance,
    name_to_number: dict[str, str],
) -> dict[str, str]:
    """Resolve ``connector.pin_to_net`` (keyed by name OR number) into a
    dict keyed by canonical pin NAME.

    ``pin_to_net`` entries may use either a pin's name (``"VBUS"``) or
    its number (``"4"``). The connector pass tries both. Here we resolve
    both forms into the canonical-name key so the classifier can use a
    single lookup. Names take precedence over numbers when both forms
    appear (shouldn't happen in well-formed configs).
    """
    number_to_name = {num: name for name, num in name_to_number.items()}
    out: dict[str, str] = {}
    for pin_id, net_name in connector.pin_to_net:
        pid = str(pin_id)
        if pid in name_to_number:
            # pin_id is a name
            out.setdefault(pid, net_name)
        elif pid in number_to_name:
            # pin_id is a number
            out.setdefault(number_to_name[pid], net_name)
        # If pid matches neither, the connector pass silently drops it
        # (resolve returns None at runtime). We preserve that behaviour
        # here so the planner's classification matches the reactive
        # build's output.
    return out


def _classify_connector_pin(
    pin_name: str,
    connector: ConnectorInstance,
    pin_to_net: dict[str, str],
    declared_nets: dict,
    *,
    in_cluster: bool,
) -> tuple[PinRole, str]:
    """Classify a connector pin into EXACTLY ONE role.

    Connector classification differs from IC classification in that
    the net mapping comes from ``connector.pin_to_net`` (resolved via
    :func:`_build_pin_to_net_map`) instead of refcircuit overrides +
    power_input/output_net. The same priority order applies.

    Pins NOT in ``pin_to_net`` and NOT in ``external_parts.from_pin``
    fall to NC (matching the reactive build's auto-NC behaviour for
    every pin not explicitly handled).
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS as _PWR
    if in_cluster:
        # The cluster pass owns the pin; the destination comes from
        # external_parts (handled at PinSpec.cluster_destinations time).
        # The net_name field is informational for diagnostics — pick the
        # most-common destination on the pin's external_parts.
        ext_destinations = [
            ep.to_net for ep in connector.refcircuit.external_parts
            if ep.from_pin == pin_name
        ]
        net = ext_destinations[0] if ext_destinations else ""
        return "CLUSTER", net
    if _is_gnd_pin_name(pin_name):
        return "GND", "GND"
    net = pin_to_net.get(pin_name, "")
    if not net:
        return "NC", ""
    if net in declared_nets:
        return "EDGE_LABEL", net
    if net in _PWR:
        return "POWER_SYMBOL", net
    return "LOCAL_LABEL", net


def _enumerate_owner_pins(
    owner_lib_id: str,
    geometry,
    rotation: float = 0.0,
) -> list[tuple[str, str, Point, float]]:
    """Resolve every pin on a symbol → ``(name, number, relative, pin_rot)``.

    Uses :meth:`SymbolGeometryCache.all_pins` for the per-pin metadata
    and looks up `pin_rotation` via the cached library. Returns a list
    so the planner can iterate deterministically.

    Pins whose geometry can't be resolved are silently dropped — same
    behaviour as the reactive ``_resolve_pin_geometry``. The audit pass
    (Stage 0) catches refcircuit/symbol mismatches before we reach the
    planner.
    """
    from zynq_eda.core.layout.geometry import _pin_rotation_from_symbol

    pins: list[tuple[str, str, Point, float]] = []
    for pin_info in geometry.all_pins(owner_lib_id, rotation=rotation):
        name = str(pin_info["name"])
        number = str(pin_info["number"])
        pos = pin_info.get("position")
        if pos is None:
            continue
        # `pos` comes from kicad-sch-api's list_pins() and is its native
        # point type with .x / .y attributes — NOT the project's Point.
        try:
            rel = Point(float(pos.x), float(pos.y))
        except AttributeError:
            # Defensive fallback: tuple-like.
            try:
                rel = Point(float(pos[0]), float(pos[1]))
            except (TypeError, IndexError):
                continue
        try:
            pin_rot = _pin_rotation_from_symbol(owner_lib_id, number)
        except Exception:
            pin_rot = 0.0
        pins.append((name, number, rel, float(pin_rot)))
    return pins


def plan_pin_specs(
    block: Block,
    geometry,
) -> tuple[PinSpec, ...]:
    """Phase 1 — pure classification of every IC + connector pin.

    Returns one :class:`PinSpec` per pin in
    ``[*block.ics, *block.connectors]``. Every pin is classified into
    EXACTLY one role; cluster pins additionally carry their slot count
    and destination nets so Phase 2 can compute lane widths.

    Pure function: no occupancy reads, no anchors needed (page_side is
    derived from pin/symbol rotation alone). The output is fully
    determined by ``block`` + ``geometry``.

    Order: ICs first (in ``block.ics`` order), then connectors (in
    ``block.connectors`` order). Within each owner, pins are emitted in
    ``geometry.all_pins`` order (which is the symbol-library's natural
    pin order).
    """
    from zynq_eda.core.layout.geometry import page_side_from_pin

    declared_nets = {n.name: n for n in block.external_nets}
    specs: list[PinSpec] = []

    # --- ICs ---------------------------------------------------------------
    for ic in block.ics:
        cluster_externals_by_pin: dict[str, list[str]] = {}
        for ep in ic.refcircuit.external_parts:
            dests = cluster_externals_by_pin.setdefault(ep.from_pin, [])
            for _ in range(ep.quantity):
                dests.append(_remap_cluster_destination(ep.to_net, ic))
        cluster_pins = set(cluster_externals_by_pin.keys())

        for pin_name, pin_number, rel, pin_rot in _enumerate_owner_pins(
            ic.lib_id, geometry, rotation=0.0,
        ):
            in_cluster = pin_name in cluster_pins
            role, net = _classify_ic_pin(
                pin_name, ic, declared_nets, in_cluster=in_cluster,
            )
            side = page_side_from_pin(pin_rotation=pin_rot, symbol_rotation=0.0)
            if role == "CLUSTER":
                dests = tuple(cluster_externals_by_pin[pin_name])
                spec = PinSpec(
                    owner_kind="ic",
                    owner_ref=ic.reference,
                    owner_lib_id=ic.lib_id,
                    pin_name=pin_name,
                    pin_number=pin_number,
                    role="CLUSTER",
                    net_name=net,
                    page_side=side,
                    pin_relative=rel,
                    cluster_slot_count=len(dests),
                    cluster_destinations=dests,
                )
            else:
                spec = PinSpec(
                    owner_kind="ic",
                    owner_ref=ic.reference,
                    owner_lib_id=ic.lib_id,
                    pin_name=pin_name,
                    pin_number=pin_number,
                    role=role,
                    net_name=net,
                    page_side=side,
                    pin_relative=rel,
                )
            specs.append(spec)

    # --- Connectors --------------------------------------------------------
    for connector in block.connectors:
        cluster_externals_by_pin = {}
        for ep in connector.refcircuit.external_parts:
            dests = cluster_externals_by_pin.setdefault(ep.from_pin, [])
            for _ in range(ep.quantity):
                # Connectors don't have external_part_net_remap.
                dests.append(ep.to_net)
        cluster_pins = set(cluster_externals_by_pin.keys())

        connector_pins = _enumerate_owner_pins(
            connector.lib_id, geometry, rotation=connector.rotation,
        )
        name_to_number = {n: num for (n, num, _r, _pr) in connector_pins}
        pin_to_net = _build_pin_to_net_map(connector, name_to_number)

        for pin_name, pin_number, rel, pin_rot in connector_pins:
            in_cluster = pin_name in cluster_pins
            role, net = _classify_connector_pin(
                pin_name, connector, pin_to_net, declared_nets,
                in_cluster=in_cluster,
            )
            side = page_side_from_pin(
                pin_rotation=pin_rot, symbol_rotation=connector.rotation,
            )
            if role == "CLUSTER":
                dests = tuple(cluster_externals_by_pin[pin_name])
                spec = PinSpec(
                    owner_kind="connector",
                    owner_ref=connector.reference,
                    owner_lib_id=connector.lib_id,
                    pin_name=pin_name,
                    pin_number=pin_number,
                    role="CLUSTER",
                    net_name=net,
                    page_side=side,
                    pin_relative=rel,
                    cluster_slot_count=len(dests),
                    cluster_destinations=dests,
                )
            else:
                spec = PinSpec(
                    owner_kind="connector",
                    owner_ref=connector.reference,
                    owner_lib_id=connector.lib_id,
                    pin_name=pin_name,
                    pin_number=pin_number,
                    role=role,
                    net_name=net,
                    page_side=side,
                    pin_relative=rel,
                )
            specs.append(spec)

    return tuple(specs)


# ---------------------------------------------------------------------------
# Phase 2 — plan_lane_widths: per-pin lane width (anchor-relative)
# ---------------------------------------------------------------------------


def _hlabel_text_width_mm(net_name: str) -> float:
    """Predict the width (mm) of a hier-label's text bbox for ``net_name``.

    Matches ``_hierarchical_label_bbox`` in ``_builder.py`` — which adds
    a trailing space to account for the hier-label's arrow decoration —
    so the width prediction matches what the validator will measure
    after emission.
    """
    from zynq_eda.core.layout.bbox import (
        DEFAULT_TEXT_SIZE_MM,
        DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
    )
    # +1 char for the decorating arrow/trailing space.
    return (
        (len(net_name) + 1)
        * DEFAULT_TEXT_SIZE_MM
        * DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO
    )


def _label_text_width_mm(net_name: str) -> float:
    """Predict the width (mm) of a local-label's text bbox for ``net_name``.

    Local labels render the bare net name with no decoration; this is
    one char narrower than the hier-label equivalent.
    """
    from zynq_eda.core.layout.bbox import (
        DEFAULT_TEXT_SIZE_MM,
        DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
    )
    return (
        len(net_name)
        * DEFAULT_TEXT_SIZE_MM
        * DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO
    )


def _lane_width_for_spec(spec: PinSpec) -> float:
    """Compute the anchor-relative lane width required by one PinSpec.

    Pure function returning a single float (mm). Encodes the per-role
    formula from the design doc:

      CLUSTER       PASSIVE_OFFSET + (slot-1)*PITCH + POWER_SYMBOL_OFFSET
                    + text_width(longest destination)
      EDGE_LABEL    HLABEL_ANCHOR_OFFSET + hlabel_text_width + 2*CLEARANCE
      LOCAL_LABEL   HLABEL_ANCHOR_OFFSET + label_text_width + 2*CLEARANCE
      GND           POWER_SYMBOL_OFFSET + GND_SYMBOL_HALF_EXTENT
      POWER_SYMBOL  0 (placed AT pin tip; the symbol's own width is
                       accounted for by the body bbox, not by a lane)
      NC            0
    """
    from zynq_eda.core.layout._constants import (
        GND_SYMBOL_HALF_EXTENT_MM,
        HLABEL_ANCHOR_OFFSET_MM,
        PASSIVE_OFFSET_MM,
        PASSIVE_PITCH_MM,
        POWER_SYMBOL_OFFSET_MM,
        VISUAL_CLEARANCE_MM,
    )

    if spec.role == "CLUSTER":
        longest_dest = max(spec.cluster_destinations, key=len, default="")
        # Max stagger depends on edge:
        #   LEFT/RIGHT: 5-way × 10.16 = 40.64 mm
        #   TOP/BOTTOM: 2-way × 5.08 = 5.08 mm
        if spec.page_side in ("left", "right"):
            max_stagger_mm = 4 * 10.16
        else:
            max_stagger_mm = 2 * 7.62  # 3-way × 7.62 for TOP/BOTTOM
        cluster_outboard = (
            PASSIVE_OFFSET_MM
            + max(0, spec.cluster_slot_count - 1) * PASSIVE_PITCH_MM
            + max_stagger_mm
        )
        far_extent = POWER_SYMBOL_OFFSET_MM + _hlabel_text_width_mm(longest_dest)
        return cluster_outboard + far_extent
    if spec.role == "EDGE_LABEL":
        return (
            HLABEL_ANCHOR_OFFSET_MM
            + _hlabel_text_width_mm(spec.net_name)
            + 2 * VISUAL_CLEARANCE_MM
        )
    if spec.role == "LOCAL_LABEL":
        return (
            HLABEL_ANCHOR_OFFSET_MM
            + _label_text_width_mm(spec.net_name)
            + 2 * VISUAL_CLEARANCE_MM
        )
    if spec.role == "GND":
        # GND symbol sits AT the pin tip (KiCad merges them); only the
        # symbol's body half-extent + visual clearance is reserved.
        return GND_SYMBOL_HALF_EXTENT_MM + 2 * VISUAL_CLEARANCE_MM
    if spec.role == "POWER_SYMBOL":
        return 0.0
    if spec.role == "NC":
        return 0.0
    raise AssertionError(f"unhandled role {spec.role!r}")


def _lane_kind_for_role(role: PinRole) -> LaneKind:
    """Map a pin's role to its lane kind."""
    return {
        "CLUSTER": "cluster",
        "EDGE_LABEL": "hier_label",
        "LOCAL_LABEL": "local_label",
        "GND": "gnd_symbol",
        "POWER_SYMBOL": "power_symbol",
        "NC": "nc",
    }[role]


def _input_pwr_flag_nets(block: Block) -> tuple[str, ...]:
    """Return the names of nets that will receive a PWR_FLAG.

    Mirrors the eligibility logic in ``edge_labels.py:_input_pwr_flags``:
    input-direction nets sourced on this block (i.e. having a connector
    pin producing them); plus output nets without an IC driver; plus
    non-canonical ground variants (CHASSIS_GND etc.).

    Returns a tuple in declaration order so the synthetic PWR_FLAG
    lane order is deterministic.
    """
    nets_sourced_by_connector: set[str] = set()
    for conn in block.connectors:
        for _pin_id, net_name in conn.pin_to_net:
            nets_sourced_by_connector.add(net_name)

    out: list[str] = []
    for net in block.external_nets:
        if net.power_kind not in ("input", "output", "ground"):
            continue
        if net.power_kind == "ground" and net.name.upper() == "GND":
            # Canonical GND driven by power:GND — no PWR_FLAG.
            continue
        if net.power_kind == "output":
            has_driver = any(ic.power_output_net == net.name for ic in block.ics)
            if has_driver:
                continue
        if net.power_kind == "input" and net.name not in nets_sourced_by_connector:
            continue
        out.append(net.name)
    return tuple(out)


def plan_lane_widths(
    pin_specs: tuple[PinSpec, ...],
    block: Block,
    geometry,
) -> tuple[LaneAllocation, ...]:
    """Phase 2 — per-pin lane widths in ANCHOR-RELATIVE coordinates.

    Produces one :class:`LaneAllocation` per non-zero-width pin
    (NC and POWER_SYMBOL pins get no lane — they're placed AT the pin
    tip with no outboard reservation). Lane positions encode "this pin
    needs N mm outboard from its tip"; Phase 5 fills the absolute
    page coordinates once Phase 4 has chosen the owner's anchor.

    Also synthesises PWR_FLAG lanes — one per input-power net the
    block emits a PWR_FLAG for. The PWR_FLAG lane is owned by the
    BLOCK (owner_ref = block.name) because the flag is anchored on a
    same-name local label that may sit on any of several IC/connector
    pins. The synthetic lane's pin_name is ``f"pwr_flag:{net_name}"``
    so the index key is unique. ``edge`` defaults to the net's
    declared edge.

    Pure function. No occupancy reads. No geometry probes.
    """
    from zynq_eda.core.layout._constants import (
        FLG_BODY_EXTENT_MM,
        VISUAL_CLEARANCE_MM,
    )
    from zynq_eda.core.model.interface import SheetEdge

    lanes: list[LaneAllocation] = []

    # --- Per-pin lanes -----------------------------------------------------
    for spec in pin_specs:
        width = _lane_width_for_spec(spec)
        if width <= 0.0:
            # NC / POWER_SYMBOL: no outboard reservation needed.
            continue
        lane_kind = _lane_kind_for_role(spec.role)
        lanes.append(LaneAllocation(
            owner_ref=spec.owner_ref,
            pin_name=spec.pin_name,
            pin_number=spec.pin_number,
            edge=spec.page_side,
            row_index=-1,
            x_start=0.0,
            x_end=width,
            y_band_lo=spec.pin_relative.y,
            y_band_hi=spec.pin_relative.y,
            lane_kind=lane_kind,
            label_text_extent_mm=(
                width if lane_kind in ("hier_label", "local_label") else 0.0
            ),
        ))

    # --- Synthetic PWR_FLAG lanes -----------------------------------------
    declared_nets_by_name = {n.name: n for n in block.external_nets}
    for net_name in _input_pwr_flag_nets(block):
        net = declared_nets_by_name[net_name]
        # PWR_FLAG lives on the same edge as the net's hier-label —
        # this keeps it visually grouped with the rail's hier-label
        # and gives the planner a deterministic placement column.
        edge: PageSide = (
            "left" if net.edge == SheetEdge.LEFT else "right"
        )
        flag_width = FLG_BODY_EXTENT_MM + _hlabel_text_width_mm(net_name)
        lanes.append(LaneAllocation(
            owner_ref=block.name,
            pin_name=f"pwr_flag:{net_name}",
            edge=edge,
            row_index=-1,
            x_start=0.0,
            x_end=flag_width,
            y_band_lo=0.0,
            y_band_hi=0.0,
            lane_kind="pwr_flag",
            label_text_extent_mm=flag_width,
        ))

    return tuple(lanes)


# ---------------------------------------------------------------------------
# Phase 3 — plan_edge_stacks: pack lanes into rows per (owner, edge)
# ---------------------------------------------------------------------------


def _owner_body_extent_mm(
    owner_ref: str,
    block: Block,
    geometry,
    edge: PageSide,
) -> float:
    """Return the symbol body's extent along the secondary axis of ``edge``.

    For LEFT/RIGHT edges (lanes extend along X), returns the body's
    full X width. For TOP/BOTTOM edges (lanes extend along Y), returns
    the body's full Y height.

    For block-owned PWR_FLAG lanes (no symbol body), returns 0.
    """
    # Find the owner among ICs / connectors. PWR_FLAG synthetic lanes
    # use owner_ref = block.name, which won't match any IC / connector.
    for ic in block.ics:
        if ic.reference == owner_ref:
            try:
                bbox = geometry.bounding_box(ic.lib_id, rotation=0.0)
            except Exception:
                return 0.0
            return bbox.width if edge in ("left", "right") else bbox.height
    for conn in block.connectors:
        if conn.reference == owner_ref:
            try:
                bbox = geometry.bounding_box(conn.lib_id, rotation=conn.rotation)
            except Exception:
                return 0.0
            return bbox.width if edge in ("left", "right") else bbox.height
    return 0.0


def _per_row_budget_mm(
    block: Block,
    body_extent_mm: float,
    edge: PageSide,
) -> float:
    """Return the maximum outboard extent (x_end) a lane on ``edge``
    can reach, assuming the owner's body sits centered between the
    two edges.

    Formula (anchor-relative, conservative lower bound):

        budget = (page_dim_along_edge - 2 * INTERIOR_MARGIN_MM
                  - body_extent_mm) / 2

    For LEFT/RIGHT edges, ``page_dim_along_edge`` = page width.
    For TOP/BOTTOM, page height.
    """
    from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    if edge in ("left", "right"):
        page_dim = paper_w
    else:
        page_dim = paper_h
    return (page_dim - 2 * INTERIOR_MARGIN_MM - body_extent_mm) / 2.0


def _y_bands_overlap(
    a_lo: float, a_hi: float,
    b_lo: float, b_hi: float,
    *,
    pad_mm: float,
) -> bool:
    """True iff ``[a_lo, a_hi]`` and ``[b_lo, b_hi]`` overlap within
    ``pad_mm`` of clearance on both sides.

    Used by the row packer to decide whether two lanes can sit on the
    same row.
    """
    a_lo_padded = a_lo - pad_mm
    a_hi_padded = a_hi + pad_mm
    return not (a_hi_padded < b_lo or b_hi < a_lo_padded)


def _label_y_band_for_lane(lane: LaneAllocation) -> tuple[float, float]:
    """Predict the Y bbox of the lane's label / symbol payload."""
    from zynq_eda.core.layout.bbox import DEFAULT_TEXT_SIZE_MM
    from zynq_eda.core.layout._constants import VISUAL_CLEARANCE_MM

    if lane.lane_kind in ("hier_label", "local_label", "pwr_flag", "cluster"):
        half = DEFAULT_TEXT_SIZE_MM / 2.0 + VISUAL_CLEARANCE_MM
        return (lane.y_band_lo - half, lane.y_band_hi + half)
    return (lane.y_band_lo - 2.54, lane.y_band_hi + 2.54)


def _format_lane_overflow_diagnostic(
    owner_ref: str,
    edge: PageSide,
    lanes_on_edge: list[LaneAllocation],
    unplaced_lane: LaneAllocation,
    rows_used: int,
    per_row_budget: float,
    max_rows: int,
    block: Block,
) -> str:
    """Build the structured RuntimeError message for lane-row overflow.

    Names the block.py edits the user should try, in priority order.
    """
    short_block_path = (
        f"eda/src/zynq_eda/projects/carrier/blocks/{block.name}.py"
    )
    return (
        f"plan_edge_stacks: row capacity exhausted on {edge.upper()} edge "
        f"of {owner_ref}.\n"
        f"  Owner:    {owner_ref}\n"
        f"  Edge:     {edge.upper()} ({len(lanes_on_edge)} lanes requested, "
        f"per-row budget {per_row_budget:.1f} mm, current rows used = "
        f"{rows_used})\n"
        f"  Unplaced: pin={unplaced_lane.pin_name!r}, width="
        f"{unplaced_lane.width_mm:.1f} mm, lane_kind="
        f"{unplaced_lane.lane_kind}\n"
        f"  Limit:    MAX_LANE_ROWS={max_rows}\n"
        f"  Upstream fix (try in priority order):\n"
        f"    1. Move ~half of the {len(lanes_on_edge)} {edge.upper()}-edge "
        f"nets to the opposite SheetEdge in {short_block_path} "
        f"(toggle .edge per ExternalNet declaration).\n"
        f"    2. Split {block.name} into two blocks (e.g. "
        f"{block.name}_a and {block.name}_b) so each has half the lanes.\n"
        f"    3. Increase paper_size from {block.paper_size!r} to a larger "
        f"size in {short_block_path} (only if (1) and (2) don't apply)."
    )


def plan_edge_stacks(
    lane_allocations: tuple[LaneAllocation, ...],
    block: Block,
    geometry,
    *,
    max_lane_rows: int | None = None,
) -> tuple[EdgeStack, ...]:
    """Phase 3 — pack lanes into rows per ``(owner_ref, edge)`` group.

    Greedy algorithm: for each lane (sorted by secondary-axis position),
    find the LOWEST row whose existing lanes don't conflict in Y AND
    whose effective outboard extent (row_offset + lane.width) fits
    within the per-row budget. If no existing row works AND we haven't
    hit :data:`MAX_LANE_ROWS`, open a new row. If we have, hard-fail
    with a structured diagnostic naming the upstream block.py edit.

    Row stacking offsets each subsequent row outboard by
    :data:`LANE_ROW_PITCH_MM`, so row 1 lanes sit further OUT than
    row 0 lanes. The row offset is recorded as the lane's
    ``row_index`` (the actual x_start shift is computed in Phase 5).

    Pure function. No side effects.
    """
    from zynq_eda.core.layout._constants import (
        LANE_ROW_PITCH_MM,
        MAX_LANE_ROWS,
        VISUAL_CLEARANCE_MM,
    )

    rows_cap = max_lane_rows if max_lane_rows is not None else MAX_LANE_ROWS

    # Group lanes by (owner_ref, edge). Preserve declaration order
    # within each group so the packing is deterministic.
    groups: dict[tuple[str, PageSide], list[LaneAllocation]] = {}
    for lane in lane_allocations:
        groups.setdefault((lane.owner_ref, lane.edge), []).append(lane)

    stacks: list[EdgeStack] = []
    for (owner_ref, edge), group in groups.items():
        body_extent = _owner_body_extent_mm(owner_ref, block, geometry, edge)
        budget = _per_row_budget_mm(block, body_extent, edge)

        # Sort by secondary axis: Y for LEFT/RIGHT, X for TOP/BOTTOM.
        # PWR_FLAG synthetic lanes have y_band_lo = y_band_hi = 0; they
        # sort to the front but get placed at the end of the row (their
        # actual Y is decided in Phase 4).
        sort_key = (
            (lambda l: (l.y_band_lo, l.pin_name))
            if edge in ("left", "right")
            else (lambda l: (l.x_start, l.pin_name))
        )
        sorted_lanes = sorted(group, key=sort_key)

        # Pack: rows[r] is the list of LaneAllocations placed on row r
        # (with row_index updated). row_max_inboard_extent[r] tracks the
        # widest lane in row r so we can compute the row's outboard reach.
        rows: list[list[LaneAllocation]] = []
        row_max_inboard_extent: list[float] = []

        def _row_can_hold(r: int, lane: LaneAllocation) -> bool:
            """Pure check: does row ``r`` have space for ``lane``?

            Two conditions, both required:
              1. No existing lane on row r conflicts with this lane's
                 predicted Y-band (label height + clearance).
              2. The lane fits within the effective per-row budget
                 (budget - r * LANE_ROW_PITCH_MM accounts for the row
                 being shifted outboard).
            """
            my_lo, my_hi = _label_y_band_for_lane(lane)
            y_conflict = any(
                _y_bands_overlap(my_lo, my_hi,
                                 *_label_y_band_for_lane(other), pad_mm=0.0)
                for other in rows[r]
            )
            if y_conflict:
                return False
            effective_budget = budget - r * LANE_ROW_PITCH_MM
            return lane.width_mm <= effective_budget

        for lane in sorted_lanes:
            # Pure-functional row pick: enumerate existing row indices,
            # filter to those that can hold this lane, take the FIRST.
            # next(gen, None) returns None when no row fits — mirrors
            # the _first_clean_route / _first_clean_candidate pattern.
            existing_rows = range(len(rows))
            picked_row = next(
                (r for r in existing_rows if _row_can_hold(r, lane)),
                None,
            )
            if picked_row is not None:
                rows[picked_row].append(lane.with_row_index(picked_row))
                row_max_inboard_extent[picked_row] = max(
                    row_max_inboard_extent[picked_row], lane.width_mm,
                )
            else:
                # No existing row fits. Need to open a new row.
                new_row = len(rows)
                effective_budget = budget - new_row * LANE_ROW_PITCH_MM
                row_count_ok = new_row < rows_cap
                lane_fits_new = lane.width_mm <= effective_budget
                if not (row_count_ok and lane_fits_new):
                    raise RuntimeError(
                        _format_lane_overflow_diagnostic(
                            owner_ref=owner_ref, edge=edge,
                            lanes_on_edge=group,
                            unplaced_lane=lane,
                            rows_used=len(rows),
                            per_row_budget=budget,
                            max_rows=rows_cap,
                            block=block,
                        )
                    )
                rows.append([lane.with_row_index(new_row)])
                row_max_inboard_extent.append(lane.width_mm)

        total_outboard = (
            max(
                (row_max_inboard_extent[r] + r * LANE_ROW_PITCH_MM
                 for r in range(len(rows))),
                default=0.0,
            )
        )
        stacks.append(EdgeStack(
            owner_ref=owner_ref, edge=edge,
            rows=tuple(tuple(row) for row in rows),
            total_outboard_extent_mm=total_outboard,
        ))

    return tuple(stacks)


# ---------------------------------------------------------------------------
# Phase 4 — plan_anchors: derive every owner's page-coord anchor
# ---------------------------------------------------------------------------


# Top-side cap chain clearance for IC Y-stacking. Mirrors the legacy
# constant in place.py:_ic_anchors_for_block (CAP_CHAIN_CLEARANCE_MM).
_IC_CAP_CHAIN_CLEARANCE_MM = 29.21


def _shift_symbol_bbox_to_page(bbox, anchor: Point):
    """Given a symbol-local SymbolBoundingBox and a page anchor, return
    a page-coord ``BBox`` with `kind="symbol"` and a unique owner_id.

    Mirrors the conversion `body_bbox.shift_by(anchor)` used elsewhere
    in the codebase. Returns a project-level :class:`BBox`.
    """
    from zynq_eda.core.layout.bbox import BBox as _BBox
    shifted = bbox.shift_by(anchor)
    return _BBox(
        min=Point(shifted.min_x, shifted.min_y),
        max=Point(shifted.max_x, shifted.max_y),
        kind="symbol",
        owner_id="planner:body",  # rewritten in Phase 6
    )


def plan_anchors(
    block: Block,
    edge_stacks: tuple[EdgeStack, ...],
    geometry,
    pin_specs: tuple[PinSpec, ...] = (),
) -> tuple[AnchorPlan, ...]:
    """Phase 4 — derive every IC and connector's page-coord anchor.

    For each owner:
      anchor.x = (page_margin + LEFT_outboard + body_half_width) for ICs
                  positioned in the left column;
                = paper_w - (page_margin + RIGHT_outboard + body_half_width)
                  for connectors on the right edge.
      anchor.y = stacked vertically using the existing bbox-aware
                 algorithm (one IC per row in a column; connectors form
                 their own column on the declared edge).

    Hard-fails when:
      * An IC's lane stacks won't fit between the page margins.
      * A connector's lane stack won't fit on its declared edge.

    Block-owned (PWR_FLAG) edge stacks are SKIPPED — they don't
    correspond to a placed symbol that needs an anchor; their
    realization happens in Phase 5.
    """
    from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.interface import SheetEdge
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM

    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]

    # Group edge stacks by owner_ref; SKIP block-owned (PWR_FLAG) groups.
    stacks_by_owner: dict[str, dict[PageSide, EdgeStack]] = {}
    for stack in edge_stacks:
        if stack.owner_ref == block.name:
            continue
        stacks_by_owner.setdefault(stack.owner_ref, {})[stack.edge] = stack

    def _outboard(owner_ref: str, edge: PageSide) -> float:
        return (
            stacks_by_owner.get(owner_ref, {})
            .get(edge, EdgeStack(owner_ref=owner_ref, edge=edge, rows=(),
                                 total_outboard_extent_mm=0.0))
            .total_outboard_extent_mm
        )

    # Per-IC TOP-side cap-chain reach. The IC anchor must sit far
    # enough from the top page margin that all TOP-side cluster caps
    # (and their far-end power symbols/labels) land INSIDE the page.
    # Compute, for each IC, the max upward extent above its anchor:
    #   max_top_pin_above_anchor + TOP_edge_outboard_extent_mm
    # where the lane's total_outboard_extent already encodes
    # PASSIVE_OFFSET + max_stagger + slot pitch + far symbol/label.
    top_reach_by_owner: dict[str, float] = {}
    for spec in pin_specs:
        if spec.owner_kind != "ic":
            continue
        if spec.page_side != "top":
            continue
        # In symbol-local coords, a TOP-side pin has pin_relative.y > 0
        # (pin sits "above" the anchor on the page after Y-flip).
        pin_above = abs(spec.pin_relative.y)
        existing = top_reach_by_owner.get(spec.owner_ref, 0.0)
        top_reach_by_owner[spec.owner_ref] = max(existing, pin_above)

    anchors: list[AnchorPlan] = []

    # --- ICs: vertical column, anchor.x = base_margin + LEFT_extent + half_w
    # The first IC sits below the top margin; subsequent ICs stack with
    # bbox-aware spacing + cap-chain clearance.
    ic_y_cursor = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
    prev_ic_half_down = 0.0
    for index, ic in enumerate(block.ics):
        try:
            body = geometry.bounding_box(ic.lib_id, rotation=0.0)
            body_half_w = body.width / 2.0
            body_half_h_up = abs(body.min_y)
            body_half_h_down = abs(body.max_y)
        except Exception:
            body = None
            body_half_w = body_half_h_up = body_half_h_down = 0.0

        left_extent = _outboard(ic.reference, "left")
        right_extent = _outboard(ic.reference, "right")
        top_extent = _outboard(ic.reference, "top")
        # Total upward reach above anchor = max pin Y above anchor +
        # TOP cluster outboard reach + cap body half + safety pad.
        top_pin_above = top_reach_by_owner.get(ic.reference, 0.0)
        top_chain_reach_above_anchor = (
            top_pin_above + top_extent if top_extent > 0 else 0.0
        )

        anchor_x = snap_to_grid(
            INTERIOR_MARGIN_MM + left_extent + body_half_w
        )
        max_anchor_x = paper_w - INTERIOR_MARGIN_MM - right_extent - body_half_w
        if anchor_x > max_anchor_x:
            raise RuntimeError(
                f"plan_anchors: IC {ic.reference} ({ic.lib_id}): the "
                f"LEFT lane stack ({left_extent:.1f} mm) + body width "
                f"({2*body_half_w:.1f} mm) + RIGHT lane stack "
                f"({right_extent:.1f} mm) + 2*margin "
                f"({2*INTERIOR_MARGIN_MM:.1f} mm) exceed page width "
                f"({paper_w:.1f} mm). Upstream fix (try in priority order):\n"
                f"  1. Move some declared external_nets to a single "
                f"sheet edge so only one side carries lane width.\n"
                f"  2. Move {ic.reference} to a separate block.\n"
                f"  3. Increase paper_size from {block.paper_size!r}."
            )

        if index == 0:
            # Anchor must clear: (a) the IC body's own top half, and
            # (b) any TOP-side cluster cap chain reaching above the
            # body. Take the larger to leave room for both cases.
            need_above_body = max(body_half_h_up, top_chain_reach_above_anchor)
            anchor_y = snap_to_grid(
                INTERIOR_MARGIN_MM + need_above_body
            )
        else:
            # For stacked ICs, the bottom of the previous IC plus the
            # cap-chain clearance must be below the top of this IC's
            # body / cap chain. Use whichever is larger.
            need_above_body = max(body_half_h_up, top_chain_reach_above_anchor)
            anchor_y = snap_to_grid(
                ic_y_cursor + prev_ic_half_down
                + _IC_CAP_CHAIN_CLEARANCE_MM + need_above_body
            )

        anchor = Point(anchor_x, anchor_y)
        if body is not None:
            body_bbox_page = _shift_symbol_bbox_to_page(body, anchor)
        else:
            from zynq_eda.core.layout.bbox import placeholder_symbol_bbox
            body_bbox_page = placeholder_symbol_bbox(
                anchor, owner_id="planner:body",
            )

        anchors.append(AnchorPlan(
            owner_ref=ic.reference,
            owner_kind="ic",
            anchor=anchor,
            rotation=0.0,
            body_bbox_page=body_bbox_page,
        ))
        ic_y_cursor = anchor_y
        prev_ic_half_down = body_half_h_down

    # --- Connectors: own column on declared edge -----------------------------
    # Group connectors by edge so each edge has its own Y cursor.
    connectors_by_edge: dict[SheetEdge, list[ConnectorInstance]] = {
        SheetEdge.LEFT: [], SheetEdge.RIGHT: [],
    }
    for connector in block.connectors:
        connectors_by_edge.setdefault(connector.edge, []).append(connector)

    # Compute max OUTBOARD-text extension per (owner_ref, edge) — the
    # text bbox of a hier-label extends OUTBOARD past lane.x_end (for
    # RIGHT) or lane.x_start (for LEFT) by ~text_width mm; the
    # connector anchor must be inset enough to leave room for this
    # additional text reach beyond the lane's outboard edge.
    text_overflow_by_owner_edge: dict[tuple[str, PageSide], float] = {}
    for stack in edge_stacks:
        if stack.owner_ref == block.name:
            continue
        for row in stack.rows:
            for lane in row:
                if lane.lane_kind not in ("hier_label", "local_label"):
                    continue
                # label_text_extent_mm encodes the full lane width
                # (HLABEL_ANCHOR_OFFSET + text_width + 2*VISUAL_CLEARANCE);
                # the actual text extension past x_end is text_width
                # which we approximate as lane.label_text_extent_mm.
                key = (stack.owner_ref, stack.edge)
                existing = text_overflow_by_owner_edge.get(key, 0.0)
                text_overflow_by_owner_edge[key] = max(
                    existing, lane.label_text_extent_mm,
                )

    for edge_enum, connectors in connectors_by_edge.items():
        if not connectors:
            continue
        edge_side: PageSide = (
            "left" if edge_enum == SheetEdge.LEFT else "right"
        )
        y_cursor = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
        for connector in connectors:
            try:
                body = geometry.bounding_box(
                    connector.lib_id, rotation=connector.rotation,
                )
                body_half_w = body.width / 2.0
                body_half_h_up = abs(body.min_y)
                body_half_h_down = abs(body.max_y)
            except Exception:
                body = None
                body_half_w = body_half_h_up = body_half_h_down = 0.0

            outboard = _outboard(connector.reference, edge_side)
            # Text past lane.x_end (RIGHT) / lane.x_start (LEFT) on the
            # OUTBOARD edge — needed because the hier-label TEXT extends
            # OUTBOARD past the lane's outboard edge by ~text_width.
            edge_text_overflow = text_overflow_by_owner_edge.get(
                (connector.reference, edge_side), 0.0
            )
            if edge_side == "left":
                anchor_x = snap_to_grid(
                    INTERIOR_MARGIN_MM + outboard
                    + edge_text_overflow + body_half_w
                )
            else:
                anchor_x = snap_to_grid(
                    paper_w - INTERIOR_MARGIN_MM - outboard
                    - edge_text_overflow - body_half_w
                )

            anchor_y = snap_to_grid(y_cursor + body_half_h_up)
            anchor = Point(anchor_x, anchor_y)
            if body is not None:
                body_bbox_page = _shift_symbol_bbox_to_page(body, anchor)
            else:
                from zynq_eda.core.layout.bbox import placeholder_symbol_bbox
                body_bbox_page = placeholder_symbol_bbox(
                    anchor, owner_id="planner:body",
                )
            anchors.append(AnchorPlan(
                owner_ref=connector.reference,
                owner_kind="connector",
                anchor=anchor,
                rotation=connector.rotation,
                body_bbox_page=body_bbox_page,
            ))
            y_cursor = snap_to_grid(
                anchor_y + body_half_h_down + 20.32
            )

    return tuple(anchors)


# ---------------------------------------------------------------------------
# Phase 5 — plan_realize_lanes: convert anchor-relative → page-coord
# ---------------------------------------------------------------------------


def plan_realize_lanes(
    edge_stacks: tuple[EdgeStack, ...],
    anchors: tuple[AnchorPlan, ...],
    block: Block,
) -> tuple[LaneAllocation, ...]:
    """Phase 5 — realize every lane in page coordinates.

    For each lane in each edge stack, compute the page-coord ``x_start``,
    ``x_end``, ``y_band_lo``, ``y_band_hi``, ``label_anchor``, and
    ``cluster_trunk_end_x`` fields. After this phase every lane is
    fully determined and ready for Phase 6/7/8 to emit primitives.

    Block-owned (PWR_FLAG) lanes are realized using the page edge as
    their x_end and a placeholder ``label_anchor`` of None (Phase 6
    will compute the final position once the local labels they
    anchor on are placed).
    """
    from zynq_eda.core.layout._constants import (
        HLABEL_ANCHOR_OFFSET_MM,
        INTERIOR_MARGIN_MM,
        LANE_ROW_PITCH_MM,
        PASSIVE_OFFSET_MM,
        PASSIVE_PITCH_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM

    paper_w, _ = PAPER_DIMENSIONS_MM[block.paper_size]
    anchor_by_ref = {a.owner_ref: a for a in anchors}

    realized: list[LaneAllocation] = []

    for stack in edge_stacks:
        # Block-owned PWR_FLAG stacks: synthetic — they sit at page edge.
        if stack.owner_ref == block.name:
            for row in stack.rows:
                for lane in row:
                    if stack.edge == "left":
                        x_end = snap_to_grid(INTERIOR_MARGIN_MM)
                        x_start = snap_to_grid(x_end - lane.width_mm)
                    else:
                        x_end = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)
                        x_start = snap_to_grid(x_end - lane.width_mm)
                    realized.append(LaneAllocation(
                        owner_ref=lane.owner_ref,
                        pin_name=lane.pin_name,
                        pin_number=lane.pin_number,
                        edge=lane.edge,
                        row_index=lane.row_index,
                        x_start=x_start,
                        x_end=x_end,
                        y_band_lo=0.0,
                        y_band_hi=0.0,
                        lane_kind=lane.lane_kind,
                        cluster_trunk_end_x=None,
                        label_anchor=None,
                        label_rotation=0.0 if stack.edge == "right" else 180.0,
                        label_text_extent_mm=lane.label_text_extent_mm,
                    ))
            continue

        try:
            owner_anchor = anchor_by_ref[stack.owner_ref]
        except KeyError as exc:
            raise RuntimeError(
                f"plan_realize_lanes: edge stack for owner "
                f"{stack.owner_ref!r} has no AnchorPlan — Phase 4 "
                f"(plan_anchors) didn't place it."
            ) from exc

        anchor_x = owner_anchor.anchor.x
        anchor_y = owner_anchor.anchor.y

        for row in stack.rows:
            row_outboard_offset = row[0].row_index * LANE_ROW_PITCH_MM
            for lane in row:
                # Compute pin tip Y in page coords. PinSpec.pin_relative
                # is in symbol-local coords (+Y up); on-page Y is
                # anchor_y - pin_relative.y (Y-flip).
                # Here we use lane.y_band_lo which was set from
                # pin_relative.y in Phase 2.
                pin_page_y = snap_to_grid(anchor_y - lane.y_band_lo)

                if stack.edge == "left":
                    # Lanes extend LEFT from the pin tip. The pin tip's
                    # X on the page = anchor_x + pin_relative.x.
                    # For a LEFT-edge pin, pin_relative.x is negative
                    # (body to the right of pin tip). Lane sits OUTBOARD,
                    # i.e. further left.
                    # Lane width was stored in x_end (anchor-relative).
                    pin_page_x = snap_to_grid(anchor_x - owner_anchor.body_bbox_page.width / 2)
                    x_end = pin_page_x - row_outboard_offset
                    x_start = snap_to_grid(x_end - lane.width_mm)
                    label_anchor_x = snap_to_grid(x_start)
                    label_rotation = 180.0
                    trunk_end_x: float | None = None
                    if lane.lane_kind == "cluster":
                        trunk_end_x = snap_to_grid(
                            x_end - PASSIVE_OFFSET_MM
                            - 0 * PASSIVE_PITCH_MM
                        )
                elif stack.edge == "right":
                    pin_page_x = snap_to_grid(
                        anchor_x + owner_anchor.body_bbox_page.width / 2
                    )
                    x_start = snap_to_grid(pin_page_x + row_outboard_offset)
                    x_end = snap_to_grid(x_start + lane.width_mm)
                    label_anchor_x = snap_to_grid(x_end)
                    label_rotation = 0.0
                    trunk_end_x = None
                    if lane.lane_kind == "cluster":
                        trunk_end_x = snap_to_grid(
                            x_start + PASSIVE_OFFSET_MM
                        )
                else:
                    # TOP / BOTTOM — not implemented yet; treat as
                    # RIGHT-style for now (Phase 6 will refine).
                    pin_page_x = snap_to_grid(anchor_x)
                    x_start = pin_page_x
                    x_end = snap_to_grid(pin_page_x + lane.width_mm)
                    label_anchor_x = x_end
                    label_rotation = 0.0
                    trunk_end_x = None

                y_band_half = max(
                    lane.y_band_hi - lane.y_band_lo, 0.0
                ) / 2.0
                realized.append(LaneAllocation(
                    owner_ref=lane.owner_ref,
                    pin_name=lane.pin_name,
                        pin_number=lane.pin_number,
                    edge=lane.edge,
                    row_index=lane.row_index,
                    x_start=x_start,
                    x_end=x_end,
                    y_band_lo=pin_page_y - y_band_half,
                    y_band_hi=pin_page_y + y_band_half,
                    lane_kind=lane.lane_kind,
                    cluster_trunk_end_x=trunk_end_x,
                    label_anchor=Point(label_anchor_x, pin_page_y),
                    label_rotation=label_rotation,
                    label_text_extent_mm=lane.label_text_extent_mm,
                ))
    return tuple(realized)


# ---------------------------------------------------------------------------
# Phase 6 — plan_symbols: emit every symbol into the partial plan
# ---------------------------------------------------------------------------


def _resolve_owner(block: Block, owner_ref: str):
    """Return the IC or connector matching ``owner_ref``, or None."""
    for ic in block.ics:
        if ic.reference == owner_ref:
            return ic
    for conn in block.connectors:
        if conn.reference == owner_ref:
            return conn
    return None


def _plan_register_symbol(
    plan: LayoutPlan,
    sym: PlacedSymbol,
    geometry,
) -> None:
    """Append ``sym`` to ``plan.symbols`` AND register every bbox it
    contributes (body + intrinsic pin text + property text) to
    ``plan.occupancy``.

    Mirrors :meth:`BlockLayoutBuilder.add_symbol` exactly, so the
    planner's occupancy matches what the builder will build during
    :func:`emit_plan`.
    """
    from zynq_eda.core.layout.bbox import (
        placeholder_symbol_bbox,
        symbol_bbox,
    )

    plan.symbols.append(sym)
    owner_id = f"symbol:{sym.reference}"
    try:
        body_bbox = symbol_bbox(
            lib_id=sym.lib_id,
            anchor=sym.position,
            rotation=sym.rotation,
            cache=geometry,
            owner_id=owner_id,
        )
    except Exception:
        body_bbox = placeholder_symbol_bbox(
            sym.position, owner_id=owner_id,
        )
    plan.occupancy.add(body_bbox)

    # Intrinsic pin name + number bboxes + property text bboxes.
    try:
        label_bboxes = geometry.intrinsic_pin_label_bboxes(
            sym.lib_id, sym.position,
            rotation=sym.rotation, owner_id=owner_id,
        )
        number_bboxes = geometry.intrinsic_pin_number_bboxes(
            sym.lib_id, sym.position,
            rotation=sym.rotation, owner_id=owner_id,
        )
        property_bboxes = geometry.property_text_bboxes(
            sym.lib_id, sym.position,
            rotation=sym.rotation, owner_id=owner_id,
            reference_override=sym.reference,
            value_override=sym.value,
            value_shift=sym.value_shift,
        )
    except Exception:
        return
    for b in label_bboxes:
        plan.occupancy.add(b)
    for b in number_bboxes:
        plan.occupancy.add(b)
    for b in property_bboxes:
        # Skip property bboxes for hidden Value / Reference text. The
        # emitter writes (hide yes) for those properties so they don't
        # render and don't participate in overlap checks.
        oid = b.owner_id
        if sym.value_hidden and oid.endswith(":property:Value"):
            continue
        if sym.reference_hidden and oid.endswith(":property:Reference"):
            continue
        plan.occupancy.add(b)


def _assert_no_body_overlap(plan: LayoutPlan) -> None:
    """Assert no two body bboxes overlap significantly in the plan.

    Hard-fails with a planner-bug diagnostic if any pair does. Lane
    reservation in Phases 2-4 should make this impossible; this assert
    catches regressions.
    """
    from zynq_eda.core.layout._constants import OVERLAP_NOISE_FLOOR_MM
    # Compare only the top-level body bboxes (owner_id == 'symbol:REF'
    # with no further ':property:Reference' / ':intrinsic:...' suffix).
    # Intrinsic pin text and property text legitimately overlap their
    # own parent body and each other; the overlap check here is for
    # CROSS-SYMBOL collisions only.
    bodies = [
        b for b in plan.occupancy
        if b.kind == "symbol"
        and b.owner_id.startswith("symbol:")
        and b.owner_id.count(":") == 1  # no nested suffix
    ]
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = bodies[i], bodies[j]
            if a.owner_id == b.owner_id:
                continue
            inter = a.intersection(b)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                raise RuntimeError(
                    f"PLANNER BUG: body bbox overlap detected between "
                    f"{a.owner_id} and {b.owner_id} ({inter.width:.2f} × "
                    f"{inter.height:.2f} mm). Phase 4 anchor allocation "
                    f"failed to leave room for both bodies. Fix Phase 4."
                )


def plan_symbols(plan: LayoutPlan, block: Block, geometry) -> None:
    """Phase 6 — emit every IC and connector body into the plan.

    Subsequent versions of this function will also emit cluster
    passives, power symbols, GND symbols, and PWR_FLAGs. For PR 7
    only the body symbols are emitted; the per-pin symbols are
    deferred to subsequent PRs that build on top of this scaffold.

    Order: ICs first (in ``block.ics`` order), then connectors. Each
    symbol's bboxes are registered in :attr:`LayoutPlan.occupancy`
    via :func:`_plan_register_symbol`.

    After all bodies are emitted, asserts no body-body overlap (this
    must hold; an overlap is a planner bug from Phase 4).
    """
    for ic in block.ics:
        anchor_plan = plan.get_anchor(ic.reference)
        sym = PlacedSymbol(
            lib_id=ic.lib_id,
            reference=ic.reference,
            value=ic.refcircuit.part_mpn,
            position=anchor_plan.anchor,
            footprint=ic.refcircuit.footprint,
            rotation=anchor_plan.rotation,
            properties=(
                ("LCSC", ic.refcircuit.lcsc),
                ("Datasheet", ic.refcircuit.datasheet_url),
            ),
        )
        _plan_register_symbol(plan, sym, geometry)

    for connector in block.connectors:
        anchor_plan = plan.get_anchor(connector.reference)
        sym = PlacedSymbol(
            lib_id=connector.lib_id,
            reference=connector.reference,
            value=connector.refcircuit.part_mpn,
            position=anchor_plan.anchor,
            footprint=connector.refcircuit.footprint,
            rotation=anchor_plan.rotation,
            properties=(
                ("LCSC", connector.refcircuit.lcsc),
                ("Datasheet", connector.refcircuit.datasheet_url),
            ),
        )
        _plan_register_symbol(plan, sym, geometry)

    _assert_no_body_overlap(plan)

    # Per-pin symbols (non-cluster): NCs, power symbols, GND symbols.
    _emit_nc_pins(plan, block, geometry)
    _emit_power_symbol_pins(plan, block, geometry)
    _emit_gnd_symbols(plan, block, geometry)

    # Cluster passives + their far-end power symbols / labels.
    # Shared reference counters used across all per-pin symbol emitters.
    next_ref_counters: dict = {}
    _emit_cluster_pins(plan, block, geometry, next_ref_counters)
    # Two-pass Reference-shift refinement: after all caps are placed
    # with default Reference positions, scan for Reference vs other
    # primitive overlaps and re-pick reference_shift for the
    # conflicting cluster passives only.
    _refine_cluster_reference_shifts(plan, geometry)
    # Value-shift refinement (J.2): after all caps + power symbols are
    # placed with greedy value_shift picks, scan for Value text bbox
    # conflicts and re-pick value_shift against the FULL occupancy.
    # The per-symbol picker checks each candidate against the cap's own
    # body AND the full occupancy, so cascading conflicts are detected.
    _refine_cluster_value_shifts(plan, geometry)
    # Store on plan for later phases (PWR_FLAG emission) to reuse.
    plan._ref_counters = next_ref_counters


def _resolve_pin_page_coord(
    plan: LayoutPlan, spec: PinSpec, geometry,
) -> Point | None:
    """Look up a pin's PAGE-coord wire-attachment point via the geometry
    cache and the owner's anchor.

    Returns ``None`` when the geometry cache can't resolve the pin
    (caller skips the emission). This is the ONLY place we still allow
    a silent skip — for unresolved geometry — because the pin physically
    doesn't exist on the symbol; the audit pass surfaces that mismatch
    upstream of the planner.
    """
    try:
        anchor_plan = plan.get_anchor(spec.owner_ref)
    except KeyError:
        return None
    try:
        pin_geom = geometry.pin_geometry_by_name(
            spec.owner_lib_id, anchor_plan.anchor, spec.pin_number,
            rotation=anchor_plan.rotation,
        )
    except KeyError:
        return None
    return pin_geom.connection


def _emit_nc_pins(plan: LayoutPlan, block: Block, geometry) -> None:
    """Emit a NoConnect marker for every NC-role PinSpec.

    Pre-filter: build a list of (spec, page_position) tuples upfront
    via a list comprehension, dedup by coordinate, then iterate. No
    in-loop continue.
    """
    from zynq_eda.core.model.sheet import PlacedNoConnect

    nc_with_pos = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry))
        for spec in plan.pin_specs if spec.role == "NC"
    ]
    resolved = [
        (spec, pos) for (spec, pos) in nc_with_pos if pos is not None
    ]
    # Dedup by page coord (multiple physical pads at same XY collapse).
    unique = {
        (round(pos.x, 3), round(pos.y, 3)): pos
        for (_spec, pos) in resolved
    }
    for pos in unique.values():
        plan.no_connects.append(PlacedNoConnect(position=pos))


def _at_pin_power_rotation(
    lib_id: str, pin_side: PageSide, geometry,
) -> float:
    """Pick rotation for a power symbol placed AT the pin tip so its
    body extends LATERALLY OUTWARD (away from the IC body), not
    vertically (which would intrude into the IC body's Y band).

    For a LEFT-side IC pin: body should extend LEFTWARD (negative X
    on page). For a RIGHT-side pin: RIGHTWARD. For TOP: upward
    (off page). For BOTTOM: downward.

    Differs from ``cluster._outward_power_symbol_rotation`` which is
    designed for CLUSTER cap.far positions (where the symbol sits
    ABOVE the cap and body should extend further up, not laterally).
    """
    try:
        bbox = geometry.bounding_box(lib_id, rotation=0.0)
    except Exception:
        return 0.0
    body_center_y = (bbox.min_y + bbox.max_y) / 2.0
    is_body_down = body_center_y > 0.0
    # For a LEFT-side pin, we want body to extend LEFT.
    # Default body-down (rotation 0): body extends down (+Y on page).
    # Rotation 90 CW: body extends right.
    # Rotation 180: body extends up.
    # Rotation 270 CW: body extends left.
    if is_body_down:
        # body-down at rotation 0 (GND-style)
        return {
            "left":   270.0,  # body extends LEFT (away from IC)
            "right":  90.0,   # body extends RIGHT
            "top":    180.0,  # body extends UP (off-page top)
            "bottom": 0.0,    # body extends DOWN (off-page bottom)
        }[pin_side]
    # body-up at rotation 0 (+3V3-style)
    return {
        "left":   90.0,   # body extends LEFT
        "right":  270.0,  # body extends RIGHT
        "top":    0.0,    # body extends UP
        "bottom": 180.0,  # body extends DOWN
    }[pin_side]


def _emit_gnd_symbols(plan: LayoutPlan, block: Block, geometry) -> None:
    """Emit a ``power:GND`` symbol AT every GND-role pin tip.

    The symbol's pin coincides with the IC pin tip (KiCad treats this
    as a direct connection — no wire needed). Symbol body extends
    LATERALLY OUTWARD per ``_at_pin_power_rotation`` so it doesn't
    intrude into the IC body's Y band.

    Pre-filter strategy: build the work list upfront via a list
    comprehension. Dedup by pin tip coordinate (multi-pad GND like
    CP2102N's GND + EP at the same XY collapses to one symbol).
    """
    work_items = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry))
        for spec in plan.pin_specs if spec.role == "GND"
    ]
    placeable = [
        (spec, pos) for (spec, pos) in work_items if pos is not None
    ]
    seen_keys: set[tuple[float, float]] = set()
    next_pwr_index = 200
    for spec, pin_pos in placeable:
        key = (round(pin_pos.x, 3), round(pin_pos.y, 3))
        if key in seen_keys:
            continue  # set-membership dedup, not handler-coordination skip
        seen_keys.add(key)
        rotation = _at_pin_power_rotation(
            lib_id="power:GND", pin_side=spec.page_side, geometry=geometry,
        )
        sym = PlacedSymbol(
            lib_id="power:GND",
            reference=f"#PWR{next_pwr_index}",
            value="GND",
            position=pin_pos,
            footprint="",
            rotation=rotation,
        )
        next_pwr_index += 1
        _plan_register_symbol(plan, sym, geometry)


def _emit_power_symbol_pins(plan: LayoutPlan, block: Block, geometry) -> None:
    """Emit a power symbol AT the pin tip for every POWER_SYMBOL-role
    PinSpec.

    Pre-filter strategy: build the work list upfront via a list
    comprehension that includes only resolvable pins with a known
    POWER_SYMBOL_LIB_IDS entry. Iterate the pre-filtered list with
    no in-loop continue.
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS
    from zynq_eda.core.layout.cluster import _outward_power_symbol_rotation

    work_items = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry),
         POWER_SYMBOL_LIB_IDS.get(spec.net_name))
        for spec in plan.pin_specs if spec.role == "POWER_SYMBOL"
    ]
    placeable = [
        (spec, pos, lib_id) for (spec, pos, lib_id) in work_items
        if pos is not None and lib_id is not None
    ]
    next_pwr_index = 100
    for spec, pin_pos, lib_id in placeable:
        rotation = _at_pin_power_rotation(
            lib_id=lib_id, pin_side=spec.page_side, geometry=geometry,
        )
        sym = PlacedSymbol(
            lib_id=lib_id,
            reference=f"#PWR{next_pwr_index}",
            value=spec.net_name,
            position=pin_pos,
            footprint="",
            rotation=rotation,
        )
        next_pwr_index += 1
        _plan_register_symbol(plan, sym, geometry)


# ---------------------------------------------------------------------------
# Cluster passive emission (Phase 6 extension)
# ---------------------------------------------------------------------------


def _adjacent_pin_stagger_offset(pin_pos: Point, page_side: PageSide) -> float:
    """Return an extra outboard offset (mm) for caps on alternating pin rows.

    Adjacent IC pins (2.54 mm apart on the same body side) put their
    cluster caps at the same X column for LEFT/RIGHT pins (same Y row
    for TOP/BOTTOM). The caps' bodies then sit 2.54 mm apart in Y — too
    close for the 1.27 mm cap-body + 2 mm visual clearance.

    Solution: stagger by parity. Pins whose secondary-axis coord
    (Y // PASSIVE_PITCH for LEFT/RIGHT, X // PASSIVE_PITCH for TOP/
    BOTTOM) is ODD get an extra :data:`PASSIVE_ADJACENT_PIN_STAGGER_MM`
    pushed outboard so even and odd rows live in two distinct columns.
    """
    # Stagger configuration per edge:
    #   LEFT/RIGHT: 5-way × 10.16 mm (5 buckets, max 40.64 outboard).
    #     Caps are VERTICAL (rotation 0), body Y=7.62. Adjacent pins
    #     2.54 mm apart in Y are well-separated in X via stagger.
    #   TOP/BOTTOM: 3-way × 7.62 mm (3 buckets, max 15.24 lateral).
    #     Caps are HORIZONTAL (rotation 90), body X=7.62. Adjacent
    #     pins 2.54 mm apart in X need at least body-width lateral
    #     separation; 3 buckets × 7.62 gives 3 unique columns.
    PIN_PITCH_MM = 2.54
    # NOTE: Python's round() uses banker's rounding ("round half to even").
    # 140.97/2.54 == 55.5 banks to 56; 143.51/2.54 == 56.5 ALSO banks to 56,
    # giving adjacent pins the SAME bucket and therefore the same cap
    # column. Use int(... + epsilon) with a small tolerance so each .5
    # rounds UP (toward bigger int) deterministically and adjacent pins
    # at exactly .5 boundaries get distinct buckets.
    # Floating point: 143.51/2.54 may compute as 56.49999... rather than
    # 56.5; add epsilon so this rounds to 57 (matching the discrete grid)
    # and adjacent pins differ by 1 bucket.
    EPS = 0.001
    if page_side in ("left", "right"):
        bucket = int(pin_pos.y / PIN_PITCH_MM + 0.5 + EPS) % 5
        return bucket * 10.16
    bucket = int(pin_pos.x / PIN_PITCH_MM + 0.5 + EPS) % 3
    return bucket * 7.62


def _cluster_slot_position(
    pin_pos: Point,
    page_side: PageSide,
    slot_index: int,
    *,
    dense_swarm: bool = False,
    multi_slot_widen: bool = False,
) -> Point:
    """Return the page-coord anchor for slot ``slot_index`` of a cluster
    whose pin sits at ``pin_pos`` on the given page side.

    For LEFT/RIGHT pins the trunk runs horizontally; caps sit ABOVE
    the trunk (smaller page Y) by :data:`CAP_VERTICAL_OFFSET_MM`. Each
    slot's X is offset from the pin by ``PASSIVE_OFFSET + s * PITCH``.

    For TOP/BOTTOM pins the trunk runs vertically; caps sit beside the
    trunk by :data:`CAP_VERTICAL_OFFSET_MM` and each slot's Y is offset
    accordingly. (Less common; only a few blocks use TOP/BOTTOM
    clustered pins.)
    """
    from zynq_eda.core.layout._constants import (
        DENSE_HORIZONTAL_SWARM_PITCH_MM,
        PASSIVE_OFFSET_MM,
        PASSIVE_PITCH_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid

    CAP_VERTICAL_OFFSET_PLANNER_MM = 5.08
    # Pitch ladder: dense_swarm > multi_slot_widen > default
    # - dense_swarm = explicit per-refcircuit opt-in (20.32 mm)
    # - multi_slot_widen = clusters with >1 slot get 7.62 mm so
    #   adjacent caps' default Reference/Value text doesn't collide
    if dense_swarm:
        pitch = DENSE_HORIZONTAL_SWARM_PITCH_MM
    elif multi_slot_widen:
        pitch = 7.62
    else:
        pitch = PASSIVE_PITCH_MM

    stagger = _adjacent_pin_stagger_offset(pin_pos, page_side)
    # For ALL sides: stagger adds to the OUTBOARD distance from pin
    # along the cluster's trunk axis. This places adjacent pins'
    # caps at DIFFERENT row distances from the pin, separating their
    # bodies even when the pin pitch is tight.
    #   LEFT/RIGHT: outboard direction is X.
    #   TOP/BOTTOM: outboard direction is Y.
    outboard = PASSIVE_OFFSET_MM + slot_index * PASSIVE_PITCH_MM + stagger
    if page_side == "left":
        return Point(
            snap_to_grid(pin_pos.x - outboard),
            snap_to_grid(pin_pos.y - CAP_VERTICAL_OFFSET_PLANNER_MM),
        )
    if page_side == "right":
        return Point(
            snap_to_grid(pin_pos.x + outboard),
            snap_to_grid(pin_pos.y - CAP_VERTICAL_OFFSET_PLANNER_MM),
        )
    if page_side == "top":
        return Point(
            snap_to_grid(pin_pos.x + CAP_VERTICAL_OFFSET_PLANNER_MM),
            snap_to_grid(pin_pos.y - outboard),
        )
    # bottom
    return Point(
        snap_to_grid(pin_pos.x + CAP_VERTICAL_OFFSET_PLANNER_MM),
        snap_to_grid(pin_pos.y + outboard),
    )


def _cluster_passive_rotation(page_side: PageSide) -> float:
    """Cap rotation so its pins lie along the perpendicular of the trunk.

    For LEFT/RIGHT trunks (horizontal): cap is vertical (rotation 0).
    For TOP/BOTTOM trunks (vertical): cap is horizontal (rotation 90).
    """
    return 0.0 if page_side in ("left", "right") else 90.0


def _cluster_passive_near_far(
    slot_pos: Point,
    page_side: PageSide,
) -> tuple[Point, Point]:
    """Return the cap's (near, far) pin positions in page coords."""
    from zynq_eda.core.layout._constants import PASSIVE_PIN_HALF
    from zynq_eda.core.model.grid import snap_to_grid

    if page_side in ("left", "right"):
        # Vertical cap above horizontal trunk: near is bottom pin
        # (closer to trunk), far is top pin (further from trunk).
        near = Point(slot_pos.x, snap_to_grid(slot_pos.y + PASSIVE_PIN_HALF))
        far = Point(slot_pos.x, snap_to_grid(slot_pos.y - PASSIVE_PIN_HALF))
        return near, far
    # TOP/BOTTOM trunks: cap is horizontal beside the trunk.
    if page_side == "top":
        near = Point(snap_to_grid(slot_pos.x - PASSIVE_PIN_HALF), slot_pos.y)
        far = Point(snap_to_grid(slot_pos.x + PASSIVE_PIN_HALF), slot_pos.y)
        return near, far
    # bottom
    near = Point(snap_to_grid(slot_pos.x - PASSIVE_PIN_HALF), slot_pos.y)
    far = Point(snap_to_grid(slot_pos.x + PASSIVE_PIN_HALF), slot_pos.y)
    return near, far


def _power_symbol_for_destination(
    destination_net: str,
) -> str | None:
    """Return the power symbol lib_id for ``destination_net``, or None
    if the destination isn't a power rail."""
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS
    return POWER_SYMBOL_LIB_IDS.get(destination_net)


def _try_emit_cluster_share_wire(
    plan: LayoutPlan,
    from_cap_far: Point,
    to_cap_far: Point,
    page_side: PageSide,
) -> bool:
    """Try to emit a 3-segment Z-bend share-wire from ``from_cap_far``
    to ``to_cap_far`` for a cluster sub-slot.

    Routes UP-OVER-DOWN (smaller Y for LEFT/RIGHT pin sides, larger X
    for TOP/BOTTOM) so the horizontal/vertical middle leg doesn't run
    along the cap-far Y/X where other slot caps' body edges sit.

    The middle leg uses one KICAD_GRID_MM step away from cap.far Y/X.
    Each segment is collision-checked against the plan's current
    occupancy; if ANY segment conflicts, the whole share-wire is
    skipped (and the sub-slot's cap.far pin remains floating from
    KiCad ERC's perspective). The validator's overlap mandate takes
    priority over ERC connectivity.

    Returns True iff the share-wire was emitted.
    """
    from zynq_eda.core.layout._constants import KICAD_GRID_MM
    from zynq_eda.core.layout.bbox import wire_bbox
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import PlacedWire

    # The share-wire is a single direct segment at the shared axis:
    # SAME Y for LEFT/RIGHT clusters (horizontal wire) or SAME X for
    # TOP/BOTTOM (vertical). The wire skims the top/bottom edges of
    # the intervening cap bodies. For LEFT/RIGHT it also skims the
    # bottom edge of slot 0's power-symbol body — fine, intersection
    # is one wire thickness (~0.127 mm), below the validator's
    # 0.15 mm noise floor. For TOP/BOTTOM the vertical wire runs
    # THROUGH slot 0's power-symbol body (the body sits along the X
    # axis the wire travels), so we skip those clusters.
    if page_side in ("left", "right"):
        # LEFT/RIGHT: direct horizontal wire at common Y.
        if abs(from_cap_far.y - to_cap_far.y) > 1e-6:
            return False
        seg1 = PlacedWire(start=from_cap_far, end=to_cap_far)
        segs = (seg1,)
    else:
        # TOP/BOTTOM: cap.fars share X but differ in Y. A direct
        # vertical wire at the shared X would cut through slot 0's
        # power-symbol body (which lives along that X axis). Route a
        # sideways Z-bend: hop horizontally to the OUTBOARD direction
        # by 3 grid steps (clears typical power-symbol body width
        # ~5 mm), run vertical at that X, hop back. The horizontal
        # hop is at cap.far Y where it skims the cap body's edge —
        # below the noise floor.
        if abs(from_cap_far.x - to_cap_far.x) > 1e-6:
            return False
        # Outboard direction in X: for TOP/BOTTOM, "outboard" is
        # the direction the cap.far horizontal pin points (positive
        # X — see _cluster_passive_near_far). Use +3*GRID = 7.62 mm.
        SIDE_HOP_MM = 3 * KICAD_GRID_MM
        hop_x = snap_to_grid(from_cap_far.x + SIDE_HOP_MM)
        seg1 = PlacedWire(start=from_cap_far, end=Point(hop_x, from_cap_far.y))
        seg2 = PlacedWire(start=seg1.end, end=Point(hop_x, to_cap_far.y))
        seg3 = PlacedWire(start=seg2.end, end=to_cap_far)
        segs = (seg1, seg2, seg3)
    # Identify owners at the two endpoints: these are LEGITIMATE
    # termination points for this wire, not obstacles. We exempt:
    #   - Any cap symbol whose body contains the endpoint (cap.far IS
    #     one of the cap's pin tips).
    #   - The power symbol / local label placed at slot 0's cap.far
    #     anchor.
    # For each owner, we also exempt its property-text owner_ids so
    # the body bbox + Value + Reference text don't block.
    from zynq_eda.core.layout._constants import PASSIVE_PIN_HALF
    EPS = 0.05
    exempt_owners: set[str] = set()

    def _exempt_symbol(ref: str) -> None:
        exempt_owners.add(f"symbol:{ref}")
        exempt_owners.add(f"symbol:{ref}:property:Value")
        exempt_owners.add(f"symbol:{ref}:property:Reference")

    for endpoint in (from_cap_far, to_cap_far):
        for sym in plan.symbols:
            # Power symbol / local-label proxy / GND symbol placed
            # AT cap.far has position == endpoint.
            if (abs(sym.position.x - endpoint.x) < EPS
                    and abs(sym.position.y - endpoint.y) < EPS):
                _exempt_symbol(sym.reference)
                continue
            # Vertical cap: pins offset by ±PASSIVE_PIN_HALF in Y.
            # Horizontal cap: pins offset by ±PASSIVE_PIN_HALF in X.
            if int(sym.rotation) % 180 == 0:
                # Vertical: same X, Y offset.
                if (abs(sym.position.x - endpoint.x) < EPS
                        and (abs(sym.position.y - PASSIVE_PIN_HALF - endpoint.y) < EPS
                             or abs(sym.position.y + PASSIVE_PIN_HALF - endpoint.y) < EPS)):
                    _exempt_symbol(sym.reference)
            else:
                # Horizontal: same Y, X offset.
                if (abs(sym.position.y - endpoint.y) < EPS
                        and (abs(sym.position.x - PASSIVE_PIN_HALF - endpoint.x) < EPS
                             or abs(sym.position.x + PASSIVE_PIN_HALF - endpoint.x) < EPS)):
                    _exempt_symbol(sym.reference)
        for lab in plan.labels:
            if (abs(lab.position.x - endpoint.x) < EPS
                    and abs(lab.position.y - endpoint.y) < EPS):
                exempt_owners.add(
                    f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
                )

    # Probe every segment against current occupancy. If any segment's
    # bbox would collide with a NON-wire primitive (symbol bodies,
    # labels, intrinsic text) NOT exempted as an endpoint terminator,
    # abort — emitting would break the overlap mandate.
    EXEMPT_KINDS = frozenset({"junction", "no_connect", "wire"})
    for seg in segs:
        if seg.start == seg.end:
            continue
        bb = wire_bbox(seg.start, seg.end, owner_id="share_probe")
        hits = plan.occupancy.collides(
            bb, ignore_kinds=EXEMPT_KINDS, ignore_owners=exempt_owners,
        )
        if hits:
            return False

    # Clean — emit all three segments.
    emitted = False
    for seg in segs:
        if seg.start == seg.end:
            continue
        if _add_wire_with_bbox(plan, seg):
            emitted = True
    return emitted


def _refine_cluster_value_shifts(
    plan: LayoutPlan, geometry, *, consider_wires: bool = False,
) -> None:
    """Two-pass refinement: detect cluster-passive Value text bbox
    overlaps; re-pick value_shift for the conflicting symbols.

    Mirror of :func:`_refine_cluster_reference_shifts` for Value text.
    After all cluster caps are emitted with their initial (greedy)
    value_shift picks, scan plan.occupancy for ``property:Value`` text
    bbox overlaps. For each conflict, temporarily remove the Value
    bbox from occupancy, call :func:`pick_dynamic_value_shift` to find
    a clean shift against the FULL final occupancy, and replace the
    PlacedSymbol via ``dataclasses.replace``.

    Pure-functional retry — if no candidate fits, the symbol's Value
    stays at the original shift and the validator surfaces it.
    """
    from zynq_eda.core.layout.geometry import (
        pick_dynamic_value_shift,
        VALUE_SHIFT_BY_LIB_ID,
    )
    from zynq_eda.core.layout._constants import OVERLAP_NOISE_FLOOR_MM

    sym_by_ref = {s.reference: s for s in plan.symbols}

    val_bboxes_by_owner: dict[str, "BBox"] = {}
    for b in plan.occupancy:
        oid = b.owner_id
        if oid.endswith(":property:Value") and oid.startswith("symbol:"):
            val_bboxes_by_owner[oid] = b

    def _conflict_count(val_bbox) -> int:
        cnt = 0
        for other in plan.occupancy:
            if other.owner_id == val_bbox.owner_id:
                continue
            inter = val_bbox.intersection(other)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                cnt += 1
        return cnt

    for owner_id, val_bbox in list(val_bboxes_by_owner.items()):
        ref = owner_id[len("symbol:"):-len(":property:Value")]
        sym = sym_by_ref.get(ref)
        if sym is None or sym.lib_id not in VALUE_SHIFT_BY_LIB_ID:
            continue
        if _conflict_count(val_bbox) == 0:
            continue
        plan.occupancy.remove_by_owner(owner_id)
        new_shift = pick_dynamic_value_shift(
            lib_id=sym.lib_id,
            anchor=sym.position,
            symbol_rotation=sym.rotation,
            occupancy=plan.occupancy,
            geometry_cache=geometry,
            owner_id=owner_id.rsplit(":property:", 1)[0],
            value_text=sym.value,
            consider_wires=consider_wires,
        )
        if new_shift is None and consider_wires:
            # Tight cluster region — retry with reduced clearance gate.
            # The default 2 mm clearance rejects near-misses; for dense
            # clusters where every candidate has a near-miss, accept any
            # candidate whose actual bbox doesn't strictly overlap an
            # existing primitive.
            new_shift = pick_dynamic_value_shift(
                lib_id=sym.lib_id,
                anchor=sym.position,
                symbol_rotation=sym.rotation,
                occupancy=plan.occupancy,
                geometry_cache=geometry,
                owner_id=owner_id.rsplit(":property:", 1)[0],
                value_text=sym.value,
                consider_wires=consider_wires,
                padding_mm=0.0,
            )
        if new_shift is None:
            plan.occupancy.add(val_bbox)
            continue
        from dataclasses import replace as _replace
        new_sym = _replace(sym, value_shift=new_shift)
        sym_by_ref[ref] = new_sym
        idx = plan.symbols.index(sym)
        plan.symbols[idx] = new_sym
        new_bboxes = geometry.property_text_bboxes(
            sym.lib_id, sym.position,
            rotation=sym.rotation,
            owner_id=f"symbol:{sym.reference}",
            reference_override=sym.reference,
            value_override=sym.value,
            value_shift=new_shift,
            reference_shift=sym.reference_shift,
        )
        for b in new_bboxes:
            if b.owner_id == owner_id:
                plan.occupancy.add(b)
                break


def _refine_cluster_reference_shifts(
    plan: LayoutPlan, geometry, *, consider_wires: bool = False,
) -> None:
    """Two-pass refinement: detect cluster-passive Reference text bbox
    overlaps; re-pick reference_shift for the conflicting symbols.

    After ``_emit_cluster_pins`` lays down all caps with their lib-
    default Reference position, this pass scans the plan's occupancy
    for ``property:Reference`` text overlaps. For each conflicting
    Reference, it calls :func:`pick_dynamic_reference_shift` to find
    a clean shift, replaces the PlacedSymbol with one carrying the
    new shift, and updates the occupancy.

    Pure-functional retry: if no shift candidate fits, the symbol's
    Reference stays at default (and the validator surfaces it for the
    user to address upstream).
    """
    from zynq_eda.core.layout.geometry import (
        pick_dynamic_reference_shift,
        VALUE_SHIFT_BY_LIB_ID,
    )
    from zynq_eda.core.layout._constants import OVERLAP_NOISE_FLOOR_MM

    # Index symbols by reference designator for quick lookup/replace.
    sym_by_ref = {s.reference: s for s in plan.symbols}

    # Walk Reference-property bboxes. Owner_id pattern is
    # "symbol:<REF>:property:Reference".
    ref_bboxes_by_owner: dict[str, "BBox"] = {}
    for b in plan.occupancy:
        oid = b.owner_id
        if oid.endswith(":property:Reference") and oid.startswith("symbol:"):
            ref_bboxes_by_owner[oid] = b

    # Build candidate refinement targets: passive caps (Device:R/C
    # family) that conflict with ANOTHER primitive at their Reference
    # bbox. Conflict = bbox intersection ≥ noise floor on both axes.
    def _conflict_count(ref_bbox) -> int:
        cnt = 0
        for other in plan.occupancy:
            if other.owner_id == ref_bbox.owner_id:
                continue
            inter = ref_bbox.intersection(other)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                cnt += 1
        return cnt

    for owner_id, ref_bbox in list(ref_bboxes_by_owner.items()):
        # Extract reference designator from owner_id.
        ref = owner_id[len("symbol:"):-len(":property:Reference")]
        sym = sym_by_ref.get(ref)
        if sym is None or sym.lib_id not in VALUE_SHIFT_BY_LIB_ID:
            continue
        if _conflict_count(ref_bbox) == 0:
            continue  # already clean
        # Try to pick a clean reference_shift.
        # Strategy: temporarily remove the conflicting Reference's bbox
        # from occupancy so the picker sees a clean slate (otherwise
        # the picker would think every candidate "conflicts" with the
        # current Reference).
        plan.occupancy.remove_by_owner(owner_id)
        new_shift = pick_dynamic_reference_shift(
            lib_id=sym.lib_id,
            anchor=sym.position,
            symbol_rotation=sym.rotation,
            occupancy=plan.occupancy,
            geometry_cache=geometry,
            owner_id=owner_id.rsplit(":property:", 1)[0],
            reference_text=sym.reference,
            consider_wires=consider_wires,
        )
        if new_shift is None and consider_wires:
            # Tight cluster: relax clearance gate.
            new_shift = pick_dynamic_reference_shift(
                lib_id=sym.lib_id,
                anchor=sym.position,
                symbol_rotation=sym.rotation,
                occupancy=plan.occupancy,
                geometry_cache=geometry,
                owner_id=owner_id.rsplit(":property:", 1)[0],
                reference_text=sym.reference,
                consider_wires=consider_wires,
                padding_mm=0.0,
            )
        if new_shift is None:
            # No clean candidate — re-add the original bbox; leave the
            # symbol with default Reference and let validator surface.
            plan.occupancy.add(ref_bbox)
            continue
        # Replace the PlacedSymbol with one carrying the new shift.
        from dataclasses import replace as _replace
        new_sym = _replace(sym, reference_shift=new_shift)
        sym_by_ref[ref] = new_sym
        idx = plan.symbols.index(sym)
        plan.symbols[idx] = new_sym
        # Re-register the Reference bbox at the shifted position.
        new_bboxes = geometry.property_text_bboxes(
            sym.lib_id, sym.position,
            rotation=sym.rotation,
            owner_id=f"symbol:{sym.reference}",
            reference_override=sym.reference,
            value_override=sym.value,
            value_shift=sym.value_shift,
            reference_shift=new_shift,
        )
        for b in new_bboxes:
            if b.owner_id == owner_id:
                plan.occupancy.add(b)
                break


def _emit_cluster_pins(
    plan: LayoutPlan, block: Block, geometry,
    next_ref_counters: dict,
) -> None:
    """Emit cluster passives + far-end power symbols / local labels for
    every CLUSTER PinSpec.

    For each slot:
      - Place a passive symbol at the slot's reserved position.
      - Compute cap near/far pin positions.
      - If the slot's destination is a power rail: emit a power symbol
        outboard of the cap.far position; the cap→symbol wire is routed
        in Phase 7.
      - Otherwise: emit a local label at cap.far naming the destination.

    The cluster TRUNK and per-slot DROP wires are emitted in Phase 7
    (plan_routes). This function only emits SYMBOLS and LABELS so the
    plan's occupancy index is populated before routing.
    """
    from zynq_eda.core.layout._constants import (
        POWER_SYMBOL_OFFSET_MM,
        PASSIVE_PIN_HALF,
    )
    from zynq_eda.core.layout.cluster import (
        _outward_power_symbol_rotation,
        passive_footprint,
        passive_lib_id,
        passive_ref_prefix,
        passive_value,
    )
    from zynq_eda.core.model.grid import snap_to_grid

    # Build cluster specs, resolving pin positions upfront.
    cluster_specs = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry))
        for spec in plan.pin_specs if spec.role == "CLUSTER"
    ]
    placeable = [
        (spec, pin_pos) for (spec, pin_pos) in cluster_specs
        if pin_pos is not None
    ]

    # Iterate cluster pins, emit per-slot symbols + far endpoints.
    for spec, pin_pos in placeable:
        # Look up the owner's IcInstance/ConnectorInstance to find the
        # part_token for each slot.
        owner = _resolve_owner(block, spec.owner_ref)
        if owner is None:
            continue
        dense_swarm = bool(getattr(owner.refcircuit, "dense_swarm", False))
        part_tokens_for_pin = [
            ep.part_token for ep in owner.refcircuit.external_parts
            if ep.from_pin == spec.pin_name
            for _ in range(ep.quantity)
        ]
        if len(part_tokens_for_pin) != spec.cluster_slot_count:
            # Defensive: refcircuit ordering changed underneath us.
            continue

        # Per-pin: which destinations have already received their
        # far-end label/symbol. Each unique destination gets ONE label
        # (the trunk + drops connect all slots to it electrically).
        emitted_destinations_for_pin: set[str] = set()
        # Track first slot's cap.far per destination so subsequent
        # slots can wire to it (closes ERC pin_not_connected).
        first_cap_far_by_dest_for_pin: dict[str, Point] = {}
        # Track which destinations were emitted as POWER SYMBOLS
        # (vs local labels). Share-wires only target power symbol
        # endpoints because wires can terminate at symbol pin tips
        # but not at label anchors.
        power_dest_destinations_for_pin: set[str] = set()
        multi_slot_widen = len(part_tokens_for_pin) > 1
        for slot_idx, part_token in enumerate(part_tokens_for_pin):
            slot_pos = _cluster_slot_position(
                pin_pos, spec.page_side, slot_idx,
                dense_swarm=dense_swarm,
                multi_slot_widen=multi_slot_widen,
            )
            cap_rotation = _cluster_passive_rotation(spec.page_side)
            cap_lib_id = passive_lib_id(part_token)
            cap_value = passive_value(part_token)
            cap_footprint = passive_footprint(part_token)
            ref_prefix = passive_ref_prefix(part_token)
            ref_counters_key = ref_prefix
            ref_index = next_ref_counters.setdefault(ref_counters_key, 100)
            next_ref_counters[ref_counters_key] = ref_index + 1
            cap_ref = f"{ref_prefix}{ref_index}"

            # Dynamic Value shift only. reference_shift infrastructure
            # is wired through the entire pipeline (model, geometry,
            # validator, emitter) and ready for activation, but the
            # call-site strategy needs further refinement to avoid
            # regressions. See task #62.
            from zynq_eda.core.layout.geometry import (
                pick_dynamic_value_shift,
                VALUE_SHIFT_BY_LIB_ID,
            )
            value_shift = pick_dynamic_value_shift(
                lib_id=cap_lib_id,
                anchor=slot_pos,
                symbol_rotation=cap_rotation,
                occupancy=plan.occupancy,
                geometry_cache=geometry,
                owner_id=f"symbol:{cap_ref}",
                value_text=cap_value,
            )
            reference_shift = None
            cap_sym = PlacedSymbol(
                lib_id=cap_lib_id,
                reference=cap_ref,
                value=cap_value,
                position=slot_pos,
                footprint=cap_footprint,
                rotation=cap_rotation,
                value_shift=value_shift,
                reference_shift=reference_shift,
            )
            _plan_register_symbol(plan, cap_sym, geometry)

            # Far endpoint: power symbol OR label, depending on
            # whether the destination is a power rail.
            _, cap_far = _cluster_passive_near_far(slot_pos, spec.page_side)
            destination_net = spec.cluster_destinations[slot_idx]
            # Set-dedup: emit far endpoint only once per (pin, destination).
            # Multiple slots going to the same net share one symbol/label
            # at slot 0; subsequent slots OPTIONALLY get a share-wire
            # to that slot 0 endpoint when slot 0 has a POWER SYMBOL
            # (wires legitimately terminate at symbol pin tips) AND
            # the wire's path is clear of bodies. Label terminators
            # are excluded — KiCad's strict wire×label rule
            # (perpendicular offset only) blocks wires ending at label
            # anchors.
            if destination_net in emitted_destinations_for_pin:
                first_cap_far = first_cap_far_by_dest_for_pin.get(destination_net)
                slot0_is_power = destination_net in power_dest_destinations_for_pin
                emitted = False
                if (first_cap_far is not None
                        and first_cap_far != cap_far
                        and slot0_is_power):
                    emitted = _try_emit_cluster_share_wire(
                        plan, cap_far, first_cap_far, spec.page_side,
                    )
                if not emitted and slot0_is_power:
                    # Fallback for power destinations only: emit a
                    # DUPLICATE power symbol at this slot's cap.far,
                    # but with Value + Reference HIDDEN so the
                    # property text doesn't compete for space with
                    # slot 0's visible symbol. KiCad merges by Value
                    # field whether hidden or not, so the sub-slot's
                    # cap.far pin is electrically on the same net.
                    # Layout-clean: body is at cap.far (cap body's
                    # edge); hidden text contributes no bbox.
                    power_lib_id_dup = _power_symbol_for_destination(destination_net)
                    if power_lib_id_dup is not None:
                        rot_dup = _outward_power_symbol_rotation(
                            lib_id=power_lib_id_dup, pin_side=spec.page_side,
                            geometry_cache=geometry,
                        )
                        pwr_ref_index_dup = next_ref_counters.setdefault("PWR", 300)
                        next_ref_counters["PWR"] = pwr_ref_index_dup + 1
                        pwr_sym_dup = PlacedSymbol(
                            lib_id=power_lib_id_dup,
                            reference=f"#PWR{pwr_ref_index_dup}",
                            value=destination_net,
                            position=cap_far,
                            footprint="",
                            rotation=rot_dup,
                            value_hidden=True,
                            reference_hidden=True,
                        )
                        # Probe: only emit if body bbox is clean.
                        from zynq_eda.core.layout.bbox import (
                            placeholder_symbol_bbox, symbol_bbox,
                        )
                        try:
                            body_bb = symbol_bbox(
                                lib_id=pwr_sym_dup.lib_id,
                                anchor=pwr_sym_dup.position,
                                rotation=pwr_sym_dup.rotation,
                                cache=geometry,
                                owner_id=f"symbol:{pwr_sym_dup.reference}",
                            )
                        except Exception:
                            body_bb = placeholder_symbol_bbox(
                                pwr_sym_dup.position,
                                owner_id=f"symbol:{pwr_sym_dup.reference}",
                            )
                        # Find owners at cap.far to exempt (the cap
                        # whose far pin is here).
                        EPS = 0.05
                        exempt: set[str] = set()
                        for s_sym in plan.symbols:
                            if (abs(s_sym.position.x - cap_far.x) < EPS
                                    and abs(s_sym.position.y - cap_far.y) < EPS):
                                exempt.add(f"symbol:{s_sym.reference}")
                                exempt.add(f"symbol:{s_sym.reference}:property:Value")
                                exempt.add(f"symbol:{s_sym.reference}:property:Reference")
                            elif int(s_sym.rotation) % 180 == 0:
                                if (abs(s_sym.position.x - cap_far.x) < EPS
                                        and (abs(s_sym.position.y - PASSIVE_PIN_HALF - cap_far.y) < EPS
                                             or abs(s_sym.position.y + PASSIVE_PIN_HALF - cap_far.y) < EPS)):
                                    exempt.add(f"symbol:{s_sym.reference}")
                                    exempt.add(f"symbol:{s_sym.reference}:property:Value")
                                    exempt.add(f"symbol:{s_sym.reference}:property:Reference")
                            else:
                                if (abs(s_sym.position.y - cap_far.y) < EPS
                                        and (abs(s_sym.position.x - PASSIVE_PIN_HALF - cap_far.x) < EPS
                                             or abs(s_sym.position.x + PASSIVE_PIN_HALF - cap_far.x) < EPS)):
                                    exempt.add(f"symbol:{s_sym.reference}")
                                    exempt.add(f"symbol:{s_sym.reference}:property:Value")
                                    exempt.add(f"symbol:{s_sym.reference}:property:Reference")
                        hits = plan.occupancy.collides(
                            body_bb,
                            ignore_kinds=frozenset({"wire", "junction", "no_connect"}),
                            ignore_owners=exempt,
                        )
                        if not hits:
                            _plan_register_symbol(plan, pwr_sym_dup, geometry)
                continue
            emitted_destinations_for_pin.add(destination_net)
            first_cap_far_by_dest_for_pin[destination_net] = cap_far
            power_lib_id = _power_symbol_for_destination(destination_net)
            if power_lib_id is not None:
                # Place the power symbol AT cap.far. KiCad merges its
                # pin with the cap's far pin, so no wire is needed.
                rotation = _outward_power_symbol_rotation(
                    lib_id=power_lib_id, pin_side=spec.page_side,
                    geometry_cache=geometry,
                )
                pwr_ref_index = next_ref_counters.setdefault("PWR", 300)
                next_ref_counters["PWR"] = pwr_ref_index + 1
                pwr_sym = PlacedSymbol(
                    lib_id=power_lib_id,
                    reference=f"#PWR{pwr_ref_index}",
                    value=destination_net,
                    position=cap_far,
                    footprint="",
                    rotation=rotation,
                )
                _plan_register_symbol(plan, pwr_sym, geometry)
                power_dest_destinations_for_pin.add(destination_net)
            else:
                # Local label at cap.far naming the destination net.
                # Set-dedup: multiple slots on the same pin going to the
                # same non-power destination share a single label.
                from zynq_eda.core.model.sheet import PlacedLabel
                label_rot = {
                    "left": 180.0, "right": 0.0,
                    "top": 90.0, "bottom": 270.0,
                }[spec.page_side]
                existing_keys = {
                    (lab.net_name,
                     round(lab.position.x, 3),
                     round(lab.position.y, 3))
                    for lab in plan.labels
                }
                key = (
                    destination_net,
                    round(cap_far.x, 3),
                    round(cap_far.y, 3),
                )
                if key not in existing_keys:
                    lbl = PlacedLabel(
                        net_name=destination_net,
                        position=cap_far,
                        rotation=label_rot,
                    )
                    _add_label_with_candidate_ladder(plan, lbl)
                    # Already tracked above for power destinations;
                    # also record for the label branch so subsequent
                    # slots can share via Z-bend (if path is clear).
                    first_cap_far_by_dest_for_pin.setdefault(
                        destination_net, cap_far,
                    )


def _route_cluster_pins(
    plan: LayoutPlan, block: Block, geometry,
) -> None:
    """Emit cluster trunk + per-slot drop + far-side wires.

    Trunk: one wire from pin tip to the OUTERMOST slot's drop X.
    Drops: per slot, a wire from trunk Y to cap.near.
    Far wires: per slot, a wire from cap.far to its power symbol /
    label (or no wire if the symbol/label sits AT cap.far).

    Junctions: emitted at trunk-drop intersections for all non-endpoint
    slots (the trunk's far endpoint coincides with the last slot's
    drop, so no junction needed there).
    """
    from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
    from zynq_eda.core.layout._constants import (
        PASSIVE_OFFSET_MM, PASSIVE_PITCH_MM, POWER_SYMBOL_OFFSET_MM,
        PASSIVE_PIN_HALF,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire

    cluster_specs = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry))
        for spec in plan.pin_specs if spec.role == "CLUSTER"
    ]
    placeable = [
        (s, pos) for (s, pos) in cluster_specs if pos is not None
    ]

    for spec, pin_pos in placeable:
        n_slots = spec.cluster_slot_count
        if n_slots <= 0:
            continue

        owner = _resolve_owner(block, spec.owner_ref)
        dense_swarm = bool(
            getattr(getattr(owner, "refcircuit", None), "dense_swarm", False)
        ) if owner is not None else False

        multi_slot_widen = n_slots > 1
        # Compute trunk endpoint = farthest slot's X.
        far_slot_pos = _cluster_slot_position(
            pin_pos, spec.page_side, n_slots - 1,
            dense_swarm=dense_swarm,
            multi_slot_widen=multi_slot_widen,
        )
        # Trunk runs at pin Y from pin tip to far slot X.
        if spec.page_side in ("left", "right"):
            trunk_far = Point(far_slot_pos.x, pin_pos.y)
        else:  # top / bottom
            trunk_far = Point(pin_pos.x, far_slot_pos.y)

        # Build avoid_owners: source IC body, source pin's intrinsic
        # number text. Initially DO NOT exempt own cap bodies — try to
        # route AROUND them. Only fall back to exempting own caps if
        # the constrained route fails.
        from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
        avoid_strict: set[str] = {f"symbol:{spec.owner_ref}"}
        if spec.pin_number:
            avoid_strict |= set(pin_intrinsic_owner_ids(
                spec.owner_ref, (spec.pin_number,),
            ))
        # Also exempt own caps' Reference/Value property text (the
        # picker / route can pass close to property text without
        # producing a real wire-symbol collision; the property text is
        # just rendered text).
        own_cap_refs: list[str] = []
        for slot_idx in range(n_slots):
            slot_pos = _cluster_slot_position(
                pin_pos, spec.page_side, slot_idx,
                dense_swarm=dense_swarm,
                multi_slot_widen=multi_slot_widen,
            )
            for sym in plan.symbols:
                if (abs(sym.position.x - slot_pos.x) < 0.1
                        and abs(sym.position.y - slot_pos.y) < 0.1):
                    own_cap_refs.append(sym.reference)
                    avoid_strict.update(
                        pin_intrinsic_owner_ids(sym.reference, ("1", "2"))
                    )
                    avoid_strict.add(
                        f"symbol:{sym.reference}:property:Reference"
                    )
                    avoid_strict.add(
                        f"symbol:{sym.reference}:property:Value"
                    )

        # Permissive avoid set (fallback) ALSO exempts own cap BODIES.
        avoid_permissive: set[str] = set(avoid_strict)
        for ref in own_cap_refs:
            avoid_permissive.add(f"symbol:{ref}")

        # Trunk wire — first try STRICT (route AROUND own caps so the
        # wire doesn't traverse cap body). If that fails, fall back to
        # the PERMISSIVE avoid set (allow crossing own caps; validator
        # will flag this but the wire connects functionally).
        from zynq_eda.core.route.router import route_orthogonal_detail
        trunk_attempt = route_orthogonal_detail(
            pin_pos, trunk_far, plan.occupancy,
            avoid_owners=frozenset(avoid_strict),
        )
        if trunk_attempt.gave_up:
            trunk_attempt = route_orthogonal_detail(
                pin_pos, trunk_far, plan.occupancy,
                avoid_owners=frozenset(avoid_permissive),
            )
        if not trunk_attempt.gave_up:
            for seg in trunk_attempt.segments:
                _add_wire_with_bbox(plan, seg)
        else:
            # Fall back to direct trunk if router can't find a path.
            # The validator surfaces the resulting overlap so it can
            # be addressed by widening PASSIVE_OFFSET or staggering.
            trunk_wire = PlacedWire(start=pin_pos, end=trunk_far)
            _add_wire_with_bbox(plan, trunk_wire)

        # Per-slot drops + far wires + junctions.
        for slot_idx in range(n_slots):
            slot_pos = _cluster_slot_position(
                pin_pos, spec.page_side, slot_idx,
                dense_swarm=dense_swarm,
                multi_slot_widen=multi_slot_widen,
            )
            cap_near, cap_far = _cluster_passive_near_far(
                slot_pos, spec.page_side,
            )
            # Drop: from trunk (at slot X, pin Y) to cap.near.
            # Direct wire — slot positions are reserved so the drop
            # path is clear by construction.
            if spec.page_side in ("left", "right"):
                drop_start = Point(slot_pos.x, pin_pos.y)
            else:
                drop_start = Point(pin_pos.x, slot_pos.y)
            drop_wire = PlacedWire(start=drop_start, end=cap_near)
            _add_wire_with_bbox(plan, drop_wire)

            # Junction at trunk-drop intersection (except at the
            # trunk's far endpoint where it naturally terminates).
            if slot_idx != n_slots - 1:
                plan.junctions.append(PlacedJunction(position=drop_start))

            # Power symbol / local label sits AT cap.far — no wire.


# ---------------------------------------------------------------------------
# PWR_FLAG emission (Phase 6 + 7 extension)
# ---------------------------------------------------------------------------


def _emit_pwr_flags(
    plan: LayoutPlan, block: Block, geometry,
    next_ref_counters: dict,
) -> None:
    """Emit PWR_FLAG symbols + wires for each block-owned PWR_FLAG lane.

    The flag anchors on the LEFTMOST/RIGHTMOST same-net local label
    that's been emitted into the plan by prior phases. The wire runs
    horizontally from the anchor label to the flag symbol at the
    page-edge lane position.
    """
    from zynq_eda.core.layout._constants import (
        FLG_BODY_EXTENT_MM,
        INTERIOR_MARGIN_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import PlacedWire

    pwr_flag_lanes = [
        l for l in plan.lane_allocations if l.lane_kind == "pwr_flag"
    ]
    # Index labels by net_name to find anchors. Hier-labels are PREFERRED
    # anchors because they sit at the lane endpoint (cleanest place to
    # attach the PWR_FLAG outboard). Fall back to local labels when no
    # hier-label exists for the net.
    hlabels_by_net: dict[str, list] = {}
    for hlab in plan.hierarchical_labels:
        hlabels_by_net.setdefault(hlab.net_name, []).append(hlab)
    locals_by_net: dict[str, list] = {}
    for lab in plan.labels:
        locals_by_net.setdefault(lab.net_name, []).append(lab)
    labels_by_net: dict[str, list] = {}
    for net in set(hlabels_by_net) | set(locals_by_net):
        # Hier-labels first (preferred). Local labels only used when
        # no hier-label exists for the net.
        labels_by_net[net] = (
            hlabels_by_net.get(net) or locals_by_net.get(net, [])
        )

    work_items = [
        (lane, lane.pin_name.split(":", 1)[1]
         if ":" in lane.pin_name else "")
        for lane in pwr_flag_lanes
    ]
    placeable = [
        (lane, net_name, labels_by_net.get(net_name, []))
        for (lane, net_name) in work_items
        if labels_by_net.get(net_name)
    ]
    for lane, net_name, anchors in placeable:
        # Pick the anchor closest to the lane's edge.
        if lane.edge == "right":
            anchor = max(anchors, key=lambda a: a.position.x)
        else:
            anchor = min(anchors, key=lambda a: a.position.x)

        # Place the PWR_FLAG on the OPPOSITE side of the anchor from
        # the anchor's text direction so the wire from anchor to flag
        # does NOT cross the anchor's text bbox.
        anchor_rotation = getattr(anchor, "rotation", 0.0)
        if anchor_rotation == 0.0:
            flag_x = snap_to_grid(
                anchor.position.x - (FLG_BODY_EXTENT_MM + 2.0)
            )
        elif anchor_rotation == 180.0:
            flag_x = snap_to_grid(
                anchor.position.x + (FLG_BODY_EXTENT_MM + 2.0)
            )
        else:
            offset = FLG_BODY_EXTENT_MM + 2.0
            if lane.edge == "right":
                flag_x = snap_to_grid(anchor.position.x + offset)
            else:
                flag_x = snap_to_grid(anchor.position.x - offset)

        # Candidate ladder: try the default position first; if its
        # predicted bbox (incl. property text) conflicts with any
        # other primitive, try X-shifts further OUTBOARD and then
        # Y-shifts away from the anchor row. Keeps the wire from
        # anchor short and horizontal whenever possible.
        from zynq_eda.core.layout._constants import KICAD_GRID_MM
        from dataclasses import replace

        # Outboard direction for X-shifts (further from connector).
        x_step_sign = -1 if anchor_rotation == 0.0 else (
            1 if anchor_rotation == 180.0 else (
                1 if lane.edge == "right" else -1
            )
        )
        candidates: list[Point] = [Point(flag_x, anchor.position.y)]
        for step in (1, 2, 3, 4, 5, 6, 7, 8):
            candidates.append(Point(
                snap_to_grid(flag_x + x_step_sign * step * KICAD_GRID_MM),
                anchor.position.y,
            ))
        # Y-shifts (DOWN preferred when anchor is near top of page).
        for y_step in (1, 2, 3, -1, -2, -3, 4, -4):
            candidates.append(Point(
                flag_x,
                snap_to_grid(anchor.position.y + y_step * KICAD_GRID_MM),
            ))
        # Combined X+Y shifts for tight cases.
        for step in (1, 2, 3, 4):
            for y_step in (1, 2, -1, -2):
                candidates.append(Point(
                    snap_to_grid(flag_x + x_step_sign * step * KICAD_GRID_MM),
                    snap_to_grid(anchor.position.y + y_step * KICAD_GRID_MM),
                ))

        chosen_pos: Point | None = None
        pwr_index_preview = next_ref_counters.get("FLG", 100)
        preview_owner_id = f"symbol:#FLG{pwr_index_preview}"
        for cand in candidates:
            preview_sym = PlacedSymbol(
                lib_id="power:PWR_FLAG",
                reference=f"#FLG{pwr_index_preview}",
                value=net_name,
                position=cand,
                footprint="",
                rotation=0.0,
            )
            preview_bboxes: list = []
            try:
                from zynq_eda.core.layout.bbox import (
                    placeholder_symbol_bbox, symbol_bbox,
                )
                try:
                    body = symbol_bbox(
                        lib_id=preview_sym.lib_id,
                        anchor=preview_sym.position,
                        rotation=preview_sym.rotation,
                        cache=geometry,
                        owner_id=preview_owner_id,
                    )
                except Exception:
                    body = placeholder_symbol_bbox(
                        preview_sym.position, owner_id=preview_owner_id,
                    )
                preview_bboxes.append(body)
                try:
                    preview_bboxes.extend(
                        geometry.property_text_bboxes(
                            preview_sym.lib_id, preview_sym.position,
                            rotation=preview_sym.rotation,
                            owner_id=preview_owner_id,
                            reference_override=preview_sym.reference,
                            value_override=preview_sym.value,
                        )
                    )
                except Exception:
                    pass
            except Exception:
                pass

            # Reject candidates that would put the flag's bbox outside
            # the page margins. The page-bounds validator uses 5.08 mm
            # (DEFAULT_MARGIN_MM); the candidate just needs to fit
            # within that, NOT the larger INTERIOR_MARGIN_MM used for
            # the body-placement region.
            from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
            from zynq_eda.core.validate.page_bounds import DEFAULT_MARGIN_MM
            paper_w_cand, paper_h_cand = PAPER_DIMENSIONS_MM[block.paper_size]
            out_of_bounds = False
            for bb in preview_bboxes:
                if (bb.min.y < DEFAULT_MARGIN_MM
                        or bb.max.y > paper_h_cand - DEFAULT_MARGIN_MM
                        or bb.min.x < DEFAULT_MARGIN_MM
                        or bb.max.x > paper_w_cand - DEFAULT_MARGIN_MM):
                    out_of_bounds = True
                    break
            if out_of_bounds:
                continue

            conflict = False
            for bb in preview_bboxes:
                # Anchor's hier-label is OK to be near the flag; that's
                # how the connection is made. Exclude it from conflicts.
                ignore_set: set[str] = set()
                ignore_set.add(preview_owner_id)
                hits = plan.occupancy.collides(
                    bb, ignore_owners=ignore_set,
                )
                for h in hits:
                    if h.owner_id == bb.owner_id:
                        continue
                    if h.owner_id.startswith(preview_owner_id):
                        continue
                    conflict = True
                    break
                if conflict:
                    break
            if not conflict:
                chosen_pos = cand
                break
        if chosen_pos is None:
            chosen_pos = Point(flag_x, anchor.position.y)

        flag_pos = chosen_pos
        pwr_index = next_ref_counters.setdefault("FLG", 100)
        next_ref_counters["FLG"] = pwr_index + 1
        flag_sym = PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=f"#FLG{pwr_index}",
            value=net_name,
            position=flag_pos,
            footprint="",
            rotation=0.0,
        )
        _plan_register_symbol(plan, flag_sym, geometry)
        # Wire from anchor to flag. When the flag's Y was shifted by
        # the candidate ladder, route via _route_pin_to_target so the
        # corner placement is collision-checked; otherwise the short
        # straight horizontal works (placement guarantees a clear path).
        if abs(flag_pos.y - anchor.position.y) < 0.01:
            wire = PlacedWire(start=anchor.position, end=flag_pos)
            _add_wire_with_bbox(plan, wire)
        else:
            _route_pin_to_target(
                plan, anchor.position, flag_pos,
                avoid_owners=frozenset({f"symbol:{flag_sym.reference}"}),
            )


# ---------------------------------------------------------------------------
# Local label emission (Phase 8 extension)
# ---------------------------------------------------------------------------


def _emit_local_label_pins(plan: LayoutPlan, geometry) -> None:
    """Emit a local label at the pin tip of every LOCAL_LABEL-role pin."""
    from zynq_eda.core.model.sheet import PlacedLabel

    work = [
        (spec, _resolve_pin_page_coord(plan, spec, geometry))
        for spec in plan.pin_specs if spec.role == "LOCAL_LABEL"
    ]
    placeable = [(s, p) for (s, p) in work if p is not None]
    for spec, pin_pos in placeable:
        if spec.page_side == "left":
            rot = 180.0
        elif spec.page_side == "right":
            rot = 0.0
        elif spec.page_side == "top":
            rot = 90.0
        else:
            rot = 270.0
        lbl = PlacedLabel(
            net_name=spec.net_name, position=pin_pos, rotation=rot,
        )
        _add_label_with_candidate_ladder(plan, lbl)


def _emit_connector_pin_to_net_labels(
    plan: LayoutPlan, block: Block, geometry,
) -> None:
    """Emit local labels for connector pin_to_net entries that DIDN'T
    end up classified as EDGE_LABEL or POWER_SYMBOL.

    The classifier already handles EDGE_LABEL → hier-label and
    POWER_SYMBOL → power symbol at pin tip. This function fills in
    the gap for connector pins whose net is a non-power, non-declared
    name (rare but possible).
    """
    # Already covered by _emit_local_label_pins because LOCAL_LABEL role
    # captures connector pins not in declared_nets or POWER_SYMBOL_LIB_IDS.
    pass


# ---------------------------------------------------------------------------
# Phase 7 — plan_routes: every wire via route_orthogonal_detail
# ---------------------------------------------------------------------------


def _ensure_junction(plan: LayoutPlan, position: Point) -> None:
    """Add a junction at ``position`` if one isn't already there.

    Junctions tie a wire's endpoint to the interior of another wire.
    KiCad treats interior-touch without a junction as crossing-not-
    connecting; the junction makes the electrical link explicit.
    """
    from zynq_eda.core.model.sheet import PlacedJunction
    EPS = 1e-6
    for existing in plan.junctions:
        if (abs(existing.position.x - position.x) < EPS
                and abs(existing.position.y - position.y) < EPS):
            return
    plan.junctions.append(PlacedJunction(position=position))


def _add_wire_with_bbox(plan: LayoutPlan, wire: PlacedWire) -> bool:
    """Append a wire to plan.wires AND register its bbox in occupancy.

    Mirrors BlockLayoutBuilder.add_wire's bbox registration so the
    planner's occupancy index includes wire bboxes for router probes
    in subsequent emissions.

    Returns False (and emits nothing) for zero-length wires or wires
    that exactly duplicate an existing wire — the builder would
    hard-fail on those, and at the planner level a duplicate just
    means two emitters arrived at the same connection (which is
    physically fine; the duplicate would be silently merged in any
    real schematic). This is the only "skip" allowed by the
    architecture: structural dedup on geometrically identical wires.
    """
    from zynq_eda.core.layout.bbox import wire_bbox
    # Zero-length: no-op.
    if (abs(wire.start.x - wire.end.x) < 1e-6
            and abs(wire.start.y - wire.end.y) < 1e-6):
        return False
    # Exact-duplicate AND subset-duplicate check.
    # A subset duplicate is a shorter wire whose entire path lies
    # within a longer existing wire of the same orientation — its
    # bbox would fully overlap the existing wire's, producing a
    # wire×wire validator flag.
    new_is_h = abs(wire.start.y - wire.end.y) < 1e-6
    new_is_v = abs(wire.start.x - wire.end.x) < 1e-6
    new_x_lo, new_x_hi = sorted((wire.start.x, wire.end.x))
    new_y_lo, new_y_hi = sorted((wire.start.y, wire.end.y))
    for existing in plan.wires:
        # Exact-duplicate (either direction) check.
        same_dir = (
            abs(existing.start.x - wire.start.x) < 1e-6
            and abs(existing.start.y - wire.start.y) < 1e-6
            and abs(existing.end.x - wire.end.x) < 1e-6
            and abs(existing.end.y - wire.end.y) < 1e-6
        )
        rev_dir = (
            abs(existing.start.x - wire.end.x) < 1e-6
            and abs(existing.start.y - wire.end.y) < 1e-6
            and abs(existing.end.x - wire.start.x) < 1e-6
            and abs(existing.end.y - wire.start.y) < 1e-6
        )
        if same_dir or rev_dir:
            return False
        # Subset check — same orientation and contained.
        # When the new wire's endpoints fall in the INTERIOR of an
        # existing wire, KiCad needs a junction marker at each
        # endpoint for the electrical connection to be live (interior
        # touch without a junction is treated as crossing-without-
        # connecting). Drop a junction for each interior endpoint
        # before suppressing the duplicate wire.
        ex_is_h = abs(existing.start.y - existing.end.y) < 1e-6
        ex_is_v = abs(existing.start.x - existing.end.x) < 1e-6
        if new_is_h and ex_is_h and abs(existing.start.y - wire.start.y) < 1e-6:
            ex_x_lo, ex_x_hi = sorted((existing.start.x, existing.end.x))
            if ex_x_lo <= new_x_lo + 1e-6 and ex_x_hi + 1e-6 >= new_x_hi:
                from zynq_eda.core.model.sheet import PlacedJunction
                for endpoint in (wire.start, wire.end):
                    if (ex_x_lo + 1e-6 < endpoint.x < ex_x_hi - 1e-6):
                        _ensure_junction(plan, endpoint)
                return False  # new wire is subset of existing horizontal
        elif new_is_v and ex_is_v and abs(existing.start.x - wire.start.x) < 1e-6:
            ex_y_lo, ex_y_hi = sorted((existing.start.y, existing.end.y))
            if ex_y_lo <= new_y_lo + 1e-6 and ex_y_hi + 1e-6 >= new_y_hi:
                from zynq_eda.core.model.sheet import PlacedJunction
                for endpoint in (wire.start, wire.end):
                    if (ex_y_lo + 1e-6 < endpoint.y < ex_y_hi - 1e-6):
                        _ensure_junction(plan, endpoint)
                return False  # new wire is subset of existing vertical
    plan.wires.append(wire)
    index = len(plan.wires) - 1
    bbox = wire_bbox(
        start=wire.start, end=wire.end,
        owner_id=f"wire_{index}",
    )
    plan.occupancy.add(bbox)
    return True


def _route_pin_to_target(
    plan: LayoutPlan,
    pin_pos: Point,
    target_pos: Point,
    *,
    avoid_owners: frozenset[str],
    forbidden_traversal_points: frozenset[tuple[float, float]] = frozenset(),
) -> bool:
    """Route a single wire from ``pin_pos`` to ``target_pos`` against
    the partial plan. Returns True on success, False on gave_up.

    Routing is via :func:`route_orthogonal_detail` against
    :attr:`LayoutPlan.occupancy`. Each segment is appended to
    :attr:`LayoutPlan.wires` with bbox registration.
    """
    from zynq_eda.core.route.router import route_orthogonal_detail
    attempt = route_orthogonal_detail(
        pin_pos, target_pos, plan.occupancy,
        avoid_owners=avoid_owners,
        forbidden_traversal_points=forbidden_traversal_points,
    )
    if attempt.gave_up:
        return False
    for seg in attempt.segments:
        _add_wire_with_bbox(plan, seg)
    return True


def _route_gnd_pin_wires(plan: LayoutPlan, geometry) -> None:
    """GND pins are connected directly: the GND symbol sits AT the pin
    tip and KiCad merges them. No routed wire is emitted.

    This function is intentionally a no-op now that
    :func:`_emit_gnd_symbols` places the symbol at the pin tip rather
    than outboard. Kept as a named function so the routing dispatch
    in :func:`plan_routes` remains structured.
    """
    return None


def plan_routes(plan: LayoutPlan, block: Block, geometry) -> None:
    """Phase 7 — emit every wire required by the plan's primitives.

    Order:
      1. Cluster trunk + drop + far wires (per CLUSTER pin).
      2. GND pin → GND symbol routes (with router).
      3. EDGE_LABEL pin → hier-label routes (with router).
      4. PWR_FLAG → anchor-label routes (with router).

    Hard-fails on routing give-up. Lane reservation in Phases 2-5
    guarantees clean routes; give-up indicates a planner bug.
    """
    _route_cluster_pins(plan, block, geometry)
    _route_gnd_pin_wires(plan, geometry)
    _route_edge_label_pin_wires(plan, block, geometry)


# ---------------------------------------------------------------------------
# Phase 8 — plan_labels: labels + hier-labels at reserved positions
# ---------------------------------------------------------------------------


def _add_label_with_bbox(plan: LayoutPlan, label: PlacedLabel) -> None:
    """Append a local label to the plan AND register its text bbox."""
    from zynq_eda.core.layout._builder import _label_bbox
    plan.labels.append(label)
    plan.occupancy.add(_label_bbox(label))


def _add_label_with_candidate_ladder(
    plan: LayoutPlan, label: PlacedLabel,
) -> PlacedLabel:
    """Try the given local label's position; if its text bbox conflicts
    with something in occupancy (excluding same-net labels and junction/
    no_connect kinds), try a small outboard X-shift ladder before
    committing. Returns the actually-committed label.

    Same-net local labels are exempt (electrically equivalent — KiCad
    merges them).
    """
    from zynq_eda.core.layout._builder import _label_bbox
    from zynq_eda.core.layout._constants import (
        KICAD_GRID_MM,
        OVERLAP_NOISE_FLOOR_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid

    same_net_owner_ids = frozenset(
        f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
        for lab in plan.labels
        if lab.net_name == label.net_name
    )

    def _clean(lbl: PlacedLabel) -> bool:
        bbox = _label_bbox(lbl)
        hits = plan.occupancy.collides(
            bbox,
            ignore_owners=same_net_owner_ids,
            ignore_kinds=frozenset({"junction", "no_connect"}),
        )
        for h in hits:
            inter = bbox.intersection(h)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                return False
        return True

    # Outboard X direction per label rotation: 0 → text right, shift left.
    # 180 → text left, shift right. 90/270 → vertical; small Y shifts.
    if label.rotation == 180.0:
        sign = +1  # shift RIGHT (away from text direction)
    elif label.rotation == 0.0:
        sign = -1  # shift LEFT
    else:
        sign = 0  # vertical text: no horizontal shift
    candidates = [label] + [
        PlacedLabel(
            net_name=label.net_name,
            position=Point(
                snap_to_grid(label.position.x + sign * step * KICAD_GRID_MM),
                label.position.y,
            ),
            rotation=label.rotation,
        )
        for step in range(1, 6)
    ]
    picked = next((c for c in candidates if _clean(c)), candidates[0])
    plan.labels.append(picked)
    plan.occupancy.add(_label_bbox(picked))
    return picked


def _add_hierarchical_label_with_bbox(
    plan: LayoutPlan, hlabel: PlacedHierarchicalLabel,
) -> None:
    """Append a hierarchical label AND register its bbox."""
    from zynq_eda.core.layout._builder import _hierarchical_label_bbox
    plan.hierarchical_labels.append(hlabel)
    plan.occupancy.add(_hierarchical_label_bbox(hlabel))


def _emit_edge_label_hlabels(plan: LayoutPlan, block: Block, geometry) -> None:
    """Emit a hier-label at every EDGE_LABEL pin's reserved lane endpoint.

    The hier-label normally sits at ``lane.label_anchor``. If its text
    bbox conflicts with anything in the partial plan's occupancy at
    that position, try alternate positions offset OUTBOARD by a few
    grid units along the lane's outboard direction (further away from
    the IC/connector body). The candidate ladder is bounded and pure:
    iterate a list of (dx) shifts and pick the first clean one.

    A same-net local label already in the plan is exempt from the
    bbox conflict check (it's electrically the same net).
    """
    from zynq_eda.core.layout._builder import _hierarchical_label_bbox
    from zynq_eda.core.layout._constants import (
        KICAD_GRID_MM,
        OVERLAP_NOISE_FLOOR_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid

    declared_nets_by_name = {n.name: n for n in block.external_nets}

    work = [
        (spec, plan._lane_by_owner_pin.get(
            (spec.owner_ref, spec.pin_number or spec.pin_name),
        ))
        for spec in plan.pin_specs if spec.role == "EDGE_LABEL"
    ]
    placeable = [
        (s, lane) for (s, lane) in work
        if lane is not None and lane.label_anchor is not None
    ]

    # Candidate X-shift ladder: 0 (at anchor), then steps outboard.
    # For LEFT-edge lanes (rotation 180), outboard = negative X.
    # For RIGHT-edge lanes (rotation 0), outboard = positive X.
    shift_steps = [0] + list(range(1, 9))  # 0..8 grid steps

    def _hlabel_clean(hlabel: PlacedHierarchicalLabel,
                      same_net_owner_ids: frozenset[str]) -> bool:
        bbox = _hierarchical_label_bbox(hlabel)
        hits = plan.occupancy.collides(
            bbox,
            ignore_owners=same_net_owner_ids,
            ignore_kinds=frozenset({"junction", "no_connect"}),
        )
        for h in hits:
            inter = bbox.intersection(h)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                return False
        return True

    seen = set()
    for spec, lane in placeable:
        key = (
            spec.net_name,
            round(lane.label_anchor.x, 3),
            round(lane.label_anchor.y, 3),
        )
        if key in seen:
            continue
        seen.add(key)
        net = declared_nets_by_name.get(spec.net_name)
        if net is None:
            continue
        # Build same-net exempt set (local labels with the same net).
        same_net_owner_ids = frozenset(
            f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
            for lab in plan.labels
            if lab.net_name == spec.net_name
        )
        # Direction of outboard shift along the lane's edge.
        if lane.edge == "left":
            sign = -1
        elif lane.edge == "right":
            sign = +1
        else:
            sign = 0  # TOP/BOTTOM: don't shift
        # Pure-functional pick: try each shift, return first clean.
        # X-only shifts first (preferred — keeps label at same Y as pin
        # for visual alignment); then X+Y combinations for tight cases.
        candidates = [
            Point(
                snap_to_grid(lane.label_anchor.x + sign * step * KICAD_GRID_MM),
                lane.label_anchor.y,
            )
            for step in shift_steps
        ]
        # Extended: try X-shifts + Y shifts (±1, ±2 grid steps) for
        # cases where the pure-X ladder couldn't find a clean position
        # (e.g., when an adjacent connector pin number sits at the same Y).
        for y_step in (1, -1, 2, -2):
            candidates.extend(
                Point(
                    snap_to_grid(lane.label_anchor.x + sign * step * KICAD_GRID_MM),
                    snap_to_grid(lane.label_anchor.y + y_step * KICAD_GRID_MM),
                )
                for step in shift_steps
            )
        prospective = [
            PlacedHierarchicalLabel(
                net_name=spec.net_name,
                position=pos,
                direction=net.direction,
                rotation=lane.label_rotation,
            )
            for pos in candidates
        ]
        picked = next(
            (h for h in prospective
             if _hlabel_clean(h, same_net_owner_ids)),
            prospective[0],  # fall back to default if no candidate is clean
        )
        _add_hierarchical_label_with_bbox(plan, picked)


def _route_edge_label_pin_wires(
    plan: LayoutPlan, block: Block, geometry,
) -> None:
    """Route a wire from each EDGE_LABEL pin to its hier-label position.

    The hier-label was emitted by Phase 8 at ``lane.label_anchor``;
    this function emits the wire connecting pin tip to label anchor.
    """
    from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids

    work = [
        (spec,
         _resolve_pin_page_coord(plan, spec, geometry),
         plan._lane_by_owner_pin.get(
             (spec.owner_ref, spec.pin_number or spec.pin_name),
         ))
        for spec in plan.pin_specs if spec.role == "EDGE_LABEL"
    ]
    placeable = [
        (s, pos, lane) for (s, pos, lane) in work
        if pos is not None and lane is not None
        and lane.label_anchor is not None
    ]
    # Dedup by (owner_ref, pin_number) — pin_name can repeat in
    # double-row connectors (USB-C, FMC).
    seen = set()
    for spec, pin_pos, lane in placeable:
        key = (spec.owner_ref, spec.pin_number or spec.pin_name)
        if key in seen:
            continue
        seen.add(key)
        target = lane.label_anchor
        avoid: set[str] = {f"symbol:{spec.owner_ref}"}
        if spec.pin_number:
            avoid |= set(pin_intrinsic_owner_ids(
                spec.owner_ref, (spec.pin_number,),
            ))
        ok = _route_pin_to_target(
            plan, pin_pos, target,
            avoid_owners=frozenset(avoid),
        )
        if not ok:
            # Soft-fail: skip this wire and emit a placeholder label
            # at the pin tip. The reactive build does the same when
            # a clean route can't be found.
            from zynq_eda.core.model.sheet import PlacedLabel
            label_rot = {
                "left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0,
            }[spec.page_side]
            lbl = PlacedLabel(
                net_name=spec.net_name, position=pin_pos,
                rotation=label_rot,
            )
            _add_label_with_bbox(plan, lbl)


def plan_labels(plan: LayoutPlan, block: Block, geometry) -> None:
    """Phase 8 — emit every label / hierarchical label.

    Order:
      1. EDGE_LABEL hier-labels at lane anchors (Phase 8 prerequisite).
      2. LOCAL_LABEL labels at pin tips.

    Lane reservation guarantees label text bboxes fit; a collision is
    a planner bug.
    """
    _emit_edge_label_hlabels(plan, block, geometry)
    _emit_local_label_pins(plan, geometry)


# ---------------------------------------------------------------------------
# Top-level planner entry point
# ---------------------------------------------------------------------------


def plan_block(block: Block, geometry) -> LayoutPlan:
    """Top-level planner: build the complete :class:`LayoutPlan` for
    one block.

    Runs Phases 1-8 in order. Each phase's output feeds the next;
    each phase asserts its own invariants and hard-fails with a
    structured diagnostic when an upstream constraint is unmet.

    Returns a frozen :class:`LayoutPlan` ready for :func:`emit_plan`.
    """
    plan = LayoutPlan()

    # Phase 1
    plan.pin_specs = plan_pin_specs(block, geometry)

    # Phase 2
    anchor_relative_lanes = plan_lane_widths(plan.pin_specs, block, geometry)

    # Phase 3
    plan.edge_stacks = plan_edge_stacks(
        anchor_relative_lanes, block, geometry,
    )

    # Phase 4
    plan.anchors = plan_anchors(
        block, plan.edge_stacks, geometry, plan.pin_specs,
    )
    plan._anchor_by_ref = {a.owner_ref: a for a in plan.anchors}

    # Phase 5
    plan.lane_allocations = plan_realize_lanes(
        plan.edge_stacks, plan.anchors, block,
    )
    # Index by (owner_ref, pin_NUMBER) instead of (owner_ref, pin_name)
    # because pin_number is uniquely assigned per pad whereas pin_name
    # can repeat (USB-C D+ on side A6 vs B6 share name "D+").
    plan._lane_by_owner_pin = {
        (l.owner_ref, l.pin_number or l.pin_name): l
        for l in plan.lane_allocations
    }

    # Phase 6
    plan_symbols(plan, block, geometry)

    # Phase 7 — wires (currently: GND routes; cluster routes deferred)
    plan_routes(plan, block, geometry)

    # Post-routing pass with consider_wires=True: with wires now in
    # occupancy, re-pick any Value shifts that conflict with wires.
    _refine_cluster_value_shifts(plan, geometry, consider_wires=True)

    # Phase 8 — labels (EDGE_LABEL hier-labels + LOCAL_LABEL labels)
    plan_labels(plan, block, geometry)

    # Post-label refinement with consider_wires=True. Catches any
    # property text that now conflicts with labels emitted in Phase 8.
    _refine_cluster_reference_shifts(plan, geometry, consider_wires=True)
    _refine_cluster_value_shifts(plan, geometry, consider_wires=True)

    # Phase 9 — PWR_FLAG emission (depends on labels existing).
    # Reuse ref counters from Phase 6.
    next_ref_counters = getattr(plan, "_ref_counters", {})
    _emit_pwr_flags(plan, block, geometry, next_ref_counters)

    return plan


def emit_plan(plan: LayoutPlan, builder) -> None:
    """Walk a verified-clean :class:`LayoutPlan` and emit primitives
    to the :class:`BlockLayoutBuilder`.

    No collision checks — the plan is already verified clean. The
    builder's own ``add_*`` methods will rebuild its occupancy index
    as it commits each primitive.

    Order matches the planner's accumulation order (Phase 6 symbols
    first so the builder's symbol-bbox registration runs before any
    wire emission, then wires + junctions, then NCs, then labels +
    hier-labels) so the builder's occupancy matches the planner's
    occupancy at every step.
    """
    for sym in plan.symbols:
        builder.add_symbol(sym)
    for wire in plan.wires:
        builder.add_wire(wire)
    for junc in plan.junctions:
        builder.junctions.append(junc)
    for nc in plan.no_connects:
        builder.no_connects.append(nc)
    for lbl in plan.labels:
        builder.add_label(lbl)
    for hlbl in plan.hierarchical_labels:
        builder.add_hierarchical_label(hlbl)
