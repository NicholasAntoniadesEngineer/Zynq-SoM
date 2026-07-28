"""Silk-text geometry, connector/header/switch FUNCTION labels, the refdes
declutter pass and the under-SoM bottom-ref hider (LAW 1 — zero text-over-text).
PURE MOVE out of the old monolithic ``schgen/generate/pcb.py`` — no behaviour
change.
"""

from __future__ import annotations

import math

from schgen.core.sexpr import Sym

from .constants import (
    _CONN_DESC,
    _INT_DESC,
    _SW_DESC,
    CONN_MATING_FACE,
    ORIGIN_X,
    ORIGIN_Y,
)
from .mating_face import _inst_courtyard

# ABSOLUTE silk refdes height floor (mm). judgment:0.8 — fab legibility floor
# (common 1oz silk capability, JLC-class): text below ~0.8 mm does not print
# legibly, so a designator nobody can read is WORSE than the overlap it dodged.
# The declutter's font-shrink ladder must NEVER emit text below this; when no
# clear spot exists at >= this size, the RELOCATION SEARCH widens (more rings /
# more angles in _place_clear_label) instead of shrinking further. This floor is
# a deliberate BOARD-WIDE DFM upgrade: it also retro-fixes the pre-existing
# 0.62-tier outputs (refs the old ladder shrank to 0.62 mm now stop at 0.8).
_REFDES_MIN_SIZE = 0.8


def _rects_overlap(a, b) -> bool:
    """Axis-aligned rectangle intersection (each rect = x0,y0,x1,y1)."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _text_box(txt: str, x: float, y: float, size: float, m: float = 0.15):
    """Bounding box of a centre-justified silk string, sized to match KiCad's
    actual rendered stroke extent (so the placer/gate agree with KiCad's
    silk_overlap DRC, min_silk_clearance=0).

    KiCad's Newstroke font advances ≈1.0×size per glyph (caps/digits — a refdes
    is all caps/digits), and the rendered box is grown by the stroke THICKNESS on
    every side (half-thickness each end). An older 0.72 aspect under-measured the
    width by ~28%, so refdes pairs ~5 mm apart read as 0.06 mm clear in the gate
    while KiCad's true strokes touched (the U18001/U18002 class of 20). ``m`` is a
    tiny extra clearance on top of KiCad's geometry."""
    thick = max(0.12, size * 0.15)
    w = max(len(txt), 1) * size * 1.0 + thick
    h = size + thick
    return (x - w / 2 - m, y - h / 2 - m, x + w / 2 + m, y + h / 2 + m)


def _sub(node, name):
    """First child s-expr of ``node`` whose head symbol is ``name`` (else None)."""
    for c in node:
        if isinstance(c, list) and c and isinstance(c[0], Sym) and str(c[0]) == name:
            return c
    return None


def _font_size(node, default: float = 1.0) -> float:
    eff = _sub(node, "effects")
    fnt = _sub(eff, "font") if eff is not None else None
    szn = _sub(fnt, "size") if fnt is not None else None
    return float(szn[1]) if szn is not None else default


def _silk_gfx_box(c, fx, fy, ca, sa):
    """Board-space axis-aligned bbox of ONE footprint silk GRAPHIC primitive
    (fp_line / fp_rect / fp_circle / fp_arc / fp_poly), transformed local->board
    by the footprint orientation (ca/sa = cos/sin frot, origin fx/fy). The
    rendered silk is grown by half the stroke width on every side so the box
    matches what KiCad's silk_overlap DRC reasons about. Returns None for a
    primitive with no usable geometry."""
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
    if not pts:
        return None
    # KiCad composes a footprint child to the board with a CLOCKWISE rotation in
    # screen coords (y-down): bx=fx+lx·ca+ly·sa, by=fy-lx·sa+ly·ca. Verified vs the
    # DRC-reported render position of a rot-90 part (U11001 ref local (0,-7.11) ->
    # x=71.49, not the CCW 85.71). Only matters for a rotated footprint with a
    # non-zero local offset; the prior CCW sign mis-placed those boxes.
    bxs = [fx + lx * ca + ly * sa for lx, ly in pts]
    bys = [fy - lx * sa + ly * ca for lx, ly in pts]
    stroke = _sub(c, "stroke")
    wn = _sub(stroke, "width") if stroke is not None else None
    hw = (float(wn[1]) / 2.0) if (wn is not None and len(wn) >= 2) else 0.06
    return (min(bxs) - hw, min(bys) - hw, max(bxs) + hw, max(bys) + hw)


