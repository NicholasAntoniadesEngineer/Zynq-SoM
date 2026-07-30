"""QUANTIZATION REGISTRY — every live geometry-touching snap / round / pad /
credit in the placement pipeline is a NAMED transform defined HERE and called
by name at its site (governance U1).

Three waves of archaeology traced the same defect class to inline geometry
perturbations no gate input had modelled (the zone ``_gridify`` snap, the
blanket ``+GRID`` credit, the ``_pack_edges`` ``_r5`` snap, the ``+_SEAT_SLIDE``
apron pad — all since retired). The rule this module enforces: a transform that
quantizes a position, clearance, reservation or outline is not an anonymous
arithmetic expression — it is a registered mechanism with a value, a basis and
a proof class. The census lint (``schgen/verify/quantize_census.py``) scans
``schgen/generate/**`` for raw quantization vocabulary outside this registry
and HARD-FAILS the board on any NEW site vs its committed (empty) baseline.

Proof classes:

* ``pre-proof``        — applied BEFORE the proofs that judge the result (the
                         gates/DRC measure the already-quantized geometry), so
                         the transform can never invalidate a passed proof.
* ``proof-preserving`` — strictly conservative: it only ever GROWS a
                         reservation or SHRINKS an allowance, so every
                         previously proven bound still holds.
* ``re-validated``     — the perturbed result is re-checked by the applying
                         stage itself (committed only if still legal, else
                         retreated/aborted).

Every function below replicates its historical call-site arithmetic
bit-for-bit — routing through the registry is proven INERT by board
byte-identity. Deterministic, stateless, no caching.
"""
from __future__ import annotations

from dataclasses import dataclass

GRID_MM = 1.27
HALF_MM = 0.5
CREDIT_MM = 0.05
SNAP_EROSION_MM = 0.75
SEAT_SLIDE_MM = 1.2
OUTLINE_SNAP_MM = 5.0
REFINE_SPAN_MM = 40.0
FINE_SNAP_MM = 1.0


@dataclass(frozen=True)
class Quantization:
    name: str
    value: str
    basis: str
    klass: str


REGISTRY: dict[str, Quantization] = {}

_CLASSES = ("pre-proof", "proof-preserving", "re-validated")


def _register(name: str, value: str, basis: str, klass: str) -> None:
    if klass not in _CLASSES:
        raise AssertionError(f"quantize: unknown proof class {klass!r}")
    if name in REGISTRY:
        raise AssertionError(f"quantize: duplicate registration {name!r}")
    REGISTRY[name] = Quantization(name=name, value=value, basis=basis,
                                  klass=klass)


_register(
    "fixed_part_grid",
    f"round(round(v / {GRID_MM}) * {GRID_MM}, 4)",
    "MH corners + SoM DF40 receptacles snap their absolute page position to "
    "the 1.27 mm placement grid at emission; subsystem parts keep their exact "
    "floorplan pose. Formula MIRRORED on both sides: the floorplan evaluator "
    "replicates it verbatim, and gridify(exact) == emitted was measured for "
    "every SoM-J + MH (scan probe P2; displacement up to +0.59 mm, worst "
    "subject-vs-MH slack +1.12 mm).",
    "proof-preserving")


def fixed_part_grid(v: float) -> float:
    return round(round(v / GRID_MM) * GRID_MM, 4)


_register(
    "evict_corridor_grid",
    f"round(round(round((origin + v) / {GRID_MM}) * {GRID_MM}, 4) - origin, 4)",
    "The corridor-eviction stage measures each DF40 stitch corridor at its "
    "POST-gridify centre: the emission fixed_part_grid snap (page frame) "
    "mapped back to the board frame, so eviction clears the very corridors "
    "the emitted board and the escape solver will have. Closes the scan-B "
    "frame-shift landmine: eviction against PRE-gridify corridors held a "
    "0.25 mm margin while the gridify moved the emitted corridor up to "
    "0.59 mm carrier / 0.38 mm devkit.",
    "pre-proof")


def evict_corridor_grid(origin: float, v: float) -> float:
    return round(fixed_part_grid(origin + v) - origin, 4)


