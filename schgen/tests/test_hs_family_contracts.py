from __future__ import annotations

import pytest

from schgen.core.link import load_subsystem
from schgen.verify import placement_contract_gate as g

_HS_FAMILY = ("hdmi_tx", "camera", "hdmi_rx_term")

_STR_REF_KEYS = ("anchor", "ic", "inductor", "cap", "resistor", "cin", "cout")
_LIST_REF_KEYS = ("members", "caps", "ics")


def _refs_used(contract: dict) -> set[str]:
    refs: set[str] = set(contract.get("roles", {}))
    for st in contract.get("structures", []):
        for k in _STR_REF_KEYS:
            v = st.get(k)
            if isinstance(v, str):
                refs.add(v)
        for k in _LIST_REF_KEYS:
            refs.update(st.get(k, []))
        for mf in st.get("min_from", []):
            if mf.get("part"):
                refs.add(mf["part"])
    return refs


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_contract_discovers_and_is_v2(sheet: str):
    c = g.discover_contract(sheet)
    assert c is not None, f"{sheet}: contract not discovered"
    assert c["contract"] == "placement/v2", (
        f"{sheet}: expected CRITICAL placement/v2, got {c['contract']!r}")
    assert c["sheet"] == sheet
    assert c.get("tier") != "lightweight", (
        f"{sheet}: still tagged lightweight — must be promoted to CRITICAL")


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_contract_has_citations(sheet: str):
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    cites = c.get("citations", [])
    assert cites, f"{sheet}: CRITICAL contract has no citations"
    assert all(isinstance(x, str) and x for x in cites), cites


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_every_ref_exists_in_the_netlist(sheet: str):
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    real = set(load_subsystem(sheet).circuit.parts)
    missing = sorted(r for r in _refs_used(c) if r not in real)
    assert not missing, f"{sheet}: contract names non-existent refs {missing}"


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_every_threshold_carries_a_basis(sheet: str):
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    for st in c["structures"]:
        assert st.get("basis"), (
            f"{sheet}: structure {st.get('type')!r} has no basis")
    for nm in c.get("external", {}).get("near_max", []):
        assert nm.get("basis"), f"{sheet}: a near_max term has no basis"
    for fr in c.get("external", {}).get("far", []):
        assert fr.get("basis"), f"{sheet}: a far term has no basis"


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_no_unknown_structure_type(sheet: str):
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    known = {"hot_loop", "bulk_in", "bulk_out", "sw_node", "fb_cluster", "boot",
             "vcc_cap", "bias_cap", "rt_r", "ldo_stage", "proximity", "same_side"}
    for st in c["structures"]:
        assert st["type"] in known, (
            f"{sheet}: unimplemented structure type {st['type']!r}")


def test_hs_family_sheets_are_wired():
    for sheet in _HS_FAMILY:
        assert sheet in g._WIRED_SHEETS, (
            f"{sheet} lost its wiring — project.json wired_sheets regressed")


from schgen.verify import placement_flow_gate as fgate  # noqa: E402

_GREEN_WIRED = ("power", "usb_pd", "ethernet")
_INTRA_RED = ("hdmi_tx", "camera")


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_check_all_discovers_the_hs_family(_real_model):
    results = g.check_all(_real_model)
    for sheet in _HS_FAMILY:
        assert sheet in results, (
            f"{sheet} not discovered by check_all (got {sorted(results)})")


def test_wired_sheets_stay_green(_real_model):
    for sheet in _GREEN_WIRED:
        res = g.check(_real_model, sheet)
        assert res.missing_refs == [], res.summary()
        assert res.ok is True, (
            f"{sheet} regressed — red-on-before needs the wired sheets green:\n"
            + res.summary())


def test_intra_zone_contracts_hold_on_board(_real_model):
    results = g.check_all(_real_model)
    for sheet in _INTRA_RED:
        res = results[sheet]
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], (
            f"{sheet}: contract refs did not map to board refs: "
            f"{res.missing_refs}")
        assert res.ok is True, (
            f"{sheet} regressed — its wired contract no longer holds:\n"
            f"{res.summary()}")


def test_hdmi_rx_term_refs_resolve_and_near_max_is_checked(_real_model):
    intra = g.check(_real_model, "hdmi_rx_term",
                    contract=g.discover_contract("hdmi_rx_term"))
    print("\n=== hdmi_rx_term (intra-zone) ===")
    print(intra.summary())
    assert intra.missing_refs == [], (
        "hdmi_rx_term contract refs did not map to board refs: "
        f"{intra.missing_refs}")

    c = g.discover_contract("hdmi_rx_term")
    ref_map = g._board_refs_by_sheet("hdmi_rx_term")
    flow = fgate.check(_real_model, contracts={"hdmi_rx_term": c},
                       ref_maps={"hdmi_rx_term": ref_map})
    print("\n=== hdmi_rx_term (composition, flow gate) ===")
    print(flow.summary())
    assert flow.near_max_checked >= 1, (
        "hdmi_rx_term near_max term was not checked:\n" + flow.summary())
    assert not any("UNRESOLVED" in v for v in flow.violations), (
        "hdmi_rx_term near_max target som_j2 did not resolve:\n" + flow.summary())
