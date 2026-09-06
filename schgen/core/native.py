from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "native" / "catalog.bin"
_CATALOG_OPEN = False

_REQUIRE = os.environ.get("SCHGEN_NATIVE", "")
_TRACE = os.environ.get("SCHGEN_NATIVE_TRACE", "") == "1"
_MOD: ModuleType | None = None
_LOAD_ERROR: str = ""


def _load() -> ModuleType | None:
    global _MOD, _LOAD_ERROR
    if _REQUIRE == "0":
        raise RuntimeError(
            "SCHGEN_NATIVE=0 is removed — the engine is C++ only. "
            "Build scripts/build_native.sh")
    if _MOD is not None or _LOAD_ERROR:
        return _MOD
    try:
        from schgen import _geom as mod
    except ImportError as exc:
        _LOAD_ERROR = str(exc)
        raise RuntimeError(
            f"schgen._geom failed to import: {exc}. Build it with "
            f"scripts/build_native.sh") from exc
    _MOD = mod
    return _MOD


def loaded() -> bool:
    return _load() is not None


def module() -> ModuleType:
    mod = _load()
    if mod is None:
        raise RuntimeError(
            "schgen._geom is not loaded — build scripts/build_native.sh "
            "or unset SCHGEN_NATIVE=1")
    return mod


def trace() -> bool:
    return _TRACE


def catalog_path() -> Path:
    return _CATALOG_PATH


def catalog_part(mpn: str) -> dict:
    global _CATALOG_OPEN
    try:
        geom = module()
        if not _CATALOG_OPEN:
            if not _CATALOG_PATH.is_file():
                raise RuntimeError(
                    f"native/catalog.bin is missing — build it with "
                    f"scripts/build_native.sh")
            if not geom.catalog_open(str(_CATALOG_PATH)):
                raise RuntimeError(
                    f"catalog_open returned false for {_CATALOG_PATH}")
            _CATALOG_OPEN = True
        return geom.catalog_lookup(mpn)
    except Exception as exc:
        raise RuntimeError(f"catalog_part({mpn!r}) failed: {exc}") from exc


def catalog_recompile(parts_dir: Path | None = None) -> bool:
    global _CATALOG_OPEN
    try:
        geom = module()
        source_dir = Path(parts_dir) if parts_dir is not None else (
            Path(__file__).resolve().parents[2] / "parts")
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
