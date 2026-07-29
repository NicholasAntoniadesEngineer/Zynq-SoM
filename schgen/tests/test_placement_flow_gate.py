"""Tests for the COMPOSITION-LEVEL PLACEMENT-FLOW gate
(schgen/verify/placement_flow_gate).

Two layers, mirroring the intra-zone gate's test discipline:

(1) SYNTHETIC UNIT TESTS per external-term type (FLOW / FACING / FAR). Each builds
    a minimal PcbModel of a few placed footprints (one per sheet is enough — the
    gate reasons about zone CENTROIDS, not pad geometry), places the zones either
    COMPLIANT (baseline: gate green) or DEFECTIVE (mutant: gate red), and asserts
    the mutant is killed. A baseline precedes every mutant. Contracts + ref maps
    are injected so the tests are hermetic + fast (no board build).

(2) The INTEGRATION check: build the REAL board model once and print the gate
    summary for the orchestrator (and assert the power contract's external block
    is exercised).
"""

from __future__ import annotations

import pytest

from schgen.generate.pcb import (
    FootprintInst,
    PcbModel,
    resolve_mod,
)
from schgen.generate.pcb.footprint import pad_names
from schgen.verify import placement_flow_gate as g

_C = "Capacitor_SMD:C_0603_1608Metric"


# ---------------------------------------------------------------------------
# synthetic fixture builders — one (or a few) placed part(s) per sheet
# ---------------------------------------------------------------------------

def _inst(ref: str, sheet: str, x: float, y: float,
          side: str = "top", fp: str = _C) -> FootprintInst:
    mod = resolve_mod(fp)
    assert mod is not None, fp
    pad_nets = {p: (i + 1, f"{ref}_{p}") for i, p in enumerate(pad_names(mod))}
    return FootprintInst(ref=ref, value="x", footprint=fp,
                         x=x, y=y, rotation=0.0, pad_nets=pad_nets,
                         mod_path=mod, sheet=sheet, side=side)


def _model(insts, board_w=170.0, board_h=145.0) -> PcbModel:
    lst = list(insts)
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=lst,
        net_numbers={"": 0}, netclass_of={}, classes={},
        placed=len(lst), deferred=[], n_top=len(lst), n_bottom=0,
        two_side=True)


# a placed part at the CENTROID we want for a sheet (single part == that centroid)
def _zone(sheet: str, x: float, y: float, ref: str | None = None) -> FootprintInst:
    return _inst(ref or f"C{sheet}", sheet, x, y)


# ---------------------------------------------------------------------------
# (1a) FLOW — each consecutive hop within FLOW_K*sqrt(area)
# ---------------------------------------------------------------------------

def _flow_contract() -> dict:
    return {"contract": "placement/test",
            "external": {"flow": ["usb_pd", "power", "power_som"]}}


def test_flow_baseline_passes():
    """BASELINE: the three flow zones sit in a short chain (each hop well within
    the ~55 mm budget on a 170x145 board) -> green."""
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),        # ~22 mm from usb_pd
        _zone("power_som", 60.0, 40.0),    # ~22 mm from power
    ])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok, res.summary()
    assert res.flow_fail == 0 and res.flow_checked == 2, res.summary()


def test_flow_far_hop_mutant_is_killed():
    """MUTANT: power_som parked on the FAR edge — the power->power_som hop blows
    the board-scaled budget -> 1 flow violation."""
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),
        _zone("power_som", 165.0, 140.0),  # opposite corner (~165 mm from power)
    ])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok is False, res.summary()
    assert res.flow_fail == 1, res.summary()
    assert any("flow power->power_som" in v for v in res.violations), res.summary()


def test_flow_budget_scales_with_board_area():
    """The SAME geometry that fails on a small board passes on a large one — the
    budget is FLOW_K*sqrt(area), not a fixed constant."""
    insts = [
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 30.0, 24.0),        # ~11.7 mm from usb_pd (in budget on big)
        _zone("power_som", 110.0, 90.0),   # ~102 mm from power
    ]
    small = g.check(_model(insts, board_w=60.0, board_h=60.0),
                    contracts={"power": _flow_contract()})
    big = g.check(_model(insts, board_w=400.0, board_h=400.0),
                  contracts={"power": _flow_contract()})
    assert small.flow_fail == 1, small.summary()   # budget ~21 mm -> only hop 2 fails
    assert big.flow_fail == 0, big.summary()       # budget ~140 mm -> passes


