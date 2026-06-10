"""Single source of truth for a placed symbol's text obstacle bboxes.

A symbol contributes more than its body to the page: KiCad draws its pin
names, pin numbers, and property text (Reference like ``C103``, Value like
``100n``). These are first-class obstacles — a wire or label crossing them
is a visible collision the overlap validator flags. Historically the
planner registered them inside a ``try/except: return`` that *silently
dropped the entire text set* if geometry raised for any reason, blinding
placement and routing to that text while the validator still measured it —
a guaranteed planner/validator divergence and a silent softening.

This helper centralizes the computation and FAILS LOUD: if geometry can't
build a symbol's text bboxes, the exception propagates. The caller (the
planner today; the router rewrite next) must surface it, never swallow it.
It mirrors exactly what :func:`zynq_eda.core.validate.overlap.validate_overlap`
measures — same ``value_shift`` *and* ``reference_shift`` — so a layout the
planner believes is clean is a layout the validator agrees is clean.
"""

from __future__ import annotations

from zynq_eda.core.layout.bbox import BBox
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.sheet import PlacedSymbol


def collect_text_bboxes(
    sym: PlacedSymbol,
    geometry: SymbolGeometryCache,
    *,
    owner_id: str | None = None,
) -> list[BBox]:
    """Return every intrinsic + property text bbox ``sym`` contributes.

    Raises whatever ``geometry`` raises — a symbol's text is never silently
    omitted from the obstacle set.
    """
    owner_id = owner_id or f"symbol:{sym.reference}"
    bboxes: list[BBox] = []
    bboxes.extend(
        geometry.intrinsic_pin_label_bboxes(
            sym.lib_id, sym.position, rotation=sym.rotation, owner_id=owner_id
        )
    )
    bboxes.extend(
        geometry.intrinsic_pin_number_bboxes(
            sym.lib_id, sym.position, rotation=sym.rotation, owner_id=owner_id
        )
    )
    bboxes.extend(
        geometry.property_text_bboxes(
            sym.lib_id,
            sym.position,
            rotation=sym.rotation,
            owner_id=owner_id,
            reference_override=sym.reference,
            value_override=sym.value,
            value_shift=sym.value_shift,
            reference_shift=sym.reference_shift,
        )
    )
    return bboxes
