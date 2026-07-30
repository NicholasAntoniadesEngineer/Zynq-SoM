"""KiCad-EXACT chiral mirror of a .kicad_mod for bottom-side (B.Cu) emission.

pcbnew 10.0.2 GROUND TRUTH (``FOOTPRINT::Flip`` LEFT_RIGHT about the footprint
origin — derived by flipping real parts (AP2112K SOT-23-5 at 0/37/90,
CP2102N QFN24 with rot-90 oval pads at 30) and reading both the runtime pad
objects and the saved board file):

* every stored LOCAL coordinate:   ``y -> -y``   (x is NOT touched),
* every stored LOCAL angle:        ``a -> -a``   (pad and text ``(at)``),
* the instance placement rotation: ``theta -> (180 - theta) % 360``,
* layer tokens F.* <-> B.* and ``(justify mirror)`` on text glyphs — applied
  at embed time by ``embed._flip_to_bottom`` exactly as for the achiral-swap
  population (this module NEVER touches layers),
* the ``(model ...)`` 3D node is untouched (KiCad renders back-side flips).

KiCad loads a footprint side-blind (pad center = fp_at + R_cw(fp_rot)·local),
so a document mirrored here and placed at ``(180 - t) % 360`` lands the exact
X-mirror of the part's top-side pattern about its origin:
``R_cw(180 - t)·M_y == M_x·R_cw(t)`` — the physically correct land pattern
for a part flipped onto the bottom copper, for ANY (chiral) footprint.

The mirrored document is materialised as a REAL .kicad_mod under
``.mirrored_fp/`` at the repo root (derived cache, gitignored,
content-addressed rewrite — deliberately OUTSIDE parts/, which gates census).
A mirrored instance is then simply an instance whose ``mod_path`` IS the
mirrored file: every geometry kernel (``_pad_boxes`` / ``_rot_pad_bbox`` /
``_footprint_bbox`` / ``_inst_pad_geom`` / ``_mod_pads`` / ``has_thru_pads``)
and the embed writer stay correct with zero side-dependent branches, and the
board file carries exactly what a pcbnew flip of the library part would
store. Any construct this transform has not been proven against raises
``MirrorUnsupported`` — never a silent partial mirror.
"""

from __future__ import annotations

import os
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym

from .constants import REPO_ROOT

MIRROR_DIR = REPO_ROOT / ".mirrored_fp"


class MirrorUnsupported(AssertionError):
    pass


def _neg(v):
    return 0 - v


def _neg_fields(node: list, tag_positions: dict[str, tuple[int, ...]]) -> None:
    head = str(node[0])
    for pos in tag_positions.get(head, ()):
        if len(node) > pos and isinstance(node[pos], (int, float)):
            node[pos] = _neg(node[pos])


_PT_TAGS = {"start": (2,), "end": (2,), "mid": (2,), "center": (2,)}
_AT_TAGS = {"at": (2, 3)}


def _mirror_pts(node: list) -> None:
    for xy in sexpr.find_all(node, "xy"):
        if len(xy) >= 3:
            xy[2] = _neg(xy[2])


def _mirror_primitive(g: list, ctx: str) -> None:
    head = str(g[0])
    if head in ("gr_line", "gr_rect", "gr_circle", "gr_arc"):
        for sub in g:
            if isinstance(sub, list) and sub:
                _neg_fields(sub, _PT_TAGS)
    elif head == "gr_poly":
        pts = sexpr.find(g, "pts")
        if pts is not None:
            _mirror_pts(pts)
    else:
        raise MirrorUnsupported(
            f"{ctx}: custom-pad primitive {head!r} has no proven mirror rule")


_PAD_PLAIN = {
    "size", "layers", "roundrect_rratio", "net", "uuid", "pinfunction",
    "pintype", "solder_mask_margin", "solder_paste_margin",
    "solder_paste_margin_ratio", "clearance", "zone_connect",
    "thermal_bridge_width", "thermal_bridge_angle", "thermal_gap",
    "die_length", "remove_unused_layers", "keep_end_layers", "property",
    "zone_layer_connections",
}


