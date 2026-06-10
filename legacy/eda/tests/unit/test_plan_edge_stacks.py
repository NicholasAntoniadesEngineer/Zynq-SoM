"""Unit tests for plan_edge_stacks (Phase 3 — row packer).

Tests cover:
- Single-row packing (fits all lanes on row 0).
- Y-conflict resolution (adjacent pins push apart to different rows).
- MAX_LANE_ROWS overflow → structured diagnostic with file path.
- Per-row budget shrinks for outer rows.
- Empty / single-lane edge cases.
- Cross-block invariant: every carrier block (except known-overflow ones)
  packs within MAX_LANE_ROWS.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout._constants import (
    LANE_ROW_PITCH_MM,
    MAX_LANE_ROWS,
)
from zynq_eda.core.layout.plan import (
    EdgeStack,
    LaneAllocation,
    plan_edge_stacks,
    plan_lane_widths,
    plan_pin_specs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lane(
    pin_name: str,
    *,
    width: float = 10.0,
    y_lo: float = 0.0,
    y_hi: float = 0.0,
    edge: str = "right",
    owner_ref: str = "U1",
    lane_kind: str = "hier_label",
) -> LaneAllocation:
    return LaneAllocation(
        owner_ref=owner_ref,
        pin_name=pin_name,
        edge=edge,
        row_index=-1,
        x_start=0.0,
        x_end=width,
        y_band_lo=y_lo,
        y_band_hi=y_hi,
        lane_kind=lane_kind,
        label_text_extent_mm=width,
    )


class _StubGeometry:
    """Minimal geometry stub for tests not requiring real bbox lookups."""

    def bounding_box(self, lib_id, rotation=0.0):
        from types import SimpleNamespace
        return SimpleNamespace(width=12.7, height=20.32)


def _make_block(
    name: str = "test",
    *,
    paper_size: str = "A3",
    ics=(),
    connectors=(),
    external_nets=(),
):
    from zynq_eda.core.model.block import Block
    return Block(
        name=name, title=name, paper_size=paper_size,
        ics=tuple(ics), connectors=tuple(connectors),
        external_nets=tuple(external_nets),
    )


def _carrier_blocks_and_geometry():
    from zynq_eda.core.layout.geometry import SymbolGeometryCache
    from zynq_eda.projects.carrier.board import (
        SHARED_SYMBOL_LIBRARIES,
        build_blocks,
    )
    cache = SymbolGeometryCache()
    cache.register_libraries(SHARED_SYMBOL_LIBRARIES)
    blocks = {b.name: b for b in build_blocks()}
    return blocks, cache


# ---------------------------------------------------------------------------
# Single-row packing
# ---------------------------------------------------------------------------


def test_plan_edge_stacks_empty_input_returns_empty():
    block = _make_block()
    geometry = _StubGeometry()
    assert plan_edge_stacks((), block, geometry) == ()


def test_plan_edge_stacks_single_lane_fits_row_0():
    block = _make_block()
    geometry = _StubGeometry()
    lane = _lane("P1", width=20.0, y_lo=50.0, y_hi=50.0)
    stacks = plan_edge_stacks((lane,), block, geometry)
    assert len(stacks) == 1
    assert stacks[0].num_rows == 1
    assert stacks[0].rows[0][0].row_index == 0
    assert stacks[0].rows[0][0].pin_name == "P1"


def test_plan_edge_stacks_well_separated_lanes_share_row():
    """Two lanes at Y positions far apart (no bbox overlap) sit on
    the same row 0."""
    block = _make_block()
    geometry = _StubGeometry()
    lane_a = _lane("A", width=20.0, y_lo=50.0, y_hi=50.0)
    lane_b = _lane("B", width=20.0, y_lo=70.0, y_hi=70.0)
    stacks = plan_edge_stacks((lane_a, lane_b), block, geometry)
    assert stacks[0].num_rows == 1
    assert stacks[0].num_lanes == 2


def test_plan_edge_stacks_adjacent_pins_split_to_rows():
    """Two lanes at adjacent Y (e.g. 2.54 mm apart on standard pin pitch)
    whose label Y-bands overlap get pushed to separate rows."""
    block = _make_block()
    geometry = _StubGeometry()
    lane_a = _lane("A", width=20.0, y_lo=50.0, y_hi=50.0)
    lane_b = _lane("B", width=20.0, y_lo=50.0, y_hi=50.0)
    stacks = plan_edge_stacks((lane_a, lane_b), block, geometry)
    # Both at the same Y → Y-band conflicts → must split.
    assert stacks[0].num_rows == 2
    assert stacks[0].num_lanes == 2


# ---------------------------------------------------------------------------
# MAX_LANE_ROWS overflow
# ---------------------------------------------------------------------------


def test_plan_edge_stacks_overflow_raises_with_block_path():
    """Lanes that don't fit within MAX_LANE_ROWS hard-fail with a
    structured diagnostic naming the user's block.py file."""
    block = _make_block(name="stressblock")
    geometry = _StubGeometry()
    # Build MAX_LANE_ROWS+1 lanes all at the same Y so each forces
    # a new row.
    lanes = tuple(
        _lane(f"P{i}", width=20.0, y_lo=50.0, y_hi=50.0)
        for i in range(MAX_LANE_ROWS + 1)
    )
    with pytest.raises(RuntimeError) as excinfo:
        plan_edge_stacks(lanes, block, geometry)
    msg = str(excinfo.value)
    assert "plan_edge_stacks" in msg
    assert "stressblock.py" in msg
    assert f"MAX_LANE_ROWS={MAX_LANE_ROWS}" in msg
    # Diagnostic must offer the three prioritised fixes.
    assert "1." in msg and "2." in msg and "3." in msg


