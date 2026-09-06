from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _nat
from schgen.generate.pcb import PcbModel, _inst_courtyard

_TIERS: tuple[tuple[int, float, str], ...] = (
    (2,  0.20, "2-pin passive — escapes on its own pads"),
    (8,  1.50, "<=8-pin non-passive — 1.5 mm absolute floor (user law 2026-07-29)"),
)
_TIER_TOP = (2.00, ">=9-pin package — 2.0 mm floor (user law 2026-07-29)")
_NEED_MM = [(max_pins, need) for max_pins, need, _basis in _TIERS]

MIN_SUBJECT_PINS = 3

_DF40_SHEET_RE = re.compile(r"^som_j\d+$")
DF40_MIN_PINS = 40

_PASSIVE_PREFIX = ("R", "C", "L")
_NOT_PLAIN_PASSIVE = ("RS", "RJ", "RN", "LED")

_TOUCH_EPS = 1e-4


def _ref_prefix_py(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else ref


def _ref_prefix(ref: str) -> str:
    if not _nat.loaded():
        raise RuntimeError("native ref_prefix required")
    got = _nat.module().ref_prefix(ref)
    if _nat.trace():
        python_ref = _ref_prefix_py(ref)
        if got != python_ref:
            raise AssertionError(
                "native ref_prefix DIVERGENCE: "
                f"cpp={got} python={python_ref} ref={ref!r}")
    return got


def _is_cluster_passive_py(ref: str, pins: int) -> bool:
    if pins > 2:
        return False
    if ref.startswith(_NOT_PLAIN_PASSIVE):
        return False
    return _ref_prefix_py(ref) in _PASSIVE_PREFIX


def _is_cluster_passive(ref: str, pins: int) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native is_cluster_passive required")
    got = bool(_nat.module().is_cluster_passive(
        ref, pins, list(_NOT_PLAIN_PASSIVE), list(_PASSIVE_PREFIX)))
    if _nat.trace():
        python_ref = _is_cluster_passive_py(ref, pins)
        if got != python_ref:
            raise AssertionError(
                "native is_cluster_passive DIVERGENCE: "
                f"cpp={got} python={python_ref} ref={ref!r} pins={pins}")
    return got


def _is_df40(inst) -> bool:
    return is_df40_part(inst.sheet, len(inst.pad_nets))


def is_df40_part(sheet: str, pins: int) -> bool:
    return bool(_DF40_SHEET_RE.match(sheet)) or pins >= DF40_MIN_PINS


def is_testpoint_ref_py(ref: str) -> bool:
    return _ref_prefix_py(ref) == "TP"


def is_testpoint_ref(ref: str) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native is_testpoint_ref required")
    got = bool(_nat.module().is_testpoint_ref(ref))
    if _nat.trace():
        python_ref = is_testpoint_ref_py(ref)
        if got != python_ref:
            raise AssertionError(
                "native is_testpoint_ref DIVERGENCE: "
                f"cpp={got} python={python_ref} ref={ref!r}")
    return got


def _is_fiducial(inst) -> bool:
    return "Fiducial" in inst.footprint


def counts_as_crowder(ref: str, sheet: str, pins: int, footprint: str,
                      subject_sheet: str) -> bool:
    return not (is_df40_part(sheet, pins)
                or "Fiducial" in footprint
                or is_testpoint_ref(ref)
                or (sheet == subject_sheet and _is_cluster_passive(ref, pins)))


def intelligent_need_py(pins: int) -> tuple[float, str]:
    for max_pins, need, basis in _TIERS:
        if pins <= max_pins:
            return need, basis
    return _TIER_TOP


def intelligent_need(pins: int) -> tuple[float, str]:
    if not _nat.loaded():
        raise RuntimeError("native intelligent_need required")
    got = tuple(_nat.module().intelligent_need(
        pins, list(_TIERS), _TIER_TOP[0], _TIER_TOP[1]))
    if _nat.trace():
        python_ref = intelligent_need_py(pins)
        if got != python_ref:
            raise AssertionError(
                "native intelligent_need DIVERGENCE: "
                f"cpp={got} python={python_ref} pins={pins}")
    return got


def _rect_gap_py(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    if dx == 0.0 and dy == 0.0:
        return 0.0
    if dx == 0.0:
        return dy
    if dy == 0.0:
        return dx
    return (dx * dx + dy * dy) ** 0.5


def _rect_gap(a, b) -> float:
    if not _nat.loaded():
        raise RuntimeError("native rect_gap required")
    got = _nat.module().rect_gap(a, b)
    if _nat.trace():
        ref = _rect_gap_py(a, b)
        if got != ref:
            raise AssertionError(
                f"native rect_gap DIVERGENCE: cpp={got} python={ref}")
    return got


@dataclass
class FanoutRec:
    ref: str
    sheet: str
    pins: int
    side: str
    clearance: float
    need: float
    nearest_ref: str
    nearest_sheet: str
    basis: str

    @property
    def slack(self) -> float:
        return self.clearance - self.need

    @property
    def starved(self) -> bool:
        return self.clearance < self.need - _TOUCH_EPS


@dataclass
class FanoutResult:
    ok: bool = True
    n_subjects: int = 0
    n_starved: int = 0
    baseline: int | None = None
    regressions: list[str] = field(default_factory=list)
    records: list[FanoutRec] = field(default_factory=list)

    @property
    def starved_records(self) -> list[FanoutRec]:
        return [r for r in self.records if r.starved]

    def summary(self) -> str:
        verdict = "PASS" if self.ok else "FAIL"
        L = [
            f"FAN-OUT CLEARANCE GATE (D13, report-first ratchet): {verdict}",
            f"  multi-pin subjects: {self.n_subjects}  starved: {self.n_starved}"
            + (f"  baseline(ratchet): {self.baseline}"
               if self.baseline is not None else "  baseline(ratchet): unset"),
            "  intelligent need = pin-count tier; clearance = min courtyard gap to "
            "nearest FOREIGN part",
            "  cluster-aware: own-sheet 2-pin R/C/L excluded; DF40 plugs (som_j*, "
            ">=40-pin) excluded (no-inflate)",
            "  OFFENDERS (starved, worst slack first):",
        ]
        starved = self.starved_records
        if not starved:
            L.append("    (none)")
        for r in starved:
            L.append(
                f"    STARVED {r.ref:9s} {r.sheet:16s} {r.pins:>3d}pin "
                f"[{r.side[:3]}] clr={r.clearance:.3f} need={r.need:.2f} "
                f"slack={r.slack:+.3f} nearest={r.nearest_ref} "
                f"({r.nearest_sheet})")
        if self.regressions:
            L.append(f"  RATCHET REGRESSION ({len(self.regressions)} — starved count "
                     f"{self.n_starved} > baseline {self.baseline}):")
            for g in self.regressions:
                L.append(f"    REGRESSION: {g}")
        spacious = [r for r in self.records if not r.starved][:5]
        if spacious:
            L.append("  (tightest PASSING subjects:)")
            for r in spacious:
                L.append(
                    f"    ok      {r.ref:9s} {r.sheet:16s} {r.pins:>3d}pin "
                    f"clr={r.clearance:.3f} need={r.need:.2f} slack={r.slack:+.3f}")
        return "\n".join(L)


def _subjects(model: PcbModel):
    for inst in model.insts:
        if _is_df40(inst):
            continue
        if len(inst.pad_nets) < MIN_SUBJECT_PINS:
            continue
        yield inst


def check(model: PcbModel, baseline: int | None = None) -> FanoutResult:
    res = FanoutResult()

    boxes = [(inst, _inst_courtyard(inst)) for inst in model.insts]

    for inst in _subjects(model):
        pins = len(inst.pad_nets)
        need, basis = intelligent_need(pins)
        my_box = _inst_courtyard(inst)

        crowders = [(other, obox) for other, obox in boxes
                    if other is not inst
                    and other.side == inst.side
                    and counts_as_crowder(other.ref, other.sheet,
                                          len(other.pad_nets), other.footprint,
                                          inst.sheet)]
        if not _nat.loaded():
            raise RuntimeError("native nearest_rect_gap required")
        others = [obox for _o, obox in crowders]
        clearance, idx = _nat.module().nearest_rect_gap(
            my_box, others, _TOUCH_EPS)
        if _nat.trace():
            best_gap = float("inf")
            best_i = -1
            for i, (_o, obox) in enumerate(crowders):
                gap = _rect_gap_py(my_box, obox)
                if gap < best_gap:
                    best_gap = gap
                    best_i = i
            ref_clr = 0.0 if best_gap < _TOUCH_EPS else best_gap
            if (clearance, idx) != (ref_clr, best_i):
                raise AssertionError(
                    "native nearest_rect_gap DIVERGENCE: "
                    f"cpp={(clearance, idx)} python={(ref_clr, best_i)}")
        if idx < 0:
            best_ref, best_sheet = "", ""
        else:
            best_ref = crowders[idx][0].ref
            best_sheet = crowders[idx][0].sheet
        res.records.append(FanoutRec(
            ref=inst.ref, sheet=inst.sheet, pins=pins, side=inst.side,
            clearance=clearance, need=need,
            nearest_ref=best_ref or "(none)",
            nearest_sheet=best_sheet or "-", basis=basis))

    res.records.sort(key=lambda r: (r.slack, r.ref))
    res.n_subjects = len(res.records)
    res.n_starved = sum(1 for r in res.records if r.starved)

    if baseline is None:
        baseline = _load_baseline()
    if baseline is None:
        baseline = res.n_starved
    res.baseline = baseline

    res.ok = res.n_starved <= baseline
    if not res.ok:
        for r in res.starved_records:
            res.regressions.append(
                f"{r.ref} ({r.sheet}) {r.pins}pin: clr={r.clearance:.3f} < "
                f"need={r.need:.2f}")
    return res


_BASELINE_PATH = (Path(__file__).resolve().parents[2]
                  / "carrier" / "reports" / "fanout_baseline.json")


def _load_baseline() -> int | None:
    try:
        data = json.loads(_BASELINE_PATH.read_text())
        return int(data["starved_baseline"])
    except Exception:      # noqa: BLE001 — absent/corrupt => caller pins current count
        return None


def write_baseline(n_starved: int, path: Path | None = None) -> None:
    p = path or _BASELINE_PATH
    cur = None
    try:
        cur = int(json.loads(p.read_text())["starved_baseline"])
    except Exception:      # noqa: BLE001
        cur = None
    new = n_starved if cur is None else min(cur, n_starved)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "starved_baseline": new,
        "note": "fan-out ratchet ceiling — may only DECREASE; a build whose starved "
                "count exceeds this FAILS. Reach 0 to promote the gate to HARD.",
    }, indent=1) + "\n")
