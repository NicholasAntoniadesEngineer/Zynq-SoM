"""DEFECT-INJECTION CORPUS — the Principle-0 validation battery (P2, U2a).

One place enumerating the historically EYE-CAUGHT defect classes and proving, per
class, that the mechanized gate FIRES on an injected defect and stays SILENT on the
clean twin (no false positives). This is the promotion battery any fast check must
pass before standing in for a visual check (docs/AI_PLATFORM_ROADMAP.md Principle 0)
AND standing regression armor that the gates keep guarding their class.

Fast + hermetic: synthetic PcbModels from real footprints via the build_zone harness —
no board build, no kicad-cli.

Classes covered HERE (gate <- defect):
  ratsnest_gate      <- off-board part; dispersed subsystem cluster
  placement_mech     <- interior connector; inward mating face; part on the SoM-TOP
                        keepout (amended LAW 6); control under the module;
                        bottom-under-SoM exemption (clean twin)
  placement_contract <- scattered decoupling (member beyond contract distance)
  fanout_gate        <- starved multi-pin fan-out (foreign non-passive crowding)

Classes covered by their OWN suites (not duplicated; listed for the battery ledger):
  facing-away/flow            test_placement_flow_gate (synthetic kernel harness)
  silk refdes overprint       test_refdes overlap suite (board-file based)
  DF40 corridor intrusion     test_return_stitch_gate / escape seat-audit fail path
  schematic short/open        netlist gate + shorts detector suites (LAW 0)
  courtyard overlap           kicad-cli DRC (external oracle)
"""
from __future__ import annotations

import pytest

from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y, FootprintInst, PcbModel
from schgen.generate.pcb.footprint import pad_names
from schgen.verify import fanout_gate, placement_mech, ratsnest_gate
from schgen.verify import placement_contract_gate as g

from .test_stage_templates import _run_zone, _subsystem_inputs

_BW, _BH = 200.0, 180.0


def _inst(ref, mod, x, y, rot=0.0, side="top", sheet="usb_pd", value="x"):
    return FootprintInst(ref=ref, value=value, footprint=f"lib:{value}",
                         x=ORIGIN_X + x, y=ORIGIN_Y + y, rotation=rot,
                         pad_nets={p: (0, "") for p in pad_names(mod)},
                         mod_path=mod, sheet=sheet, side=side)


def _model(insts, som_core=None):
    return PcbModel(board_w=_BW, board_h=_BH, insts=insts, net_numbers={"": 0},
                    netclass_of={}, classes={}, placed=len(insts), deferred=[],
                    n_top=len(insts), n_bottom=0, two_side=True,
                    som_core=som_core)


@pytest.fixture(scope="module")
def usb_pd_zone():
    """The solved usb_pd cluster (contract-clean by construction) at (40, 40)."""
    res, rot, resolvable, contract = _run_zone("usb_pd")
    assert res is not None
    top, bot, _zw, _zh = res
    insts = [_inst(r, resolvable[r], 40 + dx, 40 + dy, rot.get(r, 0.0))
             for r, (dx, dy) in {**top, **bot}.items()]
    return insts, resolvable, contract, rot


@pytest.fixture(scope="module")
def usbc_mods():
    _refs, _side, _bbox, resolvable = _subsystem_inputs("usbc_otg")
    band = g._board_refs_by_sheet("usbc_otg")
    return {"typec": resolvable[band["J2"]], "esd": resolvable[band["U2"]],
            "switch": resolvable[band["U1"]]}


# --- ratsnest ---------------------------------------------------------------------

def test_clean_cluster_passes_ratsnest(usb_pd_zone):
    insts, *_ = usb_pd_zone
    res = ratsnest_gate.check(_model(list(insts)))
    assert not res.off_board and not res.dispersed


def test_off_board_part_fires(usb_pd_zone):
    insts, resolvable, _c, rot = usb_pd_zone
    mut = list(insts)
    mut[0] = _inst(mut[0].ref, mut[0].mod_path, -500.0, 40.0)
    res = ratsnest_gate.check(_model(mut))
    assert res.off_board and not res.ok


