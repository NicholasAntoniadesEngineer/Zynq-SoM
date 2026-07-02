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


# ---------------------------------------------------------------------------
# DFM rework: the declutter's 0.8 mm refdes floor + the widened relocation
# search that replaces sub-floor shrinking (silk.py). Rationale: text below
# ~0.8 mm does not print legibly on common 1oz silk (judgment:0.8 — fab
# legibility floor), so a crowded neighbourhood is solved by finding a clear
# spot FARTHER OUT (more rings/angles), never by unreadable text.
# ---------------------------------------------------------------------------

def test_place_clear_label_widens_past_blocked_ring():
    """When the compact 8-direction scan is FULLY blocked (a 40x40 obstacle
    swallows every candidate out to its 18 mm max offset), the WIDENED search
    (16 angles, larger rings) finds a fully-clear spot beyond it instead of
    returning an overlapping 'best'."""
    from schgen.generate.pcb.silk import _overlap_area, _place_clear_label
    court = (49.0, 49.0, 51.0, 51.0)
    obstacle = (30.0, 30.0, 70.0, 70.0)
    tx, ty, box, off = _place_clear_label(*court, "U1", 1.0, [obstacle])
    assert _overlap_area(box, obstacle) == 0.0, (tx, ty, off)


def test_declutter_never_emits_subfloor_refdes():
    """END-TO-END floor invariant: a dense 9x9 grid of 0603s (every authored
    refdes colliding) is decluttered to ZERO overlaps with every emitted refdes
    height >= the 0.8 mm fab floor — the shrink ladder clamps (the old 0.78/0.62
    tiers may not emit sub-floor text) and the widened relocation search absorbs
    what shrinking no longer may. Locks the DFM rework in both directions:
    no overlap AND no unreadable text."""
    import tempfile
    from pathlib import Path

    from schgen.core import sexpr
    from schgen.core.sexpr import Sym
    from schgen.generate.pcb import (
        ORIGIN_X,
        ORIGIN_Y,
        FootprintInst,
        PcbModel,
        resolve_mod,
    )
    from schgen.generate.pcb.embed import _embed_footprint
    from schgen.generate.pcb.footprint import pad_names
    from schgen.generate.pcb.silk import (
        _REFDES_MIN_SIZE,
        _declutter_refdes,
        _font_size,
    )

    fp = "Capacitor_SMD:C_0603_1608Metric"
    mod = resolve_mod(fp)
    assert mod is not None
    insts = []
    n = 9
    for r in range(n):
        for c in range(n):
            ref = f"C{r * n + c + 1}"
            insts.append(FootprintInst(
                ref=ref, value="x", footprint=fp,
                x=ORIGIN_X + 50 + c * 1.9, y=ORIGIN_Y + 40 + r * 1.9,
                rotation=0.0,
                pad_nets={p: (0, "") for p in pad_names(mod)},
                mod_path=mod, sheet="s", side="top"))
    m = PcbModel(board_w=120.0, board_h=100.0, insts=insts,
                 net_numbers={"": 0}, netclass_of={}, classes={},
                 placed=len(insts), deferred=[], n_top=len(insts),
                 n_bottom=0, two_side=True)
    seq: dict = {}

    def uid(kind):
        seq[kind] = seq.get(kind, 0) + 1
        return f"{kind}-{seq[kind]:04d}"

    doc = [Sym("kicad_pcb")] + [_embed_footprint(i, uid) for i in insts]
    _declutter_refdes(m, uid, doc)

    sizes = []
    for node in doc:
        if isinstance(node, list) and node and node[0] == Sym("footprint"):
            for c in node:
                if (isinstance(c, list) and c and c[0] == Sym("property")
                        and len(c) > 2 and c[1] == "Reference"):
                    sizes.append(_font_size(c))
    assert len(sizes) == n * n
    assert min(sizes) >= _REFDES_MIN_SIZE - 1e-9, sorted(set(sizes))

    p = Path(tempfile.mkdtemp()) / "declutter.kicad_pcb"
    p.write_text(sexpr.dumps(doc) + "\n")
    r = g.check(p, enforce_bottom=True)
    assert r.ok and not r.top_pairs, r.top_pairs
