"""FAN-OUT CLEARANCE gate — intelligent-uniform placement floor (D13, NO-ROUTING wave).

Design intent (AI_LAYOUT_ROUTING_CONCEPT.md "FAN-OUT CLEARANCE — design intent",
2026-07-04, user-confirmed "intelligent not dumb"): every multi-pin component gets a
basic breathing-room floor around it so its pins can fan out — a UNIFORM rule with an
INTELLIGENT value, checked at PLACEMENT time. This is NOT a per-net routing calc (that
routing-flavoured escape-lane demand analysis was rejected as over-engineered); it is a
broad, simple spacing floor.

Three principles, exactly as recorded:

  * UNIFORM RULE — one principle board-wide: every multi-pin IC gets a fan-out floor.

  * INTELLIGENT VALUE — the floor is scaled to the component's OWN fan-out demand, read
    off pin count (a proxy for package / escape pressure). A 100-pin BGA-class part
    needs real room; an 8-pin SOIC needs a little; a 3-pin regulator almost none. Simple
    TIERS (below), NOT a constant halo (a flat halo bloats the board and is the "dumb"
    rule the intent rejects).

  * CLUSTER-AWARE (the anti-dumb guard) — clearance is measured to FOREIGN parts ONLY,
    and only on the SAME COPPER SIDE. Three exclusions keep the rule from fighting the
    board's intended structure:
      (1) own-cluster members — the 2-pin R/C/L decoupling caps, hot-loop caps and FB
          dividers on the SAME sheet — sit TIGHT on the IC's pins BY DESIGN and do NOT
          count as crowding, so the rule never pries a decoupling cap off a pin;
      (2) OPPOSITE-side parts — fan-out is escape room on the IC's OWN copper plane; a
          bottom-side decoupling cap directly under a top-side IC is the 2-side assembly
          working AS DESIGNED (the "small passives on the bottom under their cluster"
          policy), NOT crowding — measuring across the plane is the dumb cross-layer
          halo the intent rejects;
      (3) the DF40 mezzanine plugs (som_j*, >=40-pin) — the escape-block's domain,
          EXCLUDED (no-inflate) both as subjects and as neighbours; they sit tight under
          the SoM by design and their fan-out is the escape-lane gate's, not this one's.

Per multi-pin IC we compute the minimum courtyard-edge gap to the nearest FOREIGN part
and compare it to the intelligent NEED. STARVED iff gap < need. The offender list (ref,
sheet, pins, clearance, need, slack, nearest-foreign) sorted worst-first IS the
deliverable.

REPORT-FIRST with a RATCHET (decision below). Many ICs are starved today because the
placer packs the whole board at PLACE_CLEAR=0.5 mm courtyard clearance, so any part
whose intelligent need exceeds 0.5 mm is starved before a single template is re-spaced.
Making
this HARD now would block every build until the placement templates catch up — which the
NO-ROUTING wave is precisely the runway for. So the gate lands REPORT-FIRST: it records
the CURRENT starved count as a baseline that may only DECREASE (a ratchet). ``ok`` is
True as long as the live starved count does not EXCEED the baseline; a regression (a
placement change that starves a NEW IC) fails LOUDLY, while the standing debt is visible
and trending down. When the templates have opened every IC, the baseline reaches 0 and a
one-line flip promotes it to HARD.

LAW 4 (no softening): the tiers and the foreign/cluster rule are strict; a starved IC is
FIXED by spacing its template, never waived here. The ratchet only bounds the SCHEDULE
of the migration; it never relaxes the per-IC rule.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.generate.pcb import PcbModel, _inst_courtyard

# ---- intelligent NEED tiers ----------------------------------------------------------
# Fan-out clearance a multi-pin part needs, keyed by pin count. BASIS (kept deliberately
# simple — tiers, not a routing calc): the gap must fit the escape traces the part's own
# pins fan into before they can turn away, so it scales with pin count (more pins =>
# more simultaneous escapes => a wider reserved apron). USER LAW 2026-07-29: any
# non-passive package gets an absolute floor of 1.5 mm; anything with >= 9 pins gets
# at least 2.0 mm (routing-margin decree; supersedes the lane-count-derived 0.5/1.0
# ladder at the same 0.2 mm trace / 0.15 mm space geometry). These are FLOORS, not
# routed corridors — the escape-lane gate owns the per-net corridor math.
_TIERS: tuple[tuple[int, float, str], ...] = (
    # (max_pins_inclusive, need_mm, package-class basis)
    (2,  0.20, "2-pin passive — escapes on its own pads"),
    (8,  1.50, "<=8-pin non-passive — 1.5 mm absolute floor (user law 2026-07-29)"),
)
_TIER_TOP = (2.00, ">=9-pin package — 2.0 mm floor (user law 2026-07-29)")

# A part with fewer than this many pins is not a fan-out SUBJECT (a 1-2-pin passive is a
# cluster member, never a fan-out IC). Multi-pin == 3+.
MIN_SUBJECT_PINS = 3

# DF40 mezzanine plugs: the SoM interface receptacles. Excluded as subjects AND as
# crowding neighbours (no-inflate — they sit tight under the SoM by design; the escape-
# lane gate owns their fan-out, not this floor). Matched by sheet OR pin count so a
# refdes renumber can never smuggle one back in.
_DF40_SHEET_RE = re.compile(r"^som_j\d+$")
DF40_MIN_PINS = 40

# discrete R/C/L passive prefixes — a same-sheet 2-pin one of these is a cluster member
# (decoupling / hot-loop / FB divider), NOT foreign crowding. RS (current shunt), RJ
# (RJ45), RN (network), LED are NOT plain decoupling passives.
_PASSIVE_PREFIX = ("R", "C", "L")
_NOT_PLAIN_PASSIVE = ("RS", "RJ", "RN", "LED")

# clearance at or below this (mm) is grid-snap touch, not a real gap; report as 0.
_TOUCH_EPS = 1e-4


def _ref_prefix(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else ref


def _is_cluster_passive(ref: str, pins: int) -> bool:
    """True for a discrete 2-pin R/C/L — the parts that sit tight ON an IC's pins by
    design (decoupling / hot-loop / FB divider) and must NOT count as crowding."""
    if pins > 2:
        return False
    if ref.startswith(_NOT_PLAIN_PASSIVE):
        return False
    return _ref_prefix(ref) in _PASSIVE_PREFIX


def _is_df40(inst) -> bool:
    return is_df40_part(inst.sheet, len(inst.pad_nets))


def is_df40_part(sheet: str, pins: int) -> bool:
    return bool(_DF40_SHEET_RE.match(sheet)) or pins >= DF40_MIN_PINS


def is_testpoint_ref(ref: str) -> bool:
    """USER LAW 2026-07-29: test points are EXEMPT from fan-out crowding — a TP pad
    carries no courtyard traffic and no escape lanes, so it neither crowds a subject
    nor demands apron room, on ANY sheet (unconditional, unlike the same-sheet
    cluster-passive waiver)."""
    return _ref_prefix(ref) == "TP"


def _is_fiducial(inst) -> bool:
    """A fiducial is PCB-only fab-art (a 1 mm bare-copper registration dot, no net,
    no pin). It never blocks an IC's fan-out — the assembler places parts around it
    and it carries no escape traffic — so it must NOT count as a crowding foreign
    neighbour (same principle as the DF40-plug exclusion)."""
    return "Fiducial" in inst.footprint


def counts_as_crowder(ref: str, sheet: str, pins: int, footprint: str,
                      subject_sheet: str) -> bool:
    """THE foreign-neighbour predicate — the ONE definition of "does this part
    crowd that subject's fan-out apron", shared by the gate and by every engine
    stage that optimises toward it (breathe's march/target/no-regression guard).

    A private replica is how the machinery drifts from its own arbiter: BREATHE
    carried a copy that omitted the test-point exemption, so it read a subject's
    clearance as the gap to an exempt TP pad. That phantom crowder (a) faked
    starvation, (b) aimed the away-from-crowder march at a part the gate does not
    count, and (c) neutered the mover's own no-regression floor, which is
    min(need, current clearance) — with the phantom current at 0.50 mm the guard
    permitted a real 2.64 mm gap to collapse to 1.38 mm against a 1.50 mm need
    (measured live: U5001 bringup_en_modules vs C15002 lcd, both TOP, the single
    D13 red of the 185x163 bringup_rails outline). Call this; never re-derive it.

    ``sheet``/``pins``/``footprint`` describe the candidate neighbour;
    ``subject_sheet`` is the subject's sheet (same-sheet cluster passives are the
    only sheet-relative waiver). SIDE is the caller's business — the gate and the
    engine both filter to the subject's own copper face before asking. The four
    exclusions are the module docstring's cluster-aware rule plus the test-point
    law: DF40 plugs (no-inflate), fiducials (fab-art), TP pads (no courtyard
    traffic, on ANY sheet), own-sheet 2-pin R/C/L (tight by design)."""
    return not (is_df40_part(sheet, pins)
                or "Fiducial" in footprint
                or is_testpoint_ref(ref)
                or (sheet == subject_sheet and _is_cluster_passive(ref, pins)))


def intelligent_need(pins: int) -> tuple[float, str]:
    """The fan-out clearance FLOOR (mm) a part with ``pins`` pins needs, + a basis
    string. UNIFORM rule, INTELLIGENT value — scaled by pin count via simple tiers."""
    for max_pins, need, basis in _TIERS:
        if pins <= max_pins:
            return need, basis
    return _TIER_TOP


def _rect_gap(a, b) -> float:
    """Minimum edge-to-edge gap between two axis-aligned bboxes (0 if they overlap or
    touch). Chebyshev-style separation on the non-overlapping axis."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)   # x separation (0 if x-ranges overlap)
    dy = max(by0 - ay1, ay0 - by1, 0.0)   # y separation
    if dx == 0.0 and dy == 0.0:
        return 0.0                         # overlapping / touching courtyards
    if dx == 0.0:
        return dy
    if dy == 0.0:
        return dx
    return (dx * dx + dy * dy) ** 0.5      # diagonal corner-to-corner


