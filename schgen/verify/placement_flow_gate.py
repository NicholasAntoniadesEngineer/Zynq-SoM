from __future__ import annotations

import math
from dataclasses import dataclass, field

from schgen.core import native as _nat
from schgen.generate.pcb import PcbModel
from schgen.verify.placement_contract_gate import (
    _board_refs_by_sheet,
    load_contract,
    project_zone_names,
)

FLOW_K = 0.35

FLOW_SOM_K = 1.0


def flow_budget_py(board_w: float, board_h: float,
                   som_core: tuple[float, float, float, float] | None) -> float:
    area = max(float(board_w) * float(board_h), 1.0)
    som_diag = 0.0
    if som_core is not None:
        sx0, sy0, sx1, sy1 = som_core
        som_diag = math.hypot(sx1 - sx0, sy1 - sy0)
    return FLOW_K * math.sqrt(area) + FLOW_SOM_K * som_diag


def flow_budget(board_w: float, board_h: float,
                som_core: tuple[float, float, float, float] | None) -> float:
    if not _nat.loaded():
        raise RuntimeError("native flow_budget required")
    got = _nat.module().flow_budget(board_w, board_h, som_core)
    if _nat.trace():
        ref = flow_budget_py(board_w, board_h, som_core)
        if got != ref:
            raise AssertionError(
                f"native flow_budget DIVERGENCE: cpp={got} python={ref}")
    return got


def zone_centroids(model: PcbModel) -> dict[str, tuple[float, float]]:
    acc: dict[str, list[float]] = {}
    for i in model.insts:
        a = acc.setdefault(i.sheet, [0.0, 0.0, 0.0])
        a[0] += i.x
        a[1] += i.y
        a[2] += 1.0
    if not _nat.loaded():
        raise RuntimeError("native rounded_centroid required")
    out: dict[str, tuple[float, float]] = {}
    for sheet, acc_row in acc.items():
        if acc_row[2] <= 0:
            continue
        out[sheet] = tuple(_nat.module().round_xy(
            acc_row[0] / acc_row[2], acc_row[1] / acc_row[2], 4))
    return out


def zone_bboxes(model: PcbModel) -> dict[str, tuple[float, float, float, float]]:
    from schgen.verify.placement_contract_gate import _inst_pad_boxes
    acc: dict[str, list[float]] = {}
    for i in model.insts:
        try:
            boxes = _inst_pad_boxes(i)
        except Exception:  # noqa: BLE001 — a sheet with no parsable pads is skipped
            continue
        if not boxes:
            continue
        a = acc.get(i.sheet)
        for b in boxes.values():
            if a is None:
                a = [b[0], b[1], b[2], b[3]]
                acc[i.sheet] = a
            else:
                a[0] = min(a[0], b[0])
                a[1] = min(a[1], b[1])
                a[2] = max(a[2], b[2])
                a[3] = max(a[3], b[3])
    if not _nat.loaded():
        raise RuntimeError("native round_box required")
    return {s: tuple(_nat.module().round_box(tuple(a), 4))
            for s, a in acc.items()}


