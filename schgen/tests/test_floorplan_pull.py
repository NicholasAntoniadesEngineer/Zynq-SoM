from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from schgen.generate.floorplan import FloorplanSpecError, load_floorplan_spec


def _write_spec(tmp_path, interior_usb_pd: dict):
    spec = {
        "outline": "auto",
        "edges": {"N": ["pd_input"]},
        "interior": {"usb_pd": interior_usb_pd},
    }
    p = tmp_path / "floorplan.json"
    p.write_text(json.dumps(spec))
    return p


_NAMES = {"pd_input", "usb_pd", "power"}


def _pull(**over) -> dict:
    base = {"to": "pd_input", "weight": 60.0, "face": "inboard",
            "exclusive": True, "basis": "D11 edge-seat override (test)"}
    base.update(over)
    return base


def test_pull_parses(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull()})
    spec = load_floorplan_spec(p, valid_names=_NAMES)
    assert spec is not None
    got = spec.interior["usb_pd"]
    assert got["near"] == "pd_input"
    assert got["pull"]["to"] == "pd_input"
    assert got["pull"]["exclusive"] is True
    assert got["pull"]["weight"] == 60.0


def test_pull_unknown_key_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(wieght=60.0)})
    with pytest.raises(FloorplanSpecError, match="pull"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_nonpositive_weight_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull(weight=0.0)})
    with pytest.raises(FloorplanSpecError, match="weight"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_missing_basis_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull(basis="")})
    with pytest.raises(FloorplanSpecError, match="basis"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_unknown_target_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(to="nosuch")})
    with pytest.raises(FloorplanSpecError, match="nosuch"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_inboard_requires_edge_target(tmp_path):
    p = _write_spec(tmp_path, {"near": "power",
                               "pull": _pull(to="power", face="inboard")})
    with pytest.raises(FloorplanSpecError, match="inboard"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_exclusive_requires_matching_near(tmp_path):
    p = _write_spec(tmp_path, {"side": "E", "pull": _pull()})
    with pytest.raises(FloorplanSpecError, match="exclusive"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_bad_face_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(face="outboard")})
    with pytest.raises(FloorplanSpecError, match="face"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_spec_without_pull_still_parses(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input"})
    spec = load_floorplan_spec(p, valid_names=_NAMES)
    assert spec is not None and "pull" not in spec.interior["usb_pd"]


def test_edge_seat_blocks_hack_is_gone():
    import schgen.generate.floorplan as fp
    assert not hasattr(fp, "_EDGE_SEAT_BLOCKS")
    assert not hasattr(fp, "_EDGE_SEAT_ZONE_W")


def test_carrier_spec_carries_the_usb_pd_pull():
    from schgen.generate.floorplan import FLOORPLAN_SPEC
    raw = json.loads(FLOORPLAN_SPEC.read_text())
    usb = raw["interior"]["usb_pd"]
    assert usb.get("near") == "pd_input"
    pull = usb.get("pull")
    assert isinstance(pull, dict), "P3 migration missing"
    assert pull["to"] == "pd_input" and pull["exclusive"] is True
    assert pull["weight"] == 60.0
    assert pull["basis"]


@pytest.fixture
def floorplan_stage(monkeypatch, tmp_path):
    from schgen.core.link import LinkResult, SheetCircuit
    from schgen.core.model import Circuit
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb.placement import FloorplanStageResult

    monkeypatch.setattr(fp, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fp, "FLOORPLAN_SPEC", tmp_path / "floorplan.json")
    monkeypatch.setattr(fp, "OUT_SVG", tmp_path / "FLOORPLAN.svg")
    monkeypatch.setattr(fp, "OUT_MD", tmp_path / "FLOORPLAN.md")
    monkeypatch.setattr(fp, "BOARD_W", 168.0)
    monkeypatch.setattr(fp, "BOARD_H", 163.0)
    monkeypatch.setattr(fp, "OUTLINE_NOTE", "test outline")
    sheets = [SheetCircuit("logic", Circuit("logic"), tmp_path, None)]
    linked = LinkResult(sheets=sheets)
    plan = fp.Plan(fp.SomGeom(42.0, 32.0, (), "fixture.kicad_pcb"))
    plan.interior_blocks.append(fp.Block(
        "logic", "interior", x=12.0, y=15.0, w=20.0, h=10.0))
    stage = FloorplanStageResult.capture(
        plan, sheets, linked, [], two_side=True, spec=None)
    return SimpleNamespace(plan=plan, stage=stage, sheets=sheets, linked=linked)


def test_stage_reuse_skips_solve_and_preserves_doc_bytes(
        monkeypatch, floorplan_stage):
    from schgen.generate import floorplan as fp

    f = floorplan_stage
    solve = Mock(return_value=deepcopy(f.plan))
    monkeypatch.setattr(fp, "build_plan", solve)
    paths = fp.generate(f.sheets, f.linked)
    expected = [p.read_bytes() for p in paths]
    solve.assert_called_once_with(f.sheets, f.linked, [])
    # Model placement and unrelated outline work cannot corrupt the snapshot.
    f.plan.interior_blocks[0].x = -500.0
    f.plan.composition.append("later placement")
    fp.BOARD_W, fp.BOARD_H, fp.OUTLINE_NOTE = (900.0, 800.0, "unrelated outline")
    paths = fp.generate(f.sheets, f.linked, plan=f.stage)
    assert [p.read_bytes() for p in paths] == expected
    assert solve.call_count == 1
    assert (fp.BOARD_W, fp.BOARD_H, fp.OUTLINE_NOTE) == (
        900.0, 800.0, "unrelated outline")
    assert f.stage.plan.interior_blocks[0].x == 12.0
    assert f.stage.plan.composition == []


def test_stage_matches_independently_loaded_equivalent_inputs(floorplan_stage):
    f = floorplan_stage
    assert f.stage.matches(deepcopy(f.sheets), deepcopy(f.linked), [])


@pytest.mark.parametrize("changed", ["sheet", "bindings", "spec", "project",
                                     "som_offset", "regs"])
def test_changed_stage_inputs_rebuild(monkeypatch, floorplan_stage, changed):
    from schgen.generate import floorplan as fp
    from schgen.verify import powertree

    f = floorplan_stage
    if changed == "sheet":
        f.sheets[0].circuit.title = "changed circuit"
    elif changed == "bindings":
        f.linked.bindings.append(SimpleNamespace(targets=["different target"]))
    elif changed == "spec":
        fp.FLOORPLAN_SPEC.write_text('{"outline": [200, 200]}')
    elif changed == "project":
        monkeypatch.setattr(fp, "PROJECT_ROOT", fp.PROJECT_ROOT / "other")
    elif changed == "som_offset":
        monkeypatch.setattr(fp, "SOM_DX", fp.SOM_DX + 1.0)
    else:
        monkeypatch.setattr(powertree, "analyze",
                            lambda sheets: SimpleNamespace(regs=["changed"]))

    def fresh_plan(*args):
        raise RuntimeError("fresh plan requested")

    monkeypatch.setattr(fp, "build_plan", fresh_plan)
    with pytest.raises(RuntimeError, match="fresh plan requested"):
        fp.generate(f.sheets, f.linked, plan=f.stage)


@pytest.mark.parametrize("two_side,spec", [(False, None), (True, object())])
def test_nondefault_stage_options_are_not_reused(floorplan_stage, two_side, spec):
    from schgen.generate.pcb.placement import FloorplanStageResult

    f = floorplan_stage
    stage = FloorplanStageResult.capture(
        f.plan, f.sheets, f.linked, [], two_side=two_side, spec=spec)
    assert not stage.matches(f.sheets, f.linked, [])


def test_reuse_restores_render_context_on_error(monkeypatch, floorplan_stage):
    from schgen.generate import floorplan as fp

    f = floorplan_stage
    original = (201.0, 202.0, "other board")
    fp.BOARD_W, fp.BOARD_H, fp.OUTLINE_NOTE = original

    def fail_render(plan, notes, out):
        assert (fp.BOARD_W, fp.BOARD_H, fp.OUTLINE_NOTE) == f.stage.render_context
        plan.interior_blocks[0].x = -1.0
        raise RuntimeError("render failed")

    monkeypatch.setattr(fp, "render_svg", fail_render)
    monkeypatch.setattr(fp, "build_plan", Mock(side_effect=AssertionError))
    with pytest.raises(RuntimeError, match="render failed"):
        fp.generate(f.sheets, f.linked, plan=f.stage)
    assert (fp.BOARD_W, fp.BOARD_H, fp.OUTLINE_NOTE) == original
    assert f.stage.plan.interior_blocks[0].x == 12.0


def test_standalone_floorplan_loads_and_builds(monkeypatch, floorplan_stage):
    from schgen.core import link
    from schgen.generate import floorplan as fp

    f = floorplan_stage
    monkeypatch.setattr(link, "all_subsystem_paths", lambda: [f.sheets[0].path])
    monkeypatch.setattr(link, "load_subsystem", lambda name: f.sheets[0])
    monkeypatch.setattr(link, "load_som_contract", lambda: {})
    monkeypatch.setattr(link, "link", lambda sheets, som: f.linked)
    solve = Mock(return_value=deepcopy(f.plan))
    monkeypatch.setattr(fp, "build_plan", solve)
    fp.generate()
    solve.assert_called_once_with(f.sheets, f.linked, [])
    assert fp.OUT_SVG.exists() and fp.OUT_MD.exists()


def test_pcb_generate_forwards_stage_sink(monkeypatch):
    from schgen.generate.pcb import emit

    sink = Mock()
    model = Mock(side_effect=RuntimeError("stop before PCB emission"))
    monkeypatch.setattr(emit, "build_model", model)
    with pytest.raises(RuntimeError, match="stop before PCB emission"):
        emit.generate(plan_sink=sink)
    model.assert_called_once_with(two_side=True, plan_sink=sink)


def test_pcb_generate_preserves_default_model_call(monkeypatch):
    from schgen.generate.pcb import emit

    model = Mock(side_effect=RuntimeError("stop before PCB emission"))
    monkeypatch.setattr(emit, "build_model", model)
    with pytest.raises(RuntimeError, match="stop before PCB emission"):
        emit.generate(two_side=False)
    model.assert_called_once_with(two_side=False)


@pytest.mark.parametrize("edit_during_solve", [False, True])
def test_placement_captures_stage_before_downstream_work(
        monkeypatch, floorplan_stage, edit_during_solve):
    from schgen.core import link
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb import placement

    f = floorplan_stage
    monkeypatch.setattr(placement, "board_netlist", lambda: {})
    monkeypatch.setattr(placement, "board_parts", lambda: {})
    monkeypatch.setattr(placement._fb, "reset", lambda: None)
    zg = SimpleNamespace(zone_box={}, top_off={}, bot_off={}, side_of={},
                         bbox_of={}, resolvable={}, deferred=[], mh_refs=[])
    monkeypatch.setattr(placement, "subsystem_zone_geometry", lambda **kw: zg)
    monkeypatch.setattr(link, "all_subsystem_paths", lambda: [f.sheets[0].path])
    monkeypatch.setattr(link, "load_subsystem", lambda name: f.sheets[0])
    monkeypatch.setattr(link, "load_som_contract", lambda: {})
    monkeypatch.setattr(link, "link", lambda sheets, som: f.linked)
    def solve_plan(*args, **kwargs):
        if edit_during_solve:
            fp.FLOORPLAN_SPEC.write_text('{"outline": [200, 200]}')
        return f.plan

    solve = Mock(side_effect=solve_plan)
    monkeypatch.setattr(fp, "build_plan", solve)
    captured = []

    def stop(*args):
        raise RuntimeError("stop before downstream placement")

    monkeypatch.setattr(placement, "apply_chosen_shapes", stop)
    monkeypatch.setattr(placement._led, "open_step", lambda *args: None)
    monkeypatch.setattr(placement._led, "calc", lambda *args, **kwargs: None)

    def sink(stage):
        captured.append(stage)
        f.plan.interior_blocks[0].x = -10.0

    with pytest.raises(RuntimeError, match="stop before downstream placement"):
        placement.build_model(plan_sink=sink)
    solve.assert_called_once_with(f.sheets, f.linked, [], spec=None)
    if edit_during_solve:
        assert captured == []
        return
    assert len(captured) == 1
    assert captured[0].matches(f.sheets, f.linked, [])
    assert captured[0].plan.interior_blocks[0].x == 12.0
