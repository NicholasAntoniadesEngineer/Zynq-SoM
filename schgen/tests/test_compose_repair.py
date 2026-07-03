"""T1 P4 — the compose repair driver (schgen/generate/compose_repair.py).

Hermetic red tests: every banded-acceptance clause has a violating
before/after ledger pair that is REJECTED with a named reason; the candidate
catalog is deterministic, never proposes an unratified intent edit, and
reports edge-subject triggers as intent-gated (the D9 case). Board-scale
dry-run is env-gated (``SCHGEN_BOARD_TESTS=1``)."""

from __future__ import annotations

import os

import pytest

from schgen.generate import compose_repair as cr

_BOARD = os.environ.get("SCHGEN_BOARD_TESTS") == "1"


# ---------------------------------------------------------------------------
# synthetic ledgers
# ---------------------------------------------------------------------------

def _ledger(area=25670.0, terms=None, contract=None, flow_ok=True,
            law5_ok=True) -> dict:
    return {
        "board": {"w": 170.0, "h": 151.0, "area_mm2": area},
        "flow_gate": {"ok": flow_ok},
        "law5": {"ok": law5_ok, "slack_pct": 14.5},
        "terms": terms or [],
        "contract_violations": contract or {},
        "repair_triggers": [],
    }


def _term(kind, subj, tgt, margin, ok, enforced=True):
    return {"kind": kind, "subject": subj, "target": tgt,
            "measured": 0.0, "bound": 0.0, "margin": margin, "ok": ok,
            "enforced": enforced}


# ---------------------------------------------------------------------------
# banded_accept — every clause rejects
# ---------------------------------------------------------------------------

def test_accept_identical_ledgers():
    b = _ledger(terms=[_term("flow_hop", "a", "b", 20.0, True)])
    ok, reasons = cr.banded_accept(b, b)
    assert ok, reasons


def test_reject_gate_fail():
    b = _ledger()
    a = _ledger(flow_ok=False)
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("flow gate" in r for r in reasons)
    a2 = _ledger(law5_ok=False)
    ok2, r2 = cr.banded_accept(b, a2)
    assert not ok2 and any("LAW-5" in r for r in r2)


def test_reject_area_growth_and_intent_escalation_path():
    b = _ledger(area=25670.0)
    a = _ledger(area=25800.0)
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("area grew" in r for r in reasons)
    # the IM5 escalation path: an INTENT edit may defer the area verdict
    ok2, _ = cr.banded_accept(b, a, allow_area_growth=True)
    assert ok2


def test_reject_term_leaving_green():
    b = _ledger(terms=[_term("near_max", "x", "y", 5.0, True)])
    a = _ledger(terms=[_term("near_max", "x", "y", -1.0, False)])
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("left GREEN" in r for r in reasons)


def test_reject_fragile_margin_loss():
    """A below-floor (FRAGILE) enforced term must never lose margin, even
    while staying green."""
    b = _ledger(terms=[_term("flow_hop", "a", "b",
                             cr.FLOOR_FLOW_MM - 1.0, True)])
    a = _ledger(terms=[_term("flow_hop", "a", "b",
                             cr.FLOOR_FLOW_MM - 2.0, True)])
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("FRAGILE" in r for r in reasons)


def test_reject_nontarget_red_deepening():
    """IM3: a RED term that is not the repair target must never lose margin."""
    b = _ledger(terms=[_term("near_max", "m", "n", -48.0, False,
                             enforced=False)])
    a = _ledger(terms=[_term("near_max", "m", "n", -50.0, False,
                             enforced=False)])
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("non-target RED" in r for r in reasons)
    # as the TARGET it must IMPROVE — equal margin is a rejection too
    ok2, r2 = cr.banded_accept(b, a, target_keys={("near_max", "m", "n")})
    assert not ok2 and any("target" in r for r in r2)
    a3 = _ledger(terms=[_term("near_max", "m", "n", -40.0, False,
                              enforced=False)])
    ok3, _ = cr.banded_accept(b, a3, target_keys={("near_max", "m", "n")})
    assert ok3


def test_reject_contract_count_worsening():
    b = _ledger(contract={"ethernet": 23})
    a = _ledger(contract={"ethernet": 25})
    ok, reasons = cr.banded_accept(b, a)
    assert not ok and any("ethernet" in r for r in reasons)


# ---------------------------------------------------------------------------
# SpecEdits
# ---------------------------------------------------------------------------

def _raw_spec() -> dict:
    return {
        "outline": "auto",
        "edges": {"N": ["pd_input"], "E": ["motor_sense"],
                  "W": ["motor_pwm"]},
        "interior": {
            "usb_pd": {"near": "pd_input",
                       "pull": {"to": "pd_input", "weight": 60.0,
                                "face": "inboard", "exclusive": True,
                                "basis": "b"}},
            "ethernet": {"near": "rj45_connector"},
        },
    }


def test_add_pull_refuses_second_pull():
    with pytest.raises(ValueError, match="one pull per block"):
        cr.AddPull(block="usb_pd", to="pd_input", weight=10.0,
                   basis="x").apply(_raw_spec())


