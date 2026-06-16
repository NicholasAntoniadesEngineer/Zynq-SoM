"""carrier_structure — HARD structure gate for the carrier subsystem packages.

A carrier subsystem is one of TWO kinds, and the required on-disk shape differs:

  ADAPTER — a thin wrapper that binds the project-agnostic ``subsystems/<name>/``
    library via a META dict (``def circuit(): return _lib.circuit(META)``). The
    library ALREADY owns the README / SPICE / __init__ artifacts, so duplicating
    them carrier-side is pure bloat. An adapter is therefore a FLAT pair:

        carrier/subsystems/<name>.py        the bind (circuit() + META)
        carrier/subsystems/test_<name>.py   the LOCAL bind guard

    and MUST NOT be foldered (no ``carrier/subsystems/<name>/`` dir).

  LOCAL — a carrier-specific full netlist with NO generic library to point at
    (the J1/J2/J3 connector sheets, power_som / power_mon, the bring-up sheets,
    board-services HW, the carrier connectors). It stays a self-contained
    FOLDERED package with the full 4-artifact parity the generic library uses:

        carrier/subsystems/<name>/<name>.py        the netlist
        carrier/subsystems/<name>/__init__.py       re-exports circuit()
        carrier/subsystems/<name>/README.md         purpose / interface / parts
        carrier/subsystems/<name>/test_<name>.py    the LOCAL correctness test
        carrier/subsystems/<name>/<name>.cir        the SPICE passive network

Classification is mechanical and authoritative: a name is an ADAPTER iff a
generic library dir ``<repo>/subsystems/<name>/`` exists, else it is LOCAL.

This gate proves every carrier subsystem has the SHAPE its kind requires and its
``circuit()`` is importable + callable (adapters must also expose a ``META``
dict). It is HARD (fails the board) — the carrier package layout cannot silently
rot (an adapter must not re-bloat back into a folder; a local must not lose its
folder). The generic top-level ``subsystems/`` library is policed separately by
:mod:`schgen.verify.subsystem_structure`; this is the carrier-side mirror.

Deterministic, offline (imports each subsystem by file path, builds the model —
no kicad-cli). Run standalone: ``python -m schgen carrier-check``.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER_SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"
LIBRARY_SUBSYSTEMS_DIR = REPO_ROOT / "subsystems"


def is_adapter(name: str, lib_dir: Path = LIBRARY_SUBSYSTEMS_DIR) -> bool:
    """A carrier subsystem is an ADAPTER iff the generic library owns a
    ``subsystems/<name>/`` package it can bind; otherwise it is a carrier LOCAL."""
    return (lib_dir / name).is_dir()


def required_files(name: str, adapter: bool) -> tuple[str, ...]:
    """The on-disk artifacts the subsystem's KIND requires.

    ADAPTER (flat): just the bind module + its local bind guard — the library
    owns the README / SPICE / __init__. LOCAL (foldered): the full 4-artifact
    parity package (the carrier owns everything, no library to defer to)."""
    if adapter:
        return (f"{name}.py", f"test_{name}.py")
    return (f"{name}.py", "__init__.py", "README.md", f"test_{name}.py",
            f"{name}.cir")


@dataclass
class PackageReport:
    name: str
    path: Path
    adapter: bool = False
    missing: list[str] = field(default_factory=list)
    has_circuit: bool = False
    has_meta: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.missing or self.errors or not self.has_circuit:
            return False
        if self.adapter and not self.has_meta:
            return False
        return True

    @property
    def kind(self) -> str:
        return "adapter" if self.adapter else "local"


@dataclass
class Result:
    packages: list[PackageReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.packages) and all(p.ok for p in self.packages)

    @property
    def n_ok(self) -> int:
        return sum(1 for p in self.packages if p.ok)

    @property
    def n_adapters(self) -> int:
        return sum(1 for p in self.packages if p.adapter)

    @property
    def n_locals(self) -> int:
        return sum(1 for p in self.packages if not p.adapter)

    def summary(self) -> str:
        lines = ["schgen carrier-structure gate (HARD)", "=" * 60, ""]
        lines.append("contract: each carrier subsystem matches the SHAPE its "
                     "kind requires —")
        lines.append("  ADAPTER (has a generic subsystems/<name>/ library): FLAT "
                     "<name>.py + test_<name>.py")
        lines.append("           (NOT foldered) with a callable circuit() + a "
                     "META dict.")
        lines.append("  LOCAL  (no generic library): foldered <name>/ with "
                     "<name>.py + __init__.py +")
        lines.append("           README.md + test_<name>.py + <name>.cir and a "
                     "callable circuit().")
        lines.append("")
        for p in self.packages:
            if not p.ok:
                lines.append(f"{p.name} [{p.kind}]: INCOMPLETE")
                if p.missing:
                    lines.append(f"  missing: {', '.join(p.missing)}")
                if not p.has_circuit:
                    lines.append("  no callable circuit()")
                if p.adapter and p.has_circuit and not p.has_meta:
                    lines.append("  adapter missing a META dict")
                for e in p.errors:
                    lines.append(f"  error: {e}")
        lines.append(f"CARRIER STRUCTURE: {self.n_ok}/{len(self.packages)} "
                     f"subsystem(s) complete "
                     f"({self.n_adapters} flat adapter(s) + "
                     f"{self.n_locals} foldered local(s)) "
                     f"({'PASS' if self.ok else 'FAIL'})")
        return "\n".join(lines)


def _subsystem_names(base: Path) -> list[str]:
    """Every carrier subsystem NAME — the UNION of flat ``<name>.py`` modules and
    foldered ``<name>/`` packages (excluding ``__init__`` / dunder / ``test_*``)."""
    names: set[str] = set()
    if not base.is_dir():
        return []
    for child in sorted(base.iterdir()):
        if child.name.startswith((".", "_")):
            continue
        if child.is_dir():
            names.add(child.name)
        elif child.suffix == ".py" and not child.name.startswith("test_") \
                and child.stem != "__init__":
            names.add(child.stem)
    return sorted(names)


def check_package(name: str, base: Path = CARRIER_SUBSYSTEMS_DIR,
                  lib_dir: Path = LIBRARY_SUBSYSTEMS_DIR) -> PackageReport:
    adapter = is_adapter(name, lib_dir)
    rep = PackageReport(name=name, path=(base / name), adapter=adapter)

    if adapter:
        # ADAPTER: flat <name>.py + flat test_<name>.py, and NO leftover folder.
        netlist = base / f"{name}.py"
        rep.path = netlist
        rep.missing = [f for f in required_files(name, adapter=True)
                       if not (base / f).exists()]
        if (base / name).is_dir():
            rep.missing.append(f"{name}/ (adapter must be FLAT, not foldered)")
    else:
        # LOCAL: foldered <name>/ with the full 4-artifact parity package.
        pkg = base / name
        rep.path = pkg
        netlist = pkg / f"{name}.py"
        if not pkg.is_dir():
            rep.missing.append(f"{name}/ (local must be a foldered package)")
        rep.missing += [f for f in required_files(name, adapter=False)
                        if not (pkg / f).exists()]

    if not netlist.exists():
        return rep
    try:
        spec = importlib.util.spec_from_file_location(
            f"carrier_struct_{name}", netlist)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "circuit", None)
        rep.has_circuit = callable(fn)
        rep.has_meta = isinstance(getattr(mod, "META", None), dict)
        if rep.has_circuit:
            fn()  # must build without raising
    except Exception as exc:  # noqa: BLE001 — surface as a report line
        rep.errors.append(f"{type(exc).__name__}: {exc}")
    return rep


def check(base: Path = CARRIER_SUBSYSTEMS_DIR,
          lib_dir: Path = LIBRARY_SUBSYSTEMS_DIR) -> Result:
    res = Result()
    for name in _subsystem_names(base):
        res.packages.append(check_package(name, base, lib_dir))
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
