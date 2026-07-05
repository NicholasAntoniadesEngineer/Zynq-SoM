"""Tests for the STAGE-TEMPLATE placement engine (schgen/generate/pcb/
stage_templates) — the Phase-L ``power`` pilot.

Four layers, in the order the spec ranks them:

(1) BYTE-IDENTITY for every OTHER sheet — the decisive regression test. Compute
    the shared ZoneGeom once with the placement-contract registry DISABLED
    (``load_contract`` monkeypatched to return None everywhere) and once ENABLED,
    and assert every per-sheet field (zone_box / top_off / bot_off / side_of /
    conn_rot / zone_extra_rot) is EXACTLY equal for every sheet except ``power``.
    The template must touch nothing but its own contracted zone.

(2) GATE-GREEN integration — build the real board with the template active and
    assert ``placement_contract_gate.check`` returns ok=True, 0 violations, no
    unresolved refs. The full summary is printed for the orchestrator.

(3) UNIT — the template output is deterministic (two runs identical); every
    contract member lands top-side; and no two members' courtyards overlap within
    the zone (reusing the gate's pad boxes + PLACE_CLEAR halo).

The build_model-backed tests are module-scoped fixtures (~60-120 s each) so the
board is built at most a couple of times.
"""

from __future__ import annotations

import pytest

from schgen.generate.pcb import stage_templates as T
from schgen.generate.pcb.constants import PLACE_CLEAR
from schgen.verify import placement_contract_gate as g

_POWER = "power"
# Every engine-WIRED sheet gets a stage template, so its zone geometry LEGITIMATELY
# differs registry-on vs -off; only these sheets may change. usb_pd joined in the
# D11 wave (its proximity-cluster template). Read the live set so a future wiring
# needs no test edit.
_WIRED = set(g._WIRED_SHEETS)


# ---------------------------------------------------------------------------
# BOARD-GROWTH KNOB invariants (frozen datasheet template)
# ---------------------------------------------------------------------------

def test_template_clear_frozen_at_baseline():
    """The datasheet-stage geometry must use TEMPLATE_CLEAR, FROZEN at the
    byte-identical baseline, so a board-growth PLACE_CLEAR never slides a
    contract member past its datasheet window nor collapses a template zone.
    Guards the frozen-template swap (constants.TEMPLATE_CLEAR ==
    PLACE_CLEAR_BASELINE, and stage_templates imports it)."""
    from schgen.generate.pcb.constants import (
        PLACE_CLEAR_BASELINE,
        TEMPLATE_CLEAR,
    )
    assert TEMPLATE_CLEAR == PLACE_CLEAR_BASELINE == 0.5
    assert T.TEMPLATE_CLEAR == 0.5           # the name the templates actually use


def test_place_clear_env_default_is_baseline(monkeypatch):
    """With SCHGEN_PLACE_CLEAR unset, PLACE_CLEAR is the baseline 0.5 (shipping
    board byte-identical). A set value is read as a float; a malformed value
    fails loudly."""
    import importlib

    from schgen.generate.pcb import constants as C
    monkeypatch.delenv("SCHGEN_PLACE_CLEAR", raising=False)
    importlib.reload(C)
    assert C.PLACE_CLEAR == 0.5
    monkeypatch.setenv("SCHGEN_PLACE_CLEAR", "0.82")
    importlib.reload(C)
    assert C.PLACE_CLEAR == 0.82
    monkeypatch.setenv("SCHGEN_PLACE_CLEAR", "not-a-float")
    with pytest.raises(ValueError):
        importlib.reload(C)
    # restore the module to the baseline value for any later test in this session
    monkeypatch.delenv("SCHGEN_PLACE_CLEAR", raising=False)
    importlib.reload(C)


# ---------------------------------------------------------------------------
# helpers to drive subsystem_zone_geometry with the registry on/off
# ---------------------------------------------------------------------------

