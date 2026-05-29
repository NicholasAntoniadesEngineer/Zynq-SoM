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
    from zynq_eda.core.layout.plan import emit_plan, plan_block

    builder = BlockLayoutBuilder()
    plan = plan_block(block, geometry_cache)
    emit_plan(plan, builder)
    return builder.finalize(block, geometry_cache=geometry_cache)
