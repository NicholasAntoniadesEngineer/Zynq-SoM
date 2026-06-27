"""MUTATION coverage for the PCB gates (#1) + a kicad-cli DRC CROSS-CHECK (#2).

schgen/verify/selftest.py mutation-tests every SCHEMATIC gate (it injects each
gate's defect class and proves the gate KILLS the mutant). The PCB gates,
however, had ZERO mutation coverage — and real PCB-gate bugs shipped *because*
of that gap:

  * model3d_gate's MISPLACED check used a CCW model-Z rotation while kicad-cli
    applies CW, so a 90deg-rotated off-board header body sat off its pads and
    PASSED the gate (the ESC 3x8 PWM header bug);
  * the refdes_overlap_gate's silk box model could silently DRIFT from KiCad's
    own silk DRC with nothing tying the two together.

This module closes both. For EACH pcb gate it builds the MINIMAL input carrying
that gate's DEFECT CLASS and asserts the gate FAILS it (kills the mutant) — the
exact selftest.py discipline, now applied to the PCB gates:

  (a) model3d_gate
        - MISPLACED: a footprint whose 3D model is offset clean off its pads
          -> ``res.misplaced`` non-empty, ``res.ok`` False (HARD).
        - MISPLACED via a 90deg model-Z: the historical handedness bug — an
          off-center body that sits ON the pads at Z=0 is rotated off them at
          Z=90 (a model centered at origin is rotation-invariant, so the fixture
          is deliberately off-center); the gate must catch it.
        - MISSING/BROKEN: a footprint with no (model ...) clause and one with a
          bare (unresolvable) .wrl ref -> ``res.missing`` / ``res.broken``,
          ``res.ok`` False.
  (b) connector_model_gate
        - BAD-Z: an off-board connector footprint with model rotate Z = 90
          -> ``res.bad_z`` non-empty, ``res.ok`` False.
  (c) ratsnest_gate / refdes_overlap_gate
        - OFF-BOARD: a footprint shoved past Edge.Cuts -> ``res.off_board``.
        - DISPERSED: a scattered subsystem -> ``res.dispersed``.
        - REFDES OVERPRINT: two coincident visible reference designators
          -> ``res.top_pairs``, ``res.ok`` False.
  (d) CROSS-CHECK (#2): run ``kicad-cli pcb drc`` on the emitted carrier board
      and assert the refdes/silk gate's OWN reference-overprint count AGREES
      with KiCad's count of Reference-vs-Reference ``silk_overlap`` violations —
      so the gate cannot silently drift from DRC.

A BASELINE assertion precedes every mutant (a gate that always fires proves
nothing): the clean fixture passes, the mutated one fails. If a gate FAILS to
catch its mutant that is a REAL gap — the test is written ``xfail`` with a note
(NEVER weaken the gate to hide it, LAW 4). At authoring time every gate below
correctly kills its mutant, so none are xfail.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from schgen.generate.pcb import (FootprintInst, PcbModel, ORIGIN_X, ORIGIN_Y,
                                 resolve_mod)
from schgen.verify import (model3d_gate, connector_model_gate as cmg,
                          ratsnest_gate, refdes_overlap_gate)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CARRIER_PCB = _REPO_ROOT / "carrier" / "Zynq_Carrier.kicad_pcb"


# ---------------------------------------------------------------------------
# (a) model3d_gate — MISPLACED (body off its pads) + MISSING/BROKEN model
# ---------------------------------------------------------------------------
#
# A synthetic parts/ tree is written to a tmp dir and the gate is pointed at it
# via monkeypatch on g._PARTS_DIR (the same hook the existing gate unit tests
# use), so no tracked footprint is touched. The model3d_gate scans
# g._PARTS_DIR.glob("*/*.kicad_mod"); each MPN is a sub-dir.

def _write_part(parts: Path, mpn: str, body: str) -> None:
    d = parts / mpn
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mpn}.kicad_mod").write_text(body)


# a footprint with a real pad field (~2 mm wide) so the pad bbox is non-empty;
# {model} is spliced in so each fixture controls the (model ...) clause.
_FP = """(footprint "X" (layer "F.Cu")
  (pad "1" smd roundrect (at -1.0 0) (size 0.8 1.6) (layers "F.Cu"))
  (pad "2" smd roundrect (at  1.0 0) (size 0.8 1.6) (layers "F.Cu"))
{model}
)
"""


def _vrml_box(w_in: float, h_in: float) -> str:
    """A minimal VRML box w_in x h_in 0.1-inch VRML units (-> x2.54 mm), so a
    1.0 x 0.8 box is ~2.54 x 2.03 mm — comparable to the pad field above. The
    box is CENTERED at the model origin."""
    return _vrml_rect(-w_in / 2, -h_in / 2, w_in / 2, h_in / 2)


def _vrml_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    """A VRML rectangle spanning [x0,x1] x [y0,y1] in 0.1-inch VRML units
    (-> x2.54 mm). Unlike ``_vrml_box`` this lets the body be OFF-CENTER, which
    is what makes the model-Z rotation actually move the body — a model centered
    at origin is rotation-invariant, so an off-center body is required to
    exercise the rotation handedness."""
    return ("#VRML V2.0 utf8\nShape{geometry IndexedFaceSet{coord Coordinate{"
            f"point [{x0} {y0} 0, {x1} {y0} 0, {x1} {y1} 0, {x0} {y1} 0] }}}}\n")


def test_model3d_baseline_passes(tmp_path, monkeypatch):
    """BASELINE: a footprint whose resolving model sits centered ON its pads is
    covered and the gate is green — proving the mutants below flip a GREEN gate
    RED, not a gate that already fires."""
    parts = tmp_path / "parts"
    wrl = tmp_path / "good.wrl"
    wrl.write_text(_vrml_box(1.0, 0.8))
    model = (f'  (model "{wrl}"\n    (offset (xyz 0 0 0))\n'
             '    (scale (xyz 1 1 1))\n    (rotate (xyz 0 0 0)))')
    _write_part(parts, "GOOD", _FP.format(model=model))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert res.ok and res.covered == 1
    assert not res.misplaced and not res.broken and not res.missing


def test_model3d_misplaced_offset_mutant_is_killed(tmp_path, monkeypatch):
    """MUTANT (HARD): the model is offset 5.4 mm off its pads — the EasyEDA
    c_origin unit-mismatch defect class. The HARD position check MUST fire."""
    parts = tmp_path / "parts"
    wrl = tmp_path / "m.wrl"
    wrl.write_text(_vrml_box(1.0, 0.8))
    model = (f'  (model "{wrl}"\n    (offset (xyz -5.4 1.5 0))\n'
             '    (scale (xyz 1 1 1))\n    (rotate (xyz 0 0 0)))')
    _write_part(parts, "OFFSET", _FP.format(model=model))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert "OFFSET" in res.misplaced, res.report()
    assert res.ok is False, "a body off its pads must HARD-FAIL the board"


def test_model3d_misplaced_rotated_mutant_is_killed(tmp_path, monkeypatch):
    """MUTANT (the handedness bug): the SAME off-center body that sits ON the pads
    at model-Z 0 is rotated off them by a 90deg model-Z — the genuine handedness
    defect class the CCW->CW model-Z fix addressed (a 90deg model rotate planted
    the ESC PWM header body off its pads while the gate, doing CCW, missed it).

    The body is CENTERED at +1.0 mm X (over the right pad), so:
      * model-Z 0   -> body over the pads -> PASS (the BASELINE half here: the
                       rotation, not the body, is the load-bearing mutation);
      * model-Z 90  -> the off-center body swings clear of the short Y pad bbox
                       -> MISPLACED (killed). A model centered at origin would be
                       rotation-invariant, which is why this fixture is off-center.
    """
    # an off-center body: span [0.15,0.65] x [-0.25,0.25] 0.1-in VRML units ->
    # center (0.4, 0)*2.54 = (+1.0, 0) mm, size ~1.27 x 1.27 mm.
    wrl = tmp_path / "oc.wrl"
    wrl.write_text(_vrml_rect(0.15, -0.25, 0.65, 0.25))

    def check_with_z(z: float):
        parts = tmp_path / f"parts_z{int(z)}"
        model = (f'  (model "{wrl}"\n    (offset (xyz 0 0 0))\n'
                 f'    (scale (xyz 1 1 1))\n    (rotate (xyz 0 0 {z})))')
        _write_part(parts, "ROT", _FP.format(model=model))
        monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
        monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
        return model3d_gate.check(model_dir=tmp_path / "3dmodels")

    # baseline: the unrotated off-center body sits ON the pads -> the gate passes,
    # so the rotation alone is what flips it (a pure-offset test would not prove
    # the rotation handedness is exercised).
    assert "ROT" not in check_with_z(0.0).misplaced, "rot-0 body must sit on pads"
    # mutant: the 90deg model-Z rotates the off-center body off its pads.
    res = check_with_z(90.0)
    assert "ROT" in res.misplaced, res.report()
    assert res.ok is False


def test_model3d_missing_clause_mutant_is_killed(tmp_path, monkeypatch):
    """MUTANT: a custom footprint with NO (model ...) clause at all -> the gate
    reports it MISSING and HARD-fails (an empty 3D viewer with no signal was the
    original undocumented-gap bug)."""
    parts = tmp_path / "parts"
    _write_part(parts, "NOMODEL", _FP.format(model=""))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert res.missing == ["NOMODEL"]
    assert res.ok is False


def test_model3d_broken_ref_mutant_is_killed(tmp_path, monkeypatch):
    """MUTANT: a bare-filename (unresolvable) .wrl ref — the pre-fix EasyEDA
    state that resolved to nothing on disk -> BROKEN, HARD-fail."""
    parts = tmp_path / "parts"
    model = ('  (model "BARE.wrl"\n    (offset (xyz 0 0 0))\n'
             '    (scale (xyz 1 1 1))\n    (rotate (xyz 0 0 0)))')
    _write_part(parts, "BROKEN", _FP.format(model=model))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert "BROKEN" in res.broken
    assert res.ok is False


# ---------------------------------------------------------------------------
# (b) connector_model_gate — BAD model-Z (a flipped/perpendicular mouth)
# ---------------------------------------------------------------------------

_CONN_FP = """(footprint "X"
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


def _conn_inst(tmp_path: Path, mpn: str, z: float) -> FootprintInst:
    """A placed off-board-connector instance whose footprint has model rotate Z
    = ``z``. ``mpn`` must be a real CONN_MATING_FACE key (the gate maps by
    value). A geometry-EXCEPTION MPN is used so ONLY check (1) (model-Z) governs
    it — the synthetic pads cannot raise a spurious geometry conflict."""
    mod = tmp_path / f"{mpn}.kicad_mod"
    mod.write_text(_CONN_FP.format(z=z))
    return FootprintInst(ref="J1", value=mpn, footprint=f"{mpn}:{mpn}",
                         x=ORIGIN_X + 10, y=ORIGIN_Y + 10, rotation=0.0,
                         pad_nets={}, mod_path=mod, sheet="t", side="top")


def _conn_model(inst: FootprintInst) -> PcbModel:
    return PcbModel(board_w=50.0, board_h=50.0, insts=[inst],
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=1, deferred=[], som_core=None)


def test_connector_model_baseline_passes(tmp_path):
    """BASELINE: model-Z = 0 on an off-board connector passes the gate."""
    res = cmg.check(_conn_model(_conn_inst(tmp_path, "TF-01A", 0.0)))
    assert res.ok and not res.bad_z, res.summary()


def test_connector_model_badz_90_mutant_is_killed(tmp_path):
    """MUTANT: model rotate Z = 90 makes the rendered shell PERPENDICULAR to its
    pads (the USB-C 180-flip's worse cousin) -> bad_z, HARD-fail."""
    res = cmg.check(_conn_model(_conn_inst(tmp_path, "TF-01A", 90.0)))
    assert res.ok is False, "model-Z=90 must FAIL the connector-model gate"
    assert any("J1" in b and "TF-01A" in b for b in res.bad_z), res.summary()


# ---------------------------------------------------------------------------
# (c) ratsnest_gate (off-board + dispersed) + refdes_overlap_gate (overprint)
# ---------------------------------------------------------------------------
#
# A tiny synthetic PcbModel: two tight subsystem clusters inside a small
# Edge.Cuts rectangle. The LAW-5 ratsnest gate PASSES it; each mutant introduces
# exactly one defect class.

def _ratsnest_fixture() -> PcbModel:
    fp = "Resistor_SMD:R_0603_1608Metric"
    mod = resolve_mod(fp)
    assert mod is not None
    bw, bh = 60.0, 40.0

    def inst(ref, sheet, x, y, net):
        return FootprintInst(
            ref=ref, value="10k", footprint=fp,
            x=ORIGIN_X + x, y=ORIGIN_Y + y, rotation=0.0,
            pad_nets={"1": (1, net), "2": (2, "GND")}, mod_path=mod,
            sheet=sheet, side="top")

    insts = [
        inst("R1", "subsys_a", 8, 8, "A_SIG"),
        inst("R2", "subsys_a", 12, 8, "A_SIG"),
        inst("R3", "subsys_a", 10, 12, "A_SIG"),
        inst("R7", "subsys_a", 8, 12, "A_SIG"),
        inst("R4", "subsys_b", 48, 8, "A_SIG"),
        inst("R5", "subsys_b", 52, 8, "B_SIG"),
        inst("R6", "subsys_b", 50, 12, "B_SIG"),
    ]
    return PcbModel(
        board_w=bw, board_h=bh, insts=insts,
        net_numbers={"": 0, "A_SIG": 1, "B_SIG": 2, "GND": 3},
        netclass_of={}, classes={}, placed=len(insts), deferred=[],
        som_keepout=None, n_top=len(insts), n_bottom=0, two_side=True)


def test_ratsnest_baseline_passes():
    """BASELINE: the tight two-cluster, all-on-board fixture passes LAW-5."""
    res = ratsnest_gate.check(_ratsnest_fixture())
    assert res.ok, res.summary()
    assert not res.off_board and not res.dispersed


def test_ratsnest_offboard_mutant_is_killed():
    """MUTANT: shove R6 200 mm past the right Edge.Cuts edge -> off_board,
    HARD-fail (the historical off-board-connector defect class)."""
    mut = _ratsnest_fixture()
    for i in mut.insts:
        if i.ref == "R6":
            i.x = i.x + 200.0
    res = ratsnest_gate.check(mut)
    assert res.ok is False
    assert res.off_board and any("R6" in o for o in res.off_board), res.summary()


def test_ratsnest_dispersed_mutant_is_killed():
    """MUTANT: scatter subsys_a's 4 parts to the four board corners -> the
    dispersion metric blows past the threshold (the hairball defect class)."""
    mut = _ratsnest_fixture()
    spread = [(2, 2), (55, 2), (55, 36), (2, 36)]
    k = 0
    for i in mut.insts:
        if i.sheet == "subsys_a":
            i.x = ORIGIN_X + spread[k][0]
            i.y = ORIGIN_Y + spread[k][1]
            k += 1
    res = ratsnest_gate.check(mut)
    assert res.ok is False
    assert res.dispersed and any("subsys_a" in d for d in res.dispersed), \
        res.summary()


def _silk_board(*footprints: str) -> str:
    return "(kicad_pcb\n" + "\n".join(footprints) + "\n)"


def _silk_fp(ref: str, fx: float, fy: float, lx: float, ly: float) -> str:
    return (f'(footprint "lib:{ref}" (at {fx} {fy} 0) (layer "F.Cu") '
            f'(property "Reference" "{ref}" (at {lx} {ly}) (layer "F.SilkS")))')


def test_refdes_overlap_baseline_passes(tmp_path):
    """BASELINE: two well-separated visible refdes pass the silk gate."""
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_silk_board(_silk_fp("U1", 10, 10, 0, 0),
                             _silk_fp("U2", 60, 60, 0, 0)))
    res = refdes_overlap_gate.check(p)
    assert res.ok and not res.top_pairs and res.n_top == 2


