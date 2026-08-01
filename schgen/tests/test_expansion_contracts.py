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
from schgen.verify import placement_flow_gate as f

_LM = "LM61460AANRJRR:LM61460AANRJRR"
_C = "Capacitor_SMD:C_0603_1608Metric"
_R = "Resistor_SMD:R_0603_1608Metric"
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


def _prox_contract(max_mm=2.0, same_side=True, anchor_pins=("3",),
                   members=("C1",), min_from=None) -> dict:
    st = {"type": "proximity", "anchor": "U1", "members": list(members),
          "max_mm": max_mm, "same_side": same_side, "basis": "b"}
    if anchor_pins is not None:
        st["anchor_pins"] = list(anchor_pins)
    if min_from is not None:
        st["min_from"] = min_from
    return {"structures": [st]}


def test_proximity_baseline_passes():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


def test_proximity_far_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 8.0))
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("to U1 pins 3" in v for v in res.violations), res.summary()


def test_proximity_wrong_side_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("same_side" in v for v in res.violations), res.summary()


def test_proximity_universal_partial_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))
    c2 = _at_pin("C2", ic, "3", (0.0, 9.0))
    res = g.check(_model(ic, c1, c2), _SHEET,
                  _prox_contract(members=("C1", "C2")),
                  ref_map=_idmap("U1", "C1", "C2"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()


def test_proximity_anchor_pins_absent_uses_any_pad():
    ic = _ic()
    c1 = _at_pin("C1", ic, "10", (0.4, 0.0))
    res = g.check(_model(ic, c1), _SHEET,
                  _prox_contract(max_mm=1.0, anchor_pins=None),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


def test_proximity_min_from_clearance_mutant_is_killed():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))
    fx, fy = _pin_xy(ic, "3")
    d5 = _inst("D5", _C, fx + 0.0, fy + 1.2)
    contract = _prox_contract(
        min_from=[{"part": "D5", "min_mm": 5.0}])
    res = g.check(_model(ic, c1, d5), _SHEET, contract,
                  ref_map=_idmap("U1", "C1", "D5"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("too close" in v and "from D5" in v
               for v in res.violations), res.summary()


def test_proximity_min_from_clearance_baseline_passes():
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))
    fx, fy = _pin_xy(ic, "3")
    d5 = _inst("D5", _C, fx + 0.0, fy + 20.0)
    contract = _prox_contract(
        min_from=[{"part": "D5", "min_mm": 5.0}])
    res = g.check(_model(ic, c1, d5), _SHEET, contract,
                  ref_map=_idmap("U1", "C1", "D5"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


def test_unknown_structure_type_fails_loud():
    ic = _ic()
    contract = {"structures": [
        {"type": "totally_made_up_type", "ic": "U1", "basis": "b"}]}
    res = g.check(_model(ic), _SHEET, contract, ref_map=_idmap("U1"))
    assert res.ok is False, res.summary()
    assert res.unknown_fail == 1, res.summary()
    assert any("UNKNOWN structure type" in v for v in res.violations), \
        res.summary()


def test_en_cluster_type_now_gone_from_power_som():
    for sheet in ("power", "power_som", "usb_pd", "ethernet", "hdmi_rx",
                  "motor_sense"):
        c = g.discover_contract(sheet)
        assert c is not None, sheet
        types = {st["type"] for st in c["structures"]}
        assert "en_cluster" not in types, f"{sheet} still has en_cluster"


def _fzone(sheet: str, x: float, y: float) -> FootprintInst:
    mod = resolve_mod(_C)
    pad_nets = {p: (i + 1, f"{sheet}_{p}") for i, p in enumerate(pad_names(mod))}
    return FootprintInst(ref=f"C{sheet}", value="x", footprint=_C,
                         x=x, y=y, rotation=0.0, pad_nets=pad_nets,
                         mod_path=mod, sheet=sheet, side="top")


def _fmodel(insts, board_w=170.0, board_h=145.0) -> PcbModel:
    lst = list(insts)
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=lst,
        net_numbers={"": 0}, netclass_of={}, classes={},
        placed=len(lst), deferred=[], n_top=len(lst), n_bottom=0,
        two_side=True)


def _near_contract(other="pd_input", max_mm=15.0) -> dict:
    return {"contract": "placement/test",
            "external": {"near_max": [
                {"other": other, "max_mm": max_mm, "basis": "j"}]}}


def test_near_max_baseline_passes():
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0), _fzone("pd_input", 48.0, 36.0)])
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok, res.summary()
    assert res.near_max_fail == 0 and res.near_max_checked == 1, res.summary()


def test_near_max_too_far_mutant_is_killed():
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0), _fzone("pd_input", 100.0, 30.0)])
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok is False, res.summary()
    assert res.near_max_fail == 1, res.summary()
    assert any("near_max usb_pd to pd_input" in v
               for v in res.violations), res.summary()


