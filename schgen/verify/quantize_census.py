"""QUANTIZE CENSUS — the lint that keeps the quantization registry honest
(governance U1, the enforcement half of ``schgen/core/quantize.py``).

Scans the GEOMETRY DATA-FLOW modules of ``schgen/generate/**`` (AST, so
strings/comments never false-positive) for raw quantization vocabulary that
bypasses the registry:

* ``compound-round``  — ``round(...)`` whose argument arithmetic contains a
                        nested ``round``/``int`` call (the grid-snap shape:
                        ``round(round(v / g) * g, n)``).
* ``lattice-mult``    — multiplication by an ``int(a / b)`` term (the
                        ceil/floor snap shape: ``int((v + s) / s) * s``).
* ``credit-0.05``     — a ``+/- 0.05`` on an expression whose identifiers name
                        needs/reaches/clearances (the quantization credit).
* ``banned-const``    — a numeric-literal (re)definition of a retired raw
                        constant (``_SNAP_EROSION``, ``_SEAT_SLIDE``,
                        ``OUTLINE_SNAP``, ``FINE_SNAP``, ...).
* ``banned-call``     — a call to a retired raw snapper (``_gridify``,
                        ``_r5``, ``_snap_up``, ``_snap_up_fp``).

Every live transform is routed through the registry, so the committed baseline
(``schgen/verify/data/quantize_census_baseline.json``) is EMPTY and any site
this census finds is NEW -> the board HARD-FAILS. Plain rounding for OUTPUT
formatting (report text, SVG coords, silk, images) is out of scope: the
scanned set below is the placement/copper geometry data flow only.
Deterministic: fixed file order, fixed detector order, pure source scan.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATE_DIR = REPO_ROOT / "schgen" / "generate"
BASELINE_PATH = Path(__file__).resolve().parent / "data" \
    / "quantize_census_baseline.json"

GEOMETRY_FILES: tuple[str, ...] = (
    "floorplan.py",
    "floorplan_compose.py",
    "compose_repair.py",
    "pcb/placement.py",
    "pcb/stage_templates.py",
    "pcb/breathe.py",
    "pcb/embed.py",
    "pcb/escape.py",
    "pcb/emit.py",
    "pcb/footprint.py",
    "pcb/mating_face.py",
    "pcb/constants.py",
    "pcb/stages.py",
)

_BANNED_CONSTS = frozenset({
    "_SNAP_EROSION", "_SEAT_SLIDE", "OUTLINE_SNAP", "OUTLINE_SNAP_PCB",
    "FINE_SNAP", "REFINE_SPAN", "GRID",
})
_BANNED_CALLS = frozenset({"_gridify", "_r5", "_snap_up", "_snap_up_fp"})
_GEOM_TOKENS = ("need", "reach", "clr", "clear", "bound", "lim", "gap",
                "margin")

KNOWN_ASYMMETRIES: tuple[str, ...] = (
    "_shelf_pack reserves extra = max(0, need - PLACE_CLEAR) WITHOUT the "
    "quant_credit its sibling sites carry — 18 fan-out subjects sit at slack "
    "exactly 0.000 (scan finding F1); behavior change queued for a "
    "post-governance unit (byte-identity gate forbids it here)",
    "the gate courtyard kernel rounds instance frames to 3dp (±5e-4/corner) "
    "while _TOUCH_EPS is 1e-4 — the measurement quantum dominates the "
    "documented tolerance 5x (scan finding F2); queued with F1",
)


@dataclass
class CensusResult:
    ok: bool = True
    n_registered: int = 0
    n_files: int = 0
    n_sites: int = 0
    n_new: int = 0
    sites: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"QUANTIZE CENSUS: {'PASS' if self.ok else 'FAIL'} — "
            f"{self.n_registered} registered transforms, {self.n_files} "
            f"geometry files scanned, {self.n_sites} raw site(s), "
            f"{self.n_new} NEW vs baseline"]
        lines += [f"  RAW SITE: {s}" for s in self.sites]
        lines += [f"  NEW (unregistered — route through "
                  f"schgen/core/quantize.py): {s}" for s in self.new]
        lines += [f"  NOTE (observed asymmetry, queued — no behavior "
                  f"change): {n}" for n in KNOWN_ASYMMETRIES]
        return "\n".join(lines)


def _has_nested_snap_call(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id in ("round", "int")):
            return True
    return False


def _ids(node: ast.AST) -> list[str]:
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.append(sub.attr)
    return out


def _scan_source(src: str, relpath: str) -> list[str]:
    tree = ast.parse(src)
    hits: list[str] = []

    def hit(detector: str, node: ast.AST) -> None:
        hits.append(f"{relpath}:{getattr(node, 'lineno', 0)} [{detector}]")

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "round" and node.args
                and isinstance(node.args[0], ast.BinOp)
                and _has_nested_snap_call(node.args[0])):
            hit("compound-round", node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for side in (node.left, node.right):
                if (isinstance(side, ast.Call)
                        and isinstance(side.func, ast.Name)
                        and side.func.id == "int" and side.args
                        and any(isinstance(s, (ast.Div, ast.FloorDiv))
                                for s in ast.walk(side.args[0])
                                if isinstance(s, ast.operator))):
                    hit("lattice-mult", node)
                    break
        if (isinstance(node, ast.BinOp)
                and isinstance(node.op, (ast.Add, ast.Sub))):
            for a, b in ((node.left, node.right), (node.right, node.left)):
                if (isinstance(a, ast.Constant) and a.value == 0.05
                        and any(t in i.lower() for i in _ids(b)
                                for t in _GEOM_TOKENS)):
                    hit("credit-0.05", node)
                    break
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names & _BANNED_CONSTS and node.value is not None and all(
                    isinstance(c, (ast.Constant, ast.BinOp, ast.UnaryOp))
                    for c in ast.walk(node.value)
                    if isinstance(c, ast.expr)):
                hit("banned-const", node)
        if isinstance(node, ast.Call):
            fn = node.func
            name = (fn.id if isinstance(fn, ast.Name)
                    else fn.attr if isinstance(fn, ast.Attribute) else "")
            if name in _BANNED_CALLS:
                hit("banned-call", node)
    return hits


def scan(root: Path | None = None,
         files: tuple[str, ...] | None = None) -> tuple[list[str], int]:
    base = root or GENERATE_DIR
    rels = files if files is not None else GEOMETRY_FILES
    sites: list[str] = []
    n_files = 0
    for rel in rels:
        p = base / rel
        if not p.exists():
            continue
        n_files += 1
        sites.extend(_scan_source(p.read_text(), rel))
    return sites, n_files


def _load_baseline(path: Path | None = None) -> dict[str, int]:
    p = path or BASELINE_PATH
    try:
        raw = json.loads(p.read_text())
        return {str(k): int(v) for k, v in raw.get("allowed", {}).items()}
    except Exception:  # noqa: BLE001 — absent/corrupt baseline allows nothing
        return {}


def check(root: Path | None = None, files: tuple[str, ...] | None = None,
          baseline_path: Path | None = None) -> CensusResult:
    from schgen.core.quantize import REGISTRY
    sites, n_files = scan(root, files)
    allowed = _load_baseline(baseline_path)
    by_key: dict[str, list[str]] = {}
    for s in sites:
        key = s.split(":", 1)[0] + " " + s.rsplit("[", 1)[-1].rstrip("]")
        by_key.setdefault(key, []).append(s)
    new: list[str] = []
    for key in sorted(by_key):
        over = len(by_key[key]) - allowed.get(key, 0)
        if over > 0:
            new.extend(by_key[key][:over])
    return CensusResult(
        ok=not new, n_registered=len(REGISTRY), n_files=n_files,
        n_sites=len(sites), n_new=len(new), sites=sorted(sites),
        new=sorted(new))
