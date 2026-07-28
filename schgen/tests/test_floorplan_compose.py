"""Tests for the T1 composition term index + exact evaluator
(schgen/generate/floorplan_compose.py) and the measurement ledger
(schgen/generate/compose_repair.py). Spec: T1_COMPOSITION_SPEC.md P2.

Layers:
(1) HERMETIC term-index tests — discovery is monkeypatched so dedupe /
    fail-loud / enforcement semantics are proven without the real contracts.
(2) REAL-registry index tests — the live contracts produce the expected term
    kinds (structural assertions only; never pins a measured scalar).
(3) The None-filter (IM2) — the advisory injection excludes contract-less
    sheets, proven hermetically against the real gate.
(4) BOARD-SCALE exactness (env-gated ``SCHGEN_BOARD_TESTS=1``, mandatory at
    every T1 phase gate): evaluator prediction == emitted-gate measurement,
    with the red-on-before halves (no-snap prediction diverges; a perturbed
    pose is caught — the mutation twin).
"""

from __future__ import annotations

import math
import os

import pytest

from schgen.generate import floorplan_compose as fc

_BOARD = os.environ.get("SCHGEN_BOARD_TESTS") == "1"


# ---------------------------------------------------------------------------
# (1) hermetic term-index semantics
# ---------------------------------------------------------------------------

def _patch_contracts(monkeypatch, contracts: dict[str, dict],
                     wired: set[str]) -> None:
    import schgen.verify.placement_contract_gate as pcg
    monkeypatch.setattr(pcg, "discover_contract",
                        lambda s: contracts.get(s))
    monkeypatch.setattr(pcg, "_WIRED_SHEETS", frozenset(wired))
    # near_intent discovery reads the real floorplan.json; irrelevant names
    # cannot collide with the synthetic sheets used here.


def test_dedupe_keeps_min_bound_and_or_enforced(monkeypatch):
    """Two declarations of the SAME near_max pair merge: keep-min-bound +
    OR-enforced (IM7)."""
    contracts = {
        "a": {"contract": "t", "external": {
            "near_max": [{"other": "b", "max_mm": 10.0, "basis": "x"}]}},
        "b": {"contract": "t", "external": {}},
    }
    # duplicate declaration with a tighter bound from a WIRED sheet
    contracts["b"]["external"]["near_max"] = [
        {"other": "b", "max_mm": 6.0, "basis": "y"}]
    # make sheet b declare subject b -> target b? No — near_max subject is the
    # declaring sheet; to collide keys the two declarations must share
    # (subject, target). Redo: both a and b declare the a->b pair is not
    # expressible from b (its subject would be b). Use flow dedupe instead —
    # the REAL double-declaration case (usb_pd->power appears in two chains).
    contracts = {
        "a": {"contract": "t", "external": {"flow": ["a", "b"]}},
        "b": {"contract": "t", "external": {"flow": ["a", "b", "c"]}},
    }
    _patch_contracts(monkeypatch, contracts, wired={"b"})
    idx = fc.build_term_index(["a", "b", "c"])
    hops = [t for t in idx.terms if t.kind == "flow_hop"
            and t.subject == "a" and t.target_raw == "b"]
    assert len(hops) == 1, "duplicate flow hop must dedupe to ONE term"
    assert hops[0].enforced is True, "OR-enforced: wired declarer wins"
    # near_max min-bound merge via two sheets declaring the same subject pair
    contracts2 = {
        "a": {"contract": "t", "external": {
            "near_max": [{"other": "c", "max_mm": 10.0, "basis": "loose"}]}},
    }
    _patch_contracts(monkeypatch, contracts2, wired=set())
    idx2 = fc.build_term_index(["a", "c"])
    nm = [t for t in idx2.terms if t.kind == "near_max"]
    assert len(nm) == 1 and nm[0].bound == 10.0 and nm[0].enforced is False


def test_unknown_external_kind_fails_loud(monkeypatch):
    """A contract declaring an external kind this engine cannot express (e.g.
    region_void) RAISES — never a silent drop (E4' discipline)."""
    contracts = {"a": {"contract": "t", "external": {
        "region_void": [{"corridor": "x"}]}}}
    _patch_contracts(monkeypatch, contracts, wired=set())
    with pytest.raises(ValueError, match="region_void"):
        fc.build_term_index(["a"])


