"""Footprint EMBEDDING into the .kicad_pcb (parse the .kicad_mod, set placement
+ pad nets + side flip + content-derived uuids) plus the board-level emit
helpers (layers table, stackup, edge rectangle, SoM body silk + keepout zone).
PURE MOVE out of the old monolithic ``schgen/generate/pcb.py`` — no behaviour
change.
"""

from __future__ import annotations

import math

from schgen.core import fallbacks as _fbk
from schgen.core import sexpr
from schgen.core.sexpr import Sym

from .constants import (
    _FOOTPRINT_ALIASES,
    _FOUR_LAYER,
    _INT_DESC,
    _SW_DESC,
    CLR_HOLE_SAMENET_PAD,
    CONN_MATING_FACE,
    GND_PLANE_CLEARANCE,
    GND_PLANE_EDGE_BACK,
    GND_PLANE_LAYER,
    ISO_VOID_MARGIN,
    ISO_VOID_VALUES,
    ORIGIN_X,
    ORIGIN_Y,
    POUR_CLEARANCE,
    THERMAL_COPPER,
    THERMAL_VIA_CLEAR,
    THERMAL_VIA_DRILL,
    THERMAL_VIA_EDGE,
    THERMAL_VIA_H2H,
    THERMAL_VIA_LATTICE_PITCH,
    THERMAL_VIA_SIZE,
    THERMAL_VIA_SPACING,
    ZONE_MIN_THICKNESS,
    PcbModel,
)


def _flip_layer_token(name: str) -> str:
    """F.<x> -> B.<x> (and vice-versa, idempotent for non-F/B layers)."""
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return name
    return name


def _flip_to_bottom(node: list) -> None:
    """Recursively flip a footprint subtree from the top (F.Cu) to the bottom
    (B.Cu) side: swap every (layer ...)/(layers ...) F.* token to its B.* twin,
    and add (justify mirror) to text effects so the glyphs read correctly from
    the back. Local coordinates are NOT touched, and KiCad applies NO position
    mirror at load or render — a B.Cu footprint's stored coordinates ARE the
    final front-view frame (pcbnew-verified; the whole in-process model shares
    this convention). CONSEQUENCE: the emitted bottom land pattern is the
    CHIRAL MIRROR of the part's top-side pattern, so only mirror-symmetric,
    non-polarized parts may be placed bottom (guarded by
    tests/test_bottom_convention.py). Deterministic and reversible (re-running
    on a B.* tree is a no-op for the layers)."""
    for sub in node:
        if not isinstance(sub, list) or not sub:
            continue
        head = sub[0]
        if head in (Sym("layer"), Sym("layers")):
            for i in range(1, len(sub)):
                if isinstance(sub[i], str):
                    sub[i] = _flip_layer_token(sub[i])
        elif head == Sym("effects"):
            # add (justify mirror) if no justify present; else ensure mirror
            just = next((x for x in sub if isinstance(x, list) and x
                         and x[0] == Sym("justify")), None)
            if just is None:
                sub.append([Sym("justify"), Sym("mirror")])
            elif Sym("mirror") not in just:
                just.append(Sym("mirror"))
            _flip_to_bottom(sub)
        else:
            _flip_to_bottom(sub)


