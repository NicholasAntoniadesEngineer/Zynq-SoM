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


def test_pairs_entity_and_layout_match_python(geom):
    from schgen.generate.floorplan import (
        CLEAR,
        MH_CORNER_KO,
        OCC_BOTTOM,
        OCC_PUNCH,
        OCC_TOP,
        _offset_boxes,
        _offset_boxes_py,
        _pairs_entity,
        _pairs_entity_py,
        _pairs_hold_from_layout,
        _pairs_hold_groups_py,
        _pairs_hold_py,
        _ZeroReach,
    )
    z = _ZeroReach
    comps = ((1.25, -0.5, 2.0, 1.5, OCC_BOTTOM),
             (0.0, 3.0, 4.0, 1.0, OCC_PUNCH))
    ref_ent = _pairs_entity_py(10.0, 12.0, 8.0, 6.0, (1.0, 0.2, 0.0, 0.4),
                               z, OCC_TOP, comps)
    got_ent = [tuple(row) for row in geom.pairs_entity(
        10.0, 12.0, 8.0, 6.0, (1.0, 0.2, 0.0, 0.4), z, OCC_TOP, list(comps))]
    assert got_ent == ref_ent
    assert _pairs_entity(10.0, 12.0, 8.0, 6.0, (1.0, 0.2, 0.0, 0.4),
                         z, OCC_TOP, comps) == ref_ent

    interior_rows = [
        (12.0, 14.0, 10.0, 8.0, (0.5, 0.0, 0.2, 0.0), z, OCC_TOP,
         ((0.25, 0.25, 1.0, 1.0, OCC_BOTTOM),)),
        (40.0, 20.0, 6.0, 6.0, z, z, OCC_BOTTOM, ()),
    ]
    edge_rows = [
        (0.0, 20.0, 8.0, 12.0, (0.0, 1.2, 0.0, 0.0), z, OCC_PUNCH,
         ((-1.0, 0.0, 2.0, 4.0, OCC_PUNCH),)),
    ]
    som_occ = (30.0, 30.0, 20.0, 16.0)
    som_comps = ((1.1111, 2.2222, 3.0, 1.0, OCC_BOTTOM),)
    board_w, board_h = 80.0, 70.0
    ref_groups = _pairs_hold_groups_py(
        interior_rows, edge_rows, som_occ, OCC_TOP, som_comps, board_w,
        board_h, MH_CORNER_KO, OCC_PUNCH)
    got_groups = [[tuple(row) for row in group]
                  for group in geom.pairs_hold_groups(
                      interior_rows, edge_rows, som_occ, OCC_TOP,
                      list(som_comps), board_w, board_h, MH_CORNER_KO,
                      OCC_PUNCH)]
    assert got_groups == ref_groups
    assert geom.pairs_hold_from_layout(
        interior_rows, edge_rows, som_occ, OCC_TOP, list(som_comps),
        board_w, board_h, MH_CORNER_KO, OCC_PUNCH, CLEAR) == _pairs_hold_py(
            ref_groups, len(interior_rows))
    assert _pairs_hold_from_layout(
        interior_rows, edge_rows, som_occ, OCC_TOP, som_comps, board_w,
        board_h, MH_CORNER_KO, OCC_PUNCH, CLEAR) == _pairs_hold_py(
            ref_groups, len(interior_rows))

    boxes = ((-1.0, -0.5, 1.0, 0.5), (2.0, 3.0, 4.5, 6.25))
    assert [tuple(row) for row in geom.offset_boxes(boxes, 5.0, -2.0)] == (
        _offset_boxes_py(boxes, 5.0, -2.0))
    assert _offset_boxes(boxes, 5.0, -2.0) == _offset_boxes_py(boxes, 5.0, -2.0)


def test_escape_ladder_plan_matches_python(geom):
    from schgen.generate.pcb.escape import (
        PITCH_TOL_MM,
        SPINE_W,
        STUB_W_PAIR,
        STUB_W_SINGLE,
        escape_ladder_plan,
        escape_ladder_plan_py,
    )
    gnd_pads = [
        (-1.6, 0.4, "1"), (-1.6, -0.4, "2"),
        (0.0, 0.4, "3"), (0.0, -0.4, "4"),
        (1.6, 0.4, "5"), (1.6, -0.4, "6"),
        (3.2, 0.4, "7"),
        (4.8, -0.4, "8"),
    ]
    vias = [(0.8, 1.2), (-0.4, 0.0), (2.4, -0.9)]
    pitch = 1.6
    row_v = 0.4
    ref = escape_ladder_plan_py(
        gnd_pads, vias, pitch, PITCH_TOL_MM, row_v, STUB_W_PAIR,
        STUB_W_SINGLE, SPINE_W)
    got = [tuple(row) for row in geom.escape_ladder_plan(
        gnd_pads, vias, pitch, PITCH_TOL_MM, row_v, STUB_W_PAIR,
        STUB_W_SINGLE, SPINE_W)]
    assert got == ref
    assert escape_ladder_plan(
        gnd_pads, vias, pitch, PITCH_TOL_MM, row_v, STUB_W_PAIR,
        STUB_W_SINGLE, SPINE_W) == ref


def test_escape_ladder_connected_and_redundancy_match_python(geom):
    from schgen.generate.pcb.escape import (
        LATTICE_MM,
        REDUNDANCY_OFFSET,
        _Obstacles,
        _via_clear,
        escape_ladder_connected,
        escape_ladder_connected_py,
        escape_redundancy_u,
        escape_redundancy_u_py,
    )
    vias = [
        {"u": 0.0, "v": 1.2, "dia": 0.45},
        {"u": 1.6, "v": 1.2, "dia": 0.45},
    ]
    segs = [
        {"a": (-0.8, 0.0), "b": (2.4, 0.0), "w": 0.30, "role": "spine"},
        {"a": (0.0, 0.0), "b": (0.0, 1.2), "w": 0.25, "role": "stub_via"},
        {"a": (1.6, 0.0), "b": (1.6, 1.2), "w": 0.25, "role": "stub_via"},
        {"a": (-0.8, -0.4), "b": (-0.8, 0.4), "w": 0.30, "role": "stub_pair"},
        {"a": (2.4, -0.4), "b": (2.4, 0.4), "w": 0.30, "role": "stub_pair"},
    ]
    pads = [(-1.6, 0.4), (-1.6, -0.4), (0.0, 0.4), (0.0, -0.4),
            (1.6, 0.4), (1.6, -0.4)]
    ref = escape_ladder_connected_py(vias, segs, pads, 0.2, 0.15)
    got = tuple(geom.escape_ladder_connected(
        [(via["u"], via["v"], via["dia"]) for via in vias],
        [(seg["a"][0], seg["a"][1], seg["b"][0], seg["b"][1], seg["w"],
          seg["role"]) for seg in segs],
        pads, 0.2, 0.15))
    assert got == ref
    assert escape_ladder_connected(vias, segs, pads, 0.2, 0.15) == ref

    obs = _Obstacles()
    obs.f_cu.append((-10.0, -10.0, -9.0, -9.0, 0.15, "far"))
    ref_u = escape_redundancy_u_py(
        0.4, 1.2, 0.45, 0.3, obs, REDUNDANCY_OFFSET, LATTICE_MM, 21)
    got_u = geom.escape_redundancy_u(
        0.4, 1.2, 0.45, 0.3, obs.f_cu, obs.b_cu, obs.samenet_pads, obs.holes,
        _via_clear(), REDUNDANCY_OFFSET, LATTICE_MM, 21)
    assert got_u == ref_u
    assert escape_redundancy_u(
        0.4, 1.2, 0.45, 0.3, obs, REDUNDANCY_OFFSET, LATTICE_MM, 21) == ref_u


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


def test_place_clear_label_matches_python(geom):
    from schgen.generate.pcb.silk import (
        _BoxIndexPy,
        _place_clear_label_py,
    )
    court = (49.0, 49.0, 51.0, 51.0)
    boxes = [(30.0, 30.0, 70.0, 70.0), (10.0, 80.0, 20.0, 90.0)]
    idx = geom.SilkBoxIndex(8.0)
    for b in boxes:
        idx.add(b)
    got = geom.place_clear_label(*court, "U1", 1.0, idx, None, None)
    ref = _place_clear_label_py(*court, "U1", 1.0, _BoxIndexPy(boxes))
    assert got[:2] == ref[:2]
    assert got[2:6] == ref[2]
    assert got[6] == ref[3]
    bounded = (0.0, 0.0, 100.0, 100.0)
    got_b = geom.place_clear_label(*court, "PMOD0", 1.1, idx, None, bounded)
    ref_b = _place_clear_label_py(*court, "PMOD0", 1.1, _BoxIndexPy(boxes),
                                  bounded)
    assert got_b[:2] == ref_b[:2]
    assert got_b[2:6] == ref_b[2]
    assert got_b[6] == ref_b[3]
    placed = geom.SilkBoxIndex(8.0)
    placed.add((48.0, 54.0, 52.0, 58.0))
    from schgen.generate.pcb.silk import _PairIndex
    got_p = geom.place_clear_label(*court, "U2", 1.0, idx, placed, None)
    ref_p = _place_clear_label_py(
        *court, "U2", 1.0,
        _PairIndex(_BoxIndexPy(boxes), _BoxIndexPy([(48.0, 54.0, 52.0, 58.0)])))
    assert got_p[:2] == ref_p[:2]
    assert got_p[2:6] == ref_p[2]
    assert got_p[6] == ref_p[3]


def test_segments_cross_matches_python(geom):
    from schgen.generate.pcb.placement import _segments_cross_py
    cases = (
        (((0.0, 0.0), (2.0, 2.0)), ((0.0, 2.0), (2.0, 0.0))),
        (((0.0, 0.0), (1.0, 0.0)), ((2.0, 0.0), (3.0, 0.0))),
        (((0.0, 0.0), (1.0, 1.0)), ((1.0, 1.0), (2.0, 0.0))),
        (((0.0, 0.0), (2.0, 0.0)), ((1.0, -1.0), (1.0, 1.0))),
    )
    for s1, s2 in cases:
        (p1, p2), (p3, p4) = s1, s2
        got = geom.segments_cross(p1[0], p1[1], p2[0], p2[1],
                                  p3[0], p3[1], p4[0], p4[1])
        assert got is _segments_cross_py(s1, s2)


def test_boxes_union_and_text_metrics(geom):
    from schgen.core.config import CHAR_W
    from schgen.layout.textmetrics import (
        _LLABEL_GAP,
        _LLABEL_WIDTH_PAD,
        GLABEL_H,
        GLABEL_INSET,
        GLABEL_PAD_LEN,
        LINE_H,
        SIZE,
        centered_box_py,
        glabel_box_py,
        llabel_box_py,
        text_wh_py,
    )
    assert geom.boxes_union([]) is None
    assert tuple(geom.boxes_union([(1.0, 2.0, 3.0, 4.0), (0.0, 1.5, 3.5, 3.0)])) \
        == (0.0, 1.5, 3.5, 4.0)
    for txt in ("GND", "~{GND}", "VCC_3V3", ""):
        assert tuple(geom.text_wh(txt, SIZE, CHAR_W, LINE_H)) == text_wh_py(txt)
        assert tuple(geom.centered_box(txt, 10.0, 20.0, SIZE, CHAR_W, LINE_H,
                                       False)) == centered_box_py(txt, 10.0, 20.0)
        assert tuple(geom.llabel_box(txt, 5.0, 6.0, 0, SIZE, CHAR_W, LINE_H,
                                     _LLABEL_WIDTH_PAD, _LLABEL_GAP)) \
            == llabel_box_py(txt, 5.0, 6.0, 0)
        assert tuple(geom.glabel_box(txt, 5.0, 6.0, 90, SIZE, CHAR_W, LINE_H,
                                     GLABEL_PAD_LEN, GLABEL_H, GLABEL_INSET)) \
            == glabel_box_py(txt, 5.0, 6.0, 90)


def test_sch_xform_matches_python(geom):
    from schgen.layout.place import _xform_py
    for rot in (0, 90, 180, 270, -90, 450):
        got = tuple(geom.sch_xform(2.54, -1.27, 10.0, 20.0, rot))
        assert got == _xform_py(2.54, -1.27, 10.0, 20.0, rot)


def test_near_max_edges_matches_pair_axis(geom):
    hs = (0.0, 0.0, 8.0, 4.0)
    hg = (0.0, 0.0, 6.0, 3.0)
    sr = (10.0, 12.0, 18.0, 16.0)
    gr = (22.0, 11.0, 28.0, 14.0)
    rows = geom.near_max_edges(
        "usb", "som", 6.0, "x", hs, hg, sr, gr, True, False, None, (20.0, 10.0))
    assert rows
    assert rows[0][0] in ("usb", "#0")
    rows_y = geom.near_max_edges(
        "usb", "som", 6.0, "y", hs, hg, sr, gr, True, True, None, None)
    assert len(rows_y) == 2
    assert rows_y[0][3] is True


def test_wall_sep_edges_matches_python(geom):
    names = ["usb", "hdmi"]
    sizes = [12.0, 10.0]
    seps = [
        (True, "usb", "hdmi", 1.5),
        (True, "#som", "usb", 2.0),
        (False, "usb", "hdmi", 0.8),
    ]
    frects = [("som", (20.0, 30.0, 70.0, 80.0))]
    rows = geom.wall_sep_edges(True, names, sizes, 168.0, 0.3, seps, frects)
    assert ("#0", "usb", 168.0 - 0.3 - 12.0, "wall-hi", -1, "usb") in [
        tuple(r) for r in rows]
    assert any(r[3] == "sep" and r[0] == "hdmi" and r[1] == "usb" for r in rows)
    assert any(r[3] == "sep" and r[0] == "usb" and r[1] == "#0" for r in rows)
    assert all(r[3] != "sep" or seps[r[4]][0] is True for r in rows)


def test_silk_gfx_extent_and_pair_gap(geom):
    from schgen.generate.floorplan import CLEAR, _fanout_sep_py
    pts = [(0.0, 0.0), (2.0, 1.0), (-0.5, 1.5)]
    fx, fy, ca, sa, hw = 10.0, 20.0, 0.0, 1.0, 0.06
    got = tuple(geom.silk_gfx_extent(pts, fx, fy, ca, sa, hw))
    bxs = [fx + lx * ca + ly * sa for lx, ly in pts]
    bys = [fy - lx * sa + ly * ca for lx, ly in pts]
    want = (min(bxs) - hw, min(bys) - hw, max(bxs) + hw, max(bys) + hw)
    assert got == want
    assert geom.silk_gfx_extent([], fx, fy, ca, sa, hw) is None
    ar = (1.2, 0.0, 0.4, 0.0)
    ai = (0.0, 0.0, 0.0, 0.0)
    br = (0.0, 0.8, 0.0, 0.3)
    bi = ai
    axis = "E"
    want_g = round(max(CLEAR, _fanout_sep_py(ar, ai, br, bi, axis)), 4)
    assert geom.pair_gap(ar, ai, br, bi, axis, CLEAR) == want_g