def test_enforced_mirrors_wired_sheets(monkeypatch):
    contracts = {
        "a": {"contract": "t", "external": {
            "far": [{"what": "b.region", "min_mm": 5.0, "basis": "x"}]}},
    }
    _patch_contracts(monkeypatch, contracts, wired=set())
    idx = fc.build_term_index(["a", "b"])
    far = [t for t in idx.terms if t.kind == "far_min"]
    assert far and far[0].enforced is False
    assert far[0].target_raw == "b.region" and far[0].target == "b", \
        "raw dotted target kept; gate coarsening on .target"
    _patch_contracts(monkeypatch, contracts, wired={"a"})
    idx2 = fc.build_term_index(["a", "b"])
    assert [t for t in idx2.terms if t.kind == "far_min"][0].enforced is True


# ---------------------------------------------------------------------------
# (2) real-registry structure (no scalar pinned)
# ---------------------------------------------------------------------------

def test_real_term_index_structure():
    idx = fc.build_term_index()
    kinds = {(t.kind, t.subject, t.target_raw): t for t in idx.terms}
    # the double-declared usb_pd->power hop is ONE deduped term, enforced
    hop = kinds.get(("flow_hop", "usb_pd", "power"))
    assert hop is not None and hop.enforced is True
    # motor near_max exists and is ENFORCED (full-wire world)
    m = kinds.get(("near_max", "motor_sense", "motor_pwm"))
    assert m is not None and m.enforced is True and m.bound == 20.0
    # far term keeps the RAW dotted target
    f = kinds.get(("far_min", "power", "ethernet.line_side"))
    assert f is not None and f.target == "ethernet"
    # facing terms resolved output refs
    fac = kinds.get(("facing", "power", "power_som"))
    assert fac is not None and fac.out_refs, "facing must resolve board refs"
    # near_intent advisories from floorplan.json (no contract near_max pair);
    # uart_bridge graduated to a contract near_max at the audit wave
    ni = [t for t in idx.terms if t.kind == "near_intent"]
    ni_pairs = {(t.subject, t.target_raw) for t in ni}
    assert ni_pairs == {("power_mon", "power_som")}
    assert all(not t.enforced for t in ni)
    # usb_pd's near intent is COVERED by its contract near_max -> NOT near_intent
    assert ("usb_pd", "pd_input") not in ni_pairs


def test_wired_term_sheets_excludes_som_token():
    idx = fc.build_term_index()
    parts = fc.wired_term_sheets(idx)
    assert "@som" not in parts
    assert "usb_pd" in parts and "power" in parts


# ---------------------------------------------------------------------------
# (3) the None-filter (IM2) against the real gate, hermetically
# ---------------------------------------------------------------------------

def test_advisory_injection_none_filter():
    """The advisory injection comprehension excludes contract-less sheets —
    without the filter the gate dies on a None contract (the crash at
    placement_flow_gate's ``c.get("external")``)."""
    from schgen.verify.placement_contract_gate import discover_contract
    sheets = ["power", "definitely_not_a_sheet"]
    injected = {s: c for s in sheets
                if (c := discover_contract(s)) is not None}
    assert "power" in injected and "definitely_not_a_sheet" not in injected
    # the filtered dict runs through the real gate on a tiny synthetic model
    from schgen.tests.test_placement_flow_gate import _model, _zone
    m = _model([_zone("power", 40.0, 30.0)])
    from schgen.verify import placement_flow_gate as pfg
    res = pfg.check(m, contracts=injected)     # must not raise
    assert res.n_contracts == 1


def test_flow_terms_data_channel_matches_counts():
    """The additive ``.terms`` channel carries one record per examined term
    (checked == len for each kind); the summary text is not consulted."""
    from schgen.tests.test_placement_flow_gate import _model, _zone
    from schgen.verify import placement_flow_gate as pfg
    m = _model([
        _zone("usb_pd", 20.0, 20.0),
        _zone("power", 40.0, 30.0),
        _zone("power_som", 60.0, 40.0),
    ])
    c = {"power": {"contract": "t", "external": {
        "flow": ["usb_pd", "power", "power_som"],
        "far": [{"what": "usb_pd.io", "min_mm": 1.0, "basis": "b"}],
        "near_max": [{"other": "usb_pd", "max_mm": 50.0, "basis": "b"}]}}}
    res = pfg.check(m, contracts=c)
    by_kind: dict[str, int] = {}
    for t in res.terms:
        by_kind[t.kind] = by_kind.get(t.kind, 0) + 1
    assert by_kind.get("flow", 0) == res.flow_checked == 2
    assert by_kind.get("far", 0) == res.far_checked == 1
    assert by_kind.get("near_max", 0) == res.near_max_checked == 1
    assert all(t.ok for t in res.terms), res.summary()


