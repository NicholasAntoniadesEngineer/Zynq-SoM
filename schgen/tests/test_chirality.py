"""Wave-9 CHIRALITY: KiCad-exact mirrored bottom emission (pcb/mirror.py).

PINNED GROUND TRUTH (pcbnew 10.0.2 FOOTPRINT::Flip LEFT_RIGHT, measured on
AP2112K SOT-23-5 at rots 0/37/90 and CP2102N QFN24 rot 30 with rot-90 oval
pads, runtime objects + saved file): stored local y -> -y, stored local
angles -> -a, instance rotation t -> (180 - t) % 360, layers/justify via the
unchanged embed._flip_to_bottom, (model ...) untouched. The full-strength
proof lives in the wave ledger: a 32-footprint fixture emitted by
embed._embed_footprint matched pcbnew's own flip objects pad-for-pad at
0.0 nm (584 pads) with kicad-cli DRC at 0 violations. These tests pin the
transform, the placed-pattern mirror identity R_cw(180-t)*M_y == M_x*R_cw(t)
on the emitted file, the zone-variant algebra, and the loud failure modes.
"""

from __future__ import annotations

import dataclasses
import math
import shutil
import subprocess

import pytest

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.generate.floorplan import load_floorplan_spec
from schgen.generate.pcb.constants import PARTS_DIR, FootprintInst
from schgen.generate.pcb.embed import (
    _embed_footprint,
    _mirror_thermal_spec,
)
from schgen.generate.pcb.footprint import _footprint_bbox, pad_names
from schgen.generate.pcb.mating_face import _inst_pad_geom, _rot_bbox_cw
from schgen.generate.pcb.mirror import (
    MIRROR_DIR,
    MirrorUnsupported,
    is_mirrored_path,
    mirror_fp_doc,
    mirrored_mod,
)
from schgen.generate.pcb.placement import (
    apply_chosen_shapes,
    subsystem_zone_geometry,
)

_CHIRAL_PARTS = [
    "AP2112K-3.3TRG1",
    "CP2102N-A02-GQFN24R",
    "FUSB302BMPX",
    "HX5008NLT",
    "TYPE-C-31-M-12",
]


def _src(name: str):
    return PARTS_DIR / name / f"{name}.kicad_mod"


def test_mirror_involution_on_real_chiral_parts():
    for name in _CHIRAL_PARTS:
        doc = sexpr.loads(_src(name).read_text())
        orig = sexpr.dumps(doc)
        mirror_fp_doc(doc)
        once = sexpr.dumps(doc)
        assert once != orig, f"{name}: mirror changed nothing (chiral part)"
        mirror_fp_doc(doc)
        assert sexpr.dumps(doc) == orig, f"{name}: mirror is not an involution"


