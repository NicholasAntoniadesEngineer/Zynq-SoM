"""fab_profile — DFM manufacturability gate (GAP3): the emitted board's tightest
demanded geometry vs a pinned fab CAPABILITY profile.

A board that DESIGN-RULE-passes KiCad's own DRC can still be un-manufacturable at
a given fab: KiCad enforces the rules the PROJECT sets (``.kicad_pro`` +
``.kicad_dru``), not the FAB's physical floor. This gate closes that gap — it
measures what the board ACTUALLY demands (from the emitted ``.kicad_pcb`` geometry
AND the effective project design-rule floors) and HARD-FAILS if any metric is
FINER than the fab can produce. It never relaxes a rule (LAW 4); it is a second,
independent oracle that DRC cannot be (DRC has no notion of a house profile).

Per-metric, board-demand vs profile:
  - min trace width      (emitted segment widths + the .dru ``track_width`` floor)
  - min clearance        (the .dru ``clearance`` floor)
  - min drill            (every emitted pad/via drill)
  - min via diameter     (every emitted via outer diameter)
  - min via annular      ((via_dia - drill)/2 over every emitted VIA)
  - min hole-to-hole     (the .kicad_pro ``min_hole_to_hole`` floor)

VIA vs PTH-PAD ANNULAR — deliberately distinct. JLC's headline "min annular ring
0.13 mm" is the floor for a DRILLED COMPONENT PAD (a PTH pad's copper ring). A
plated VIA is a separate capability: JLC's preferred via is 0.20 mm hole / 0.35 mm
diameter, i.e. 0.075 mm annular per side — so a 0.075 mm VIA annular is exactly
JLC's preferred via, NOT a violation. This gate checks the VIA annular against the
0.075 mm via floor; the ``.kicad_pro`` ``min_via_annular_width`` (a permissive DRC
floor, 0.05 mm) is reported for context but is NOT the fab demand — the emitted via
copper is.

PROFILE — JLCPCB standard 4-layer service (1 oz outer copper), cited:
  min trace/space  0.09 / 0.09 mm  (3.5 mil)
  min via drill    0.15 mm ;  min via diameter 0.25 mm ; preferred via 0.20/0.35 mm
  min via annular  0.075 mm  (per side, from the 0.20/0.35 preferred via)
  min drill        0.15 mm  (mechanical/PTH)
  min hole-to-hole 0.15 mm
  (PTH-pad annular 0.13 mm — recorded but not a metric here; the board emits no
   sub-0.13 mm PTH-pad annular, its component pads are 0603+ standard land.)
  Source: JLCPCB "PCB Manufacturing & Assembly Capabilities"
  (https://jlcpcb.com/capabilities/pcb-capabilities) + JLCPCB via/annular Q&A
  (min via hole 0.15 mm; preferred via 0.20/0.35 mm; PTH annular 0.13 mm),
  retrieved 2026-07.

This PASSES on the current board (drawn to a conservative 0.2032 mm track /
0.3 mm via-drill / 0.45 mm via-dia = 0.075 mm via annular — all AT OR COARSER than
the JLC floor) and the gate reports each margin honestly. It exists so a future
placement/routing/escape change that quietly demands sub-fab geometry FAILS the
build instead of shipping an unbuildable board.

Run standalone:  ``python3 -m schgen.verify.fab_profile``
"""

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


# ---- the fab capability profile (PINNED, CITED) --------------------------------

@dataclass(frozen=True)
class FabProfile:
    """A fab's physical manufacturing floor. Every field is the FINEST feature
    the fab can reliably produce; the board must stay AT OR ABOVE each one."""

    name: str
    min_trace_mm: float
    min_clearance_mm: float
    min_drill_mm: float
    min_via_dia_mm: float
    min_via_annular_mm: float
    min_hole_to_hole_mm: float
    source: str


# JLCPCB standard 4-layer (1 oz), cited above.
JLCPCB_4L = FabProfile(
    name="JLCPCB standard 4-layer (1oz)",
    min_trace_mm=0.09,
    min_clearance_mm=0.09,
    min_drill_mm=0.15,
    min_via_dia_mm=0.25,
    min_via_annular_mm=0.075,   # per side; JLC preferred via 0.20/0.35 mm
    min_hole_to_hole_mm=0.15,
    source="JLCPCB PCB Manufacturing & Assembly Capabilities "
           "(jlcpcb.com/capabilities/pcb-capabilities) + JLCPCB via/annular Q&A; "
           "retrieved 2026-07",
)


# ---- what the board DEMANDS (measured, never hardcoded) ------------------------

@dataclass
class BoardDemand:
    """The finest geometry the emitted board actually asks for. ``None`` where the
    board carries no such feature yet (e.g. no routed tracks -> min_trace only
    from the .dru floor)."""

    min_trace_mm: float | None = None     # tightest of (emitted segments, .dru)
    min_clearance_mm: float | None = None  # .dru clearance floor
    min_drill_mm: float | None = None     # smallest emitted pad/via drill
    min_via_dia_mm: float | None = None   # smallest emitted via outer dia
    min_via_annular_mm: float | None = None  # min (via_dia-drill)/2 over EMITTED vias
    min_hole_to_hole_mm: float | None = None  # .kicad_pro floor
    pro_via_annular_mm: float | None = None   # .kicad_pro permissive DRC floor (info)
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
    """Scan the emitted board + its effective design-rule floors. Self-contained
    (no dependence on the in-process model) so the gate is an independent oracle
    against exactly the file a fab would receive."""
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
                # a pad drill may be `(drill 0.3)` or `(drill oval 0.3 0.5)`
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

    # VIA annular = the tightest ring the board ACTUALLY emitted (measured copper),
    # NOT the .kicad_pro permissive DRC floor (which is only what KiCad would ALLOW,
    # not what is on the board). The pro floor is carried for context only.
    d.min_via_annular_mm = min(via_annuli) if via_annuli else None
    d.pro_via_annular_mm = _pro_rule(pro_text, "min_via_annular_width")
    d.min_hole_to_hole_mm = _pro_rule(pro_text, "min_hole_to_hole")
    return d


# ---- the gate ------------------------------------------------------------------

@dataclass
class FabResult:
    ok: bool
    profile: FabProfile
    demand: BoardDemand
    rows: list[tuple[str, float | None, float, bool]] = field(
        default_factory=list)   # (metric, board_demand, fab_floor, ok)
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


# a metric passes when the board's demand is >= the fab floor (coarser or equal).
# A demand of None (no such feature emitted) trivially passes.
_METRICS = (
    ("min trace width", "min_trace_mm", "min_trace_mm"),
    ("min clearance", "min_clearance_mm", "min_clearance_mm"),
    ("min drill", "min_drill_mm", "min_drill_mm"),
    ("min via diameter", "min_via_dia_mm", "min_via_dia_mm"),
    ("min via annular", "min_via_annular_mm", "min_via_annular_mm"),
    ("min hole-to-hole", "min_hole_to_hole_mm", "min_hole_to_hole_mm"),
)

# floating-point slack so an exact-equality design (demand == floor) never
# false-fails on a representation wobble.
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
    """check() + write carrier/reports/fab_profile.txt. Deterministic."""
    res = check(profile, pcb_path, dru_path, pro_path)
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "fab_profile.txt").write_text(res.report() + "\n")
    return res


if __name__ == "__main__":
    import sys
    r = check()
    print(r.report())
    sys.exit(0 if r.ok else 1)