def test_embed_sexpr_helpers(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    from schgen.generate.pcb.embed import (
        _restamp_uuid_py,
        _set_or_add_py,
        _set_pad_net_py,
    )
    node = [Sym("footprint"), "R", [Sym("layer"), "F.Cu"], [Sym("uuid"), "old"]]
    got = _from_tagged(geom.restamp_uuid(node, "new"))
    ref = [c for c in node]
    _restamp_uuid_py(ref, "new")
    assert dumps(got) == dumps(ref)
    node2 = [Sym("footprint"), "R", [Sym("layer"), "F.Cu"]]
    got2 = _from_tagged(geom.set_or_add(node2, [Sym("uuid"), "u1"]))
    ref2 = [c for c in node2]
    _set_or_add_py(ref2, [Sym("uuid"), "u1"])
    assert dumps(got2) == dumps(ref2)
    pad = [Sym("pad"), "1", [Sym("at"), 0, 0], [Sym("uuid"), "p"]]
    got3 = _from_tagged(geom.set_pad_net(pad, 7, "GND"))
    ref3 = [c for c in pad]
    _set_pad_net_py(ref3, 7, "GND")
    assert dumps(got3) == dumps(ref3)
    assert geom.thermal_via_inherit(1.0, 1.0, [(1.0, 1.0, 0.5, 0.5, 3, "GND")]) \
        == (3, "GND")
    assert geom.thermal_via_inherit(4.0, 4.0, [(1.0, 1.0, 0.5, 0.5, 3, "GND")]) \
        is None


def test_place_search_and_extents(geom):
    from schgen.core.config import CHAR_W, GRID
    from schgen.layout.place import _xform_py
    from schgen.layout.textmetrics import LINE_H, SIZE, centered_box_py

    box = geom.body_box(-2.54, -1.27, 2.54, 1.27, 10.0, 20.0, 90)
    pts = [_xform_py(px, py, 10.0, 20.0, 90)
           for px in (-2.54, 2.54) for py in (-1.27, 1.27)]
    want = (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))
    assert tuple(box) == want
    assert tuple(geom.boxes_paths_extent(
        [(1.0, 2.0, 3.0, 4.0)], [(0.0, 5.0), (4.0, 1.0)])) == (
        0.0, 1.0, 4.0, 5.0)
    assert tuple(geom.boxes_paths_extent([], [])) == (0.0, 0.0, 0.0, 0.0)
    boxes = [(0.0, 0.0, 4.0, 2.0), (8.0, 1.0, 12.0, 3.0)]
    segs = [(1.0, 0.5, 9.0, 1.5)]
    assert geom.band_edge(0.0, 2.5, -1, 100.0, boxes, segs) == 0.0
    assert geom.band_edge(0.0, 2.5, 1, -100.0, boxes, segs) == 12.0
    assert geom.cell_floor(0.5, 3.5, boxes, segs) == 2.0
    ncs = [(10.0, 10.0, 12.0, 12.0)]
    vp = (11.0, 11.0)
    got = tuple(geom.dodge_value_off_nc(
        "GND", vp[0], vp[1], 11.0, 8.0, GRID, CHAR_W, LINE_H, SIZE, ncs, 0.2))
    assert got != vp
    bx = centered_box_py("GND", got[0], got[1])
    assert not (bx[0] - 0.2 < 12.0 and bx[2] + 0.2 > 10.0
                and bx[1] - 0.2 < 12.0 and bx[3] + 0.2 > 10.0)
    stems = [(0.0, 0.0, 0.0, 5.0)]
    assert geom.vband_stem_free(0.0, 1.0, 2.0, stems, 0.3) is False
    assert geom.vband_stem_free(2.0, 1.0, 2.0, stems, 0.3) is True
    lane = geom.lane_x(1, 0.0, 4.0, 1.0, GRID, 0.7, 0.3, 0.0,
                       [(0.0, 0.0, 2.0, 4.0)], [], [])
    assert lane is not None
    assert geom.foreign_rows_clear((0.0, 1.0, 2.0, 3.0), [2.0], 1e-6) is False
    assert geom.foreign_rows_clear((0.0, 1.0, 2.0, 3.0), [4.0], 1e-6) is True
    gap, idx = geom.nearest_rect_gap(
        (0.0, 0.0, 1.0, 1.0), [(3.0, 0.0, 4.0, 1.0), (10.0, 0.0, 11.0, 1.0)],
        1e-4)
    assert idx == 0
    assert gap == pytest.approx(2.0)


def test_pack_anchor_and_decoupling(geom):
    from schgen.generate.floorplan import (
        ANCHOR_AFF_POW,
        ANCHOR_SOM_W,
        ANCHOR_ZONE_W,
        BOARD_H,
        BOARD_W,
        OCC_PUNCH,
        SOM_HALO,
        _zone_anchor_py,
    )
    from schgen.generate.pcb.placement import (
        SOM_DECOUPLING_INSET,
        som_decoupling_cells_py,
        som_decoupling_grid_py,
    )
    from types import SimpleNamespace

    plan = SimpleNamespace(som_x=40.0, som_y=30.0,
                           som=SimpleNamespace(w=50.0, h=40.0))
    for zone in "NESW":
        got = tuple(geom.zone_anchor(zone, plan.som_x, plan.som_y,
                                     plan.som.w, plan.som.h, BOARD_W, BOARD_H))
        assert got == _zone_anchor_py(plan, zone)
    face = geom.pack_anchor(
        True, "E", 40.0, 30.0, 50.0, 40.0, SOM_HALO, 12.0, 8.0,
        0.0, 0.0, False, False, False, "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.0, False, 0.0, 0.0, ANCHOR_ZONE_W, ANCHOR_SOM_W, 0.0, ANCHOR_AFF_POW,
        65.0, 50.0, [])
    assert tuple(face) == (40.0 + 50.0 + SOM_HALO + 6.0, 30.0 + 20.0)
    weighted = geom.pack_anchor(
        False, "", 40.0, 30.0, 50.0, 40.0, SOM_HALO, 12.0, 8.0,
        80.0, 20.0, False, False, False, "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.0, False, 0.0, 0.0, ANCHOR_ZONE_W, ANCHOR_SOM_W, 1.0, ANCHOR_AFF_POW,
        65.0, 50.0, [(10.0, 12.0, 2.0)])
    zw = ANCHOR_ZONE_W
    sp = ANCHOR_SOM_W * 1.0
    pw = 2.0 ** ANCHOR_AFF_POW
    wsum = zw + sp + pw
    want = ((zw * 80.0 + sp * 65.0 + pw * 10.0) / wsum,
            (zw * 20.0 + sp * 50.0 + pw * 12.0) / wsum)
    assert tuple(weighted) == pytest.approx(want)
    comps = geom.edge_components(
        "N", 12.0, 5.0, BOARD_W, BOARD_H, OCC_PUNCH,
        [(1.0, 2.0, 3.0, 4.0, OCC_PUNCH), (0.5, 0.5, 1.0, 1.0, 1)])
    assert comps[0] == (round(1.0, 4), round(-5.0, 4),
                        round(3.0, 4), round(5.0 + 2.0 + 4.0, 4), OCC_PUNCH)
    assert comps[1] == (round(0.5, 4), round(0.5, 4),
                        round(1.0, 4), round(1.0, 4), 1)
    for n in (0, 1, 4, 8, 9):
        g = tuple(geom.som_decoupling_grid(53.0, 45.0, n, SOM_DECOUPLING_INSET))
        ref = som_decoupling_grid_py(53.0, 45.0, n)
        assert (g[0], g[1], int(g[2]), int(g[3])) == (
            ref[0], ref[1], int(ref[2]), int(ref[3]))
        cells = [tuple(p) for p in geom.som_decoupling_cells(
            10.0, 12.0, 53.0, 45.0, n, SOM_DECOUPLING_INSET)]
        assert cells == som_decoupling_cells_py(10.0, 12.0, 53.0, 45.0, n)


def test_cc_and_embed_kernels(geom):
    from schgen.core.sexpr import Sym, _from_tagged, dumps
    from schgen.generate.pcb.embed import (
        _embed_footprint_body_py,
        _pad_geom_py,
    )
    from schgen.generate.pcb.stage_templates import _beside_py
    from schgen.verify.cc_gate import _UF, _key_py, _seed_geometry_unions_py
    from schgen.verify.visual_gate import Seg
    from types import SimpleNamespace

    assert tuple(geom.geom_key(1.23456, -2.5)) == _key_py(1.23456, -2.5)
    nodes = {
        _key_py(0.0, 0.0): SimpleNamespace(key=_key_py(0.0, 0.0), x=0.0, y=0.0),
        _key_py(2.0, 0.0): SimpleNamespace(key=_key_py(2.0, 0.0), x=2.0, y=0.0),
        _key_py(1.0, 0.0): SimpleNamespace(key=_key_py(1.0, 0.0), x=1.0, y=0.0),
    }
    segs = [Seg(0.0, 0.0, 2.0, 0.0, "A")]
    uf = _UF()
    _seed_geometry_unions_py(nodes, uf, segs, [])
    raw_nodes = [(n.key[0], n.key[1], n.x, n.y) for n in nodes.values()]
    roots = [tuple(r) for r in geom.seed_geometry_unions(
        raw_nodes, [(0.0, 0.0, 2.0, 0.0)], [])]
    ref = [uf.find(n.key) for n in nodes.values()]
    assert roots == ref

    mod = [Sym("footprint"), "R_0402",
           [Sym("layer"), "F.Cu"],
           [Sym("at"), 0, 0],
           [Sym("uuid"), "old"],
           [Sym("pad"), "1", [Sym("at"), 0.5, 0.0],
            [Sym("size"), 0.6, 0.3]]]
    got = _from_tagged(geom.embed_footprint_body(
        mod, 12.0, 8.0, 90.0, "top", "fp-u1"))
    ref_tree = _embed_footprint_body_py(
        copy.deepcopy(mod), 12.0, 8.0, 90.0, "top", "fp-u1")
    assert dumps(got) == dumps(ref_tree)
    pad = [Sym("pad"), "1", [Sym("at"), 0.5, 0.0, 90.0],
           [Sym("size"), 0.6, 0.3]]
    assert tuple(geom.pad_geom(pad)) == _pad_geom_py(pad)
    from schgen.generate.pcb.embed import _embed_footprint_decorate_py
    from types import SimpleNamespace as _NS
    deco = [Sym("footprint"), "R_0402",
            [Sym("property"), "Reference", "R?", [Sym("uuid"), "u1"]],
            [Sym("property"), "Value", "10k", [Sym("uuid"), "u2"]],
            [Sym("pad"), "1", [Sym("at"), 0.5, 0.0], [Sym("size"), 0.6, 0.3]],
            [Sym("fp_line"), [Sym("uuid"), "g1"]]]
    inst = _NS(ref="R12", value="10k", rotation=90.0, footprint="R_0402",
               pad_nets={"1": (3, "N1")})
    seq = {"n": 0}

    def uid(kind: str) -> str:
        seq["n"] += 1
        return f"uuid-{seq['n']}-{kind}"

    ref_tree = _embed_footprint_decorate_py(
        copy.deepcopy(deco), inst, {}, uid)
    seq["n"] = 0
    got_tree = _from_tagged(geom.embed_footprint_decorate(
        deco, "R12", "10k", 90.0, False, [("1", 3, "N1")], [], uid))
    assert dumps(got_tree) == dumps(ref_tree)
    ox, oy = geom.beside_offset(1.2, 0.8, (0.0, 0.0, 4.0, 2.0), "R", 0.5, None)
    from pathlib import Path
    dummy = _beside_py(Path("x"), 0.0, "top", (0.0, 0.0, 4.0, 2.0), "R", 0.5,
                       None, 1.2, 0.8)
    assert (ox, oy) == (dummy.ox, dummy.oy)


def test_som_lane_and_stage_kernels(geom):
    from schgen.generate.floorplan import OCC_BOTTOM, OCC_PUNCH
    from schgen.generate.pcb.placement import som_decoupling_cells_py
    from schgen.generate.pcb.stage_templates import TEMPLATE_CLEAR

    cells = som_decoupling_cells_py(10.0, 12.0, 53.0, 45.0, 4)
    bands = [(8.0, 10.0, 20.0, 11.0)]
    got = [tuple(c) for c in geom.som_components(
        10.0, 12.0, 0.5, cells, bands, OCC_BOTTOM, OCC_PUNCH)]
    want = []
    for cx, cy in cells:
        want.append((round(cx - 0.5 - 10.0, 4), round(cy - 0.5 - 12.0, 4),
                     round(1.0, 4), round(1.0, 4), OCC_BOTTOM))
    want.append((round(8.0 - 10.0, 4), round(10.0 - 12.0, 4),
                 round(12.0, 4), round(1.0, 4), OCC_PUNCH))
    assert got == want
    boxes = [(0.0, 0.0, 1.0, 1.0), (2.0, 0.0, 3.0, 1.0),
             (0.8, 0.8, 1.2, 1.2)]
    assert geom.any_boxes_overlap(boxes[:2], 0.0) is False
    assert geom.any_boxes_overlap(boxes, 0.0) is True
    assert geom.any_boxes_overlap(boxes[:2], 1.1) is True
    parts = [(0.0, 0.0, 2.0, 4.0)]
    lane = geom.lane_in_dir(
        1, 3.0, 2.0, 6.0, 1.27, 0.7, 0.3, 0.0, 0.3, 0.01,
        parts, [], [], parts, [])
    assert lane is not None
    union = geom.boxes_union([(0.0, 1.0, 2.0, 3.0), (1.0, 0.0, 4.0, 2.0)])
    assert tuple(union) == (0.0, 0.0, 4.0, 3.0)
    assert geom.boxes_union([]) is None
    assert geom.any_boxes_overlap([], TEMPLATE_CLEAR) is False


