from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.artifacts import is_sync_duplicate
from schgen.core.model import Circuit
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER_SUBSYSTEMS_DIR = PROJECT_ROOT / "subsystems"
LIBRARY_SUBSYSTEMS_DIR = REPO_ROOT / "subsystems"


def is_adapter(name: str, lib_dir: Path = LIBRARY_SUBSYSTEMS_DIR) -> bool:
    return (lib_dir / name).is_dir()


def required_files(name: str, adapter: bool) -> tuple[str, ...]:
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
        lines.append("           An IR-only <name>/circuit.json companion must "
                     "match circuit() exactly.")
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
        netlist = base / f"{name}.py"
        rep.path = netlist
        rep.missing = [f for f in required_files(name, adapter=True)
                       if not (base / f).exists()]
        companion = base / name
        if companion.is_dir():
            entries = [p.name for p in companion.iterdir()
                       if not is_sync_duplicate(p)]
            if entries != ["circuit.json"]:
                rep.missing.append(
                    f"{name}/ (adapter companion must contain only circuit.json)")
    else:
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
            circuit = fn()
            if adapter and (base / name).is_dir():
                payload = json.loads((base / name / "circuit.json").read_text())
                if Circuit.from_ir(payload).to_ir() != circuit.to_ir():
                    rep.errors.append("circuit.json differs from the adapter netlist")
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
