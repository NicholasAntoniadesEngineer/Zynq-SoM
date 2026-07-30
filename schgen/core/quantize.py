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
VIA_SIZE_MM = 0.6
VIA_CLEAR_MM = 0.25
STACK_THICKNESS_MM = 1.6


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


EST_VIA_ORDINARY_MM = 2 * (VIA_SIZE_MM + 2 * VIA_CLEAR_MM)

EST_VIA_COST_MM: dict[str, float] = {
    "impedance": round(2 * 2 * (VIA_SIZE_MM + 2 * VIA_CLEAR_MM)
                       + 2 * STACK_THICKNESS_MM, 4),
    "ordinary": EST_VIA_ORDINARY_MM,
}

_register(
    "est_via_cost",
    "{impedance: 2 legs * 2 layers * (0.6 + 2 * 0.25) + 2 legs * 1.6 = 7.6, "
    "ordinary: 2 * (0.6 + 2 * 0.25) = 2.2} mm per side-crossing "
    "cross-subsystem MST edge, keyed on whether the net's routing class "
    "carries a controlled-impedance geometry",
    "LAW-5 sizing-estimator VIA-COST term, NET-CLASS AWARE (user decree "
    "2026-07-30: \"vias are perfectly acceptable for all but most high speed "
    "components\"). The class set is DERIVED, never listed: a net is charged "
    "the impedance row iff schgen.generate.pcb.footprint._net_classes gives "
    "its class a DiffGeometry — i.e. the typed port declared an impedance, "
    "which is exactly DP90_USB / DP100_TMDS / DP<imp>_DIFF today and picks up "
    "any future impedance class for free; I2C, SD_<lv>, POWER and Default "
    "carry no geometry and take the ordinary row. IMPEDANCE = 7.6 mm: a "
    "controlled-impedance pair changes layers as a PAIR (2 legs, else the "
    "intra-pair skew budget — 0.15 mm for TMDS — is blown by the first "
    "unmatched via), each leg's via consumes its barrel (0.6 mm = "
    "THERMAL_VIA_SIZE) plus a clearance annulus (2 x 0.25 mm = "
    "THERMAL_VIA_CLEAR) of routing channel on BOTH signal layers, and each "
    "leg's transition adds the stackup's own 1.6 mm (JLC04161H-7628 4-layer) "
    "of unbudgeted stub/electrical length — so a block with many impedance "
    "nets loses its bottom variant on estimate, which is the intent (3.45x "
    "the ordinary row). ORDINARY = 2.2 mm is the same barrel+annulus channel "
    "on both signal layers. Wave-10 measured a STEP at 0+: sweeping the "
    "ordinary row at 0.0 / 0.1 / 1.0 / 2.2 / 3.0 with the bringup_rails "
    "opt-in gave 188x164 (30832 mm², cross 15558.8) at 0.0 and the identical, "
    "better 185x163 board (30155 mm², cross 15319.0) at every strictly-"
    "positive point, and attributed that step to the PUNCH-MODEL DEFECT of "
    "docs/BOTTOM_SIDE_MODEL_DEFECTS.md. WAVE-11 LANDED THAT FIX (edge blocks "
    "and the SoM now reserve only their own copper face + the geometry that "
    "genuinely pierces, releasing 8155.8 mm² = 27.0 % of the bottom surface) "
    "and RE-SWEPT: the step is GONE — 0.0 and 2.2 now emit the IDENTICAL, "
    "best board (185x163, 30155 mm², cross 15319.0, md5 "
    "8c093a49db4c7fc71edb1acc91ce756a). The whole swept range is one plateau, "
    "so there is NO measured reason to move the constant and 2.2 stays as its "
    "physically-derived member, not a fitted one. It remains INTERIM for a "
    "DIFFERENT, now-isolated reason: the est/emission gap SURVIVED the punch "
    "fix (measured — with power_mon bottom-eligible this estimator preferred "
    "the freed plan while the EMITTED cross came out +1217 mm worse), so the "
    "row cannot be re-derived toward its physical value until the estimator "
    "models what the post-floorplan movers (l4_pull / breathe / refit_facing "
    "/ reorder) do to a side flip. Until then the wave-11 monotonicity guard "
    "(fallback punch_free_plan_rejected) bounds the damage: a plan the freed "
    "reservation produces is kept only when it is strictly better on THIS "
    "estimator, ties to the conservative superset. DRC + the strict LAW-5 "
    "ratsnest gate remain the arbiters of any board it helped size.",
    "pre-proof")


def est_via_cost(impedance_controlled: bool) -> float:
    return EST_VIA_COST_MM["impedance" if impedance_controlled
                           else "ordinary"]


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