def _mirror_pad(pad: list, ctx: str) -> None:
    for sub in pad:
        if not (isinstance(sub, list) and sub and isinstance(sub[0], Sym)):
            continue
        head = str(sub[0])
        if head == "at":
            _neg_fields(sub, _AT_TAGS)
        elif head == "drill":
            if sexpr.find(sub, "offset") is not None:
                raise MirrorUnsupported(
                    f"{ctx}: pad drill (offset ...) has no proven mirror rule "
                    f"— pin it against a pcbnew flip before allowing it")
        elif head == "options":
            continue
        elif head == "primitives":
            for g in sub:
                if isinstance(g, list) and g and isinstance(g[0], Sym):
                    _mirror_primitive(g, ctx)
        elif head in ("chamfer", "chamfer_ratio", "rect_delta"):
            raise MirrorUnsupported(
                f"{ctx}: pad {head!r} has no proven mirror rule (corner "
                f"remap unproven) — pin it against a pcbnew flip first")
        elif head in _PAD_PLAIN:
            continue
        else:
            raise MirrorUnsupported(
                f"{ctx}: pad child {head!r} is not in the proven mirror set")


_FP_GEOM_PTS = {"fp_line", "fp_rect", "fp_circle", "fp_arc"}
_FP_PLAIN = {
    "version", "generator", "generator_version", "layer", "descr", "tags",
    "attr", "model", "solder_mask_margin", "solder_paste_margin",
    "solder_paste_ratio", "solder_paste_margin_ratio", "clearance",
    "autoplace_cost90", "autoplace_cost180", "net_tie_pad_groups",
    "private_layers", "embedded_fonts", "uuid", "path", "sheetname",
    "sheetfile", "zone_connect", "thermal_bridge_width", "thermal_gap",
    "duplicate_pad_numbers_are_jumpers", "jumper_pad_groups",
}


def mirror_fp_doc(doc: list) -> None:
    """In-place pcbnew-LEFT_RIGHT geometry mirror of a parsed ``(footprint``
    document (layers untouched — ``embed._flip_to_bottom`` owns those)."""
    assert isinstance(doc, list) and doc and doc[0] == Sym("footprint"), \
        "mirror_fp_doc wants a parsed (footprint ...) document"
    name = doc[1] if len(doc) > 1 else "?"
    for node in doc:
        if not (isinstance(node, list) and node and isinstance(node[0], Sym)):
            continue
        head = str(node[0])
        if head == "pad":
            _mirror_pad(node, f"{name} pad {node[1] if len(node) > 1 else '?'}")
        elif head in ("fp_text", "property"):
            for sub in node:
                if isinstance(sub, list) and sub:
                    _neg_fields(sub, _AT_TAGS)
        elif head in _FP_GEOM_PTS:
            if head == "fp_arc" and sexpr.find(node, "angle") is not None:
                raise MirrorUnsupported(
                    f"{name}: legacy fp_arc (angle) form has no proven "
                    f"mirror rule")
            for sub in node:
                if isinstance(sub, list) and sub:
                    _neg_fields(sub, _PT_TAGS)
        elif head == "fp_poly":
            pts = sexpr.find(node, "pts")
            if pts is not None:
                _mirror_pts(pts)
        elif head in _FP_PLAIN:
            continue
        else:
            raise MirrorUnsupported(
                f"{name}: footprint child {head!r} is not in the proven "
                f"mirror set — pin its transform against a pcbnew flip "
                f"before allowing it")


_CACHE: dict[str, Path] = {}


def mirrored_mod(src: Path) -> Path:
    """The KiCad-exact mirrored twin of ``src`` as a real .kicad_mod under
    parts/_mirrored/ (content-addressed rewrite; deterministic; cached)."""
    key = str(src)
    got = _CACHE.get(key)
    if got is not None:
        return got
    doc = sexpr.loads(src.read_text())
    mirror_fp_doc(doc)
    lib = src.parent.name
    if lib.endswith(".pretty"):
        lib = lib[: -len(".pretty")]
    out = MIRROR_DIR / f"{lib}__{src.stem}.kicad_mod"
    text = sexpr.dumps(doc) + "\n"
    if not (out.exists() and out.read_text() == text):
        MIRROR_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f"{out.name}.tmp{os.getpid()}")
        tmp.write_text(text)
        os.replace(tmp, out)
    _CACHE[key] = out
    return out


def is_mirrored_path(p: Path) -> bool:
    return p.parent.name == MIRROR_DIR.name
