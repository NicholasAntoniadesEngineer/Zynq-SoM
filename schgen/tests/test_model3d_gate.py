"""Tests for the 3D-model coverage gate (schgen/verify/model3d_gate.py).

Locks the SOFT-gate contract:
  * a footprint whose (model ...) path RESOLVES to a file on disk counts as
    covered; a bare/missing/broken ref does NOT;
  * a documented-unmatched part keeps the gate GREEN (ok=True) and lands in
    .unmatched (not .broken / .missing);
  * an UNDOCUMENTED broken/missing ref flips ok=False (visible regression);
  * the one-line summary + report are DETERMINISTIC (sorted by MPN);
  * the CURRENT real parts/ tree is covered (every custom footprint either
    resolves a stock model or is a documented unmatched part — no surprise
    gaps), proving the gate passes on the shipped board.

Synthetic footprints are written to a tmp dir with a fake 3D-model dir, so the
core resolution logic is pure/offline; one test also runs against the real
parts/ tree to lock the shipped coverage."""

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
    # The pre-fix EasyEDA bare-filename ref: a relative path never resolves.
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"X1": '  (model "X1.wrl" (offset (xyz 0 0 0)) '
                                   '(scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))'})
        _patch(monkeypatch, parts, known={})
        res = g.check(model_dir=root / "3dmodels")
        assert res.covered == 0
        assert "X1" in res.broken
        assert res.ok is False          # undocumented broken ref -> regression


def test_missing_model_clause_fails(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        parts = root / "parts"
        _make_parts(parts, {"X2": None})       # no (model ...) at all
        _patch(monkeypatch, parts, known={})
        res = g.check(model_dir=root / "3dmodels")
        assert res.covered == 0
        assert res.missing == ["X2"]
        assert res.ok is False


def test_documented_unmatched_stays_green(monkeypatch):
    # A part on the documented unmatched list with NO model clause is a KNOWN
    # gap: it lands in .unmatched, NOT .missing/.broken, and keeps ok=True.
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
        # two unmatched, declared OUT of sorted order on disk creation
        _make_parts(parts, {"ZZ": None, "AA": None})
        _patch(monkeypatch, parts, known={"ZZ": "z", "AA": "a"})
        res = g.check(model_dir=root / "3dmodels")
        # unmatched list in the one-line summary is sorted by MPN
        assert res.line() == ("3D MODELS: 0/2 footprints; 2 unmatched: "
                              "[AA, ZZ]")
        # report stable across calls
        assert res.report() == g.check(model_dir=root / "3dmodels").report()


def test_real_parts_tree_is_covered_or_documented():
    """The shipped parts/ tree: every custom footprint either resolves a stock
    3D model or is a documented unmatched part — NO undocumented gap, so the
    SOFT gate is green on the real board."""
    res = g.check()
    assert res.total >= 50            # ~56 custom footprints
    assert res.covered >= 50          # the overwhelming majority have a model
    assert res.ok is True             # no broken/missing undocumented ref
    assert not res.broken
    assert not res.missing
    # every gap is an explicitly documented unmatched part
    for mpn in res.unmatched:
        assert mpn in g._KNOWN_UNMATCHED
