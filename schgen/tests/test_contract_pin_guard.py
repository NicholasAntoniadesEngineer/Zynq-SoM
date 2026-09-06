from __future__ import annotations

import copy
from pathlib import Path

import pytest

from schgen.verify import placement_contract_gate as g

_REPO = Path(__file__).resolve().parents[2]


def _contract_sheets() -> list[str]:
    return sorted(p.parent.name for root in
                  (_REPO / "subsystems", _REPO / "carrier" / "subsystems")
                  for p in root.glob("*/placement_contract.json"))


def test_every_authored_contract_passes_pin_validation():
    sheets = _contract_sheets()
    assert len(sheets) == 23, sheets
    for sheet in sheets:
        contract = g.discover_contract(sheet)
        assert contract is not None, sheet
        g.validate_contract_pins(sheet, contract)


def test_bogus_anchor_pin_raises_loud_error():
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
    bad = copy.deepcopy(g.discover_contract("power"))
    st = next(s for s in bad["structures"] if s.get("type") == "sw_node")
    st["sw_pin"] = "SW"
    with pytest.raises(g.ContractPinError, match=r"sw_node.*sw_pin.*'SW'"):
        g.validate_contract_pins("power", bad)


def test_bogus_min_from_pin_raises():
    bad = copy.deepcopy(g.discover_contract("camera"))
    st = next(s for s in bad["structures"] if s.get("min_from"))
    st["min_from"][0]["pin"] = "VBUS"
    with pytest.raises(g.ContractPinError, match=r"min_from\.pin.*'VBUS'"):
        g.validate_contract_pins("camera", bad)


def test_unresolvable_part_stays_soft():
    contract = {"structures": [
        {"type": "proximity", "anchor": "U999", "anchor_pins": ["NOPE"],
         "members": ["C1"], "max_mm": 2.0, "basis": "judgment:test"}]}
    g.validate_contract_pins("usb_pd", contract)


def test_chokepoint_is_wired_into_discover(monkeypatch):
    bad = copy.deepcopy(g.discover_contract("pd_input"))
    next(s for s in bad["structures"]
         if s.get("type") == "proximity")["anchor_pins"] = ["ILIM"]
    monkeypatch.setattr(g, "read_contract_file", lambda _path: bad)
    monkeypatch.setattr(g, "_PIN_VALIDATED", set())
    with pytest.raises(g.ContractPinError, match=r"'ILIM'"):
        g.discover_contract("pd_input")
    assert "pd_input" not in g._PIN_VALIDATED
