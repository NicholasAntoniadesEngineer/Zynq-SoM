"""WAVE-13 — face=top parts LIFTED out of a rigid stage template.

The defect closed: a CONTRACTED sheet's bottom variant was all-or-nothing, so a
handful of test points and LEDs packed by the datasheet template on the primary
side VETOED the whole sheet from bottom eligibility (the biggest blocks on the
carrier — `power`, `usb_jtag`, `power_som`, `uart_bridge`). The lift moves those
parts into the SECONDARY pack (which emits F.Cu inside a bottom-assigned block)
and moves NOTHING else.

Every test here is a property of the mechanism, not of one board: the stage
survives the lift byte-exactly, the lifted part presents on the top face while
its block's primary is on B.Cu, a lift that would move CONTRACT-CONSTRUCTED
geometry is refused through the registered fallback (never forced), the
seated-connector refusals still stand, and the emitted board is gated — a
user-facing part on B.Cu FAILS LAW 6.
"""

from __future__ import annotations

import dataclasses

import pytest

from schgen.core import fallbacks as fb
from schgen.generate import pcb
from schgen.generate.floorplan import load_floorplan_spec
from schgen.generate.pcb import FootprintInst, PcbModel
from schgen.generate.pcb.placement import (
    _bottom_zone_shapes,
    _is_face_top_part,
    _lift_face_top,
    _mirror_offsets_x,
    apply_chosen_shapes,
    subsystem_zone_geometry,
)
from schgen.verify import placement_mech as pm

LIFT_SHEETS = ("power", "usb_jtag", "power_som", "uart_bridge")


@pytest.fixture(scope="module")
def real_spec():
    return load_floorplan_spec()


@pytest.fixture(scope="module")
def zg_lift(real_spec):
    interior = dict(real_spec.interior)
    for s in LIFT_SHEETS:
        interior[s] = {**interior[s], "layer": "either"}
    spec = dataclasses.replace(real_spec, interior=interior)
    return subsystem_zone_geometry(two_side=True, spec=spec)


def _bottom_shape(zg, sheet):
    return next(s for s in zg.shapes[sheet] if s.side == "bottom")


def test_every_vetoed_sheet_now_offers_a_bottom_variant(zg_lift):
    """The four sheets the veto locked out are bottom-eligible again, and the
    face=top parts that caused the veto are all on the SECONDARY (F.Cu) side."""
    for sheet in LIFT_SHEETS:
        shp = _bottom_shape(zg_lift, sheet)
        face_top = {r for r in zg_lift.refs_by_sheet[sheet]
                    if _is_face_top_part(r, "", str(zg_lift.resolvable[r]))
                    or r.startswith(("TP", "SW", "LED"))}
        assert face_top, f"{sheet} has no face=top part — wrong fixture sheet"
        assert not (face_top & set(shp.top_off)), \
            f"{sheet}: a user-facing part stayed in the B.Cu primary pack"
        assert face_top <= set(shp.bot_off), \
            f"{sheet}: a user-facing part is in neither pack"


def test_the_stage_is_never_reflowed_by_the_lift(zg_lift):
    """Every part that STAYS in the primary keeps its datasheet stage offset
    exactly: the bottom primary is the pure X-mirror of shape 0's template
    offsets about the zone mid-axis, part for part — and the pre-existing
    SECONDARY offsets are the same box-preserving mirror they always were. Only
    the lifted refs are new."""
    for sheet in LIFT_SHEETS:
        tmpl = zg_lift.shapes[sheet][0]
        shp = _bottom_shape(zg_lift, sheet)
        assert (shp.w, shp.h) == (tmpl.w, tmpl.h), \
            f"{sheet}: the lift grew the zone box"
        lifted = set(tmpl.top_off) - set(shp.top_off)
        assert lifted, f"{sheet}: nothing was lifted"
        assert set(shp.top_off) == set(tmpl.top_off) - lifted
        for r, (ox, oy) in tmpl.top_off.items():
            if r in lifted:
                continue
            assert shp.top_off[r] == (round(shp.w - ox, 4), oy), \
                f"{sheet}/{r}: the stage moved under the lift"
        want = _mirror_offsets_x(
            tmpl.bot_off, zg_lift.bbox_of,
            {r: tmpl.extra_rot.get(r, 0.0) for r in tmpl.bot_off}, shp.w)
        for r, off in want.items():
            assert shp.bot_off[r] == off, \
                f"{sheet}/{r}: an existing secondary part moved under the lift"


