"""WAVE-17: the interior packer's BOUNDED RE-SEAT RETRY.

``_attempt_pack``'s interior loop was greedy first-fit-nearest-anchor with NO
backtracking: one block whose every registered shape returned None from
place_near killed the whole candidate outline. Measured on the carrier, that —
not any block's geometry — was the W = 172 wall: at W in [168, 171] one block
was fatal in 48/48 interior rejects, shrinking it was worthless AND non-
monotone, while freeing 5 mm at a neighbouring seat packed all four widths.

These tests pin the correction on synthetic geometry: it fires and rescues a
pack the greedy order loses, it is bounded and terminating, it is deterministic
under shuffled inputs, a pack that succeeds without it is untouched, and the
place_near WINDOW the retry uses returns the full-lattice first fit.
"""
import pytest

from schgen.core import fallbacks as _fb
from schgen.generate import floorplan as fp
from schgen.generate.floorplan import Block, Plan, SomGeom, _Occupancy

BOARD = (60.0, 30.0)


@pytest.fixture(autouse=True)
def _board():
    saved = (fp.BOARD_W, fp.BOARD_H)
    fp.BOARD_W, fp.BOARD_H = BOARD
    ev = _fb.snapshot()
    yield
    _fb.restore(ev)
    fp.BOARD_W, fp.BOARD_H = saved


def _scene(sizes, conns):
    """A plan with no edge blocks, a corner-parked 1x1 SoM, and one interior
    block per (name -> (w, h)). ``conns`` sets each block's affinity sum, which
    is the pack ORDER key, and every block also pulls on the previous one."""
    som = SomGeom(w=1.0, h=1.0, js=(), source="test")
    plan = Plan(som)
    plan.som_x = plan.som_y = 1.5
    plan.punch_free = False
    names = list(sizes)
    interior = [Block(name=n, kind="interior", zone="E") for n in names]
    zbox = {n: sizes[n] for n in names}
    affinity = {n: {} for n in names}
    for i, n in enumerate(names):
        if i:
            affinity[n][names[i - 1]] = 1.0
    for n, c in conns.items():
        affinity[n][n + "_lead"] = c
    return plan, interior, zbox, affinity


def _pack(sizes, conns, budget=None, interior_order=None):
    plan, interior, zbox, affinity = _scene(sizes, conns)
    if interior_order is not None:
        interior = [next(b for b in interior if b.name == n)
                    for n in interior_order]
    saved = fp._RESEAT_EVICT_BUDGET
    if budget is not None:
        fp._RESEAT_EVICT_BUDGET = budget
    mark = len(_fb.snapshot())
    try:
        ok = fp._attempt_pack(plan, interior, {}, zbox, affinity, {})
    finally:
        fp._RESEAT_EVICT_BUDGET = saved
    fired = sum(1 for e in _fb.snapshot()[mark:]
                if e == "interior_reseat_retry")
    pose = {b.name: (b.x, b.y, b.w, b.h) for b in interior}
    return ok, fired, pose


def _legal(pose):
    """Replay the packed result through a virgin occupancy: every block must
    still fit against all the others, the SoM pad and the corner keepouts."""
    occ = _Occupancy()
    occ.add(0.0, 0.0, 4.0, 4.0)
    for cx, cy in ((0.0, 0.0), (fp.BOARD_W - fp.MH_CORNER_KO, 0.0),
                   (fp.BOARD_W - fp.MH_CORNER_KO,
                    fp.BOARD_H - fp.MH_CORNER_KO),
                   (0.0, fp.BOARD_H - fp.MH_CORNER_KO)):
        occ.add(cx, cy, fp.MH_CORNER_KO, fp.MH_CORNER_KO)
    for x, y, w, h in pose.values():
        if not occ.fits(x, y, w, h, mask=fp.OCC_TOP):
            return False
        occ.add(x, y, w, h, mask=fp.OCC_TOP)
    return True


# The wall in miniature: `wide` only fits the 60x30 board's middle band (it is
# wider than the 39.4 mm channel the corner keepouts leave), and `first` — placed
# first because it is more connected — lands in the middle of that band.
WALL = ({"first": (8.0, 8.0), "wide": (45.0, 8.0)}, {"first": 2.0})


def test_retry_rescues_a_pack_the_greedy_first_fit_loses():
    ok0, fired0, _ = _pack(*WALL, budget=0)
    assert not ok0 and fired0 == 0, "the greedy wall must be real"
    ok, fired, pose = _pack(*WALL)
    assert ok, "the bounded re-seat retry must clear the greedy wall"
    assert fired == 1
    assert _legal(pose), "a retry may only produce seats that were always legal"


def test_retry_never_produces_an_illegal_seat():
    """The legality predicate is untouched, so the rescued layout replays
    clean through a virgin occupancy — the eviction/restore bookkeeping cannot
    leave a stale rect behind."""
    _ok, _fired, pose = _pack(*WALL)
    assert _legal(pose)
    boxes = list(pose.values())
    for i, (x, y, w, h) in enumerate(boxes):
        for x2, y2, w2, h2 in boxes[i + 1:]:
            assert (x + w <= x2 or x2 + w2 <= x
                    or y + h <= y2 or y2 + h2 <= y)