def _embed_footprint(inst, uid) -> list:
    """Parse the .kicad_mod, set its placement + pad nets, return the
    (footprint ...) node for the .kicad_pcb. Every nested uuid is content-
    derived so regeneration is byte-identical."""
    mod = sexpr.loads(inst.mod_path.read_text())
    assert isinstance(mod, list) and mod and mod[0] == Sym("footprint")

    # lib_id (footprint name) -> the full "lib:name". Use the RESOLVED name so
    # an aliased footprint (e.g. C_1206_3225Metric -> _3216Metric) carries the
    # name of the .kicad_mod actually embedded, not the requested one.
    mod[1] = _FOOTPRINT_ALIASES.get(inst.footprint, inst.footprint)

    # placement: (at x y rot) at the top level (after version/generator/layer)
    # remove any existing (at ...) then insert ours right after (layer ...).
    body = [x for x in mod
            if not (isinstance(x, list) and x and x[0] == Sym("at"))]
    at_node = [Sym("at"), inst.x, inst.y] + (
        [inst.rotation] if inst.rotation else [])
    # find insert point: after the first (layer ...) child
    out: list = []
    inserted = False
    for x in body:
        out.append(x)
        if (not inserted and isinstance(x, list) and x and x[0] == Sym("layer")):
            out.append(at_node)
            inserted = True
    if not inserted:
        out.insert(1, at_node)

    # 2-side assembly: a bottom-side footprint flips to B.Cu. The local
    # pad/graphic COORDINATES stay unchanged and only every F.* layer token
    # swaps to its B.* twin, plus a (justify mirror) on text glyphs. KiCad
    # applies NO position mirror on load — the stored frame IS the front-view
    # frame (see _flip_to_bottom). Done before the uuid/net pass so the
    # flipped tree is what gets stamped.
    if inst.side == "bottom":
        _flip_to_bottom(out)

    # stamp a stable top-level uuid, replace placement+pad uuids deterministically
    _set_or_add(out, [Sym("uuid"), uid(f"fp:{inst.ref}")])

    # thermal-via inheritance: a faithful EP-bearing footprint carries blank
    # ("") no-net thermal vias/pads SITTING INSIDE its exposed pad's copper
    # (e.g. the TPS26631 EP + its thermal vias). They are physically the SAME
    # copper as the EP, so they inherit the EP pad's net — that removes the
    # false "no-net via vs GND EP" clearance/mask error without touching the
    # footprint geometry (we only assign nets, exactly like every other pad).
    inherit = _thermal_via_nets(out, inst.pad_nets)

    # set Reference/Value property text + assign pad nets + restamp child uuids
    pad_seq = 0
    prop_seq = 0
    for node in out:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if head == Sym("property") and len(node) > 2:
            if node[1] == "Reference":
                node[2] = inst.ref
                # OFF-BOARD CONNECTORS: hide the J-ref on silk — the human
                # FUNCTION label (_connector_descriptors: PWR/JTAG/HDMI/...) is
                # what the user reads on the board, and the ref clutters the only
                # clear spot beside the connector. The ref stays in the footprint
                # data (netlist/BOM), just not printed.
                # TEST POINTS: same treatment — a TP is identified by the NET it
                # probes (its Value), not its TPxxxx ref; the dense bring-up TP
                # fields otherwise overprint each other (LAW 1). Keyed on the
                # TestPoint footprint, not a 'TP' ref prefix (robust).
                if (inst.value in CONN_MATING_FACE or inst.ref in _INT_DESC
                        or inst.ref in _SW_DESC or "TestPoint" in inst.footprint):
                    hb = next((x for x in node if isinstance(x, list) and x
                               and x[0] == Sym("hide")), None)
                    if hb is None:
                        node.insert(3, [Sym("hide"), Sym("yes")])
                    else:
                        hb[1] = Sym("yes")
            elif node[1] == "Value":
                node[2] = inst.value
            _restamp_uuid(node, uid(f"fp:{inst.ref}:prop:{prop_seq}"))
            prop_seq += 1
        elif head == Sym("pad") and len(node) > 1:
            pad_name = str(node[1])
            num, nname = inst.pad_nets.get(pad_name, (0, ""))
            if (num, nname) == (0, "") and pad_seq in inherit:
                num, nname = inherit[pad_seq]
            _set_pad_net(node, num, nname)
            # propagate the footprint rotation into each pad's LOCAL orientation
            # — KiCad's native representation of a rotated footprint (its own
            # SoM J1/J2/J3 store (at x y <fp-rot>) on every pad). Without this a
            # non-square rect pad authored for the 0-deg frame keeps its 0-deg
            # orientation and KiCad's pad-clearance check sees the rect's long
            # side fall along the pitch axis -> false intra-footprint shorts.
            if inst.rotation:
                _rotate_pad(node, inst.rotation)
            _restamp_uuid(node, uid(f"fp:{inst.ref}:pad:{pad_seq}"))
            pad_seq += 1
        elif head in (Sym("fp_text"), Sym("fp_line"), Sym("fp_rect"),
                      Sym("fp_circle"), Sym("fp_arc"), Sym("fp_poly")):
            _restamp_uuid(node, uid(f"fp:{inst.ref}:gfx:{pad_seq}:{prop_seq}"))
    return out


def _rotate_pad(pad: list, fp_rot: float) -> None:
    """Add ``fp_rot`` to a pad's LOCAL (at x y [rot]) orientation, matching how
    KiCad stores a rotated footprint (every pad carries the footprint rotation
    in its own (at)). The pad's local x/y are NOT changed — KiCad rotates the
    positions by the footprint (at) at load; only the pad's own rect must turn
    so a non-square pad keeps its correct orientation relative to the row."""
    at = next((x for x in pad
               if isinstance(x, list) and x and x[0] == Sym("at")), None)
    if at is None:
        return
    cur = float(at[3]) if len(at) > 3 else 0.0
    new = round((cur + fp_rot) % 360.0, 4)
    if len(at) > 3:
        at[3] = new
    else:
        at.append(new)


def _pad_geom(node: list) -> tuple[float, float, float, float] | None:
    """(cx, cy, half_w, half_h) of a (pad ...) node, in footprint-local mm."""
    at = sexpr.find(node, "at")
    size = sexpr.find(node, "size")
    if not (at and len(at) >= 3 and size and len(size) >= 3):
        return None
    hw, hh = float(size[1]) / 2, float(size[2]) / 2
    rot = int(float(at[3])) % 180 if len(at) > 3 else 0
    if rot == 90:
        hw, hh = hh, hw
    return float(at[1]), float(at[2]), hw, hh


def _thermal_via_nets(out: list, pad_nets: dict) -> dict[int, tuple[int, str]]:
    """pad ORDINAL -> inherited (net number, name) for blank no-net pads whose
    center lies inside a netted pad's copper of the same footprint. Returns
    only the inheritances (empty for the common no-thermal-via case)."""
    pads = [n for n in out if isinstance(n, list) and n and n[0] == Sym("pad")]
    netted: list[tuple[float, float, float, float, int, str]] = []
    for n in pads:
        nm = str(n[1]) if len(n) > 1 else ""
        net = pad_nets.get(nm)
        g = _pad_geom(n)
        if net and net[0] > 0 and g is not None:
            netted.append((*g, net[0], net[1]))
    if not netted:
        return {}
    out_map: dict[int, tuple[int, str]] = {}
    for seq, n in enumerate(pads):
        nm = str(n[1]) if len(n) > 1 else ""
        if pad_nets.get(nm, (0, ""))[0] > 0 or nm not in ("", " "):
            continue                       # only blank, currently-no-net pads
        g = _pad_geom(n)
        if g is None:
            continue
        cx, cy, _hw, _hh = g
        for px, py, phw, phh, num, name in netted:
            if abs(cx - px) <= phw and abs(cy - py) <= phh:
                out_map[seq] = (num, name)
                break
    return out_map