def test_a_lifted_part_emits_top_copper_while_its_block_primary_is_bottom(
        zg_lift):
    """The whole point: bind the bottom shape and the lifted TP/LED/SW is on
    the board TOP face while the block it belongs to is on B.Cu."""
    for sheet in LIFT_SHEETS:
        idx = next(k for k, s in enumerate(zg_lift.shapes[sheet])
                   if s.side == "bottom")
        shp = zg_lift.shapes[sheet][idx]
        bound = apply_chosen_shapes(zg_lift, {sheet: idx})
        lifted = set(zg_lift.shapes[sheet][0].top_off) - set(shp.top_off)
        for r in lifted:
            assert bound.side_of[r] == "top", \
                f"{sheet}/{r}: a user-facing part bound face-down"
            assert r not in bound.mirror_refs, \
                f"{sheet}/{r}: a top-facing part was bound to a mirrored doc"
        assert shp.top_off, f"{sheet}: the bottom primary is empty"
        for r in shp.top_off:
            assert bound.side_of[r] == "bottom"
            assert r in bound.mirror_refs


def test_a_contract_constructed_face_top_part_is_refused_not_forced(zg_lift):
    """A face=top part that the CONTRACT itself places is load-bearing stage
    geometry — lifting it would move a part the contract owns, so the whole
    bottom variant is refused through the registered fallback. Loud, counted,
    never a silent drop and never a forced lift."""
    sheet = "power"
    tmpl = zg_lift.shapes[sheet][0]
    victim = next(r for r in sorted(tmpl.top_off)
                  if not _is_face_top_part(r, "", str(zg_lift.resolvable[r]))
                  and not r.startswith(("TP", "SW", "LED")))
    fb.reset()
    out = _bottom_zone_shapes(
        sheet, zg_lift.refs_by_sheet[sheet], zg_lift.side_of, zg_lift.bbox_of,
        zg_lift.resolvable, frozenset({victim}),
        (tmpl.top_off, tmpl.bot_off, tmpl.w, tmpl.h), tmpl.extra_rot,
        frozenset({victim}))
    assert out == [], "a contract-constructed lift must not be offered"
    assert fb.census()["bottom_variant_contract_reject"] == 1, fb.census()
    fb.reset()
    ok = _bottom_zone_shapes(
        sheet, zg_lift.refs_by_sheet[sheet], zg_lift.side_of, zg_lift.bbox_of,
        zg_lift.resolvable, frozenset({victim}),
        (tmpl.top_off, tmpl.bot_off, tmpl.w, tmpl.h), tmpl.extra_rot,
        frozenset())
    assert len(ok) == 1, "the same lift is legal when the part is not a member"
    assert fb.census()["bottom_variant_contract_reject"] == 0


