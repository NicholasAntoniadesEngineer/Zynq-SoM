from __future__ import annotations

import pathlib
import tempfile

from schgen.verify import model3d_gate as g


def _fp(model_line: str | None) -> str:
    body = '(footprint "T" (layer "F.Cu")\n  (pad "1" smd rect (at 0 0) ' \
           '(size 1 1) (layers "F.Cu"))\n'
    if model_line is not None:
        body += model_line + "\n"
    return body + ")\n"


def _make_parts(tmp: pathlib.Path, parts: dict[str, str | None]) -> None:
    for mpn, model_line in parts.items():
        d = tmp / mpn
        d.mkdir(parents=True)
        (d / f"{mpn}.kicad_mod").write_text(_fp(model_line))


def _patch(monkeypatch, parts_dir, known=None):
    monkeypatch.setattr(g, "_PARTS_DIR", parts_dir)
    if known is not None:
        monkeypatch.setattr(g, "_KNOWN_UNMATCHED", known)


def test_resolving_model_is_covered(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        md = root / "3dmodels"
        (md / "Resistor_SMD.3dshapes").mkdir(parents=True)
        (md / "Resistor_SMD.3dshapes" / "R_0603.step").write_text("x")
        parts = root / "parts"
        _make_parts(parts, {
            "R1": '  (model "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/'
                  'R_0603.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) '
                  '(rotate (xyz 0 0 0)))',
        })
        _patch(monkeypatch, parts, known={})
        res = g.check(model_dir=md)
        assert res.total == 1
        assert res.covered == 1
        assert res.ok is True
        assert not res.unmatched and not res.broken and not res.missing


def test_bare_wrl_ref_is_broken_and_fails(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"X1": '  (model "X1.wrl" (offset (xyz 0 0 0)) '
                                   '(scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))'})
        _patch(monkeypatch, parts, known={})
        res = g.check(model_dir=root / "3dmodels")
        assert res.covered == 0
        assert "X1" in res.broken
        assert res.ok is False


def test_missing_model_clause_fails(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"X2": None})
        _patch(monkeypatch, parts, known={})
        res = g.check(model_dir=root / "3dmodels")
        assert res.covered == 0
        assert res.missing == ["X2"]
        assert res.ok is False


def test_documented_unmatched_stays_green(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"BESPOKE": None})
        _patch(monkeypatch, parts, known={"BESPOKE": "no stock body"})
        res = g.check(model_dir=root / "3dmodels")
        assert res.ok is True
        assert res.unmatched == {"BESPOKE": "no stock body"}
        assert not res.broken and not res.missing


def test_line_and_report_deterministic(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"ZZ": None, "AA": None})
        _patch(monkeypatch, parts, known={"ZZ": "z", "AA": "a"})
        res = g.check(model_dir=root / "3dmodels")
        assert res.line() == ("3D MODELS: 0/2 footprints; 2 unmatched: "
                              "[AA, ZZ]")
        assert res.report() == g.check(model_dir=root / "3dmodels").report()


def test_real_parts_tree_is_covered_or_documented():
    res = g.check()
    assert res.total >= 50
    assert res.covered >= 50
    assert res.ok is True
    assert not res.broken
    assert not res.missing
    for mpn in res.unmatched:
        assert mpn in g._KNOWN_UNMATCHED


def _fitwrl(w_in, h_in):
    return ("#VRML V2.0 utf8\nShape{geometry IndexedFaceSet{coord Coordinate{"
            f"point [{-w_in/2} {-h_in/2} 0, {w_in/2} {-h_in/2} 0, "
            f"{w_in/2} {h_in/2} 0, {-w_in/2} {h_in/2} 0] }}}}\n")


def _fitfp(w_mm, h_mm):
    return ('(footprint "X"\n'
            f'  (fp_line (start {-w_mm/2} {-h_mm/2}) (end {w_mm/2} {-h_mm/2}) '
            '(layer "F.Fab"))\n'
            f'  (fp_line (start {w_mm/2} {h_mm/2}) (end {-w_mm/2} {h_mm/2}) '
            '(layer "F.Fab"))\n)\n')


def test_fit_law_passes_a_matching_model_and_fails_a_misfit(tmp_path):
    from schgen.verify import model3d_gate as g
    mod = tmp_path / "X.kicad_mod"
    mod.write_text(_fitfp(5.08, 5.08))
    good = tmp_path / "good.wrl"
    good.write_text(_fitwrl(2.0, 2.0))
    body = "\n(scale (xyz 1 1 1))\n(rotate (xyz 0 0 0))"
    assert g._fit_ok(mod, body, good) is None

    big = tmp_path / "big.wrl"
    big.write_text(_fitwrl(8.0, 8.0))
    assert g._fit_ok(mod, body, big) is not None

    mod.write_text(_fitfp(10.16, 2.54))
    rot = tmp_path / "rot.wrl"
    rot.write_text(_fitwrl(4.0, 1.0))
    assert g._fit_ok(mod, "\n(scale (xyz 1 1 1))\n(rotate (xyz 0 0 0))",
                     rot) is None
    assert g._fit_ok(mod, "\n(scale (xyz 1 1 1))\n(rotate (xyz 0 0 90))",
                     rot) is not None


def _padfp():
    return ('(footprint "X"\n'
            '  (pad "1" smd roundrect (at -1.0 0) (size 0.8 1.6) (layers "F.Cu"))\n'
            '  (pad "2" smd roundrect (at 1.0 0) (size 0.8 1.6) (layers "F.Cu"))\n'
            ')\n')


def test_position_law_fails_a_body_planted_off_its_pads(tmp_path):
    from schgen.verify import model3d_gate as g
    mod = tmp_path / "X.kicad_mod"
    mod.write_text(_padfp())
    wrl = tmp_path / "m.wrl"
    wrl.write_text(_fitwrl(1.0, 0.8))
    scale_rot = "\n(scale (xyz 1 1 1))\n(rotate (xyz 0 0 0))"

    assert g._placed_ok(mod, "(offset (xyz 0 0 0))" + scale_rot, wrl) is None

    bad = g._placed_ok(mod, "(offset (xyz -5.4 1.5 0))" + scale_rot, wrl)
    assert bad is not None and "off its pads" in bad

    assert g._placed_ok(mod, "(offset (xyz 0.3 0 0))" + scale_rot, wrl) is None


def test_position_law_is_hard_in_the_result():
    from schgen.verify import model3d_gate as g
    r = g.check()
    assert not r.misplaced, f"models planted off their pads: {dict(r.misplaced)}"
    assert r.ok
