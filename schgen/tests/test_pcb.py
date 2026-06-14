"""Unit tests for the PCB foundation (schgen.generate.pcb) — the pure,
fast pieces: footprint resolution + alias, bbox parsing, the non-overlapping
shelf packer, the layer/stackup structure, and the net-class derivation. The
full net-accurate emission is exercised by `schgen board` (the regression bar);
these lock the building blocks so a regression is caught without a board run.
"""

from __future__ import annotations

import itertools

import pytest

from schgen.generate import pcb


# ---- footprint resolution + alias ------------------------------------------------

def test_resolve_local_part_footprint():
    """A parts/<MPN>/ footprint resolves to its .kicad_mod."""
    mod = pcb.resolve_mod("FUSB302BMPX:FUSB302BMPX")
    assert mod is not None and mod.name == "FUSB302BMPX.kicad_mod"


def test_resolve_std_kicad_footprint():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    assert mod is not None and mod.exists()


def test_footprint_alias_substitution():
    """The 1206 3225->3216 alias resolves to a real .kicad_mod (same body)."""
    assert "Capacitor_SMD:C_1206_3225Metric" in pcb._FOOTPRINT_ALIASES
    mod = pcb.resolve_mod("Capacitor_SMD:C_1206_3225Metric")
    assert mod is not None and "3216" in mod.name


def test_unresolvable_footprint_is_none():
    assert pcb.resolve_mod("No_Such_Lib:No_Such_Footprint") is None


# ---- footprint bbox --------------------------------------------------------------

def test_footprint_bbox_resistor_symmetric():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    bx0, by0, bx1, by1 = pcb._footprint_bbox(mod)
    # 0603 body ~1.6x0.8 with pads — wider than tall, centered near origin.
    assert bx1 > bx0 and by1 > by0
    assert (bx1 - bx0) > (by1 - by0)
    assert abs(bx0 + bx1) < 1.0 and abs(by0 + by1) < 1.0


def test_footprint_bbox_cached():
    mod = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
    a = pcb._footprint_bbox(mod)
    b = pcb._footprint_bbox(mod)
    assert a == b


# ---- the non-overlapping shelf packer --------------------------------------------

def _overlap(a, b, clear):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + clear <= bx0 or bx1 + clear <= ax0
                or ay1 + clear <= by0 or by1 + clear <= ay0)


def test_packer_no_overlap_and_deterministic():
    """Every placed footprint's bbox keeps PLACE_CLEAR from every other and
    from the reserved keep-out; two identical packs give identical positions."""
    bboxes = []
    # a deterministic mix of small + large parts
    for i in range(60):
        w = 1.0 + (i % 5)
        h = 1.0 + (i % 3)
        bboxes.append((-w / 2, -h / 2, w / 2, h / 2))

    def run():
        occ = pcb._Occ(120.0, 100.0, [(40.0, 30.0, 90.0, 72.0)])  # keep-out
        placed = []
        for bb in bboxes:
            ox, oy = occ.place(bb)
            bx0, by0, bx1, by1 = bb
            placed.append((ox + bx0, oy + by0, ox + bx1, oy + by1))
        return placed

    r1 = run()
    r2 = run()
    assert r1 == r2, "packer must be deterministic"
    # pairwise no-overlap with a margin a touch under PLACE_CLEAR (rounding)
    margin = pcb.PLACE_CLEAR - 0.01
    for a, b in itertools.combinations(r1, 2):
        assert not _overlap(a, b, margin), f"{a} overlaps {b}"
    # none collide with the reserved keep-out
    keep = (40.0, 30.0, 90.0, 72.0)
    for a in r1:
        assert not _overlap(a, keep, 0.0), f"{a} overlaps keep-out"


def test_packer_spills_below_board_when_full():
    """Parts that exhaust the board land in the staging strip below it
    (y beyond the board height), never silently dropped or overlapping."""
    occ = pcb._Occ(20.0, 20.0, [])     # tiny board -> forces spill
    big = (-5.0, -5.0, 5.0, 5.0)
    ys = []
    for _ in range(12):
        _ox, oy = occ.place(big)
        ys.append(oy)
    assert max(ys) > 20.0, "some parts must spill into the staging strip"


# ---- layer table + stackup -------------------------------------------------------

def test_four_layer_stackup_is_sig_gnd_pwr_sig():
    node = pcb._layers_node()
    copper = [(e[1], str(e[2])) for e in node[1:]
              if len(e) > 2 and str(e[2]) in ("signal", "power")]
    assert copper == [
        ("F.Cu", "signal"), ("In1.Cu", "power"),
        ("In2.Cu", "power"), ("B.Cu", "signal"),
    ]


def test_stackup_has_two_inner_copper_layers():
    from schgen.core.sexpr import find_all, Sym
    stk = pcb._stackup_node()
    cu = [l for l in find_all(stk, "layer")
          if any(isinstance(x, list) and x and x[0] == Sym("type")
                 and len(x) > 1 and str(x[1]) == "copper" for x in l)]
    names = {str(l[1]) for l in cu}
    assert {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"} <= names


# ---- edge-cuts outline -----------------------------------------------------------

def test_edge_rect_is_closed_rectangle():
    seen = {}
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


# ---- net-class derivation --------------------------------------------------------

def test_net_classes_from_carrier_typed_ports():
    """The carrier's typed ports yield the impedance diff classes + a POWER
    class; the net->class map is non-empty and every class is named."""
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    classes, netclass_of = pcb._net_classes(sheets)
    assert pcb.POWER_CLASS in classes
    # the high-speed classes the carrier declares
    assert {"DP90_USB", "DP100_TMDS"} <= set(classes)
    assert netclass_of, "some nets must be assigned to a class"
    assert all(c in classes for c in netclass_of.values())


# ---- pad-net thermal-via inheritance ---------------------------------------------

def test_thermal_via_inherits_ep_net():
    """A blank no-net pad sitting inside a netted pad inherits that net."""
    from schgen.core.sexpr import Sym
    # one EP pad on GND (net 7) covering origin, one blank no-net via inside it
    ep = [Sym("pad"), "21", Sym("smd"), Sym("rect"),
          [Sym("at"), 0.0, 0.0], [Sym("size"), 4.0, 4.0]]
    via = [Sym("pad"), "", Sym("thru_hole"), Sym("circle"),
           [Sym("at"), 0.5, 0.5], [Sym("size"), 0.6, 0.6]]
    out = [Sym("footprint"), ep, via]
    pad_nets = {"21": (7, "GND"), "": (0, "")}
    inherit = pcb._thermal_via_nets(out, pad_nets)
    # the via is the 2nd pad (ordinal 1) and must inherit (7, GND)
    assert inherit.get(1) == (7, "GND")


def test_thermal_via_no_inherit_when_outside():
    from schgen.core.sexpr import Sym
    ep = [Sym("pad"), "21", Sym("smd"), Sym("rect"),
          [Sym("at"), 0.0, 0.0], [Sym("size"), 1.0, 1.0]]
    via = [Sym("pad"), "", Sym("thru_hole"), Sym("circle"),
           [Sym("at"), 5.0, 5.0], [Sym("size"), 0.6, 0.6]]  # far away
    out = [Sym("footprint"), ep, via]
    inherit = pcb._thermal_via_nets(out, {"21": (7, "GND"), "": (0, "")})
    assert inherit == {}
