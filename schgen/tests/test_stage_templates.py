from __future__ import annotations

import pytest

from schgen.generate.pcb import stage_templates as T
from schgen.generate.pcb.constants import PLACE_CLEAR
from schgen.verify import placement_contract_gate as g

_POWER = "power"
_WIRED = set(g._WIRED_SHEETS)


def test_template_clear_frozen_at_baseline():
    from schgen.generate.pcb.constants import (
        PLACE_CLEAR_BASELINE,
        TEMPLATE_CLEAR,
    )
    assert TEMPLATE_CLEAR == PLACE_CLEAR_BASELINE == 0.5
    assert T.TEMPLATE_CLEAR == 0.5


def test_place_clear_env_default_is_baseline(monkeypatch):
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
    monkeypatch.delenv("SCHGEN_PLACE_CLEAR", raising=False)
    importlib.reload(C)


def _zone_geom_with_contract(enabled: bool):
    from schgen.generate.pcb import placement
    real = g.load_contract
    try:
        if not enabled:
            g.load_contract = lambda _sheet: None      # type: ignore[assignment]
        return placement.subsystem_zone_geometry(two_side=True)
    finally:
        g.load_contract = real                          # type: ignore[assignment]


def test_every_other_sheet_is_byte_identical():
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

    for s in _WIRED:
        assert off.zone_box.get(s) != on.zone_box.get(s), \
            f"the template did not change the {s} zone at all"


@pytest.fixture(scope="module")
def _power_inputs():
    from schgen.core.link import load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb.footprint import _footprint_bbox, resolve_mod
    from schgen.generate.pcb.placement import _classify_side, _decoupling_caps

    band = g._board_refs_by_sheet(_POWER)  # noqa: F841
    idx = 20
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
    side = dict(side_of)
    for m in T.contract_member_brefs(_POWER, g.load_contract(_POWER),
                                     resolvable):
        side[m] = "top"
    rot: dict[str, float] = {}
    res = T.build_zone(_POWER, g.load_contract(_POWER), refs, side, bbox_of,
                       resolvable, rot)
    return res, rot, side


def test_template_is_deterministic(_power_inputs):
    r1, rot1, _ = _run_template(_power_inputs)
    r2, rot2, _ = _run_template(_power_inputs)
    assert r1 is not None and r2 is not None
    assert r1 == r2, "template output is not deterministic"
    assert rot1 == rot2


def test_all_contract_members_are_top_side(_power_inputs):
    (top_off, bot_off, _zw, _zh), _rot, _side = _run_template(_power_inputs)
    members = T.contract_member_brefs(
        _POWER, g.load_contract(_POWER), _power_inputs[3])
    for m in members:
        assert m in top_off, f"contract member {m} not placed top-side"
        assert m not in bot_off, f"contract member {m} landed on the bottom"


def test_no_courtyard_overlap_in_zone(_power_inputs):
    (top_off, bot_off, _zw, _zh), rot, _side = _run_template(_power_inputs)
    _refs, _side_in, bbox_of, resolvable = _power_inputs
    from schgen.generate.pcb.mating_face import _rot_bbox_cw

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
    (_top, _bot, zw, _zh), _rot, _side = _run_template(_power_inputs)
    assert zw <= 48.0, f"power zone width {zw:.2f}mm exceeds the 48 mm budget"


_USB_PD = "usb_pd"


def _hook_facing(sheet: str, contract: dict) -> str | None:
    from schgen.generate.pcb.placement import _downstream_facing, _media_facing
    return _downstream_facing(sheet, contract) or _media_facing(sheet, contract)


def _subsystem_inputs(sheet: str):
    import json

    from schgen.core.link import load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb.constants import CARRIER, CONN_MATING_FACE
    from schgen.generate.pcb.footprint import _footprint_bbox, resolve_mod
    from schgen.generate.pcb.mating_face import connector_edge_rotation
    from schgen.generate.pcb.placement import (
        _classify_side,
        _connector_sheet_edges,
        _decoupling_caps,
    )

    idx = json.loads((CARRIER / "sheet_index.json").read_text())[sheet]
    sc = load_subsystem(sheet)
    snets = {n: [PinRef(_renamed_ref(p.ref, idx, sheet=sheet)
                        if not p.ref.startswith("#") else p.ref, p.pin)
                 for p in net.pins] for n, net in sc.circuit.nets.items()}
    sdec = _decoupling_caps(snets)
    edge = _connector_sheet_edges().get(sheet)
    refs, side_of, bbox_of, resolvable = [], {}, {}, {}
    conn_rot: dict[str, float] = {}
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
        if part.value in CONN_MATING_FACE and edge is not None:
            conn_rot[bref] = connector_edge_rotation(
                CONN_MATING_FACE[part.value], edge)
    outer_dir = edge if conn_rot else None
    return refs, side_of, bbox_of, resolvable, conn_rot, outer_dir


