"""carrier_structure — HARD structure gate for the carrier subsystem packages.

Every carrier subsystem (both the thin adapters that consume the generic
``subsystems/<name>/`` library AND the carrier-LOCAL full-netlist sheets) lives
as a self-contained package ``carrier/subsystems/<name>/`` with the same
4-artifact parity the generic library uses:

  <name>.py        the netlist (adapter `circuit()=_lib.circuit(META)`, or a
                   carrier-local full circuit())
  README.md        purpose / bind table or interface / parts / notes
  test_<name>.py   the LOCAL correctness test (bind guard for adapters, full
                   model/design-rule slice for locals)
  <name>.cir       the SPICE subckt (thin pointer for adapters; passive network
                   for locals)
  __init__.py      re-exports circuit (+ META for adapters)

This gate proves every ``carrier/subsystems/<name>/`` is COMPLETE + its
``circuit()`` is importable and callable. It is HARD (fails the board) — the
carrier package layout cannot silently rot. (The generic top-level
``subsystems/`` library is policed separately by
:mod:`schgen.verify.subsystem_structure`; this is the carrier-side mirror.)

Deterministic, offline (imports each package by file path, builds the model — no
kicad-cli). Run standalone: ``python -m schgen carrier-check``.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER_SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"


def required_files(name: str) -> tuple[str, ...]:
    return (f"{name}.py", "__init__.py", "README.md", f"test_{name}.py",
            f"{name}.cir")


@dataclass
class PackageReport:
    name: str
    path: Path
    missing: list[str] = field(default_factory=list)
    has_circuit: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.errors) and self.has_circuit


@dataclass
class Result:
    packages: list[PackageReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.packages) and all(p.ok for p in self.packages)

    @property
    def n_ok(self) -> int:
        return sum(1 for p in self.packages if p.ok)

    def summary(self) -> str:
        lines = ["schgen carrier-structure gate (HARD)", "=" * 60, ""]
        lines.append("contract: every carrier/subsystems/<name>/ is a complete "
                     "package —")
        lines.append("  <name>.py + __init__.py + README.md + test_<name>.py + "
                     "<name>.cir, with a callable circuit().")
        lines.append("")
        for p in self.packages:
            if not p.ok:
                lines.append(f"{p.name}: INCOMPLETE")
                if p.missing:
                    lines.append(f"  missing: {', '.join(p.missing)}")
                if not p.has_circuit:
                    lines.append("  no callable circuit()")
                for e in p.errors:
                    lines.append(f"  error: {e}")
        lines.append(f"CARRIER STRUCTURE: {self.n_ok}/{len(self.packages)} "
                     f"package(s) complete "
                     f"({'PASS' if self.ok else 'FAIL'})")
        return "\n".join(lines)


def _package_names(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    out = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "_")) \
                and (child / "__init__.py").exists():
            out.append(child.name)
    return out


def check_package(name: str, base: Path = CARRIER_SUBSYSTEMS_DIR) -> PackageReport:
    pkg = base / name
    rep = PackageReport(name=name, path=pkg)
    rep.missing = [f for f in required_files(name) if not (pkg / f).exists()]
    netlist = pkg / f"{name}.py"
    if not netlist.exists():
        return rep
    try:
        spec = importlib.util.spec_from_file_location(
            f"carrier_struct_{name}", netlist)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "circuit", None)
        rep.has_circuit = callable(fn)
        if rep.has_circuit:
            fn()  # must build without raising
    except Exception as exc:  # noqa: BLE001 — surface as a report line
        rep.errors.append(f"{type(exc).__name__}: {exc}")
    return rep


def check(base: Path = CARRIER_SUBSYSTEMS_DIR) -> Result:
    res = Result()
    for name in _package_names(base):
        res.packages.append(check_package(name, base))
    return res


def run(reports_dir: Path | None = None) -> Result:
    res = check()
    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "carrier_structure.txt").write_text(res.summary() + "\n")
    return res


def cmd(args) -> int:
    repo = Path(__file__).resolve().parents[2]
    res = run(repo / "carrier" / "reports")
    print(res.summary())
    return 0 if res.ok else 1


if __name__ == "__main__":
    import argparse
    raise SystemExit(cmd(argparse.ArgumentParser().parse_args()))