def _set_or_add(node: list, kv: list) -> None:
    tag = kv[0]
    for i, x in enumerate(node):
        if isinstance(x, list) and x and x[0] == tag:
            node[i] = kv
            return
    node.append(kv)


def _restamp_uuid(node: list, new: str) -> None:
    for i, x in enumerate(node):
        if isinstance(x, list) and x and x[0] == Sym("uuid"):
            node[i] = [Sym("uuid"), new]
            return
    node.append([Sym("uuid"), new])


def _set_pad_net(pad: list, num: int, name: str) -> None:
    """Insert/replace the pad's (net N "name"). Drop any stale net first; net 0
    (no net) gets NO net node (KiCad treats the absence as the no-net pad)."""
    pad[:] = [x for x in pad
              if not (isinstance(x, list) and x and x[0] == Sym("net"))]
    if num <= 0:
        return
    # net node must precede (pintype ...)/(uuid ...) but KiCad accepts it
    # anywhere inside the pad; append before the uuid for tidiness.
    net_node = [Sym("net"), num, name]
    for i, x in enumerate(pad):
        if isinstance(x, list) and x and x[0] == Sym("uuid"):
            pad.insert(i, net_node)
            return
    pad.append(net_node)


def _layers_node() -> list:
    node: list = [Sym("layers")]
    for idx, name, ltype, user in _FOUR_LAYER:
        entry = [idx, name, Sym(ltype)]
        if user is not None:
            entry.append(user)
        node.append(entry)
    return node


def _stackup_node() -> list:
    """JLC04161H-7628 1.6 mm 4-layer build. Outer signal layers reference the
    L2 GND plane through one sheet of 7628 prepreg (0.2104 mm, er~4.6) — the
    geometry schgen/generate/constraints.py's diff-pair widths are calculated
    for. L2/L3 core is 1.065 mm; total ~1.6 mm."""
    def cu(name, th):
        return [Sym("layer"), name, [Sym("type"), "copper"],
                [Sym("thickness"), th]]

    def diel(name, dtype, th, er):
        return [Sym("layer"), name, [Sym("type"), dtype],
                [Sym("thickness"), th], [Sym("material"), "FR4"],
                [Sym("epsilon_r"), er], [Sym("loss_tangent"), 0.02]]

    return [Sym("stackup"),
            [Sym("layer"), "F.SilkS", [Sym("type"), "Top Silk Screen"]],
            [Sym("layer"), "F.Paste", [Sym("type"), "Top Solder Paste"]],
            [Sym("layer"), "F.Mask", [Sym("type"), "Top Solder Mask"],
             [Sym("thickness"), 0.01]],
            cu("F.Cu", 0.035),
            diel("dielectric 1", "prepreg", 0.2104, 4.6),
            cu("In1.Cu", 0.0152),
            diel("dielectric 2", "core", 1.065, 4.6),
            cu("In2.Cu", 0.0152),
            diel("dielectric 3", "prepreg", 0.2104, 4.6),
            cu("B.Cu", 0.035),
            [Sym("layer"), "B.Mask", [Sym("type"), "Bottom Solder Mask"],
             [Sym("thickness"), 0.01]],
            [Sym("layer"), "B.Paste", [Sym("type"), "Bottom Solder Paste"]],
            [Sym("layer"), "B.SilkS", [Sym("type"), "Bottom Silk Screen"]],
            [Sym("copper_finish"), "ENIG"],
            [Sym("dielectric_constraints"), Sym("no")]]


