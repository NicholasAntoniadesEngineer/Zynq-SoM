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

RULE (any violation HARD-FAILS the board):
  For every pair of off-board connectors of the SAME overmold family on the SAME
  board edge, the edge-to-edge gap between their COPPER (pad) bboxes — measured
  ALONG the edge (the axis the two neighbours are separated on) — must be at least
  the family's required overmold clearance ``_FAMILY_MIN_GAP_MM[family]``. A
  smaller gap means the two plug overmolds would collide; FAIL.

The min-gap table is small and per-family so a new wide connector is one entry:
  HDMI-019S : 18 mm  (HDMI plug overmold boot ~18-22 mm wide)

LAW 4: strict — a too-tight pair is FIXED in the placer (spread the two
connectors along the edge, or move one to a different edge), NEVER waived here.
The measured gap is reported so a regression shows AS a number, not a binary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schgen.generate.pcb import (PcbModel, ORIGIN_X, ORIGIN_Y, CONN_MATING_FACE,
                                 _inst_pad_bbox)


# overmold-family -> minimum required edge-to-edge gap (mm) between two of that
# family's connectors mating SIMULTANEOUSLY on the same edge. The value is the
# cable-plug overmold/strain-relief boot width (the part wider than the PCB
# footprint). Keyed by the connector MPN so adding a wide connector is one line.
_FAMILY_MIN_GAP_MM: dict[str, float] = {
    "HDMI-019S": 18.0,   # HDMI Type-A plug overmold boot ~18-22 mm wide
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
        L.append(f"  same-family same-edge connector pairs: {len(self.pairs)} "
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
                # overlap on each axis
                ox = _overlap_1d(a[0], a[2], b[0], b[2])
                oy = _overlap_1d(a[1], a[3], b[1], b[3])
                wx = min(a[2] - a[0], b[2] - b[0])
                hy = min(a[3] - a[1], b[3] - b[1])
                same_x_band = wx > 0 and ox >= _SAME_BAND_FRAC * wx
                same_y_band = hy > 0 and oy >= _SAME_BAND_FRAC * hy
                # SAME EDGE = they share one band and are separated on the other
                # axis: y-band overlap + x separation => a horizontal edge (N/S),
                # neighbours separated ALONG x; vice-versa for E/W edges.
                if same_y_band and not same_x_band:
                    axis = "x"
                    gap = max(a[0], b[0]) - min(a[2], b[2])
                elif same_x_band and not same_y_band:
                    axis = "y"
                    gap = max(a[1], b[1]) - min(a[3], b[3])
                else:
                    continue              # not a same-edge side-by-side pair
                ok = gap >= need
                res.pairs.append((ra, rb, fam, axis, gap, need, ok))
                if not ok:
                    res.violations.append(
                        f"{ra} <-> {rb} ({fam}): overmold gap {gap:.2f}mm along "
                        f"{axis} < required {need:g}mm — the two cable plugs' "
                        f"overmolds would collide; cannot mate both at once")

    res.pairs.sort(key=lambda p: p[4])
    res.ok = not res.violations
    return res
