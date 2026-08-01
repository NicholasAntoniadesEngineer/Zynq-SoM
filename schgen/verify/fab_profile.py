from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.project import PROJECT_ROOT
from schgen.core.sexpr import Sym

REPO_ROOT = Path(__file__).resolve().parents[2]
_PCB = PROJECT_ROOT / "Zynq_Carrier.kicad_pcb"
_DRU = PROJECT_ROOT / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
_PRO = PROJECT_ROOT / "Zynq_Carrier.kicad_pro"


@dataclass(frozen=True)
class FabProfile:
    name: str
    min_trace_mm: float
    min_clearance_mm: float
    min_drill_mm: float
    min_via_dia_mm: float
    min_via_annular_mm: float
    min_hole_to_hole_mm: float
    source: str


JLCPCB_4L = FabProfile(
    name="JLCPCB standard 4-layer (1oz)",
    min_trace_mm=0.09,
    min_clearance_mm=0.09,
    min_drill_mm=0.15,
    min_via_dia_mm=0.25,
    min_via_annular_mm=0.075,
    min_hole_to_hole_mm=0.15,
    source="JLCPCB PCB Manufacturing & Assembly Capabilities "
           "(jlcpcb.com/capabilities/pcb-capabilities) + JLCPCB via/annular Q&A; "
           "retrieved 2026-07",
)


@dataclass
class BoardDemand:
    min_trace_mm: float | None = None
    min_clearance_mm: float | None = None
    min_drill_mm: float | None = None
    min_via_dia_mm: float | None = None
    min_via_annular_mm: float | None = None
    min_hole_to_hole_mm: float | None = None
    pro_via_annular_mm: float | None = None
    n_segments: int = 0
    n_vias: int = 0
    n_drills: int = 0


_NUM = r"([-+]?\d*\.?\d+)"
_DRU_TRACK = re.compile(r"track_width\s*\(min\s*" + _NUM + r"mm")
_DRU_CLEAR = re.compile(r"\bclearance\s*\(min\s*" + _NUM + r"mm")


def _dru_floor(dru_text: str, pat: re.Pattern) -> float | None:
    vals = [float(m) for m in pat.findall(dru_text)]
    return min(vals) if vals else None


def _pro_rule(pro_text: str, key: str) -> float | None:
    m = re.search(r'"' + re.escape(key) + r'"\s*:\s*' + _NUM, pro_text)
    return float(m.group(1)) if m else None


def measure_board(pcb_path: Path = _PCB, dru_path: Path = _DRU,
                  pro_path: Path = _PRO) -> BoardDemand:
    d = BoardDemand()
    if not pcb_path.exists():
        return d
    doc = sexpr.loads(pcb_path.read_text())

    seg_widths: list[float] = []
    via_dias: list[float] = []
    via_annuli: list[float] = []
    drills: list[float] = []

    def walk(node: list) -> None:
        for sub in node:
            if not isinstance(sub, list) or not sub:
                continue
            head = sub[0]
            if head == Sym("segment"):
                w = sexpr.find(sub, "width")
                if w and len(w) > 1:
                    seg_widths.append(float(w[1]))
            elif head == Sym("via"):
                sz = sexpr.find(sub, "size")
                dr = sexpr.find(sub, "drill")
                dia = float(sz[1]) if sz and len(sz) > 1 else None
                drill = float(dr[1]) if dr and len(dr) > 1 else None
                if dia is not None:
                    via_dias.append(dia)
                if drill is not None:
                    drills.append(drill)
                if dia is not None and drill is not None:
                    via_annuli.append(round((dia - drill) / 2.0, 6))
            elif head == Sym("pad"):
                dr = sexpr.find(sub, "drill")
                if dr:
                    nums = [float(x) for x in dr[1:]
                            if isinstance(x, (int, float))]
                    if nums:
                        drills.append(min(nums))
            walk(sub)

    walk(doc)
    d.n_segments = len(seg_widths)
    d.n_vias = len(via_dias)
    d.n_drills = len(drills)

    dru_text = dru_path.read_text() if dru_path.exists() else ""
    pro_text = pro_path.read_text() if pro_path.exists() else ""

    dru_track = _dru_floor(dru_text, _DRU_TRACK)
    trace_candidates = [v for v in ([min(seg_widths)] if seg_widths else [])
                        + ([dru_track] if dru_track is not None else [])]
    d.min_trace_mm = min(trace_candidates) if trace_candidates else None
    d.min_clearance_mm = _dru_floor(dru_text, _DRU_CLEAR)

    d.min_drill_mm = min(drills) if drills else None
    d.min_via_dia_mm = min(via_dias) if via_dias else None

    d.min_via_annular_mm = min(via_annuli) if via_annuli else None
    d.pro_via_annular_mm = _pro_rule(pro_text, "min_via_annular_width")
    d.min_hole_to_hole_mm = _pro_rule(pro_text, "min_hole_to_hole")
    return d