def _emitted_text_boxes(doc: list, include_silk_gfx: bool = False) -> list:
    """Bounding boxes of every VISIBLE silk designator already in the board — the
    footprint reference/value fp_text (transformed local->board by the footprint
    orientation) plus any top-level gr_text — so interior descriptor labels can be
    placed to clear them (LAW 1: zero text-over-text).

    When ``include_silk_gfx`` is set, also returns the board-space bbox of every
    footprint F.SilkS GRAPHIC primitive (fp_line/fp_rect/fp_circle/fp_arc/fp_poly
    — the component body/pin-1/courtyard outlines). The descriptor/refdes placer
    needs these so a function label ('BOOT: DFU BSEL', 'ESC PWR OUT') or a moved
    refdes does not land on top of a part's silk outline (the GFX-vs-TEXT class of
    silk_overlap DRC warnings that text-only boxes missed)."""
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
                    # modern KiCad stores the designator/value as a
                    # (property "Reference"/"Value" ...) node, NOT fp_text — the
                    # emitted board has 564 of these and 0 fp_text, so scanning
                    # only fp_text left the descriptor placer blind to every
                    # visible refdes and it could overprint them (LAW 1). Count
                    # only printed silk (F.SilkS); value on F.Fab is not printed.
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
                # CW screen-space compose (see _silk_gfx_box) so a rotated part's
                # property text box lands where KiCad renders it.
                boxes.append(_text_box(txt, fx + lx * ca + ly * sa,
                                       fy - lx * sa + ly * ca, _font_size(c)))
    return boxes


def _overlap_area(a, b) -> float:
    """Intersection area of two rects (0 if disjoint)."""
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if (dx > 0.0 and dy > 0.0) else 0.0


