"""Tests for the ENGINE-WAVE placement-contract EXPANSION (E1-E5).

Three layers, mirroring ``test_placement_contract_gate`` / ``test_placement_flow_gate``:

(1) SYNTHETIC UNIT TESTS for the GENERIC ``proximity`` structure type (E4') and
    the composition ``near_max`` external term (E5-lite). Each builds a minimal
    PcbModel from the REAL LM61460 (and passive) footprint pads, places the
    members either COMPLIANT (baseline: gate green) or DEFECTIVE (mutant: gate
    red), and asserts the mutant is killed. A baseline precedes every mutant.
    Refs are injected via an identity ``ref_map`` so the units are hermetic + fast.

(2) FAIL-LOUD: the intra-zone gate must FAIL (violation, not skip) on any
    structure type it does not implement — a false-green guard (LAW 4).

(3) The DECISIVE RED-ON-BEFORE INTEGRATION TEST: build the REAL board model once
    and run ``check_all``; the four NEW contracts (usb_pd/ethernet/hdmi_rx/
    motor_sense) MUST currently FAIL — the scattered value-sorted packer cannot
    satisfy them (no template is wired for these sheets yet) — while ``power``
    (its template active) stays GREEN. Each contract's violation summary is
    PRINTED for the orchestrator. This is the pilot's red-on-before discipline:
    prove the gate BITES before wiring the template that makes it green.
"""

from __future__ import annotations

import pytest

from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
    resolve_mod,
)
from schgen.generate.pcb.footprint import pad_names
from schgen.verify import placement_contract_gate as g
from schgen.verify import placement_flow_gate as f

_LM = "LM61460AANRJRR:LM61460AANRJRR"
_C = "Capacitor_SMD:C_0603_1608Metric"
_R = "Resistor_SMD:R_0603_1608Metric"
_SHEET = "power"          # any name; ref_map is injected so no real sheet needed


# ---------------------------------------------------------------------------
# synthetic fixture builders (shared shape with test_placement_contract_gate)
# ---------------------------------------------------------------------------

def _inst(ref: str, fp: str, x: float, y: float, side: str = "top",
          rot: float = 0.0) -> FootprintInst:
    mod = resolve_mod(fp)
    assert mod is not None, fp
    pad_nets = {p: (i + 1, f"{ref}_{p}") for i, p in enumerate(pad_names(mod))}
    return FootprintInst(ref=ref, value="x", footprint=fp,
                         x=ORIGIN_X + x, y=ORIGIN_Y + y, rotation=rot,
                         pad_nets=pad_nets, mod_path=mod, sheet=_SHEET, side=side)


def _model(*insts: FootprintInst) -> PcbModel:
    return PcbModel(
        board_w=80.0, board_h=60.0, insts=list(insts),
        net_numbers={"": 0}, netclass_of={}, classes={},
        placed=len(insts), deferred=[], n_top=len(insts), n_bottom=0,
        two_side=True)


def _pin_xy(inst: FootprintInst, pin: str) -> tuple[float, float]:
    b = g._inst_pad_boxes(inst)[pin]
    return ((b[0] + b[2]) / 2 - ORIGIN_X, (b[1] + b[3]) / 2 - ORIGIN_Y)


_ICX, _ICY = 40.0, 30.0


def _ic(ref: str = "U1", x: float = _ICX, y: float = _ICY) -> FootprintInst:
    return _inst(ref, _LM, x, y)


def _at_pin(ref: str, ic: FootprintInst, pin: str, dxy: tuple[float, float],
            side: str = "top", fp: str = _C) -> FootprintInst:
    px, py = _pin_xy(ic, pin)
    return _inst(ref, fp, px + dxy[0], py + dxy[1], side=side)


def _idmap(*refs: str) -> dict[str, str]:
    return {r: r for r in refs}


# ---------------------------------------------------------------------------
# (1a) PROXIMITY — member <= max_mm of the anchor pins, same side (E4')
# ---------------------------------------------------------------------------

