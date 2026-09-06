from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from schgen.core import native as _nat
from schgen.core import sexpr

GRID = 1.27

# shared across every Library: callers must treat a cached parse as read-only
_FILE_PARSE_CACHE: dict[tuple[str, int, int], list] = {}

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
    return abs(v / GRID - round(v / GRID)) < 1e-4


def _parse_lib_file(f: Path) -> list:
    st = f.stat()
    key = (str(f.resolve()), st.st_mtime_ns, st.st_size)
    cached = _FILE_PARSE_CACHE.get(key)
    if cached is None:
        cached = sexpr.loads(f.read_text())
        _FILE_PARSE_CACHE[key] = cached
    return cached


class Library:
    def __init__(self, extra_paths: list[Path] | None = None) -> None:
        self.paths = list(extra_paths or []) + _SEARCH_PATHS
        self._files: dict[str, list] = {}
        self._defs: dict[str, SymbolDef] = {}

    def _lib_file(self, libname: str) -> list:
        if libname not in self._files:
            for base in self.paths:
                for f in (base / f"{libname}.kicad_sym",
                          base / libname / f"{libname}.kicad_sym"):
                    if f.exists():
                        self._files[libname] = _parse_lib_file(f)
                        break
                if libname in self._files:
                    break
            else:
                raise SymbolError(f"library {libname!r} not found in {self.paths}")
        return self._files[libname]

    def get(self, lib_id: str) -> SymbolDef:
        if lib_id in self._defs:
            return self._defs[lib_id]
        libname, _, symname = lib_id.partition(":")
        root = self._lib_file(libname)
        block = None
        for s in sexpr.find_all(root, "symbol"):
            if len(s) > 1 and s[1] == symname:
                block = s
                break
        if block is None and libname == "schgen" and symname.startswith("+"):
            block = _synth_power_symbol(root, symname)
        if block is None:
            raise SymbolError(f"symbol {symname!r} not in {libname}")
        d = _parse_symbol(lib_id, block)
        for p in d.pins:
            if not (_on_grid(p.x) and _on_grid(p.y)):
                raise SymbolError(
                    f"{lib_id} pin {p.number} at ({p.x},{p.y}) is OFF-GRID — "
                    f"fix the symbol; schgen never lands wires off-grid")
        self._defs[lib_id] = d
        return d

    def pin_numbers(self, lib_id: str) -> set[str]:
        return {p.number for p in self.get(lib_id).pins}


def _clone_replace(node, old: str, new: str):
    if isinstance(node, list):
        return [_clone_replace(x, old, new) for x in node]
    if isinstance(node, sexpr.Sym):
        return node
    if isinstance(node, str):
        return node.replace(old, new)
    return node


def _synth_power_symbol(root: list, name: str) -> list:
    for s in sexpr.find_all(root, "symbol"):
        if len(s) > 1 and s[1] == "+5V_USB":
            return _clone_replace(s, "+5V_USB", name)
    raise SymbolError("rail template '+5V_USB' missing from schgen lib")


def _parse_symbol(lib_id: str, block: list) -> SymbolDef:
    pins: list[Pin] = []
    xs: list[float] = []
    ys: list[float] = []

    pn = sexpr.find(block, "pin_names")
    pnames_hidden = bool(pn and (sexpr.find(pn, "hide") or sexpr.Sym("hide") in pn))
    pnum = sexpr.find(block, "pin_numbers")
    pnums_hidden = bool(
        pnum and (sexpr.find(pnum, "hide") or sexpr.Sym("hide") in pnum))

    def walk(node: list) -> None:
        nonlocal xs, ys
        for sub in sexpr.find_all(node, "symbol"):
            walk(sub)
        for p in sexpr.find_all(node, "pin"):
            at = sexpr.find(p, "at") or [None, 0, 0, 0]
            ln = sexpr.find(p, "length")
            nm = sexpr.find(p, "name")
            num = sexpr.find(p, "number")
            hd = sexpr.find(p, "hide")
            pins.append(Pin(
                number=str(num[1]) if num and len(num) > 1 else "",
                name=str(nm[1]) if nm and len(nm) > 1 else "",
                etype=str(p[1]) if len(p) > 1 else "passive",
                x=float(at[1]), y=float(at[2]),
                rotation=int(float(at[3])) % 360 if len(at) > 3 else 0,
                length=float(ln[1]) if ln and len(ln) > 1 else 2.54,
                hidden=bool(hd and len(hd) > 1 and str(hd[1]) == "yes")
                       or sexpr.Sym("hide") in p,
            ))
        for r in sexpr.find_all(node, "rectangle"):
            for tag in ("start", "end"):
                pt = sexpr.find(r, tag)
                if pt:
                    xs.append(float(pt[1]))
                    ys.append(float(pt[2]))
        for poly in sexpr.find_all(node, "polyline"):
            ptsl = sexpr.find(poly, "pts")
            for xy in sexpr.find_all(ptsl or [], "xy"):
                xs.append(float(xy[1]))
                ys.append(float(xy[2]))
        for c in sexpr.find_all(node, "circle"):
            ctr = sexpr.find(c, "center")
            rad = sexpr.find(c, "radius")
            if ctr and rad:
                xs += [float(ctr[1]) - float(rad[1]), float(ctr[1]) + float(rad[1])]
                ys += [float(ctr[2]) - float(rad[1]), float(ctr[2]) + float(rad[1])]
        for a in sexpr.find_all(node, "arc"):
            for tag in ("start", "mid", "end"):
                pt = sexpr.find(a, tag)
                if pt:
                    xs.append(float(pt[1]))
                    ys.append(float(pt[2]))

    walk(block)
    if not xs:
        xs = [p.x for p in pins] or [0.0]
        ys = [p.y for p in pins] or [0.0]
    body = (min(xs), min(ys), max(xs), max(ys))
    return SymbolDef(lib_id=lib_id, raw=block, pins=pins, body=body,
                     pin_names_hidden=pnames_hidden, pin_numbers_hidden=pnums_hidden)


def pin_page_position_py(pin: Pin, anchor_x: float, anchor_y: float,
                         rotation: int) -> tuple[float, float]:
    """Page position (+Y down) of a pin: the one symbol-to-page transform."""
    r = math.radians(rotation % 360)
    c, s = round(math.cos(r)), round(math.sin(r))
    px = anchor_x + (pin.x * c - pin.y * s)
    py = anchor_y + (-pin.x * s - pin.y * c)
    return (round(px, 4), round(py, 4))


def pin_page_position(pin: Pin, anchor_x: float, anchor_y: float,
                      rotation: int) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native pin_page_position required")
    got = tuple(_nat.module().pin_page_position(
        pin.x, pin.y, anchor_x, anchor_y, rotation))
    if _nat.trace():
        ref = pin_page_position_py(pin, anchor_x, anchor_y, rotation)
        if got != ref:
            raise AssertionError(
                "native pin_page_position DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got
