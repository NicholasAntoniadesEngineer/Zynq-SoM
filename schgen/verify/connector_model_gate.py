from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from schgen.generate.pcb import CONN_MATING_FACE, PcbModel, Sym, resolve_mod, sexpr

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
    "XT60PW-M":
        "ESC power XT60: the plug mates onto the bullet contacts (pads 1/2 at "
        "local +X, the chamfered fp_arc mouth at +X), not opposite a dense SMT "
        "tail row — same class as RJ45/QWIIC, so the copper tail-row rule (2) does "
        "not apply. CONN_MATING_FACE=+X matches the footprint. NOTE: the EasyEDA "
        ".wrl shipped facing -X, so it was re-oriented 180deg about Z in the .wrl "
        "itself (footprint model-rotate stays 0 so bad-Z stays clean) — 3D-render-"
        "verified (E-edge view shows the bullet mouths facing off-board).",
}

_GEOM_SHELL = ("TYPE-C-31-M-12", "HDMI-019S")

assert set(_GEOM_SHELL) | set(_GEOM_EXCEPTIONS) >= set(CONN_MATING_FACE), (
    "connector_model_gate: a CONN_MATING_FACE MPN is neither geometry-checked "
    "nor a reviewed exception — review it, do not leave it unclassified: "
    + repr(sorted(set(CONN_MATING_FACE)
                  - set(_GEOM_SHELL) - set(_GEOM_EXCEPTIONS))))

_NUMERIC = re.compile(r"\d+")


def _model_z(mod_path: Path) -> float | None:
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
    doc = sexpr.loads(mod_path.read_text())
    pads: list[tuple[str, float]] = []
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
        pads.append((name, y))
    if not pads or not all_y:
        return None
    rows = Counter(round(y, 1) for _, y in pads)
    tail_y = rows.most_common(1)[0][0]
    center_y = (min(all_y) + max(all_y)) / 2.0
    if abs(tail_y - center_y) < 0.5:
        return None
    tail_side = "+Y" if tail_y > center_y else "-Y"
    return "-Y" if tail_side == "+Y" else "+Y"


@dataclass
class ConnModelResult:
    ok: bool = True
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
        for ref, mpn, _value, z, ok in self.models:
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
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def check(model: PcbModel | None = None) -> ConnModelResult:
    res = ConnModelResult()

    if model is not None:
        rows = []
        for inst in model.insts:
            mpn = _mpn_of(inst)
            if mpn is None:
                continue
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
