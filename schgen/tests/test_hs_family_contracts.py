"""Tests for the WAVE-2 HS-FAMILY CRITICAL placement contracts.

Three high-speed subsystems were promoted to CRITICAL, datasheet-cited v2
placement contracts (the HS-family audit):

  * ``hdmi_tx``       — flow-through TPD12S016 AT the HDMI connector, TMDS pass-
                        through, supply-pin bypass; cites TI SLLSE96F + SLLA324.
  * ``camera``        — 2-lane MIPI CSI-2 D-PHY: the 100R terminations at the
                        RECEIVER/mezzanine end (clear of the FFC), ESD at the FFC;
                        cites Xilinx XAPP894.
  * ``hdmi_rx_term``  — NEW: 8x49.9R TMDS sink source-terminations + AVCC bypass
                        clustered at the mezzanine RX escape; cites Xilinx XAPP460.

Two layers, mirroring ``test_expansion_contracts.py``:

(1) STATIC per-contract checks (fast, no board build): each contract imports,
    is schema-valid, every ref it names exists in the subsystem's real netlist,
    and it carries datasheet citations. These are the mechanically-checkable
    acceptance criteria.

(2) INTEGRATION on the REAL board (built once; ``_WIRED_SHEETS`` untouched so the
    already-wired power/usb_pd/ethernet stay GREEN — the control). The HS-family
    splits by whether the scattered packer already satisfies the contract:
      * hdmi_tx / camera — RED-ON-BEFORE: their layout truth is INTRA-zone and the
        packer flings the passives to the bottom side away from the connector, so
        check_all BITES (the pilot's red-on-before discipline).
      * hdmi_rx_term — GREEN-ON-BEFORE and honestly so: an IC-less island of ten
        identical passives that the affinity packer already clusters AND seats
        flush against som_j2 (near_max edge gap ~0.8 mm). No scattered defect to
        paint red without inventing a requirement (a LAW-4 softening in reverse);
        the near_max is asserted as a regression tripwire, not a red-on-before.
    Every violation summary is PRINTED for the orchestrator.
"""

from __future__ import annotations

import pytest

from schgen.core.link import load_subsystem
from schgen.verify import placement_contract_gate as g

# the three HS-family sheets promoted/created in this wave
_HS_FAMILY = ("hdmi_tx", "camera", "hdmi_rx_term")

# refs may appear under any of these structure keys (string-valued or list-valued)
_STR_REF_KEYS = ("anchor", "ic", "inductor", "cap", "resistor", "cin", "cout")
_LIST_REF_KEYS = ("members", "caps", "ics")


def _refs_used(contract: dict) -> set[str]:
    """Every LIBRARY ref the contract names (roles + every structure + min_from)."""
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


# ---------------------------------------------------------------------------
# (1) STATIC per-contract acceptance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_contract_discovers_and_is_v2(sheet: str):
    """The contract imports via the two-root registry and is a CRITICAL v2 (not a
    lightweight tier)."""
    c = g.discover_contract(sheet)
    assert c is not None, f"{sheet}: contract not discovered"
    assert c["contract"] == "placement/v2", (
        f"{sheet}: expected CRITICAL placement/v2, got {c['contract']!r}")
    assert c["sheet"] == sheet
    assert c.get("tier") != "lightweight", (
        f"{sheet}: still tagged lightweight — must be promoted to CRITICAL")


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_contract_has_citations(sheet: str):
    """A CRITICAL contract MUST carry >=1 datasheet/standard citation (LAW 7)."""
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    cites = c.get("citations", [])
    assert cites, f"{sheet}: CRITICAL contract has no citations"
    assert all(isinstance(x, str) and x for x in cites), cites


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_every_ref_exists_in_the_netlist(sheet: str):
    """Every ref the contract names is a REAL part in the subsystem's netlist —
    the roles are derived from the actual netlist, not invented."""
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    real = set(load_subsystem(sheet).circuit.parts)
    missing = sorted(r for r in _refs_used(c) if r not in real)
    assert not missing, f"{sheet}: contract names non-existent refs {missing}"


