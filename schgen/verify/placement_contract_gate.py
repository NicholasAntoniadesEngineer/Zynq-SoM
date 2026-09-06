from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _nat
from schgen.core import sexpr
from schgen.core.project import PROJECT_ROOT
from schgen.core.project import spec as _project_spec
from schgen.core.sexpr import Sym
from schgen.generate.pcb import PcbModel

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBSYSTEMS_DIR = _REPO_ROOT / "subsystems"
_PROJECT_SUBSYSTEMS_DIR = PROJECT_ROOT / "subsystems"

_CONTRACT_ROOTS: tuple[tuple[Path, str | None], ...] = (
    (_SUBSYSTEMS_DIR, "subsystems"),
    (_PROJECT_SUBSYSTEMS_DIR, None),
)

_WIRED_SHEETS: frozenset[str] = _project_spec().wired_sheets


def discover_contract(sheet_name: str) -> dict | None:
    import importlib
    import importlib.util
    for root_dir, pkg_prefix in _CONTRACT_ROOTS:
        pkg = root_dir / sheet_name / "placement_contract.py"
        if not pkg.exists():
            continue
        if pkg_prefix is not None:
            mod = importlib.import_module(
                f"{pkg_prefix}.{sheet_name}.placement_contract")
        else:
            spec = importlib.util.spec_from_file_location(
                f"_project_contract_{sheet_name}", pkg)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        contract = getattr(mod, "CONTRACT", None)
        if contract is not None and sheet_name not in _PIN_VALIDATED:
            validate_contract_pins(sheet_name, contract)
            _PIN_VALIDATED.add(sheet_name)
        return contract
    return None


def load_contract(sheet_name: str) -> dict | None:
    if sheet_name not in _WIRED_SHEETS:
        return None
    return discover_contract(sheet_name)


class ContractPinError(ValueError):
    pass


_PIN_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "hot_loop": (("ic", "pin_pairs"),),
    "bulk_in": (("ic", "vin_pins"),),
    "bulk_out": (("inductor", "inductor_out_pin"),),
    "sw_node": (("ic", "sw_pin"),),
    "fb_cluster": (("ic", "fb_pin"), ("ic", "own_sw_pin"),
                   ("foreign_ic", "foreign_sw_pin")),
    "boot": (("ic", "pins"),),
    "vcc_cap": (("ic", "pin"),),
    "bias_cap": (("ic", "pin"),),
    "rt_r": (("ic", "pin"),),
    "ldo_stage": (("ic", "cin_pin"), ("ic", "cout_pin")),
    "proximity": (("anchor", "anchor_pins"),),
}

_PIN_VALIDATED: set[str] = set()