def _edge_rect(x0, y0, x1, y1, uid) -> list:
    """Four Edge.Cuts lines forming the board outline rectangle."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    out: list = []
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        out.append([Sym("gr_line"),
                    [Sym("start"), ax, ay], [Sym("end"), bx, by],
                    [Sym("stroke"), [Sym("width"), 0.1],
                     [Sym("type"), Sym("default")]],
                    [Sym("layer"), "Edge.Cuts"],
                    [Sym("uuid"), uid(f"edge:{i}")]])
    return out


def _som_body_silk(box: tuple[float, float, float, float], uid) -> list:
    """Top-silk outline of the SoM module body (the DF40 mezzanine footprint) on
    the carrier, so an assembler sees exactly where the module lands and that its
    shadow is a passives-only keepout (LAW 6). Drawn at the module-body edge — the
    carrier DF40 receptacles + any under-SoM passives sit inboard of it, so the
    line never crosses a pad. A pin-1 corner chamfer + a small corner label give
    orientation. The user explicitly called out that this outline was missing."""
    x0, y0, x1, y1 = box
    out: list = []
    # body rectangle
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        out.append([Sym("gr_line"),
                    [Sym("start"), round(ax, 3), round(ay, 3)],
                    [Sym("end"), round(bx, 3), round(by, 3)],
                    [Sym("stroke"), [Sym("width"), 0.15],
                     [Sym("type"), Sym("default")]],
                    [Sym("layer"), "F.SilkS"],
                    [Sym("uuid"), uid(f"som-silk:{i}")]])
    # pin-1 / orientation chamfer across the top-left corner
    ch = 3.0
    out.append([Sym("gr_line"),
                [Sym("start"), round(x0, 3), round(y0 + ch, 3)],
                [Sym("end"), round(x0 + ch, 3), round(y0, 3)],
                [Sym("stroke"), [Sym("width"), 0.15],
                 [Sym("type"), Sym("default")]],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:ch")]])
    # corner label just OUTSIDE the top-left corner (clear of the module shadow)
    out.append([Sym("gr_text"), "Zynq SoM",
                [Sym("at"), round(x0 + 1.0, 3), round(y0 - 1.2, 3), 0],
                [Sym("layer"), "F.SilkS"],
                [Sym("uuid"), uid("som-silk:label")],
                [Sym("effects"),
                 [Sym("font"), [Sym("size"), 1.4, 1.4], [Sym("thickness"), 0.25]],
                 [Sym("justify"), Sym("left"), Sym("bottom")]]])
    return out


# ---- T2 escape copper emission (RECONCILED with GAP1 @ 28f8e15) -------------------
# The GENERAL via/segment node builders.  Interface decision (flagged for
# Ring-0): T2's dict-driven builders are the general implementation — any
# size/drill/net, optional (locked yes), caller-chosen uid key — so GAP1's
# fixed-size thermal-via emission now routes through _via_node (byte-identical
# output: without "locked" the node shape matches GAP1's original inline
# construction exactly, and the uid key is passed through unchanged).  Zones
# are GAP1's territory (_fill_zone/_gnd_plane_zone/_iso_void_zones below):
# T2 emits NO zone — its stitch vias land on GAP1's canonical In1 GND plane.
# (locked yes) probe-verified on kicad-cli 10.0.2 (T2 P0): parses + DRCs clean.

def _via_node(c: dict, uid, uid_key: str = "stitch-via") -> list:
    """A board-level GND via node.  ``c`` keys: x, y, size, drill, net,
    optional locked (default True — the T2 escape vias are Freerouting
    fixed-preroute; GAP1's thermal vias pass locked=False)."""
    node = [Sym("via"),
            [Sym("at"), c["x"], c["y"]],
            [Sym("size"), c["size"]],
            [Sym("drill"), c["drill"]],
            [Sym("layers"), "F.Cu", "B.Cu"]]
    if c.get("locked", True):
        node.append([Sym("locked"), Sym("yes")])
    node.append([Sym("net"), c["net"]])
    node.append([Sym("uuid"), uid(uid_key)])
    return node


def _segment_node(c: dict, uid) -> list:
    """A locked ladder segment (spine / GND-pad stub / via stub)."""
    return [Sym("segment"),
            [Sym("start"), c["x1"], c["y1"]],
            [Sym("end"), c["x2"], c["y2"]],
            [Sym("width"), c["width"]],
            [Sym("layer"), c["layer"]],
            [Sym("locked"), Sym("yes")],
            [Sym("net"), c["net"]],
            [Sym("uuid"), uid("stitch-seg")]]


def _som_keepout_zone(box: tuple[float, float, float, float], uid) -> list:
    """A rule-area MARKER over the SoM body on both copper layers (drawn in the
    ratsnest view + KiCad as a hatched region). It is PERMISSIVE: under an SMD
    DF40 mezzanine the shadow is the most power-critical region — it must carry
    full GND/PWR planes, the bottom-side rail-entry decoupling (som_decoupling)
    and its fanout vias right beneath the connector. An old restrictive keepout
    (no tracks/vias/pour) would have starved the SoM of power planes and left the
    under-SoM decoupling unroutable (a LAW-0 open). So everything is allowed; the
    zone only LABELS the mezzanine shadow. Drawn as the rectangle's 4 corners."""
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = [Sym("pts")] + [[Sym("xy"), round(px, 3), round(py, 3)]
                          for px, py in corners]
    return [Sym("zone"),
            [Sym("net"), 0], [Sym("net_name"), ""],
            [Sym("layers"), "F.Cu", "B.Cu"],
            [Sym("uuid"), uid("som-keepout")],
            [Sym("name"), "SoM_body_keepout"],
            [Sym("hatch"), Sym("edge"), 0.5],
            [Sym("connect_pads"), [Sym("clearance"), 0]],
            [Sym("min_thickness"), 0.25],
            # PERMISSIVE marker: the SoM shadow is the power-entry region — it
            # carries the GND/PWR planes, the bottom-side rail decoupling and its
            # vias beneath the SMD mezzanine. Everything is allowed; the zone
            # only labels the region (see docstring).
            [Sym("keepout"),
             [Sym("tracks"), Sym("allowed")],
             [Sym("vias"), Sym("allowed")],
             [Sym("pads"), Sym("allowed")],
             [Sym("copperpour"), Sym("allowed")],
             [Sym("footprints"), Sym("allowed")]],
            [Sym("fill"), [Sym("thermal_gap"), 0.5],
             [Sym("thermal_bridge_width"), 0.5]],
            [Sym("polygon"), pts]]


# ---- EMITTED thermal copper: In1 GND plane + per-part via fields + pours ---------
#
# LAW-0 honesty: the thermal gate (schgen/verify/thermal.py) credits a
# pour-aware effective RthJA ONLY against copper that is actually in the
# emitted .kicad_pcb. These emitters put that copper there:
#   * a board-interior GND plane zone on In1.Cu (the stackup L2 GND layer),
#   * per-buck/LDO local GND pours + thermal-via fields at the power-ground
#     pads (SNVSBD5D 11.1.1 / JESD51-5), keyed on the part's placed position,
#   * rule-area plane VOIDS under the ethernet magnetics/RJ45 (isolation).
# DETERMINISM: every zone is emitted UNFILLED but with (fill yes ...) settings
# — the file carries no fill polygons, so build-twice is byte-identical; the
# build's DRC runs kicad-cli with --refill-zones, so the REAL computed fill
# (connectivity, clearance, starved thermals) is what gets checked, in memory,
# without rewriting the board.

def _corners_rot(rect: tuple[float, float, float, float], inst,
                 model: PcbModel) -> list[tuple[float, float]]:
    """A footprint-LOCAL rect's 4 corners placed on the board with the KiCad
    CW (+y-down) placement rotation, then clamped into the board interior
    (GND_PLANE_EDGE_BACK inside Edge.Cuts). NO bottom-side mirror: KiCad
    stores a B.Cu footprint's local coordinates in the FINAL (front-view)
    frame and applies only the rotation at load — verified against pcbnew
    (bottom 4D03 network + rot-90 bottom caps land at at+R(rot)·(px,py))."""
    x0, y0, x1, y1 = rect
    r = math.radians(inst.rotation or 0.0)
    cs, sn = math.cos(r), math.sin(r)
    lo_x = ORIGIN_X + GND_PLANE_EDGE_BACK
    lo_y = ORIGIN_Y + GND_PLANE_EDGE_BACK
    hi_x = ORIGIN_X + model.board_w - GND_PLANE_EDGE_BACK
    hi_y = ORIGIN_Y + model.board_h - GND_PLANE_EDGE_BACK
    out: list[tuple[float, float]] = []
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        bx = inst.x + px * cs + py * sn
        by = inst.y - px * sn + py * cs
        out.append((round(min(max(bx, lo_x), hi_x), 3),
                    round(min(max(by, lo_y), hi_y), 3)))
    return out


def _fill_zone(net_num: int, net_name: str, zname: str, layer: str,
               corners: list[tuple[float, float]], uid_key: str, uid,
               clearance: float, solid: bool) -> list:
    """A REAL copper zone (net + fill settings), emitted UNFILLED (see the
    determinism note above). ``solid`` picks solid pad connection (the local
    thermal pours — the whole point is dumping heat through the pads); the
    plane keeps thermal reliefs so TH parts stay hand-solderable."""
    pts = [Sym("pts")] + [[Sym("xy"), px, py] for px, py in corners]
    connect = ([Sym("connect_pads"), Sym("yes"), [Sym("clearance"), clearance]]
               if solid else
               [Sym("connect_pads"), [Sym("clearance"), clearance]])
    return [Sym("zone"),
            [Sym("net"), net_num], [Sym("net_name"), net_name],
            [Sym("layer"), layer],
            [Sym("uuid"), uid(uid_key)],
            [Sym("name"), zname],
            [Sym("hatch"), Sym("edge"), 0.5],
            connect,
            [Sym("min_thickness"), ZONE_MIN_THICKNESS],
            [Sym("filled_areas_thickness"), Sym("no")],
            [Sym("fill"), Sym("yes"), [Sym("thermal_gap"), 0.5],
             [Sym("thermal_bridge_width"), 0.5]],
            [Sym("polygon"), pts]]


def _gnd_plane_zone(model: PcbModel, uid) -> list | None:
    """The board-interior GND plane on In1.Cu (stackup L2): outline inset
    GND_PLANE_EDGE_BACK from Edge.Cuts (above the 0.3 mm copper-edge design
    rule). This is the plane the DP90/DP100 microstrip geometry references and
    the buried half of every emitted thermal-via path."""
    num = model.net_numbers.get("GND")
    if not num:
        return None
    b = GND_PLANE_EDGE_BACK
    x0, y0 = round(ORIGIN_X + b, 3), round(ORIGIN_Y + b, 3)
    x1 = round(ORIGIN_X + model.board_w - b, 3)
    y1 = round(ORIGIN_Y + model.board_h - b, 3)
    return _fill_zone(num, "GND", "GND_plane_In1", GND_PLANE_LAYER,
                      [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                      "gnd-plane", uid, GND_PLANE_CLEARANCE, solid=False)


def _iso_void_zones(model: PcbModel, uid) -> list[list]:
    """Rule-area VOIDS (copperpour not_allowed on In1.Cu) punched in the GND
    plane under the ethernet line-side parts (ISO_VOID_VALUES: HX5008
    magnetics + RJ45): Pulse layout guidance + the Bob-Smith 2kV island say no
    ground plane belongs under the isolation transformer / media pins. Tracks
    and vias stay allowed (the media pairs must still cross); ONLY the plane
    pour is voided. The RJ45<->magnetics corridor is routing-wave debt
    (carrier/reports/copper_debt.txt)."""
    from .mating_face import _inst_courtyard
    out: list[list] = []
    for inst in model.insts:
        if not inst.value.startswith(ISO_VOID_VALUES):
            continue
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        m = ISO_VOID_MARGIN
        corners = [(round(cx0 - m, 3), round(cy0 - m, 3)),
                   (round(cx1 + m, 3), round(cy0 - m, 3)),
                   (round(cx1 + m, 3), round(cy1 + m, 3)),
                   (round(cx0 - m, 3), round(cy1 + m, 3))]
        pts = [Sym("pts")] + [[Sym("xy"), px, py] for px, py in corners]
        out.append([Sym("zone"),
                    [Sym("net"), 0], [Sym("net_name"), ""],
                    [Sym("layers"), GND_PLANE_LAYER],
                    [Sym("uuid"), uid(f"iso-void:{inst.ref}")],
                    [Sym("name"), f"ethernet_isolation_void_{inst.ref}"],
                    [Sym("hatch"), Sym("edge"), 0.5],
                    [Sym("connect_pads"), [Sym("clearance"), 0]],
                    [Sym("min_thickness"), ZONE_MIN_THICKNESS],
                    [Sym("keepout"),
                     [Sym("tracks"), Sym("allowed")],
                     [Sym("vias"), Sym("allowed")],
                     [Sym("pads"), Sym("allowed")],
                     [Sym("copperpour"), Sym("not_allowed")],
                     [Sym("footprints"), Sym("allowed")]],
                    [Sym("fill"), [Sym("thermal_gap"), 0.5],
                     [Sym("thermal_bridge_width"), 0.5]],
                    [Sym("polygon"), pts]])
    return out


# per-.kicad_mod pad table cache: [(px, py, prot_deg, sw, sh, drill), ...]
_MOD_PAD_CACHE: dict[str, list[tuple[float, float, float, float, float, float]]] = {}


def _mod_pads(mod_path) -> list[tuple[str, float, float, float, float, float, float]]:
    """(pad_name, px, py, prot_deg, sw, sh, drill) rows of a .kicad_mod, in the
    footprint LOCAL frame (drill 0 => SMD). Cached per path."""
    key = str(mod_path)
    cached = _MOD_PAD_CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    rows: list = []
    doc = sexpr.loads(mod_path.read_text())
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3 and sz and len(sz) >= 3):
            continue
        prot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) \
            else 0.0
        dr = sexpr.find(node, "drill")
        drill = float(dr[1]) if dr and len(dr) > 1 and \
            isinstance(dr[1], (int, float)) else 0.0
        rows.append((name, float(at[1]), float(at[2]), prot,
                     float(sz[1]), float(sz[2]), drill))
    _MOD_PAD_CACHE[key] = rows
    return rows