@pytest.fixture(scope="module")
def _usb_pd_inputs():
    return _subsystem_inputs(_USB_PD)


def _run_prox(inputs):
    refs, side_of, bbox_of, resolvable, conn_rot, outer_dir = inputs
    contract = g.load_contract(_USB_PD)
    side = dict(side_of)
    for m in T.contract_member_brefs(_USB_PD, contract, resolvable):
        side[m] = "top"
    rot: dict[str, float] = {}
    res = T.build_zone(_USB_PD, contract, refs, side, bbox_of, resolvable, rot,
                       facing=_hook_facing(_USB_PD, contract),
                       outer_dir=outer_dir)
    for bref, r in conn_rot.items():
        rot[bref] = (r + rot.get(bref, 0.0)) % 360.0
    return res, rot, side, contract


def test_proximity_zone_is_deterministic(_usb_pd_inputs):
    r1, rot1, _, _ = _run_prox(_usb_pd_inputs)
    r2, rot2, _, _ = _run_prox(_usb_pd_inputs)
    assert r1 is not None and r1 == r2, "proximity template not deterministic"
    assert rot1 == rot2


def test_proximity_all_members_top_side(_usb_pd_inputs):
    (top_off, bot_off, _zw, _zh), _rot, _side, _c = _run_prox(_usb_pd_inputs)
    members = T.contract_member_brefs(_USB_PD, g.load_contract(_USB_PD),
                                      _usb_pd_inputs[3])
    assert len(members) == 6, sorted(members)
    for m in members:
        assert m in top_off, f"proximity member {m} not placed top-side"
        assert m not in bot_off, f"proximity member {m} landed on the bottom"


def test_proximity_zone_passes_its_own_gate(_usb_pd_inputs):
    (top_off, _bot, _zw, _zh), rot, _side, contract = _run_prox(_usb_pd_inputs)
    band = g._board_refs_by_sheet(_USB_PD)
    resolvable = _usb_pd_inputs[3]

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


@pytest.fixture(scope="module")
def _real_model(carrier_model):
    return carrier_model


def test_gate_is_green_on_the_templated_board(_real_model):
    for sheet in sorted(g._WIRED_SHEETS):
        res = g.check(_real_model, sheet)
        print(f"\n--- {sheet} ---\n" + res.summary())
        assert res.have_contract is True, sheet
        assert res.missing_refs == [], f"{sheet} unresolved refs: {res.missing_refs}"
        assert res.ok is True, res.summary()
        assert not res.violations, res.summary()


def test_wired_zone_coordinate_dump_is_a_report_that_always_passes(_real_model):
    for sheet in sorted(g._WIRED_SHEETS):
        rows = sorted(
            (i.ref, round(i.x, 3), round(i.y, 3), round(i.rotation, 1), i.side)
            for i in _real_model.insts if i.sheet == sheet)
        print(f"\n{sheet} zone: {len(rows)} parts")
        for ref, x, y, rot, s in rows:
            print(f"  {ref:8} x={x:9.3f} y={y:9.3f} rot={rot:5.1f} {s}")
        assert rows


def _zone_model(sheet: str, top_off, bot_off, rot, resolvable):
    from schgen.generate.pcb import (
        ORIGIN_X,
        ORIGIN_Y,
        FootprintInst,
        PcbModel,
    )
    from schgen.generate.pcb.footprint import pad_names
    zx, zy = 30.0, 40.0
    insts = []
    for side, off in (("top", top_off), ("bottom", bot_off)):
        for r, (dx, dy) in off.items():
            mod = resolvable[r]
            insts.append(FootprintInst(
                ref=r, value="x", footprint="x",
                x=ORIGIN_X + zx + dx, y=ORIGIN_Y + zy + dy,
                rotation=rot.get(r, 0.0),
                pad_nets={p: (0, "") for p in pad_names(mod)},
                mod_path=mod, sheet=sheet, side=side))
    return PcbModel(board_w=200.0, board_h=180.0, insts=insts,
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=len(insts), deferred=[], n_top=len(insts),
                    n_bottom=0, two_side=True)


