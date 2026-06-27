"""Footprint EMBEDDING into the .kicad_pcb (parse the .kicad_mod, set placement
+ pad nets + side flip + content-derived uuids) plus the board-level emit
helpers (layers table, stackup, edge rectangle, SoM body silk + keepout zone).
PURE MOVE out of the old monolithic ``schgen/generate/pcb.py`` — no behaviour
change.
"""

from __future__ import annotations

from schgen.core import sexpr
from schgen.core.sexpr import Sym

from .constants import (
    _FOOTPRINT_ALIASES, CONN_MATING_FACE, _INT_DESC, _SW_DESC, _FOUR_LAYER,
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
    (B.Cu) side, the KiCad way: swap every (layer ...)/(layers ...) F.* token to
    its B.* twin, and add (justify mirror) to text effects. Local coordinates
    are NOT touched — KiCad mirrors at render time from the layer. Deterministic
    and reversible (re-running on a B.* tree is a no-op for the layers)."""
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

    # 2-side assembly: a bottom-side footprint flips to B.Cu. KiCad's on-disk
    # convention keeps the local pad/graphic COORDINATES unchanged and only
    # swaps every F.* layer token to its B.* twin (the renderer mirrors based on
    # the layer), plus a (justify mirror) on text. Done before the uuid/net pass
    # so the flipped tree is what gets stamped.
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