def _named_pins(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    out: list[str] = []
    for x in v:
        out.extend(_named_pins(x))
    return out


def validate_contract_pins(sheet_name: str, contract: dict) -> None:
    from schgen.core.link import load_subsystem
    from schgen.generate.pcb.footprint import resolve_mod

    parts = load_subsystem(sheet_name).circuit.parts
    pads_of: dict[str, frozenset[str] | None] = {}

    def pads(ref: str) -> frozenset[str] | None:
        if ref not in pads_of:
            part = parts.get(ref)
            fp = getattr(part, "footprint", "") if part is not None else ""
            mod = resolve_mod(fp) if fp else None
            pads_of[ref] = None if mod is None else frozenset(
                p for p in _pad_boxes(mod, 0.0) if p)
        return pads_of[ref]

    def demand(idx: int, typ: str, ref: str, fld: str,
               pins: list[str]) -> None:
        avail = pads(ref)
        if avail is None:
            return
        for p in pins:
            if p not in avail:
                raise ContractPinError(
                    f"placement contract {sheet_name!r} structure #{idx} "
                    f"({typ}): {fld} names pin {p!r} but {ref} (footprint "
                    f"{parts[ref].footprint!r}) has no such pad — pin fields "
                    f"must be FOOTPRINT pad ids, not symbol pin names. "
                    f"Available pads: "
                    f"{sorted(avail, key=lambda s: (len(s), s))}")

    for idx, st in enumerate(contract.get("structures", [])):
        typ = str(st.get("type"))
        for ref_key, fld in _PIN_FIELDS.get(typ, ()):
            ref, val = st.get(ref_key), st.get(fld)
            if ref and val:
                demand(idx, typ, ref, fld, _named_pins(val))
        if typ == "proximity":
            for mf in st.get("min_from", []):
                ref, p = mf.get("part"), mf.get("pin")
                if ref and p:
                    demand(idx, typ, ref, "min_from.pin", [p])


def project_zone_names() -> frozenset[str]:
    from schgen.core.link import all_subsystem_paths
    return frozenset(p.stem for p in all_subsystem_paths())


def discover_all() -> dict[str, dict]:
    from schgen.core.link import all_subsystem_paths
    out: dict[str, dict] = {}
    for p in sorted(all_subsystem_paths()):
        c = discover_contract(p.stem)
        if c is not None:
            out[p.stem] = c
    return out


def coverage(model) -> dict:
    return {sheet: check(model, sheet, contract=c)
            for sheet, c in sorted(discover_all().items())}


def coverage_report(cov: dict) -> tuple[str, int, int, int]:
    wired = met = viol = 0
    detail: list[str] = []
    for sheet in sorted(cov):
        res = cov[sheet]
        if not getattr(res, "have_contract", False):
            continue
        w = sheet in _WIRED_SHEETS
        nv = len(res.violations)
        if w:
            wired += 1
            status = "WIRED-gated"
        elif nv == 0:
            met += 1
            status = "inert-met"
        else:
            viol += 1
            status = "inert-VIOLATED"
        worst = (res.violations[0] if res.violations else "").split(" [")[0]
        detail.append(f"  {sheet:22} {status:15} {res.checked:2} chk  "
                      f"{nv} viol  {worst[:64]}")
    head = (f"CONTRACT COVERAGE: {wired} wired(gated) / {met} inert-met / "
            f"{viol} inert-VIOLATED  (authored SI/PI intent not yet placer-enforced)")
    return head + "\n" + "\n".join(detail), wired, met, viol


def wired_term_participants() -> tuple[frozenset[str], frozenset[str]]:
    exempt: set[str] = set(_WIRED_SHEETS)
    others: set[str] = set()
    for sheet, c in sorted(discover_all().items()):
        if sheet not in _WIRED_SHEETS:
            continue
        ext = c.get("external") or {}
        for nm in ext.get("near_max", []):
            exempt.add(sheet)
            exempt.add(str(nm.get("other", "")).split(".", 1)[0])
        flow = list(ext.get("flow", []))
        for a, b in zip(flow, flow[1:], strict=False):
            others.update((str(a).split(".", 1)[0],
                           str(b).split(".", 1)[0]))
        if ext.get("downstream") and ext.get("output_roles"):
            others.add(sheet)
            others.add(str(ext["downstream"]).split(".", 1)[0])
        for far in ext.get("far", []):
            others.add(sheet)
            others.add(str(far.get("what", "")).split(".", 1)[0])
    exempt.discard("@som")
    others.discard("@som")
    return frozenset(exempt), frozenset(others - exempt)


_pad_box_cache: dict[tuple[str, float], dict[str, tuple]] = {}


def _pad_named_rows(mod_path: Path
                    ) -> list[tuple[str, float, float, float, float, float]]:
    rows: list[tuple[str, float, float, float, float, float]] = []
    for node in sexpr.loads(mod_path.read_text()):
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3):
            continue
        prot = float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) \
            else 0.0
        sw, sh = (float(sz[1]), float(sz[2])) if sz and len(sz) >= 3 \
            else (0.0, 0.0)
        rows.append((name, float(at[1]), float(at[2]), prot, sw, sh))
    return rows


def _pad_boxes_py(
    mod_path: Path, rotation: float
) -> dict[str, tuple[float, float, float, float]]:
    R = math.radians(rotation or 0.0)
    cs, sn = math.cos(R), math.sin(R)
    out: dict[str, tuple[float, float, float, float]] = {}
    for name, px, py, prot_deg, sw, sh in _pad_named_rows(mod_path):
        prot = math.radians(prot_deg)
        cx = px * cs + py * sn
        cy = -px * sn + py * cs
        tot = R + prot
        ct, st = abs(math.cos(tot)), abs(math.sin(tot))
        hx = ct * sw / 2 + st * sh / 2
        hy = st * sw / 2 + ct * sh / 2
        b = (cx - hx, cy - hy, cx + hx, cy + hy)
        if name in out:
            o = out[name]
            b = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
        out[name] = b
    return out


