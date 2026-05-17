"""KiCad symbol-library path discovery via environment variables.

Resolves the location of ``.kicad_sym`` library files by reading the
standard KiCad symbol-directory environment variables. The carrier
generator embeds its own symbols in ``scripts.carrier.core.symbols``;
this module is used only when a sheet generator opts in to reading a
KiCad stock library symbol (e.g. ``Device:R``) at generation time.

Per the project compliance rule "Relative paths only: no absolute paths",
no install location is hardcoded here. If none of the supported env vars
are set, ``find_symbol_library`` raises a clear FileNotFoundError telling
the caller which variable to populate.
"""

from __future__ import annotations

import os
from pathlib import Path


SYMBOL_LIB_EXTENSION: str = ".kicad_sym"

KICAD_SYMBOL_ENV_VARS: tuple[str, ...] = (
    "KICAD_SYMBOL_DIR",
    "KICAD9_SYMBOL_DIR",
    "KICAD8_SYMBOL_DIR",
    "KICAD7_SYMBOL_DIR",
)


def discover_kicad_symbol_paths() -> list[Path]:
    """Return the ordered list of directories from the KiCad env vars.

    Each variable may contain one or more directories separated by the
    platform path separator. Directories that do not exist on disk are
    dropped; duplicates are removed while preserving first occurrence.
    """

    raw_paths: list[Path] = []
    for env_var_name in KICAD_SYMBOL_ENV_VARS:
        env_value = os.environ.get(env_var_name)
        if not env_value:
            continue
        for raw_segment in env_value.split(os.pathsep):
            stripped = raw_segment.strip()
            if stripped:
                raw_paths.append(Path(stripped))

    seen: set[Path] = set()
    resolved_paths: list[Path] = []
    for path in raw_paths:
        candidate = path.expanduser()
        if candidate in seen:
            continue
        if not candidate.is_dir():
            continue
        seen.add(candidate)
        resolved_paths.append(candidate)
    return resolved_paths


def find_symbol_library(library_name: str) -> Path:
    """Locate ``<library_name>.kicad_sym`` on disk via env-var directories.

    ``library_name`` is the KiCad library nickname (e.g. ``"Device"``).
    Returns the absolute resolved Path. Raises FileNotFoundError if no
    discoverable directory contains the requested library file.
    """

    if not library_name:
        raise ValueError("find_symbol_library: library_name must be non-empty")
    target_file_name = f"{library_name}{SYMBOL_LIB_EXTENSION}"
    search_directories = discover_kicad_symbol_paths()

    for directory in search_directories:
        candidate = directory / target_file_name
        if candidate.is_file():
            return candidate.resolve()

    if not search_directories:
        raise FileNotFoundError(
            f"find_symbol_library: cannot locate {target_file_name!r}; "
            f"none of {KICAD_SYMBOL_ENV_VARS} are set. "
            f"Export one of these env vars to point at a directory "
            f"containing KiCad's symbol libraries."
        )
    raise FileNotFoundError(
        f"find_symbol_library: could not locate {target_file_name!r} in any of "
        f"{[str(directory) for directory in search_directories]}"
    )


def find_symbol(lib_id: str) -> Path:
    """Locate the file containing the symbol identified by ``lib_id``.

    ``lib_id`` is in the form ``"<library>:<symbol>"`` (e.g.
    ``"Device:R"``). Returns the path to the ``.kicad_sym`` file. The
    caller can then parse it to extract the named symbol body.
    """

    if ":" not in lib_id:
        raise ValueError(
            f"find_symbol: lib_id must be in 'library:symbol' form, got {lib_id!r}"
        )
    library_name, _ = lib_id.split(":", 1)
    return find_symbol_library(library_name)


__all__ = [
    "KICAD_SYMBOL_ENV_VARS",
    "SYMBOL_LIB_EXTENSION",
    "discover_kicad_symbol_paths",
    "find_symbol",
    "find_symbol_library",
]
