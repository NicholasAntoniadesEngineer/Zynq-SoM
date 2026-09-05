from __future__ import annotations

import copy
import math

import pytest

from schgen.core import native as nat
from schgen.generate import floorplan as fp
from schgen.generate.floorplan import _fanout_sep, _fanout_sep_py, _Occupancy

_REACHES = (
    (0.0, 0.0, 0.0, 0.0),
    (1.5, 0.3, 0.0, 2.2),
    (3.32, 3.32, 3.32, 3.32),
    (0.0, 1.48, 0.5, 0.0),
)
_ZERO = (0.0, 0.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def geom():
    if not nat.loaded():
        pytest.skip("schgen._geom not built — run scripts/build_native.sh")
    return nat.module()


def test_py_round_matches_occupancy_inputs(geom):
    samples = (
        0.0, 1.0, -1.0, 1.23456, 1.23454, 37.3155, 12.3456,
        55.0 + 0.25, 3.0 + 16.0, 80.5 + 70.25,
        11.24955, 40.74095, 0.00005, -0.00005, -11.24955,
        8.9163 + 5 * 0.5, -8.9163 + 3 * 0.5, 4.1537, -0.1537,
    )
    for v in samples:
        assert geom.py_round(v, 4) == round(v, 4)
        assert geom.py_round(v, 1) == round(v, 1)


def test_fanout_sep_matches_python(geom):
    a = (1.5, 0.0, 2.2, 0.3)
    b = (0.0, 1.27, 0.5, 0.0)
    ai = _ZERO
    bi = (0.1, 0.0, 0.0, 0.2)
    for axis in ("E", "W", "N", "S"):
        assert geom.fanout_sep(a, ai, b, bi, axis) == pytest.approx(
            _fanout_sep_py(a, ai, b, bi, axis))
        assert _fanout_sep(a, ai, b, bi, axis) == _fanout_sep_py(
            a, ai, b, bi, axis)


def test_boxes_separated_kernel(geom):
    assert geom.boxes_separated(0, 0, 10, 8, 12, 0, 4, 8, 0.3, 0.3)
    assert not geom.boxes_separated(0, 0, 10, 8, 10.1, 0, 4, 8, 0.3, 0.3)


def test_occupancy_fits_matches_python(geom, monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 200.0)
    monkeypatch.setattr(fp, "BOARD_H", 180.0)
    occ = _Occupancy(far_ceil=10.0, max_reach=3.32)
    assert occ._cpp is not None
    k = 0
    for i in range(8):
        for j in range(6):
            occ.add(3.0 + i * 16.0, 2.5 + j * 17.5, 9.0, 7.5, _REACHES[k % 4])
            k += 1
    disagreements = 0
    x = 0.0
    while x < fp.BOARD_W:
        y = 0.0
        while y < fp.BOARD_H:
            for reach in _REACHES:
                py = occ._fits_hashed(x, y, 10.0, 8.0, reach)
                cpp = occ._cpp.fits_hashed(x, y, 10.0, 8.0, reach, _ZERO,
                                           fp.OCC_PUNCH, [])
                if py is not cpp:
                    disagreements += 1
            y += 5.0
        x += 5.0
    assert disagreements == 0


def test_place_near_matches_python(geom, monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 160.0)
    monkeypatch.setattr(fp, "BOARD_H", 140.0)
    hashed = _Occupancy(far_ceil=10.0, max_reach=3.32)
    assert hashed._cpp is not None
    hashed.add(55.0, 45.0, 50.0, 50.0)
    hashed.add(10.0, 10.0, 30.0, 12.0, _REACHES[1])
    hashed.add(110.0, 100.0, 24.0, 20.0, _REACHES[3])
    for ax, ay, w, h, reach in (
            (80.0, 70.0, 20.0, 15.0, _REACHES[1]),
            (12.0, 12.0, 16.0, 10.0, _REACHES[0]),
            (150.0, 20.0, 25.0, 22.0, _REACHES[2])):
        py = hashed._place_near_py(ax, ay, w, h, reach, _ZERO, fp.OCC_PUNCH,
                                   (), None)
        cpp = hashed._cpp.place_near(ax, ay, w, h, reach, _ZERO, fp.OCC_PUNCH,
                                     [], -160.0, 320.0, -140.0, 280.0)
        assert cpp == py
        assert py is not None
        hashed.add(*py, reach)


def test_box_gap_matches_python(geom):
    from schgen.verify.fanout_gate import _rect_gap, _rect_gap_py
    from schgen.verify.placement_contract_gate import _box_gap, _box_gap_py
    pairs = (
        ((0.0, 0.0, 2.0, 1.0), (3.0, 0.0, 4.0, 1.0)),
        ((0.0, 0.0, 2.0, 1.0), (1.0, 0.5, 1.5, 0.8)),
        ((-2.0, -1.0, 0.0, 0.0), (0.5, 0.5, 1.0, 1.0)),
        ((0.0, 0.0, 10.0, 8.0), (12.0, 1.0, 20.0, 9.0)),
        ((0.0, 0.0, 10.0, 8.0), (8.0, 4.0, 14.0, 12.0)),
    )
    for a, b in pairs:
        assert geom.box_gap(a, b) == pytest.approx(_box_gap_py(a, b))
        assert _box_gap(a, b) == _box_gap_py(a, b)
        assert geom.bbox_gap(a, b) == pytest.approx(_box_gap_py(a, b))
        assert geom.rect_gap(a, b) == pytest.approx(_rect_gap_py(a, b))
        assert _rect_gap(a, b) == _rect_gap_py(a, b)
    pins = {"1": (0.0, 0.0, 1.0, 1.0), "2": (4.0, 0.0, 5.0, 1.0)}
    part = {"U1": (8.0, 0.0, 12.0, 4.0)}
    from schgen.verify.placement_contract_gate import (
        _part_to_part,
        _part_to_part_py,
        _pins_to_part,
        _pins_to_part_py,
    )
    assert geom.min_box_gap(list(pins.values()), list(part.values())) == (
        _pins_to_part_py(pins, part, ["1", "2"]))
    assert _pins_to_part(pins, part, ["1", "2"]) == _pins_to_part_py(
        pins, part, ["1", "2"])
    assert _part_to_part(pins, part) == _part_to_part_py(pins, part)
    assert geom.min_box_gap([], list(part.values())) is None


def test_seat_dfs_picks_first_non_overlapping(geom):
    a = (0.0, 0.0, 2.0, 2.0)
    b_hit = (0.5, 0.5, 2.5, 2.5)
    b_free = (4.0, 0.0, 6.0, 2.0)
    solved, budget, nodes, pick = geom.seat_dfs([[a], [b_hit, b_free]], [], 0.3,
                                                1000)
    assert solved is True
    assert budget is False
    assert nodes >= 2
    assert list(pick) == [0, 1]


def test_sexpr_roundtrip_matches_python(geom):
    from schgen.core import sexpr
    samples = (
        "(kicad_pcb (version 20241229) (generator \"schgen\"))",
        "(xy 1.5 0)",
        "(general (thickness 1.6))",
        "(" + " ".join(["n"] * 40) + ")",
        '(descr "TF-SMD_TF-01A — TF-01A (TF-SMD_TF-01A) '
        '(EasyEDA/LCSC C91145, faithful conversion)")',
    )
    for text in samples:
        assert geom.sexpr_roundtrip(text) == sexpr._dumps_py(sexpr._loads_py(text))
        tree = sexpr.loads(text)
        assert sexpr.dumps(tree) == sexpr._dumps_py(tree)
    for v in (0.0, 1.0, 1.6, 12.3456, -0.75, 168.0):
        assert geom.sexpr_fmt_num(v) == sexpr._fmt_num_py(v)


def test_corridor_and_cell_kernels(geom):
    boxes = [(0.0, 0.0, 10.0, 8.0)]
    segs = [(12.0, 1.0, 20.0, 1.0)]
    assert geom.corridor_free(1.0, 12.5, 18.0, boxes, segs, 0.3) is False
    assert geom.corridor_free(4.0, 12.5, 18.0, boxes, segs, 0.3) is True
    assert geom.cell_free_point(5.0, 4.0, boxes, segs, 0.3) is False
    assert geom.cell_free_point(15.0, 4.0, boxes, segs, 0.3) is True


def test_route_grid_and_bfs(geom):
    from schgen.core.config import GRID
    from schgen.layout import route as R
    assert geom.route_cell_of(0.0, 1.27, GRID) == (0, 1)
    assert geom.route_point_of(0, 1, GRID) == R.point_of((0, 1))
    assert list(geom.route_cells_between(0.0, 0.0, 2.54, 0.0, GRID)) == [
        (0, 0), (1, 0), (2, 0)]
    grid = geom.RouteGrid()
    grid.claim("A", [(0, 0), (1, 0)], "stem")
    grid.block_box(-1.0, 2.0, 4.0, 5.0, GRID)
    way = geom.route_bfs_join(grid, "A", [(0.0, 0.0)], [(5.08, 0.0)], GRID)
    assert way[0] == (0.0, 0.0)
    assert way[-1] == (5.08, 0.0)


def test_emit_nodes_match_python(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    via = _from_tagged(geom.emit_via(1.25, 2.5, 0.6, 0.3, 3.0, "uid-via", True))
    want = [Sym("via"),
            [Sym("at"), 1.25, 2.5],
            [Sym("size"), 0.6],
            [Sym("drill"), 0.3],
            [Sym("layers"), "F.Cu", "B.Cu"],
            [Sym("locked"), Sym("yes")],
            [Sym("net"), 3],
            [Sym("uuid"), "uid-via"]]
    assert dumps(via) == dumps(want)
    wire = _from_tagged(geom.emit_wire(0.0, 0.0, 2.54, 0.0, "uid-wire"))
    assert wire[0] == Sym("wire")
    line = _from_tagged(geom.emit_gr_line(
        1.0, 2.0, 3.0, 4.0, 0.15, "F.SilkS", "uid-silk"))
    assert dumps(line) == dumps([
        Sym("gr_line"),
        [Sym("start"), 1.0, 2.0], [Sym("end"), 3.0, 4.0],
        [Sym("stroke"), [Sym("width"), 0.15], [Sym("type"), Sym("default")]],
        [Sym("layer"), "F.SilkS"],
        [Sym("uuid"), "uid-silk"],
    ])
    text = _from_tagged(geom.emit_gr_text(
        "Zynq SoM", 10.0, 20.0, 0.0, "F.SilkS", "uid-txt", 1.4, 0.25,
        "left bottom"))
    assert dumps(text) == dumps([
        Sym("gr_text"), "Zynq SoM",
        [Sym("at"), 10.0, 20.0, 0.0],
        [Sym("layer"), "F.SilkS"],
        [Sym("uuid"), "uid-txt"],
        [Sym("effects"),
         [Sym("font"), [Sym("size"), 1.4, 1.4], [Sym("thickness"), 0.25]],
         [Sym("justify"), Sym("left"), Sym("bottom")]],
    ])
    zone = _from_tagged(geom.emit_fill_zone(
        1.0, "GND", "GND_plane_In1", "In1.Cu",
        [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
        "uid-zone", 0.3, False, 0.25))
    assert dumps(zone) == dumps([
        Sym("zone"),
        [Sym("net"), 1], [Sym("net_name"), "GND"],
        [Sym("layer"), "In1.Cu"],
        [Sym("uuid"), "uid-zone"],
        [Sym("name"), "GND_plane_In1"],
        [Sym("hatch"), Sym("edge"), 0.5],
        [Sym("connect_pads"), [Sym("clearance"), 0.3]],
        [Sym("min_thickness"), 0.25],
        [Sym("filled_areas_thickness"), Sym("no")],
        [Sym("fill"), Sym("yes"), [Sym("thermal_gap"), 0.5],
         [Sym("thermal_bridge_width"), 0.5]],
        [Sym("polygon"),
         [Sym("pts"),
          [Sym("xy"), 0.0, 0.0], [Sym("xy"), 10.0, 0.0],
          [Sym("xy"), 10.0, 8.0], [Sym("xy"), 0.0, 8.0]]],
    ])
    keep = _from_tagged(geom.emit_keepout_zone(
        [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)],
        "uid-ko", "SoM_body_keepout"))
    assert keep[0] == Sym("zone")
    lab = _from_tagged(geom.emit_sch_label(
        "global_label", "USB_DP", "bidirectional", 12.7, 5.08, 180.0,
        "right", "uid-lab"))
    assert dumps(lab) == dumps([
        Sym("global_label"), "USB_DP",
        [Sym("shape"), Sym("bidirectional")],
        [Sym("at"), 12.7, 5.08, 180.0],
        [Sym("effects"),
         [Sym("font"), [Sym("size"), 1.27, 1.27]],
         [Sym("justify"), Sym("right")]],
        [Sym("uuid"), "uid-lab"],
    ])
    prop = _from_tagged(geom.emit_property(
        "Reference", "R1", 0.0, -2.54, 0.0, False))
    assert dumps(prop) == dumps([
        Sym("property"), "Reference", "R1",
        [Sym("at"), 0.0, -2.54, 0.0],
        [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]],
    ])


def test_quads_overlap_matches_python(geom):
    from schgen.generate.pcb.embed import _quads_overlap_py
    a = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    b = [(3.0, 1.0), (7.0, 1.0), (7.0, 4.0), (3.0, 4.0)]
    c = [(10.0, 0.0), (12.0, 0.0), (12.0, 2.0), (10.0, 2.0)]
    assert geom.quads_overlap(a, b) is True
    assert geom.quads_overlap(a, c) is False
    assert geom.quads_overlap(a, b) == _quads_overlap_py(a, b)
    assert geom.quads_overlap(a, c) == _quads_overlap_py(a, c)


def test_layers_and_stackup_match_python(geom):
    from schgen.core.sexpr import _from_tagged, dumps
    from schgen.generate.pcb.embed import _layers_node_py, _stackup_node_py
    assert dumps(_from_tagged(geom.emit_layers_node())) == dumps(
        _layers_node_py())
    assert dumps(_from_tagged(geom.emit_stackup_node())) == dumps(
        _stackup_node_py())


def test_turn_kernels_match_python(geom):
    from schgen.generate.pcb.turn import (
        pad_half_extent_py,
        turn_box_py,
        turn_point_py,
    )
    box = (1.0, -2.0, 9.0, 2.0)
    assert geom.turn_box(box, 90.0) == (-2.0, -9.0, 2.0, -1.0)
    for deg in (0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 359.0, -90.0):
        assert geom.turn_point(14.64, -3.0, deg) == turn_point_py(
            14.64, -3.0, deg)
        assert geom.turn_box(box, deg) == turn_box_py(box, deg)
        assert geom.pad_half_extent(1.6, 0.8, deg) == pad_half_extent_py(
            1.6, 0.8, deg)


def test_corners_rot_matches_python(geom):
    from types import SimpleNamespace

    from schgen.generate.pcb.constants import (
        GND_PLANE_EDGE_BACK,
        ORIGIN_X,
        ORIGIN_Y,
    )
    from schgen.generate.pcb.embed import CORNER_DECIMALS, _corners_rot_py
    inst = SimpleNamespace(x=40.0, y=55.0, rotation=90.0)
    model = SimpleNamespace(board_w=168.0, board_h=163.0)
    rect = (-2.0, -1.0, 6.0, 3.0)
    lo_x = ORIGIN_X + GND_PLANE_EDGE_BACK
    lo_y = ORIGIN_Y + GND_PLANE_EDGE_BACK
    hi_x = ORIGIN_X + model.board_w - GND_PLANE_EDGE_BACK
    hi_y = ORIGIN_Y + model.board_h - GND_PLANE_EDGE_BACK
    got = [tuple(p) for p in geom.corners_rot(
        rect, inst.rotation, inst.x, inst.y, lo_x, lo_y, hi_x, hi_y,
        CORNER_DECIMALS)]
    assert got == _corners_rot_py(rect, inst, model)


def test_iso_void_and_channel_demand_match_python(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    from schgen.generate.floorplan_compose import (
        CHANNEL_FLOOR_MM,
        CHANNEL_MIN_NETS,
        CHANNEL_PER_NET_MM,
        channel_demand_mm_py,
    )
    from schgen.generate.pcb.constants import GND_PLANE_LAYER, ZONE_MIN_THICKNESS
    corners = [(1.0, 2.0), (4.0, 2.0), (4.0, 5.0), (1.0, 5.0)]
    void = _from_tagged(geom.emit_iso_void_zone(
        corners, "uid-iso", "ethernet_isolation_void_U1", GND_PLANE_LAYER,
        ZONE_MIN_THICKNESS))
    assert dumps(void) == dumps([
        Sym("zone"),
        [Sym("net"), 0], [Sym("net_name"), ""],
        [Sym("layers"), GND_PLANE_LAYER],
        [Sym("uuid"), "uid-iso"],
        [Sym("name"), "ethernet_isolation_void_U1"],
        [Sym("hatch"), Sym("edge"), 0.5],
        [Sym("connect_pads"), [Sym("clearance"), 0]],
        [Sym("min_thickness"), ZONE_MIN_THICKNESS],
        [Sym("keepout"),
         [Sym("tracks"), Sym("allowed")],
         [Sym("vias"), Sym("allowed")],
         [Sym("pads"), Sym("allowed")],
         [Sym("copperpour"), Sym("not_allowed")],
         [Sym("footprints"), Sym("allowed")]],
        [Sym("fill"), [Sym("thermal_gap"), 0.5],
         [Sym("thermal_bridge_width"), 0.5]],
        [Sym("polygon"),
         [Sym("pts"),
          [Sym("xy"), 1.0, 2.0], [Sym("xy"), 4.0, 2.0],
          [Sym("xy"), 4.0, 5.0], [Sym("xy"), 1.0, 5.0]]],
    ])
    for n in (0, 5, 6, 12):
        assert geom.channel_demand_mm(
            n, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
            CHANNEL_PER_NET_MM) == channel_demand_mm_py(n)


def test_emit_symbol_matches_python(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    node = _from_tagged(geom.emit_symbol(
        "Device:R", 10.0, 20.0, 90.0, "uid-sym", "R1",
        10.0, 17.46, 0.0, False, "10k", 10.0, 22.54, 0.0, False,
        "R_0603", [("Datasheet", ""), ("MPN", "RC0603")],
        [("1", "uid-p1"), ("2", "uid-p2")], "Zynq_Carrier", "/root"))
    want = [Sym("symbol"),
            [Sym("lib_id"), "Device:R"],
            [Sym("at"), 10.0, 20.0, 90.0],
            [Sym("unit"), 1],
            [Sym("exclude_from_sim"), Sym("no")],
            [Sym("in_bom"), Sym("yes")],
            [Sym("on_board"), Sym("yes")],
            [Sym("dnp"), Sym("no")],
            [Sym("uuid"), "uid-sym"],
            [Sym("property"), "Reference", "R1",
             [Sym("at"), 10.0, 17.46, 0.0],
             [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]],
            [Sym("property"), "Value", "10k",
             [Sym("at"), 10.0, 22.54, 0.0],
             [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]],
            [Sym("property"), "Footprint", "R_0603",
             [Sym("at"), 10.0, 20.0, 0.0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("hide"), Sym("yes")]]],
            [Sym("property"), "Datasheet", "",
             [Sym("at"), 10.0, 20.0, 0.0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("hide"), Sym("yes")]]],
            [Sym("property"), "MPN", "RC0603",
             [Sym("at"), 10.0, 20.0, 0.0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("hide"), Sym("yes")]]],
            [Sym("pin"), "1", [Sym("uuid"), "uid-p1"]],
            [Sym("pin"), "2", [Sym("uuid"), "uid-p2"]],
            [Sym("instances"),
             [Sym("project"), "Zynq_Carrier",
              [Sym("path"), "/root",
               [Sym("reference"), "R1"], [Sym("unit"), 1]]]]]
    assert dumps(node) == dumps(want)


