from __future__ import annotations

import copy
import math

from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.sexpr import Sym, _from_tagged

from .constants import (
    _CONN_DESC,
    _INT_DESC,
    _SW_DESC,
    CONN_MATING_FACE,
    ORIGIN_X,
    ORIGIN_Y,
)
from .mating_face import _inst_courtyard

_REFDES_MIN_SIZE = 0.8


def _rects_overlap_py(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _rects_overlap(a, b) -> bool:
    if _nat.loaded():
        got = _nat.module().boxes_overlap(a, b, 0.0)
        if _nat.trace():
            ref = _rects_overlap_py(a, b)
            if got is not ref:
                raise AssertionError(
                    "native boxes_overlap DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _rects_overlap_py(a, b)


def _text_box_py(txt: str, x: float, y: float, size: float, m: float = 0.15):
    thick = max(0.12, size * 0.15)
    w = max(len(txt), 1) * size * 1.0 + thick
    h = size + thick
    return (x - w / 2 - m, y - h / 2 - m, x + w / 2 + m, y + h / 2 + m)


def _text_box(txt: str, x: float, y: float, size: float, m: float = 0.15):
    if _nat.loaded():
        got = tuple(_nat.module().text_box(txt, x, y, size, m))
        if _nat.trace():
            ref = _text_box_py(txt, x, y, size, m)
            if got != ref:
                raise AssertionError(
                    f"native text_box DIVERGENCE: cpp={got} python={ref}")
        return got
    return _text_box_py(txt, x, y, size, m)


def _sub(node, name):
    for c in node:
        if isinstance(c, list) and c and isinstance(c[0], Sym) and str(c[0]) == name:
            return c
    return None


def _font_size(node, default: float = 1.0) -> float:
    eff = _sub(node, "effects")
    fnt = _sub(eff, "font") if eff is not None else None
    szn = _sub(fnt, "size") if fnt is not None else None
    return float(szn[1]) if szn is not None else default


def _silk_gfx_pts_py(c):
    tag = str(c[0])
    pts: list = []
    if tag == "fp_circle":
        ctr = _sub(c, "center")
        end = _sub(c, "end")
        if ctr is not None and end is not None and len(ctr) >= 3 and len(end) >= 3:
            cxf, cyf = float(ctr[1]), float(ctr[2])
            r = ((float(end[1]) - cxf) ** 2 + (float(end[2]) - cyf) ** 2) ** 0.5
            pts = [(cxf - r, cyf - r), (cxf + r, cyf + r)]
    else:
        for tagname in ("start", "mid", "end", "center"):
            p = _sub(c, tagname)
            if p is not None and len(p) >= 3:
                pts.append((float(p[1]), float(p[2])))
        ptsn = _sub(c, "pts")
        if ptsn is not None:
            for xy in ptsn:
                if isinstance(xy, list) and xy and str(xy[0]) == "xy" and len(xy) >= 3:
                    pts.append((float(xy[1]), float(xy[2])))
    stroke = _sub(c, "stroke")
    wn = _sub(stroke, "width") if stroke is not None else None
    hw = (float(wn[1]) / 2.0) if (wn is not None and len(wn) >= 2) else 0.06
    return pts, hw


def _silk_gfx_pts(c):
    if _nat.loaded():
        pts, hw = _nat.module().silk_gfx_pts(c)
        got = ([tuple(p) for p in pts], hw)
        if _nat.trace():
            ref = _silk_gfx_pts_py(c)
            if got != ref:
                raise AssertionError(
                    "native silk_gfx_pts DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _silk_gfx_pts_py(c)


def _silk_gfx_box_py(c, fx, fy, ca, sa):
    pts, hw = _silk_gfx_pts_py(c)
    if not pts:
        return None
    bxs = [fx + lx * ca + ly * sa for lx, ly in pts]
    bys = [fy - lx * sa + ly * ca for lx, ly in pts]
    return (min(bxs) - hw, min(bys) - hw, max(bxs) + hw, max(bys) + hw)


def _collect_refdes_props_py(doc: list) -> list:
    import math
    top: list = []
    bot: list = []
    for fi, node in enumerate(doc):
        if not (isinstance(node, list) and node and str(node[0]) == "footprint"):
            continue
        fat = _sub(node, "at")
        if fat is None:
            continue
        fx, fy = float(fat[1]), float(fat[2])
        frot = (
            float(fat[3])
            if (len(fat) > 3 and isinstance(fat[3], (int, float)))
            else 0.0
        )
        a = math.radians(frot)
        ca, sa = math.cos(a), math.sin(a)
        flay = _sub(node, "layer")
        bottom = flay is not None and str(flay[1]) == "B.Cu"
        want = "B.SilkS" if bottom else "F.SilkS"
        for pi, c in enumerate(node):
            if not (isinstance(c, list) and len(c) > 2
                    and str(c[0]) == "property" and c[1] == "Reference"):
                continue
            lay = _sub(c, "layer")
            if lay is None or str(lay[1]) != want:
                continue
            hb = _sub(c, "hide")
            if hb is not None and (len(hb) < 2 or str(hb[1]) == "yes"):
                continue
            lat = _sub(c, "at")
            if lat is None:
                continue
            (bot if bottom else top).append((fi, pi, c[2], bottom))
    return sorted(top, key=lambda r: r[2]) + sorted(bot, key=lambda r: r[2])


def _refdes_hits_to_rows(doc: list, hits, court_by_ref: dict) -> list:
    rows = []
    for (fi, pi, ref, fx, fy, ca, sa, lx, ly, size, bottom, *box) in hits:
        node = doc[int(fi)]
        c = node[int(pi)]
        lat = _sub(c, "at")
        bx = fx + lx * ca + ly * sa
        by = fy - lx * sa + ly * ca
        court = court_by_ref.get(ref, (bx - 1, by - 1, bx + 1, by + 1))
        rows.append((ref, c, lat, fx, fy, ca, sa, court, size,
                     tuple(box), bool(bottom)))
    return rows


def _collect_refdes_rows_py(doc: list, court_by_ref: dict) -> list:
    import math
    top: list = []
    bot: list = []
    for node in doc:
        if not (isinstance(node, list) and node and str(node[0]) == "footprint"):
            continue
        fat = _sub(node, "at")
        if fat is None:
            continue
        fx, fy = float(fat[1]), float(fat[2])
        frot = (
            float(fat[3])
            if (len(fat) > 3 and isinstance(fat[3], (int, float)))
            else 0.0
        )
        a = math.radians(frot)
        ca, sa = math.cos(a), math.sin(a)
        flay = _sub(node, "layer")
        bottom = flay is not None and str(flay[1]) == "B.Cu"
        want = "B.SilkS" if bottom else "F.SilkS"
        for c in node:
            if not (isinstance(c, list) and len(c) > 2
                    and str(c[0]) == "property" and c[1] == "Reference"):
                continue
            lay = _sub(c, "layer")
            if lay is None or str(lay[1]) != want:
                continue
            hb = _sub(c, "hide")
            if hb is not None and (len(hb) < 2 or str(hb[1]) == "yes"):
                continue
            lat = _sub(c, "at")
            if lat is None:
                continue
            ref, size = c[2], _font_size(c)
            lx, ly = float(lat[1]), float(lat[2])
            bx, by = fx + lx * ca + ly * sa, fy - lx * sa + ly * ca
            court = court_by_ref.get(ref, (bx - 1, by - 1, bx + 1, by + 1))
            (bot if bottom else top).append(
                (ref, c, lat, fx, fy, ca, sa, court, size,
                 _text_box(ref, bx, by, size), bottom))
    return (sorted(top, key=lambda r: r[0])
            + sorted(bot, key=lambda r: r[0]))


def _collect_gr_text_boxes_py(doc: list) -> list:
    boxes: list = []
    for node in doc:
        if (isinstance(node, list) and node and str(node[0]) == "gr_text"
                and isinstance(node[1], str)):
            at = _sub(node, "at")
            if at is not None:
                boxes.append(_text_box_py(node[1], float(at[1]), float(at[2]),
                                          _font_size(node)))
    return boxes


def _collect_fp_silk_gfx_py(node):
    import math
    top: list = []
    bot: list = []
    fat = _sub(node, "at")
    if fat is None:
        return top, bot
    gfx, gfy = float(fat[1]), float(fat[2])
    ga = math.radians(float(fat[3])) if (
        len(fat) > 3 and isinstance(fat[3], (int, float))) else 0.0
    gca, gsa = math.cos(ga), math.sin(ga)
    for c in node:
        if not (isinstance(c, list) and c and isinstance(c[0], Sym)):
            continue
        if str(c[0]) not in ("fp_line", "fp_rect", "fp_circle",
                             "fp_arc", "fp_poly"):
            continue
        lyr = _sub(c, "layer")
        if lyr is None:
            continue
        ln = str(lyr[1])
        if ln not in ("F.SilkS", "B.SilkS"):
            continue
        gb = _silk_gfx_box_py(c, gfx, gfy, gca, gsa)
        if gb is not None:
            (top if ln == "F.SilkS" else bot).append(gb)
    return top, bot


def _silk_gfx_box(c, fx, fy, ca, sa):
    if _nat.loaded():
        pts, hw = _silk_gfx_pts(c)
        got = _nat.module().silk_gfx_extent(pts, fx, fy, ca, sa, hw)
        if got is not None:
            got = tuple(got)
        if _nat.trace():
            ref = _silk_gfx_box_py(c, fx, fy, ca, sa)
            if got != ref:
                raise AssertionError(
                    "native silk_gfx_extent DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _silk_gfx_box_py(c, fx, fy, ca, sa)


def _emitted_text_boxes(doc: list, include_silk_gfx: bool = False) -> list:
    import math
    boxes: list = []
    for node in doc:
        if not (isinstance(node, list) and node and isinstance(node[0], Sym)):
            continue
        head = str(node[0])
        if head == "gr_text" and isinstance(node[1], str):
            at = _sub(node, "at")
            if at is not None:
                boxes.append(_text_box(node[1], float(at[1]), float(at[2]),
                                       _font_size(node)))
        elif head == "footprint":
            fat = _sub(node, "at")
            if fat is None:
                continue
            fx, fy = float(fat[1]), float(fat[2])
            a = math.radians(float(fat[3])) if len(fat) > 3 else 0.0
            ca, sa = math.cos(a), math.sin(a)
            if include_silk_gfx:
                for c in node:
                    if not (isinstance(c, list) and c and isinstance(c[0], Sym)):
                        continue
                    if str(c[0]) not in ("fp_line", "fp_rect", "fp_circle",
                                         "fp_arc", "fp_poly"):
                        continue
                    lyr = _sub(c, "layer")
                    if lyr is None or str(lyr[1]) != "F.SilkS":
                        continue
                    gb = _silk_gfx_box(c, fx, fy, ca, sa)
                    if gb is not None:
                        boxes.append(gb)
            for c in node:
                if not (isinstance(c, list) and c and isinstance(c[0], Sym)):
                    continue
                tag = str(c[0])
                if tag == "fp_text":
                    kind = str(c[1]) if isinstance(c[1], Sym) else ""
                    if kind not in ("reference", "value"):
                        continue
                    txt = c[2] if isinstance(c[2], str) else None
                elif tag == "property":
                    name = c[1] if isinstance(c[1], str) else ""
                    if name not in ("Reference", "Value"):
                        continue
                    lyr = _sub(c, "layer")
                    if lyr is None or str(lyr[1]) != "F.SilkS":
                        continue
                    txt = c[2] if isinstance(c[2], str) else None
                else:
                    continue
                hide = _sub(c, "hide")
                if hide is not None and (len(hide) < 2 or str(hide[1]) == "yes"):
                    continue
                lat = _sub(c, "at")
                if lat is None or txt is None:
                    continue
                lx, ly = float(lat[1]), float(lat[2])
                boxes.append(_text_box(txt, fx + lx * ca + ly * sa,
                                       fy - lx * sa + ly * ca, _font_size(c)))
    return boxes


def _overlap_area_py(a, b) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if (dx > 0.0 and dy > 0.0) else 0.0


def _overlap_area(a, b) -> float:
    if _nat.loaded():
        got = _nat.module().overlap_area(a, b)
        if _nat.trace():
            ref = _overlap_area_py(a, b)
            if got != ref:
                raise AssertionError(
                    f"native overlap_area DIVERGENCE: cpp={got} python={ref}")
        return got
    return _overlap_area_py(a, b)


class _BoxIndexPy:
    __slots__ = ("cell", "cells", "boxes")

    def __init__(self, boxes=(), cell: float = 8.0):
        self.cell = cell
        self.cells: dict[tuple[int, int], list[int]] = {}
        self.boxes: list = []
        for b in boxes:
            self.add(b)

    def add(self, b) -> None:
        i = len(self.boxes)
        self.boxes.append(b)
        c = self.cell
        for gx in range(int(b[0] // c), int(b[2] // c) + 1):
            for gy in range(int(b[1] // c), int(b[3] // c) + 1):
                self.cells.setdefault((gx, gy), []).append(i)

    def _near(self, b) -> list[int]:
        c = self.cell
        gx0, gy0 = int(b[0] // c), int(b[1] // c)
        gx1, gy1 = int(b[2] // c), int(b[3] // c)
        if gx0 == gx1 and gy0 == gy1:
            return self.cells.get((gx0, gy0), [])
        out: set[int] = set()
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                out.update(self.cells.get((gx, gy), ()))
        return sorted(out)

    def pen(self, gb) -> float:
        bx = self.boxes
        return sum(_overlap_area_py(gb, bx[i]) for i in self._near(gb))

    def hits(self, gb) -> bool:
        bx = self.boxes
        return any(_overlap_area_py(gb, bx[i]) > 0.0 for i in self._near(gb))


class _BoxIndex:
    __slots__ = ("_cpp", "_py", "_boxes")

    def __init__(self, boxes=(), cell: float = 8.0):
        self._cpp = None
        self._py = None
        self._boxes = list(boxes)
        if _nat.loaded():
            self._cpp = _nat.module().SilkBoxIndex(cell)
            for b in boxes:
                self._cpp.add(b)
            if _nat.trace():
                self._py = _BoxIndexPy(boxes, cell)
        else:
            self._py = _BoxIndexPy(boxes, cell)

    def add(self, b) -> None:
        self._boxes.append(b)
        if self._cpp is not None:
            self._cpp.add(b)
        if self._py is not None:
            self._py.add(b)

    def pen(self, gb) -> float:
        if self._cpp is not None:
            got = self._cpp.pen(gb)
            if self._py is not None and got != self._py.pen(gb):
                raise AssertionError(
                    f"native SilkBoxIndex.pen DIVERGENCE: "
                    f"cpp={got} python={self._py.pen(gb)}")
            return got
        return self._py.pen(gb)

    def hits(self, gb) -> bool:
        if self._cpp is not None:
            got = self._cpp.hits(gb)
            if self._py is not None and got is not self._py.hits(gb):
                raise AssertionError(
                    "native SilkBoxIndex.hits DIVERGENCE: "
                    f"cpp={got} python={self._py.hits(gb)}")
            return got
        return self._py.hits(gb)


class _PairIndex:
    __slots__ = ("a", "b")

    def __init__(self, a: _BoxIndex, b: _BoxIndex):
        self.a = a
        self.b = b

    def pen(self, gb) -> float:
        return self.a.pen(gb) + self.b.pen(gb)


def _place_clear_label_py(cx0, cy0, cx1, cy1, label, size, occupied,
                          bounds=None):
    if isinstance(occupied, list):
        occupied = _BoxIndexPy(occupied)
    midx, midy = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
    thick = max(0.12, size * 0.15)
    w = max(len(label), 1) * size * 1.0 + thick
    h = size + thick
    g = 0.9
    best = None
    best_pen = None
    best_any = None
    best_any_pen = None
    for extra in (0.0, 2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0):
        dy = g + extra + h / 2
        dx = g + extra + w / 2
        for tx, ty in ((midx, cy1 + dy),
                       (midx, cy0 - dy),
                       (cx1 + dx, midy),
                       (cx0 - dx, midy),
                       (cx1 + dx, cy1 + dy),
                       (cx0 - dx, cy1 + dy),
                       (cx1 + dx, cy0 - dy),
                       (cx0 - dx, cy0 - dy)):
            box = _text_box_py(label, tx, ty, size)
            gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
            pen = occupied.pen(gb)
            onboard = bounds is None or (
                box[0] >= bounds[0] and box[1] >= bounds[1]
                and box[2] <= bounds[2] and box[3] <= bounds[3])
            if onboard:
                if pen == 0.0:
                    return tx, ty, box, extra
                if best_pen is None or pen < best_pen:
                    best_pen, best = pen, (tx, ty, box, extra)
            if best_any_pen is None or pen < best_any_pen:
                best_any_pen, best_any = pen, (tx, ty, box, extra)

    for extra in (2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0, 28.0, 32.0):
        rx = (cx1 - cx0) / 2.0 + g + extra + w / 2
        ry = (cy1 - cy0) / 2.0 + g + extra + h / 2
        for k in range(16):
            a = math.tau * k / 16.0
            tx = midx + rx * math.cos(a)
            ty = midy + ry * math.sin(a)
            box = _text_box_py(label, tx, ty, size)
            onboard = bounds is None or (
                box[0] >= bounds[0] and box[1] >= bounds[1]
                and box[2] <= bounds[2] and box[3] <= bounds[3])
            if not onboard:
                continue
            gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
            pen = occupied.pen(gb)
            if pen == 0.0:
                return tx, ty, box, extra
            if best_pen is None or pen < best_pen:
                best_pen, best = pen, (tx, ty, box, extra)
    return best if best is not None else best_any


def _place_clear_label(cx0, cy0, cx1, cy1, label, size, occupied, bounds=None):
    if isinstance(occupied, list):
        occupied = _BoxIndex(occupied)
    if _nat.loaded():
        occ_cpp = None
        placed = None
        boxes_a = None
        boxes_b = None
        if isinstance(occupied, _PairIndex):
            if occupied.a._cpp is not None and occupied.b._cpp is not None:
                occ_cpp = occupied.a._cpp
                placed = occupied.b._cpp
                boxes_a = occupied.a._boxes
                boxes_b = occupied.b._boxes
        elif occupied._cpp is not None:
            occ_cpp = occupied._cpp
            boxes_a = occupied._boxes
        if occ_cpp is not None:
            got = _nat.module().place_clear_label(
                cx0, cy0, cx1, cy1, label, size, occ_cpp, placed, bounds)
            out = (got[0], got[1], (got[2], got[3], got[4], got[5]), got[6])
            if _nat.trace():
                if boxes_b is None:
                    py_occ = _BoxIndexPy(boxes_a)
                else:
                    py_occ = _PairIndex(_BoxIndexPy(boxes_a),
                                        _BoxIndexPy(boxes_b))
                ref = _place_clear_label_py(
                    cx0, cy0, cx1, cy1, label, size, py_occ, bounds)
                if out != ref:
                    raise AssertionError(
                        "native place_clear_label DIVERGENCE: "
                        f"cpp={out} python={ref}")
            return out
    if isinstance(occupied, _BoxIndex) and occupied._py is None:
        occupied = occupied._boxes
    return _place_clear_label_py(cx0, cy0, cx1, cy1, label, size,
                                 occupied, bounds)


def _silk_text(txt: str, x: float, y: float, size: float, uuid) -> list:
    return [Sym("gr_text"), txt,
            [Sym("at"), round(x, 3), round(y, 3), 0],
            [Sym("layer"), "F.SilkS"],
            [Sym("uuid"), uuid],
            [Sym("effects"),
             [Sym("font"), [Sym("size"), size, size],
              [Sym("thickness"), round(max(0.12, size * 0.16), 3)]]]]


def _connector_descriptors(model, uid, doc: list) -> list:
    out: list = []
    ex0, ey0 = ORIGIN_X, ORIGIN_Y
    ex1, ey1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    occupied = _BoxIndex([_inst_courtyard(i) for i in model.insts]
                         + _emitted_text_boxes(doc, include_silk_gfx=True))
    pmods = sorted(i.ref for i in model.insts if i.value == "DS1024-2x6R2")
    pmod_n = {ref: n for n, ref in enumerate(pmods)}
    for inst in model.insts:
        if inst.value not in CONN_MATING_FACE:
            continue
        desc = _CONN_DESC.get(inst.sheet)
        if desc is None:
            continue
        if inst.ref in pmod_n:
            desc = f"PMOD{pmod_n[inst.ref]}"
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        d = {"N": cy0 - ey0, "S": ey1 - cy1, "W": cx0 - ex0, "E": ex1 - cx1}
        edge = min(d, key=d.get)
        if d[edge] > 12.0:
            continue
        midx, midy = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
        dsize = 1.1
        tx, ty = midx, midy
        clear = False
        for g in (1.8, 3.2, 4.6, 6.0, 7.6, 9.4):
            if edge == "N":
                tx, ty = midx, cy1 + g
            elif edge == "S":
                tx, ty = midx, cy0 - g
            elif edge == "W":
                tx, ty = cx1 + g, midy
            else:
                tx, ty = cx0 - g, midy
            tbox = _text_box(desc, tx, ty, dsize)
            if not occupied.hits(tbox):
                clear = True
                break
        if not clear:
            tx, ty, _box, _off = _place_clear_label(
                cx0, cy0, cx1, cy1, desc, dsize, occupied,
                bounds=(ex0, ey0, ex1, ey1))
        out.append(_silk_text(desc, tx, ty, dsize, uid(f"conn-desc:{inst.ref}")))
        occupied.add(_text_box(desc, tx, ty, dsize))
    for inst in model.insts:
        label = _INT_DESC.get(inst.ref)
        pfx = "conn-desc"
        if label is None:
            label = _SW_DESC.get(inst.ref)
            pfx = "sw-desc"
        if label is None:
            continue
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)

        def _sized(lbl):
            n = len(lbl)
            return 1.1 if n <= 8 else 0.95 if n <= 16 else 0.85 if n <= 24 else 0.78

        size = _sized(label)
        tx, ty, box, off = _place_clear_label(cx0, cy0, cx1, cy1, label, size,
                                              occupied, bounds=(ex0, ey0, ex1, ey1))
        if off > 8.0 and ":" in label:
            short = label.split(":", 1)[0].strip()
            ssize = _sized(short)
            stx, sty, sbox, soff = _place_clear_label(cx0, cy0, cx1, cy1, short,
                                                      ssize, occupied,
                                                      bounds=(ex0, ey0, ex1, ey1))
            if soff < off:
                label, size, tx, ty, box = short, ssize, stx, sty, sbox
        occupied.add(box)
        out.append(_silk_text(label, tx, ty, size, uid(f"{pfx}:{inst.ref}")))
    return out


def _set_font_size_py(prop: list, size: float) -> None:
    eff = _sub(prop, "effects")
    fnt = _sub(eff, "font") if eff is not None else None
    if fnt is None:
        return
    szn = _sub(fnt, "size")
    if szn is not None and len(szn) >= 3:
        szn[1] = szn[2] = round(size, 3)
    thk = _sub(fnt, "thickness")
    if thk is not None and len(thk) >= 2:
        thk[1] = round(max(0.1, size * 0.15), 3)


def _set_font_size(prop: list, size: float) -> None:
    if _nat.loaded():
        got = _from_tagged(_nat.module().set_font_size(prop, size))
        if _nat.trace():
            ref = copy.deepcopy(prop)
            _set_font_size_py(ref, size)
            if sexpr.dumps(got) != sexpr.dumps(ref):
                raise AssertionError(
                    "native set_font_size DIVERGENCE: "
                    f"cpp={sexpr.dumps(got)} python={sexpr.dumps(ref)}")
        prop[:] = got
        return
    _set_font_size_py(prop, size)


def _hide_undersom_bottom_refs_py(model, doc: list) -> int:
    kp = model.som_keepout
    if kp is None:
        return 0
    x0, y0, x1, y1 = kp
    n = 0
    for node in doc:
        if not (isinstance(node, list) and node and str(node[0]) == "footprint"):
            continue
        flay = _sub(node, "layer")
        if flay is None or str(flay[1]) != "B.Cu":
            continue
        fat = _sub(node, "at")
        if fat is None:
            continue
        fx, fy = float(fat[1]), float(fat[2])
        if not (x0 <= fx <= x1 and y0 <= fy <= y1):
            continue
        for c in node:
            if (isinstance(c, list) and len(c) > 2 and str(c[0]) == "property"
                    and c[1] == "Reference"):
                hb = _sub(c, "hide")
                if hb is not None and len(hb) >= 2:
                    hb[1] = Sym("yes")
                else:
                    c.insert(3, [Sym("hide"), Sym("yes")])
                n += 1
                break
    return n


def _hide_undersom_bottom_refs(model, doc: list) -> int:
    kp = model.som_keepout
    if kp is None:
        return 0
    if _nat.loaded():
        tagged, n = _nat.module().hide_undersom_bottom_refs(doc, *kp)
        got = _from_tagged(tagged)
        if _nat.trace():
            ref = copy.deepcopy(doc)
            rn = _hide_undersom_bottom_refs_py(model, ref)
            if int(n) != rn or sexpr.dumps(got) != sexpr.dumps(ref):
                raise AssertionError(
                    "native hide_undersom_bottom_refs DIVERGENCE: "
                    f"cpp=({int(n)}, {sexpr.dumps(got)}) "
                    f"python=({rn}, {sexpr.dumps(ref)})")
        doc[:] = got
        return int(n)
    return _hide_undersom_bottom_refs_py(model, doc)


def _place_refdes_py(occ, plc, court, ref, size, box, fx, fy, ca, sa, bounds):
    gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
    if not (occ.hits(gb) or plc.hits(gb)):
        return False, 0.0, 0.0, size, box
    tx, ty, nbox, off = _place_clear_label(
        court[0], court[1], court[2], court[3], ref, size,
        _PairIndex(occ, plc), bounds=bounds)

    def _pen(bx, _occ=occ, _plc=plc) -> float:
        return _occ.pen(bx) + _plc.pen(bx)

    new_size = size
    cur_pen = _pen(nbox)
    if off > 8.0 or cur_pen > 0.0:
        tried = {round(size, 3)}
        for shrink in (0.78, 0.62):
            s2 = max(round(size * shrink, 3), _REFDES_MIN_SIZE)
            if s2 in tried or s2 >= size:
                continue
            tried.add(s2)
            tx2, ty2, nbox2, off2 = _place_clear_label(
                court[0], court[1], court[2], court[3], ref, s2,
                _PairIndex(occ, plc), bounds=bounds)
            pen2 = _pen(nbox2)
            if (pen2 < cur_pen - 1e-9) or (
                    cur_pen <= 0.0 and off2 < off - 0.5):
                tx, ty, nbox, off, new_size = tx2, ty2, nbox2, off2, s2
                cur_pen = pen2
                if cur_pen <= 0.0 and off <= 8.0:
                    break
    dx, dy = tx - fx, ty - fy
    return True, round(dx * ca - dy * sa, 4), round(dx * sa + dy * ca, 4), \
        new_size, nbox


# Must run after the footprint loop AND _connector_descriptors — it reads their
# courtyards and function labels as the occupied set.
def _declutter_refdes(model, uid, doc: list) -> int:
    import math
    ex0, ey0 = ORIGIN_X, ORIGIN_Y
    ex1, ey1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    occupied = [_inst_courtyard(i) for i in model.insts]
    if _nat.loaded():
        texts = [tuple(b) for b in _nat.module().collect_gr_text_boxes(doc, 1.0)]
        if _nat.trace():
            ref = _collect_gr_text_boxes_py(doc)
            if texts != ref:
                raise AssertionError(
                    "native collect_gr_text_boxes DIVERGENCE: "
                    f"cpp={texts} python={ref}")
        occupied.extend(texts)
    else:
        occupied.extend(_collect_gr_text_boxes_py(doc))
    silk_gfx_top: list = []
    silk_gfx_bot: list = []
    for node in doc:
        if not (isinstance(node, list) and node and str(node[0]) == "footprint"):
            continue
        if _nat.loaded():
            top, bot = _nat.module().collect_fp_silk_gfx(node)
            top = [tuple(b) for b in top]
            bot = [tuple(b) for b in bot]
            if _nat.trace():
                ref_top, ref_bot = _collect_fp_silk_gfx_py(node)
                if top != ref_top or bot != ref_bot:
                    raise AssertionError(
                        "native collect_fp_silk_gfx DIVERGENCE: "
                        f"cpp={(top, bot)} python={(ref_top, ref_bot)}")
            silk_gfx_top.extend(top)
            silk_gfx_bot.extend(bot)
            continue
        top, bot = _collect_fp_silk_gfx_py(node)
        silk_gfx_top.extend(top)
        silk_gfx_bot.extend(bot)
    occupied += silk_gfx_top
    occupied = _BoxIndex(occupied)
    occupied_bot = _BoxIndex(
        [_inst_courtyard(i) for i in model.insts if i.side == "bottom"]
        + silk_gfx_bot)
    court_by_ref = {i.ref: _inst_courtyard(i) for i in model.insts}
    if _nat.loaded():
        hits = _nat.module().collect_refdes_props(doc, 1.0)
        if _nat.trace():
            ref_hits = _collect_refdes_props_py(doc)
            got = [(int(h[0]), int(h[1]), h[2], bool(h[10])) for h in hits]
            if got != ref_hits:
                raise AssertionError(
                    "native collect_refdes_props DIVERGENCE: "
                    f"cpp={got} python={ref_hits}")
        refs = _refdes_hits_to_rows(doc, hits, court_by_ref)
    else:
        refs = _collect_refdes_rows_py(doc, court_by_ref)
    placed_top = _BoxIndex()
    placed_bot = _BoxIndex()
    moved = 0
    for ref, c, lat, fx, fy, ca, sa, court, size, box, bottom in refs:
        occ = occupied_bot if bottom else occupied
        plc = placed_bot if bottom else placed_top
        if (_nat.loaded() and occ._cpp is not None
                and plc._cpp is not None):
            got = _nat.module().place_refdes(
                court, ref, size, box, occ._cpp, plc._cpp,
                (ex0, ey0, ex1, ey1), fx, fy, ca, sa, _REFDES_MIN_SIZE,
                0.02, 8.0, 1e-9, 0.5, (0.78, 0.62))
            moved_hit, lx, ly, new_size, ax0, ay0, ax1, ay1 = got
            add_box = (ax0, ay0, ax1, ay1)
            if _nat.trace():
                ref_move, ref_lx, ref_ly, ref_size, ref_box = (
                    _place_refdes_py(
                        occ, plc, court, ref, size, box, fx, fy, ca, sa,
                        (ex0, ey0, ex1, ey1)))
                if (moved_hit, lx, ly, new_size, add_box) != (
                        ref_move, ref_lx, ref_ly, ref_size, ref_box):
                    raise AssertionError(
                        "native place_refdes DIVERGENCE: "
                        f"cpp={(moved_hit, lx, ly, new_size, add_box)} "
                        f"python={(ref_move, ref_lx, ref_ly, ref_size, ref_box)}")
            plc.add(add_box)
            if moved_hit:
                lat[1] = lx
                lat[2] = ly
                if new_size != size:
                    _set_font_size(c, new_size)
                moved += 1
            continue
        moved_hit, lx, ly, new_size, add_box = _place_refdes_py(
            occ, plc, court, ref, size, box, fx, fy, ca, sa,
            (ex0, ey0, ex1, ey1))
        plc.add(add_box)
        if moved_hit:
            lat[1] = lx
            lat[2] = ly
            if new_size != size:
                _set_font_size(c, new_size)
            moved += 1
    return moved