def test_mirror_pinned_doc_transform():
    doc = sexpr.loads(
        '(footprint "t:asym" (layer "F.Cu")'
        ' (property "Reference" "X" (at 1.5 -2 45) (layer "F.SilkS")'
        '  (effects (font (size 1 1) (thickness 0.15))))'
        ' (fp_line (start -2.15 -1.7) (end -2.15 2.1) (stroke (width 0.1)'
        '  (type solid)) (layer "F.SilkS"))'
        ' (fp_arc (start 1 0.2) (mid 0 1.2) (end -1 0.2) (stroke (width 0.1)'
        '  (type solid)) (layer "F.Fab"))'
        ' (fp_poly (pts (xy 0 0) (xy 1 0.5) (xy 0.25 1)) (stroke (width 0.1)'
        '  (type solid)) (fill yes) (layer "F.Fab"))'
        ' (pad "1" smd roundrect (at -0.9 1.3 90) (size 0.6 1.2)'
        '  (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))'
        ' (pad "2" thru_hole oval (at 2 -1) (size 1.6 1.2) (drill 0.8)'
        '  (layers "*.Cu" "*.Mask"))'
        ' (model "x.wrl" (offset (xyz 1 2 3)) (scale (xyz 1 1 1))'
        '  (rotate (xyz 0 0 90))))')
    mirror_fp_doc(doc)
    txt = sexpr.dumps(doc)
    prop = sexpr.find(doc, "property")
    assert sexpr.find(prop, "at")[1:] == [1.5, 2, -45]
    line = sexpr.find(doc, "fp_line")
    assert sexpr.find(line, "start")[1:] == [-2.15, 1.7]
    assert sexpr.find(line, "end")[1:] == [-2.15, -2.1]
    arc = sexpr.find(doc, "fp_arc")
    assert sexpr.find(arc, "mid")[1:] == [0, -1.2]
    poly = sexpr.find(doc, "fp_poly")
    assert [tuple(x[1:]) for x in sexpr.find_all(sexpr.find(poly, "pts"), "xy")] \
        == [(0, 0), (1, -0.5), (0.25, -1)]
    pads = [n for n in doc if isinstance(n, list) and n and n[0] == Sym("pad")]
    assert sexpr.find(pads[0], "at")[1:] == [-0.9, -1.3, -90]
    assert sexpr.find(pads[1], "at")[1:] == [2, 1]
    model = sexpr.find(doc, "model")
    assert sexpr.find(sexpr.find(model, "offset"), "xyz")[1:] == [1, 2, 3]
    assert sexpr.find(sexpr.find(model, "rotate"), "xyz")[1:] == [0, 0, 90]
    assert '"F.Cu"' in txt and '"B.Cu"' not in txt


def test_mirror_unsupported_constructs_raise():
    cases = [
        '(footprint "t:x" (pad "1" smd roundrect (at 0 0) (size 1 1)'
        ' (layers "F.Cu") (chamfer top_left) (chamfer_ratio 0.2)))',
        '(footprint "t:x" (pad "1" thru_hole circle (at 0 0) (size 2 2)'
        ' (drill 1 (offset 0.3 0)) (layers "*.Cu")))',
        '(footprint "t:x" (fp_text_box "hi" (at 0 0) (layer "F.Fab")))',
        '(footprint "t:x" (pad "1" smd custom (at 0 0) (size 1 1)'
        ' (layers "F.Cu") (options (clearance outline) (anchor rect))'
        ' (primitives (gr_curve (pts (xy 0 0) (xy 1 1))))))',
    ]
    for text in cases:
        doc = sexpr.loads(text)
        with pytest.raises(MirrorUnsupported):
            mirror_fp_doc(doc)


def test_mirrored_mod_cache_and_location(tmp_path):
    p1 = mirrored_mod(_src("AP2112K-3.3TRG1"))
    p2 = mirrored_mod(_src("AP2112K-3.3TRG1"))
    assert p1 == p2 and p1.exists()
    assert p1.parent == MIRROR_DIR and is_mirrored_path(p1)
    assert MIRROR_DIR.name == ".mirrored_fp"
    assert PARTS_DIR not in p1.parents, \
        "mirror cache must stay OUT of parts/ (model3d gate census)"
    doc = sexpr.loads(p1.read_text())
    mirror_fp_doc(doc)
    src_norm = sexpr.dumps(sexpr.loads(_src("AP2112K-3.3TRG1").read_text()))
    assert sexpr.dumps(doc) == src_norm, "mirror(cache file) != source"
    assert pad_names(p1) == pad_names(_src("AP2112K-3.3TRG1"))


def _emitted_pad_globals(node: list) -> dict[str, list[tuple[float, float]]]:
    """pcbnew loader math on an emitted (footprint ...) node: pad center =
    fp_at + R_cw(fp_rot) . stored_local, side-blind (the pinned rule)."""
    at = next(x for x in node
              if isinstance(x, list) and x and x[0] == Sym("at"))
    fx, fy = float(at[1]), float(at[2])
    rot = math.radians(float(at[3]) if len(at) > 3 else 0.0)
    cs, sn = math.cos(rot), math.sin(rot)
    out: dict[str, list[tuple[float, float]]] = {}
    for p in node:
        if not (isinstance(p, list) and p and p[0] == Sym("pad")):
            continue
        pat = sexpr.find(p, "at")
        px, py = float(pat[1]), float(pat[2])
        out.setdefault(str(p[1]), []).append(
            (fx + px * cs + py * sn, fy - px * sn + py * cs))
    return out


