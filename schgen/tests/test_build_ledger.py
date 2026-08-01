from __future__ import annotations

import pytest

from schgen.core import ledger
from schgen.verify import ledger_gate


@pytest.fixture(autouse=True)
def _clean():
    ledger.reset()
    yield
    ledger.reset()


def test_every_declaration_has_a_declared_step_and_terse_basis():
    for name, d in ledger.REGISTRY.items():
        assert d.step in ledger.STEP_PARENT, name
        assert len(d.basis) <= ledger.BASIS_MAX_CHARS, name
        assert d.kind in (ledger.CALC_KIND, ledger.ASSUME_KIND), name
        if d.kind == ledger.ASSUME_KIND:
            assert d.source in ledger.SOURCE_CLASSES, name
            assert len(d.covers) == 1, name
        else:
            assert d.inputs and d.expr, name


def test_assumption_source_class_cannot_be_invented():
    with pytest.raises(AssertionError, match="source class"):
        ledger._assume("bogus_source_probe", "netlist", "config.CROSS_K",
                       "mm", "vibes", "probe")


def test_basis_longer_than_the_cap_is_refused():
    with pytest.raises(AssertionError, match="data, not prose"):
        ledger._assume("bogus_prose_probe", "netlist", "config.CROSS_K", "mm",
                       "policy", "x" * (ledger.BASIS_MAX_CHARS + 1))


def test_every_assumption_cover_resolves_to_a_live_constant():
    for name, d in ledger.REGISTRY.items():
        if d.kind != ledger.ASSUME_KIND:
            continue
        assert ledger._resolve(d.covers[0]) is not None, name


def test_calc_refuses_an_undeclared_name():
    with pytest.raises(AssertionError, match="not a declared calculation"):
        with ledger.step("netlist"):
            ledger.calc("no_such_calculation", 1.0, a=1)


def test_calc_refuses_the_wrong_step():
    with pytest.raises(AssertionError, match="declared under step"):
        with ledger.step("netlist"):
            ledger.calc("sizing_winner", "1x1", board_w=1, board_h=1, area=1,
                        est_cross=1, budget=1, headroom=1, plan="x")


def test_calc_refuses_drifting_inputs():
    with pytest.raises(AssertionError, match="inputs may not drift"):
        with ledger.step("netlist"):
            ledger.calc("sheet_census", 1, n_sheets=1, n_som_j=1)


def test_step_refuses_the_wrong_parent():
    with pytest.raises(AssertionError, match="execution order"):
        with ledger.step("sizing.pass", "probe"):
            pass


def test_recorded_lines_are_recomputable_from_their_own_text():
    with ledger.step("netlist"):
        ledger.calc("sheet_census", 30, n_sheets=37, n_som_j=3,
                    n_decoupling=1)
    line = [e.text for e in ledger.entries() if e.name == "sheet_census"][0]
    assert "n_sheets=37" in line and "n_som_j=3" in line
    assert "n_sheets - n_som_j - n_decoupling" in line
    assert "= 30" in line


def test_replay_of_a_repeated_step_collapses_to_one_identical_line():
    for _ in range(2):
        with ledger.step("floorplan.sizing"):
            ledger.calc("subsystem_count", 33, n_sheets=37, n_som_j=3,
                        n_mechanical_only=1)
    kinds = [e.kind for e in ledger.entries()]
    assert kinds.count(ledger.REPLAY_KIND) == 1
    assert kinds.count(ledger.CALC_KIND) == 1
    assert "identical=yes" in ledger.entries()[-1].text
    assert not ledger.problems()


def test_replay_divergence_is_a_loud_problem():
    with ledger.step("floorplan.sizing"):
        ledger.calc("subsystem_count", 33, n_sheets=37, n_som_j=3,
                    n_mechanical_only=1)
    with ledger.step("floorplan.sizing"):
        ledger.calc("subsystem_count", 32, n_sheets=36, n_som_j=3,
                    n_mechanical_only=1)
    assert ledger.problems()
    assert "identical=NO" in ledger.entries()[-1].text


def test_gate_fails_when_a_declared_entry_never_appears():
    res = ledger_gate.check()
    assert not res.ok
    assert res.absent


def test_gate_census_finds_an_undeclared_constant(tmp_path):
    src = tmp_path / "config.py"
    src.write_text("KNOWN = 1.0\nSMUGGLED_MARGIN = 4.2\n")
    top, buried = ledger_gate.scan("config", src)
    assert "config.SMUGGLED_MARGIN" in top
    assert not buried


def test_gate_census_finds_a_constant_buried_in_a_function(tmp_path):
    src = tmp_path / "config.py"
    src.write_text("def f():\n    HIDDEN_GAP = 2.5\n    return HIDDEN_GAP\n")
    _top, buried = ledger_gate.scan("config", src)
    assert any("HIDDEN_GAP" in b for b in buried)


def test_live_decision_files_hold_no_undeclared_or_buried_constant():
    res = ledger_gate.check()
    assert res.undeclared == []
    assert res.buried == []
    assert res.stale == []
    assert res.n_constants > 0


def test_number_rendering_is_stable_and_unit_free():
    assert ledger._num(3.0) == "3"
    assert ledger._num(0.62) == "0.62"
    assert ledger._num(16382.55) == "16382.55"
    assert ledger._num(7) == "7"