def test_retry_is_inert_when_the_greedy_pack_succeeds():
    """Every pack that first-fit already wins is byte-identical with the retry
    live — it only runs on the ``return False`` paths."""
    fits = ({"first": (8.0, 8.0), "second": (8.0, 8.0)}, {"first": 2.0})
    ok_off, fired_off, pose_off = _pack(*fits, budget=0)
    ok_on, fired_on, pose_on = _pack(*fits)
    assert ok_off and ok_on
    assert fired_off == 0 and fired_on == 0
    assert pose_off == pose_on


def test_retry_is_bounded_and_gives_up_loudly():
    """Two blocks that BOTH need the same exclusive band: evicting the
    incumbent seats the newcomer but the incumbent then has nowhere to go, so
    the trial is rolled back, the candidate pool is exhausted and the packer
    returns False exactly as before — no budget is consumed by a failure and
    the search is not extended."""
    both = ({"first": (45.0, 8.0), "wide": (45.0, 8.0)}, {"first": 2.0})
    ok, fired, _ = _pack(*both)
    assert not ok
    assert fired == 0
    assert fp._RESEAT_EVICT_BUDGET == 3


@pytest.mark.parametrize("sizes,conns", [
    WALL,
    ({"first": (8.0, 8.0), "second": (8.0, 8.0), "wide": (45.0, 8.0)},
     {"first": 3.0, "second": 2.0}),
    ({"first": (45.0, 8.0), "wide": (45.0, 8.0)}, {"first": 2.0}),
    ({"first": (8.0, 8.0), "second": (45.0, 8.0), "wide": (45.0, 8.0)},
     {"first": 3.0, "second": 2.0}),
])
def test_retry_events_never_exceed_the_per_pack_budget(sizes, conns):
    """Whatever the scene, one _attempt_pack call may evict at most
    _RESEAT_EVICT_BUDGET blocks, and whatever it returns True on is legal."""
    ok, fired, pose = _pack(sizes, conns)
    assert fired <= fp._RESEAT_EVICT_BUDGET
    assert not ok or _legal(pose)


def test_retry_is_deterministic_including_under_shuffled_inputs():
    """The eviction candidate order is a total order over a LIST — (distance,
    placement index, name) — never a set or dict iteration over geometry, so
    the pack is a pure function of its inputs."""
    ok_a, fired_a, pose_a = _pack(*WALL)
    ok_b, fired_b, pose_b = _pack(*WALL)
    assert (ok_a, fired_a, pose_a) == (ok_b, fired_b, pose_b)
    ok_c, fired_c, pose_c = _pack(*WALL, interior_order=["wide", "first"])
    assert (ok_a, fired_a, pose_a) == (ok_c, fired_c, pose_c)


def test_retry_window_returns_the_full_lattice_first_fit(monkeypatch):
    """The retry narrows each place_near to a window its eviction geometry
    proves contains every newly-fitting cell. Every windowed call made during a
    real rescue must return exactly what the unwindowed scan returns."""
    real = fp._Occupancy.place_near
    seen = [0]

    def checked(self, ax, ay, w, h, reach=fp._ZeroReach, inset=fp._ZeroReach,
                mask=fp.OCC_PUNCH, comps=(), win=None):
        got = real(self, ax, ay, w, h, reach, inset, mask, comps, win)
        if win is not None:
            seen[0] += 1
            assert got == real(self, ax, ay, w, h, reach, inset, mask, comps)
        return got

    monkeypatch.setattr(fp._Occupancy, "place_near", checked)
    ok, fired, _pose = _pack(*WALL)
    assert ok and fired == 1
    assert seen[0] >= 1, "the rescue must have gone through the window"


def test_occupancy_remove_then_add_restores_the_predicate():
    """The primitive the trial rollback rests on: a rect removed and re-added
    leaves the accept/reject boolean identical everywhere, whatever the
    internal rect ORDER becomes."""
    occ = _Occupancy()
    for x, y in ((0.0, 0.0), (20.0, 0.0), (0.0, 20.0)):
        occ.add(x, y, 10.0, 10.0, mask=fp.OCC_TOP)
    probes = [(px, py) for px in range(0, 40, 3) for py in range(0, 40, 3)]
    before = [occ.fits(float(px), float(py), 6.0, 6.0, mask=fp.OCC_TOP)
              for px, py in probes]
    occ.remove(20.0, 0.0, 10.0, 10.0, mask=fp.OCC_TOP)
    occ.add(20.0, 0.0, 10.0, 10.0, mask=fp.OCC_TOP)
    after = [occ.fits(float(px), float(py), 6.0, 6.0, mask=fp.OCC_TOP)
             for px, py in probes]
    assert before == after