def test_pin_escape_and_buck_kernels(geom):
    from schgen.core.config import CHAR_W
    from schgen.core.symbols import Pin, pin_page_position_py
    from schgen.layout.route import _stem_dir_py
    from schgen.layout.textmetrics import LINE_H, SIZE

    pin = Pin(number="1", name="VIN", etype="passive", x=2.54, y=-1.27,
              rotation=0, length=2.54, hidden=False)
    for rot in (0, 90, 180, 270, -90, 450):
        assert tuple(geom.pin_page_position(
            pin.x, pin.y, 10.0, 20.0, rot)) == pin_page_position_py(
            pin, 10.0, 20.0, rot)
    for pin_rot in (0, 90, 180, 270):
        for part_rot in (0, 90, 180, 270, -90):
            assert tuple(geom.stem_dir(pin_rot, part_rot)) == _stem_dir_py(
                pin_rot, part_rot)
    from schgen.core.symbols import SymbolDef
    from schgen.layout.place import _pin_text_boxes_py
    from schgen.output.emit import PlacedPart

    pins_obj = [
        Pin(number="1", name="VIN", etype="passive", x=2.54, y=-1.27,
            rotation=0, length=2.54, hidden=False),
        Pin(number="2", name="GND", etype="passive", x=2.54, y=1.27,
            rotation=180, length=2.54, hidden=False),
        Pin(number="3", name="NC", etype="passive", x=0.0, y=0.0,
            rotation=90, length=2.54, hidden=True),
    ]
    sdef = SymbolDef(lib_id="U", raw=[], pins=pins_obj, body=(0, 0, 1, 1),
                     pin_names_hidden=False, pin_numbers_hidden=False)
    part = PlacedPart(ref="U1", lib_id="U", value="x", x=10.0, y=20.0,
                      rotation=0)
    pins = [(p.x, p.y, int(p.rotation), p.length, bool(p.hidden),
             p.number, p.name) for p in pins_obj]
    got = [tuple(r) for r in geom.pin_text_boxes(
        pins, 10.0, 20.0, 0, False, False, CHAR_W, LINE_H, SIZE)]
    ref = [(b.x0, b.y0, b.x1, b.y1, b.kind)
           for b in _pin_text_boxes_py(sdef, part)]
    assert got == ref
    legs = [tuple(r) for r in geom.escape_run_legs(
        0.0, 5.0, 20.0, 1.27, 0.127,
        [(8.0, 4.0, 12.0, 6.0, "U1", "body")],
        [(8.0, 4.0, 12.0, 6.0)], [], [],
        [(8.0, 4.0, 12.0, 6.0)], [], [], 0.0, 0.3, 0.3)]
    assert legs
    assert legs[0][:2] == (0.0, 5.0)
    assert legs[-1][2:] == (20.0, 5.0)
    centers = [tuple(p) for p in geom.cout_column_centers(
        (0.0, 0.0, 4.0, 2.0), 0.2, 1.0, 0.3, [(1.0, 0.5), (1.2, 0.8)])]
    assert len(centers) == 2
    assert centers[0][0] == centers[1][0]
    ox, oy = geom.bulk_cap_pose(1.0, (0.0, 0.0, 2.0, 1.0), "D", 0.4,
                                0.8, 0.6, 5.0, 0.3)
    assert (ox, oy) == (round(min(1.0, 5.0 - 0.3 - 0.8), 4),
                        round(1.0 + 0.4 + 0.6, 4))


def test_bfs_escape_and_place_refdes(geom):
    from schgen.generate.pcb.silk import _BoxIndex, _place_refdes_py

    way = geom.bfs_escape(
        0.0, 0.0, 5.08, 1.27, -2.0, -2.0, 8.0, 8.0, 16.0,
        [(10.0, 10.0, 12.0, 12.0)], [], 0.3)
    assert way is not None
    pts = [tuple(p) for p in way]
    assert pts[0] == (0.0, 0.0)
    assert pts[-1][1] == 5.08
    blocked = geom.bfs_escape(
        0.0, 0.0, 2.54, 1.27, -1.0, -1.0, 3.0, 3.0, 2.0,
        [(-10.0, 0.5, 10.0, 2.0)], [], 0.3)
    assert blocked is None
    occ = geom.SilkBoxIndex(8.0)
    occ.add((0.0, 0.0, 4.0, 2.0))
    plc = geom.SilkBoxIndex(8.0)
    court = (0.0, 0.0, 4.0, 2.0)
    box = (1.0, 0.5, 3.0, 1.5)
    moved, lx, ly, size, *add = geom.place_refdes(
        court, "R1", 1.0, box, occ, plc, (-20.0, -20.0, 40.0, 40.0),
        2.0, 1.0, 1.0, 0.0, 0.8, 0.02, 8.0, 1e-9, 0.5, (0.78, 0.62))
    assert moved is True
    assert size <= 1.0
    py_occ = _BoxIndex([(0.0, 0.0, 4.0, 2.0)])
    py_plc = _BoxIndex()
    ref = _place_refdes_py(
        py_occ, py_plc, court, "R1", 1.0, box, 2.0, 1.0, 1.0, 0.0,
        (-20.0, -20.0, 40.0, 40.0))
    assert (moved, lx, ly, size, tuple(add)) == (
        ref[0], ref[1], ref[2], ref[3], ref[4])


def test_pack_edges_and_hf_pose(geom):
    from schgen.generate.floorplan import (
        AFFINITY_FLOOR,
        BOARD_H,
        BOARD_W,
        CABLE_NEIGHBOR_GAP,
        CLEAR,
        EDGE_INSET,
        EDGE_MARGIN,
        OVERMOLD_SIDE_GAP,
        Block,
        Plan,
        SomGeom,
        _edge_target_py,
        _pack_edges_py,
    )
    from schgen.generate.pcb.stage_templates import TEMPLATE_CLEAR

    som = SomGeom(w=50.0, h=42.0, js=[], source="test")
    plan = Plan(som)
    plan.som_x, plan.som_y = 40.0, 30.0
    a = Block(name="a", kind="edge", w=12.0, h=8.0, edge="S",
              fanout_reach=(1.0, 0.5, 0.0, 0.0), j_aff={"J1": 2.0})
    b = Block(name="b", kind="edge", w=10.0, h=8.0, edge="S")
    plan.edge_blocks = [a, b]
    edge_of = {"a": "S", "b": "S"}
    _pack_edges_py(plan, edge_of)
    ref = [(blk.name, blk.edge, blk.x, blk.y) for blk in plan.edge_blocks]
    zero = (0.0, 0.0, 0.0, 0.0)
    rows = [(blk.name, blk.w, blk.h, None, blk.fanout_reach, zero,
             list(blk.j_aff.items()), False, blk.edge, edge_of[blk.name])
            for blk in (a, b)]
    poses, spilled = geom.pack_edges(
        rows, [], BOARD_W, BOARD_H, EDGE_MARGIN, EDGE_INSET, CLEAR,
        CABLE_NEIGHBOR_GAP, OVERMOLD_SIDE_GAP, AFFINITY_FLOOR,
        plan.som_x, plan.som_y, plan.som.w, plan.som.h)
    got = [(n, e, x, y) for n, e, x, y in poses]
    assert got == ref
    assert list(spilled) == []
    tgt = geom.edge_target(
        "S", plan.som_x, plan.som_y, plan.som.w, plan.som.h,
        list(a.j_aff.items()), [])
    assert tgt == _edge_target_py(a, "S", plan)
    assert geom.pick_sided_challenger(1.0, 0.5, 1e-6) is True
    assert geom.pick_sided_challenger(1.0, 0.999999, 1e-6) is False
    assert geom.reseat_rank(0.0, 0.0, [
        (10.0, 0.0, 2.0, 2.0, "far"),
        (1.0, 0.0, 2.0, 2.0, "near"),
        (1.0, 0.0, 2.0, 2.0, "also"),
    ]) == [1, 2, 0]
    assert tuple(geom.hf_cap_pose(3.25, 10.0, TEMPLATE_CLEAR, 1.1)) == (
        round(10.0 - TEMPLATE_CLEAR - 1.1, 4), 3.25)


def test_pcb_scan_and_place_helpers(geom):
    from schgen.core.sexpr import Sym, _from_tagged
    from schgen.generate.pcb.embed import _thermal_via_nets_py
    from schgen.generate.pcb.silk import (
        _collect_fp_silk_gfx_py,
        _silk_gfx_pts_py,
    )
    from schgen.layout.place import (
        A3_CENTER,
        A3_TITLEBLOCK_LEFT,
        TITLEBLOCK_MARGIN,
        _conn_cluster_groups_py,
        _conn_port_columns_py,
        _farm_row_right_bound_py,
    )

    line = [Sym("fp_line"),
            [Sym("start"), 0.0, 0.0],
            [Sym("end"), 2.0, 0.0],
            [Sym("layer"), Sym("F.SilkS")],
            [Sym("stroke"), [Sym("width"), 0.12]]]
    pts, hw = geom.silk_gfx_pts(line)
    ref_pts, ref_hw = _silk_gfx_pts_py(line)
    assert [tuple(p) for p in pts] == ref_pts
    assert hw == ref_hw
    circ = [Sym("fp_circle"),
            [Sym("center"), 1.0, 1.0],
            [Sym("end"), 2.0, 1.0],
            [Sym("layer"), Sym("B.SilkS")]]
    cpts, chw = geom.silk_gfx_pts(circ)
    rpts, rhw = _silk_gfx_pts_py(circ)
    assert [tuple(p) for p in cpts] == rpts
    assert chw == rhw
    fp = [Sym("footprint"), "X",
          [Sym("at"), 10.0, 20.0, 90.0],
          line, circ]
    top, bot = geom.collect_fp_silk_gfx(fp)
    rtop, rbot = _collect_fp_silk_gfx_py(fp)
    assert [tuple(b) for b in top] == rtop
    assert [tuple(b) for b in bot] == rbot
    pad_net = [Sym("pad"), "1",
               [Sym("at"), 0.0, 0.0],
               [Sym("size"), 1.0, 1.0]]
    via = [Sym("pad"), " ",
           [Sym("at"), 0.1, 0.0],
           [Sym("size"), 0.3, 0.3]]
    tree = [Sym("footprint"), "Y", pad_net, via]
    hits = {int(s): (int(n), name)
            for s, n, name in geom.thermal_via_scan(tree, [("1", 3, "GND")])}
    assert hits == _thermal_via_nets_py(tree, {"1": (3, "GND")})
    assert geom.farm_row_right_bound(
        0.0, 40.0, A3_CENTER[0], A3_TITLEBLOCK_LEFT, TITLEBLOCK_MARGIN,
        10.16) == _farm_row_right_bound_py(
            0.0, 40.0, A3_CENTER[0], A3_TITLEBLOCK_LEFT, TITLEBLOCK_MARGIN,
            10.16)
    ys = [0.0, 2.54, 7.62, 10.16]
    assert list(geom.conn_port_columns(ys, 2.54, 1e-6)) == (
        _conn_port_columns_py(ys, 2.54, 1e-6))
    assert [list(g) for g in geom.conn_cluster_groups(ys, 2.54, 1e-6)] == (
        _conn_cluster_groups_py(ys, 2.54, 1e-6))
    from schgen.generate.pcb.mating_face import COURTYARD_DECIMALS
    from schgen.generate.pcb.silk import _collect_gr_text_boxes_py
    from schgen.generate.pcb.turn import pad_half_extent, turn_box, turn_point

    rows = [("smd", 1.0, 0.5, 90.0, 1.2, 0.6)]
    got_pads = [tuple(r) for r in geom.pad_boxes_local(rows, 90.0)]
    cx, cy = turn_point(1.0, 0.5, 90.0)
    hx, hy = pad_half_extent(1.2, 0.6, 180.0)
    assert got_pads == [("smd", cx - hx, cy - hy, cx + hx, cy + hy)]
    local = (-2.0, -1.0, 2.0, 1.0)
    rb = turn_box(local, 90.0)
    assert tuple(geom.inst_placed_box(local, 10.0, 20.0, 90.0,
                                      COURTYARD_DECIMALS)) == (
        round(10.0 + rb[0], COURTYARD_DECIMALS),
        round(20.0 + rb[1], COURTYARD_DECIMALS),
        round(10.0 + rb[2], COURTYARD_DECIMALS),
        round(20.0 + rb[3], COURTYARD_DECIMALS))
    doc = [Sym("kicad_pcb"),
           [Sym("gr_text"), "PWR",
            [Sym("at"), 5.0, 6.0],
            [Sym("effects"), [Sym("font"), [Sym("size"), 1.2, 1.2]]]]]
    assert [tuple(b) for b in geom.collect_gr_text_boxes(doc, 1.0)] == (
        _collect_gr_text_boxes_py(doc))
    from schgen.generate.pcb.silk import _collect_refdes_props_py
    from schgen.layout.place import U, gceil, gsnap

    fp_ref = [Sym("footprint"), "R",
              [Sym("at"), 4.0, 5.0, 0.0],
              [Sym("layer"), Sym("F.Cu")],
              [Sym("property"), "Reference", "R1",
               [Sym("at"), 0.5, 0.25],
               [Sym("layer"), Sym("F.SilkS")],
               [Sym("effects"), [Sym("font"), [Sym("size"), 1.0, 1.0]]]]]
    pcb = [Sym("kicad_pcb"), fp_ref]
    hits = geom.collect_refdes_props(pcb, 1.0)
    assert [(int(h[0]), int(h[1]), h[2], bool(h[10])) for h in hits] == (
        _collect_refdes_props_py(pcb))
    assert geom.footprint_alias(
        "Capacitor_SMD:C_1206_3225Metric",
        [("Capacitor_SMD:C_1206_3225Metric",
          "Capacitor_SMD:C_1206_3216Metric")]) == (
        "Capacitor_SMD:C_1206_3216Metric")
    assert geom.footprint_alias("X", []) == "X"
    assert geom.mirror_assert_ok(False, "top", False) is True
    assert geom.mirror_assert_ok(True, "top", True) is False
    assert geom.mirror_assert_ok(True, "bottom", True) is True
    assert geom.needs_flag(["passive", "power_in"], ["power_out", "output"])
    assert not geom.needs_flag(["power_in", "output"], ["power_out", "output"])
    assert tuple(geom.farm_cluster_origin(0.0, 10.0, U, 2)) == (
        gsnap(0.0 + 4 * U), gsnap(0.0 + 4 * U), gceil(8 * U),
        gceil(10.0 + 12 * U))
    assert geom.next_rail_col(20.0, 10.16, 4.0, 4.0, U, 1.27) == gceil(
        20.0 - 10.16 + max(10.16, 2.0 + 2.0 + 1.27))
    zero = (0.0, 0.0, 0.0, 0.0)
    occ = geom.Occupancy(80.0, 60.0, 0.3, 8.0, 2.0, 1.0, 0.05)
    occ.set_board(80.0, 60.0)
    occ.add(10.0, 10.0, 6.0, 6.0, zero, zero, 1, [])
    occ.add(30.0, 10.0, 6.0, 6.0, zero, zero, 1, [])
    row = ("a", 10.0, 10.0, 6.0, 6.0, zero, zero, 1, [],
           False, "", 20.0, 15.0, 20.0, 20.0, 7.0,
           12.0, 12.0, False, False, False, "",
           0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "",
           1.0, 0.0, 0.0, 1.6, 30.0, 25.0, [])
    poses, npass = geom.refine_pack_passes(
        occ, [row], [("a", 13.0, 13.0)], 16, 80.0, 60.0)
    assert npass >= 1
    assert len(poses) == 1
    win = (-80.0, 160.0, -60.0, 120.0)
    hits = geom.seat_shape_sides(
        occ, 40.0, 20.0,
        [(0, 6.0, 6.0, zero, zero, 1, "top", [], *win),
         (1, 6.0, 6.0, zero, zero, 2, "bottom", [], *win),
         (2, 200.0, 6.0, zero, zero, 1, "top", [], *win)],
        80.0, 60.0, 0.3)
    assert [h[0] for h in hits][0] == "top"
    assert {h[0] for h in hits} <= {"top", "bottom"}
    from schgen.core.sexpr import dumps as sexpr_dumps
    from schgen.generate.pcb.silk import _set_font_size_py

    prop = [Sym("property"), "Reference", "R1",
            [Sym("at"), 0.0, 0.0],
            [Sym("effects"),
             [Sym("font"),
              [Sym("size"), 1.0, 1.0],
              [Sym("thickness"), 0.15]]]]
    got_font = _from_tagged(geom.set_font_size(prop, 0.8))
    ref_font = copy.deepcopy(prop)
    _set_font_size_py(ref_font, 0.8)
    assert sexpr_dumps(got_font) == sexpr_dumps(ref_font)
    pcb = [Sym("kicad_pcb"),
           [Sym("footprint"), "C",
            [Sym("layer"), Sym("B.Cu")],
            [Sym("at"), 5.0, 5.0],
            [Sym("property"), "Reference", "C1",
             [Sym("at"), 0.0, 0.0]]]]
    tagged, hidden = geom.hide_undersom_bottom_refs(pcb, 0.0, 0.0, 10.0, 10.0)
    hid = _from_tagged(tagged)
    assert hidden == 1
    assert str(hid[1][4][3][0]) == "hide"
    assert str(hid[1][4][3][1]) == "yes"


