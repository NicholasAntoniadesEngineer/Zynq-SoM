"""Emit a .kicad_sch from placed geometry. Every coordinate written verbatim.

The emitter is intentionally dumb: placement/routing decide everything; this
file just serialises. The only logic is symbol-definition embedding (copying
the library s-expr into ``lib_symbols`` with the full lib_id name) and uuid
generation. No transforms, no fallbacks, no repairs.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from schgen import sexpr
from schgen.model import Circuit
from schgen.sexpr import Sym
from schgen.symbols import Library

PAPER_DEFAULT = "A4"


@dataclass
class PlacedPart:
    ref: str
    lib_id: str
    value: str
    x: float
    y: float
    rotation: int = 0
    footprint: str = ""
    # property text positions (page coords) + rotation; None = hide
    ref_pos: tuple[float, float, int] | None = None
    val_pos: tuple[float, float, int] | None = None


@dataclass
class PlacedPower:
    """A power/GND symbol instance; net name == value (KiCad derives the
    global net from the Value field). ``net`` overrides for PWR_FLAG, whose
    value is not a net name. ``show_value`` renders the rail name text at
    ``val_pos`` (page coords) — placement owns that position like any text."""
    lib_id: str          # power:GND / power:+3V3 …
    value: str           # GND / +3V3 …
    ref: str             # #PWR01 …
    x: float
    y: float
    rotation: int = 0
    net: str = ""                                    # default: value
    val_pos: tuple[float, float, int] | None = None
    show_value: bool = False

    @property
    def net_name(self) -> str:
        return self.net or self.value


@dataclass
class Wire:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Junction:
    x: float
    y: float


@dataclass
class HierLabel:
    """A PORT-net label. Emitted as a GLOBAL label when the design is built
    standalone (a hier label on a root sheet is an ERC error — no parent to
    bind to; a once-only global label is explicitly ignored by ERC). Hierarchy
    assembly later flips ``PlacedDesign.standalone`` and gets true hier labels."""
    name: str
    x: float
    y: float
    rotation: int = 0          # 0 text-right, 180 text-left …
    shape: str = "bidirectional"


@dataclass
class LocalLabel:
    """A sheet-local net-name label placed ON a drawn wire. It never replaces
    wiring (the net is fully drawn); it gives an internal SIGNAL net its name —
    required because kicad-cli's netlist export omits unnamed nets, which would
    blind the netlist gate to a purely-drawn net."""
    name: str
    x: float
    y: float
    rotation: int = 0


@dataclass
class NoConnect:
    x: float
    y: float


@dataclass
class PlacedDesign:
    circuit: Circuit
    parts: list[PlacedPart] = field(default_factory=list)
    powers: list[PlacedPower] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    hlabels: list[HierLabel] = field(default_factory=list)
    llabels: list[LocalLabel] = field(default_factory=list)
    no_connects: list[NoConnect] = field(default_factory=list)
    paper: str = PAPER_DEFAULT
    standalone: bool = True   # True: PORT labels emit as global_label


def _u() -> str:
    return str(uuid.uuid4())


def _effects(size: float = 1.27, hide: bool = False, justify: str | None = None):
    e: list = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify"), *[Sym(t) for t in justify.split()]])
    if hide:
        e.append([Sym("hide"), Sym("yes")])
    return e


def _prop(name: str, value: str, x: float, y: float, rot: int = 0,
          hide: bool = False) -> list:
    return [Sym("property"), name, value,
            [Sym("at"), x, y, rot],
            _effects(hide=hide)]


def _embed_symbol(lib: Library, lib_id: str) -> list:
    block = copy.deepcopy(lib.get(lib_id).raw)
    block[1] = lib_id            # "R" -> "Device:R"
    return block


def emit(design: PlacedDesign, out_path: Path, lib: Library) -> Path:
    c = design.circuit
    # The root sheet uuid MUST also be the symbol-instance path ("/<uuid>"):
    # with a bare "/" KiCad cannot resolve instance references, and every net
    # whose name would be pad-derived (no label, no power symbol) silently
    # drops out of ERC and the exported netlist.
    root_uuid = _u()
    doc: list = [Sym("kicad_sch"),
                 [Sym("version"), 20250114],
                 [Sym("generator"), "schgen"],
                 [Sym("generator_version"), "1.0"],
                 [Sym("uuid"), root_uuid],
                 [Sym("paper"), design.paper]]

    lib_ids = sorted({p.lib_id for p in design.parts}
                     | {p.lib_id for p in design.powers})
    doc.append([Sym("lib_symbols"), *[_embed_symbol(lib, lid) for lid in lib_ids]])

    for w in design.wires:
        doc.append([Sym("wire"),
                    [Sym("pts"), [Sym("xy"), w.x0, w.y0], [Sym("xy"), w.x1, w.y1]],
                    [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                    [Sym("uuid"), _u()]])
    for j in design.junctions:
        doc.append([Sym("junction"), [Sym("at"), j.x, j.y],
                    [Sym("diameter"), 0], [Sym("color"), 0, 0, 0, 0],
                    [Sym("uuid"), _u()]])
    for nc in design.no_connects:
        doc.append([Sym("no_connect"), [Sym("at"), nc.x, nc.y], [Sym("uuid"), _u()]])
    for h in design.hlabels:
        just = "right" if h.rotation in (180, 270) else "left"
        tag = "global_label" if design.standalone else "hierarchical_label"
        doc.append([Sym(tag), h.name,
                    [Sym("shape"), Sym(h.shape)],
                    [Sym("at"), h.x, h.y, h.rotation],
                    _effects(justify=just),
                    [Sym("uuid"), _u()]])
    for ll in design.llabels:
        just = "right bottom" if ll.rotation == 180 else "left bottom"
        doc.append([Sym("label"), ll.name,
                    [Sym("at"), ll.x, ll.y, ll.rotation],
                    _effects(justify=just),
                    [Sym("uuid"), _u()]])

    def _sym_instance(ref: str, lib_id: str, value: str, x: float, y: float,
                      rot: int, footprint: str,
                      ref_pos: tuple[float, float, int] | None,
                      val_pos: tuple[float, float, int] | None,
                      hide_ref: bool, hide_val: bool) -> list:
        sdef = lib.get(lib_id)
        node: list = [Sym("symbol"),
                      [Sym("lib_id"), lib_id],
                      [Sym("at"), x, y, rot],
                      [Sym("unit"), 1],
                      [Sym("exclude_from_sim"), Sym("no")],
                      [Sym("in_bom"), Sym("yes")],
                      [Sym("on_board"), Sym("yes")],
                      [Sym("dnp"), Sym("no")],
                      [Sym("uuid"), _u()]]
        rp = ref_pos or (x, y - 2.54, 0)
        vp = val_pos or (x, y + 2.54, 0)
        node.append(_prop("Reference", ref, rp[0], rp[1], rp[2], hide=hide_ref))
        node.append(_prop("Value", value, vp[0], vp[1], vp[2], hide=hide_val))
        node.append(_prop("Footprint", footprint, x, y, 0, hide=True))
        node.append(_prop("Datasheet", "", x, y, 0, hide=True))
        for p in sdef.pins:
            node.append([Sym("pin"), p.number, [Sym("uuid"), _u()]])
        node.append([Sym("instances"),
                     [Sym("project"), c.name,
                      [Sym("path"), f"/{root_uuid}",
                       [Sym("reference"), ref], [Sym("unit"), 1]]]])
        return node

    for p in design.parts:
        doc.append(_sym_instance(p.ref, p.lib_id, p.value, p.x, p.y, p.rotation,
                                 p.footprint, p.ref_pos, p.val_pos, False, False))
    for pw in design.powers:
        doc.append(_sym_instance(pw.ref, pw.lib_id, pw.value, pw.x, pw.y,
                                 pw.rotation, "", None, pw.val_pos,
                                 True, not pw.show_value))

    doc.append([Sym("sheet_instances"),
                [Sym("path"), "/", [Sym("page"), "1"]]])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sexpr.dumps(doc) + "\n")
    return out_path