def _mk_inst(ref, name, mod, x, y, rot, side, mirror):
    return FootprintInst(ref=ref, value=name, footprint=f"t:{name}", x=x, y=y,
                         rotation=rot, pad_nets={}, mod_path=mod, sheet="t",
                         side=side, mirror=mirror)


def test_emitted_bottom_is_exact_xmirror_of_top():
    """THE chirality theorem on the emitted file: the mirrored bottom
    instance's pad-net pattern is the exact X-mirror (about the instance
    center) of the top instance's — per pad NAME, so a chiral part's pin 1
    lands where physically flipping the part puts it."""
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return f"00000000-0000-4000-8000-{n:012d}"

    for name in ("AP2112K-3.3TRG1", "CP2102N-A02-GQFN24R", "HX5008NLT"):
        src = _src(name)
        mir = mirrored_mod(src)
        for rot in (0.0, 37.0, 90.0, 270.0):
            top = _embed_footprint(
                _mk_inst("T1", name, src, 100.0, 50.0, rot, "top", False), uid)
            bot = _embed_footprint(
                _mk_inst("B1", name, mir, 100.0, 50.0,
                         (180.0 - rot) % 360.0, "bottom", True), uid)
            gt = _emitted_pad_globals(top)
            gb = _emitted_pad_globals(bot)
            assert sorted(gt) == sorted(gb)
            worst = 0.0
            for pn in gt:
                want = sorted((round(200.0 - gx, 6), round(gy, 6))
                              for gx, gy in gt[pn])
                got = sorted((round(gx, 6), round(gy, 6)) for gx, gy in gb[pn])
                for (wx, wy), (gx, gy) in zip(want, got, strict=True):
                    worst = max(worst, math.hypot(wx - gx, wy - gy))
            assert worst <= 1e-6, (name, rot, worst)
            btxt = sexpr.dumps(bot)
            assert '"B.Cu"' in btxt
            assert '"F.Cu"' not in btxt.replace('"F.Cu" "B.Cu"', "")


def test_inst_pad_geom_reads_mirrored_doc():
    src = _src("AP2112K-3.3TRG1")
    mir = mirrored_mod(src)
    t = {n: (x, y) for n, x, y, _ in _inst_pad_geom(
        _mk_inst("T1", "a", src, 100.0, 50.0, 0.0, "top", False))}
    b = {n: (x, y) for n, x, y, _ in _inst_pad_geom(
        _mk_inst("B1", "a", mir, 100.0, 50.0, 180.0, "bottom", True))}
    for pn, (tx, ty) in t.items():
        bx, by = b[pn]
        assert abs((200.0 - tx) - bx) < 2e-3 and abs(ty - by) < 2e-3, pn
    tb = _footprint_bbox(src)
    bb = _footprint_bbox(mir)
    assert bb == (tb[0], round(-tb[3], 3), tb[2], round(-tb[1], 3))


def test_embed_guard_rejects_malformed_mirror_insts():
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return f"00000000-0000-4000-8000-{n:012d}"

    src = _src("AP2112K-3.3TRG1")
    mir = mirrored_mod(src)
    with pytest.raises(AssertionError, match="chiral-wrong"):
        _embed_footprint(
            _mk_inst("X1", "a", mir, 10.0, 10.0, 0.0, "top", True), uid)
    with pytest.raises(AssertionError, match="chiral-wrong"):
        _embed_footprint(
            _mk_inst("X1", "a", src, 10.0, 10.0, 0.0, "bottom", True), uid)


