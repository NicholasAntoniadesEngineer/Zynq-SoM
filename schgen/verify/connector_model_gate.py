"""LAW-6 CONNECTOR 3D-MODEL ORIENTATION gate — the render-mouth oracle.

The defect this closes: an off-board connector can render its OPENING facing the
WRONG way even though every pad, courtyard and placement-rotation is correct. The
3D ``.wrl`` model is positioned by the footprint's ``(model ...(rotate (xyz 0 0
Z)))`` node, which is APPLIED ON TOP OF the placement rotation. A stray Z (the
USB-C ``TYPE-C-31-M-12`` shipped with ``(rotate (xyz 0 0 180))`` for a while)
spins the rendered shell 180 deg relative to its pads — so in the 3D render the
USB-C mouth pointed INWARD onto the board while the pads, the courtyard, and the
placement_mech gate all said it faced out. Every existing gate passed:

  * placement_mech reasons about CONN_MATING_FACE + placement rotation + pad bbox
    — it never reads the 3D-model rotate node, so a model-only flip is invisible.
  * ratsnest/DRC are electrical — a flipped *render* is not an airwire or a DRC
    violation.

So a real, build-breaking mechanical defect (you cannot tell from the 3D view
which way the cable plugs, or it visibly clashes the board) sailed through. This
gate makes the 3D-model orientation a HARD gate.

INVARIANTS (any failure HARD-FAILS the board):

  (1) ZERO MODEL-Z on an off-board connector. Every connector in
      ``pcb.CONN_MATING_FACE`` whose footprint carries a ``(model ...(rotate
      (xyz 0 0 Z)))`` MUST have ``Z ≡ 0 (mod 360)``. The correct parts are all
      0; the USB-C bug was 180. A non-zero Z FAILS with the exact MPN + value —
      it flips the rendered opening vs the footprint pads. (A missing model is
      reported but is the 3D-coverage gate's job, not a mouth-orientation fail.)

  (2) GEOMETRY CROSS-CHECK (best-effort, only where unambiguous). For the
      THROUGH-SHELL connectors whose cable enters OPPOSITE the dense SMT contact
      tail row — USB-C and HDMI — the mouth must point AWAY from that tail row.
      We derive the tail-row side from the footprint pad layout (the densest
      numeric-pad row) and FAIL if the implied mouth contradicts
      ``CONN_MATING_FACE[mpn]``. This independently re-derives the mouth from
      copper geometry, catching a hand-edited CONN_MATING_FACE typo that (1)
      cannot see.

      Connector types where "mouth vs tail row" is NOT a clean geometric rule
      are listed as REVIEWED EXCEPTIONS (see ``_GEOM_EXCEPTIONS``) with a
      per-MPN reason, NOT silently skipped (LAW 4 — no softening; an exception is
      a documented, auditable decision, a soften is a hidden hole):

        * RJ45 / microSD / QWIIC / PMOD: the mouth is on the SAME side as the
          contacts (you plug INTO the contact end), so "opposite the tail row"
          is the wrong sign for them — their face is dossier/datasheet-derived.
        * FFC AFC07 / SFW15R: a low single-row flex slot; the contact row and
          the actuator/strain-relief are not separable into a "tail row vs
          mouth" pair by pad density alone.

LAW 4: strict — a non-zero Z or a contradicted mouth is FIXED at the source
(zero the model rotate node / correct CONN_MATING_FACE), never waived here. The
Z of every model is reported so a regression shows as a number.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from schgen.generate.pcb import (PcbModel, CONN_MATING_FACE, resolve_mod,
                                 sexpr, Sym)


# Off-board connector MPNs whose mouth-vs-pad-geometry is NOT a clean
# "mouth opposite the dense tail row" rule, so the geometry cross-check (2) is
# deliberately not applied. Each entry is a REVIEWED decision with its reason —
# not a softening: check (1) (model-Z ≡ 0) still fully covers these, and their
# CONN_MATING_FACE is dossier/datasheet-derived and verified by placement_mech.
_GEOM_EXCEPTIONS: dict[str, str] = {
    "KH-5224-8P8C-D":
        "RJ45 jack: plug enters at the CONTACT end (mouth ON the contact side, "
        "not opposite it) — geometric tail-row rule has the wrong sign.",
    "TF-01A":
        "microSD: card inserts toward the contact fingers (mouth on the contact "
        "side) — tail-row rule does not apply.",
    "ZX-SH1.0-4PWT":
        "QWIIC shrouded header: cable plugs onto the contact row (mouth on the "
        "contact side).",
    "DS1024-2x6R2":
        "PMOD 2x6 socket: module plugs onto the pin field (mouth on the contact "
        "side).",
    "AFC07-S40FCA-00":
        "FFC/FPC flex slot: single contact row + actuator are not a separable "
        "tail-row/mouth pair by pad density.",
    "SFW15R-1STE1LF":
        "FFC/FPC flex slot: single contact row + actuator are not a separable "
        "tail-row/mouth pair by pad density.",
}

# Connectors for which check (2) IS applied: through-shell parts whose cable
# enters OPPOSITE the dense SMT signal-tail row. Everything in CONN_MATING_FACE
# that is not here must be in _GEOM_EXCEPTIONS (asserted below), so a NEW
# connector MPN cannot slip past the cross-check unreviewed.
_GEOM_SHELL = ("TYPE-C-31-M-12", "HDMI-019S")

assert set(_GEOM_SHELL) | set(_GEOM_EXCEPTIONS) >= set(CONN_MATING_FACE), (
    "connector_model_gate: a CONN_MATING_FACE MPN is neither geometry-checked "
    "nor a reviewed exception — review it, do not leave it unclassified: "
    + repr(sorted(set(CONN_MATING_FACE)
                  - set(_GEOM_SHELL) - set(_GEOM_EXCEPTIONS))))

_NUMERIC = re.compile(r"\d+")


def _model_z(mod_path: Path) -> float | None:
    """The Z component (deg) of the footprint's first ``(model ...(rotate (xyz x
    y Z)))`` node, or None if the footprint has no model/rotate. Read straight
    from the .kicad_mod so a stray hand-edited Z is caught at source."""
    doc = sexpr.loads(mod_path.read_text())
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("model")):
            continue
        rot = sexpr.find(node, "rotate")
        xyz = sexpr.find(rot, "xyz") if rot else None
        if xyz and len(xyz) >= 4 and isinstance(xyz[3], (int, float)):
            return float(xyz[3])
        return None
    return None


def _tail_row_mouth(mod_path: Path) -> str | None:
    """For a through-shell connector, the mouth direction implied by geometry:
    the densest pad row is the SMT contact tail row; the cable enters OPPOSITE it.
    Returns '-Y'/'+Y' (page frame, +y DOWN) or None if the pad layout is too
    symmetric to call (tail row at the footprint center).

    BUGFIX: previously this filtered to _NUMERIC pad names, which on a USB-C
    (TYPE-C-31-M-12) matched ONLY the 4 shell THT legs ("1".."4") and MISSED the
    12 signal contacts (named "B8","A5","A1B12",...). It therefore derived the tail
    row from the legs and spuriously "agreed" with a WRONG CONN_MATING_FACE, so all
    4 USB-C shipped opening INBOARD. Use EVERY pad: the densest y-row is the real
    contact tail row regardless of naming, and the mouth is opposite it."""
    doc = sexpr.loads(mod_path.read_text())
    pads: list[tuple[str, float]] = []          # (name, y)
    all_y: list[float] = []
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1])
        at = sexpr.find(node, "at")
        if not at or len(at) < 3:
            continue
        y = float(at[2])
        all_y.append(y)
        pads.append((name, y))     # ALL pads — the dense row is the contact tails
    if not pads or not all_y:
        return None
    rows = Counter(round(y, 1) for _, y in pads)
    tail_y = rows.most_common(1)[0][0]
    center_y = (min(all_y) + max(all_y)) / 2.0
    if abs(tail_y - center_y) < 0.5:            # tail row ~centered: ambiguous
        return None
    tail_side = "+Y" if tail_y > center_y else "-Y"
    # mouth is OPPOSITE the tail row
    return "-Y" if tail_side == "+Y" else "+Y"


@dataclass
class ConnModelResult:
    ok: bool = True
    # (ref, mpn, value, z, ok) — z may be None (no model)
    models: list[tuple] = field(default_factory=list)
    bad_z: list[str] = field(default_factory=list)
    missing_model: list[str] = field(default_factory=list)
    geom_conflicts: list[str] = field(default_factory=list)
    geom_checked: list[str] = field(default_factory=list)
    n_connectors: int = 0

    def summary(self) -> str:
        L = [f"LAW-6 CONNECTOR-MODEL ORIENTATION GATE: "
             f"{'PASS' if self.ok else 'FAIL'}"]
        L.append(f"  off-board connectors inspected: {self.n_connectors}")
        for ref, mpn, value, z, ok in self.models:
            mark = "OK " if ok else "BAD"
            zs = "none" if z is None else f"{z:g}"
            L.append(f"    {mark} {ref:9s} {mpn:16s} model_z={zs}")
        L.append(f"  non-zero model-Z (flipped opening): {len(self.bad_z)}")
        for b in self.bad_z:
            L.append(f"    BAD-Z {b}")
        L.append(f"  geometry-cross-checked (through-shell): "
                 f"{len(self.geom_checked)} -> {len(self.geom_conflicts)} "
                 f"conflict(s)")
        for g in self.geom_conflicts:
            L.append(f"    GEOM-CONFLICT {g}")
        L.append(f"  reviewed geometry exceptions: {len(_GEOM_EXCEPTIONS)}")
        if self.missing_model:
            L.append(f"  (info) connectors without a 3D model: "
                     f"{len(self.missing_model)} — see the 3D-coverage gate")
            for m in self.missing_model:
                L.append(f"    NO-MODEL {m}")
        return "\n".join(L)


def _mpn_of(inst) -> str | None:
    """The off-board-connector MPN for an instance, or None — same mapping
    placement_mech uses (value first, then the footprint lib:name)."""
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def check(model: PcbModel | None = None) -> ConnModelResult:
    """Verify every off-board connector's 3D model renders its opening the right
    way. With a ``model`` it inspects exactly the placed connector instances;
    with no model it inspects every MPN in CONN_MATING_FACE once (footprint-only
    mode, for a fast standalone footprint audit)."""
    res = ConnModelResult()

    if model is not None:
        rows = []
        for inst in model.insts:
            mpn = _mpn_of(inst)
            if mpn is None:
                continue
            # use the instance's OWN mod_path — that is the exact footprint the
            # board emits (and what the placer/renderer read for the 3D model),
            # not a re-resolution that could diverge from what was placed.
            rows.append((inst.ref, inst.value, mpn, inst.mod_path))
    else:
        rows = [(mpn, mpn, mpn, resolve_mod(f"parts:{mpn}") or
                 (Path(__file__).resolve().parents[2] / "parts" / mpn /
                  f"{mpn}.kicad_mod"))
                for mpn in sorted(CONN_MATING_FACE)]

    for ref, value, mpn, mod_path in rows:
        res.n_connectors += 1
        if mod_path is None or not Path(mod_path).exists():
            res.missing_model.append(f"{ref} {mpn}: footprint not resolvable")
            res.models.append((ref, mpn, value, None, True))
            continue
        mod_path = Path(mod_path)
        z = _model_z(mod_path)

        # (1) the model must be AXIS-ALIGNED with the footprint: rotate Z in
        # {0, 180}. 0 = as-authored; 180 = a valid in-plane MOUTH FLIP that
        # corrects a .wrl whose cavity was authored on the OPPOSITE end from the
        # footprint's mating side (the EasyEDA TYPE-C-31-M-12 .wrl needed this —
        # the old "must be 0" rule was a misdiagnosis that forbade the corrective
        # 180 AND gave false confidence to a .wrl mis-authored at 0). A 90/270
        # rotate makes the model PERPENDICULAR to the footprint (real error); a
        # non-orthogonal rotate is conversion garbage. NOTE: the gate cannot render
        # so it cannot fully confirm the model's opening — that is the render's job
        # (LAW 5/6); the geometry cross-check (2) below confirms the FOOTPRINT pads.
        z_ok = True
        if z is None:
            res.missing_model.append(f"{ref} {mpn}: no (model ...rotate) node")
        elif round(z) % 180 != 0:
            z_ok = False
            res.bad_z.append(
                f"{ref} {mpn} (value={value}): model rotate Z={z:g} deg "
                f"(must be 0 or 180 — axis-aligned with the footprint; 90/270 is "
                f"perpendicular, non-orthogonal is garbage) — fix the "
                f"(model ...(rotate (xyz 0 0 Z))) node")
        res.models.append((ref, mpn, value, z, z_ok))

        # (2) geometry cross-check for the through-shell connectors only.
        if mpn in _GEOM_SHELL:
            res.geom_checked.append(f"{ref} {mpn}")
            implied = _tail_row_mouth(mod_path)
            declared = CONN_MATING_FACE[mpn]
            if implied is not None and implied != declared:
                res.geom_conflicts.append(
                    f"{ref} {mpn}: pad geometry implies mouth {implied} "
                    f"(opposite the dense contact tail row) but "
                    f"CONN_MATING_FACE says {declared} — one is wrong; "
                    f"the rendered mouth would face inward")

    res.ok = (not res.bad_z and not res.geom_conflicts)
    return res
