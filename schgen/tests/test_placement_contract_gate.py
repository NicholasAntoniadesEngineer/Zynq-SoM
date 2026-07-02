"""Tests for the PLACEMENT-CONTRACT gate (schgen/verify/placement_contract_gate).

Two layers, mirroring the ``test_pcb_gate_mutation`` discipline:

(1) SYNTHETIC UNIT TESTS per structure type. Each builds a minimal PcbModel from
    the REAL LM61460 (and AP2112K) footprint pads, places the contract members
    either COMPLIANT (baseline: gate green) or DEFECTIVE (mutant: gate red), and
    asserts the mutant is killed. A baseline precedes every mutant (a gate that
    always fires proves nothing). Refs are injected via an identity ``ref_map``
    on a synthetic sheet, so the unit tests are hermetic + fast (no board build).

(2) The DECISIVE INTEGRATION TEST: build the REAL board model once
    (``build_model`` — the current known-bad "before": every critical passive is
    in a bottom-side value-sorted grid) and assert the gate FAILS it with >= 1
    hot_loop violation AND >= 1 same_side violation naming power-sheet refs. A
    gate that PASSES the before-board is itself defective (Phase-L wave-A rule).
    The full ``summary()`` is printed for the orchestrator to read.
"""

from __future__ import annotations

import pytest

from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
    resolve_mod,
)
from schgen.generate.pcb.footprint import pad_names
from schgen.verify import placement_contract_gate as g

_LM = "LM61460AANRJRR:LM61460AANRJRR"
_LDO = "Package_TO_SOT_SMD:SOT-23-5"
_C = "Capacitor_SMD:C_0603_1608Metric"
_R = "Resistor_SMD:R_0603_1608Metric"
_L = "SWPA8040S100MT:SWPA8040S100MT"   # the real buck inductor (pads 1=SW, 2=OUT)
_SHEET = "power"          # any name; ref_map is injected so no real sheet needed


# ---------------------------------------------------------------------------
# synthetic fixture builders
# ---------------------------------------------------------------------------

def _inst(ref: str, fp: str, x: float, y: float, side: str = "top",
          rot: float = 0.0) -> FootprintInst:
    mod = resolve_mod(fp)
    assert mod is not None, fp
    # every pad -> a distinct fake net (nets are irrelevant to this gate; it
    # measures geometry). Keeps FootprintInst well-formed.
    pad_nets = {p: (i + 1, f"{ref}_{p}") for i, p in enumerate(pad_names(mod))}
    return FootprintInst(ref=ref, value="x", footprint=fp,
                         x=ORIGIN_X + x, y=ORIGIN_Y + y, rotation=rot,
                         pad_nets=pad_nets, mod_path=mod, sheet=_SHEET, side=side)


def _model(*insts: FootprintInst) -> PcbModel:
    return PcbModel(
        board_w=80.0, board_h=60.0, insts=list(insts),
        net_numbers={"": 0}, netclass_of={}, classes={},
        placed=len(insts), deferred=[], n_top=len(insts), n_bottom=0,
        two_side=True)


def _pin_xy(inst: FootprintInst, pin: str) -> tuple[float, float]:
    """Board-frame center of a pin (for placing a member right at it)."""
    b = g._inst_pad_boxes(inst)[pin]
    return ((b[0] + b[2]) / 2 - ORIGIN_X, (b[1] + b[3]) / 2 - ORIGIN_Y)


# The IC sits at a fixed spot; its LM61460 pins (SNVSBD5D): 1 BIAS 2 VCC 3 AGND
# 4 FB 6 RT 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT 14 CBOOT.
_ICX, _ICY = 40.0, 30.0


def _ic(ref: str = "U1", x: float = _ICX, y: float = _ICY) -> FootprintInst:
    return _inst(ref, _LM, x, y)


def _at_pin(ref: str, ic: FootprintInst, pin: str, dxy: tuple[float, float],
            side: str = "top", fp: str = _C) -> FootprintInst:
    """A passive placed at IC ``pin`` + offset (dx,dy) mm."""
    px, py = _pin_xy(ic, pin)
    return _inst(ref, fp, px + dxy[0], py + dxy[1], side=side)


def _idmap(*refs: str) -> dict[str, str]:
    """Identity ref_map so the contract's library refs ARE the board refs."""
    return {r: r for r in refs}


# ---------------------------------------------------------------------------
# (1a) HOT LOOP — existential per VIN/PGND pin-pair, same side as IC
# ---------------------------------------------------------------------------

