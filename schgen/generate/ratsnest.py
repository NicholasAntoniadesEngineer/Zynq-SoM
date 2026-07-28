"""Ratsnest IMAGE renderer — SEE the placed board (LAW 5).

``schgen ratsnest`` (also run by ``schgen board``) draws the PLACED PCB so a
human can verify, by eye, that the layout is RIGHT before trusting DRC=0:

  - every footprint is a BOX at its placed (x, y), on its side, COLORED by its
    owning subsystem — so each subsystem should read as one tight contiguous
    block of one colour, never scattered confetti;
  - the unrouted AIRWIRES (a thin line between pads on the same net, drawn as a
    per-net minimum spanning tree) — INTRA-subsystem airwires are faint local
    bundles; CROSS-subsystem airwires are drawn bold + red so a board-spanning
    hairball is impossible to miss;
  - the Edge.Cuts OUTLINE + the SoM-body KEEP-OUT, so an off-board part (LAW-5
    forbidden) sticks out past the outline immediately.

Two PNGs (``carrier/renders/ratsnest_top.png`` + ``ratsnest_bottom.png``) and
one combined SVG (``carrier/docs/RATSNEST.svg``) are emitted every build. DRC=0
hid the old board-spanning hairball + off-board connectors; this image is the
LAW-5 visual oracle that no longer lets that pass silently.

DETERMINISM: colours are assigned by SORTED subsystem name, element order is
stable, there is no Date.now/random — two builds yield byte-identical images
(the PNG via a fixed-palette deterministic raster, the SVG as sorted text).
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

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

SCALE = 4.0              # image px per board mm
PAD = 28.0              # px margin around the board in the image


# ---- deterministic per-subsystem palette ----------------------------------------

def _palette(sheets: list[str]) -> dict[str, tuple[int, int, int]]:
    """A stable colour per subsystem: evenly-spaced hues in SORTED name order,
    so the same board always paints the same way. som_j* share one gold."""
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
            out[s] = (201, 148, 32)        # SoM mezzanine: gold
    return out


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ---- per-net airwire MST (the unrouted ratsnest) --------------------------------

def _mst_edges(pts: list[tuple[float, float, str, str]]
               ) -> list[tuple[int, int]]:
    """Prim's MST over the pad centers of ONE net (city-block distance). The
    edges ARE the airwires KiCad would show for that unrouted net — a tree, not
    every pad-pair, so the picture is the real ratsnest, not a clutter ball.
    Deterministic: ties break on index order."""
    n = len(pts)
    if n < 2:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    best = [(abs(pts[i][0] - pts[0][0]) + abs(pts[i][1] - pts[0][1]), 0)
            for i in range(n)]
    edges: list[tuple[int, int]] = []
    for _ in range(n - 1):
        # pick the nearest not-yet-in-tree vertex (stable on index)
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


def _airwires(model: PcbModel, side: str | None):
    """Yield (x0,y0,x1,y1, cross) airwire segments for the given side (or both
    if side is None). ``cross`` is True when the two pads belong to different
    subsystems. Both endpoints are filtered to the requested side so the per-
    side PNG shows only the airwires that touch that side's copper."""
    side_of_ref = {inst.ref: inst.side for inst in model.insts}
    out = []
    for _net, pts in sorted(net_pad_positions(model).items()):
        # de-duplicate identical pad centers within a net so the MST is stable
        for a, b in _mst_edges(pts):
            xa, ya, ra, sa = pts[a]
            xb, yb, rb, sb = pts[b]
            if side is not None and not (side_of_ref.get(ra) == side
                                         or side_of_ref.get(rb) == side):
                continue
            out.append((xa, ya, xb, yb, sa != sb))
    return out


def cross_airwire_length(model: PcbModel) -> tuple[float, float, int]:
    """(cross-subsystem airwire mm, total airwire mm, cross count) over the MST
    ratsnest — the LAW-5 budget metric. A small cross/total ratio means the
    subsystems cluster (few long inter-block wires)."""
    side_of_ref = {inst.ref: inst.side for inst in model.insts}  # noqa: F841
    cross = total = 0.0
    n_cross = 0
    for _net, pts in sorted(net_pad_positions(model).items()):
        for a, b in _mst_edges(pts):
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            d = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
            total += d
            if sa != sb:
                cross += d
                n_cross += 1
    return round(cross, 1), round(total, 1), n_cross


# ---- SVG ------------------------------------------------------------------------