def bbox_gap_py(a: tuple[float, float, float, float],
                b: tuple[float, float, float, float]) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def bbox_gap(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native bbox_gap required")
    got = _nat.module().bbox_gap(a, b)
    if _nat.trace():
        ref = bbox_gap_py(a, b)
        if got != ref:
            raise AssertionError(
                f"native bbox_gap DIVERGENCE: cpp={got} python={ref}")
    return got


def facing_dot_py(czone: tuple[float, float], cout: tuple[float, float],
                  cdown: tuple[float, float]) -> tuple[float, float]:
    ox, oy = cout[0] - czone[0], cout[1] - czone[1]
    dx, dy = cdown[0] - czone[0], cdown[1] - czone[1]
    dot = ox * dx + oy * dy
    mo = math.hypot(ox, oy)
    md = math.hypot(dx, dy)
    angle = (math.degrees(math.acos(max(-1.0, min(1.0, dot / (mo * md)))))
             if mo > 1e-9 and md > 1e-9 else 180.0)
    return dot, angle


def facing_dot(czone: tuple[float, float], cout: tuple[float, float],
               cdown: tuple[float, float]) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native facing_dot required")
    got = _nat.module().facing_dot(czone[0], czone[1], cout[0], cout[1],
                                   cdown[0], cdown[1])
    if _nat.trace():
        ref = facing_dot_py(czone, cout, cdown)
        if got != ref:
            raise AssertionError(
                f"native facing_dot DIVERGENCE: cpp={got} python={ref}")
    return got


_zone_centroids = zone_centroids
_zone_bboxes = zone_bboxes
_bbox_gap = bbox_gap


def _resolve_target_bbox(name: str,
                         bboxes: dict[str, tuple[float, float, float, float]],
                         model: PcbModel
                         ) -> tuple[float, float, float, float] | None:
    if name == _SOM_TOKEN:
        return model.som_core
    return bboxes.get(name)


_SOM_TOKEN = "@som"


def _som_centroid(model: PcbModel) -> tuple[float, float] | None:
    if model.som_core is None:
        return None
    if not _nat.loaded():
        raise RuntimeError("native round_xy required")
    x0, y0, x1, y1 = model.som_core
    return tuple(_nat.module().round_xy((x0 + x1) / 2.0, (y0 + y1) / 2.0, 4))


def _resolve_target(name: str, centroids: dict[str, tuple[float, float]],
                    model: PcbModel) -> tuple[float, float] | None:
    if name == _SOM_TOKEN:
        return _som_centroid(model)
    return centroids.get(name)


def _members_centroid(model: PcbModel, sheet: str,
                      brefs: set[str]) -> tuple[float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for i in model.insts:
        if i.sheet == sheet and i.ref in brefs:
            xs.append(i.x)
            ys.append(i.y)
    if not xs:
        return None
    if not _nat.loaded():
        raise RuntimeError("native rounded_centroid required")
    return tuple(_nat.module().rounded_centroid(list(zip(xs, ys, strict=True)),
                                                4))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native hypot_xy required")
    return _nat.module().hypot_xy(a[0], a[1], b[0], b[1])


@dataclass(frozen=True)
class FlowTerm:
    kind: str
    subject: str
    target: str
    measured: float
    bound: float
    ok: bool
    basis: str = ""


@dataclass
class PlacementFlowResult:
    ok: bool = True
    n_contracts: int = 0
    flow_checked: int = 0
    flow_fail: int = 0
    facing_checked: int = 0
    facing_fail: int = 0
    far_checked: int = 0
    far_fail: int = 0
    near_max_checked: int = 0
    near_max_fail: int = 0
    unresolved: list[str] = field(default_factory=list)
    na: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)
    board_area: float = 0.0
    flow_budget_mm: float = 0.0
    terms: list[FlowTerm] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"PLACEMENT-FLOW GATE: {'PASS' if self.ok else 'FAIL'} "
             f"({self.n_contracts} external contract(s); "
             f"board_area={self.board_area:.0f}mm^2, "
             f"flow_budget={self.flow_budget_mm:.1f}mm)"]
        L.append(
            "  fails: "
            f"flow={self.flow_fail}/{self.flow_checked} "
            f"facing={self.facing_fail}/{self.facing_checked} "
            f"far={self.far_fail}/{self.far_checked} "
            f"near_max={self.near_max_fail}/{self.near_max_checked}")
        L.append(f"  unresolved: {len(self.unresolved)}")
        for u in sorted(self.unresolved):
            L.append(f"    UNRESOLVED {u}")
        if self.na:
            L.append(f"  n/a (subsystem not in this project): {len(self.na)}")
            for x in sorted(self.na):
                L.append(f"    {x}")
        L.append(f"  violations: {len(self.violations)}")
        for v in sorted(self.violations):
            L.append(f"    {v}")
        L.append(f"  detail: {len(self.detail)}")
        for d in sorted(self.detail):
            L.append(f"    {d}")
        return "\n".join(L)


