"""STAGE-TEMPLATE placement engine — the datasheet-faithful intra-zone layout
for subsystems that carry a placement contract (Phase L, ``power`` pilot).

The intra-zone shelf packer sorts a subsystem's parts by footprint SIZE, so a
buck's hot-loop cap, its bulk caps and its whole FB divider scatter into a
value-sorted grid far from the IC (the measured Phase-L defect). This module
REPLACES that packer for a contracted subsystem: it DETERMINISTICALLY constructs
the datasheet layout (TI SNVSBD5D Fig 11-2 for the LM61460 bucks; the AP2112K
LDO) as rigid per-stage clusters, composes the stages left-to-right in
``stage_order``, and shelf-packs only the true leftovers (LEDs, test points,
strap parts) into the band below.

CONSUMES THE SAME DATA THE GATE READS. Pad centers come from the resolved
footprint via the gate's ``placement_contract_gate._pad_boxes`` — no hardcoded
coordinates, and the template adapts if a footprint revs. The template
constructs TIGHTER than the gate bound (e.g. hot-loop caps at ~0.4 mm when the
gate allows 1.0 mm) so the emitted board passes with margin; the gate — reading
the EMITTED board, never this module's intent — is the arbiter.

OUTPUT SHAPE == ``_pack_one_zone``: ``build_zone`` returns
``(top_off, bot_off, zone_w, zone_h)`` (or ``None`` to fall through to the legacy
packer), keyed on the same BOARD-unique refs, with the same ZONE_PAD margin and
rounding conventions, so the ``subsystem_zone_geometry`` hook is a drop-in. The
one thing the tuple cannot carry is the per-part PLACEMENT ROTATION the template
chooses for passives ({0,90,180,270} so a cap's pads face its target pins); the
hook passes a mutable ``rot_out`` dict that ``build_zone`` fills (bref -> extra
rotation), which ``build_model`` folds into ``zone_extra_rot`` — the SAME channel
LEVER-L1's 90-deg zone rotation already uses. See ``AI_LAYOUT_ROUTING_CONCEPT.md``
"Phase L / Engine-consumption design".

DETERMINISM: no randomness, no Date, no global mutation; a fixed part order and
rounded offsets, so two builds are byte-identical.
"""

from __future__ import annotations

import math
from pathlib import Path

from schgen.core.project import spec as _project_spec
from schgen.verify import placement_contract_gate as _g
from schgen.verify.fanout_gate import _is_cluster_passive, intelligent_need

from .constants import CONN_MATING_FACE, EDGE_PAD_CLEAR, TEMPLATE_CLEAR, ZONE_PAD
from .footprint import _footprint_bbox
from .footprint import has_thru_pads as _has_thru_pads
from .mating_face import _rot_bbox_cw, _rot_pad_bbox, connector_edge_rotation
from .placement import _shelf_pack

# Construction gaps (mm). Most placements are COURTYARD-clearance driven (part
# courtyard clears its neighbour by PLACE_CLEAR + the widen ``pad``), which lands
# the PAD-edge gaps comfortably inside the contract's gate bounds; only the two
# below are explicit body/pad gaps the courtyard rule does not cover.
_IND_BODY_GAP = 1.0        # inductor body -> IC courtyard, its pad toward SW
_LDO_GAP = 0.6             # LDO Cin/Cout -> its pins (gate bound 2.0)
_COUT_GAP = 1.0            # COUT cap column -> inductor output pad (gate bound 5.0)
_LEFTOVER_BAND_GAP = 2.0   # stage cluster -> leftover band (LAW-1 refdes headroom)
# Inter-stage gaps are CONSTRAINT-DERIVED per pair (v2), NOT a uniform widened gap.
# Two bucks sharing a row keep a small headroom gap (_INTERSTAGE_GAP0) for their
# FB<->foreign-SW isolation; a pair with NO foreign-SW constraint (buck|LDO — the
# LDO has neither an SW pad nor an inductor) collapses to the tight PLACE_CLEAR-
# grade gap below. v1 grew EVERY gap in lockstep, handing the LDO a needless
# buck-grade ~13 mm gap; per-pair gaps + the multi-row layout search recover it.
_INTERSTAGE_GAP0 = 6.0
_NONSW_STAGE_GAP = round(TEMPLATE_CLEAR + 0.7, 4)   # ~1.2 mm: a pair with no SW rule
# Row-wrap width budget (mm): the layout search prefers the fewest-rows layout that
# keeps the power ZONE width within this bound (acceptance: zone width <= 48 mm) AND
# satisfies foreign-SW. Two ~25 mm bucks WITH their COUT banks cannot share a row
# under this bound, so the search stacks one buck per row (LDO beside the last).
_ROW_WIDTH_BUDGET = 46.0
# Inter-ROW gap between two BUCK-bearing rows (mm). When the layout search stacks
# one buck per row (the L2/L3 shapes the power sheet selects), consecutive
# buck rows are otherwise separated only by the courtyard-grade TEMPLATE_CLEAR
# below, packing the two hot LM61460 ICs ~18 mm apart center-to-center. The three
# bucks share ONE In1 GND plane, so their self-heat superposes; widening the
# buck-to-buck ROW boundary spreads the two hottest dies (U20001/U20002) apart to
# thin the mutual-heating field WITHOUT touching any stage's internal topology
# (each buck's hot-loop cap / inductor / COUT bank / FB divider is unchanged), the
# power tree (shared +VIN_SYS input, +5V interstage rail), or the zone WIDTH (the
# board-inflating dimension). The extra separation runs ALONG the E edge as zone
# HEIGHT, which the E side-band absorbs (verified: emitted board dims + all gates).
# Applied ONLY at a buck|buck row boundary; a buck|LDO or LDO row boundary keeps
# the tight TEMPLATE_CLEAR (the LDO is cool, no benefit to spreading it).
_INTERROW_BUCK_GAP = 8.0


# --- local-frame primitives -------------------------------------------------------
# A "placed part" during construction is (bref, rot, side, ox, oy): its pad boxes
# in the stage-local frame are _pad_boxes(mod, rot) shifted by (ox, oy) — the
# transform is SIDE-INDEPENDENT (unified no-bottom-mirror convention). We
# reuse the gate's _pad_boxes so the geometry the template constructs is EXACTLY
# the geometry the gate later measures on the emitted board.


class _Part:
    __slots__ = ("bref", "mod", "rot", "side", "ox", "oy")

    def __init__(self, bref: str, mod: Path, rot: float, side: str,
                 ox: float, oy: float) -> None:
        self.bref = bref
        self.mod = mod
        self.rot = rot
        self.side = side
        self.ox = ox
        self.oy = oy

    def pad_boxes(self) -> dict[str, tuple[float, float, float, float]]:
        rel = _g._pad_boxes(self.mod, self.rot)
        return {n: (self.ox + b[0], self.oy + b[1], self.ox + b[2], self.oy + b[3])
                for n, b in rel.items()}

    def local_box(self) -> tuple[float, float, float, float]:
        """Courtyard bbox (rotation applied, SIDE-INDEPENDENT — the unified
        no-bottom-mirror convention) in the stage-local frame — the box used
        for overlap/extent (the SAME transform ``mating_face._inst_courtyard``
        applies to the emitted footprint)."""
        rb = _rot_bbox_cw(_footprint_bbox(self.mod), self.rot)
        return (self.ox + rb[0], self.oy + rb[1], self.ox + rb[2], self.oy + rb[3])


def _pad_half(mod: Path) -> tuple[float, float]:
    """Half width/height of a 2-pin passive's pad box at rot 0 (for gap solves)."""
    pb = _g._pad_boxes(mod, 0.0)
    b = next(iter(pb.values()))
    return (b[2] - b[0]) / 2.0, (b[3] - b[1]) / 2.0


def _crtyd_half(mod: Path, rot: float) -> tuple[float, float]:
    """Half width/height of the COURTYARD box after rotation — the extent the
    intra-zone overlap check reasons about (bigger than the pad box). Placing a
    part so its courtyard clears a neighbour by PLACE_CLEAR is collision-free by
    construction; the resulting PAD gap is smaller (courtyard overhangs the pads)
    and comfortably inside the pad-edge gate bounds."""
    rb = _rot_bbox_cw(_footprint_bbox(mod), rot)
    return (rb[2] - rb[0]) / 2.0, (rb[3] - rb[1]) / 2.0


def _pin_box(ic_boxes: dict[str, tuple], pins: list[str]
             ) -> tuple[float, float, float, float]:
    """Union bbox of the given IC pins (stage-local)."""
    boxes = [ic_boxes[p] for p in pins if p in ic_boxes]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _boxes_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float], halo: float) -> bool:
    return (a[0] - halo < b[2] and a[2] + halo > b[0]
            and a[1] - halo < b[3] and a[3] + halo > b[1])


# --- the buck stage ---------------------------------------------------------------

# The buck-stage RELATIVE geometry is identical for every LM61460 stage (same
# footprints, same pin map), so it is solved ONCE and reused: the CSP + widen
# search is the expensive step, and there are two bucks. Cached by a signature of
# (IC footprint, every member footprint in slot order, the pin map) -> per-slot
# (rot, ox, oy). Keyed on geometry only, never on the board refs — deterministic.
_BUCK_CACHE: dict[tuple, list[tuple[float, float, float]]] = {}


def _build_buck_stage(ic_bref: str, members: dict[str, str],
                      resolvable: dict[str, Path],
                      hf_caps: list[str], bulk_caps: list[str],
                      out_caps: list[str],
                      inductor: str, fb_members: list[str],
                      boot_cap: str, vcc_cap: str,
                      bias_r: str, bias_c: str, rt_r: str,
                      pins: dict[str, str]) -> list[_Part]:
    """Construct ONE LM61460 buck stage (SNVSBD5D Fig 11-2) as rigid local-frame
    parts. IC at (0,0) rot 0 top; every member top (same-side override). The widen
    loop grows whitespace until the layout is collision-free (rules never relax);
    the solved RELATIVE geometry is CACHED and reused for the identical second
    buck. Slot order (stable): IC, inductor, hf x2, bulk x2, out xN, FB xN, boot,
    vcc, bias_r, bias_c, rt. ``out_caps`` are the COUT bank (v2 bulk_out): seated
    just beyond the inductor's OUTPUT pad so the L->COUT->GND loop is short."""
    ic_mod = resolvable[ic_bref]
    slot_brefs = ([ic_bref, inductor, *hf_caps, *bulk_caps, *out_caps,
                   *fb_members, boot_cap, vcc_cap, bias_r, bias_c, rt_r])
    sig = (str(ic_mod), tuple(str(resolvable[b]) for b in slot_brefs),
           tuple(sorted(pins.items())))
    cached = _BUCK_CACHE.get(sig)
    if cached is not None:
        return [_Part(b, resolvable[b], rot, "top", ox, oy)
                for b, (rot, ox, oy) in zip(slot_brefs, cached, strict=True)]

    parts: list[_Part] = []
    for scale in range(0, 20):          # widen loop: grow gaps, never relax rules
        pad = scale * 0.25
        parts = _lay_buck(ic_bref, ic_mod, resolvable, hf_caps, bulk_caps,
                          out_caps, inductor, fb_members, boot_cap, vcc_cap,
                          bias_r, bias_c, rt_r, pins, pad)
        if not _any_overlap(parts):
            break
    # cache the relative geometry in the STABLE slot order (parts is built in the
    # same order _lay_buck appends, but re-key by bref to be order-robust)
    by_bref = {p.bref: p for p in parts}
    _BUCK_CACHE[sig] = [(by_bref[b].rot, by_bref[b].ox, by_bref[b].oy)
                        for b in slot_brefs]
    return parts


# The buck is built quadrant by quadrant around the QFN (SNVSBD5D Fig 11-2):
#   +X  the SW pad + inductor (the switch node)
#   +Y / -Y  the two VIN/PGND pin-pairs -> HF cap then bulk cap, outboard
#   -Y  also the BOOT pins (13/14) -> BOOT cap, at a different X than the HF cap
#   -X  the FB/AGND/VCC/BIAS pins -> FB cluster (mid), VCC (upper), BIAS (top),
#       marched leftward in courtyard-clearing columns so they never collide
#   +Y  bottom edge -> RT resistor, tucked below the IC left of the +Y HF cap
# Every "beside" placement clears the target courtyard by PLACE_CLEAR (+ the
# widen ``pad``); the resulting PAD-edge gaps are smaller and inside the bounds.

def _beside(mod: Path, rot: float, side: str,
            target: tuple[float, float, float, float],
            direction: str, gap: float,
            along_center: float | None = None) -> _Part:
    """Place a part's COURTYARD ``gap`` beyond the ``target`` box in ``direction``
    ('L','R','U','D' = -x,+x,-y,+y), centered on the target's perpendicular span
    (or ``along_center`` if given). Returns a _Part with no bref (caller sets it
    by rebuilding); here we return a bare part with bref='' the caller replaces."""
    hx, hy = _crtyd_half(mod, rot)
    tcx = (target[0] + target[2]) / 2.0
    tcy = (target[1] + target[3]) / 2.0
    if direction == "L":
        ox = target[0] - gap - hx
        oy = along_center if along_center is not None else tcy
    elif direction == "R":
        ox = target[2] + gap + hx
        oy = along_center if along_center is not None else tcy
    elif direction == "U":
        oy = target[1] - gap - hy
        ox = along_center if along_center is not None else tcx
    else:                                # "D"
        oy = target[3] + gap + hy
        ox = along_center if along_center is not None else tcx
    return _Part("", mod, rot, side, round(ox, 4), round(oy, 4))


def _rebref(p: _Part, bref: str) -> _Part:
    return _Part(bref, p.mod, p.rot, p.side, p.ox, p.oy)


