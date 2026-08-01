from __future__ import annotations

from pathlib import Path

import pytest

from schgen.generate import pcb
from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y, FootprintInst, PcbModel
from schgen.verify import connector_model_gate as cmg


def test_current_footprints_pass_footprint_only():
    res = cmg.check()
    assert res.ok, res.summary()
    assert res.n_connectors == len(pcb.CONN_MATING_FACE)
    assert not res.bad_z and not res.geom_conflicts


def test_built_board_connectors_have_clean_model_orientation(carrier_model):
    res = cmg.check(carrier_model)
    assert res.ok, res.summary()
    assert res.n_connectors >= len(pcb.CONN_MATING_FACE)
    assert not res.bad_z and not res.geom_conflicts


def test_every_mpn_is_classified():
    classified = set(cmg._GEOM_SHELL) | set(cmg._GEOM_EXCEPTIONS)
    assert set(pcb.CONN_MATING_FACE) <= classified, \
        f"unclassified MPNs: {set(pcb.CONN_MATING_FACE) - classified}"


_SYNTH_FP = """(footprint "X"
  (pad "1" smd rect (at -1 2) (size 0.5 0.5) (layers "F.Cu"))
  (pad "2" smd rect (at  1 2) (size 0.5 0.5) (layers "F.Cu"))
  (pad "MP" smd rect (at 0 -2) (size 1 1) (layers "F.Cu"))
  (model "x.wrl"
    (offset (xyz 0 0 0))
    (scale  (xyz 1 1 1))
    (rotate (xyz 0 0 {z}))
  )
)
"""


def _synth_inst(tmp_path: Path, mpn: str, z: float) -> FootprintInst:
    mod = tmp_path / f"{mpn}.kicad_mod"
    mod.write_text(_SYNTH_FP.format(z=z))
    return FootprintInst(ref="J1", value=mpn, footprint=f"{mpn}:{mpn}",
                         x=ORIGIN_X + 10, y=ORIGIN_Y + 10, rotation=0.0,
                         pad_nets={}, mod_path=mod, sheet="t", side="top")


def _model_with(inst: FootprintInst) -> PcbModel:
    return PcbModel(board_w=50.0, board_h=50.0, insts=[inst],
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=1, deferred=[], som_core=None)


def test_zero_model_z_passes(tmp_path):
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 0.0)))
    assert res.ok, res.summary()
    assert not res.bad_z


@pytest.mark.parametrize("z", [90.0, -90.0, 270.0, 45.0])
def test_mutant_perpendicular_or_garbage_model_z_fails(tmp_path, z):
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", z)))
    assert not res.ok, f"model-Z={z} must FAIL the gate"
    assert any("J1" in b and "TF-01A" in b for b in res.bad_z), res.summary()


@pytest.mark.parametrize("z", [180.0, -180.0])
def test_axis_aligned_180_model_z_passes(tmp_path, z):
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", z)))
    assert not res.bad_z, res.summary()


def test_model_z_360_is_zero_mod_360(tmp_path):
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 360.0)))
    assert res.ok, res.summary()


def test_mutant_flipped_mating_face_geom_conflict(monkeypatch, tmp_path):
    bad_face = dict(pcb.CONN_MATING_FACE)
    bad_face["TYPE-C-31-M-12"] = "-Y"
    monkeypatch.setattr(cmg, "CONN_MATING_FACE", bad_face)

    real_mod = pcb.resolve_mod("TYPE-C-31-M-12:TYPE-C-31-M-12")
    assert real_mod is not None
    inst = FootprintInst(ref="J1", value="TYPE-C-31-M-12",
                         footprint="TYPE-C-31-M-12:TYPE-C-31-M-12",
                         x=ORIGIN_X + 10, y=ORIGIN_Y + 10, rotation=0.0,
                         pad_nets={}, mod_path=real_mod, sheet="t", side="top")
    res = cmg.check(_model_with(inst))
    assert not res.ok, "a CONN_MATING_FACE that contradicts pad geometry must FAIL"
    assert any("J1" in g and "TYPE-C-31-M-12" in g for g in res.geom_conflicts), \
        res.summary()


def test_geometry_check_only_runs_for_shell_connectors(tmp_path):
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 0.0)))
    assert not any("TF-01A" in g for g in res.geom_checked)
    assert not res.geom_conflicts