def _pad_boxes(
    mod_path: Path, rotation: float
) -> dict[str, tuple[float, float, float, float]]:
    key = (str(mod_path), round(rotation or 0.0, 3))
    hit = _pad_box_cache.get(key)
    if hit is not None:
        return hit
    if _nat.loaded():
        rows = _pad_named_rows(mod_path)
        got = {n: (x0, y0, x1, y1)
               for n, x0, y0, x1, y1 in _nat.module().pad_boxes_named(
                   rows, rotation or 0.0)}
        if _nat.trace():
            ref = _pad_boxes_py(mod_path, rotation)
            if got != ref:
                raise AssertionError(
                    "native pad_boxes_named DIVERGENCE: "
                    f"cpp={got} python={ref}")
        _pad_box_cache[key] = got
        return got
    out = _pad_boxes_py(mod_path, rotation)
    _pad_box_cache[key] = out
    return out


def _inst_pad_boxes(inst) -> dict[str, tuple[float, float, float, float]]:
    rel = _pad_boxes(inst.mod_path, inst.rotation or 0.0)
    return {n: (inst.x + b[0], inst.y + b[1], inst.x + b[2], inst.y + b[3])
            for n, b in rel.items()}


def _box_gap_py(a: tuple[float, float, float, float],
                b: tuple[float, float, float, float]) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _box_gap(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> float:
    if _nat.loaded():
        got = _nat.module().box_gap(a, b)
        if _nat.trace():
            ref = _box_gap_py(a, b)
            if got != ref:
                raise AssertionError(
                    f"native box_gap DIVERGENCE: cpp={got} python={ref}")
        return got
    return _box_gap_py(a, b)


def _pins_to_part_py(pin_boxes: dict[str, tuple], part_boxes: dict[str, tuple],
                     pins: list[str]) -> float | None:
    best: float | None = None
    part = list(part_boxes.values())
    if not part:
        return None
    for p in pins:
        pb = pin_boxes.get(p)
        if pb is None:
            continue
        for qb in part:
            g = _box_gap_py(pb, qb)
            best = g if best is None else min(best, g)
    return best


def _pins_to_part(pin_boxes: dict[str, tuple], part_boxes: dict[str, tuple],
                  pins: list[str]) -> float | None:
    part = list(part_boxes.values())
    pin_hits = [pin_boxes[p] for p in pins if p in pin_boxes]
    if _nat.loaded():
        got = _nat.module().min_box_gap(pin_hits, part)
        if _nat.trace():
            ref = _pins_to_part_py(pin_boxes, part_boxes, pins)
            if got != ref:
                raise AssertionError(
                    "native min_box_gap DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _pins_to_part_py(pin_boxes, part_boxes, pins)


def _part_to_part_py(a_boxes: dict[str, tuple], b_boxes: dict[str, tuple]
                     ) -> float | None:
    best: float | None = None
    for ab in a_boxes.values():
        for bb in b_boxes.values():
            g = _box_gap_py(ab, bb)
            best = g if best is None else min(best, g)
    return best


def _part_to_part(a_boxes: dict[str, tuple], b_boxes: dict[str, tuple]
                  ) -> float | None:
    if _nat.loaded():
        got = _nat.module().min_box_gap(list(a_boxes.values()),
                                        list(b_boxes.values()))
        if _nat.trace():
            ref = _part_to_part_py(a_boxes, b_boxes)
            if got != ref:
                raise AssertionError(
                    "native min_box_gap DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got
    return _part_to_part_py(a_boxes, b_boxes)


def _board_refs_by_sheet(sheet_name: str, parts=None) -> dict[str, str]:
    import json

    from schgen.generate.board import _renamed_ref
    idx_path = PROJECT_ROOT / "sheet_index.json"
    sheet_index = (json.loads(idx_path.read_text())
                   if idx_path.exists() else {})
    idx = sheet_index.get(sheet_name)
    if idx is None:
        from schgen.core.link import all_subsystem_paths
        order = [p.stem for p in all_subsystem_paths()]
        idx = order.index(sheet_name) + 1 if sheet_name in order else 1
    if parts is None:
        from schgen.core.link import load_subsystem
        parts = load_subsystem(sheet_name).circuit.parts
    return {ref: _renamed_ref(ref, idx, sheet=sheet_name)
            for ref in parts}


@dataclass
class PlacementContractResult:
    ok: bool = True
    sheet: str = ""
    have_contract: bool = False
    checked: int = 0
    violations: list[str] = field(default_factory=list)
    hot_loop_fail: int = 0
    same_side_fail: int = 0
    bulk_fail: int = 0
    bulk_out_fail: int = 0
    sw_node_fail: int = 0
    fb_fail: int = 0
    boot_fail: int = 0
    vcc_fail: int = 0
    bias_fail: int = 0
    rt_fail: int = 0
    ldo_fail: int = 0
    proximity_fail: int = 0
    unknown_fail: int = 0
    missing_refs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"PLACEMENT-CONTRACT GATE ({self.sheet or '?'}): "
             f"{'PASS' if self.ok else 'FAIL'} "
             f"(contract={'yes' if self.have_contract else 'none'}, "
             f"{self.checked} structures)"]
        L.append(
            "  fails: "
            f"hot_loop={self.hot_loop_fail} same_side={self.same_side_fail} "
            f"bulk={self.bulk_fail} bulk_out={self.bulk_out_fail} "
            f"sw_node={self.sw_node_fail} "
            f"fb={self.fb_fail} boot={self.boot_fail} vcc={self.vcc_fail} "
            f"bias={self.bias_fail} rt={self.rt_fail} ldo={self.ldo_fail} "
            f"proximity={self.proximity_fail} unknown={self.unknown_fail}")
        L.append(f"  unresolved refs: {len(self.missing_refs)}")
        for r in sorted(self.missing_refs):
            L.append(f"    MISSING {r}")
        L.append(f"  violations: {len(self.violations)}")
        for v in sorted(self.violations):
            L.append(f"    {v}")
        return "\n".join(L)


def check(model: PcbModel, sheet_name: str = "power",
          contract: dict | None = None,
          ref_map: dict[str, str] | None = None) -> PlacementContractResult:
    res = PlacementContractResult(sheet=sheet_name)
    if contract is None:
        contract = load_contract(sheet_name)
    if contract is None:
        res.have_contract = False
        res.ok = True
        return res
    res.have_contract = True

    if ref_map is None:
        ref_map = _board_refs_by_sheet(sheet_name)
    inst_by_bref = {i.ref: i for i in model.insts if i.sheet == sheet_name}

    def inst(lib_ref: str):
        bref = ref_map.get(lib_ref)
        if bref is None or bref not in inst_by_bref:
            miss = f"{lib_ref}->{bref or '?'}"
            if miss not in res.missing_refs:
                res.missing_refs.append(miss)
            return None
        return inst_by_bref[bref]

    def boxes(lib_ref: str) -> dict[str, tuple] | None:
        it = inst(lib_ref)
        return None if it is None else _inst_pad_boxes(it)

    def add(v: str) -> None:
        res.violations.append(v)

    for st in contract.get("structures", []):
        typ = st.get("type")
        res.checked += 1

        if typ == "hot_loop":
            ic = st["ic"]
            ic_it = inst(ic)
            ic_boxes = None if ic_it is None else _inst_pad_boxes(ic_it)
            lim = float(st["max_pad_to_pin_mm"])
            basis = st["basis"]
            cap_data = [(cref, inst(cref), boxes(cref)) for cref in st["caps"]]
            for pair in st["pin_pairs"]:
                best_ref, best_d = None, None
                for cref, cit, cboxes in cap_data:
                    if ic_boxes is None or cboxes is None or cit is None:
                        continue
                    if st.get("same_side") and ic_it is not None \
                            and cit.side != ic_it.side:
                        continue
                    d = _pins_to_part(ic_boxes, cboxes, pair)
                    if d is None:
                        continue
                    if best_d is None or d < best_d:
                        best_ref, best_d = cref, d
                if best_d is None or best_d > lim:
                    res.hot_loop_fail += 1
                    detail = (f"none within {lim:g}mm same-side"
                              if best_d is None
                              else f"nearest {best_ref} {best_d:.2f}mm")
                    add(f"hot_loop {ic} pins {'/'.join(pair)} (VIN/PGND): "
                        f"{detail} > {lim:g}mm [{basis}]")

        elif typ == "bulk_in":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lim = float(st["max_pad_to_pin_mm"])
            for cref in st["caps"]:
                cb = boxes(cref)
                if ic_boxes is None or cb is None:
                    continue
                d = _pins_to_part(ic_boxes, cb, st["vin_pins"])
                if d is None or d > lim:
                    res.bulk_fail += 1
                    add(f"bulk_in {ic} {cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to VIN {st['vin_pins']} [{st['basis']}]")

        elif typ == "bulk_out":
            ic = st["ic"]
            ic_it = inst(ic)
            l_it = inst(st["inductor"])
            l_boxes = None if l_it is None else _inst_pad_boxes(l_it)
            lim = float(st["max_pad_to_pin_mm"])
            out_pin = st["inductor_out_pin"]
            for cref in st["caps"]:
                cit = inst(cref)
                cb = boxes(cref)
                if l_boxes is None or cb is None or cit is None:
                    continue
                if st.get("same_side") and ic_it is not None \
                        and cit.side != ic_it.side:
                    res.bulk_out_fail += 1
                    add(f"bulk_out {ic} {cref}: on {cit.side} but IC is "
                        f"{ic_it.side} (same_side) [{st['basis']}]")
                    continue
                d = _pins_to_part(l_boxes, cb, [out_pin])
                if d is None or d > lim:
                    res.bulk_out_fail += 1
                    add(f"bulk_out {ic} {cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to L={st['inductor']} out pad {out_pin} "
                        f"[{st['basis']}]")

        elif typ == "sw_node":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lb = boxes(st["inductor"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and lb is not None:
                d = _pins_to_part(ic_boxes, lb, [st["sw_pin"]])
                if d is None or d > lim:
                    res.sw_node_fail += 1
                    add(f"sw_node {ic} L={st['inductor']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to SW pin {st['sw_pin']} [{st['basis']}]")

        elif typ == "fb_cluster":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            own_l = boxes(st["own_inductor"])
            foreign_ic_ref = st.get("foreign_ic")
            for_ic = boxes(foreign_ic_ref) if foreign_ic_ref else None
            foreign_l_ref = st.get("foreign_inductor")
            for_l = boxes(foreign_l_ref) if foreign_l_ref else None
            foreign_sw_pin = st.get("foreign_sw_pin")
            to_fb = float(st["max_to_fb_mm"])
            min_own = float(st["min_to_own_sw_mm"])
            min_for = float(st.get("min_to_foreign_sw_mm", 0.0))
            for mref in st["members"]:
                mb = boxes(mref)
                if mb is None:
                    continue
                if ic_boxes is not None:
                    d = _pins_to_part(ic_boxes, mb, [st["fb_pin"]])
                    if d is None or d > to_fb:
                        res.fb_fail += 1
                        add(f"fb_cluster {ic} {mref}: "
                            f"{'n/a' if d is None else f'{d:.2f}mm'} > {to_fb:g}mm "
                            f"to FB pin {st['fb_pin']} [{st['basis']}]")
                own_d = None
                if ic_boxes is not None:
                    own_d = _pins_to_part(ic_boxes, mb, [st["own_sw_pin"]])
                if own_l is not None:
                    dl = _part_to_part(mb, own_l)
                    own_d = dl if own_d is None else (
                        dl if dl is not None and dl < own_d else own_d)
                if own_d is not None and own_d < min_own:
                    res.fb_fail += 1
                    add(f"fb_cluster {ic} {mref}: {own_d:.2f}mm < {min_own:g}mm "
                        f"from own SW/L (too close) [{st['basis']}]")
                if foreign_ic_ref is not None:
                    for_d = None
                    if for_ic is not None and foreign_sw_pin is not None:
                        for_d = _pins_to_part(for_ic, mb, [foreign_sw_pin])
                    if for_l is not None:
                        dl = _part_to_part(mb, for_l)
                        for_d = dl if for_d is None else (
                            dl if dl is not None and dl < for_d else for_d)
                    if for_d is not None and for_d < min_for:
                        res.fb_fail += 1
                        add(f"fb_cluster {ic} {mref}: {for_d:.2f}mm < "
                            f"{min_for:g}mm from foreign {foreign_ic_ref} SW/L "
                            f"[{st['basis']}]")

        elif typ == "boot":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, st["pins"])
                if d is None or d > lim:
                    res.boot_fail += 1
                    add(f"boot {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to pins {st['pins']} [{st['basis']}]")

        elif typ == "vcc_cap":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, [st["pin"]])
                if d is None or d > lim:
                    res.vcc_fail += 1
                    add(f"vcc_cap {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to VCC pin {st['pin']} [{st['basis']}]")

        elif typ == "bias_cap":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, [st["pin"]])
                if d is None or d > lim:
                    res.bias_fail += 1
                    add(f"bias_cap {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to BIAS pin {st['pin']} [{st['basis']}]")

        elif typ == "rt_r":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            rb = boxes(st["resistor"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and rb is not None:
                d = _pins_to_part(ic_boxes, rb, [st["pin"]])
                if d is None or d > lim:
                    res.rt_fail += 1
                    add(f"rt_r {ic} {st['resistor']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to RT pin {st['pin']} [{st['basis']}]")

        elif typ == "ldo_stage":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lim = float(st["max_pad_to_pin_mm"])
            for role, cref, pin in (("Cin", st["cin"], st["cin_pin"]),
                                    ("Cout", st["cout"], st["cout_pin"])):
                cb = boxes(cref)
                if ic_boxes is None or cb is None:
                    continue
                d = _pins_to_part(ic_boxes, cb, [pin])
                if d is None or d > lim:
                    res.ldo_fail += 1
                    add(f"ldo_stage {ic} {role}={cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to pin {pin} [{st['basis']}]")

        elif typ == "proximity":
            _proximity(st, res, inst, boxes, add)

        elif typ == "same_side":
            roles = contract.get("roles", {})
            for ic in st["ics"]:
                ic_it = inst(ic)
                if ic_it is None:
                    continue
                members: set[str] = set()
                for s2 in contract.get("structures", []):
                    if s2.get("type") == "same_side":
                        continue
                    if s2.get("ic") != ic and s2.get("anchor") != ic:
                        continue
                    for k in ("cap", "inductor", "resistor", "cin", "cout"):
                        if k in s2:
                            members.add(s2[k])
                    for k in ("caps", "members"):
                        members.update(s2.get(k, []))
                for mref in sorted(members):
                    mit = inst(mref)
                    if mit is None:
                        continue
                    if mit.side != ic_it.side:
                        res.same_side_fail += 1
                        add(f"same_side {ic} {mref}: on {mit.side} but IC is "
                            f"{ic_it.side} [{st['basis']}]")
                _ = roles

        else:
            res.unknown_fail += 1
            add(f"UNKNOWN structure type {typ!r} — gate has no branch to check "
                f"it (fail-loud) [{st.get('basis', '')}]")

    res.ok = (not res.violations)
    return res


def _proximity(st: dict, res: PlacementContractResult, inst, boxes, add) -> None:
    anchor = st.get("anchor")
    anchor_it = inst(anchor) if anchor else None
    anchor_boxes = boxes(anchor) if anchor else None
    anchor_pins = st.get("anchor_pins")
    max_mm = float(st["max_mm"])
    same_side = bool(st.get("same_side", False))
    basis = st.get("basis", "")

    for mref in st.get("members", []):
        mb = boxes(mref)
        mit = inst(mref)
        if mb is None or anchor_boxes is None:
            continue
        if anchor_pins:
            d = _pins_to_part(anchor_boxes, mb, anchor_pins)
        else:
            d = _part_to_part(anchor_boxes, mb)
        tgt = (f"pins {'/'.join(anchor_pins)}" if anchor_pins else "any pad")
        if d is None or d > max_mm:
            res.proximity_fail += 1
            add(f"proximity {anchor} {mref}: "
                f"{'n/a' if d is None else f'{d:.2f}mm'} > {max_mm:g}mm "
                f"to {anchor} {tgt} [{basis}]")
        if same_side and anchor_it is not None and mit is not None \
                and mit.side != anchor_it.side:
            res.proximity_fail += 1
            add(f"proximity {anchor} {mref}: on {mit.side} but anchor "
                f"{anchor} is {anchor_it.side} (same_side) [{basis}]")
        for mf in st.get("min_from", []):
            other = mf.get("part")
            ob = boxes(other) if other else None
            if ob is None:
                continue
            mm = float(mf.get("min_mm", 0.0))
            opin = mf.get("pin")
            fd = (_pins_to_part(ob, mb, [opin]) if opin
                  else _part_to_part(ob, mb))
            otgt = (f"pin {opin}" if opin else "any pad")
            if fd is not None and fd < mm:
                res.proximity_fail += 1
                add(f"proximity {anchor} {mref}: {fd:.2f}mm < {mm:g}mm from "
                    f"{other} {otgt} (too close) [{basis}]")


def check_all(model: PcbModel) -> dict[str, PlacementContractResult]:
    out: dict[str, PlacementContractResult] = {}
    for sheet in sorted({i.sheet for i in model.insts}):
        c = discover_contract(sheet)
        if c is None:
            continue
        out[sheet] = check(model, sheet_name=sheet, contract=c)
    return out