def _svg(model: PcbModel, palette: dict) -> str:
    bw, bh = model.board_w, model.board_h
    W = int(bw * SCALE + 2 * PAD + 230)         # +legend column
    H = int(bh * SCALE + 2 * PAD + 40)

    def px(x):
        return round(PAD + (x - ORIGIN_X) * SCALE, 2)

    def py(y):
        return round(PAD + (y - ORIGIN_Y) * SCALE, 2)

    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" font-family="monospace" font-size="9">')
    e.append(f'<rect width="{W}" height="{H}" fill="#0f1115"/>')
    # edge cuts
    e.append(f'<rect x="{px(ORIGIN_X)}" y="{py(ORIGIN_Y)}" '
             f'width="{round(bw * SCALE, 2)}" height="{round(bh * SCALE, 2)}" '
             f'fill="#161922" stroke="#e5e7eb" stroke-width="1.5"/>')
    # SoM keepout
    if model.som_keepout:
        kx0, ky0, kx1, ky1 = model.som_keepout
        e.append(f'<rect x="{px(kx0)}" y="{py(ky0)}" '
                 f'width="{round((kx1 - kx0) * SCALE, 2)}" '
                 f'height="{round((ky1 - ky0) * SCALE, 2)}" '
                 f'fill="none" stroke="#c99420" stroke-width="1" '
                 f'stroke-dasharray="4,3"/>')
    # airwires (intra faint, cross bold red), bottom under top
    for x0, y0, x1, y1, cross in _airwires(model, None):
        if cross:
            e.append(f'<line x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" '
                     f'y2="{py(y1)}" stroke="#ff3b30" stroke-width="0.9" '
                     f'opacity="0.85"/>')
    for x0, y0, x1, y1, cross in _airwires(model, None):
        if not cross:
            e.append(f'<line x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" '
                     f'y2="{py(y1)}" stroke="#5b6472" stroke-width="0.35" '
                     f'opacity="0.5"/>')
    # footprints (bottom first so top reads above), colored by subsystem
    for inst in sorted(model.insts, key=lambda i: (i.side != "bottom", i.ref)):
        x0, y0, x1, y1 = _inst_courtyard(inst)
        col = _hex(palette.get(inst.sheet, (140, 140, 140)))
        op = 0.45 if inst.side == "bottom" else 0.9
        e.append(f'<rect x="{px(x0)}" y="{py(y0)}" '
                 f'width="{round((x1 - x0) * SCALE, 2)}" '
                 f'height="{round((y1 - y0) * SCALE, 2)}" fill="{col}" '
                 f'opacity="{op}" stroke="#0f1115" stroke-width="0.3"/>')
    # legend
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


# ---- PNG (PIL, deterministic) ---------------------------------------------------

def _png(model: PcbModel, palette: dict, side: str, out: Path) -> None:
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

    # edge cuts
    d.rectangle([px(ORIGIN_X), py(ORIGIN_Y),
                 px(ORIGIN_X) + bw * SCALE, py(ORIGIN_Y) + bh * SCALE],
                fill=(22, 25, 34), outline=(229, 231, 235), width=2)
    # SoM keepout
    if model.som_keepout:
        kx0, ky0, kx1, ky1 = model.som_keepout
        d.rectangle([px(kx0), py(ky0), px(kx1), py(ky1)],
                    outline=(201, 148, 32), width=1)
    # airwires for this side (intra faint, cross bold red)
    for x0, y0, x1, y1, cross in _airwires(model, side):
        if cross:
            d.line([px(x0), py(y0), px(x1), py(y1)],
                   fill=(255, 59, 48, 230), width=2)
        else:
            d.line([px(x0), py(y0), px(x1), py(y1)],
                   fill=(120, 132, 150, 130), width=1)
    # footprints on this side, colored by subsystem
    for inst in sorted(model.insts, key=lambda i: i.ref):
        if inst.side != side and not (side == "top" and inst.ref.startswith("H")):
            # mounting holes (top, all-layer) draw on both sides for context
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


# ---- entry point -----------------------------------------------------------------

def generate(model: PcbModel | None = None) -> dict:
    """Emit the two per-side PNGs + the combined SVG from the placed board.
    Returns paths + the cross-subsystem airwire budget metric."""
    if model is None:
        model = pcb_mod.build_model()
    sheets = sorted({inst.sheet for inst in model.insts})
    palette = _palette(sheets)
    _png(model, palette, "top", PNG_TOP)
    _png(model, palette, "bottom", PNG_BOTTOM)
    SVG_COMBINED.parent.mkdir(parents=True, exist_ok=True)
    SVG_COMBINED.write_text(_svg(model, palette))
    cross, total, n_cross = cross_airwire_length(model)
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