def test_dispersion_by_sheet_maps_clusters():
    from schgen.verify import ratsnest_gate as rg
    res = rg.RatsnestResult()
    res.clusters = [("a", 5, 100.0, 2.5), ("b", 3, 50.0, 1.1)]
    assert rg.dispersion_by_sheet(res) == {"a": 2.5, "b": 1.1}


def test_channel_demand_thresholds():
    """D13 channel reservation: zero below the hotspot threshold, floor +
    per-net above, monotonic."""
    assert fc.channel_demand_mm(fc.CHANNEL_MIN_NETS - 1) == 0.0
    lo = fc.channel_demand_mm(fc.CHANNEL_MIN_NETS)
    hi = fc.channel_demand_mm(fc.CHANNEL_MIN_NETS + 10)
    assert lo >= fc.CHANNEL_FLOOR_MM
    assert hi > lo
    assert hi == pytest.approx(
        fc.CHANNEL_FLOOR_MM
        + fc.CHANNEL_PER_NET_MM * (fc.CHANNEL_MIN_NETS + 10))


def test_seat_consistency_advisory_tracks_spec():
    """D-1: a WIRED near_max whose subject rides a floorplan ``near`` anchor at
    an edge block must carry an exclusive pull. Expectation computed LIVE from
    the current floorplan.json (before P3 lands the pull: usb_pd flagged;
    after: clean) — the test never pins the migration state."""
    import json

    from schgen.generate.compose_repair import _seat_consistency
    from schgen.generate.floorplan import FLOORPLAN_SPEC
    idx = fc.build_term_index()
    flags = _seat_consistency(idx)
    raw = json.loads(FLOORPLAN_SPEC.read_text())
    usb = raw.get("interior", {}).get("usb_pd", {})
    has_pull = isinstance(usb.get("pull"), dict) and usb["pull"].get(
        "exclusive")
    if has_pull:
        assert not any(f.startswith("usb_pd:") for f in flags), flags
    else:
        assert any(f.startswith("usb_pd:") for f in flags), (
            "usb_pd rides the edge-seat near-anchor without a pull — the D-1 "
            "advisory must flag it until the P3 migration lands")


# ---------------------------------------------------------------------------
# (4) BOARD-SCALE exactness (mandatory at every T1 phase gate)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _board_ctx():
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.generate import floorplan as fp
    from schgen.generate import pcb as pcb_mod
    from schgen.generate.pcb.placement import build_model, som_core_rect
    from schgen.verify import powertree
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    lr = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = fp.build_plan(sheets, lr, regs)
    poses = {b.name: (b.x, b.y) for b in plan.blocks}
    som_rect = som_core_rect(plan.som_x, plan.som_y, plan.som.w, plan.som.h)
    zg = pcb_mod.subsystem_zone_geometry(two_side=True)
    metrics = fc.zone_local_metrics(zg)
    index = fc.build_term_index([sc.name for sc in sheets])
    model = build_model()
    return dict(plan=plan, poses=poses, som=som_rect, metrics=metrics,
                index=index, model=model, zg=zg,
                W=model.board_w, H=model.board_h)


@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1 "
                                       "(mandatory at T1 phase gates)")
