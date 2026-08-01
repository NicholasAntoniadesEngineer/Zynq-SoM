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
_L = "SWPA8040S100MT:SWPA8040S100MT"
_SHEET = "power"


def _inst(ref: str, fp: str, x: float, y: float, side: str = "top",
          rot: float = 0.0) -> FootprintInst:
    mod = resolve_mod(fp)
    assert mod is not None, fp
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
    b = g._inst_pad_boxes(inst)[pin]
    return ((b[0] + b[2]) / 2 - ORIGIN_X, (b[1] + b[3]) / 2 - ORIGIN_Y)


_ICX, _ICY = 40.0, 30.0


def _ic(ref: str = "U1", x: float = _ICX, y: float = _ICY) -> FootprintInst:
    return _inst(ref, _LM, x, y)


def _at_pin(ref: str, ic: FootprintInst, pin: str, dxy: tuple[float, float],
            side: str = "top", fp: str = _C) -> FootprintInst:
    px, py = _pin_xy(ic, pin)
    return _inst(ref, fp, px + dxy[0], py + dxy[1], side=side)


def _idmap(*refs: str) -> dict[str, str]:
    return {r: r for r in refs}


def _hot_loop_contract() -> dict:
    return {"structures": [
        {"type": "hot_loop", "ic": "U1",
         "pin_pairs": [["8", "9"], ["12", "11"]], "caps": ["C1", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True, "basis": "b"}]}


def test_hot_loop_baseline_passes():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4))
    c25 = _at_pin("C25", ic, "12", (0.0, 0.4))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok, res.summary()
    assert res.hot_loop_fail == 0


def test_hot_loop_far_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 8.0))
    c25 = _at_pin("C25", ic, "12", (0.0, 8.0))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok is False
    assert res.hot_loop_fail == 2, res.summary()


