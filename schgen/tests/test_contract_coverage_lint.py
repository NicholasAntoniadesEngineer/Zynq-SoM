"""Tests for the CONTRACT COVERAGE LINT (schgen/verify/contract_coverage_lint).

(1) SYNTHETIC: a four-part sheet (anchored IC, clustered cap, declared-free TP,
    naked pull-up) exercises all three classes — STRUCTURED / FREE / UNGATED —
    plus the free channel's self-policing notes, on an injected circuit,
    contract and ref_map. Hermetic: no real sheet, no board build.
(2) REAL SWEEP: ``lint_project()`` over the 23 wired sheets runs clean, every
    part lands in exactly one class, and two independent runs emit
    byte-identical reports (determinism).
"""

from __future__ import annotations

from types import SimpleNamespace

from schgen.core.model import Net, NetClass, Part, PinRef
from schgen.verify import contract_coverage_lint as lint

_SHEET = "synth"


def _part(ref: str, value: str) -> Part:
    return Part(ref=ref, lib_id="Device:C", value=value)


def _circuit() -> SimpleNamespace:
    parts = {
        "U1": _part("U1", "FUSB302BMPX"),
        "C1": _part("C1", "100n"),
        "TP1": _part("TP1", "SENSE"),
        "R9": _part("R9", "10k"),
    }
    nets = {
        "+3V3": Net("+3V3", NetClass.POWER,
                    [PinRef("U1", "1"), PinRef("C1", "1"), PinRef("R9", "1")]),
        "GND": Net("GND", NetClass.GROUND,
                   [PinRef("U1", "2"), PinRef("C1", "2")]),
        "SENSE": Net("SENSE", NetClass.SIGNAL,
                     [PinRef("R9", "2"), PinRef("TP1", "1")]),
    }
    return SimpleNamespace(parts=parts, nets=nets)


_CONTRACT: dict = {
    "structures": [
        {"type": "proximity", "anchor": "U1", "members": ["C1"],
         "max_mm": 2.0, "basis": "judgment:2.0"},
    ],
    "free": [{"ref": "TP1", "why": "test point"}],
}


def _idmap() -> dict[str, str]:
    return {r: r for r in ("U1", "C1", "TP1", "R9")}


def _lint(contract=_CONTRACT):
    return lint.lint_sheet(_SHEET, circuit=_circuit(), contract=contract,
                           ref_map=_idmap())


def test_synthetic_three_classes():
    res = _lint()
    assert res.have_contract and res.n_parts == 4
    assert res.structured == ["C1", "U1"]
    assert res.free_used == [("TP1", "test point")]
    assert [row[0] for row in res.ungated] == ["R9"]
    assert res.notes == []


def test_synthetic_ungated_row_carries_nets_value_and_board_ref():
    res = lint.lint_sheet(_SHEET, circuit=_circuit(), contract=_CONTRACT,
                          ref_map={"R9": "R9009", "U1": "U1", "C1": "C1",
                                   "TP1": "TP1"})
    (ref, bref, value, nets), = res.ungated
    assert (ref, bref, value) == ("R9", "R9009", "10k")
    assert nets == "+3V3, SENSE"
    text = "\n".join(res.lines())
    assert "UNGATED R9" in text and "R9009" in text and "+3V3, SENSE" in text
    assert "FREE    TP1" in text and "test point" in text


def test_free_channel_self_policing_notes():
    bad = {
        "structures": _CONTRACT["structures"],
        "free": [{"ref": "TP1", "why": ""},
                 {"ref": "C1", "why": "shadowed"},
                 {"ref": "X9", "why": "ghost"},
                 "not-a-dict"],
    }
    res = _lint(bad)
    assert res.free_used == [("TP1", "")]
    joined = "\n".join(res.notes)
    assert "missing 'why'" in joined
    assert "'C1' is already STRUCTURED" in joined
    assert "'X9' names no part" in joined
    assert "not-a-dict" in joined
    assert [row[0] for row in res.ungated] == ["R9"]


def test_no_contract_every_part_ungated():
    res = _lint(contract=None)
    assert not res.have_contract
    assert res.structured == [] and res.free_used == []
    assert [row[0] for row in res.ungated] == ["C1", "R9", "TP1", "U1"]
    assert "(no contract)" in res.lines()[0]


def test_net_list_truncates_deterministically():
    parts = {"J1": _part("J1", "conn")}
    nets = {f"N{i}": Net(f"N{i}", NetClass.SIGNAL, [PinRef("J1", str(i))])
            for i in range(9)}
    res = lint.lint_sheet(_SHEET, circuit=SimpleNamespace(parts=parts,
                                                          nets=nets),
                          contract=None, ref_map={"J1": "J1"})
    (_, _, _, shown), = res.ungated
    assert shown == "N0, N1, N2, N3, N4, N5 (+3 more)"


def test_result_ok_tracks_ungated_and_default_is_advisory():
    assert lint.ENFORCE is False
    covered = lint.CoverageLintResult(sheets=[_lint()])
    assert covered.n_ungated == 1 and not covered.ok
    full = {"structures": _CONTRACT["structures"],
            "roles": {"R9": "pullup"},
            "free": _CONTRACT["free"]}
    clean = lint.CoverageLintResult(sheets=[_lint(full)])
    assert clean.n_ungated == 0 and clean.ok
    assert "advisory" in covered.summary_line()


def test_structured_traversal_covers_typed_fields_and_roles():
    c = {"roles": {"RL": "x"},
         "structures": [
             {"type": "sw_node", "ic": "U7", "inductor": "L1", "sw_pin": "10",
              "max_pad_to_pin_mm": 2.0, "basis": "b"},
             {"type": "ldo_stage", "ic": "U8", "cin": "C8", "cout": "C9",
              "cin_pin": "1", "cout_pin": "5", "max_pad_to_pin_mm": 2.0,
              "basis": "b"},
             {"type": "same_side", "ics": ["U7", "U8"], "basis": "b"},
             {"type": "proximity", "anchor": "U9", "members": ["C10"],
              "min_from": [{"part": "L1", "min_mm": 3.0}], "max_mm": 2.0,
              "basis": "b"},
         ]}
    assert lint.structured_lib_refs(c) == frozenset(
        {"RL", "U7", "L1", "U8", "C8", "C9", "U9", "C10"})


def test_real_sweep_runs_clean_and_deterministic():
    r1 = lint.lint_project()
    r2 = lint.lint_project()
    assert len(r1.sheets) == 23
    for s in r1.sheets:
        assert s.have_contract, s.sheet
        assert s.n_parts == (len(s.structured) + len(s.free_used)
                             + len(s.ungated)), s.sheet
        for _, bref, _, nets in s.ungated:
            assert bref != "?" and nets, s.sheet
    assert r1.n_parts == sum(s.n_parts for s in r1.sheets)
    assert r1.report() == r2.report()
    assert r1.summary_line().startswith("CONTRACT COVERAGE LINT (advisory): "
                                        "23 sheets,")
