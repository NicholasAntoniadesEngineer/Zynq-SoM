from __future__ import annotations

import copy

from schgen.generate import pcb
from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y
from schgen.generate.pcb import breathe as bz
from schgen.generate.pcb.footprint import pad_names

_R_MOD = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
assert _R_MOD is not None, "R_0603 footprint missing"
_RN = len(pad_names(_R_MOD))


def _mkinputs(placements):
    from schgen.generate.pcb.footprint import _footprint_bbox
    pos, resolvable, parts, bbox_of, fixed_rot, side_of = {}, {}, {}, {}, {}, {}
    zorigin: dict[str, tuple[float, float]] = {}
    for ref, x, y, sheet, side in placements:
        pos[ref] = (x, y)
        resolvable[ref] = _R_MOD
        parts[ref] = (sheet, "lib:R", "10k", "lib")
        bbox_of[ref] = _footprint_bbox(_R_MOD)
        fixed_rot[ref] = 0.0
        side_of[ref] = side
        zorigin.setdefault(sheet, (x, y))
    return pos, resolvable, parts, bbox_of, fixed_rot, side_of, zorigin


def _call(pos, resolvable, parts, bbox_of, fixed_rot, side_of, zorigin,
          *, phase="A", som_keepout=(300.0, 300.0, 310.0, 310.0),
          df40_bands=None, board_w=120.0, board_h=100.0):
    return bz.breathe_fanout(
        pos, resolvable=resolvable, parts=parts, bbox_of=bbox_of,
        fixed_rot=fixed_rot, side_of=side_of, zorigin=zorigin,
        board_w=board_w, board_h=board_h, som_keepout=som_keepout,
        conn_edge={}, mh_refs=set(), som_j_refs=set(),
        df40_pad_boxes=df40_bands or [], phase=phase)


def test_starved_ic_gains_clearance():
    from schgen.generate.pcb.footprint import _footprint_bbox
    bb = _footprint_bbox(_R_MOD)
    w = bb[2] - bb[0]
    ins = _mkinputs([
        ("U1", 40.0, 40.0, "s1", "top"),
        ("U2", 40.0 + w, 40.0, "s2", "top"),
    ])
    pos = ins[0]
    before = copy.deepcopy(pos)
    _call(*ins, phase="A")
    assert pos == before, "sub-3-pin passives must not be spread for their own sake"


def test_hemmed_zone_positions_are_byte_identical_to_the_seed():
    ins = _mkinputs([
        ("U1", 50.0, 50.0, "s1", "top"),
        ("H1", 47.0, 50.0, "mech", "top"),
        ("H2", 53.0, 50.0, "mech", "top"),
        ("H3", 50.0, 47.0, "mech", "top"),
        ("H4", 50.0, 53.0, "mech", "top"),
    ])
    pos = ins[0]
    before = copy.deepcopy(pos)
    _call(*ins, phase="A")
    assert pos == before


