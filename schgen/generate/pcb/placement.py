"""The placement engine: per-subsystem shelf packing, 2-side classification,
the LAW-6 edge-connector packer, the SHARED zone-geometry oracle and the
``build_model`` entry that turns the netlist + floorplan into a placed
``PcbModel``. PURE MOVE out of the old monolithic ``schgen/generate/pcb.py`` —
no behaviour change.
"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import (
    _TOP_ALWAYS_LIBS,
    BUTTON_GAP,
    CARRIER,
    CONN_MATING_FACE,
    EDGE_PAD_CLEAR,
    EDGE_ZONE_ASPECT,
    GRID,
    INTERIOR_ZONE_ASPECT,
    INTERIOR_ZONE_BAND_TARGET,
    MH_INSET,
    ORIGIN_X,
    ORIGIN_Y,
    PLACE_CLEAR,
    SOM_CORE_CLEARANCE,
    TOP_AREA_MM2,
    ZONE_PAD,
    FootprintInst,
    PcbModel,
    ZoneGeom,
)
from .footprint import (
    _footprint_bbox,
    _gridify,
    _net_classes,
    board_netlist,
    board_parts,
    has_thru_pads,
    pad_names,
    resolve_mod,
)
from .mating_face import _rot_bbox, _rot_bbox_cw, _rot_pad_bbox, connector_edge_rotation


def _shelf_pack(items: list[tuple[str, tuple, float]], target_w: float,
                blockers: list[tuple[float, float, float, float]] | None = None
                ) -> tuple[dict[str, tuple[float, float]], float, float]:
    """Deterministic shelf packer for ONE subsystem's footprints.

    ``items`` is [(ref, bbox, rotation), ...]; ``target_w`` is the width to
    fill before wrapping to a new shelf row. ``blockers`` are zone-relative
    rectangles (x0,y0,x1,y1) the placed boxes must AVOID — used to keep a
    bottom-side SMD out from under a top-side through-hole pad (whose copper is
    on every layer): a bottom part there would short to the THT pad. Returns
    ``(origin_of_ref, packed_w, packed_h)`` where ``origin_of_ref[ref]`` is the
    (x, y) to put at the footprint ORIGIN so its haloed rotated bbox sits inside
    the [0, packed_w] x [0, packed_h] zone with a ZONE_PAD margin. Parts are
    laid LARGEST-first (by haloed height, then width, then ref) so tall parts
    anchor each row. There is NO overflow path: the returned box is exactly
    large enough to hold every part, so the caller sizes the zone to fit and
    never spills a part off-board."""
    blk = list(blockers or [])
    placed: dict[str, tuple[float, float]] = {}
    occ: list[tuple[float, float, float, float]] = list(blk)
    # haloed rotated bbox per ref
    halo: dict[str, tuple[float, float, float, float]] = {}
    for ref, bbox, rot in items:
        rb = _rot_bbox(bbox, rot)
        halo[ref] = (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                     rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)
    order = sorted(items, key=lambda it: (
        -(halo[it[0]][3] - halo[it[0]][1]),
        -(halo[it[0]][2] - halo[it[0]][0]), it[0]))

    def _free(x0, y0, x1, y1, w_lim) -> bool:
        if x1 > ZONE_PAD + w_lim + 1e-6:
            return False
        for rx0, ry0, rx1, ry1 in occ:
            if not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0):
                return False
        return True

    used_w = ZONE_PAD
    used_h = ZONE_PAD
    cy = ZONE_PAD
    row_h = 0.0
    for ref, _bbox, _rot in order:
        hx0, hy0, hx1, hy1 = halo[ref]
        hw, hh = hx1 - hx0, hy1 - hy0
        w_lim = max(target_w, hw)
        # raster scan within the growing shelf area; blockers force a slide.
        cx = ZONE_PAD
        slot = None
        guard = 0
        scan_cy = cy
        scan_row_h = row_h
        while slot is None and guard < 100000:
            guard += 1
            if cx + hw > ZONE_PAD + w_lim + 1e-6:
                cx = ZONE_PAD
                scan_cy += scan_row_h if scan_row_h else hh
                scan_row_h = 0.0
                continue
            if _free(cx, scan_cy, cx + hw, scan_cy + hh, w_lim):
                slot = (cx, scan_cy)
                break
            cx += GRID
        sx, sy = slot
        occ.append((sx, sy, sx + hw, sy + hh))
        placed[ref] = (round(sx - hx0, 4), round(sy - hy0, 4))
        used_w = max(used_w, sx + hw)
        used_h = max(used_h, sy + hh)
        # advance the primary shelf cursor in row order
        if sy == cy:
            row_h = max(row_h, hh)
        else:
            cy, row_h = sy, hh
    packed_w = round(max(used_w, ZONE_PAD) + ZONE_PAD, 4)
    packed_h = round(max(used_h, ZONE_PAD) + ZONE_PAD, 4)
    return placed, packed_w, packed_h


def _is_button(mod_path: Path) -> bool:
    """A user-facing tactile PUSHBUTTON (the round 6 mm TS-1187A). DIP/SLIDE
    config switches (DSHP*) are NOT included — they are set-once configuration,
    not pressable controls, and pack with the passives. LAW 6: pressable controls
    read as an organised array, never scattered among the passives."""
    return "TS-1187A" in mod_path.stem


def _grid_controls(refs: list[str], bbox_of: dict, resolvable: dict,
                   target_w: float
                   ) -> tuple[dict[str, tuple[float, float]],
                              list[tuple[float, float, float, float]],
                              float, float]:
    """Lay tactile buttons in a CLEAN uniform grid in a reserved band at the top
    of the zone (LAW 6 — controls organised, not ugly). All buttons share one
    square cell = the largest button halo, so identical buttons align perfectly.
    Returns (origin_of_ref, occupied_cells, band_w, band_h); the occupied cells
    are handed to the rest-of-zone shelf pack as blockers so no passive intrudes
    into the button array."""
    cell = 0.0
    bb: dict[str, tuple[float, float, float, float]] = {}
    for r in refs:
        bx0, by0, bx1, by1 = bbox_of[r]
        bb[r] = (bx0, by0, bx1, by1)
        # BUTTON_GAP (not just PLACE_CLEAR) gives a finger-friendly air gap
        # between adjacent buttons so the array reads cleanly + presses easily
        # (user: "switches need slightly more spacing between them").
        cell = max(cell, (bx1 - bx0) + BUTTON_GAP, (by1 - by0) + BUTTON_GAP)
    cols = max(1, min(len(refs), int((target_w) // cell) or 1))
    off: dict[str, tuple[float, float]] = {}
    occ: list[tuple[float, float, float, float]] = []
    order = sorted(refs)
    for i, r in enumerate(order):
        cx, cy = i % cols, i // cols
        x0 = ZONE_PAD + cx * cell
        y0 = ZONE_PAD + cy * cell
        bx0, by0, bx1, by1 = bb[r]
        # seat the footprint's halo box centred in its square cell
        fw, fh = (bx1 - bx0) + PLACE_CLEAR, (by1 - by0) + PLACE_CLEAR
        ox = x0 + (cell - fw) / 2 - bx0 + PLACE_CLEAR / 2
        oy = y0 + (cell - fh) / 2 - by0 + PLACE_CLEAR / 2
        off[r] = (round(ox, 4), round(oy, 4))
        occ.append((x0, y0, x0 + cell, y0 + cell))
    rows = (len(refs) + cols - 1) // cols
    return off, occ, ZONE_PAD + cols * cell, ZONE_PAD + rows * cell


def _is_passive_ref(ref: str) -> bool:
    """A discrete passive whose reference designator starts R/C/L (the parts a
    2-side build may relocate to the bottom). FB (ferrite), D (diode) stay on
    top — they are often in the signal path or LED-visible."""
    return ref[:1] in ("R", "C", "L") and not ref.startswith(("RJ", "LED"))


def _decoupling_caps(nets: dict[str, list]) -> set[str]:
    """Refs of decoupling/bypass caps: a 2-pin cap across GROUND and exactly
    one other (rail) net. These are the bottom-side candidates placed directly
    under their IC's supply pins — derived from the netlist, never guessed."""
    cap_nets: dict[str, set[str]] = {}
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            continue
        for pr in pins:
            if pr.ref.startswith("C") and not pr.ref.startswith("#"):
                cap_nets.setdefault(pr.ref, set()).add(name)
    out: set[str] = set()
    for ref, ns in cap_nets.items():
        has_gnd = "GND" in ns
        rails = {n for n in ns if n != "GND"}
        if has_gnd and len(rails) == 1 and len(ns) == 2:
            out.add(ref)
    return out