def _lay_buck(ic_bref: str, ic_mod: Path, resolvable: dict[str, Path],
              hf_caps: list[str], bulk_caps: list[str], out_caps: list[str],
              inductor: str, fb_members: list[str], boot_cap: str, vcc_cap: str,
              bias_r: str, bias_c: str, rt_r: str, pins: dict[str, str],
              pad: float) -> list[_Part]:
    """One construction pass at extra whitespace ``pad`` (0 first, grows on retry).

    The SWPA8040 inductor is 9.6x8 mm — more than 2x the QFN's height — so it OWNS
    the +X lane and its Y-span brackets the IC. The small caps therefore sit in the
    top/bottom LANES clear of the inductor's left edge, and the BOOT/RT parts (whose
    pins are on the LEFT half of the top/bottom edges) are ROTATED 90 deg (narrow,
    1.46 mm across) so they nest beside the HF caps without a courtyard clash. The
    left side stacks FB/VCC/BIAS in Y-spaced columns. Gaps are courtyard-based (+
    the widen ``pad``) with a small extra margin so no boundary case tips into an
    overlap; the resulting PAD-edge gaps stay inside every gate bound."""
    ic = _Part(ic_bref, ic_mod, 0.0, "top", 0.0, 0.0)
    ib = ic.pad_boxes()
    icb = ic.local_box()
    parts: list[_Part] = [ic]

    m = 0.2                              # a hair of extra margin past PLACE_CLEAR
    clr = TEMPLATE_CLEAR + m + pad
    vin1, pgnd1 = pins["vin1"], pins["pgnd1"]
    vin2, pgnd2 = pins["vin2"], pins["pgnd2"]

    # ---- SW node: inductor to the RIGHT of the SW pad, body gap from courtyard --
    swb = ib[pins["sw"]]
    ind = _rebref(_beside(resolvable[inductor], 0.0, "top", icb, "R",
                          _IND_BODY_GAP + pad,
                          along_center=(swb[1] + swb[3]) / 2.0), inductor)
    parts.append(ind)
    ind_left = ind.local_box()[0]

    # ---- COUT bank (v2 bulk_out): a vertical column just beyond the inductor's
    # OUTPUT pad (pad 2, the +X/rightmost pad — pad 1 is the SW side toward the
    # IC). Each 0805 cap sits rot 0 (long axis horizontal) so its LEFT terminal
    # faces the output pad, centred on the pad's Y span, PLACE_CLEAR-stacked in Y.
    # This closes the L->COUT->GND loop tight (Fig 11-2) and keeps the COUT bank
    # inside the 5 mm gate bound while adding only ~1 cap-width to the stage. --
    for oc in _cout_column(resolvable, out_caps, ind.pad_boxes()[pins["ind_out"]],
                           pad):
        parts.append(oc)

    # ---- HOT-LOOP HF caps: pads face each VIN/PGND pair, outboard on the lane ----
    # centre on the pair midpoint; clamp so the right courtyard clears the inductor.
    hf1 = _hf_cap(resolvable[hf_caps[0]], ib, [vin1, pgnd1], "D", clr, ind_left,
                  hf_caps[0])
    hf2 = _hf_cap(resolvable[hf_caps[1]], ib, [vin2, pgnd2], "U", clr, ind_left,
                  hf_caps[1])
    parts += [hf1, hf2]

    # ---- BULK caps: outboard of each HF cap, ROTATED 90 (narrow in X) so the wide
    # 1206 body does NOT reach left into the top/bottom-LEFT region the BOOT/RT
    # parts need (the solver proved a left-spilling bulk over-subscribes that
    # region). Clamped so the right courtyard clears the inductor. <=5 mm to VIN. --
    bulk1 = bulk2 = None
    if len(bulk_caps) >= 1:
        bulk1 = _bulk_cap(resolvable[bulk_caps[0]], hf1, "D", clr, ind_left,
                          bulk_caps[0])
        parts.append(bulk1)
    if len(bulk_caps) >= 2:
        bulk2 = _bulk_cap(resolvable[bulk_caps[1]], hf2, "U", clr, ind_left,
                          bulk_caps[1])
        parts.append(bulk2)

    # ---- EDGE-PIN parts: BACKTRACKING assignment (bound-strict, collision-free) -
    # The QFN's LEFT/TOP/BOTTOM edges host FB(4)/VCC(2)/BIAS(1)/BOOT(13,14)/RT(6) +
    # the (free) BIAS resistor: nine small parts hug those pins on a 4x4 mm package.
    # A pure greedy is order-trapped here (FB steals VCC's only slots), so each part
    # gets a ranked list of candidate poses (rot in {0,90} on a fine LEFT/TOP/BOTTOM
    # grid, in-bound, off the +X inductor lane) and a DETERMINISTIC backtracking
    # search seats all nine mutually collision-free — the datasheet layout as a CSP.
    # If infeasible at this ``pad`` the widen loop grows spacing and retries (rules
    # never relax). Most-constrained-first (fewest candidate poses) speeds it.
    sw = pins["sw"]
    demands = [
        *[(m, [pins["fb"]], 3.0, [sw], 2.0) for m in fb_members],
        (vcc_cap, [pins["vcc"]], 2.0, None, 0.0),
        (boot_cap, [pins["rboot"], pins["cboot"]], 2.0, None, 0.0),
        (bias_c, [pins["bias"]], 3.0, None, 0.0),
        (rt_r, [pins["rt"]], 3.0, None, 0.0),
        (bias_r, [pins["bias"]], 20.0, None, 0.0),   # unbounded: nearest free pose
    ]
    seated = _seat_all(demands, resolvable, ib, icb, parts, pad)
    parts += seated
    return parts


def _hf_cap(mod: Path, ib: dict[str, tuple], pair: list[str], direction: str,
            gap: float, ind_left: float, bref: str) -> _Part:
    """A hot-loop HF cap outboard of ``pair`` (U=above -Y pair, D=below +Y pair),
    pushed as far +X as the inductor allows (right courtyard clears the inductor
    left edge by PLACE_CLEAR) but never left of the pair midpoint. Seating the HF
    (and its bulk) toward +X keeps the top/bottom-LEFT region CLEAR for the BOOT /
    RT parts whose pins are on the left half of those edges (the solver confirmed
    a left-stacked bulk over-subscribes that region)."""
    p = _beside(mod, 0.0, "top", _pin_box(ib, pair), direction, gap)
    hx, _hy = _crtyd_half(mod, 0.0)
    ox = ind_left - TEMPLATE_CLEAR - hx     # push fully +X (clamped by the inductor)
    return _Part(bref, mod, 0.0, "top", round(ox, 4), p.oy)


def _bulk_cap(mod: Path, hf: _Part, direction: str, gap: float,
              ind_left: float, bref: str) -> _Part:
    """A bulk input cap outboard of the HF cap (same lane), ROTATED 90 so its wide
    1206 body is NARROW in X and does not spill into the top/bottom-LEFT region.
    Right courtyard clamped to clear the inductor; X aligned to the HF cap."""
    hfb = hf.local_box()
    hx, hy = _crtyd_half(mod, 90.0)
    cy = (hfb[3] + gap + hy) if direction == "D" else (hfb[1] - gap - hy)
    ox = min(hf.ox, ind_left - TEMPLATE_CLEAR - hx)
    return _Part(bref, mod, 90.0, "top", round(ox, 4), round(cy, 4))


def _cout_column(resolvable: dict[str, Path], out_caps: list[str],
                 ind_out_box: tuple[float, float, float, float],
                 pad: float) -> list[_Part]:
    """The COUT bank as a vertical column just +X of the inductor's OUTPUT pad box
    ``ind_out_box`` (stage-local). Each cap is ROTATED 90 (long axis VERTICAL, so it
    is NARROW in X — 1.96 mm vs 3.4 mm for an 0805) with one terminal toward the pad;
    the caps stack in Y centred on the pad's Y midpoint, PLACE_CLEAR-separated, all
    at the same X (left courtyard clears the pad by ``_COUT_GAP`` + the widen
    ``pad``). Rot 90 keeps the stage — and thus the E-side interior zone's depth into
    the board — as narrow as possible while staying well inside the 5 mm bulk_out
    bound. The taller column runs in Y, which for this zone packs ALONG the edge."""
    if not out_caps:
        return []
    mods = [resolvable[c] for c in out_caps]
    halves = [_crtyd_half(m, 90.0) for m in mods]        # (hx, hy) rot 90
    hx = max(h[0] for h in halves)
    col_x = round(ind_out_box[2] + _COUT_GAP + pad + hx, 4)
    pad_cy = (ind_out_box[1] + ind_out_box[3]) / 2.0
    step = TEMPLATE_CLEAR + pad
    # total column height, then lay caps top->bottom centred on the pad Y.
    heights = [2 * h[1] for h in halves]
    total = sum(heights) + step * (len(out_caps) - 1)
    y = pad_cy - total / 2.0
    parts: list[_Part] = []
    for c, m, (_chx, chy) in zip(out_caps, mods, halves, strict=True):
        cy = y + chy
        parts.append(_Part(c, m, 90.0, "top", col_x, round(cy, 4)))
        y += 2 * chy + step
    return parts


_CAND_STEP = 0.5           # candidate-position grid step (mm) around a pin
_CAND_CAP = 400            # keep the N nearest in-bound poses per part (speed cap)

_Demand = tuple[str, "list[str] | None", float, "list[str] | None", float]
# a candidate pose carries its precomputed courtyard box (backtracking is then a
# pure box-overlap test — no footprint re-parse in the hot loop)
_Cand = tuple[_Part, tuple[float, float, float, float]]


def _candidates(bref: str, mod: Path, ib: dict[str, tuple],
                icb: tuple[float, float, float, float],
                target_pins: list[str] | None,
                bound: float, keep_pins: list[str] | None, keep_min: float,
                pad: float, skel_boxes: list[tuple[float, float, float, float]],
                forbid_plus_x: bool = True) -> list[_Cand]:
    """Up-to-_CAND_CAP nearest-target-first candidate poses for ``bref``: rot in
    {90,0} over a _CAND_STEP grid around the target, each meeting the pad-edge
    bound (+ keep-pin minimum) AND already clear of the skeleton (so the
    backtracking only tests peers). The courtyard box is precomputed.
    Deterministic tie-break.

    ``target_pins`` = the anchor pins the part hugs; None -> the anchor's WHOLE
    pad box (a proximity structure with no ``anchor_pins``), and the pad-edge
    bound is then measured to any anchor pad. ``forbid_plus_x`` (default True,
    the buck's +X inductor lane exclusion) is turned OFF for the generic
    proximity cluster (no inductor — parts may seat on all four sides of the
    anchor)."""
    if target_pins:
        tgt = _pin_box(ib, target_pins)
    else:
        # no anchor_pins -> centre the search on the whole anchor pad box and
        # measure the bound to ANY anchor pad.
        allb = list(ib.values())
        tgt = (min(b[0] for b in allb), min(b[1] for b in allb),
               max(b[2] for b in allb), max(b[3] for b in allb))
    tcx, tcy = (tgt[0] + tgt[2]) / 2.0, (tgt[1] + tgt[3]) / 2.0
    all_pins = list(ib) if not target_pins else target_pins
    n = int((9.0 + pad) / _CAND_STEP)
    halo = TEMPLATE_CLEAR + pad
    scored: list[tuple[float, float, float, _Part, tuple]] = []
    for rot in (90.0, 0.0):
        for gx in range(-n, n + 1):
            for gy in range(-n, n + 1):
                cx = round(tcx + gx * _CAND_STEP, 4)
                cy = round(tcy + gy * _CAND_STEP, 4)
                p = _Part(bref, mod, rot, "top", cx, cy)
                b = p.local_box()
                if forbid_plus_x and b[2] + halo > icb[2]:   # +X inductor lane
                    continue
                if _boxes_overlap(b, icb, halo):
                    continue
                if any(_boxes_overlap(b, s, halo) for s in skel_boxes):
                    continue
                d = _pins_to_target(p, ib, all_pins)
                eff = bound - _SNAP_EROSION if bound >= 5.0 else bound
                if d > eff:
                    continue
                if keep_pins and _pins_to_target(p, ib, keep_pins) < keep_min:
                    continue
                scored.append((round(d, 4), abs(cx), abs(cy), p, b))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3].rot))
    return [(p, b) for _d, _ax, _ay, p, b in scored[:_CAND_CAP]]


def _seat_all(demands: list[_Demand], resolvable: dict[str, Path],
              ib: dict[str, tuple], icb: tuple[float, float, float, float],
              skeleton: list[_Part], pad: float,
              forbid_plus_x: bool = True) -> list[_Part]:
    """Seat every demand collision-free by DETERMINISTIC backtracking over each
    part's ranked candidate poses (most-constrained variable first). Candidates
    are pre-cleared of the skeleton, so the search is a pure peer box-overlap test.
    If no full assignment exists at this ``pad`` it returns each part's nearest
    candidate (colliding) so the caller's widen loop retries — bounds never relax.
    ``forbid_plus_x`` (default True) keeps the buck's +X inductor-lane exclusion;
    the generic proximity cluster turns it OFF (all four sides available)."""
    halo = TEMPLATE_CLEAR + pad
    skel_boxes = [s.local_box() for s in skeleton]
    cand: dict[str, list[_Cand]] = {}
    for bref, tpins, bound, keep, kmin in demands:
        cand[bref] = _candidates(bref, resolvable[bref], ib, icb, tpins, bound,
                                 keep, kmin, pad, skel_boxes,
                                 forbid_plus_x=forbid_plus_x)
    order = sorted((d[0] for d in demands), key=lambda r: len(cand[r]))
    chosen: dict[str, tuple[float, float, float, float]] = {}
    picked: dict[str, _Part] = {}

    # DFS backtracking is worst-case O(len(cand) ** len(order)). When a template is
    # INFEASIBLE at this halo (e.g. the demanded gap exceeds what the candidate grid
    # can satisfy), the tree explodes and the build HANGS (a real 34-min hang was
    # caused by inflating a clearance into the template halo). A node budget bounds
    # the search: exhaust it -> treat as no-assignment -> the nearest-candidate
    # fallback below -> the caller's widen loop retries. Feasible templates solve in
    # a few hundred nodes, so the cap never changes a solvable layout (LAW 4: this
    # bounds effort, not the rules — bounds never relax).
    _NODE_BUDGET = 300_000
    nodes = [0]

    def _bt(i: int) -> bool:
        if i == len(order):
            return True
        nodes[0] += 1
        if nodes[0] > _NODE_BUDGET:
            return False        # search exploded -> infeasible -> fallback + widen
        bref = order[i]
        placed_boxes = list(chosen.values())
        for p, b in cand[bref]:
            if any(_boxes_overlap(b, q, halo) for q in placed_boxes):
                continue
            chosen[bref] = b
            picked[bref] = p
            if _bt(i + 1):
                return True
            del chosen[bref]
            del picked[bref]
        return False

    if _bt(0):
        return [picked[d[0]] for d in demands]
    return [(cand[d[0]][0][0] if cand[d[0]]
             else _Part(d[0], resolvable[d[0]], 90.0, "top", icb[0] - 1.0, 0.0))
            for d in demands]