def _run_zone(sheet: str):
    refs, side_of, bbox_of, resolvable, conn_rot, outer_dir = \
        _subsystem_inputs(sheet)
    contract = g.discover_contract(sheet)
    side = dict(side_of)
    for m in T.contract_member_brefs(sheet, contract, resolvable):
        side[m] = "top"
    rot: dict[str, float] = {}
    res = T.build_zone(sheet, contract, refs, side, bbox_of, resolvable, rot,
                       facing=_hook_facing(sheet, contract),
                       outer_dir=outer_dir)
    for bref, r in conn_rot.items():
        rot[bref] = (r + rot.get(bref, 0.0)) % 360.0
    return res, rot, resolvable, contract


def test_fmc_header_root_is_flipped_and_members_follow():
    res, rot, resolvable, _contract = _run_zone("fmc")
    assert res is not None
    top_off, bot_off, _zw, _zh = res
    assert rot.get("J11001") == 180.0, f"header not flipped: {rot.get('J11001')}"
    m = _zone_model("fmc", top_off, bot_off, rot, resolvable)
    inst = {i.ref: i for i in m.insts}
    flipped = g._inst_pad_boxes(inst["J11001"])
    for cap in ("C11001", "C11002", "C11005"):
        cb = g._inst_pad_boxes(inst[cap])
        d_anchor = g._pins_to_part(flipped, cb, ["1", "2"])
        d_far_end = g._pins_to_part(flipped, cb, ["39", "40"])
        assert d_anchor is not None and d_anchor <= 8.0, f"{cap}: {d_anchor}"
        assert d_far_end is not None and d_far_end > 8.0, \
            f"{cap} seated at the WRONG (GND) end: {d_far_end}"


def test_flip_chooser_excludes_mating_and_small_parts():
    from schgen.core.link import load_subsystem
    from schgen.generate.pcb.footprint import resolve_mod
    pmod = load_subsystem("pmod")
    sock = resolve_mod(pmod.circuit.parts["J1"].footprint)
    assert T._som_flip_rot("pmod", "J1", sock) == 0.0
    fmc = load_subsystem("fmc")
    ldo = resolve_mod(fmc.circuit.parts["U1"].footprint)
    assert T._som_flip_rot("fmc", "U1", ldo) == 0.0
    hdr = resolve_mod(fmc.circuit.parts["J1"].footprint)
    assert T._som_flip_rot("fmc", "J1", hdr) == 180.0


def test_camera_multi_anchor_contract_is_satisfied():
    res, rot, resolvable, contract = _run_zone("camera")
    assert res is not None, "build_zone returned None for camera"
    top_off, bot_off, _zw, _zh = res
    m = _zone_model("camera", top_off, bot_off, rot, resolvable)
    band = g._board_refs_by_sheet("camera")
    chk = g.check(m, sheet_name="camera", contract=contract, ref_map=band)
    print("\n" + chk.summary())
    assert chk.missing_refs == [], f"camera unresolved refs: {chk.missing_refs}"
    assert chk.proximity_fail == 0, chk.summary()
    assert chk.ok, chk.summary()


def _proximity_sheets() -> list[str]:
    out = []
    for sheet, c in g.discover_all().items():
        types = {s.get("type") for s in c.get("structures", [])}
        if "proximity" in types and "hot_loop" not in types:
            out.append(sheet)
    return sorted(out)


@pytest.mark.parametrize("sheet", _proximity_sheets())
def test_proximity_contract_is_solved(sheet):
    res, rot, resolvable, contract = _run_zone(sheet)
    assert res is not None, f"build_zone returned None for {sheet}"
    top_off, bot_off, _zw, _zh = res
    m = _zone_model(sheet, top_off, bot_off, rot, resolvable)
    band = g._board_refs_by_sheet(sheet)
    chk = g.check(m, sheet_name=sheet, contract=contract, ref_map=band)
    print(f"\n[{sheet}] " + chk.summary())
    assert chk.missing_refs == [], f"{sheet} unresolved refs: {chk.missing_refs}"
    assert chk.proximity_fail == 0, chk.summary()
    assert chk.same_side_fail == 0, chk.summary()
    assert chk.ok, chk.summary()