def _hot_loop_contract() -> dict:
    return {"structures": [
        {"type": "hot_loop", "ic": "U1",
         "pin_pairs": [["8", "9"], ["12", "11"]], "caps": ["C1", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True, "basis": "b"}]}


def test_hot_loop_baseline_passes():
    """BASELINE: a 100 nF touching each VIN/PGND pin-pair, same side -> green."""
    ic = _ic()
    # pad 8 (VIN1) and 12 (VIN2) are the two input pins; drop a cap ~0.3 mm off
    # each so the pad-edge gap stays under the 1.0 mm limit.
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4))
    c25 = _at_pin("C25", ic, "12", (0.0, 0.4))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok, res.summary()
    assert res.hot_loop_fail == 0


def test_hot_loop_far_mutant_is_killed():
    """MUTANT: both HF caps shoved 8 mm away -> neither pin-pair has a 100 nF
    within 1 mm -> 2 hot_loop violations (one per pair)."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 8.0))
    c25 = _at_pin("C25", ic, "12", (0.0, 8.0))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok is False
    assert res.hot_loop_fail == 2, res.summary()


def test_hot_loop_wrong_side_mutant_is_killed():
    """MUTANT (the before-board defect class): the HF caps are tight to the pins
    but on the BOTTOM while the IC is on TOP -> the same-side filter rejects
    them, so every VIN/PGND pair fails existentially."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4), side="bottom")
    c25 = _at_pin("C25", ic, "12", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok is False
    assert res.hot_loop_fail == 2, res.summary()


def test_hot_loop_is_existential_not_per_ref():
    """A SWAPPED assignment (C25 at pair-1, C1 at pair-2) must still PASS — the
    gate checks each pin-pair for SOME listed cap, never a specific ref->pin."""
    ic = _ic()
    c25 = _at_pin("C25", ic, "8", (0.0, 0.4))     # swapped vs the baseline
    c1 = _at_pin("C1", ic, "12", (0.0, 0.4))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok, res.summary()


# ---------------------------------------------------------------------------
# (1b) BULK IN — <= 5 mm of a VIN pin
# ---------------------------------------------------------------------------

def _bulk_contract() -> dict:
    return {"structures": [
        {"type": "bulk_in", "ic": "U1", "caps": ["C2"],
         "vin_pins": ["8", "12"], "max_pad_to_pin_mm": 5.0, "basis": "b"}]}


def test_bulk_baseline_passes():
    ic = _ic()
    c2 = _at_pin("C2", ic, "8", (0.0, 3.0))
    res = g.check(_model(ic, c2), _SHEET, _bulk_contract(),
                  ref_map=_idmap("U1", "C2"))
    assert res.ok and res.bulk_fail == 0, res.summary()


def test_bulk_far_mutant_is_killed():
    ic = _ic()
    c2 = _at_pin("C2", ic, "8", (0.0, 12.0))
    res = g.check(_model(ic, c2), _SHEET, _bulk_contract(),
                  ref_map=_idmap("U1", "C2"))
    assert res.ok is False and res.bulk_fail == 1, res.summary()


# ---------------------------------------------------------------------------
# (1b') BULK OUT — every COUT <= 5 mm of the inductor OUTPUT pad, same side (v2)
# ---------------------------------------------------------------------------

def _bulk_out_contract() -> dict:
    return {"structures": [
        {"type": "bulk_out", "ic": "U1", "caps": ["C5", "C6"],
         "inductor": "L1", "inductor_out_pin": "2",
         "max_pad_to_pin_mm": 5.0, "same_side": True, "basis": "b"}]}


def _at_ind_pin(ref: str, ind: FootprintInst, pin: str,
                dxy: tuple[float, float], side: str = "top") -> FootprintInst:
    """A COUT cap placed at the inductor ``pin`` + offset (mm)."""
    b = g._inst_pad_boxes(ind)[pin]
    px = (b[0] + b[2]) / 2 - ORIGIN_X
    py = (b[1] + b[3]) / 2 - ORIGIN_Y
    return _inst(ref, _C, px + dxy[0], py + dxy[1], side=side)


def test_bulk_out_baseline_passes():
    """BASELINE: both COUT caps ~1 mm beyond the inductor OUTPUT pad (pad 2),
    same side as the IC -> green. The IC anchors same-side; L1 holds the pad."""
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)   # inductor near SW
    # inductor pad 2 (output) is at the far +X edge of L1; drop caps just past it
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5))
    c6 = _at_ind_pin("C6", l1, "2", (2.5, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok and res.bulk_out_fail == 0, res.summary()


def test_bulk_out_far_mutant_is_killed():
    """MUTANT (the v1 defect class): the COUT caps land ~10 mm away (the
    bottom-side value-sorted grid) -> every COUT is out of bound (universal
    check, not existential — BOTH fail)."""
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (10.0, -1.5))
    c6 = _at_ind_pin("C6", l1, "2", (10.0, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 2, res.summary()


def test_bulk_out_partial_mutant_is_killed():
    """MUTANT: ONE COUT is tight but the OTHER is far — proves the check is
    UNIVERSAL (every member in-bound), so a stray cap cannot hide behind a
    compliant sibling the way the existential hot_loop tolerates."""
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5))      # tight
    c6 = _at_ind_pin("C6", l1, "2", (12.0, 1.5))      # far
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 1, res.summary()


def test_bulk_out_wrong_side_mutant_is_killed():
    """MUTANT (the exact v1 defect: COUT relocated to the bottom grid): a COUT
    tight to the output pad but on the BOTTOM while the IC is on TOP fails the
    same_side clause of bulk_out."""
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5), side="bottom")
    c6 = _at_ind_pin("C6", l1, "2", (2.5, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 1, res.summary()
    assert any("bulk_out U1 C5" in v and "bottom" in v
               for v in res.violations), res.summary()


# ---------------------------------------------------------------------------
# (1c) SW NODE — inductor <= 3 mm of the SW pad
# ---------------------------------------------------------------------------

def _sw_contract() -> dict:
    return {"structures": [
        {"type": "sw_node", "ic": "U1", "inductor": "L1", "sw_pin": "10",
         "max_pad_to_pin_mm": 3.0, "basis": "b"}]}


def test_sw_node_baseline_passes():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (2.0, 0.0), fp=_C)
    res = g.check(_model(ic, l1), _SHEET, _sw_contract(),
                  ref_map=_idmap("U1", "L1"))
    assert res.ok and res.sw_node_fail == 0, res.summary()


def test_sw_node_far_mutant_is_killed():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (10.0, 0.0), fp=_C)
    res = g.check(_model(ic, l1), _SHEET, _sw_contract(),
                  ref_map=_idmap("U1", "L1"))
    assert res.ok is False and res.sw_node_fail == 1, res.summary()