def _pins_to_target(p: _Part, ib: dict[str, tuple],
                    target_pins: list[str]) -> float:
    """MIN pad-edge gap from ``p``'s pads to any of the target IC pins (the same
    measure the gate uses)."""
    best = 1e9
    pads = list(p.pad_boxes().values())
    for pin in target_pins:
        pb = ib.get(pin)
        if pb is None:
            continue
        for qb in pads:
            best = min(best, _g._box_gap(pb, qb))
    return best


# --- the generic proximity cluster (D10 / Decision D11 wiring) --------------------
# A subsystem whose contract carries ONLY ``proximity`` / ``same_side`` structures
# (no buck ``hot_loop``) is placed by anchoring its IC at the origin and seating
# every member with the SAME deterministic ranked-candidate backtracking the buck
# uses — honouring each proximity structure's ``max_mm`` (+ optional ``min_from``
# clearances) and courtyard clearance. There is no inductor lane to avoid, so the
# +X exclusion is OFF (members may seat on all four sides of the anchor). Widen-on-
# infeasible; deterministic; no randomness — the same discipline as the buck.

# solved RELATIVE geometry cache, keyed on (anchor fp, member fps in demand order,
# the demand bounds) — never on board refs, so it is deterministic + reusable.
_PROX_CACHE: dict[tuple, list[tuple[float, float, float]]] = {}


def _build_proximity_cluster(anchor_bref: str, contract: dict,
                             bref_of: dict[str, str],
                             resolvable: dict[str, Path]) -> list[_Part] | None:
    """Construct a proximity-only contract as rigid local-frame parts: the anchor
    IC at (0,0) rot 0 top, every member of every ``proximity`` structure seated by
    the backtracking search within its ``max_mm`` of the structure's anchor pins
    (or any anchor pad if none), respecting ``min_from`` clearances against the
    anchor's pins and courtyard clearance. Returns the placed parts, or None if a
    member/anchor ref does not resolve.

    ``bref_of`` maps a contract LIBRARY ref to the board ref on this sheet (already
    filtered to resolvable refs by the caller). Every member on the top side (the
    same_side override the hook applies before templating)."""
    anchor_mod = resolvable.get(anchor_bref)
    if anchor_mod is None:
        return None

    # collect the per-member demand from every proximity structure (stable order:
    # structure order in the contract, then member order within a structure).
    demands: list[_Demand] = []
    member_brefs: list[str] = []
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        if bref_of.get(st.get("anchor", "")) != anchor_bref:
            continue                       # a different anchor — not this cluster
        apins = st.get("anchor_pins")      # None -> any anchor pad
        bound = float(st["max_mm"])
        # min_from against an anchor PIN becomes the (keep_pins, keep_min) clause the
        # candidate generator already honours; a peer-part min_from is enforced by
        # the collision halo (every member clears every other by PLACE_CLEAR).
        keep_pins: list[str] | None = None
        keep_min = 0.0
        for mf in st.get("min_from", []):
            if bref_of.get(mf.get("part", "")) == anchor_bref and mf.get("pin"):
                keep_pins = [mf["pin"]]
                keep_min = float(mf.get("min_mm", 0.0))
                break
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is None or mb not in resolvable:
                return None
            demands.append((mb, list(apins) if apins else None, bound,
                            keep_pins, keep_min))
            member_brefs.append(mb)

    if not demands:
        # a same_side-only / empty contract: just the anchor (nothing to seat).
        return [_Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)]

    # cache signature: anchor fp + (member fp, bound) per demand, in order.
    sig = (str(anchor_mod),
           tuple((str(resolvable[d[0]]), round(d[2], 4),
                  tuple(d[1] or []), round(d[4], 4)) for d in demands))
    cached = _PROX_CACHE.get(sig)
    if cached is not None:
        anchor = _Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)
        return [anchor] + [
            _Part(mb, resolvable[mb], rot, "top", ox, oy)
            for mb, (rot, ox, oy) in zip(member_brefs, cached, strict=True)]

    # widen-on-infeasible loop: grow whitespace until the seat is collision-free
    # (rules never relax). The anchor is the sole skeleton; the +X lane is OFF.
    anchor = _Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)
    ib = anchor.pad_boxes()
    icb = anchor.local_box()
    seated: list[_Part] = []
    for scale in range(0, 20):
        pad = scale * 0.25
        seated = _seat_all(demands, resolvable, ib, icb, [anchor], pad,
                           forbid_plus_x=False)
        if not _any_overlap([anchor, *seated]):
            break
    parts = [anchor, *seated]
    by_bref = {p.bref: p for p in seated}
    _PROX_CACHE[sig] = [(by_bref[mb].rot, by_bref[mb].ox, by_bref[mb].oy)
                        for mb in member_brefs]
    return parts


# --- the general MULTI-ANCHOR contract solver -------------------------------------
# The single-anchor cluster above solves ONE star (an anchor + its direct members).
# A real contract is a MULTI-ANCHOR constraint GRAPH: a member of one proximity
# structure is the ANCHOR of the next (camera: J1->U1/U2, then U1->R1/R2/R3 with a
# min_from clearance against J1, then R1->R2/R3), and a ``min_from`` may name ANY
# part (not just the anchor's own pins). The single-anchor builder drops every
# non-primary-anchor member to the unconstrained leftover pack, silently violating
# those structures. This solver treats the WHOLE contract as a graph and seats
# every part in ONE global frame, honouring every ``proximity`` (pad-edge <= max_mm
# to the anchor's pins/pads) + every ``min_from`` (pad-edge >= min_mm from an
# arbitrary part) + same_side (all top) + courtyard clearance — the SAME measures
# the gate reads. It reuses the buck/cluster discipline exactly: ranked-candidate
# backtracking, widen-on-infeasible, no randomness, geometry-only cache.
_MULTI_CACHE: dict[tuple, list[tuple[str, float, float, float]]] = {}

# per-member constraint atoms parsed from the contract's proximity structures:
# _Attract = (anchor bref, pins|None, max_mm); _Repel = (part bref, pin|None, min_mm).
_Attract = tuple[str, "tuple[str, ...] | None", float]
_Repel = tuple[str, "str | None", float]

_ROOT_GAP = 2.0            # deterministic gap between two independent roots (mm)
_SEAT_SLIDE = 1.2          # edge-seat courtyard->pad-flush slide allowance (mm)
_SNAP_EROSION = 0.75       # GRID/2 origin snap + edge-band rounding slop (mm)
_OVEC = {"N": (0.0, -1.0), "S": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}
_GRID_MAX_N = 60           # cap the candidate grid half-extent (30 mm at _CAND_STEP)
# The FROZEN pilot proximity sheets (project spec) keep the legacy single-anchor
# cluster so their proven byte-identical layout never moves; every other proximity
# contract uses the general graph solver below.
_PILOT_PROX_SHEETS = _project_spec().pilot_prox_sheets


def _is_single_anchor_star(contract: dict, bref_of: dict[str, str]) -> bool:
    """True when the contract's ``proximity`` structures form ONE star the legacy
    single-anchor cluster already solves byte-identically: exactly one distinct
    RESOLVED proximity anchor, and no ``min_from`` naming a part OTHER than that
    anchor (the legacy path honours min_from only against the anchor's own pins).
    usb_pd (U1) and ethernet (T1) are single-anchor stars -> unchanged path."""
    anchors: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        a = bref_of.get(st.get("anchor", ""))
        if a is not None:
            anchors.add(a)
        for mf in st.get("min_from", []):
            mp = bref_of.get(mf.get("part", ""))
            if mp is not None and mp != a:
                return False          # cross-part clearance -> needs the graph solver
    return len(anchors) <= 1


def _topo_order(parts: set[str], deps: dict[str, set[str]]) -> list[str] | None:
    """Deterministic Kahn topological sort (ready set drained in ``sorted`` bref
    order, so the output is byte-stable). Returns None on a cycle (an ill-formed
    contract — the caller falls through to the legacy packer)."""
    indeg = {p: len(deps.get(p, set())) for p in parts}
    ready = sorted(p for p in parts if indeg[p] == 0)
    out: list[str] = []
    while ready:
        p = ready.pop(0)
        out.append(p)
        for q in sorted(parts):
            if p in deps.get(q, set()):
                indeg[q] -= 1
                if indeg[q] == 0:
                    ready.append(q)
        ready.sort()
    return out if len(out) == len(parts) else None


def _gcandidates(bref: str, mod: Path,
                 attractors: list[_Attract], repuls: list[_Repel],
                 placed: dict[str, _Part], pad: float,
                 forbid: list[tuple[float, float, float, float]] | None = None,
                 conn_roots: set[str] | None = None) -> list[_Part]:
    """Ranked candidate poses (rot in {90,0} on the _CAND_STEP grid) for ``bref``
    in the GLOBAL frame, each meeting EVERY attractor's pad-edge ``max_mm`` to its
    (already-placed) anchor's pins/pads, EVERY repulsor's pad-edge ``min_mm``, and
    already clear of every placed part's courtyard by the halo. The grid centres on
    the tightest (smallest-``max_mm``) attractor's target and its radius tracks that
    bound (capped), so the nearest in-bound poses come first. Deterministic
    tie-break; the same measure (``_pins_to_target`` == the gate's pad-edge gap)."""
    # per-attractor (anchor pad boxes, target pins, bound); primary = tightest bound
    att: list[tuple[dict[str, tuple], list[str], float]] = []
    for ab, apins, bound in attractors:
        pb = placed[ab].pad_boxes()
        att.append((pb, list(apins) if apins else list(pb), bound))
    prim = min(range(len(att)), key=lambda k: att[k][2])
    ppb, ppins, pbound = att[prim]
    tgt = _pin_box(ppb, ppins)
    tcx, tcy = (tgt[0] + tgt[2]) / 2.0, (tgt[1] + tgt[3]) / 2.0
    rep: list[tuple[dict[str, tuple], list[str], float]] = []
    for rb, rpin, mm in repuls:
        pb = placed[rb].pad_boxes()
        rep.append((pb, [rpin] if rpin else list(pb), mm))
    placed_boxes = [pp.local_box() for pp in placed.values()]
    halo = TEMPLATE_CLEAR + pad
    # FAN-OUT clearance (mirror fanout_gate exactly, single source of truth): a member
    # that is NOT a plain 2-pin decoupling passive (a diode, resistor network, shunt,
    # crystal, IC) must not crowd a placed multi-pin IC's escape apron — keep it
    # >= intelligent_need(pins) from every placed >=3-pin subject's courtyard. Plain
    # R/C/L decoupling is EXEMPT (it sits tight on pins by design). Without this the
    # solver ranks nearest-first and parks e.g. a gate-resistor network 0.56 mm off a
    # 20-pin driver, starving its fan-out (the ratchet regression). Since every such
    # member's contract max_mm exceeds its target IC's need, the [need, max_mm] band
    # is non-empty, so the contract still holds.
    member_pins = len(_g._pad_boxes(mod, 0.0))
    own_need = intelligent_need(member_pins)[0] if member_pins >= 3 else 0.0
    subjects: list[tuple[tuple[float, float, float, float], float]] = []
    for pp in placed.values():
        npins = len(_g._pad_boxes(pp.mod, 0.0))
        if npins >= 3 and not _is_cluster_passive(bref, member_pins):
            need = intelligent_need(npins)[0]
            if conn_roots and pp.bref in conn_roots:
                need += _SEAT_SLIDE
            subjects.append((pp.local_box(), need))
        # SYMMETRIC apron: a multi-pin member is itself a gate subject and
        # must keep its OWN need from every placed non-exempt crowder (the
        # shunt-anchored INA3221 landed 0.637 from its 2-pin shunt: RS is a
        # crowder, the IC was the subject, and only the reverse direction
        # was enforced).
        if own_need and not _is_cluster_passive(pp.bref, npins):
            subjects.append((pp.local_box(), own_need))
    # Grid radius must reach ANY target pad — a big connector's far edge pads (the
    # target box spans the whole part when anchor_pins is absent) — PLUS the bound
    # PLUS a body-slack so the member's pad can hug an inner pin from OUTSIDE the
    # courtyard (the same 9 mm slack the proven single-anchor _candidates uses). A
    # too-tight radius (bound only) can't reach an inner pin or a wide connector's
    # edge and yields zero candidates (the microsd/motor_sense infeasibility).
    t_half = max(tgt[2] - tgt[0], tgt[3] - tgt[1]) / 2.0
    n = min(int((t_half + pbound + 9.0 + pad) / _CAND_STEP), _GRID_MAX_N)
    scored: list[tuple[float, float, float, float, _Part]] = []
    for rot in (90.0, 0.0):
        for gx in range(-n, n + 1):
            for gy in range(-n, n + 1):
                cx = round(tcx + gx * _CAND_STEP, 4)
                cy = round(tcy + gy * _CAND_STEP, 4)
                p = _Part(bref, mod, rot, "top", cx, cy)
                b = p.local_box()
                if any(_boxes_overlap(b, q, halo) for q in placed_boxes):
                    continue
                if forbid and any(_boxes_overlap(b, f, halo) for f in forbid):
                    continue
                dsum = 0.0
                ok = True
                # the emit snaps each zone origin to GRID: a bound met with
                # zero margin in-zone can emerge 0.04 over on the board
                # (hdmi_tx J1->U1 5.04 vs 5.00, measured). Solve with half a
                # grid of allowance in BOTH directions so the snap can never
                # push a met bound over the line.
                for pb, pins, bound in att:
                    d = _pins_to_target(p, pb, pins)
                    eff = bound - _SNAP_EROSION if bound >= 5.0 else bound
                    if d > eff:
                        ok = False
                        break
                    dsum += d
                if not ok:
                    continue
                for pb, pins, mm in rep:
                    if _pins_to_target(p, pb, pins) < mm + (
                            _SNAP_EROSION if mm >= 5.0 else 0.0):
                        ok = False
                        break
                if not ok:
                    continue
                # fan-out: this non-passive member must clear every placed multi-pin
                # IC's escape apron (its courtyard by >= that IC's need).
                for sb, need in subjects:
                    if _boxes_overlap(b, sb, need):
                        ok = False
                        break
                if not ok:
                    continue
                scored.append((round(dsum, 4), abs(cx), abs(cy), rot, p))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return [t[4] for t in scored[:_CAND_CAP]]


