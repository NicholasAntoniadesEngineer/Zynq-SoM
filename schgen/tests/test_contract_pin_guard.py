"""Tests for the contract PIN-NAME chokepoint
(``placement_contract_gate.validate_contract_pins`` + its ``discover_contract``
wiring).

The measured defect class (2026-07-28): a placement contract authored with
symbol pin NAMES instead of footprint pad ids ("ILIM" for TPS26631 pad "11",
"+" for XT60 pad "2", "VDD" for TF-01A pad "4") crashed the zone solver deep
inside candidate generation with a bare ``ValueError: min() iterable argument
is empty`` (``stage_templates._pin_box`` on an empty pad-box selection). The
chokepoint turns that into a load-time :class:`ContractPinError` naming the
sheet, structure index/type, part, the missing pin and the sorted available
pad ids — while a part that does not resolve at all keeps its existing SOFT
unresolved handling. The 23-contract sweep is the standing regression net for
future contract authoring. Hermetic: no board build, no kicad-cli.
"""

from __future__ import annotations

import copy
import importlib
from pathlib import Path

import pytest

from schgen.verify import placement_contract_gate as g

_REPO = Path(__file__).resolve().parents[2]


def _contract_sheets() -> list[str]:
    return sorted(p.parent.name for root in
                  (_REPO / "subsystems", _REPO / "carrier" / "subsystems")
                  for p in root.glob("*/placement_contract.py"))


def test_every_authored_contract_passes_pin_validation():
    """SWEEP: all 23 authored contracts validate — every named pin (anchor_pins,
    typed fields, min_from.pin) is a real pad id of its resolved footprint. A
    future contract joins this net automatically; the pinned count catches a
    contract that silently drops out of discovery."""
    sheets = _contract_sheets()
    assert len(sheets) == 23, sheets
    for sheet in sheets:
        contract = g.discover_contract(sheet)
        assert contract is not None, sheet
        g.validate_contract_pins(sheet, contract)


def test_bogus_anchor_pin_raises_loud_error():
    """The measured bug shape: TPS26631 ILIM authored by symbol NAME. The error
    names the sheet, structure index/type, the anchor, the missing pin AND the
    sorted available pad ids (the real ILIM pad '11' among them)."""
    bad = copy.deepcopy(g.discover_contract("pd_input"))
    idx, st = next((i, s) for i, s in enumerate(bad["structures"])
                   if s.get("type") == "proximity" and s.get("anchor") == "U1")
    st["anchor_pins"] = ["ILIM"]
    with pytest.raises(g.ContractPinError) as ei:
        g.validate_contract_pins("pd_input", bad)
    msg = str(ei.value)
    assert "'pd_input'" in msg
    assert f"#{idx}" in msg and "proximity" in msg
    assert "U1" in msg and "'ILIM'" in msg and "anchor_pins" in msg
    assert "Available pads" in msg and "'11'" in msg


def test_bogus_typed_pin_field_raises():
    """Typed structure fields are guarded too: a buck sw_node whose sw_pin is a
    symbol name fails at load, before the solver's _buck_pins/_lay_buck consume
    it."""
    bad = copy.deepcopy(g.discover_contract("power"))
    st = next(s for s in bad["structures"] if s.get("type") == "sw_node")
    st["sw_pin"] = "SW"
    with pytest.raises(g.ContractPinError, match=r"sw_node.*sw_pin.*'SW'"):
        g.validate_contract_pins("power", bad)


def test_bogus_min_from_pin_raises():
    """min_from clearance pins are guarded against the part they clear FROM."""
    bad = copy.deepcopy(g.discover_contract("camera"))
    st = next(s for s in bad["structures"] if s.get("min_from"))
    st["min_from"][0]["pin"] = "VBUS"
    with pytest.raises(g.ContractPinError, match=r"min_from\.pin.*'VBUS'"):
        g.validate_contract_pins("camera", bad)


def test_unresolvable_part_stays_soft():
    """A pin on a part the sheet cannot resolve does NOT raise — soft-missing
    refs keep the gate's existing unresolved handling; only bad pin names on
    RESOLVABLE parts are load errors."""
    contract = {"structures": [
        {"type": "proximity", "anchor": "U999", "anchor_pins": ["NOPE"],
         "members": ["C1"], "max_mm": 2.0, "basis": "judgment:test"}]}
    g.validate_contract_pins("usb_pd", contract)


def test_chokepoint_is_wired_into_discover(monkeypatch):
    """discover_contract IS the chokepoint: a bad pin in the authored module
    raises at load for every consumer (gate, solver hook, floorplan compose),
    and the sheet is not memoised as validated."""
    mod = importlib.import_module("subsystems.pd_input.placement_contract")
    bad = copy.deepcopy(mod.CONTRACT)
    next(s for s in bad["structures"]
         if s.get("type") == "proximity")["anchor_pins"] = ["ILIM"]
    monkeypatch.setattr(mod, "CONTRACT", bad)
    monkeypatch.setattr(g, "_PIN_VALIDATED", set())
    with pytest.raises(g.ContractPinError, match=r"'ILIM'"):
        g.discover_contract("pd_input")
    assert "pd_input" not in g._PIN_VALIDATED