# ---------------------------------------------------------------------------
# (1d) FB CLUSTER — <= 3 mm of FB, >= 3 mm own SW/L, >= 5 mm foreign SW/L
# ---------------------------------------------------------------------------

def _fb_contract() -> dict:
    return {"structures": [
        {"type": "fb_cluster", "ic": "U1", "fb_pin": "4", "members": ["R1"],
         "own_sw_pin": "10", "own_inductor": "L1",
         "foreign_ic": "U2", "foreign_sw_pin": "10", "foreign_inductor": "L2",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 3.0,
         "min_to_foreign_sw_mm": 5.0, "basis": "b"}]}


def _fb_scene(r1_off, l1_off=(20.0, 0.0), u2_x=200.0):
    """IC + FB resistor R1 (offset from FB pin 4, on the FB/left side of the IC,
    away from the SW pad on the right) + own inductor L1 far off the SW side + a
    foreign buck U2/L2 far away, so ONLY the R1->FB distance governs unless a
    mutant moves L1/L2 near. The LM61460 FB pin (4, left edge) and SW pad (10,
    right edge) are ~3.5 mm apart, so R1 is offset LEFTWARD (-X) to sit close to
    FB yet clear of the own SW pin — the layout the datasheet requires."""
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", r1_off, fp=_R)
    l1 = _at_pin("L1", ic, "10", l1_off, fp=_C)
    u2 = _ic("U2", x=u2_x, y=_ICY)
    l2 = _at_pin("L2", u2, "10", (5.0, 0.0), fp=_C)
    return ic, r1, l1, u2, l2


def test_fb_baseline_passes():
    # R1 to the LEFT of FB pin 4 (away from the SW pad on the IC's right edge):
    # <= 3 mm of FB yet >= 3 mm from the own SW pad (a 0603 body is 2.5 mm and
    # the LM61460 FB<->SW pad span is small, so this is the real datasheet
    # tension the contract encodes).
    ic, r1, l1, u2, l2 = _fb_scene(r1_off=(-3.5, 0.0))
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok and res.fb_fail == 0, res.summary()


def test_fb_far_from_fb_mutant_is_killed():
    ic, r1, l1, u2, l2 = _fb_scene(r1_off=(0.0, 9.0))
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok is False and res.fb_fail >= 1, res.summary()
    assert any("to FB pin 4" in v for v in res.violations), res.summary()


