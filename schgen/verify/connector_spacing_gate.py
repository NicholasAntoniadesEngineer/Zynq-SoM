from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.generate.floorplan import OVERMOLD_SIDE_GAP
from schgen.generate.pcb import (
    CONN_MATING_FACE,
    PcbModel,
    _inst_pad_bbox,
)

_FAMILY_MIN_GAP_MM: dict[str, float] = {
    "HDMI-019S": 18.0,
}

_FAMILY_SIDE_GAP_MM: dict[str, float] = {
    "HDMI-019S": OVERMOLD_SIDE_GAP,
}

_FAMILY_OF: dict[str, str] = {mpn: mpn for mpn in _FAMILY_MIN_GAP_MM}

_SAME_BAND_FRAC = 0.5


def _conn_mpn(inst) -> str | None:
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def _overlap_1d_py(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    if not _nat.loaded():
        raise RuntimeError("native overlap_1d required")
    got = float(_nat.module().overlap_1d(a0, a1, b0, b1))
    if _nat.trace():
        ref = _overlap_1d_py(a0, a1, b0, b1)
        if got != ref:
            raise AssertionError(
                "native overlap_1d DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _same_edge_gap_py(a: tuple, b: tuple) -> tuple[str, float] | None:
    ox = _overlap_1d_py(a[0], a[2], b[0], b[2])
    oy = _overlap_1d_py(a[1], a[3], b[1], b[3])
    wx = min(a[2] - a[0], b[2] - b[0])
    hy = min(a[3] - a[1], b[3] - b[1])
    same_x_band = wx > 0 and ox >= _SAME_BAND_FRAC * wx
    same_y_band = hy > 0 and oy >= _SAME_BAND_FRAC * hy
    if same_y_band and not same_x_band:
        return "x", max(a[0], b[0]) - min(a[2], b[2])
    if same_x_band and not same_y_band:
        return "y", max(a[1], b[1]) - min(a[3], b[3])
    return None


def _same_edge_gap(a: tuple, b: tuple) -> tuple[str, float] | None:
    if not _nat.loaded():
        raise RuntimeError("native same_edge_gap required")
    hit = _nat.module().same_edge_gap(a, b, _SAME_BAND_FRAC)
    got = None if hit is None else (str(hit[0]), float(hit[1]))
    if _nat.trace():
        ref = _same_edge_gap_py(a, b)
        if got != ref:
            raise AssertionError(
                "native same_edge_gap DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


@dataclass
class SpacingResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    pairs: list[tuple] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        from schgen.verify._native_pcb import summary
        return summary("connector-spacing", self)


def check(model: PcbModel, *, prepared=None) -> SpacingResult:
    from schgen.verify._native_pcb import prepare
    return SpacingResult(**_nat.module().pcb_connector_spacing((prepare(model) if prepared is None else prepared)))
