"""LAW-1 silk gate: VISIBLE reference designators must not overprint each other.

KiCad stamps each footprint's refdes at the author's local position; in dense
clusters those collide. ``_declutter_refdes`` (schgen/generate/pcb.py) relocates
the colliding top-side ones and test-point refs are hidden. This gate proves the
result on the ACTUAL emitted board — it parses the .kicad_pcb, composes every
visible ``property "Reference"`` to its board position, and counts padded-box
overlaps, so a future placement change cannot silently regress the zero-overlap
invariant.

F.SilkS (top) is the enforced surface — the side ``_declutter_refdes`` owns. The
B.SilkS (bottom, under-SoM cap grid) count is reported for visibility but not
hard-failed (tracked separately as OPEN-1b); flip ``enforce_bottom`` once the
bottom side is decluttered too.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path


def _tokenize(s: str):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', s)


def _build(toks, i):
    node = []
    i += 1                                    # consume '('
    while toks[i] != ')':
        if toks[i] == '(':
            sub, i = _build(toks, i)
            node.append(sub)
        else:
            t = toks[i]
            node.append(t[1:-1] if t.startswith('"') else t)
            i += 1
    return node, i + 1


def _sub(node, name):
    for c in node:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return None


def _text_box(txt, x, y, size, m=0.35):
    w = max(len(txt), 1) * size * 0.72
    h = size * 1.1
    return (x - w / 2 - m, y - h / 2 - m, x + w / 2 + m, y + h / 2 + m)


def _overlaps(a, b):
    return (min(a[2], b[2]) - max(a[0], b[0]) > 0.0
            and min(a[3], b[3]) - max(a[1], b[1]) > 0.0)


def _font_size(prop):
    eff = _sub(prop, "effects")
    fnt = _sub(eff, "font") if eff else None
    szn = _sub(fnt, "size") if fnt else None
    return float(szn[1]) if szn else 1.0


def _hidden(prop):
    hb = _sub(prop, "hide")
    return hb is not None and (len(hb) < 2 or str(hb[1]) == "yes")


@dataclass
class RefdesOverlapResult:
    ok: bool = True
    n_top: int = 0
    n_bottom: int = 0
    top_pairs: list = field(default_factory=list)
    bottom_pairs: int = 0


def _collect(pcb_path: Path, layer: str):
    toks = _tokenize(Path(pcb_path).read_text())
    root, _ = _build(toks, 0)
    refs = []
    for node in root:
        if not (isinstance(node, list) and node and node[0] == "footprint"):
            continue
        fat = _sub(node, "at")
        if fat is None:
            continue
        fx, fy = float(fat[1]), float(fat[2])
        frot = (float(fat[3]) if len(fat) > 3 and re.match(r'-?[\d.]+$', str(fat[3]))
                else 0.0)
        ca, sa = math.cos(math.radians(frot)), math.sin(math.radians(frot))
        # a B.Cu footprint is MIRRORED — its child board position is the mirror of
        # the top compose: fp + R(-frot)·(lx,ly), verified vs the KiCad renderer.
        # (On THIS board every B.SilkS ref has lx=0 so the two only differ in the
        # frot=90 y-term, but the mirror must be right for any lx!=0 part.)
        flay = _sub(node, "layer")
        bottom = flay is not None and flay[1] == "B.Cu"
        for c in node:
            if not (isinstance(c, list) and len(c) > 2 and c[0] == "property"
                    and c[1] == "Reference"):
                continue
            lay = _sub(c, "layer")
            if lay is None or lay[1] != layer or _hidden(c):
                continue
            lat = _sub(c, "at")
            if lat is None:
                continue
            lx, ly = float(lat[1]), float(lat[2])
            if bottom:
                bx, by = fx + lx * ca + ly * sa, fy - lx * sa + ly * ca
            else:
                bx, by = fx + lx * ca - ly * sa, fy + lx * sa + ly * ca
            refs.append((c[2], _text_box(c[2], bx, by, _font_size(c))))
    return refs


def _count_pairs(refs):
    pairs = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            if _overlaps(refs[i][1], refs[j][1]):
                pairs.append((refs[i][0], refs[j][0]))
    return pairs


def check(pcb_path, enforce_bottom: bool = False) -> RefdesOverlapResult:
    top = _collect(pcb_path, "F.SilkS")
    bot = _collect(pcb_path, "B.SilkS")
    top_pairs = _count_pairs(top)
    bottom_pairs = len(_count_pairs(bot))
    res = RefdesOverlapResult(
        n_top=len(top), n_bottom=len(bot),
        top_pairs=top_pairs, bottom_pairs=bottom_pairs)
    res.ok = (not top_pairs) and (not enforce_bottom or bottom_pairs == 0)
    return res