def _seat_multi(order: list[str], roots: set[str],
                attractors: dict[str, list[_Attract]],
                repulsors: dict[str, list[_Repel]],
                resolvable: dict[str, Path], pad: float,
                conn_roots: set[str] | None = None,
                outer_vec: tuple[float, float] | None = None,
                root_rot: dict[str, float] | None = None
                ) -> dict[str, _Part] | None:
    """Seat the graph GREEDILY in topological order: roots (a connector/IC that
    anchors others) laid deterministically left-to-right, then each member placed at
    its BEST (nearest, deterministic) candidate against the already-committed
    upstream — honouring every attractor's max_mm + every repulsor's min_mm +
    courtyard clearance. No backtracking: the candidate GRID SCAN is the cost, so
    regenerating it per DFS node explodes (a real hang); topological order means each
    member's anchors are already fixed, so one nearest-first pick per part is a
    sound, fast greedy. A part with zero candidates returns None -> the caller's
    widen loop grows whitespace and retries (bounds never relax). Deterministic."""
    placed: dict[str, _Part] = {}
    # ROOT ROW AXIS (LAW 6): roots lay along the EDGE-PARALLEL axis (an E/W edge
    # runs vertically, so its connectors spread along Y; N/S along X — interior
    # sheets keep X). Two mating connectors on one sheet keep the CABLE gap
    # (motor_sense's XT60 pair overlapped at 0.00 when both sat at y=0 and the
    # edge-seat stacked them). Deterministic sorted order.
    _along_y = outer_vec is not None and abs(outer_vec[0]) > abs(outer_vec[1])
    cursor = 0.0
    prev_conn = False
    for r in sorted(roots):
        is_conn = bool(conn_roots and r in conn_roots)
        gap = _ROOT_GAP
        if prev_conn and is_conn:
            from schgen.generate.floorplan import CABLE_NEIGHBOR_GAP
            gap = CABLE_NEIGHBOR_GAP
        rr = (root_rot or {}).get(r, 0.0)
        p0 = _Part(r, resolvable[r], rr, "top", 0.0, 0.0)
        b0 = p0.local_box()
        if _along_y:
            d = round(cursor - b0[1], 4)
            p = _Part(r, resolvable[r], rr, "top", 0.0, d)
            cursor = p.local_box()[3] + TEMPLATE_CLEAR + pad + gap
        else:
            d = round(cursor - b0[0], 4)
            p = _Part(r, resolvable[r], rr, "top", d, 0.0)
            cursor = p.local_box()[2] + TEMPLATE_CLEAR + pad + gap
        placed[r] = p
        prev_conn = is_conn
    # LAW-6 OUTBOARD HALF-PLANE exclusion: the edge-seat slides each mating
    # connector flush to the board edge, so the zone's outer face must BE the
    # connector face — NOTHING may sit outboard of the innermost connector face
    # (members beside-but-outboard opened 11-23mm contract gaps when the seat
    # slid the connector away; leftover TPs in the slide path were crushed at
    # clr=0.000). Supersedes the earlier per-connector sweep corridor (subset).
    _sweeps: list[tuple[float, float, float, float]] = []
    if conn_roots and outer_vec is not None:
        _far = 1e4
        vx, vy = outer_vec
        faces = []
        for r in sorted(conn_roots):
            if r not in placed:
                continue
            pp = placed[r]
            # the SEAT's own pad kernel (shell/mounting tabs included) — the
            # gate kernel's signal-pad face sat 1.9mm short on HDMI shells.
            sb = _rot_pad_bbox(pp.mod, pp.rot)
            faces.append(pp.ox + sb[2] if vx > 0
                         else pp.ox + sb[0] if vx < 0
                         else pp.oy + sb[3] if vy > 0
                         else pp.oy + sb[1])
        if faces:
            face = min(faces) if (vx > 0 or vy > 0) else max(faces)
            face += -_SEAT_SLIDE if (vx > 0 or vy > 0) else _SEAT_SLIDE
            if vx > 0:
                _sweeps.append((face, -_far, _far, _far))
            elif vx < 0:
                _sweeps.append((-_far, -_far, face, _far))
            elif vy > 0:
                _sweeps.append((-_far, face, _far, _far))
            else:
                _sweeps.append((-_far, -_far, _far, face))
    for bref in order:
        if bref in roots:
            continue
        cands = _gcandidates(bref, resolvable[bref], attractors[bref],
                             repulsors.get(bref, []), placed, pad,
                             forbid=_sweeps or None, conn_roots=conn_roots)
        if not cands:
            return None
        placed[bref] = cands[0]
    return placed


def _solve_contract(contract: dict, bref_of: dict[str, str],
                    resolvable: dict[str, Path],
                    outer_dir: str | None = None) -> list[_Part] | None:
    """Solve a MULTI-ANCHOR proximity contract as one rigid, collision-free local-
    frame cluster satisfying every ``proximity`` (max_mm) + ``min_from`` (arbitrary
    part, min_mm) + same_side. Returns the placed parts in topological order, or
    None (a missing/unresolved anchor, a cyclic graph, or infeasible even after the
    widen loop) so the caller falls through to the legacy packer and the gate
    reports it. Deterministic; geometry-only cache keyed on footprints + bounds."""
    attractors: dict[str, list[_Attract]] = {}
    repulsors: dict[str, list[_Repel]] = {}
    all_parts: set[str] = set()
    members: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        a = bref_of.get(st.get("anchor", ""))
        if a is None or a not in resolvable:
            return None
        apins = tuple(st["anchor_pins"]) if st.get("anchor_pins") else None
        bound = float(st["max_mm"])
        mfs: list[tuple[str, str | None, float]] = []
        for mf in st.get("min_from", []):
            rp = bref_of.get(mf.get("part", ""))
            if rp is None or rp not in resolvable:
                continue
            mfs.append((rp, mf.get("pin"), float(mf.get("min_mm", 0.0))))
        all_parts.add(a)
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is None or mb not in resolvable:
                return None
            all_parts.add(mb)
            members.add(mb)
            attractors.setdefault(mb, []).append((a, apins, bound))
            for rp, pin, mm in mfs:
                repulsors.setdefault(mb, []).append((rp, pin, mm))
                all_parts.add(rp)
    if not members:
        return None

    # Connected components under (attractor + repulsor) edges. Each is an
    # independent rigid cluster (an anchor + everything that clusters around it).
    # Solving a component IN ISOLATION gives its members the full 360 deg around
    # their anchor; jamming a foreign root adjacent would steal exactly the space an
    # edge-pin bypass needs (the microsd VCCA-cap-vs-SD-slot infeasibility).
    adj: dict[str, set[str]] = {p: set() for p in all_parts}
    for m in members:
        for a, _p, _b in attractors.get(m, []):
            adj[m].add(a)
            adj[a].add(m)
        for rp, _pin, _mm in repulsors.get(m, []):
            adj[m].add(rp)
            adj[rp].add(m)
    comps: list[set[str]] = []
    seen: set[str] = set()
    for p in sorted(all_parts):
        if p in seen:
            continue
        stack, comp = [p], set()
        while stack:
            q = stack.pop()
            if q in seen:
                continue
            seen.add(q)
            comp.add(q)
            stack.extend(adj[q] - seen)
        comps.append(comp)

    _outer_vec = {"N": (0.0, -1.0), "S": (0.0, 1.0),
                  "E": (1.0, 0.0), "W": (-1.0, 0.0)}.get(outer_dir or "")
    _conn_roots = {r for r in (all_parts - members)
                   if resolvable[r].stem in CONN_MATING_FACE}
    # LAW 6: zone offsets are for the FINAL-ROTATED part (the legacy packer's
    # convention) — the board's conn_rot supplies the rotation, so the solver
    # must build the connector's geometry AT that rotation or every solved
    # adjacency shatters when placement rotates it (camera's W-edge FFC turned
    # 90 deg: terms 3.7mm from the jack, TPs in the slide path).
    _root_rot = {r: connector_edge_rotation(
                     CONN_MATING_FACE[resolvable[r].stem], outer_dir)
                 for r in _conn_roots} if outer_dir else {}

    sig = (outer_dir or "",
           tuple(sorted(_root_rot.items())),
           tuple((b, str(resolvable[b])) for b in sorted(all_parts)),
           tuple((m, tuple((a, p or (), round(bd, 4))
                           for a, p, bd in attractors.get(m, [])),
                  tuple((r, pn or "", round(mm, 4))
                        for r, pn, mm in repulsors.get(m, [])))
                 for m in sorted(members)))
    cached = _MULTI_CACHE.get(sig)
    if cached is not None:
        return [_Part(b, resolvable[b], rot, "top", ox, oy)
                for b, rot, ox, oy in cached]

    clusters: list[list[_Part]] = []
    for comp in sorted(comps, key=sorted):
        cl = _solve_component(comp, members, attractors, repulsors, resolvable,
                              conn_roots=_conn_roots, outer_vec=_outer_vec,
                              root_rot=_root_rot)
        if cl is None:
            return None
        clusters.append(cl)
    parts = _compose_clusters(clusters, conn_roots=_conn_roots,
                              outer_vec=_outer_vec)
    _MULTI_CACHE[sig] = [(p.bref, p.rot, p.ox, p.oy) for p in parts]
    return parts


def _solve_component(comp: set[str], members: set[str],
                     attractors: dict[str, list[_Attract]],
                     repulsors: dict[str, list[_Repel]],
                     resolvable: dict[str, Path],
                     conn_roots: set[str] | None = None,
                     outer_vec: tuple[float, float] | None = None,
                     root_rot: dict[str, float] | None = None
                     ) -> list[_Part] | None:
    """Seat ONE connected component (a root anchor + everything clustering around
    it) as a rigid collision-free cluster: root(s) at the origin, every member
    DFS-seated around its in-component anchors honouring each attractor/repulsor,
    widen-on-infeasible. Returns the placed parts (topological order) or None."""
    members_c = comp & members
    roots_c = comp - members_c
    deps: dict[str, set[str]] = {p: set() for p in comp}
    for m in members_c:
        for a, _p, _b in attractors.get(m, []):
            if a in comp:
                deps[m].add(a)
        for rp, _pin, _mm in repulsors.get(m, []):
            if rp in comp:
                deps[m].add(rp)
        deps[m].discard(m)
    order = _topo_order(comp, deps)
    if order is None:
        return None
    for scale in range(0, 24):
        placed = _seat_multi(order, roots_c, attractors, repulsors,
                             resolvable, scale * 0.25,
                             conn_roots=(conn_roots or set()) & comp,
                             outer_vec=outer_vec, root_rot=root_rot)
        if placed is None:
            continue
        parts = [placed[b] for b in order]
        if not _any_overlap(parts):
            return parts
    return None


def _compose_clusters(clusters: list[list[_Part]],
                      conn_roots: set[str] | None = None,
                      outer_vec: tuple[float, float] | None = None
                      ) -> list[_Part]:
    """Lay independent solved clusters along the EDGE-PARALLEL axis (X for
    interior/N/S sheets, Y for E/W), each normalised and clearance-separated —
    collision-free by construction. On an EDGE sheet every cluster's mating-
    connector OUTER face is additionally ALIGNED to the common outer line, and
    conn-bearing neighbours keep the CABLE gap, so the composed zone presents
    ONE flush connector face for the edge-seat (slide ~= 0, contract adjacency
    preserved). Single-cluster zones are re-anchored only."""
    along_y = outer_vec is not None and abs(outer_vec[0]) > abs(outer_vec[1])
    vx, vy = outer_vec if outer_vec is not None else (0.0, 0.0)
    out: list[_Part] = []
    cursor = 0.0
    prev_conn = False
    placed_clusters: list[list[_Part]] = []
    for cl in clusters:
        has_conn = bool(conn_roots and any(p.bref in conn_roots for p in cl))
        gap = _ROOT_GAP
        if prev_conn and has_conn:
            from schgen.generate.floorplan import CABLE_NEIGHBOR_GAP
            gap = CABLE_NEIGHBOR_GAP
        minx = min(p.local_box()[0] for p in cl)
        miny = min(p.local_box()[1] for p in cl)
        if along_y:
            height = max(p.local_box()[3] for p in cl) - miny
            moved = [_Part(p.bref, p.mod, p.rot, "top",
                           round(p.ox - minx, 4),
                           round(p.oy - miny + cursor, 4)) for p in cl]
            cursor += height + TEMPLATE_CLEAR + gap
        else:
            width = max(p.local_box()[2] for p in cl) - minx
            moved = [_Part(p.bref, p.mod, p.rot, "top",
                           round(p.ox - minx + cursor, 4),
                           round(p.oy - miny, 4)) for p in cl]
            cursor += width + TEMPLATE_CLEAR + gap
        placed_clusters.append(moved)
        prev_conn = has_conn
    # OUTER-FACE ALIGNMENT: shift each conn-bearing cluster along the outer axis
    # so every connector face sits on the common outermost line.
    if conn_roots and outer_vec is not None:
        def _face(cl: list[_Part]) -> float | None:
            fs = []
            for p in cl:
                if p.bref not in conn_roots:
                    continue
                sb = _rot_pad_bbox(p.mod, p.rot)
                fs.append(p.ox + sb[2] if vx > 0
                          else p.ox + sb[0] if vx < 0
                          else p.oy + sb[3] if vy > 0
                          else p.oy + sb[1])
            if not fs:
                return None
            return max(fs) if (vx > 0 or vy > 0) else min(fs)
        faces = [f for f in (_face(cl) for cl in placed_clusters)
                 if f is not None]
        if faces:
            target = max(faces) if (vx > 0 or vy > 0) else min(faces)
            for i, cl in enumerate(placed_clusters):
                f = _face(cl)
                if f is None:
                    continue
                d = round(target - f, 4)
                if d:
                    placed_clusters[i] = [
                        _Part(p.bref, p.mod, p.rot, "top",
                              round(p.ox + (d if vx else 0.0), 4),
                              round(p.oy + (d if vy else 0.0), 4))
                        for p in cl]
            # clusters WITHOUT a connector must stay INBOARD of the aligned
            # pad line — normalising them to 0 left an LDO cluster outboard
            # of it, and the seat-line shift dragged its cap off-board
            # (C16002, 1.0mm past Edge.Cuts, measured).
            inline = round(target + (_SEAT_SLIDE if (vx < 0 or vy < 0)
                                     else -_SEAT_SLIDE), 4)
            for i, cl in enumerate(placed_clusters):
                if _face(cl) is not None:
                    continue
                if vx > 0:
                    e = max(p.local_box()[2] for p in cl)
                    d = min(0.0, round(inline - e, 4))
                elif vx < 0:
                    e = min(p.local_box()[0] for p in cl)
                    d = max(0.0, round(inline - e, 4))
                elif vy > 0:
                    e = max(p.local_box()[3] for p in cl)
                    d = min(0.0, round(inline - e, 4))
                else:
                    e = min(p.local_box()[1] for p in cl)
                    d = max(0.0, round(inline - e, 4))
                if d:
                    placed_clusters[i] = [
                        _Part(p.bref, p.mod, p.rot, "top",
                              round(p.ox + (d if vx else 0.0), 4),
                              round(p.oy + (d if vy else 0.0), 4))
                        for p in cl]
    for cl in placed_clusters:
        out.extend(cl)
    return out