def _zone_geom_with_contract(enabled: bool):
    """Compute the shared ZoneGeom with the placement-contract registry either
    ENABLED (real) or DISABLED (``load_contract`` -> None for every sheet, so the
    template hook always falls through to the legacy packer). Restores the real
    loader afterwards."""
    from schgen.generate.pcb import placement
    real = g.load_contract
    try:
        if not enabled:
            g.load_contract = lambda _sheet: None      # type: ignore[assignment]
        return placement.subsystem_zone_geometry(two_side=True)
    finally:
        g.load_contract = real                          # type: ignore[assignment]


# ---------------------------------------------------------------------------
# (1) BYTE-IDENTITY for every sheet except `power`
# ---------------------------------------------------------------------------

def test_every_other_sheet_is_byte_identical():
    """The decisive regression test: enabling the templates changes ONLY the
    engine-WIRED zones (``power`` + ``usb_pd``); every OTHER sheet's geometry is
    byte-identical (the legacy packer is untouched)."""
    off = _zone_geom_with_contract(enabled=False)
    on = _zone_geom_with_contract(enabled=True)

    sheets = set(off.zone_box) | set(on.zone_box)
    assert _POWER in sheets
    changed = []
    for sheet in sorted(sheets):
        if sheet in _WIRED:
            continue
        same = (
            off.zone_box.get(sheet) == on.zone_box.get(sheet)
            and off.top_off.get(sheet) == on.top_off.get(sheet)
            and off.bot_off.get(sheet) == on.bot_off.get(sheet))
        if not same:
            changed.append(sheet)
    assert not changed, f"template perturbed non-wired sheets: {changed}"

    # per-ref side / conn_rot / zone_extra_rot: identical for every ref that is
    # NOT a wired-sheet ref (the templates' same-side override + rotations are the
    # only intended deltas, and they live entirely on the wired sheets).
    wired_refs: set[str] = set()
    for s in _WIRED:
        wired_refs |= set(on.refs_by_sheet.get(s, [])) \
            | set(off.refs_by_sheet.get(s, []))
    for ref in set(off.side_of) | set(on.side_of):
        if ref in wired_refs:
            continue
        assert off.side_of.get(ref) == on.side_of.get(ref), \
            f"side_of[{ref}] changed off={off.side_of.get(ref)} " \
            f"on={on.side_of.get(ref)}"
    for ref in set(off.conn_rot) | set(on.conn_rot):
        if ref in wired_refs:
            continue
        assert off.conn_rot.get(ref) == on.conn_rot.get(ref), ref
    for ref in set(off.zone_extra_rot) | set(on.zone_extra_rot):
        if ref in wired_refs:
            continue
        assert off.zone_extra_rot.get(ref) == on.zone_extra_rot.get(ref), ref

    # and the wired zones MUST have actually changed (proves the templates ran).
    for s in _WIRED:
        assert off.zone_box.get(s) != on.zone_box.get(s), \
            f"the template did not change the {s} zone at all"


# ---------------------------------------------------------------------------
# (3) UNIT — determinism, top-side, no courtyard overlap (no board build)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _power_inputs():
    """side_of / bbox_of / resolvable / refs for the ``power`` sheet, built the
    SAME way subsystem_zone_geometry does (per-sheet decoupling classification on
    the board-unique ref namespace), so build_zone gets exactly its real inputs —
    with no full board build."""
    from schgen.core.link import load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb.footprint import _footprint_bbox, resolve_mod
    from schgen.generate.pcb.placement import _classify_side, _decoupling_caps

    band = g._board_refs_by_sheet(_POWER)  # noqa: F841 — force the band load path
    idx = 20                               # power sheet band (carrier/sheet_index)
    sc = load_subsystem(_POWER)
    snets: dict[str, list[PinRef]] = {}
    for nname, net in sc.circuit.nets.items():
        snets[nname] = [
            PinRef(_renamed_ref(p.ref, idx, sheet=_POWER)
                   if not p.ref.startswith("#") else p.ref, p.pin)
            for p in net.pins]
    sdec = _decoupling_caps(snets)
    refs: list[str] = []
    side_of: dict[str, str] = {}
    bbox_of: dict[str, tuple] = {}
    resolvable: dict = {}
    for ref, part in sc.circuit.parts.items():
        bref = _renamed_ref(ref, idx, sheet=_POWER)
        mod = resolve_mod(part.footprint)
        if mod is None:
            continue
        resolvable[bref] = mod
        bbox_of[bref] = _footprint_bbox(mod)
        side_of[bref] = _classify_side(bref, part.lib_id, bbox_of[bref], sdec,
                                       True)
        refs.append(bref)
    return refs, side_of, bbox_of, resolvable