def test_collect_refdes_rows_matches_python(geom):
    from schgen.core.sexpr import Sym
    from schgen.generate.pcb.silk import (
        _collect_refdes_rows,
        _collect_refdes_rows_py,
    )

    r2_at = [Sym("at"), 0.25, -0.5]
    r2_prop = [Sym("property"), "Reference", "R2",
               r2_at,
               [Sym("layer"), Sym("F.SilkS")],
               [Sym("effects"), [Sym("font"), [Sym("size"), 1.2, 1.2]]]]
    r1_at = [Sym("at"), 0.5, 0.25]
    r1_prop = [Sym("property"), "Reference", "R1",
               r1_at,
               [Sym("layer"), Sym("F.SilkS")],
               [Sym("effects"), [Sym("font"), [Sym("size"), 1.0, 1.0]]]]
    c1_at = [Sym("at"), 1.0, 0.0]
    c1_prop = [Sym("property"), "Reference", "C1",
               c1_at,
               [Sym("layer"), Sym("B.SilkS")],
               [Sym("effects"), [Sym("font"), [Sym("size"), 0.8, 0.8]]]]
    hidden = [Sym("property"), "Reference", "TP1",
              [Sym("at"), 0.0, 0.0],
              [Sym("layer"), Sym("F.SilkS")],
              [Sym("hide"), Sym("yes")]]
    wrong_lay = [Sym("property"), "Reference", "R9",
                 [Sym("at"), 0.0, 0.0],
                 [Sym("layer"), Sym("B.SilkS")]]
    no_at = [Sym("property"), "Reference", "R8",
             [Sym("layer"), Sym("F.SilkS")]]
    pcb = [Sym("kicad_pcb"),
           [Sym("footprint"), "R",
            [Sym("at"), 4.0, 5.0, 0.0],
            [Sym("layer"), Sym("F.Cu")],
            r2_prop, hidden, wrong_lay, no_at],
           [Sym("gr_text"), "skip"],
           [Sym("footprint"), "R",
            [Sym("at"), 10.0, 8.0],
            [Sym("layer"), Sym("F.Cu")],
            r1_prop],
           [Sym("footprint"), "C",
            [Sym("at"), 2.0, 3.0, 90.0],
            [Sym("layer"), Sym("B.Cu")],
            c1_prop]]
    courts = {"R1": (9.0, 7.0, 12.0, 10.0)}
    raw = geom.collect_refdes_rows(pcb, list(courts.items()), 1.0)
    oracle = _collect_refdes_rows_py(pcb, courts)
    assert [(int(h[0]), int(h[1]), h[2], bool(h[10])) for h in raw] == [
        (3, 4, "R1", False),
        (1, 4, "R2", False),
        (4, 4, "C1", True),
    ]
    got = _collect_refdes_rows(pcb, courts)
    assert len(got) == len(oracle) == 3
    for row, ref in zip(got, oracle):
        assert row[0] == ref[0]
        assert row[1] is ref[1]
        assert row[2] is ref[2]
        assert row[3:] == ref[3:]
    assert got[0][1] is r1_prop and got[0][2] is r1_at
    assert got[1][1] is r2_prop and got[1][2] is r2_at
    assert got[2][1] is c1_prop and got[2][2] is c1_at
    empty = _collect_refdes_rows(pcb, {})
    assert empty[0][7] == _collect_refdes_rows_py(pcb, {})[0][7]


def test_pack_legalize_preflight_kernels(geom):
    from schgen.generate.floorplan_compose import (
        CHANNEL_FLOOR_MM, CHANNEL_MIN_NETS, CHANNEL_PER_NET_MM,
        channel_gap_mm, channel_gap_mm_py)

    demand = {frozenset(("power", "usb")): 10}
    near = {frozenset(("power", "som"))}
    assert channel_gap_mm("power", "usb", demand, near, 0.3) == (
        channel_gap_mm_py("power", "usb", demand, near, 0.3))
    assert geom.channel_gap_mm(
        False, 10, 0.3, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
        CHANNEL_PER_NET_MM) == (CHANNEL_FLOOR_MM + 10 * CHANNEL_PER_NET_MM,
                                "D13-channel(10 nets)")
    assert geom.channel_gap_mm(
        True, 10, 0.3, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
        CHANNEL_PER_NET_MM) == (0.3, "near_max-adjacency(terminus)")
    assert geom.channel_gap_mm(
        False, 0, 0.3, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
        CHANNEL_PER_NET_MM) == (0.3, "CLEAR")

    a = (0.0, 0.0, 10.0, 8.0)
    b = (12.0, 0.0, 16.0, 8.0)
    c = (9.5, 0.0, 14.0, 4.0)
    assert geom.rects_overlap_any([a], [b], 1e-6) is False
    assert geom.rects_overlap_any([a], [c], 1e-6) is True
    assert geom.rects_overlap_any([a], [a], 1e-6) is True

    zero = (0.0, 0.0, 0.0, 0.0)
    reach = (1.5, 0.3, 0.0, 2.2)
    hold = geom.cross_edge_fanout_hold(
        [(0.0, 10.0, 20.0, 8.0, zero, zero, "N"),
         (40.0, 10.0, 20.0, 8.0, reach, zero, "S")],
        0.3)
    fail = geom.cross_edge_fanout_hold(
        [(0.0, 10.0, 20.0, 8.0, reach, zero, "W"),
         (10.0, 10.0, 20.0, 8.0, reach, zero, "E")],
        0.3)
    assert hold is True
    assert fail is False
    assert geom.edge_run_margin_ok(
        "N", 5.0, 0.0, 20.0, 8.0, 80.0, 60.0, 10.0, 0.1) is False
    assert geom.edge_run_margin_ok(
        "N", 12.0, 0.0, 20.0, 8.0, 80.0, 60.0, 10.0, 0.1) is True
    assert geom.edge_runs_margin_ok(
        [("S", 12.0, 42.0, 20.0, 8.0)], 80.0, 60.0, 10.0, 0.1) is True
    assert list(geom.pack_interior_order(
        ["z", "a", "m"], [2, 0, 1], [1.0, 0.5, 3.0], [10.0, 4.0, 8.0])) == (
        [1, 2, 0])
    seps = geom.legalize_build_seps(
        ["a", "b"], [a, b], ["som"], [(20.0, 20.0, 40.0, 40.0)],
        [("a", "b", 10)], [], 0.3, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
        CHANNEL_PER_NET_MM)
    assert seps
    assert seps[0][0] in ("x", "y")
    from schgen.layout.place import U, gceil, gsnap

    assert geom.next_flag_x(10.0, 10.16, 4.0, 4.0, U, 2.54) == gceil(
        10.0 + max(10.16, 2.0 + 2.0 + 2.54))
    assert tuple(geom.flags_row_origin(0.0, 10.0, U)) == (
        gsnap(0.0 + 4 * U), gceil(10.0 + 6 * U))
    assert geom.conn_signed_ceil(1, 5.08, U) == gceil(5.08)
    assert geom.conn_gnd_x(1, 4.0, 0.0, 2.0, 5.08, U) == gceil(4.0 + 5.08)
    wrap = geom.farm_wrap_advance(40.0, 30.0, True, 10.0, 5.0, 8.0, U)
    assert wrap[0] is True
    assert wrap[1] == 10.0
    assert wrap[2] == gceil(5.0 + 8.0)
    assert geom.conn_flag_y(10.0, U) == gceil(10.0 + 8 * U)
    assert geom.conn_flag_x0(10.16, 3, U) == gsnap(-10.16)


def test_evaluate_terms_matches_python(geom, monkeypatch):
    from schgen.generate import floorplan_compose as fc
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y

    def metrics_one_part(width, height):
        return fc.LocalMetrics(
            offsets=(("U1", width / 2, height / 2),),
            pad_union=(("U1", 0.0, 0.0, width, height),),
            zone_wh=(width, height))

    mets = {"a": metrics_one_part(10, 10), "b": metrics_one_part(8, 8)}
    som = (60.0, 60.0, 111.0, 103.0)
    poses = {"a": (20.0, 20.0), "b": (54.0, 20.0)}
    hop = fc.Term(kind="flow_hop", sheet="a", subject="a", target_raw="b",
                  bound=None, basis="test", enforced=True)
    near = fc.Term(kind="near_max", sheet="a", subject="a", target_raw="b",
                   bound=12.0, basis="test", enforced=True)
    intent = fc.Term(kind="near_intent", sheet="a", subject="a",
                     target_raw="b", bound=None, basis="test", enforced=False)
    far = fc.Term(kind="far_min", sheet="a", subject="a", target_raw="b",
                  bound=5.0, basis="test", enforced=True)
    face = fc.Term(kind="facing", sheet="a", subject="a", target_raw="b",
                   bound=None, basis="test", enforced=True,
                   out_refs=("U1",))
    missing = fc.Term(kind="near_max", sheet="a", subject="a",
                      target_raw="gone", bound=4.0, basis="test",
                      enforced=True)
    index = fc.TermIndex(hard=(hop, near, far, face, missing), soft=(intent,))
    monkeypatch.setattr(fc._nat, "trace", lambda: True)
    got = fc.evaluate_terms(170.0, 151.0, som, poses, mets, index)
    ref = fc.evaluate_terms_py(170.0, 151.0, som, poses, mets, index)
    assert [(e.term.key, e.measured, e.bound, e.margin, e.ok, e.note)
            for e in got] == [
                (e.term.key, e.measured, e.bound, e.margin, e.ok, e.note)
                for e in ref]
    rows = geom.evaluate_terms(
        170.0, 151.0, som, list(poses.items()),
        [(name, list(m.offsets), list(m.pad_union))
         for name, m in mets.items()],
        [(t.kind, t.subject, t.target, t.bound, list(t.out_refs))
         for t in index.terms],
        list(fc.FAR_L4_GUARD_MM.items()), [], ORIGIN_X, ORIGIN_Y)
    assert [(measured, bound, margin, ok, note)
            for measured, bound, margin, ok, note in rows] == [
                (e.measured, e.bound, e.margin, e.ok, e.note) for e in ref]


def test_legalize_descend_matches_python(geom, monkeypatch):
    from schgen.generate import floorplan_compose as fc

    def metrics_one_part(width, height):
        return fc.LocalMetrics(
            offsets=(("U1", width / 2, height / 2),),
            pad_union=(("U1", 0.0, 0.0, width, height),),
            zone_wh=(width, height))

    monkeypatch.setattr(fc._nat, "trace", lambda: True)
    mets = {"a": metrics_one_part(10, 10), "b": metrics_one_part(8, 8)}
    movable = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
    hop = fc.Term(kind="flow_hop", sheet="a", subject="a", target_raw="b",
                  bound=None, basis="test", enforced=True)
    near = fc.Term(kind="near_max", sheet="a", subject="a", target_raw="b",
                   bound=12.0, basis="test", enforced=True)
    index = fc.TermIndex(hard=(hop, near), soft=())
    log = []
    ok = fc.legalize_compact(
        170.0, 151.0, (60.0, 60.0, 111.0, 103.0),
        [("b", 100.0, 20.0, 108.0, 28.0)], [movable], index, mets,
        {"b": (100.0, 20.0)}, {}, 0.3, compact=True, log=log)
    assert ok, log
    names = ["a"]
    pos_x = [20.0]
    pos_y = [20.0]
    seed_x = [20.0]
    seed_y = [20.0]
    edges_x = [("#0", "a", 159.7), ("a", "#0", -0.3)]
    edges_y = [("#0", "a", 140.7), ("a", "#0", -0.3)]
    nx, ny = geom.legalize_descend_passes(
        names, pos_x, pos_y, seed_x, seed_y, edges_x, edges_y,
        [("a", "b")], [("a", (5.0, 5.0)), ("b", (4.0, 4.0))],
        [("b", (100.0, 20.0))], 60.5, 56.5, True, False, 1.0, 0.05, 8)
    keep_x = {"a": 20.0, "#0": 0.0}
    keep_y = {"a": 20.0, "#0": 0.0}
    hops = (("a", "b"),)
    cents = {"a": (5.0, 5.0), "b": (4.0, 4.0)}
    fixed = {"b": (100.0, 20.0)}
    for _pass in range(8):
        moved = 0.0
        for name in names:
            for axis, pos, edges, seed in (
                    ("x", keep_x, edges_x, seed_x),
                    ("y", keep_y, edges_y, seed_y)):
                lo, hi = -math.inf, math.inf
                for src, dst, cost in edges:
                    if dst == name and src != name:
                        hi = min(hi, pos.get(src, 0.0) + cost)
                    if src == name and dst != name:
                        lo = max(lo, pos.get(dst, 0.0) - cost)
                if lo > hi:
                    continue
                axis_i = 0 if axis == "x" else 1
                pulls = []
                self_c = cents[name][axis_i]
                for left, right in hops:
                    other = (right if left == name
                             else left if right == name else None)
                    if other is None:
                        continue
                    other_c = cents[other][axis_i]
                    if other in keep_x:
                        other_p = (keep_x if axis == "x" else keep_y)[other]
                        pulls.append((1.0, other_p + other_c - self_c))
                    elif other in fixed:
                        pulls.append((1.0, fixed[other][axis_i]
                                      + other_c - self_c))
                pulls.append((0.05, seed[0]))
                best = fc.weighted_median_py(pulls)
                from schgen.core.quantize import legalize_pose_quantum
                quant = legalize_pose_quantum(best)
                quant = max(lo, min(quant, hi))
                old = pos[name]
                if abs(quant - old) > 1e-12:
                    pos[name] = quant
                    moved = max(moved, abs(quant - old))
        if moved <= 1e-9:
            break
    assert nx[0] == keep_x["a"]
    assert ny[0] == keep_y["a"]