def test_flow_som_detour_widens_budget():
    """A central SoM keepout (``som_core``) adds its diagonal to the budget: a hop
    that FAILS the free-space budget alone PASSES once the go-around detour is
    credited (the center-module carrier reality — opposite-side chain zones cannot
    be closer than routing around the SoM)."""
    insts = [
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 30.0, 24.0),
        _zone("power_som", 90.0, 60.0),    # ~70 mm from power
    ]
    # free budget on a 100x100 board = 0.35*100 = 35 mm -> the 2nd hop fails.
    m_no_som = _model(insts, board_w=100.0, board_h=100.0)
    res_no = g.check(m_no_som, contracts={"power": _flow_contract()})
    assert res_no.flow_fail == 1, res_no.summary()
    # add a big central SoM (diagonal ~70 mm) -> budget ~105 mm -> the hop passes.
    m_som = _model(insts, board_w=100.0, board_h=100.0)
    m_som.som_core = (20.0, 20.0, 70.0, 70.0)      # 50x50 -> diag ~70.7 mm
    res_som = g.check(m_som, contracts={"power": _flow_contract()})
    assert res_som.flow_fail == 0, res_som.summary()
    assert res_som.flow_budget_mm > res_no.flow_budget_mm, res_som.summary()


def test_flow_missing_zone_is_unresolved_and_fails():
    """A flow zone with NO placed part is UNRESOLVED and fails (strict)."""
    m = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved, res.summary()
    assert res.flow_fail == 1, res.summary()


# ---------------------------------------------------------------------------
# (1b) FACING — output parts on the downstream-facing half of the zone
# ---------------------------------------------------------------------------

def _facing_contract() -> dict:
    return {"contract": "placement/test",
            "roles": {"U1": "buck_ic", "C5": "cout_bulk", "C6": "cout_bulk"},
            "external": {"downstream": "power_som",
                         "output_roles": ["cout_bulk"]}}


def _facing_refmap() -> dict:
    return {"power": {"U1": "U1", "C5": "C5", "C6": "C6"}}


def test_facing_baseline_passes():
    """BASELINE: the COUT parts sit on the +X side of the power zone, and
    power_som is to the +X (downstream) — dot > 0 -> green."""
    m = _model([
        _inst("U1", "power", 40.0, 30.0),     # IC anchors the zone body (-X)
        _inst("C5", "power", 48.0, 30.0),     # output caps on the +X side
        _inst("C6", "power", 48.0, 32.0),
        _zone("power_som", 80.0, 30.0),       # downstream to the +X
    ])
    res = g.check(m, contracts={"power": _facing_contract()},
                  ref_maps=_facing_refmap())
    assert res.ok, res.summary()
    assert res.facing_fail == 0 and res.facing_checked == 1, res.summary()


def test_facing_wrong_way_mutant_is_killed():
    """MUTANT (the pilot OPEN(a) defect): the COUT parts face the -X edge while
    power_som is to the +X — output faces AWAY from downstream, dot <= 0."""
    m = _model([
        _inst("U1", "power", 40.0, 30.0),
        _inst("C5", "power", 32.0, 30.0),     # output caps on the -X side
        _inst("C6", "power", 32.0, 32.0),
        _zone("power_som", 80.0, 30.0),       # downstream to the +X
    ])
    res = g.check(m, contracts={"power": _facing_contract()},
                  ref_maps=_facing_refmap())
    assert res.ok is False, res.summary()
    assert res.facing_fail == 1, res.summary()
    assert any("face AWAY" in v for v in res.violations), res.summary()


def test_facing_no_output_role_is_unresolved():
    """A downstream declared but output_roles matching NO role -> unresolved."""
    c = {"contract": "placement/test",
         "roles": {"U1": "buck_ic"},
         "external": {"downstream": "power_som", "output_roles": ["nope"]}}
    m = _model([_inst("U1", "power", 40.0, 30.0), _zone("power_som", 80.0, 30.0)])
    res = g.check(m, contracts={"power": c}, ref_maps={"power": {"U1": "U1"}})
    assert res.ok is False, res.summary()
    assert res.facing_fail == 1 and res.unresolved, res.summary()


# ---------------------------------------------------------------------------
# (1c) FAR — declared minimum separations between named zones (strict resolve)
# ---------------------------------------------------------------------------

def _far_contract(min_mm=10.0, what="ethernet.line_side") -> dict:
    return {"contract": "placement/test",
            "external": {"far": [{"what": what, "min_mm": min_mm, "basis": "j"}]}}


def test_far_baseline_passes():
    """BASELINE: power and ethernet zones are 40 mm apart >= the 10 mm moat."""
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 80.0, 30.0)])
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok, res.summary()
    assert res.far_fail == 0 and res.far_checked == 1, res.summary()


def test_far_too_close_mutant_is_killed():
    """MUTANT: ethernet is crowded within the 10 mm moat of power."""
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 45.0, 32.0)])
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok is False, res.summary()
    assert res.far_fail == 1, res.summary()
    assert any("vs ethernet.line_side" in v for v in res.violations), res.summary()


def test_far_coarsens_region_to_zone():
    """A ``zone.region`` target resolves to the ``zone`` centroid (documented
    coarsening) — ``ethernet.line_side`` measures against the ``ethernet`` zone."""
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 80.0, 30.0)])
    res = g.check(m, contracts={"power": _far_contract(what="ethernet.line_side")})
    assert res.far_checked == 1 and res.far_fail == 0, res.summary()
    assert any("ethernet.line_side" in d and "40.00mm" in d
               for d in res.detail), res.summary()


