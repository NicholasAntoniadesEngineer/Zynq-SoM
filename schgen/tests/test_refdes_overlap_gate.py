"""Unit tests for the LAW-1 refdes-overlap silk gate (schgen/verify/
refdes_overlap_gate). Synthetic .kicad_pcb fragments — fast, no board build.
The full-board integration is exercised by `schgen board` (which now runs the
gate and FAILs the build on any F.SilkS refdes overprint)."""
from schgen.verify import refdes_overlap_gate as g


def _board(*footprints) -> str:
    return "(kicad_pcb\n" + "\n".join(footprints) + "\n)"


def _fp(ref, fx, fy, lx, ly, layer="F.SilkS", frot=0, hide=False):
    h = " (hide yes)" if hide else ""
    return (f'(footprint "lib:{ref}" (at {fx} {fy} {frot}) '
            f'(property "Reference" "{ref}" (at {lx} {ly}) (layer "{layer}"){h}))')


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
    same board point must be caught — the gate composes, it does not read local."""
    # fp A at origin rot 0: local (5,0) -> board (5,0).
    # fp B at origin rot 90: local (0,-5) -> board (5,0) too.
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("U1", 0, 0, 5, 0, frot=0),
                        _fp("U2", 0, 0, 0, -5, frot=90)))
    r = g.check(p)
    assert not r.ok and len(r.top_pairs) == 1


def test_bottom_overlap_reported_not_enforced(tmp_path):
    p = tmp_path / "b.kicad_pcb"
    p.write_text(_board(_fp("C1", 10, 10, 0, 0, layer="B.SilkS"),
                        _fp("C2", 10, 10, 0, 0, layer="B.SilkS")))
    r = g.check(p)
    assert r.ok and r.bottom_pairs == 1            # reported, OPEN-1b not enforced
    assert not g.check(p, enforce_bottom=True).ok  # enforce flag flips it
