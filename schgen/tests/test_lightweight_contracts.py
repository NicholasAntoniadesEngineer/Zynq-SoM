from __future__ import annotations

import pytest

from schgen.core.link import load_subsystem
from schgen.verify import placement_contract_gate as g

_LIGHTWEIGHT = (
    "lcd", "microsd", "uart_bridge", "usb_jtag",
    "usbc_otg", "pd_input", "pmod",
)

_ALLOWED_TYPES = {"proximity", "same_side"}


def _structure_refs(st: dict) -> set[str]:
    refs: set[str] = set()
    if st.get("anchor"):
        refs.add(st["anchor"])
    refs.update(st.get("members", []))
    refs.update(st.get("ics", []))
    for mf in st.get("min_from", []):
        if mf.get("part"):
            refs.add(mf["part"])
    return refs


@pytest.mark.parametrize("sheet", _LIGHTWEIGHT)
def test_contract_imports_and_schema_is_lightweight(sheet):
    c = g.discover_contract(sheet)
    assert c is not None, f"{sheet}: no placement_contract.py discovered"
    assert c.get("sheet") == sheet
    assert c.get("subsystem") == sheet
    assert c.get("tier") == "lightweight", c.get("tier")
    ext = c.get("external")
    if ext is not None:
        assert set(ext) <= {"near_max"}, (
            f"{sheet}: lightweight external carries only near_max "
            f"seat-pulls (audit wave: uart_bridge), got {sorted(ext)}")
    structures = c.get("structures", [])
    assert structures, f"{sheet}: contract has no structures"
    for st in structures:
        typ = st.get("type")
        assert typ in _ALLOWED_TYPES, (
            f"{sheet}: structure type {typ!r} is not lightweight-tier")
        basis = st.get("basis")
        assert isinstance(basis, str) and basis.strip(), (
            f"{sheet}: structure {typ} missing its basis string")
        assert "judgment" in basis, (
            f"{sheet}: lightweight basis must record its judgment: {basis}")
        if typ == "proximity":
            assert st.get("anchor"), f"{sheet}: proximity without an anchor"
            members = st.get("members")
            assert members and all(isinstance(m, str) for m in members), (
                f"{sheet}: proximity without members")
            assert float(st["max_mm"]) > 0.0
        else:
            assert st.get("ics"), f"{sheet}: same_side without ics"


@pytest.mark.parametrize("sheet", _LIGHTWEIGHT)
def test_contract_refs_and_pins_exist_in_the_netlist(sheet):
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    parts = load_subsystem(sheet).circuit.parts
    for st in c["structures"]:
        for ref in sorted(_structure_refs(st)):
            assert ref in parts, (
                f"{sheet}: contract names {ref!r} but the netlist has no "
                f"such part (has {sorted(parts)})")
        pins = st.get("anchor_pins")
        if pins:
            anchor = parts[st["anchor"]]
            assert anchor.pin_numbers, (
                f"{sheet}: anchor {st['anchor']} has no dossier pin table "
                f"to verify anchor_pins against")
            for p in pins:
                assert p in anchor.pin_numbers, (
                    f"{sheet}: anchor {st['anchor']} has no pin {p!r} "
                    f"(has {sorted(anchor.pin_numbers)})")
    for ref in c.get("roles", {}):
        assert ref in parts, f"{sheet}: roles names unknown ref {ref!r}"


def test_usb_jtag_carries_the_crystal_structure():
    c = g.discover_contract("usb_jtag")
    assert c is not None
    xtal = [st for st in c["structures"]
            if st.get("type") == "proximity" and st.get("members") == ["Y1"]]
    assert len(xtal) == 1, "usb_jtag: expected exactly one Y1 structure"
    st = xtal[0]
    assert st["anchor"] == "U1"
    assert sorted(st["anchor_pins"]) == ["19", "20"]
    assert float(st["max_mm"]) == 5.0
    assert "crystal" in st["basis"]


def test_lightweight_sheets_are_wired():
    missing = set(_LIGHTWEIGHT) - set(g._WIRED_SHEETS)
    assert not missing, f"lightweight sheet lost wiring: {sorted(missing)}"
    for sheet in _LIGHTWEIGHT:
        assert g.load_contract(sheet) is not None, (
            f"{sheet}: engine-facing load_contract must resolve (wired)")


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_check_all_discovers_every_lightweight_contract(_real_model):
    results = g.check_all(_real_model)
    for sheet in _LIGHTWEIGHT:
        assert sheet in results, (
            f"{sheet} contract not discovered by check_all "
            f"(got {sorted(results)})")


def test_wired_sheets_stay_green_on_the_real_board(_real_model):
    for sheet in sorted(g._WIRED_SHEETS):
        res = g.check(_real_model, sheet)
        print("\n" + res.summary())
        assert res.missing_refs == [], res.summary()
        assert res.ok is True, (
            f"{sheet} regressed — lightweight contracts must not perturb the "
            f"wired sheets:\n{res.summary()}")


def test_lightweight_contracts_run_on_the_real_board(_real_model):
    results = g.check_all(_real_model)
    print("\n=== LIGHTWEIGHT TIER (check_all) — red expected, not asserted ===")
    for sheet in _LIGHTWEIGHT:
        res = results[sheet]
        n_struct = len(g.discover_contract(sheet)["structures"])
        print(f"\n--- {sheet}: {len(res.violations)} violation(s), "
              f"{res.checked} structure(s) ---")
        print(res.summary())
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], (
            f"{sheet}: contract refs did not map to board refs: "
            f"{res.missing_refs}")
        assert res.checked == n_struct, (
            f"{sheet}: gate examined {res.checked} of {n_struct} structures")
        assert res.unknown_fail == 0, (
            f"{sheet}: gate hit an unknown structure type:\n{res.summary()}")
