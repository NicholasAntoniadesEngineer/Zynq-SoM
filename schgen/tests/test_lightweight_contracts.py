"""Tests for the LIGHTWEIGHT-TIER placement contracts (Decision D6, "the rest").

Two layers, mirroring ``test_expansion_contracts``:

(1) AUTHORED-DATA VALIDITY per contract: it imports (via ``discover_contract``'s
    importlib path), carries ONLY the lightweight schema (``proximity`` /
    ``same_side`` structures, judgment ``basis`` strings, no ``external``
    composition block), and every ref/anchor-pin it names EXISTS in the
    subsystem's netlist (loaded with the same ``schgen.core.link.load_subsystem``
    the gate's ref-mapping uses).

(2) INTEGRATION on the REAL board: ``check_all`` must DISCOVER and RUN every
    lightweight contract (refs resolve to placed board footprints; structures
    are checked, never skipped) and each contract's violation count is PRINTED
    for the orchestrator. RED IS EXPECTED — the scattered value-sorted packer
    does not satisfy these contracts (no template is wired; ``_WIRED_SHEETS`` is
    untouched) — but this test asserts only that the gate RUNS them, NOT that
    they fail, while the engine-WIRED sheets (``power``) stay GREEN.
"""

from __future__ import annotations

import pytest

from schgen.core.link import load_subsystem
from schgen.verify import placement_contract_gate as g

# The lightweight-tier sheets (D6 "rest of the board"). board_qwiic is
# EXCLUDED: it exists only as a carrier-local package (carrier/subsystems/
# board_qwiic), not in the top-level subsystems/ library this wave covers.
# ``camera`` and ``hdmi_tx`` were PROMOTED out of this tier to CRITICAL, datasheet-
# cited placement/v2 contracts (the HS-family audit — they are high-speed: MIPI
# CSI-2 D-PHY and flow-through HDMI TMDS). Their v2 schema (an ``external`` block,
# citations) is covered by ``test_hs_family_contracts.py``, not this lightweight
# suite, so they are no longer asserted lightweight here.
_LIGHTWEIGHT = (
    "lcd", "microsd", "uart_bridge", "usb_jtag",
    "usbc_otg", "pd_input", "pmod",
)

_ALLOWED_TYPES = {"proximity", "same_side"}


def _structure_refs(st: dict) -> set[str]:
    """Every part ref a structure names (anchor, members, ics, min_from)."""
    refs: set[str] = set()
    if st.get("anchor"):
        refs.add(st["anchor"])
    refs.update(st.get("members", []))
    refs.update(st.get("ics", []))
    for mf in st.get("min_from", []):
        if mf.get("part"):
            refs.add(mf["part"])
    return refs


# ---------------------------------------------------------------------------
# (1) authored-data validity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sheet", _LIGHTWEIGHT)
def test_contract_imports_and_schema_is_lightweight(sheet):
    """The contract imports cleanly and carries ONLY the lightweight schema:
    proximity/same_side structures, a basis on every structure, positive
    distance bounds, and NO composition ``external`` block."""
    c = g.discover_contract(sheet)
    assert c is not None, f"{sheet}: no placement_contract.py discovered"
    assert c.get("sheet") == sheet
    assert c.get("subsystem") == sheet
    assert c.get("tier") == "lightweight", c.get("tier")
    assert "external" not in c, (
        f"{sheet}: lightweight contracts carry NO composition block")
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
        else:  # same_side
            assert st.get("ics"), f"{sheet}: same_side without ics"


@pytest.mark.parametrize("sheet", _LIGHTWEIGHT)
def test_contract_refs_and_pins_exist_in_the_netlist(sheet):
    """Every ref the contract names (structures + roles) exists in the
    subsystem netlist, and every ``anchor_pins`` entry is a real pin NUMBER of
    its anchor part (dossier pin table)."""
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
    """usb_jtag additionally gates the crystal at its IC (render-audit
    finding): Y1 within 5 mm of the CH347's XI/XO pins."""
    c = g.discover_contract("usb_jtag")
    assert c is not None
    xtal = [st for st in c["structures"]
            if st.get("type") == "proximity" and st.get("members") == ["Y1"]]
    assert len(xtal) == 1, "usb_jtag: expected exactly one Y1 structure"
    st = xtal[0]
    assert st["anchor"] == "U1"
    assert sorted(st["anchor_pins"]) == ["19", "20"]     # XI/XO
    assert float(st["max_mm"]) == 5.0
    assert "crystal" in st["basis"]


def test_lightweight_sheets_stay_unwired():
    """The lightweight tier does NOT wire the engine: ``_WIRED_SHEETS`` carries
    none of these sheets, so the contracts stay INERT to the placer/emit
    (authored data only — the red-on-before discipline)."""
    assert g._WIRED_SHEETS.isdisjoint(_LIGHTWEIGHT), (
        f"lightweight sheet unexpectedly wired: "
        f"{sorted(g._WIRED_SHEETS & set(_LIGHTWEIGHT))}")
    for sheet in _LIGHTWEIGHT:
        assert g.load_contract(sheet) is None, (
            f"{sheet}: engine-facing load_contract must stay None (unwired)")


# ---------------------------------------------------------------------------
# (2) integration — check_all on the real board (red expected, gate must RUN)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _real_model():
    """Build the REAL board model ONCE (~60-120 s)."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


def test_check_all_discovers_every_lightweight_contract(_real_model):
    """``check_all`` discovers all nine lightweight contracts on the emitted
    board (two-root registry, no engine wiring needed)."""
    results = g.check_all(_real_model)
    for sheet in _LIGHTWEIGHT:
        assert sheet in results, (
            f"{sheet} contract not discovered by check_all "
            f"(got {sorted(results)})")


def test_wired_sheets_stay_green_on_the_real_board(_real_model):
    """CONTROL: the engine-WIRED sheets (the pilot ``power``) stay GREEN — the
    lightweight authoring must not perturb the wired gate chain."""
    for sheet in sorted(g._WIRED_SHEETS):
        res = g.check(_real_model, sheet)
        print("\n" + res.summary())
        assert res.missing_refs == [], res.summary()
        assert res.ok is True, (
            f"{sheet} regressed — lightweight contracts must not perturb the "
            f"wired sheets:\n{res.summary()}")


def test_lightweight_contracts_run_on_the_real_board(_real_model):
    """The gate RUNS every lightweight contract against real geometry: refs
    resolve to placed footprints (nothing silently skipped) and every structure
    is examined. Each sheet's violation count is PRINTED — red is EXPECTED
    (no template wired), and deliberately NOT asserted."""
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
