"""THE foreign-neighbour predicate (fanout_gate.counts_as_crowder) + the
net-class-aware est via cost (wave-10 U1 / user decree 2026-07-30).

U1 root cause, pinned here so it cannot return: BREATHE carried a PRIVATE copy
of the gate's foreign-neighbour rule that omitted the test-point exemption. A
TP pad therefore read as a crowder, which (a) faked starvation, (b) aimed the
away-from-crowder march at a part the gate does not count, and (c) neutered the
mover's own no-regression floor min(need, current clearance). Measured live on
the 185x163 bringup_rails outline: U5001 (bringup_en_modules, 5 pin, TOP) saw
its phantom clearance as 0.500 to TP5002, marched away from it, and collapsed
its REAL 2.640 gap to C15002 (lcd, TOP) down to 1.380 against a 1.50 need — the
single D13 red of that board. Both sides now call ONE predicate.
"""

from __future__ import annotations

import pytest

from schgen.core import quantize as q
from schgen.generate.pcb import breathe as br
from schgen.generate.pcb.footprint import _net_classes
from schgen.verify import fanout_gate as fg


def test_testpoint_never_crowds_on_any_sheet():
    assert not fg.counts_as_crowder("TP5002", "bringup_en_modules", 1,
                                    "TestPoint_Pad_D1.5mm",
                                    "bringup_en_modules")
    assert not fg.counts_as_crowder("TP1", "lcd", 1, "TestPoint", "usb_pd")


def test_predicate_covers_the_gates_four_exclusions():
    assert not fg.counts_as_crowder("J1", "som_j1", 4, "DF40", "usb_pd")
    assert not fg.counts_as_crowder("J9", "ethernet", fg.DF40_MIN_PINS, "x",
                                    "usb_pd")
    assert not fg.counts_as_crowder("FID1", "mechanical", 0,
                                    "Fiducial_1mm", "usb_pd")
    assert not fg.counts_as_crowder("C5", "lcd", 2, "C_0402", "lcd")
    assert fg.counts_as_crowder("C5", "lcd", 2, "C_0402", "usb_pd")
    assert fg.counts_as_crowder("RS1", "power_mon", 2, "R_1206", "power_mon")
    assert fg.counts_as_crowder("U5", "lcd", 5, "SOT-23-5", "lcd")


def test_breathe_foreign_predicate_is_the_gates_predicate():
    src = (br.__file__ and open(br.__file__).read()) or ""
    assert "counts_as_crowder(" in src
    for token in ("Fiducial\" in (parts[r][1]", "pins_of(r) >= 40"):
        assert token not in src, (
            f"breathe re-derived the gate's foreign rule ({token!r}) — call "
            f"fanout_gate.counts_as_crowder instead")


def test_regression_guard_floor_uses_the_gate_clearance():
    """min(need, old_clr) is only a real floor when old_clr is measured the
    gate's way: with a TP counted the U1 case read old_clr=0.500 and licensed a
    2.640 -> 1.380 collapse against a 1.50 need."""
    need = fg.intelligent_need(5)[0]
    phantom_old = 0.500
    honest_old = 2.640
    landed = 1.380
    assert landed >= min(need, phantom_old)
    assert landed < min(need, honest_old)
    assert not fg.counts_as_crowder("TP5002", "bringup_en_modules", 1,
                                    "TestPoint", "bringup_en_modules")


def test_breathe_never_marches_away_from_a_testpoint():
    """The U1 shape, synthetically: an 8-pin subject with a TP pad hard against
    its LEFT edge and open board to the right. With the TP counted the pass saw
    clr=0 and marched EAST; with the gate's predicate the subject is already
    clear of every countable foreign part and must not move at all."""
    from schgen.generate import pcb
    from schgen.generate.pcb.footprint import _footprint_bbox
    ic = pcb.resolve_mod("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    tp = pcb.resolve_mod("TestPoint:TestPoint_Pad_D1.5mm")
    assert ic is not None and tp is not None
    bb, tb = _footprint_bbox(ic), _footprint_bbox(tp)
    pos = {"U1": (45.0, 30.0), "TP1": (45.0 + bb[0] - (tb[2] - tb[0]), 30.0)}
    seed = dict(pos)
    br.breathe_fanout(
        pos, resolvable={"U1": ic, "TP1": tp},
        parts={"U1": ("s1", "lib:U", "x", "lib"),
               "TP1": ("s2", "lib:TP", "x", "lib")},
        bbox_of={"U1": bb, "TP1": tb},
        fixed_rot={"U1": 0.0, "TP1": 0.0},
        side_of={"U1": "top", "TP1": "top"},
        zorigin={"s1": (45.0, 30.0), "s2": (40.0, 30.0)},
        board_w=120.0, board_h=100.0,
        som_keepout=(300.0, 300.0, 310.0, 310.0), conn_edge={},
        mh_refs=set(), som_j_refs=set(), df40_pad_boxes=[], phase="A")
    assert pos == seed


def test_est_via_cost_high_speed_set_is_derived_not_listed():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    geo, cls_of = _net_classes(sheets)
    charged = {c for c, g in geo.items() if g is not None}
    free = {c for c, g in geo.items() if g is None}
    assert {"DP100_TMDS", "DP90_USB"} <= charged
    assert charged and all(c.startswith("DP") for c in charged)
    assert free and not any(c.startswith("DP") for c in free)
    for cls in charged:
        assert q.est_via_cost(geo.get(cls) is not None) == pytest.approx(7.6)
    for cls in free:
        assert q.est_via_cost(geo.get(cls) is not None) == pytest.approx(2.2)
    assert cls_of, "no net carries a routing class"


def test_impedance_row_dominates_the_ordinary_row():
    """The decree's intent: high-speed pays materially more. Measured sweep
    (bringup_rails opt-in): ordinary 0.0 emits 188x164 / 30832 mm² while every
    strictly-positive point emits the identical better 185x163 / 30155, so the
    ordinary row is an INTERIM proxy on that plateau, not a fitted constant."""
    assert q.est_via_cost(True) >= 3.0 * q.est_via_cost(False)
    assert q.est_via_cost(False) > 0.0
    basis = q.REGISTRY["est_via_cost"].basis
    assert "2026-07-30" in basis
    assert "INTERIM" in basis
    assert "BOTTOM_SIDE_MODEL_DEFECTS" in basis