def test_sheet_flip_hull_and_pad_angle_match_python(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    from schgen.generate.pcb.embed import _flip_layer_token_py
    pins = [("USB_DP", "bidirectional", 10.0, 20.0, 180.0, "right", "uid-p0")]
    sheet = _from_tagged(geom.emit_sheet(
        12.7, 25.4, 50.8, 38.1, "uid-sh", "usb", "usb.kicad_sch",
        "Zynq_Carrier", "/root-uuid", "3", pins))
    want = [Sym("sheet"),
            [Sym("at"), 12.7, 25.4],
            [Sym("size"), 50.8, 38.1],
            [Sym("exclude_from_sim"), Sym("no")],
            [Sym("in_bom"), Sym("yes")],
            [Sym("on_board"), Sym("yes")],
            [Sym("dnp"), Sym("no")],
            [Sym("fields_autoplaced"), Sym("yes")],
            [Sym("stroke"), [Sym("width"), 0.1524],
             [Sym("type"), Sym("solid")]],
            [Sym("fill"), [Sym("color"), 0, 0, 0, 0.0]],
            [Sym("uuid"), "uid-sh"],
            [Sym("property"), "Sheetname", "usb",
             [Sym("at"), 12.7, 25.4 - 0.7116, 0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("justify"), Sym("left"), Sym("bottom")]]],
            [Sym("property"), "Sheetfile", "usb.kicad_sch",
             [Sym("at"), 12.7, 25.4 + 38.1 + 0.5846, 0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("justify"), Sym("left"), Sym("top")]]],
            [Sym("pin"), "USB_DP", Sym("bidirectional"),
             [Sym("at"), 10.0, 20.0, 180.0],
             [Sym("effects"),
              [Sym("font"), [Sym("size"), 1.27, 1.27]],
              [Sym("justify"), Sym("right")]],
             [Sym("uuid"), "uid-p0"]],
            [Sym("instances"),
             [Sym("project"), "Zynq_Carrier",
              [Sym("path"), "/root-uuid", [Sym("page"), "3"]]]]]
    assert dumps(sheet) == dumps(want)
    assert geom.flip_layer_token("F.Cu") == "B.Cu"
    assert geom.flip_layer_token("B.SilkS") == "B.SilkS"
    assert geom.flip_layer_token("In1.Cu") == "In1.Cu"
    for name in ("F.Cu", "B.Cu", "F.SilkS", "Edge.Cuts", "In1.Cu"):
        assert geom.flip_layer_token(name) == _flip_layer_token_py(name)
    assert geom.rotate_pad_angle(10.0, 90.0) == round((10.0 + 90.0) % 360.0, 4)
    assert geom.rotate_pad_angle(350.0, 20.0) == round((350.0 + 20.0) % 360.0, 4)
    pads = [("R1", 0.0, 0.0, 2.0, 1.0), ("C1", -1.0, 0.5, 3.0, 4.0)]
    assert geom.pad_union_hull(pads) == (-1.0, 0.0, 3.0, 4.0)
    assert geom.pad_union_hull([]) is None
    offs = [("R1", 1.0, 2.0), ("C1", 3.0, 4.0)]
    assert geom.centroid_offset(offs, 9.0, 8.0) == (2.0, 3.0)
    assert geom.centroid_offset([], 9.0, 8.0) == (9.0, 8.0)