def _place_clear_label(cx0, cy0, cx1, cy1, label, size, occupied, bounds=None):
    """Nearest spot just OUTSIDE the courtyard (8 directions, growing offset)
    whose label box clears every occupied box. Returns the first fully-clear
    candidate; in a too-dense corner where none is clear, the LEAST-overlapping
    one (never a blind drop). Returns (tx, ty, box, offset) where offset is the
    clearance distance from the courtyard edge the spot was found at (a far offset
    means the label detached from its switch — the caller can then degrade it).

    When ``bounds`` (ex0, ey0, ex1, ey1) is given, candidates whose box stays
    fully ON the board are STRICTLY preferred: silk must not spill past an edge
    (LAW 1). This matters for an edge-flushed connector whose courtyard hugs the
    edge — the outward direction is empty (pen 0) but off-board, so it would
    otherwise win. An off-board spot is only ever returned if NO on-board
    candidate exists at all (cannot happen for a real part).

    WIDENED FALLBACK (DFM rework): when the compact 8-direction scan finds NO
    fully-clear on-board spot, the search WIDENS — 16 angles per ring and larger
    ring offsets — before giving up. The caller must never respond to a crowded
    neighbourhood by shrinking text below the fab-legibility floor
    (_REFDES_MIN_SIZE); finding a clear spot farther out is the correct move. The
    widened pass runs ONLY after the compact scan failed, so every label the
    compact scan already places keeps its exact position (deterministic,
    byte-stable for the non-crowded board)."""
    midx, midy = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
    # match _text_box's CORRECTED extent (Newstroke advances ~1.0*size/glyph + the
    # stroke thickness on each side). The old 0.72 aspect here under-measured the
    # candidate-box width ~28%, so the relocation search seated a ref where its OWN
    # collision test (_text_box, wider) — and the refdes gate — then saw an overlap:
    # exactly the U5004/U5007 stack a placement reshuffle exposed. Keep the search
    # box == the checked box so a "clear" spot is really clear (LAW 4: match KiCad).
    thick = max(0.12, size * 0.15)
    w = max(len(label), 1) * size * 1.0 + thick
    h = size + thick
    g = 0.9
    best = None            # best ON-BOARD candidate (lowest courtyard overlap)
    best_pen = None
    best_any = None        # absolute fallback if nothing is on-board
    best_any_pen = None
    for extra in (0.0, 2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0):
        dy = g + extra + h / 2
        dx = g + extra + w / 2
        for tx, ty in ((midx, cy1 + dy),          # S
                       (midx, cy0 - dy),          # N
                       (cx1 + dx, midy),          # E
                       (cx0 - dx, midy),          # W
                       (cx1 + dx, cy1 + dy),      # SE
                       (cx0 - dx, cy1 + dy),      # SW
                       (cx1 + dx, cy0 - dy),      # NE
                       (cx0 - dx, cy0 - dy)):     # NW
            box = _text_box(label, tx, ty, size)
            gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
            pen = sum(_overlap_area(gb, o) for o in occupied)
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

    # -- widened relocation search: 16 angles per ring, larger offsets ---------
    # Rings are centred on the courtyard: for angle a the candidate centre sits at
    # (mid + rx·cos a, mid + ry·sin a) where rx/ry extend the courtyard half-span
    # by the ring offset plus the label half-extent — so every candidate clears
    # the courtyard by ~``extra`` like the compact scan's cardinal spots. First
    # fully-clear ON-BOARD candidate wins (deterministic ring/angle order).
    for extra in (2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0, 28.0, 32.0):
        rx = (cx1 - cx0) / 2.0 + g + extra + w / 2
        ry = (cy1 - cy0) / 2.0 + g + extra + h / 2
        for k in range(16):
            a = math.tau * k / 16.0
            tx = midx + rx * math.cos(a)
            ty = midy + ry * math.sin(a)
            box = _text_box(label, tx, ty, size)
            onboard = bounds is None or (
                box[0] >= bounds[0] and box[1] >= bounds[1]
                and box[2] <= bounds[2] and box[3] <= bounds[3])
            if not onboard:
                continue
            gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
            pen = sum(_overlap_area(gb, o) for o in occupied)
            if pen == 0.0:
                return tx, ty, box, extra
            if best_pen is None or pen < best_pen:
                best_pen, best = pen, (tx, ty, box, extra)
    return best if best is not None else best_any


def _silk_text(txt: str, x: float, y: float, size: float, uuid) -> list:
    return [Sym("gr_text"), txt,
            [Sym("at"), round(x, 3), round(y, 3), 0],
            [Sym("layer"), "F.SilkS"],
            [Sym("uuid"), uuid],
            [Sym("effects"),
             [Sym("font"), [Sym("size"), size, size],
              [Sym("thickness"), round(max(0.12, size * 0.16), 3)]]]]


