from __future__ import annotations

from pathlib import Path

from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.generate import constraints as cst

from .constants import (
    _FOOTPRINT_ALIASES,
    _PAD_RE,
    _THRU_PAD_RE,
    CARRIER,
    PARTS_DIR,
    POWER_CLASS,
    _kicad_fp_root,
)
from .turn import pad_half_extent

BBOX_DECIMALS = 3


def pad_half_size(at: list, size: list) -> tuple[float, float]:
    deg = (float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float))
           else 0.0)
    return pad_half_extent(float(size[1]), float(size[2]), deg)


def resolve_mod(footprint: str) -> Path | None:
    fp = _FOOTPRINT_ALIASES.get(footprint, footprint)
    lib, _, name = fp.partition(":")
    local = PARTS_DIR / lib / f"{name}.kicad_mod"
    if local.exists():
        return local
    root = _kicad_fp_root()
    if root is not None:
        std = root / f"{lib}.pretty" / f"{name}.kicad_mod"
        if std.exists():
            return std
    return None


def pad_names(mod_path: Path) -> list[str]:
    return _PAD_RE.findall(mod_path.read_text())


_thru_cache: dict[str, bool] = {}


def has_thru_pads(mod_path: Path) -> bool:
    key = str(mod_path)
    if key not in _thru_cache:
        _thru_cache[key] = bool(_THRU_PAD_RE.search(mod_path.read_text()))
    return _thru_cache[key]


def board_netlist() -> dict[str, list]:
    from schgen.verify.netlist_gate import extract_netlist
    root = CARRIER / "Zynq_Carrier.kicad_sch"
    if not root.exists():
        raise FileNotFoundError(
            f"{root} not found — run `schgen board` first (the PCB seeds its "
            f"net-accurate connectivity from the emitted root schematic).")
    return extract_netlist(root)


def board_parts() -> dict[str, tuple[str, str, str, str]]:
    import json as _json

    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.generate.board import _renamed_ref
    _idx_path = CARRIER / "sheet_index.json"
    sheet_index = (_json.loads(_idx_path.read_text())
                   if _idx_path.exists() else {})
    out: dict[str, tuple[str, str, str, str]] = {}
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    for i, sc in enumerate(sheets, start=1):
        idx = sheet_index.get(sc.name, i)
        for ref, part in sc.circuit.parts.items():
            bref = _renamed_ref(ref, idx, sheet=sc.name)
            out[bref] = (sc.name, part.footprint, part.value, part.lib_id)
    return out


def _net_classes(sheets) -> tuple[dict[str, cst.DiffGeometry | None],
                                  dict[str, str]]:
    from schgen.core.model import NetClass
    classes: dict[str, cst.DiffGeometry | None] = {}
    netclass_of: dict[str, str] = {}
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class == NetClass.PORT:
                pt = c.port_type_of(net.name)
                if pt.kind == "single":
                    continue
                ncls = cst._net_class(pt.kind, pt.impedance, pt.level_v)
                geo = cst.GEOMETRY.get(pt.impedance) if pt.impedance else None
                classes.setdefault(ncls, geo)
                netclass_of[net.name] = ncls
            elif net.net_class == NetClass.POWER:
                classes.setdefault(POWER_CLASS, None)
                netclass_of[net.name] = POWER_CLASS
    return classes, netclass_of


_bbox_cache: dict[str, tuple[float, float, float, float]] = {}


def _footprint_bbox_from_doc_py(doc: list) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def add(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    def walk(node: list) -> None:
        for sub in node:
            if not isinstance(sub, list) or not sub:
                continue
            head = sub[0]
            if head in (Sym("fp_line"), Sym("fp_rect"), Sym("fp_poly"),
                        Sym("fp_circle"), Sym("fp_arc")):
                lyr = sexpr.find(sub, "layer")
                if lyr and len(lyr) > 1 and "CrtYd" in str(lyr[1]):
                    if head == Sym("fp_circle"):
                        ctr = sexpr.find(sub, "center")
                        end = sexpr.find(sub, "end")
                        if (ctr and len(ctr) >= 3 and end and len(end) >= 3):
                            cxf, cyf = float(ctr[1]), float(ctr[2])
                            r = ((float(end[1]) - cxf) ** 2
                                 + (float(end[2]) - cyf) ** 2) ** 0.5
                            add(cxf - r, cyf - r)
                            add(cxf + r, cyf + r)
                    for tag in ("start", "end", "mid", "center"):
                        p = sexpr.find(sub, tag)
                        if p and len(p) >= 3:
                            add(float(p[1]), float(p[2]))
                    pts = sexpr.find(sub, "pts")
                    if pts:
                        for xy in sexpr.find_all(pts, "xy"):
                            if len(xy) >= 3:
                                add(float(xy[1]), float(xy[2]))
            elif head == Sym("pad"):
                at = sexpr.find(sub, "at")
                size = sexpr.find(sub, "size")
                if at and len(at) >= 3 and size and len(size) >= 3:
                    px, py = float(at[1]), float(at[2])
                    hx, hy = pad_half_size(at, size)
                    add(px - hx, py - hy)
                    add(px + hx, py + hy)
            else:
                walk(sub)

    walk(doc)
    if not xs:
        raise AssertionError(
            "footprint carries neither a courtyard outline nor a single "
            "sized pad — it has no measurable extent, and every consumer of "
            "this bbox (courtyard, clearance, zone packing) would be reading "
            "invented geometry. Fix the footprint document.")
    return (round(min(xs), BBOX_DECIMALS), round(min(ys), BBOX_DECIMALS),
            round(max(xs), BBOX_DECIMALS), round(max(ys), BBOX_DECIMALS))


def _footprint_bbox(mod_path: Path) -> tuple[float, float, float, float]:
    key = str(mod_path)
    if key in _bbox_cache:
        return _bbox_cache[key]
    text = mod_path.read_text()
    if _nat.loaded():
        try:
            got = tuple(_nat.module().footprint_bbox(text, BBOX_DECIMALS))
        except RuntimeError as exc:
            raise AssertionError(
                f"{mod_path} carries neither a courtyard outline nor a single "
                f"sized pad — it has no measurable extent, and every consumer of "
                f"this bbox (courtyard, clearance, zone packing) would be reading "
                f"invented geometry. Fix the footprint document.") from exc
        if _nat.trace():
            ref = _footprint_bbox_from_doc_py(sexpr.loads(text))
            if got != ref:
                raise AssertionError(
                    "native footprint_bbox DIVERGENCE: "
                    f"cpp={got} python={ref} path={mod_path}")
        _bbox_cache[key] = got
        return got
    try:
        bbox = _footprint_bbox_from_doc_py(sexpr.loads(text))
    except AssertionError as exc:
        raise AssertionError(
            f"{mod_path} carries neither a courtyard outline nor a single "
            f"sized pad — it has no measurable extent, and every consumer of "
            f"this bbox (courtyard, clearance, zone packing) would be reading "
            f"invented geometry. Fix the footprint document.") from exc
    _bbox_cache[key] = bbox
    return bbox