def _classify_side(ref: str, lib: str, bbox: tuple,
                   decoupling: set[str], two_side: bool) -> str:
    """top|bottom for a footprint. Single-side -> always top. The SoM,
    connectors, mounting holes, test points and large/active ICs are top;
    decoupling caps and other small passives go to the bottom."""
    if not two_side:
        return "top"
    if any(tok in lib for tok in _TOP_ALWAYS_LIBS):
        return "top"
    bx0, by0, bx1, by1 = bbox
    area = (bx1 - bx0) * (by1 - by0)
    if area >= TOP_AREA_MM2:
        return "top"               # an IC / large part: top
    if ref in decoupling:
        return "bottom"            # bypass cap under its IC's supply pins
    if _is_passive_ref(ref):
        return "bottom"            # other small passive: relieve top pressure
    return "top"


def _eff_bbox_for(bbox: tuple[float, float, float, float],
                  side: str) -> tuple[float, float, float, float]:
    """The footprint's on-board local bbox. A BOTTOM part is flipped to B.Cu,
    which mirrors its geometry about the origin's X axis (KiCad's F->B
    convention), so its courtyard occupies the X-mirror of the top bbox."""
    bx0, by0, bx1, by1 = bbox
    if side == "bottom":
        return (-bx1, by0, -bx0, by1)
    return (bx0, by0, bx1, by1)


def _pack_one_zone(sheet_refs: list[str], side_of: dict[str, str],
                   bbox_of: dict, resolvable: dict, aspect: float = 1.0,
                   conn_rot: dict[str, float] | None = None,
                   outer_dir: str | None = None
                   ) -> tuple[dict[str, tuple[float, float]],
                              dict[str, tuple[float, float]],
                              float, float]:
    """Shelf-pack ONE subsystem's footprints 2-sided (TOP + BOTTOM overlay on
    the same XY area; the zone holds the LARGER of the two). Returns
    (top_off, bot_off, packed_w, packed_h). The BOTTOM pack avoids the TOP
    through-hole pads (copper on all layers) so no bottom SMD shorts to a THT
    pad. ``aspect`` widens the shelf target (>1 => wider + SHALLOWER zone): an
    EDGE-connector subsystem packs WIDE-and-SHALLOW so its block does not eat
    deep into the board behind its edge, which keeps the interior — and the whole
    board — tight. Deterministic in the given ref order.

    LAW 6: ``conn_rot`` (bref -> placement rotation) ROTATES each off-board
    connector so its mating face points off-board; ``outer_dir`` (N/S/E/W, the
    zone-LOCAL direction the board edge lies in once this zone is placed) makes
    the connector seat FLUSH at that outer boundary with the rest of the
    subsystem packed behind it, inward. When both are given the zone uses the
    dedicated edge-aware packer; otherwise it is the plain shelf pack."""
    sr = {"top": [], "bottom": []}
    for r in sheet_refs:
        sr[side_of[r]].append(r)
    conn_rot = conn_rot or {}

    def items(refs, side):
        return [(r, _eff_bbox_for(bbox_of[r], side), conn_rot.get(r, 0.0))
                for r in refs]

    if conn_rot and outer_dir:
        return _pack_connector_zone(sr, items, bbox_of, resolvable,
                                    conn_rot, outer_dir, aspect)

    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in sheet_refs)
    target_w = max(8.0, (tot_area * 0.62) ** 0.5) * aspect
    # LAW 6: pull the tactile buttons into a clean uniform grid at the top of the
    # zone, then shelf-pack the remaining parts around that array (its cells are
    # blockers). >=2 buttons trigger the grid; otherwise the plain shelf pack.
    top_btns = [r for r in sr["top"] if _is_button(resolvable[r])]
    if len(top_btns) >= 2:
        g_off, g_occ, g_w, g_h = _grid_controls(top_btns, bbox_of, resolvable,
                                                target_w)
        rest_top = [r for r in sr["top"] if r not in set(top_btns)]
        r_off, rw, rh = _shelf_pack(items(rest_top, "top"), target_w, g_occ)
        t_off = {**g_off, **r_off}
        tw, th = max(g_w, rw), max(g_h, rh)
    else:
        t_off, tw, th = _shelf_pack(items(sr["top"], "top"), target_w)
    blockers: list[tuple[float, float, float, float]] = []
    for r in sr["top"]:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_off[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2,
                         oy + by0 - PLACE_CLEAR / 2,
                         ox + bx1 + PLACE_CLEAR / 2,
                         oy + by1 + PLACE_CLEAR / 2))
    b_off, bw, bh = _shelf_pack(items(sr["bottom"], "bottom"),
                                target_w, blockers)
    return t_off, b_off, round(max(tw, bw), 4), round(max(th, bh), 4)


