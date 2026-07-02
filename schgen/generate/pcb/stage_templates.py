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

from pathlib import Path

from schgen.verify import placement_contract_gate as _g

from .constants import PLACE_CLEAR, ZONE_PAD
from .footprint import _footprint_bbox
from .footprint import has_thru_pads as _has_thru_pads
from .mating_face import _rot_bbox_cw
from .placement import _eff_bbox_for, _shelf_pack

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
_NONSW_STAGE_GAP = round(PLACE_CLEAR + 0.7, 4)   # ~1.2 mm: a pair with no SW rule
# Row-wrap width budget (mm): the layout search prefers the fewest-rows layout that
# keeps the power ZONE width within this bound (acceptance: zone width <= 48 mm) AND
# satisfies foreign-SW. Two ~25 mm bucks WITH their COUT banks cannot share a row
# under this bound, so the search stacks one buck per row (LDO beside the last).
_ROW_WIDTH_BUDGET = 46.0


# --- local-frame primitives -------------------------------------------------------
# A "placed part" during construction is (bref, rot, side, ox, oy): its pad boxes
# in the stage-local frame are _pad_boxes(mod, rot, side) shifted by (ox, oy). We
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
        rel = _g._pad_boxes(self.mod, self.rot, self.side)
        return {n: (self.ox + b[0], self.oy + b[1], self.ox + b[2], self.oy + b[3])
                for n, b in rel.items()}

    def local_box(self) -> tuple[float, float, float, float]:
        """Courtyard bbox (F->B mirror for a bottom part, plus rotation) in the
        stage-local frame — the box used for overlap/extent, matching the packer's
        ``_eff_bbox_for`` + rotation convention (the SAME transform
        ``mating_face._inst_courtyard`` applies to the emitted footprint)."""
        rb = _rot_bbox_cw(_eff_bbox_for(_footprint_bbox(self.mod), self.side),
                          self.rot)
        return (self.ox + rb[0], self.oy + rb[1], self.ox + rb[2], self.oy + rb[3])


def _pad_half(mod: Path) -> tuple[float, float]:
    """Half width/height of a 2-pin passive's pad box at rot 0 (for gap solves)."""
    pb = _g._pad_boxes(mod, 0.0, "top")
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
    clr = PLACE_CLEAR + m + pad
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
    ox = ind_left - PLACE_CLEAR - hx     # push fully +X (clamped by the inductor)
    return _Part(bref, mod, 0.0, "top", round(ox, 4), p.oy)


