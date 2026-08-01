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


def _zone(sheet: str, x: float, y: float, ref: str | None = None) -> FootprintInst:
    return _inst(ref or f"C{sheet}", sheet, x, y)


def _flow_contract() -> dict:
    return {"contract": "placement/test",
            "external": {"flow": ["usb_pd", "power", "power_som"]}}


def test_flow_baseline_passes():
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),
        _zone("power_som", 60.0, 40.0),
    ])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok, res.summary()
    assert res.flow_fail == 0 and res.flow_checked == 2, res.summary()


def test_flow_far_hop_mutant_is_killed():
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),
        _zone("power_som", 165.0, 140.0),
    ])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok is False, res.summary()
    assert res.flow_fail == 1, res.summary()
    assert any("flow power->power_som" in v for v in res.violations), res.summary()


def test_flow_budget_scales_with_board_area():
    insts = [
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 30.0, 24.0),
        _zone("power_som", 110.0, 90.0),
    ]
    small = g.check(_model(insts, board_w=60.0, board_h=60.0),
                    contracts={"power": _flow_contract()})
    big = g.check(_model(insts, board_w=400.0, board_h=400.0),
                  contracts={"power": _flow_contract()})
    assert small.flow_fail == 1, small.summary()
    assert big.flow_fail == 0, big.summary()


def test_flow_som_detour_widens_budget():
    insts = [
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 30.0, 24.0),
        _zone("power_som", 90.0, 60.0),
    ]
    m_no_som = _model(insts, board_w=100.0, board_h=100.0)
    res_no = g.check(m_no_som, contracts={"power": _flow_contract()})
    assert res_no.flow_fail == 1, res_no.summary()
    m_som = _model(insts, board_w=100.0, board_h=100.0)
    m_som.som_core = (20.0, 20.0, 70.0, 70.0)
    res_som = g.check(m_som, contracts={"power": _flow_contract()})
    assert res_som.flow_fail == 0, res_som.summary()
    assert res_som.flow_budget_mm > res_no.flow_budget_mm, res_som.summary()


def test_flow_missing_zone_is_unresolved_and_fails():
    m = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved, res.summary()
    assert res.flow_fail == 1, res.summary()


def _facing_contract() -> dict:
    return {"contract": "placement/test",
            "roles": {"U1": "buck_ic", "C5": "cout_bulk", "C6": "cout_bulk"},
            "external": {"downstream": "power_som",
                         "output_roles": ["cout_bulk"]}}


def _facing_refmap() -> dict:
    return {"power": {"U1": "U1", "C5": "C5", "C6": "C6"}}


def test_facing_baseline_passes():
    m = _model([
        _inst("U1", "power", 40.0, 30.0),
        _inst("C5", "power", 48.0, 30.0),
        _inst("C6", "power", 48.0, 32.0),
        _zone("power_som", 80.0, 30.0),
    ])
    res = g.check(m, contracts={"power": _facing_contract()},
                  ref_maps=_facing_refmap())
    assert res.ok, res.summary()
    assert res.facing_fail == 0 and res.facing_checked == 1, res.summary()


def test_facing_wrong_way_mutant_is_killed():
    m = _model([
        _inst("U1", "power", 40.0, 30.0),
        _inst("C5", "power", 32.0, 30.0),
        _inst("C6", "power", 32.0, 32.0),
        _zone("power_som", 80.0, 30.0),
    ])
    res = g.check(m, contracts={"power": _facing_contract()},
                  ref_maps=_facing_refmap())
    assert res.ok is False, res.summary()
    assert res.facing_fail == 1, res.summary()
    assert any("face AWAY" in v for v in res.violations), res.summary()


def test_facing_no_output_role_is_unresolved():
    c = {"contract": "placement/test",
         "roles": {"U1": "buck_ic"},
         "external": {"downstream": "power_som", "output_roles": ["nope"]}}
    m = _model([_inst("U1", "power", 40.0, 30.0), _zone("power_som", 80.0, 30.0)])
    res = g.check(m, contracts={"power": c}, ref_maps={"power": {"U1": "U1"}})
    assert res.ok is False, res.summary()
    assert res.facing_fail == 1 and res.unresolved, res.summary()