def test_pairs_hold_matches_python(geom):
    from schgen.generate.floorplan import (
        CLEAR,
        OCC_PUNCH,
        _pairs_hold_py,
        _ZeroReach,
    )
    z = _ZeroReach
    interior = [[(10.0, 10.0, 20.0, 15.0, z, z, OCC_PUNCH, OCC_PUNCH, True)]]
    other = [[(40.0, 10.0, 12.0, 12.0, z, z, OCC_PUNCH, OCC_PUNCH, True)]]
    hit = [[(18.0, 12.0, 20.0, 10.0, z, z, OCC_PUNCH, OCC_PUNCH, True)]]
    groups_ok = interior + other
    groups_bad = interior + hit
    assert geom.pairs_hold(groups_ok, 1, CLEAR) is True
    assert geom.pairs_hold(groups_bad, 1, CLEAR) is False
    assert geom.pairs_hold(groups_ok, 1, CLEAR) == _pairs_hold_py(groups_ok, 1)
    assert geom.pairs_hold(groups_bad, 1, CLEAR) == _pairs_hold_py(groups_bad, 1)


def test_pair_axis_matches_python(geom):
    from schgen.generate.floorplan_compose import _pair_axis, _pair_axis_py
    cases = (
        ((0.0, 0.0, 10.0, 8.0), (12.0, 0.0, 16.0, 8.0)),
        ((0.0, 0.0, 10.0, 8.0), (0.0, 10.0, 10.0, 18.0)),
        ((20.0, 4.0, 30.0, 12.0), (0.0, 0.0, 8.0, 20.0)),
        ((5.0, 5.0, 15.0, 15.0), (6.0, 6.0, 14.0, 14.0)),
    )
    for a, b in cases:
        assert geom.pair_axis(a, b) == _pair_axis_py(a, b)
        assert _pair_axis(a, b) == _pair_axis_py(a, b)