def _bulk_cap(mod: Path, hf: _Part, direction: str, gap: float,
              ind_left: float, bref: str) -> _Part:
    """A bulk input cap outboard of the HF cap (same lane), ROTATED 90 so its wide
    1206 body is NARROW in X and does not spill into the top/bottom-LEFT region.
    Right courtyard clamped to clear the inductor; X aligned to the HF cap."""
    hfb = hf.local_box()
    hx, hy = _crtyd_half(mod, 90.0)
    cy = (hfb[3] + gap + hy) if direction == "D" else (hfb[1] - gap - hy)
    ox = min(hf.ox, ind_left - PLACE_CLEAR - hx)
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
    step = PLACE_CLEAR + pad
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
    halo = PLACE_CLEAR + pad
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
                if d > bound:
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
    halo = PLACE_CLEAR + pad
    skel_boxes = [s.local_box() for s in skeleton]
    cand: dict[str, list[_Cand]] = {}
    for bref, tpins, bound, keep, kmin in demands:
        cand[bref] = _candidates(bref, resolvable[bref], ib, icb, tpins, bound,
                                 keep, kmin, pad, skel_boxes,
                                 forbid_plus_x=forbid_plus_x)
    order = sorted((d[0] for d in demands), key=lambda r: len(cand[r]))
    chosen: dict[str, tuple[float, float, float, float]] = {}
    picked: dict[str, _Part] = {}

    def _bt(i: int) -> bool:
        if i == len(order):
            return True
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
            if _boxes_overlap(boxes[i][1], boxes[j][1], PLACE_CLEAR):
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
               facing: str | None = None
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
                rot_out)
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
            nb = _g._pad_boxes(p.mod, nrot, p.side)
            ob = _g._pad_boxes(p.mod, p.rot, p.side)
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
        for row in layout:
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
            y_base = row_bottom + PLACE_CLEAR
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
        if abs(p.rot) > 1e-6:
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
                          rot_out: dict[str, float]
                          ) -> tuple[dict[str, tuple[float, float]],
                                     dict[str, tuple[float, float]],
                                     float, float] | None:
    """Build a PROXIMITY-ONLY contract (usb_pd's FUSB302B bypass/CC network) as a
    single rigid cluster around its anchor IC, re-anchored into the zone frame,
    then shelf-pack the true leftovers into a band below (the SAME leftover machinery
    the power path uses). Returns the ``_pack_one_zone`` 4-tuple, or None to fall
    through. Deterministic; the cluster's chosen rotations come back via ``rot_out``
    (the SAME channel LEVER-L1 uses), folded into ``zone_extra_rot`` by build_model."""
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

    parts = _build_proximity_cluster(anchor_bref, contract, bref_of, resolvable)
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

    top_off: dict[str, tuple[float, float]] = {}
    bot_off: dict[str, tuple[float, float]] = {}
    for p in placed_abs.values():
        top_off[p.bref] = (p.ox, p.oy)
        if abs(p.rot) > 1e-6:
            rot_out[p.bref] = p.rot % 360.0

    zw, zh = _row_extent(placed_abs)
    row_bottom = max((pp.local_box()[3] for pp in placed_abs.values()),
                     default=ZONE_PAD)

    # leftovers: everything not in the cluster, banded below (usb_pd has none — all
    # 6 parts are contracted — but keep the band so a lightly-contracted subsystem
    # still packs its extras, exactly like the power path).
    leftovers = [r for r in refs if r not in placed_abs]
    if leftovers:
        lt = [r for r in leftovers if side_of.get(r, "top") == "top"]
        lb = [r for r in leftovers if side_of.get(r, "top") == "bottom"]
        target_w = max(zw - 2 * ZONE_PAD, 8.0)
        band_top = row_bottom + _LEFTOVER_BAND_GAP
        t_lo, t_w, t_h, b_lo, b_w, b_h = _pack_leftover_bands(
            lt, lb, target_w, bbox_of, resolvable)
        for r, (ox, oy) in t_lo.items():
            top_off[r] = (round(ox, 4), round(oy + band_top - ZONE_PAD, 4))
        for r, (ox, oy) in b_lo.items():
            bot_off[r] = (round(ox, 4), round(oy + band_top - ZONE_PAD, 4))
        zw = round(max(zw, t_w, b_w), 4)
        zh = round(max(zh, band_top - ZONE_PAD + t_h, band_top - ZONE_PAD + b_h),
                   4)

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
    t_items = [(r, _eff_bbox_for(bbox_of[r], "top"), 0.0) for r in lt]
    t_lo, t_w, t_h = _shelf_pack(t_items, target_w)
    blockers = []
    for r in lt:
        if r in resolvable and _has_thru_pads(resolvable[r]):
            ox, oy = t_lo[r]
            bx0, by0, bx1, by1 = bbox_of[r]
            blockers.append((ox + bx0 - PLACE_CLEAR / 2,
                             oy + by0 - PLACE_CLEAR / 2,
                             ox + bx1 + PLACE_CLEAR / 2,
                             oy + by1 + PLACE_CLEAR / 2))
    b_items = [(r, _eff_bbox_for(bbox_of[r], "bottom"), 0.0) for r in lb]
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
    def b(lib: str) -> str | None:
        x = lib2board.get(lib)
        return x if x in placed else None
    for st in contract.get("structures", []):
        if st.get("type") != "fb_cluster":
            continue
        for_ic = b(st["foreign_ic"])
        for_l = b(st["foreign_inductor"])
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
        ob = _g._pad_boxes(p.mod, p.rot, p.side)
        nb = _g._pad_boxes(p.mod, nrot, p.side)
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