def test_move_edge_block_moves_and_validates():
    out = cr.MoveEdgeBlock(name="motor_sense", from_edge="E",
                           to_edge="W").apply(_raw_spec())
    assert "motor_sense" not in out["edges"]["E"]
    assert out["edges"]["W"][-1] == "motor_sense"
    with pytest.raises(ValueError, match="not on edge"):
        cr.MoveEdgeBlock(name="motor_sense", from_edge="N",
                         to_edge="W").apply(_raw_spec())


def test_composite_is_intent_iff_a_member_is():
    move = cr.MoveEdgeBlock(name="motor_sense", from_edge="E", to_edge="W")
    pull = cr.AddPull(block="ethernet", to="pd_input", weight=5.0, basis="x")
    assert cr.CompositeEdit(edits=(move, pull)).intent is True
    assert cr.CompositeEdit(edits=(pull,)).intent is False
    assert move.intent is True and pull.intent is False


# ---------------------------------------------------------------------------
# propose — deterministic, intent-gated
# ---------------------------------------------------------------------------

def _trigger_ledger() -> dict:
    return _ledger(terms=[
        # advisory RED whose subject is an EDGE block (the D9 shape)
        _term("near_max", "motor_sense", "motor_pwm", -48.0, False,
              enforced=False),
        # advisory RED whose subject is an interior near-anchored block
        _term("near_max", "ethernet", "rj45_connector", -3.0, False,
              enforced=False),
    ])


def test_propose_gates_edge_subject_without_ratification():
    led = _trigger_ledger()
    cands = cr.propose(led, _raw_spec(), allow_intent=[])
    assert not any(isinstance(c, cr.MoveEdgeBlock) for c in cands), (
        "an edge move must NEVER be proposed unratified")
    assert any("motor_sense" in g for g in led["intent_gated"])


def test_propose_offers_ratified_move_and_composite():
    led = _trigger_ledger()
    moves = cr._parse_allow_intent(["motor_sense:E->W"])
    cands = cr.propose(led, _raw_spec(), allow_intent=moves)
    assert any(isinstance(c, cr.MoveEdgeBlock) and c.name == "motor_sense"
               for c in cands)


def test_propose_interior_near_target_gets_exclusive_ladder():
    """ethernet is near-anchored at rj45_connector; rj45 is NOT on an edge
    list in this synthetic spec, so the pulls must be non-exclusive; put rj45
    on an edge and the seat (exclusive+inboard) ladder appears."""
    led = _trigger_ledger()
    cands = cr.propose(led, _raw_spec(), allow_intent=[])
    eth = [c for c in cands if isinstance(c, cr.AddPull)
           and c.block == "ethernet"]
    assert eth and all(not c.exclusive for c in eth)
    spec2 = _raw_spec()
    spec2["edges"]["E"] = ["motor_sense", "rj45_connector"]
    led2 = _trigger_ledger()
    cands2 = cr.propose(led2, spec2, allow_intent=[])
    eth2 = [c for c in cands2 if isinstance(c, cr.AddPull)
            and c.block == "ethernet"]
    assert eth2 and all(c.exclusive and c.face == "inboard" for c in eth2), (
        "near-anchored block at an edge-listed target must be offered the "
        "SEAT (exclusive inboard) ladder — the ethernet-wave spec diff")


def test_propose_existing_pull_gets_weight_ladder_above_current():
    led = _ledger(terms=[
        _term("near_max", "usb_pd", "pd_input", 1.0, True, enforced=True)])
    # enforced + below near_max floor (2.0) -> FRAGILE trigger
    cands = cr.propose(led, _raw_spec(), allow_intent=[])
    ups = [c for c in cands if isinstance(c, cr.SetPullWeight)]
    assert not ups, "60.0 is already the ladder top — nothing above"
    spec2 = _raw_spec()
    spec2["interior"]["usb_pd"]["pull"]["weight"] = 10.0
    cands2 = cr.propose(led, spec2, allow_intent=[])
    ups2 = [c for c in cands2 if isinstance(c, cr.SetPullWeight)]
    assert ups2 and all(c.weight > 10.0 for c in ups2)


def test_propose_is_deterministic():
    a = [c.describe() for c in
         cr.propose(_trigger_ledger(), _raw_spec(), allow_intent=[])]
    b = [c.describe() for c in
         cr.propose(_trigger_ledger(), _raw_spec(), allow_intent=[])]
    assert a == b


def test_allow_intent_parse_rejects_garbage():
    with pytest.raises(ValueError, match="NAME:FROM->TO"):
        cr._parse_allow_intent(["motor_sense=E,W"])


# ---------------------------------------------------------------------------
# board-scale dry-run (env-gated)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1")
def test_dry_run_on_the_carrier_proposes_no_unratified_intent(capsys):
    """The carrier's only trigger today is the motor advisory RED; its subject
    is an edge block, so a dry-run proposes ZERO unratified edits and reports
    D9 as intent-gated."""
    rc = cr.repair(dry_run=True, allow_intent=[])
    out = capsys.readouterr().out
    assert rc == 0
    assert "INTENT-GATED" in out and "motor_sense" in out
    assert "applying" not in out
