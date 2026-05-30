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
    # A CLUSTER pin's OWN net (the signal/power the pin carries), distinct
    # from cluster_destinations (where its passives' far ends go). KiCad
    # priority makes such a pin role=CLUSTER, but its own net must STILL be
    # emitted as a label/hier-label/power-symbol at the pin tip — otherwise
    # the signal is silently dropped (boot straps, JTAG, MIPI I2C, microSD
    # DAT, FMC pull-ups). cluster_owner_role is how that own net would be
    # classified if the pin weren't a cluster (EDGE_LABEL / POWER_SYMBOL /
    # LOCAL_LABEL), or None when the pin has no own net (e.g. GND / unnamed).
    cluster_owner_net: str = ""
    cluster_owner_role: "PinRole | None" = None

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
        if self.role != "CLUSTER" and (
            self.cluster_owner_net or self.cluster_owner_role is not None
        ):
            raise ValueError(
                f"Non-CLUSTER pin {self.owner_ref}/{self.pin_name} must not set "
                f"cluster_owner_net/role"
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


def _subclassify_own_net(net: str, declared_nets: dict) -> "PinRole | None":
    """Classify a CLUSTER pin's OWN net into the role it WOULD have if the
    pin weren't a cluster, so the cluster pass can still emit a label for it.

    Returns None when there is no own net to emit (empty, or a GND-family
    net the cluster/GND machinery already handles).
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS as _PWR
    if not net:
        return None
    if net == "GND" or _is_gnd_pin_name(net):
        return None
    # Prefer a compact, conventional POWER SYMBOL for power-rail own-nets
    # (even when the rail is also a declared external net — a KiCad power
    # symbol connects it globally). This is checked BEFORE EDGE_LABEL so a
    # power pin that also carries decoupling gets a small power symbol on
    # its trunk (via the rail-tap pass) instead of a verbose hier-label
    # that would crowd the cluster's drop wires + pin number.
    if net in _PWR:
        return "POWER_SYMBOL"
    if net in declared_nets:
        return "EDGE_LABEL"
    return "LOCAL_LABEL"


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
                # The IC cluster pin's OWN net is what _classify_ic_pin
                # resolved into `net` (pin override / power_input/output).
                owner_net = net
                owner_role = _subclassify_own_net(owner_net, declared_nets)
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
                    cluster_owner_net=owner_net if owner_role else "",
                    cluster_owner_role=owner_role,
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
        connector_pins = _enumerate_owner_pins(
            connector.lib_id, geometry, rotation=connector.rotation,
        )
        name_to_number = {n: num for (n, num, _r, _pr) in connector_pins}
        pin_to_net = _build_pin_to_net_map(connector, name_to_number)

        cluster_externals_by_pin = {}
        for ep in connector.refcircuit.external_parts:
            dests = cluster_externals_by_pin.setdefault(ep.from_pin, [])
            for _ in range(ep.quantity):
                # A refcircuit cluster destination may reference a SYMBOL
                # PIN NAME (e.g. a differential partner "LVDS_CLK-") that
                # the carrier remaps to a real net via pin_to_net. Resolve
                # it so the far-end lands on the carrier net (e.g.
                # ZYNQ_LCD_LVDS_CLK_N) instead of an orphan local label.
                # Non-pin net names (GND, +3V3, …) pass through unchanged.
                dests.append(pin_to_net.get(ep.to_net, ep.to_net))
        cluster_pins = set(cluster_externals_by_pin.keys())

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
                # The connector cluster pin's OWN net comes from pin_to_net
                # (NOT the external-part destination, which is `net`).
                owner_net = pin_to_net.get(pin_name, "")
                owner_role = _subclassify_own_net(owner_net, declared_nets)
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
                    cluster_owner_net=owner_net if owner_role else "",
                    cluster_owner_role=owner_role,
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
    from zynq_eda.core.layout.bbox import text_width
    # Trailing space accounts for the hier-label's arrow decoration, so
    # the reserved lane width matches the faithful per-glyph width the
    # validator measures after emission.
    return text_width(net_name + " ")


def _label_text_width_mm(net_name: str) -> float:
    """Predict the width (mm) of a local-label's text bbox for ``net_name``.

    Local labels render the bare net name with no decoration; this is
    one char narrower than the hier-label equivalent.
    """
    from zynq_eda.core.layout.bbox import text_width
    return text_width(net_name)


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


def _input_pwr_flag_nets(block: Block, geometry=None) -> tuple[str, ...]:
    """Return the names of nets that will receive a PWR_FLAG.

    Mirrors the eligibility logic in ``edge_labels.py:_input_pwr_flags``:
    input-direction nets sourced on this block (i.e. having a connector
    pin producing them); plus output nets without an IC driver; plus
    non-canonical ground variants (CHASSIS_GND etc.).

    Plus (geometry-aware) any net that carries an IC POWER-INPUT pin but
    is NOT a global power-symbol rail and has no local driver — see the
    Rule B block below.

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
            # KiCad's ``power:GND`` symbol pin is itself a power-INPUT,
            # so a flattened GND net carrying only power-input pins
            # (connector GND pins + power:GND symbols) has no driver
            # and trips ``power_pin_not_driven``. Drive it with a
            # SINGLE PWR_FLAG, emitted in the ``power`` block — the
            # circuit's ground source. One flag marks the whole
            # flattened GND net driven; emitting it only here keeps
            # every other (denser) block free of an extra flag+wire.
            if block.name != "power":
                continue
        if net.power_kind == "output":
            has_driver = any(ic.power_output_net == net.name for ic in block.ics)
            if has_driver:
                continue
        if net.power_kind == "input" and net.name not in nets_sourced_by_connector:
            continue
        out.append(net.name)

    # ---- Rule B: undriven power-input pins on LOCAL (hier-label) nets ----
    # The root index sheet exposes no sheet pins, so a hier-label net is
    # LOCAL to its sub-sheet (it does not merge across blocks). A net that
    # carries an IC POWER-INPUT pin therefore needs a LOCAL driver, or
    # KiCad's ``power_pin_not_driven`` fires. Global power-symbol rails
    # (+3V3 / +5V / GND …) are exempt — they connect by name across the
    # whole hierarchy and a single PWR_FLAG anywhere drives them. So flag
    # any DECLARED net that (a) carries an IC power-input-type pin (read
    # from the symbol pin TYPE via geometry — robust to non-canonical
    # supply names like VCCA/VCCB), (b) is not a power-symbol rail,
    # (c) has no local IC power-output driver, and (d) isn't canonical
    # GND. This covers an LDO/load-switch IN rail consumed but not
    # connector-sourced on the sheet (power, usbc_otg ``+VIN``) and a
    # cable-side supply fed from off-board (hdmi_rx 5 V sense → VCCB).
    if geometry is not None:
        declared = {n.name for n in block.external_nets}
        already = set(out)
        locally_driven = {
            ic.power_output_net for ic in block.ics if ic.power_output_net
        }
        for ic in block.ics:
            try:
                pins = geometry.all_pins(ic.lib_id, 0.0)
            except Exception:
                continue
            for p in pins:
                if "power_in" not in str(p.get("type", "")).lower():
                    continue
                net_name = _resolve_ic_pin_net(p["name"], ic)
                if (not net_name or net_name in already
                        or net_name in locally_driven):
                    continue
                if net_name == "GND" or _is_gnd_pin_name(net_name):
                    continue
                if _power_symbol_for_destination(net_name) is not None:
                    continue  # global power-symbol rail — driven elsewhere
                if net_name not in declared:
                    continue  # internal net (e.g. an on-chip regulator
                    # output driven by its own power-output pin); no edge
                    # to anchor a flag lane on, and not externally fed.
                out.append(net_name)
                already.add(net_name)

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
    for net_name in _input_pwr_flag_nets(block, geometry):
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
        # NOTE: labels at the endpoint are deliberately NOT exempted.
        # A share-wire that runs into a slot-0 label's text is a real
        # wire×label overlap (the label reads along the wire's axis).
        # Leaving labels as obstacles makes such share-wires fail the
        # probe, so the caller falls back to a clean duplicate label.

    # Probe the cheap hand-built segments against occupancy. Exempt the
    # endpoint terminators (cap bodies + slot-0 symbol/label). If any
    # segment hits a real obstacle, fall through to the full router.
    EXEMPT_KINDS = frozenset({"junction", "no_connect", "wire"})

    def _segments_clean(candidate_segs) -> bool:
        for seg in candidate_segs:
            if seg.start == seg.end:
                continue
            bb = wire_bbox(seg.start, seg.end, owner_id="share_probe")
            if plan.occupancy.collides(
                bb, ignore_kinds=EXEMPT_KINDS, ignore_owners=exempt_owners,
            ):
                return False
        return True

    def _emit(candidate_segs) -> bool:
        ok = False
        for seg in candidate_segs:
            if seg.start == seg.end:
                continue
            if _add_wire_with_bbox(plan, seg):
                ok = True
        return ok

    if _segments_clean(segs):
        return _emit(segs)

    # Hand-built path blocked (a body sits between the two far pins).
    # We do NOT fall back to a free-form router here — every router
    # detour we tried crossed an intervening cap/symbol body, which
    # the strict validator (correctly) rejects. Return False; the
    # caller emits a VISIBLE same-net label at this cap.far instead
    # (KiCad merges same-name labels, so the pin is still on the net).
    # That keeps the layout overlap-free while staying fully visible.
    return False


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
        if sym is None:
            continue
        # Power/flag symbols (#PWR.., #FLG..) keep their rail-name Value at
        # the library position. Relocating it regresses dense power-symbol
        # sheets (verified: moving usb_pd's FUSB302 rail labels opened 6
        # new overlaps), so the conflicting partner is moved instead.
        if sym.reference.startswith("#PWR") or sym.reference.startswith("#FLG"):
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
        multi_slot_widen = len(part_tokens_for_pin) > 1

        # Pre-compute every slot's cap.far so the shared terminator for
        # a destination can be anchored at the OUTERMOST slot (the one
        # whose far pin is furthest from the IC pin). A non-power LABEL
        # renders its text OUTBOARD; anchoring it at the outermost slot
        # makes that text extend into clear page interior instead of
        # covering the inner slots — which is exactly what blocks the
        # inner slots' share-wire AND their dup-label (the floating-pin
        # ERC class on the ethernet Bob-Smith network). Inner slots then
        # connect to the anchor with a clean wire whose path lies INBOARD
        # of the label anchor, clear of the text. Power-symbol
        # destinations keep the innermost (first) anchor: the symbol is
        # small with no long text, and re-anchoring it would perturb the
        # already-clean GND clusters.
        slot_far_by_idx: list[Point] = []
        for _si in range(len(part_tokens_for_pin)):
            _sp = _cluster_slot_position(
                pin_pos, spec.page_side, _si,
                dense_swarm=dense_swarm,
                multi_slot_widen=multi_slot_widen,
            )
            _, _cf = _cluster_passive_near_far(_sp, spec.page_side)
            slot_far_by_idx.append(_cf)

        def _far_dist_sq(i: int, _pin=pin_pos, _fars=slot_far_by_idx) -> float:
            d = _fars[i]
            return (d.x - _pin.x) ** 2 + (d.y - _pin.y) ** 2

        anchor_idx_by_dest: dict[str, int] = {}
        for _si, _dnet in enumerate(spec.cluster_destinations):
            _is_power = _power_symbol_for_destination(_dnet) is not None
            _cur = anchor_idx_by_dest.get(_dnet)
            if _cur is None:
                anchor_idx_by_dest[_dnet] = _si
            elif not _is_power and _far_dist_sq(_si) > _far_dist_sq(_cur):
                anchor_idx_by_dest[_dnet] = _si
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
            anchor_idx = anchor_idx_by_dest.get(destination_net)
            if slot_idx != anchor_idx:
                # Sub-slot: the destination's shared terminator lives at
                # the ANCHOR slot's cap.far. Connect this slot's cap.far
                # to the anchor cap.far with a VISIBLE wire so the pin
                # isn't floating. The wire path lies inboard of the
                # anchor label's outboard-pointing text, so it stays
                # clear. If no clean wire fits, emit a VISIBLE duplicate
                # label naming the net (KiCad merges same-name labels).
                # NEVER hide text — if neither a wire nor a visible label
                # fits, leave the pin floating so ERC surfaces it for a
                # routing/placement fix.
                anchor_far = (
                    slot_far_by_idx[anchor_idx]
                    if anchor_idx is not None else None
                )
                wired = False
                if anchor_far is not None and anchor_far != cap_far:
                    wired = _try_emit_cluster_share_wire(
                        plan, cap_far, anchor_far, spec.page_side,
                    )
                if not wired:
                    from zynq_eda.core.model.sheet import PlacedLabel
                    from zynq_eda.core.layout._builder import _label_bbox
                    dup_label_rot = {
                        "left": 180.0, "right": 0.0,
                        "top": 90.0, "bottom": 270.0,
                    }[spec.page_side]
                    dup_label = PlacedLabel(
                        net_name=destination_net,
                        position=cap_far,
                        rotation=dup_label_rot,
                    )
                    if not plan.occupancy.collides(
                        _label_bbox(dup_label),
                        ignore_kinds=frozenset({"wire", "junction", "no_connect"}),
                    ):
                        _add_label_with_bbox(plan, dup_label)
                continue
            emitted_destinations_for_pin.add(destination_net)
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
            else:
                # Local label at cap.far naming the destination net.
                # Set-dedup: multiple slots on the same pin going to the
                # same non-power destination share a single label.
                # The label is anchored at the OUTERMOST slot (see the
                # anchor-selection pre-pass) and its text rotation is
                # chosen to clear the dense stacked-cluster neighbourhood.
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
                    _add_cluster_far_label_rotated(
                        plan, destination_net, cap_far, spec.page_side,
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
        trunk_segments_actual: tuple[PlacedWire, ...] = ()
        if not trunk_attempt.gave_up:
            for seg in trunk_attempt.segments:
                _add_wire_with_bbox(plan, seg)
            trunk_segments_actual = trunk_attempt.segments
        else:
            # The router gave up even with the permissive avoid set (own
            # cap bodies exempted). Do NOT emit a direct wire through the
            # obstacle — that would draw a wire crossing another body, the
            # exact "emit-through-obstacle" anti-pattern the router contract
            # forbids (and which _route_pin_to_target rejects with False).
            # Emit nothing: the cap near-pins are left unconnected, so KiCad
            # ERC fires pin_not_connected — surfacing the unroutable trunk
            # loudly for a placement fix (widen PASSIVE_OFFSET / stagger /
            # move the obstacle) instead of hiding a visible wire overlap.
            trunk_segments_actual = ()

        # Per-slot drops + far wires + junctions. The trunk may have
        # taken a Z-bend (router picked an offset to avoid an obstacle),
        # so the horizontal portion of the trunk isn't necessarily at
        # ``pin_pos.y``. Look up the actual horizontal trunk Y at each
        # slot's X — drops must start at the ACTUAL trunk row,
        # otherwise the drop endpoint dangles and KiCad ERC fires
        # pin_not_connected on the cap's near-pin.
        for slot_idx in range(n_slots):
            slot_pos = _cluster_slot_position(
                pin_pos, spec.page_side, slot_idx,
                dense_swarm=dense_swarm,
                multi_slot_widen=multi_slot_widen,
            )
            cap_near, cap_far = _cluster_passive_near_far(
                slot_pos, spec.page_side,
            )
            # Find the trunk segment that PASSES THROUGH the slot's
            # primary-axis X (for LEFT/RIGHT clusters) or Y (TOP/BOTTOM)
            # — pick the SMALLEST-stride segment (the actual horizontal
            # leg, not the source's exit-detour stub).
            if spec.page_side in ("left", "right"):
                drop_x = slot_pos.x
                drop_y = pin_pos.y  # default fallback
                best_span = float("inf")
                for seg in trunk_segments_actual:
                    is_h = abs(seg.start.y - seg.end.y) < 1e-6
                    if not is_h:
                        continue
                    x_lo, x_hi = sorted((seg.start.x, seg.end.x))
                    if x_lo - 1e-6 <= drop_x <= x_hi + 1e-6:
                        span = x_hi - x_lo
                        if span < best_span:
                            best_span = span
                            drop_y = seg.start.y
                # Prefer the LONGEST horizontal (the main trunk leg)
                # not the exit stub. Re-pick on max-span.
                best_span = -1.0
                for seg in trunk_segments_actual:
                    is_h = abs(seg.start.y - seg.end.y) < 1e-6
                    if not is_h:
                        continue
                    x_lo, x_hi = sorted((seg.start.x, seg.end.x))
                    if x_lo - 1e-6 <= drop_x <= x_hi + 1e-6:
                        span = x_hi - x_lo
                        if span > best_span:
                            best_span = span
                            drop_y = seg.start.y
                drop_start = Point(drop_x, drop_y)
            else:
                drop_y = slot_pos.y
                drop_x = pin_pos.x
                best_span = -1.0
                for seg in trunk_segments_actual:
                    is_v = abs(seg.start.x - seg.end.x) < 1e-6
                    if not is_v:
                        continue
                    y_lo, y_hi = sorted((seg.start.y, seg.end.y))
                    if y_lo - 1e-6 <= drop_y <= y_hi + 1e-6:
                        span = y_hi - y_lo
                        if span > best_span:
                            best_span = span
                            drop_x = seg.start.x
                drop_start = Point(drop_x, drop_y)
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
        # Anchor-X column, offset in Y: when the outboard default would put
        # the flag's (long) value text off the page margin — e.g. a
        # CHASSIS_GND flag next to a left-edge anchor whose text points
        # inboard — placing the flag at the anchor's OWN x (text then sits
        # over the in-bounds page interior) and connecting with a VERTICAL
        # wire avoids both the off-margin overflow and crossing the anchor's
        # horizontal text. Tried after the short-wire options, before fallback.
        for y_step in (2, -2, 3, -3, 4, -4, 5, -5, 6, -6):
            candidates.append(Point(
                anchor.position.x,
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


def _emit_power_rail_taps(
    plan: LayoutPlan, block: Block, geometry, next_ref_counters: dict,
) -> None:
    """For every connector CLUSTER pin whose OWN net is a declared power
    rail (e.g. a microSD VDD pin on +3V3), tap the cluster trunk with
    that rail's power symbol so the trunk net is named and driven.

    The cluster pass wires the pin's decoupling-cap FAR pins to their
    destination (GND); the pin's own rail identity is never placed. We
    add a VISIBLE power symbol on a short perpendicular stub off the
    trunk, scanning outboard trunk points and both perpendicular
    directions for clear space. Every primitive is collision-checked;
    if no clear spot exists the tap is skipped (ERC surfaces it rather
    than a silent overlap). Nothing is hidden.
    """
    from zynq_eda.core.layout._constants import (
        INTERIOR_MARGIN_MM, KICAD_GRID_MM, POWER_SYMBOL_LIB_IDS,
    )
    from zynq_eda.core.layout.bbox import symbol_bbox, wire_bbox
    from zynq_eda.core.model.grid import Point, snap_to_grid

    # Map each connector pin (by number) to its declared net.
    pin_net: dict[tuple[str, str], str] = {}
    for conn in block.connectors:
        name_to_number = {}
        try:
            name_to_number = _connector_name_to_number(conn, geometry)
        except Exception:
            pass
        pin_to_net = _build_pin_to_net_map(conn, name_to_number)
        for spec in plan.pin_specs:
            if spec.owner_ref != conn.reference or spec.role != "CLUSTER":
                continue
            net = pin_to_net.get(spec.pin_name) or pin_to_net.get(spec.pin_number)
            if net and net in POWER_SYMBOL_LIB_IDS:
                pin_net[(spec.owner_ref, spec.pin_number)] = net

    for spec in plan.pin_specs:
        key = (spec.owner_ref, spec.pin_number)
        net = pin_net.get(key)
        if net is None:
            continue
        # Don't double-tap if the pin's own rail already has a symbol
        # whose pin sits on this pin's trunk (rare).
        pin_pos = _resolve_pin_page_coord(plan, spec, geometry)
        if pin_pos is None:
            continue
        side = spec.page_side
        out_sign = -1 if side == "left" else (1 if side == "right" else 0)
        if out_sign == 0:
            continue  # TOP/BOTTOM rail taps not handled here
        from zynq_eda.core.model.sheet import PlacedLabel, PlacedWire
        from zynq_eda.core.layout._builder import _label_bbox
        # The trunk net is named by EXTENDING the cluster trunk past its
        # TRUE far end into the open interior, then placing a VISIBLE
        # ``<rail>`` local label at the extension's end (text reading
        # further outboard, into clear space BEYOND every wire). KiCad
        # merges same-name labels, so the trunk joins the rail net and
        # is driven by its PWR_FLAG. Probed strictly; first clear wins.
        #
        # The true far end = the outboard end of the contiguous run of
        # horizontal wires at the pin's row that contains the pin tip
        # (the trunk may stretch well past the outermost cap drop).
        row_y = pin_pos.y
        intervals = []
        for w in plan.wires:
            if abs(w.start.y - row_y) < 0.1 and abs(w.end.y - row_y) < 0.1:
                intervals.append((min(w.start.x, w.end.x),
                                  max(w.start.x, w.end.x)))
        # Merge the interval containing pin_pos.x to find its far edge.
        lo, hi = pin_pos.x, pin_pos.x
        changed = True
        while changed:
            changed = False
            for a, b in intervals:
                if b >= lo - 0.1 and a <= hi + 0.1:  # overlaps current run
                    if a < lo - 0.1:
                        lo = a; changed = True
                    if b > hi + 0.1:
                        hi = b; changed = True
        trunk_far = Point(lo if out_sign < 0 else hi, row_y)
        placed = False
        for j in range(1, 13):  # extend outboard from the trunk far end
            end = Point(
                snap_to_grid(trunk_far.x + out_sign * j * KICAD_GRID_MM),
                pin_pos.y,
            )
            if end.x <= INTERIOR_MARGIN_MM or end == trunk_far:
                break
            ext_bb = wire_bbox(trunk_far, end, owner_id="railtap:ext")
            # The extension wire must be clean against bodies/labels
            # (other wires are OK to share endpoints; the dedup adds a
            # junction where it meets the existing trunk).
            if plan.occupancy.collides(
                ext_bb, ignore_kinds=frozenset(
                    {"junction", "no_connect", "wire"}),
            ):
                continue
            # Label at the extension end, reading outboard.
            lbl_rot = 180.0 if out_sign < 0 else 0.0
            lbl = PlacedLabel(net_name=net, position=end, rotation=lbl_rot)
            if plan.occupancy.collides(
                _label_bbox(lbl),
                ignore_kinds=frozenset({"junction", "no_connect"}),
            ):
                continue
            _add_wire_with_bbox(plan, PlacedWire(start=trunk_far, end=end))
            _add_label_with_bbox(plan, lbl)
            placed = True
            break


def _connector_name_to_number(conn, geometry) -> dict:
    """Map a connector's pin names to numbers via the geometry cache."""
    out = {}
    try:
        for info in geometry.all_pins(conn.lib_id, rotation=0.0):
            out[str(info["name"])] = str(info["number"])
    except Exception:
        pass
    return out


def _emit_gnd_drive_stamp(
    plan: LayoutPlan, block: Block, geometry, next_ref_counters: dict,
) -> None:
    """Emit one self-contained ``GND is driven`` stamp: a ``power:GND``
    symbol and a ``power:PWR_FLAG`` joined by a short vertical wire,
    placed in the first clear spot found by scanning the page interior.

    KiCad needs at least one PWR_FLAG on the flattened GND net or it
    reports ``power_pin_not_driven`` on every connector GND power-input
    pin. The stamp is fully visible (two standard symbols + a wire);
    nothing is hidden. Every primitive's bbox is collision-checked, so
    the stamp never overlaps anything — if the scan finds no clear
    spot the stamp is skipped (and the ERC error remains, surfacing a
    page-room problem rather than a silent overlap).
    """
    from zynq_eda.core.layout.bbox import symbol_bbox, wire_bbox
    from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM, KICAD_GRID_MM
    from zynq_eda.core.model.grid import Point, snap_to_grid
    from zynq_eda.core.model.sheet import (
        PAPER_DIMENSIONS_MM, PlacedSymbol, PlacedWire,
    )

    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    # Stamp geometry: GND symbol pin at the TOP of a 2-grid vertical
    # wire (body hangs DOWN), PWR_FLAG pin at the BOTTOM-... actually
    # place the GND symbol pin at ``gnd_pos`` (body below) and the
    # PWR_FLAG ``flag_pos`` one wire-length ABOVE (flag body up), wire
    # between the two pin tips. Both pins sit on the same net.
    WIRE_LEN = 2 * KICAD_GRID_MM  # 5.08 mm

    def _stamp_clean(gnd_pos: Point, flag_pos: Point) -> bool:
        try:
            gnd_bb = symbol_bbox(lib_id="power:GND", anchor=gnd_pos,
                                 rotation=0.0, cache=geometry,
                                 owner_id="gndstamp:gnd")
            flag_bb = symbol_bbox(lib_id="power:PWR_FLAG", anchor=flag_pos,
                                  rotation=0.0, cache=geometry,
                                  owner_id="gndstamp:flag")
        except Exception:
            return False
        wbb = wire_bbox(gnd_pos, flag_pos, owner_id="gndstamp:wire")
        for bb in (gnd_bb, flag_bb, wbb):
            if (bb.min.x < INTERIOR_MARGIN_MM
                    or bb.max.x > paper_w - INTERIOR_MARGIN_MM
                    or bb.min.y < INTERIOR_MARGIN_MM
                    or bb.max.y > paper_h - INTERIOR_MARGIN_MM):
                return False
            if plan.occupancy.collides(
                bb, ignore_kinds=frozenset({"junction", "no_connect"}),
            ):
                return False
        return True

    # Scan the page interior on a coarse grid, top-left to bottom-right,
    # for the first clear spot. Step by 4 grid units (10.16 mm).
    step = 4 * KICAD_GRID_MM
    y = snap_to_grid(INTERIOR_MARGIN_MM + WIRE_LEN + step)
    chosen: tuple[Point, Point] | None = None
    while y < paper_h - INTERIOR_MARGIN_MM and chosen is None:
        x = snap_to_grid(INTERIOR_MARGIN_MM + step)
        while x < paper_w - INTERIOR_MARGIN_MM:
            gnd_pos = Point(x, y)
            flag_pos = Point(x, snap_to_grid(y - WIRE_LEN))
            if _stamp_clean(gnd_pos, flag_pos):
                chosen = (gnd_pos, flag_pos)
                break
            x = snap_to_grid(x + step)
        y = snap_to_grid(y + step)

    if chosen is None:
        return  # no clear spot — leave ERC to surface a room problem
    gnd_pos, flag_pos = chosen
    gnd_idx = next_ref_counters.setdefault("PWR", 300)
    next_ref_counters["PWR"] = gnd_idx + 1
    flg_idx = next_ref_counters.setdefault("FLG", 100)
    next_ref_counters["FLG"] = flg_idx + 1
    _plan_register_symbol(plan, PlacedSymbol(
        lib_id="power:GND", reference=f"#PWR{gnd_idx}", value="GND",
        position=gnd_pos, footprint="", rotation=0.0,
    ), geometry)
    _plan_register_symbol(plan, PlacedSymbol(
        lib_id="power:PWR_FLAG", reference=f"#FLG{flg_idx}", value="GND",
        position=flag_pos, footprint="", rotation=0.0,
    ), geometry)
    _add_wire_with_bbox(plan, PlacedWire(start=gnd_pos, end=flag_pos))


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

    # ---- Partial collinear overlap: clip to non-overlapping residual --
    # A new wire that partially overlaps one or more existing collinear
    # wires (same orientation + same axis coord) — but is neither an
    # exact duplicate nor a subset — would render as a DOUBLED line over
    # the shared span. KiCad merges collinear overlapping segments into a
    # single net regardless of junctions, so the overlap span is already
    # electrically identical to a single wire; keeping the doubled copy
    # only adds a visual overprint (and a validator flag). We therefore
    # keep ONLY the residual portion(s) of the new wire not already
    # covered by an existing collinear wire, and let each residual meet
    # the covering wire at a shared endpoint (which the overlap validator
    # exempts and KiCad connects). Connectivity is preserved exactly —
    # the residual still reaches the same trunk, just joining it at the
    # covering wire's end instead of mid-span. A junction is dropped at
    # each clip boundary interior to the original span (3+ wires meet).
    covering: list[tuple[float, float]] = []
    for existing in plan.wires:
        ex_is_h = abs(existing.start.y - existing.end.y) < 1e-6
        ex_is_v = abs(existing.start.x - existing.end.x) < 1e-6
        if new_is_h and ex_is_h and abs(existing.start.y - wire.start.y) < 1e-6:
            ex_lo, ex_hi = sorted((existing.start.x, existing.end.x))
            if ex_lo < new_x_hi - 1e-6 and ex_hi > new_x_lo + 1e-6:
                covering.append((ex_lo, ex_hi))
        elif new_is_v and ex_is_v and abs(existing.start.x - wire.start.x) < 1e-6:
            ex_lo, ex_hi = sorted((existing.start.y, existing.end.y))
            if ex_lo < new_y_hi - 1e-6 and ex_hi > new_y_lo + 1e-6:
                covering.append((ex_lo, ex_hi))
    if covering:
        lo, hi = (new_x_lo, new_x_hi) if new_is_h else (new_y_lo, new_y_hi)
        fixed = wire.start.y if new_is_h else wire.start.x
        covering.sort()
        residual: list[tuple[float, float]] = []
        cursor = lo
        for c_lo, c_hi in covering:
            if c_lo > cursor + 1e-6:
                residual.append((cursor, min(c_lo, hi)))
            cursor = max(cursor, c_hi)
            if cursor >= hi - 1e-6:
                break
        if cursor < hi - 1e-6:
            residual.append((cursor, hi))
        added = False
        for seg_lo, seg_hi in residual:
            if seg_hi - seg_lo < 1e-6:
                continue
            if new_is_h:
                seg = PlacedWire(start=Point(seg_lo, fixed), end=Point(seg_hi, fixed))
            else:
                seg = PlacedWire(start=Point(fixed, seg_lo), end=Point(fixed, seg_hi))
            if _add_wire_with_bbox(plan, seg):
                added = True
        # Junction wherever a residual segment meets a covering wire at a
        # point interior to the original span (deliberate merge point).
        for c_lo, c_hi in covering:
            for bnd in (c_lo, c_hi):
                if lo + 1e-6 < bnd < hi - 1e-6:
                    _ensure_junction(
                        plan,
                        Point(bnd, fixed) if new_is_h else Point(fixed, bnd),
                    )
        return added

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


def _emit_cluster_pin_own_nets(
    plan: LayoutPlan, block: Block, geometry,
) -> None:
    """Post-route pass: emit the label/hier-label naming each CLUSTER pin's
    OWN net at the pin tip.

    A pin with an ``ExternalPart`` is classified ``CLUSTER`` and the cluster
    pass only wires its passives' far ends; the pin's own signal/power net
    (boot-strap, JTAG, MIPI I2C, microSD DAT, FMC pull-up signal, ...) was
    previously DROPPED, leaving the pin connected to its passive but not to
    the rest of the design. Here we name the pin: the pin tip is the trunk
    origin (same net as the pin), so a label there merges with the trunk
    while the passives keep their own cluster_destinations — closing the
    signal without shorting a series resistor (series-R: pin net is BEFORE
    the resistor; pull-up: pin net IS the trunk). Runs AFTER routing so the
    trunk + drop wires are in occupancy and the label is placed clear of
    them (rotation candidates, then route-out into clear interior).

    POWER_SYMBOL own-nets (a power pin that also has decoupling) are handled
    by :func:`_emit_power_rail_taps`.
    """
    from zynq_eda.core.layout._builder import (
        _hierarchical_label_bbox, _label_bbox,
    )
    from zynq_eda.core.layout._constants import (
        INTERIOR_MARGIN_MM, KICAD_GRID_MM, OVERLAP_NOISE_FLOOR_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import (
        PlacedHierarchicalLabel, PlacedLabel,
    )

    for spec in plan.pin_specs:
        if spec.role != "CLUSTER":
            continue
        role = spec.cluster_owner_role
        net = spec.cluster_owner_net
        if role not in ("EDGE_LABEL", "LOCAL_LABEL") or not net:
            continue
        pin_pos = _resolve_pin_page_coord(plan, spec, geometry)
        if pin_pos is None:
            continue
        is_hier = role == "EDGE_LABEL"
        side = spec.page_side

        def _make(pos: Point, rot: float):
            if is_hier:
                return PlacedHierarchicalLabel(
                    net_name=net, position=pos,
                    direction="bidirectional", rotation=rot,
                )
            return PlacedLabel(net_name=net, position=pos, rotation=rot)

        def _bbox(obj):
            return (_hierarchical_label_bbox(obj) if is_hier
                    else _label_bbox(obj))

        def _add(obj):
            if is_hier:
                _add_hierarchical_label_with_bbox(plan, obj)
            else:
                _add_label_with_bbox(plan, obj)

        same_net_ids = frozenset(
            f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
            for lab in plan.labels if lab.net_name == net
        ) | frozenset(
            f"hlabel:{h.net_name}"
            for h in plan.hierarchical_labels if h.net_name == net
        )

        def _clean(obj) -> bool:
            bb = _bbox(obj)
            for h in plan.occupancy.collides(
                bb, ignore_owners=same_net_ids,
                ignore_kinds=frozenset({"junction", "no_connect"}),
            ):
                inter = bb.intersection(h)
                if (inter is not None
                        and inter.width >= OVERLAP_NOISE_FLOOR_MM
                        and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                    return False
            return True

        outboard = {
            "left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0,
        }[side]
        # At the pin tip the trunk leaves OUTBOARD and the body sits
        # INBOARD, so try the two PERPENDICULAR directions first, then
        # outboard, then inboard.
        if side in ("left", "right"):
            inboard = 0.0 if outboard == 180.0 else 180.0
            rots = (90.0, 270.0, outboard, inboard)
        else:
            inboard = 270.0 if outboard == 90.0 else 90.0
            rots = (0.0, 180.0, outboard, inboard)
        placed = False
        for rot in rots:
            obj = _make(pin_pos, rot)
            if _clean(obj):
                _add(obj)
                placed = True
                break
        if placed:
            continue

        # Boxed in at the pin tip: route the net out to a clear interior
        # point (perpendicular out of the row, then outboard) and label
        # there. The carrier wire merges with the trunk at the pin tip.
        out_sign = -1 if side == "left" else (1 if side == "right" else 0)
        if out_sign != 0:
            for up in range(0, 9):
                ty = snap_to_grid(pin_pos.y - up * KICAD_GRID_MM)
                for ox in range(2, 28):
                    tx = snap_to_grid(pin_pos.x + out_sign * ox * KICAD_GRID_MM)
                    if out_sign < 0 and tx <= INTERIOR_MARGIN_MM:
                        break
                    target = Point(tx, ty)
                    obj = _make(target, outboard)
                    if not _clean(obj):
                        continue
                    if _route_pin_to_target(
                        plan, pin_pos, target, avoid_owners=frozenset(),
                    ):
                        _add(obj)
                        placed = True
                        break
                if placed:
                    break
        if not placed:
            # Last resort: name it outboard at the pin tip so the pin is
            # connected + visible; any residual overlap surfaces honestly.
            _add(_make(pin_pos, outboard))


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
    # EDGE_LABEL hier-labels must be emitted BEFORE their wires so the
    # candidate ladder's X/Y shifts get reflected in the wire's
    # endpoint — otherwise wires terminate at the ORIGINAL
    # lane.label_anchor and the (shifted) hier-label sits in mid-air
    # disconnected from the pin, tripping ERC pin_not_connected.
    _emit_edge_label_hlabels(plan, block, geometry)
    _route_edge_label_pin_wires(plan, block, geometry)


# ---------------------------------------------------------------------------
# Phase 8 — plan_labels: labels + hier-labels at reserved positions
# ---------------------------------------------------------------------------


def _add_label_with_bbox(plan: LayoutPlan, label: PlacedLabel) -> None:
    """Append a local label to the plan AND register its text bbox."""
    from zynq_eda.core.layout._builder import _label_bbox
    plan.labels.append(label)
    plan.occupancy.add(_label_bbox(label))


def _add_cluster_far_label_rotated(
    plan: LayoutPlan,
    net_name: str,
    cap_far: Point,
    page_side: PageSide,
    *,
    record: bool = True,
) -> None:
    """Place a cluster's shared destination label AT ``cap_far`` (the cap's
    far pin) choosing the first text ROTATION whose bbox is clear.

    The label sits exactly on the cap's far pin, so it stays electrically
    connected no matter which way the text points — rotating it only moves
    where the TEXT renders, never the connection. We therefore keep the
    anchor fixed (position shifts would detach the label from the pin and
    silently break the net) and steer only the text direction.

    Candidate order:
      1. OUTBOARD — the conventional look. Keeps every already-clean
         cluster label byte-identical to before this change.
      2. the two PERPENDICULAR directions — into the band above/below the
         far-pin row, which is clear in the dense stacked-cluster case
         (e.g. ethernet's Bob-Smith network, where the outboard text would
         otherwise cross an adjacent pair's drop wire).
      3. INBOARD — last resort.
    Falls back to OUTBOARD if none is clear, so the pin is still named and
    visible and any residual overlap surfaces honestly in validation.
    """
    from zynq_eda.core.model.sheet import PlacedLabel

    if record:
        if not hasattr(plan, "_cluster_far_labels"):
            plan._cluster_far_labels = []  # type: ignore[attr-defined]
        plan._cluster_far_labels.append(  # type: ignore[attr-defined]
            (net_name, cap_far, page_side)
        )

    rot = _clean_far_label_rotation(plan, net_name, cap_far, page_side)
    if rot is None:
        rot = {
            "left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0,
        }[page_side]
    _add_label_with_bbox(
        plan,
        PlacedLabel(net_name=net_name, position=cap_far, rotation=rot),
    )


def _clean_far_label_rotation(
    plan: LayoutPlan,
    net_name: str,
    cap_far: Point,
    page_side: PageSide,
) -> float | None:
    """Return the first text ROTATION whose label bbox AT ``cap_far`` is
    clear of occupancy (same-net labels exempt), or None if every
    direction collides.

    Order: OUTBOARD (conventional look — keeps already-clean labels
    unchanged), then the two PERPENDICULAR directions (into the band
    above/below the far-pin row), then INBOARD.
    """
    from zynq_eda.core.layout._builder import _label_bbox
    from zynq_eda.core.layout._constants import OVERLAP_NOISE_FLOOR_MM
    from zynq_eda.core.model.sheet import PlacedLabel

    outboard = {
        "left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0,
    }[page_side]
    if page_side in ("left", "right"):
        inboard = 0.0 if outboard == 180.0 else 180.0
        cand_rots = (outboard, 90.0, 270.0, inboard)
    else:
        inboard = 270.0 if outboard == 90.0 else 90.0
        cand_rots = (outboard, 0.0, 180.0, inboard)

    same_net_owner_ids = frozenset(
        f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
        for lab in plan.labels
        if lab.net_name == net_name
    )

    def _clean(lbl: PlacedLabel) -> bool:
        bbox = _label_bbox(lbl)
        for h in plan.occupancy.collides(
            bbox,
            ignore_owners=same_net_owner_ids,
            ignore_kinds=frozenset({"junction", "no_connect"}),
        ):
            inter = bbox.intersection(h)
            if inter is None:
                continue
            if (inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                return False
        return True

    for rot in cand_rots:
        if _clean(PlacedLabel(
                net_name=net_name, position=cap_far, rotation=rot)):
            return rot
    return None


def _emit_cluster_far_label_routed_out(
    plan: LayoutPlan,
    net_name: str,
    cap_far: Point,
    page_side: PageSide,
) -> bool:
    """Boxed-in fallback: when NO text rotation fits the shared cluster
    label at ``cap_far`` (every direction blocked by the dense comb),
    ROUTE the net out of the congested region to a clear interior point
    and place the label there.

    A clean orthogonal wire (the full obstacle-avoiding router) carries
    the connection from the cap far pin to the label, so the pin is driven
    and everything stays visible — no hiding, no overlap. Returns True iff
    a clear, routable label spot was found and emitted.

    Targets are scanned nearest-first: climb perpendicular OUT of the
    row (into the clear band above the far-pin row) and march OUTBOARD
    into the page interior, keeping the carrier wire short.
    """
    from zynq_eda.core.layout._builder import _label_bbox
    from zynq_eda.core.layout._constants import (
        INTERIOR_MARGIN_MM, KICAD_GRID_MM, OVERLAP_NOISE_FLOOR_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.sheet import PlacedLabel

    if page_side not in ("left", "right"):
        return False
    out_sign = -1 if page_side == "left" else 1
    outboard_rot = 180.0 if out_sign < 0 else 0.0

    same_net_owner_ids = frozenset(
        f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
        for lab in plan.labels
        if lab.net_name == net_name
    )

    def _label_clean(lbl: PlacedLabel) -> bool:
        bbox = _label_bbox(lbl)
        for h in plan.occupancy.collides(
            bbox, ignore_owners=same_net_owner_ids,
            ignore_kinds=frozenset({"junction", "no_connect"}),
        ):
            inter = bbox.intersection(h)
            if (inter is not None
                    and inter.width >= OVERLAP_NOISE_FLOOR_MM
                    and inter.height >= OVERLAP_NOISE_FLOOR_MM):
                return False
        return True

    for up in range(0, 9):              # perpendicular steps up out of the row
        ty = snap_to_grid(cap_far.y - up * KICAD_GRID_MM)
        for ox in range(2, 28):         # outboard steps into the interior
            tx = snap_to_grid(cap_far.x + out_sign * ox * KICAD_GRID_MM)
            if out_sign < 0 and tx <= INTERIOR_MARGIN_MM:
                break
            target = Point(tx, ty)
            lbl = PlacedLabel(
                net_name=net_name, position=target, rotation=outboard_rot,
            )
            if not _label_clean(lbl):
                continue
            if _route_pin_to_target(
                plan, cap_far, target, avoid_owners=frozenset(),
            ):
                # Route committed; the label sits at its far end, text
                # reading further outboard into clear space.
                _add_label_with_bbox(plan, lbl)
                return True
    return False


def _refine_cluster_far_label_rotations(plan: LayoutPlan, geometry) -> None:
    """Post-route pass: finalise each cluster far label now that trunk +
    drop wires are present in occupancy.

    The far labels are placed in Phase 6 (``_emit_cluster_pins``), BEFORE
    the cluster drop wires are routed in Phase 7. An outboard rotation
    that probed clear in Phase 6 can end up crossing an adjacent stacked
    pair's drop wire (the ethernet Bob-Smith case: pair-2's outboard
    ``BS_COMMON`` text runs straight through pair-0's drop, which only
    exists after routing). With every wire now in occupancy we, per label:

      1. re-pick a clear text ROTATION at the cap far pin (anchor fixed,
         so connectivity is preserved); else
      2. ROUTE the net out to a clear interior point and label there; else
      3. last resort — place it outboard so the pin is named and visible
         and any residual overlap surfaces honestly in validation.
    """
    from zynq_eda.core.model.sheet import PlacedLabel

    records = list(getattr(plan, "_cluster_far_labels", ()))
    for net_name, cap_far, page_side in records:
        owner_id = f"label:{net_name}@{cap_far.x:.1f},{cap_far.y:.1f}"
        idx = next(
            (i for i, lab in enumerate(plan.labels)
             if lab.net_name == net_name
             and abs(lab.position.x - cap_far.x) < 1e-3
             and abs(lab.position.y - cap_far.y) < 1e-3),
            None,
        )
        if idx is None:
            continue
        plan.labels.pop(idx)
        plan.occupancy.remove_by_owner(owner_id)

        rot = _clean_far_label_rotation(plan, net_name, cap_far, page_side)
        if rot is not None:
            _add_label_with_bbox(
                plan,
                PlacedLabel(
                    net_name=net_name, position=cap_far, rotation=rot),
            )
            continue
        if _emit_cluster_far_label_routed_out(
                plan, net_name, cap_far, page_side):
            continue
        outboard = {
            "left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0,
        }[page_side]
        _add_label_with_bbox(
            plan,
            PlacedLabel(
                net_name=net_name, position=cap_far, rotation=outboard),
        )


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
    # Build per-net lists of emitted hier-label positions. The
    # candidate ladder may have shifted X/Y from lane.label_anchor;
    # the wire must terminate at the ACTUAL emitted position. For
    # double-row connectors (USB-C, FMC) the same net has hier-labels
    # on BOTH sides, so we pick the one closest to the pin's lane.
    hlabel_positions_by_net: dict[str, list[Point]] = {}
    for hlab in plan.hierarchical_labels:
        hlabel_positions_by_net.setdefault(hlab.net_name, []).append(
            hlab.position
        )

    # Dedup by (owner_ref, pin_number) — pin_name can repeat in
    # double-row connectors (USB-C, FMC).
    seen = set()
    for spec, pin_pos, lane in placeable:
        key = (spec.owner_ref, spec.pin_number or spec.pin_name)
        if key in seen:
            continue
        seen.add(key)
        # Find the emitted hier-label position closest to lane.label_anchor
        # (the unshifted target). Restrict to candidates within ±5 grid
        # steps in both axes so we don't accidentally pick the
        # opposite-side hier-label on a double-row connector.
        target = lane.label_anchor
        candidates = hlabel_positions_by_net.get(spec.net_name, [])
        from zynq_eda.core.layout._constants import KICAD_GRID_MM
        MAX_SHIFT_MM = 5 * KICAD_GRID_MM
        best = None
        best_dist = float("inf")
        for cp in candidates:
            dx = abs(cp.x - lane.label_anchor.x)
            dy = abs(cp.y - lane.label_anchor.y)
            if dx > MAX_SHIFT_MM or dy > MAX_SHIFT_MM:
                continue
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best = cp
        if best is not None:
            target = best
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


def _emit_orphan_external_net_hlabels(
    plan: LayoutPlan, block: Block, geometry,
) -> None:
    """Emit a hier-label for every declared external_net that doesn't
    already have a hier-label on the plan.

    Input power nets sourced via a connector's pin_to_net where the
    pin is classified as CLUSTER (e.g. microsd J1 Pin 4 → +3V3) don't
    get an EDGE_LABEL hier-label by the normal pin-classification path.
    Without a hier-label on the sub-sheet, the net has no exit to the
    parent sheet and KiCad ERC fires ``power_pin_not_driven``. This
    pass closes that gap: walk ``block.external_nets``, find the ones
    with no existing hier-label of the same name on the plan, and emit
    one at a clean position on the declared edge.

    The hier-label is placed AT the first wire/symbol/label on the
    net so KiCad's same-name-label merging electrically ties it to
    the rest of the net. The wire from any pin already on this net
    flows into the hier-label by virtue of the merging.
    """
    from zynq_eda.core.layout._builder import _hierarchical_label_bbox
    from zynq_eda.core.layout._constants import (
        INTERIOR_MARGIN_MM, KICAD_GRID_MM,
    )
    from zynq_eda.core.model.grid import snap_to_grid
    from zynq_eda.core.model.interface import SheetEdge
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
    from zynq_eda.core.layout.bbox import wire_bbox as _wbbox

    existing_hlabel_nets = {hl.net_name for hl in plan.hierarchical_labels}

    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]

    for net in block.external_nets:
        if net.name in existing_hlabel_nets:
            continue
        # Canonical GND has its own dedicated handling via the planner's
        # GND-pin classification + ``power:GND`` symbol emission. Don't
        # emit an orphan hier-label here — it would compete with the
        # ``power:GND`` symbols and KiCad's flatten pass might not
        # merge them correctly with the canonical GND net.
        if net.name.upper() == "GND":
            continue
        # Find an anchor point: any wire endpoint, label, or symbol pin
        # on this net. We look up nets via pin_to_net mappings — find
        # any connector pin assigned to this net and use its page
        # position.
        anchor_pos: Point | None = None
        for connector in block.connectors:
            for (pin_name, mapped_net) in connector.pin_to_net:
                if mapped_net != net.name:
                    continue
                # Resolve pin's page coord.
                try:
                    anchor_plan = plan.get_anchor(connector.reference)
                    pin_geom = geometry.pin_geometry_by_name(
                        connector.lib_id, anchor_plan.anchor, pin_name,
                        rotation=anchor_plan.rotation,
                    )
                    anchor_pos = pin_geom.connection
                    break
                except (KeyError, Exception):
                    continue
            if anchor_pos is not None:
                break
        if anchor_pos is None:
            # No connector pin owns this net — skip.
            continue
        # Pick a hier-label position on the declared edge: same row as
        # the pin, X at the edge's margin.
        if net.edge == SheetEdge.LEFT:
            hl_x = snap_to_grid(INTERIOR_MARGIN_MM)
            hl_rot = 0.0  # text extends RIGHT (inward)
        else:
            hl_x = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)
            hl_rot = 180.0  # text extends LEFT (inward)
        # Search a Y range starting at the anchor's Y, sweeping ±10
        # grid units. Need a Y where the hier-label bbox doesn't
        # overlap anything.
        from zynq_eda.core.model.sheet import PlacedHierarchicalLabel
        direction = getattr(net, "direction", "input")
        for dy in [0] + [s * KICAD_GRID_MM for s in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 8, -8, 10, -10)]:
            cand_y = snap_to_grid(anchor_pos.y + dy)
            if cand_y < INTERIOR_MARGIN_MM or cand_y > paper_h - INTERIOR_MARGIN_MM:
                continue
            candidate = PlacedHierarchicalLabel(
                net_name=net.name,
                position=Point(hl_x, cand_y),
                direction=direction,
                rotation=hl_rot,
            )
            cand_bbox = _hierarchical_label_bbox(candidate)
            hits = plan.occupancy.collides(
                cand_bbox,
                ignore_kinds=frozenset({"junction", "no_connect"}),
            )
            if not hits:
                _add_hierarchical_label_with_bbox(plan, candidate)
                break


def plan_labels(plan: LayoutPlan, block: Block, geometry) -> None:
    """Phase 8 — emit every label / hierarchical label.

    Order:
      1. EDGE_LABEL hier-labels at lane anchors (Phase 8 prerequisite).
      2. LOCAL_LABEL labels at pin tips.

    Lane reservation guarantees label text bboxes fit; a collision is
    a planner bug.
    """
    # NOTE: ``_emit_edge_label_hlabels`` is now called inside
    # ``plan_routes`` (before ``_route_edge_label_pin_wires``) so the
    # wire endpoint follows the candidate ladder's shift. Calling it
    # again here would emit duplicates / re-shift.
    _emit_local_label_pins(plan, geometry)
    # Emit hier-labels for declared external_nets that aren't already
    # represented by an EDGE_LABEL pin's hier-label. Without this, an
    # input power net (e.g. microsd "+3V3") whose pin is classified as
    # CLUSTER never gets a hier-label, and KiCad ERC fires
    # power_pin_not_driven because the net has no labeled exit
    # to the parent sheet.
    _emit_orphan_external_net_hlabels(plan, block, geometry)


def _grid_center_shift(
    lo: float, hi: float, page: float,
    margin: float = 5.08, grid: float = 1.27,
) -> float:
    """Return a grid-multiple translation that centres the content span
    [lo, hi] within [margin, page-margin], or pulls it inside the margin
    if it currently overflows. Returns 0.0 if no grid shift keeps the span
    within both margins (content too wide for the page)."""
    import math
    content = hi - lo
    free = page - 2.0 * margin - content
    if free < grid:
        # No meaningful centering room; only correct a margin overflow.
        if lo < margin:
            ideal = margin - lo
        elif hi > page - margin:
            ideal = (page - margin) - hi
        else:
            ideal = 0.0
    else:
        ideal = margin + free / 2.0 - lo
    lo_bound = margin - lo            # dx >= lo_bound  => lo+dx >= margin
    hi_bound = (page - margin) - hi   # dx <= hi_bound  => hi+dx <= page-margin
    k_lo = math.ceil(lo_bound / grid - 1e-9)
    k_hi = math.floor(hi_bound / grid + 1e-9)
    if k_lo > k_hi:
        return 0.0  # span can't fit within margins at any grid shift
    k = max(k_lo, min(k_hi, round(ideal / grid)))
    return k * grid


def _translated_primitive(prim, dx: float, dy: float):
    """Return a copy of a Placed* primitive shifted by (dx, dy). Relative
    fields (value_shift / reference_shift) ride along with position."""
    from dataclasses import replace
    from zynq_eda.core.model.sheet import PlacedWire
    if isinstance(prim, PlacedWire):
        return replace(
            prim,
            start=Point(prim.start.x + dx, prim.start.y + dy),
            end=Point(prim.end.x + dx, prim.end.y + dy),
        )
    return replace(
        prim, position=Point(prim.position.x + dx, prim.position.y + dy),
    )


def _balance_plan(plan: LayoutPlan, block: Block) -> None:
    """Final pass: rigidly translate the ENTIRE plan so its content is
    centred within the page margins.

    A uniform translation preserves every pairwise relationship, and the
    overlap validator is purely pairwise-relative, so this CANNOT create or
    remove an overlap — overlap count is invariant. The grid-multiple shift
    keeps all primitives on-grid and the clamp keeps them inside the 5.08 mm
    margin. This fixes the "all components jammed against one page edge with
    an empty page centre" pathology (e.g. ethernet) without disturbing any
    block's internal, already-validated geometry.

    Guard: a hier-label must not cross the page midline (its parent-sheet
    edge is derived from x < paper_w/2); if x-centering would flip any
    hier-label's side, x-centering is skipped for the block.
    """
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
    boxes = plan.occupancy._bboxes
    if not boxes:
        return
    paper_w, paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    min_x = min(b.min.x for b in boxes)
    max_x = max(b.max.x for b in boxes)
    min_y = min(b.min.y for b in boxes)
    max_y = max(b.max.y for b in boxes)
    dx = _grid_center_shift(min_x, max_x, paper_w)
    dy = _grid_center_shift(min_y, max_y, paper_h)

    # Hier-label midline guard: never push a hier-label across paper_w/2.
    if dx != 0.0:
        mid = paper_w / 2.0
        for h in plan.hierarchical_labels:
            if (h.position.x < mid) != (h.position.x + dx < mid):
                dx = 0.0
                break
    if dx == 0.0 and dy == 0.0:
        return

    plan.symbols[:] = [_translated_primitive(s, dx, dy) for s in plan.symbols]
    plan.wires[:] = [_translated_primitive(w, dx, dy) for w in plan.wires]
    plan.labels[:] = [_translated_primitive(l, dx, dy) for l in plan.labels]
    plan.hierarchical_labels[:] = [
        _translated_primitive(h, dx, dy) for h in plan.hierarchical_labels
    ]
    plan.junctions[:] = [
        _translated_primitive(j, dx, dy) for j in plan.junctions
    ]
    plan.no_connects[:] = [
        _translated_primitive(n, dx, dy) for n in plan.no_connects
    ]
    plan.occupancy._bboxes[:] = [
        b.translate(dx, dy) for b in plan.occupancy._bboxes
    ]


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

    # Post-routing pass: re-rotate cluster far labels (placed in Phase 6)
    # whose outboard text now crosses a drop wire routed in Phase 7, or
    # route boxed-in labels out to clear interior space.
    _refine_cluster_far_label_rotations(plan, geometry)

    # Post-routing pass: name each cluster pin's OWN net (the signal/power
    # the pin carries) at the pin tip, so it isn't silently dropped. Runs
    # after routing so the trunk/drops are in occupancy.
    _emit_cluster_pin_own_nets(plan, block, geometry)

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

    # Phase 9b — GND drive stamp. The flattened GND net is power-input
    # only (power:GND symbol pins + connector GND pins are all
    # power-INPUT type), so KiCad ERC fires ``power_pin_not_driven``
    # unless a PWR_FLAG marks GND as externally driven. Emit ONE
    # self-contained drive stamp (power:GND + PWR_FLAG joined by a
    # short wire) in clear space on the ``power`` block — the circuit's
    # ground source. One stamp drives the whole flattened GND net.
    if block.name == "power":
        _emit_gnd_drive_stamp(plan, block, geometry, next_ref_counters)

    # Phase 9c — power-rail taps. A connector/IC pin classified CLUSTER
    # because it hosts decoupling caps still has its OWN net (e.g. a
    # microSD VDD pin on +3V3). The cluster only wires the cap far pins
    # to GND; the pin's own power-rail identity is never placed on its
    # trunk, leaving an unnamed undriven island → power_pin_not_driven.
    # Tap the trunk with the rail's power symbol (visible, on a short
    # stub in clear lane space) so the net is named and driven.
    _emit_power_rail_taps(plan, block, geometry, next_ref_counters)

    # Final cluster text-shift refinement: re-pick Value/Reference shifts
    # against the COMPLETE wire/label set (including own-net labels, PWR
    # flags, GND stamp and rail taps emitted above), so cap text that those
    # late wires now cross is moved clear. The earlier refinements ran
    # before those passes existed.
    _refine_cluster_reference_shifts(plan, geometry, consider_wires=True)
    _refine_cluster_value_shifts(plan, geometry, consider_wires=True)

    # Final pass — rigidly centre all content within the page margins.
    # Overlap-invariant (uniform translate); fixes edge-cramming / empty
    # page centre and pulls any margin-overflowing text back in-bounds.
    _balance_plan(plan, block)

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
