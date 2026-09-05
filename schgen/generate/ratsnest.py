from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from schgen.core import native as _nat
from schgen.core.project import PROJECT_ROOT
from schgen.generate import pcb as pcb_mod
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    PcbModel,
    _inst_courtyard,
    net_pad_positions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER = PROJECT_ROOT

PNG_TOP = CARRIER / "renders" / "ratsnest_top.png"
PNG_BOTTOM = CARRIER / "renders" / "ratsnest_bottom.png"
SVG_COMBINED = CARRIER / "docs" / "RATSNEST.svg"

SCALE = 4.0
PAD = 28.0


def _palette(sheets: list[str]) -> dict[str, tuple[int, int, int]]:
    real = sorted(s for s in sheets if not s.startswith("som_j"))
    out: dict[str, tuple[int, int, int]] = {}
    n = max(1, len(real))
    for i, name in enumerate(real):
        h = (i / n) % 1.0
        s = 0.55 if i % 2 == 0 else 0.78
        v = 0.92 if i % 3 else 0.74
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        out[name] = (int(r * 255), int(g * 255), int(b * 255))
    for s in sheets:
        if s.startswith("som_j"):
            out[s] = (201, 148, 32)
    return out


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mst_edges_py(pts: list[tuple[float, float, str, str]]
                  ) -> list[tuple[int, int]]:
    n = len(pts)
    if n < 2:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    best = [(abs(pts[i][0] - pts[0][0]) + abs(pts[i][1] - pts[0][1]), 0)
            for i in range(n)]
    edges: list[tuple[int, int]] = []
    for _ in range(n - 1):
        u = -1
        ud = None
        for i in range(n):
            if in_tree[i]:
                continue
            if ud is None or best[i][0] < ud:
                ud, u = best[i][0], i
        if u < 0:
            break
        in_tree[u] = True
        edges.append((best[u][1], u))
        for i in range(n):
            if in_tree[i]:
                continue
            d = abs(pts[i][0] - pts[u][0]) + abs(pts[i][1] - pts[u][1])
            if d < best[i][0]:
                best[i] = (d, u)
    return edges


def _mst_edges(pts: list[tuple[float, float, str, str]]
               ) -> list[tuple[int, int]]:
    if _nat.loaded():
        got = [(int(a), int(b))
               for a, b in _nat.module().mst_manhattan(
                   [(p[0], p[1]) for p in pts])]
        if _nat.trace():
            ref = _mst_edges_py(pts)
            if got != ref:
                raise AssertionError(
                    f"native mst_manhattan DIVERGENCE: cpp={got} python={ref}")
        return got
    return _mst_edges_py(pts)


def net_mst_edges(model: PcbModel,
                  npp: dict | None = None) -> dict[str, list[tuple[int, int]]]:
    if npp is None:
        npp = net_pad_positions(model)
    return {net: _mst_edges(pts) for net, pts in sorted(npp.items())}


def _airwires(model: PcbModel, side: str | None, npp: dict, mst: dict):
    side_of_ref = {inst.ref: inst.side for inst in model.insts}
    out = []
    for _net, pts in sorted(npp.items()):
        for a, b in mst[_net]:
            xa, ya, ra, sa = pts[a]
            xb, yb, rb, sb = pts[b]
            if side is not None and not (side_of_ref.get(ra) == side
                                         or side_of_ref.get(rb) == side):
                continue
            out.append((xa, ya, xb, yb, sa != sb))
    return out


def cross_airwire_length(model: PcbModel, npp: dict | None = None,
                         mst: dict | None = None) -> tuple[float, float, int]:
    side_of_ref = {inst.ref: inst.side for inst in model.insts}  # noqa: F841
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    cross = total = 0.0
    n_cross = 0
    for _net, pts in sorted(npp.items()):
        for a, b in mst[_net]:
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            d = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
            total += d
            if sa != sb:
                cross += d
                n_cross += 1
    return round(cross, 1), round(total, 1), n_cross