# --- the LDO stage ----------------------------------------------------------------

def _build_ldo_stage(ic_bref: str, resolvable: dict[str, Path],
                     cin: str, cin_pin: str, cout: str, cout_pin: str
                     ) -> list[_Part]:
    """AP2112K LDO with Cin/Cout at its VIN/VOUT pins (<= gate bound 2.0)."""
    ic_mod = resolvable[ic_bref]
    for scale in range(0, 12):
        pad = scale * 0.25
        ic = _Part(ic_bref, ic_mod, 0.0, "top", 0.0, 0.0)
        ib = ic.pad_boxes()
        parts = [ic]
        for cap, pin, sgn in ((cin, cin_pin, -1), (cout, cout_pin, +1)):
            mod = resolvable[cap]
            hx, _hy = _pad_half(mod)
            pb = ib[pin]
            cy = (pb[1] + pb[3]) / 2.0
            if sgn < 0:                  # Cin to the LEFT of the VIN pin
                cx = pb[0] - _LDO_GAP - pad - hx
            else:                        # Cout to the RIGHT of the VOUT pin
                cx = pb[2] + _LDO_GAP + pad + hx
            parts.append(_Part(cap, mod, 0.0, "top", round(cx, 4), round(cy, 4)))
        if not _any_overlap(parts):
            return parts
    return parts


# --- overlap + extents ------------------------------------------------------------

def _any_overlap(parts: list[_Part]) -> bool:
    boxes = [(p.bref, p.local_box()) for p in parts]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _boxes_overlap(boxes[i][1], boxes[j][1], TEMPLATE_CLEAR):
                return True
    return False


def _stage_extent(parts: list[_Part]) -> tuple[float, float, float, float]:
    xs0 = [p.local_box()[0] for p in parts]
    ys0 = [p.local_box()[1] for p in parts]
    xs1 = [p.local_box()[2] for p in parts]
    ys1 = [p.local_box()[3] for p in parts]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


# --- the public entry -------------------------------------------------------------

def contract_member_brefs(sheet_name: str, contract: dict,
                          resolvable: dict[str, Path]) -> set[str]:
    """BOARD-unique refs of every contract MEMBER (the union of ``roles`` keys —
    which already list every stage part — mapped through the per-sheet band).
    Used by the hook to force ``side_of[member]="top"`` (the same_side override)
    before templating, so the 2-side classifier and later L4 see the override.
    Only refs present on this sheet (resolvable) are returned."""
    lib2board = _g._board_refs_by_sheet(sheet_name)
    out: set[str] = set()
    for lib in contract.get("roles", {}):
        b = lib2board.get(lib)
        if b is not None and b in resolvable:
            out.add(b)
    return out


