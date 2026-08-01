from __future__ import annotations

from schgen.generate import pcb
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
    _inst_pad_bbox,
)
from schgen.verify import connector_spacing_gate as cs


def _hdmi(ref, x, y, rot=0.0):
    mod = pcb.resolve_mod("HDMI-019S:HDMI-019S")
    assert mod is not None, "HDMI-019S footprint missing"
    return FootprintInst(ref=ref, value="HDMI-019S",
                         footprint="HDMI-019S:HDMI-019S",
                         x=x, y=y, rotation=rot, pad_nets={}, mod_path=mod,
                         sheet="hdmi", side="top")


def _model_with_two_hdmi(dx):
    W, H = 170.0, 150.0
    y = ORIGIN_Y + H - 10.0
    j1 = _hdmi("J12001", ORIGIN_X + 30.0, y)
    j2 = _hdmi("J14001", ORIGIN_X + 30.0 + dx, y)
    insts = [j1, j2]
    return PcbModel(board_w=W, board_h=H, insts=insts, net_numbers={"": 0},
                    netclass_of={}, classes={}, placed=len(insts), deferred=[])


def _gap_x(model):
    a = _inst_pad_bbox(model.insts[0])
    b = _inst_pad_bbox(model.insts[1])
    return max(a[0], b[0]) - min(a[2], b[2])


def test_hdmi_is_a_policed_overmold_family():
    assert "HDMI-019S" in cs._FAMILY_MIN_GAP_MM
    assert cs._FAMILY_MIN_GAP_MM["HDMI-019S"] >= 18.0
    assert cs._FAMILY_OF["HDMI-019S"] == "HDMI-019S"


def test_real_board_passes(carrier_model):
    res = cs.check(carrier_model)
    assert res.ok, res.summary()
    assert any({"J12001", "J14001"} == {p[0], p[1]} for p in res.pairs), \
        res.summary()


def test_well_spaced_pair_passes():
    model = _model_with_two_hdmi(dx=40.0)
    assert _gap_x(model) >= cs._FAMILY_MIN_GAP_MM["HDMI-019S"]
    res = cs.check(model)
    assert res.ok, res.summary()
    assert len(res.pairs) == 1


def test_mutant_overmolds_collide_fails():
    model = _model_with_two_hdmi(dx=22.0)
    gap = _gap_x(model)
    assert gap < cs._FAMILY_MIN_GAP_MM["HDMI-019S"], gap
    res = cs.check(model)
    assert not res.ok, "colliding overmolds must FAIL the gate\n" + res.summary()
    assert any("J12001" in v and "J14001" in v for v in res.violations), \
        res.summary()


def test_just_under_threshold_fails():
    need = cs._FAMILY_MIN_GAP_MM["HDMI-019S"]
    bb = _inst_pad_bbox(_hdmi("X", ORIGIN_X, ORIGIN_Y))
    w = bb[2] - bb[0]
    model = _model_with_two_hdmi(dx=w + need - 0.5)
    res = cs.check(model)
    assert not res.ok, res.summary()


def _pmod(ref, x, y, rot=0.0):
    mod = pcb.resolve_mod("DS1024-2x6R2:DS1024-2x6R2")
    assert mod is not None, "DS1024-2x6R2 footprint missing"
    return FootprintInst(ref=ref, value="DS1024-2x6R2",
                         footprint="DS1024-2x6R2:DS1024-2x6R2",
                         x=x, y=y, rotation=rot, pad_nets={}, mod_path=mod,
                         sheet="pmod", side="top")


def _model_hdmi_beside_pmod(dx):
    W, H = 170.0, 150.0
    y = ORIGIN_Y + H - 10.0
    return PcbModel(board_w=W, board_h=H,
                    insts=[_hdmi("J12001", ORIGIN_X + 30.0, y),
                           _pmod("J18001", ORIGIN_X + 30.0 + dx, y)],
                    net_numbers={"": 0}, netclass_of={}, classes={}, placed=2,
                    deferred=[])


def test_one_sided_rule_polices_hdmi_beside_a_plain_neighbour():
    model = _model_hdmi_beside_pmod(dx=60.0)
    res = cs.check(model)
    assert res.ok, res.summary()
    rows = [p for p in res.pairs if p[2].endswith("|1")]
    assert len(rows) == 1, res.summary()
    assert {rows[0][0], rows[0][1]} == {"J12001", "J18001"}
    assert rows[0][5] == cs._FAMILY_SIDE_GAP_MM["HDMI-019S"]


def test_mutant_one_sided_boot_overhang_fails():
    need = cs._FAMILY_SIDE_GAP_MM["HDMI-019S"]
    a = _inst_pad_bbox(_hdmi("X", ORIGIN_X, ORIGIN_Y))
    b = _inst_pad_bbox(_pmod("Y", ORIGIN_X, ORIGIN_Y))
    half = (a[2] - a[0]) / 2.0 + (b[2] - b[0]) / 2.0
    model = _model_hdmi_beside_pmod(dx=half + need - 0.5)
    res = cs.check(model)
    assert not res.ok, res.summary()
    assert any("one-sided" in v for v in res.violations), res.summary()


def test_one_sided_rule_does_not_re_police_the_same_family():
    res = cs.check(_model_with_two_hdmi(dx=40.0))
    assert [p[2] for p in res.pairs] == ["HDMI-019S"], res.summary()


def test_different_edges_not_compared():
    W, H = 170.0, 150.0
    j1 = _hdmi("J12001", ORIGIN_X + 30.0, ORIGIN_Y + H - 10.0)
    j2 = _hdmi("J14001", ORIGIN_X + 10.0, ORIGIN_Y + 30.0, rot=90.0)
    model = PcbModel(board_w=W, board_h=H, insts=[j1, j2],
                     net_numbers={"": 0}, netclass_of={}, classes={}, placed=2,
                     deferred=[])
    res = cs.check(model)
    assert res.ok, res.summary()
    assert not res.violations, res.summary()
