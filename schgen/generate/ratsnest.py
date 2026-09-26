from __future__ import annotations

import argparse
from pathlib import Path

from schgen.core import native as _nat
from schgen.core.project import PROJECT_ROOT
from schgen.generate import pcb as pcb_mod
from schgen.generate.pcb import PcbModel, net_pad_positions
from schgen.generate.pcb._native_emit import prepare

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER = PROJECT_ROOT
PNG_TOP = CARRIER / "renders" / "ratsnest_top.png"
PNG_BOTTOM = CARRIER / "renders" / "ratsnest_bottom.png"
SVG_COMBINED = CARRIER / "docs" / "RATSNEST.svg"
PNG_SHEET_DIR = CARRIER / "renders" / "ratsnest"
SCALE = 4.0
PAD = 28.0


def _palette(sheets):
    return {key: tuple(value) for key, value in _nat.module().ratsnest_palette(sheets).items()}


def _hex(rgb):
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
    if not _nat.loaded():
        raise RuntimeError("native mst_manhattan required")
    got = [(int(a), int(b))
           for a, b in _nat.module().mst_manhattan(
               [(p[0], p[1]) for p in pts])]
    if _nat.trace():
        ref = _mst_edges_py(pts)
        if got != ref:
            raise AssertionError(
                f"native mst_manhattan DIVERGENCE: cpp={got} python={ref}")
    return got


def net_mst_edges(model: PcbModel,
                  npp: dict | None = None) -> dict[str, list[tuple[int, int]]]:
    if npp is None:
        npp = net_pad_positions(model)
    got = _nat.module().ratsnest_mst(npp)
    if _nat.trace():
        ref = {net: _mst_edges_py(pts) for net, pts in sorted(npp.items())}
        if got != ref:
            raise AssertionError("native ratsnest_mst DIVERGENCE")
    return got


def _airwires(model, side, npp, mst):
    return _nat.module().ratsnest_airwires(prepare(model), side, npp, mst)


def cross_airwire_length(model, npp=None, mst=None):
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    return _nat.module().ratsnest_lengths(npp, mst)


def _svg(model, palette, npp, mst):
    return _nat.module().ratsnest_svg(prepare(model), palette, npp, mst)


def _png(model, palette, side, out, npp, mst):
    data = _nat.module().ratsnest_board_png(prepare(model), palette, side, npp, mst)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)


def _png_sheet(model, sheet, refs, out, npp, mst, *, som_refs=None):
    data = _nat.module().ratsnest_sheet_png(
        prepare(model), sheet, refs, npp, mst, som_refs or set())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)


def per_subsystem_pngs(model, npp=None, mst=None):
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    images = _nat.module().ratsnest_sheet_pngs(prepare(model), npp, mst)
    PNG_SHEET_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in images:
        path = PNG_SHEET_DIR / Path(name).name
        path.write_bytes(data)
        paths.append(path)
    for stale in PNG_SHEET_DIR.glob("*.png"):
        if stale not in paths:
            stale.unlink()
    return paths


def generate(model=None, npp=None, mst=None):
    if model is None:
        model = pcb_mod.build_model()
    result = _nat.module().ratsnest_run(prepare(model), str(CARRIER), npp, mst)
    for key in ("png_top", "png_bottom", "svg"):
        result[key] = Path(result[key])
    return result


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
    parser = argparse.ArgumentParser(prog="schgen ratsnest")
    sys.exit(cmd_ratsnest(parser.parse_args()))