def test_far_unresolved_target_fails_strict():
    """A FAR target that resolves to NO placed zone is UNRESOLVED and FAILS —
    never a silent skip (LAW 4)."""
    m = _model([_zone("power", 40.0, 30.0)])   # no ethernet zone placed
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.far_fail == 1, res.summary()
    assert any("UNRESOLVED" in v for v in res.violations), res.summary()


# ---------------------------------------------------------------------------
# determinism + no-external behaviour
# ---------------------------------------------------------------------------

def test_summary_is_deterministic():
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),
        _zone("power_som", 165.0, 140.0),
    ])
    c = {"power": _flow_contract()}
    s1 = g.check(m, contracts=c).summary()
    s2 = g.check(m, contracts=c).summary()
    assert s1 == s2


def test_no_external_block_contributes_nothing():
    m = _model([_zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": {"contract": "x"}})
    assert res.ok and res.n_contracts == 0, res.summary()


# ---------------------------------------------------------------------------
# (2) INTEGRATION — the real board's power external block is exercised
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_flow_gate_runs_on_the_real_board(_real_model):
    """The gate loads the power contract's external block from the registry and
    checks it on the emitted board. Prints the summary for the orchestrator."""
    res = g.check(_real_model)
    print("\n" + res.summary())
    assert res.n_contracts >= 1, "the power external contract was not exercised"
    # every declared flow/facing/far term was examined (a number, not silence)
    assert res.flow_checked >= 2, res.summary()
    assert res.facing_checked >= 1, res.summary()
    assert res.far_checked >= 1, res.summary()


# ---------------------------------------------------------------------------
# (3) T1 P1 — single-oracle metric kernels (identity: kernel == gate report)
# ---------------------------------------------------------------------------

def test_flow_budget_kernel_matches_gate_report():
    """IDENTITY: the published ``flow_budget`` kernel computes EXACTLY the
    budget the gate reports (``flow_budget_mm``) — with and without a placed
    SoM core. The composition engine recomputes per-candidate budgets through
    this kernel, so any drift here is an engine/gate split-brain."""
    m = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.flow_budget_mm == round(
        g.flow_budget(m.board_w, m.board_h, m.som_core), 4), res.summary()

    m2 = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    m2.som_core = (60.0, 60.0, 111.0, 103.0)
    res2 = g.check(m2, contracts={"power": _flow_contract()})
    assert res2.flow_budget_mm == round(
        g.flow_budget(m2.board_w, m2.board_h, m2.som_core), 4), res2.summary()
    assert res2.flow_budget_mm > res.flow_budget_mm   # SoM detour widens


def test_facing_dot_kernel_matches_gate_detail():
    """IDENTITY: ``facing_dot`` reproduces the dot/angle the FACING check
    prints in its detail line."""
    dot, angle = g.facing_dot((10.0, 10.0), (12.0, 10.0), (20.0, 10.0))
    assert dot > 0.0 and angle == 0.0
    dot2, angle2 = g.facing_dot((10.0, 10.0), (8.0, 10.0), (20.0, 10.0))
    assert dot2 < 0.0 and angle2 == 180.0
    # degenerate zero-length output vector reports 180 (the gate's convention)
    _d3, a3 = g.facing_dot((10.0, 10.0), (10.0, 10.0), (20.0, 10.0))
    assert a3 == 180.0


def test_bbox_gap_public_and_aliases_are_same_objects():
    """The pre-P1 private names remain bound to the SAME function objects (no
    fork, no drift; back-compat only)."""
    assert g._bbox_gap is g.bbox_gap
    assert g._zone_centroids is g.zone_centroids
    assert g._zone_bboxes is g.zone_bboxes
    assert g.bbox_gap((0, 0, 1, 1), (3, 0, 4, 1)) == 2.0
    assert g.bbox_gap((0, 0, 2, 2), (1, 1, 3, 3)) == 0.0   # overlap -> 0


def test_som_core_rect_kernel_matches_build_model_arithmetic():
    """IDENTITY: ``som_core_rect`` reproduces the exact som_core arithmetic
    build_model used inline pre-P1 (ORIGIN shift + 3% centred growth)."""
    from schgen.generate.pcb.constants import (
        ORIGIN_X,
        ORIGIN_Y,
        SOM_CORE_CLEARANCE,
    )
    from schgen.generate.pcb.placement import som_core_rect
    sx, sy, sw, sh = 59.5, 54.0, 51.0, 43.0
    ccx = sw * SOM_CORE_CLEARANCE / 2
    ccy = sh * SOM_CORE_CLEARANCE / 2
    assert som_core_rect(sx, sy, sw, sh) == (
        ORIGIN_X + sx - ccx, ORIGIN_Y + sy - ccy,
        ORIGIN_X + sx + sw + ccx, ORIGIN_Y + sy + sh + ccy)
