"""Carrier floorplan SUGGESTION — generated from the netlists, to scale.

``schgen floorplan`` (also run by ``schgen board``) writes
``carrier/docs/FLOORPLAN.svg`` + ``carrier/docs/FLOORPLAN.md``: a 2D
placement suggestion for the PCB layout's first hour. Every number is
DERIVED, never invented:

  - SoM outline + DF40 J1/J2/J3 mezzanine positions: parsed live from
    ``som/Zynq_SoM.kicad_pcb`` (Edge.Cuts bbox + footprint ``at`` + pad
    extents), mirrored to the carrier-top view;
  - block sizes: per-part courtyard boxes (``parts/<MPN>/<MPN>.kicad_mod``
    F.CrtYd bbox; KiCad-standard footprints from the dimensions encoded in
    their own names) plus a routing factor on small parts;
  - edge pinning + zone affinity: connector parts found in each sheet's
    netlist + the linker's J1/J2/J3 bindings (including author-declared
    ``expect=`` deferrals naming their target connector);
  - electrical notes: schgen/constraints.py JLC04161H-7628 geometry, the
    power-tree analysis (regulator stages -> thermal), typed-port levels
    (the 1.8V SDIO island).

SUGGESTION, NOT CONSTRAINT: PLAN.md round 2 leaves the form factor free
("connector-driven ~120x100 class expected; user owns outline"). The SVG is
one self-consistent, to-scale starting point; the MD explains every WHY so
each decision can be overruled deliberately. Deterministic output: same
inputs -> byte-identical files (no timestamps).
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOM_PCB = REPO_ROOT / "som" / "Zynq_SoM.kicad_pcb"
PARTS_DIR = REPO_ROOT / "parts"
OUT_SVG = REPO_ROOT / "carrier" / "docs" / "FLOORPLAN.svg"
OUT_MD = REPO_ROOT / "carrier" / "docs" / "FLOORPLAN.md"

# Suggested outline class — PLAN.md round 2 (user): "Form factor: free,
# connector-driven (~120x100 class expected; user owns outline)".
BOARD_W = 120.0
BOARD_H = 100.0

EDGE_MARGIN = 4.0        # board corners kept clear of edge connectors
CONN_SIDE_MARGIN = 1.5   # block width = connector span + this each side
EDGE_DEPTH_CAP = 22.0    # edge block max depth into the board
CLEAR = 1.5              # block-to-block clearance
BIG_PART_MM2 = 40.0      # parts at/above this use raw courtyard area
ROUTE_FACTOR = 3.5       # small-part area multiplier (escape + routing)

FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"
SCALE = 6.0              # SVG px per mm


# ---- SoM PCB extraction ----------------------------------------------------------

@dataclass(frozen=True)
class SomJ:
    ref: str
    pcb_x: float          # raw position in the SoM PCB file
    pcb_y: float
    rot: float
    x: float              # carrier-top view, SoM-relative (mirrored)
    y: float
    w: float              # pad-extent box in that view
    h: float


@dataclass(frozen=True)
class SomGeom:
    w: float
    h: float
    js: tuple[SomJ, ...]
    source: str


_NUMS = re.compile(r"-?\d+(?:\.\d+)?")


def _floats(s: str) -> list[float]:
    return [float(m) for m in _NUMS.findall(s)]


def extract_som(pcb: Path = SOM_PCB) -> SomGeom:
    """Outline bbox (Edge.Cuts) + the three DF40 mezzanine footprints,
    identified by their Reference property. Positions are mirrored about the
    vertical axis: the connectors sit on the SoM's BOTTOM copper, so the
    carrier-top view of the mating receptacles is the bottom-side view."""
    edge_pts: list[tuple[float, float]] = []
    js_raw: dict[str, tuple[float, float, float, float, float]] = {}

    in_gr = False
    gr_pts: list[tuple[float, float]] = []
    in_fp = False
    fp_at: tuple[float, float, float] | None = None
    fp_ref: str | None = None
    pad_xs: list[float] = []
    pad_ys: list[float] = []
    pad_at: tuple[float, float] | None = None
    pad_pending = False

    def commit_fp() -> None:
        nonlocal in_fp
        if in_fp and fp_ref in ("J1", "J2", "J3") and fp_at and pad_xs:
            w = max(pad_xs) - min(pad_xs)
            h = max(pad_ys) - min(pad_ys)
            js_raw[fp_ref] = (fp_at[0], fp_at[1], fp_at[2], w, h)
        in_fp = False

    for raw in pcb.read_text().splitlines():
        s = raw.strip()
        if s.startswith("(gr_line") or s.startswith("(gr_arc"):
            commit_fp()
            in_gr, gr_pts = True, []
            continue
        if in_gr:
            if s.startswith(("(start ", "(mid ", "(end ")):
                v = _floats(s)
                if len(v) >= 2:
                    gr_pts.append((v[0], v[1]))
            elif s.startswith("(layer "):
                if '"Edge.Cuts"' in s:
                    edge_pts.extend(gr_pts)
                in_gr = False
            continue
        if s.startswith("(footprint "):
            commit_fp()
            in_fp = True
            fp_at, fp_ref = None, None
            pad_xs, pad_ys = [], []
            pad_pending, pad_at = False, None
            continue
        if not in_fp:
            continue
        if fp_at is None and s.startswith("(at "):
            v = _floats(s)
            fp_at = (v[0], v[1], v[2] if len(v) > 2 else 0.0)
        elif s.startswith('(property "Reference"'):
            q = s.split('"')
            if len(q) >= 4:
                fp_ref = q[3]
        elif s.startswith("(pad "):
            pad_pending, pad_at = True, None
        elif pad_pending and s.startswith("(at "):
            v = _floats(s)
            pad_at = (v[0], v[1])
        elif pad_pending and pad_at and s.startswith("(size "):
            v = _floats(s)
            pad_xs += [pad_at[0] - v[0] / 2, pad_at[0] + v[0] / 2]
            pad_ys += [pad_at[1] - v[1] / 2, pad_at[1] + v[1] / 2]
            pad_pending = False
    commit_fp()

    if not edge_pts:
        raise RuntimeError(f"no Edge.Cuts outline found in {pcb}")
    missing = {"J1", "J2", "J3"} - set(js_raw)
    if missing:
        raise RuntimeError(f"DF40 footprints not found in {pcb}: "
                           f"{sorted(missing)}")
    x0 = min(p[0] for p in edge_pts)
    y0 = min(p[1] for p in edge_pts)
    w = max(p[0] for p in edge_pts) - x0
    h = max(p[1] for p in edge_pts) - y0
    js = []
    for ref in ("J1", "J2", "J3"):
        px, py, rot, pw, ph = js_raw[ref]
        ew, eh = (ph, pw) if rot % 180 == 90 else (pw, ph)
        js.append(SomJ(ref=ref, pcb_x=px, pcb_y=py, rot=rot,
                       x=round(w - (px - x0), 3),       # mirror (bottom view)
                       y=round(py - y0, 3),
                       w=round(ew, 3), h=round(eh, 3)))
    return SomGeom(w=round(w, 3), h=round(h, 3), js=tuple(js),
                   source=str(pcb.relative_to(REPO_ROOT)))


# ---- part footprint areas --------------------------------------------------------

_DIMS_IN_NAME = re.compile(r"_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm")
_METRIC = re.compile(r"_(\d{2})(\d{2})Metric")
# nominal body+lead spans for name-only footprints (JEDEC class, mm)
_FIXED_DIMS = {
    "TSOT-23-6": (2.9, 2.8),
    "SOT-23-5": (2.9, 2.8),
    "SOT-23": (2.9, 2.4),
    "D_SMA": (4.3, 2.6),
    "D_SMB": (5.4, 3.6),
    "TestPoint_Pad_D1.5mm": (1.5, 1.5),
    "MountingHole_3.2mm_M3_Pad": (6.4, 6.4),   # M3 plated pad OD (lib has no parts/ folder)
}
_DEFAULT_DIMS = (1.6, 0.8)      # unspecified passive

_crtyd_cache: dict[str, tuple[float, float] | None] = {}


def _courtyard_dims(lib: str) -> tuple[float, float] | None:
    """F.CrtYd bbox of parts/<lib>/<lib>.kicad_mod (pads as fallback)."""
    if lib in _crtyd_cache:
        return _crtyd_cache[lib]
    mod = PARTS_DIR / lib / f"{lib}.kicad_mod"
    dims = None
    if mod.exists():
        text = mod.read_text()
        xs: list[float] = []
        ys: list[float] = []
        for m in re.finditer(
                r"\(fp_(?:line|rect|poly|circle|arc)\b(.*?)"
                r"\(layer \"F\.CrtYd\"\)", text, re.S):
            for c in re.finditer(
                    r"\((?:start|end|mid|xy|center) (-?\d+(?:\.\d+)?) "
                    r"(-?\d+(?:\.\d+)?)\)", m.group(1)):
                xs.append(float(c.group(1)))
                ys.append(float(c.group(2)))
        if not xs:
            for m in re.finditer(
                    r"\(pad [^\n]*\n\s*\(at (-?\d+(?:\.\d+)?) "
                    r"(-?\d+(?:\.\d+)?)", text):
                xs.append(float(m.group(1)))
                ys.append(float(m.group(2)))
        if xs:
            dims = (round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2))
    _crtyd_cache[lib] = dims
    return dims


def part_dims(footprint: str) -> tuple[float, float]:
    lib, _, name = footprint.partition(":")
    if lib:
        d = _courtyard_dims(lib)
        if d:
            return d
    for key in sorted(_FIXED_DIMS, key=len, reverse=True):
        if key in name:
            return _FIXED_DIMS[key]
    m = _DIMS_IN_NAME.search(name)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = _METRIC.search(name)
    if m:
        return (int(m.group(1)) / 10.0, int(m.group(2)) / 10.0)
    return _DEFAULT_DIMS


def sheet_area(c, factor: float) -> float:
    """Component area estimate: big parts (connectors, magnetics, headers)
    count at raw courtyard area; small parts get the routing factor."""
    total = 0.0
    for part in c.parts.values():
        w, h = part_dims(part.footprint)
        a = w * h
        total += a if a >= BIG_PART_MM2 else a * factor
    return total


# ---- edge-connector classification ------------------------------------------------
# Which connector FAMILIES mate off-board horizontally (a cable/plug/card
# enters across the board edge) — the mating direction is a property of the
# part, the membership of a sheet is read from its netlist.
_EDGE_FAMILIES: dict[str, str] = {
    "TYPE-C-31-M-12": "USB-C receptacle",
    "HDMI-019S": "HDMI receptacle",
    "AFC07-S40FCA-00": "FFC 40-pin 0.5mm (LCD)",
    "SFW15R-1STE1LF": "FFC 15-pin 1mm (camera)",
    "TF-01A": "microSD push-pull",
    "DS1024-2x6R2": "PMOD 2x6 socket",
    "ASP-134603-01": "FMC LPC (VITA 57.1)",
}
# author-declared expect= deferrals that name a future EDGE connector
_DEFERRED_EDGE = re.compile(r"\b(rj45|usb_uart)_connector\b")

# j1/j2/j3 tokens inside expect= strings ("som_j3_connector",
# "som_j2/j3 bank-33 spare"): underscore is a \w char, so \b alone misses
# the som_jN forms — bound by not-alphanumeric instead.
_J_IN_EXPECT = re.compile(r"(?<![A-Za-z0-9])j([123])(?![A-Za-z0-9])",
                          re.IGNORECASE)


# ---- model -----------------------------------------------------------------------

@dataclass
class Block:
    name: str                    # sheet name
    kind: str                    # "edge" | "interior"
    x: float = 0.0               # top-left, board frame (mm)
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    edge: str = ""               # N/E/S/W for edge blocks
    conns: list[tuple[str, str, float, float]] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)   # deferred connectors
    n_parts: int = 0
    area: float = 0.0            # block area target (mm^2)
    j_aff: dict[str, int] = field(default_factory=dict)
    zone: str = ""               # N/E/S/W zone for interior blocks
    notes: list[int] = field(default_factory=list)

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _r5(v: float) -> float:
    return round(round(v * 2) / 2, 1)


def _j_affinity(sheets, link_result) -> dict[str, dict[str, int]]:
    """sheet -> {J1: n, ...} from bound targets AND deferred expects."""
    aff: dict[str, dict[str, int]] = {sc.name: {} for sc in sheets}
    for b in link_result.bindings:
        d = aff.setdefault(b.sheet, {})
        if b.status == "deferred" and b.ptype.expect:
            for m in _J_IN_EXPECT.finditer(b.ptype.expect):
                jn = f"J{m.group(1)}"
                d[jn] = d.get(jn, 0) + 1
            continue
        for t in b.targets:
            jn = None
            if t.startswith("sheet som_j"):
                jn = "J" + t.split()[1][len("som_j"):].split(":")[0]
            elif t.startswith("SoM ") and "(J" in t:
                jn = t.split("(", 1)[1][:2]
            if jn in ("J1", "J2", "J3"):
                d[jn] = d.get(jn, 0) + 1
    return aff


def _dominant_j(aff: dict[str, int]) -> str | None:
    if not aff:
        return None
    return sorted(aff.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _j_edge_map(som: SomGeom) -> dict[str, str]:
    """Which board edge each mezzanine connector faces (nearest SoM edge in
    the carrier-top view) — derived from the extracted positions."""
    out: dict[str, str] = {}
    for j in som.js:
        cands = [(j.y, "N"), (som.h - j.y, "S"),
                 (j.x, "W"), (som.w - j.x, "E")]
        out[j.ref] = min(cands)[1]
    return out


# ---- layout ----------------------------------------------------------------------

class Plan:
    def __init__(self, som: SomGeom):
        self.som = som
        self.som_x = _r5((BOARD_W - som.w) / 2)
        self.som_y = _r5((BOARD_H - som.h) / 2)
        self.edge_blocks: list[Block] = []
        self.interior_blocks: list[Block] = []
        self.factor = ROUTE_FACTOR
        self.spilled: list[str] = []      # edge blocks moved off their edge

    @property
    def blocks(self) -> list[Block]:
        return self.edge_blocks + self.interior_blocks


def _edge_block_dims(b: Block) -> tuple[float, float]:
    conn_w = sum(c[2] for c in b.conns) + 2.0 * max(0, len(b.conns) - 1)
    conn_d = max((c[3] for c in b.conns), default=0.0)
    if b.conns:
        w = _r5(conn_w + 2 * CONN_SIDE_MARGIN)
    else:                          # reservation-only block (deferred conn)
        w = _r5(max(12.0, b.area / EDGE_DEPTH_CAP))
    d = _r5(min(EDGE_DEPTH_CAP, max(conn_d + 3.0, b.area / w)))
    return w, d


def _pack_edges(plan: Plan, edge_of: dict[str, str]) -> None:
    """Place edge blocks flush on their edge; overflow spills to the next
    edge in a fixed cycle (recorded honestly in plan.spilled)."""
    spill_next = {"W": "S", "S": "N", "N": "E", "E": "W"}
    pending: dict[str, list[Block]] = {"N": [], "E": [], "S": [], "W": []}
    for b in plan.edge_blocks:
        pending[edge_of[b.name]].append(b)

    placed: dict[str, list[Block]] = {"N": [], "E": [], "S": [], "W": []}
    for _round in range(4):
        for edge in ("W", "S", "N", "E"):
            cap = (BOARD_H if edge in "WE" else BOARD_W) - 2 * EDGE_MARGIN
            used = sum(bb.w + CLEAR for bb in placed[edge])
            queue = sorted(pending[edge], key=lambda bb: (-bb.w, bb.name))
            pending[edge] = []
            for b in queue:
                if used + b.w <= cap:
                    placed[edge].append(b)
                    used += b.w + CLEAR
                else:
                    nxt = spill_next[edge]
                    pending[nxt].append(b)
                    plan.spilled.append(
                        f"{b.name}: {edge} edge full -> {nxt}")
    for edge in ("N", "E", "S", "W"):
        blocks = sorted(placed[edge], key=lambda bb: bb.name)
        total = sum(bb.w for bb in blocks) + CLEAR * (len(blocks) - 1)
        span = (BOARD_H if edge in "WE" else BOARD_W)
        gap = max(CLEAR, (span - 2 * EDGE_MARGIN - total)
                  / (len(blocks) + 1) if blocks else 0)
        pos = EDGE_MARGIN + gap
        for b in blocks:
            b.edge = edge
            w, d = b.w, b.h
            if edge == "N":
                b.x, b.y = _r5(pos), 0.0
            elif edge == "S":
                b.x, b.y = _r5(pos), _r5(BOARD_H - d)
            elif edge == "W":
                b.x, b.y = 0.0, _r5(pos)
                b.w, b.h = d, w            # rotate: depth into board is x
            else:
                b.x, b.y = _r5(BOARD_W - d), _r5(pos)
                b.w, b.h = d, w
            pos += w + gap


class _Occupancy:
    """2mm-lattice occupancy for first-fit-nearest-anchor placement."""
    STEP = 2.0

    def __init__(self) -> None:
        self.rects: list[tuple[float, float, float, float]] = []

    def add(self, x: float, y: float, w: float, h: float) -> None:
        self.rects.append((x, y, w, h))

    def fits(self, x: float, y: float, w: float, h: float) -> bool:
        if x < CLEAR or y < CLEAR or x + w > BOARD_W - CLEAR \
                or y + h > BOARD_H - CLEAR:
            return False
        for rx, ry, rw, rh in self.rects:
            if not (x + w + CLEAR <= rx or rx + rw + CLEAR <= x
                    or y + h + CLEAR <= ry or ry + rh + CLEAR <= y):
                return False
        return True

    def place_near(self, ax: float, ay: float, w: float,
                   h: float) -> tuple[float, float, float, float] | None:
        """Deterministic: scan lattice positions sorted by city-block
        distance of the block CENTER from the anchor; first fit wins
        (either orientation)."""
        s = self.STEP
        cands = []
        nx = int(BOARD_W / s) + 1
        ny = int(BOARD_H / s) + 1
        for ix in range(nx):
            for iy in range(ny):
                x, y = ix * s, iy * s
                d = abs(x + w / 2 - ax) + abs(y + h / 2 - ay)
                cands.append((round(d, 1), x, y))
        cands.sort()
        for _d, x, y in cands:
            if self.fits(x, y, w, h):
                return x, y, w, h
            if h != w and self.fits(x, y, h, w):
                return x, y, h, w
        return None


def _interior_dims(area: float) -> tuple[float, float]:
    h = _r5(min(30.0, max(8.0, (area / 1.6) ** 0.5)))
    w = _r5(max(8.0, area / h))
    return w, h


def _zone_anchor(plan: Plan, zone: str) -> tuple[float, float]:
    sx, sy = plan.som_x, plan.som_y
    sw, sh = plan.som.w, plan.som.h
    return {
        "N": ((sx + sw / 2), sy / 2),
        "S": ((sx + sw / 2), (sy + sh + BOARD_H) / 2),
        "W": (sx / 2, sy + sh / 2),
        "E": ((sx + sw + BOARD_W) / 2, BOARD_H / 2),
    }[zone]


def build_plan(sheets, link_result, regs) -> Plan:
    som = extract_som()
    plan = Plan(som)
    aff = _j_affinity(sheets, link_result)
    j_edge = _j_edge_map(som)
    reg_sheets = {r.sheet for r in regs}
    by_name = {sc.name: sc for sc in sheets}

    edge_of: dict[str, str] = {}
    interior: list[Block] = []
    for sc in sorted(sheets, key=lambda s: s.name):
        if sc.name.startswith("som_j"):
            continue            # the mezzanine receptacles ARE the SoM block
        c = sc.circuit
        conns = []
        for ref, part in sorted(c.parts.items()):
            fam = next((f for f in _EDGE_FAMILIES if part.value == f), None)
            if fam:
                w, h = part_dims(part.footprint)
                conns.append((ref, part.value, w, h))
        reserved = sorted({m.group(0)
                           for n, pt in sorted(c.port_types.items())
                           if pt.expect
                           for m in _DEFERRED_EDGE.finditer(pt.expect)})
        b = Block(name=sc.name, kind="edge" if (conns or reserved)
                  else "interior",
                  conns=conns, reserved=reserved,
                  n_parts=len(c.parts), j_aff=aff.get(sc.name, {}))
        if b.kind == "edge":
            dom = _dominant_j(b.j_aff)
            edge_of[b.name] = j_edge.get(dom or "", "N")
            plan.edge_blocks.append(b)
        else:
            interior.append(b)

    # interior zones: the regulator/bringup/power cluster keeps to the
    # SoM-free side (no mezzanine connector faces E in the mirrored view);
    # everything else follows its dominant J edge, with an EXCLUSIVE
    # port-sharing pull toward an edge sheet (usb_pd follows the pd_input
    # inlet via the CC nets — nets shared by exactly those two sheets).
    port_sheets: dict[str, set[str]] = {}
    from schgen.model import NetClass
    for sc in sheets:
        if sc.name.startswith("som_j"):
            continue        # the mezzanine carries almost every port
        for net in sc.circuit.nets.values():
            if net.net_class == NetClass.PORT:
                port_sheets.setdefault(net.name, set()).add(sc.name)
    for b in interior:
        dom = _dominant_j(b.j_aff)
        if b.name in reg_sheets or b.name.startswith(("bringup", "power")):
            b.zone = "E"
            continue
        b.zone = j_edge[dom] if dom else "E"
        best, best_n = None, 0
        for eb in plan.edge_blocks:
            n = sum(1 for net, ss in port_sheets.items()
                    if ss == {b.name, eb.name})     # exclusive pair nets
            if n > best_n:
                best, best_n = eb, n
        if best_n >= 2 and best is not None:
            b.zone = f"@{best.name}"     # anchor at that edge block

    # size + pack, shrinking the small-part routing factor until it fits
    factor = ROUTE_FACTOR
    for _try in range(12):
        ok = _attempt_pack(plan, sheets, interior, edge_of, factor)
        if ok:
            plan.factor = round(factor, 2)
            plan.interior_blocks = interior
            return plan
        factor *= 0.85
    raise RuntimeError("floorplan: could not fit all blocks on the "
                       f"{BOARD_W:g}x{BOARD_H:g} suggestion outline")


def _attempt_pack(plan: Plan, sheets, interior: list[Block],
                  edge_of: dict[str, str], factor: float) -> bool:
    by_name = {sc.name: sc for sc in sheets}
    plan.spilled = []
    for b in plan.edge_blocks:
        b.area = round(sheet_area(by_name[b.name].circuit, factor), 1)
        b.w, b.h = _edge_block_dims(b)
    _pack_edges(plan, edge_of)

    occ = _Occupancy()
    occ.add(plan.som_x, plan.som_y, plan.som.w, plan.som.h)
    for b in plan.edge_blocks:
        occ.add(b.x, b.y, b.w, b.h)

    edge_pos = {b.name: b for b in plan.edge_blocks}
    order = sorted(interior, key=lambda b: (-sheet_area(
        by_name[b.name].circuit, factor), b.name))
    for b in order:
        b.area = round(sheet_area(by_name[b.name].circuit, factor), 1)
        b.w, b.h = _interior_dims(b.area)
        if b.zone.startswith("@") and b.zone[1:] in edge_pos:
            eb = edge_pos[b.zone[1:]]
            ax, ay = eb.cx, eb.cy
        else:
            ax, ay = _zone_anchor(
                plan, b.zone if b.zone in ("N", "E", "S", "W") else "E")
        pos = occ.place_near(ax, ay, b.w, b.h)
        if pos is None:
            return False
        b.x, b.y, b.w, b.h = pos
        occ.add(b.x, b.y, b.w, b.h)
    return True


# ---- notes ------------------------------------------------------------------------

@dataclass(frozen=True)
class Note:
    n: int
    block: str       # sheet name ("" = board-level, MD only)
    short: str       # SVG legend line
    long: str        # MD bullet


def _has_value(c, prefix: str) -> bool:
    return any(p.value.startswith(prefix) for p in c.parts.values())


def _pair_count(c, kind: str) -> int:
    return sum(1 for pt in c.port_types.values() if pt.kind == kind) // 2


def build_notes(plan: Plan, sheets, regs) -> list[Note]:
    from schgen.powertree import rail_volts
    by_name = {sc.name: sc.circuit for sc in sheets}
    notes: list[Note] = []

    def add(block: str, short: str, long: str = "") -> None:
        notes.append(Note(len(notes) + 1, block, short, long or short))

    edge_order = {"N": 0, "W": 1, "E": 2, "S": 3}
    ordered = sorted(plan.edge_blocks,
                     key=lambda b: (edge_order[b.edge], b.x, b.y)) \
        + sorted(plan.interior_blocks, key=lambda b: b.name)
    for b in ordered:
        c = by_name[b.name]
        nets = set(c.nets)
        kinds = {pt.kind for pt in c.port_types.values()}
        conn_vals = {v for _r, v, _w, _h in b.conns}
        if "TYPE-C-31-M-12" in conn_vals and "+VIN" in nets:
            efuse = _has_value(c, "TPS2594")
            add(b.name,
                "power inlet: VBUS->TVS->bulk->+VIN; CC pair to FUSB302",
                "PD power inlet: keep the VBUS path (receptacle -> "
                + ("eFuse soft-start -> " if efuse else "")
                + "TVS -> bulk -> +VIN) in one corner so the +VIN plane "
                "spreads from a single point; CC1/CC2 route to the FUSB302 "
                "(usb_pd block, anchored next to this inlet)."
                + ("" if efuse else " PLAN.md round 5: a TPS25940-class "
                   "eFuse lands between receptacle and bulk — reserve "
                   "space for it here."))
        elif "TYPE-C-31-M-12" in conn_vals:
            esd = next((p.value for p in c.parts.values()
                        if p.value.startswith(("USBLC", "TPD"))), "")
            add(b.name,
                "USB-C OTG: 90R HS pair short + matched; ESD at conn",
                "USB-C OTG: the 90R D+/D- pair wants the shortest matched "
                "run to its SoM pins; "
                + (f"{esd} ESD array within ~10 mm of the receptacle; "
                   if esd else "")
                + "VBUS source switch beside the connector.")
        if "HDMI-019S" in conn_vals:
            np = _pair_count(c, "tmds_pair")
            shifter = next((p.value for p in c.parts.values()
                            if p.value.startswith(("TPD12S", "M24C"))),
                           "the companion IC")
            add(b.name,
                f"{np} TMDS pairs 100R; companion IC at connector",
                f"{np} TMDS pairs at 100R differential, intra-pair skew "
                f"<= 0.15 mm (constraints.py); place {shifter} directly "
                "behind the receptacle so all pairs pass straight "
                "through.")
        if b.name in ("ethernet",) or _has_value(c, "HX5008"):
            add(b.name,
                "magnetics keep-out: no planes line-side; 100R MDI",
                "Magnetics isolation: void ALL planes under the HX5008 "
                "line side + Bob-Smith network (CHASSIS_GND moat to the "
                "RJ45); MDI pairs are 100R differential. RJ45 itself is "
                "an author-declared deferral (expect rj45_connector) — "
                "the dashed reservation is its landing zone.")
        if "TF-01A" in conn_vals:
            add(b.name,
                "SDIO 1.8V island: TXS02612 splits 1.8V / 3.3V sides",
                "microSD: SDIO runs at 1.8 V on the SoM side (typed "
                "sd_bus level in the netlist) — keep the TXS02612 "
                "translator mid-block: 1.8V side faces the SoM, 3.3V card "
                "side faces the slot; bus length match <= 2.5 mm to CLK.")
        if "AFC07-S40FCA-00" in conn_vals:
            boost = next((p.value for p in c.parts.values()
                          if p.value.startswith("SY7201")), "")
            add(b.name,
                "LCD FFC exit; backlight boost loop tight",
                "40-pin LCD FFC: cable exits over the board edge; "
                + (f"keep the {boost} backlight boost loop (L/D/C) tight "
                   "and away from the FFC signal rows; " if boost else "")
                + "RGB888 bus is single-ended bank-34 3V3 — bus-route "
                "together.")
        if "SFW15R-1STE1LF" in conn_vals:
            np = _pair_count(c, "diff_pair")
            add(b.name,
                f"camera FFC: {np} CSI-2 pairs 100R to J3 side",
                f"RPi camera FFC: {np} MIPI CSI-2 pairs at 100R "
                "differential to the J3 side of the SoM (bank 35, 2.5 V "
                "VCCO per the expect= notes) — keep the run to the J3 "
                "strip short.")
        if "DS1024-2x6R2" in conn_vals:
            add(b.name,
                "PMOD pair on gated +3V3_PMOD rail",
                "Two PMOD sockets side by side; both fed from the gated "
                "+3V3_PMOD rail (SY6280 cell in bringup_modules) — route "
                "the gated rail once, star at the sockets.")
        if "ASP-134603-01" in conn_vals:
            ldo = next((r for r in regs if r.sheet == b.name), None)
            extra = ""
            if ldo is not None:
                vi = rail_volts(ldo.vin) or 0.0
                vo = rail_volts(ldo.vout) or 0.0
                extra = (f" {ldo.value} VADJ LDO dissipates ~"
                         f"{(vi - vo) * ldo.i_out:.2f} W at the declared "
                         f"{ldo.i_out:g} A — give it copper.")
            add(b.name,
                "FMC: VITA 57.1 mezzanine overhang; VADJ LDO copper",
                "FMC LPC: a VITA 57.1 mezzanine overhangs the board edge "
                "— keep tall parts out of the overhang strip behind the "
                "connector." + extra)
        if "usb_uart_connector" in b.reserved:
            add(b.name,
                "USB-UART conn deferred; TPs on TX/RX",
                "CP2102N UART bridge: its USB connector is an "
                "author-declared deferral (expect usb_uart_connector) — "
                "the block reserves edge space for it; TX/RX test points "
                "stay probe-able.")
        if b.name == "power":
            bucks = [r for r in regs if r.sheet == b.name
                     and r.kind == "buck"]
            diss = []
            for r in bucks:
                vo = rail_volts(r.vout) or 0.0
                diss.append(f"{r.value} {r.vout} ~"
                            f"{(1 / r.eff - 1) * vo * r.i_out:.2f} W")
            add(b.name,
                "2 bucks: thermal copper + vias; keep SW loops tight",
                "Buck thermal (worst-case declared draws): "
                + "; ".join(diss)
                + ". Pour copper on the SW/PGND side, stitch vias under "
                "the packages, keep each SW node loop minimal.")
        if b.name == "bringup_modules":
            gated = sorted(r.vout for r in regs if r.sheet == b.name)
            add(b.name,
                f"{len(gated)} load switches: gated-rail star points",
                f"{len(gated)} SY6280 load-switch cells; each gated rail "
                "(" + ", ".join(gated) + ") stars from its switch — place "
                "this block centrally so every gated rail leaves toward "
                "its module without crossing the others.")
        if b.name == "bringup_rails":
            add(b.name,
                "rail-EN DIPs + PG LEDs: human access",
                "Rail-enable DIP switches + power-good LEDs: face them "
                "where fingers and eyes reach them with the mezzanine "
                "mounted — keep clear of the SoM shadow.")
        if b.name == "power_mon":
            add(b.name,
                "INA3221 shunts sit IN the rail path",
                "Power monitor: the shunt resistors are in series with "
                "the rails — the rails must physically route through this "
                "block; place it between the regulators and the loads, "
                "Kelvin-connect the sense pairs.")
        if b.name == "debug_boot":
            add(b.name,
                "JTAG/SWD headers vertical: probe clearance",
                "JTAG (2x7 2 mm) + SWD (2x5 1.27 mm) headers mate "
                "vertically — any top-side spot works; keep cable/probe "
                "clearance and the boot DIP reachable.")
        if b.name == "usb_pd":
            add(b.name,
                "FUSB302 beside inlet: short CC stubs",
                "FUSB302 PD controller: anchored beside the pd_input "
                "receptacle so CC1/CC2 stay short stubs; I2C runs to the "
                "SoM J1 side.")
        if b.name == "user_io":
            add(b.name,
                "LEDs + buttons human-facing",
                "User LEDs + buttons: human-facing — keep at the "
                "accessible S side, clear of the PMOD cable shadow.")
    # board-level (MD-only) notes
    n_tp = sum(1 for sc in sheets for r in sc.circuit.parts
               if r.startswith("TP"))
    notes.append(Note(0, "",
                      f"{n_tp} test points board-wide",
                      f"{n_tp} test points board-wide (test-point gate): "
                      "spread them with probe clearance as the blocks "
                      "settle; none may end up under the SoM."))
    return notes


# ---- SVG --------------------------------------------------------------------------

OX, OY = 46.0, 64.0


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _px(x: float) -> float:
    return round(OX + x * SCALE, 1)


def _py(y: float) -> float:
    return round(OY + y * SCALE, 1)


def render_svg(plan: Plan, notes: list[Note], out: Path) -> Path:
    note_of: dict[str, list[int]] = {}
    for nt in notes:
        if nt.block:
            note_of.setdefault(nt.block, []).append(nt.n)
    legend = [nt for nt in notes if nt.n]

    W = int(OX + BOARD_W * SCALE + 30 + 400)
    H = int(max(OY + BOARD_H * SCALE + 56, 130 + len(legend) * 22 + 20))
    e: list[str] = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {W} {H}" font-family="{FONT}" font-size="11">')
    e.append('<defs><pattern id="keepout" width="6" height="6" '
             'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="6" stroke="#dc2626" '
             'stroke-width="1.2"/></pattern></defs>')
    e.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    e.append(f'<text x="{OX}" y="26" font-size="16" font-weight="bold">'
             f'carrier floorplan — SUGGESTION, not constraint</text>')
    e.append(f'<text x="{OX}" y="44" fill="#6b7280">to scale; derived from '
             f'the netlists + {_esc(plan.som.source)} — regenerate with '
             f'`schgen floorplan`; the user owns the outline (PLAN.md '
             f'round 2)</text>')

    # board outline (suggested -> dashed) + 10 mm grid
    bx, by = _px(0), _py(0)
    bw, bh = BOARD_W * SCALE, BOARD_H * SCALE
    e.append(f'<rect x="{bx}" y="{by}" width="{bw:g}" height="{bh:g}" '
             f'fill="#fcfcfd" stroke="#111827" stroke-width="2" '
             f'stroke-dasharray="9,5"/>')
    for gx in range(10, int(BOARD_W), 10):
        e.append(f'<line x1="{_px(gx)}" y1="{by}" x2="{_px(gx)}" '
                 f'y2="{_py(BOARD_H)}" stroke="#eceef1" stroke-width="1"/>')
        e.append(f'<text x="{_px(gx)}" y="{by - 4}" fill="#9ca3af" '
                 f'font-size="8" text-anchor="middle">{gx}</text>')
    for gy in range(10, int(BOARD_H), 10):
        e.append(f'<line x1="{bx}" y1="{_py(gy)}" x2="{_px(BOARD_W)}" '
                 f'y2="{_py(gy)}" stroke="#eceef1" stroke-width="1"/>')
        e.append(f'<text x="{bx - 6}" y="{_py(gy) + 3}" fill="#9ca3af" '
                 f'font-size="8" text-anchor="end">{gy}</text>')
    e.append(f'<text x="{bx}" y="{_py(BOARD_H) + 16}" fill="#6b7280">'
             f'suggested outline {BOARD_W:g} x {BOARD_H:g} mm '
             f'(PLAN: connector-driven ~120x100 class)</text>')

    # blocks under the SoM so the SoM reads on top
    for b in sorted(plan.blocks, key=lambda b: b.name):
        x, y = _px(b.x), _py(b.y)
        w, h = b.w * SCALE, b.h * SCALE
        if b.kind == "edge":
            fill, stroke = "#eff6ff", "#1e3a8a"
        elif b.name.startswith(("power", "bringup")):
            fill, stroke = "#ecfdf5", "#047857"
        else:
            fill, stroke = "#f9fafb", "#374151"
        dash = ' stroke-dasharray="5,4"' if (b.reserved and not b.conns) \
            else ""
        e.append(f'<rect x="{x}" y="{y}" width="{w:g}" height="{h:g}" '
                 f'rx="3" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.4"{dash}/>')
        # physical connector strips, flush at the block's board edge,
        # equal gaps between multiple connectors (to scale)
        n_c = len(b.conns)
        run = sum(c[2] for c in b.conns)
        for k, (_ref, val, cw, cd) in enumerate(b.conns):
            if b.edge in ("N", "S", ""):
                gap = (b.w - run) / (n_c + 1)
                cx0 = b.x + gap * (k + 1) + sum(c[2] for c in b.conns[:k])
                cw_, ch_ = cw, cd
                cy0 = b.y + b.h - cd if b.edge == "S" else b.y
            else:
                gap = (b.h - run) / (n_c + 1)
                cy0 = b.y + gap * (k + 1) + sum(c[2] for c in b.conns[:k])
                cw_, ch_ = cd, cw
                cx0 = b.x if b.edge == "W" else b.x + b.w - cd
            e.append(f'<rect x="{_px(cx0)}" y="{_py(cy0)}" '
                     f'width="{cw_ * SCALE:g}" height="{ch_ * SCALE:g}" '
                     f'fill="#bfdbfe" stroke="#1e3a8a" '
                     f'stroke-width="1.2"/>')
        if b.name == "ethernet":      # magnetics line-side keep-out wash,
            kx, ky, kw, kh = x, y, w, h / 2      # on the connector side
            if b.edge == "S":
                ky = y + h / 2
            elif b.edge == "E":
                kx, kw, kh = x + w / 2, w / 2, h
            elif b.edge == "W":
                kw, kh = w / 2, h
            e.append(f'<rect x="{kx:g}" y="{ky:g}" width="{kw:g}" '
                     f'height="{kh:g}" fill="url(#keepout)" '
                     f'opacity="0.5"/>')
        # label (rotated on W/E edges), part count below
        cx, cy = _px(b.cx), _py(b.cy)
        if b.edge in ("W", "E") and h > w:      # vertical: two columns
            fs = min(11.0, max(7.0, (h - 6) / (0.62 * max(1, len(b.name)))))
            e.append(f'<text x="{cx - 3:g}" y="{cy}" text-anchor="middle" '
                     f'font-size="{fs:.1f}" font-weight="bold" '
                     f'transform="rotate(-90 {cx - 3:g} {cy})">'
                     f'{_esc(b.name)}</text>')
            e.append(f'<text x="{cx + 8:g}" y="{cy}" text-anchor="middle" '
                     f'font-size="7.5" fill="#6b7280" '
                     f'transform="rotate(-90 {cx + 8:g} {cy})">'
                     f'{b.n_parts}p</text>')
        else:
            fs = min(11.0, max(7.0, (w - 6) / (0.62 * max(1, len(b.name)))))
            e.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" '
                     f'font-size="{fs:.1f}" font-weight="bold">'
                     f'{_esc(b.name)}</text>')
            e.append(f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" '
                     f'font-size="7.5" fill="#6b7280">{b.n_parts}p</text>')
        for k, nn in enumerate(note_of.get(b.name, [])):
            bcx, bcy = x + 16 * k, y      # on the block's top-left corner
            e.append(f'<circle cx="{bcx:g}" cy="{bcy:g}" r="7" '
                     f'fill="white" stroke="#111827" stroke-width="1.2"/>')
            e.append(f'<text x="{bcx:g}" y="{bcy + 3:g}" '
                     f'text-anchor="middle" font-size="9" '
                     f'font-weight="bold">{nn}</text>')

    # SoM on top
    sx, sy = _px(plan.som_x), _py(plan.som_y)
    sw, sh = plan.som.w * SCALE, plan.som.h * SCALE
    e.append(f'<rect x="{sx}" y="{sy}" width="{sw:g}" height="{sh:g}" '
             f'rx="8" fill="#fef3c7" stroke="#92400e" stroke-width="2" '
             f'opacity="0.95"/>')
    e.append(f'<text x="{sx + sw / 2:g}" y="{sy + sh / 2 - 6:g}" '
             f'text-anchor="middle" font-size="13" font-weight="bold" '
             f'fill="#92400e">Zynq SoM {plan.som.w:g} x {plan.som.h:g}</text>')
    e.append(f'<text x="{sx + sw / 2:g}" y="{sy + sh / 2 + 10:g}" '
             f'text-anchor="middle" font-size="8.5" fill="#92400e">'
             f'(bottom view: DF40 positions mirrored from the SoM PCB)'
             f'</text>')
    for j in plan.som.js:
        jx = _px(plan.som_x + j.x - j.w / 2)
        jy = _py(plan.som_y + j.y - j.h / 2)
        e.append(f'<rect x="{jx}" y="{jy}" width="{j.w * SCALE:g}" '
                 f'height="{j.h * SCALE:g}" fill="#92400e"/>')
        lx = _px(plan.som_x + j.x)
        ly = _py(plan.som_y + j.y)
        rot = (f' transform="rotate(-90 {lx} {ly + 3.5:g})"'
               if j.w < j.h else "")        # vertical strip: rotated label
        e.append(f'<text x="{lx}" y="{ly + 3.5:g}" text-anchor="middle" '
                 f'font-size="10" font-weight="bold" fill="white"{rot}>'
                 f'{j.ref}</text>')

    # scale bar
    sb_y = _py(BOARD_H) + 30
    e.append(f'<line x1="{bx}" y1="{sb_y}" x2="{_px(20)}" y2="{sb_y}" '
             f'stroke="#111827" stroke-width="3"/>')
    e.append(f'<text x="{_px(10)}" y="{sb_y + 14}" text-anchor="middle" '
             f'fill="#6b7280">20 mm</text>')

    # legend
    lx = OX + BOARD_W * SCALE + 30
    e.append(f'<text x="{lx:g}" y="{OY + 4:g}" font-size="13" '
             f'font-weight="bold">placement notes (derived)</text>')
    for i, nt in enumerate(legend):
        yy = OY + 26 + i * 22
        e.append(f'<circle cx="{lx + 8:g}" cy="{yy - 4:g}" r="8" '
                 f'fill="white" stroke="#111827" stroke-width="1.2"/>')
        e.append(f'<text x="{lx + 8:g}" y="{yy - 1:g}" text-anchor="middle"'
                 f' font-size="9" font-weight="bold">{nt.n}</text>')
        e.append(f'<text x="{lx + 24:g}" y="{yy:g}">'
                 f'{_esc(nt.short)}</text>')
    foot = OY + 26 + len(legend) * 22 + 12
    e.append(f'<text x="{lx:g}" y="{foot:g}" fill="#6b7280" font-size="10">'
             f'block area = courtyards (big parts raw, small x'
             f'{plan.factor:g}) — see FLOORPLAN.md</text>')
    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


# ---- markdown ---------------------------------------------------------------------

def render_md(plan: Plan, notes: list[Note], sheets, regs,
              out: Path) -> Path:
    from schgen import constraints as cst
    from schgen.powertree import rail_volts

    note_of: dict[str, list[int]] = {}
    for nt in notes:
        if nt.block:
            note_of.setdefault(nt.block, []).append(nt.n)

    L: list[str] = []
    L.append("# Carrier floorplan — SUGGESTION, not constraint")
    L.append("")
    L.append("Generated by `schgen floorplan` (also by `schgen board`). "
             "**The user owns the outline and the placement** — PLAN.md "
             "round 2 leaves the form factor free (\"connector-driven "
             "~120x100 class expected\"). This document is one "
             "self-consistent, to-scale starting point whose every number "
             "is derived from the design data, so each suggestion can be "
             "kept or overruled deliberately. Shuffle blocks freely; the "
             "WHY notes say what each move costs.")
    L.append("")
    L.append("![floorplan](FLOORPLAN.svg)")
    L.append("")
    L.append("## Sources (everything derived, nothing invented)")
    L.append("")
    L.append(f"- SoM outline + DF40 positions: `{plan.som.source}` "
             "(Edge.Cuts bbox + J1/J2/J3 footprints, parsed live)")
    L.append("- block sizes: per-part courtyards (`parts/<MPN>/"
             "<MPN>.kicad_mod` F.CrtYd; KiCad-standard footprints from "
             "the dims in their names), big parts raw + small parts x"
             f"{plan.factor:g} routing factor")
    L.append("- edge pinning + zones: connector parts in each sheet "
             "netlist + linker J1/J2/J3 bindings (incl. `expect=` "
             "deferrals)")
    L.append("- electrical notes: `schgen/constraints.py` "
             "(JLC04161H-7628), `schgen/powertree.py` analysis, typed "
             "ports (1.8V SDIO)")
    L.append("")
    L.append("## Extracted SoM geometry")
    L.append("")
    L.append(f"SoM outline: **{plan.som.w:g} x {plan.som.h:g} mm**. The "
             "DF40 mezzanine connectors sit on the SoM's bottom copper; "
             "the carrier-top view below mirrors their X coordinate "
             "(bottom view). Verify mate orientation against the DF40 "
             "datasheet before committing footprints.")
    L.append("")
    L.append("| conn | SoM PCB `(at)` | carrier-top view (SoM-rel) | "
             "pad extent |")
    L.append("|---|---|---|---|")
    for j in plan.som.js:
        L.append(f"| {j.ref} | ({j.pcb_x:g}, {j.pcb_y:g}) rot {j.rot:g} | "
                 f"({j.x:g}, {j.y:g}) | {j.w:g} x {j.h:g} mm |")
    L.append("")
    L.append(f"Suggested board: **{BOARD_W:g} x {BOARD_H:g} mm**; SoM "
             f"origin at **({plan.som_x:g}, {plan.som_y:g})** "
             "(centered). All coordinates below are board-frame mm, "
             "origin top-left, +y down (KiCad convention).")
    L.append("")
    L.append("## Edge connectors (pinned to edges by their mating "
             "direction)")
    L.append("")
    L.append("| edge | sheet | block (x, y, w x h) | connector(s) | "
             "notes |")
    L.append("|---|---|---|---|---|")
    edge_order = {"N": 0, "W": 1, "E": 2, "S": 3}
    for b in sorted(plan.edge_blocks,
                    key=lambda b: (edge_order[b.edge], b.x, b.y)):
        conns = ", ".join(f"{v} ({_EDGE_FAMILIES.get(v, '?')})"
                          for _r, v, _w, _h in b.conns)
        if b.reserved:
            conns = (conns + "; " if conns else "") + ", ".join(
                f"RESERVED: {r} (deferred)" for r in b.reserved)
        nn = " ".join(f"({k})" for k in note_of.get(b.name, []))
        L.append(f"| {b.edge} | {b.name} | ({b.x:g}, {b.y:g}, "
                 f"{b.w:g} x {b.h:g}) | {conns} | {nn} |")
    if plan.spilled:
        L.append("")
        L.append("Edge spills (preferred edge full — honest, not "
                 "hidden):")
        for s in plan.spilled:
            L.append(f"- {s}")
    L.append("")
    L.append("## Interior blocks (zone = dominant SoM connector side, "
             "or the power cluster)")
    L.append("")
    L.append("| sheet | anchor | block (x, y, w x h) | parts | est mm2 | "
             "notes |")
    L.append("|---|---|---|---|---|---|")
    for b in sorted(plan.interior_blocks, key=lambda b: b.name):
        nn = " ".join(f"({k})" for k in note_of.get(b.name, []))
        L.append(f"| {b.name} | {b.zone} | ({b.x:g}, {b.y:g}, {b.w:g} x "
                 f"{b.h:g}) | {b.n_parts} | {b.area:g} | {nn} |")
    L.append("")
    L.append("## Routing constraint classes (JLC04161H-7628 — from "
             "constraints.py)")
    L.append("")
    classes: dict[str, dict] = {}
    for sc in sorted(sheets, key=lambda s: s.name):
        for name, pt in sorted(sc.circuit.port_types.items()):
            if pt.kind == "single":
                continue
            ncls = cst._net_class(pt.kind, pt.impedance, pt.level_v)
            d = classes.setdefault(ncls, {"nets": set(), "kind": pt.kind,
                                          "imp": pt.impedance})
            d["nets"].add(name)
    L.append("| class | nets | geometry (track/gap mm) | match budget |")
    L.append("|---|---|---|---|")
    for ncls, d in sorted(classes.items()):
        geo = cst.GEOMETRY.get(d["imp"]) if d["imp"] else None
        gtxt = (f"{geo.width_mm:g} / {geo.gap_mm:g}" if geo else "-")
        if d["kind"] in cst.INTRA_PAIR_SKEW_MM:
            match = (f"intra-pair <= "
                     f"{cst.INTRA_PAIR_SKEW_MM[d['kind']]:g} mm")
            if d["kind"] == "tmds_pair":
                match += "; inter-pair <= 5 mm (policy)"
        elif d["kind"] == "sd_bus":
            match = f"bus to CLK <= {cst.SD_BUS_MATCH_MM:g} mm"
        else:
            match = "-"
        L.append(f"| {ncls} | {len(d['nets'])} | {gtxt} | {match} |")
    L.append("")
    L.append("Full per-net table: "
             "`carrier/manufacturing/layout_constraints.csv` (+ the "
             "`.kicad_dru` rules).")
    L.append("")
    L.append("## Power and thermal (worst-case declared draws — "
             "powertree analysis)")
    L.append("")
    L.append("| regulator | sheet | rail | I out (A) | est dissipation |")
    L.append("|---|---|---|---|---|")
    for r in regs:
        vo = rail_volts(r.vout) or 0.0
        vi = rail_volts(r.vin) or 0.0
        if r.kind == "buck":
            p = (1 / r.eff - 1) * vo * r.i_out
        elif r.kind == "ldo":
            p = max(0.0, vi - vo) * r.i_out
        else:
            p = 0.0
        ptxt = f"~{p:.2f} W" if p >= 0.05 else "negligible"
        L.append(f"| {r.value} ({r.ref}) | {r.sheet} | {r.vin} -> "
                 f"{r.vout} | {r.i_out:.3f} | {ptxt} |")
    L.append("")
    L.append("Numbers are the power-tree gate's worst-case declared "
             "draws (`carrier/reports/power_tree.txt`); regulators above "
             "~0.3 W want copper pours + stitching vias.")
    L.append("")
    L.append("## Placement notes (the WHYs)")
    L.append("")
    for nt in notes:
        tag = f"**({nt.n}) {nt.block}**" if nt.n else "**(board)**"
        L.append(f"- {tag}: {nt.long}")
    L.append("")
    L.append("## Honest limits")
    L.append("")
    L.append("- Block rectangles are AREA estimates (courtyards + "
             "routing factor), not layouts; their order along an edge "
             "is alphabetical, not optimized — shuffle freely.")
    L.append("- The outline is the PLAN's ~120x100 class, drawn dashed "
             "in the SVG because the user owns it.")
    L.append("- The mirror convention (bottom view) must be checked "
             "against the DF40 mating datasheet before any footprint is "
             "placed.")
    L.append("- som_j1/j2/j3 sheets are not blocks: they ARE the three "
             "DF40 strips drawn inside the SoM footprint.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out


# ---- entry points -----------------------------------------------------------------

def generate(sheets=None, link_result=None) -> list[Path]:
    from schgen import powertree
    from schgen.link import (all_subsystem_paths, link, load_som_contract,
                             load_subsystem)
    if sheets is None:
        sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    if link_result is None:
        link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = build_plan(sheets, link_result, regs)
    notes = build_notes(plan, sheets, regs)
    svg = render_svg(plan, notes, OUT_SVG)
    md = render_md(plan, notes, sheets, regs, OUT_MD)
    return [svg, md]


def cmd_floorplan(args: argparse.Namespace) -> int:
    paths = generate()
    for p in paths:
        print(f"floorplan: {p.relative_to(REPO_ROOT)}")
    print("FLOORPLAN: suggestion written (derived from netlists — "
          "see the honest-limits section)")
    return 0
