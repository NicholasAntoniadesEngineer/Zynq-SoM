"""Per-block placement entry point.

Thin wrapper that runs the predictive layout planner. The actual work
lives in :mod:`zynq_eda.core.layout.plan` — see ``plan_block`` and
``emit_plan``. This module exists so the public callsite
``place_block(block, geometry_cache=...)`` is stable across the
pre-planner / planner transition.
"""

from __future__ import annotations

from zynq_eda.core.layout._builder import BlockLayoutBuilder
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.sheet import Sheet


def place_block(
    block: Block,
    *,
    geometry_cache: SymbolGeometryCache,
) -> Sheet:
    """Render a :class:`Block` into a placed :class:`Sheet`.

    Runs the predictive layout planner (``plan_block`` → ``emit_plan``).
    The planner computes every primitive's final position into a
    frozen ``LayoutPlan`` first, then mechanically walks it to emit
    symbols, wires, junctions, no-connects, and labels into a fresh
    :class:`BlockLayoutBuilder`. Validation runs after emission and
    must report ``bounds=0, overlap=0``; any error is a planner bug,
    not a recoverable condition.

    Args:
        block: The declarative block.
        geometry_cache: Pre-loaded symbol geometry cache.
    """
    from zynq_eda.core.layout.plan import (
        _compute_slot_overrides,
        emit_plan,
        plan_block,
    )
    from zynq_eda.core.validate.overlap import validate_overlap
    from zynq_eda.core.validate.page_bounds import validate_page_bounds

    def _build(plan) -> Sheet:
        builder = BlockLayoutBuilder()
        emit_plan(plan, builder)
        return builder.finalize(block, geometry_cache=geometry_cache)

    def _score(sheet: Sheet) -> tuple[int, int]:
        # (crowding/overlap findings, bounds findings) — lower is better.
        return (
            len(validate_overlap(sheet, geometry=geometry_cache, strict=False)),
            len(validate_page_bounds(sheet, geometry=geometry_cache)),
        )

    # Two-pass placement with a strict no-regression gate. Pass 1 lays the
    # whole sheet so the adaptive separator can see where every body /
    # hier-label / label sits; it then spreads crowded cluster cap-slots to
    # >= the visual clearance against all of them as fixed obstacles, and
    # pass 2 re-plans with the separated cap anchors (which BOTH placement
    # and routing read, so the wiring follows). The separator guarantees the
    # cap FOOTPRINTS clear, but the re-routed wires it can't model may, on a
    # dense sheet, create new crowding — so we only ADOPT pass 2 when it is
    # measurably no worse on both overlap and bounds, and never when it
    # raised. This makes the pass strictly an improvement-or-no-op per block;
    # it can never regress a sheet (the failure the Laws forbid).
    plan1 = plan_block(block, geometry_cache)
    sheet1 = _build(plan1)
    score1 = _score(sheet1)
    if score1[0] == 0:
        # Already free of overlap/crowding — separation can only no-op, so
        # skip the (expensive) second pass entirely. Most connector-only
        # sheets land here.
        return sheet1
    overrides = _compute_slot_overrides(plan1, block, geometry_cache)
    if not overrides:
        return sheet1
    try:
        sheet2 = _build(plan_block(block, geometry_cache, slot_overrides=overrides))
    except Exception:
        return sheet1
    return sheet2 if _score(sheet2) <= score1 else sheet1
