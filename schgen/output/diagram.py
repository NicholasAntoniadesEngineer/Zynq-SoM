"""Block diagram (SVG) generated from the linked port graph. No deps.

A layered, left-to-right system map (a documentation drawing — it carries NO
electrical meaning, so junctions/crossings here are cosmetic, never a net).

Layout (BD-1..8):
  * every sheet is assigned a ROLE LAYER (column): power/bring-up sources on
    the left, the SoM connector sheets + the SoM contract spine in the middle,
    peripherals next, physical connectors on the right.  Within each column the
    node order is refined by barycentre sweeps to reduce edge crossings.
  * sheet<->sheet PORT links are AGGREGATED to one edge per sheet-pair carrying
    a net COUNT + a dominant-kind summary (the full net list lives in the edge
    <title> tooltip).
  * the SoM contract is a TALL central node; each incoming edge gets its own
    entry y so the old "star into one pixel" is gone.
  * edges route orthogonally (Manhattan) through the inter-column gutters with
    per-edge lanes; boxes are painted on top of the edges.
  * colour/​weight is driven by the dominant ptype.kind (power rails vs
    diff/tmds/usb pairs vs i2c vs single); a legend explains it.
  * sheets sit inside labelled subsystem CLUSTER containers.

Deterministic: sorted iteration, content-derived geometry, no timestamps —
re-running is byte-identical.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

# ---- type -> colour / weight (BD-5) -------------------------------------------
FONT = "Segoe UI, Helvetica, Arial, sans-serif"
LABEL_PX = 13

# dominant kind -> (stroke colour, stroke width, human group label)
KIND_STYLE: dict[str, tuple[str, float, str]] = {
    "power":        ("#b45309", 2.6, "power rail"),
    "diff_pair":    ("#7c3aed", 2.0, "diff pair"),
    "tmds_pair":    ("#db2777", 2.0, "TMDS pair"),
    "usb_hs_pair":  ("#0891b2", 2.0, "USB HS pair"),
    "i2c":          ("#16a34a", 1.7, "I2C bus"),
    "sd_bus":       ("#ca8a04", 1.9, "SD bus"),
    "single":       ("#2563eb", 1.4, "signal"),
}
SOM_EDGE = ("#1d4ed8", 2.0)        # sheet -> SoM contract spine
DEFER_EDGE = ("#9ca3af", 1.4)      # deferred (dashed)

# ---- subsystem clusters (BD-7) -------------------------------------------------
# (cluster key -> (human title, fill, stroke)).  Order here is the column order
# of clusters within a layer when several clusters share a layer.
CLUSTERS: dict[str, tuple[str, str, str]] = {
    "power":   ("Power & bring-up",   "#fff7ed", "#fdba74"),
    "som":     ("SoM connectors",     "#fffbeb", "#fcd34d"),
    "video":   ("Video / display",    "#faf5ff", "#d8b4fe"),
    "storage": ("Storage & USB",      "#ecfeff", "#67e8f9"),
    "net":     ("Networking",         "#f0fdf4", "#86efac"),
    "io":      ("FMC / user IO",      "#eff6ff", "#93c5fd"),
}

# sheet -> (cluster, role-layer).  Layer 0 = sources (left); the SoM connector
# sheets sit at layer 1 next to the contract spine; peripherals at 2; physical
# connectors / leaf sheets at 3.  Anything unlisted defaults to ("io", 2).
SHEET_ROLE: dict[str, tuple[str, int]] = {
    # layer 0 — power input + bring-up control sources
    "pd_input":           ("power", 0),
    "power":              ("power", 0),
    "power_mon":          ("power", 0),
    "bringup_rails":      ("power", 0),
    "bringup_en":         ("power", 0),
    "bringup_en_modules": ("power", 0),
    "bringup_modules":    ("power", 0),
    # layer 1 — the SoM connector sheets (the contract spine sits between them)
    "som_j1":             ("som", 1),
    "som_j2":             ("som", 1),
    "som_j3":             ("som", 1),
    # layer 2 — peripherals fed off the SoM
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
    # layer 3 — physical connectors / termination leaves
    "hdmi_rx_term":      ("video", 3),
    "rj45_connector":    ("net", 3),
    "usb_uart_connector": ("storage", 3),
}
DEFAULT_ROLE = ("io", 2)

# ---- geometry -----------------------------------------------------------------
BOX_W = 168
BOX_H = 48
COL_GAP = 150           # gutter between column body edges (lanes live here)
ROW_GAP = 26            # vertical gap between boxes in a column
COL0_X = 150            # left margin before first column
TOP = 96               # space for title + legend
SOM_W = 140             # the central contract spine width
CLUSTER_PAD = 14


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- edge label grammar (BD-6) ------------------------------------------------
def _net_word(n: int) -> str:
    return "net" if n == 1 else "nets"


def _dominant_kind(kinds: list[str]) -> str:
    """The most common non-'single' kind, else 'single'. Deterministic."""
    c = Counter(kinds)
    ranked = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    for k, _ in ranked:
        if k != "single":
            return k
    return "single"


def _edge_label(items: list[tuple[str, str]]) -> tuple[str, str]:
    """items = [(net, kind), ...] -> (short label, dominant kind)."""
    n = len(items)
    dom = _dominant_kind([k for _, k in items])
    grp = KIND_STYLE[dom][2]
    return f"{n} {_net_word(n)} · {grp}", dom


# ---- the renderer -------------------------------------------------------------
def render(link_result, som_nets: dict[str, list[str]], out: Path) -> Path:
    sheets = sorted(sc.name for sc in link_result.sheets)

    # --- harvest the graph from the bindings ----------------------------------
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
    # peer lists carry both directions of every shared net once each — de-dup.
    for k in list(peer):
        peer[k] = sorted(set(peer[k]))

    rails = sorted({r.split(" ", 1)[0] for r in link_result.rail_bindings
                    if "SoM" in r})

    # --- assign each sheet a (cluster, layer) ---------------------------------
    role = {s: SHEET_ROLE.get(s, DEFAULT_ROLE) for s in sheets}
    layer_of = {s: role[s][1] for s in sheets}
    cluster_of = {s: role[s][0] for s in sheets}

    # The SoM contract spine is a virtual node in its OWN column, placed just
    # right of the SoM-connector layer (so connector/source layers sit to its
    # left and peripheral/connector layers to its right).
    SPINE = "\x00SoM"
    cl_order = list(CLUSTERS)

    # --- pack each role layer into physical COLUMNS, capped in height ----------
    # A single layer may hold many sheets (peripherals); splitting it across a
    # couple of columns keeps the canvas LANDSCAPE.  Splits fall on cluster
    # boundaries so a cluster never straddles two columns, and the per-column
    # box budget keeps every column under the height target.
    MAX_PER_COL = 6

    def layer_columns(members: list[str]) -> list[list[str]]:
        """Order a layer's sheets by cluster then split into <=MAX_PER_COL
        columns without breaking a cluster across a column boundary."""
        by_cl: dict[str, list[str]] = defaultdict(list)
        for s in sorted(members):
            by_cl[cluster_of[s]].append(s)
        runs = [by_cl[cl] for cl in cl_order if cl in by_cl]
        cols: list[list[str]] = []
        cur: list[str] = []
        for run in runs:
            if cur and len(cur) + len(run) > MAX_PER_COL:
                cols.append(cur)
                cur = []
            cur.extend(run)
        if cur:
            cols.append(cur)
        return cols or [[]]

    layers = sorted({layer_of[s] for s in sheets})
    layer_members = {lv: [s for s in sheets if layer_of[s] == lv]
                     for lv in layers}

    # Build the ordered list of physical columns, inserting the spine column
    # immediately after the SoM-connector layer (role layer 1).
    columns: dict[int, list[str]] = {}
    col_is_spine: dict[int, bool] = {}
    ci = 0
    for lv in layers:
        for col in layer_columns(layer_members[lv]):
            columns[ci] = col
            col_is_spine[ci] = False
            ci += 1
        if lv == 1:                       # spine sits right after connectors
            columns[ci] = []
            col_is_spine[ci] = True
            SPINE_COL = ci
            ci += 1
    if not any(col_is_spine.values()):    # no layer-1 sheets: spine at front
        SPINE_COL = 0
        columns = {k + 1: v for k, v in columns.items()}
        col_is_spine = {k + 1: v for k, v in col_is_spine.items()}
        columns[0] = []
        col_is_spine[0] = True

    col_of: dict[str, int] = {s: ci for ci, mem in columns.items() for s in mem}

    def physical_col(s: str) -> int:
        return col_of[s]

    # --- adjacency for crossing-reduction ordering ----------------------------
    adj: dict[str, list[str]] = defaultdict(list)
    for (a, c) in peer:
        adj[a].append(c)
        adj[c].append(a)
    for s in som_bound:
        adj[s].append(SPINE)
        adj[SPINE].append(s)

    pos_in_col: dict[str, int] = {}

    def reindex() -> None:
        for cidx, mem in columns.items():
            for i, s in enumerate(mem):
                pos_in_col[s] = i
        # spine pseudo-position: mean of its bound sheets' positions
        bp = [pos_in_col[s] for s in som_bound if s in pos_in_col]
        pos_in_col[SPINE] = sum(bp) / len(bp) if bp else 0
    reindex()

    def barycentre(s: str) -> float:
        ns = adj.get(s, [])
        vals = [pos_in_col.get(n, 0) for n in ns]
        return sum(vals) / len(vals) if vals else pos_in_col.get(s, 0)

    # 3 barycentre sweeps (deterministic; N is tiny), keeping clusters grouped
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

    # --- vertical layout: stack boxes per column, grouped by cluster ----------
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
            y += 26   # gap between clusters in a column
        col_height[cidx] = y
        x += (SOM_W if col_is_spine[cidx] else BOX_W) + COL_GAP

    total_w = x - COL_GAP + COL0_X
    body_h = max(col_height.values())

    # gutter[gcol] = (x just right of column gcol's boxes,
    #                 x just left of column gcol+1's boxes) — the empty band
    # where vertical edge legs and their labels live (never over a box).
    col_w = {ci: (SOM_W if col_is_spine[ci] else BOX_W) for ci in columns}
    gutter_bounds: dict[int, tuple[float, float]] = {}
    cols_sorted = sorted(columns)
    for i, ci in enumerate(cols_sorted[:-1]):
        nxt = cols_sorted[i + 1]
        lo = col_x[ci] + col_w[ci] + 6
        hi = col_x[nxt] - 6
        gutter_bounds[ci] = (lo, hi)
    # a trailing gutter past the last column (for any rightmost same-col hops)
    last = cols_sorted[-1]
    gutter_bounds[last] = (col_x[last] + col_w[last] + 6,
                           col_x[last] + col_w[last] + 6 + COL_GAP * 0.6)

    # --- SoM spine geometry (BD-3): tall, centred, one anchor per bound sheet --
    spine_x = col_x[SPINE_COL]
    n_bound = max(1, len(som_bound))
    spine_top = TOP + 18
    spine_h = max(body_h - TOP - 40, n_bound * 30 + 60)
    spine_bottom = spine_top + spine_h
    total_h = max(body_h, spine_bottom + 56) + 24

    # --- begin SVG ------------------------------------------------------------
    W, H = round(total_w), round(total_h)
    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
             f'font-family="{FONT}" font-size="{LABEL_PX}">')
    e.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    e.append(f'<text x="28" y="34" font-size="22" font-weight="700" '
             f'fill="#0f172a">Zynq carrier — linked port graph</text>')
    e.append(f'<text x="28" y="56" font-size="13" fill="#64748b">'
             f'{len(sheets)} sheets · {len(som_nets)} SoM contract nets '
             f'· left-to-right by role; edges aggregated per sheet-pair'
             f'</text>')

    _legend(e, W)

    # --- cluster containers (painted first, behind everything) ----------------
    for cl, cx, cy, cw, ch in sorted(cluster_rects, key=lambda r: (r[1], r[2])):
        title, fill, stroke = CLUSTERS[cl]
        e.append(f'<rect x="{cx:.0f}" y="{cy:.0f}" width="{cw:.0f}" '
                 f'height="{ch:.0f}" rx="12" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.3"/>')
        e.append(f'<text x="{cx + 10:.0f}" y="{cy + 15:.0f}" font-size="12" '
                 f'font-weight="700" fill="{stroke}">{_esc(title)}</text>')

    # --- plan every edge, then route + label with anti-collision ---------------
    # Each edge is (left_node, right_node, items, kind-style, role) where the
    # node may be a sheet or the SPINE.  We give every edge a distinct EXIT slot
    # on its source box (so edges fan out instead of stacking on the centre) and
    # a distinct vertical LANE in the gutter it crosses; the label sits on that
    # lane's vertical segment, so labels separate horizontally by construction.

    bound_sheets = sorted(som_bound)

    edges: list[dict] = []

    def add_edge(left, right, items, colour, width, role, dash="",
                 right_is_spine=False, left_is_spine=False):
        edges.append(dict(left=left, right=right, items=items, colour=colour,
                          width=width, role=role, dash=dash,
                          right_is_spine=right_is_spine,
                          left_is_spine=left_is_spine))

    # peer edges
    for (a, c) in sorted(peer):
        items = peer[(a, c)]
        ca, cc = physical_col(a), physical_col(c)
        left, right = (a, c) if ca <= cc else (c, a)
        label, dom = _edge_label(items)
        colour, width, _ = KIND_STYLE[dom]
        add_edge(left, right, items, colour, width, "peer")
    # SoM-contract edges
    for s in bound_sheets:
        colour, width = SOM_EDGE
        if physical_col(s) < SPINE_COL:
            add_edge(s, SPINE, som_bound[s], colour, width, "som",
                     right_is_spine=True)
        else:
            add_edge(SPINE, s, som_bound[s], colour, width, "som",
                     left_is_spine=True)
    # deferred edges
    for s in sorted(deferred):
        dcol, dwid = DEFER_EDGE
        items = [(n, "single") for n in sorted(deferred[s])]
        add_edge(s, "\x00LATER", items, dcol, dwid, "defer", dash="5,4",
                 right_is_spine=True)

    # ---- distribute EXIT slots along each source/target box edge -------------
    # group edges by the box they leave on the right and the box they enter on
    # the left; order by the partner's vertical position so lines don't cross
    # near the box.
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

    exit_y: dict[int, float] = {}     # id(edge) -> source y
    entry_y: dict[int, float] = {}    # id(edge) -> target y

    def slot_ys(box, edge_list, of_left):
        bx, by = box_xy[box]
        n = len(edge_list)
        # usable inner band of the box edge
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

    # spine entry anchors: one distributed y per bound sheet (BD-3)
    spine_anchor: dict[str, float] = {}
    if bound_sheets:
        step = spine_h / (len(bound_sheets) + 1)
        for i, s in enumerate(bound_sheets, 1):
            spine_anchor[s] = spine_top + step * i

    # ---- resolve every edge's endpoints + its gutter -------------------------
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
    # group edges by gutter so each gets a UNIQUE lane x (no modulo collisions)
    by_gutter: dict[int, list] = defaultdict(list)
    for edge in ordered_edges:
        gcol, _same = edge_gutter(edge)
        by_gutter[gcol].append(edge)
    lane_x: dict[int, float] = {}
    for gcol, el in by_gutter.items():
        g_lo, g_hi = gutter_bounds[gcol]
        n = len(el)
        # order lanes by the vertical midpoint of the edge so adjacent lanes
        # carry adjacent edges (fewer crossings inside the gutter)
        el_sorted = sorted(el, key=lambda ed: (lambda p: (p[1] + p[3]) / 2)
                           (endpoints(ed)))
        for i, ed in enumerate(el_sorted):
            frac = (i + 1) / (n + 1)
            lane_x[id(ed)] = g_lo + (g_hi - g_lo) * frac

    edges_svg: list[str] = []
    label_plan: list[tuple] = []   # (x, y, text, colour, lo, hi)

    for edge in ordered_edges:
        left, right = edge["left"], edge["right"]
        colour, width = edge["colour"], edge["width"]
        x0, y0, x1, y1 = endpoints(edge)
        gcol, same = edge_gutter(edge)
        if same:
            # deterministic small stagger keyed on the pair name (no id()):
            jitter = (sum(map(ord, str(left) + str(right))) % 5) * 7
            mx = max(x0, x1) + 14 + jitter
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
            f'stroke-width="{width}" stroke-linejoin="round"{da}>'
            f'<title>{ln} ↔ {rn}: {_esc(title)}</title></path>')
        if right == SPINE:
            edges_svg.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2.6" '
                             f'fill="{colour}"/>')
        if edge["left_is_spine"]:
            edges_svg.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="2.6" '
                             f'fill="{colour}"/>')
        # label candidate: count + dominant group.  Anchor it just OUTSIDE the
        # destination box, on the horizontal entry segment — destinations have
        # few incoming edges each, so labels separate vertically by box-row and
        # stay out of the congested source gutter.
        if edge["role"] == "defer":
            text = f"{len(edge['items'])} {_net_word(len(edge['items']))} deferred"
        else:
            text, _dom = _edge_label(edge["items"])
        # choose the endpoint with more clearance: the SoM spine entry (roomy,
        # distributed) for SoM edges, else the right/destination box entry.
        if right == SPINE:
            ax, ay = x1 - 6, y1            # at the spine's left entry
            anchor = "end"
            lo, hi = spine_top + 6, spine_bottom - 6
        elif edge["left_is_spine"]:
            ax, ay = x0 + 6, y0            # at the spine's right entry
            anchor = "start"
            lo, hi = spine_top + 6, spine_bottom - 6
        elif right == "\x00LATER":
            ax, ay, anchor = x0 + 8, y0, "start"
            lo, hi = y0 - 6, y0 + 30
        else:
            ax, ay = x1 - 6, y1            # just left of the destination box
            anchor = "end"
            lo, hi = y1 - 40, y1 + 40
        label_plan.append((ax, ay, text, colour, anchor, lo, hi))

    e.extend(edges_svg)

    # ---- labels: anchored at the (roomy) endpoint, nudged to dodge neighbours,
    # SKIP on collision (detail stays in the edge <title> tooltip).  Readability
    # beats completeness (LAW 1).
    label_svg: list[str] = []
    placed: list[tuple[float, float, float]] = []   # cx, cy, half-width
    label_plan.sort(key=lambda t: (round(t[0]), t[1], t[2]))
    for ax, ay, text, colour, anchor, lo, hi in label_plan:
        w = 6.0 * len(text) + 8
        # the label box's centre x depends on the anchor
        cx = ax - w / 2 if anchor == "end" else ax + w / 2
        half = w / 2
        yy = ay
        # search up and down for a clear vertical slot within [lo, hi]
        found = False
        for step in range(0, 40):
            for sgn in ((0,) if step == 0 else (-1, 1)):
                cand = ay + sgn * step * 13
                if cand < lo or cand > hi:
                    continue
                clash = any(abs(px - cx) < (half + phw) and abs(py - cand) < 13
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
            f'<rect x="{cx - half:.1f}" y="{yy - 8.5:.1f}" width="{w:.1f}" '
            f'height="15" rx="4" fill="#ffffff" fill-opacity="0.92" '
            f'stroke="{colour}" stroke-opacity="0.25" stroke-width="0.7"/>')
        label_svg.append(
            f'<text x="{ax:.1f}" y="{yy + 3:.1f}"{a} font-size="11" '
            f'font-weight="600" fill="{colour}">{_esc(text)}</text>')
    e.extend(label_svg)

    # --- SoM contract spine (BD-3) -------------------------------------------
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
    # rail summary down the spine
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

    # later-waves tag (under the spine; deferred edges route here)
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

    # --- sheet boxes (on top of edges) ----------------------------------------
    for s in sheets:
        bx, by = box_xy[s]
        _, fill, stroke = CLUSTERS[cluster_of[s]]
        nb, nd = len(som_bound.get(s, [])), len(deferred.get(s, []))
        np = sum(len(v) for (a, c), v in peer.items() if s in (a, c))
        e.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{BOX_W}" '
                 f'height="{BOX_H}" rx="8" fill="#ffffff" stroke="{stroke}" '
                 f'stroke-width="1.6"/>')
        e.append(f'<text x="{bx + 10:.0f}" y="{by + 19:.0f}" font-size="13.5" '
                 f'font-weight="700" fill="#0f172a">{_esc(s)}</text>')
        sub = []
        if nb:
            sub.append(f"{nb} SoM")
        if np:
            sub.append(f"{np} peer")
        if nd:
            sub.append(f"{nd} deferred")
        e.append(f'<text x="{bx + 10:.0f}" y="{by + 36:.0f}" font-size="10.5" '
                 f'fill="#64748b">{_esc(" · ".join(sub) or "—")}</text>')

    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


def _legend(e: list[str], W: int) -> None:
    """Colour/weight legend (BD-5), top-right."""
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
    cw = 150
    rows = (len(items) + cols - 1) // cols
    bw = cols * cw + 16
    bh = rows * 17 + 20
    lx = W - bw - 24
    ly = 18
    e.append(f'<rect x="{lx}" y="{ly}" width="{bw}" height="{bh}" rx="8" '
             f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
    e.append(f'<text x="{lx + 10}" y="{ly + 15}" font-size="11" '
             f'font-weight="700" fill="#334155">legend</text>')
    for i, ((colour, width, _g), name) in enumerate(items):
        col = i % cols
        rw = i // cols
        ix = lx + 10 + col * cw
        iy = ly + 30 + rw * 17
        dash = ' stroke-dasharray="5,4"' if name == "deferred" else ""
        e.append(f'<line x1="{ix}" y1="{iy - 3}" x2="{ix + 24}" y2="{iy - 3}" '
                 f'stroke="{colour}" stroke-width="{width}"{dash}/>')
        e.append(f'<text x="{ix + 30}" y="{iy}" font-size="10.5" '
                 f'fill="#475569">{_esc(name)}</text>')
