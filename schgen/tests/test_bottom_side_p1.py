"""Bottom-side P1 guards (docs/BOTTOM_SIDE_STRATEGY.md): the two-layer +
punch occupancy legality, the mirrored re-pack determinism, the face=top
constraint inside bottom variants, the floorplan.json layer-side parsing,
and — the landing gate's unit form — zero-opt-in inertness (no bottom shape
exists, no side flips, no via-cost term) with the real project spec. The
board-level control is the byte-identical .kicad_pcb md5 pair."""

from __future__ import annotations

import dataclasses
import json

import pytest

from schgen.core import quantize as q
from schgen.generate import floorplan as fp
from schgen.generate.floorplan import (
    OCC_BOTTOM,
    OCC_PUNCH,
    OCC_TOP,
    FloorplanSpecError,
    _Occupancy,
    load_floorplan_spec,
)
from schgen.generate.pcb.placement import (
    _mirror_offsets_x,
    _pack_one_zone,
    apply_chosen_shapes,
    subsystem_zone_geometry,
)


@pytest.fixture(scope="module")
def real_spec():
    return load_floorplan_spec()


@pytest.fixture(scope="module")
def zg_real(real_spec):
    return subsystem_zone_geometry(two_side=True, spec=real_spec)


def _either_spec(real_spec, sheet="hdmi_rx_term"):
    return dataclasses.replace(
        real_spec, interior={**real_spec.interior, sheet: {"side": "either"}})


@pytest.fixture(scope="module")
def zg_either(real_spec):
    spec2 = _either_spec(real_spec)
    a = subsystem_zone_geometry(two_side=True, spec=spec2)
    b = subsystem_zone_geometry(two_side=True, spec=spec2)
    return a, b


def test_est_via_cost_registered():
    reg = q.REGISTRY["est_via_cost"]
    assert reg.klass == "pre-proof"
    assert "byte-inert" in reg.basis
    assert q.est_via_cost() == pytest.approx(2.2)


def test_spec_layer_side_parsing(tmp_path):
    p = tmp_path / "floorplan.json"
    p.write_text(json.dumps({
        "outline": "auto",
        "edges": {"N": []},
        "interior": {"a_block": {"side": "either"},
                     "b_block": {"side": "S"},
                     "c_block": {"near": "b_block", "side": "bottom"},
                     "d_block": {"side": "E", "layer": "either"}},
    }))
    spec = load_floorplan_spec(p)
    assert spec.layer_of == {"a_block": "either", "c_block": "bottom",
                             "d_block": "either"}
    assert spec.interior["d_block"]["side"] == "E"
    p.write_text(json.dumps({
        "outline": "auto",
        "interior": {"a_block": {"side": "sideways"}},
    }))
    with pytest.raises(FloorplanSpecError, match="top/bottom/either"):
        load_floorplan_spec(p)
    p.write_text(json.dumps({
        "outline": "auto",
        "interior": {"a_block": {"layer": "E"}},
    }))
    with pytest.raises(FloorplanSpecError, match="layer must be"):
        load_floorplan_spec(p)
    p.write_text(json.dumps({
        "outline": "auto",
        "interior": {"a_block": {"side": "either", "layer": "bottom"}},
    }))
    with pytest.raises(FloorplanSpecError, match="copper face twice"):
        load_floorplan_spec(p)


def test_occupancy_two_layer_legality(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 100.0)
    monkeypatch.setattr(fp, "BOARD_H", 80.0)
    occ = _Occupancy()
    comps = ((2.0, 2.0, 4.0, 4.0, OCC_BOTTOM), (12.0, 12.0, 3.0, 3.0, OCC_PUNCH))
    occ.add(10, 10, 20, 20, mask=OCC_TOP, comps=comps)
    assert not occ._fits_exhaustive(15, 15, 10, 10, mask=OCC_TOP)
    assert not occ._fits_exhaustive(15, 15, 10, 10, mask=OCC_PUNCH)
    assert occ._fits_exhaustive(40, 40, 5, 5, mask=OCC_BOTTOM)
    assert occ._fits_exhaustive(17.5, 25.5, 4, 4, mask=OCC_BOTTOM)
    assert not occ._fits_exhaustive(11, 11, 6, 6, mask=OCC_BOTTOM)
    assert not occ._fits_exhaustive(21, 21, 4, 4, mask=OCC_BOTTOM)
    cc = ((0.5, 0.5, 2.0, 2.0, OCC_TOP),)
    assert not occ._fits_exhaustive(12, 28, 30, 10, mask=OCC_BOTTOM, comps=cc)
    assert occ._fits_exhaustive(12, 32.5, 30, 10, mask=OCC_BOTTOM, comps=cc)
    queries = [
        (15.0, 15.0, 10.0, 10.0, OCC_TOP, ()),
        (15.0, 15.0, 10.0, 10.0, OCC_BOTTOM, ()),
        (11.0, 11.0, 6.0, 6.0, OCC_BOTTOM, ()),
        (21.0, 21.0, 4.0, 4.0, OCC_BOTTOM, ()),
        (12.0, 28.0, 30.0, 10.0, OCC_BOTTOM, cc),
        (12.0, 32.5, 30.0, 10.0, OCC_BOTTOM, cc),
        (40.0, 40.0, 5.0, 5.0, OCC_PUNCH, ()),
    ]
    for x, y, w, h, m, c in queries:
        ex = occ._fits_exhaustive(x, y, w, h, mask=m, comps=c)
        ha = occ._fits_hashed(x, y, w, h, mask=m, comps=c)
        tr = occ._fits_traced(x, y, w, h, mask=m, comps=c)
        assert ex is ha is tr, (x, y, w, h, m)
    pos = occ.place_near(20, 20, 6, 6, mask=OCC_BOTTOM)
    assert pos is not None
    occ.remove(10, 10, 20, 20, mask=OCC_TOP, comps=comps)
    assert not occ.rects
    assert all(not v for v in occ._cells.values())


