from __future__ import annotations

import itertools
import json
from types import SimpleNamespace

import pytest

from schgen.generate import pcb


@pytest.fixture
def connector_sheet_model(monkeypatch, tmp_path):
    """Exercise real native packing with connector-sheet auxiliaries only."""
    from schgen.core import ledger
    from schgen.core import link as linker
    from schgen.core.model import Circuit, PinRef
    from schgen.generate import floorplan as fp
    from schgen.generate.board import _renamed_ref
    from schgen.generate.pcb import escape, footprint, placement
    from schgen.verify import powertree

    c = Circuit("som_j1")
    c.part("J1", "Connector_Generic:Conn_02x50_Odd_Even", "DF40",
           "DF40C-100DP-0.4V_51:DF40C-100DP-0.4V_51")
    for i in range(1, 4):
        c.part(f"TP{i}", "Connector:TestPoint", f"PROBE{i}",
               "TestPoint:TestPoint_Pad_D1.0mm")
        c.net(f"PROBE{i}", f"J1.{i}", f"TP{i}.1")
    c.part("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
    c.nets["PROBE1"].pins.append(PinRef("R1", "1"))
    c.nets["PROBE2"].pins.append(PinRef("R1", "2"))
    sc = linker.SheetCircuit("som_j1", c, tmp_path / "som_j1.py", None)
    (tmp_path / "sheet_index.json").write_text(json.dumps({sc.name: 8}))
    monkeypatch.setattr(linker, "all_subsystem_paths", lambda: [sc.path])
    monkeypatch.setattr(linker, "load_subsystem", lambda name: sc)
    monkeypatch.setattr(linker, "load_som_contract", lambda: {})
    monkeypatch.setattr(linker, "link", lambda sheets, contract:
                        linker.LinkResult(sheets=sheets))
    monkeypatch.setattr(powertree, "analyze", lambda sheets:
                        SimpleNamespace(regs=[]))
    for mod, attr in ((placement, "CARRIER"), (footprint, "CARRIER"),
                      (fp, "PROJECT_ROOT")):
        monkeypatch.setattr(mod, attr, tmp_path)
    # Restore outline globals after the actual floorplan solver runs.
    for attr in ("BOARD_W", "BOARD_H", "OUTLINE_NOTE"):
        monkeypatch.setattr(fp, attr, getattr(fp, attr))
    nets = {name: [PinRef(_renamed_ref(p.ref, 8), p.pin) for p in net.pins]
            for name, net in c.nets.items()}
    monkeypatch.setattr(placement, "board_netlist", lambda: nets)
    # Escape routing is independent of the placement regression.
    monkeypatch.setattr(escape, "build_escape_copper", lambda model: ([], {}))
    monkeypatch.setattr(escape, "build_escape_plan", lambda model: None)
    ledger.reset()
    yield SimpleNamespace(sheet=sc, spec=fp.FloorplanSpec("auto", {}, {}))
    ledger.reset()


@pytest.mark.parametrize("two_side", [False, True])
def test_connector_sheet_auxiliaries_are_packed_and_emitted(
        connector_sheet_model, two_side):
    from schgen.core import ledger
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb import placement

    f = connector_sheet_model
    stages = []
    model = placement.build_model(two_side=two_side, spec=f.spec,
                                  plan_sink=stages.append)
    expected = {"J8001", "TP8001", "TP8002", "TP8003", "R8001"}
    parts = [p for p in model.insts if p.sheet == "som_j1"]
    assert {p.ref for p in parts} == expected
    assert len(parts) == len(expected)
    assert not model.deferred
    plan = stages[0].plan
    block, = plan.blocks
    assert block.name == "som_j1" and block.n_parts == 4
    probes = [p for p in parts if p.ref.startswith("TP")]
    for p in probes:
        assert p.side == "top"
        assert p.pad_nets["1"][1] == f"PROBE{p.ref[-1]}"
        assert pcb.ORIGIN_X < p.x < pcb.ORIGIN_X + model.board_w
        assert pcb.ORIGIN_Y < p.y < pcb.ORIGIN_Y + model.board_h
        x0, y0, x1, y1 = model.som_keepout
        assert not (x0 < p.x < x1 and y0 < p.y < y1)
    boxes = [pcb._inst_pad_bbox(p) for p in probes]
    for a, b in itertools.combinations(boxes, 2):
        assert not _overlap(a, b, pcb.PLACE_CLEAR - 0.05)
    connector = next(p for p in parts if p.ref == "J8001")
    j = next(j for j in plan.som.js if j.ref == "J1")
    from schgen.core import quantize as q
    assert connector.x == q.fixed_part_grid(pcb.ORIGIN_X + plan.som_x + j.x)
    assert connector.y == q.fixed_part_grid(pcb.ORIGIN_Y + plan.som_y + j.y)
    assert connector.rotation == (90.0 if j.w < j.h else 0.0)
    assert connector.side == "top"
    aux_area = sum(fp.part_dims(p.footprint)[0] * fp.part_dims(p.footprint)[1]
                   for r, p in f.sheet.circuit.parts.items() if r != "J1")
    assert fp._raw_component_area([f.sheet]) == pytest.approx(aux_area)
    assert not ledger.problems()


@pytest.mark.parametrize("failure_point", ["apply_chosen_shapes", "som_core_rect"])
def test_placement_failure_closes_ledger(connector_sheet_model, monkeypatch,
                                        failure_point):
    from schgen.core import ledger
    from schgen.core.link import LinkResult
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb import placement

    original = KeyError("TP8001")

    def fail(*args, **kwargs):
        raise original

    monkeypatch.setattr(placement, failure_point, fail)
    with pytest.raises(KeyError) as raised:
        placement.build_model(two_side=False, spec=connector_sheet_model.spec)
    assert raised.value is original
    assert not ledger.problems()
    assert any(e.name == "pcb.placement" for e in ledger.entries())
    with ledger.step("census"):
        pass
    with ledger.step("docs.floorplan"):
        sheets = [connector_sheet_model.sheet]
        fp.build_plan(sheets, LinkResult(sheets=sheets), [],
                      spec=connector_sheet_model.spec)
    assert not ledger.problems()


def test_connector_only_sheet_has_no_auxiliary_block(connector_sheet_model):
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb import placement

    f = connector_sheet_model
    c = f.sheet.circuit
    c.parts = {"J1": c.parts["J1"]}
    for net in c.nets.values():
        net.pins = [p for p in net.pins if p.ref == "J1"]
    stages = []
    model = placement.build_model(two_side=False, spec=f.spec,
                                  plan_sink=stages.append)
    assert [p.ref for p in model.insts if p.sheet == "som_j1"] == ["J8001"]
    assert not stages[0].plan.blocks
    assert fp._raw_component_area([f.sheet]) == 0.0


def test_connector_estimator_keeps_fixed_pads_when_auxiliaries_turn(
        connector_sheet_model, monkeypatch, tmp_path):
    from schgen.core import link as linker
    from schgen.core.model import Circuit
    from schgen.generate import floorplan as fp
    from schgen.generate.pcb import placement

    f = connector_sheet_model
    c = Circuit("connector_peer")
    c.part("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
    c.net("PROBE1", "R1.1")
    c.net("PROBE2", "R1.2")
    c.part("TP1", "Connector:TestPoint", "PROBE3",
           "TestPoint:TestPoint_Pad_D1.0mm")
    c.net("PROBE3", "TP1.1")
    peer = linker.SheetCircuit(c.name, c, tmp_path / "connector_peer.py", None)
    sheets = [f.sheet, peer]
    monkeypatch.setattr(linker, "all_subsystem_paths",
                        lambda: [sc.path for sc in sheets])
    monkeypatch.setattr(linker, "load_subsystem",
                        lambda name: next(sc for sc in sheets if sc.name == name))
    zg = placement.subsystem_zone_geometry(spec=f.spec)
    plan = fp.Plan(fp.extract_som())
    captured = []

    def capture(pts, *args):
        captured.extend(pts)
        return 0.0

    monkeypatch.setattr(fp, "_cross_net_cost", capture)
    evaluate = fp._cross_estimator(plan, zg, sheets)
    blocks = [fp.Block("som_j1", "interior", x=10.0, y=10.0),
              fp.Block("connector_peer", "interior", x=70.0, y=20.0)]
    fixed_pads = []
    auxiliary_pads = []
    assert len(zg.shapes["som_j1"]) > 1
    for k in range(len(zg.shapes["som_j1"])):
        blocks[0].shape_idx = k
        captured.clear()
        evaluate(blocks)
        fixed_pads.append(sorted(p for p in captured if p[2] == "J8001"))
        auxiliary_pads.append(sorted(p for p in captured
                                     if p[3] == "som_j1" and p[2] != "J8001"))
    assert fixed_pads[0]
    assert all(p == fixed_pads[0] for p in fixed_pads)
    assert auxiliary_pads[0]
    assert any(p != auxiliary_pads[0] for p in auxiliary_pads)


def test_resolve_local_part_footprint():
    mod = pcb.resolve_mod("FUSB302BMPX:FUSB302BMPX")
    assert mod is not None and mod.name == "FUSB302BMPX.kicad_mod"


def test_resolve_std_kicad_footprint():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    assert mod is not None and mod.exists()


def test_footprint_alias_substitution():
    assert "Capacitor_SMD:C_1206_3225Metric" in pcb._FOOTPRINT_ALIASES
    mod = pcb.resolve_mod("Capacitor_SMD:C_1206_3225Metric")
    assert mod is not None and "3216" in mod.name


def test_unresolvable_footprint_is_none():
    assert pcb.resolve_mod("No_Such_Lib:No_Such_Footprint") is None


def test_footprint_bbox_resistor_symmetric():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    bx0, by0, bx1, by1 = pcb._footprint_bbox(mod)
    assert bx1 > bx0 and by1 > by0
    assert (bx1 - bx0) > (by1 - by0)
    assert abs(bx0 + bx1) < 1.0 and abs(by0 + by1) < 1.0


def test_footprint_bbox_cached():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    a = pcb._footprint_bbox(mod)
    b = pcb._footprint_bbox(mod)
    assert a == b


def _overlap(a, b, clear):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + clear <= bx0 or bx1 + clear <= ax0
                or ay1 + clear <= by0 or by1 + clear <= ay0)


def test_shelf_pack_no_overlap_and_deterministic():
    items = []
    for i in range(40):
        w = 1.0 + (i % 5)
        h = 1.0 + (i % 3)
        items.append((f"R{i}", (-w / 2, -h / 2, w / 2, h / 2), 0.0))

    def run():
        off, w, h = pcb._shelf_pack(items, target_w=20.0)
        boxes = []
        for ref, bb, _rot in items:
            ox, oy = off[ref]
            bx0, by0, bx1, by1 = bb
            boxes.append((ox + bx0, oy + by0, ox + bx1, oy + by1))
        return off, w, h, boxes

    off1, w1, h1, boxes1 = run()
    off2, w2, h2, boxes2 = run()
    assert (off1, w1, h1) == (off2, w2, h2), "packer must be deterministic"
    margin = pcb.PLACE_CLEAR - 0.05
    for a, b in itertools.combinations(boxes1, 2):
        assert not _overlap(a, b, margin), f"{a} overlaps {b}"
    for _bx0, _by0, bx1, by1 in boxes1:
        assert bx1 <= w1 + 1e-6 and by1 <= h1 + 1e-6, "part outside its zone box"


def test_shelf_pack_keeps_bottom_parts_out_of_top_thru_hole_blockers():
    items = [(f"C{i}", (-0.5, -0.5, 0.5, 0.5), 0.0) for i in range(6)]
    blocker = (0.0, 0.0, 6.0, 6.0)
    off, w, h = pcb._shelf_pack(items, target_w=10.0, blockers=[blocker])
    for ref, bb, _rot in items:
        ox, oy = off[ref]
        bx0, by0, bx1, by1 = bb
        box = (ox + bx0, oy + by0, ox + bx1, oy + by1)
        assert not _overlap(box, blocker, 0.0), f"{ref} sits in the blocker"


def test_build_model_no_off_board_parts(carrier_model):
    model = carrier_model
    x0, y0 = pcb.ORIGIN_X, pcb.ORIGIN_Y
    x1, y1 = pcb.ORIGIN_X + model.board_w, pcb.ORIGIN_Y + model.board_h
    for inst in model.insts:
        cx0, cy0, cx1, cy1 = pcb._inst_pad_bbox(inst)
        assert (cx0 >= x0 - 1e-6 and cy0 >= y0 - 1e-6
                and cx1 <= x1 + 1e-6 and cy1 <= y1 + 1e-6), \
            f"{inst.ref} ({inst.sheet}) copper off-board: " \
            f"({cx0:.1f},{cy0:.1f})..({cx1:.1f},{cy1:.1f})"


def test_four_layer_stackup_is_sig_gnd_pwr_sig():
    node = pcb._layers_node()
    copper = [(e[1], str(e[2])) for e in node[1:]
              if len(e) > 2 and str(e[2]) in ("signal", "power")]
    assert copper == [
        ("F.Cu", "signal"), ("In1.Cu", "power"),
        ("In2.Cu", "power"), ("B.Cu", "signal"),
    ]


def test_stackup_has_two_inner_copper_layers():
    from schgen.core.sexpr import Sym, find_all
    stk = pcb._stackup_node()
    cu = [layer for layer in find_all(stk, "layer")
          if any(isinstance(x, list) and x and x[0] == Sym("type")
                 and len(x) > 1 and str(x[1]) == "copper" for x in layer)]
    names = {str(layer[1]) for layer in cu}
    assert {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"} <= names


def test_edge_rect_is_closed_rectangle():
    segs = pcb._edge_rect(0, 0, 120, 100, lambda k: f"u:{k}")
    assert len(segs) == 4
    from schgen.core.sexpr import find
    xs, ys = [], []
    for s in segs:
        st, en = find(s, "start"), find(s, "end")
        xs += [st[1], en[1]]
        ys += [st[2], en[2]]
        assert find(s, "layer")[1] == "Edge.Cuts"
    assert (min(xs), max(xs), min(ys), max(ys)) == (0, 120, 0, 100)


def test_net_classes_from_carrier_typed_ports():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    classes, netclass_of = pcb._net_classes(sheets)
    assert pcb.POWER_CLASS in classes
    assert {"DP90_USB", "DP100_TMDS"} <= set(classes)
    assert netclass_of, "some nets must be assigned to a class"
    assert all(c in classes for c in netclass_of.values())


def test_thermal_via_inherits_ep_net():
    from schgen.core.sexpr import Sym
    ep = [Sym("pad"), "21", Sym("smd"), Sym("rect"),
          [Sym("at"), 0.0, 0.0], [Sym("size"), 4.0, 4.0]]
    via = [Sym("pad"), "", Sym("thru_hole"), Sym("circle"),
           [Sym("at"), 0.5, 0.5], [Sym("size"), 0.6, 0.6]]
    out = [Sym("footprint"), ep, via]
    pad_nets = {"21": (7, "GND"), "": (0, "")}
    inherit = pcb._thermal_via_nets(out, pad_nets)
    assert inherit.get(1) == (7, "GND")


def test_thermal_via_no_inherit_when_outside():
    from schgen.core.sexpr import Sym
    ep = [Sym("pad"), "21", Sym("smd"), Sym("rect"),
          [Sym("at"), 0.0, 0.0], [Sym("size"), 1.0, 1.0]]
    via = [Sym("pad"), "", Sym("thru_hole"), Sym("circle"),
           [Sym("at"), 5.0, 5.0], [Sym("size"), 0.6, 0.6]]
    out = [Sym("footprint"), ep, via]
    inherit = pcb._thermal_via_nets(out, {"21": (7, "GND"), "": (0, "")})
    assert inherit == {}