def _run_template(inputs):
    refs, side_of, bbox_of, resolvable = inputs
    # force the same-side override the hook applies before templating
    side = dict(side_of)
    for m in T.contract_member_brefs(_POWER, g.load_contract(_POWER),
                                     resolvable):
        side[m] = "top"
    rot: dict[str, float] = {}
    res = T.build_zone(_POWER, g.load_contract(_POWER), refs, side, bbox_of,
                       resolvable, rot)
    return res, rot, side


def test_template_is_deterministic(_power_inputs):
    """Two runs produce byte-identical offsets / zone / rotations."""
    r1, rot1, _ = _run_template(_power_inputs)
    r2, rot2, _ = _run_template(_power_inputs)
    assert r1 is not None and r2 is not None
    assert r1 == r2, "template output is not deterministic"
    assert rot1 == rot2


def test_all_contract_members_are_top_side(_power_inputs):
    """Every constructed member is on the top offset map (never bottom) — the
    same_side override (SNVSBD5D 11.1 loop-area rule)."""
    (top_off, bot_off, _zw, _zh), _rot, _side = _run_template(_power_inputs)
    members = T.contract_member_brefs(
        _POWER, g.load_contract(_POWER), _power_inputs[3])
    for m in members:
        assert m in top_off, f"contract member {m} not placed top-side"
        assert m not in bot_off, f"contract member {m} landed on the bottom"


def test_no_courtyard_overlap_in_zone(_power_inputs):
    """No two placed parts' courtyards overlap within the emitted zone (reusing
    the gate's pad boxes + a PLACE_CLEAR halo — the template asserts this by
    construction and widens gaps on any collision)."""
    (top_off, bot_off, _zw, _zh), rot, _side = _run_template(_power_inputs)
    _refs, _side_in, bbox_of, resolvable = _power_inputs
    from schgen.generate.pcb.mating_face import _rot_bbox_cw

    # Courtyard overlap is a PER-SIDE property: a TOP part and a BOTTOM part at the
    # same XY do NOT collide (different copper layers) — this is exactly how the
    # legacy packer overlays its top+bottom sub-packs on one XY area, and the
    # template's leftovers follow suit. Check overlaps WITHIN each side only (top
    # holds every contract member + top leftovers; bottom holds bottom leftovers).
    # Bbox transform is SIDE-INDEPENDENT (unified no-bottom-mirror convention).
    for off in (top_off, bot_off):
        boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        for ref, (ox, oy) in off.items():
            rb = _rot_bbox_cw(bbox_of[ref], rot.get(ref, 0.0))
            boxes.append((ref, (ox + rb[0], oy + rb[1], ox + rb[2], oy + rb[3])))
        halo = PLACE_CLEAR / 2.0
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i][1], boxes[j][1]
                overlap = (a[0] - halo < b[2] and a[2] + halo > b[0]
                           and a[1] - halo < b[3] and a[3] + halo > b[1])
                assert not overlap, (
                    f"courtyard overlap: {boxes[i][0]} {a} vs {boxes[j][0]} {b}")


def test_bulk_out_caps_seated_at_inductor_output(_power_inputs):
    """v2: the template seats every COUT (bulk_out) cap within the contract's
    5 mm bound of its stage's inductor OUTPUT pad, on the top side. Reads the
    contract to find the caps/inductor, then measures with the gate's pad boxes —
    the same measure the gate applies to the emitted board."""
    (top_off, _bot_off, _zw, _zh), rot, _side = _run_template(_power_inputs)
    contract = g.load_contract(_POWER)
    band = g._board_refs_by_sheet(_POWER)
    _refs, _side_in, _bbox, resolvable = _power_inputs

    def pad_boxes(bref):
        off = top_off[bref]
        rel = g._pad_boxes(resolvable[bref], rot.get(bref, 0.0))
        return {n: (off[0] + b[0], off[1] + b[1], off[0] + b[2], off[1] + b[3])
                for n, b in rel.items()}

    checked = 0
    for st in contract["structures"]:
        if st.get("type") != "bulk_out":
            continue
        l_bref = band[st["inductor"]]
        l_out = pad_boxes(l_bref)[st["inductor_out_pin"]]
        lim = float(st["max_pad_to_pin_mm"])
        for cap in st["caps"]:
            cb = band[cap]
            assert cb in top_off, f"COUT {cap} not top-side"
            d = min(g._box_gap(l_out, pb) for pb in pad_boxes(cb).values())
            assert d <= lim, f"COUT {cap} {d:.2f}mm > {lim}mm to {st['inductor']}"
            checked += 1
    assert checked >= 5, f"expected the 5 buck COUT caps, checked {checked}"


