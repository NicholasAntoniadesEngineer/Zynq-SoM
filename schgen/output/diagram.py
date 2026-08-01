from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

FONT = "Segoe UI, Helvetica, Arial, sans-serif"
LABEL_PX = 13

KIND_STYLE: dict[str, tuple[str, float, str]] = {
    "power":        ("#b45309", 2.6, "power rail"),
    "diff_pair":    ("#7c3aed", 2.0, "diff pair"),
    "tmds_pair":    ("#db2777", 2.0, "TMDS pair"),
    "usb_hs_pair":  ("#0891b2", 2.0, "USB HS pair"),
    "i2c":          ("#16a34a", 1.7, "I2C bus"),
    "sd_bus":       ("#ca8a04", 1.9, "SD bus"),
    "single":       ("#2563eb", 1.4, "signal"),
}
SOM_EDGE = ("#1d4ed8", 2.0)
DEFER_EDGE = ("#9ca3af", 1.4)

CLUSTERS: dict[str, tuple[str, str, str]] = {
    "power":   ("Power & bring-up",   "#fff7ed", "#fdba74"),
    "som":     ("SoM connectors",     "#fffbeb", "#fcd34d"),
    "video":   ("Video / display",    "#faf5ff", "#d8b4fe"),
    "storage": ("Storage & USB",      "#ecfeff", "#67e8f9"),
    "net":     ("Networking",         "#f0fdf4", "#86efac"),
    "io":      ("FMC / user IO",      "#eff6ff", "#93c5fd"),
}

SHEET_ROLE: dict[str, tuple[str, int]] = {
    "pd_input":           ("power", 0),
    "power":              ("power", 0),
    "power_mon":          ("power", 0),
    "bringup_rails":      ("power", 0),
    "bringup_en":         ("power", 0),
    "bringup_en_modules": ("power", 0),
    "bringup_modules":    ("power", 0),
    "som_j1":             ("som", 1),
    "som_j2":             ("som", 1),
    "som_j3":             ("som", 1),
    "hdmi_tx":            ("video", 2),
    "hdmi_rx":            ("video", 2),
    "lcd":               ("video", 2),
    "camera":            ("video", 2),
    "microsd":           ("storage", 2),
    "usbc_otg":          ("storage", 2),
    "usb_pd":            ("storage", 2),
    "uart_bridge":       ("storage", 2),
    "ethernet":          ("net", 2),
    "fmc":               ("io", 2),
    "pmod":              ("io", 2),
    "user_io":           ("io", 2),
    "debug_boot":        ("io", 2),
    "hdmi_rx_term":      ("video", 3),
    "rj45_connector":    ("net", 3),
    "usb_uart_connector": ("storage", 3),
}
DEFAULT_ROLE = ("io", 2)

BOX_W = 172
BOX_H = 56
COL_GAP = 128
ROW_GAP = 36
COL0_X = 150
TOP = 120
SOM_W = 168
CLUSTER_PAD = 15


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _net_word(n: int) -> str:
    return "net" if n == 1 else "nets"


def _dominant_kind(kinds: list[str]) -> str:
    c = Counter(kinds)
    ranked = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    for k, _ in ranked:
        if k != "single":
            return k
    return "single"


def _edge_label(items: list[tuple[str, str]]) -> tuple[str, str]:
    n = len(items)
    dom = _dominant_kind([k for _, k in items])
    grp = KIND_STYLE[dom][2]
    return f"{n} {_net_word(n)} · {grp}", dom


