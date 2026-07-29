"""Tests for the ORDER-OF-ASSEMBLY generator (schgen/generate/assembly).

Property layer on the REAL board model (shared ``carrier_model`` fixture):
the two partitions (process steps / bring-up phases) each cover every
non-fiducial part EXACTLY once, the phase order respects the derived rail
chain (entry -> rail sheets -> SoM interface -> mate -> the rest -> mounting
hardware), and every emitted CHECKPOINT names a real test point sitting on
the named rail. Classification pin-checks lock the known traps: the XT60s
are step-4 connectors, the som_decoupling caps bottom-SMD, and the TPS26631
(an SMD efuse whose footprint carries thru_hole EP stitch vias) stays SMD.
Determinism: the markdown and a stage PNG are byte-identical across two
renders of the same model.
"""

from __future__ import annotations

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