def test_halo_and_spatial_bounds_match_python(geom, monkeypatch):
    from schgen.generate.floorplan import (
        CABLE_NEIGHBOR_GAP,
        CLEAR,
        _halo4,
        _halo4_py,
        _occ_pair_active,
        _occ_pair_active_py,
        _spatial_bounds,
        _spatial_bounds_py,
    )
    from schgen.generate.pcb.constants import PLACE_CLEAR
    from schgen.verify.fanout_gate import _TIER_TOP, _TIERS

    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    reach = (1.5, 0.0, 2.2, 0.3)
    inset = (0.1, -0.4, 0.0, -1.0)
    assert geom.halo4(reach, inset) == _halo4_py(reach, inset)
    assert _halo4(reach, inset) == _halo4_py(reach, inset)
    assert geom.occ_pair_active(1, 0, True, 1, 0, True) is True
    assert geom.occ_pair_active(1, 2, False, 1, 2, False) is False
    assert _occ_pair_active(2, 1, False, 2, 0, True) is (
        _occ_pair_active_py(2, 1, False, 2, 0, True))
    need_ceil = max(_TIER_TOP[0], max(n for _p, n, _b in _TIERS))
    assert tuple(geom.spatial_bounds(
        10.0, 3.32, CLEAR, PLACE_CLEAR, CABLE_NEIGHBOR_GAP, need_ceil)) == (
        _spatial_bounds_py(10.0, 3.32))
    assert _spatial_bounds(10.0, 3.32) == _spatial_bounds_py(10.0, 3.32)
    assert _spatial_bounds(0.0, None) == _spatial_bounds_py(0.0, None)


def test_outline_and_interior_dims_match_python(geom, monkeypatch):
    from schgen.generate.floorplan import (
        EDGE_BAND,
        PACK_EFFICIENCY,
        PERIM_KEEPOUT,
        PLACEHOLDER_ASPECT,
        PLACEHOLDER_MAX_MM,
        PLACEHOLDER_MIN_MM,
        SOM_HALO,
        _derive_outline_wh,
        _derive_outline_wh_py,
        _interior_dims,
        _interior_dims_py,
    )
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    for area in (40.0, 120.0, 480.0, 1600.0):
        assert tuple(geom.interior_dims(
            area, PLACEHOLDER_ASPECT, PLACEHOLDER_MIN_MM,
            PLACEHOLDER_MAX_MM)) == _interior_dims_py(area)
        assert _interior_dims(area) == _interior_dims_py(area)
    for som_w, som_h, comp in ((50.0, 42.0, 8200.0), (40.0, 40.0, 1200.0)):
        got = tuple(geom.derive_outline_wh(
            som_w, som_h, SOM_HALO, EDGE_BAND, PERIM_KEEPOUT,
            PACK_EFFICIENCY, comp))
        ref = _derive_outline_wh_py(som_w, som_h, comp)
        assert got == ref
        assert _derive_outline_wh(som_w, som_h, comp) == ref


def test_legalize_repair_axis_matches_python(geom):
    names = ["a", "b"]
    sizes = [10.0, 8.0]
    seps = [
        (True, "a", "b", 0.3, True),
        (True, "b", "a", 200.0, True),
    ]
    ok, pos, newseps, flips, fail = geom.legalize_repair_axis(
        True, names, sizes, 80.0, 0.3, seps, [], [], 16)
    assert ok is True
    assert fail == ""
    assert len(pos) == 2
    ok2, _pos2, _seps2, _flips2, fail2 = geom.legalize_repair_axis(
        True, names, sizes, 80.0, 0.3,
        [(True, "a", "b", 0.3, False), (True, "b", "a", 200.0, False)],
        [], [], 0)
    assert ok2 is False
    assert fail2 in ("cycle", "exhausted")


def test_j_edge_and_affinity_tokens_match_python(geom, monkeypatch):
    from types import SimpleNamespace

    from schgen.generate.floorplan import (
        _affinity_j_from_expect,
        _affinity_j_from_expect_py,
        _affinity_j_from_target,
        _affinity_j_from_target_py,
        _dominant_j,
        _dominant_j_py,
        _j_edge_map,
        _j_edge_map_py,
    )

    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    som = SimpleNamespace(
        w=50.0, h=42.0,
        js=(
            SimpleNamespace(ref="J1", x=0.0, y=21.0),
            SimpleNamespace(ref="J2", x=25.0, y=0.0),
            SimpleNamespace(ref="J3", x=50.0, y=42.0),
        ))
    assert dict(geom.j_edge_map(
        [(j.ref, j.x, j.y) for j in som.js], som.w, som.h)) == (
        _j_edge_map_py(som))
    assert _j_edge_map(som) == _j_edge_map_py(som)
    assert geom.j_edge_of(25.0, 21.0, 50.0, 42.0) == min([
        (21.0, "N"), (21.0, "S"), (25.0, "W"), (25.0, "E")])[1]
    assert geom.dominant_j([]) is None
    assert geom.dominant_j([("J2", 1), ("J1", 1)]) == "J1"
    assert geom.dominant_j([("J3", 4), ("J1", 2)]) == "J3"
    assert _dominant_j({"J2": 1, "J1": 1}) == _dominant_j_py({"J2": 1, "J1": 1})
    assert _dominant_j({}) is None
    expects = (
        "j1 connector",
        "foo J2 bar",
        "xj1 no",
        "j12 no",
        "use j3 and j1",
        "",
    )
    for text in expects:
        assert list(geom.affinity_j_from_expect(text)) == (
            _affinity_j_from_expect_py(text))
        assert _affinity_j_from_expect(text) == (
            _affinity_j_from_expect_py(text))
    targets = (
        "sheet som_j1:HDMI",
        "sheet som_j2",
        "SoM east (J3)",
        "SoM west (J1) extra",
        "other",
        "sheet other",
    )
    for text in targets:
        assert geom.affinity_j_from_target(text) == (
            _affinity_j_from_target_py(text))
        assert _affinity_j_from_target(text) == (
            _affinity_j_from_target_py(text))


def test_j_affinity_nets_conn_and_obstacles_match_python(geom, monkeypatch):
    from types import SimpleNamespace

    from schgen.generate.floorplan import (
        _j_affinity,
        _j_affinity_py,
        _nets_by_sheet,
        _nets_by_sheet_py,
    )
    from schgen.generate.pcb.escape import _net_rule

    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    sheets = [SimpleNamespace(name="usb"), SimpleNamespace(name="hdmi")]
    bindings = [
        SimpleNamespace(sheet="usb", status="deferred",
                        ptype=SimpleNamespace(expect="use j1 and j3"),
                        targets=[]),
        SimpleNamespace(sheet="hdmi", status="bound",
                        ptype=SimpleNamespace(expect=""),
                        targets=["sheet som_j2:HDMI", "other"]),
        SimpleNamespace(sheet="extra", status="bound",
                        ptype=SimpleNamespace(expect=""),
                        targets=["SoM east (J3)"]),
    ]
    link = SimpleNamespace(bindings=bindings)
    assert _j_affinity(sheets, link) == _j_affinity_py(sheets, link)
    net_pts = {
        "N_B": [("R1", "hdmi", ()), ("R2", "usb", ())],
        "N_A": [("R3", "usb", ()), ("R4", "usb", ())],
        "N_C": [("R5", "extra", ())],
    }
    assert _nets_by_sheet(net_pts) == _nets_by_sheet_py(net_pts)
    assert geom.pack_conn_weight([1.0, 2.0], 0.5) == 1.0 + 2.0 + 3.0 * 0.5
    assert geom.pack_conn_weight([], 0.0) == 0.0
    assert geom.obstacle_bucket(0.0, 0.0, 10.0, 10.0, 11.0, 0.0, 12.0, 1.0,
                                True, True, True) == 0
    assert geom.obstacle_bucket(0.0, 0.0, 10.0, 10.0, 1.0, 1.0, 2.0, 2.0,
                                True, True, False) == 1
    assert geom.obstacle_bucket(0.0, 0.0, 10.0, 10.0, 1.0, 1.0, 2.0, 2.0,
                                True, False, False) == 2
    assert geom.obstacle_bucket(0.0, 0.0, 10.0, 10.0, 1.0, 1.0, 2.0, 2.0,
                                False, False, False) == 3
    assert tuple(geom.obstacle_hole(0.0, 2.0, 4.0, 6.0)) == (2.0, 4.0, 2.0)
    model = SimpleNamespace(netclass_of={"+VIN": "POWER", "GND": "GROUND"})
    assert _net_rule(model, "+VIN") == 0.2
    assert _net_rule(model, "GND") == 0.15


def test_escape_region_legalize_rects_and_stagger_match_python(geom):
    zone = (10.0, 20.0, 40.0, 50.0)
    assert geom.via_in_escape_region(25.0, 35.0, zone, 0.5) is True
    assert geom.via_in_escape_region(10.4, 35.0, zone, 0.5) is False
    assert geom.via_in_escape_region(25.0, 49.6, zone, 0.5) is False
    box = (1.0, 1.0, 2.0, 2.0)
    assert geom.coexistence_box_hit(0.0, 0.0, 0.0, box, 3.0, 3.0) is True
    assert geom.coexistence_box_hit(0.0, 0.0, 0.0, box, 0.4, 0.4) is False
    assert tuple(geom.legalize_som_rect(10.0, 12.0, 20.0, 8.0, 1.5)) == (
        8.5, 10.5, 31.5, 21.5)
    assert [tuple(r) for r in geom.legalize_mh_corners(100.0, 80.0, 10.0)] == [
        (0.0, 0.0, 10.0, 10.0),
        (90.0, 0.0, 100.0, 10.0),
        (90.0, 70.0, 100.0, 80.0),
        (0.0, 70.0, 10.0, 80.0),
    ]
    jacks = [("J1", 4.0, 6.0, 2.0, 4.0), ("J2", 8.0, 1.0, 6.0, 2.0)]
    got = {n: (x0, y0, x1, y1)
           for n, x0, y0, x1, y1 in geom.som_jack_rects(10.0, 20.0, jacks)}
    assert got == {
        "som_j1": (13.0, 24.0, 15.0, 28.0),
        "som_j2": (15.0, 20.0, 21.0, 22.0),
    }
    q0 = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    q1 = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    q2 = [(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)]
    assert [int(k) for k in geom.stagger_overlap_ranks([q0, q1, q2])] == [
        0, 1, 0]


def test_escape_zone_cover_reach_and_halo_match_python(geom, monkeypatch):
    from schgen.generate.pcb import breathe as br
    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb.escape import (
        aabb_from_corners,
        aabb_from_corners_py,
        coexistence_region,
        coexistence_region_py,
        construct_reach,
        construct_reach_py,
        escape_lane_extents,
        escape_lane_extents_py,
        grow_rect,
        grow_rect_py,
        min_hypot_to_points,
        min_hypot_to_points_py,
        obstacle_scan_region,
        obstacle_scan_region_py,
        offset_rect,
        offset_rect_py,
        point_in_rect,
        point_in_rect_py,
        rect_center,
        rect_center_py,
        rect_covers,
        rect_covers_py,
        rects_intersect_open,
        rects_intersect_open_py,
    )
    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(br._nat, "trace", lambda: True)
    keepout = (10.0, 20.0, 40.0, 50.0)
    zone = grow_rect(keepout, 2.0)
    assert zone == grow_rect_py(keepout, 2.0)
    assert tuple(geom.grow_rect(keepout, 2.0)) == (8.0, 18.0, 42.0, 52.0)
    plane = (5.0, 15.0, 50.0, 60.0)
    void = (41.0, 18.5, 43.0, 22.0)
    miss = (43.0, 18.5, 45.0, 22.0)
    assert rect_covers(plane, zone) is True
    assert rect_covers_py(plane, zone) is True
    assert rect_covers((8.1, 18.0, 42.0, 52.0), zone) is False
    assert rects_intersect_open(void, zone) is True
    assert rects_intersect_open_py(void, zone) is True
    assert rects_intersect_open(miss, zone) is False
    assert rects_intersect_open_py(keepout, (40.0, 20.0, 41.0, 21.0)) is False
    assert point_in_rect(10.0, 20.0, keepout) is True
    assert point_in_rect_py(40.0, 50.0, keepout) is True
    assert point_in_rect(9.9, 20.0, keepout) is False
    assert rect_center(keepout) == rect_center_py(keepout) == (25.0, 35.0)
    assert coexistence_region(4.2, 1.1, 0.4, 1.0, 0.5) == (
        coexistence_region_py(4.2, 1.1, 0.4, 1.0, 0.5))
    assert construct_reach(1.8, 0.9) == construct_reach_py(1.8, 0.9)
    assert construct_reach(1.8, 2.0) == 0.0
    assert obstacle_scan_region([-1.2, 0.0, 3.4], 6.0) == (
        obstacle_scan_region_py([-1.2, 0.0, 3.4], 6.0))
    assert escape_lane_extents(1.1, 0.4, 1.0) == escape_lane_extents_py(
        1.1, 0.4, 1.0)
    assert aabb_from_corners(12.34567, 9.1, 8.2, 11.87654, 4) == (
        aabb_from_corners_py(12.34567, 9.1, 8.2, 11.87654, 4))
    seats = [(0.0, 0.0), (1.5, -0.4), (-0.2, 0.8)]
    assert min_hypot_to_points(0.1, 0.2, seats) == min_hypot_to_points_py(
        0.1, 0.2, seats)
    assert offset_rect(keepout, 3.0, -1.5) == offset_rect_py(
        keepout, 3.0, -1.5)
    assert br._halo(keepout, 2.0) == br._halo_py(keepout, 2.0)
    assert br._eff_box((0.0, 0.0, 4.0, 2.0), 90.0, 10.0, 20.0) == (
        br._eff_box_py((0.0, 0.0, 4.0, 2.0), 90.0, 10.0, 20.0))


def test_reach_mid_pair_and_signed_mag_match_python(geom, monkeypatch):
    from schgen.generate import floorplan_compose as fc
    from schgen.generate.pcb import embed as em
    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb.embed import (
        count_within_reach,
        count_within_reach_py,
        within_reach,
        within_reach_py,
    )
    from schgen.generate.pcb.escape import (
        pair_convergence,
        pair_convergence_py,
        signed_mag,
        signed_mag_py,
    )
    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(em._nat, "trace", lambda: True)
    monkeypatch.setattr(fc._nat, "trace", lambda: True)
    assert within_reach(0.0, 0.0, 3.0, 4.0, 5.0) is True
    assert within_reach_py(0.0, 0.0, 3.0, 4.0, 4.9) is False
    pts = [(1.0, 0.0), (10.0, 0.0), (0.0, 2.0)]
    assert count_within_reach(0.0, 0.0, pts, 2.0) == count_within_reach_py(
        0.0, 0.0, pts, 2.0) == 2
    page = (25.0, 37.0, 55.0, 67.0)
    assert fc.page_mid_local(page, 25.0, 25.0) == fc.page_mid_local_py(
        page, 25.0, 25.0)
    halo = (-1.0, -2.0, 8.0, 6.0)
    assert fc.pose_halo_abs((10.0, 20.0), halo) == fc.pose_halo_abs_py(
        (10.0, 20.0), halo)
    assert pair_convergence(True, 1) == pair_convergence_py(True, 1) == (
        "immediate")
    assert pair_convergence(True, 2) == "quad"
    assert pair_convergence(True, 5) == "split"
    assert pair_convergence(False, 1) == "row_wrap"
    assert signed_mag(3.5, -1.0) == signed_mag_py(3.5, -1.0) == -3.5
    assert signed_mag(3.5, 1.0) == 3.5