@dataclass
class FanoutRec:
    """One starved-or-not multi-pin IC."""
    ref: str
    sheet: str
    pins: int
    side: str
    clearance: float          # min courtyard gap to nearest FOREIGN part (mm)
    need: float               # intelligent fan-out floor (mm)
    nearest_ref: str          # the foreign part that sets the clearance
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
    baseline: int | None = None       # ratchet baseline (starved count ceiling)
    regressions: list[str] = field(default_factory=list)
    records: list[FanoutRec] = field(default_factory=list)   # sorted worst-first

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
        # a short spacious-side tail so a reader sees the healthy end of the ladder too
        spacious = [r for r in self.records if not r.starved][:5]
        if spacious:
            L.append("  (tightest PASSING subjects:)")
            for r in spacious:
                L.append(
                    f"    ok      {r.ref:9s} {r.sheet:16s} {r.pins:>3d}pin "
                    f"clr={r.clearance:.3f} need={r.need:.2f} slack={r.slack:+.3f}")
        return "\n".join(L)


def _subjects(model: PcbModel):
    """Multi-pin fan-out subjects (>=3 pins), excluding the DF40 mezzanine plugs."""
    for inst in model.insts:
        if _is_df40(inst):
            continue
        if len(inst.pad_nets) < MIN_SUBJECT_PINS:
            continue
        yield inst