def build_zone(sheet_name: str, contract: dict, refs: list[str],
               side_of: dict[str, str],
               bbox_of: dict[str, tuple[float, float, float, float]],
               resolvable: dict[str, Path],
               rot_out: dict[str, float] | None = None,
               facing: str | None = None,
               outer_dir: str | None = None
               ) -> tuple[dict[str, tuple[float, float]],
                          dict[str, tuple[float, float]],
                          float, float] | None:
    """Construct the datasheet layout for a contracted subsystem and return the
    ``_pack_one_zone`` 4-tuple ``(top_off, bot_off, zone_w, zone_h)`` (keyed on
    BOARD-unique refs), or ``None`` to fall through to the legacy packer.

    ``rot_out`` (optional; the hook passes a live dict) is filled bref -> extra
    placement rotation for every constructed member — the SAME channel LEVER-L1
    uses (folded into ``zone_extra_rot`` by ``build_model``). This is the one
    piece the 4-tuple cannot carry (see the module docstring); the ``build_zone``
    positional signature is unchanged, so the hook stays a drop-in.

    ``facing`` (optional; N/E/S/W) is the zone-local direction the DOWNSTREAM zone
    lies in (the hook derives it from the floorplan — the ``power_som``/SoM flow
    direction, i.e. the board INTERIOR). After the column is composed (output/COUT
    edge toward +X by construction), a size-preserving 180-deg whole-zone TURN is
    applied when it makes the OUTPUT-role (bulk_out) parts face the ``facing``
    direction — so the composition-level FLOW gate's FACING check passes. A turn
    is a rigid {0,90,180,270} operation on every part (legal for every footprint,
    same side), and preserves the zone bounding box, so the floorplan block size
    is unchanged.

    DISPATCH (D11 wiring): a BUCK-STAGE contract (has a ``hot_loop`` structure —
    the power/power_som pattern) takes the existing datasheet-stage path below; a
    PROXIMITY-ONLY contract (only ``proximity``/``same_side`` structures — e.g.
    usb_pd's FUSB302B bypass/CC-filter network) is built by the generic
    proximity-cluster builder (:func:`_build_proximity_zone`). An unrecognised
    contract returns None (falls through to the legacy packer)."""
    if contract is None:
        return None
    rot_out = rot_out if rot_out is not None else {}
    _types = {st.get("type") for st in contract.get("structures", [])}
    if "hot_loop" not in _types:
        # not a buck-stage contract. A proximity-bearing contract -> the generic
        # cluster builder; anything else falls through to the legacy packer.
        if "proximity" in _types:
            return _build_proximity_zone(
                sheet_name, contract, refs, side_of, bbox_of, resolvable,
                rot_out, facing=facing, outer_dir=outer_dir)
        return None

    # LIBRARY ref -> BOARD ref for this sheet (same band the gate/netlist use).
    lib2board = _g._board_refs_by_sheet(sheet_name)
    board_set = set(refs)

    def bref(lib: str) -> str | None:
        b = lib2board.get(lib)
        return b if (b is not None and b in board_set and b in resolvable) else None

    roles = contract.get("roles", {})
    structs = contract.get("structures", [])
    order = contract.get("stage_order", [])

    # collect per-IC structure data from the contract (existential caps etc.)
    def _find(typ: str, ic: str) -> dict | None:
        for st in structs:
            if st.get("type") == typ and st.get("ic") == ic:
                return st
        return None

    # LM61460 pin map (shared) — read from the FIRST buck's structures. The
    # ``ind_out`` entry is the INDUCTOR's output pad (bulk_out.inductor_out_pin),
    # keyed here so _lay_buck can seat the COUT bank at it; it is an inductor pad,
    # not an IC pin, but lives in the same map for a single threaded lookup.
    def _buck_pins(ic: str) -> dict[str, str]:
        hl = _find("hot_loop", ic)
        sw = _find("sw_node", ic)
        fb = _find("fb_cluster", ic)
        boot = _find("boot", ic)
        vcc = _find("vcc_cap", ic)
        bias = _find("bias_cap", ic)
        rt = _find("rt_r", ic)
        bo = _find("bulk_out", ic)
        return {
            "vin1": hl["pin_pairs"][0][0], "pgnd1": hl["pin_pairs"][0][1],
            "vin2": hl["pin_pairs"][1][0], "pgnd2": hl["pin_pairs"][1][1],
            "sw": sw["sw_pin"], "fb": fb["fb_pin"],
            "rboot": boot["pins"][0], "cboot": boot["pins"][1],
            "vcc": vcc["pin"], "bias": bias["pin"], "rt": rt["pin"],
            "ind_out": bo["inductor_out_pin"] if bo else "2",
        }

    # bias RESISTORs are declared only in ``roles`` (not in a structure); collect
    # them in the roles' declaration order and consume one per buck stage in
    # stage_order — deterministic, and the v1 roles dict is stage-grouped.
    bias_r_libs = [k for k, v in roles.items() if v == "bias_r"]
    bias_r_iter = iter(bias_r_libs)

    # --- build every stage in its own local frame -----------------------------
    stages: list[list[_Part]] = []
    stage_kind: list[str] = []
    for ic in order:
        ic_b = bref(ic)
        if ic_b is None:
            return None                      # contract ref missing -> fall through
        role = roles.get(ic, "")
        if role == "buck_ic":
            hl = _find("hot_loop", ic)
            bulk = _find("bulk_in", ic)
            bulk_o = _find("bulk_out", ic)
            sw = _find("sw_node", ic)
            fb = _find("fb_cluster", ic)
            boot = _find("boot", ic)
            vcc = _find("vcc_cap", ic)
            bias = _find("bias_cap", ic)
            rt = _find("rt_r", ic)
            # library refs -> board refs (all must resolve on this sheet)
            hf = [bref(c) for c in hl["caps"]]
            bulk_c = [bref(c) for c in bulk["caps"]]
            out_c = [bref(c) for c in bulk_o["caps"]] if bulk_o else []
            ind = bref(sw["inductor"])
            fbm = [bref(m) for m in fb["members"]]
            boot_c = bref(boot["cap"])
            vcc_c = bref(vcc["cap"])
            # BIAS: the bias_cap is a structure; the bias_r is only in ``roles``,
            # consumed in declaration order (one per buck stage — see above).
            bias_r_lib = next(bias_r_iter, None)
            bias_r_b = bref(bias_r_lib) if bias_r_lib else None
            bias_c = bref(bias["cap"])
            rt_b = bref(rt["resistor"])
            need = hf + bulk_c + out_c + [ind, boot_c, vcc_c, bias_r_b, bias_c,
                                          rt_b] + fbm
            if any(x is None for x in need):
                return None
            pins = _buck_pins(ic)
            parts = _build_buck_stage(
                ic_b, roles, resolvable, hf, bulk_c, out_c, ind, fbm,
                boot_c, vcc_c, bias_r_b, bias_c, rt_b, pins)
            stages.append(parts)
            stage_kind.append("buck")
        elif role == "ldo_ic":
            ldo = _find("ldo_stage", ic)
            cin, cout = bref(ldo["cin"]), bref(ldo["cout"])
            if cin is None or cout is None:
                return None
            parts = _build_ldo_stage(ic_b, resolvable, cin, ldo["cin_pin"],
                                     cout, ldo["cout_pin"])
            stages.append(parts)
            stage_kind.append("ldo")
        else:
            return None

    # generic proximity members join their anchor IC's STAGE FRAME before the
    # row composer runs — post-compose the pin region is packed solid and the
    # greedy finds no candidate (power_som's EN clamp trio measured 13-15mm in
    # the leftover band against an authored 3mm).
    _stage_of = {p.bref: si for si, sp in enumerate(stages) for p in sp}
    # tightest authored bound per board ref (movability: a part is displaceable
    # for a TIGHTER member iff its own slack allows re-solving it elsewhere).
    _bound_of: dict[str, float] = {}
    _att_of: dict[str, list] = {}
    _rep_of: dict[str, list] = {}
    for st in structs:
        _t = st.get("type")
        if _t == "proximity":
            _a = bref(st.get("anchor", ""))
            _mm = float(st.get("max_mm", 0.0) or 0.0)
            if _a is None or _mm <= 0.0:
                continue
            _ap = st.get("anchor_pins")
            for _ml in st.get("members", []):
                _mb = bref(_ml)
                if _mb is not None and _mm < _bound_of.get(_mb, 1e9):
                    _bound_of[_mb] = _mm
                    _att_of[_mb] = [(_a, tuple(_ap) if _ap else None, _mm)]
                    _rep_of[_mb] = []
            continue
        # typed recipe structures, translated to the same (anchor, pins,
        # bound) form so displacement can re-solve their members faithfully.
        _spec = {"fb_cluster": ("members", "fb_pin", "max_to_fb_mm"),
                 "rt_r": ("resistor", "pin", "max_pad_to_pin_mm"),
                 "bias_cap": ("cap", "pin", "max_pad_to_pin_mm"),
                 "boot": ("cap", "pins", "max_pad_to_pin_mm"),
                 "vcc_cap": ("cap", "pin", "max_pad_to_pin_mm")}.get(_t)
        if _spec is None:
            continue
        _mk, _pk, _bk = _spec
        _ic = bref(st.get("ic", ""))
        _mm = float(st.get(_bk, 0.0) or 0.0)
        if _ic is None or _mm <= 0.0:
            continue
        _pins = st.get(_pk)
        _pins = tuple(_pins) if isinstance(_pins, list) else (_pins,)
        _mls = st.get(_mk)
        _mls = _mls if isinstance(_mls, list) else [_mls]
        _rep = []
        if _t == "fb_cluster":
            _msw = float(st.get("min_to_own_sw_mm", 0.0) or 0.0)
            if _msw > 0.0:
                if st.get("own_sw_pin"):
                    _rep.append((_ic, st["own_sw_pin"], _msw))
                _ol = bref(st.get("own_inductor", ""))
                if _ol is not None:
                    _rep.append((_ol, None, _msw))
        for _ml in _mls:
            _mb = bref(_ml)
            if _mb is not None and _mm < _bound_of.get(_mb, 1e9):
                _bound_of[_mb] = _mm
                _att_of[_mb] = [(_ic, _pins, _mm)]
                _rep_of[_mb] = _rep

    def _try_place(mb, att, frame, rep=()):
        rep = [r for r in rep if r[0] in frame]
        for wpad in (0.0, 0.5, 1.0):
            cands = _gcandidates(mb, resolvable[mb], att, list(rep), frame,
                                 wpad)
            if cands:
                return cands[0]
        return None

    for st in structs:
        if st.get("type") != "proximity":
            continue
        ab = bref(st.get("anchor", ""))
        si = _stage_of.get(ab)
        bound = float(st.get("max_mm", 0.0) or 0.0)
        if si is None or bound <= 0.0:
            continue
        apins = st.get("anchor_pins")
        att = [(ab, tuple(apins) if apins else None, bound)]
        for mlib in st.get("members", []):
            mb = bref(mlib)
            if mb is None or mb in _stage_of or mb not in resolvable:
                continue
            frame = {p.bref: p for p in stages[si]}
            got = _try_place(mb, att, frame)
            if got is None:
                # BOUND-PRIORITY DISPLACEMENT: the recipe ringed the anchor
                # with slacker-bound parts (fb/rt at 5-10mm squatting the EN
                # clamp's 3mm ring — priority inversion, measured). Evict the
                # slackest ring part that can re-solve within ITS OWN bound,
                # then retry; restore on any failure.
                ring = [r for r in frame
                        if r != ab and _bound_of.get(r, 0.0) >= bound
                        and r in _att_of
                        and len(_g._pad_boxes(frame[r].mod, 0.0)) <= 2]
                ring.sort(key=lambda r: (-_bound_of[r], r))
                for victim in ring:
                    f2 = dict(frame)
                    f2.pop(victim)
                    got2 = _try_place(mb, att, f2)
                    if got2 is None:
                        continue
                    f2[mb] = got2
                    back = _try_place(victim, _att_of[victim], f2,
                                      _rep_of.get(victim, ()))
                    if back is None:
                        continue
                    stages[si] = [*(p for p in stages[si]
                                    if p.bref != victim), got2, back]
                    _stage_of[mb] = si
                    got = got2
                    break
            else:
                stages[si] = [*stages[si], got]
                _stage_of[mb] = si

    # --- compose stages into ROWS (multi-row layout search, v2) ----------------
    # v1 laid every stage in ONE left->right row with the 2nd buck MIRRORED (FB
    # faces +X, away from stage-1's SW) and grew a UNIFORM inter-stage gap until the
    # foreign-SW isolation held. Two bucks WITH their COUT banks are ~25 mm wide
    # EACH, so side-by-side they blow the <=48 mm zone-width bound (and the LDO in
    # the same row pushed v1 to 65 mm). v2 searches a small set of ROW LAYOUTS and
    # picks the FIRST that (a) keeps the zone width within _ROW_WIDTH_BUDGET and
    # (b) still satisfies foreign-SW (verified on the composed pad boxes — the rule
    # is NEVER relaxed; we place better instead, LAW 4). Candidates, cheapest first:
    #   L0  single row  [U1 U2 U3]         (v1 shape; fits only if narrow enough)
    #   L1  bucks row0, LDO wraps to row1  [U1 U2] / [U3]
    #   L2  one buck per row               [U1] / [U2 U3]  (LDO beside U2)
    #   L3  one stage per row              [U1] / [U2] / [U3]
    # A buck is NEVER mirrored when it is alone on its row (its FB already faces -X,
    # away from the other buck's SW on the far side of the zone); the mirror is used
    # ONLY for two bucks sharing a row (candidate L0), exactly as v1.
    def _has_sw(si: int) -> bool:
        return stage_kind[si] == "buck"

    def _mirror_stage(parts: list[_Part]) -> list[_Part]:
        """180-deg turn of a whole stage about its extent center (+180 to each part
        rotation), preserving every intra-stage relationship. Legal for every
        footprint (all placed at {0,90,180,270})."""
        ext = _stage_extent(parts)
        sp: list[_Part] = []
        for p in parts:
            nrot = (p.rot + 180.0) % 360.0
            nb = _g._pad_boxes(p.mod, nrot)
            ob = _g._pad_boxes(p.mod, p.rot)
            ocx = p.ox + (min(b[0] for b in ob.values())
                          + max(b[2] for b in ob.values())) / 2.0
            ocy = p.oy + (min(b[1] for b in ob.values())
                          + max(b[3] for b in ob.values())) / 2.0
            ecx = (ext[0] + ext[2]) / 2.0
            ecy = (ext[1] + ext[3]) / 2.0
            ncx = 2 * ecx - ocx
            ncy = 2 * ecy - ocy
            nhx = (min(b[0] for b in nb.values())
                   + max(b[2] for b in nb.values())) / 2.0
            nhy = (min(b[1] for b in nb.values())
                   + max(b[3] for b in nb.values())) / 2.0
            sp.append(_Part(p.bref, p.mod, nrot, p.side,
                            round(ncx - nhx, 4), round(ncy - nhy, 4)))
        return sp

    def _lay(layout: list[list[int]], mirror: set[int]) -> dict[str, _Part]:
        """Compose a ROW LAYOUT (``layout`` = list of rows, each a list of stage
        indices in left->right order); stages in ``mirror`` are 180-turned. Each row
        packs left->right at a common Y baseline, PLACE_CLEAR-stacked below the
        previous row. Same-row adjacent stages are separated by a courtyard-grade
        gap (buck|buck a hair wider for the FB isolation headroom; buck|LDO tight).
        Returns bref -> absolute _Part in the zone-local frame."""
        frames = [
            _mirror_stage(stages[si]) if si in mirror
            else [_Part(p.bref, p.mod, p.rot, p.side, p.ox, p.oy)
                  for p in stages[si]]
            for si in range(len(stages))]
        abs_parts: dict[str, _Part] = {}
        y_base = ZONE_PAD
        for ri, row in enumerate(layout):
            row_min_y = min(_stage_extent(frames[si])[1] for si in row)
            dy = y_base - row_min_y
            x = ZONE_PAD
            row_bottom = y_base
            for k, si in enumerate(row):
                sp = frames[si]
                ext = _stage_extent(sp)
                dx = x - ext[0]
                for p in sp:
                    abs_parts[p.bref] = _Part(p.bref, p.mod, p.rot, p.side,
                                              round(p.ox + dx, 4),
                                              round(p.oy + dy, 4))
                row_bottom = max(row_bottom, ext[3] + dy)
                if k + 1 < len(row):
                    nxt = row[k + 1]
                    gap = (_INTERSTAGE_GAP0 if (_has_sw(si) and _has_sw(nxt))
                           else _NONSW_STAGE_GAP)
                    x = ext[2] + dx + gap
            # inter-ROW gap: widen ONLY at a buck|buck row boundary (spreads the
            # two hottest dies on the shared plane; a buck|LDO or LDO boundary
            # keeps the tight courtyard gap). See _INTERROW_BUCK_GAP.
            row_gap = TEMPLATE_CLEAR
            if ri + 1 < len(layout):
                nxt_row = layout[ri + 1]
                if (any(_has_sw(si) for si in row)
                        and any(_has_sw(si) for si in nxt_row)):
                    row_gap = _INTERROW_BUCK_GAP
            y_base = row_bottom + row_gap
        return abs_parts

    def _width(placed: dict[str, _Part]) -> float:
        return _row_extent(placed)[0]

    min_foreign = _foreign_sw_bound(structs)

    def _ok(placed: dict[str, _Part]) -> bool:
        return _foreign_ok(placed, contract, lib2board, board_set, resolvable,
                           min_foreign)

    # enumerate candidate layouts from the stage sequence: bucks (in order) then
    # the LDO(s). Deterministic — built from stage_kind, no data-dependent set
    # iteration.
    bucks = [si for si in range(len(stages)) if stage_kind[si] == "buck"]
    others = [si for si in range(len(stages)) if stage_kind[si] != "buck"]
    seq = list(range(len(stages)))
    candidates: list[tuple[list[list[int]], set[int]]] = []
    #  L0 single row (2nd buck mirrored, v1 shape)
    candidates.append(([seq], {bucks[1]} if len(bucks) >= 2 else set()))
    #  L1 bucks row0 (2nd mirrored), others row1
    if bucks and others:
        candidates.append(
            ([bucks, others], {bucks[1]} if len(bucks) >= 2 else set()))
    #  L2 one buck per row; the LDO(s) ride the LAST buck's row (no mirror needed —
    #  each buck alone on its row already has FB facing -X, away from the other's SW)
    if len(bucks) >= 2:
        rows2 = [[b] for b in bucks[:-1]] + [[bucks[-1], *others]]
        candidates.append((rows2, set()))
    #  L3 one stage per row (the fully-stacked fallback)
    candidates.append(([[si] for si in seq], set()))

    # SELECT the NARROWEST valid layout. The power zone is an E-side INTERIOR block,
    # so its WIDTH is the DEPTH it eats into the board interior from the edge — the
    # board-inflating dimension (the taller/narrower a stack, the better it seats in
    # the ~39.5 mm SoM side-band, and its height runs harmlessly ALONG the edge).
    # v1's single wide row (65 mm) inflated the board +24%; minimising width here is
    # what recovers it. Among candidates that fit the width budget AND pass
    # foreign-SW (rule never relaxed, LAW 4), pick the smallest width; ties broken
    # by the fewest rows (flatter) then candidate order — deterministic.
    scored = []
    for ci, (layout, mirror) in enumerate(candidates):
        cand = _lay(layout, mirror)
        w = _width(cand)
        if w <= _ROW_WIDTH_BUDGET and _ok(cand):
            scored.append((round(w, 4), len(layout), ci, cand))
    if scored:
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        placed_abs = scored[0][3]
    else:
        # no candidate met BOTH; prefer a foreign-SW-correct one (never relax the
        # rule), else the narrowest — so the result is always electrically valid.
        ok_cands = [_lay(la, mi) for la, mi in candidates]
        valid = [c for c in ok_cands if _ok(c)]
        placed_abs = (min(valid, key=_width) if valid
                      else min(ok_cands, key=_width))

    # --- FACING: turn the composed column so its OUTPUT faces downstream -------
    # The column is built with the COUT (bulk_out) bank toward +X of each stage,
    # so by construction the zone's OUTPUT edge faces +X (E). The downstream zone
    # (power_som/SoM) is toward the board INTERIOR; the hook passes that direction
    # as ``facing`` (N/E/S/W). A size-preserving 180-deg whole-zone TURN flips the
    # output from +X to -X (and top<->bottom), which is a rigid {0,90,180,270}
    # op on every part (legal, same side) and leaves the zone bbox unchanged — so
    # the floorplan block size the plan already committed to does not move. We
    # apply the turn iff it moves the OUTPUT-role centroid onto the ``facing``
    # half of the zone (the SAME dot-product test the FLOW gate's FACING check
    # applies to the emitted board). Deterministic; no-op when ``facing`` is None
    # or already correct.
    out_libs = [k for k, v in roles.items()
                if v in set(contract.get("external", {}).get(
                    "output_roles", ["cout_bulk"]))]
    out_brefs = {b for b in (bref(x) for x in out_libs) if b is not None}
    placed_abs = _apply_facing(placed_abs, out_brefs, facing)

    # --- leftovers: shelf-pack below the stage row, stages as blockers ---------
    stage_refs = set(placed_abs)
    leftovers = [r for r in refs if r not in stage_refs]
    # blockers = the stage-row extents (zone-local), so leftovers pack below
    blockers = [pp.local_box() for pp in placed_abs.values()]
    row_bottom = max((b[3] for b in blockers), default=ZONE_PAD)

    top_off: dict[str, tuple[float, float]] = {}
    bot_off: dict[str, tuple[float, float]] = {}
    for p in placed_abs.values():
        top_off[p.bref] = (p.ox, p.oy)
        if abs(p.rot) > 1e-6 and p.mod.stem not in CONN_MATING_FACE:
            # a mating connector's rotation is OWNED by the LAW-6 conn_rot
            # machinery — the zone builds its geometry AT that rotation but
            # must not ALSO emit it as extra rot (double rotation = mouths
            # inward, 8 mis-placed connectors, measured).
            rot_out[p.bref] = p.rot % 360.0

    zw, zh = _row_extent(placed_abs)

    if leftovers:
        # Shelf-pack the true leftovers (LEDs, PG-sense FET, test points, PG-LED
        # resistors — all SMD for the power BOM) in a band BELOW the stacked stage
        # rows. The zone is an E-side INTERIOR block, so its WIDTH is the depth it
        # eats into the board interior — the board-inflating dimension. The band is
        # packed to the STAGE width (never wider), so the leftovers add HEIGHT (which
        # runs harmlessly ALONG the edge) and NOT width. Bottom-side leftovers stay
        # bottom; the bottom pack avoids any top-side THROUGH-HOLE leftover pad
        # (copper on all layers would short a bottom SMD), as ``_pack_one_zone`` does.
        # (LAW 0/1: leftovers are electrically non-critical here; only their band
        # position moves, never a contract member.)
        lt = [r for r in leftovers if side_of.get(r, "top") == "top"]
        lb = [r for r in leftovers if side_of.get(r, "top") == "bottom"]
        target_w = max(zw - 2 * ZONE_PAD, 8.0)
        # LAW 1: leave a REFDES-height gap (not just PLACE_CLEAR) between the stage
        # cluster and the leftover band. The refdes declutter pass flings a
        # stage-edge ref that cannot fit at its footprint to the nearest clear
        # spot; with only a PLACE_CLEAR gap that spot can land IN the leftover band
        # (a decluttered stage ref overprinting a leftover ref — the one F.SilkS
        # overlap the whole-zone facing turn otherwise induced). A ~2 mm band gap
        # gives the flung text its own lane. Courtyard clearance is already met by
        # PLACE_CLEAR; this only adds refdes headroom, never removes clearance.
        band_top = row_bottom + _LEFTOVER_BAND_GAP
        t_lo, t_w, t_h, b_lo, b_w, b_h = _pack_leftover_bands(
            lt, lb, target_w, bbox_of, resolvable)
        for r, (dx, dy) in t_lo.items():
            top_off[r] = (round(dx, 4), round(dy + band_top - ZONE_PAD, 4))
        for r, (dx, dy) in b_lo.items():
            bot_off[r] = (round(dx, 4), round(dy + band_top - ZONE_PAD, 4))
        zw = round(max(zw, t_w, b_w), 4)
        zh = round(max(zh, band_top - ZONE_PAD + t_h, band_top - ZONE_PAD + b_h),
                   4)

    return top_off, bot_off, round(zw, 4), round(zh, 4)