def _pad_obstacles(inst) -> list[tuple[float, float, float, float, str, float, str]]:
    """Every pad of a placed footprint as an axis-aligned obstacle
    (cx, cy, half_w, half_h, net_name, drill, label) in the BOARD frame: the
    KiCad CW rotation, NO bottom mirror (a B.Cu footprint's stored coordinates
    are already the final front-view frame — pcbnew-verified; an X-mirror here
    put a thermal via onto C16003's +3V3_SD pad while the model thought the
    spot was that cap's GND pad). ``label`` is the ref.pad the shortfall
    diagnostic names when this pad vetoes a via site."""
    r = math.radians(inst.rotation or 0.0)
    cs, sn = math.cos(r), math.sin(r)
    out: list[tuple[float, float, float, float, str, float, str]] = []
    for name, px, py, prot, sw, sh, drill in _mod_pads(inst.mod_path):
        pr = math.radians(prot)
        cx = inst.x + px * cs + py * sn
        cy = inst.y - px * sn + py * cs
        tot = r + pr
        ct, st = abs(math.cos(tot)), abs(math.sin(tot))
        hx = ct * sw / 2 + st * sh / 2
        hy = st * sw / 2 + ct * sh / 2
        nname = inst.pad_nets.get(name, (0, ""))[1]
        out.append((round(cx, 4), round(cy, 4), hx, hy, nname, drill,
                    f"{inst.ref}.{name}"))
    return out