def test_exactness_evaluator_matches_emitted_gate(_board_ctx):
    """Exactness expectations are COMPUTED FROM THE SAME-RUN MODEL (stale-
    scalar law): a sheet outside ``emit_mobile_sheets`` (no L4 mover, no
    edge-snap connector) must match the evaluator <= 1e-6, per sheet AND per
    term; a mobile sheet is bounded by its declared guard (FAR_L4_GUARD_MM)
    or only printed. P2 measured truth: usb_pd + motor_pwm are the exact set
    — the P5 exemption grows it (pd_input/power/power_som) and tightens this
    test automatically through the same derivation."""
    from schgen.verify.placement_flow_gate import zone_bboxes, zone_centroids
    ctx = _board_ctx
    mobile = fc.emit_mobile_sheets(ctx["zg"])
    exact = ({s for s in ctx["poses"] if s in ctx["metrics"]}) - set(mobile)
    assert "usb_pd" in exact, (
        "usb_pd left the emit-exact set — its template stopped forcing every "
        "part to the top side (or its P5 exemption vanished); the P6 "
        "legalizer seat prediction just broke")

    # per-sheet: exact sheets match the emitted gate geometry to 1e-6;
    # snap-ONLY sheets (edge connector, no L4) are bounded by GUARD_MM.
    cent = zone_centroids(ctx["model"])
    bbs = zone_bboxes(ctx["model"])
    for sheet in sorted(set(ctx["poses"]) & set(ctx["metrics"])):
        if sheet not in cent:
            continue
        reasons = mobile.get(sheet, frozenset())
        if "l4" in reasons:
            continue                      # bounded only by measurement pre-P5
        bound = 1e-6 if not reasons else fc.GUARD_MM
        pc = fc.predicted_centroid(ctx["poses"][sheet], ctx["metrics"][sheet])
        pb = fc.predicted_bbox(ctx["poses"][sheet], ctx["metrics"][sheet])
        assert pc is not None and pb is not None, sheet
        assert max(abs(pc[0] - cent[sheet][0]),
                   abs(pc[1] - cent[sheet][1])) <= bound, (
            f"{sheet} ({sorted(reasons)}): centroid pred {pc} != emitted "
            f"{cent[sheet]} (bound {bound})")
        assert max(abs(a - b)
                   for a, b in zip(pb, bbs[sheet], strict=True)) <= bound, (
            f"{sheet} ({sorted(reasons)}): bbox pred {pb} != emitted "
            f"{bbs[sheet]} (bound {bound})")

    # per-term: tolerance = sum of endpoint tolerances (0 exact / GUARD_MM
    # snap-only / declared FAR_L4_GUARD / unbounded-print for L4 mobiles)
    pred = fc.evaluate_terms(ctx["W"], ctx["H"], ctx["som"], ctx["poses"],
                             ctx["metrics"], ctx["index"], far_guard={})
    meas = fc.measure_terms(ctx["model"], ctx["index"])

    def tol(sheet: str) -> float | None:
        if sheet == "@som" or sheet in exact:
            return 0.0
        reasons = mobile.get(sheet, frozenset())
        if reasons == {"snap"}:
            return fc.GUARD_MM
        if sheet in fc.FAR_L4_GUARD_MM:
            return fc.FAR_L4_GUARD_MM[sheet]
        return None                      # undeclared L4 mobile: print only

    printed = []
    for p, m in zip(pred, meas, strict=True):
        assert p.term.key == m.term.key
        if not (math.isfinite(p.measured) and math.isfinite(m.measured)):
            continue
        resid = abs(p.measured - m.measured)
        ta, tb = tol(p.term.subject), tol(p.term.target)
        bound = None if (ta is None or tb is None) else (ta + tb + 1e-6)
        printed.append(
            f"{p.term.kind} {p.term.subject}->{p.term.target_raw}: "
            f"resid {resid:.6f}"
            + (f" (bound {bound:.3f})" if bound is not None else " (print)"))
        if bound is not None and p.term.kind != "facing":
            assert resid <= bound, printed[-1]
    print("\n".join(["", "=== exactness residual vector ==="] + printed))

    # the D11 seat pair: while pd_input still carries L4 movers ("l4" reason,
    # pre-P5 state) they can only CLOSE the gap toward the inboard usb_pd
    # (motion is SoM-ward) — one-sided conservative; post-P5 the pair is
    # GUARD-bounded above.
    if "l4" in mobile.get("pd_input", frozenset()):
        for p, m in zip(pred, meas, strict=True):
            if p.term.kind == "near_max" and p.term.subject == "usb_pd" \
                    and p.term.target == "pd_input":
                assert p.measured >= m.measured - 1e-6, (
                    f"usb_pd<->pd_input gap prediction is not conservative: "
                    f"pred {p.measured} < meas {m.measured}")


@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1")
def test_exactness_red_without_snap_replication(_board_ctx):
    """RED-ON-BEFORE (a): WITHOUT the ``_gridify`` zone-origin snap the
    prediction diverges from the emitted board beyond the exact tolerance for
    at least one wired-term sheet — proving the rounding-chain replication is
    load-bearing, not decorative."""
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    ctx = _board_ctx
    from schgen.verify.placement_flow_gate import zone_centroids
    cent = zone_centroids(ctx["model"])
    # restrict to the SAME-RUN exact set: for these sheets the snapped
    # prediction IS the emitted centroid (proven above), so any naive-vs-
    # emitted divergence is attributable to the snap alone.
    exact = ({s for s in ctx["poses"] if s in ctx["metrics"]}
             - set(fc.emit_mobile_sheets(ctx["zg"])))
    diverged = 0.0
    for sheet in sorted(exact):
        if sheet not in cent:
            continue
        m = ctx["metrics"][sheet]
        zx, zy = ctx["poses"][sheet]
        xs = [ORIGIN_X + zx + dx for _r, dx, _dy in m.offsets]
        ys = [ORIGIN_Y + zy + dy for _r, _dx, dy in m.offsets]
        naive = (sum(xs) / len(xs), sum(ys) / len(ys))
        mx, my = cent[sheet]
        diverged = max(diverged, abs(naive[0] - mx), abs(naive[1] - my))
    assert diverged > 1e-6, (
        "the no-snap prediction matched the emitted board — either the snap "
        "replication is dead code or the poses happened to be on-grid; "
        "investigate before trusting the exactness test")


