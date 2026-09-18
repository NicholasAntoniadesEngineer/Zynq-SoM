from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schgen.core import native as _nat
from schgen.core import sexpr

GRID = 1.27

# Keep this exact caller-configurable order. The native adapter receives these
# paths explicitly rather than adding its own platform defaults.
_SEARCH_PATHS = [
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
    Path(__file__).resolve().parents[1] / "lib",
    Path(__file__).resolve().parents[2] / "parts",
]


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    etype: str
    x: float
    y: float
    rotation: int
    length: float
    hidden: bool = False


@dataclass
class SymbolDef:
    lib_id: str
    raw: list
    pins: list[Pin]
    body: tuple[float, float, float, float]
    pin_names_hidden: bool
    pin_numbers_hidden: bool


class SymbolError(ValueError):
    pass


def _on_grid(v: float) -> bool:
    return _nat.module().symbols_on_grid(v)


def _symbol_call(function, *args):
    try:
        return function(*args)
    except _nat.module().SymbolError as exc:
        raise SymbolError(str(exc)) from exc


class Library:
    """Dataclass transport over the required native symbol library."""

    def __init__(self, extra_paths: list[Path] | None = None) -> None:
        self.paths = list(extra_paths or []) + _SEARCH_PATHS
        self._native = _nat.module().SymbolLibrary(
            [str(path) for path in self.paths], Pin, SymbolDef, sexpr._from_tagged)

    def get(self, lib_id: str) -> SymbolDef:
        return _symbol_call(self._native.get, lib_id)

    def pin_numbers(self, lib_id: str) -> set[str]:
        return _symbol_call(self._native.pin_numbers, lib_id)


def _parse_symbol(lib_id: str, block: list) -> SymbolDef:
    return _symbol_call(_nat.module().symbols_parse, lib_id, block,
                        Pin, SymbolDef, sexpr._from_tagged)


def pin_page_position(pin: Pin, anchor_x: float, anchor_y: float,
                      rotation: int) -> tuple[float, float]:
    """Page position (+Y down), using the native full-Pin transform."""
    return tuple(_nat.module().symbols_pin_page_position(
        pin, anchor_x, anchor_y, rotation))