def _svg(model: PcbModel, palette: dict, npp: dict, mst: dict) -> str:
    bw, bh = model.board_w, model.board_h
    W = int(bw * SCALE + 2 * PAD + 230)
    H = int(bh * SCALE + 2 * PAD + 40)

    def px(x):
        return round(PAD + (x - ORIGIN_X) * SCALE, 2)

    def py(y):
        return round(PAD + (y - ORIGIN_Y) * SCALE, 2)

    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" font-family="monospace" font-size="9">')
    e.append(f'<rect width="{W}" height="{H}" fill="#0f1115"/>')
    e.append(f'<rect x="{px(ORIGIN_X)}" y="{py(ORIGIN_Y)}" '
             f'width="{round(bw * SCALE, 2)}" height="{round(bh * SCALE, 2)}" '
             f'fill="#161922" stroke="#e5e7eb" stroke-width="1.5"/>')
    if model.som_keepout:
        kx0, ky0, kx1, ky1 = model.som_keepout
        e.append(f'<rect x="{px(kx0)}" y="{py(ky0)}" '
                 f'width="{round((kx1 - kx0) * SCALE, 2)}" '
                 f'height="{round((ky1 - ky0) * SCALE, 2)}" '
                 f'fill="none" stroke="#c99420" stroke-width="1" '
                 f'stroke-dasharray="4,3"/>')
    aw = _airwires(model, None, npp, mst)
    for x0, y0, x1, y1, cross in aw:
        if cross:
            e.append(f'<line x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" '
                     f'y2="{py(y1)}" stroke="#ff3b30" stroke-width="0.9" '
                     f'opacity="0.85"/>')
    for x0, y0, x1, y1, cross in aw:
        if not cross:
            e.append(f'<line x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" '
                     f'y2="{py(y1)}" stroke="#5b6472" stroke-width="0.35" '
                     f'opacity="0.5"/>')
    for inst in sorted(model.insts, key=lambda i: (i.side != "bottom", i.ref)):
        x0, y0, x1, y1 = _inst_courtyard(inst)
        col = _hex(palette.get(inst.sheet, (140, 140, 140)))
        op = 0.45 if inst.side == "bottom" else 0.9
        e.append(f'<rect x="{px(x0)}" y="{py(y0)}" '
                 f'width="{round((x1 - x0) * SCALE, 2)}" '
                 f'height="{round((y1 - y0) * SCALE, 2)}" fill="{col}" '
                 f'opacity="{op}" stroke="#0f1115" stroke-width="0.3"/>')
    lx = PAD + bw * SCALE + 16
    ly = PAD + 4
    e.append(f'<text x="{lx}" y="{ly}" fill="#e5e7eb" font-size="11" '
             f'font-weight="bold">subsystems</text>')
    for i, name in enumerate(sorted(palette)):
        yy = ly + 16 + i * 12
        e.append(f'<rect x="{lx}" y="{yy - 8}" width="9" height="9" '
                 f'fill="{_hex(palette[name])}"/>')
        e.append(f'<text x="{lx + 14}" y="{yy}" fill="#cbd5e1">{name}</text>')
    e.append(f'<text x="{PAD}" y="{H - 10}" fill="#94a3b8">'
             f'board {bw:g} x {bh:g} mm — boxes=footprints (top solid / bottom '
             f'faint), red=cross-subsystem airwire, grey=intra, gold dash=SoM '
             f'keep-out. schgen ratsnest (deterministic).</text>')
    e.append("</svg>")
    return "\n".join(e) + "\n"


