"""Unit tests for the LAW-6 connector 3D-MODEL ORIENTATION gate
(schgen.verify.connector_model_gate).

The gate exists to KILL a board whose pads/courtyard/placement-rotation are all
correct (placement_mech PASS, DRC=0, ratsnest PASS) but whose 3D ``.wrl`` model
renders its OPENING the wrong way — the historical USB-C ``(rotate (xyz 0 0
180))`` faced the rendered mouth INWARD while every other gate was green. So each
test is a mutant: a state that should PASS, then a single-defect mutation that
must FAIL, proving the gate bites.

Two mutation surfaces are exercised:
  (1) the footprint's model rotate Z (the exact USB-C bug), via a synthetic
      .kicad_mod written to tmp so a real file is never touched;
  (2) the CONN_MATING_FACE geometry cross-check, by flipping the declared face
      of a through-shell connector against its real pad geometry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from schgen.generate import pcb
from schgen.generate.pcb import FootprintInst, PcbModel, ORIGIN_X, ORIGIN_Y
from schgen.verify import connector_model_gate as cmg


# ---- the static contract: the current footprints are all clean ----------------

def test_current_footprints_pass_footprint_only():
    """Footprint-only mode (no board build) over every CONN_MATING_FACE MPN: all
    8 must have model-Z = 0 and no geometry conflict on the real parts."""
    res = cmg.check()
    assert res.ok, res.summary()
    assert res.n_connectors == len(pcb.CONN_MATING_FACE)
    assert not res.bad_z and not res.geom_conflicts


def test_built_board_passes():
    """The real placed board: every placed off-board connector instance has a
    clean 3D-model orientation."""
    res = cmg.check(pcb.build_model())
    assert res.ok, res.summary()
    assert res.n_connectors >= len(pcb.CONN_MATING_FACE)
    assert not res.bad_z and not res.geom_conflicts


def test_every_mpn_is_classified():
    """Every off-board MPN is either geometry-checked or a REVIEWED exception —
    a new connector cannot slip past the cross-check unclassified (this is the
    module-load assert, re-asserted as a test for visibility)."""
    classified = set(cmg._GEOM_SHELL) | set(cmg._GEOM_EXCEPTIONS)
    assert set(pcb.CONN_MATING_FACE) <= classified, \
        f"unclassified MPNs: {set(pcb.CONN_MATING_FACE) - classified}"


# ---- mutant (1): a non-zero model-Z must FAIL ---------------------------------

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
    """A FootprintInst whose footprint file is a synthetic .kicad_mod with model
    rotate Z = ``z`` — lets us inject the Z bug without touching a tracked part.
    ``mpn`` must be a real CONN_MATING_FACE key (the gate maps by value/name)."""
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
    """A synthetic off-board connector with model-Z = 0 passes check (1)."""
    # use a geometry-EXCEPTION MPN so only check (1) applies (no geom conflict
    # from the synthetic pad layout).
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 0.0)))
    assert res.ok, res.summary()
    assert not res.bad_z


@pytest.mark.parametrize("z", [90.0, -90.0, 270.0, 45.0])
def test_mutant_perpendicular_or_garbage_model_z_fails(tmp_path, z):
    """A 90/270 model-Z makes the model PERPENDICULAR to its footprint, and a
    non-orthogonal value is conversion garbage — both MUST fail."""
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", z)))
    assert not res.ok, f"model-Z={z} must FAIL the gate"
    assert any("J1" in b and "TF-01A" in b for b in res.bad_z), res.summary()


@pytest.mark.parametrize("z", [180.0, -180.0])
def test_axis_aligned_180_model_z_passes(tmp_path, z):
    """Model-Z = 180 is AXIS-ALIGNED with the footprint (a valid in-plane MOUTH
    FLIP that corrects a .wrl authored with its cavity on the opposite end — the
    real TYPE-C-31-M-12 needs exactly this). It must NOT be flagged as bad-Z."""
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", z)))
    assert not res.bad_z, res.summary()


def test_model_z_360_is_zero_mod_360(tmp_path):
    """Z = 360 is congruent to 0 — it must NOT fail (the gate checks Z mod 360,
    not Z == 0, so a redundant full turn is not a false positive)."""
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 360.0)))
    assert res.ok, res.summary()


# ---- mutant (2): geometry cross-check vs CONN_MATING_FACE ----------------------

def test_mutant_flipped_mating_face_geom_conflict(monkeypatch, tmp_path):
    """Flip the DECLARED mating face of a through-shell connector (USB-C) so it
    contradicts the real pad geometry. The geometry cross-check MUST fail even
    though model-Z is 0 — this catches a hand-edited CONN_MATING_FACE typo that
    the Z check cannot see."""
    # USB-C real geometry: the 12 dense SMD signal contacts are at -Y, so the
    # mouth is OPPOSITE = +Y (the correct shipped value). Declare -Y to conflict
    # (that wrong value is exactly what faced the mouth inboard before the fix).
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
    """An exception-listed MPN (microSD) is never geometry-cross-checked, so its
    synthetic-pad geometry cannot raise a false conflict — only check (1)
    governs it."""
    res = cmg.check(_model_with(_synth_inst(tmp_path, "TF-01A", 0.0)))
    assert not any("TF-01A" in g for g in res.geom_checked)
    assert not res.geom_conflicts
