"""Unit tests for the LAW-6 mechanical/use-case placement gate
(schgen.verify.placement_mech) + the connector edge-rotation helpers it relies
on. The gate's whole reason to exist is to KILL a board that is electrically
clean (DRC=0, ratsnest-pass) but mechanically UNBUILDABLE, so every test here is
a mutant: a synthetic placed model that should PASS, then a single-defect
mutation that must FAIL — proving the gate bites.
"""

from __future__ import annotations

from schgen.generate import pcb
from schgen.generate.pcb import (FootprintInst, PcbModel, ORIGIN_X, ORIGIN_Y,
                                 connector_edge_rotation, _mating_face_out_dir)
from schgen.verify import placement_mech as pm


# ---- the rotation contract: a connector ON an edge must face OFF-BOARD --------

def test_edge_rotation_points_mouth_off_board():
    """For every connector face direction and every edge, the chosen placement
    rotation turns the mating mouth toward the OFF-BOARD side of that edge."""
    edge_out = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
    for face in ("-Y", "+Y"):
        for edge in ("N", "S", "E", "W"):
            rot = connector_edge_rotation(face, edge)
            assert _mating_face_out_dir(face, rot) == edge_out[edge], \
                f"face {face} on {edge} edge: rot {rot} does not face off-board"


def test_every_offboard_mpn_has_a_mating_face():
    """Every off-board connector family the floorplan can pin has a researched
    mating-face direction (so the placer can rotate it)."""
    for mpn, face in pcb.CONN_MATING_FACE.items():
        assert face in ("-Y", "+Y"), f"{mpn} has an illegal mating face {face!r}"


# ---- a synthetic placed model: PASS, then per-rule mutants must FAIL ----------

def _inst(ref, mpn, x, y, rot, sheet="t"):
    """A real-footprint FootprintInst placed at (x, y) with rotation ``rot``."""
    mod = pcb.resolve_mod(f"{mpn}:{mpn}")
    assert mod is not None, f"{mpn} footprint missing"
    return FootprintInst(ref=ref, value=mpn, footprint=f"{mpn}:{mpn}",
                         x=x, y=y, rotation=rot, pad_nets={}, mod_path=mod,
                         sheet=sheet, side="top")


def _passing_model():
    """A small board: a USB-C flush on the N edge facing off-board, a microSD
    flush on the S edge facing off-board, an R passive under the SoM core (GOOD),
    and a clear SoM core. Should PASS the LAW-6 gate."""
    W, H = 100.0, 80.0
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    bx1, by1 = ORIGIN_X + W, ORIGIN_Y + H
    # USB-C (-Y face) on the N edge: the gate-derived rotation faces the mouth
    # off-board (top); seat it flush so its top courtyard face is at the edge.
    r_usbc = connector_edge_rotation(pcb.CONN_MATING_FACE["TYPE-C-31-M-12"], "N")
    ub = pcb._rot_bbox(pcb._footprint_bbox(
        pcb.resolve_mod("TYPE-C-31-M-12:TYPE-C-31-M-12")), r_usbc)
    j_usbc = _inst("J1", "TYPE-C-31-M-12", bx0 + 20, by0 - ub[1] + 0.1, r_usbc)
    # microSD (+Y face) on the S edge: the gate-derived rotation faces +Y/bottom.
    r_sd = connector_edge_rotation(pcb.CONN_MATING_FACE["TF-01A"], "S")
    sb = pcb._rot_bbox(pcb._footprint_bbox(
        pcb.resolve_mod("TF-01A:TF-01A")), r_sd)
    j_sd = _inst("J2", "TF-01A", bx0 + 60, by1 - sb[3] - 0.1, r_sd)
    # a BOTTOM-side passive UNDER the SoM core (allowed — opposite face from the
    # SoM) + the SoM core rectangle. A TOP-side part here is forbidden (the SoM's
    # own bottom components sit in the standoff gap — see the top-keepout mutant).
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
    """Drag the USB-C off its edge into the board interior — the cable can no
    longer plug in. The gate MUST fail (this is the exact densifier defect)."""
    model = _passing_model()
    j = next(i for i in model.insts if i.ref == "J1")
    j.x += 25.0
    j.y += 25.0           # now ~25 mm interior of the N edge
    res = pm.check(model)
    assert not res.ok, "interior off-board connector must FAIL the gate"
    assert any("J1" in b for b in res.bad_connectors), res.summary()


def test_mutant_connector_inward_facing_fails():
    """Keep the USB-C on the N edge but rotate it 180 so its mouth faces INWARD
    (you cannot insert the cable). The gate MUST fail even though it is on-edge."""
    model = _passing_model()
    j = next(i for i in model.insts if i.ref == "J1")
    # rot 180 turns the -Y mouth to +Y (inward) while it still sits at the top
    j.rotation = 180.0
    res = pm.check(model)
    assert not res.ok, "inward-facing edge connector must FAIL the gate"
    assert any("J1" in b and "inward" in b for b in res.bad_connectors), \
        res.summary()


def test_mutant_top_passive_under_som_fails():
    """A carrier TOP-side passive under the SoM body collides with the SoM's own
    bottom-side components in the standoff gap and stops it mating. The gate MUST
    fail it as TOP-under-SoM — even though the SAME passive on the BOTTOM is fine."""
    model = _passing_model()
    r = next(i for i in model.insts if i.ref == "R5")
    assert pm.check(model).ok, "baseline (bottom passive) must pass"
    r.side = "top"                       # flip the allowed bottom passive to top
    res = pm.check(model)
    assert not res.ok, "a TOP-side passive under the SoM must FAIL the gate"
    assert any("R5" in t for t in res.top_under_som), res.summary()


def test_bottom_active_under_som_is_ok():
    """A carrier BOTTOM-side active (IC) under the SoM is FINE — it sits on the
    OPPOSITE face from the module (full clearance), so it is allowed (user: actives
    may go on the bottom; only connectors must be top). Only the TOP under the SoM
    is the keepout. The SAME IC on the TOP must FAIL (see test_mutant_ic_under_som)."""
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
    """Place an IC under the SoM module body — the module physically crushes it.
    The gate MUST fail (non-passive under the core)."""
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
    """A tactile button under the SoM is unreachable. The gate MUST fail and
    name it as a control-under-SoM."""
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
    """A discrete R/C/L under the SoM is GOOD (it uses otherwise-dead space) —
    the gate must NOT flag it."""
    res = pm.check(_passing_model())
    assert not res.under_som, res.summary()