@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1")
def test_exactness_mutation_twin_kills_dead_evaluator(_board_ctx):
    """MUTATION TWIN: perturbing the power pose by 0.7 mm must move the
    evaluator's usb_pd->power hop — an evaluator that echoes the emitted
    measurement regardless of pose would pass exactness while being useless
    to the legalizer."""
    ctx = _board_ctx
    base = fc.evaluate_terms(ctx["W"], ctx["H"], ctx["som"], ctx["poses"],
                             ctx["metrics"], ctx["index"], far_guard={})
    poses2 = dict(ctx["poses"])
    px, py = poses2["power"]
    poses2["power"] = (px + 0.7, py + 0.7)
    mut = fc.evaluate_terms(ctx["W"], ctx["H"], ctx["som"], poses2,
                            ctx["metrics"], ctx["index"], far_guard={})
    moved = 0.0
    for b, m in zip(base, mut, strict=True):
        if b.term.kind == "flow_hop" and "power" in (b.term.subject,
                                                     b.term.target):
            moved = max(moved, abs(b.measured - m.measured))
    assert moved > 0.05, "0.7mm pose perturbation did not move any power hop"


# ---------------------------------------------------------------------------
# (5) T1 P5 — per-kind wired-term participants (the L4 exemption sets)
# ---------------------------------------------------------------------------

def test_wired_term_participants_pinned_today():
    """PINNED (re-pinned at every wiring wave): full-wire world — every
    sheet with a contract is wired (23), so the L4-exempt set is all 23
    plus the near_max targets (rj45_connector, som_j2) and NOTHING is
    L4-guarded."""
    from schgen.core.project import spec
    from schgen.verify.placement_contract_gate import (
        _WIRED_SHEETS,
        wired_term_participants,
    )
    assert _WIRED_SHEETS == spec().wired_sheets and len(_WIRED_SHEETS) == 23
    exempt, guarded = wired_term_participants()
    assert exempt == _WIRED_SHEETS | {"rj45_connector", "som_j2"}
    assert guarded == frozenset()



def test_emit_mobile_reasons_respect_exemption():
    """emit_mobile_sheets never tags an exempt sheet 'l4'; a snapped-connector
    sheet keeps its 'snap' reason even when exempt (the LAW-6 seat step is
    NOT exempted — GUARD_MM bounds it)."""
    class _ZG:      # minimal duck-typed zone geometry
        top_off = {"a": {"U1": (0.0, 0.0)}}
        bot_off = {"a": {"C1": (0.0, 0.0), "C2": (1.0, 0.0)},
                   "b": {"R1": (0.0, 0.0), "R2": (1.0, 0.0)}}
        side_of = {"C1": "bottom", "C2": "bottom",
                   "R1": "bottom", "R2": "bottom"}
        refs_by_sheet = {"a": ["U1", "C1", "C2"], "b": ["R1", "R2"]}
        conn_edge = {"U1": "N"}
    mobile = fc.emit_mobile_sheets(_ZG(), l4_exempt=frozenset({"a"}))
    assert mobile["a"] == frozenset({"snap"})
    assert mobile["b"] == frozenset({"l4"})
    mobile2 = fc.emit_mobile_sheets(_ZG(), l4_exempt=frozenset())
    assert mobile2["a"] == frozenset({"l4", "snap"})


def test_flow_terms_mutation_twin_synthetic():
    """MUTATION TWIN (fast): moving a zone changes the gate's .terms data —
    a terms channel that echoed constants regardless of geometry would be
    useless to the ledger. Baseline precedes the mutant."""
    from schgen.tests.test_placement_flow_gate import _model, _zone
    from schgen.verify import placement_flow_gate as pfg
    c = {"power": {"contract": "t", "external": {
        "flow": ["usb_pd", "power"]}}}
    base = pfg.check(_model([_zone("usb_pd", 20.0, 20.0),
                             _zone("power", 40.0, 30.0)]), contracts=c)
    mut = pfg.check(_model([_zone("usb_pd", 20.0, 20.0),
                            _zone("power", 60.0, 30.0)]), contracts=c)
    b = [t for t in base.terms if t.kind == "flow"][0]
    m = [t for t in mut.terms if t.kind == "flow"][0]
    assert abs(m.measured - b.measured) > 10.0, (b.measured, m.measured)
