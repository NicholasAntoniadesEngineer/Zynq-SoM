"""Deliberately-broken self-tests for the governance mechanisms (U1-U4):
the quantize census must TRIP on a fake raw snap, the fallback ratchet must
TRIP on a forced fallback, the stage tracker must TRIP on movement in a
``may_move=no`` stage — loud, named errors, never silent — plus inertness
spot-proofs for every registered transform and determinism of the generated
pipeline doc. Pure/offline: no board build, no kicad-cli."""

from __future__ import annotations

import json

import pytest

from schgen.core import fallbacks, quantize
from schgen.generate import pipeline_doc
from schgen.generate.pcb.stages import (
    PLACEMENT_STAGES,
    StageMovementError,
    StageTracker,
)
from schgen.verify import fallback_gate, quantize_census


def test_census_trips_on_fake_raw_snap(tmp_path):
    (tmp_path / "pcb").mkdir()
    (tmp_path / "pcb" / "placement.py").write_text(
        "def seat(v, g):\n"
        "    snapped = round(round(v / g) * g, 4)\n"
        "    lim = need + 0.05\n"
        "    _SNAP_EROSION = 0.75\n"
        "    return _gridify(snapped)\n")
    res = quantize_census.check(root=tmp_path,
                                files=("pcb/placement.py",))
    assert not res.ok
    detectors = {s.rsplit("[", 1)[-1].rstrip("]") for s in res.new}
    assert {"compound-round", "credit-0.05", "banned-const",
            "banned-call"} <= detectors
    assert any("pcb/placement.py" in s for s in res.new)


def test_census_baseline_allows_pinned_site_count(tmp_path):
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "geo.py").write_text(
        "x = round(round(v / 1.27) * 1.27, 4)\n")
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps(
        {"allowed": {"gen/geo.py compound-round": 1}}))
    res = quantize_census.check(root=tmp_path, files=("gen/geo.py",),
                                baseline_path=bl)
    assert res.ok and res.n_sites == 1 and res.n_new == 0


def test_live_tree_census_is_clean():
    res = quantize_census.check()
    assert res.ok, res.summary()
    assert res.n_sites == 0
    assert res.n_registered == len(quantize.REGISTRY)


def test_fallback_ratchet_trips_on_forced_fallback(tmp_path):
    fallbacks.reset()
    fallbacks.record("seat_node_budget")
    census = fallbacks.census()
    assert census["seat_node_budget"] == 1
    bl = tmp_path / "fallback_baseline.json"
    bl.write_text(json.dumps({"counts": {n: 0 for n in fallbacks.REGISTRY}}))
    res = fallback_gate.check(census, baseline_path=bl)
    assert not res.ok
    assert any("seat_node_budget" in r for r in res.regressions)
    fallbacks.reset()


def test_fallback_unknown_name_raises_and_baseline_pins(tmp_path):
    with pytest.raises(AssertionError, match="not a registered fallback"):
        fallbacks.record("made_up_fallback")
    fallbacks.reset()
    fallbacks.record("thermal_via_lattice")
    bl = tmp_path / "fallback_baseline.json"
    res = fallback_gate.check(fallbacks.census(), baseline_path=bl)
    assert res.ok and res.pinned and bl.exists()
    pinned = json.loads(bl.read_text())["counts"]
    assert pinned["thermal_via_lattice"] == 1
    res2 = fallback_gate.check({n: 0 for n in fallbacks.REGISTRY},
                               baseline_path=bl)
    assert res2.ok and not res2.pinned
    assert json.loads(bl.read_text())["counts"]["thermal_via_lattice"] == 0
    fallbacks.reset()


def test_solver_infeasible_zone_raises_loudly():
    from schgen.generate.pcb import stage_templates as st
    with pytest.raises(st.ZoneInfeasible, match="badsheet.*no legacy pack"):
        st.build_zone("badsheet",
                      {"structures": [{"type": "same_side", "ics": ["U1"]}]},
                      [], {}, {}, {})
    with pytest.raises(st.ZoneInfeasible, match="anchor U9.*no resolvable"):
        st._build_proximity_cluster("U9", {"structures": []}, {}, {})


def test_infeasible_proximity_demand_raises_not_ships():
    from schgen.generate import pcb
    from schgen.generate.pcb import stage_templates as st
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    assert mod is not None
    contract = {"structures": [{
        "type": "proximity", "anchor": "U1", "max_mm": 0.2,
        "members": ["C1"],
        "min_from": [{"part": "U1", "pin": "1", "min_mm": 50.0}]}]}
    bref_of = {"U1": "U1", "C1": "C1"}
    resolvable = {"U1": mod, "C1": mod}
    with pytest.raises(st.ZoneInfeasible, match="widen exhausted"):
        st._build_proximity_cluster("U1", contract, bref_of, resolvable)
    assert not any("U1" in str(k) for k in st._PROX_CACHE)