def test_row_tier_bus_and_world_point_match_python(geom, monkeypatch):
    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb import turn as tn
    from schgen.generate.pcb.escape import (
        bus_lane_adjacent,
        bus_lane_adjacent_py,
        pad_row_sign,
        pad_row_sign_py,
    )
    from schgen.generate.pcb.turn import (
        world_turned_point,
        world_turned_point_py,
    )
    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(tn._nat, "trace", lambda: True)
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    assert pad_row_sign(0.4, 0.5) == pad_row_sign_py(0.4, 0.5) == 0
    assert pad_row_sign(0.5, 0.5) == 1
    assert pad_row_sign(-0.5, 0.5) == -1
    assert bus_lane_adjacent("VCC", "VCC", 3, 4) is True
    assert bus_lane_adjacent_py("VCC", "VCC", 3, 5) is False
    assert bus_lane_adjacent("VCC", "GND", 3, 4) is False
    assert geom.interior_tier(True, False) == 0
    assert geom.interior_tier(False, True) == 1
    assert geom.interior_tier(False, False) == 2
    assert world_turned_point(10.0, 20.0, 1.25, -0.4, 90.0, 4) == (
        world_turned_point_py(10.0, 20.0, 1.25, -0.4, 90.0, 4))


def test_padded_box_and_void_corners_match_python(geom, monkeypatch):
    from schgen.generate.pcb import embed as em
    from schgen.generate.pcb.embed import (
        isolation_void_rect,
        isolation_void_rect_py,
        rect_corners_ccw,
        rect_corners_ccw_py,
    )
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    monkeypatch.setattr(em._nat, "trace", lambda: True)
    assert fp.padded_xywh(10.0, 12.0, 20.0, 8.0, 1.5) == fp.padded_xywh_py(
        10.0, 12.0, 20.0, 8.0, 1.5)
    box = (8.5, 10.5, 31.5, 21.5)
    assert fp.box_to_xywh(box) == fp.box_to_xywh_py(box)
    court = (10.0, 12.0, 14.0, 16.0)
    void = isolation_void_rect(court, 0.6)
    assert void == isolation_void_rect_py(court, 0.6)
    assert rect_corners_ccw(void) == rect_corners_ccw_py(void)


def test_area_round_pair_and_svg_map_match_python(geom, monkeypatch):
    from schgen.generate.pcb import embed as em
    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb.embed import (
        closed_rect_pts,
        closed_rect_pts_py,
        round_xy,
        round_xy_py,
    )
    from schgen.generate.pcb.escape import (
        genuine_pair_ok,
        genuine_pair_ok_py,
        rounded_unique_sorted,
        rounded_unique_sorted_py,
    )
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(em._nat, "trace", lambda: True)
    assert fp.block_area(12.3, 8.7) == fp.block_area_py(12.3, 8.7)
    assert fp.svg_map(10.0, 46.0, 6.0) == fp.svg_map_py(10.0, 46.0, 6.0)
    assert fp._px(10.0) == fp.svg_map(10.0, fp.OX, fp.SCALE)
    assert fp._py(8.0) == fp.svg_map(8.0, fp.OY, fp.SCALE)
    assert genuine_pair_ok(True, 2) is True
    assert genuine_pair_ok_py(True, 3) is False
    assert genuine_pair_ok(False, 1) is False
    assert rounded_unique_sorted([1.2344, 1.2346, -0.001, 1.2344], 3) == (
        rounded_unique_sorted_py([1.2344, 1.2346, -0.001, 1.2344], 3))
    assert round_xy(12.34567, 9.87654, 4) == round_xy_py(12.34567, 9.87654, 4)
    box = (10.1234, 20.9876, 40.1111, 50.5555)
    assert closed_rect_pts(box, 3) == closed_rect_pts_py(box, 3)
    assert tuple(geom.round_box(box, 3)) == (
        round(box[0], 3), round(box[1], 3), round(box[2], 3), round(box[3], 3))


def test_offset_named_boxes_match_python(geom, monkeypatch):
    from schgen.verify import placement_contract_gate as pcg
    monkeypatch.setattr(pcg._nat, "trace", lambda: True)
    boxes = {
        "1": (0.0, 0.0, 1.0, 0.5),
        "A": (-2.0, 3.0, 0.25, 4.5),
    }
    assert pcg.offset_named_boxes(boxes, 10.0, -4.0) == (
        pcg.offset_named_boxes_py(boxes, 10.0, -4.0))
    got = {n: (x0, y0, x1, y1)
           for n, x0, y0, x1, y1 in geom.offset_named_boxes(
               [("1", 0.0, 0.0, 1.0, 0.5)], 5.0, 6.0)}
    assert got == {"1": (5.0, 6.0, 6.0, 6.5)}


def test_place_geom_wrappers_match_python(geom, monkeypatch):
    from schgen.layout import place as pl
    monkeypatch.setattr(pl._nat, "trace", lambda: True)
    assert pl.gceil(5.08) == geom.conn_signed_ceil(1, 5.08, pl.U)
    assert geom.conn_signed_ceil(-1, 5.08, pl.U) == -pl.gceil(5.08)
    assert tuple(geom.flags_row_origin(2.0, 11.0, pl.U)) == (
        pl.gsnap(2.0 + 4 * pl.U), pl.gceil(11.0 + 6 * pl.U))
    assert geom.next_flag_x(10.0, 10.16, 4.0, 6.0, pl.U, 2.54) == pl.gceil(
        10.0 + max(10.16, 2.0 + 3.0 + 2.54))
    assert geom.conn_gnd_x(-1, 8.0, 0.0, 3.0, 5.08, pl.U) == (
        -pl.gceil(max(8.0, 3.0) + 5.08))
    wrap = geom.farm_wrap_advance(12.0, 30.0, True, 4.0, 5.0, 8.0, pl.U)
    assert wrap == (False, 12.0, 5.0)
    wrap = geom.farm_wrap_advance(40.0, 30.0, False, 4.0, 5.0, 8.0, pl.U)
    assert wrap == (False, 40.0, 5.0)


def test_evict_corridor_and_part_dims_match_python(geom, monkeypatch):
    from schgen.core import quantize as qz
    from schgen.generate.floorplan import (
        _DEFAULT_DIMS,
        _FIXED_DIMS,
        _part_dims_from_name,
        _part_dims_from_name_py,
    )
    monkeypatch.setattr(qz._nat, "trace", lambda: True)
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    assert qz.evict_corridor_grid(25.0, 37.3) == geom.evict_corridor_grid(
        25.0, 37.3)
    keys = [(k, w, h) for k, (w, h) in sorted(
        _FIXED_DIMS.items(), key=lambda kv: len(kv[0]), reverse=True)]
    names = (
        "Device:SOT-23-5",
        "Device:SOT-23",
        "R_0603_1608Metric",
        "C_0402_1005Metric",
        "Thing_3.2x1.6mm_Pad",
        "UnknownPart",
        "Package_SO:TSOT-23-6",
    )
    for name in names:
        got = tuple(geom.part_dims_from_name(
            name, keys, _DEFAULT_DIMS[0], _DEFAULT_DIMS[1]))
        ref = _part_dims_from_name_py(name)
        assert got == ref
        assert _part_dims_from_name(name) == ref


def test_footprint_bbox_and_som_scan_match_python(geom, monkeypatch):
    from pathlib import Path

    from schgen.generate.floorplan import (
        SOM_PCB,
        extract_som,
        extract_som_py,
    )
    from schgen.generate.pcb.footprint import (
        BBOX_DECIMALS,
        _footprint_bbox,
        _footprint_bbox_from_doc_py,
        resolve_mod,
    )
    from schgen.core import sexpr
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    py = extract_som_py(SOM_PCB)
    w, h, rows = geom.extract_som_scan(SOM_PCB.read_text())
    assert (w, h) == (py.w, py.h)
    assert [(r[0], r[4], r[5], r[6], r[7]) for r in rows] == [
        (j.ref, j.x, j.y, j.w, j.h) for j in py.js]
    assert extract_som(SOM_PCB) == py
    samples = (
        "Device:R_0603_1608Metric",
        "Connector_FFC-FPC:Hirose_FH12-15S-0.5SH_1x15-1MP_P0.50mm_Horizontal",
    )
    from schgen.generate.pcb import footprint as fpp
    monkeypatch.setattr(fpp._nat, "trace", lambda: True)
    for fp_id in samples:
        mod = resolve_mod(fp_id)
        if mod is None:
            continue
        text = Path(mod).read_text()
        got = tuple(geom.footprint_bbox(text, BBOX_DECIMALS))
        ref = _footprint_bbox_from_doc_py(sexpr.loads(text))
        assert got == ref
        fpp._bbox_cache.clear()
        assert _footprint_bbox(mod) == ref


def test_som_keepout_and_zone_assemble_match_python(geom, monkeypatch):
    from types import SimpleNamespace

    from schgen.generate.floorplan import (
        OCC_BOTTOM,
        OCC_PUNCH,
        _som_keepout_rects,
        _som_keepout_rects_py,
        _zone_components_assemble,
        _zone_components_assemble_py,
    )
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    plan = SimpleNamespace(
        som_x=40.0, som_y=30.0,
        som=SimpleNamespace(w=50.0, h=42.0, js=(
            SimpleNamespace(x=0.0, y=21.0, w=8.0, h=4.0),
            SimpleNamespace(x=25.0, y=0.0, w=6.0, h=10.0),
        )))
    assert _som_keepout_rects(plan) == _som_keepout_rects_py(plan)
    minor = [(1.0, 2.0, 4.0, 6.0), (0.5, 1.5, 3.0, 5.5)]
    punches = [(10.0, 11.0, 12.5, 13.0)]
    ref = _zone_components_assemble_py(minor, punches, OCC_BOTTOM)
    got = tuple(tuple(r) for r in geom.zone_components_assemble(
        minor, punches, OCC_BOTTOM, OCC_PUNCH))
    assert got == ref
    assert _zone_components_assemble(minor, punches, OCC_BOTTOM) == ref


def test_courtyard_pad_scan_and_fanout_policy_match_python(geom, monkeypatch):
    from pathlib import Path

    from schgen.generate.floorplan import (
        PARTS_DIR,
        _courtyard_dims_from_text,
        _courtyard_dims_from_text_py,
        _zone_fanout_members_rows,
        _zone_fanout_members_rows_py,
    )
    from schgen.generate.pcb.footprint import (
        has_thru_pads,
        has_thru_pads_py,
        pad_names,
        pad_names_py,
    )
    from schgen.generate.pcb.embed import _MOD_PAD_CACHE, _mod_pads, _mod_pads_py
    from schgen.generate.pcb.escape import thru_pad_names, thru_pad_names_py
    from schgen.generate.pcb.mating_face import _pad_rows, _pad_rows_py
    from schgen.verify import fanout_gate as fg
    from schgen.verify.placement_contract_gate import (
        _pad_named_rows,
        _pad_named_rows_py,
    )

    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    monkeypatch.setattr(fg._nat, "trace", lambda: True)
    from schgen.generate.pcb import embed as emb
    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb import footprint as fpp
    from schgen.generate.pcb import mating_face as mf
    from schgen.verify import placement_contract_gate as pcg
    monkeypatch.setattr(emb._nat, "trace", lambda: True)
    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(fpp._nat, "trace", lambda: True)
    monkeypatch.setattr(mf._nat, "trace", lambda: True)
    monkeypatch.setattr(pcg._nat, "trace", lambda: True)

    samples = (
        "0603WAF1001T5E",
        "TPS54302DDCR",
        "DF40C-100DS-0.4V_51",
        "HX_PZ2.54-3x8P_ZZ",
        "MountingHole_3.2mm_M3_Pad",
    )
    for lib in samples:
        mod = PARTS_DIR / lib / f"{lib}.kicad_mod"
        if not mod.exists():
            continue
        text = Path(mod).read_text()
        assert geom.courtyard_dims_from_text(text) == (
            _courtyard_dims_from_text_py(text) or None)
        assert _courtyard_dims_from_text(text) == _courtyard_dims_from_text_py(
            text)
        assert list(geom.pad_names_from_text(text)) == pad_names_py(text)
        assert pad_names(mod) == pad_names_py(text)
        assert geom.has_thru_pads_from_text(text) == has_thru_pads_py(text)
        fpp._thru_cache.clear()
        assert has_thru_pads(mod) == has_thru_pads_py(text)
        named = [(n, px, py, prot, sw, sh)
                 for n, _t, px, py, prot, sw, sh in geom.scan_pad_nodes(text)]
        typed = [(_t, px, py, prot, sw, sh)
                 for _n, _t, px, py, prot, sw, sh in geom.scan_pad_nodes(text)]
        assert named == _pad_named_rows_py(text)
        assert tuple(typed) == _pad_rows_py(text)
        assert _pad_named_rows(mod) == _pad_named_rows_py(text)
        mf._PAD_ROW_CACHE.clear()
        assert _pad_rows(mod) == _pad_rows_py(text)
        assert [tuple(r) for r in geom.scan_mod_pads(text)] == _mod_pads_py(
            text)
        _MOD_PAD_CACHE.clear()
        assert _mod_pads(mod) == _mod_pads_py(text)
        assert list(geom.thru_pad_names(text)) == thru_pad_names_py(text)
        assert thru_pad_names(text) == thru_pad_names_py(text)

    refs = ("R1", "C12", "L3", "RS1", "RJ45", "RN2", "LED1", "U7", "TP3",
            "J1", "1R", "TP")
    for ref in refs:
        assert geom.ref_prefix(ref) == fg._ref_prefix_py(ref)
        assert geom.is_testpoint_ref(ref) == fg.is_testpoint_ref_py(ref)
        assert fg._ref_prefix(ref) == fg._ref_prefix_py(ref)
        assert fg.is_testpoint_ref(ref) == fg.is_testpoint_ref_py(ref)
        for pins in (1, 2, 3, 8, 9, 40):
            assert geom.is_cluster_passive(
                ref, pins, list(fg._NOT_PLAIN_PASSIVE),
                list(fg._PASSIVE_PREFIX)) == fg._is_cluster_passive_py(
                    ref, pins)
            assert fg._is_cluster_passive(ref, pins) == (
                fg._is_cluster_passive_py(ref, pins))
    for pins in range(0, 12):
        assert tuple(geom.intelligent_need(
            pins, list(fg._TIERS), fg._TIER_TOP[0],
            fg._TIER_TOP[1])) == fg.intelligent_need_py(pins)
        assert fg.intelligent_need(pins) == fg.intelligent_need_py(pins)

    rows = [
        (1.0, 2.0, -1.5, -0.8, 1.5, 0.8, 0.0, 2),
        (4.0, 5.0, -3.0, -2.0, 3.0, 2.0, 90.0, 8),
        (0.0, 0.0, 0.0, 0.0, 4.0, 4.0, 180.0, 16),
    ]
    ref = _zone_fanout_members_rows_py(rows)
    got = [tuple(r) for r in geom.zone_fanout_members_rows(
        rows, fg.MIN_SUBJECT_PINS, fg._NEED_MM, fg._TIER_TOP[0])]
    assert got == ref
    assert _zone_fanout_members_rows(rows) == ref