def _rotate_zone_90(t_off: dict[str, tuple[float, float]],
                    b_off: dict[str, tuple[float, float]],
                    bbox_of: dict, side_of: dict[str, str],
                    base_rot: dict[str, float],
                    zw: float, zh: float
                    ) -> tuple[dict[str, tuple[float, float]],
                               dict[str, tuple[float, float]],
                               dict[str, float], float, float]:
    """Turn an entire packed zone 90 deg about its local origin so a zone that
    packed TALL now lies FLAT (its (w, h) -> (h, w)). The part footprints are NOT
    redrawn: each gains +90 deg of placement rotation and its origin offset is
    transformed so its rotated courtyard lands in the new [0, zh] x [0, zw] box —
    i.e. the whole block is turned, exactly as a hand layout orients a rigid 2x40
    header along the side-band (NEVER-redraw-parts memo). Returns the rotated
    (t_off, b_off, extra_rot, new_w, new_h) where extra_rot[ref] = +90 must be
    ADDED to that part's placement rotation in build_model.

    Geometry — KiCad CONVENTION (the same CLOCKWISE sign _rot_pad_bbox already
    uses, page +y DOWN): a placement rotation A in `(at x y A)` turns the footprint
    so a local point (x, y) maps under +90 to (y, -x) (verified against kicad-cli
    DRC: a 2x40 header at +90 extends in +x). The zone box [0, zw] x [0, zh] then
    lands in x in [0, zh], y in [-zw, 0], so it is shifted +zw in Y to re-anchor to
    [0, zh] x [0, zw]. Each part's offset is the zone-local position of its
    footprint ORIGIN, which transforms the SAME way: (dx, dy) -> (dy, zw - dx).
    Using KiCad's true sign here (NOT the math-CCW _rot_bbox used elsewhere for the
    symmetric edge connectors, where CW==CCW) is what lands the emitted header
    inside the reserved block instead of off its +x side."""
    extra_rot: dict[str, float] = {}
    new_t: dict[str, tuple[float, float]] = {}
    new_b: dict[str, tuple[float, float]] = {}
    for off_in, off_out in ((t_off, new_t), (b_off, new_b)):
        for ref, (dx, dy) in off_in.items():
            off_out[ref] = (round(dy, 4), round(zw - dx, 4))
            extra_rot[ref] = 90.0
    return new_t, new_b, extra_rot, round(zh, 4), round(zw, 4)


def _pack_connector_zone(sr: dict[str, list[str]], items, bbox_of: dict,
                         resolvable: dict, conn_rot: dict[str, float],
                         outer_dir: str, aspect: float
                         ) -> tuple[dict[str, tuple[float, float]],
                                    dict[str, tuple[float, float]],
                                    float, float]:
    """Pack an EDGE-connector subsystem so every off-board connector seats FLUSH
    at the zone's OUTER boundary (the board edge), mouth pointing off-board, with
    the rest of the subsystem packed BEHIND it, inward (LAW 6).

    ``outer_dir`` is the zone-LOCAL direction (N/S/E/W) of the board edge once
    the zone is placed: N -> outer is local -y (top), S -> +y (bottom),
    W -> -x (left), E -> +x (right). The connectors form one row flush along that
    boundary; the non-connector parts shelf-pack into the remaining inboard area.
    Offsets are returned for the connector ROTATED in place (so its haloed rotated
    bbox sits inside the zone) and for every other part at rotation 0.
    Deterministic in the given ref order."""
    conn_refs_top = [r for r in sr["top"] if r in conn_rot]
    conn_refs_bot = [r for r in sr["bottom"] if r in conn_rot]
    rest_top = [r for r in sr["top"] if r not in conn_rot]
    rest_bot = [r for r in sr["bottom"] if r not in conn_rot]

    horiz = outer_dir in ("N", "S")     # connectors row spreads along X (N/S) ...
    #                                     ... or down Y (W/E)
    # haloed ROTATED bbox of each connector (the box it really occupies)
    def hbox(r, side):
        rb = _rot_bbox(_eff_bbox_for(bbox_of[r], side), conn_rot.get(r, 0.0))
        return (rb[0] - PLACE_CLEAR / 2, rb[1] - PLACE_CLEAR / 2,
                rb[2] + PLACE_CLEAR / 2, rb[3] + PLACE_CLEAR / 2)

    # 1) lay the connectors in one flush row along the outer boundary. Largest
    # cross-axis first so the row is tight; deterministic by (-cross, ref).
    conn_all = [(r, "top") for r in conn_refs_top] + \
               [(r, "bottom") for r in conn_refs_bot]
    if horiz:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[2] - hbox(*rs)[0]), rs[0]))
    else:
        conn_all.sort(key=lambda rs: (-(hbox(*rs)[3] - hbox(*rs)[1]), rs[0]))

    placed: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
    occ: list[tuple[float, float, float, float]] = []
    conn_depth = 0.0                      # how deep the connector row reaches in
    cursor = ZONE_PAD                     # position along the boundary axis
    for r, side in conn_all:
        hx0, hy0, hx1, hy1 = hbox(r, side)
        hw, hh = hx1 - hx0, hy1 - hy0
        if horiz:                          # row along X, flush at top (y=ZONE_PAD)
            ox = cursor - hx0
            oy = ZONE_PAD - hy0
            occ.append((cursor, ZONE_PAD, cursor + hw, ZONE_PAD + hh))
            cursor += hw + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hh)
        else:                              # column along Y, flush at left (x=PAD)
            ox = ZONE_PAD - hx0
            oy = cursor - hy0
            occ.append((ZONE_PAD, cursor, ZONE_PAD + hw, cursor + hh))
            cursor += hh + PLACE_CLEAR
            conn_depth = max(conn_depth, ZONE_PAD + hw)
        placed[side][r] = (round(ox, 4), round(oy, 4))

    # 2) shelf-pack the remaining parts into the inboard area, OFFSET behind the
    # connector row (so they never poke past the connector toward the edge). The
    # inter-band gap is generous (CONN_REST_GAP) — a faithful connector's KiCad
    # F.CrtYd (arcs / mechanical-post polygons) can exceed the parsed pad+line
    # bbox the packer reserves, and a thin gap then trips courtyards_overlap with
    # an inboard part (the camera FFC vs its CAM_SCL test point).
    CONN_REST_GAP = 2.0
    behind = conn_depth + CONN_REST_GAP
    tot_area = sum((bbox_of[r][2] - bbox_of[r][0] + PLACE_CLEAR) *
                   (bbox_of[r][3] - bbox_of[r][1] + PLACE_CLEAR)
                   for r in rest_top + rest_bot)
    # the connector row sets the boundary-axis span; keep the rest at least that
    # wide so the zone stays wide+shallow.
    row_span = max(cursor, 8.0)
    target_w = max(row_span - ZONE_PAD, (tot_area * 0.62) ** 0.5 * aspect)

    rt = [(r, _eff_bbox_for(bbox_of[r], "top"), 0.0) for r in rest_top]
    t_rest, _tw, _th = _shelf_pack(rt, target_w)
    blockers: list[tuple[float, float, float, float]] = []
    for r in rest_top:
        if not has_thru_pads(resolvable[r]):
            continue
        ox, oy = t_rest[r]
        bx0, by0, bx1, by1 = bbox_of[r]
        blockers.append((ox + bx0 - PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by0 - PLACE_CLEAR / 2 + (behind if horiz else 0),
                         ox + bx1 + PLACE_CLEAR / 2 + (0 if horiz else behind),
                         oy + by1 + PLACE_CLEAR / 2 + (behind if horiz else 0)))
    rb = [(r, _eff_bbox_for(bbox_of[r], "bottom"), 0.0) for r in rest_bot]
    b_rest, _bw, _bh = _shelf_pack(rb, target_w, blockers)

    for r, (dx, dy) in t_rest.items():
        placed["top"][r] = (round(dx + (0 if horiz else behind), 4),
                            round(dy + (behind if horiz else 0), 4))
    for r, (dx, dy) in b_rest.items():
        placed["bottom"][r] = (round(dx + (0 if horiz else behind), 4),
                               round(dy + (behind if horiz else 0), 4))

    # 3) zone extent = max over every placed haloed (rotated for conns) bbox.
    zw = zh = ZONE_PAD
    for side in ("top", "bottom"):
        for r, (ox, oy) in placed[side].items():
            if r in conn_rot:
                rb2 = _rot_bbox(_eff_bbox_for(bbox_of[r], side),
                                conn_rot.get(r, 0.0))
            else:
                rb2 = _eff_bbox_for(bbox_of[r], side)
            zw = max(zw, ox + rb2[2] + PLACE_CLEAR / 2)
            zh = max(zh, oy + rb2[3] + PLACE_CLEAR / 2)
    zw = round(zw + ZONE_PAD, 4)
    zh = round(zh + ZONE_PAD, 4)

    # 4) for a BOTTOM (S/+y) or RIGHT (E/+x) outer edge, the connectors were laid
    # flush at the LOW boundary (top/left); flip the depth axis so they end flush
    # at the HIGH boundary (the actual board edge) with the rest behind, inward.
    if outer_dir in ("S", "E"):
        flip_y = (outer_dir == "S")
        out: dict[str, dict[str, tuple[float, float]]] = {"top": {}, "bottom": {}}
        for side in ("top", "bottom"):
            for r, (ox, oy) in placed[side].items():
                if r in conn_rot:
                    rb2 = _rot_bbox(_eff_bbox_for(bbox_of[r], side),
                                    conn_rot.get(r, 0.0))
                else:
                    rb2 = _eff_bbox_for(bbox_of[r], side)
                if flip_y:
                    noy = zh - (oy + rb2[3]) - rb2[1]
                    out[side][r] = (round(ox, 4), round(noy, 4))
                else:
                    nox = zw - (ox + rb2[2]) - rb2[0]
                    out[side][r] = (round(nox, 4), round(oy, 4))
        placed = out

    return placed["top"], placed["bottom"], zw, zh


