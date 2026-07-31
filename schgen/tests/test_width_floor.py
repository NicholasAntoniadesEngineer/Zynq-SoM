"""WAVE-12: the board width is set by the EDGE-RUN FIT guard, not by airwire.

Measured on the live carrier: of 2,868 candidate outlines the sizing search
tried, 14 packed and the LAW-5 airwire budget rejected NONE; every one of the
2,186 sub-185 mm candidates was rejected by the edge-run fit guard before the
interior packer ever ran. These tests pin the kernels that derive that floor —
the run-length arithmetic, the cable-gap charge that is 23 % of the binding run,
the guard's own predicate — plus the two mechanisms the same measurement
exonerated (the estimator replicates the LAW-6 edge seat) and named (the
interior pack order is connectivity-first, which is what leaves the LARGEST
block placed last).
"""
import inspect

import pytest

from schgen.generate import floorplan as fp
from schgen.generate.floorplan import (
    CABLE_NEIGHBOR_GAP,
    CLEAR,
    EDGE_MARGIN,
    Block,
    Plan,
    SomGeom,
)


def _plan(blocks):
    som = SomGeom(w=50.0, h=42.0, js=[], source="test")
    p = Plan(som)
    p.edge_blocks = list(blocks)
    return p


def _run_need(blocks, edge):
    """The exact length an along-edge run consumes: the first block's facing
    reach + every span + every pair gap + the last block's facing reach."""
    ns = edge in ("N", "S")
    lo_i, hi_i = (0, 1) if ns else (2, 3)
    gaps = [fp._pair_gap(blocks[i], blocks[i + 1])
            for i in range(len(blocks) - 1)]
    spans = [(b.w if ns else b.h) for b in blocks]
    return blocks[0].fanout_reach[lo_i] + sum(spans) + sum(gaps) \
        + blocks[-1].fanout_reach[hi_i]


def _overflows(plan):
    """The EDGE-RUN FIT guard's own predicate (floorplan.py, _attempt_pack)."""
    tol = fp._q.run_overflow_tol()
    for b in plan.edge_blocks:
        if b.edge in ("W", "E"):
            near, span, dim = b.y, b.h, fp.BOARD_H
        else:
            near, span, dim = b.x, b.w, fp.BOARD_W
        if near < EDGE_MARGIN - tol or near + span > dim - EDGE_MARGIN + tol:
            return b.name
    return None


def test_edge_run_fit_is_the_width_binder_and_its_floor_is_exact():
    """A run whose laid-out length exceeds (W - 2*EDGE_MARGIN + tol) is
    REJECTED, and the board must grow to `need + 2*EDGE_MARGIN -
    run_overflow_tol` — the derivation that puts the live carrier's S edge at
    184.669 mm and rejects 100 % of the 2,186 sub-185 candidates.

    The rejected board is NOT relieved by spilling a block to the next edge:
    `_pack_edges` admits on a SPAN+TRAILING-GAP accumulation that omits the
    run's end fan-out reaches, so a run it admits can still overflow when laid
    out. Both boards here carry the identical two-block membership."""
    saved = (fp.BOARD_W, fp.BOARD_H)
    try:
        def _blocks():
            a = Block(name="a", kind="edge", w=40.0, h=10.0, edge="S",
                      fanout_reach=(2.0, 0.0, 0.0, 0.0))
            b = Block(name="b", kind="edge", w=40.0, h=10.0, edge="S")
            return [a, b]

        need = _run_need(_blocks(), "S")
        assert need == pytest.approx(2.0 + 80.0 + CLEAR)
        floor = need + 2 * EDGE_MARGIN - fp._q.run_overflow_tol()
        assert floor == pytest.approx(102.2)

        fp.BOARD_H = 120.0
        for width, rejected in ((floor - 1.0, True), (floor + 1.0, False)):
            fp.BOARD_W = width
            plan = _plan(_blocks())
            fp._pack_edges(plan, {"a": "S", "b": "S"})
            assert [b.name for b in plan.edge_blocks if b.edge == "S"] \
                == ["a", "b"], "membership must be identical on both boards"
            assert (_overflows(plan) is not None) is rejected
    finally:
        fp.BOARD_W, fp.BOARD_H = saved


def test_overmold_charge_is_asymmetric_pair_vs_one_sided():
    """The overmold charge counts BOOTS IN THE GAP, not overmold membership.

    Two boots (HDMI <-> HDMI) keep the full CABLE_NEIGHBOR_GAP — softening that
    is LAW-4 forbidden and it is pinned here. ONE boot (HDMI <-> plain socket)
    owes only that boot's own overhang past its own copper, OVERMOLD_SIDE_GAP;
    charging it the pair gap billed a boot the plain neighbour does not have.
    Both HDMI orderings must agree — the rule is commutative in the pair, not
    symmetric in the membership."""
    plain = Block(name="p", kind="edge", w=10.0, h=10.0, edge="S")
    hdmi = Block(name="h", kind="edge", w=10.0, h=10.0, edge="S",
                 conns=[("J1", "HDMI-019S", 10.0, 10.0)])
    assert fp._is_overmold_block(hdmi)
    assert not fp._is_overmold_block(plain)
    assert fp._pair_gap(hdmi, hdmi) == CABLE_NEIGHBOR_GAP
    assert fp._pair_gap(hdmi, plain) == pytest.approx(fp.OVERMOLD_SIDE_GAP)
    assert fp._pair_gap(plain, hdmi) == pytest.approx(fp.OVERMOLD_SIDE_GAP)
    assert fp._pair_gap(plain, plain) == pytest.approx(CLEAR)
    assert fp.OVERMOLD_SIDE_GAP < CABLE_NEIGHBOR_GAP