def test_refdes_overlap_mutant_is_killed(tmp_path):
    """MUTANT: two coincident visible reference designators -> top_pairs,
    HARD-fail (the dense-cluster silk-overprint defect class)."""
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_silk_board(_silk_fp("U1", 10, 10, 0, 0),
                             _silk_fp("U2", 10, 10, 0, 0)))
    res = refdes_overlap_gate.check(p)
    assert res.ok is False
    assert res.top_pairs == [("U1", "U2")], res


# ---------------------------------------------------------------------------
# (d) CROSS-CHECK (#2): the refdes/silk gate must AGREE with kicad-cli DRC
# ---------------------------------------------------------------------------
#
# The refdes_overlap_gate composes its own silk text boxes and counts
# Reference-vs-Reference overprints. KiCad's own ``silk_overlap`` DRC check
# composes the real silkscreen and reports overlapping items. If the gate's
# notion of a reference overprint ever drifts from KiCad's, the two counts
# diverge — the exact #2 failure mode (a gate disagreeing with DRC). This test
# runs ``kicad-cli pcb drc`` on the EMITTED carrier board and asserts the gate's
# top_pairs count equals KiCad's count of Reference-vs-Reference silk_overlap
# violations. On the shipped board both are 0; the equality is the contract.

_KICAD_CLI = shutil.which("kicad-cli")