_register(
    "breathe_anchor_grid",
    f"round(round(v / {GRID_MM}) * {GRID_MM}, 4)",
    "A BREATHE-moved anchor snaps its winning delta to the page grid for a "
    "stable coarse move quantum; the snapped delta is re-tested (group_free "
    "+ leash_ok, with a CELL-step retreat and a no-move abort) before any "
    "commit, plus the stayer-need guard and the whole-sheet dispersion "
    "revert. Measured live: 150 engagements, max snap displacement "
    "0.6347 mm (= GRID/2), final gate 0 starved (scan probe R4).",
    "re-validated")


def breathe_anchor_grid(v: float) -> float:
    return round(round(v / GRID_MM) * GRID_MM, 4)


_register(
    "som_pose_half_mm",
    "round(round(v * 2) / 2, 1)",
    "The SoM body pose (board-centred + declared offset) sits on a 0.5 mm "
    "grid; the pack search then proves every block against that pose.",
    "pre-proof")


def som_pose_half_mm(v: float) -> float:
    return round(round(v * 2) / 2, 1)


_register(
    "placeholder_zone_half_mm",
    "round(round(v * 2) / 2, 1)",
    "Blocks with no packed zone (reservation-only / mechanical) get a 0.5 mm-"
    "grid landing rectangle from the small-area estimate; real zones use the "
    "exact packed box.",
    "pre-proof")


def placeholder_zone_half_mm(v: float) -> float:
    return round(round(v * 2) / 2, 1)


_register(
    "quant_credit",
    f"v + {CREDIT_MM}",
    "4dp coordinate quantization eats microns: a fan-out reach met exactly "
    "emerged 15 um short (measured). Reservations carry need + 0.05 so the "
    "proven floor survives rounding — the credit only GROWS a reservation.",
    "proof-preserving")


def quant_credit(v: float) -> float:
    return v + CREDIT_MM


_register(
    "snap_erosion_bound",
    f"bound - {SNAP_EROSION_MM} if bound >= 5.0 else bound",
    "Template candidate bounds >= 5 mm are pre-tightened (conservative "
    "direction). BASIS RE-BASED against measurement (wave-8 U2, scan "
    "finding F3): the one post-solve mover is the LAW-6 edge-seat slide, "
    "measured EXACTLY EDGE_INSET = 1.5 mm on every contracted conn sheet "
    "(live probe, all 15 slides = 1.500; the 1.96 outlier is the "
    "un-contracted rj45_connector, outside this engine) — member-member "
    "distances have NO mover (breathe/reorder/L4 exempt contract members; "
    "refit/facing turns rigid). An EDGE_INSET-derived scalar cover is "
    "REFUTED: 1.5 and 2.0 both close motor_sense's D1 annulus (measured "
    "solver-infeasible), and the exact outward-vector projection of "
    "connector targets re-derives every conn zone and broke emergent "
    "edge-run invariants in integration (USB-C run overlap, hdmi split "
    "140 mm — measured, reverted). 0.75 is therefore RETAINED as declared "
    "margin, not a cover claim; the honest cover needs the vector form "
    "landed with the run/compose machinery re-proven.",
    "proof-preserving")


def snap_erosion_bound(bound: float) -> float:
    return bound - SNAP_EROSION_MM if bound >= 5.0 else bound


_register(
    "snap_erosion_pad",
    f"mm + ({SNAP_EROSION_MM} if mm >= 5.0 else 0.0)",
    "The min-clearance twin of snap_erosion_bound: repulsion minima >= 5 mm "
    "grow by the same margin (conservative direction; the same wave-8 U2 "
    "re-based basis — declared margin, the slide grows these distances so "
    "a covering pad is not needed).",
    "proof-preserving")


def snap_erosion_pad(mm: float) -> float:
    return mm + (SNAP_EROSION_MM if mm >= 5.0 else 0.0)


_register(
    "seat_slide",
    f"{SEAT_SLIDE_MM}",
    "Edge-seat courtyard->pad-flush slide allowance: the connector face line "
    "(and the inboard cluster line) is offset by 1.2 mm so the later "
    "EDGE_PAD_CLEAR outward seat cannot strand a cluster outboard of it. "
    "Conservative direction: every use ENLARGES a forbidden half-plane or "
    "pulls alignment inboard of the swept path.",
    "pre-proof")


