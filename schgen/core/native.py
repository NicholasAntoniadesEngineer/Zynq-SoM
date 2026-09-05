from __future__ import annotations

import os
from types import ModuleType

_REQUIRE = os.environ.get("SCHGEN_NATIVE", "")
_TRACE = os.environ.get("SCHGEN_NATIVE_TRACE", "") == "1"
_MOD: ModuleType | None = None
_LOAD_ERROR: str = ""


def _load() -> ModuleType | None:
    global _MOD, _LOAD_ERROR
    if _REQUIRE == "0":
        return None
    if _MOD is not None or _LOAD_ERROR:
        return _MOD
    try:
        from schgen import _geom as mod
    except ImportError as exc:
        _LOAD_ERROR = str(exc)
        raise RuntimeError(
            f"schgen._geom failed to import: {exc}. Build it with "
            f"scripts/build_native.sh, or set SCHGEN_NATIVE=0 to force "
            f"the Python kernels") from exc
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


def occupancy(board_w: float, board_h: float, clear: float,
              bucket: float, reach_bound: float, step: float,
              frontier_half: float):
    return module().Occupancy(board_w, board_h, clear, bucket, reach_bound,
                              step, frontier_half)