@pytest.mark.parametrize("sheet", _HS_FAMILY)
def test_every_threshold_carries_a_basis(sheet: str):
    """Every structure and every external near_max term carries a ``basis`` string
    (a citation or ``judgment:<value>``) — auditable, LAW 4 / LAW 7."""
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
    """Every structure type the contract declares is one the gate implements — a
    type with no gate branch would fail-loud on the real board (a false-red)."""
    c = g.discover_contract(sheet)
    assert c is not None, sheet
    known = {"hot_loop", "bulk_in", "bulk_out", "sw_node", "fb_cluster", "boot",
             "vcc_cap", "bias_cap", "rt_r", "ldo_stage", "proximity", "same_side"}
    for st in c["structures"]:
        assert st["type"] in known, (
            f"{sheet}: unimplemented structure type {st['type']!r}")


def test_hs_family_sheets_are_wired():
    """Full-wire world (platform-rework): every HS-family sheet is engine-WIRED
    via the project spec, so its contract gates the build. The historical
    red-on-before proof lives in the hermetic defect corpus now."""
    for sheet in _HS_FAMILY:
        assert sheet in g._WIRED_SHEETS, (
            f"{sheet} lost its wiring — project.json wired_sheets regressed")


# ---------------------------------------------------------------------------
# (2) INTEGRATION on the real board — red-on-before where the packer scatters,
#     green-on-before (honestly) where it already seats the parts
# ---------------------------------------------------------------------------
# No template is wired for any HS-family sheet (``_WIRED_SHEETS`` is untouched), so
# the already-wired sheets (power/usb_pd/ethernet) stay GREEN — the control.
#
# The HS-family splits by whether the SCATTERED value-sorted packer already
# satisfies the contract:
#   * hdmi_tx / camera — RED-ON-BEFORE. Their layout truth is INTRA-zone (companion
#     AT the connector + supply bypass tight to its pins; ESD at the FFC + the D-PHY
#     terms clear of it), and the packer flings those passives to the bottom side
#     far from their anchors, so check_all BITES. This is the pilot's red-on-before
#     discipline: the gate fires before the template lands.
#   * hdmi_rx_term — GREEN-ON-BEFORE, and honestly so. It is an IC-LESS termination
#     island of ten identical-value passives; the packer already (a) clusters them
#     on one side (intra-zone same_side + proximity satisfied) and (b) net-affinity-
#     pulls the island flush against som_j2 (measured near_max edge gap ~0.8 mm <=
#     the 10 mm cap). Its contract is authored, cited, and refs-resolve, but there
#     is NO defect to paint red. Forcing a red would mean inventing a requirement
#     the board does not violate — a LAW-4 softening in reverse. Recorded as a
#     FACT: the affinity packer seats this island correctly; the contract stands as
#     the guard that keeps it there once templates start moving parts.
#
# The near_max is still ASSERTED (it is checked and currently passes) so a future
# regression that pulls the island off the escape is caught.

from schgen.verify import placement_flow_gate as fgate  # noqa: E402

_GREEN_WIRED = ("power", "usb_pd", "ethernet")
_INTRA_RED = ("hdmi_tx", "camera")     # red via check_all (intra-zone)


@pytest.fixture(scope="module")
def _real_model():
    """Build the REAL board model ONCE (~60-120 s)."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


def test_check_all_discovers_the_hs_family(_real_model):
    """``check_all`` discovers all three HS-family contracts on the real board via
    the two-root registry (hdmi_tx/camera in ``subsystems/``, hdmi_rx_term in
    ``carrier/subsystems/``)."""
    results = g.check_all(_real_model)
    for sheet in _HS_FAMILY:
        assert sheet in results, (
            f"{sheet} not discovered by check_all (got {sorted(results)})")


def test_wired_sheets_stay_green(_real_model):
    """CONTROL: the already-wired sheets stay GREEN — proving the intra-zone
    failures below are REAL red-on-before, not a broken build."""
    for sheet in _GREEN_WIRED:
        res = g.check(_real_model, sheet)
        assert res.missing_refs == [], res.summary()
        assert res.ok is True, (
            f"{sheet} regressed — red-on-before needs the wired sheets green:\n"
            + res.summary())


def test_intra_zone_contracts_hold_on_board(_real_model):
    """Full-wire world: hdmi_tx + camera solve through the stage-template
    placer and their intra-zone contracts HOLD on the emitted board (the
    red-on-before scatter these once proved is now a defect-corpus case)."""
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
    """hdmi_rx_term is IC-less and the affinity packer already seats its island at
    the mezzanine escape, so it is HONESTLY green-on-before (see the module note).
    We still assert its contract binds to real board refs (no missing_refs) and
    that its near_max som_j2 term is CHECKED — so a future regression that pulls the
    island off the escape is caught. Both verdicts are PRINTED."""
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