def test_power_zone_width_within_budget(_power_inputs):
    """v2 acceptance (hard): the rebuilt power ZONE width is <= 48 mm — the
    multi-row layout search stacked the bucks so the E-band no longer inflates."""
    (_top, _bot, zw, _zh), _rot, _side = _run_template(_power_inputs)
    assert zw <= 48.0, f"power zone width {zw:.2f}mm exceeds the 48 mm budget"


# ---------------------------------------------------------------------------
# (1b) PROXIMITY-CLUSTER template — usb_pd (D11 wiring), no board build
# ---------------------------------------------------------------------------
# The generic proximity-cluster builder anchors the IC at the origin and seats the
# 6-part FUSB302B bypass/CC network by the SAME backtracking search the buck uses.
# These drive build_zone on usb_pd's REAL inputs (its band + footprints), with NO
# full board build, and assert: it produces a result, it is deterministic, every
# member lands top-side, and the emitted geometry PASSES usb_pd's intra-zone gate.

_USB_PD = "usb_pd"


def _subsystem_inputs(sheet: str):
    """side_of / bbox_of / resolvable / refs for ``sheet``, built the SAME way
    subsystem_zone_geometry does (per-sheet decoupling classification on the
    board-unique ref namespace), so build_zone gets its real inputs — no board
    build. Mirrors ``_power_inputs`` for an arbitrary contracted sheet."""
    import json

    from schgen.core.link import load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb.constants import CARRIER
    from schgen.generate.pcb.footprint import _footprint_bbox, resolve_mod
    from schgen.generate.pcb.placement import _classify_side, _decoupling_caps

    idx = json.loads((CARRIER / "sheet_index.json").read_text())[sheet]
    sc = load_subsystem(sheet)
    snets = {n: [PinRef(_renamed_ref(p.ref, idx, sheet=sheet)
                        if not p.ref.startswith("#") else p.ref, p.pin)
                 for p in net.pins] for n, net in sc.circuit.nets.items()}
    sdec = _decoupling_caps(snets)
    refs, side_of, bbox_of, resolvable = [], {}, {}, {}
    for ref, part in sc.circuit.parts.items():
        bref = _renamed_ref(ref, idx, sheet=sheet)
        mod = resolve_mod(part.footprint)
        if mod is None:
            continue
        resolvable[bref] = mod
        bbox_of[bref] = _footprint_bbox(mod)
        side_of[bref] = _classify_side(bref, part.lib_id, bbox_of[bref], sdec,
                                       True)
        refs.append(bref)
    return refs, side_of, bbox_of, resolvable


@pytest.fixture(scope="module")
def _usb_pd_inputs():
    return _subsystem_inputs(_USB_PD)


def _run_prox(inputs):
    refs, side_of, bbox_of, resolvable = inputs
    contract = g.load_contract(_USB_PD)
    side = dict(side_of)
    for m in T.contract_member_brefs(_USB_PD, contract, resolvable):
        side[m] = "top"
    rot: dict[str, float] = {}
    res = T.build_zone(_USB_PD, contract, refs, side, bbox_of, resolvable, rot)
    return res, rot, side, contract