def _connector_sheet_edges() -> dict[str, str]:
    """sheet -> board EDGE (N/E/S/W) for every subsystem that carries an off-board
    connector (LAW 6). The edge is read from the DECLARATIVE carrier/floorplan.json
    (the same spec build_plan pins blocks from); a connector sheet pinned to an
    INTERIOR slot, or absent from the spec, is reported (the placement_mech gate
    then HARD-FAILS it — an off-board connector that is not on an edge is
    unbuildable). Deterministic: the spec is read once and keyed by sheet name."""
    from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
    out: dict[str, str] = {}
    if not FLOORPLAN_SPEC.exists():
        return out
    try:
        spec = load_floorplan_spec()
    except Exception:  # noqa: BLE001 — a malformed spec is reported by build_plan
        return out
    if spec is None:
        return out
    return dict(spec.edge_of)


def _downstream_facing(sheet: str, contract: dict) -> str | None:
    """The zone-LOCAL direction (N/E/S/W) the contract's declared DOWNSTREAM zone
    lies in, for the stage-template FACING turn (Unit 3). Deterministic, derived
    from the DECLARATIVE carrier/floorplan.json (the same spec build_plan reads) —
    NOT the final packed positions, so it cannot deadlock the sizing pass (the
    template's facing turn is bbox-preserving, so it never changes the block size
    the plan is about to commit to).

    Rule: the downstream zone (``external.downstream``, e.g. ``power_som``) is a
    SoM-power subsystem that sits toward the board INTERIOR / SoM. A contracted
    INTERIOR block declared on floorplan side ``S`` has its interior toward ``S``'s
    opposite (N<->S, E<->W); an EDGE block's interior is likewise inboard. So the
    facing direction is the INTERIOR direction = the opposite of this sheet's
    declared board side. Returns None if the side cannot be determined (the
    template then skips the turn — no facing hint, no change)."""
    ext = contract.get("external") or {}
    if not ext.get("downstream"):
        return None
    from schgen.generate.floorplan import FLOORPLAN_SPEC, load_floorplan_spec
    if not FLOORPLAN_SPEC.exists():
        return None
    try:
        spec = load_floorplan_spec()
    except Exception:  # noqa: BLE001 — a malformed spec is reported by build_plan
        return None
    if spec is None:
        return None
    _OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
    # interior blocks declare {"side": X}; edge blocks are in spec.edge_of.
    side = None
    cfg = spec.interior.get(sheet)
    if isinstance(cfg, dict):
        side = cfg.get("side")
    if side is None:
        side = spec.edge_of.get(sheet)
    if side not in _OPP:
        return None
    return _OPP[side]                     # interior/downstream = opposite the edge