def test_thermal_spec_mirror():
    spec = {"pour": (-3.0, -4.75, 4.4, 4.75),
            "via_sites": [(1.55, -2.5), (2.85, 0.0)],
            "max_vias": 8, "pour_layers": ("F.Cu", "B.Cu"), "cite": "x"}
    m = _mirror_thermal_spec(spec)
    assert m["pour"] == (-3.0, -4.75, 4.4, 4.75)
    assert m["via_sites"] == [(1.55, 2.5), (2.85, 0.0)]
    assert m["pour_layers"] == ("B.Cu", "F.Cu")
    assert m["max_vias"] == 8 and spec["via_sites"][0] == (1.55, -2.5)


@pytest.fixture(scope="module")
def zg_either_pair():
    spec = load_floorplan_spec()
    spec2 = dataclasses.replace(
        spec, interior={**spec.interior, "hdmi_rx_term": {"side": "either"}})
    return subsystem_zone_geometry(two_side=True, spec=spec2)


def test_bottom_shape_carries_kicad_exact_mirror(zg_either_pair):
    zg = zg_either_pair
    shapes = zg.shapes["hdmi_rx_term"]
    bots = [s for s in shapes if s.side == "bottom"]
    assert bots
    s0 = shapes[0]
    for bs in bots:
        assert set(bs.mirror) == set(bs.top_off)
        for r, mp in bs.mirror.items():
            assert is_mirrored_path(mp)
            assert bs.extra_rot[r] == (180.0 - s0.extra_rot.get(r, 0.0)) % 360.0
            ox, oy = s0.top_off[r]
            assert bs.top_off[r] == (round(bs.w - ox, 4), oy)
            c0 = _rot_bbox_cw(zg.bbox_of[r], s0.extra_rot.get(r, 0.0))
            b0 = (ox + c0[0], oy + c0[1], ox + c0[2], oy + c0[3])
            cm = _rot_bbox_cw(_footprint_bbox(mp), bs.extra_rot[r])
            mx, my = bs.top_off[r]
            bm = (mx + cm[0], my + cm[1], mx + cm[2], my + cm[3])
            exp = (bs.w - b0[2], b0[1], bs.w - b0[0], b0[3])
            assert all(abs(a - b) < 5e-3 for a, b in zip(bm, exp, strict=True)), \
                (r, bm, exp)


def test_apply_chosen_shapes_rebinds_mirrored_docs(zg_either_pair):
    zg = zg_either_pair
    shapes = zg.shapes["hdmi_rx_term"]
    k = next(i for i, s in enumerate(shapes) if s.side == "bottom")
    zg2 = apply_chosen_shapes(zg, {"hdmi_rx_term": k})
    for r in shapes[k].top_off:
        assert zg2.side_of[r] == "bottom"
        assert r in zg2.mirror_refs
        assert is_mirrored_path(zg2.resolvable[r])
        tb = _footprint_bbox(zg.resolvable[r])
        assert zg2.bbox_of[r] == (tb[0], round(-tb[3], 3),
                                  tb[2], round(-tb[1], 3))
    for r in shapes[k].bot_off:
        assert r not in zg2.mirror_refs
        assert zg2.resolvable[r] == zg.resolvable[r]
    assert not zg.mirror_refs
    assert not any(is_mirrored_path(p) for p in zg.resolvable.values())


def test_zone_shape_metrics_uses_mirrored_pads(zg_either_pair):
    from schgen.generate.floorplan_compose import (
        _local_metrics_one,
        zone_shape_metrics,
    )
    zg = zg_either_pair
    shapes = zg.shapes["hdmi_rx_term"]
    k = next(i for i, s in enumerate(shapes) if s.side == "bottom")
    bs = shapes[k]
    s0 = shapes[0]
    m0 = _local_metrics_one(zg, s0.top_off, s0.bot_off, s0.extra_rot,
                            (s0.w, s0.h))
    mk = zone_shape_metrics(zg)[("hdmi_rx_term", k)]
    pu0 = {r: (x0, y0, x1, y1) for r, x0, y0, x1, y1 in m0.pad_union}
    puk = {r: (x0, y0, x1, y1) for r, x0, y0, x1, y1 in mk.pad_union}
    for r in bs.mirror:
        x0, y0, x1, y1 = pu0[r]
        exp = (bs.w - x1, y0, bs.w - x0, y1)
        assert all(abs(a - b) < 5e-3
                   for a, b in zip(puk[r], exp, strict=True)), (r, puk[r], exp)