def test_punch_default_matches_legacy(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 60.0)
    monkeypatch.setattr(fp, "BOARD_H", 60.0)
    occ = _Occupancy()
    occ.add(10, 10, 15, 15)
    for m in (OCC_TOP, OCC_BOTTOM, OCC_PUNCH):
        assert not occ._fits_exhaustive(12, 12, 8, 8, mask=m)


def test_zero_optin_no_bottom_machinery(real_spec):
    """The INERTNESS control is the spec with every copper-face declaration
    stripped (the landed tree legitimately declares board_aux "either", so
    the raw spec is no longer the zero-opt-in world)."""
    stripped = dataclasses.replace(real_spec, interior={
        name: {k: v for k, v in entry.items()
               if k != "layer" and not (k == "side"
                                        and v in ("top", "bottom", "either"))}
        for name, entry in real_spec.interior.items()})
    zg0 = subsystem_zone_geometry(two_side=True, spec=stripped)
    for sheet, shapes in zg0.shapes.items():
        for s in shapes:
            assert s.side == "top", (sheet, s.tag)
            assert not s.mirror, (sheet, s.tag)
    assert not zg0.mirror_refs
    zg2 = apply_chosen_shapes(zg0, {})
    assert zg2 is zg0
    any_multi = next(s for s in sorted(zg0.shapes)
                     if len(zg0.shapes[s]) >= 2)
    zg3 = apply_chosen_shapes(zg0, {any_multi: 1})
    assert zg3.side_of == zg0.side_of
    assert zg3.resolvable == zg0.resolvable


def test_bottom_variant_offered_and_deterministic(zg_real, zg_either):
    a, b = zg_either
    sa = a.shapes["hdmi_rx_term"]
    sb = b.shapes["hdmi_rx_term"]
    assert sa == sb
    base = zg_real.shapes.get("hdmi_rx_term", ())
    assert sa[:len(base)] == base
    bots = [s for s in sa if s.side == "bottom"]
    assert bots, "declared-either sheet offered no bottom variant"
    s0 = sa[0]
    for bs in bots:
        assert (bs.w, bs.h) == (s0.w, s0.h)
        assert set(bs.top_off) == set(s0.top_off)
        assert set(bs.mirror) == set(bs.top_off)
        for r, (ox, oy) in s0.top_off.items():
            assert bs.top_off[r] == (round(bs.w - ox, 4), oy)
            assert bs.extra_rot[r] == \
                (180.0 - s0.extra_rot.get(r, 0.0)) % 360.0
        exp_sec = _mirror_offsets_x(
            s0.bot_off, a.bbox_of,
            {r: s0.extra_rot.get(r, 0.0) for r in s0.bot_off}, s0.w)
        assert bs.bot_off == exp_sec


def test_bottom_choice_flips_sides_by_membership(zg_either):
    a, _b = zg_either
    shapes = a.shapes["hdmi_rx_term"]
    k = next(i for i, s in enumerate(shapes) if s.side == "bottom")
    zg2 = apply_chosen_shapes(a, {"hdmi_rx_term": k})
    for r in shapes[k].top_off:
        assert zg2.side_of[r] == "bottom"
        assert a.side_of[r] == "top"
    for r in shapes[k].bot_off:
        assert zg2.side_of[r] == "top"
    untouched = {r: s for r, s in a.side_of.items()
                 if r not in shapes[k].top_off and r not in shapes[k].bot_off}
    for r, s in untouched.items():
        assert zg2.side_of[r] == s


def test_face_top_forced_secondary(zg_real):
    tp = next((r for r, m in sorted(zg_real.resolvable.items())
               if "TestPoint" in str(m)), None)
    assert tp is not None
    others = [r for r, m in sorted(zg_real.resolvable.items())
              if "0402" in str(m)][:2]
    refs = [tp, *others]
    side_of = {r: "top" for r in refs}
    t_off, b_off, _w, _h = _pack_one_zone(
        refs, side_of, zg_real.bbox_of, zg_real.resolvable,
        face_top=frozenset({tp}))
    assert tp in b_off and tp not in t_off
    assert all(r in t_off for r in others)


def test_conn_and_zoneless_declarations_raise(real_spec):
    spec_conn = dataclasses.replace(
        real_spec,
        edges={e: tuple(n for n in ns if n != "microsd")
               for e, ns in real_spec.edges.items()},
        interior={**real_spec.interior, "microsd": {"side": "either"}})
    with pytest.raises(ValueError, match="seated off-board connector"):
        subsystem_zone_geometry(two_side=True, spec=spec_conn)
    spec_mech = dataclasses.replace(
        real_spec, interior={**real_spec.interior,
                             "mechanical": {"side": "bottom"}})
    with pytest.raises(ValueError, match="no packable zone"):
        subsystem_zone_geometry(two_side=True, spec=spec_mech)