def subsystem_zone_geometry(two_side: bool = True) -> ZoneGeom:
    """The SHARED packer: for every non-SoM subsystem, its REAL 2-sided packed
    zone (w, h) + per-part offsets, keyed on the STABLE board-unique refs. Built
    from the subsystem circuits (no dependence on the emitted root schematic), so
    `schgen floorplan` and `schgen board` get byte-identical geometry."""
    import json as _json

    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.model import PinRef
    from schgen.generate.board import _renamed_ref

    idx_path = CARRIER / "sheet_index.json"
    sheet_index = (_json.loads(idx_path.read_text())
                   if idx_path.exists() else {})
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]

    from schgen.generate.floorplan import _EDGE_FAMILIES

    refs_by_sheet: dict[str, list[str]] = {}
    bbox_of: dict[str, tuple[float, float, float, float]] = {}
    resolvable: dict[str, Path] = {}
    side_of: dict[str, str] = {}
    mh_refs: list[str] = []
    deferred: list[str] = []
    edge_sheets: set[str] = set()       # sheets with an off-board edge connector
    # LAW 6: off-board connector refs per sheet + their MPN (for the rotation).
    conn_mpn_of: dict[str, str] = {}    # bref -> mating-face MPN

    sheet_edge = _connector_sheet_edges()    # sheet -> board edge (from the spec)

    for i, sc in enumerate(sheets, start=1):
        if sc.name.startswith("som_j") or sc.name == "som_decoupling":
            continue        # receptacles ARE the SoM; som_decoupling is placed
            #                 BOTTOM-side under the SoM core, not in a zone (LAW 6)
        band = sheet_index.get(sc.name, i)
        c = sc.circuit
        # per-sheet decoupling on the board-unique ref namespace (equivalent to
        # the merged-netlist classification — proven — and side-stable).
        snets: dict[str, list[PinRef]] = {}
        for nname, net in c.nets.items():
            snets[nname] = [
                PinRef(_renamed_ref(p.ref, band, sheet=sc.name)
                       if not p.ref.startswith("#") else p.ref, p.pin)
                for p in net.pins]
        sdec = _decoupling_caps(snets)
        for ref, part in c.parts.items():
            bref = _renamed_ref(ref, band, sheet=sc.name)
            if part.value in _EDGE_FAMILIES:
                edge_sheets.add(sc.name)
            if part.value in CONN_MATING_FACE:
                conn_mpn_of[bref] = part.value
            if part.lib_id.startswith("Mechanical:MountingHole"):
                mh_refs.append(bref)
                continue
            mod = resolve_mod(part.footprint)
            if mod is None:
                deferred.append(f"{bref} ({sc.name}): footprint "
                                f"{part.footprint!r} not found")
                continue
            resolvable[bref] = mod
            bbox_of[bref] = _footprint_bbox(mod)
            side_of[bref] = _classify_side(bref, part.lib_id, bbox_of[bref],
                                           sdec, two_side)
            refs_by_sheet.setdefault(sc.name, []).append(bref)

    # LAW 6: per-connector placement rotation (mating face -> off-board) keyed on
    # the connector's assigned board edge; the local OUTER direction the edge lies
    # in once the zone is placed (== the edge, since the zone keeps board axes).
    conn_rot: dict[str, float] = {}
    conn_edge: dict[str, str] = {}
    sheet_conn_rot: dict[str, dict[str, float]] = {}
    sheet_outer: dict[str, str] = {}
    for sheet, brefs in refs_by_sheet.items():
        edge = sheet_edge.get(sheet)
        for bref in brefs:
            mpn = conn_mpn_of.get(bref)
            if mpn is None or bref not in bbox_of:
                continue
            if edge is None:
                # connector NOT pinned to an edge — leave un-rotated; the
                # placement_mech gate HARD-FAILS it (off-board connector off-edge).
                continue
            rot = connector_edge_rotation(CONN_MATING_FACE[mpn], edge)
            conn_rot[bref] = rot
            conn_edge[bref] = edge
            sheet_conn_rot.setdefault(sheet, {})[bref] = rot
            sheet_outer[sheet] = edge

    zone_box: dict[str, tuple[float, float]] = {}
    top_off: dict[str, dict[str, tuple[float, float]]] = {}
    bot_off: dict[str, dict[str, tuple[float, float]]] = {}
    zone_extra_rot: dict[str, float] = {}
    for sheet in sorted(refs_by_sheet):
        # EDGE-connector subsystems pack WIDE + SHALLOW (aspect > 1) so their
        # block sits behind the edge without eating deep into the board; INTERIOR
        # subsystems stay squarish.
        is_edge = sheet in edge_sheets
        aspect = EDGE_ZONE_ASPECT if is_edge else 1.0

        # PLACEMENT CONTRACT: a subsystem carrying a placement_contract.py gets a
        # datasheet-faithful STAGE TEMPLATE (Phase L) instead of the size-sorted
        # shelf pack. The template FORCES every contract member to the IC's side
        # (the same_side override) BEFORE building — so both the 2-side classifier
        # here and any later L4 pull see "top" — then returns the SAME 4-tuple
        # _pack_one_zone does (drop-in). A None result falls through to the legacy
        # packer UNCHANGED (byte-identical for every non-contracted sheet). The
        # template's chosen passive rotations come back via ``tmpl_rot`` and fold
        # into zone_extra_rot (the SAME channel LEVER-L1 uses). See stage_templates.
        from schgen.verify.placement_contract_gate import load_contract

        from . import stage_templates
        _contract = load_contract(sheet)
        _tmpl = None
        if _contract is not None:
            _members = stage_templates.contract_member_brefs(sheet, _contract,
                                                             resolvable)
            for _m in _members:
                side_of[_m] = "top"
            tmpl_rot: dict[str, float] = {}
            # FACING hint (Unit 3): the zone-local direction the contract's
            # declared DOWNSTREAM zone (external.flow / external.downstream) lies
            # in — the template turns the composed column so its OUTPUT-role parts
            # face that way, so the composition-level FLOW gate's FACING check
            # passes. Derived from the floorplan (below) without needing the final
            # plan positions (the turn is bbox-preserving, so it does not perturb
            # the block size the plan is about to commit to).
            _facing = _downstream_facing(sheet, _contract)
            _tmpl = stage_templates.build_zone(
                sheet, _contract, refs_by_sheet[sheet], side_of, bbox_of,
                resolvable, tmpl_rot, facing=_facing)
            if _tmpl is not None:
                zone_extra_rot.update(tmpl_rot)
        if _tmpl is not None:
            t_off, b_off, zw, zh = _tmpl
            top_off[sheet] = t_off
            bot_off[sheet] = b_off
            zone_box[sheet] = (zw, zh)
            continue

        t_off, b_off, zw, zh = _pack_one_zone(
            refs_by_sheet[sheet], side_of, bbox_of, resolvable, aspect,
            conn_rot=sheet_conn_rot.get(sheet),
            outer_dir=sheet_outer.get(sheet))

        # LEVER L1: an INTERIOR zone packed TALLER than the SoM side-band forces the
        # board wide (the interior packer does not rotate). Lay it flat in the band
        # WITHOUT redrawing any part: first try re-flowing it wide-and-shallow (an
        # INTERIOR_ZONE_ASPECT shelf re-pack — fixes zones of small parts); if its
        # SINGLE tallest part is itself taller than the band so no re-flow can help
        # (a rigid 2x40 header), turn the whole BLOCK 90 deg instead. Edge zones are
        # already seated flush on their edge and must not be touched here.
        if (not is_edge) and zh > INTERIOR_ZONE_BAND_TARGET:
            # (1) wide-shallow re-flow of the SAME parts (no rotation).
            rt_off, rb_off, rzw, rzh = _pack_one_zone(
                refs_by_sheet[sheet], side_of, bbox_of, resolvable,
                INTERIOR_ZONE_ASPECT)
            if rzh <= INTERIOR_ZONE_BAND_TARGET and rzh < zh:
                t_off, b_off, zw, zh = rt_off, rb_off, rzw, rzh
            elif zw <= INTERIOR_ZONE_BAND_TARGET and zw < zh:
                # (2) the zone is tall because a RIGID part is tall and re-flow
                # cannot shrink the height; rotate the whole packed block 90 deg so
                # it lies flat (its narrow width becomes the depth into the band).
                t_off, b_off, er, zw, zh = _rotate_zone_90(
                    t_off, b_off, bbox_of, side_of, {}, zw, zh)
                zone_extra_rot.update(er)

        top_off[sheet] = t_off
        bot_off[sheet] = b_off
        zone_box[sheet] = (zw, zh)

    return ZoneGeom(zone_box=zone_box, top_off=top_off, bot_off=bot_off,
                    side_of=side_of, bbox_of=bbox_of, resolvable=resolvable,
                    refs_by_sheet=refs_by_sheet, mh_refs=sorted(mh_refs),
                    deferred=deferred, conn_rot=conn_rot, conn_edge=conn_edge,
                    zone_extra_rot=zone_extra_rot)


