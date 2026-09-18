from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

from schgen.core.project import PROJECT_ROOT, REPO_ROOT

# Parts come from one shared library; only circuit catalogs are project-scoped.
_CATALOG_PATH = REPO_ROOT / "native" / "catalog.bin"
_CIRCUITS_PATH = PROJECT_ROOT.resolve() / "native" / "circuits.bin"
_CATALOG_OPEN = False
_CIRCUITS_OPEN = False
_CIRCUITS_COMPILED_PATH: Path | None = None

_REQUIRE = os.environ.get("SCHGEN_NATIVE", "")
_TRACE = os.environ.get("SCHGEN_NATIVE_TRACE", "") == "1"
_MOD: ModuleType | None = None
_LOAD_ERROR: str = ""


def _load() -> ModuleType:
    global _MOD, _LOAD_ERROR
    if _REQUIRE == "0":
        raise RuntimeError(
            "SCHGEN_NATIVE=0 is removed — native kernels are required. "
            "Build scripts/build_native.sh")
    if _MOD is not None:
        return _MOD
    if _LOAD_ERROR:
        raise RuntimeError(_LOAD_ERROR)
    try:
        from schgen import _geom as mod
    except ImportError as exc:
        _LOAD_ERROR = (
            f"schgen._geom failed to import: {exc}. Build it with "
            f"scripts/build_native.sh")
        raise RuntimeError(_LOAD_ERROR) from exc
    _MOD = mod
    return _MOD


def loaded() -> bool:
    return _load() is not None


def module() -> ModuleType:
    return _load()


def trace() -> bool:
    return _TRACE


def catalog_path() -> Path:
    return _CATALOG_PATH


def catalog_part(mpn: str) -> dict:
    global _CATALOG_OPEN
    try:
        geom = module()
        if not _CATALOG_PATH.is_file():
            catalog_recompile()
        # Native open is idempotent for the current path. Always select it:
        # direct extension users may have opened another project's catalog.
        if not geom.catalog_open(str(_CATALOG_PATH)):
            raise RuntimeError(
                f"catalog_open returned false for {_CATALOG_PATH}")
        _CATALOG_OPEN = True
        return geom.catalog_lookup(mpn)
    except Exception as exc:
        raise RuntimeError(f"catalog_part({mpn!r}) failed: {exc}") from exc


def circuits_path() -> Path:
    return _CIRCUITS_PATH


def subsystem_json_paths(subsystems_dir: Path | None = None) -> list[tuple[str, Path]]:
    """Native canonical discovery; incomplete authoring migrations are errors."""
    root = Path(subsystems_dir) if subsystems_dir is not None else (
        PROJECT_ROOT / "subsystems")
    return [(name, Path(path)) for name, path in
            module().discover_project_subsystems(str(root))]


def circuit_sheet(name: str) -> dict:
    global _CIRCUITS_OPEN
    try:
        geom = module()
        if (_CIRCUITS_COMPILED_PATH != _CIRCUITS_PATH
                or not _CIRCUITS_PATH.is_file()):
            # Validate/build once per process so removed/renamed JSON cannot
            # survive in an older catalog. Subsequent authoring edits use the
            # explicit recompile API.
            circuit_recompile()
        if not geom.circuit_open(str(_CIRCUITS_PATH)):
            raise RuntimeError(
                f"circuit_open returned false for {_CIRCUITS_PATH}")
        _CIRCUITS_OPEN = True
        return geom.circuit_lookup(name)
    except Exception as exc:
        raise RuntimeError(f"circuit_sheet({name!r}) failed: {exc}") from exc


def circuit_recompile(circuits_dir: Path | None = None) -> bool:
    global _CIRCUITS_OPEN, _CIRCUITS_COMPILED_PATH
    try:
        geom = module()
        source_dir = Path(circuits_dir) if circuits_dir is not None else (
            PROJECT_ROOT / "subsystems")
        if not geom.project_circuit_compile(str(source_dir), str(_CIRCUITS_PATH)):
            raise RuntimeError(
                f"circuit_compile returned false for {_CIRCUITS_PATH}")
        geom.circuit_close()
        _CIRCUITS_OPEN = False
        _CIRCUITS_COMPILED_PATH = _CIRCUITS_PATH
        return True
    except Exception as exc:
        raise RuntimeError(f"circuit_recompile failed: {exc}") from exc


def catalog_recompile(parts_dir: Path | None = None) -> bool:
    global _CATALOG_OPEN
    try:
        geom = module()
        source_dir = Path(parts_dir) if parts_dir is not None else (
            REPO_ROOT / "parts")
        if not geom.catalog_compile(str(source_dir), str(_CATALOG_PATH)):
            raise RuntimeError(
                f"catalog_compile returned false for {_CATALOG_PATH}")
        geom.catalog_close()
        _CATALOG_OPEN = False
        return True
    except Exception as exc:
        raise RuntimeError(f"catalog_recompile failed: {exc}") from exc


def occupancy(board_w: float, board_h: float, clear: float,
              bucket: float, reach_bound: float, step: float,
              frontier_half: float):
    return module().Occupancy(board_w, board_h, clear, bucket, reach_bound,
                              step, frontier_half)
