from __future__ import annotations

import ast
from pathlib import Path

import pytest

from schgen.generate import assembly as asm


@pytest.fixture(scope="module")
def sheets():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


@pytest.fixture(scope="module")
def steps(carrier_model):
    return asm.process_steps(carrier_model)


@pytest.fixture(scope="module")
def phases(carrier_model, sheets):
    return asm.bringup_phases(carrier_model, sheets)


def _cover(groups, model):
    parts = asm.assembly_insts(model)
    refs = [i.ref for g in groups for i in g]
    assert len(refs) == len(set(refs)), "a part appears in two groups"
    assert sorted(refs) == sorted(i.ref for i in parts)
    return len(refs)


def test_step_partition(carrier_model, steps):
    assert [s.n for s in steps] == [1, 2, 3, 4]
    n = _cover([s.insts for s in steps], carrier_model)
    n_fid = sum(1 for i in carrier_model.insts
                if i.footprint == asm.FIDUCIAL_FOOTPRINT)
    assert n == len(carrier_model.insts) - n_fid
    assert n_fid == 5


def test_phase_partition(carrier_model, phases):
    _cover([p.insts for p in phases], carrier_model)
    assert [p.n for p in phases] == list(range(1, len(phases) + 1))


def test_step_classification_pins(carrier_model, steps):
    of = {i.ref: s.n for s in steps for i in s.insts}
    for i in carrier_model.insts:
        stem = i.mod_path.stem
        if stem == "XT60PW-M" or "MountingHole" in i.footprint \
                or stem.startswith("DF40C"):
            assert of[i.ref] == 4, (i.ref, "belongs with connectors/mech")
        if i.sheet == "som_decoupling":
            assert of[i.ref] == 1 and i.side == "bottom", i.ref
        if i.value.startswith("TPS26631"):
            assert of[i.ref] == 2, (i.ref, "SMD efuse: EP vias are not a joint")
    assert not steps[0].insts or all(
        i.side == "bottom" for i in steps[0].insts)


def test_phase_order(phases):
    pos = {p.slug: p.n for p in phases}
    assert phases[0].slug == "power_entry"
    assert "pd_input" in phases[0].sheets
    assert pos["power"] < pos["power_som"] < pos["som_interface"] \
        < pos["som_mate"]
    mate = next(p for p in phases if p.slug == "som_mate")
    assert not mate.insts and mate.checkpoints
    assert all(asm._is_mech(i) for i in phases[-1].insts)
    assert phases[-1].insts


def test_checkpoints_name_real_testpoints(carrier_model, phases):
    tp_net = {}
    for i in carrier_model.insts:
        if i.ref.startswith("TP"):
            nets = [n for _num, n in i.pad_nets.values() if n]
            tp_net[i.ref] = nets[0] if nets else ""
    checked = 0
    for p in phases:
        for cp in p.checkpoints:
            if not cp.startswith("verify "):
                continue
            rail, _, tp = cp[len("verify "):].partition(" at ")
            assert tp_net.get(tp) == rail, cp
            checked += 1
    assert checked >= 5


def test_markdown_and_png_deterministic(carrier_model, steps, phases,
                                        tmp_path):
    md1 = asm._markdown(carrier_model, steps, phases, "carrier")
    md2 = asm._markdown(carrier_model, steps, phases, "carrier")
    assert md1 == md2
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    cur = list(steps[3].insts)
    done = list(steps[0].insts)
    asm._png_stage(carrier_model, done, cur, a, "step 4/4 - determinism")
    asm._png_stage(carrier_model, done, cur, b, "step 4/4 - determinism")
    assert a.read_bytes() == b.read_bytes()
    assert a.stat().st_size > 2000


_REBUILD = ("rebuild the project (`python -m schgen board [--project X]`) "
            "and commit the regenerated artifacts")


def test_committed_markdown_is_current(carrier_model, steps, phases):
    from schgen.core.project import spec
    live = asm._markdown(carrier_model, steps, phases, spec().name)
    assert asm.ASSEMBLY_MD.exists(), f"{asm.ASSEMBLY_MD} missing — {_REBUILD}"
    committed = asm.ASSEMBLY_MD.read_text()
    if committed != live:
        cl, ll = committed.splitlines(), live.splitlines()
        first = next((f"line {i + 1}: committed {c!r} != live {v!r}"
                      for i, (c, v) in enumerate(zip(cl, ll, strict=False))
                      if c != v), f"length {len(cl)} != {len(ll)}")
        raise AssertionError(
            f"{asm.ASSEMBLY_MD} is STALE — {first}; {_REBUILD}")