def test_fb_too_close_to_own_sw_mutant_is_killed():
    """MUTANT: R1 stays near FB but the own inductor L1 is placed right on it
    (< 3 mm) -> the FB-vs-own-SW/L separation fails."""
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", (0.0, 2.0), fp=_R)
    # put L1 essentially on top of R1
    rx, ry = _pin_xy(ic, "4")
    l1 = _inst("L1", _C, rx + 0.0, ry + 2.5)      # ~0.5 mm from R1
    u2 = _ic("U2", x=200.0, y=_ICY)
    l2 = _at_pin("L2", u2, "10", (5.0, 0.0), fp=_C)
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok is False and res.fb_fail >= 1, res.summary()
    assert any("from own SW/L" in v for v in res.violations), res.summary()


def test_fb_too_close_to_foreign_sw_mutant_is_killed():
    """MUTANT: the foreign buck's inductor L2 is brought within 5 mm of R1."""
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", (0.0, 2.0), fp=_R)
    l1 = _at_pin("L1", ic, "10", (20.0, 0.0), fp=_C)
    rx, ry = _pin_xy(ic, "4")
    u2 = _ic("U2", x=200.0, y=_ICY)
    l2 = _inst("L2", _C, rx + 2.0, ry + 2.0)      # ~a couple mm from R1
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok is False and res.fb_fail >= 1, res.summary()
    assert any("from foreign U2 SW/L" in v for v in res.violations), res.summary()


# ---------------------------------------------------------------------------
# (1e) BOOT / VCC / BIAS / RT — simple pin-proximity structures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("typ,ref,pin_key,pin,lim,attr", [
    ("boot", "C4", "pins", ["13", "14"], 2.0, "boot_fail"),
    ("vcc_cap", "C24", "pin", "2", 2.0, "vcc_fail"),
    ("bias_cap", "C28", "pin", "1", 3.0, "bias_fail"),
    ("rt_r", "R10", "pin", "6", 3.0, "rt_fail"),
])
def test_proximity_structures_baseline_and_mutant(typ, ref, pin_key, pin, lim,
                                                  attr):
    """BASELINE tight + MUTANT far for each single-pin proximity structure."""
    refkey = {"rt_r": "resistor"}.get(typ, "cap")
    pinval = pin if pin_key == "pin" else pin
    st = {"type": typ, "ic": "U1", refkey: ref, pin_key: pinval,
          "max_pad_to_pin_mm": lim, "basis": "b"}
    contract = {"structures": [st]}
    idm = _idmap("U1", ref)
    anchor = pin[0] if isinstance(pin, list) else pin

    # baseline: passive ~0.4 mm off the target pin
    ic = _ic()
    near = _at_pin(ref, ic, anchor, (0.4, 0.0),
                   fp=_R if typ == "rt_r" else _C)
    res = g.check(_model(ic, near), _SHEET, contract, ref_map=idm)
    assert res.ok, f"{typ} baseline: {res.summary()}"
    assert getattr(res, attr) == 0

    # mutant: shove it well past the limit
    ic = _ic()
    far = _at_pin(ref, ic, anchor, (lim + 6.0, 0.0),
                  fp=_R if typ == "rt_r" else _C)
    res = g.check(_model(ic, far), _SHEET, contract, ref_map=idm)
    assert res.ok is False, f"{typ} mutant not killed: {res.summary()}"
    assert getattr(res, attr) == 1, res.summary()


# ---------------------------------------------------------------------------
# (1f) LDO STAGE — Cin/Cout <= 2 mm of the LDO pins
# ---------------------------------------------------------------------------

def _ldo_contract() -> dict:
    return {"structures": [
        {"type": "ldo_stage", "ic": "U3", "cin": "C12", "cin_pin": "1",
         "cout": "C13", "cout_pin": "5", "max_pad_to_pin_mm": 2.0,
         "basis": "b"}]}


def test_ldo_baseline_passes():
    u3 = _inst("U3", _LDO, 40.0, 30.0)
    cin = _at_pin("C12", u3, "1", (0.6, 0.0))
    cout = _at_pin("C13", u3, "5", (0.6, 0.0))
    res = g.check(_model(u3, cin, cout), _SHEET, _ldo_contract(),
                  ref_map=_idmap("U3", "C12", "C13"))
    assert res.ok and res.ldo_fail == 0, res.summary()