def test_lift_keeps_the_lifted_part_off_every_primary_through_hole_pad(zg_lift):
    """A lifted part seats on the opposite copper face, so only THROUGH-HOLE
    pad copper (present on every layer) can collide. The lift reserves against
    exactly those parts and against every secondary courtyard."""
    from schgen.generate.pcb.constants import PLACE_CLEAR
    from schgen.generate.pcb.footprint import has_thru_pads
    from schgen.generate.pcb.mating_face import _rot_bbox_cw
    for sheet in LIFT_SHEETS:
        tmpl = zg_lift.shapes[sheet][0]
        rot = tmpl.extra_rot
        keep, sec, _w, _h = _lift_face_top(
            tmpl.top_off, tmpl.bot_off, tmpl.w, tmpl.h,
            sorted(set(tmpl.top_off)
                   - set(_bottom_shape(zg_lift, sheet).top_off)),
            zg_lift.bbox_of, zg_lift.resolvable, rot)

        def _box(r, off, _rot=rot):
            cb = _rot_bbox_cw(zg_lift.bbox_of[r], _rot.get(r, 0.0))
            return (off[0] + cb[0], off[1] + cb[1],
                    off[0] + cb[2], off[1] + cb[3])

        gap = PLACE_CLEAR - 1e-6
        hazards = [_box(r, o) for r, o in keep.items()
                   if has_thru_pads(zg_lift.resolvable[r])]
        boxes = [(r, _box(r, o)) for r, o in sec.items()]
        for i, (ra, a) in enumerate(boxes):
            for rb, b in boxes[i + 1:]:
                assert (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                        or a[3] + gap <= b[1] or b[3] + gap <= a[1]), \
                    f"{sheet}: secondary {ra} and {rb} overlap after the lift"
            for h in hazards:
                assert (a[2] + gap <= h[0] or h[2] + gap <= a[0]
                        or a[3] + gap <= h[1] or h[3] + gap <= a[1]), \
                    f"{sheet}: secondary {ra} sits on primary THT pad copper"


def test_seated_connector_sheets_still_refuse_bottom(real_spec):
    """The lift extends the TEMPLATE, not the eligibility rules: a sheet with a
    seated off-board connector, a connector-class part, or no packable zone
    still raises when it declares a copper face."""
    spec_conn = dataclasses.replace(
        real_spec,
        edges={e: tuple(n for n in ns if n != "microsd")
               for e, ns in real_spec.edges.items()},
        interior={**real_spec.interior, "microsd": {"side": "either"}})
    with pytest.raises(ValueError, match="seated off-board connector"):
        subsystem_zone_geometry(two_side=True, spec=spec_conn)
    spec_cls = dataclasses.replace(
        real_spec, interior={**real_spec.interior,
                             "debug_boot": {"side": "N", "layer": "either"}})
    with pytest.raises(ValueError, match="connector-class part"):
        subsystem_zone_geometry(two_side=True, spec=spec_cls)
    spec_mech = dataclasses.replace(
        real_spec, interior={**real_spec.interior,
                             "mechanical": {"side": "bottom"}})
    with pytest.raises(ValueError, match="no packable zone"):
        subsystem_zone_geometry(two_side=True, spec=spec_mech)


def _tp_model(side: str) -> PcbModel:
    mod = pcb.resolve_mod("TestPoint:TestPoint_Pad_D1.0mm")
    assert mod is not None
    tp = FootprintInst(ref="TP1", value="TP",
                       footprint="TestPoint:TestPoint_Pad_D1.0mm",
                       x=pcb.ORIGIN_X + 20, y=pcb.ORIGIN_Y + 20, rotation=0.0,
                       pad_nets={}, mod_path=mod, sheet="t", side=side)
    return PcbModel(board_w=60.0, board_h=40.0, insts=[tp],
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=1, deferred=[], som_core=None)


def test_law6_gate_fails_a_user_facing_part_on_bottom_copper():
    """The emitted-board arbiter: a test point on B.Cu is unprobeable, so LAW 6
    FAILS it — the same predicate the placer classifies with, so the gate can
    never under-detect what the lift is responsible for."""
    good = pm.check(_tp_model("top"))
    assert good.ok and good.n_face_top == 1 and not good.face_top_on_bottom
    bad = pm.check(_tp_model("bottom"))
    assert not bad.ok, "a face-down test point must FAIL LAW 6"
    assert any("TP1" in r for r in bad.face_top_on_bottom), bad.summary()
    assert "FACE-DOWN" in bad.summary()
