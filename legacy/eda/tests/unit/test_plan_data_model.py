"""Unit tests for the predictive planner's data model (plan.py).

PR 1 of the predictive-layout-planner rewrite — only the dataclasses
exist yet. No call sites; these tests verify constructor invariants
(frozen-ness, __post_init__ validation, derived properties) so future
PRs can rely on the contracts.

See ``/Users/nicholasantoniades/.claude/plans/i-need-you-to-crystalline-fairy.md``
for the design these dataclasses implement.
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError, replace

from zynq_eda.core.layout.bbox import BBox, placeholder_symbol_bbox
from zynq_eda.core.layout.plan import (
    AnchorPlan,
    EdgeStack,
    LaneAllocation,
    LayoutPlan,
    PinSpec,
    emit_plan,
)
from zynq_eda.core.model.grid import Point


# ---------------------------------------------------------------------------
# PinSpec
# ---------------------------------------------------------------------------


def _good_pin_spec(**overrides) -> PinSpec:
    """Construct a PinSpec with default valid fields, overriding any."""
    base = dict(
        owner_kind="ic",
        owner_ref="U1",
        owner_lib_id="lib:Symbol",
        pin_name="OUT",
        pin_number="3",
        role="LOCAL_LABEL",
        net_name="MY_NET",
        page_side="right",
        pin_relative=Point(2.54, 0.0),
        cluster_slot_count=0,
        cluster_destinations=(),
    )
    base.update(overrides)
    return PinSpec(**base)


def test_pin_spec_minimal_valid():
    spec = _good_pin_spec()
    assert spec.owner_ref == "U1"
    assert spec.role == "LOCAL_LABEL"


def test_pin_spec_frozen():
    spec = _good_pin_spec()
    with pytest.raises(FrozenInstanceError):
        spec.owner_ref = "X"  # type: ignore[misc]


def test_pin_spec_rejects_bad_owner_kind():
    with pytest.raises(ValueError, match="owner_kind"):
        _good_pin_spec(owner_kind="board")


def test_pin_spec_rejects_bad_role():
    with pytest.raises(ValueError, match="role"):
        _good_pin_spec(role="MAGIC")


def test_pin_spec_rejects_bad_page_side():
    with pytest.raises(ValueError, match="page_side"):
        _good_pin_spec(page_side="northeast")


def test_pin_spec_nc_requires_empty_net_name():
    with pytest.raises(ValueError, match="NC pins"):
        _good_pin_spec(role="NC", net_name="X")


def test_pin_spec_nc_with_empty_net_ok():
    spec = _good_pin_spec(role="NC", net_name="")
    assert spec.role == "NC"


def test_pin_spec_cluster_requires_positive_slot_count():
    with pytest.raises(ValueError, match="cluster_slot_count"):
        _good_pin_spec(role="CLUSTER", cluster_slot_count=0,
                       cluster_destinations=())


def test_pin_spec_cluster_destinations_count_matches_slots():
    with pytest.raises(ValueError, match="cluster_destinations"):
        _good_pin_spec(role="CLUSTER", cluster_slot_count=2,
                       cluster_destinations=("GND",))


def test_pin_spec_cluster_valid_with_matched_slots():
    spec = _good_pin_spec(
        role="CLUSTER", cluster_slot_count=2,
        cluster_destinations=("GND", "GND"),
    )
    assert spec.cluster_slot_count == 2


def test_pin_spec_non_cluster_forbids_slots():
    with pytest.raises(ValueError, match="Non-CLUSTER"):
        _good_pin_spec(role="LOCAL_LABEL", cluster_slot_count=1,
                       cluster_destinations=("X",))


# ---------------------------------------------------------------------------
# LaneAllocation
# ---------------------------------------------------------------------------


def _good_lane(**overrides) -> LaneAllocation:
    base = dict(
        owner_ref="U1",
        pin_name="OUT",
        edge="right",
        row_index=0,
        x_start=0.0,
        x_end=10.0,
        y_band_lo=20.0,
        y_band_hi=22.0,
        lane_kind="hier_label",
    )
    base.update(overrides)
    return LaneAllocation(**base)


def test_lane_minimal_valid():
    lane = _good_lane()
    assert lane.width_mm == 10.0


def test_lane_frozen():
    lane = _good_lane()
    with pytest.raises(FrozenInstanceError):
        lane.row_index = 9  # type: ignore[misc]


def test_lane_rejects_bad_edge():
    with pytest.raises(ValueError, match="edge"):
        _good_lane(edge="diagonal")


def test_lane_rejects_bad_lane_kind():
    with pytest.raises(ValueError, match="lane_kind"):
        _good_lane(lane_kind="exotic")


def test_lane_rejects_inverted_x():
    with pytest.raises(ValueError, match="x_end"):
        _good_lane(x_start=10.0, x_end=5.0)


def test_lane_rejects_inverted_y_band():
    with pytest.raises(ValueError, match="y_band_hi"):
        _good_lane(y_band_lo=22.0, y_band_hi=20.0)


def test_lane_rejects_negative_text_extent():
    with pytest.raises(ValueError, match="label_text_extent_mm"):
        _good_lane(label_text_extent_mm=-1.0)


def test_lane_with_row_index_replaces_field():
    lane = _good_lane(row_index=-1)
    repacked = lane.with_row_index(2)
    assert repacked.row_index == 2
    assert lane.row_index == -1  # original unchanged
    # All other fields preserved.
    assert repacked.owner_ref == lane.owner_ref
    assert repacked.x_end == lane.x_end


def test_lane_width_mm_zero_allowed():
    lane = _good_lane(x_start=5.0, x_end=5.0, lane_kind="nc")
    assert lane.width_mm == 0.0


# ---------------------------------------------------------------------------
# EdgeStack
# ---------------------------------------------------------------------------


def test_edge_stack_empty_rows():
    stack = EdgeStack(
        owner_ref="U1", edge="left", rows=(), total_outboard_extent_mm=0.0,
    )
    assert stack.num_rows == 0
    assert stack.num_lanes == 0


def test_edge_stack_single_row():
    lane_a = _good_lane(pin_name="A", row_index=0, y_band_lo=10, y_band_hi=12)
    lane_b = _good_lane(pin_name="B", row_index=0, y_band_lo=14, y_band_hi=16)
    stack = EdgeStack(
        owner_ref="U1", edge="right",
        rows=((lane_a, lane_b),),
        total_outboard_extent_mm=lane_a.x_end,
    )
    assert stack.num_rows == 1
    assert stack.num_lanes == 2


def test_edge_stack_multi_row():
    row0 = (_good_lane(pin_name="A", row_index=0),)
    row1 = (_good_lane(pin_name="B", row_index=1),)
    stack = EdgeStack(
        owner_ref="U1", edge="right",
        rows=(row0, row1),
        total_outboard_extent_mm=10.0,
    )
    assert stack.num_rows == 2
    assert stack.num_lanes == 2


def test_edge_stack_rejects_lane_with_wrong_owner():
    bad_lane = _good_lane(owner_ref="U2", row_index=0)
    with pytest.raises(ValueError, match="belonging to"):
        EdgeStack(owner_ref="U1", edge="right", rows=((bad_lane,),),
                  total_outboard_extent_mm=10.0)


def test_edge_stack_rejects_lane_with_wrong_edge():
    bad_lane = _good_lane(edge="left", row_index=0)
    with pytest.raises(ValueError, match="edge"):
        EdgeStack(owner_ref="U1", edge="right", rows=((bad_lane,),),
                  total_outboard_extent_mm=10.0)


def test_edge_stack_rejects_lane_with_wrong_row_index():
    bad_lane = _good_lane(row_index=5)
    with pytest.raises(ValueError, match="row_index"):
        EdgeStack(owner_ref="U1", edge="right", rows=((bad_lane,),),
                  total_outboard_extent_mm=10.0)


def test_edge_stack_rejects_negative_extent():
    with pytest.raises(ValueError, match="total_outboard_extent_mm"):
        EdgeStack(owner_ref="U1", edge="right", rows=(),
                  total_outboard_extent_mm=-1.0)


# ---------------------------------------------------------------------------
# AnchorPlan
# ---------------------------------------------------------------------------


def _good_anchor(**overrides) -> AnchorPlan:
    base = dict(
        owner_ref="U1",
        owner_kind="ic",
        anchor=Point(100.0, 100.0),
        rotation=0.0,
        body_bbox_page=placeholder_symbol_bbox(
            Point(100.0, 100.0), owner_id="symbol:U1",
        ),
    )
    base.update(overrides)
    return AnchorPlan(**base)


def test_anchor_minimal_valid():
    a = _good_anchor()
    assert a.owner_ref == "U1"
    assert a.anchor.x == 100.0


def test_anchor_frozen():
    a = _good_anchor()
    with pytest.raises(FrozenInstanceError):
        a.owner_ref = "X"  # type: ignore[misc]


def test_anchor_rejects_bad_owner_kind():
    with pytest.raises(ValueError, match="owner_kind"):
        _good_anchor(owner_kind="board")


def test_anchor_rejects_bad_rotation():
    with pytest.raises(ValueError, match="rotation"):
        _good_anchor(rotation=45.0)


def test_anchor_accepts_canonical_rotations():
    for r in (0.0, 90.0, 180.0, 270.0):
        a = _good_anchor(rotation=r)
        assert a.rotation == r


# ---------------------------------------------------------------------------
# LayoutPlan
# ---------------------------------------------------------------------------


def test_layout_plan_default_empty():
    plan = LayoutPlan()
    assert plan.pin_specs == ()
    assert plan.lane_allocations == ()
    assert plan.edge_stacks == ()
    assert plan.anchors == ()
    assert plan.symbols == []
    assert plan.wires == []
    assert plan.labels == []
    assert plan.hierarchical_labels == []
    assert plan.junctions == []
    assert plan.no_connects == []
    assert len(plan) == 0


def test_layout_plan_len_sums_primitive_lists():
    from zynq_eda.core.model.sheet import PlacedJunction, PlacedNoConnect

    plan = LayoutPlan()
    plan.junctions.append(PlacedJunction(position=Point(0.0, 0.0)))
    plan.no_connects.append(PlacedNoConnect(position=Point(2.54, 0.0)))
    assert len(plan) == 2


def test_layout_plan_get_anchor_missing_hard_fails():
    plan = LayoutPlan()
    with pytest.raises(KeyError, match="no AnchorPlan"):
        plan.get_anchor("U99")


def test_layout_plan_get_anchor_returns_indexed():
    plan = LayoutPlan()
    a = _good_anchor()
    plan._anchor_by_ref[a.owner_ref] = a
    assert plan.get_anchor("U1") is a


def test_layout_plan_get_lane_missing_hard_fails():
    plan = LayoutPlan()
    with pytest.raises(KeyError, match="no LaneAllocation"):
        plan.get_lane("U1", "OUT")


def test_layout_plan_get_lane_returns_indexed():
    plan = LayoutPlan()
    lane = _good_lane()
    plan._lane_by_owner_pin[(lane.owner_ref, lane.pin_name)] = lane
    assert plan.get_lane("U1", "OUT") is lane


# ---------------------------------------------------------------------------
# emit_plan
# ---------------------------------------------------------------------------


def test_emit_plan_empty_plan_no_calls():
    """emit_plan on an empty plan must do nothing — and not raise."""

    class _RecordingBuilder:
        def __init__(self):
            self.calls = []
            self.junctions = []
            self.no_connects = []

        def add_symbol(self, sym):
            self.calls.append(("add_symbol", sym))

        def add_wire(self, wire):
            self.calls.append(("add_wire", wire))

        def add_label(self, lab):
            self.calls.append(("add_label", lab))

        def add_hierarchical_label(self, hlab):
            self.calls.append(("add_hier_label", hlab))

    builder = _RecordingBuilder()
    emit_plan(LayoutPlan(), builder)
    assert builder.calls == []
    assert builder.junctions == []
    assert builder.no_connects == []
