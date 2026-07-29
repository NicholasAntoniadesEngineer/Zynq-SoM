"""project — the PROJECT SPEC loader (P1 engine/project separation).

Board-specific POLICY that previously lived as engine constants (wired sheet
sets, the module pose, name-anchors, band prefixes, ref-keyed silk function
labels) is data in the project's ``project.json``; the engine is pure
MECHANISM reading it here. One project
today (``carrier/``); the resolution root generalizes to ``--project`` in a
later unit without touching any consumer.

Deterministic: the spec is read once per process and cached; every field has
the type the consumers need (frozensets / tuples), so consumers stay hashable
and byte-stable. A missing or malformed spec FAILS LOUDLY — a project without
a spec is a build error, not a silent default.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# U1f: the project root is data, not engine — SCHGEN_PROJECT names a directory
# (relative to the repo root, or absolute) holding project.json; the CLI's
# --project sets it before engine modules resolve their paths.
DEFAULT_PROJECT = "carrier"
_PROJ = os.environ.get("SCHGEN_PROJECT", DEFAULT_PROJECT)
PROJECT_ROOT = (Path(_PROJ) if Path(_PROJ).is_absolute()
                else REPO_ROOT / _PROJ)
IS_DEFAULT_PROJECT = PROJECT_ROOT == REPO_ROOT / DEFAULT_PROJECT


@dataclass(frozen=True)
class ProjectSpec:
    name: str
    wired_sheets: frozenset[str]
    pilot_prox_sheets: frozenset[str]
    module_offset: tuple[float, float]
    module_face_anchors: dict[str, str]
    reg_band_prefixes: tuple[str, ...]
    bank_rails: dict[str, str]
    escape: dict
    header_desc: dict[str, str]
    switch_desc: dict[str, str]


_CACHE: ProjectSpec | None = None


def spec() -> ProjectSpec:
    global _CACHE
    if _CACHE is None:
        raw = json.loads((PROJECT_ROOT / "project.json").read_text())
        pl = raw["placement"]
        lbl = raw.get("silk_labels", {})
        _CACHE = ProjectSpec(
            name=raw["name"],
            wired_sheets=frozenset(pl["wired_sheets"]),
            pilot_prox_sheets=frozenset(pl["pilot_prox_sheets"]),
            module_offset=(float(pl["module_offset"][0]),
                           float(pl["module_offset"][1])),
            module_face_anchors=dict(pl["module_face_anchors"]),
            reg_band_prefixes=tuple(pl["reg_band_prefixes"]),
            bank_rails={str(k): str(v) for k, v in
                        raw.get("fpga", {}).get("bank_rails", {}).items()},
            escape=dict(raw.get("escape", {})),
            header_desc={str(k): str(v)
                         for k, v in lbl.get("headers", {}).items()},
            switch_desc={str(k): str(v)
                         for k, v in lbl.get("switches", {}).items()},
        )
    return _CACHE