def render(link_result, som_nets: dict[str, list[str]], out: Path) -> Path:
    sheets = sorted(sc.name for sc in link_result.sheets)

    som_bound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    deferred: dict[str, list[str]] = defaultdict(list)
    peer: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for b in sorted(link_result.bindings, key=lambda b: (b.sheet, b.net)):
        kind = b.ptype.kind
        if b.status == "deferred":
            deferred[b.sheet].append(b.net)
            continue
        for t in b.targets:
            if t.startswith("SoM "):
                som_bound[b.sheet].append((b.net, kind))
            elif t.startswith("sheet "):
                pk = t.split()[1].split(":")[0]
                a, c = sorted((b.sheet, pk))
                peer[(a, c)].append((b.net, kind))
    for k in list(peer):
        peer[k] = sorted(set(peer[k]))

    rails = sorted({r.split(" ", 1)[0] for r in link_result.rail_bindings
                    if "SoM" in r})

    degree: dict[str, int] = defaultdict(int)
    for (a, c) in peer:
        degree[a] += 1
        degree[c] += 1
    for s in som_bound:
        degree[s] += 1
    for s in deferred:
        degree[s] += 1
    isolated = sorted(s for s in sheets if degree[s] == 0)
    iso_set = set(isolated)
    laid_sheets = [s for s in sheets if s not in iso_set]

    role = {s: SHEET_ROLE.get(s, DEFAULT_ROLE) for s in sheets}
    layer_of = {s: role[s][1] for s in sheets}
    cluster_of = {s: role[s][0] for s in sheets}

    SPINE = "\x00SoM"
    cl_order = list(CLUSTERS)

    MAX_PER_COL = 12

    def _split_run(run: list[str]) -> list[list[str]]:
        if len(run) <= MAX_PER_COL:
            return [run]
        import math
        parts = math.ceil(len(run) / MAX_PER_COL)
        size = math.ceil(len(run) / parts)
        return [run[i:i + size] for i in range(0, len(run), size)]

    def layer_columns(members: list[str]) -> list[list[str]]:
        by_cl: dict[str, list[str]] = defaultdict(list)
        for s in sorted(members):
            by_cl[cluster_of[s]].append(s)
        runs = [by_cl[cl] for cl in cl_order if cl in by_cl]
        cols: list[list[str]] = []
        cur: list[str] = []
        for run in runs:
            if len(run) > MAX_PER_COL:
                if cur:
                    cols.append(cur)
                    cur = []
                cols.extend(_split_run(run))
                continue
            if cur and len(cur) + len(run) > MAX_PER_COL:
                cols.append(cur)
                cur = []
            cur.extend(run)
        if cur:
            cols.append(cur)
        return cols or [[]]

    layers = sorted({layer_of[s] for s in laid_sheets})
    layer_members = {lv: [s for s in laid_sheets if layer_of[s] == lv]
                     for lv in layers}

    columns: dict[int, list[str]] = {}
    col_is_spine: dict[int, bool] = {}
    ci = 0
    for lv in layers:
        for col in layer_columns(layer_members[lv]):
            columns[ci] = col
            col_is_spine[ci] = False
            ci += 1
        if lv == 1:
            columns[ci] = []
            col_is_spine[ci] = True
            SPINE_COL = ci
            ci += 1
    if not any(col_is_spine.values()):
        SPINE_COL = 0
        columns = {k + 1: v for k, v in columns.items()}
        col_is_spine = {k + 1: v for k, v in col_is_spine.items()}
        columns[0] = []
        col_is_spine[0] = True

    col_of: dict[str, int] = {s: ci for ci, mem in columns.items() for s in mem}

    def physical_col(s: str) -> int:
        return col_of[s]

    adj: dict[str, list[str]] = defaultdict(list)
    for (a, c) in peer:
        adj[a].append(c)
        adj[c].append(a)
    for s in som_bound:
        adj[s].append(SPINE)
        adj[SPINE].append(s)

    pos_in_col: dict[str, int] = {}

    def reindex() -> None:
        for mem in columns.values():
            for i, s in enumerate(mem):
                pos_in_col[s] = i
        bp = [pos_in_col[s] for s in som_bound if s in pos_in_col]
        pos_in_col[SPINE] = sum(bp) / len(bp) if bp else 0
    reindex()

    def barycentre(s: str) -> float:
        ns = adj.get(s, [])
        vals = [pos_in_col.get(n, 0) for n in ns]
        return sum(vals) / len(vals) if vals else pos_in_col.get(s, 0)

    for _ in range(3):
        for cidx in sorted(columns):
            order = columns[cidx]
            if len(order) < 2:
                continue
            keyed = sorted(order, key=lambda s: (barycentre(s), s))
            members: dict[str, list[str]] = defaultdict(list)
            for s in keyed:
                members[cluster_of[s]].append(s)
            cl_bary = {cl: sum(keyed.index(m) for m in ms) / len(ms)
                       for cl, ms in members.items()}
            new: list[str] = []
            for cl in sorted(members,
                             key=lambda c: (cl_bary[c], cl_order.index(c))):
                new.extend(members[cl])
            columns[cidx] = new
            reindex()

    def col_runs(cidx: int) -> list[tuple[str, list[str]]]:
        runs: list[tuple[str, list[str]]] = []
        for s in columns[cidx]:
            if runs and runs[-1][0] == cluster_of[s]:
                runs[-1][1].append(s)
            else:
                runs.append((cluster_of[s], [s]))
        return runs

    box_xy: dict[str, tuple[float, float]] = {}
    cluster_rects: list[tuple[str, float, float, float, float]] = []
    col_x: dict[int, float] = {}
    col_height: dict[int, float] = {}

    x = COL0_X
    for cidx in sorted(columns):
        col_x[cidx] = x
        y = TOP + 18
        for cl, members in col_runs(cidx):
            top = y
            for s in members:
                box_xy[s] = (x, y)
                y += BOX_H + ROW_GAP
            bottom = y - ROW_GAP
            cluster_rects.append((cl, x - CLUSTER_PAD, top - 22,
                                  BOX_W + 2 * CLUSTER_PAD,
                                  (bottom - top) + 22 + CLUSTER_PAD))
            y += 26
        col_height[cidx] = y
        x += (SOM_W if col_is_spine[cidx] else BOX_W) + COL_GAP

    total_w = x - COL_GAP + COL0_X
    body_h = max(col_height.values())

    col_w = {ci: (SOM_W if col_is_spine[ci] else BOX_W) for ci in columns}
    gutter_bounds: dict[int, tuple[float, float]] = {}
    cols_sorted = sorted(columns)
    for i, ci in enumerate(cols_sorted[:-1]):
        nxt = cols_sorted[i + 1]
        lo = col_x[ci] + col_w[ci] + 6
        hi = col_x[nxt] - 6
        gutter_bounds[ci] = (lo, hi)
    last = cols_sorted[-1]
    gutter_bounds[last] = (col_x[last] + col_w[last] + 6,
                           col_x[last] + col_w[last] + 6 + COL_GAP * 0.6)

    spine_x = col_x[SPINE_COL]
    n_bound = max(1, len(som_bound))
    spine_top = TOP + 18
    spine_h = max(body_h - TOP - 40, n_bound * 30 + 60)
    spine_bottom = spine_top + spine_h
    content_h = max(body_h, spine_bottom + 56)

    HW_LANE_GAP = 7.5
    highway_ids: set[int] = set()
    n_span2 = sum(1 for (a, c) in peer
                  if abs(physical_col(a) - physical_col(c)) >= 2)
    hw_band_top = content_h + 16
    hw_h = (24 + n_span2 * HW_LANE_GAP + 10) if n_span2 else 0
    hw_band_bottom = hw_band_top + hw_h

    ISO_BOX_W = BOX_W
    ISO_GAP = 28
    iso_xy: dict[str, tuple[float, float]] = {}
    iso_top = (hw_band_bottom if n_span2 else content_h) + 30
    if isolated:
        iso_per_row = max(1, int((total_w - 2 * COL0_X + ISO_GAP)
                                 // (ISO_BOX_W + ISO_GAP)))
        for i, s in enumerate(isolated):
            r, c = divmod(i, iso_per_row)
            ix = COL0_X + c * (ISO_BOX_W + ISO_GAP)
            iy = iso_top + 24 + r * (BOX_H + 22)
            iso_xy[s] = (ix, iy)
        iso_rows = (len(isolated) + iso_per_row - 1) // iso_per_row
        iso_bottom = iso_top + 24 + iso_rows * (BOX_H + 22)
    else:
        iso_bottom = content_h
    total_h = max(content_h, iso_bottom) + 24

    W, H = round(total_w), round(total_h)
    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
             f'font-family="{FONT}" font-size="{LABEL_PX}">')
    e.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    e.append('<text x="30" y="38" font-size="26" font-weight="700" '
             'fill="#0f172a">Zynq carrier — linked port graph</text>')
    e.append(f'<text x="30" y="62" font-size="15" fill="#64748b">'
             f'{len(sheets)} sheets · {len(som_nets)} SoM contract nets · '
             f'left-to-right by role; edges aggregated per sheet-pair '
             f'(count · dominant kind); long cross-board links in the bottom '
             f'channel</text>')

    _legend(e, W)

    for cl, cx, cy, cw, ch in sorted(cluster_rects, key=lambda r: (r[1], r[2])):
        title, fill, stroke = CLUSTERS[cl]
        e.append(f'<rect x="{cx:.0f}" y="{cy:.0f}" width="{cw:.0f}" '
                 f'height="{ch:.0f}" rx="12" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.3"/>')
        e.append(f'<text x="{cx + 11:.0f}" y="{cy + 16:.0f}" font-size="14" '
                 f'font-weight="700" fill="{stroke}">{_esc(title)}</text>')

    if n_span2:
        e.append(f'<rect x="{COL0_X - CLUSTER_PAD:.0f}" '
                 f'y="{hw_band_top:.0f}" '
                 f'width="{total_w - 2 * (COL0_X - CLUSTER_PAD):.0f}" '
                 f'height="{hw_h:.0f}" rx="12" fill="#f8fafc" '
                 f'stroke="#e2e8f0" stroke-width="1.2"/>')
        e.append(f'<text x="{COL0_X - CLUSTER_PAD + 12:.0f}" '
                 f'y="{hw_band_top + 14:.0f}" font-size="12" font-weight="700" '
                 f'fill="#94a3b8">cross-board links '
                 f'({n_span2} edges spanning &#8805;2 columns, routed clear of '
                 f'the centre)</text>')

    bound_sheets = sorted(som_bound)

    edges: list[dict] = []

    def add_edge(left, right, items, colour, width, role, dash="",
                 right_is_spine=False, left_is_spine=False):
        edges.append(dict(left=left, right=right, items=items, colour=colour,
                          width=width, role=role, dash=dash,
                          right_is_spine=right_is_spine,
                          left_is_spine=left_is_spine))

    for (a, c) in sorted(peer):
        items = peer[(a, c)]
        ca, cc = physical_col(a), physical_col(c)
        left, right = (a, c) if ca <= cc else (c, a)
        label, dom = _edge_label(items)
        colour, width, _ = KIND_STYLE[dom]
        add_edge(left, right, items, colour, width, "peer")
    for s in bound_sheets:
        colour, width = SOM_EDGE
        if physical_col(s) < SPINE_COL:
            add_edge(s, SPINE, som_bound[s], colour, width, "som",
                     right_is_spine=True)
        else:
            add_edge(SPINE, s, som_bound[s], colour, width, "som",
                     left_is_spine=True)
    for s in sorted(deferred):
        dcol, dwid = DEFER_EDGE
        items = [(n, "single") for n in sorted(deferred[s])]
        add_edge(s, "\x00LATER", items, dcol, dwid, "defer", dash="5,4",
                 right_is_spine=True)

    def partner_y(edge, of_left):
        other = edge["right"] if of_left else edge["left"]
        if other in ("\x00LATER", SPINE):
            return spine_top + spine_h / 2
        bx, by = box_xy[other]
        return by + BOX_H / 2

    right_groups: dict[str, list] = defaultdict(list)
    left_groups: dict[str, list] = defaultdict(list)
    for edge in edges:
        if not edge["left_is_spine"]:
            right_groups[edge["left"]].append(edge)
        if not edge["right_is_spine"] and edge["right"] != "\x00LATER":
            left_groups[edge["right"]].append(edge)

    exit_y: dict[int, float] = {}
    entry_y: dict[int, float] = {}

    def slot_ys(box, edge_list, of_left):
        bx, by = box_xy[box]
        n = len(edge_list)
        lo, hi = by + 10, by + BOX_H - 10
        ordered = sorted(edge_list, key=lambda ed: partner_y(ed, of_left))
        for i, ed in enumerate(ordered):
            frac = (i + 1) / (n + 1)
            yield ed, lo + (hi - lo) * frac

    for box, el in right_groups.items():
        for ed, y in slot_ys(box, el, of_left=True):
            exit_y[id(ed)] = y
    for box, el in left_groups.items():
        for ed, y in slot_ys(box, el, of_left=False):
            entry_y[id(ed)] = y

    spine_anchor: dict[str, float] = {}
    if bound_sheets:
        step = spine_h / (len(bound_sheets) + 1)
        for i, s in enumerate(bound_sheets, 1):
            spine_anchor[s] = spine_top + step * i

    def endpoints(edge):
        left, right = edge["left"], edge["right"]
        if edge["left_is_spine"]:
            x0, y0 = spine_x + SOM_W, spine_anchor[right]
        else:
            bx, by = box_xy[left]
            x0, y0 = bx + BOX_W, exit_y[id(edge)]
        if edge["right_is_spine"]:
            if right == "\x00LATER":
                x1, y1 = spine_x + SOM_W / 2, spine_bottom + 30
            else:
                x1, y1 = spine_x, spine_anchor[left]
        else:
            bx, by = box_xy[right]
            x1, y1 = bx, entry_y[id(edge)]
        return x0, y0, x1, y1

    def edge_gutter(edge):
        left, right = edge["left"], edge["right"]
        lcol = (SPINE_COL if left in (SPINE, "\x00LATER")
                else physical_col(left))
        rcol = (SPINE_COL if right in (SPINE, "\x00LATER")
                else physical_col(right))
        return min(lcol, rcol), lcol == rcol

    ordered_edges = sorted(edges, key=lambda ed: (ed["role"], str(ed["left"]),
                                                  str(ed["right"])))

    def is_highway(edge) -> bool:
        if edge["role"] != "peer":
            return False
        return abs(physical_col(edge["left"])
                   - physical_col(edge["right"])) >= 2
    for edge in ordered_edges:
        if is_highway(edge):
            highway_ids.add(id(edge))

    by_gutter: dict[int, list] = defaultdict(list)
    for edge in ordered_edges:
        if id(edge) in highway_ids:
            continue
        gcol, _same = edge_gutter(edge)
        by_gutter[gcol].append(edge)
    lane_x: dict[int, float] = {}
    for gcol, el in by_gutter.items():
        g_lo, g_hi = gutter_bounds[gcol]
        n = len(el)
        el_sorted = sorted(el, key=lambda ed: (lambda p: (p[1] + p[3]) / 2)
                           (endpoints(ed)))
        for i, ed in enumerate(el_sorted):
            frac = (i + 1) / (n + 1)
            lane_x[id(ed)] = g_lo + (g_hi - g_lo) * frac

    hw_edges = [ed for ed in ordered_edges if id(ed) in highway_ids]
    hw_lane_y: dict[int, float] = {}
    hw_src_x: dict[int, float] = {}
    hw_dst_x: dict[int, float] = {}

    def _ep_cols(edge):
        lcol, rcol = physical_col(edge["left"]), physical_col(edge["right"])
        return (lcol, rcol) if lcol <= rcol else (rcol, lcol)

    hw_sorted = sorted(
        hw_edges,
        key=lambda ed: (_ep_cols(ed)[0], endpoints(ed)[1], str(ed["left"]),
                        str(ed["right"])))
    src_gutter: dict[int, list] = defaultdict(list)
    dst_gutter: dict[int, list] = defaultdict(list)
    for ed in hw_sorted:
        lcol, rcol = _ep_cols(ed)
        src_gutter[lcol].append(ed)
        dst_gutter[rcol - 1].append(ed)
    for g, el in src_gutter.items():
        g_lo, g_hi = gutter_bounds[g]
        for i, ed in enumerate(el):
            hw_src_x[id(ed)] = g_lo + (g_hi - g_lo) * (i + 1) / (len(el) + 1)
    for g, el in dst_gutter.items():
        g_lo, g_hi = gutter_bounds[g]
        for i, ed in enumerate(el):
            hw_dst_x[id(ed)] = g_lo + (g_hi - g_lo) * (i + 1) / (len(el) + 1)
    for i, ed in enumerate(hw_sorted):
        hw_lane_y[id(ed)] = hw_band_top + 24 + i * HW_LANE_GAP

    edges_svg: list[str] = []
    label_plan: list[tuple] = []

    for edge in ordered_edges:
        left, right = edge["left"], edge["right"]
        colour, width = edge["colour"], edge["width"]
        x0, y0, x1, y1 = endpoints(edge)
        gcol, same = edge_gutter(edge)
        is_hw = id(edge) in highway_ids
        if is_hw:
            sx, dx = hw_src_x[id(edge)], hw_dst_x[id(edge)]
            hy = hw_lane_y[id(edge)]
            d = (f"M{x0:.1f},{y0:.1f} H{sx:.1f} V{hy:.1f} H{dx:.1f} "
                 f"V{y1:.1f} H{x1:.1f}")
        elif same:
            jitter = (sum(map(ord, str(left) + str(right))) % 5) * 7
            mx = max(x0, x1) + 14 + jitter
            d = f"M{x0:.1f},{y0:.1f} H{mx:.1f} V{y1:.1f} H{x1:.1f}"
        else:
            mx = lane_x[id(edge)]
            d = f"M{x0:.1f},{y0:.1f} H{mx:.1f} V{y1:.1f} H{x1:.1f}"
        da = f' stroke-dasharray="{edge["dash"]}"' if edge["dash"] else ""
        title = ", ".join(n for n, _ in edge["items"])
        ln = "SoM" if left == SPINE else _esc(str(left))
        rn = ("SoM" if right == SPINE else
              "later" if right == "\x00LATER" else _esc(str(right)))
        edges_svg.append(
            f'<path d="{d}" fill="none" stroke="{colour}" '
            f'stroke-width="{width}" stroke-linejoin="round" '
            f'stroke-opacity="0.72"{da}>'
            f'<title>{ln} ↔ {rn}: {_esc(title)}</title></path>')
        if right == SPINE:
            edges_svg.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2.6" '
                             f'fill="{colour}"/>')
        if edge["left_is_spine"]:
            edges_svg.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="2.6" '
                             f'fill="{colour}"/>')
        if edge["role"] == "defer":
            text = f"{len(edge['items'])} {_net_word(len(edge['items']))} deferred"
        else:
            text, _dom = _edge_label(edge["items"])
        if right == SPINE:
            ax, ay = x1 - 6, y1
            anchor = "end"
            lo, hi = spine_top + 6, spine_bottom - 6
        elif edge["left_is_spine"]:
            ax, ay = x0 + 6, y0
            anchor = "start"
            lo, hi = spine_top + 6, spine_bottom - 6
        elif right == "\x00LATER":
            ax, ay, anchor = x0 + 8, y0, "start"
            lo, hi = y0 - 6, y0 + 30
        else:
            ax, ay = x1 - 6, y1
            anchor = "end"
            lo, hi = y1 - 40, y1 + 40
        label_plan.append((ax, ay, text, colour, anchor, lo, hi))

    e.extend(edges_svg)

    LBL_PX = 13
    LBL_CH = 6.7
    LBL_VGAP = 16
    label_svg: list[str] = []
    placed: list[tuple[float, float, float]] = []
    label_plan.sort(key=lambda t: (round(t[0]), t[1], t[2]))
    for ax, ay, text, colour, anchor, lo, hi in label_plan:
        w = LBL_CH * len(text) + 12
        cx = ax - w / 2 if anchor == "end" else ax + w / 2
        half = w / 2
        yy = ay
        found = False
        for step in range(0, 48):
            for sgn in ((0,) if step == 0 else (-1, 1)):
                cand = ay + sgn * step * 8
                if cand < lo or cand > hi:
                    continue
                clash = any(abs(px - cx) < (half + phw) and
                            abs(py - cand) < LBL_VGAP
                            for px, py, phw in placed)
                if not clash:
                    yy = cand
                    found = True
                    break
            if found:
                break
        if not found:
            continue
        placed.append((cx, yy, half))
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        label_svg.append(
            f'<rect x="{cx - half:.1f}" y="{yy - 9.5:.1f}" width="{w:.1f}" '
            f'height="17" rx="5" fill="#ffffff" fill-opacity="0.97" '
            f'stroke="{colour}" stroke-opacity="0.5" stroke-width="0.8"/>')
        label_svg.append(
            f'<text x="{ax:.1f}" y="{yy + 3.5:.1f}"{a} font-size="{LBL_PX}" '
            f'font-weight="600" fill="{colour}">{_esc(text)}</text>')
    e.extend(label_svg)

    e.append(f'<rect x="{spine_x:.0f}" y="{spine_top:.0f}" width="{SOM_W}" '
             f'height="{spine_h:.0f}" rx="12" fill="#fef3c7" '
             f'stroke="#b45309" stroke-width="2.4"/>')
    e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{spine_top + 26:.0f}" '
             f'text-anchor="middle" font-size="15" font-weight="700" '
             f'fill="#78350f">Zynq SoM</text>')
    e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{spine_top + 44:.0f}" '
             f'text-anchor="middle" font-size="11" fill="#92400e">'
             f'J1 / J2 / J3 contract</text>')
    e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{spine_top + 62:.0f}" '
             f'text-anchor="middle" font-size="11" fill="#92400e">'
             f'{len(som_nets)} nets</text>')
    ry = spine_top + 86
    e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{ry:.0f}" '
             f'text-anchor="middle" font-size="10.5" font-weight="600" '
             f'fill="#78350f">rails</text>')
    for r in rails:
        ry += 15
        e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{ry:.0f}" '
                 f'text-anchor="middle" font-size="10.5" fill="#92400e">'
                 f'{_esc(r)}</text>')
    nub = len(link_result.unbound_som)
    e.append(f'<text x="{spine_x + SOM_W / 2:.0f}" y="{spine_bottom - 10:.0f}" '
             f'text-anchor="middle" font-size="10" fill="#a16207">'
             f'{nub} unbound (later)</text>')

    if deferred:
        n_def = sum(len(v) for v in deferred.values())
        later_x = spine_x + SOM_W / 2
        later_y = spine_bottom + 30
        e.append(f'<rect x="{later_x - 58:.0f}" y="{later_y - 13:.0f}" '
                 f'width="116" height="26" rx="8" fill="#ffffff" '
                 f'stroke="#9ca3af" stroke-width="1.3" '
                 f'stroke-dasharray="5,4"/>')
        e.append(f'<text x="{later_x:.0f}" y="{later_y + 4:.0f}" '
                 f'text-anchor="middle" font-size="11" fill="#6b7280">'
                 f'later waves · {n_def}</text>')

    for s in laid_sheets:
        bx, by = box_xy[s]
        _, fill, stroke = CLUSTERS[cluster_of[s]]
        nb, nd = len(som_bound.get(s, [])), len(deferred.get(s, []))
        np = sum(len(v) for (a, c), v in peer.items() if s in (a, c))
        e.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{BOX_W}" '
                 f'height="{BOX_H}" rx="8" fill="#ffffff" stroke="{stroke}" '
                 f'stroke-width="1.8"/>')
        e.append(f'<text x="{bx + 11:.0f}" y="{by + 23:.0f}" font-size="15.5" '
                 f'font-weight="700" fill="#0f172a">{_esc(s)}</text>')
        sub = []
        if nb:
            sub.append(f"{nb} SoM")
        if np:
            sub.append(f"{np} peer")
        if nd:
            sub.append(f"{nd} deferred")
        e.append(f'<text x="{bx + 11:.0f}" y="{by + 43:.0f}" font-size="12.5" '
                 f'fill="#64748b">{_esc(" · ".join(sub) or "—")}</text>')

    if isolated:
        e.append(f'<text x="{COL0_X:.0f}" y="{iso_top + 6:.0f}" font-size="13" '
                 f'font-weight="700" fill="#475569">'
                 f'unconnected sheets (no inter-sheet nets)</text>')
        for s in isolated:
            bx, by = iso_xy[s]
            _, fill, stroke = CLUSTERS[cluster_of[s]]
            e.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{ISO_BOX_W}" '
                     f'height="{BOX_H}" rx="8" fill="#f8fafc" '
                     f'stroke="{stroke}" stroke-width="1.6"/>')
            e.append(f'<text x="{bx + 11:.0f}" y="{by + 23:.0f}" '
                     f'font-size="15.5" font-weight="700" '
                     f'fill="#334155">{_esc(s)}</text>')
            e.append(f'<text x="{bx + 11:.0f}" y="{by + 43:.0f}" '
                     f'font-size="12.5" fill="#94a3b8">—</text>')

    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