@dataclass
class FabResult:
    ok: bool
    profile: FabProfile
    demand: BoardDemand
    rows: list[tuple[str, float | None, float, bool]] = field(
        default_factory=list)
    errors: list[str] = field(default_factory=list)

    def report(self) -> str:
        L = [f"FAB PROFILE GATE  ({self.profile.name})",
             f"  source: {self.profile.source}",
             "",
             f"  {'metric':<18} {'board demands':>14} {'fab floor':>12}"
             f"   verdict",
             "  " + "-" * 58]
        for metric, demand, floor, ok in self.rows:
            dv = "n/a" if demand is None else f"{demand:.4f} mm"
            note = "PASS" if ok else "FAIL (finer than fab)"
            L.append(f"  {metric:<18} {dv:>14} {floor:>9.4f} mm   {note}")
        L.append("")
        L.append(f"  segments {self.demand.n_segments}, vias {self.demand.n_vias}"
                 f", drilled holes {self.demand.n_drills}")
        if self.demand.pro_via_annular_mm is not None:
            L.append(f"  (.kicad_pro min_via_annular_width DRC floor: "
                     f"{self.demand.pro_via_annular_mm:.4f} mm — permissive rule, "
                     f"not what the board emits)")
        L.append("")
        L.append(f"  VERDICT: {'PASS' if self.ok else 'FAIL'} — "
                 + ("every demanded feature is at or above the fab floor"
                    if self.ok else
                    "the board demands geometry finer than the fab can produce"))
        if self.errors:
            L.append("")
            for e in self.errors:
                L.append(f"  FAIL: {e}")
        return "\n".join(L)


_METRICS = (
    ("min trace width", "min_trace_mm", "min_trace_mm"),
    ("min clearance", "min_clearance_mm", "min_clearance_mm"),
    ("min drill", "min_drill_mm", "min_drill_mm"),
    ("min via diameter", "min_via_dia_mm", "min_via_dia_mm"),
    ("min via annular", "min_via_annular_mm", "min_via_annular_mm"),
    ("min hole-to-hole", "min_hole_to_hole_mm", "min_hole_to_hole_mm"),
)

_EPS = 1e-6


def check(profile: FabProfile = JLCPCB_4L,
          pcb_path: Path = _PCB, dru_path: Path = _DRU,
          pro_path: Path = _PRO) -> FabResult:
    demand = measure_board(pcb_path, dru_path, pro_path)
    rows: list[tuple[str, float | None, float, bool]] = []
    errors: list[str] = []
    ok = True
    for label, dattr, pattr in _METRICS:
        dv = getattr(demand, dattr)
        floor = getattr(profile, pattr)
        metric_ok = dv is None or dv >= floor - _EPS
        rows.append((label, dv, floor, metric_ok))
        if not metric_ok:
            ok = False
            errors.append(
                f"{label}: board demands {dv:.4f} mm but "
                f"{profile.name} floor is {floor:.4f} mm "
                f"(finer than the fab can produce)")
    return FabResult(ok=ok, profile=profile, demand=demand, rows=rows,
                     errors=errors)


def run(rep_dir: Path, profile: FabProfile = JLCPCB_4L,
        pcb_path: Path = _PCB, dru_path: Path = _DRU,
        pro_path: Path = _PRO) -> FabResult:
    res = check(profile, pcb_path, dru_path, pro_path)
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "fab_profile.txt").write_text(res.report() + "\n")
    return res


if __name__ == "__main__":
    import sys
    r = check()
    print(r.report())
    sys.exit(0 if r.ok else 1)