def test_near_max_unresolved_target_fails_strict():
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0)])
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.near_max_fail == 1, res.summary()
    assert any("UNRESOLVED" in v for v in res.violations), res.summary()


def _wide_zone(sheet: str, xs: list[float], y: float = 30.0
               ) -> list[FootprintInst]:
    return [_fzone(sheet, x, y) for x in xs]


def test_near_max_edge_gap_passes_where_centroid_would_fail():
    insts = _wide_zone("usb_pd", [10.0, 30.0, 50.0]) + [_fzone("pd_input", 52.0, 30.0)]
    m = _fmodel(insts)
    res = f.check(m, contracts={"usb_pd": _near_contract(max_mm=10.0)})
    assert res.ok, res.summary()
    assert res.near_max_fail == 0 and res.near_max_checked == 1, res.summary()
    gap_lines = [d for d in res.detail if "near_max usb_pd to pd_input" in d]
    assert gap_lines and "gap" in gap_lines[0], res.summary()


def test_near_max_edge_gap_zero_on_overlap():
    insts = _wide_zone("usb_pd", [40.0, 50.0]) + _wide_zone("pd_input", [45.0, 55.0])
    m = _fmodel(insts)
    res = f.check(m, contracts={"usb_pd": _near_contract(max_mm=0.5)})
    assert res.ok, res.summary()
    assert any("near_max usb_pd to pd_input: 0.00mm gap" in d
               for d in res.detail), res.summary()


def test_near_max_edge_gap_too_far_mutant_is_killed():
    insts = _wide_zone("usb_pd", [10.0, 20.0]) + [_fzone("pd_input", 100.0, 30.0)]
    m = _fmodel(insts)
    res = f.check(m, contracts={"usb_pd": _near_contract(max_mm=15.0)})
    assert res.ok is False, res.summary()
    assert res.near_max_fail == 1, res.summary()
    assert any("near_max usb_pd to pd_input" in v and "gap >" in v
               for v in res.violations), res.summary()


def test_flow_at_som_resolves_to_som_core():
    m = _fmodel([_fzone("power_mon", 40.0, 30.0),
                 _fzone("power_som", 50.0, 40.0)],
                board_w=170.0, board_h=145.0)
    m.som_core = (55.0, 40.0, 90.0, 70.0)
    c = {"contract": "placement/test",
         "external": {"flow": ["power_mon", "power_som", "@som"]}}
    res = f.check(m, contracts={"power_som": c})
    assert res.flow_checked == 2, res.summary()
    assert not any("@som" in u for u in res.unresolved), res.summary()


def test_flow_at_som_unresolved_without_som_core():
    m = _fmodel([_fzone("power_mon", 40.0, 30.0),
                 _fzone("power_som", 50.0, 40.0)])
    c = {"contract": "placement/test",
         "external": {"flow": ["power_som", "@som"]}}
    res = f.check(m, contracts={"power_som": c})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.flow_fail == 1, res.summary()


def test_facing_at_som_resolves(monkeypatch):
    out = _fzone("power_som", 50.0, 30.0)
    out.ref = "COUT"
    ic = _fzone("power_som", 42.0, 30.0)
    ic.ref = "U4"
    m = _fmodel([ic, out])
    m.som_core = (60.0, 25.0, 90.0, 45.0)
    c = {"contract": "placement/test",
         "roles": {"U4": "buck_ic", "COUT": "cout_bulk"},
         "external": {"downstream": "@som", "output_roles": ["cout_bulk"]}}
    res = f.check(m, contracts={"power_som": c},
                  ref_maps={"power_som": {"U4": "U4", "COUT": "COUT"}})
    assert res.facing_checked == 1, res.summary()
    assert res.facing_fail == 0, res.summary()


_GREEN_WIRED = ("power", "usb_pd", "ethernet")
_RED_ON_BEFORE = ("hdmi_rx", "motor_sense")


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_check_all_discovers_every_registered_contract(_real_model):
    results = g.check_all(_real_model)
    for sheet in (*_GREEN_WIRED, "power_som", *_RED_ON_BEFORE):
        assert sheet in results, (
            f"{sheet} contract not discovered by check_all "
            f"(got {sorted(results)})")


def test_wired_sheets_stay_green_on_the_real_board(_real_model):
    for sheet in _GREEN_WIRED:
        res = g.check(_real_model, sheet)
        print(f"\n--- {sheet} (wired, expect green) ---")
        print(res.summary())
        assert res.missing_refs == [], res.summary()
        assert res.ok is True, (
            f"{sheet} regressed — the red-on-before proof needs the wired "
            f"sheets green:\n" + res.summary())


def test_new_contracts_hold_on_board(_real_model):
    results = g.check_all(_real_model)
    for sheet in _RED_ON_BEFORE:
        res = results[sheet]
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], (
            f"{sheet}: contract refs did not map to board refs: "
            f"{res.missing_refs}")
        assert res.ok is True, (
            f"{sheet} regressed — its wired contract no longer holds:\n"
            f"{res.summary()}")