def test_ldo_far_mutant_is_killed():
    u3 = _inst("U3", _LDO, 40.0, 30.0)
    cin = _at_pin("C12", u3, "1", (8.0, 0.0))
    cout = _at_pin("C13", u3, "5", (8.0, 0.0))
    res = g.check(_model(u3, cin, cout), _SHEET, _ldo_contract(),
                  ref_map=_idmap("U3", "C12", "C13"))
    assert res.ok is False and res.ldo_fail == 2, res.summary()


# ---------------------------------------------------------------------------
# (1g) SAME SIDE — contract members must share the IC's PCB side
# ---------------------------------------------------------------------------

def _same_side_contract() -> dict:
    return {"roles": {"U1": "buck_ic", "C1": "cin_hf@VIN1"},
            "structures": [
                {"type": "hot_loop", "ic": "U1",
                 "pin_pairs": [["8", "9"]], "caps": ["C1"],
                 "max_pad_to_pin_mm": 1.0, "same_side": True, "basis": "b"},
                {"type": "same_side", "ics": ["U1"], "basis": "b"}]}


def test_same_side_baseline_passes():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4))       # top, same as IC
    res = g.check(_model(ic, c1), _SHEET, _same_side_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok and res.same_side_fail == 0, res.summary()


def test_same_side_mutant_is_killed():
    """MUTANT: the member is on the BOTTOM while its IC is on TOP (the exact
    before-board defect: small passives relocated to the bottom grid)."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1), _SHEET, _same_side_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False and res.same_side_fail == 1, res.summary()
    assert any("same_side U1 C1" in v for v in res.violations), res.summary()


# ---------------------------------------------------------------------------
# registry + no-contract behaviour
# ---------------------------------------------------------------------------

def test_load_contract_power_present_and_versioned():
    c = g.load_contract("power")
    assert c is not None and c["contract"] == "placement/v2"
    assert c["sheet"] == "power"
    # every structure threshold carries a basis string
    for st in c["structures"]:
        assert st.get("basis"), st


def test_load_contract_absent_returns_none():
    assert g.load_contract("no_such_subsystem_xyz") is None


def test_no_contract_passes_vacuously():
    ic = _ic()
    res = g.check(_model(ic), "no_such_subsystem_xyz")
    assert res.ok and res.have_contract is False


def test_summary_is_deterministic():
    """summary() sorts its violation list, so two runs are byte-identical."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 8.0), side="bottom")
    c25 = _at_pin("C25", ic, "12", (0.0, 8.0), side="bottom")
    contract = _hot_loop_contract()
    idm = _idmap("U1", "C1", "C25")
    s1 = g.check(_model(ic, c1, c25), _SHEET, contract, ref_map=idm).summary()
    s2 = g.check(_model(ic, c1, c25), _SHEET, contract, ref_map=idm).summary()
    assert s1 == s2


# ---------------------------------------------------------------------------
# (2) INTEGRATION — the STAGE TEMPLATE (Phase-L wave B) makes the board GREEN
# ---------------------------------------------------------------------------
# WAVE A -> B TRANSITION: this test was authored in wave A, when NO template
# existed, to prove the gate BIT the value-sorted "before" board (>=1 hot_loop +
# >=1 same_side violation). Wave B landed the stage-template engine
# (schgen/generate/pcb/stage_templates.py), which now constructs the datasheet
# layout for the ``power`` sheet, so ``build_model`` emits a COMPLIANT power zone
# and the gate PASSES it. The assertion is inverted accordingly: the decisive
# check is now that the templated board is GREEN. (The gate's ability to BITE a
# broken layout stays fully covered by the synthetic mutant tests above — every
# structure type has a killed mutant — so this inversion loses no gate coverage.)


@pytest.fixture(scope="module")
def _real_model():
    """Build the REAL board model ONCE (~60-120 s). With the stage template
    active, the ``power`` sheet is laid out to the SNVSBD5D datasheet contract."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


def test_gate_is_green_on_the_templated_board(_real_model):
    """DECISIVE (wave B): the placement-contract gate PASSES the emitted power
    zone — the stage template placed every structure within its datasheet bound,
    so ok=True with 0 violations and no unresolved refs."""
    res = g.check(_real_model, "power")
    # print the full verdict for the orchestrator
    print("\n" + res.summary())

    assert res.have_contract is True
    assert res.missing_refs == [], (
        f"contract refs did not map to board refs: {res.missing_refs}")
    assert res.ok is True, (
        "the stage template did NOT satisfy the placement contract:\n"
        + res.summary())
    assert not res.violations, res.summary()
