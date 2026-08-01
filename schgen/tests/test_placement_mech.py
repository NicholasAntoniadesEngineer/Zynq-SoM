from __future__ import annotations

from schgen.generate import pcb
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
    _mating_face_out_dir,
    connector_edge_rotation,
)
from schgen.verify import placement_mech as pm


def test_edge_rotation_points_mouth_off_board():
    edge_out = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
    for face in pcb._ROT_TABLES:
        for edge in ("N", "S", "E", "W"):
            rot = connector_edge_rotation(face, edge)
            assert _mating_face_out_dir(face, rot) == edge_out[edge], \
                f"face {face} on {edge} edge: rot {rot} does not face off-board"


def test_mouth_oracle_uses_kicads_true_rotation_sign():
    from schgen.generate.pcb.mating_face import _rot_bbox_cw

    for face, vec in pcb._FACE_VEC.items():
        for rot in (0.0, 90.0, 180.0, 270.0):
            v = (float(vec[0]), float(vec[1]))
            rb = _rot_bbox_cw((v[0], v[1], v[0], v[1]), rot)
            geo = (int(round(rb[0])), int(round(rb[1])))
            assert _mating_face_out_dir(face, rot) == geo, \
                f"{face} at {rot}: oracle says {_mating_face_out_dir(face, rot)}" \
                f" but the emitted geometry lands at {geo}"
    assert _mating_face_out_dir("+Y", 90.0) == (1, 0)
    assert _mating_face_out_dir("+Y", 270.0) == (-1, 0)


def test_every_offboard_mpn_has_a_mating_face():
    for mpn, face in pcb.CONN_MATING_FACE.items():
        assert face in pcb._ROT_TABLES, \
            f"{mpn} has an unsupported mating face {face!r} " \
            "(not in the rotation engine)"


def _inst(ref, mpn, x, y, rot, sheet="t"):
    mod = pcb.resolve_mod(f"{mpn}:{mpn}")
    assert mod is not None, f"{mpn} footprint missing"
    return FootprintInst(ref=ref, value=mpn, footprint=f"{mpn}:{mpn}",
                         x=x, y=y, rotation=rot, pad_nets={}, mod_path=mod,
                         sheet=sheet, side="top")


def _passing_model():
    W, H = 100.0, 80.0
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    _bx1, by1 = ORIGIN_X + W, ORIGIN_Y + H
    r_usbc = connector_edge_rotation(pcb.CONN_MATING_FACE["TYPE-C-31-M-12"], "N")
    ub = pcb._rot_bbox(pcb._footprint_bbox(
        pcb.resolve_mod("TYPE-C-31-M-12:TYPE-C-31-M-12")), r_usbc)
    j_usbc = _inst("J1", "TYPE-C-31-M-12", bx0 + 20, by0 - ub[1] + 0.1, r_usbc)
    r_sd = connector_edge_rotation(pcb.CONN_MATING_FACE["TF-01A"], "S")
    sb = pcb._rot_bbox(pcb._footprint_bbox(
        pcb.resolve_mod("TF-01A:TF-01A")), r_sd)
    j_sd = _inst("J2", "TF-01A", bx0 + 60, by1 - sb[3] - 0.1, r_sd)
    som_core = (bx0 + 40, by0 + 30, bx0 + 60, by0 + 50)
    rmod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    r_under = FootprintInst(ref="R5", value="10k",
                            footprint="Resistor_SMD:R_0603_1608Metric",
                            x=(som_core[0] + som_core[2]) / 2,
                            y=(som_core[1] + som_core[3]) / 2,
                            rotation=0.0, pad_nets={}, mod_path=rmod,
                            sheet="t", side="bottom")
    insts = [j_usbc, j_sd, r_under]
    return PcbModel(board_w=W, board_h=H, insts=insts, net_numbers={"": 0},
                    netclass_of={}, classes={}, placed=len(insts), deferred=[],
                    som_core=som_core)


def test_passing_model_passes():
    res = pm.check(_passing_model())
    assert res.ok, res.summary()
    assert res.n_connectors == 2
    assert not res.bad_connectors and not res.under_som