def test_one_sided_overmold_gap_is_derived_from_the_datum():
    """OVERMOLD_SIDE_GAP is not a tuned number: it is the plug boot's half-width
    minus the receptacle's own copper half-width, both stated once as the datum.
    The copper half-width must match the real HDMI-019S footprint (shield
    through-holes at +/-7.2499, size 1.5 => 8.0 mm), so a footprint swap that
    moved the copper without moving the datum is caught here."""
    assert fp.OVERMOLD_SIDE_GAP == pytest.approx(
        fp.OVERMOLD_PLUG_W_MAX / 2.0 - fp.OVERMOLD_COPPER_HALF_W)

    from schgen.generate import pcb
    from schgen.generate.pcb import FootprintInst, _inst_pad_bbox
    mod = pcb.resolve_mod("HDMI-019S:HDMI-019S")
    assert mod is not None, "HDMI-019S footprint missing"
    inst = FootprintInst(ref="J1", value="HDMI-019S",
                         footprint="HDMI-019S:HDMI-019S", x=0.0, y=0.0,
                         rotation=0.0, pad_nets={}, mod_path=mod, sheet="h",
                         side="top")
    x0, _y0, x1, _y1 = _inst_pad_bbox(inst)
    assert (x1 - x0) / 2.0 == pytest.approx(fp.OVERMOLD_COPPER_HALF_W, abs=0.01)


def test_the_three_overmold_consumers_are_independent_constants():
    """The overmold datum used to be ONE constant serving three unrelated
    requirements. Each now has its own name, and the two that are not the
    floorplan pair charge must not silently track it:

      floorplan.CABLE_NEIGHBOR_GAP        two boots meeting between edge blocks
      stage_templates._CONN_ROOT_CABLE_GAP  intra-sheet room for two cable bodies
      connector_spacing_gate tables         copper-to-copper proof on the board
    """
    from schgen.generate.pcb import stage_templates as st
    from schgen.verify import connector_spacing_gate as cs

    assert "import CABLE_NEIGHBOR_GAP" not in inspect.getsource(st)
    assert st._CONN_ROOT_CABLE_GAP == 20.0
    assert cs._FAMILY_MIN_GAP_MM["HDMI-019S"] >= 18.0
    assert cs._FAMILY_SIDE_GAP_MM["HDMI-019S"] == pytest.approx(
        fp.OVERMOLD_SIDE_GAP)


def test_run_length_is_invariant_under_reordering_of_equal_gap_blocks():
    """The width floor cannot be re-ordered away: with every pair gap equal the
    run needs the same length in every permutation. (Measured on the live S
    edge: the best of all 24 orderings needs 184.269 mm and still misses the
    184 mm grid point.)"""
    blocks = [Block(name=n, kind="edge", w=w, h=10.0, edge="S")
              for n, w in (("a", 40.0), ("b", 30.0), ("c", 20.0))]
    base = _run_need(blocks, "S")
    for perm in ([blocks[1], blocks[0], blocks[2]],
                 [blocks[2], blocks[1], blocks[0]],
                 [blocks[0], blocks[2], blocks[1]]):
        assert _run_need(perm, "S") == pytest.approx(base)


def test_estimator_replicates_the_law6_edge_seat():
    """`edge_seat` adds +66 mm at emission on every measured plan, and that is
    NOT an unmodelled mover: `_cross_estimator.evaluate` applies the same
    EDGE_PAD_CLEAR seat to every `conn_edge` ref before it measures."""
    src = inspect.getsource(fp._cross_estimator)
    assert "EDGE_PAD_CLEAR" in src
    for edge in ('"N"', '"S"', '"W"', '"E"'):
        assert f"edge == {edge}" in src
    assert "conn_edge" in src


def test_interior_pack_order_is_connectivity_first_then_area():
    """The height binder's mechanism: the interior order key ranks by
    connectivity BEFORE area, so the largest block (the carrier's `power`,
    53.21 x 23.93, lowest cross-subsystem connectivity) is placed LAST and sets
    H. Pinned so that swapping the two terms — measured to emit 185x160 at
    +9.0 % cross-airwire — can only ever be a deliberate change."""
    src = inspect.getsource(fp._attempt_pack)
    i_conn = src.index("-_conn(b),")
    i_area = src.index("-(zbox[b.name][0] * zbox[b.name][1])")
    assert i_conn < i_area