def _png(model: PcbModel, palette: dict, side: str, out: Path,
         npp: dict, mst: dict) -> None:
    from PIL import Image, ImageDraw
    bw, bh = model.board_w, model.board_h
    W = int(bw * SCALE + 2 * PAD)
    H = int(bh * SCALE + 2 * PAD)
    im = Image.new("RGB", (W, H), (15, 17, 21))
    d = ImageDraw.Draw(im, "RGBA")

    def px(x):
        return PAD + (x - ORIGIN_X) * SCALE

    def py(y):
        return PAD + (y - ORIGIN_Y) * SCALE

    d.rectangle([px(ORIGIN_X), py(ORIGIN_Y),
                 px(ORIGIN_X) + bw * SCALE, py(ORIGIN_Y) + bh * SCALE],
                fill=(22, 25, 34), outline=(229, 231, 235), width=2)
    if model.som_keepout:
        kx0, ky0, kx1, ky1 = model.som_keepout
        d.rectangle([px(kx0), py(ky0), px(kx1), py(ky1)],
                    outline=(201, 148, 32), width=1)
    for x0, y0, x1, y1, cross in _airwires(model, side, npp, mst):
        if cross:
            d.line([px(x0), py(y0), px(x1), py(y1)],
                   fill=(255, 59, 48, 230), width=2)
        else:
            d.line([px(x0), py(y0), px(x1), py(y1)],
                   fill=(120, 132, 150, 130), width=1)
    for inst in sorted(model.insts, key=lambda i: i.ref):
        if inst.side != side and not (side == "top" and inst.ref.startswith("H")):
            if not (inst.mod_path.name.startswith("MountingHole")):
                continue
        if inst.side != side:
            continue
        x0, y0, x1, y1 = _inst_courtyard(inst)
        r, g, b = palette.get(inst.sheet, (140, 140, 140))
        d.rectangle([px(x0), py(y0), px(x1), py(y1)],
                    fill=(r, g, b, 235), outline=(15, 17, 21, 255), width=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG", optimize=True)


PNG_SHEET_DIR = CARRIER / "renders" / "ratsnest"
_SHEET_SC = 12.0
_SHEET_M = 10.0


def _png_sheet(model: PcbModel, sheet: str, refs: set[str], out: Path,
               npp: dict, mst: dict,
               som_refs: set[str] | None = None) -> None:
    from PIL import Image, ImageDraw
    insts = {i.ref: i for i in model.insts}
    som_refs = som_refs or set()
    boxes = [_inst_courtyard(insts[r]) for r in sorted(refs | som_refs)]
    if som_refs and model.som_keepout:
        boxes.append(model.som_keepout)
    x0 = min(b[0] for b in boxes) - _SHEET_M
    y0 = min(b[1] for b in boxes) - _SHEET_M
    x1 = max(b[2] for b in boxes) + _SHEET_M
    y1 = max(b[3] for b in boxes) + _SHEET_M
    im = Image.new("RGB", (int((x1 - x0) * _SHEET_SC),
                           int((y1 - y0) * _SHEET_SC)), (15, 17, 21))
    d = ImageDraw.Draw(im, "RGBA")

    def px(x):
        return (x - x0) * _SHEET_SC

    def py(y):
        return (y - y0) * _SHEET_SC

    if model.som_keepout:
        kx0, ky0, kx1, ky1 = model.som_keepout
        d.rectangle([px(kx0), py(ky0), px(kx1), py(ky1)],
                    outline=(201, 148, 32, 255), width=2)
    for i in sorted(model.insts, key=lambda i: i.ref):
        bx0, by0, bx1, by1 = _inst_courtyard(i)
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        own = i.ref in refs
        if own:
            fill = ((70, 160, 255, 235) if i.side == "top"
                    else (255, 170, 60, 235))
        elif i.ref in som_refs:
            fill = ((110, 150, 190, 235) if i.side == "top"
                    else (80, 105, 135, 235))
        else:
            fill = ((60, 66, 78, 200) if i.side == "top"
                    else (40, 44, 54, 200))
        d.rectangle([px(bx0), py(by0), px(bx1), py(by1)], fill=fill,
                    outline=(15, 17, 21, 255), width=1)
        if own and i.side == "bottom":
            d.rectangle([px(bx0), py(by0), px(bx1), py(by1)],
                        outline=(255, 230, 120, 255), width=2)
    for _net, pts in sorted(npp.items()):
        if not any(p[2] in refs for p in pts):
            continue
        for a, b in mst[_net]:
            xa, ya, ra, _sa = pts[a]
            xb, yb, rb, _sb = pts[b]
            own_edge = ra in refs and rb in refs
            to_som = ((ra in refs and rb in som_refs)
                      or (rb in refs and ra in som_refs))
            leaves = (ra in refs) != (rb in refs)
            ln = abs(xb - xa) + abs(yb - ya)
            col = ((120, 220, 160, 220) if own_edge
                   else (255, 59, 48, 235) if to_som
                   else (255, 110, 100, 130) if leaves
                   else (110, 118, 132, 70))
            d.line([px(xa), py(ya), px(xb), py(yb)], fill=col,
                   width=2 if (to_som or (own_edge and ln > 12)) else 1)
    for r in sorted(refs):
        bx0, by0, _bx1, _by1 = _inst_courtyard(insts[r])
        d.text((px(bx0), py(by0) - 11), r, fill=(240, 240, 245, 255))
    im.save(out, "PNG", optimize=True)


def per_subsystem_pngs(model: PcbModel, npp: dict | None = None,
                       mst: dict | None = None) -> list[Path]:
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    PNG_SHEET_DIR.mkdir(parents=True, exist_ok=True)
    for stale in PNG_SHEET_DIR.glob("*.png"):
        stale.unlink()
    by_sheet: dict[str, set[str]] = {}
    for i in model.insts:
        by_sheet.setdefault(i.sheet, set()).add(i.ref)
    som_refs = {r for sh, rr in by_sheet.items()
                if sh.startswith("som_") for r in rr}
    out: list[Path] = []
    for sheet, refs in sorted(by_sheet.items()):
        if sheet.startswith("som_"):
            continue
        p = PNG_SHEET_DIR / f"{sheet}.png"
        _png_sheet(model, sheet, refs, p, npp, mst, som_refs=som_refs)
        out.append(p)
    if som_refs:
        p = PNG_SHEET_DIR / "som.png"
        _png_sheet(model, "som", som_refs, p, npp, mst)
        out.append(p)
    return out


def generate(model: PcbModel | None = None, npp: dict | None = None,
             mst: dict | None = None) -> dict:
    if model is None:
        model = pcb_mod.build_model()
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    sheets = sorted({inst.sheet for inst in model.insts})
    palette = _palette(sheets)
    _png(model, palette, "top", PNG_TOP, npp, mst)
    _png(model, palette, "bottom", PNG_BOTTOM, npp, mst)
    per_subsystem_pngs(model, npp, mst)
    SVG_COMBINED.parent.mkdir(parents=True, exist_ok=True)
    SVG_COMBINED.write_text(_svg(model, palette, npp, mst))
    cross, total, n_cross = cross_airwire_length(model, npp, mst)
    return {
        "png_top": PNG_TOP, "png_bottom": PNG_BOTTOM, "svg": SVG_COMBINED,
        "cross_mm": cross, "total_mm": total, "n_cross": n_cross,
        "board_w": model.board_w, "board_h": model.board_h,
        "n_top": model.n_top, "n_bottom": model.n_bottom,
    }


def cmd_ratsnest(args: argparse.Namespace) -> int:
    res = generate()
    print(f"ratsnest: {res['png_top'].relative_to(REPO_ROOT)} + "
          f"{res['png_bottom'].relative_to(REPO_ROOT)} + "
          f"{res['svg'].relative_to(REPO_ROOT)}")
    print(f"  board {res['board_w']:g} x {res['board_h']:g} mm  "
          f"(top {res['n_top']} / bottom {res['n_bottom']})")
    ratio = (100 * res['cross_mm'] / res['total_mm']) if res['total_mm'] else 0
    print(f"  airwires: {res['total_mm']:g} mm total, {res['cross_mm']:g} mm "
          f"cross-subsystem ({res['n_cross']} edges, {ratio:.1f}% of length)")
    return 0


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser(prog="schgen ratsnest")
    sys.exit(cmd_ratsnest(p.parse_args()))