def _connector_descriptors(model, uid, doc: list) -> list:
    """A short F.SilkS function label beside every OFF-BOARD connector (PWR / USB
    OTG / JTAG / UART / HDMI TX-RX / ETH / microSD / QWIIC / CAM / LCD / PMODn),
    every interior developer header (_INT_DESC), and every SWITCH (_SW_DESC: DIP
    enables + tactile buttons), so the bare board tells you what each one is. The
    connector's own J/SW-ref is hidden (see _embed_footprint), freeing the spot.
    Off-board labels sit just INBOARD of the mating edge. Interior labels (headers
    + switches, in a dense region) are placed OVERLAP-AWARE: the nearest clear
    spot that touches no courtyard and no existing designator (LAW 1). All
    programmatic — never hand-placed."""
    out: list = []
    ex0, ey0 = ORIGIN_X, ORIGIN_Y
    ex1, ey1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    # everything already on the board that a label must not collide with
    occupied: list = [_inst_courtyard(i) for i in model.insts]
    occupied += _emitted_text_boxes(doc, include_silk_gfx=True)
    # number the PMOD ports PMOD0/1/2 in ref order (they span two sheets)
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
        # nearest board edge = the connector's mating edge
        d = {"N": cy0 - ey0, "S": ey1 - cy1, "W": cx0 - ex0, "E": ex1 - cx1}
        edge = min(d, key=d.get)
        if d[edge] > 12.0:                 # not actually an edge connector — skip
            continue
        midx, midy = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
        # Anchor the label just INBOARD of the mating edge, then step it further
        # inboard (away from the edge) if its box collides with a courtyard, an
        # existing designator, or a component SILK GRAPHIC — a fixed 1.8 mm offset
        # otherwise dropped 'ESC PWR OUT'/'PWR'/etc. straight onto the connector's
        # own silk outline (the GFX-vs-TEXT silk_overlap class). The label stays on
        # the SAME inboard axis (never flips to the off-board side, LAW 1).
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
            else:                          # E
                tx, ty = cx0 - g, midy
            tbox = _text_box(desc, tx, ty, dsize)
            if not any(_overlap_area(tbox, o) > 0.0 for o in occupied):
                clear = True
                break
        # If stepping straight inboard never clears (a neighbour part sits on the
        # inboard axis — e.g. QWIIC's label pinned against U2001's silk outline),
        # fall back to the general 8-direction nearest-clear placer around the
        # connector courtyard so the label finds the closest collision-free spot.
        if not clear:
            tx, ty, _box, _off = _place_clear_label(
                cx0, cy0, cx1, cy1, desc, dsize, occupied,
                bounds=(ex0, ey0, ex1, ey1))
        out.append(_silk_text(desc, tx, ty, dsize, uid(f"conn-desc:{inst.ref}")))
        occupied.append(_text_box(desc, tx, ty, dsize))
    # interior developer headers (_INT_DESC) + switches (_SW_DESC): overlap-aware.
    # Font shrinks with the label so the inline DIP position legends stay compact.
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
        # if a multi-position legend got flung > ~8 mm from its switch (a dense
        # corner like debug_boot), it has visually detached — degrade to the short
        # function label (text before ':'), which fits clear AND close.
        if off > 8.0 and ":" in label:
            short = label.split(":", 1)[0].strip()
            ssize = _sized(short)
            stx, sty, sbox, soff = _place_clear_label(cx0, cy0, cx1, cy1, short,
                                                      ssize, occupied,
                                                      bounds=(ex0, ey0, ex1, ey1))
            if soff < off:
                label, size, tx, ty, box = short, ssize, stx, sty, sbox
        occupied.append(box)
        out.append(_silk_text(label, tx, ty, size, uid(f"{pfx}:{inst.ref}")))
    return out


def _set_font_size(prop: list, size: float) -> None:
    """Rewrite a property's silk font size (+ a proportional thickness) in place —
    used to shrink a refdes the declutter pass would otherwise fling far, so it
    lands closer at a smaller but still-legible size."""
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


def _hide_undersom_bottom_refs(model, doc: list) -> int:
    """Hide the B.SilkS reference of every BOTTOM-side part under the SoM shadow.
    Those parts (the som_decoupling bypass bank + co-located passives) sit on a
    uniform ~2 mm grid with no room for a legible refdes at ANY font (a 6-char ref
    is wider than the pitch even at the 0.8 mm _REFDES_MIN_SIZE floor), so they get the
    test-point treatment: the ref stays in the footprint data (netlist/BOM), just
    not printed. Keyed on a B.Cu footprint whose origin is inside model.som_keepout.
    Runs BEFORE _declutter_refdes so the hidden refs are skipped there. Returns the
    count hidden."""
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