def test_bellman_ford_matches_python(geom):
    from schgen.generate.floorplan_compose import (
        _bellman_ford,
        _bellman_ford_py,
    )
    nodes = ["#0", "a", "b"]
    feasible = [
        ("#0", "a", 20.0, "wall-hi-a"),
        ("a", "#0", -0.3, "wall-lo-a"),
        ("#0", "b", 30.0, "wall-hi-b"),
        ("b", "#0", -0.3, "wall-lo-b"),
        ("b", "a", -10.3, "sep"),
    ]
    cycle = [
        ("#0", "a", 5.0, "hi"),
        ("a", "#0", -6.0, "neg"),
        ("#0", "b", 8.0, "hib"),
        ("b", "#0", -0.3, "lob"),
    ]
    for edges in (feasible, cycle):
        py = _bellman_ford_py(nodes, edges)
        wrapped = _bellman_ford(nodes, edges)
        src = [nodes.index(u) for u, _v, _c, _t in edges]
        dst = [nodes.index(v) for _u, v, _c, _t in edges]
        cost = [c for _u, _v, c, _t in edges]
        ok, dist, cyc = geom.bellman_ford(len(nodes), src, dst, cost)
        if py[0] is None:
            assert ok is False
            assert wrapped[0] is None
            assert wrapped[1] == py[1]
            assert [edges[i][3] for i in cyc] == py[1]
        else:
            assert ok is True
            assert wrapped == py
            assert dist == [py[0][n] for n in nodes]