def check(model: PcbModel,
          contracts: dict[str, dict] | None = None,
          ref_maps: dict[str, dict[str, str]] | None = None
          ) -> PlacementFlowResult:
    res = PlacementFlowResult()
    centroids = zone_centroids(model)
    bboxes = zone_bboxes(model)
    area = max(float(model.board_w) * float(model.board_h), 1.0)
    res.board_area = area
    budget = flow_budget(model.board_w, model.board_h, model.som_core)
    res.flow_budget_mm = round(budget, 4)

    if contracts is None:
        contracts = {}
        for sheet in sorted({i.sheet for i in model.insts}):
            c = load_contract(sheet)
            if c is not None and c.get("external"):
                contracts[sheet] = c
    else:
        contracts = {s: c for s, c in contracts.items() if c.get("external")}

    zones_known = project_zone_names()

    def foreign(*names: str) -> list[str]:
        return [n for n in names
                if n != _SOM_TOKEN and n.split(".", 1)[0] not in zones_known]

    def add(v: str) -> None:
        res.violations.append(v)

    for sheet in sorted(contracts):
        contract = contracts[sheet]
        ext = contract.get("external") or {}
        res.n_contracts += 1

        flow = ext.get("flow", [])
        for a, b in zip(flow, flow[1:], strict=False):
            gone_na = foreign(a, b)
            if gone_na:
                res.na.append(f"flow {a}->{b}: n/a — "
                              f"{'/'.join(gone_na)} not a subsystem of this "
                              f"project")
                continue
            res.flow_checked += 1
            ca = _resolve_target(a, centroids, model)
            cb = _resolve_target(b, centroids, model)
            if ca is None or cb is None:
                gone = "/".join(x for x, c in ((a, ca), (b, cb)) if c is None)
                miss = f"{sheet}: flow zone {gone} not placed"
                if miss not in res.unresolved:
                    res.unresolved.append(miss)
                res.flow_fail += 1
                cid = contract.get("contract", "?")
                add(f"flow {a}->{b}: zone(s) not placed [{cid}]")
                res.terms.append(FlowTerm("flow", a, b, math.inf,
                                          round(budget, 4), False))
                continue
            d = _dist(ca, cb)
            res.detail.append(
                f"flow {a}->{b}: {d:.2f}mm / {budget:.1f}mm budget")
            res.terms.append(FlowTerm("flow", a, b, d, round(budget, 4),
                                      d <= budget))
            if d > budget:
                res.flow_fail += 1
                add(f"flow {a}->{b}: {d:.2f}mm > {budget:.1f}mm budget "
                    f"(FLOW_K={FLOW_K} free + SoM detour)")

        downstream = ext.get("downstream")
        output_roles = set(ext.get("output_roles", []))
        if downstream and output_roles:
            if foreign(downstream):
                res.na.append(f"facing {sheet}->{downstream}: n/a — "
                              f"{downstream!r} not a subsystem of this "
                              f"project")
            else:
                res.facing_checked += 1
                _facing(res, model, sheet, contract, downstream, output_roles,
                        centroids, ref_maps, add)

        for far in ext.get("far", []):
            what = far.get("what", "?")
            min_mm = float(far.get("min_mm", 0.0))
            basis = far.get("basis", "")
            zname = what.split(".", 1)[0]
            if foreign(zname):
                res.na.append(f"far {sheet} vs {what}: n/a — {zname!r} not a "
                              f"subsystem of this project")
                continue
            res.far_checked += 1
            czone = centroids.get(sheet)
            ctgt = centroids.get(zname)
            if czone is None or ctgt is None:
                un = f"{sheet}: far target {what!r} (zone {zname!r}) not placed"
                if un not in res.unresolved:
                    res.unresolved.append(un)
                res.far_fail += 1
                add(f"far {sheet} vs {what}: UNRESOLVED (zone {zname!r} not "
                    f"placed) [{basis}]")
                res.terms.append(FlowTerm("far", sheet, what, math.inf,
                                          min_mm, False, basis))
                continue
            d = _dist(czone, ctgt)
            res.detail.append(
                f"far {sheet} vs {what}: {d:.2f}mm / >= {min_mm:g}mm")
            res.terms.append(FlowTerm("far", sheet, what, d, min_mm,
                                      d >= min_mm, basis))
            if d < min_mm:
                res.far_fail += 1
                add(f"far {sheet} vs {what}: {d:.2f}mm < {min_mm:g}mm "
                    f"[{basis}]")

        for near in ext.get("near_max", []):
            other = near.get("other", "?")
            max_mm = float(near.get("max_mm", 0.0))
            basis = near.get("basis", "")
            if foreign(other):
                res.na.append(f"near_max {sheet} to {other}: n/a — "
                              f"{other!r} not a subsystem of this project")
                continue
            res.near_max_checked += 1
            bzone = bboxes.get(sheet)
            btgt = _resolve_target_bbox(other, bboxes, model)
            if bzone is None or btgt is None:
                un = f"{sheet}: near_max target {other!r} not placed"
                if un not in res.unresolved:
                    res.unresolved.append(un)
                res.near_max_fail += 1
                add(f"near_max {sheet} to {other}: UNRESOLVED ({other!r} not "
                    f"placed) [{basis}]")
                res.terms.append(FlowTerm("near_max", sheet, other, math.inf,
                                          max_mm, False, basis))
                continue
            d = bbox_gap(bzone, btgt)
            res.detail.append(
                f"near_max {sheet} to {other}: {d:.2f}mm gap / <= {max_mm:g}mm")
            res.terms.append(FlowTerm("near_max", sheet, other, d, max_mm,
                                      d <= max_mm, basis))
            if d > max_mm:
                res.near_max_fail += 1
                add(f"near_max {sheet} to {other}: {d:.2f}mm gap > {max_mm:g}mm "
                    f"[{basis}]")

    res.ok = (not res.violations and not res.unresolved)
    return res