def _via_obstacles(model: PcbModel, inst, reach: float) \
        -> list[tuple[float, float, float, float, str, float, str]]:
    """Everything a thermal-via candidate around ``inst`` must dodge: the pads
    of every footprint whose origin is within ``reach``, plus the T2 escape
    vias already planned on the model (``model.copper``) — an emitted via hole
    takes the same hole-to-hole margin as a drilled pad, and the exhaustive
    lattice search below reaches ground the curated site list never visited."""
    names = {num: nm for nm, num in model.net_numbers.items()}
    out: list[tuple[float, float, float, float, str, float, str]] = []
    for other in model.insts:
        if math.hypot(other.x - inst.x, other.y - inst.y) <= reach:
            out.extend(_pad_obstacles(other))
    for c in model.copper:
        if c.get("kind") != "via":
            continue
        cx, cy = float(c["x"]), float(c["y"])
        if math.hypot(cx - inst.x, cy - inst.y) > reach:
            continue
        vr = float(c.get("size", THERMAL_VIA_SIZE)) / 2
        out.append((round(cx, 4), round(cy, 4), vr, vr,
                    names.get(int(c.get("net", 0)), ""),
                    float(c.get("drill", THERMAL_VIA_DRILL)),
                    f"escape via @({cx:.3f},{cy:.3f})"))
    return out