def test_mutant_connector_interior_fails():
    model = _passing_model()
    j = next(i for i in model.insts if i.ref == "J1")
    j.x += 25.0
    j.y += 25.0
    res = pm.check(model)
    assert not res.ok, "interior off-board connector must FAIL the gate"
    assert any("J1" in b for b in res.bad_connectors), res.summary()


def test_mutant_connector_recessed_off_edge_fails():
    model = _passing_model()
    assert pm.check(model).ok, "baseline (flush) must pass"
    j = next(i for i in model.insts if i.ref == "J1")
    j.y += 1.0
    res = pm.check(model)
    assert not res.ok, "a connector recessed ~1mm off the edge must FAIL"
    assert any("J1" in b and ("interior" in b or "recess" in b.lower()
                              or "mm" in b) for b in res.bad_connectors), res.summary()


def test_mutant_connector_inward_facing_fails():
    model = _passing_model()
    j = next(i for i in model.insts if i.ref == "J1")
    j.rotation = (j.rotation + 180.0) % 360.0
    res = pm.check(model)
    assert not res.ok, "inward-facing edge connector must FAIL the gate"
    assert any("J1" in b and "inward" in b for b in res.bad_connectors), \
        res.summary()


def test_mutant_top_passive_under_som_fails():
    model = _passing_model()
    r = next(i for i in model.insts if i.ref == "R5")
    assert pm.check(model).ok, "baseline (bottom passive) must pass"
    r.side = "top"
    res = pm.check(model)
    assert not res.ok, "a TOP-side passive under the SoM must FAIL the gate"
    assert any("R5" in t for t in res.top_under_som), res.summary()


def test_bottom_active_under_som_is_ok():
    model = _passing_model()
    sc = model.som_core
    ic_mod = pcb.resolve_mod("USBLC6-2SC6:USBLC6-2SC6")
    assert ic_mod is not None
    model.insts.append(FootprintInst(
        ref="U9", value="USBLC6-2SC6", footprint="USBLC6-2SC6:USBLC6-2SC6",
        x=(sc[0] + sc[2]) / 2, y=(sc[1] + sc[3]) / 2, rotation=0.0,
        pad_nets={}, mod_path=ic_mod, sheet="t", side="bottom"))
    res = pm.check(model)
    assert res.ok, ("a BOTTOM active under the SoM must PASS", res.summary())
    assert not any("U9" in u for u in res.under_som + res.top_under_som)


def test_mutant_ic_under_som_fails():
    model = _passing_model()
    sc = model.som_core
    ic_mod = pcb.resolve_mod("USBLC6-2SC6:USBLC6-2SC6")
    assert ic_mod is not None
    model.insts.append(FootprintInst(
        ref="U9", value="USBLC6-2SC6", footprint="USBLC6-2SC6:USBLC6-2SC6",
        x=(sc[0] + sc[2]) / 2, y=(sc[1] + sc[3]) / 2, rotation=0.0,
        pad_nets={}, mod_path=ic_mod, sheet="t", side="top"))
    res = pm.check(model)
    assert not res.ok, "an IC under the SoM body must FAIL the gate"
    assert any("U9" in u for u in res.under_som), res.summary()


def test_mutant_button_under_som_fails():
    model = _passing_model()
    sc = model.som_core
    sw_mod = pcb.resolve_mod("TS-1187A-B-A-B:TS-1187A-B-A-B")
    assert sw_mod is not None
    model.insts.append(FootprintInst(
        ref="SW9", value="USER", footprint="TS-1187A-B-A-B:TS-1187A-B-A-B",
        x=(sc[0] + sc[2]) / 2, y=(sc[1] + sc[3]) / 2, rotation=0.0,
        pad_nets={}, mod_path=sw_mod, sheet="t", side="top"))
    res = pm.check(model)
    assert not res.ok, "a button under the SoM must FAIL the gate"
    assert any("SW9" in c for c in res.controls_under_som), res.summary()


def test_passive_under_som_is_allowed():
    res = pm.check(_passing_model())
    assert not res.under_som, res.summary()
