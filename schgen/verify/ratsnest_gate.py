from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core.config import CROSS_K
from schgen.generate.pcb import PcbModel

DISPERSION_MAX = 9.0
SMALL_N = 3


@dataclass
class RatsnestResult:
    ok: bool = True
    off_board: list[str] = field(default_factory=list)
    dispersed: list[str] = field(default_factory=list)
    clusters: list[tuple[str, int, float, float]] = field(default_factory=list)
    cross_mm: float = 0.0
    total_mm: float = 0.0
    n_cross: int = 0
    n_subsystems: int = 0
    cross_budget_mm: float = 0.0
    board_w: float = 0.0
    board_h: float = 0.0

    @property
    def cross_ratio(self) -> float:
        return (self.cross_mm / self.total_mm) if self.total_mm else 0.0

    @property
    def cross_ok(self) -> bool:
        return self.cross_mm <= self.cross_budget_mm

    def summary(self) -> str:
        from dataclasses import asdict
        from schgen.core import native
        return native.module().pcb_ratsnest_summary(asdict(self))


def dispersion_by_sheet(res: RatsnestResult) -> dict[str, float]:
    return {name: disp for name, _n, _area, disp in res.clusters}


def check(model: PcbModel, npp: dict | None = None,
          mst: dict | None = None, *, prepared=None) -> RatsnestResult:
    from schgen.core import native
    from schgen.verify._native_pcb import prepare
    return RatsnestResult(**native.module().pcb_ratsnest(
        prepare(model) if prepared is None else prepared, npp, mst, CROSS_K))
