from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import ledger

REPO_ROOT = Path(__file__).resolve().parents[2]

CENSUS_FILES: dict[str, str] = {
    "config": "schgen/core/config.py",
    "quantize": "schgen/core/quantize.py",
    "floorplan": "schgen/generate/floorplan.py",
    "pcbconst": "schgen/generate/pcb/constants.py",
    "placement": "schgen/generate/pcb/placement.py",
    "fanout": "schgen/verify/fanout_gate.py",
    "ratsnest": "schgen/verify/ratsnest_gate.py",
}

NUMERIC_CALLS = frozenset({"round", "int", "float", "min", "max", "abs"})
FIRST_INDEX = 0


@dataclass
class LedgerResult:
    ok: bool = True
    n_declared: int = 0
    n_recorded: int = 0
    n_lines: int = 0
    n_constants: int = 0
    n_files: int = 0
    absent: list[str] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)
    buried: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"BUILD LEDGER GATE: {'PASS' if self.ok else 'FAIL'} — "
            f"{self.n_declared} declared entries, {self.n_recorded} recorded, "
            f"{self.n_lines} ledger lines, {self.n_constants} constants over "
            f"{self.n_files} decision files"]
        lines += [f"  DECLARED BUT ABSENT (it influenced the board without "
                  f"appearing in the ledger): {n}" for n in self.absent]
        lines += [f"  UNDECLARED CONSTANT (declare it in "
                  f"schgen/core/ledger.py): {n}" for n in self.undeclared]
        lines += [f"  BURIED CONSTANT (hoist it to module scope): {n}"
                  for n in self.buried]
        lines += [f"  STALE COVER (the declaration names a constant that no "
                  f"longer exists): {n}" for n in self.stale]
        lines += [f"  LEDGER PROBLEM: {n}" for n in self.divergences]
        return "\n".join(lines)


def _numeric(node: ast.AST, known: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return (isinstance(node.value, (int, float))
                and not isinstance(node.value, bool))
    if isinstance(node, ast.UnaryOp):
        return _numeric(node.operand, known)
    if isinstance(node, ast.BinOp):
        return _numeric(node.left, known) and _numeric(node.right, known)
    if isinstance(node, ast.Name):
        return node.id in known
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in NUMERIC_CALLS):
        return all(_numeric(a, known) for a in node.args)
    return False


def _targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _is_upper(name: str) -> bool:
    return name.lstrip("_").isupper() and any(c.isalpha() for c in name)


def scan(alias: str, path: Path) -> tuple[list[str], list[str]]:
    tree = ast.parse(path.read_text())
    known: set[str] = set()
    top: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        for name in _targets(node):
            if node.value is not None and _numeric(node.value, known):
                known.add(name)
                top.append(f"{alias}.{name}")
    buried: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, (ast.Assign, ast.AnnAssign)):
                continue
            for name in _targets(sub):
                if (_is_upper(name) and sub.value is not None
                        and _numeric(sub.value, known)):
                    buried.append(
                        f"{CENSUS_FILES[alias]}:{sub.lineno} "
                        f"{node.name}.{name}")
    return top, sorted(set(buried))


def _covered() -> set[str]:
    out: set[str] = set()
    for d in ledger.REGISTRY.values():
        out.update(d.covers)
    return out


def _resolves(path: str) -> bool:
    alias, _dot, attr = path.partition(".")
    module = ledger.MODULE_ALIAS.get(alias)
    if module is None:
        return False
    return hasattr(importlib.import_module(module), attr)


def check(root: Path | None = None) -> LedgerResult:
    base = root or REPO_ROOT
    res = LedgerResult(n_declared=len(ledger.REGISTRY),
                       n_recorded=len(ledger.recorded()),
                       n_lines=len(ledger.entries()))
    covered = _covered()
    constants: list[str] = []
    for alias, rel in CENSUS_FILES.items():
        p = base / rel
        if not p.exists():
            continue
        res.n_files += 1
        top, buried = scan(alias, p)
        constants += top
        res.buried += buried
    res.n_constants = len(constants)
    res.undeclared = sorted(c for c in constants if c not in covered)
    res.stale = sorted(c for c in covered if not _resolves(c))
    seen = ledger.recorded()
    res.absent = sorted(n for n, d in ledger.REGISTRY.items()
                        if not d.repeated and n not in seen)
    res.divergences = list(ledger.problems())
    res.ok = not (res.absent or res.undeclared or res.buried or res.stale
                  or res.divergences)
    return res