def test_stage_tracker_trips_on_no_move_stage():
    trk = StageTracker()
    trk.checkpoint("step3_emission", {"R1": (10.0, 10.0, 0.0)})
    trk.checkpoint("corridor_eviction", {"R1": (12.0, 10.0, 0.0)})
    assert trk.moves["corridor_eviction"] == 1
    with pytest.raises(StageMovementError, match="'instantiate'.*may_move"):
        trk.checkpoint("instantiate", {"R1": (13.0, 10.0, 0.0)})


def test_stage_tracker_enforces_declared_order_and_names():
    trk = StageTracker()
    trk.checkpoint("l4_pull", {"R1": (0.0, 0.0, 0.0)})
    with pytest.raises(StageMovementError, match="out of declared order"):
        trk.checkpoint("step3_emission", {"R1": (0.0, 0.0, 0.0)})
    with pytest.raises(StageMovementError, match="not a declared stage"):
        StageTracker().checkpoint("mystery_stage", {})


def test_stage_tracker_page_domain_is_independent():
    trk = StageTracker()
    trk.checkpoint("instantiate", {"R1": (10.0, 10.0, 0.0)})
    trk.checkpoint("emission_frame", {"R1": (35.0, 35.0, 0.0, "top")})
    trk.checkpoint("escape_copper", {"R1": (35.0, 35.0, 0.0, "top")})
    assert trk.moves.get("escape_copper") == 0


def test_manifest_declares_the_two_frozen_stages():
    frozen = {s.name for s in PLACEMENT_STAGES if not s.may_move and s.tracked}
    assert frozen == {"instantiate", "escape_copper"}
    names = [s.name for s in PLACEMENT_STAGES]
    assert names.index("reorder") < names.index("corridor_eviction") \
        < names.index("instantiate")


def test_registered_transforms_replicate_historical_arithmetic():
    for v in (37.3, 0.0, -12.7, 104.229, 51.4999):
        assert quantize.fixed_part_grid(v) == round(round(v / 1.27) * 1.27, 4)
        assert quantize.breathe_anchor_grid(v) == quantize.fixed_part_grid(v)
        assert quantize.evict_corridor_grid(25.0, v) == round(
            quantize.fixed_part_grid(25.0 + v) - 25.0, 4)
        assert quantize.som_pose_half_mm(v) == round(round(v * 2) / 2, 1)
        assert quantize.legalize_pose_quantum(v) == round(round(v / 0.5)
                                                          * 0.5, 4)
        assert quantize.quant_credit(v) == v + 0.05
        assert quantize.outline_snap_up(abs(v) + 0.1) % 5.0 in (0.0, 5.0)
    assert quantize.snap_erosion_bound(6.0) == 5.25
    assert quantize.snap_erosion_bound(4.99) == 4.99
    assert quantize.snap_erosion_pad(6.0) == 6.75
    assert quantize.snap_erosion_pad(4.99) == 4.99
    assert quantize.seat_slide() == 1.2
    assert quantize.run_overflow_tol() == 0.1
    assert quantize.outline_snap_up(161.0001) == 165.0
    assert quantize.outline_grow(3) == 15.0
    assert quantize.fine_steps() == 41
    assert quantize.fine_shrink(183.0, 2) == 181.0


def test_every_transform_has_a_registry_entry():
    assert set(quantize.REGISTRY) == {
        "fixed_part_grid", "breathe_anchor_grid", "evict_corridor_grid",
        "som_pose_half_mm",
        "placeholder_zone_half_mm", "quant_credit", "snap_erosion_bound",
        "snap_erosion_pad", "seat_slide", "run_overflow_tol",
        "legalize_pose_quantum", "outline_snap_up", "outline_grow_step",
        "outline_fine_grid"}
    for q in quantize.REGISTRY.values():
        assert q.klass in ("pre-proof", "proof-preserving", "re-validated")
        assert q.value and q.basis


def test_pipeline_doc_render_is_deterministic():
    a = pipeline_doc.render()
    b = pipeline_doc.render()
    assert a == b
    assert "## Placement stages" in a
    assert "## Quantization registry" in a
    assert "## Fallback registry" in a
    for name in fallbacks.REGISTRY:
        assert f"`{name}`" in a
    for name in quantize.REGISTRY:
        assert f"`{name}`" in a
