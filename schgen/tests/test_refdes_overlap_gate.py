"""Unit tests for the LAW-1 refdes-overlap silk gate (schgen/verify/
refdes_overlap_gate). Synthetic .kicad_pcb fragments — fast, no board build.
The full-board integration is exercised by `schgen board` (which now runs the
gate and FAILs the build on any F.SilkS refdes overprint)."""
from schgen.verify import refdes_overlap_gate as g


def _board(*footprints) -> str:
    return "(kicad_pcb\n" + "\n".join(footprints) + "\n)"


def _fp(ref, fx, fy, lx, ly, layer="F.SilkS", frot=0, hide=False):
    h = " (hide yes)" if hide else ""
    fplayer = "B.Cu" if layer == "B.SilkS" else "F.Cu"   # B.Cu fp is mirrored
    return (f'(footprint "lib:{ref}" (at {fx} {fy} {frot}) (layer "{fplayer}") '
            f'(property "Reference" "{ref}" (at {lx} {ly}) (layer "{layer}"){h}))')


def test_bottom_mirror_compose(tmp_path):
    """A B.Cu footprint is MIRRORED: a ref's board position is fp + R(-frot)·(lx,ly),
    not the top formula. fp C1 at (20,20) frot 90 local (4,0): the mirror puts it at
    (20, 20-4)=(20,16) (the TOP formula would give (20,24)). C2 at (20,16) local (0,0)
    sits there too — so the CORRECT mirror sees them coincident; the wrong one would
    not. Locks the bottom transform."""
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("C1", 20, 20, 4, 0, layer="B.SilkS", frot=90),
                        _fp("C2", 20, 16, 0, 0, layer="B.SilkS")))
    r = g.check(p, enforce_bottom=True)
    assert not r.ok and r.bottom_pairs == 1


def test_separated_refs_pass(tmp_path):
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("U1", 10, 10, 0, 0), _fp("U2", 60, 60, 0, 0)))
    r = g.check(p)
    assert r.ok and not r.top_pairs and r.n_top == 2


def test_coincident_refs_fail(tmp_path):
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("U1", 10, 10, 0, 0), _fp("U2", 10, 10, 0, 0)))
    r = g.check(p)
    assert not r.ok and r.top_pairs == [("U1", "U2")]


def test_hidden_ref_not_counted(tmp_path):
    """A hidden ref (test points, connectors) cannot overprint — it is not drawn."""
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("U1", 10, 10, 0, 0),
                        _fp("TP1", 10, 10, 0, 0, hide=True)))
    r = g.check(p)
    assert r.ok and not r.top_pairs and r.n_top == 1


def test_rotation_composes_local_at(tmp_path):
    """Two refs whose LOCAL ats differ but compose (via footprint rotation) to the
    same board point must be caught — the gate composes, it does not read local.

    KiCad composes a footprint child with a CLOCKWISE rotation in screen coords
    (y-down): bx=fx+lx·ca+ly·sa, by=fy-lx·sa+ly·ca. Verified vs the real DRC-render
    position of a rot-90 part on this board (U11001 local (0,-7.11) -> KiCad x=fx-7.11,
    NOT the CCW fx+7.11). So a rot-90 fp at the origin maps local (0,5) -> board
    (5,0), coincident with a rot-0 fp's local (5,0). (An earlier revision of this
    test asserted the CCW (0,-5) mapping — that encoded the very handedness bug the
    CW fix corrects.)"""
    # fp A at origin rot 0:  local (5,0) -> board (5,0).
    # fp B at origin rot 90: local (0,5) -> board (5,0) too (CW compose).
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("U1", 0, 0, 5, 0, frot=0),
                        _fp("U2", 0, 0, 0, 5, frot=90)))
    r = g.check(p)
    assert not r.ok and len(r.top_pairs) == 1


def test_bottom_overlap_reported_not_enforced(tmp_path):
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("C1", 10, 10, 0, 0, layer="B.SilkS"),
                        _fp("C2", 10, 10, 0, 0, layer="B.SilkS")))
    r = g.check(p)
    assert r.ok and r.bottom_pairs == 1            # reported, OPEN-1b not enforced
    assert not g.check(p, enforce_bottom=True).ok  # enforce flag flips it