def check(model: PcbModel, baseline: int | None = None) -> FanoutResult:
    """Measure the fan-out clearance floor for every multi-pin IC.

    ``baseline`` is the ratchet ceiling on the starved count (see module docstring). If
    None it is read from the sidecar baseline file; if that is absent the CURRENT
    starved count is adopted as the baseline (first run pins the debt) and it PASSES —
    subsequent runs may only DECREASE it. Pass an explicit int in tests.
    """
    res = FanoutResult()

    # pre-compute every part's placed courtyard once (foreign-neighbour scan is O(n^2)
    # over ~564 parts — fine, but do the geometry once).
    boxes = [(inst, _inst_courtyard(inst)) for inst in model.insts]

    for inst in _subjects(model):
        pins = len(inst.pad_nets)
        need, basis = intelligent_need(pins)
        my_box = _inst_courtyard(inst)

        best_gap = float("inf")
        best_ref = ""
        best_sheet = ""
        for other, obox in boxes:
            if other is inst:
                continue
            if other.side != inst.side:
                continue                      # opposite copper plane — not fan-out room
            if not counts_as_crowder(other.ref, other.sheet,
                                     len(other.pad_nets), other.footprint,
                                     inst.sheet):
                continue
            gap = _rect_gap(my_box, obox)
            if gap < best_gap:
                best_gap = gap
                best_ref = other.ref
                best_sheet = other.sheet

        clearance = 0.0 if best_gap < _TOUCH_EPS else (
            best_gap if best_gap != float("inf") else float("inf"))
        res.records.append(FanoutRec(
            ref=inst.ref, sheet=inst.sheet, pins=pins, side=inst.side,
            clearance=clearance, need=need,
            nearest_ref=best_ref or "(none)",
            nearest_sheet=best_sheet or "-", basis=basis))

    # deterministic: worst slack first, then ref for ties.
    res.records.sort(key=lambda r: (r.slack, r.ref))
    res.n_subjects = len(res.records)
    res.n_starved = sum(1 for r in res.records if r.starved)

    if baseline is None:
        baseline = _load_baseline()
    if baseline is None:
        baseline = res.n_starved          # first run pins the current debt
    res.baseline = baseline

    # RATCHET: OK iff the live starved count does not EXCEED the baseline. A NEW starved
    # IC (a placement change that crowds a previously-clear part) pushes the count over
    # the baseline and FAILS loudly; the standing debt is reported but does not block.
    res.ok = res.n_starved <= baseline
    if not res.ok:
        for r in res.starved_records:
            res.regressions.append(
                f"{r.ref} ({r.sheet}) {r.pins}pin: clr={r.clearance:.3f} < "
                f"need={r.need:.2f}")
    return res


# ---- ratchet baseline persistence ----------------------------------------------------
# The baseline lives beside the report so the ratchet survives across builds and is
# reviewable in git. It is DATA, not a validator softening (LAW 4): it bounds only how
# fast the standing debt must retire, never the per-IC rule.
_BASELINE_PATH = (Path(__file__).resolve().parents[2]
                  / "carrier" / "reports" / "fanout_baseline.json")


def _load_baseline() -> int | None:
    try:
        data = json.loads(_BASELINE_PATH.read_text())
        return int(data["starved_baseline"])
    except Exception:      # noqa: BLE001 — absent/corrupt => caller pins current count
        return None


def write_baseline(n_starved: int, path: Path | None = None) -> None:
    """Persist (or RATCHET DOWN) the starved-count baseline. Only ever writes a value
    that is <= the stored one — the ceiling may decrease, never grow (that is the whole
    point). Called by ``schgen board`` after a PASS."""
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
