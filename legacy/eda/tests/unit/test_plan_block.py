"""Integration test for the top-level plan_block + plan_symbols (Phase 6).

These tests verify:
- plan_block runs end-to-end for every carrier block without raising.
- The resulting LayoutPlan has one PlacedSymbol per IC + per connector.
- Phase 6's no-body-overlap assertion holds for every carrier block.
- The plan's occupancy contains the expected symbol bboxes.

PR 7 only emits BODY symbols; cluster passives, GND symbols, power
symbols, and PWR_FLAGs are added in subsequent PRs that extend
plan_symbols.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout.plan import (
    LayoutPlan,
    emit_plan,
    plan_block,
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


def test_plan_block_runs_for_every_carrier_block():
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        # Must not raise — every block fits within MAX_LANE_ROWS=3 and
        # within page bounds.
        plan = plan_block(block, geometry)
        assert isinstance(plan, LayoutPlan)
        # Phase 6 emits at LEAST one PlacedSymbol per IC + connector
        # (additional symbols: power symbols at POWER_SYMBOL pins, GND
        # symbols at GND pins, PWR_FLAGs etc.).
        min_count = len(block.ics) + len(block.connectors)
        assert len(plan.symbols) >= min_count, (
            f"block {block_name}: expected at least {min_count} body "
            f"symbols, got {len(plan.symbols)}"
        )


def test_plan_block_anchor_count_matches_owners():
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        plan = plan_block(block, geometry)
        assert len(plan.anchors) == len(block.ics) + len(block.connectors)


def test_plan_block_pin_specs_total():
    """Total pin_specs equals total pins on every IC + connector."""
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        plan = plan_block(block, geometry)
        expected_total = 0
        for ic in block.ics:
            expected_total += sum(
                1 for _ in geometry.all_pins(ic.lib_id, rotation=0.0)
            )
        for conn in block.connectors:
            expected_total += sum(
                1 for _ in geometry.all_pins(
                    conn.lib_id, rotation=conn.rotation,
                )
            )
        assert len(plan.pin_specs) == expected_total, (
            f"block {block_name}: pin_specs has {len(plan.pin_specs)}, "
            f"expected {expected_total}"
        )


def test_emit_plan_dispatches_symbols_to_builder():
    """emit_plan calls builder.add_symbol once per plan.symbols entry."""
    from zynq_eda.core.layout._builder import BlockLayoutBuilder

    blocks, geometry = _carrier_blocks_and_geometry()
    block = blocks["power"]  # smallest IC-only block
    plan = plan_block(block, geometry)

    builder = BlockLayoutBuilder()
    emit_plan(plan, builder)
    assert len(builder.symbols) == len(plan.symbols)
    # Each emitted symbol matches one of the plan's symbols.
    for sym in plan.symbols:
        assert sym in builder.symbols


def test_plan_symbols_registers_bboxes_in_occupancy():
    """After Phase 6, the plan's occupancy contains at least one
    'symbol'-kind bbox per emitted symbol."""
    blocks, geometry = _carrier_blocks_and_geometry()
    block = blocks["power"]
    plan = plan_block(block, geometry)
    symbol_bboxes = [b for b in plan.occupancy if b.kind == "symbol"]
    assert len(symbol_bboxes) >= len(plan.symbols)