def _legend(e: list[str], W: int) -> None:
    items = [(KIND_STYLE["power"], "power rail"),
             (KIND_STYLE["diff_pair"], "diff pair"),
             (KIND_STYLE["tmds_pair"], "TMDS pair"),
             (KIND_STYLE["usb_hs_pair"], "USB HS pair"),
             (KIND_STYLE["sd_bus"], "SD bus"),
             (KIND_STYLE["i2c"], "I2C bus"),
             (KIND_STYLE["single"], "signal"),
             ((SOM_EDGE[0], SOM_EDGE[1], ""), "SoM contract"),
             ((DEFER_EDGE[0], DEFER_EDGE[1], ""), "deferred")]
    cols = 3
    cw = 168
    rh = 21
    rows = (len(items) + cols - 1) // cols
    bw = cols * cw + 18
    bh = rows * rh + 26
    lx = W - bw - 26
    ly = 18
    e.append(f'<rect x="{lx}" y="{ly}" width="{bw}" height="{bh}" rx="8" '
             f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
    e.append(f'<text x="{lx + 12}" y="{ly + 17}" font-size="13" '
             f'font-weight="700" fill="#334155">legend</text>')
    for i, ((colour, width, _g), name) in enumerate(items):
        col = i % cols
        rw = i // cols
        ix = lx + 12 + col * cw
        iy = ly + 36 + rw * rh
        dash = ' stroke-dasharray="5,4"' if name == "deferred" else ""
        e.append(f'<line x1="{ix}" y1="{iy - 4}" x2="{ix + 28}" y2="{iy - 4}" '
                 f'stroke="{colour}" stroke-width="{width + 0.4}"{dash}/>')
        e.append(f'<text x="{ix + 34}" y="{iy}" font-size="12.5" '
                 f'fill="#475569">{_esc(name)}</text>')