def _via_site_blocker(vx: float, vy: float, model: PcbModel,
                      obstacles: list[tuple[float, float, float, float,
                                            str, float, str]],
                      chosen: list[tuple[float, float]]) -> str | None:
    """The object that vetoes a thermal-via candidate (named, with its
    coordinates, for the shortfall diagnostic) — None when the site is legal.
    A candidate survives when its barrel keeps THERMAL_VIA_CLEAR to every
    FOREIGN (non-GND) pad's copper, its HOLE edge keeps CLR_HOLE_SAMENET_PAD
    to SAME-net (GND) solder-pad copper (a via hole in a pad wicks the joint's
    solder even on the same net — the T2-wave DFM rule; the via ties to the pad
    through the POUR, never in the joint), THERMAL_VIA_H2H hole-edge spacing to
    every drilled pad (any net), THERMAL_VIA_EDGE to Edge.Cuts, and
    THERMAL_VIA_SPACING to the vias already chosen."""
    if not (ORIGIN_X + THERMAL_VIA_EDGE <= vx
            <= ORIGIN_X + model.board_w - THERMAL_VIA_EDGE
            and ORIGIN_Y + THERMAL_VIA_EDGE <= vy
            <= ORIGIN_Y + model.board_h - THERMAL_VIA_EDGE):
        return "Edge.Cuts keep-back"
    vr = THERMAL_VIA_SIZE / 2
    hr = THERMAL_VIA_DRILL / 2
    for cx, cy, hx, hy, nname, drill, label in obstacles:
        dx = max(0.0, abs(vx - cx) - hx)
        dy = max(0.0, abs(vy - cy) - hy)
        gap = math.hypot(dx, dy)
        where = f"{label} [{nname or 'no-net'}] @({cx:.3f},{cy:.3f})"
        if nname != "GND" and gap < vr + THERMAL_VIA_CLEAR:
            return where
        if nname == "GND" and gap < hr + CLR_HOLE_SAMENET_PAD:
            return where
        if drill > 0 and math.hypot(vx - cx, vy - cy) < \
                hr + drill / 2 + THERMAL_VIA_H2H:
            return where
    for ox, oy in chosen:
        if math.hypot(vx - ox, vy - oy) < THERMAL_VIA_SPACING:
            return f"thermal via @({ox:.3f},{oy:.3f})"
    return None


def _fallback_via_sites(spec: dict) -> list[tuple[float, float]]:
    """Every lattice site inside the part's OWN thermal pour (inset by the via
    radius so the barrel's copper stays in poured copper), NEAREST-TO-ORIGIN
    first — the exhaustive search the curated preference list falls back to
    when a neighbour's pads block the preferred sites. Deterministic: a fixed
    pitch and a total order on (radius, y, x)."""
    x0, y0, x1, y1 = spec["pour"]
    m = THERMAL_VIA_SIZE / 2
    x0, y0, x1, y1 = x0 + m, y0 + m, x1 - m, y1 - m
    ranked: list[tuple[float, float, float]] = []
    for i in range(int((x1 - x0) / THERMAL_VIA_LATTICE_PITCH) + 1):
        for j in range(int((y1 - y0) / THERMAL_VIA_LATTICE_PITCH) + 1):
            sx = round(x0 + i * THERMAL_VIA_LATTICE_PITCH, 3)
            sy = round(y0 + j * THERMAL_VIA_LATTICE_PITCH, 3)
            ranked.append((round(math.hypot(sx, sy), 4), sy, sx))
    return [(sx, sy) for _r, sy, sx in sorted(ranked)]


def _pour_credit_need(value: str):
    """The emitted-copper floor the THERMAL gate credits this part against,
    READ from schgen.verify.thermal.POUR_EVIDENCE (never duplicated, so the
    emitter's target and the gate's requirement cannot drift): the strictest
    matching PourNeed, or None for a part that claims no pour credit."""
    from schgen.verify.thermal import POUR_EVIDENCE
    needs = [n for n in POUR_EVIDENCE.values()
             if value.startswith(n.value_prefix)]
    return max(needs, key=lambda n: (n.min_vias, n.radius_mm)) if needs else None