def test_committed_stage_pngs_are_current(carrier_model, steps, phases,
                                          tmp_path):
    live = asm._stage_pngs(carrier_model, steps, phases, tmp_path)
    have = sorted(p.name for p in asm.PNG_DIR.glob("*.png"))
    want = sorted(p.name for p in live)
    assert have == want, (
        f"{asm.PNG_DIR}: stage set drifted "
        f"(missing {sorted(set(want) - set(have))}, "
        f"orphan {sorted(set(have) - set(want))}) — {_REBUILD}")
    stale = [p.name for p in live
             if (asm.PNG_DIR / p.name).read_bytes() != p.read_bytes()]
    assert not stale, f"{asm.PNG_DIR}: {len(stale)} STALE PNGs {stale[:6]} — {_REBUILD}"


def test_verdict_absence_and_error_are_failures():
    for empty in (None, {}, {"ok": True}):
        ok, line = asm.verdict(empty)
        assert not ok and line.startswith("ASSEMBLY: FAIL"), empty
    ok, line = asm.verdict({"ok": False, "error": "PIL exploded"})
    assert not ok and "PIL exploded" in line
    ok, line = asm.verdict({
        "ok": True, "md": asm.ASSEMBLY_MD, "png_dir": asm.PNG_DIR,
        "n_steps": 4, "n_phases": 33, "n_parts": 502, "n_pngs": 37})
    assert ok
    assert line.startswith("ASSEMBLY: 4 steps + 33 phases, 502 parts -> ")
    assert "(37 PNGs)" in line


def test_generation_failure_is_a_ceiling_zero_fallback(tmp_path):
    import json

    from schgen.core import fallbacks as fb
    from schgen.verify import fallback_gate
    assert fb.REGISTRY["assembly_generation_failed"].stage == "assembly_docs"
    for proj in ("carrier", "devkit_mini"):
        bl = json.loads((Path(asm.__file__).resolve().parents[2] / proj
                         / "reports" / "fallback_baseline.json").read_text())
        assert bl["counts"].get("assembly_generation_failed", 0) == 0
    bl_path = tmp_path / "fallback_baseline.json"
    bl_path.write_text(json.dumps({"counts": {n: 0 for n in fb.REGISTRY}}))
    res = fallback_gate.check({n: 0 for n in fb.REGISTRY}, baseline_path=bl_path)
    assert res.ok
    res = fallback_gate.check({**{n: 0 for n in fb.REGISTRY},
                               "assembly_generation_failed": 1},
                              baseline_path=bl_path)
    assert not res.ok and "assembly_generation_failed" in res.regressions[0]


def _hook_call_targets(path: Path, func: str) -> set[str]:
    tree = ast.parse(path.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == func)
    aliases = set()
    for n in list(ast.walk(tree)):
        if isinstance(n, ast.ImportFrom) and n.module == "schgen.generate":
            aliases |= {a.asname or a.name for a in n.names
                        if a.name == "assembly"}
    return {f"{ast.unparse(n.func.value)}.{n.func.attr}"
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and ast.unparse(n.func.value) in aliases}


def test_emit_calls_the_generator_and_cmd_board_calls_assembly_verdict():
    root = Path(asm.__file__).resolve().parents[2]
    emit_calls = _hook_call_targets(root / "schgen" / "generate" / "pcb"
                                    / "emit.py", "generate")
    assert any(c.endswith(".generate") for c in emit_calls), (
        "schgen/generate/pcb/emit.py: generate() no longer calls "
        "assembly.generate — the ASSEMBLY artifacts would go stale silently")
    main_calls = _hook_call_targets(root / "schgen" / "__main__.py",
                                    "cmd_board")
    assert any(c.endswith(".verdict") for c in main_calls), (
        "schgen/__main__.py: cmd_board() no longer calls assembly.verdict — "
        "a missing/failed ASSEMBLY step would print nothing")
