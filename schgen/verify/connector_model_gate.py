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
        from schgen.verify._native_pcb import summary
        return summary("connector-model", self)


def _mpn_of(inst) -> str | None:
    if inst.value in CONN_MATING_FACE:
        return inst.value
    nm = inst.footprint.split(":")[-1]
    if nm in CONN_MATING_FACE:
        return nm
    return None


def check(model: PcbModel | None = None, *, prepared=None) -> ConnModelResult:
    from types import SimpleNamespace
    from schgen.core import native
    from schgen.verify._native_pcb import prepare
    if model is None:
        insts = []
        for mpn in sorted(CONN_MATING_FACE):
            path = resolve_mod(f"parts:{mpn}") or (
                Path(__file__).resolve().parents[2] / "parts" / mpn / f"{mpn}.kicad_mod")
            insts.append(SimpleNamespace(
                ref=mpn, value=mpn, footprint=f"parts:{mpn}", mod_path=path,
                sheet="", side="top", x=0.0, y=0.0, rotation=0.0, pad_nets={}))
        model = SimpleNamespace(board_w=0.0, board_h=0.0, insts=insts)
    return ConnModelResult(**native.module().pcb_connector_models((prepare(model) if prepared is None else prepared), CONN_MATING_FACE))