def _report_via_shortfall(inst, chosen: list[tuple[float, float]],
                          vetoes: dict[str, int], n_cand: int) -> str | None:
    """LOUD, actionable line when a part's emitted via field lands UNDER the
    pour-credit floor after the exhaustive search: how many seats it got, out
    of how many candidate sites, and the objects that vetoed the most sites
    (ranked, named, with coordinates) — the parts a human must move. Returns
    the line (printed) or None when the field is whole."""
    need = _pour_credit_need(inst.value)
    if need is None:
        return None
    n_in = sum(1 for vx, vy in chosen
               if math.hypot(vx - inst.x, vy - inst.y) <= need.radius_mm)
    if n_in >= need.min_vias:
        return None
    top = sorted(vetoes.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
    line = (f"THERMAL VIA SHORTFALL: {inst.ref} ({inst.value}) at "
            f"({inst.x:.3f},{inst.y:.3f}) rot {inst.rotation:g} seated "
            f"{n_in}/{need.min_vias} GND vias within {need.radius_mm:g} mm; "
            f"{n_cand} candidate seats searched (curated + lattice), every "
            "other one blocked. Worst blockers: "
            + "; ".join(f"{obj} x{n}" for obj, n in top)
            + ". MOVE those parts (or this one): the thermal gate WITHHOLDS "
              "the pour credit on a short field.")
    print(line)
    return line


def _thermal_copper_nodes(model: PcbModel, uid) -> tuple[list[list], list[list]]:
    """(zones, vias) for every placed THERMAL_COPPER part: a local GND pour per
    listed layer (rotated with the part, solid pad connection) + a GND
    thermal-via field at the LOCAL candidate sites that survive the obstacle
    filter — the curated preference list first, then the EXHAUSTIVE
    nearest-first lattice over the part's own pour (``_fallback_via_sites``)
    when a neighbour's copper blocks the preferred sites, so the field is short
    only where no legal seat exists at all (deterministic: fixed site order,
    fixed inst order, first max_vias win). A field that still lands under the
    pour-credit floor prints a shortfall line naming the blocking objects. The
    vias tie the power-ground pads through the local pour into the In1 GND
    plane — the copper the thermal gate's pour credit is verified against."""
    num = model.net_numbers.get("GND")
    if not num:
        return [], []
    zones: list[list] = []
    zone_geom: list[tuple[str, list[tuple[float, float]], list]] = []
    vias: list[list] = []
    placed: list[tuple[float, float]] = []
    for inst in model.insts:
        spec = next((s for pfx, s in THERMAL_COPPER.items()
                     if inst.value.startswith(pfx)), None)
        if spec is None:
            continue
        # local pours (per layer; the B.Cu twin gives the buck a second outer
        # spreader stitched by the same via field)
        corners = _corners_rot(spec["pour"], inst, model)
        for layer in spec["pour_layers"]:
            z = _fill_zone(
                num, "GND", f"thermal_pour_{inst.ref}_{layer.split('.')[0]}",
                layer, corners, f"thpour:{inst.ref}:{layer}", uid,
                POUR_CLEARANCE, solid=True)
            zones.append(z)
            zone_geom.append((layer, corners, z))
        reach = max(abs(v) for site in spec["via_sites"] for v in site) + 20.0
        obstacles = _via_obstacles(model, inst, reach)
        r = math.radians(inst.rotation or 0.0)
        cs, sn = math.cos(r), math.sin(r)
        chosen: list[tuple[float, float]] = []
        vetoes: dict[str, int] = {}
        n_curated = len(spec["via_sites"])
        candidates = list(spec["via_sites"]) + _fallback_via_sites(spec)
        n_lattice = 0
        for ci, (sx, sy) in enumerate(candidates):
            if len(chosen) >= spec["max_vias"]:
                break
            vx = round(inst.x + sx * cs + sy * sn, 3)
            vy = round(inst.y - sx * sn + sy * cs, 3)
            veto = _via_site_blocker(vx, vy, model, obstacles, placed + chosen)
            if veto is None:
                chosen.append((vx, vy))
                if ci >= n_curated:
                    _fbk.record("thermal_via_lattice")
                    n_lattice += 1
            else:
                vetoes[veto] = vetoes.get(veto, 0) + 1
        if n_lattice:
            print(f"THERMAL VIA LATTICE: {inst.ref} ({inst.value}) seated "
                  f"{n_lattice}/{len(chosen)} via(s) from the exhaustive "
                  f"lattice — curated preferred site(s) blocked (registered "
                  f"fallback; drift from datasheet-preferred via geometry)")
        placed.extend(chosen)
        _report_via_shortfall(inst, chosen, vetoes, len(candidates))
        for i, (vx, vy) in enumerate(chosen):
            # through the unified builder (T2 reconciliation): locked=False
            # keeps the node shape + uid key byte-identical to the original
            # inline construction — thermal vias stay unlocked (their seats
            # re-derive per placement; only the T2 escape preroute is locked).
            vias.append(_via_node(
                {"x": vx, "y": vy, "size": THERMAL_VIA_SIZE,
                 "drill": THERMAL_VIA_DRILL, "net": num, "locked": False},
                uid, uid_key=f"thvia:{inst.ref}:{i}"))
    _stagger_overlapping_pours(zone_geom)
    return zones, vias


def _quads_overlap(a: list[tuple[float, float]],
                   b: list[tuple[float, float]]) -> bool:
    """Separating-axis test for two convex quads; exact edge-touch counts as
    separated (only a real area overlap trips KiCad's zones_intersect)."""
    for poly in (a, b):
        for i in range(len(poly)):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % len(poly)]
            nx, ny = y1 - y0, x0 - x1
            pa = [px * nx + py * ny for px, py in a]
            pb = [px * nx + py * ny for px, py in b]
            if max(pa) <= min(pb) + 1e-9 or max(pb) <= min(pa) + 1e-9:
                return False
    return True


def _stagger_overlapping_pours(
        zone_geom: list[tuple[str, list[tuple[float, float]], list]]) -> None:
    """Two same-net local pours on one layer may legitimately overlap on a
    dense board (two regulators side by side) — electrically one copper region,
    but KiCad's DRC demands DISTINCT zone priorities for intersecting zones.
    Give each overlap component's later members priorities 1..k (emission
    order; the first keeps the implicit 0). Boards whose pours never overlap
    emit no priority token — byte-identical output."""
    by_layer: dict[str, list[tuple[list[tuple[float, float]], list]]] = {}
    for layer, corners, z in zone_geom:
        by_layer.setdefault(layer, []).append((corners, z))
    for members in by_layer.values():
        comp = list(range(len(members)))

        def find(i: int, comp: list[int] = comp) -> int:
            while comp[i] != i:
                comp[i] = comp[comp[i]]
                i = comp[i]
            return i

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if _quads_overlap(members[i][0], members[j][0]):
                    comp[find(i)] = find(j)
        ranks: dict[int, int] = {}
        for i, (_c, z) in enumerate(members):
            root = find(i)
            k = ranks.get(root, 0)
            ranks[root] = k + 1
            if k:
                hatch_at = next(idx for idx, node in enumerate(z)
                                if isinstance(node, list) and node
                                and node[0] == Sym("hatch"))
                z.insert(hatch_at + 1, [Sym("priority"), k])
