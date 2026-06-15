"""subsystem_structure — the reusable-subsystem PACKAGE-STRUCTURE gate.

The re-architecture turns each portable subsystem into a self-contained,
project-agnostic library package under the top-level ``subsystems/<name>/``.
This gate proves each such package is COMPLETE and well-formed:

  REQUIRED FILES   every ``subsystems/<name>/`` has exactly the four artifacts
                   the contract mandates: ``<name>.py`` (the netlist with
                   abstract ports), ``README.md`` (the interface table + design
                   notes), ``test_<name>.py`` (the local correctness test), and
                   ``<name>.cir`` (the SPICE subckt).

  ABSTRACT IFACE   ``<name>.py`` exposes a top-level ``circuit(meta=None)`` that
                   accepts the standard ``meta`` adapter dict (see
                   :mod:`schgen.core.subsystem`) AND a declared abstract
                   ``INTERFACE`` (the externally-visible port + rail names a
                   project binds). The circuit built standalone must contain
                   exactly those nets as its externals — so the declared
                   interface cannot drift from the netlist.

REPORT-FIRST (LAW: prove exemplars before the gate hard-fails). The migration is
incremental: most subsystems still live only as carrier adapters. So this gate
REPORTS the state of ``subsystems/`` and does NOT fail the board yet. Promote it
to hard-fail (``run(..., strict=True)`` / flip the board hook) once every
intended subsystem has been migrated into a package. Deterministic; no
timestamps; offline (imports the package, reads the model — no kicad-cli).

Run standalone: ``python -m schgen subsystem-check`` (see ``cmd``).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import NetClass

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSYSTEMS_DIR = REPO_ROOT / "subsystems"


def required_files(name: str) -> tuple[str, ...]:
    return (f"{name}.py", "README.md", f"test_{name}.py", f"{name}.cir")


@dataclass
class PackageReport:
    name: str
    path: Path
    missing: list[str] = field(default_factory=list)      # required files absent
    has_circuit: bool = False
    accepts_meta: bool = False
    declared_interface: tuple[str, ...] = ()
    interface_drift: list[str] = field(default_factory=list)  # declared vs built
    errors: list[str] = field(default_factory=list)       # import / build errors

    @property
    def ok(self) -> bool:
        return not (self.missing or self.interface_drift or self.errors) \
            and self.has_circuit and self.accepts_meta \
            and bool(self.declared_interface)


@dataclass
class Result:
    packages: list[PackageReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.packages)

    @property
    def n_ok(self) -> int:
        return sum(1 for p in self.packages if p.ok)

    def summary(self) -> str:
        lines = ["schgen subsystem-structure gate (REPORT-FIRST)", "=" * 60, ""]
        lines.append("contract: each subsystems/<name>/ is a self-contained, "
                     "project-agnostic package with")
        lines.append("  <name>.py (abstract-port netlist + circuit(meta=)) + "
                     "README.md + test_<name>.py + <name>.cir,")
        lines.append("  and a declared abstract INTERFACE that matches the "
                     "netlist's externals.")
        lines.append("")
        if not self.packages:
            lines.append("(no subsystems/ packages found)")
        for p in self.packages:
            lines.append(f"{p.name}: {'OK' if p.ok else 'INCOMPLETE'}")
            if p.missing:
                lines.append(f"  missing files: {', '.join(p.missing)}")
            if not p.has_circuit:
                lines.append("  no top-level circuit()")
            elif not p.accepts_meta:
                lines.append("  circuit() does not accept a meta= argument")
            if not p.declared_interface and p.has_circuit:
                lines.append("  no declared INTERFACE (abstract port/rail names)")
            for d in p.interface_drift:
                lines.append(f"  interface drift: {d}")
            for e in p.errors:
                lines.append(f"  error: {e}")
            if p.declared_interface:
                lines.append(f"  interface ({len(p.declared_interface)}): "
                             + ", ".join(p.declared_interface))
        lines.append("")
        lines.append(f"SUBSYSTEM STRUCTURE: {self.n_ok}/{len(self.packages)} "
                     f"package(s) complete "
                     f"({'PASS' if self.ok else 'REPORT'})")
        return "\n".join(lines)


def _package_names() -> list[str]:
    if not SUBSYSTEMS_DIR.is_dir():
        return []
    out = []
    for child in sorted(SUBSYSTEMS_DIR.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists() \
                and not child.name.startswith("_"):
            out.append(child.name)
    return out


def _import_circuit(name: str):
    """Import subsystems.<name>.<name> and return its module (None on failure)."""
    return importlib.import_module(f"subsystems.{name}.{name}")


def check_package(name: str) -> PackageReport:
    import inspect

    pkg_dir = SUBSYSTEMS_DIR / name
    rep = PackageReport(name=name, path=pkg_dir)
    rep.missing = [f for f in required_files(name)
                   if not (pkg_dir / f).exists()]

    # only attempt the import / interface check if the netlist file is present
    if f"{name}.py" in rep.missing:
        return rep
    try:
        mod = _import_circuit(name)
    except Exception as exc:  # noqa: BLE001 — surface as a report line
        rep.errors.append(f"import failed: {type(exc).__name__}: {exc}")
        return rep

    fn = getattr(mod, "circuit", None)
    rep.has_circuit = callable(fn)
    if not rep.has_circuit:
        return rep
    try:
        rep.accepts_meta = "meta" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        rep.accepts_meta = False

    iface = getattr(mod, "INTERFACE", None)
    if isinstance(iface, (list, tuple)) and iface:
        rep.declared_interface = tuple(iface)

    # build standalone and compare the declared interface to the real externals
    try:
        c = fn()
    except Exception as exc:  # noqa: BLE001
        rep.errors.append(f"circuit() build failed: {type(exc).__name__}: {exc}")
        return rep
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    if rep.declared_interface:
        declared = set(rep.declared_interface)
        for extra in sorted(externals - declared):
            rep.interface_drift.append(
                f"net {extra!r} is an external but not in the declared "
                f"INTERFACE")
        for missing in sorted(declared - externals):
            rep.interface_drift.append(
                f"INTERFACE name {missing!r} is not an external net of the "
                f"built circuit")
    return rep


def check() -> Result:
    res = Result()
    for name in _package_names():
        res.packages.append(check_package(name))
    return res


def run(reports_dir: Path | None = None, strict: bool = False) -> Result:
    """Gate entry point. REPORT-FIRST: returns a Result whose ``.ok`` reflects
    completeness, but the board hook treats it as report-only until ``strict``.
    Writes ``reports_dir/subsystem_structure.txt`` when given."""
    res = check()
    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "subsystem_structure.txt").write_text(
            res.summary() + "\n")
    return res


def cmd(args) -> int:
    repo = Path(__file__).resolve().parents[2]
    res = run(repo / "carrier" / "reports")
    print(res.summary())
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'subsystem_structure.txt'}")
    # REPORT-FIRST: exit 0 even when incomplete, UNLESS --strict is given.
    if getattr(args, "strict", False):
        return 0 if res.ok else 1
    return 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(prog="schgen subsystem-check")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if any package is incomplete "
                        "(default: report-only)")
    raise SystemExit(cmd(p.parse_args()))