def _prox_contract(max_mm=2.0, same_side=True, anchor_pins=("3",),
                   members=("C1",), min_from=None) -> dict:
    st = {"type": "proximity", "anchor": "U1", "members": list(members),
          "max_mm": max_mm, "same_side": same_side, "basis": "b"}
    if anchor_pins is not None:
        st["anchor_pins"] = list(anchor_pins)
    if min_from is not None:
        st["min_from"] = min_from
    return {"structures": [st]}


def test_proximity_baseline_passes():
    """BASELINE: a member ~0.4 mm off the anchor pin, same side -> green."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))       # VDD-ish pin 3
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


def test_proximity_far_mutant_is_killed():
    """MUTANT: the member is shoved 8 mm off the anchor pin -> 1 proximity fail."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 8.0))
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("to U1 pins 3" in v for v in res.violations), res.summary()


def test_proximity_wrong_side_mutant_is_killed():
    """MUTANT (the before-board defect class): tight to the pin but on the BOTTOM
    while the anchor is TOP -> the same_side clause fires."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4), side="bottom")
    res = g.check(_model(ic, c1), _SHEET, _prox_contract(),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("same_side" in v for v in res.violations), res.summary()


def test_proximity_universal_partial_mutant_is_killed():
    """MUTANT: ONE member is tight, the OTHER is far — proves the check is
    UNIVERSAL (every member in-bound), so a stray one cannot hide."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))       # tight
    c2 = _at_pin("C2", ic, "3", (0.0, 9.0))       # far
    res = g.check(_model(ic, c1, c2), _SHEET,
                  _prox_contract(members=("C1", "C2")),
                  ref_map=_idmap("U1", "C1", "C2"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()


def test_proximity_anchor_pins_absent_uses_any_pad():
    """anchor_pins ABSENT -> distance measured to ANY pad of the anchor. A member
    near the IC body (but not near pin 3) still passes."""
    ic = _ic()
    # place the cap ~0.4 mm off pin 10 (SW) — far from pin 3 but touching the IC
    c1 = _at_pin("C1", ic, "10", (0.4, 0.0))
    res = g.check(_model(ic, c1), _SHEET,
                  _prox_contract(max_mm=1.0, anchor_pins=None),
                  ref_map=_idmap("U1", "C1"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


def test_proximity_min_from_clearance_mutant_is_killed():
    """min_from: a member near the anchor but TOO CLOSE to another named part
    (pin) fails the clearance clause."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))       # near the anchor pin (ok)
    # a foreign part right next to C1 (< 5 mm) trips min_from
    fx, fy = _pin_xy(ic, "3")
    d5 = _inst("D5", _C, fx + 0.0, fy + 1.2)      # ~1 mm from C1
    contract = _prox_contract(
        min_from=[{"part": "D5", "min_mm": 5.0}])
    res = g.check(_model(ic, c1, d5), _SHEET, contract,
                  ref_map=_idmap("U1", "C1", "D5"))
    assert res.ok is False, res.summary()
    assert res.proximity_fail == 1, res.summary()
    assert any("too close" in v and "from D5" in v
               for v in res.violations), res.summary()


def test_proximity_min_from_clearance_baseline_passes():
    """min_from BASELINE: the same layout with the foreign part far away -> green."""
    ic = _ic()
    c1 = _at_pin("C1", ic, "3", (0.0, 0.4))
    fx, fy = _pin_xy(ic, "3")
    d5 = _inst("D5", _C, fx + 0.0, fy + 20.0)     # ~20 mm from C1 (clear)
    contract = _prox_contract(
        min_from=[{"part": "D5", "min_mm": 5.0}])
    res = g.check(_model(ic, c1, d5), _SHEET, contract,
                  ref_map=_idmap("U1", "C1", "D5"))
    assert res.ok, res.summary()
    assert res.proximity_fail == 0


# ---------------------------------------------------------------------------
# (2) FAIL-LOUD — an unimplemented structure type is a VIOLATION (E4')
# ---------------------------------------------------------------------------

def test_unknown_structure_type_fails_loud():
    """A structure type the gate has no branch for FAILS (violation, not a silent
    skip). This is the guard that a new bespoke type cannot pass vacuously."""
    ic = _ic()
    contract = {"structures": [
        {"type": "totally_made_up_type", "ic": "U1", "basis": "b"}]}
    res = g.check(_model(ic), _SHEET, contract, ref_map=_idmap("U1"))
    assert res.ok is False, res.summary()
    assert res.unknown_fail == 1, res.summary()
    assert any("UNKNOWN structure type" in v for v in res.violations), \
        res.summary()


def test_en_cluster_type_now_gone_from_power_som():
    """The old ``en_cluster`` was converted to ``proximity`` (E4' / D10); no
    contract may still carry it (it would now fail-loud). Uses ``discover_contract``
    so it reads the authored data regardless of engine wiring."""
    for sheet in ("power", "power_som", "usb_pd", "ethernet", "hdmi_rx",
                  "motor_sense"):
        c = g.discover_contract(sheet)
        assert c is not None, sheet
        types = {st["type"] for st in c["structures"]}
        assert "en_cluster" not in types, f"{sheet} still has en_cluster"


# ---------------------------------------------------------------------------
# (3a) NEAR_MAX — composition zone-centroid distance <= max_mm (E5-lite)
# ---------------------------------------------------------------------------

def _fzone(sheet: str, x: float, y: float) -> FootprintInst:
    mod = resolve_mod(_C)
    pad_nets = {p: (i + 1, f"{sheet}_{p}") for i, p in enumerate(pad_names(mod))}
    return FootprintInst(ref=f"C{sheet}", value="x", footprint=_C,
                         x=x, y=y, rotation=0.0, pad_nets=pad_nets,
                         mod_path=mod, sheet=sheet, side="top")


def _fmodel(insts, board_w=170.0, board_h=145.0) -> PcbModel:
    lst = list(insts)
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=lst,
        net_numbers={"": 0}, netclass_of={}, classes={},
        placed=len(lst), deferred=[], n_top=len(lst), n_bottom=0,
        two_side=True)


def _near_contract(other="pd_input", max_mm=15.0) -> dict:
    return {"contract": "placement/test",
            "external": {"near_max": [
                {"other": other, "max_mm": max_mm, "basis": "j"}]}}


def test_near_max_baseline_passes():
    """BASELINE: usb_pd sits 10 mm from pd_input <= the 15 mm near_max cap."""
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0), _fzone("pd_input", 48.0, 36.0)])
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok, res.summary()
    assert res.near_max_fail == 0 and res.near_max_checked == 1, res.summary()


def test_near_max_too_far_mutant_is_killed():
    """MUTANT: pd_input drifts 60 mm away — the near_max cap is blown."""
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0), _fzone("pd_input", 100.0, 30.0)])
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok is False, res.summary()
    assert res.near_max_fail == 1, res.summary()
    assert any("near_max usb_pd to pd_input" in v
               for v in res.violations), res.summary()


def test_near_max_unresolved_target_fails_strict():
    """A near_max target that resolves to NO placed zone is UNRESOLVED and FAILS
    (strict — never a silent skip, LAW 4)."""
    m = _fmodel([_fzone("usb_pd", 40.0, 30.0)])   # no pd_input placed
    res = f.check(m, contracts={"usb_pd": _near_contract()})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.near_max_fail == 1, res.summary()
    assert any("UNRESOLVED" in v for v in res.violations), res.summary()


# ---------------------------------------------------------------------------
# (3b) @som DOWNSTREAM resolution (E3) — flow/facing to the SoM core region
# ---------------------------------------------------------------------------

def test_flow_at_som_resolves_to_som_core():
    """A flow chain ending in ``@som`` resolves the hop to the SoM core centroid;
    with the SoM near power_som the hop is in budget -> green."""
    m = _fmodel([_fzone("power_mon", 40.0, 30.0),
                 _fzone("power_som", 50.0, 40.0)],
                board_w=170.0, board_h=145.0)
    m.som_core = (55.0, 40.0, 90.0, 70.0)   # centroid ~ (72.5, 55)
    c = {"contract": "placement/test",
         "external": {"flow": ["power_mon", "power_som", "@som"]}}
    res = f.check(m, contracts={"power_som": c})
    # the @som hop was examined (a number), and resolved (no unresolved token)
    assert res.flow_checked == 2, res.summary()
    assert not any("@som" in u for u in res.unresolved), res.summary()


def test_flow_at_som_unresolved_without_som_core():
    """Without a placed SoM (``som_core`` None), the ``@som`` hop is UNRESOLVED
    and fails (strict)."""
    m = _fmodel([_fzone("power_mon", 40.0, 30.0),
                 _fzone("power_som", 50.0, 40.0)])
    c = {"contract": "placement/test",
         "external": {"flow": ["power_som", "@som"]}}
    res = f.check(m, contracts={"power_som": c})
    assert res.ok is False, res.summary()
    assert res.unresolved and res.flow_fail == 1, res.summary()


def test_facing_at_som_resolves(monkeypatch):
    """FACING to ``@som``: the output-role parts must face the SoM core region.
    With the output parts on the +X half and the SoM to the +X -> dot > 0 green."""
    out = _fzone("power_som", 50.0, 30.0)
    out.ref = "COUT"
    ic = _fzone("power_som", 42.0, 30.0)
    ic.ref = "U4"
    m = _fmodel([ic, out])
    m.som_core = (60.0, 25.0, 90.0, 45.0)   # centroid ~ (75, 35), +X of the zone
    c = {"contract": "placement/test",
         "roles": {"U4": "buck_ic", "COUT": "cout_bulk"},
         "external": {"downstream": "@som", "output_roles": ["cout_bulk"]}}
    res = f.check(m, contracts={"power_som": c},
                  ref_maps={"power_som": {"U4": "U4", "COUT": "COUT"}})
    assert res.facing_checked == 1, res.summary()
    assert res.facing_fail == 0, res.summary()


# ---------------------------------------------------------------------------
# (4) DECISIVE RED-ON-BEFORE INTEGRATION — check_all on the real board
# ---------------------------------------------------------------------------
# The four NEW contracts MUST currently FAIL (the scattered value-sorted packer
# cannot satisfy them — no template is wired for these sheets yet) while ``power``
# (its template active) stays GREEN. This is the pilot's red-on-before proof:
# the gate BITES before the template lands. When the templates are wired in a
# LATER wave these assertions invert (like the intra-zone gate's wave A->B test).

_RED_ON_BEFORE = ("usb_pd", "ethernet", "hdmi_rx", "motor_sense")


@pytest.fixture(scope="module")
def _real_model():
    """Build the REAL board model ONCE (~60-120 s)."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


def test_check_all_discovers_every_registered_contract(_real_model):
    """``check_all`` discovers every registered contract present on the board —
    the pilot ``power`` + ``power_som`` + the four new sheets, all resolved via
    the two-root registry (E1)."""
    results = g.check_all(_real_model)
    for sheet in ("power", "power_som", *_RED_ON_BEFORE):
        assert sheet in results, (
            f"{sheet} contract not discovered by check_all "
            f"(got {sorted(results)})")


def test_power_stays_green_on_the_real_board(_real_model):
    """CONTROL: ``power`` (its stage template active) is GREEN — proving the new
    contracts' failures below are REAL red-on-before, not a broken build."""
    res = g.check(_real_model, "power")
    print("\n" + res.summary())
    assert res.missing_refs == [], res.summary()
    assert res.ok is True, (
        "power regressed — the red-on-before proof needs power green:\n"
        + res.summary())


def test_new_contracts_are_red_on_before(_real_model):
    """DECISIVE: every NEW contract currently FAILS on the emitted board (the
    scattered packer scatters its passives) — the gate BITES before any template
    lands. Each contract's violation summary is PRINTED for the orchestrator."""
    results = g.check_all(_real_model)
    print("\n=== RED-ON-BEFORE (check_all) — new contracts must FAIL ===")
    for sheet in _RED_ON_BEFORE:
        res = results[sheet]
        print(f"\n--- {sheet} ---")
        print(res.summary())
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], (
            f"{sheet}: contract refs did not map to board refs: "
            f"{res.missing_refs}")
        assert res.ok is False, (
            f"{sheet} is UNEXPECTEDLY green — red-on-before expects the "
            f"scattered packer to VIOLATE this contract:\n{res.summary()}")
        assert (res.proximity_fail + res.same_side_fail) >= 1, (
            f"{sheet} failed but with no proximity/same_side violation:\n"
            f"{res.summary()}")