def _kicad_ref_ref_silk_overlaps(pcb: Path, out_json: Path) -> int:
    """Run kicad-cli DRC and count silk_overlap violations whose BOTH items are
    reference-designator fields (the subset the refdes gate is responsible for).
    KiCad describes such an item as "Reference 'U1' on F.Silkscreen"."""
    subprocess.run(
        [_KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all",
         "-o", str(out_json), str(pcb)],
        check=True, capture_output=True, text=True, timeout=600)
    d = json.loads(out_json.read_text())
    n = 0
    for v in d.get("violations", []):
        if v.get("type") != "silk_overlap":
            continue
        descs = [it.get("description", "") for it in v.get("items", [])]
        if descs and all(de.startswith("Reference") for de in descs):
            n += 1
    return n


@pytest.mark.skipif(_KICAD_CLI is None, reason="kicad-cli not on PATH")
def test_refdes_gate_agrees_with_kicad_drc(tmp_path):
    """#2 CROSS-CHECK: the refdes gate's reference-overprint count on the emitted
    carrier board MUST equal kicad-cli DRC's count of Reference-vs-Reference
    silk_overlap violations — so the gate cannot silently drift from DRC."""
    if not _CARRIER_PCB.exists():
        pytest.skip("carrier board not emitted (run `schgen board` first)")
    gate_pairs = len(refdes_overlap_gate.check(_CARRIER_PCB).top_pairs)
    kicad_pairs = _kicad_ref_ref_silk_overlaps(
        _CARRIER_PCB, tmp_path / "drc.json")
    assert gate_pairs == kicad_pairs, (
        f"refdes_overlap_gate reports {gate_pairs} reference overprints but "
        f"kicad-cli DRC reports {kicad_pairs} Reference-vs-Reference "
        f"silk_overlap violations — the gate has DRIFTED from KiCad's silk DRC")
    # On the shipped board the agreed count is 0 (the gate passes the board).
    assert gate_pairs == 0, (
        f"the emitted carrier board has {gate_pairs} reference overprints "
        f"(both the gate and KiCad agree) — a real silk regression")
