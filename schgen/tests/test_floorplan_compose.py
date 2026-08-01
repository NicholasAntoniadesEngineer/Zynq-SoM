from __future__ import annotations

import math
import os

import pytest

from schgen.generate import floorplan_compose as fc

_BOARD = os.environ.get("SCHGEN_BOARD_TESTS") == "1"


def _patch_contracts(monkeypatch, contracts: dict[str, dict],
                     wired: set[str]) -> None:
    import schgen.verify.placement_contract_gate as pcg
    monkeypatch.setattr(pcg, "discover_contract",
                        lambda s: contracts.get(s))
    monkeypatch.setattr(pcg, "_WIRED_SHEETS", frozenset(wired))


def test_dedupe_keeps_min_bound_and_or_enforced(monkeypatch):
    contracts = {
        "a": {"contract": "t", "external": {
            "near_max": [{"other": "b", "max_mm": 10.0, "basis": "x"}]}},
        "b": {"contract": "t", "external": {}},
    }
    contracts["b"]["external"]["near_max"] = [
        {"other": "b", "max_mm": 6.0, "basis": "y"}]
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
    contracts2 = {
        "a": {"contract": "t", "external": {
            "near_max": [{"other": "c", "max_mm": 10.0, "basis": "loose"}]}},
    }
    _patch_contracts(monkeypatch, contracts2, wired=set())
    idx2 = fc.build_term_index(["a", "c"])
    nm = [t for t in idx2.terms if t.kind == "near_max"]
    assert len(nm) == 1 and nm[0].bound == 10.0 and nm[0].enforced is False


def test_unknown_external_kind_fails_loud(monkeypatch):
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


def test_real_term_index_structure():
    idx = fc.build_term_index()
    kinds = {(t.kind, t.subject, t.target_raw): t for t in idx.terms}
    hop = kinds.get(("flow_hop", "usb_pd", "power"))
    assert hop is not None and hop.enforced is True
    m = kinds.get(("near_max", "motor_sense", "motor_pwm"))
    assert m is not None and m.enforced is True and m.bound == 20.0
    f = kinds.get(("far_min", "power", "ethernet.line_side"))
    assert f is not None and f.target == "ethernet"
    fac = kinds.get(("facing", "power", "power_som"))
    assert fac is not None and fac.out_refs, "facing must resolve board refs"
    ni = [t for t in idx.terms if t.kind == "near_intent"]
    ni_pairs = {(t.subject, t.target_raw) for t in ni}
    assert ni_pairs == {("power_mon", "power_som")}
    assert all(not t.enforced for t in ni)
    assert ("usb_pd", "pd_input") not in ni_pairs


def test_wired_term_sheets_excludes_som_token():
    idx = fc.build_term_index()
    parts = fc.wired_term_sheets(idx)
    assert "@som" not in parts
    assert "usb_pd" in parts and "power" in parts


def test_advisory_injection_none_filter():
    from schgen.verify.placement_contract_gate import discover_contract
    sheets = ["power", "definitely_not_a_sheet"]
    injected = {s: c for s in sheets
                if (c := discover_contract(s)) is not None}
    assert "power" in injected and "definitely_not_a_sheet" not in injected
    from schgen.tests.test_placement_flow_gate import _model, _zone
    m = _model([_zone("power", 40.0, 30.0)])
    from schgen.verify import placement_flow_gate as pfg
    res = pfg.check(m, contracts=injected)
    assert res.n_contracts == 1


def test_flow_terms_data_channel_matches_counts():
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
    assert fc.channel_demand_mm(fc.CHANNEL_MIN_NETS - 1) == 0.0
    lo = fc.channel_demand_mm(fc.CHANNEL_MIN_NETS)
    hi = fc.channel_demand_mm(fc.CHANNEL_MIN_NETS + 10)
    assert lo >= fc.CHANNEL_FLOOR_MM
    assert hi > lo
    assert hi == pytest.approx(
        fc.CHANNEL_FLOOR_MM
        + fc.CHANNEL_PER_NET_MM * (fc.CHANNEL_MIN_NETS + 10))


def test_seat_consistency_advisory_tracks_spec():
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
    smet = fc.zone_shape_metrics(zg)
    for b in plan.blocks:
        if b.shape_idx:
            metrics[b.name] = smet[(b.name, b.shape_idx)]
    index = fc.build_term_index([sc.name for sc in sheets])
    model = build_model()
    return dict(plan=plan, poses=poses, som=som_rect, metrics=metrics,
                index=index, model=model, zg=zg,
                W=model.board_w, H=model.board_h)


@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1 "
                                       "(mandatory at T1 phase gates)")
def test_exactness_evaluator_matches_emitted_gate(_board_ctx):
    from schgen.verify.placement_flow_gate import zone_bboxes, zone_centroids
    ctx = _board_ctx
    mobile = fc.emit_mobile_sheets(ctx["zg"])
    exact = ({s for s in ctx["poses"] if s in ctx["metrics"]}) - set(mobile)
    assert "usb_pd" in exact, (
        "usb_pd left the emit-exact set — its template stopped forcing every "
        "part to the top side (or its P5 exemption vanished); the P6 "
        "legalizer seat prediction just broke")

    cent = zone_centroids(ctx["model"])
    bbs = zone_bboxes(ctx["model"])
    for sheet in sorted(set(ctx["poses"]) & set(ctx["metrics"])):
        if sheet not in cent:
            continue
        reasons = mobile.get(sheet, frozenset())
        if "l4" in reasons or "refit" in reasons:
            continue
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

    pred = fc.evaluate_terms(ctx["W"], ctx["H"], ctx["som"], ctx["poses"],
                             ctx["metrics"], ctx["index"], far_guard={})
    meas = fc.measure_terms(ctx["model"], ctx["index"])

    def tol(sheet: str) -> float | None:
        if sheet == "@som" or sheet in exact:
            return 0.0
        reasons = mobile.get(sheet, frozenset())
        if "refit" in reasons:
            return None
        if reasons == {"snap"}:
            return fc.GUARD_MM
        if sheet in fc.FAR_L4_GUARD_MM:
            return fc.FAR_L4_GUARD_MM[sheet]
        return None

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

    if "l4" in mobile.get("pd_input", frozenset()):
        for p, m in zip(pred, meas, strict=True):
            if p.term.kind == "near_max" and p.term.subject == "usb_pd" \
                    and p.term.target == "pd_input":
                assert p.measured >= m.measured - 1e-6, (
                    f"usb_pd<->pd_input gap prediction is not conservative: "
                    f"pred {p.measured} < meas {m.measured}")


@pytest.mark.skipif(not _BOARD, reason="board-scale; SCHGEN_BOARD_TESTS=1")
def test_exactness_red_without_snap_replication(_board_ctx):
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    ctx = _board_ctx
    from schgen.verify.placement_flow_gate import zone_centroids
    cent = zone_centroids(ctx["model"])
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


def test_wired_term_participants_pinned_today():
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
    class _ZG:
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