def _far_contract(min_mm=10.0, what="ethernet.line_side") -> dict:
    return {"contract": "placement/test",
            "external": {"far": [{"what": what, "min_mm": min_mm, "basis": "j"}]}}


def test_far_baseline_passes():
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 80.0, 30.0)])
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok, res.summary()
    assert res.far_fail == 0 and res.far_checked == 1, res.summary()


def test_far_too_close_mutant_is_killed():
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 45.0, 32.0)])
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok is False, res.summary()
    assert res.far_fail == 1, res.summary()
    assert any("vs ethernet.line_side" in v for v in res.violations), res.summary()


def test_far_coarsens_region_to_zone():
    m = _model([_zone("power", 40.0, 30.0), _zone("ethernet", 80.0, 30.0)])
    res = g.check(m, contracts={"power": _far_contract(what="ethernet.line_side")})
    assert res.far_checked == 1 and res.far_fail == 0, res.summary()
    assert any("ethernet.line_side" in d and "40.00mm" in d
               for d in res.detail), res.summary()


def test_far_unresolved_target_fails_strict():
    m = _model([_zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": _far_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.far_fail == 1, res.summary()
    assert any("UNRESOLVED" in v for v in res.violations), res.summary()


def test_term_naming_uninstantiated_subsystem_is_na_not_failed():
    c = {"contract": "placement/test",
         "external": {
             "flow": ["no_such_subsystem", "power"],
             "far": [{"what": "also_absent.line_side", "min_mm": 10.0,
                      "basis": "j"}],
             "near_max": [{"other": "gone_too", "max_mm": 5.0, "basis": "j"}],
         }}
    m = _model([_zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": c})
    assert res.ok, res.summary()
    assert not res.violations and not res.unresolved, res.summary()
    assert res.flow_checked == 0 and res.far_checked == 0 \
        and res.near_max_checked == 0, res.summary()
    assert len(res.na) == 3, res.summary()
    assert any("no_such_subsystem" in x for x in res.na), res.summary()
    assert "n/a (subsystem not in this project): 3" in res.summary()


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


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_flow_gate_runs_on_the_real_board(_real_model):
    res = g.check(_real_model)
    print("\n" + res.summary())
    assert res.n_contracts >= 1, "the power external contract was not exercised"
    assert res.flow_checked >= 2, res.summary()
    assert res.facing_checked >= 1, res.summary()
    assert res.far_checked >= 1, res.summary()


def test_flow_budget_kernel_matches_gate_report():
    m = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    res = g.check(m, contracts={"power": _flow_contract()})
    assert res.flow_budget_mm == round(
        g.flow_budget(m.board_w, m.board_h, m.som_core), 4), res.summary()

    m2 = _model([_zone("usb_pd", 20.0, 20.0), _zone("power", 40.0, 30.0)])
    m2.som_core = (60.0, 60.0, 111.0, 103.0)
    res2 = g.check(m2, contracts={"power": _flow_contract()})
    assert res2.flow_budget_mm == round(
        g.flow_budget(m2.board_w, m2.board_h, m2.som_core), 4), res2.summary()
    assert res2.flow_budget_mm > res.flow_budget_mm


def test_facing_dot_kernel_matches_gate_detail():
    dot, angle = g.facing_dot((10.0, 10.0), (12.0, 10.0), (20.0, 10.0))
    assert dot > 0.0 and angle == 0.0
    dot2, angle2 = g.facing_dot((10.0, 10.0), (8.0, 10.0), (20.0, 10.0))
    assert dot2 < 0.0 and angle2 == 180.0
    _d3, a3 = g.facing_dot((10.0, 10.0), (10.0, 10.0), (20.0, 10.0))
    assert a3 == 180.0


def test_bbox_gap_public_and_aliases_are_same_objects():
    assert g._bbox_gap is g.bbox_gap
    assert g._zone_centroids is g.zone_centroids
    assert g._zone_bboxes is g.zone_bboxes
    assert g.bbox_gap((0, 0, 1, 1), (3, 0, 4, 1)) == 2.0
    assert g.bbox_gap((0, 0, 2, 2), (1, 1, 3, 3)) == 0.0


def test_som_core_rect_kernel_matches_build_model_arithmetic():
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
