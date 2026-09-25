from __future__ import annotations

import re
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.generate.pcb import (
    CONN_MATING_FACE,
    EDGE_FLUSH_MM,
    ORIGIN_X,
    ORIGIN_Y,
    PcbModel,
    _inst_courtyard,
    _mating_face_out_dir,
)

_OVERLAP_EPS = 0.5

_PASSIVE_PREFIX = ("R", "C", "L")
_BUTTON_PREFIX = ("SW",)
_COINCELL_PREFIX = ("BT",)
_TESTPOINT_PREFIX = ("TP",)


def _ref_prefix(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else ref


def _is_passive_under_som(ref: str) -> bool:
    p = _ref_prefix(ref)
    if ref.startswith(("RS", "RJ", "LED")):
        return False
    return p in _PASSIVE_PREFIX


def _is_control(ref: str) -> bool:
    return _ref_prefix(ref) in (_BUTTON_PREFIX + _COINCELL_PREFIX)


def _rect_overlap_area_py(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0.0, min(ay1, by1) - max(ay0, by0))
    return ox * oy


def _rect_overlap_area(a, b) -> float:
    if not _nat.loaded():
        raise RuntimeError("native overlap_area required")
    got = float(_nat.module().overlap_area(a, b))
    if _nat.trace():
        ref = _rect_overlap_area_py(a, b)
        if got != ref:
            raise AssertionError(
                "native overlap_area DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


@dataclass
class MechResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    n_connectors: int = 0
    connectors: list[tuple] = field(default_factory=list)
    bad_connectors: list[str] = field(default_factory=list)
    under_som: list[str] = field(default_factory=list)
    controls_under_som: list[str] = field(default_factory=list)
    top_under_som: list[str] = field(default_factory=list)
    face_top_on_bottom: list[str] = field(default_factory=list)
    n_face_top: int = 0
    som_core: tuple | None = None

    def summary(self) -> str:
        from schgen.verify._native_pcb import summary
        return summary("placement-mech", self)


def check(model: PcbModel, *, prepared=None) -> MechResult:
    from schgen.verify._native_pcb import prepare
    return MechResult(**_nat.module().pcb_placement_mech((prepare(model) if prepared is None else prepared)))