def _facing(res: PlacementFlowResult, model: PcbModel, sheet: str,
            contract: dict, downstream: str, output_roles: set[str],
            centroids: dict[str, tuple[float, float]],
            ref_maps: dict[str, dict[str, str]] | None,
            add) -> None:
    roles = contract.get("roles", {})
    out_libs = [r for r, v in roles.items() if v in output_roles]
    if not out_libs:
        un = f"{sheet}: facing output_roles {sorted(output_roles)} match no role"
        if un not in res.unresolved:
            res.unresolved.append(un)
        res.facing_fail += 1
        add(f"facing {sheet}: no output-role parts declared for "
            f"{sorted(output_roles)} [{contract.get('contract', '?')}]")
        res.terms.append(FlowTerm("facing", sheet, downstream, math.inf,
                                  90.0, False, contract.get("contract", "?")))
        return

    if ref_maps is not None and sheet in ref_maps:
        ref_map = ref_maps[sheet]
    else:
        ref_map = _board_refs_by_sheet(sheet)
    out_brefs = {ref_map[r] for r in out_libs if r in ref_map}

    czone = centroids.get(sheet)
    cds = _resolve_target(downstream, centroids, model)
    cout = _members_centroid(model, sheet, out_brefs)
    if czone is None or cds is None or cout is None:
        missing = []
        if czone is None:
            missing.append(sheet)
        if cds is None:
            missing.append(downstream)
        if cout is None:
            missing.append(f"{sheet}.output_parts")
        un = f"{sheet}: facing needs placed {missing}"
        if un not in res.unresolved:
            res.unresolved.append(un)
        res.facing_fail += 1
        add(f"facing {sheet}->{downstream}: UNRESOLVED (not placed: "
            f"{missing}) [{contract.get('contract', '?')}]")
        res.terms.append(FlowTerm("facing", sheet, downstream, math.inf,
                                  90.0, False, contract.get("contract", "?")))
        return

    dot, angle = facing_dot(czone, cout, cds)
    res.detail.append(
        f"facing {sheet}->{downstream}: dot={dot:+.2f} "
        f"angle={angle:.1f}deg (output@{cout} zone@{czone} down@{cds})")
    res.terms.append(FlowTerm("facing", sheet, downstream, angle, 90.0,
                              dot > 0.0, contract.get("contract", "?")))
    if dot <= 0.0:
        res.facing_fail += 1
        add(f"facing {sheet}->{downstream}: output parts face AWAY "
            f"(dot={dot:+.2f} <= 0, angle={angle:.1f}deg) "
            f"[{contract.get('contract', '?')}]")