def test_cross_reorder_and_visual_kernels_match_python(geom, monkeypatch):
    from schgen.generate.floorplan import _cross_net_cost, _cross_net_cost_py
    from schgen.generate.pcb.placement import (
        _reorder_cluster_assign,
        _reorder_cluster_assign_py,
    )
    from schgen.verify.visual_gate import (
        Seg,
        _collinear_overlap,
        _collinear_overlap_py,
        _cross,
        _cross_py,
    )
    from schgen.generate.pcb import placement as pl
    from schgen.verify import visual_gate as vg
    monkeypatch.setattr(fp._nat, "trace", lambda: True)
    monkeypatch.setattr(pl._nat, "trace", lambda: True)
    monkeypatch.setattr(vg._nat, "trace", lambda: True)

    pts = [
        (0.0, 0.0, "R1", "power"),
        (4.0, 0.0, "R2", "io"),
        (4.0, 3.0, "U1", "io"),
        (1.0, 2.0, "C1", "power"),
    ]
    sides = ["top", "bottom", "bottom", "top"]
    bot_sel = {"io": 1}
    for via in (0.0, 0.8):
        ref = _cross_net_cost_py(pts, via, bot_sel, sides)
        encoded = []
        sheets = []
        ids = {}
        for (x, y, _r, s), side in zip(pts, sides):
            if s not in ids:
                ids[s] = len(sheets)
                sheets.append(s)
            encoded.append((x, y, ids[s], 0 if side == "top" else 1))
        flags = [1 if s in bot_sel else 0 for s in sheets]
        assert geom.cross_net_cost(encoded, via, flags) == ref
        assert _cross_net_cost(pts, via, bot_sel, sides) == ref

    segs = [
        [[(0.0, 0.0, 2.0, 2.0), (0.0, 1.0, 3.0, 1.0)],
         [(1.0, 0.0, 1.0, 3.0)]],
        [[(0.5, 0.5, 2.5, 2.5)],
         [(2.0, 0.0, 2.0, 3.0), (0.0, 2.0, 3.0, 2.0)]],
    ]
    init = [0, 1]
    ref = _reorder_cluster_assign_py(segs, init, 6)
    got = geom.reorder_cluster_assign(segs, init, 6)
    assert (int(got[0]), int(got[1]), [int(v) for v in got[2]]) == ref
    assert _reorder_cluster_assign(segs, init, 6) == ref

    pairs = (
        Seg(0.0, 1.0, 4.0, 1.0, "a"),
        Seg(2.0, 0.0, 2.0, 3.0, "b"),
        Seg(0.0, 1.0, 2.0, 1.0, "c"),
        Seg(1.5, 1.0, 3.5, 1.0, "d"),
        Seg(0.0, 0.0, 0.0, 2.0, "e"),
        Seg(0.0, 1.5, 0.0, 3.0, "f"),
        Seg(0.0, 0.0, 1.0, 1.0, "g"),
    )
    for a in pairs:
        for b in pairs:
            assert geom.visual_hv_cross(
                a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1) == _cross_py(
                    a, b)
            assert _cross(a, b) == _cross_py(a, b)
            assert geom.collinear_overlap(
                a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1) == (
                    _collinear_overlap_py(a, b))
            assert _collinear_overlap(a, b) == _collinear_overlap_py(a, b)


def test_som_cluster_gap_and_court_kernels_match_python(geom, monkeypatch):
    from schgen.generate.pcb import mating_face as mf
    from schgen.generate.pcb import placement as pl
    from schgen.generate.pcb import silk as sk
    from schgen.generate.pcb.constants import (
        ORIGIN_X,
        ORIGIN_Y,
        SOM_CORE_CLEARANCE,
    )
    from schgen.generate.pcb.mating_face import (
        _mating_face_out_dir,
        _mating_face_out_dir_py,
    )
    from schgen.generate.pcb.placement import (
        _cluster_interchangeable_rows,
        _cluster_interchangeable_rows_py,
        _nearest_manhattan,
        _nearest_manhattan_py,
        _rotate_offsets_90,
        _rotate_offsets_90_py,
        som_core_rect,
        som_core_rect_py,
    )
    from schgen.generate.pcb.silk import _refdes_hit_court, _refdes_hit_court_py
    from schgen.verify import connector_spacing_gate as csg
    from schgen.verify import placement_mech as pm
    from schgen.verify import visual_gate as vg
    from schgen.verify.connector_spacing_gate import (
        _overlap_1d,
        _overlap_1d_py,
        _same_edge_gap,
        _same_edge_gap_py,
    )
    from schgen.verify.placement_mech import (
        _rect_overlap_area,
        _rect_overlap_area_py,
    )
    from schgen.verify.visual_gate import Seg, _foreign_t_touch, _foreign_t_touch_py

    monkeypatch.setattr(pl._nat, "trace", lambda: True)
    monkeypatch.setattr(mf._nat, "trace", lambda: True)
    monkeypatch.setattr(sk._nat, "trace", lambda: True)
    monkeypatch.setattr(pm._nat, "trace", lambda: True)
    monkeypatch.setattr(csg._nat, "trace", lambda: True)
    monkeypatch.setattr(vg._nat, "trace", lambda: True)

    got = tuple(geom.som_core_rect(
        10.0, 12.0, 50.0, 40.0, ORIGIN_X, ORIGIN_Y, SOM_CORE_CLEARANCE))
    assert got == som_core_rect_py(10.0, 12.0, 50.0, 40.0)
    assert som_core_rect(10.0, 12.0, 50.0, 40.0) == got

    offs = {"R1": (1.25, 3.5), "U2": (0.0, 8.0), "C3": (4.4444, 0.1111)}
    ref = _rotate_offsets_90_py(offs, 12.0)
    native_rows = [(r, x, y) for r, x, y in geom.rotate_offsets_90(
        [(k, v[0], v[1]) for k, v in offs.items()], 12.0)]
    assert {r: (x, y) for r, x, y in native_rows} == ref
    assert _rotate_offsets_90(offs, 12.0) == ref

    pos = {
        "A": (0.0, 0.0), "B": (2.0, 0.1), "C": (4.0, 0.05),
        "D": (0.1, 5.0), "E": (0.2, 7.0), "F": (10.0, 10.0),
    }
    members = list(pos)
    ref_cl = _cluster_interchangeable_rows_py(pos, members, 1.5, 0.5)
    rows = [(m, pos[m][0], pos[m][1]) for m in members]
    got_cl = [(axis, list(refs)) for axis, refs in
              geom.cluster_interchangeable_rows(rows, 1.5, 0.5)]
    assert got_cl == ref_cl
    assert _cluster_interchangeable_rows(pos, members, 1.5, 0.5) == ref_cl

    pts = [(3.0, 1.0), (0.0, 0.0), (1.0, 1.0), (1.0, 0.5)]
    assert tuple(geom.nearest_manhattan(1.0, 0.0, pts)) == (
        _nearest_manhattan_py(1.0, 0.0, pts))
    assert _nearest_manhattan(1.0, 0.0, pts) == _nearest_manhattan_py(
        1.0, 0.0, pts)

    a = (0.0, 0.0, 2.0, 2.0)
    b = (1.0, 1.0, 3.0, 1.5)
    assert geom.overlap_area(a, b) == _rect_overlap_area_py(a, b)
    assert _rect_overlap_area(a, b) == _rect_overlap_area_py(a, b)
    assert geom.overlap_1d(0.0, 2.0, 1.5, 4.0) == _overlap_1d_py(
        0.0, 2.0, 1.5, 4.0)
    assert _overlap_1d(0.0, 2.0, 1.5, 4.0) == _overlap_1d_py(0.0, 2.0, 1.5, 4.0)
    boxes = (
        (0.0, 0.0, 4.0, 1.0),
        (5.0, 0.1, 8.0, 0.9),
        (0.0, 3.0, 1.0, 6.0),
        (0.2, 7.0, 0.8, 9.0),
        (0.0, 0.0, 1.0, 1.0),
        (2.0, 2.0, 3.0, 3.0),
    )
    for i, aa in enumerate(boxes):
        for bb in boxes[i:]:
            assert geom.same_edge_gap(aa, bb, 0.5) == _same_edge_gap_py(aa, bb)
            assert _same_edge_gap(aa, bb) == _same_edge_gap_py(aa, bb)

    segs = (
        Seg(0.0, 0.0, 4.0, 0.0, "n1"),
        Seg(2.0, 0.0, 2.0, 3.0, "n2"),
        Seg(0.0, 0.0, 4.0, 0.0, "n1"),
        Seg(1.0, 1.0, 3.0, 1.0, "n3"),
    )
    for s0 in segs:
        for s1 in segs:
            hit = geom.foreign_t_touch(
                s0.x0, s0.y0, s0.x1, s0.y1, s1.x0, s1.y0, s1.x1, s1.y1,
                s0.net == s1.net)
            ref_hit = _foreign_t_touch_py(s0, s1)
            if hit is None:
                assert ref_hit is None
            else:
                assert ref_hit == (float(hit[0]), float(hit[1]))
            assert _foreign_t_touch(s0, s1) == ref_hit

    court = _refdes_hit_court_py(10.0, 20.0, 1.0, 0.0, 0.5, -0.25, None)
    got_c = geom.refdes_hit_court(10.0, 20.0, 1.0, 0.0, 0.5, -0.25, None)
    assert (got_c[0], got_c[1], (got_c[2], got_c[3], got_c[4], got_c[5])) == court
    assert _refdes_hit_court(10.0, 20.0, 1.0, 0.0, 0.5, -0.25, None) == court
    known = (0.0, 0.0, 2.0, 2.0)
    assert _refdes_hit_court(
        10.0, 20.0, 0.0, 1.0, 1.0, 0.0, known) == _refdes_hit_court_py(
            10.0, 20.0, 0.0, 1.0, 1.0, 0.0, known)

    for face in ("+Y", "-Y", "+X", "-X", "nope"):
        for rot in (0.0, 90.0, 180.0, 270.0, 45.0):
            assert _mating_face_out_dir(face, rot) == _mating_face_out_dir_py(
                face, rot)


def test_escape_frame_corridor_and_grid_match_python(geom, monkeypatch):
    from types import SimpleNamespace

    from schgen.generate.pcb import escape as esc
    from schgen.generate.pcb import placement as pl
    from schgen.generate.pcb.constants import (
        BUTTON_GAP,
        PLACE_CLEAR,
        ZONE_PAD,
    )
    from schgen.generate.pcb.escape import (
        CORRIDOR_V_MARGIN,
        R_CONSTRUCT,
        _to_board,
        _to_board_py,
        _to_local,
        _to_local_py,
        corridor_board_rect_py,
        df40_corridor_local_py,
    )
    from schgen.generate.pcb.placement import (
        _grid_controls,
        _grid_controls_py,
        _mirror_offsets_x,
        _mirror_offsets_x_py,
    )
    from schgen.generate.pcb.turn import turn_box

    monkeypatch.setattr(esc._nat, "trace", lambda: True)
    monkeypatch.setattr(pl._nat, "trace", lambda: True)
    monkeypatch.setattr(fp._nat, "trace", lambda: True)

    inst = SimpleNamespace(x=40.0, y=30.0, rotation=90.0)
    for u, v in ((0.0, 0.0), (1.5, -0.8), (-2.0, 3.25)):
        assert tuple(geom.uv_to_board(inst.x, inst.y, u, v, inst.rotation)) == (
            _to_board_py(inst, u, v))
        assert _to_board(inst, u, v) == _to_board_py(inst, u, v)
        bx, by = _to_board_py(inst, u, v)
        assert tuple(geom.board_to_uv(inst.x, inst.y, bx, by, inst.rotation)) == (
            _to_local_py(inst, bx, by))
        assert _to_local(inst, bx, by) == _to_local_py(inst, bx, by)

    pads = {"1": (-3.2, 0.4), "2": (3.2, -0.4), "3": (0.0, 1.1)}
    ref_loc = df40_corridor_local_py(pads)
    assert tuple(geom.corridor_local_from_uv(
        list(pads.values()), R_CONSTRUCT, CORRIDOR_V_MARGIN)) == ref_loc
    ref_br = corridor_board_rect_py(ref_loc, 25.0, 40.0, 180.0)
    assert tuple(geom.corridor_board_rect(ref_loc, 25.0, 40.0, 180.0)) == ref_br

    bbox = (-1.6, -0.8, 1.6, 0.8)
    rot = 90.0
    ox, oy = 4.0, 5.5
    c = turn_box(bbox, rot)
    ref_off = (ox + c[0], oy + c[1], ox + c[2], oy + c[3])
    assert tuple(geom.offset_turned_box(bbox, rot, ox, oy)) == ref_off
    cb = turn_box(bbox, 0.0)
    assert tuple(geom.mirror_offset_x(2.0, 3.0, cb, 20.0)) == (
        round(20.0 - 2.0 - cb[0] - cb[2], 4), 3.0)
    offs = {"R2": (2.0, 3.0), "R1": (0.5, 1.0)}
    bbox_of = {"R1": bbox, "R2": (-2.0, -1.0, 2.0, 1.0)}
    rot_of = {"R1": 0.0, "R2": 90.0}
    assert _mirror_offsets_x(offs, bbox_of, rot_of, 20.0) == (
        _mirror_offsets_x_py(offs, bbox_of, rot_of, 20.0))

    refs = ["SW2", "SW1", "SW3"]
    boxes = {
        "SW1": (-2.0, -1.0, 2.0, 1.0),
        "SW2": (-1.5, -1.5, 1.5, 1.5),
        "SW3": (-2.5, -1.0, 2.5, 1.0),
    }
    ref_grid = _grid_controls_py(refs, boxes, {}, 12.0)
    items = [(r, *boxes[r]) for r in refs]
    native = geom.grid_controls(items, 12.0, BUTTON_GAP, ZONE_PAD, PLACE_CLEAR)
    got_grid = ({r: (x, y) for r, x, y in native[0]},
                [tuple(b) for b in native[1]], float(native[2]),
                float(native[3]))
    assert got_grid == ref_grid
    assert _grid_controls(refs, boxes, {}, 12.0) == ref_grid