def test_plan_edge_stacks_oversize_lane_hard_fails():
    """A single lane wider than the per-row budget hard-fails (no row
    count can rescue it)."""
    block = _make_block(name="oversize")
    geometry = _StubGeometry()
    # A lane wider than half the page (A3 landscape = 420 mm, budget ≈ 195 mm).
    huge_lane = _lane("HUGE", width=300.0, y_lo=50.0, y_hi=50.0)
    with pytest.raises(RuntimeError) as excinfo:
        plan_edge_stacks((huge_lane,), block, geometry)
    msg = str(excinfo.value)
    assert "oversize.py" in msg
    assert "HUGE" in msg


def test_plan_edge_stacks_respects_max_rows_override():
    """Passing max_lane_rows=5 allows 5 rows even when MAX_LANE_ROWS=3."""
    block = _make_block()
    geometry = _StubGeometry()
    lanes = tuple(
        _lane(f"P{i}", width=20.0, y_lo=50.0, y_hi=50.0) for i in range(5)
    )
    stacks = plan_edge_stacks(lanes, block, geometry, max_lane_rows=5)
    assert stacks[0].num_rows == 5
    assert stacks[0].num_lanes == 5


# ---------------------------------------------------------------------------
# Outer-row budget shrinks
# ---------------------------------------------------------------------------


def test_plan_edge_stacks_outer_row_has_less_budget():
    """Row N's effective budget is reduced by N * LANE_ROW_PITCH_MM.
    A lane that fits on row 0 but not row 1 should land on row 0 first."""
    block = _make_block()
    geometry = _StubGeometry()
    # First lane goes on row 0.
    lane_a = _lane("A", width=180.0, y_lo=50.0, y_hi=50.0)
    # Second lane at same Y → must go on row 1. Width must be
    # ≤ budget - LANE_ROW_PITCH_MM.
    # A3 budget = (420 - 30.48 - 12.7)/2 = 188.41. Row 1 budget =
    # 188.41 - 20.32 = 168.09.
    lane_b = _lane("B", width=160.0, y_lo=50.0, y_hi=50.0)
    stacks = plan_edge_stacks((lane_a, lane_b), block, geometry)
    assert stacks[0].num_rows == 2
    assert stacks[0].rows[0][0].pin_name == "A"
    assert stacks[0].rows[1][0].pin_name == "B"


# ---------------------------------------------------------------------------
# Carrier-wide invariant
# ---------------------------------------------------------------------------


def test_plan_edge_stacks_carrier_blocks_either_pack_or_diagnose():
    """For every carrier block, plan_edge_stacks either succeeds within
    MAX_LANE_ROWS or raises a RuntimeError with the standard diagnostic.

    Blocks that succeed are validated below — every lane has a row_index
    assigned, lanes on same (owner, edge, row) don't overlap in Y.
    Blocks that raise are recorded so PR 5 can edit them.
    """
    blocks, geometry = _carrier_blocks_and_geometry()
    overflowed: list[str] = []
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)
        lanes = plan_lane_widths(specs, block, geometry)
        try:
            stacks = plan_edge_stacks(lanes, block, geometry)
        except RuntimeError as exc:
            assert "plan_edge_stacks" in str(exc)
            assert f"{block_name}.py" in str(exc)
            overflowed.append(block_name)
            continue

        # Validate packed stacks.
        for stack in stacks:
            for r, row in enumerate(stack.rows):
                for lane in row:
                    assert lane.row_index == r
                # Lanes within a row don't overlap in Y.
                from zynq_eda.core.layout.plan import (
                    _label_y_band_for_lane,
                    _y_bands_overlap,
                )
                for i in range(len(row)):
                    for j in range(i + 1, len(row)):
                        a_lo, a_hi = _label_y_band_for_lane(row[i])
                        b_lo, b_hi = _label_y_band_for_lane(row[j])
                        assert not _y_bands_overlap(
                            a_lo, a_hi, b_lo, b_hi, pad_mm=0.0,
                        ), (
                            f"block {block_name}: lanes "
                            f"{row[i].pin_name} and {row[j].pin_name} "
                            f"overlap in Y on row {r}"
                        )

    # Print which blocks overflowed for PR 5 inspection.
    if overflowed:
        print(f"\nblocks needing PR 5 edits: {overflowed}")
