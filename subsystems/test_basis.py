from __future__ import annotations

import ast
import tokenize
from pathlib import Path

import pytest

from subsystems import basis, basis_census

HERE = Path(__file__).resolve().parent
BASIS_SRC = HERE / "basis.py"


def test_census_passes_with_no_raw_values():
    res = basis_census.check()
    assert res.ok, res.summary()
    assert res.n_sites > 0
    assert res.n_files == len(basis_census._netlist_files())


def test_every_registration_matches_a_declared_constant():
    for name, entry in basis.REGISTRY.items():
        assert getattr(basis, name) == entry.value, name


def test_every_entry_carries_unit_basis_and_class():
    for name, entry in basis.REGISTRY.items():
        assert entry.unit in basis._UNITS, (name, entry.unit)
        assert entry.klass in basis._CLASSES, (name, entry.klass)
        assert len(entry.basis.split()) >= 5, name
        assert entry.value.strip(), name


def test_class_set_separates_datasheet_measured_and_policy():
    assert basis._CLASSES == ("datasheet", "measured", "policy")
    seen = {e.klass for e in basis.REGISTRY.values()}
    assert {"datasheet", "policy"} <= seen


def test_register_rejects_an_unknown_class():
    with pytest.raises(AssertionError, match="unknown source class"):
        basis._register("X_TEST_ONE", "1k", "ohm", "some stated basis text",
                        "vibes")


def test_register_rejects_an_unknown_unit():
    with pytest.raises(AssertionError, match="unknown unit"):
        basis._register("X_TEST_TWO", "1k", "furlong", "some basis text here",
                        "policy")


def test_register_rejects_a_conflicting_reregistration():
    name = next(iter(basis.REGISTRY))
    with pytest.raises(AssertionError, match="conflicting registration"):
        basis._register(name, "1k", "ohm", "some stated basis text", "policy")


def test_register_is_idempotent_on_an_identical_reregistration():
    name = next(iter(basis.REGISTRY))
    e = basis.REGISTRY[name]
    before = dict(basis.REGISTRY)
    assert basis._register(e.name, e.value, e.unit, e.basis, e.klass) == e.value
    assert basis.REGISTRY == before


def test_gate_kills_a_raw_literal_value(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'c.part("R1", "Device:R", "4k7", FP, LCSC="C1")\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.ok
    assert any("'4k7'" in r for r in res.raw), res.summary()


def test_gate_kills_an_unregistered_constant(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'c.part("R1", "Device:R", MADE_UP_PULL, FP, LCSC="C1")\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.ok
    assert any("MADE_UP_PULL" in u for u in res.undeclared), res.summary()


def test_gate_kills_a_raw_literal_hidden_in_a_data_table(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'ROWS = (("C1", "100n", FP, "C1"),)\n'
        'for ref, val, fp, lcsc in ROWS:\n'
        '    c.part(ref, "Device:C", val, fp, LCSC=lcsc)\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.ok
    assert any("'100n'" in r for r in res.raw), res.summary()


def test_gate_kills_a_raw_decouple_and_pullup_value(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'c.decouple("U1.1", "100n")\n'
        'c.pullup("U1.2", "10k", "+3V3")\n'
        'c.series("A", "B", "22k1")\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.ok
    assert len(res.raw) == 3, res.summary()


def test_gate_kills_a_dead_registration(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text("PLACEHOLDER = 1\n")
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.ok
    assert len(res.unused) == len(basis.REGISTRY), res.summary()


def test_gate_ignores_a_part_identity_value(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'c.use_part("TPD4E1U06DBVR", ref="U2", value="TPD4E1U06")\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert not res.raw, res.summary()


def test_gate_catches_an_si_magnitude_on_use_part(tmp_path, monkeypatch):
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "widget.py").write_text(
        'c.use_part("SWPA4030S100MT", ref="L1", value="10uH")\n')
    monkeypatch.setattr(basis_census, "SUBSYSTEMS_DIR", tmp_path)
    res = basis_census.check()
    assert any("'10uH'" in r for r in res.raw), res.summary()


def test_basis_module_carries_no_prose():
    src = BASIS_SRC.read_text()
    assert ast.get_docstring(ast.parse(src)) is None
    with BASIS_SRC.open("rb") as fh:
        comments = [t for t in tokenize.tokenize(fh.readline)
                    if t.type == tokenize.COMMENT]
    assert not comments, [t.string for t in comments]


def test_registered_values_are_the_values_the_netlists_emit():
    import subsystems.microsd.microsd as microsd
    c = microsd.circuit()
    pulls = sorted(p.value for p in c.parts.values()
                   if p.lib_id.endswith(":R"))
    assert pulls.count(basis.MICROSD_CARD_PULL) == 5
    assert pulls.count(basis.MICROSD_DETECT_PULL) == 1