def test_proximity_zone_is_deterministic(_usb_pd_inputs):
    """Two runs of the proximity-cluster template are byte-identical (no
    randomness — the same discipline as the buck template)."""
    r1, rot1, _, _ = _run_prox(_usb_pd_inputs)
    r2, rot2, _, _ = _run_prox(_usb_pd_inputs)
    assert r1 is not None and r1 == r2, "proximity template not deterministic"
    assert rot1 == rot2


def test_proximity_all_members_top_side(_usb_pd_inputs):
    """Every one of usb_pd's 6 contracted parts (U1 + the 5 caps) lands on the
    top offset map — the same_side override (FUSB302B EVB co-location)."""
    (top_off, bot_off, _zw, _zh), _rot, _side, _c = _run_prox(_usb_pd_inputs)
    members = T.contract_member_brefs(_USB_PD, g.load_contract(_USB_PD),
                                      _usb_pd_inputs[3])
    assert len(members) == 6, sorted(members)
    for m in members:
        assert m in top_off, f"proximity member {m} not placed top-side"
        assert m not in bot_off, f"proximity member {m} landed on the bottom"


def test_proximity_zone_passes_its_own_gate(_usb_pd_inputs):
    """The emitted proximity geometry PASSES usb_pd's intra-zone placement
    contract (all 5 proximity structures + same_side), measured with the gate's
    pad boxes — the same measure the gate applies to the real board."""
    (top_off, _bot, _zw, _zh), rot, _side, contract = _run_prox(_usb_pd_inputs)
    band = g._board_refs_by_sheet(_USB_PD)
    _refs, _si, _bb, resolvable = _usb_pd_inputs

    ZX, ZY = 30.0, 40.0
    from schgen.generate.pcb import (
        ORIGIN_X,
        ORIGIN_Y,
        FootprintInst,
        PcbModel,
    )
    from schgen.generate.pcb.footprint import pad_names
    insts = []
    for r, (dx, dy) in top_off.items():
        mod = resolvable[r]
        insts.append(FootprintInst(
            ref=r, value="x", footprint="x",
            x=ORIGIN_X + ZX + dx, y=ORIGIN_Y + ZY + dy,
            rotation=rot.get(r, 0.0),
            pad_nets={p: (0, "") for p in pad_names(mod)},
            mod_path=mod, sheet=_USB_PD, side="top"))
    m = PcbModel(board_w=170.0, board_h=145.0, insts=insts,
                 net_numbers={"": 0}, netclass_of={}, classes={},
                 placed=len(insts), deferred=[], n_top=len(insts), n_bottom=0,
                 two_side=True)
    res = g.check(m, sheet_name=_USB_PD, contract=contract, ref_map=band)
    print("\n" + res.summary())
    assert res.ok, res.summary()
    assert res.proximity_fail == 0 and res.same_side_fail == 0, res.summary()


# ---------------------------------------------------------------------------
# (2) GATE-GREEN integration — the template makes the real board pass
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _real_model():
    """Build the REAL board ONCE with the template active (~60-120 s)."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


def test_gate_is_green_on_the_templated_board(_real_model):
    """The placement-contract gate PASSES every WIRED sheet's zone (power + the
    usb_pd proximity cluster): ok=True, no violations, no unresolved refs. Prints
    each summary for the orchestrator."""
    for sheet in sorted(g._WIRED_SHEETS):
        res = g.check(_real_model, sheet)
        print(f"\n--- {sheet} ---\n" + res.summary())
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], f"{sheet} unresolved refs: {res.missing_refs}"
        assert res.ok is True, res.summary()
        assert not res.violations, res.summary()


def test_wired_zone_coordinate_dumps(_real_model):
    """Print a sorted (ref, x, y, rot, side) dump of every WIRED zone (power +
    usb_pd) so the orchestrator can pre-check the layout before rendering. Always
    passes — it is a report."""
    for sheet in sorted(g._WIRED_SHEETS):
        rows = sorted(
            (i.ref, round(i.x, 3), round(i.y, 3), round(i.rotation, 1), i.side)
            for i in _real_model.insts if i.sheet == sheet)
        print(f"\n{sheet} zone: {len(rows)} parts")
        for ref, x, y, rot, s in rows:
            print(f"  {ref:8} x={x:9.3f} y={y:9.3f} rot={rot:5.1f} {s}")
        assert rows
