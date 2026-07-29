"""ORDER-OF-ASSEMBLY doc + renders — the staged build sequence, from the data.

``schgen board`` (via the PCB step) writes ``<project>/manufacturing/ASSEMBLY.md``
plus one PNG per stage under ``<project>/renders/assembly/``. Two ORTHOGONAL
partitions of the placed parts (every non-fiducial part appears in EXACTLY ONE
of each — asserted):

A. INCREMENTAL BRING-UP PHASES (primary): hand-assembly by SECTION in
   dependency order, derived from the netlists — power-entry sheets (the
   off-board connector sourcing the root rail of the module's supply chain, +
   every sheet touching that root), then the rail chain ordered by regulator
   depth (``powertree.analyze`` vin->vout edges, shunt bridges merged), then
   the module interface (the sheets placed wholly inside the SoM keepout),
   then the SoM MODULE MATE as its own solder-free phase, then the remaining
   sections topologically ordered by produced->consumed rail edges (ties
   alphabetical), mounting hardware last. Rail phases carry a CHECKPOINT line
   only where a test point actually lands on a produced rail; the mate phase
   checks boot/debug against the debug_boot interface. Nothing is invented.

B. PRODUCTION PROCESS STEPS: (1) bottom SMD paste+reflow, (2) top SMD,
   (3) through-hole non-connector parts short-to-tall (courtyard area is the
   stated height proxy — no measured part heights exist in-tree), (4)
   connectors + mechanical hardware. The joint class is derived from the
   footprint pad types (majority thru_hole = THT), so an SMD part whose
   footprint carries EP stitch vias or locating pegs stays SMD.

Fiducials are bare-copper marks — no part to fit — and are excluded from both
partitions (stated in the doc header). DETERMINISM: fixed palettes, natural
ref sort, no timestamps — two builds are byte-identical (doc and PNGs).
Advisory: emitted every build, gated by tests, never a board verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import IS_DEFAULT_PROJECT, PROJECT_ROOT
from schgen.generate import pcb as pcb_mod
from schgen.generate.pcb import PcbModel, _inst_courtyard
from schgen.generate.pcb.constants import (
    _CONN_DESC,
    _INT_DESC,
    _SW_DESC,
    CONN_MATING_FACE,
    FIDUCIAL_FOOTPRINT,
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
)
from schgen.generate.pcb.footprint import _footprint_bbox
from schgen.generate.pcb.mating_face import _mating_face_out_dir

CARRIER = PROJECT_ROOT
ASSEMBLY_MD = CARRIER / "manufacturing" / "ASSEMBLY.md"
PNG_DIR = CARRIER / "renders" / "assembly"

SCALE = 5.0
PAD = 28.0

_GREY_TOP = (60, 66, 78)
_GREY_BOT = (40, 44, 54)
_HILITE = (70, 160, 255)
_BOT_EDGE = (255, 230, 120)

_PAD_TYPE_RE = re.compile(r'\(pad\s+"[^"]*"\s+(\w+)')
_REF_RE = re.compile(r"([A-Za-z]+)(\d+)")
_DIR_NAME = {(0, -1): "N", (0, 1): "S", (1, 0): "E", (-1, 0): "W"}

_joint_cache: dict[str, str] = {}


def _joint(mod_path: Path) -> str:
    """"tht" iff thru_hole pads OUTNUMBER smd pads: the TPS26631 EP stitch vias
    and the USB-C shell posts are thru_hole pads on reflow parts, so any-thru
    would misclassify them — majority is the honest joint class."""
    key = str(mod_path)
    if key not in _joint_cache:
        smd = thru = 0
        for typ in _PAD_TYPE_RE.findall(mod_path.read_text()):
            if typ == "smd":
                smd += 1
            elif typ == "thru_hole":
                thru += 1
        _joint_cache[key] = "tht" if thru > smd else "smd"
    return _joint_cache[key]


def _is_fiducial(inst: FootprintInst) -> bool:
    return inst.footprint == FIDUCIAL_FOOTPRINT


def _is_mech(inst: FootprintInst) -> bool:
    return "MountingHole" in inst.footprint


def _is_connector(inst: FootprintInst) -> bool:
    return inst.ref[:1] == "J"


def _natkey(ref: str) -> tuple[str, int]:
    m = _REF_RE.fullmatch(ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def _ikey(inst: FootprintInst) -> tuple[str, int]:
    return _natkey(inst.ref)


def _area(inst: FootprintInst) -> float:
    x0, y0, x1, y1 = _footprint_bbox(inst.mod_path)
    return round((x1 - x0) * (y1 - y0), 3)


def assembly_insts(model: PcbModel) -> list[FootprintInst]:
    """Every placed part that is actually FITTED — fiducials (bare-copper
    registration marks) are the sole exclusion, stated in the doc header."""
    return [i for i in model.insts if not _is_fiducial(i)]



@dataclass(frozen=True)
class Step:
    n: int
    slug: str
    title: str
    insts: tuple[FootprintInst, ...]
    notes: tuple[str, ...] = ()


def _assert_partition(parts: list[FootprintInst],
                      groups: list[tuple[FootprintInst, ...]],
                      kind: str) -> None:
    seen: dict[str, int] = {}
    for gi, gg in enumerate(groups):
        for i in gg:
            if i.ref in seen:
                raise ValueError(
                    f"{kind} partition: {i.ref} appears in {kind}s "
                    f"{seen[i.ref] + 1} and {gi + 1}")
            seen[i.ref] = gi
    missing = sorted((i.ref for i in parts if i.ref not in seen),
                     key=_natkey)
    if missing or len(seen) != len(parts):
        raise ValueError(
            f"{kind} partition: {len(seen)} assigned != {len(parts)} parts; "
            f"missing {missing[:8]}")


def _polarity_notes(insts: tuple[FootprintInst, ...]) -> tuple[str, ...]:
    d = sorted((i.ref for i in insts if i.ref[:1] == "D"), key=_natkey)
    u = sorted((i.ref for i in insts if i.ref[:1] in ("U", "Q")), key=_natkey)
    cp = sorted((i.ref for i in insts if ":CP_" in i.footprint), key=_natkey)
    out: list[str] = []
    if d:
        refs = ", ".join(d) if len(d) <= 8 else f"{len(d)} parts, D refs"
        out.append(f"diode polarity ({refs}): cathode per silkscreen")
    if cp:
        out.append(f"electrolytic polarity ({', '.join(cp)}): "
                   f"positive mark per silkscreen")
    if u:
        refs = ", ".join(u) if len(u) <= 8 else f"{len(u)} parts, U/Q refs"
        out.append(f"pin-1 orientation ({refs}): dot per silkscreen")
    return tuple(out)


def _conn_desc(inst: FootprintInst) -> str:
    """Sheet-keyed descriptors travel across projects; the REF-keyed tables
    (_INT_DESC/_SW_DESC) are authored for the default project and a foreign
    project reuses their refs — so ref lookups apply there ONLY."""
    if IS_DEFAULT_PROJECT and inst.ref in _INT_DESC:
        return _INT_DESC[inst.ref]
    return _CONN_DESC.get(inst.sheet, "")


def _connector_notes(insts: tuple[FootprintInst, ...],
                     som_refs: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    for i in sorted(insts, key=_ikey):
        face = CONN_MATING_FACE.get(i.mod_path.stem)
        if face is None:
            continue
        edge = _DIR_NAME[_mating_face_out_dir(face, i.rotation)]
        desc = _conn_desc(i)
        label = f" ({desc})" if desc else ""
        out.append(f"{i.ref} {i.value}{label}: mating face toward the "
                   f"{edge} board edge")
    xt = sorted((i for i in insts if i.mod_path.stem == "XT60PW-M"), key=_ikey)
    if len(xt) == 2:
        a, b = xt
        out.append(f"XT60 pair: {a.ref} ({_conn_desc(a)}) / "
                   f"{b.ref} ({_conn_desc(b)}) — IN/OUT per silkscreen label")
    if som_refs:
        out.append(f"{', '.join(som_refs)}: DF40C SoM receptacles — the SoM "
                   f"module mates onto them (bring-up section, mate phase)")
    return tuple(out)


def process_steps(model: PcbModel) -> list[Step]:
    """The 4-step PCBA process partition. Assignment order: connector/mech
    class first (a THT header is a connector, not a step-3 part), then joint
    class, then side."""
    parts = assembly_insts(model)
    b_smd: list[FootprintInst] = []
    t_smd: list[FootprintInst] = []
    tht: list[FootprintInst] = []
    conn: list[FootprintInst] = []
    for i in parts:
        if _is_connector(i) or _is_mech(i):
            conn.append(i)
        elif _joint(i.mod_path) == "tht":
            tht.append(i)
        elif i.side == "bottom":
            b_smd.append(i)
        else:
            t_smd.append(i)
    som_refs = sorted((i.ref for i in conn if i.sheet.startswith("som_j")),
                      key=_natkey)
    steps = [
        Step(1, "bottom_smd", "Bottom-side SMD (paste + reflow)",
             tuple(sorted(b_smd, key=_ikey)),
             _polarity_notes(tuple(b_smd))),
        Step(2, "top_smd", "Top-side SMD (paste + reflow)",
             tuple(sorted(t_smd, key=_ikey)),
             _polarity_notes(tuple(t_smd))),
        Step(3, "tht", "Through-hole (short-to-tall)",
             tuple(sorted(tht, key=lambda i: (_area(i), _ikey(i)))),
             _polarity_notes(tuple(tht))),
        Step(4, "connectors_mech", "Connectors + mechanical hardware",
             tuple(sorted(conn, key=_ikey)),
             _connector_notes(tuple(conn), som_refs)),
    ]
    _assert_partition(parts, [s.insts for s in steps], "step")
    return steps



@dataclass(frozen=True)
class Phase:
    n: int
    slug: str
    title: str
    sheets: tuple[str, ...]
    insts: tuple[FootprintInst, ...]
    checkpoints: tuple[str, ...] = ()
    lead: str = ""


def _sheet_power_nets(model: PcbModel) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for i in model.insts:
        rails = {n for _num, n in i.pad_nets.values()
                 if model.netclass_of.get(n) == "POWER"}
        out.setdefault(i.sheet, set()).update(rails)
    return out


def _conn_root_rails(model: PcbModel, produced: set[str]) -> dict[str, set[str]]:
    """sheet -> POWER rails entering ON an off-board connector's pads that no
    regulator produces: the board's true supply entries (+VBUS_IN on the PD
    inlet, +5V_DBG on the debug USB-C)."""
    out: dict[str, set[str]] = {}
    for i in model.insts:
        if i.mod_path.stem not in CONN_MATING_FACE:
            continue
        rails = {n for _num, n in i.pad_nets.values()
                 if model.netclass_of.get(n) == "POWER" and n not in produced}
        if rails:
            out.setdefault(i.sheet, set()).update(rails)
    return out


def _tp_by_net(model: PcbModel) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in sorted(model.insts, key=_ikey):
        if not i.ref.startswith("TP"):
            continue
        for _num, n in sorted(i.pad_nets.values()):
            if n and n not in out:
                out[n] = i.ref
    return out


class _Rails:
    """Bridge-merged rail groups + regulator depth from the supply roots."""

    def __init__(self, pt) -> None:
        self.parent: dict[str, str] = {}
        for _s, _r, a, b in pt.bridges:
            self._union(a, b)
        self.producers: dict[str, list] = {}
        for r in pt.regs:
            self.producers.setdefault(self._find(r.vout), []).append(r)
        self.depth: dict[str, int] = {}
        groups = {self._find(x) for r in pt.regs for x in (r.vin, r.vout)}
        for g in sorted(groups):
            if g not in self.producers:
                self.depth[g] = 0
        for _ in range(len(groups) + 1):
            for r in pt.regs:
                gi, go = self._find(r.vin), self._find(r.vout)
                if gi in self.depth:
                    d = self.depth[gi] + 1
                    if self.depth.get(go, 1 << 30) > d:
                        self.depth[go] = d

    def _find(self, r: str) -> str:
        while self.parent.get(r, r) != r:
            r = self.parent[r]
        return r

    def _union(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo

    def group(self, rail: str) -> str:
        return self._find(rail)

    def members(self, rail: str, universe: set[str]) -> list[str]:
        g = self._find(rail)
        return sorted(x for x in universe if self._find(x) == g)

    def rail_depth(self, rail: str) -> int:
        return self.depth.get(self._find(rail), 0)


def _upstream_closure(rails: _Rails, som_rails: set[str]) -> set[str]:
    todo = sorted({rails.group(r) for r in som_rails})
    closed: set[str] = set()
    while todo:
        g = todo.pop()
        if g in closed:
            continue
        closed.add(g)
        for r in rails.producers.get(g, []):
            gi = rails.group(r.vin)
            if gi not in closed:
                todo.append(gi)
    return closed


def _checkpoint_lines(rail_set: set[str], rails: _Rails, tp_of: dict[str, str],
                      universe: set[str]) -> tuple[str, ...]:
    expanded: set[str] = set()
    for r in sorted(rail_set):
        expanded.update(rails.members(r, universe | {r}))
    hits = [(rails.rail_depth(r), r, tp_of[r])
            for r in sorted(expanded) if r in tp_of]
    return tuple(f"verify {r} at {tp}" for _d, r, tp in sorted(hits))


def bringup_phases(model: PcbModel, sheets) -> list[Phase]:
    """The section-by-section hand-assembly order (module docstring, part A),
    every ordering decision read off the netlists/placement — no name lists."""
    from schgen.verify import powertree
    pt = powertree.analyze(sheets)
    rails = _Rails(pt)
    parts = assembly_insts(model)
    by_sheet: dict[str, list[FootprintInst]] = {}
    for i in parts:
        by_sheet.setdefault(i.sheet, []).append(i)
    touched = _sheet_power_nets(model)
    universe = {n for n, c in model.netclass_of.items() if c == "POWER"}
    produced_on: dict[str, set[str]] = {}
    for r in pt.regs:
        produced_on.setdefault(r.sheet, set()).add(r.vout)
    all_produced = {r.vout for r in pt.regs}
    conn_roots = _conn_root_rails(model, all_produced)
    tp_of = _tp_by_net(model)

    kx0, ky0, kx1, ky1 = model.som_keepout or (0.0, 0.0, 0.0, 0.0)

    def _inside(i: FootprintInst) -> bool:
        x0, y0, x1, y1 = _inst_courtyard(i)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return kx0 <= cx <= kx1 and ky0 <= cy <= ky1

    module_sheets = sorted(
        s for s, ii in by_sheet.items()
        if model.som_keepout and all(_inside(i) for i in ii))
    som_rails = set()
    for s in module_sheets:
        som_rails |= touched.get(s, set())
    closure = _upstream_closure(rails, som_rails)
    root_groups = {g for g in closure if g not in rails.producers}
    conn_groups = {rails.group(r) for rr in conn_roots.values() for r in rr}
    entry_roots = root_groups & conn_groups
    entry_sheets = sorted(
        s for s, tt in touched.items()
        if s not in module_sheets
        and any(rails.group(r) in entry_roots for r in tt))

    chain: list[tuple[float, str]] = []
    for s in sorted(by_sheet):
        if s in module_sheets or s in entry_sheets:
            continue
        ranks = [rails.rail_depth(v) for v in produced_on.get(s, ())
                 if rails.group(v) in closure]
        ranks += [rails.rail_depth(a) + 0.5
                  for _sh, _r, a, _b in pt.bridges
                  if _sh == s and rails.group(a) in closure]
        if ranks:
            chain.append((min(ranks), s))
    chain_sheets = [s for _rk, s in sorted(chain)]

    mech_sheets = sorted(
        s for s, ii in by_sheet.items()
        if s not in module_sheets and s not in entry_sheets
        and s not in chain_sheets and all(_is_mech(i) for i in ii))

    rest = sorted(s for s in by_sheet
                  if s not in module_sheets and s not in entry_sheets
                  and s not in chain_sheets and s not in mech_sheets)
    prod_of = {s: set(produced_on.get(s, set())) | conn_roots.get(s, set())
               for s in rest}
    rank = dict.fromkeys(rest, 0)
    for _ in range(len(rest)):
        for a in rest:
            for b in rest:
                if a == b or not (prod_of[a] & touched.get(b, set())):
                    continue
                if rank[b] < rank[a] + 1 < len(rest):
                    rank[b] = rank[a] + 1
    rest_sheets = sorted(rest, key=lambda s: (rank[s], s))

    def _phase(n: int, slug: str, title: str, group: list[str],
               checkpoints: tuple[str, ...] = (), lead: str = "") -> Phase:
        ii = sorted((i for s in group for i in by_sheet.get(s, [])), key=_ikey)
        return Phase(n, slug, title, tuple(group), tuple(ii), checkpoints, lead)

    phases: list[Phase] = []

    def _add(slug: str, title: str, group: list[str],
             rail_set: set[str], lead: str = "") -> None:
        cps = _checkpoint_lines(rail_set, rails, tp_of, universe)
        phases.append(_phase(len(phases) + 1, slug, title, group, cps, lead))

    if entry_sheets:
        rail_set: set[str] = set()
        for s in entry_sheets:
            rail_set |= {r for r in touched.get(s, set())
                         if rails.group(r) in entry_roots}
            rail_set |= produced_on.get(s, set())
        _add("power_entry", f"power entry ({', '.join(entry_sheets)})",
             entry_sheets, rail_set)
    for s in chain_sheets:
        _add(s, s, [s], produced_on.get(s, set()))
    if module_sheets:
        _add("som_interface", f"SoM interface ({', '.join(module_sheets)})",
             module_sheets, set())
        som_recs = sorted((i.ref for s in module_sheets
                           for i in by_sheet.get(s, []) if _is_connector(i)),
                          key=_natkey)
        mate_cps: tuple[str, ...] = ()
        if "debug_boot" in by_sheet:
            dbg = []
            for i in sorted(by_sheet["debug_boot"], key=_ikey):
                if i.ref[:1] not in ("J", "S"):
                    continue
                desc = (_INT_DESC.get(i.ref) or _SW_DESC.get(i.ref)
                        if IS_DEFAULT_PROJECT else None)
                dbg.append(f"{i.ref} ({desc})" if desc else i.ref)
            mate_cps = (f"boot/debug via debug_boot: {', '.join(dbg)}",)
        phases.append(Phase(
            len(phases) + 1, "som_mate", "SoM module mate", (), (),
            mate_cps,
            f"No solder parts. Mate the SoM module onto "
            f"{', '.join(som_recs)} after the rail checkpoints above."))
    for s in rest_sheets:
        _add(s, s, [s], produced_on.get(s, set()) | conn_roots.get(s, set()))
    for s in mech_sheets:
        _add(s, f"mechanical hardware ({s})", [s], set())

    _assert_partition(parts, [p.insts for p in phases], "phase")
    return phases



def _table(insts: tuple[FootprintInst, ...], joint_col: bool = False
           ) -> list[str]:
    head = "| ref | value | package | sheet |"
    sep = "|---|---|---|---|"
    if joint_col:
        head = "| ref | value | package | sheet | joint |"
        sep = "|---|---|---|---|---|"
    rows = [head, sep]
    for i in insts:
        pkg = i.footprint.partition(":")[2] or i.footprint
        row = f"| {i.ref} | {i.value} | {pkg} | {i.sheet} |"
        if joint_col:
            row += f" {_joint(i.mod_path).upper()} |"
        rows.append(row)
    return rows

def _side_count(insts: tuple[FootprintInst, ...]) -> str:
    top = sum(1 for i in insts if i.side == "top")
    return f"{len(insts)} parts ({top} top / {len(insts) - top} bottom)"


def _markdown(model: PcbModel, steps: list[Step], phases: list[Phase],
              name: str) -> str:
    parts = assembly_insts(model)
    n_fid = len(model.insts) - len(parts)
    top = sum(1 for i in parts if i.side == "top")
    L = [
        f"# Assembly order — {name}",
        "",
        f"Board {model.board_w:g} x {model.board_h:g} mm. "
        f"{len(parts)} placed parts ({top} top / {len(parts) - top} bottom); "
        f"{n_fid} fiducials are bare-copper marks, excluded from every phase "
        f"and step.",
        "Section A is the staged hand-assembly + bring-up order; section B "
        "is the PCBA process order. Every part appears in exactly one phase "
        "and exactly one step.",
        "",
        "## A. Incremental bring-up order",
        "",
        "| phase | section | parts | checkpoint |",
        "|---|---|---|---|",
    ]
    for p in phases:
        cp = "; ".join(p.checkpoints) if p.checkpoints else "—"
        L.append(f"| {p.n} | {p.title} | {len(p.insts)} | {cp} |")
    L.append("")
    for p in phases:
        L += [f"### Phase {p.n} — {p.title}", ""]
        L.append(f"![phase {p.n}](../renders/assembly/"
                 f"phase_{p.n:02d}_{p.slug}.png)")
        L.append("")
        if p.lead:
            L += [p.lead, ""]
        if p.insts:
            L.append(_side_count(p.insts))
            L.append("")
            L += _table(p.insts)
            L.append("")
        for cp in p.checkpoints:
            L.append(f"CHECKPOINT: {cp}")
        if p.checkpoints:
            L.append("")
    L += ["## B. Production process order", ""]
    for s in steps:
        L += [f"### Step {s.n} — {s.title}", ""]
        L.append(f"![step {s.n}](../renders/assembly/"
                 f"step_{s.n}_{s.slug}.png)")
        L.append("")
        if not s.insts:
            L += ["No parts in this step on this board.", ""]
            continue
        if s.n == 3:
            L.append("Sorted short-to-tall by courtyard area (height proxy — "
                     "no measured part heights in-tree).")
            L.append("")
        L.append(_side_count(s.insts))
        L.append("")
        L += _table(s.insts, joint_col=(s.n == 4))
        L.append("")
        for note in s.notes:
            L.append(f"NOTES: {note}")
        if s.notes:
            L.append("")
    return "\n".join(L) + "\n"



def _png_stage(model: PcbModel, done: list[FootprintInst],
               cur: list[FootprintInst], out: Path, caption: str,
               mate_box: tuple[float, float, float, float] | None = None
               ) -> None:
    from PIL import Image, ImageDraw
    bw, bh = model.board_w, model.board_h
    W = int(bw * SCALE + 2 * PAD)
    H = int(bh * SCALE + 2 * PAD)
    im = Image.new("RGB", (W, H), (15, 17, 21))
    d = ImageDraw.Draw(im, "RGBA")

    def px(x: float) -> float:
        return PAD + (x - ORIGIN_X) * SCALE

    def py(y: float) -> float:
        return PAD + (y - ORIGIN_Y) * SCALE

    d.rectangle([px(ORIGIN_X), py(ORIGIN_Y),
                 px(ORIGIN_X) + bw * SCALE, py(ORIGIN_Y) + bh * SCALE],
                fill=(22, 25, 34), outline=(229, 231, 235), width=2)
    if model.som_keepout:
        k = model.som_keepout
        d.rectangle([px(k[0]), py(k[1]), px(k[2]), py(k[3])],
                    outline=(201, 148, 32), width=1)
    for i in sorted(done, key=_ikey):
        x0, y0, x1, y1 = _inst_courtyard(i)
        fill = _GREY_TOP if i.side == "top" else _GREY_BOT
        d.rectangle([px(x0), py(y0), px(x1), py(y1)], fill=fill,
                    outline=(15, 17, 21), width=1)
    for i in sorted(cur, key=_ikey):
        x0, y0, x1, y1 = _inst_courtyard(i)
        d.rectangle([px(x0), py(y0), px(x1), py(y1)], fill=_HILITE,
                    outline=(15, 17, 21), width=1)
        if i.side == "bottom":
            d.rectangle([px(x0), py(y0), px(x1), py(y1)],
                        outline=_BOT_EDGE, width=2)
    if mate_box is not None:
        d.rectangle([px(mate_box[0]), py(mate_box[1]),
                     px(mate_box[2]), py(mate_box[3])],
                    outline=_HILITE, width=3)
        d.text((px(mate_box[0]) + 4, py(mate_box[1]) + 4), "SoM module",
               fill=(240, 240, 245))
    placed: list[tuple[float, float, float, float]] = []

    def _fits(tb: tuple[float, float, float, float]) -> bool:
        return (tb[0] >= 0 and tb[1] >= 0 and tb[2] <= W and tb[3] <= H
                and all(tb[2] < b[0] or tb[0] > b[2]
                        or tb[3] < b[1] or tb[1] > b[3] for b in placed))

    for i in sorted(cur, key=_ikey):
        x0, y0, _x1, y1 = _inst_courtyard(i)
        for at in ((px(x0), py(y0) - 11), (px(x0), py(y1) + 2)):
            tb = d.textbbox(at, i.ref)
            if _fits(tb):
                d.text(at, i.ref, fill=(240, 240, 245))
                placed.append(tb)
                break
    d.text((8, 6), caption, fill=(203, 213, 225))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG", optimize=True)


def _stage_pngs(model: PcbModel, steps: list[Step], phases: list[Phase],
                out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()
    out: list[Path] = []
    done: list[FootprintInst] = []
    for s in steps:
        p = out_dir / f"step_{s.n}_{s.slug}.png"
        _png_stage(model, done, list(s.insts), p,
                   f"step {s.n}/{len(steps)} - {s.title} "
                   f"({len(s.insts)} parts)")
        done += list(s.insts)
        out.append(p)
    done = []
    for ph in phases:
        p = out_dir / f"phase_{ph.n:02d}_{ph.slug}.png"
        mate = model.som_core if (ph.slug == "som_mate") else None
        _png_stage(model, done, list(ph.insts), p,
                   f"phase {ph.n}/{len(phases)} - {ph.title} "
                   f"({len(ph.insts)} parts)", mate_box=mate)
        done += list(ph.insts)
        out.append(p)
    return out



def generate(model: PcbModel | None = None) -> dict:
    """Build both partitions, write ASSEMBLY.md + the per-stage PNGs. Pure
    consumer of the placed model — reads it, never mutates it."""
    if model is None:
        model = pcb_mod.build_model()
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import spec
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    steps = process_steps(model)
    phases = bringup_phases(model, sheets)
    name = spec().name
    ASSEMBLY_MD.parent.mkdir(parents=True, exist_ok=True)
    ASSEMBLY_MD.write_text(_markdown(model, steps, phases, name))
    pngs = _stage_pngs(model, steps, phases, PNG_DIR)
    return {
        "md": ASSEMBLY_MD, "png_dir": PNG_DIR, "pngs": pngs,
        "n_steps": len(steps), "n_phases": len(phases),
        "n_parts": len(assembly_insts(model)),
    }
