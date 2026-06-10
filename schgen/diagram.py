"""Block diagram (SVG) generated from the linked port graph. No deps.

Sheets are boxes in a left column; the SoM contract (J1/J2/J3) is the
central node on the right; a dashed "later waves" node collects the
author-deferred ports. Edges: solid sheet->SoM for contract-bound ports
(label = net count + typed-pair summary), solid sheet->sheet for shared
ports, dashed sheet->later-waves for deferred ports.
"""

from __future__ import annotations

from pathlib import Path

FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"

BOX_W = 220
ROW_H = 18
PAD = 14
COL_SHEETS_X = 40
COL_SOM_X = 560
WIDTH = 860


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render(link_result, som_nets: dict[str, list[str]], out: Path) -> Path:
    sheets = [sc.name for sc in link_result.sheets]

    # per sheet: bound-to-SoM nets, deferred nets, sheet<->sheet nets
    som_bound: dict[str, list[str]] = {s: [] for s in sheets}
    deferred: dict[str, list[str]] = {s: [] for s in sheets}
    peer_edges: set[tuple[str, str, str]] = set()
    for b in link_result.bindings:
        if b.status == "deferred":
            deferred[b.sheet].append(b.net)
            continue
        for t in b.targets:
            if t.startswith("SoM "):
                som_bound[b.sheet].append(b.net)
            elif t.startswith("sheet "):
                peer = t.split()[1].split(":")[0]
                peer_edges.add((*sorted((b.sheet, peer)), b.net))
    rails = [r.split(" ", 1)[0] for r in link_result.rail_bindings
             if "SoM" in r]

    # ---- layout ---------------------------------------------------------------
    y = 40
    sheet_pos: dict[str, tuple[int, int, int]] = {}   # name -> x, y, h
    for s in sheets:
        n_ports = len(som_bound[s]) + len(deferred[s])
        h = 3 * ROW_H + PAD
        sheet_pos[s] = (COL_SHEETS_X, y, h)
        y += h + 28
    total_h = max(y + 140, 360)
    som_h = 120
    som_y = max(40, (y - 28 - som_h) // 2)
    later_y = som_y + som_h + 60

    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {WIDTH} {total_h}" '
             f'font-family="{FONT}" font-size="12">')
    e.append(f'<rect width="{WIDTH}" height="{total_h}" fill="white"/>')
    e.append(f'<text x="{COL_SHEETS_X}" y="24" font-size="15" '
             f'font-weight="bold">carrier board — linked port graph</text>')

    # ---- edges first (under the boxes) ----------------------------------------
    for s in sheets:
        sx, sy, sh = sheet_pos[s]
        x0, y0 = sx + BOX_W, sy + sh // 2
        # edge labels anchor just right of the source box (one row per edge)
        # so labels never collide mid-canvas where the curves converge.
        if som_bound[s]:
            x1, y1 = COL_SOM_X, som_y + som_h // 2
            e.append(f'<path d="M{x0},{y0} C{x0 + 80},{y0} {x1 - 80},{y1} '
                     f'{x1},{y1}" fill="none" stroke="#2563eb" '
                     f'stroke-width="2"/>')
            label = _edge_label(som_bound[s])
            e.append(f'<text x="{x0 + 10}" y="{y0 - 6}" '
                     f'fill="#2563eb">{_esc(label)}</text>')
        if deferred[s]:
            x1, y1 = COL_SOM_X, later_y + 40
            e.append(f'<path d="M{x0},{y0 + 8} C{x0 + 80},{y0 + 8} '
                     f'{x1 - 80},{y1} {x1},{y1}" fill="none" '
                     f'stroke="#9ca3af" stroke-width="1.5" '
                     f'stroke-dasharray="5,4"/>')
            label = _edge_label(deferred[s]) + " (deferred)"
            e.append(f'<text x="{x0 + 10}" y="{y0 + 24}" '
                     f'fill="#6b7280">{_esc(label)}</text>')
    for a, b_, net in sorted(peer_edges):
        ax, ay, ah = sheet_pos[a]
        bx, by, bh = sheet_pos[b_]
        e.append(f'<line x1="{ax + BOX_W // 2}" y1="{ay + ah}" '
                 f'x2="{bx + BOX_W // 2}" y2="{by}" stroke="#16a34a" '
                 f'stroke-width="2"/>')
        e.append(f'<text x="{ax + BOX_W // 2 + 6}" '
                 f'y="{(ay + ah + by) // 2}" fill="#16a34a">'
                 f'{_esc(net)}</text>')

    # ---- sheet boxes ------------------------------------------------------------
    for s in sheets:
        sx, sy, sh = sheet_pos[s]
        e.append(f'<rect x="{sx}" y="{sy}" width="{BOX_W}" height="{sh}" '
                 f'rx="8" fill="#eff6ff" stroke="#1e3a8a" '
                 f'stroke-width="1.5"/>')
        e.append(f'<text x="{sx + 12}" y="{sy + ROW_H + 2}" '
                 f'font-weight="bold" font-size="14">{_esc(s)}</text>')
        e.append(f'<text x="{sx + 12}" y="{sy + 2 * ROW_H + 4}" '
                 f'fill="#1e40af">{len(som_bound[s])} SoM-bound port(s)'
                 f'</text>')
        e.append(f'<text x="{sx + 12}" y="{sy + 3 * ROW_H + 2}" '
                 f'fill="#6b7280">{len(deferred[s])} deferred</text>')

    # ---- SoM node ----------------------------------------------------------------
    e.append(f'<rect x="{COL_SOM_X}" y="{som_y}" width="{BOX_W}" '
             f'height="{som_h}" rx="10" fill="#fef3c7" stroke="#92400e" '
             f'stroke-width="2"/>')
    e.append(f'<text x="{COL_SOM_X + 12}" y="{som_y + 24}" '
             f'font-weight="bold" font-size="14">Zynq SoM (J1/J2/J3)</text>')
    e.append(f'<text x="{COL_SOM_X + 12}" y="{som_y + 46}">'
             f'{len(som_nets)} contract nets</text>')
    e.append(f'<text x="{COL_SOM_X + 12}" y="{som_y + 66}" fill="#92400e">'
             f'{len(link_result.unbound_som)} unbound (later waves)</text>')
    if rails:
        e.append(f'<text x="{COL_SOM_X + 12}" y="{som_y + 86}" '
                 f'fill="#374151">rails: {_esc(", ".join(sorted(set(rails))))}'
                 f'</text>')

    # ---- later-waves node ----------------------------------------------------------
    e.append(f'<rect x="{COL_SOM_X}" y="{later_y}" width="{BOX_W}" '
             f'height="80" rx="10" fill="none" stroke="#9ca3af" '
             f'stroke-width="1.5" stroke-dasharray="6,4"/>')
    e.append(f'<text x="{COL_SOM_X + 12}" y="{later_y + 24}" fill="#6b7280" '
             f'font-weight="bold">later waves</text>')
    n_def = sum(len(v) for v in deferred.values())
    e.append(f'<text x="{COL_SOM_X + 12}" y="{later_y + 46}" fill="#6b7280">'
             f'{n_def} deferred port(s)</text>')
    e.append(f'<text x="{COL_SOM_X + 12}" y="{later_y + 64}" fill="#6b7280">'
             f'rj45, usb conn, J1-J3 sheets</text>')

    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


def _edge_label(nets: list[str]) -> str:
    pairs = sum(1 for n in nets if n.upper().endswith(("_P", "DP")))
    if pairs and pairs * 2 == len(nets):
        return f"{len(nets)} nets ({pairs} pairs)"
    return f"{len(nets)} nets"
