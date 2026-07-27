"""LAW-6 MECHANICAL / USE-CASE placement gate — the buildability oracle.

The defect this closes: a densifier shrank the carrier 36 % yet left it
UNBUILDABLE — off-board connectors interior and inward-facing (you could not
plug a cable in), parts crushed under the SoM module body, buttons scattered —
and EVERY electrical gate passed (DRC = 0, ratsnest LAW-5 PASS, ERC 0). DRC and
the airwire budget are blind to mechanics: a connector you cannot mate, a button
you cannot press, and a part under a module are none of them DRC errors.

LAW 6 makes the MECHANIZABLE rules a HARD gate (any failure fails the board):

  (a) OFF-BOARD CONNECTOR ON AN EDGE, MATING FACE OUT. Every connector that mates
      with an external cable / plug / card (the MPNs in pcb.CONN_MATING_FACE:
      USB-C, HDMI, RJ45, microSD, the FFC/FPC ribbons, QWIIC, PMOD) MUST sit on a
      board edge with its mouth pointing OFF the board. An interior connector, or
      one rotated so its mouth faces inward, is a FAIL.

  (b) SoM MODULE-BODY KEEPOUT (side-split; LAW 6 as amended 2026-07-09). The
      rectangle the plugged-in SoM overhangs (model.som_core): the carrier TOP
      under it is a FULL keepout — NO component at all, low-profile passives
      included (the mated standoff gap leaves no usable height). The carrier
      BOTTOM under it is the OPPOSITE board face — any part is fine there
      (som_decoupling's caps live there). Only the DF40 receptacles themselves,
      mounting holes and the zero-height stencil fiducials are exempt on top.

  (c) CONTROLS REACHABLE. A button / switch must be pressable and a coin cell
      replaceable — none may sit under the SoM (a control buried under the module
      is unusable). This is the (b) check specialised to controls so the verdict
      names the exact unreachable control.

LAW 4: strict — a misplaced connector or a part under the SoM is FIXED in the
placer (rotate it to its edge, reserve the SoM body, relocate the control),
never waived here. Numbers are reported so a regression shows as numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from schgen.generate.pcb import (
    CONN_MATING_FACE,
    EDGE_FLUSH_MM,
    ORIGIN_X,
    ORIGIN_Y,
    PcbModel,
    _inst_courtyard,
    _mating_face_out_dir,
)

# overlap (mm^2 of courtyard area inside the SoM core) below this is numerical
# touch from grid snap, not a real placement under the module.
_OVERLAP_EPS = 0.5

# ref-prefix taxonomy. Only R/C/L discrete passives may sit under the SoM.
_PASSIVE_PREFIX = ("R", "C", "L")
_BUTTON_PREFIX = ("SW",)            # tactile buttons + DIP switches
_COINCELL_PREFIX = ("BT",)         # coin-cell holder
_TESTPOINT_PREFIX = ("TP",)


def _ref_prefix(ref: str) -> str:
    m = re.match(r"[A-Za-z]+", ref)
    return m.group(0) if m else ref


def _is_passive_under_som(ref: str) -> bool:
    """True only for a discrete R/C/L passive (the parts a module may overhang).
    RS (current-shunt), RJ (RJ45) and LED are NOT plain passives."""
    p = _ref_prefix(ref)
    if ref.startswith(("RS", "RJ", "LED")):
        return False
    return p in _PASSIVE_PREFIX


def _is_control(ref: str) -> bool:
    return _ref_prefix(ref) in (_BUTTON_PREFIX + _COINCELL_PREFIX)


def _rect_overlap_area(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0.0, min(ay1, by1) - max(ay0, by0))
    return ox * oy


@dataclass
class MechResult:
    ok: bool = True
    board_w: float = 0.0
    board_h: float = 0.0
    n_connectors: int = 0
    connectors: list[tuple] = field(default_factory=list)  # report rows
    bad_connectors: list[str] = field(default_factory=list)
    under_som: list[str] = field(default_factory=list)
    controls_under_som: list[str] = field(default_factory=list)
    top_under_som: list[str] = field(default_factory=list)
    som_core: tuple | None = None

    def summary(self) -> str:
        L = [f"LAW-6 PLACEMENT (mechanical) GATE: {'PASS' if self.ok else 'FAIL'} "
             f"(board {self.board_w:g} x {self.board_h:g} mm)"]
        sc = self.som_core
        if sc:
            L.append(f"  SoM module-body core: ({sc[0]:.1f},{sc[1]:.1f}).."
                     f"({sc[2]:.1f},{sc[3]:.1f}) mm — "
                     f"bottom-passives-only, TOP keepout")
        L.append(f"  off-board connectors: {self.n_connectors} "
                 f"({len(self.bad_connectors)} mis-placed)")
        for ref, mpn, edge, rot, face_dir, flush, ok in self.connectors:
            mark = "OK " if ok else "BAD"
            L.append(f"    {mark} {ref:9s} {mpn:16s} edge={edge} rot={rot:>3.0f} "
                     f"mouth->{face_dir} flush={flush:.1f}mm")
        for b in self.bad_connectors:
            L.append(f"    MISPLACED {b}")
        L.append(f"  non-passive parts under SoM core: {len(self.under_som)}")
        for u in self.under_som:
            L.append(f"    UNDER-SoM {u}")
        L.append(f"  controls under SoM core: {len(self.controls_under_som)}")
        for c in self.controls_under_som:
            L.append(f"    CONTROL-UNDER-SoM {c}")
        L.append(f"  carrier TOP parts under SoM core (keepout): "
                 f"{len(self.top_under_som)}")
        for t in self.top_under_som:
            L.append(f"    TOP-UNDER-SoM {t}")
        return "\n".join(L)


def check(model: PcbModel) -> MechResult:
    res = MechResult(board_w=model.board_w, board_h=model.board_h,
                     som_core=model.som_core)
    bx0, by0 = ORIGIN_X, ORIGIN_Y
    bx1, by1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    # board-edge direction the off-board side of each edge points (page +y DOWN)
    edge_out = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}

    for inst in model.insts:
        mpn = inst.value if inst.value in CONN_MATING_FACE else None
        # footprint name (lib:name) also carries the MPN
        if mpn is None:
            nm = inst.footprint.split(":")[-1]
            if nm in CONN_MATING_FACE:
                mpn = nm
        if mpn is None:
            continue
        res.n_connectors += 1
        cx0, cy0, cx1, cy1 = _inst_courtyard(inst)
        # which board edge is this connector nearest? (the edge its courtyard
        # sits against). Distance from each board edge to the connector's
        # OUTER courtyard face.
        d = {"N": cy0 - by0, "S": by1 - cy1, "W": cx0 - bx0, "E": bx1 - cx1}
        edge = min(d, key=lambda e: d[e])
        flush = d[edge]
        face_dir = _mating_face_out_dir(CONN_MATING_FACE[mpn], inst.rotation)
        mouth_out = (face_dir == edge_out[edge])
        on_edge = (flush <= EDGE_FLUSH_MM)
        ok = on_edge and mouth_out
        res.connectors.append(
            (inst.ref, mpn, edge, float(inst.rotation), face_dir, flush, ok))
        if not ok:
            why = []
            if not on_edge:
                why.append(f"interior ({flush:.1f}mm > {EDGE_FLUSH_MM:g}mm "
                           f"off the {edge} edge)")
            if not mouth_out:
                why.append(f"mouth {face_dir} faces inward (off-board for the "
                           f"{edge} edge is {edge_out[edge]})")
            res.bad_connectors.append(
                f"{inst.ref} ({inst.sheet}) {mpn}: " + "; ".join(why))

    # (b)/(c) SoM module-body core: passives only.
    core = model.som_core
    if core is not None:
        for inst in model.insts:
            ct = _inst_courtyard(inst)
            ov = _rect_overlap_area(ct, core)
            if ov <= _OVERLAP_EPS:
                continue
            if inst.mod_path.name.startswith("MountingHole"):
                continue          # not a placed component
            if inst.mod_path.name.startswith("Fiducial"):
                continue          # zero-height PCB fab-art (a bare-copper
                #                   registration dot) — no body to collide with the
                #                   module in the standoff gap; the local pair is
                #                   DELIBERATELY next to the under-SoM DF40s so the
                #                   fine-pitch stencil can register there (GAP3).
            if inst.sheet.startswith("som_j"):
                continue          # the DF40 mezzanine receptacles ARE the SoM
                #                   interface — they MUST sit under the module
                #                   body (the SoM plugs onto them). Not a defect.
            if inst.side == "bottom":
                continue          # LAW 6: the carrier BOTTOM under the SoM is the
                #                   OPPOSITE face from the module — ANY part (active
                #                   or passive) is fine there (uses dead space). Only
                #                   the TOP (the standoff gap with the SoM's own
                #                   bottom components) is the keepout, below.
            row = (f"{inst.ref} ({inst.sheet}) {inst.value} [TOP]: courtyard "
                   f"({ct[0]:.1f},{ct[1]:.1f})..({ct[2]:.1f},{ct[3]:.1f}) "
                   f"overlaps SoM core — carrier TOP under the module is a keepout")
            # a TOP-side part under the SoM collides with the module's components in
            # the standoff gap. Classify a passive as top_under_som (the relaxation
            # that was previously allowed), a non-passive as under_som.
            if _is_passive_under_som(inst.ref):
                res.top_under_som.append(row)
                continue
            res.under_som.append(row)
            if _is_control(inst.ref):
                res.controls_under_som.append(row)

    res.ok = (not res.bad_connectors and not res.under_som
              and not res.controls_under_som and not res.top_under_som)
    return res