def _build_proximity_zone(sheet_name: str, contract: dict, refs: list[str],
                          side_of: dict[str, str],
                          bbox_of: dict[str, tuple[float, float, float, float]],
                          resolvable: dict[str, Path],
                          rot_out: dict[str, float],
                          facing: str | None = None,
                          outer_dir: str | None = None
                          ) -> tuple[dict[str, tuple[float, float]],
                                     dict[str, tuple[float, float]],
                                     float, float] | None:
    """Build a PROXIMITY-ONLY contract (usb_pd's FUSB302B bypass/CC network) as a
    single rigid cluster around its anchor IC, re-anchored into the zone frame,
    then shelf-pack the true leftovers into a band below (the SAME leftover machinery
    the power path uses). Returns the ``_pack_one_zone`` 4-tuple, or None to fall
    through. Deterministic; the cluster's chosen rotations come back via ``rot_out``
    (the SAME channel LEVER-L1 uses), folded into ``zone_extra_rot`` by build_model.

    ``facing`` (optional; N/E/S/W; T1 P7a): the zone-local direction the MEDIA side
    — the members that hug an ``anchor_pins`` centre-tap row — must face. A rigid
    {0,90,180,270}-deg whole-cluster turn (``_apply_media_facing``) is applied so
    those members land on the ``facing`` half of the zone (ethernet's Bob-Smith
    R/C row faces the RJ45 jack). Applied BEFORE the extent/leftover pack so a
    90/270 turn's w<->h swap is reflected in the returned block size. No-op when
    ``facing`` is None or the contract has no anchor-pinned proximity members."""
    lib2board = _g._board_refs_by_sheet(sheet_name)
    board_set = set(refs)
    bref_of = {lib: b for lib, b in lib2board.items()
               if b in board_set and b in resolvable}

    # the anchor is the same_side IC (or the single proximity anchor). Prefer a
    # same_side ``ics`` entry; else the first proximity structure's anchor.
    anchor_lib: str | None = None
    for st in contract.get("structures", []):
        if st.get("type") == "same_side" and st.get("ics"):
            anchor_lib = st["ics"][0]
            break
    if anchor_lib is None:
        for st in contract.get("structures", []):
            if st.get("type") == "proximity":
                anchor_lib = st.get("anchor")
                break
    anchor_bref = bref_of.get(anchor_lib or "")
    if anchor_bref is None:
        return None

    # DISPATCH: the two FROZEN pilot sheets (usb_pd/ethernet) keep the byte-identical
    # legacy single-anchor cluster; EVERY other contract — single- or multi-anchor —
    # is solved by the general graph solver (the one reusable mechanic). The legacy
    # cluster is retained only to freeze the pilots' proven layout; it is also the
    # single-anchor DFS whose backtracking exhausts its node budget on a large star
    # (hdmi_rx_term's 10-part cluster hangs ~20s), so new wiring must not use it.
    if sheet_name in _PILOT_PROX_SHEETS and _is_single_anchor_star(contract, bref_of):
        parts = _build_proximity_cluster(anchor_bref, contract, bref_of, resolvable)
    else:
        parts = _solve_contract(contract, bref_of, resolvable,
                                outer_dir=outer_dir)
    if parts is None:
        return None

    # re-anchor: shift so the cluster's min pad corner sits at ZONE_PAD (parts can
    # sit on all four sides of the anchor, so origin-relative offsets go negative).
    minx = min(b[0] for p in parts for b in p.pad_boxes().values())
    miny = min(b[1] for p in parts for b in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    placed_abs = {p.bref: _Part(p.bref, p.mod, p.rot, p.side,
                                round(p.ox + dx, 4), round(p.oy + dy, 4))
                  for p in parts}

    # MEDIA FACING (T1 P7a): the members that hug an ``anchor_pins`` centre-tap row
    # (ethernet's Bob-Smith R/C at T1's MCT pins 24/21/18/15) form the MEDIA side;
    # turn the whole cluster so they face ``facing`` (the RJ45 jack's edge). Applied
    # HERE — after re-anchor, before the extent/leftover pack — so a 90/270 turn's
    # w<->h swap flows into the returned block size and the re-anchor stays valid.
    media_brefs: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity" or not st.get("anchor_pins"):
            continue
        if bref_of.get(st.get("anchor", "")) != anchor_bref:
            continue
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is not None:
                media_brefs.add(mb)
    placed_abs = _apply_media_facing(placed_abs, media_brefs, facing)

    top_off: dict[str, tuple[float, float]] = {}
    bot_off: dict[str, tuple[float, float]] = {}
    for p in placed_abs.values():
        top_off[p.bref] = (p.ox, p.oy)
        if abs(p.rot) > 1e-6 and p.mod.stem not in CONN_MATING_FACE:
            rot_out[p.bref] = p.rot % 360.0

    zw, zh = _row_extent(placed_abs)
    row_bottom = max((pp.local_box()[3] for pp in placed_abs.values()),
                     default=ZONE_PAD)
    _gx = _gy = 0.0

    # leftovers: everything not in the cluster, banded below (usb_pd has none — all
    # 6 parts are contracted — but keep the band so a lightly-contracted subsystem
    # still packs its extras, exactly like the power path).
    leftovers = [r for r in refs if r not in placed_abs]
    if leftovers:
        lt = [r for r in leftovers if side_of.get(r, "top") == "top"]
        lb = [r for r in leftovers if side_of.get(r, "top") == "bottom"]
        # LAW 6: the leftover band sits on the INBOARD side of the cluster —
        # on an edge sheet the outer side IS the mating-connector face and a
        # banded TP/strap there lands in the edge-seat slide path (measured:
        # camera/hdmi TPs crushed at clr=0.000). N keeps the historical
        # below-band (inboard == +y); S bands above; E left; W right.
        _in = {"S": (0.0, -1.0)}.get(outer_dir or "N", (0.0, 1.0))
        target_w = max(zw - 2 * ZONE_PAD, 8.0)
        # the band must clear every mating connector by its fan-out need plus
        # the seat slide (a TP at 0.00 below the camera FFC was the defect).
        _conn_lo, _conn_hi = [], []
        if outer_dir:
            for pp in placed_abs.values():
                if pp.mod.stem in CONN_MATING_FACE:
                    bb = pp.local_box()
                    _conn_lo.append(bb[1])
                    _conn_hi.append(bb[3])
        t_lo, t_w, t_h, b_lo, b_w, b_h = _pack_leftover_bands(
            lt, lb, target_w, bbox_of, resolvable)
        row_top = min((pp.local_box()[1] for pp in placed_abs.values()),
                      default=ZONE_PAD)
        _need_gap = 1.0 + _SEAT_SLIDE
        if _in == (0.0, 1.0):
            floor_y = max([row_bottom]
                          + [h + _need_gap for h in _conn_hi])
            bx, by = 0.0, floor_y + _LEFTOVER_BAND_GAP - ZONE_PAD
        else:
            bh_all = max(t_h, b_h)
            ceil_y = min([row_top] + [lo - _need_gap for lo in _conn_lo])
            bx, by = 0.0, ceil_y - _LEFTOVER_BAND_GAP - bh_all - ZONE_PAD
        if outer_dir == "W":
            _pf0 = [pp.ox + _rot_pad_bbox(pp.mod, pp.rot)[0]
                    for pp in placed_abs.values()
                    if pp.mod.stem in CONN_MATING_FACE]
            if _pf0:
                bx = min(_pf0) + _SEAT_SLIDE
        for r, (ox, oy) in t_lo.items():
            top_off[r] = (round(ox + bx, 4), round(oy + by, 4))
        for r, (ox, oy) in b_lo.items():
            bot_off[r] = (round(ox + bx, 4), round(oy + by, 4))
        # global re-anchor: a band on the -x/-y side pushes offsets negative;
        # shift EVERYTHING so the min offset sits at ZONE_PAD again.
        allx = [v[0] for v in top_off.values()] + [v[0] for v in bot_off.values()]
        ally = [v[1] for v in top_off.values()] + [v[1] for v in bot_off.values()]
        sx = ZONE_PAD - min(allx) if min(allx) < ZONE_PAD else 0.0
        sy = ZONE_PAD - min(ally) if min(ally) < ZONE_PAD else 0.0
        if sx or sy:
            _gx, _gy = sx, sy
            top_off = {r: (round(x + sx, 4), round(y + sy, 4))
                       for r, (x, y) in top_off.items()}
            bot_off = {r: (round(x + sx, 4), round(y + sy, 4))
                       for r, (x, y) in bot_off.items()}
        ext_x = [pp.local_box()[2] + sx for pp in placed_abs.values()]
        ext_y = [pp.local_box()[3] + sy for pp in placed_abs.values()]
        if t_lo or b_lo:
            ext_x += [bx + sx + t_w, bx + sx + b_w]
            ext_y += [by + sy + t_h, by + sy + b_h]
        zw = round(max(ext_x) + ZONE_PAD, 4)
        zh = round(max(ext_y) + ZONE_PAD, 4)

    _connp = [pp for pp in placed_abs.values()
              if pp.mod.stem in CONN_MATING_FACE]
    if outer_dir and _connp:
        # SEAT-LINE REPLICATION: the board edge-seat overwrites each mating
        # connector's perpendicular coordinate so its outer PAD sits at
        # EDGE_PAD_CLEAR inside the board edge == this zone's outer boundary.
        # Put the boundary exactly there; the mouth overhangs off-zone the
        # same way it overhangs off-board (a DS1024's 9mm mouth counted in
        # the extents left ESD members 13.5mm from the pads; limit 5).
        vx, vy = _OVEC[outer_dir]

        def _pface(pp: _Part) -> float:
            sb = _rot_pad_bbox(pp.mod, pp.rot)
            return (pp.ox + sb[2] + _gx if vx > 0
                    else pp.ox + sb[0] + _gx if vx < 0
                    else pp.oy + sb[3] + _gy if vy > 0
                    else pp.oy + sb[1] + _gy)

        faces = [_pface(pp) for pp in _connp]
        if vx > 0:
            zw = max(faces) + EDGE_PAD_CLEAR
        elif vy > 0:
            zh = max(faces) + EDGE_PAD_CLEAR
        else:
            d = EDGE_PAD_CLEAR - min(faces)
            if vx < 0:
                top_off = {r: (round(x + d, 4), y)
                           for r, (x, y) in top_off.items()}
                bot_off = {r: (round(x + d, 4), y)
                           for r, (x, y) in bot_off.items()}
                zw += d
            else:
                top_off = {r: (x, round(y + d, 4))
                           for r, (x, y) in top_off.items()}
                bot_off = {r: (x, round(y + d, 4))
                           for r, (x, y) in bot_off.items()}
                zh += d

    return top_off, bot_off, round(zw, 4), round(zh, 4)


# --- small helpers used by build_zone ---------------------------------------------

def _pack_leftover_bands(lt: list[str], lb: list[str], target_w: float,
                         bbox_of: dict[str, tuple[float, float, float, float]],
                         resolvable: dict[str, Path]
                         ) -> tuple[dict, float, float, dict, float, float]:
    """Shelf-pack top-side (``lt``) and bottom-side (``lb``) leftovers to a common
    ``target_w`` in a shared (0,0)-based frame; the BOTTOM pack avoids any top-side
    THROUGH-HOLE leftover pad (copper on all layers would short a bottom SMD),
    exactly as ``_pack_one_zone`` does. Returns (t_lo, t_w, t_h, b_lo, b_w, b_h)."""
    t_items = [(r, bbox_of[r], 0.0) for r in lt]
    t_lo, t_w, t_h = _shelf_pack(t_items, target_w)
    blockers = []
    for r in lt:
        if r in resolvable and _has_thru_pads(resolvable[r]):
            ox, oy = t_lo[r]
            bx0, by0, bx1, by1 = bbox_of[r]
            blockers.append((ox + bx0 - TEMPLATE_CLEAR / 2,
                             oy + by0 - TEMPLATE_CLEAR / 2,
                             ox + bx1 + TEMPLATE_CLEAR / 2,
                             oy + by1 + TEMPLATE_CLEAR / 2))
    b_items = [(r, bbox_of[r], 0.0) for r in lb]
    b_lo, b_w, b_h = _shelf_pack(b_items, target_w, blockers)
    return t_lo, t_w, t_h, b_lo, b_w, b_h


def _buck_index(stage_i: int, stage_kind: list[str]) -> int:
    """0-based index AMONG buck stages of the stage at position ``stage_i``."""
    return sum(1 for k in stage_kind[:stage_i] if k == "buck")


def _foreign_sw_bound(structs: list[dict]) -> float:
    for st in structs:
        if st.get("type") == "fb_cluster":
            return float(st.get("min_to_foreign_sw_mm", 5.0))
    return 5.0


def _foreign_ok(placed: dict[str, _Part], contract: dict,
                lib2board: dict[str, str], board_set: set[str],
                resolvable: dict[str, Path], min_foreign: float) -> bool:
    """Every FB member clears the OTHER buck's SW pad / inductor by >= min."""
    def b(lib: str | None) -> str | None:
        x = lib2board.get(lib) if lib else None
        return x if x in placed else None
    for st in contract.get("structures", []):
        if st.get("type") != "fb_cluster":
            continue
        # E2: a single-buck sheet's fb_cluster has NO foreign_* keys — the
        # foreign-SW guard is inter-subsystem there (FAR/flow gate), not
        # intra-zone geometry.
        if "foreign_ic" not in st:
            continue
        for_ic = b(st["foreign_ic"])
        for_l = b(st.get("foreign_inductor"))
        if for_ic is None:
            continue
        for_boxes = placed[for_ic].pad_boxes()
        sw_box = for_boxes.get(st["foreign_sw_pin"])
        l_boxes = placed[for_l].pad_boxes() if for_l else {}
        for m in st["members"]:
            mb = b(m)
            if mb is None:
                continue
            for pb in placed[mb].pad_boxes().values():
                if sw_box is not None and _g._box_gap(pb, sw_box) < min_foreign:
                    return False
                for lb in l_boxes.values():
                    if _g._box_gap(pb, lb) < min_foreign:
                        return False
    return True


def _row_extent(placed: dict[str, _Part]) -> tuple[float, float]:
    allb = [pp.local_box() for pp in placed.values()]
    zw = round(max(b[2] for b in allb) + ZONE_PAD, 4)
    zh = round(max(b[3] for b in allb) + ZONE_PAD, 4)
    return zw, zh


# --- FACING (Unit 3): turn the composed zone so its output faces downstream -------

_FACING_VEC: dict[str, tuple[float, float]] = {
    # zone-local (page frame, +y DOWN): N is -y, S is +y, W is -x, E is +x.
    "N": (0.0, -1.0), "S": (0.0, 1.0), "W": (-1.0, 0.0), "E": (1.0, 0.0),
}


def _pad_center(p: _Part) -> tuple[float, float]:
    """(x, y) center of a placed part's pad-box union in the zone-local frame."""
    b = p.pad_boxes().values()
    xs = [x for bb in b for x in (bb[0], bb[2])]
    ys = [y for bb in b for y in (bb[1], bb[3])]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def _turn_zone_180(placed: dict[str, _Part]) -> dict[str, _Part]:
    """Rigid 180-deg TURN of the whole composed zone about its pad-extent center:
    every part rotation gains 180 deg and its position reflects through the center,
    preserving every intra-zone relationship AND the zone bounding box (so the
    floorplan block size is unchanged). Legal for every footprint ({0,90,180,270}).
    Mirrors the per-stage ``_mirror_stage`` transform, applied zone-wide."""
    # extent center over every part's pad boxes
    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx = (min(x for x, _ in allpts) + max(x for x, _ in allpts)) / 2.0
    ecy = (min(y for _, y in allpts) + max(y for _, y in allpts)) / 2.0
    out: dict[str, _Part] = {}
    for ref, p in placed.items():
        nrot = (p.rot + 180.0) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        ocx = p.ox + (min(b[0] for b in ob.values())
                      + max(b[2] for b in ob.values())) / 2.0
        ocy = p.oy + (min(b[1] for b in ob.values())
                      + max(b[3] for b in ob.values())) / 2.0
        ncx = 2 * ecx - ocx
        ncy = 2 * ecy - ocy
        nhx = (min(b[0] for b in nb.values())
               + max(b[2] for b in nb.values())) / 2.0
        nhy = (min(b[1] for b in nb.values())
               + max(b[3] for b in nb.values())) / 2.0
        out[ref] = _Part(ref, p.mod, nrot, p.side,
                         round(ncx - nhx, 4), round(ncy - nhy, 4))
    # re-anchor to a ZONE_PAD-margined top-left (the turn moved the extent origin);
    # the plan/floorplan expects offsets in [ZONE_PAD, ...] just like the un-turned
    # composition, so shift so the min pad corner sits at ZONE_PAD.
    minx = min(bb[0] for p in out.values() for bb in p.pad_boxes().values())
    miny = min(bb[1] for p in out.values() for bb in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    return {ref: _Part(ref, p.mod, p.rot, p.side,
                       round(p.ox + dx, 4), round(p.oy + dy, 4))
            for ref, p in out.items()}


def _apply_facing(placed: dict[str, _Part], out_brefs: set[str],
                  facing: str | None) -> dict[str, _Part]:
    """Return ``placed`` turned 180 deg iff that lands the OUTPUT-role parts on the
    ``facing`` half of the zone (the same dot-product test the FLOW gate applies).
    No-op when ``facing`` is unset/unknown, there are no output parts, or the
    output already faces ``facing``. Deterministic."""
    fv = _FACING_VEC.get((facing or "").upper())
    if fv is None or not out_brefs:
        return placed
    present = [r for r in out_brefs if r in placed]
    if not present:
        return placed

    def _dot(pl: dict[str, _Part]) -> float:
        zc = _centroid([_pad_center(p) for p in pl.values()])
        oc = _centroid([_pad_center(pl[r]) for r in present])
        return (oc[0] - zc[0]) * fv[0] + (oc[1] - zc[1]) * fv[1]

    if _dot(placed) > 0.0:
        return placed                     # output already faces downstream
    turned = _turn_zone_180(placed)
    # only accept the turn if it actually improves facing (defensive: a symmetric
    # zone could tie — then keep the original to stay deterministic).
    return turned if _dot(turned) > _dot(placed) else placed


def refit_facing(sheet_name: str, contract: dict,
                 parts_xy: dict[str, tuple[float, float]],
                 rots_now: dict[str, float],
                 resolvable: dict[str, Path],
                 down_centroid: tuple[float, float]
                 ) -> dict[str, tuple[float, float, float]] | None:
    """POSITION-AWARE facing refit on the FINAL absolute positions — run after
    every mover (grid translation, L4 pull, connector edge-seat, BREATHE), on the
    exact coordinates the model will freeze.

    ``build_zone`` turned the zone with the SPEC-derived facing hint (positions
    did not exist yet), but the packer may seat the zone anywhere — capacity
    exiled power to the far W when the E side filled — and later movers shift the
    downstream centroid again, so only the final frame is decidable. The decision
    replicates the FLOW gate's ``facing_dot`` kernel EXACTLY: equal-weight
    PART-ORIGIN centroids over the sheet's placed parts (czone) and the
    output-role parts (cout), downstream vector anchored AT czone. Turn 180 iff
    the gate's dot is non-positive AND the turn improves it — exactly when the
    gate would fail — so a gate-passing pose is an exact NO-OP and the default
    board stays byte-identical. The turn is a rigid reflection through the zone's
    pad-extent centre (bbox-preserving, every part +180 deg); returns
    ``{ref: (x, y, new_rot)}`` for the turned zone, or None for the no-op."""
    roles = contract.get("roles", {})
    out_libs = [k for k, v in roles.items()
                if v in set(contract.get("external", {}).get(
                    "output_roles", ["cout_bulk"]))]
    lib2board = _g._board_refs_by_sheet(sheet_name)
    out_brefs = {lib2board.get(x) for x in out_libs} - {None}
    present = sorted(r for r in out_brefs if r in parts_xy)
    if not present:
        return None
    if any(r not in resolvable for r in parts_xy):
        return None
    placed = {r: _Part(r, resolvable[r], rots_now.get(r, 0.0) % 360.0,
                       "top", x, y)
              for r, (x, y) in parts_xy.items()}

    def _gate_dot(xy: dict[str, tuple[float, float]]) -> float:
        n = len(xy)
        zcx = sum(p[0] for p in xy.values()) / n
        zcy = sum(p[1] for p in xy.values()) / n
        ocx = sum(xy[r][0] for r in present) / len(present)
        ocy = sum(xy[r][1] for r in present) / len(present)
        dvx = down_centroid[0] - zcx
        dvy = down_centroid[1] - zcy
        return (ocx - zcx) * dvx + (ocy - zcy) * dvy

    if _gate_dot(parts_xy) > 0.0:
        return None                       # gate passes this pose: exact no-op

    # rigid 180 about the pad-extent centre, ABSOLUTE frame (no re-anchor — the
    # extent is symmetric under the reflection, so the zone bbox stays put).
    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx = (min(x for x, _ in allpts) + max(x for x, _ in allpts)) / 2.0
    ecy = (min(y for _, y in allpts) + max(y for _, y in allpts)) / 2.0
    turned: dict[str, tuple[float, float, float]] = {}
    for r, p in placed.items():
        nrot = (p.rot + 180.0) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        ocx = p.ox + (min(b[0] for b in ob.values())
                      + max(b[2] for b in ob.values())) / 2.0
        ocy = p.oy + (min(b[1] for b in ob.values())
                      + max(b[3] for b in ob.values())) / 2.0
        nhx = (min(b[0] for b in nb.values())
               + max(b[2] for b in nb.values())) / 2.0
        nhy = (min(b[1] for b in nb.values())
               + max(b[3] for b in nb.values())) / 2.0
        turned[r] = (round(2 * ecx - ocx - nhx, 4),
                     round(2 * ecy - ocy - nhy, 4), nrot)
    if _gate_dot({r: (t[0], t[1]) for r, t in turned.items()}
                 ) <= _gate_dot(parts_xy):
        return None                       # symmetric tie: keep deterministic
    return turned


def _turn_zone_quadrant(placed: dict[str, _Part], deg: float
                        ) -> dict[str, _Part]:
    """Rigid {0,90,180,270}-deg TURN of the whole composed zone about its pad-extent
    center, then re-anchored so its min pad corner sits at ZONE_PAD. Every part
    rotation gains ``deg`` and its position rotates about the center by the SAME
    CLOCKWISE (+y-down) transform ``_pad_boxes`` uses — so intra-zone geometry is
    preserved exactly and the result stays on-grid/on-side. The bbox is preserved
    for 0/180; a 90/270 turn SWAPS w<->h (the caller re-reads the extent), which is
    fine for a small square-ish proximity cluster whose block size the plan has not
    yet committed (the proximity path applies facing BEFORE computing zw/zh).
    Generalises ``_turn_zone_180`` to any quadrant (T1 P7a: a media row must be able
    to face any of the four edges, not only the opposite one)."""
    deg = deg % 360.0
    if abs(deg) < 1e-6:
        return placed
    R = math.radians(deg)
    cs, sn = math.cos(R), math.sin(R)
    # extent center over every part's pad boxes (pre-turn frame)
    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx = (min(x for x, _ in allpts) + max(x for x, _ in allpts)) / 2.0
    ecy = (min(y for _, y in allpts) + max(y for _, y in allpts)) / 2.0
    out: dict[str, _Part] = {}
    for ref, p in placed.items():
        nrot = (p.rot + deg) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        # old pad-union center (zone-local), rotate it about the extent center by
        # the SAME CW transform, then back out the new footprint half-offset so the
        # part origin lands where the rotated center wants it.
        ocx = p.ox + (min(b[0] for b in ob.values())
                      + max(b[2] for b in ob.values())) / 2.0
        ocy = p.oy + (min(b[1] for b in ob.values())
                      + max(b[3] for b in ob.values())) / 2.0
        rx, ry = ocx - ecx, ocy - ecy
        # CW rotation (+y-down), matches _pad_boxes
        ncx = ecx + (rx * cs + ry * sn)
        ncy = ecy + (-rx * sn + ry * cs)
        nhx = (min(b[0] for b in nb.values())
               + max(b[2] for b in nb.values())) / 2.0
        nhy = (min(b[1] for b in nb.values())
               + max(b[3] for b in nb.values())) / 2.0
        out[ref] = _Part(ref, p.mod, nrot, p.side,
                         round(ncx - nhx, 4), round(ncy - nhy, 4))
    # re-anchor to a ZONE_PAD-margined top-left (the turn moved the extent origin).
    minx = min(bb[0] for p in out.values() for bb in p.pad_boxes().values())
    miny = min(bb[1] for p in out.values() for bb in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    return {ref: _Part(ref, p.mod, p.rot, p.side,
                       round(p.ox + dx, 4), round(p.oy + dy, 4))
            for ref, p in out.items()}


def _apply_media_facing(placed: dict[str, _Part], media_brefs: set[str],
                        facing: str | None) -> dict[str, _Part]:
    """Turn the composed PROXIMITY cluster by whichever of {0,90,180,270} deg lands
    the MEDIA parts (the anchor-pin discretes — e.g. ethernet's Bob-Smith R/C at T1's
    centre-tap row) on the ``facing`` half of the zone. Unlike ``_apply_facing`` (a
    binary 180 flip toward the opposite edge), a media row may need to face ANY of
    the four edges, so all four quadrant turns are scored and the best (highest
    dot with the facing vector, ties -> smallest turn) is chosen. Deterministic;
    no-op when ``facing`` is unset/unknown or there are no media parts."""
    fv = _FACING_VEC.get((facing or "").upper())
    if fv is None or not media_brefs:
        return placed
    present = [r for r in media_brefs if r in placed]
    if not present:
        return placed

    def _dot(pl: dict[str, _Part]) -> float:
        zc = _centroid([_pad_center(p) for p in pl.values()])
        mc = _centroid([_pad_center(pl[r]) for r in present])
        return (mc[0] - zc[0]) * fv[0] + (mc[1] - zc[1]) * fv[1]

    best = placed
    best_dot = _dot(placed)
    best_turn = 0.0
    for deg in (90.0, 180.0, 270.0):
        cand = _turn_zone_quadrant(placed, deg)
        d = _dot(cand)
        # strictly better, or equal-but-smaller-turn (determinism); the 0-turn
        # incumbent already holds best_turn=0 so it wins ties against 90/180/270.
        if d > best_dot + 1e-6:
            best, best_dot, best_turn = cand, d, deg
    _ = best_turn
    return best