def test_mover_avoids_df40_band_and_keepout():
    ic = pcb.resolve_mod("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    assert ic is not None
    from schgen.generate.pcb.footprint import _footprint_bbox
    bb = _footprint_bbox(ic)
    hw = bb[2] - bb[0]
    pos = {"U1": (45.0, 15.0), "U2": (45.0 + hw, 15.0)}
    resolvable = {"U1": ic, "U2": ic}
    parts = {"U1": ("s1", "lib:U", "x", "lib"), "U2": ("s2", "lib:U", "x", "lib")}
    bbox_of = {"U1": bb, "U2": bb}
    fixed_rot = {"U1": 0.0, "U2": 0.0}
    side_of = {"U1": "top", "U2": "top"}
    zorigin = {"s1": (45.0, 15.0), "s2": (45.0 + hw, 15.0)}
    keepout = (40.0, 40.0, 60.0, 60.0)
    band = (20.0, 8.0, 40.0, 26.0)
    bz.breathe_fanout(
        pos, resolvable=resolvable, parts=parts, bbox_of=bbox_of,
        fixed_rot=fixed_rot, side_of=side_of, zorigin=zorigin,
        board_w=120.0, board_h=100.0, som_keepout=keepout, conn_edge={},
        mh_refs=set(), som_j_refs=set(), df40_pad_boxes=[band], phase="B")
    for ref in ("U1", "U2"):
        b = bz._eff_box(bbox_of[ref], 0.0, pos[ref][0], pos[ref][1])
        for guard in (keepout, band):
            assert not (b[0] < guard[2] and b[2] > guard[0]
                        and b[1] < guard[3] and b[3] > guard[1]), (
                f"{ref} entered a hard keepout {guard}")


def test_identical_seeds_give_identical_committed_positions():
    ic = pcb.resolve_mod("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    from schgen.generate.pcb.footprint import _footprint_bbox
    bb = _footprint_bbox(ic)

    def run():
        pos = {"U1": (30.0, 30.0), "U2": (30.0, 35.0), "U3": (50.0, 30.0)}
        resolvable = {r: ic for r in pos}
        parts = {r: (f"s{r[-1]}", "lib:U", "x", "lib") for r in pos}
        bbox_of = {r: bb for r in pos}
        fixed_rot = {r: 0.0 for r in pos}
        side_of = {r: "top" for r in pos}
        zorigin = {parts[r][0]: pos[r] for r in pos}
        bz.breathe_fanout(
            pos, resolvable=resolvable, parts=parts, bbox_of=bbox_of,
            fixed_rot=fixed_rot, side_of=side_of, zorigin=zorigin,
            board_w=120.0, board_h=100.0, som_keepout=(300, 300, 310, 310),
            conn_edge={}, mh_refs=set(), som_j_refs=set(),
            df40_pad_boxes=[], phase="B")
        return dict(pos)

    assert run() == run()


def test_committed_positions_grid_snapped():
    from schgen.generate.pcb.constants import GRID
    ic = pcb.resolve_mod("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    from schgen.generate.pcb.footprint import _footprint_bbox
    bb = _footprint_bbox(ic)
    pos = {"U1": (30.0, 30.0), "U2": (30.0, 34.0)}
    seed = copy.deepcopy(pos)
    resolvable = {r: ic for r in pos}
    parts = {"U1": ("s1", "lib:U", "x", "lib"), "U2": ("s2", "lib:U", "x", "lib")}
    bbox_of = {r: bb for r in pos}
    fixed_rot = {r: 0.0 for r in pos}
    side_of = {r: "top" for r in pos}
    zorigin = {"s1": (30.0, 30.0), "s2": (30.0, 34.0)}
    bz.breathe_fanout(
        pos, resolvable=resolvable, parts=parts, bbox_of=bbox_of,
        fixed_rot=fixed_rot, side_of=side_of, zorigin=zorigin,
        board_w=120.0, board_h=100.0, som_keepout=(300, 300, 310, 310),
        conn_edge={}, mh_refs=set(), som_j_refs=set(),
        df40_pad_boxes=[], phase="B")
    moved_any = any(pos[r] != seed[r] for r in pos)
    if moved_any:
        px = ORIGIN_X + pos["U1"][0]
        py = ORIGIN_Y + pos["U1"][1]
        assert abs((px / GRID) - round(px / GRID)) < 1e-6, px
        assert abs((py / GRID) - round(py / GRID)) < 1e-6, py


def test_contract_members_are_fixed():
    kw = dict(mh_refs=set(), som_j_refs=set(), conn_edge={}, contract_sheets=set(),
              l4_exempt=frozenset())
    members = {"C22014", "L22003", "R22012", "Y28001", "RN36001"}
    for m in members:
        assert bz._is_fixed(m, "power_som", "Capacitor_SMD:C_0402",
                            contract_members=members, **kw), m
    assert not bz._is_fixed("C6001", "bringup_modules", "Capacitor_SMD:C_0402",
                            contract_members=members, **kw)
