from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y, FootprintInst, PcbModel, resolve_mod
from schgen.verify import connector_model_gate as cmg
from schgen.verify import model3d_gate, ratsnest_gate, refdes_overlap_gate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CARRIER_PCB = _REPO_ROOT / "carrier" / "Zynq_Carrier.kicad_pcb"


def _write_part(parts: Path, mpn: str, body: str) -> None:
    d = parts / mpn
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mpn}.kicad_mod").write_text(body)


_FP = """(footprint "X" (layer "F.Cu")
  (pad "1" smd roundrect (at -1.0 0) (size 0.8 1.6) (layers "F.Cu"))
  (pad "2" smd roundrect (at  1.0 0) (size 0.8 1.6) (layers "F.Cu"))
{model}
)
"""


def _vrml_box(w_in: float, h_in: float) -> str:
    return _vrml_rect(-w_in / 2, -h_in / 2, w_in / 2, h_in / 2)


def _vrml_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    return ("#VRML V2.0 utf8\nShape{geometry IndexedFaceSet{coord Coordinate{"
            f"point [{x0} {y0} 0, {x1} {y0} 0, {x1} {y1} 0, {x0} {y1} 0] }}}}\n")


def test_model3d_baseline_passes(tmp_path, monkeypatch):
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

    assert "ROT" not in check_with_z(0.0).misplaced, "rot-0 body must sit on pads"
    res = check_with_z(90.0)
    assert "ROT" in res.misplaced, res.report()
    assert res.ok is False


def test_model3d_missing_clause_mutant_is_killed(tmp_path, monkeypatch):
    parts = tmp_path / "parts"
    _write_part(parts, "NOMODEL", _FP.format(model=""))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert res.missing == ["NOMODEL"]
    assert res.ok is False


def test_model3d_broken_ref_mutant_is_killed(tmp_path, monkeypatch):
    parts = tmp_path / "parts"
    model = ('  (model "BARE.wrl"\n    (offset (xyz 0 0 0))\n'
             '    (scale (xyz 1 1 1))\n    (rotate (xyz 0 0 0)))')
    _write_part(parts, "BROKEN", _FP.format(model=model))
    monkeypatch.setattr(model3d_gate, "_PARTS_DIR", parts)
    monkeypatch.setattr(model3d_gate, "_KNOWN_UNMATCHED", {})
    res = model3d_gate.check(model_dir=tmp_path / "3dmodels")
    assert "BROKEN" in res.broken
    assert res.ok is False


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
    res = cmg.check(_conn_model(_conn_inst(tmp_path, "TF-01A", 0.0)))
    assert res.ok and not res.bad_z, res.summary()


def test_connector_model_badz_90_mutant_is_killed(tmp_path):
    res = cmg.check(_conn_model(_conn_inst(tmp_path, "TF-01A", 90.0)))
    assert res.ok is False, "model-Z=90 must FAIL the connector-model gate"
    assert any("J1" in b and "TF-01A" in b for b in res.bad_z), res.summary()


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
    res = ratsnest_gate.check(_ratsnest_fixture())
    assert res.ok, res.summary()
    assert not res.off_board and not res.dispersed


def test_ratsnest_offboard_mutant_is_killed():
    mut = _ratsnest_fixture()
    for i in mut.insts:
        if i.ref == "R6":
            i.x = i.x + 200.0
    res = ratsnest_gate.check(mut)
    assert res.ok is False
    assert res.off_board and any("R6" in o for o in res.off_board), res.summary()


def test_ratsnest_dispersed_mutant_is_killed():
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
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_silk_board(_silk_fp("U1", 10, 10, 0, 0),
                             _silk_fp("U2", 60, 60, 0, 0)))
    res = refdes_overlap_gate.check(p)
    assert res.ok and not res.top_pairs and res.n_top == 2


def test_refdes_overlap_mutant_is_killed(tmp_path):
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_silk_board(_silk_fp("U1", 10, 10, 0, 0),
                             _silk_fp("U2", 10, 10, 0, 0)))
    res = refdes_overlap_gate.check(p)
    assert res.ok is False
    assert res.top_pairs == [("U1", "U2")], res


_KICAD_CLI = shutil.which("kicad-cli")


def _kicad_ref_ref_silk_overlaps(pcb: Path, out_json: Path) -> int:
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
    if not _CARRIER_PCB.exists():
        pytest.skip("carrier board not emitted (run `schgen board` first)")
    gate_pairs = len(refdes_overlap_gate.check(_CARRIER_PCB).top_pairs)
    kicad_pairs = _kicad_ref_ref_silk_overlaps(
        _CARRIER_PCB, tmp_path / "drc.json")
    assert gate_pairs == kicad_pairs, (
        f"refdes_overlap_gate reports {gate_pairs} reference overprints but "
        f"kicad-cli DRC reports {kicad_pairs} Reference-vs-Reference "
        f"silk_overlap violations — the gate has DRIFTED from KiCad's silk DRC")
    assert gate_pairs == 0, (
        f"the emitted carrier board has {gate_pairs} reference overprints "
        f"(both the gate and KiCad agree) — a real silk regression")
