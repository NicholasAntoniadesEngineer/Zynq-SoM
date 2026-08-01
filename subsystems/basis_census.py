from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from subsystems import basis

SUBSYSTEMS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUBSYSTEMS_DIR.parent
CONSUMER_ROOTS = ("carrier/subsystems", "devkit_mini/subsystems",
                  "examples")

PASSIVE_LIBS = frozenset({"Device:R", "Device:C", "Device:L"})

VALUE_ARG = {"part": 2, "pullup": 1, "pulldown": 1, "series": 2}
VARIADIC_FROM = {"decouple": 1}

_SI_VALUE = re.compile(r"^[0-9]+(\.[0-9]+)?([pnuµmkKMG]?)([0-9]*)"
                       r"(R|F|H|Hz|uH|MHz|kHz)?$")


def _is_si_value(text: str) -> bool:
    return bool(_SI_VALUE.fullmatch(text)) and any(ch.isdigit() for ch in text)


@dataclass
class CensusResult:
    ok: bool = True
    n_registered: int = 0
    n_files: int = 0
    n_sites: int = 0
    raw: list[str] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"BASIS CENSUS: {'PASS' if self.ok else 'FAIL'} — "
            f"{self.n_registered} registered component values, "
            f"{self.n_files} subsystem netlists scanned, "
            f"{self.n_sites} value site(s), {len(self.raw)} RAW"]
        lines += [f"  RAW LITERAL (declare it in subsystems/basis.py): {s}"
                  for s in self.raw]
        lines += [f"  UNREGISTERED constant: {s}" for s in self.undeclared]
        lines += [f"  DEAD registration (no site uses it): {s}"
                  for s in self.unused]
        lines += [f"  BROKEN entry: {s}" for s in self.broken]
        return "\n".join(lines)


def _netlist_files() -> list[Path]:
    out = []
    for child in sorted(SUBSYSTEMS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        p = child / f"{child.name}.py"
        if p.exists():
            out.append(p)
    return out


def _consumer_files() -> list[Path]:
    out: list[Path] = []
    for rel in CONSUMER_ROOTS:
        root = REPO_ROOT / rel
        if root.is_dir():
            out.extend(sorted(root.rglob("*.py")))
    return out


def _referenced_names(paths: list[Path]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in basis.REGISTRY:
                out.add(node.id)
            elif isinstance(node, ast.Attribute) \
                    and node.attr in basis.REGISTRY:
                out.add(node.attr)
    return out


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def _positional(node: ast.Call, idx: int) -> ast.expr | None:
    return node.args[idx] if len(node.args) > idx else None


def _module_consts(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.value is not None:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value
    return out


def _parents(tree: ast.Module) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def _binding(site: ast.AST, name: str,
             par: dict[int, ast.AST]) -> tuple[ast.expr, int | None] | None:
    cur = par.get(id(site))
    while cur is not None:
        if isinstance(cur, (ast.For, ast.AsyncFor)):
            target = cur.target
            if isinstance(target, ast.Name) and target.id == name:
                return (cur.iter, None)
            if isinstance(target, ast.Tuple):
                for i, el in enumerate(target.elts):
                    if isinstance(el, ast.Name) and el.id == name:
                        return (cur.iter, i)
        cur = par.get(id(cur))
    return None


def _rows(node: ast.expr, consts: dict[str, ast.expr]) -> list[ast.expr] | None:
    if isinstance(node, ast.Name):
        node = consts.get(node.id)
    if isinstance(node, (ast.Tuple, ast.List)):
        return list(node.elts)
    return None


def _resolve(node: ast.expr, consts: dict[str, ast.expr],
             par: dict[int, ast.AST], site: ast.AST,
             seen: frozenset[str] = frozenset()) -> list[ast.expr]:
    if not isinstance(node, ast.Name) or node.id in basis.REGISTRY \
            or node.id in seen:
        return [node]
    bound = _binding(site, node.id, par)
    if bound is None:
        return [node]
    it, idx = bound
    rows = _rows(it, consts)
    if rows is None:
        return [node]
    out: list[ast.expr] = []
    for row in rows:
        if idx is None:
            out.append(row)
            continue
        cells = _rows(row, consts)
        if cells is None or len(cells) <= idx:
            return [node]
        out.append(cells[idx])
    flat: list[ast.expr] = []
    for el in out:
        flat.extend(_resolve(el, consts, par, site, seen | {node.id}))
    return flat


def _sites(path: Path) -> list[tuple[str, ast.expr]]:
    tree = ast.parse(path.read_text())
    consts = _module_consts(tree)
    par = _parents(tree)
    raw: list[tuple[str, ast.expr, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        where = f"{path.parent.name}/{path.name}:{node.lineno}"
        if name == "part":
            lib = _positional(node, 1)
            val = _positional(node, VALUE_ARG["part"])
            if (isinstance(lib, ast.Constant) and lib.value in PASSIVE_LIBS
                    and val is not None):
                raw.append((f"{where} part", val, node))
        elif name in ("pullup", "pulldown", "series"):
            val = _positional(node, VALUE_ARG[name])
            if val is not None:
                raw.append((f"{where} {name}", val, node))
        elif name == "decouple":
            for val in node.args[VARIADIC_FROM["decouple"]:]:
                raw.append((f"{where} decouple", val, node))
        elif name == "use_part":
            for kw in node.keywords:
                if kw.arg != "value":
                    continue
                val = kw.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str) \
                        and not _is_si_value(val.value):
                    continue
                raw.append((f"{where} use_part", val, node))
    out: list[tuple[str, ast.expr]] = []
    for where, val, site in raw:
        for leaf in _resolve(val, consts, par, site):
            out.append((where, leaf))
    return out


def check() -> CensusResult:
    res = CensusResult(n_registered=len(basis.REGISTRY))
    used: set[str] = set()
    files = _netlist_files()
    res.n_files = len(files)
    for path in files:
        for where, node in _sites(path):
            res.n_sites += 1
            if isinstance(node, ast.Name):
                if node.id in basis.REGISTRY:
                    used.add(node.id)
                else:
                    res.undeclared.append(f"{where} -> {node.id}")
            elif isinstance(node, ast.Constant):
                res.raw.append(f"{where} -> {node.value!r}")
            else:
                res.raw.append(f"{where} -> {ast.dump(node)[:60]}")
    used |= _referenced_names(_consumer_files())

    for name, entry in sorted(basis.REGISTRY.items()):
        declared = getattr(basis, name, None)
        if declared is None:
            res.broken.append(f"{name}: registered but not a basis constant")
        elif declared != entry.value:
            res.broken.append(
                f"{name}: constant {declared!r} != registered {entry.value!r}")
        if not entry.basis.strip() or not entry.unit.strip():
            res.broken.append(f"{name}: empty basis or unit")
        if entry.klass not in basis._CLASSES:
            res.broken.append(f"{name}: illegal class {entry.klass!r}")
        if name not in used:
            res.unused.append(name)

    res.ok = not (res.raw or res.undeclared or res.unused or res.broken)
    return res