def test_dispersed_cluster_fires(usb_pd_zone):
    insts, *_ = usb_pd_zone
    mut = list(insts)
    far = _inst(mut[0].ref, mut[0].mod_path, 150.0, 150.0)
    mut[0] = far
    res = ratsnest_gate.check(_model(mut))
    assert res.dispersed and not res.ok


# --- placement_mech (LAW 6) -------------------------------------------------------

def test_interior_connector_fires(usbc_mods):
    j = _inst("J1", usbc_mods["typec"], _BW / 2, _BH / 2,
              sheet="usbc_otg", value="TYPE-C-31-M-12")
    res = placement_mech.check(_model([j]))
    assert res.bad_connectors and not res.ok


def test_inward_mating_face_fires(usbc_mods):
    j = _inst("J1", usbc_mods["typec"], _BW / 2, 2.0, rot=0.0,
              sheet="usbc_otg", value="TYPE-C-31-M-12")
    res = placement_mech.check(_model([j]))
    assert res.bad_connectors and not res.ok


def test_edge_connector_mouth_out_clean(usbc_mods):
    j = _inst("J1", usbc_mods["typec"], _BW / 2, 2.0, rot=180.0,
              sheet="usbc_otg", value="TYPE-C-31-M-12")
    res = placement_mech.check(_model([j]))
    assert not res.bad_connectors


_CORE = (ORIGIN_X + 80, ORIGIN_Y + 70, ORIGIN_X + 130, ORIGIN_Y + 112)


def test_top_part_under_som_fires(usb_pd_zone):
    insts, resolvable, _c, _r = usb_pd_zone
    cap = _inst("C9001", insts[-1].mod_path, 105.0, 90.0)
    res = placement_mech.check(_model([cap], som_core=_CORE))
    assert res.top_under_som and not res.ok


def test_bottom_part_under_som_exempt(usb_pd_zone):
    insts, *_ = usb_pd_zone
    cap = _inst("C9001", insts[-1].mod_path, 105.0, 90.0, side="bottom")
    res = placement_mech.check(_model([cap], som_core=_CORE))
    assert not res.top_under_som and not res.under_som


def test_control_under_som_fires(usbc_mods):
    sw = _inst("SW9001", usbc_mods["switch"], 105.0, 90.0)
    res = placement_mech.check(_model([sw], som_core=_CORE))
    assert res.under_som and res.controls_under_som and not res.ok


# --- placement_contract (scattered decoupling) ------------------------------------

def test_scattered_decoupling_fires(usb_pd_zone):
    insts, resolvable, contract, rot = usb_pd_zone
    band = g._board_refs_by_sheet("usb_pd")
    c1 = band["C1"]
    mut = [i if i.ref != c1 else
           _inst(c1, i.mod_path, (i.x - ORIGIN_X) + 30.0, i.y - ORIGIN_Y,
                 i.rotation)
           for i in insts]
    chk = g.check(_model(mut), sheet_name="usb_pd", contract=contract,
                  ref_map=band)
    assert chk.proximity_fail > 0 and not chk.ok


def test_clean_zone_passes_contract(usb_pd_zone):
    insts, _res, contract, _rot = usb_pd_zone
    chk = g.check(_model(list(insts)), sheet_name="usb_pd", contract=contract,
                  ref_map=g._board_refs_by_sheet("usb_pd"))
    assert chk.ok and chk.proximity_fail == 0


# --- fanout -----------------------------------------------------------------------

def test_starved_fanout_fires(usbc_mods):
    ic = _inst("U9001", usbc_mods["switch"], 100.0, 100.0, sheet="a")
    crowd = _inst("U9002", usbc_mods["esd"], 103.2, 100.0, sheet="b")
    res = fanout_gate.check(_model([ic, crowd]), baseline=0)
    assert res.n_starved >= 1 and not res.ok


def test_spread_fanout_clean(usbc_mods):
    ic = _inst("U9001", usbc_mods["switch"], 60.0, 100.0, sheet="a")
    other = _inst("U9002", usbc_mods["esd"], 140.0, 100.0, sheet="b")
    res = fanout_gate.check(_model([ic, other]), baseline=0)
    assert res.n_starved == 0 and res.ok