def test_hot_loop_wrong_side_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4), side="bottom")
    c25 = _at_pin("C25", ic, "12", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok is False
    assert res.hot_loop_fail == 2, res.summary()


def test_hot_loop_is_existential_not_per_ref():
    ic = _ic()
    c25 = _at_pin("C25", ic, "8", (0.0, 0.4))
    c1 = _at_pin("C1", ic, "12", (0.0, 0.4))
    res = g.check(_model(ic, c1, c25), _SHEET, _hot_loop_contract(),
                  ref_map=_idmap("U1", "C1", "C25"))
    assert res.ok, res.summary()


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


def _bulk_out_contract() -> dict:
    return {"structures": [
        {"type": "bulk_out", "ic": "U1", "caps": ["C5", "C6"],
         "inductor": "L1", "inductor_out_pin": "2",
         "max_pad_to_pin_mm": 5.0, "same_side": True, "basis": "b"}]}


def _at_ind_pin(ref: str, ind: FootprintInst, pin: str,
                dxy: tuple[float, float], side: str = "top") -> FootprintInst:
    b = g._inst_pad_boxes(ind)[pin]
    px = (b[0] + b[2]) / 2 - ORIGIN_X
    py = (b[1] + b[3]) / 2 - ORIGIN_Y
    return _inst(ref, _C, px + dxy[0], py + dxy[1], side=side)


def test_bulk_out_baseline_passes():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5))
    c6 = _at_ind_pin("C6", l1, "2", (2.5, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok and res.bulk_out_fail == 0, res.summary()


def test_bulk_out_far_mutant_is_killed():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (10.0, -1.5))
    c6 = _at_ind_pin("C6", l1, "2", (10.0, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 2, res.summary()


def test_bulk_out_partial_mutant_is_killed():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5))
    c6 = _at_ind_pin("C6", l1, "2", (12.0, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 1, res.summary()


def test_bulk_out_wrong_side_mutant_is_killed():
    ic = _ic()
    l1 = _at_pin("L1", ic, "10", (8.0, 0.0), fp=_L)
    c5 = _at_ind_pin("C5", l1, "2", (2.5, -1.5), side="bottom")
    c6 = _at_ind_pin("C6", l1, "2", (2.5, 1.5))
    res = g.check(_model(ic, l1, c5, c6), _SHEET, _bulk_out_contract(),
                  ref_map=_idmap("U1", "L1", "C5", "C6"))
    assert res.ok is False and res.bulk_out_fail == 1, res.summary()
    assert any("bulk_out U1 C5" in v and "bottom" in v
               for v in res.violations), res.summary()


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


def _fb_contract() -> dict:
    return {"structures": [
        {"type": "fb_cluster", "ic": "U1", "fb_pin": "4", "members": ["R1"],
         "own_sw_pin": "10", "own_inductor": "L1",
         "foreign_ic": "U2", "foreign_sw_pin": "10", "foreign_inductor": "L2",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 3.0,
         "min_to_foreign_sw_mm": 5.0, "basis": "b"}]}


def _fb_scene(r1_off, l1_off=(20.0, 0.0), u2_x=200.0):
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", r1_off, fp=_R)
    l1 = _at_pin("L1", ic, "10", l1_off, fp=_C)
    u2 = _ic("U2", x=u2_x, y=_ICY)
    l2 = _at_pin("L2", u2, "10", (5.0, 0.0), fp=_C)
    return ic, r1, l1, u2, l2


def test_fb_baseline_passes():
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
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", (0.0, 2.0), fp=_R)
    rx, ry = _pin_xy(ic, "4")
    l1 = _inst("L1", _C, rx + 0.0, ry + 2.5)
    u2 = _ic("U2", x=200.0, y=_ICY)
    l2 = _at_pin("L2", u2, "10", (5.0, 0.0), fp=_C)
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok is False and res.fb_fail >= 1, res.summary()
    assert any("from own SW/L" in v for v in res.violations), res.summary()


def test_fb_too_close_to_foreign_sw_mutant_is_killed():
    ic = _ic("U1")
    r1 = _at_pin("R1", ic, "4", (0.0, 2.0), fp=_R)
    l1 = _at_pin("L1", ic, "10", (20.0, 0.0), fp=_C)
    rx, ry = _pin_xy(ic, "4")
    u2 = _ic("U2", x=200.0, y=_ICY)
    l2 = _inst("L2", _C, rx + 2.0, ry + 2.0)
    res = g.check(_model(ic, r1, l1, u2, l2), _SHEET, _fb_contract(),
                  ref_map=_idmap("U1", "R1", "L1", "U2", "L2"))
    assert res.ok is False and res.fb_fail >= 1, res.summary()
    assert any("from foreign U2 SW/L" in v for v in res.violations), res.summary()


@pytest.mark.parametrize("typ,ref,pin_key,pin,lim,attr", [
    ("boot", "C4", "pins", ["13", "14"], 2.0, "boot_fail"),
    ("vcc_cap", "C24", "pin", "2", 2.0, "vcc_fail"),
    ("bias_cap", "C28", "pin", "1", 3.0, "bias_fail"),
    ("rt_r", "R10", "pin", "6", 3.0, "rt_fail"),
])
def test_proximity_structures_baseline_and_mutant(typ, ref, pin_key, pin, lim,
                                                  attr):
    refkey = {"rt_r": "resistor"}.get(typ, "cap")
    pinval = pin if pin_key == "pin" else pin
    st = {"type": typ, "ic": "U1", refkey: ref, pin_key: pinval,
          "max_pad_to_pin_mm": lim, "basis": "b"}
    contract = {"structures": [st]}
    idm = _idmap("U1", ref)
    anchor = pin[0] if isinstance(pin, list) else pin

    ic = _ic()
    near = _at_pin(ref, ic, anchor, (0.4, 0.0),
                   fp=_R if typ == "rt_r" else _C)
    res = g.check(_model(ic, near), _SHEET, contract, ref_map=idm)
    assert res.ok, f"{typ} baseline: {res.summary()}"
    assert getattr(res, attr) == 0

    ic = _ic()
    far = _at_pin(ref, ic, anchor, (lim + 6.0, 0.0),
                  fp=_R if typ == "rt_r" else _C)
    res = g.check(_model(ic, far), _SHEET, contract, ref_map=idm)
    assert res.ok is False, f"{typ} mutant not killed: {res.summary()}"
    assert getattr(res, attr) == 1, res.summary()


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


def _same_side_contract() -> dict:
    return {"roles": {"U1": "buck_ic", "C1": "cin_hf@VIN1"},
            "structures": [
                {"type": "hot_loop", "ic": "U1",
                 "pin_pairs": [["8", "9"]], "caps": ["C1"],
                 "max_pad_to_pin_mm": 1.0, "same_side": True, "basis": "b"},
                {"type": "same_side", "ics": ["U1"], "basis": "b"}]}


def test_same_side_baseline_passes():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4))
    res = g.check(_model(ic, c1), _SHEET, _same_side_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok and res.same_side_fail == 0, res.summary()


def test_same_side_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1), _SHEET, _same_side_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False and res.same_side_fail == 1, res.summary()
    assert any("same_side U1 C1" in v for v in res.violations), res.summary()


def test_load_contract_power_present_and_versioned():
    c = g.load_contract("power")
    assert c is not None and c["contract"] == "placement/v2"
    assert c["sheet"] == "power"
    for st in c["structures"]:
        assert st.get("basis"), st


def test_load_contract_absent_returns_none():
    assert g.load_contract("no_such_subsystem_xyz") is None


def test_no_contract_passes_vacuously():
    ic = _ic()
    res = g.check(_model(ic), "no_such_subsystem_xyz")
    assert res.ok and res.have_contract is False


def test_summary_is_deterministic():
    ic = _ic()
    c1 = _at_pin("C1", ic, "8", (0.0, 8.0), side="bottom")
    c25 = _at_pin("C25", ic, "12", (0.0, 8.0), side="bottom")
    contract = _hot_loop_contract()
    idm = _idmap("U1", "C1", "C25")
    s1 = g.check(_model(ic, c1, c25), _SHEET, contract, ref_map=idm).summary()
    s2 = g.check(_model(ic, c1, c25), _SHEET, contract, ref_map=idm).summary()
    assert s1 == s2


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_gate_is_green_on_the_templated_board(_real_model):
    res = g.check(_real_model, "power")
    print("\n" + res.summary())

    assert res.have_contract is True
    assert res.missing_refs == [], (
        f"contract refs did not map to board refs: {res.missing_refs}")
    assert res.ok is True, (
        "the stage template did NOT satisfy the placement contract:\n"
        + res.summary())
    assert not res.violations, res.summary()