def test_chiral_part_in_synthetic_zone_variant(zg_either_pair):
    from schgen.generate.pcb.placement import _bottom_zone_shapes
    zg = zg_either_pair
    chiral = next(r for r, m in sorted(zg.resolvable.items())
                  if "AP2112K" in str(m) and not is_mirrored_path(m))
    passives = [r for r, m in sorted(zg.resolvable.items())
                if "0402" in str(m)][:2]
    refs = [chiral, *passives]
    side_of = {r: "top" for r in refs}
    shapes = _bottom_zone_shapes("__syn__", refs, side_of, zg.bbox_of,
                                 zg.resolvable, frozenset(), None, {})
    assert shapes and all(s.side == "bottom" for s in shapes)
    for s in shapes:
        assert chiral in s.mirror and is_mirrored_path(s.mirror[chiral])
        assert s.extra_rot[chiral] == 180.0


_KICAD = shutil.which("kicad-cli")


@pytest.mark.skipif(_KICAD is None, reason="kicad-cli not on PATH")
def test_fixture_board_drc_clean_both_sides(tmp_path):
    """Emit one chiral part top + mirrored bottom through the REAL embed
    path and run KiCad's own DRC: zero violations (courtyards, clearance,
    mask, silk — both sides). Unconnected items are the unrouted rats of the
    single-net fixture, exactly like the unrouted foundation board."""
    from schgen.generate.pcb.embed import _edge_rect, _layers_node, _stackup_node
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return f"00000000-0000-4000-8000-{n:012d}"

    doc: list = [Sym("kicad_pcb"), [Sym("version"), 20260206],
                 [Sym("generator"), "schgen"],
                 [Sym("generator_version"), "1.0"],
                 [Sym("general"), [Sym("thickness"), 1.6],
                  [Sym("legacy_teardrops"), Sym("no")]],
                 [Sym("paper"), "A3"], _layers_node(),
                 [Sym("setup"), _stackup_node(),
                  [Sym("pad_to_mask_clearance"), 0],
                  [Sym("allow_soldermask_bridges_in_footprints"), Sym("yes")]],
                 [Sym("net"), 0, ""], [Sym("net"), 1, "N_T"],
                 [Sym("net"), 2, "N_B"]]
    doc.extend(_edge_rect(0.0, 0.0, 100.0, 100.0, uid))
    name = "CP2102N-A02-GQFN24R"
    src = _src(name)
    mir = mirrored_mod(src)
    pn_t = {p: (1, "N_T") for p in pad_names(src) if p.strip()}
    pn_b = {p: (2, "N_B") for p in pad_names(src) if p.strip()}
    ti = _mk_inst("T1", name, src, 30.0, 50.0, 37.0, "top", False)
    bi = _mk_inst("B1", name, mir, 70.0, 50.0, 143.0, "bottom", True)
    ti = dataclasses.replace(ti, pad_nets=pn_t)
    bi = dataclasses.replace(bi, pad_nets=pn_b)
    doc.append(_embed_footprint(ti, uid))
    doc.append(_embed_footprint(bi, uid))
    board = tmp_path / "chir.kicad_pcb"
    board.write_text(sexpr.dumps(doc) + "\n")
    rpt = tmp_path / "drc.rpt"
    subprocess.run([_KICAD, "pcb", "drc", "--severity-error", "-o", str(rpt),
                    str(board)], check=True, capture_output=True, text=True)
    text = rpt.read_text()
    assert "** Found 0 DRC violations **" in text, text[:2000]