def _declutter_refdes(model, uid, doc: list) -> int:
    """Re-place the VISIBLE F.SilkS component reference designators that overprint
    each other or another silk object (LAW 1). KiCad stamps each ref at the
    footprint-author's local (at); in dense clusters (diode/IC strings) those
    positions collide. We move ONLY a ref that actually overlaps — a non-colliding
    ref keeps its exact authored position (byte-identical) — to the nearest clear
    spot just outside its OWN footprint courtyard, reusing _place_clear_label.

    BOTH sides (F.SilkS + B.SilkS) compose IDENTICALLY: child board position is
    fp + R_cw(frot)·(lx,ly) — KiCad applies NO position mirror to a B.Cu
    footprint's children (only the text GLYPHS render mirrored via `justify
    mirror`; unified no-bottom-mirror convention, pcbnew-verified). The ref's
    local (at) is rewritten by inverse-composing the chosen board point. Greedy
    in ref-name
    order; top refs are visited first (one shared `placed`) so F.SilkS stays
    byte-identical. Under-SoM bottom refs are hidden upstream
    (_hide_undersom_bottom_refs) — a ~2 mm cap grid has no room for a legible ref —
    so they never reach here. Mutates ``doc`` in place; MUST run after the
    footprint loop AND _connector_descriptors so the occupied set already holds
    every courtyard and function label. Returns the number of refs relocated."""
    import math
    ex0, ey0 = ORIGIN_X, ORIGIN_Y
    ex1, ey1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    # static obstacles every ref must clear: each footprint courtyard + each silk
    # FUNCTION label (the gr_text from _connector_descriptors). Refs clear each
    # other separately (greedily, below) so a moved ref is never an obstacle to a
    # ref that has not been visited yet.
    occupied = [_inst_courtyard(i) for i in model.insts]
    for node in doc:
        if (isinstance(node, list) and node and str(node[0]) == "gr_text"
                and isinstance(node[1], str)):
            at = _sub(node, "at")
            if at is not None:
                occupied.append(_text_box(node[1], float(at[1]), float(at[2]),
                                          _font_size(node)))
    # component SILK GRAPHICS (body/pin-1/outline strokes): a refdes must clear
    # these too, else a moved-or-authored ref lands on a part's silk outline (the
    # GFX-vs-refdes silk_overlap class KiCad flags but courtyard+text boxes miss).
    # Split per side so a bottom ref only sees bottom silk (see occupied_bot).
    silk_gfx_top: list = []
    silk_gfx_bot: list = []
    for node in doc:
        if not (isinstance(node, list) and node and str(node[0]) == "footprint"):
            continue
        fat = _sub(node, "at")
        if fat is None:
            continue
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
            gb = _silk_gfx_box(c, gfx, gfy, gca, gsa)
            if gb is not None:
                (silk_gfx_top if ln == "F.SilkS" else silk_gfx_bot).append(gb)
    occupied += silk_gfx_top
    # B.SilkS refs need only clear BOTTOM-side silk (top parts are not on the
    # bottom layer + the F.SilkS function labels are top) — a far less crowded
    # obstacle set, so dense bottom banks find room the top-side set would deny.
    occupied_bot = [_inst_courtyard(i) for i in model.insts if i.side == "bottom"]
    occupied_bot += silk_gfx_bot
    court_by_ref = {i.ref: _inst_courtyard(i) for i in model.insts}
    top_refs: list = []
    bot_refs: list = []
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
            if not (isinstance(c, list) and len(c) > 2 and str(c[0]) == "property"
                    and c[1] == "Reference"):
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
            # KiCad composes a footprint child with a CLOCKWISE rotation in
            # screen coords (y-down). The TOP-side compose was previously CCW
            # (fy + lx·sa) which placed a rotated ref ~14 mm off its true render
            # spot (U11001 rot-90: CCW x=85.71 vs KiCad x=71.49), so the declutter
            # never saw its real silk collision. ONE form, BOTH sides — a B.Cu
            # footprint's children compose with the SAME CW transform, no
            # position mirror (unified convention, pcbnew-verified).
            bx, by = fx + lx * ca + ly * sa, fy - lx * sa + ly * ca
            court = court_by_ref.get(ref, (bx - 1, by - 1, bx + 1, by + 1))
            (bot_refs if bottom else top_refs).append(
                (ref, c, lat, fx, fy, ca, sa, court, size,
                 _text_box(ref, bx, by, size), bottom))
    # TOP refs visited before ANY bottom ref, one greedy `placed` set: a top ref
    # never sees a bottom box, so the F.SilkS result stays byte-identical; bottom
    # refs then clear the top boxes too (cross-side overlap is harmless but kept
    # conservative). Under-SoM bottom refs were hidden upstream and are skipped.
    refs = (sorted(top_refs, key=lambda r: r[0])
            + sorted(bot_refs, key=lambda r: r[0]))
    placed_top: list = []
    placed_bot: list = []
    moved = 0
    for ref, c, lat, fx, fy, ca, sa, court, size, box, bottom in refs:
        occ = occupied_bot if bottom else occupied   # bottom clears only bottom silk
        plc = placed_bot if bottom else placed_top
        # 0.02 mm guard band: exact tangency passes an area test but float
        # noise re-reads it as an overlap in the gate (C6007|R6017 abutted at
        # y=79.808 and differed by 1e-14).
        gb = (box[0] - 0.02, box[1] - 0.02, box[2] + 0.02, box[3] + 0.02)
        if not (any(_overlap_area(gb, o) > 0.0 for o in occ)
                or any(_overlap_area(gb, p) > 0.0 for p in plc)):
            plc.append(box)                          # clear -> keep authored spot
            continue
        tx, ty, nbox, off = _place_clear_label(
            court[0], court[1], court[2], court[3], ref, size,
            occ + plc, bounds=(ex0, ey0, ex1, ey1))

        def _pen(bx, _occ=occ, _plc=plc) -> float:
            return (sum(_overlap_area(bx, o) for o in _occ)
                    + sum(_overlap_area(bx, p) for p in _plc))

        # Retry at smaller fonts when the chosen spot is either FAR (a dense grid
        # flung the ref out, ambiguous to read) OR still OVERLAPS (no fully-clear
        # spot existed at the authored size — a tight stage cluster whose 0603
        # refdes text collides even at the nearest slot). Each tier is CLAMPED to
        # the ABSOLUTE fab-legibility floor _REFDES_MIN_SIZE (judgment:0.8 — common
        # 1oz silk capability): the ladder may NEVER emit text below it — an
        # unreadable designator is worse than the overlap it dodged. When even the
        # floor size finds no clear spot, the answer is the WIDENED relocation
        # search inside _place_clear_label (more rings/angles), never smaller text.
        # (Deliberate board-wide DFM upgrade: the pre-existing 0.62 tier now clamps
        # to 0.8 too.) We accept a shrunk spot only if it is CLOSER and/or strictly
        # LESS overlapping (never worse — LAW 1).
        new_size = size
        cur_pen = _pen(nbox)
        if off > 8.0 or cur_pen > 0.0:
            tried = {round(size, 3)}
            for shrink in (0.78, 0.62):
                s2 = max(round(size * shrink, 3), _REFDES_MIN_SIZE)
                if s2 in tried or s2 >= size:
                    continue                     # floor-clamped duplicate tier
                tried.add(s2)
                tx2, ty2, nbox2, off2 = _place_clear_label(
                    court[0], court[1], court[2], court[3], ref, s2,
                    occ + plc, bounds=(ex0, ey0, ex1, ey1))
                pen2 = _pen(nbox2)
                # take the shrunk spot if it removes an overlap, or (overlap already
                # gone) if it is meaningfully closer.
                if (pen2 < cur_pen - 1e-9) or (
                        cur_pen <= 0.0 and off2 < off - 0.5):
                    tx, ty, nbox, off, new_size = tx2, ty2, nbox2, off2, s2
                    cur_pen = pen2
                    if cur_pen <= 0.0 and off <= 8.0:
                        break
        # rewrite the ref's footprint-local (at) so it composes back to (tx, ty);
        # ONE inverse, both sides (no side-dependent mirror — unified convention).
        dx, dy = tx - fx, ty - fy
        # inverse of the CW forward bx=fx+lx·ca+ly·sa, by=fy-lx·sa+ly·ca:
        #   lx = dx·ca - dy·sa,  ly = dx·sa + dy·ca   (both sides CW).
        lat[1] = round(dx * ca - dy * sa, 4)
        lat[2] = round(dx * sa + dy * ca, 4)
        if new_size != size:
            _set_font_size(c, new_size)
        plc.append(nbox)
        moved += 1
    return moved