def seat_slide() -> float:
    return SEAT_SLIDE_MM


_register(
    "run_overflow_tol",
    "0.1",
    "The edge-run overflow REJECT test tolerates 0.1 mm of clamp slop "
    "before rejecting a candidate board (a run spilling toward the M3 "
    "corner keepout). Probe-proven byte-inert on the live board: zeroed, "
    "the rebuild is byte-identical (scan probe R1; min live margin "
    "+6.60 mm) — a latent credit, registered so any future engagement is "
    "a named mechanism.",
    "proof-preserving")


def run_overflow_tol() -> float:
    return 0.1


_register(
    "est_via_cost",
    "2 * (0.6 + 2 * 0.25) = 2.2 mm per side-crossing cross-subsystem MST edge",
    "LAW-5 sizing-estimator VIA-COST term (bottom-side P1): a cross-subsystem "
    "net whose endpoints sit on opposite copper faces needs a layer-transition "
    "via, and one via consumes its barrel (0.6 mm copper dia — the project's "
    "standard THERMAL_VIA_SIZE) plus a clearance annulus (2 x 0.25 mm "
    "THERMAL_VIA_CLEAR) of routing channel on BOTH signal layers = 2.2 mm of "
    "equivalent airwire. Charged ONLY on cross-sheet MST edges with differing "
    "endpoint sides where an endpoint sheet chose a side-tagged BOTTOM shape: "
    "the baseline board's existing top/bottom splits are already priced by "
    "the calibrated LAW-5 budget, so the term is exactly zero when no block "
    "opts in (the byte-inert control) and the strict ratsnest gate remains "
    "the arbiter of any board it helped size.",
    "pre-proof")


def est_via_cost() -> float:
    return 2 * (0.6 + 2 * 0.25)


_register(
    "legalize_pose_quantum",
    f"round(round(v / {HALF_MM}) * {HALF_MM}, 4)",
    "The composition legalizer's L4' compaction writes each pulled pose back "
    "on a 0.5 mm quantum (matching the template engine's _CAND_STEP), then "
    "CLAMPs to the feasible window; the whole compaction is REVERTED if any "
    "hard term goes red or a separation breaks.",
    "re-validated")


def legalize_pose_quantum(v: float) -> float:
    return round(round(v / HALF_MM) * HALF_MM, 4)


_register(
    "outline_snap_up",
    f"ceil(v / {OUTLINE_SNAP_MM}) * {OUTLINE_SNAP_MM}",
    "Derived board W/H rounds UP to the 5 mm outline grid; every candidate "
    "board is then re-proven by the real pack + the LAW-5 budget estimate.",
    "pre-proof")


def outline_snap_up(v: float) -> float:
    n = int((v + OUTLINE_SNAP_MM - 1e-6) / OUTLINE_SNAP_MM)
    return round(n * OUTLINE_SNAP_MM, 1)


_register(
    "outline_grow_step",
    f"k * {OUTLINE_SNAP_MM}",
    "The aspect-family sizing search grows the seed outline in 5 mm steps; "
    "each candidate is re-proven (pack + budget), never assumed.",
    "pre-proof")


def outline_grow(k: int) -> float:
    return k * OUTLINE_SNAP_MM


_register(
    "outline_fine_grid",
    f"round(base - k * {FINE_SNAP_MM}, 1) over a {REFINE_SPAN_MM} mm window",
    "The independent-axis refinement scans a 1 mm grid (packing feasibility "
    "is jagged at that scale — 161/163 pack where 160/162/164 do not) for "
    f"{REFINE_SPAN_MM:g} mm below the aspect-best; every candidate re-runs "
    "the real pack and budget.",
    "pre-proof")


def fine_shrink(base: float, k: int) -> float:
    return round(base - k * FINE_SNAP_MM, 1)


def fine_steps() -> int:
    return int(REFINE_SPAN_MM / FINE_SNAP_MM) + 1