def test_escape_seat_classify_and_scan_kernels(geom):
    from schgen.core.sexpr import Sym
    from schgen.generate.floorplan import _floats
    from schgen.generate.pcb.escape import (
        CLR_HOLE_FOREIGN,
        CLR_HOLE_HOLE,
        CLR_HOLE_SAMENET_PAD,
        CLR_MARGIN,
        _via_clear,
    )
    from schgen.generate.pcb.placement import (
        _classify_side,
        _decoupling_caps,
        _is_passive_ref,
    )
    from schgen.generate.pcb.silk import _font_size

    pads = [
        (-1.6, 0.4, 0.3, 0.25),
        (1.6, 0.4, 0.3, 0.25),
        (-1.6, -0.4, 0.3, 0.25),
        (1.6, -0.4, 0.3, 0.25),
        (0.0, 0.0, 1.0, 1.0),
    ]
    row_v, half_w, half_h, span_u, pitch = geom.contact_geometry(pads)
    assert row_v == 0.4
    assert half_w == 0.15
    assert half_h == 0.125
    assert span_u == 1.6
    assert pitch == 3.2

    clear = (CLR_MARGIN, CLR_HOLE_FOREIGN, CLR_HOLE_SAMENET_PAD, CLR_HOLE_HOLE)
    assert _via_clear() == clear
    ok, _msg = geom.via_feasible(
        0.0, 0.0, 0.45, 0.3, [], [], [], [], clear, False)
    assert ok is True
    ok, msg = geom.via_feasible(
        0.0, 0.0, 0.45, 0.3,
        [( -0.1, -0.1, 0.1, 0.1, 0.2, "U1.1")],
        [], [], [], clear, True)
    assert ok is False
    assert "F.Cu" in msg and "annulus" in msg

    assert geom.is_passive_ref("C12") is True
    assert geom.is_passive_ref("RJ45") is False
    assert geom.is_passive_ref("LED1") is False
    assert _is_passive_ref("R2") is True
    assert geom.classify_side(
        "C1", "Capacitor_SMD:C_0402", (-0.5, -0.25, 0.5, 0.25),
        True, True, 12.0, ["DF40C", "Connector"]) == "bottom"
    assert _classify_side(
        "U1", "DF40C-100", (-2, -2, 2, 2), set(), True) == "top"

    class _Pin:
        def __init__(self, ref):
            self.ref = ref
    nets = {
        "+3V3": [_Pin("C1"), _Pin("U1")],
        "GND": [_Pin("C1"), _Pin("U1")],
        "unconnected-C2": [_Pin("C2")],
    }
    assert _decoupling_caps(nets) == {"C1"}
    assert set(geom.decoupling_caps(
        [("+3V3", ["C1", "U1"]), ("GND", ["C1", "U1"])])) == {"C1"}

    assert geom.zone_target_w(100.0, 0.62, 1.0, 8.0) == max(
        8.0, (100.0 * 0.62) ** 0.5)
    plane = tuple(geom.canonical_plane_rect(25.0, 25.0, 100.0, 80.0, 0.5))
    assert plane == (25.5, 25.5, 124.5, 104.5)
    void = tuple(geom.isolation_void_rect((10.0, 12.0, 14.0, 16.0), 0.6))
    assert void == (9.4, 11.4, 14.6, 16.6)

    uv = tuple(geom.board_box_to_uv(0.0, 0.0, 0.0, (1.0, 2.0, 3.0, 4.0)))
    assert uv == (1.0, 2.0, 3.0, 4.0)

    segs = geom.cluster_slot_segs(
        [("1", 0.5, 0.0), ("2", -0.5, 0.0)],
        ["N1", "N2"],
        [(0.0, 0.0), (2.0, 0.0)],
        [("N1", [(10.0, 0.0)]), ("N2", [(0.0, 10.0)])],
    )
    assert len(segs) == 2
    assert len(segs[0]) == 2

    assert _floats("x=-1.25 y=3") == [-1.25, 3.0]
    assert geom.scan_floats("x=-1.25 y=3") == [-1.25, 3.0]
    node = [Sym("property"), "Reference", "R1",
            [Sym("effects"), [Sym("font"), [Sym("size"), 1.2, 1.2]]]]
    assert geom.font_size(node, 1.0) == 1.2
    assert _font_size(node) == 1.2
    placed = geom.inst_pad_xy([("1", 1.0, 0.0)], 10.0, 20.0, 90.0, 3)
    assert placed[0][0] == "1"
    assert placed[0][1] == 10.0
    assert placed[0][2] == 19.0


def test_timing_span_records():
    from schgen.core import timing
    timing.reset()
    with timing.span("unit.example"):
        math.sqrt(2.0)
    text = timing.report()
    assert "unit.example" in text
    timing.reset()


def test_part_catalog_matches_every_part_json(geom, tmp_path):
    from pathlib import Path
    import json
    from schgen.core.model import Circuit

    parts_root = Path(__file__).resolve().parents[2] / "parts"
    json_paths = sorted(parts_root.glob("*/part.json"))
    assert len(json_paths) == 62
    catalog_bin = tmp_path / "catalog.bin"
    assert geom.catalog_compile(str(parts_root), str(catalog_bin)) is True
    assert geom.catalog_open(str(catalog_bin)) is True
    assert geom.catalog_count() == 62
    for json_path in json_paths:
        payload = json.loads(json_path.read_text())
        rec = geom.catalog_lookup(payload["safe_name"])
        assert rec["mpn"] == payload["mpn"]
        assert rec["safe_name"] == payload["safe_name"]
        assert rec["lcsc"] == payload["lcsc"]
        assert rec["prefix"] == payload["prefix"]
        assert rec["lib_id"] == payload["lib_id"]
        assert rec["footprint"] == payload["footprint"]
        assert rec["datasheet"] == payload["datasheet"]
        assert list(rec["models_3d"]) == payload["models_3d"]
        assert [(a, b, c) for a, b, c in rec["pins"]] == [
            (p["num"], p["name"], p["etype"]) for p in payload["pins"]]
        if payload["mpn"] != payload["safe_name"]:
            alias = geom.catalog_lookup(payload["mpn"])
            assert alias["safe_name"] == payload["safe_name"]
    geom.catalog_close()
    from schgen.core import native as nat_mod
    nat_mod._CATALOG_OPEN = False
    c = Circuit("catalog_identity")
    part = c.use_part("TPS54302DDCR", ref="U1")
    assert part.lib_id == "TPS54302DDCR:TPS54302DDCR"
    assert part.footprint == "TPS54302DDCR:TPS54302DDCR"
    assert part.fields["LCSC"] == "C311983"
    assert "GND" in part.pin_names
    assert "1" in part.pin_numbers


def test_part_catalog_rejects_unknown_mpn(geom, tmp_path):
    from pathlib import Path
    parts_root = Path(__file__).resolve().parents[2] / "parts"
    catalog_bin = tmp_path / "catalog.bin"
    assert geom.catalog_compile(str(parts_root), str(catalog_bin)) is True
    assert geom.catalog_open(str(catalog_bin)) is True
    with pytest.raises(RuntimeError, match="unknown mpn"):
        geom.catalog_lookup("NOT-A-REAL-MPN")
    geom.catalog_close()
    from schgen.core import native as nat_mod
    nat_mod._CATALOG_OPEN = False


def test_group_and_reorder_interchangeable_match_python(geom):
    from schgen.generate.pcb.placement import (
        _group_interchangeable_py,
        _reorder_interchangeable_from_pads_py,
    )

    rows = [
        ("R2", "top", "/fp/0402", 0.04, True),
        ("R1", "top", "/fp/0402", 359.96, True),
        ("C1", "bottom", "/fp/0402", 90.0, True),
        ("C2", "bottom", "/fp/0402", 90.04, True),
        ("U1", "top", "/fp/qfn", 0.0, False),
        ("R3", "top", "/fp/0603", -0.06, True),
        ("R4", "top", "/fp/0402", 0.0, True),
    ]
    ref = _group_interchangeable_py(rows)
    got = [(side, fp, float(rot), bool(pas), list(mems))
           for side, fp, rot, pas, mems in geom.group_interchangeable(rows)]
    assert got == ref
    assert any(mems == ["R1", "R2", "R4"] for *_k, mems in ref)
    assert any(mems == ["C1", "C2"] for *_k, mems in ref)
    assert any(round(rot, 1) % 360.0 == 359.9 and mems == ["R3"]
               for _s, _f, rot, _p, mems in ref)

    pos = {
        "R1": (0.0, 0.0),
        "R2": (4.0, 0.0),
        "U1": (4.0, 10.0),
        "U2": (0.0, 10.0),
        "R9": (0.0, 8.0),
    }
    refs_by_sheet = {
        "pwr": ["R2", "R1", "U1", "U2"],
        "skip": ["R9"],
    }
    members = [
        ("R1", "top", "/fp/0402", 0.0, True),
        ("R2", "top", "/fp/0402", 0.0, True),
        ("R9", "top", "/fp/0402", 0.0, True),
    ]
    bbox_of = {
        "R1": (-1.0, -0.5, 1.0, 0.5),
        "R2": (-1.0, -0.5, 1.0, 0.5),
        "R9": (-1.0, -0.5, 1.0, 0.5),
    }
    pad_names_of = {
        "R1": ["1"],
        "R2": ["1"],
        "R9": ["1"],
    }
    pad_local = {
        "R1": {"1": (0.0, 0.0)},
        "R2": {"1": (0.0, 0.0)},
        "R9": {"1": (0.0, 0.0)},
        "U1": {"1": (0.0, 0.0)},
        "U2": {"1": (0.0, 0.0)},
    }
    pin_net = {
        ("R1", "1"): "N1",
        ("R2", "1"): "N2",
        ("U1", "1"): "N1",
        ("U2", "1"): "N2",
        ("R9", "1"): "N1",
    }
    nets = {
        "N1": [("R1", "1"), ("U1", "1")],
        "N2": [("R2", "1"), ("U2", "1")],
    }
    resolvable = {"R1", "R2", "U1", "U2", "R9"}
    skip_sheets = {"skip"}
    conn_seated: set[str] = set()

    ref_pos, ref_rep = _reorder_interchangeable_from_pads_py(
        pos, refs_by_sheet, skip_sheets, conn_seated, members, bbox_of,
        pad_names_of, pad_local, pin_net, nets, resolvable)
    pos_rows, report_rows = geom.reorder_interchangeable(
        [(r, xy[0], xy[1]) for r, xy in pos.items()],
        [(s, list(refs)) for s, refs in refs_by_sheet.items()],
        list(skip_sheets), list(conn_seated), members,
        [(r, *b) for r, b in bbox_of.items()],
        [(r, list(p)) for r, p in pad_names_of.items()],
        [(r, [(p, xy[0], xy[1]) for p, xy in offs.items()])
         for r, offs in pad_local.items()],
        [(r, p, n) for (r, p), n in pin_net.items()],
        [(n, list(pins)) for n, pins in nets.items()],
        list(resolvable),
    )
    got_pos = {r: (x, y) for r, x, y in pos_rows}
    got_rep: dict[str, list[tuple[str, int, int]]] = {}
    for sheet, label, before, best in report_rows:
        got_rep.setdefault(sheet, []).append(
            (label, int(before), int(best)))
    assert got_pos == ref_pos
    assert got_rep == ref_rep
    assert "pwr" in ref_rep
    assert ref_pos["R1"] != pos["R1"] or ref_pos["R2"] != pos["R2"]
    assert ref_pos["R9"] == pos["R9"]

    seated_pos, seated_rep = _reorder_interchangeable_from_pads_py(
        pos, refs_by_sheet, set(), {"R1"}, members, bbox_of,
        pad_names_of, pad_local, pin_net, nets, resolvable)
    seated_rows, seated_report = geom.reorder_interchangeable(
        [(r, xy[0], xy[1]) for r, xy in pos.items()],
        [(s, list(refs)) for s, refs in refs_by_sheet.items()],
        [], ["R1"], members,
        [(r, *b) for r, b in bbox_of.items()],
        [(r, list(p)) for r, p in pad_names_of.items()],
        [(r, [(p, xy[0], xy[1]) for p, xy in offs.items()])
         for r, offs in pad_local.items()],
        [(r, p, n) for (r, p), n in pin_net.items()],
        [(n, list(pins)) for n, pins in nets.items()],
        list(resolvable),
    )
    assert {r: (x, y) for r, x, y in seated_rows} == seated_pos
    seated_got: dict[str, list[tuple[str, int, int]]] = {}
    for sheet, label, before, best in seated_report:
        seated_got.setdefault(sheet, []).append(
            (label, int(before), int(best)))
    assert seated_got == seated_rep
    assert seated_pos["R1"] == pos["R1"]
    assert seated_pos["R2"] == pos["R2"]


def test_stage_flow_and_verify_leftover_kernels_match_python(geom, monkeypatch):
    from schgen.generate.pcb import stage_templates as st
    from schgen.verify import placement_flow_gate as pfg
    from schgen.verify import visual_gate as vg

    monkeypatch.setattr(st._nat, "trace", lambda: True)
    monkeypatch.setattr(pfg._nat, "trace", lambda: True)
    monkeypatch.setattr(vg._nat, "trace", lambda: True)

    pairs = [(1.0, 3.0, "n1"), (0.0, 4.0, "n0"), (2.0, 1.0, "n2")]
    assert st._inversion_count(pairs) == st._inversion_count_py(pairs)
    assert geom.inversion_count(pairs) == st._inversion_count_py(pairs)

    pts = [(0.0, 0.0), (4.0, 2.0), (2.0, 6.0)]
    assert st._centroid(pts) == st._centroid_py(pts)
    assert tuple(geom.points_centroid(pts)) == st._centroid_py(pts)
    assert tuple(geom.rounded_centroid(pts, 4)) == (
        round(sum(p[0] for p in pts) / len(pts), 4),
        round(sum(p[1] for p in pts) / len(pts), 4))
    assert geom.hypot_xy(0.0, 0.0, 3.0, 4.0) == 5.0
    assert pfg._dist((0.0, 0.0), (3.0, 4.0)) == 5.0

    boxes = [(0.0, 0.0, 2.0, 1.0), (3.0, -1.0, 5.0, 4.0)]
    assert tuple(geom.boxes_center(boxes)) == (2.5, 1.5)
    assert tuple(geom.row_extent(boxes, 0.8)) == (
        round(5.0 + 0.8, 4), round(4.0 + 0.8, 4))

    centers = [("1", 0.0, 1.0), ("2", 4.0, 1.2), ("3", 2.0, 0.8)]
    got = dict(geom.long_axis_coords(centers))
    assert got == {"1": 0.0, "2": 4.0, "3": 2.0}

    parts = {"c", "a", "b"}
    deps = {"b": {"a"}, "c": {"b"}}
    assert st._topo_order(parts, deps) == st._topo_order_py(parts, deps) == [
        "a", "b", "c"]
    cycle = {"a": {"b"}, "b": {"a"}}
    assert st._topo_order({"a", "b"}, cycle) is None
    assert st._topo_order_py({"a", "b"}, cycle) is None

    a = vg.Box(0.0, 0.0, 2.0, 2.0, "body", "U1")
    b = vg.Box(1.5, 1.5, 3.0, 3.0, "body", "U2")
    assert a.intersects(b, 0.0) is a.intersects_py(b, 0.0)
    assert a.intersects(b, 0.6) is a.intersects_py(b, 0.6)