# ---- the model build -------------------------------------------------------------

def build_model(two_side: bool = True) -> PcbModel:
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.generate import floorplan as fp
    from schgen.verify import powertree

    nets = board_netlist()
    parts = board_parts()

    # net-number table: 0 reserved for "no net"; deterministic by sorted name.
    real_nets = sorted(n for n in nets if n and not n.startswith("unconnected-"))
    net_numbers: dict[str, int] = {"": 0}
    for i, name in enumerate(real_nets, start=1):
        net_numbers[name] = i
    # pin -> (net number, net name)
    pin_net: dict[tuple[str, str], tuple[int, str]] = {}
    for name, pins in nets.items():
        if name.startswith("unconnected-"):
            continue          # unrouted/un-netted: pad stays net 0
        num = net_numbers.get(name, 0)
        for pr in pins:
            if not pr.ref.startswith("#"):
                pin_net[(pr.ref, pr.pin)] = (num, name)

    # SHARED zone geometry: the REAL 2-sided packed (w, h) + per-part offsets for
    # every subsystem, keyed on the stable board-unique refs. This is the SAME
    # function the FLOORPLAN sizes its blocks from, so the floorplan block (w, h)
    # and the PCB zone (w, h) are byte-identical -> the placement lands inside the
    # floorplan block and FLOORPLAN.svg agrees with the PCB ratsnest by
    # construction (no more 235x215-vs-165x155 divergence).
    zg = subsystem_zone_geometry(two_side=two_side)
    zone_box = zg.zone_box
    top_off = zg.top_off
    bot_off = zg.bot_off
    side_of = dict(zg.side_of)
    bbox_of = dict(zg.bbox_of)
    resolvable = dict(zg.resolvable)
    deferred = list(zg.deferred)
    mh_refs = list(zg.mh_refs)
    mh_set = set(mh_refs)

    # The shared packer omits the FIXED-position parts (mounting holes + the SoM
    # DF40 receptacles) + the under-SoM decoupling — they are not zone-packed.
    # Resolve their footprints from the board parts so the emission loop still
    # places them (positions set in STEP 3: corner-forced holes, centered/mirrored
    # mezzanine, and the bottom-side SoM-shadow decoupling grid).
    for ref, (sheet, footprint, _value, _lib) in parts.items():
        if ref in resolvable:
            continue
        if not (ref in mh_set or sheet.startswith("som_j")
                or sheet == "som_decoupling"):
            continue
        mod = resolve_mod(footprint)
        if mod is None:
            deferred.append(f"{ref} ({sheet}): footprint {footprint!r} "
                            f"not found in parts/ or the KiCad std libs")
            continue
        resolvable[ref] = mod
        bbox_of[ref] = _footprint_bbox(mod)
        side_of[ref] = "top"

    # floorplan plan (block POSITIONS + the derived outline) + net classes. The
    # floorplan calls the SAME subsystem_zone_geometry above for its block sizes,
    # so plan.blocks[*].w/h == zone_box[*] and the floorplan outline (fp.BOARD_W/H)
    # holds every packed block. The PCB honours both as the source of truth.
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    link_result = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = fp.build_plan(sheets, link_result, regs)
    classes, netclass_of = _net_classes(sheets)
    board_w, board_h = fp.BOARD_W, fp.BOARD_H

    # The SoM mezzanine receptacles (sheets som_j1/2/3) are FIXED at the
    # centered, SoM-mirrored DF40 positions and form the SoM region; every
    # other sheet is a SUBSYSTEM whose footprints cluster into one contiguous
    # zone. Per-connector ROTATION matches the SoM (J3 vertical, others flat).
    som = plan.som
    som_rot = {j.ref: (90.0 if j.w < j.h else 0.0) for j in som.js}
    som_rel = {j.ref: (j.x, j.y) for j in som.js}     # SoM-relative centers
    som_j_refs: dict[str, str] = {}                    # board ref -> J1/J2/J3
    fixed_rot: dict[str, float] = {}
    for ref, (sheet, _fp, _v, _lib) in parts.items():
        if ref not in resolvable or not sheet.startswith("som_j"):
            continue
        m = re.match(r"som_j(\d)", sheet)
        if m and ref.startswith("J"):
            jname = f"J{m.group(1)}"
            if jname in som_rel:
                som_j_refs[ref] = jname
                fixed_rot[ref] = som_rot[jname]

    # LAW 6: every off-board edge connector carries the placement rotation that
    # turns its mating face OFF-BOARD (computed in subsystem_zone_geometry from the
    # connector's assigned board edge). The shared packer already reserved the
    # ROTATED bbox + seated the connector flush at the zone's outer edge, so this
    # rotation lands the footprint exactly where the zone expects it.
    for ref, rot in zg.conn_rot.items():
        if ref in resolvable:
            fixed_rot[ref] = rot

    # LEVER L1: a 90-deg INTERIOR-zone rotation (subsystem_zone_geometry) turned an
    # over-tall block flat in the SoM side-band; ADD that +rot to each of its parts'
    # placement rotation so the footprint lands where the rotated zone offsets
    # (top_off/bot_off) expect it. These zones carry no off-board connector, so this
    # never collides with the LAW-6 conn_rot above.
    for ref, extra in zg.zone_extra_rot.items():
        if ref in resolvable:
            fixed_rot[ref] = (fixed_rot.get(ref, 0.0) + extra) % 360.0

    # ---- STEP 1: zone geometry comes from the SHARED packer (above) ----------
    # zone_box / top_off / bot_off already hold every subsystem's REAL 2-sided
    # packed (w, h) + per-part offsets (zg). The floorplan sized its blocks from
    # the SAME zg, so each block's (w, h) == zone_box[sheet] exactly.

    # ---- STEP 2: HONOUR the floorplan — positions + outline are the truth ----
    # The board outline is the floorplan's derived+grown outline (fp.BOARD_W/H),
    # and every subsystem zone is anchored at its FLOORPLAN block top-left
    # (plan.blocks). The SoM is at the floorplan's centered origin. No re-sizing,
    # no re-layout, no independent board grow: the FLOORPLAN.svg and this PCB are
    # the same picture. (The floorplan layout proved every block fits inside the
    # outline with the SoM region clear, so nothing lands off-board.)
    block_of = {b.name: b for b in plan.blocks}
    zorigin: dict[str, tuple[float, float]] = {}
    for sheet in zone_box:
        b = block_of.get(sheet)
        if b is None:
            continue
        zorigin[sheet] = (b.x, b.y)

    # SoM keep-out (centered on the floorplan SoM body) + SoM mezzanine J
    # positions (the floorplan-centered, SoM-mirrored DF40 centers).
    halo = 1.0
    keepout = (plan.som_x - halo, plan.som_y - halo,
               plan.som_x + som.w + halo, plan.som_y + som.h + halo)
    som_view = {jn: (plan.som_x + sx, plan.som_y + sy)
                for jn, (sx, sy) in som_rel.items()}

    # ---- STEP 3: final origins (board frame) for every footprint ------------
    pos: dict[str, tuple[float, float]] = {}
    # mounting holes -> the 4 corners of the FLOORPLAN-sized board
    corners = [(MH_INSET, MH_INSET),
               (board_w - MH_INSET, MH_INSET),
               (board_w - MH_INSET, board_h - MH_INSET),
               (MH_INSET, board_h - MH_INSET)]
    for i, ref in enumerate(mh_refs):
        pos[ref] = corners[i % 4]
    # SoM receptacles
    for ref, jname in som_j_refs.items():
        pos[ref] = som_view[jname]
    # subsystem footprints: GRID-SNAPPED zone origin + per-part packed offset.
    # The shelf packer (above) reserved EXACT PLACE_CLEAR gaps between the parts
    # in each zone's local frame; snapping each part's ABSOLUTE board position to
    # the coarse GRID afterwards would round two neighbours across a half-grid
    # boundary in OPPOSITE directions and collapse a 2.46 mm row pitch to 1.27 mm
    # — a 0.19 mm courtyard overlap (the intra-zone courtyards_overlap DRC errors
    # this caused). Instead snap the zone ORIGIN once and add the raw packed
    # offsets, so the packer's exact intra-zone clearance is preserved verbatim
    # while the zone as a whole still lands on the placement grid.
    grid_placed: set[str] = set()
    for sheet in zorigin:
        zx, zy = zorigin[sheet]
        gzx = _gridify(ORIGIN_X + zx) - ORIGIN_X
        gzy = _gridify(ORIGIN_Y + zy) - ORIGIN_Y
        for r, (dx, dy) in top_off[sheet].items():
            pos[r] = (gzx + dx, gzy + dy)
            grid_placed.add(r)
        for r, (dx, dy) in bot_off[sheet].items():
            pos[r] = (gzx + dx, gzy + dy)
            grid_placed.add(r)

    # LAW 6: SoM power-entry decoupling — grid the som_decoupling caps on the
    # BOTTOM side, spread across the SoM shadow (the dead area under the
    # mezzanine). They bypass the rails the carrier delivers to the DF40 right at
    # the power entry. Bottom side clears the top-side DF40 receptacles (different
    # copper layer); the shadow is otherwise empty so the grid never collides.
    udec = sorted(r for r, (sh, _f, _v, _l) in parts.items()
                  if sh == "som_decoupling" and r in resolvable)
    if udec:
        M = 6.0                                    # inset from the SoM core edge
        rx0, ry0 = plan.som_x + M, plan.som_y + M
        rw = max(1.0, som.w - 2 * M)
        rh = max(1.0, som.h - 2 * M)
        n = len(udec)
        cols = max(1, min(n, round((n * rw / rh) ** 0.5)))
        rows = max(1, (n + cols - 1) // cols)
        for i, ref in enumerate(udec):
            cxi, cyi = i % cols, i // cols
            px = rx0 + rw * (cxi + 0.5) / cols
            py = ry0 + rh * (cyi + 0.5) / rows
            pos[ref] = (round(px, 4), round(py, 4))
            side_of[ref] = "bottom"
            grid_placed.add(ref)

    # ---- LEVER L4: BOTTOM-PULL toward the SoM (cross-airwire reduction) ------
    # The board is AIRWIRE-BUDGET bound (LAW 5) and the BOTTOM is ~82% empty. Every
    # subsystem nets most of its pins to the SoM DF40 J-strips at the board centre,
    # so its cross-subsystem airwire is dominated by the span from its cluster to
    # the SoM. The 2-side policy already put its small passives on the BOTTOM layer,
    # so that bottom sub-cluster can slide toward the SoM to SHORTEN those net spans
    # and drop the REAL cross-airwire the LAW-5 gate measures. The cluster moves as
    # a RIGID GROUP (internal packing — every intra-cluster clearance — preserved),
    # by the LARGEST shift toward the SoM centre that still: (a) keeps every part
    # on-board; (b) clears — with full courtyard halo — EVERY other part already on
    # the BOTTOM layer (other subsystems' clusters, the som_decoupling grid, and the
    # not-yet-moved bottom parts) so no bottom-vs-bottom overlap/short; (c) never
    # lands a bottom SMD over a TOP through-hole pad (copper on all layers); and
    # (d) keeps the subsystem's combined top+bottom dispersion under a conservative
    # cap (below the LAW-5 9x gate) so it still reads as ONE cluster. ADDS no net,
    # RELOCATES no net (LAW 0): only the physical XY of already-bottom passives
    # moves. The REAL DRC + ratsnest gates remain the arbiters.
    if two_side:
        som_cx = plan.som_x + som.w / 2.0
        som_cy = plan.som_y + som.h / 2.0

        def _eff_box(ref: str, px: float, py: float
                     ) -> tuple[float, float, float, float]:
            # apply the part's placement ROTATION (a LEVER-L1 zone rotation turns
            # interior passives 90 deg) BEFORE the F->B side mirror, so the L4
            # collision/dispersion bound matches the courtyard the part really
            # occupies — otherwise a rotated zone's bottom passives could be
            # bound by their un-rotated box and the move clip a neighbour. Uses
            # KiCad's CLOCKWISE sign (_rot_bbox_cw) so the bound matches where the
            # emitted footprint really lands (the same sign _rot_pad_bbox uses).
            rb = _rot_bbox_cw(bbox_of[ref], fixed_rot.get(ref, 0.0))
            ex0, ey0, ex1, ey1 = _eff_bbox_for(rb, side_of.get(ref, "top"))
            return (px + ex0, py + ey0, px + ex1, py + ey1)

        def _halo(b: tuple[float, float, float, float], m: float
                  ) -> tuple[float, float, float, float]:
            return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)

        def _hit(b: tuple[float, float, float, float],
                 boxes: list[tuple[float, float, float, float]]) -> bool:
            for o in boxes:
                if (b[0] < o[2] and b[2] > o[0]
                        and b[1] < o[3] and b[3] > o[1]):
                    return True
            return False

        # TOP through-hole pad keepout boxes (haloed) — a bottom SMD over one is a
        # cross-layer short (copper on all layers).
        tht_boxes: list[tuple[float, float, float, float]] = [
            _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR)
            for r in pos
            if side_of.get(r) == "top" and r in resolvable
            and has_thru_pads(resolvable[r])]

        # occupancy of every BOTTOM-layer part (haloed) — the moving cluster must
        # not overlap any of these. Built once; each subsystem removes its own
        # movers before testing and re-adds them (shifted) after committing, so a
        # later subsystem sees the earlier one's final seat.
        bot_box: dict[str, tuple[float, float, float, float]] = {
            r: _halo(_eff_box(r, pos[r][0], pos[r][1]), PLACE_CLEAR / 2)
            for r in pos
            if side_of.get(r) == "bottom" and r in bbox_of}

        DISP_CAP_L4 = 5.0          # conservative; LAW-5 gate fails only at 9.0x
        EDGE_MARGIN = 0.6          # keep shifted copper this far inside Edge.Cuts
        STEP = 1.0
        for sheet in sorted(zorigin):
            movers = [r for r in bot_off.get(sheet, {})
                      if side_of.get(r) == "bottom" and r in pos
                      and r[:1] in ("R", "C", "L")
                      and not r.startswith(("RJ", "LED"))]
            if len(movers) < 2:
                continue
            gcx = sum(pos[r][0] for r in movers) / len(movers)
            gcy = sum(pos[r][1] for r in movers) / len(movers)
            vx, vy = som_cx - gcx, som_cy - gcy
            dist = (vx * vx + vy * vy) ** 0.5
            if dist < 1.0:
                continue
            ux, uy = vx / dist, vy / dist
            # bottom occupancy EXCLUDING this subsystem's own movers
            others = [bot_box[r] for r in bot_box if r not in set(movers)]
            allr = [r for r in (list(top_off.get(sheet, {}))
                                + list(bot_off.get(sheet, {})))
                    if r in pos and r in bbox_of]
            sum_area = sum((_eff_box(r, 0.0, 0.0)[2] - _eff_box(r, 0.0, 0.0)[0])
                           * (_eff_box(r, 0.0, 0.0)[3] - _eff_box(r, 0.0, 0.0)[1])
                           for r in allr) or 1.0
            chosen = 0.0
            for k in range(int(min(dist, 40.0) / STEP), 0, -1):
                shift = k * STEP
                ok = True
                shifted: dict[str, tuple[float, float]] = {}
                for r in movers:
                    nx, ny = pos[r][0] + ux * shift, pos[r][1] + uy * shift
                    bb = _eff_box(r, nx, ny)
                    if (bb[0] < EDGE_MARGIN or bb[1] < EDGE_MARGIN
                            or bb[2] > board_w - EDGE_MARGIN
                            or bb[3] > board_h - EDGE_MARGIN):
                        ok = False
                        break
                    hb = _halo(bb, PLACE_CLEAR / 2)
                    if _hit(hb, others) or _hit(hb, tht_boxes):
                        ok = False
                        break
                    shifted[r] = (nx, ny)
                if not ok:
                    continue
                xs0 = []
                ys0 = []
                xs1 = []
                ys1 = []
                for r in allr:
                    px, py = shifted.get(r, pos[r])
                    bb = _eff_box(r, px, py)
                    xs0.append(bb[0])
                    ys0.append(bb[1])
                    xs1.append(bb[2])
                    ys1.append(bb[3])
                if ((max(xs1) - min(xs0)) * (max(ys1) - min(ys0))
                        / sum_area) > DISP_CAP_L4:
                    continue
                chosen = shift
                break
            if chosen > 0.0:
                for r in movers:
                    nx, ny = (round(pos[r][0] + ux * chosen, 4),
                              round(pos[r][1] + uy * chosen, 4))
                    pos[r] = (nx, ny)
                    bot_box[r] = _halo(_eff_box(r, nx, ny), PLACE_CLEAR / 2)

    # LAW 6: seat every off-board connector AT the board edge — push it outward
    # (perpendicular to its edge) until its outermost PAD clears EDGE_PAD_CLEAR,
    # so the mouth/shell reaches/overhangs the edge and a cable actually mates
    # (user: "connectors at the absolute edge or they won't mate"). Only the
    # perpendicular axis moves; the along-edge position from the zone pack stays.
    # Connectors keep their exact (non-gridified) seat so the pad clearance holds.
    for ref, edge in zg.conn_edge.items():
        if ref not in resolvable or ref not in pos:
            continue
        pb = _rot_pad_bbox(resolvable[ref], fixed_rot.get(ref, 0.0),
                           side_of.get(ref, "top"))
        if pb is None:
            continue
        px0, py0, px1, py1 = pb
        x, y = pos[ref]
        if edge == "N":
            y = EDGE_PAD_CLEAR - py0
        elif edge == "S":
            y = board_h - EDGE_PAD_CLEAR - py1
        elif edge == "W":
            x = EDGE_PAD_CLEAR - px0
        elif edge == "E":
            x = board_w - EDGE_PAD_CLEAR - px1
        pos[ref] = (round(x, 4), round(y, 4))
        grid_placed.add(ref)

    fixed = set(mh_refs) | set(som_j_refs)

    insts: list[FootprintInst] = []
    placed = 0
    n_top = n_bottom = 0
    for ref in sorted(resolvable):
        sheet, footprint, value, lib = parts[ref]
        mod = resolvable[ref]
        bx, by = pos[ref]
        side = "top" if ref in fixed else side_of[ref]
        # pad -> net
        pad_nets: dict[str, tuple[int, str]] = {}
        for pad in pad_names(mod):
            pad_nets[pad] = pin_net.get((ref, pad), (0, ""))
        # subsystem parts carry a grid-snapped zone origin + the packer's RAW
        # offset (intra-zone clearance preserved — see STEP 3 above), so they are
        # NOT re-gridified here; only the fixed-position parts (mounting holes,
        # SoM receptacles) snap their absolute board position to the grid.
        if ref in grid_placed:
            fx, fy = round(ORIGIN_X + bx, 4), round(ORIGIN_Y + by, 4)
        else:
            fx, fy = _gridify(ORIGIN_X + bx), _gridify(ORIGIN_Y + by)
        insts.append(FootprintInst(
            ref=ref, value=value, footprint=footprint,
            x=fx, y=fy,
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side))
        placed += 1
        if side == "bottom":
            n_bottom += 1
        else:
            n_top += 1

    kx0, ky0, kx1, ky1 = keepout
    # SoM module-body CORE (board page frame, NO halo) — the rectangle the
    # plugged-in SoM physically covers. Grown SOM_CORE_CLEARANCE (3%, 1.5% each
    # side, centred) beyond the bare DF40 body span so the silk outline + the
    # keepout reserve a mating-clearance margin around the module (user request).
    # The placement_mech gate forbids any non-passive/test-point/tall part inside
    # it AND any carrier TOP-side part (the SoM's own bottom components occupy the
    # standoff gap) — LAW 6.
    _ccx = som.w * SOM_CORE_CLEARANCE / 2
    _ccy = som.h * SOM_CORE_CLEARANCE / 2
    som_core = (ORIGIN_X + plan.som_x - _ccx, ORIGIN_Y + plan.som_y - _ccy,
                ORIGIN_X + plan.som_x + som.w + _ccx,
                ORIGIN_Y + plan.som_y + som.h + _ccy)
    return PcbModel(
        board_w=board_w, board_h=board_h, insts=insts,
        net_numbers=net_numbers, netclass_of=netclass_of, classes=classes,
        placed=placed, deferred=deferred,
        som_keepout=(ORIGIN_X + kx0, ORIGIN_Y + ky0,
                     ORIGIN_X + kx1, ORIGIN_Y + ky1),
        n_top=n_top, n_bottom=n_bottom, two_side=two_side,
        som_core=som_core)
