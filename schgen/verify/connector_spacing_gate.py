"""Connector OVERMOLD SIMULTANEOUS-MATE SPACING gate.

The defect this closes: two wide-overmold cable connectors of the SAME family on
the SAME board edge (the primary case: the two HDMI-019S receptacles J12001 +
J14001) can be DRC-clean, ratsnest-clustered, LAW-6 edge-flush AND mouth-out, yet
still be UNBUILDABLE — placed so close that the two cable plugs' OVERMOLDS
physically collide and you cannot have BOTH cables seated at once. A bare-pad-bbox
spacing is fine for the PCB but the cable BODY (the moulded strain-relief boot,
~18-22 mm wide for an HDMI plug) extends well beyond the connector shell.

Every existing gate is blind to this: DRC measures copper, ratsnest_gate measures
airwires/clustering, placement_mech measures edge-flush + mouth-out direction for
EACH connector individually. None of them looks at the BETWEEN-connector mating
clearance for simultaneously-cabled neighbours. This makes that clearance a HARD
gate (LAW 6 — mechanical buildability, NOT just electrical correctness).

RULE (any violation HARD-FAILS the board), in two parts because an overmold is
NOT symmetric — the clearance depends on how many boots meet in the gap:

  PAIR (both connectors of the SAME overmold family, on the same board edge):
  the edge-to-edge gap between their COPPER (pad) bboxes — measured ALONG the
  edge (the axis the two neighbours are separated on) — must be at least
  ``_FAMILY_MIN_GAP_MM[family]``. A smaller gap means the two plug overmolds
  would collide; FAIL.

  ONE-SIDED (an overmold connector beside ANY other off-board connector that is
  not of its family): only the overmold's OWN boot enters the gap, so the
  requirement is its per-side overhang past its own copper,
  ``_FAMILY_SIDE_GAP_MM[family]``. Until this rule existed the pair was policed
  by NOTHING (the audit's under-charge finding, VISUAL_PCB_AUDIT.md:139) while
  the floorplan billed it the full pair gap — the check and the charge were both
  wrong, in opposite directions.

The tables are small and per-family so a new wide connector is two entries:
  HDMI-019S : pair 18 mm, one-sided 3 mm (= floorplan.OVERMOLD_SIDE_GAP)

LAW 4: strict — a too-tight pair is FIXED in the placer (spread the two
connectors along the edge, or move one to a different edge), NEVER waived here.
The measured gap is reported so a regression shows AS a number, not a binary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schgen.generate.floorplan import OVERMOLD_SIDE_GAP
from schgen.generate.pcb import (
    CONN_MATING_FACE,
    PcbModel,
    _inst_pad_bbox,
)

# overmold-family -> minimum required edge-to-edge gap (mm) between TWO of that
# family's connectors mating SIMULTANEOUSLY on the same edge (two boots in one
# gap). Conservative: the datum-derived copper requirement is the boot width
# minus the two connectors' own copper half-widths, 22.0 - 2*8.0 = 6.0 mm, and
# this table keeps the historical 18.0 because nothing measured asks it to move.
_FAMILY_MIN_GAP_MM: dict[str, float] = {
    "HDMI-019S": 18.0,
}

# overmold-family -> minimum edge-to-edge gap (mm) between one of that family's
# connectors and a NON-family off-board neighbour: ONE boot in the gap, so the
# requirement is its per-side overhang past its own copper. Derived, not fitted —
# floorplan._is_overmold_block.__doc__ carries the datum and its sourcing.
_FAMILY_SIDE_GAP_MM: dict[str, float] = {
    "HDMI-019S": OVERMOLD_SIDE_GAP,
}

# the MPN -> overmold family. Today each wide MPN is its own family (two HDMIs
# share the HDMI-019S family); a future shared-boot pair (e.g. two USB-C plugs)
# would map several MPNs to one family key.
_FAMILY_OF: dict[str, str] = {mpn: mpn for mpn in _FAMILY_MIN_GAP_MM}

# two connectors count as "on the same edge" when their pad bboxes overlap on the
# axis PERPENDICULAR to the edge by at least this fraction of the smaller bbox's
# extent on that axis (they sit in the same edge band, side by side along it).
_SAME_BAND_FRAC = 0.5


def _conn_mpn(inst) -> str | None:
    """The off-board-connector MPN of an instance, or None if it is not one.
    Mirrors placement_mech: value first, then the footprint name (lib:name)."""
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _same_edge_gap(a: tuple, b: tuple) -> tuple[str, float] | None:
    """``(axis, copper gap mm)`` when two pad bboxes are side by side in ONE edge
    band, else None: they share a band on one axis and are separated on the other
    (y-band overlap + x separation => a horizontal edge, neighbours along x)."""
    ox = _overlap_1d(a[0], a[2], b[0], b[2])
    oy = _overlap_1d(a[1], a[3], b[1], b[3])
    wx = min(a[2] - a[0], b[2] - b[0])
    hy = min(a[3] - a[1], b[3] - b[1])
    same_x_band = wx > 0 and ox >= _SAME_BAND_FRAC * wx
    same_y_band = hy > 0 and oy >= _SAME_BAND_FRAC * hy
    if same_y_band and not same_x_band:
        return "x", max(a[0], b[0]) - min(a[2], b[2])
    if same_x_band and not same_y_band:
        return "y", max(a[1], b[1]) - min(a[3], b[3])
    return None


@dataclass
class SpacingResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    pairs: list[tuple] = field(default_factory=list)   # report rows
    violations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"CONNECTOR OVERMOLD SPACING GATE: {'PASS' if self.ok else 'FAIL'} "
             f"(board {self.board_w:g} x {self.board_h:g} mm)"]
        L.append(f"  same-edge overmold connector pairs: {len(self.pairs)} "
                 f"({len(self.violations)} too tight)")
        for ra, rb, fam, axis, gap, need, ok in self.pairs:
            mark = "OK " if ok else "BAD"
            L.append(f"    {mark} {ra:9s} <-> {rb:9s} {fam:12s} "
                     f"gap={gap:6.2f}mm along {axis} (need >= {need:g}mm)")
        for v in self.violations:
            L.append(f"    TOO-TIGHT {v}")
        return "\n".join(L)


def check(model: PcbModel) -> SpacingResult:
    res = SpacingResult(board_w=model.board_w, board_h=model.board_h)

    # collect wide-overmold connectors grouped by family, with their pad bboxes.
    by_family: dict[str, list[tuple]] = {}
    for inst in model.insts:
        mpn = _conn_mpn(inst)
        if mpn is None:
            continue
        fam = _FAMILY_OF.get(mpn)
        if fam is None:
            continue                      # not a wide-overmold family we police
        bb = _inst_pad_bbox(inst)         # (x0, y0, x1, y1) copper bbox
        by_family.setdefault(fam, []).append((inst.ref, bb))

    # LAW 4 (close the blind spot): two off-board connectors must never be
    # COINCIDENT — footprints overlapping on BOTH axes (a stacked placement that
    # shorts pads, as the two motor_sense XT60s did under a placement bug). The
    # family-gated overmold check below only polices wide-overmold families, so it
    # SKIPPED that pair (and even for a policed family, a full overlap fell through
    # the side-by-side `else: continue`). This catches a coincident pair for ANY
    # connector MPN. (kicad-cli DRC also flags it, but the LAW-6 connector gate
    # must not have the hole.) A correctly side-by-side pair overlaps on only ONE
    # axis (gap on the other), so it is not flagged here.
    conns = [(i.ref, _inst_pad_bbox(i)) for i in model.insts if _conn_mpn(i)]
    for ci in range(len(conns)):
        for cj in range(ci + 1, len(conns)):
            ra, a = conns[ci]
            rb, b = conns[cj]
            ox = _overlap_1d(a[0], a[2], b[0], b[2])
            oy = _overlap_1d(a[1], a[3], b[1], b[3])
            if ox > 0.05 and oy > 0.05:
                res.violations.append(
                    f"{ra} <-> {rb}: connector footprints OVERLAP "
                    f"(ox={ox:.2f} oy={oy:.2f}mm) — coincident/stacked placement")

    for fam, members in by_family.items():
        need = _FAMILY_MIN_GAP_MM[fam]
        members.sort(key=lambda m: m[0])
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                ra, a = members[i]
                rb, b = members[j]
                hit = _same_edge_gap(a, b)
                if hit is None:
                    continue
                axis, gap = hit
                ok = gap >= need
                res.pairs.append((ra, rb, fam, axis, gap, need, ok))
                if not ok:
                    res.violations.append(
                        f"{ra} <-> {rb} ({fam}): overmold gap {gap:.2f}mm along "
                        f"{axis} < required {need:g}mm — the two cable plugs' "
                        f"overmolds would collide; cannot mate both at once")

    # ONE-SIDED: an overmold connector beside a NON-family off-board neighbour.
    fam_of_ref = {inst.ref: _FAMILY_OF.get(_conn_mpn(inst) or "")
                  for inst in model.insts if _conn_mpn(inst)}
    for fam, members in by_family.items():
        side_need = _FAMILY_SIDE_GAP_MM[fam]
        for ra, a in sorted(members):
            for rb, b in conns:
                if fam_of_ref.get(rb) == fam:
                    continue
                hit = _same_edge_gap(a, b)
                if hit is None:
                    continue
                axis, gap = hit
                ok = gap >= side_need
                res.pairs.append((ra, rb, f"{fam}|1", axis, gap, side_need, ok))
                if not ok:
                    res.violations.append(
                        f"{ra} <-> {rb} ({fam} one-sided): gap {gap:.2f}mm along "
                        f"{axis} < required {side_need:g}mm — the {fam} plug's "
                        f"own boot overhangs its copper into the neighbour")

    res.pairs.sort(key=lambda p: p[4])
    res.ok = not res.violations
    return res