def test_flow_kernels_match_python(geom):
    from schgen.verify.placement_flow_gate import (
        bbox_gap_py,
        facing_dot_py,
        flow_budget_py,
    )
    som = (40.0, 50.0, 90.0, 100.0)
    assert geom.flow_budget(168.0, 163.0, som) == flow_budget_py(
        168.0, 163.0, som)
    assert geom.flow_budget(100.0, 100.0, None) == flow_budget_py(
        100.0, 100.0, None)
    a = (0.0, 0.0, 10.0, 8.0)
    b = (12.0, 1.0, 20.0, 9.0)
    c = (8.0, 4.0, 14.0, 12.0)
    assert geom.bbox_gap(a, b) == bbox_gap_py(a, b)
    assert geom.bbox_gap(a, c) == bbox_gap_py(a, c)
    assert geom.facing_dot(0.0, 0.0, 1.0, 0.0, 2.0, 0.0) == facing_dot_py(
        (0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
    assert geom.facing_dot(0.0, 0.0, 1.0, 0.0, 0.0, 1.0) == facing_dot_py(
        (0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    assert geom.facing_dot(5.0, 5.0, 5.0, 5.0, 8.0, 9.0) == facing_dot_py(
        (5.0, 5.0), (5.0, 5.0), (8.0, 9.0))


def test_predicted_metrics_match_python(geom):
    from schgen.generate.floorplan_compose import (
        LocalMetrics,
        predicted_bbox_py,
        predicted_centroid_py,
    )
    m = LocalMetrics(
        offsets=(("R1", 1.2, -0.4), ("C2", 4.8, 2.1), ("U1", 0.0, 0.0)),
        pad_union=(
            ("R1", 0.7, -0.9, 1.7, 0.1),
            ("C2", 4.3, 1.6, 5.3, 2.6),
            ("U1", -2.0, -2.0, 2.0, 2.0),
        ),
        zone_wh=(12.0, 8.0),
    )
    pose = (37.3155, 12.3456)
    assert predicted_centroid_py(pose, m) == geom.predicted_centroid(
        pose[0], pose[1], 25.0, 25.0, list(m.offsets), None)
    assert predicted_centroid_py(pose, m, {"R1", "U1"}) == geom.predicted_centroid(
        pose[0], pose[1], 25.0, 25.0, list(m.offsets), ["R1", "U1"])
    assert predicted_centroid_py(pose, m, set()) is None
    assert geom.predicted_centroid(
        pose[0], pose[1], 25.0, 25.0, list(m.offsets), []) is None
    assert predicted_bbox_py(pose, m) == geom.predicted_bbox(
        pose[0], pose[1], 25.0, 25.0, list(m.offsets), list(m.pad_union))


def test_quantize_matches_python(geom):
    from schgen.core import quantize
    samples = (37.3, 0.0, -12.7, 104.229, 51.4999, 11.24955, 40.74095)
    for v in samples:
        assert geom.fixed_part_grid(v) == round(round(v / 1.27) * 1.27, 4)
        assert geom.som_pose_half_mm(v) == round(round(v * 2) / 2, 1)
        assert geom.legalize_pose_quantum(v) == round(round(v / 0.5) * 0.5, 4)
        assert geom.quant_credit(v) == v + 0.05
        assert quantize.fixed_part_grid(v) == geom.fixed_part_grid(v)
        assert quantize.legalize_pose_quantum(v) == geom.legalize_pose_quantum(v)
    assert geom.snap_erosion_bound(6.0) == 5.25
    assert geom.snap_erosion_bound(4.99) == 4.99
    assert geom.outline_snap_up(161.0001) == 165.0
    assert geom.outline_grow(3) == 15.0
    assert geom.fine_shrink(183.0, 2) == 181.0
    assert geom.est_via_cost(True) == 7.6
    assert geom.est_via_cost(False) == 2.2
    assert geom.evict_corridor_grid(25.0, 37.3) == round(
        geom.fixed_part_grid(25.0 + 37.3) - 25.0, 4)
    u = 1.27
    for v in samples:
        assert geom.gsnap(v, u) == round(round(v / u) * u, 3)
        assert geom.gfloor(v, u) == round(math.floor(v / u + 1e-6) * u, 3)
        assert geom.gceil(v, u) == round(math.ceil(v / u - 1e-6) * u, 3)


def test_mst_and_median_match_python(geom):
    from schgen.generate.floorplan_compose import (
        weighted_median,
        weighted_median_py,
    )
    from schgen.generate.ratsnest import _mst_edges, _mst_edges_py
    pts = [
        (0.0, 0.0, "A", "1"),
        (3.0, 0.0, "B", "1"),
        (0.0, 4.0, "C", "1"),
        (3.0, 4.0, "D", "1"),
        (1.5, 2.0, "E", "1"),
    ]
    assert geom.mst_manhattan([(p[0], p[1]) for p in pts]) == _mst_edges_py(pts)
    assert _mst_edges(pts) == _mst_edges_py(pts)
    assert geom.mst_manhattan([]) == []
    assert geom.mst_manhattan([(0.0, 0.0)]) == []
    pulls = [(1.0, 4.0), (0.05, 1.0), (1.0, 2.0), (1.0, 2.0)]
    assert geom.weighted_median(pulls) == weighted_median_py(pulls)
    assert weighted_median(pulls) == weighted_median_py(pulls)
    src = [0, 1]
    dst = [1, 0]
    cost = [5.0, -0.3]
    assert geom.constraint_edges_ok(src, dst, cost, [0.0, 4.0]) is True
    assert geom.constraint_edges_ok(src, dst, cost, [0.0, 6.0]) is False


def test_boxes_overlap_and_flip_to_bottom(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    from schgen.generate.pcb.embed import (
        _flip_to_bottom,
        _flip_to_bottom_py,
    )
    from schgen.generate.pcb.stage_templates import (
        _boxes_overlap,
        _boxes_overlap_py,
    )
    a = (0.0, 0.0, 10.0, 8.0)
    b = (10.2, 0.0, 16.0, 8.0)
    assert geom.boxes_overlap(a, b, 0.3) is _boxes_overlap_py(a, b, 0.3)
    assert _boxes_overlap(a, b, 0.3) is _boxes_overlap_py(a, b, 0.3)
    assert geom.boxes_overlap(a, b, 0.3) is True
    assert geom.boxes_overlap(a, b, 0.1) is False
    node = [
        Sym("footprint"), "Lib:FP",
        [Sym("layer"), "F.Cu"],
        [Sym("fp_text"), Sym("reference"), "R1",
         [Sym("at"), 0.0, 0.0, 0.0],
         [Sym("layer"), "F.SilkS"],
         [Sym("effects"),
          [Sym("font"), [Sym("size"), 1.0, 1.0]],
          [Sym("justify"), Sym("left")]]],
        [Sym("pad"), "1", Sym("smd"), Sym("rect"),
         [Sym("at"), 1.0, 0.0],
         [Sym("layers"), "F.Cu", "F.Paste", "F.Mask"]],
    ]
    py_node = copy.deepcopy(node)
    cpp_node = copy.deepcopy(node)
    _flip_to_bottom_py(py_node)
    _flip_to_bottom(cpp_node)
    assert dumps(cpp_node) == dumps(py_node)
    tagged = geom.flip_to_bottom(copy.deepcopy(node))
    assert dumps(_from_tagged(tagged)) == dumps(py_node)


def test_shelf_pack_and_via_lattice(geom):
    from schgen.generate.pcb.constants import (
        ORIGIN_X,
        ORIGIN_Y,
        THERMAL_VIA_LATTICE_PITCH,
        THERMAL_VIA_SIZE,
    )
    from schgen.generate.pcb.embed import (
        _fallback_via_sites,
        _fallback_via_sites_py,
        _via_site_blocker,
        _via_site_blocker_py,
    )
    from schgen.generate.pcb.placement import _shelf_pack, _shelf_pack_py
    items = [
        ("U1", (-4.0, -2.0, 4.0, 2.0), 0.0),
        ("R1", (-1.0, -0.5, 1.0, 0.5), 0.0),
        ("C2", (-1.2, -0.6, 1.2, 0.6), 90.0),
    ]
    fanout = {"U1": (2.0, False), "R1": (0.5, True), "C2": (0.5, True)}
    blockers = [(0.3, 0.3, 4.0, 2.0, 0.0, False)]
    assert _shelf_pack(items, 18.0, blockers, fanout) == _shelf_pack_py(
        items, 18.0, blockers, fanout)
    empty = _shelf_pack([], 10.0)
    assert empty == _shelf_pack_py([], 10.0)
    spec = {"pour": (10.0, 12.0, 16.0, 18.0)}
    assert _fallback_via_sites(spec) == _fallback_via_sites_py(spec)
    assert geom.fallback_via_sites(
        10.0, 12.0, 16.0, 18.0, THERMAL_VIA_SIZE,
        THERMAL_VIA_LATTICE_PITCH) == _fallback_via_sites_py(spec)

    class _Board:
        board_w = 168.0
        board_h = 163.0

    model = _Board()
    obstacles = [
        (ORIGIN_X + 20.0, ORIGIN_Y + 20.0, 0.4, 0.3, "GND", 0.3, "pad U1.1"),
        (ORIGIN_X + 24.0, ORIGIN_Y + 20.0, 0.5, 0.5, "3V3", 0.0, "pad U1.2"),
    ]
    chosen = [(ORIGIN_X + 22.0, ORIGIN_Y + 22.0)]
    sites = (
        (ORIGIN_X + 5.0, ORIGIN_Y + 5.0),
        (ORIGIN_X + 0.2, ORIGIN_Y + 5.0),
        (ORIGIN_X + 20.0, ORIGIN_Y + 20.0),
        (ORIGIN_X + 22.0, ORIGIN_Y + 22.1),
        (ORIGIN_X + 30.0, ORIGIN_Y + 30.0),
    )
    for vx, vy in sites:
        assert _via_site_blocker(vx, vy, model, obstacles, chosen) == (
            _via_site_blocker_py(vx, vy, model, obstacles, chosen))
    members = [(1.0, 1.0, 4.0, 3.0, 8, 1.55),
               (16.0, 8.0, 19.0, 11.0, 2, 0.0)]
    reach, inset = geom.zone_fanout_reach(20.0, 12.0, members, 3)
    assert reach == (0.55, 0.0, 0.55, 0.0)
    assert inset == (1.0, 1.0, 1.0, 1.0)
    src = [0, 1]
    dst = [1, 0]
    cost = [5.0, -0.3]
    lo, hi = geom.constraint_bounds(1, src, dst, cost, [0.0, 4.0])
    assert hi == 5.0
    assert lo == 0.3


def test_silk_escape_and_seg_kernels(geom):
    from schgen.generate.pcb.escape import (
        _box_dist,
        _box_dist_py,
        _seg_box_dist,
        _seg_box_dist_py,
        band_cover,
        band_cover_py,
    )
    from schgen.generate.pcb.silk import (
        _overlap_area,
        _overlap_area_py,
        _rects_overlap,
        _rects_overlap_py,
        _text_box,
        _text_box_py,
    )
    from schgen.verify.visual_gate import Seg, _point_on_seg, _point_on_seg_py
    a = (0.0, 0.0, 4.0, 2.0)
    b = (3.0, 1.0, 6.0, 3.0)
    c = (4.0, 2.0, 5.0, 3.0)
    assert _rects_overlap(a, b) is _rects_overlap_py(a, b)
    assert _rects_overlap(a, c) is _rects_overlap_py(a, c)
    assert _overlap_area(a, b) == _overlap_area_py(a, b)
    assert _text_box("J1", 10.0, 12.0, 1.0) == _text_box_py("J1", 10.0, 12.0, 1.0)
    assert _box_dist(5.0, 1.0, a) == _box_dist_py(5.0, 1.0, a)
    assert _seg_box_dist((0.0, 3.0), (8.0, 3.0), a) == _seg_box_dist_py(
        (0.0, 3.0), (8.0, 3.0), a)
    pts = [(0.4, "90"), (0.4, "11"), (0.0, "1"), (2.1, "2")]
    assert band_cover(pts, 1.0) == band_cover_py(pts, 1.0)
    seg = Seg(0.0, 1.0, 4.0, 1.0, "N")
    assert _point_on_seg(2.0, 1.0, seg, interior_only=False) is (
        _point_on_seg_py(2.0, 1.0, seg, interior_only=False))
    assert _point_on_seg(0.0, 1.0, seg, interior_only=True) is (
        _point_on_seg_py(0.0, 1.0, seg, interior_only=True))
    ok, worst = geom.coverage_ok(0.0, 0.0, [(0.3, 0.4), (1.0, 0.0)], 2.0)
    assert ok is True
    assert worst == (1.0 ** 2 + 0.0 ** 2) ** 0.5 or worst > 0.0


def test_breathe_grid_matches_python(geom):
    from schgen.generate.pcb.breathe import CELL, _Grid, _GridPy
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    py = _GridPy(80.0, 60.0)
    cpp = geom.BreatheGrid(80.0, 60.0, CELL, ORIGIN_X, ORIGIN_Y)
    wrapped = _Grid(80.0, 60.0)
    boxes = (
        (ORIGIN_X + 2.0, ORIGIN_Y + 2.0, ORIGIN_X + 10.0, ORIGIN_Y + 8.0),
        (ORIGIN_X + 20.0, ORIGIN_Y + 15.0, ORIGIN_X + 28.0, ORIGIN_Y + 22.0),
        (ORIGIN_X - 1.0, ORIGIN_Y + 1.0, ORIGIN_X + 1.0, ORIGIN_Y + 3.0),
    )
    probes = (
        (ORIGIN_X + 3.0, ORIGIN_Y + 3.0, ORIGIN_X + 5.0, ORIGIN_Y + 5.0),
        (ORIGIN_X + 40.0, ORIGIN_Y + 40.0, ORIGIN_X + 42.0, ORIGIN_Y + 42.0),
        (ORIGIN_X + 19.0, ORIGIN_Y + 14.0, ORIGIN_X + 21.0, ORIGIN_Y + 16.0),
        (ORIGIN_X + 79.0, ORIGIN_Y + 59.0, ORIGIN_X + 81.0, ORIGIN_Y + 61.0),
    )
    for box in boxes:
        py.stamp(box)
        cpp.stamp(box)
        wrapped.stamp(box)
    for box in probes:
        assert cpp.free(box) is py.free(box)
        assert wrapped.free(box) is py.free(box)


def test_silk_box_index_matches_python(geom):
    from schgen.generate.pcb.silk import _BoxIndex, _BoxIndexPy
    boxes = (
        (0.0, 0.0, 4.0, 2.0),
        (10.0, 8.0, 14.0, 12.0),
        (-3.0, -2.0, 1.0, 1.0),
        (20.0, 20.0, 21.0, 21.0),
    )
    py = _BoxIndexPy(boxes)
    wrapped = _BoxIndex(boxes)
    probes = (
        (1.0, 0.5, 3.0, 1.5),
        (9.0, 7.0, 11.0, 9.0),
        (50.0, 50.0, 51.0, 51.0),
        (-2.0, -1.0, 0.0, 0.0),
    )
    for gb in probes:
        assert wrapped.pen(gb) == py.pen(gb)
        assert wrapped.hits(gb) is py.hits(gb)
        assert geom.SilkBoxIndex(8.0).pen(gb) == 0.0


def test_evict_window_matches_python(geom):
    from schgen.generate.floorplan import CLEAR, _fanout_sep_py, _ZeroReach
    e_reach = (1.5, 0.0, 0.3, 0.0)
    e_inset = _ZeroReach
    rch = (0.0, 2.0, 0.0, 0.5)
    ins = _ZeroReach
    e_comps = [(2.0, 0.0, 3.0, 2.0, 1)]
    cc = [(-1.0, -0.5, 2.0, 1.0, 1)]
    got = geom.evict_window(
        10.0, 12.0, 8.0, 6.0, e_reach, e_inset, e_comps,
        9.0, 7.0, rch, ins, cc, CLEAR)
    erects = [(10.0, 12.0, 8.0, 6.0, e_reach, e_inset),
              (12.0, 12.0, 3.0, 2.0, _ZeroReach, _ZeroReach)]
    g = max([CLEAR] + [_fanout_sep_py(a_r, a_i, r[4], r[5], axis)
                       for r in erects
                       for a_r, a_i in ((rch, ins), (_ZeroReach, _ZeroReach))
                       for axis in ("E", "W", "N", "S")])
    ex_lo = max([9.0] + [dx + cw for dx, _dy, cw, _ch, _cm in cc])
    ex_hi = min([0.0] + [dx for dx, _dy, _cw, _ch, _cm in cc])
    ey_lo = max([7.0] + [dy + ch for _dx, dy, _cw, ch, _cm in cc])
    ey_hi = min([0.0] + [dy for _dx, dy, _cw, _ch, _cm in cc])
    want = (min(r[0] for r in erects) - ex_lo - g,
            max(r[0] + r[2] for r in erects) + g - ex_hi,
            min(r[1] for r in erects) - ey_lo - g,
            max(r[1] + r[3] for r in erects) + g - ey_hi)
    assert got == want


def test_timing_span_records():
    from schgen.core import timing
    timing.reset()
    with timing.span("unit.example"):
        math.sqrt(2.0)
    text = timing.report()
    assert "unit.example" in text
    timing.reset()
