from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from schgen.core import native as _nat
from schgen.core import quantize as _q
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]


GUARD_MM = 4.0

FAR_L4_GUARD_MM: dict[str, float] = {"ethernet": 14.0, "power_som": 25.0}

W_HOP = 1.0
W_SEED = 0.05
REPAIR_MAX = 16
CUT_MAX = 8
MEDIAN_PASSES = 8
EPS_FACE = 2.0
EPS_CUT = 0.5
AREA_TARGET_MM2 = 24600.0

CHANNEL_FLOOR_MM = 2.0
CHANNEL_PER_NET_MM = 0.2
CHANNEL_MIN_NETS = 6

_KNOWN_EXTERNAL_KEYS = {"flow", "downstream", "output_roles", "far", "near_max",
                        "media_faces_near_max"}
_SOM_TOKEN = "@som"


def weighted_median_py(pulls: list[tuple[float, float]]) -> float:
    ordered = sorted(pulls, key=lambda pp: pp[1])
    tot = sum(w for w, _ in ordered)
    acc = 0.0
    best = ordered[0][1]
    for weight, pos in ordered:
        acc += weight
        if acc >= tot / 2 - 1e-12:
            best = pos
            break
    return best


def weighted_median(pulls: list[tuple[float, float]]) -> float:
    if not _nat.loaded():
        raise RuntimeError("native weighted_median required")
    got = _nat.module().weighted_median(pulls)
    if _nat.trace():
        ref = weighted_median_py(pulls)
        if got != ref:
            raise AssertionError(
                "native weighted_median DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


ESCAPE_SIDECAR = PROJECT_ROOT / "escape_block.json"


def escape_corridors(path: Path | None = None
                     ) -> list[tuple[str, float, float, float, float]]:
    import json as _json
    if path is None:
        path = ESCAPE_SIDECAR
    if not path.exists():
        return []
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    raw = _json.loads(path.read_text())
    out: list[tuple[str, float, float, float, float]] = []
    for name in sorted((raw.get("t1_constraints") or {}).get("corridors",
                                                             {})):
        r = raw["t1_constraints"]["corridors"][name]["rect"]
        out.append((f"escape:{name}", r[0] - ORIGIN_X, r[1] - ORIGIN_Y,
                    r[2] - ORIGIN_X, r[3] - ORIGIN_Y))
    return out


def corridor_intrusions(model, corridors=None
                        ) -> tuple[list[str], list[str]]:
    import json as _json

    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    from schgen.verify.placement_contract_gate import _inst_pad_boxes
    if corridors is None:
        corridors = escape_corridors()
    if not corridors:
        return [], []
    managed_refs: dict[tuple[str, str], str] = {}
    if ESCAPE_SIDECAR.exists():
        raw = _json.loads(ESCAPE_SIDECAR.read_text())
        for c in (raw.get("escape_meta") or {}).get("coexistence", []):
            managed_refs[(c.get("ref", ""), c.get("sheet", ""))] = \
                c.get("verdict", "?")
    page = [(n, x0 + ORIGIN_X, y0 + ORIGIN_Y, x1 + ORIGIN_X, y1 + ORIGIN_Y)
            for n, x0, y0, x1, y1 in corridors]
    unmanaged: list[str] = []
    managed: list[str] = []
    for i in model.insts:
        if i.sheet.startswith("som_j"):
            continue
        try:
            boxes = _inst_pad_boxes(i)
        except Exception:  # noqa: BLE001
            continue
        hit = None
        for b in boxes.values():
            for n, x0, y0, x1, y1 in page:
                if b[0] < x1 and b[2] > x0 and b[1] < y1 and b[3] > y0:
                    hit = n
                    break
            if hit:
                break
        if hit is None:
            continue
        v = managed_refs.get((i.ref, i.sheet))
        line = f"{i.ref} ({i.sheet}) in {hit}"
        if v is not None:
            managed.append(line + f" [T2 {v}]")
        else:
            unmanaged.append(line)
    return sorted(unmanaged), sorted(managed)


@dataclass(frozen=True)
class Term:
    kind: str
    sheet: str
    subject: str
    target_raw: str
    bound: float | None
    basis: str
    enforced: bool
    output_roles: tuple[str, ...] = ()
    out_refs: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        return self.target_raw.split(".", 1)[0]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.subject, self.target_raw)


@dataclass(frozen=True)
class TermIndex:
    hard: tuple[Term, ...]
    soft: tuple[Term, ...]
    na: tuple[Term, ...] = ()

    @property
    def terms(self) -> tuple[Term, ...]:
        return self.hard + self.soft


def build_term_index(sheet_names: list[str] | None = None) -> TermIndex:
    from schgen.verify.placement_contract_gate import (
        _WIRED_SHEETS,
        _board_refs_by_sheet,
        discover_contract,
    )
    if sheet_names is None:
        from schgen.core.link import all_subsystem_paths
        sheet_names = [p.stem for p in all_subsystem_paths()]

    merged: dict[tuple[str, str, str], Term] = {}

    def _add(t: Term) -> None:
        old = merged.get(t.key)
        if old is None:
            merged[t.key] = t
            return
        bound = old.bound
        if t.bound is not None and (bound is None or t.bound < bound):
            bound = t.bound
        merged[t.key] = Term(
            kind=old.kind, sheet=old.sheet, subject=old.subject,
            target_raw=old.target_raw, bound=bound, basis=old.basis,
            enforced=old.enforced or t.enforced,
            output_roles=old.output_roles or t.output_roles,
            out_refs=old.out_refs or t.out_refs)

    for sheet in sorted(set(sheet_names)):
        contract = discover_contract(sheet)
        if contract is None:
            continue
        ext = contract.get("external") or {}
        unknown = set(ext) - _KNOWN_EXTERNAL_KEYS
        if unknown:
            raise ValueError(
                f"placement contract {sheet!r}: unsupported external term "
                f"kind(s) {sorted(unknown)} — floorplan_compose has no "
                f"engine for them (region_void et al. are separate units); "
                f"refusing to build a term index that silently drops terms")
        enforced = sheet in _WIRED_SHEETS
        basis_default = contract.get("contract", "?")

        flow = list(ext.get("flow", []))
        for a, b in zip(flow, flow[1:], strict=False):
            _add(Term(kind="flow_hop", sheet=sheet, subject=a, target_raw=b,
                      bound=None, basis=f"flow chain [{basis_default}]",
                      enforced=enforced))
        for near in ext.get("near_max", []):
            _add(Term(kind="near_max", sheet=sheet, subject=sheet,
                      target_raw=str(near.get("other", "?")),
                      bound=float(near.get("max_mm", 0.0)),
                      basis=str(near.get("basis", "")), enforced=enforced))
        for far in ext.get("far", []):
            _add(Term(kind="far_min", sheet=sheet, subject=sheet,
                      target_raw=str(far.get("what", "?")),
                      bound=float(far.get("min_mm", 0.0)),
                      basis=str(far.get("basis", "")), enforced=enforced))
        downstream = ext.get("downstream")
        output_roles = tuple(ext.get("output_roles", []))
        if downstream and output_roles:
            roles = contract.get("roles", {})
            out_libs = sorted(r for r, v in roles.items() if v in output_roles)
            ref_map = _board_refs_by_sheet(sheet)
            out_refs = tuple(ref_map[r] for r in out_libs if r in ref_map)
            _add(Term(kind="facing", sheet=sheet, subject=sheet,
                      target_raw=str(downstream), bound=None,
                      basis=f"facing/output_roles [{basis_default}]",
                      enforced=enforced, output_roles=output_roles,
                      out_refs=out_refs))

    from schgen.generate.floorplan import load_floorplan_spec
    spec = load_floorplan_spec()
    if spec is not None:
        near_max_pairs = {(t.subject, t.target)
                          for t in merged.values() if t.kind == "near_max"}
        for name in sorted(spec.interior):
            anchor = spec.interior[name]
            tgt = anchor.get("near")
            if tgt and (name, tgt) not in near_max_pairs:
                _add(Term(kind="near_intent", sheet=name, subject=name,
                          target_raw=str(tgt), bound=None,
                          basis="carrier/floorplan.json near-intent (advisory)",
                          enforced=False))

    zones_known = frozenset(sheet_names)

    def _is_na(t: Term) -> bool:
        return any(n != _SOM_TOKEN and n not in zones_known
                   for n in (t.subject, t.target))

    terms = [merged[k] for k in sorted(merged)]
    hard = tuple(t for t in terms if t.enforced and not _is_na(t))
    soft = tuple(t for t in terms if not t.enforced and not _is_na(t))
    na = tuple(t for t in terms if _is_na(t))
    return TermIndex(hard=hard, soft=soft, na=na)


def emit_mobile_sheets(zg, l4_exempt: frozenset[str] | None = None
                       ) -> dict[str, frozenset[str]]:
    if l4_exempt is None:
        from schgen.verify.placement_contract_gate import (
            wired_term_participants,
        )
        l4_exempt, _ = wired_term_participants()
    mobile: dict[str, set[str]] = {}
    for sheet in sorted(set(zg.top_off) | set(zg.bot_off)):
        if sheet in l4_exempt:
            continue
        movers = [r for r in zg.bot_off.get(sheet, {})
                  if zg.side_of.get(r) == "bottom"
                  and r[:1] in ("R", "C", "L")
                  and not r.startswith(("RJ", "LED"))]
        if len(movers) >= 2:
            mobile.setdefault(sheet, set()).add("l4")
    sheet_of = {ref: sheet for sheet, refs in zg.refs_by_sheet.items()
                for ref in refs}
    for ref in zg.conn_edge:
        s = sheet_of.get(ref)
        if s is not None:
            mobile.setdefault(s, set()).add("snap")
    from schgen.verify.placement_contract_gate import load_contract
    for sheet in sorted(set(zg.top_off) | set(zg.bot_off)):
        c = load_contract(sheet)
        ds = ((c or {}).get("external") or {}).get("downstream")
        if not ds:
            continue
        if any(r in zg.conn_rot for r in zg.refs_by_sheet.get(sheet, [])):
            continue
        mobile.setdefault(sheet, set()).add("refit")
    return {s: frozenset(v) for s, v in sorted(mobile.items())}


def wired_term_sheets(index: TermIndex) -> set[str]:
    out: set[str] = set()
    for t in index.hard:
        out.add(t.subject)
        if t.target != _SOM_TOKEN and not t.target.startswith("som_j"):
            out.add(t.target)
    return out


@dataclass(frozen=True)
class LocalMetrics:
    offsets: tuple[tuple[str, float, float], ...]
    pad_union: tuple[tuple[str, float, float, float, float], ...]
    zone_wh: tuple[float, float]

    @property
    def n_parts(self) -> int:
        return len(self.offsets)


def _local_metrics_one(zg, t_off: dict, b_off: dict, extra_rot: dict,
                       zone_wh: tuple[float, float],
                       mods: dict | None = None) -> LocalMetrics:
    from schgen.verify.placement_contract_gate import _pad_boxes
    offs: list[tuple[str, float, float]] = []
    pads: list[tuple[str, float, float, float, float]] = []
    both = dict(t_off)
    both.update(b_off)
    for ref in sorted(both):
        dx, dy = both[ref]
        offs.append((ref, dx, dy))
        mod = (mods or {}).get(ref) or zg.resolvable.get(ref)
        if mod is None:
            continue
        rot = (zg.conn_rot.get(ref, 0.0) + extra_rot.get(ref, 0.0)) % 360.0
        boxes = _pad_boxes(mod, rot)
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes.values()) + dx
        y0 = min(b[1] for b in boxes.values()) + dy
        x1 = max(b[2] for b in boxes.values()) + dx
        y1 = max(b[3] for b in boxes.values()) + dy
        pads.append((ref, x0, y0, x1, y1))
    return LocalMetrics(offsets=tuple(offs), pad_union=tuple(pads),
                        zone_wh=zone_wh)


def zone_local_metrics(zg=None) -> dict[str, LocalMetrics]:
    if zg is None:
        from schgen.generate import pcb as _pcb
        zg = _pcb.subsystem_zone_geometry(two_side=True)

    out: dict[str, LocalMetrics] = {}
    for sheet in sorted(set(zg.top_off) | set(zg.bot_off)):
        out[sheet] = _local_metrics_one(
            zg, zg.top_off.get(sheet, {}), zg.bot_off.get(sheet, {}),
            zg.zone_extra_rot, zg.zone_box.get(sheet, (0.0, 0.0)))
    return out


def zone_shape_metrics(zg) -> dict[tuple[str, int], LocalMetrics]:
    out: dict[tuple[str, int], LocalMetrics] = {}
    for sheet in sorted(zg.shapes):
        for k, shp in enumerate(zg.shapes[sheet]):
            if k == 0:
                continue
            out[(sheet, k)] = _local_metrics_one(
                zg, shp.top_off, shp.bot_off, shp.extra_rot, (shp.w, shp.h),
                mods=shp.mirror)
    return out


@dataclass(frozen=True)
class TermEval:
    term: Term
    measured: float
    bound: float
    margin: float
    ok: bool
    note: str = ""

    def line(self) -> str:
        t = self.term
        flag = "HARD" if t.enforced else "soft"
        state = "ok" if self.ok else "RED"
        return (f"{flag} {t.kind} {t.subject}->{t.target_raw}: "
                f"{self.measured:.2f} vs {self.bound:.2f} "
                f"(margin {self.margin:+.2f}) {state} [{t.basis}]"
                + (f" {self.note}" if self.note else ""))


def _emitted_zone_frame(pose: tuple[float, float]) -> tuple[float, float]:
    return pose


def predicted_centroid_py(pose: tuple[float, float], m: LocalMetrics,
                          refs: set[str] | None = None
                          ) -> tuple[float, float] | None:
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    xs: list[float] = []
    ys: list[float] = []
    for ref, dx, dy in m.offsets:
        if refs is not None and ref not in refs:
            continue
        xs.append(round(ORIGIN_X + gzx + dx, 4))
        ys.append(round(ORIGIN_Y + gzy + dy, 4))
    if not xs:
        return None
    return (round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4))


def predicted_centroid(pose: tuple[float, float], m: LocalMetrics,
                       refs: set[str] | None = None
                       ) -> tuple[float, float] | None:
    if not _nat.loaded():
        raise RuntimeError("native predicted_centroid required")
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    allow = None if refs is None else list(refs)
    got = _nat.module().predicted_centroid(
        gzx, gzy, ORIGIN_X, ORIGIN_Y, list(m.offsets), allow)
    if _nat.trace():
        ref = predicted_centroid_py(pose, m, refs)
        if got != ref:
            raise AssertionError(
                "native predicted_centroid DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def predicted_bbox_py(pose: tuple[float, float], m: LocalMetrics
                      ) -> tuple[float, float, float, float] | None:
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    a: list[float] | None = None
    off = {ref: (dx, dy) for ref, dx, dy in m.offsets}
    for ref, x0, y0, x1, y1 in m.pad_union:
        dx, dy = off[ref]
        px = round(ORIGIN_X + gzx + dx, 4)
        py = round(ORIGIN_Y + gzy + dy, 4)
        b = (px + (x0 - dx), py + (y0 - dy), px + (x1 - dx), py + (y1 - dy))
        if a is None:
            a = list(b)
        else:
            a[0] = min(a[0], b[0])
            a[1] = min(a[1], b[1])
            a[2] = max(a[2], b[2])
            a[3] = max(a[3], b[3])
    if a is None:
        return None
    return (round(a[0], 4), round(a[1], 4), round(a[2], 4), round(a[3], 4))


def predicted_bbox(pose: tuple[float, float], m: LocalMetrics
                   ) -> tuple[float, float, float, float] | None:
    if not _nat.loaded():
        raise RuntimeError("native predicted_bbox required")
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    got = _nat.module().predicted_bbox(
        gzx, gzy, ORIGIN_X, ORIGIN_Y, list(m.offsets), list(m.pad_union))
    if _nat.trace():
        ref = predicted_bbox_py(pose, m)
        if got != ref:
            raise AssertionError(
                "native predicted_bbox DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def evaluate_terms_py(board_w: float, board_h: float,
                      som_core: tuple[float, float, float, float] | None,
                      poses: dict[str, tuple[float, float]],
                      metrics: dict[str, LocalMetrics],
                      index: TermIndex,
                      far_guard: dict[str, float] | None = None,
                      som_j_rects: dict[str, tuple[float, float, float, float]]
                      | None = None) -> list[TermEval]:
    from schgen.verify.placement_flow_gate import (
        bbox_gap,
        facing_dot,
        flow_budget,
    )
    if far_guard is None:
        far_guard = FAR_L4_GUARD_MM

    budget = flow_budget(board_w, board_h, som_core)

    def centroid_of(name: str) -> tuple[float, float] | None:
        if name == _SOM_TOKEN:
            if som_core is None:
                return None
            x0, y0, x1, y1 = som_core
            return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))
        if name.startswith("som_j"):
            r = (som_j_rects or {}).get(name)
            if r is None:
                return None
            from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
            return (round((r[0] + r[2]) / 2.0 + ORIGIN_X, 4),
                    round((r[1] + r[3]) / 2.0 + ORIGIN_Y, 4))
        if name not in poses or name not in metrics:
            return None
        return predicted_centroid(poses[name], metrics[name])

    def bbox_of(name: str) -> tuple[float, float, float, float] | None:
        if name == _SOM_TOKEN:
            return som_core
        if name.startswith("som_j"):
            r = (som_j_rects or {}).get(name)
            if r is None:
                return None
            from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
            return (r[0] + ORIGIN_X, r[1] + ORIGIN_Y,
                    r[2] + ORIGIN_X, r[3] + ORIGIN_Y)
        if name not in poses or name not in metrics:
            return None
        return predicted_bbox(poses[name], metrics[name])

    out: list[TermEval] = []
    for t in index.terms:
        if t.kind == "flow_hop":
            ca = centroid_of(t.subject)
            cb = centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, round(budget, 4), -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            g = (far_guard.get(t.subject, 0.0) + far_guard.get(t.target, 0.0))
            eff = budget - g
            note = f"incl L4 guard {g:g}mm" if g else ""
            out.append(TermEval(t, d, round(eff, 4),
                                round(eff - d, 4), d <= eff, note))
        elif t.kind in ("near_max", "near_intent"):
            ba = bbox_of(t.subject)
            bb = bbox_of(t.target)
            if ba is None or bb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    t.kind == "near_intent", "UNRESOLVED"))
                continue
            g = bbox_gap(ba, bb)
            if t.kind == "near_intent":
                out.append(TermEval(t, g, 0.0, 0.0, True, "advisory"))
            else:
                out.append(TermEval(t, g, t.bound or 0.0,
                                    round((t.bound or 0.0) - g, 4),
                                    g <= (t.bound or 0.0)))
        elif t.kind == "far_min":
            ca = centroid_of(t.subject)
            cb = centroid_of(t.target)
            guard = max(far_guard.get(t.subject, 0.0),
                        far_guard.get(t.target, 0.0))
            bound = (t.bound or 0.0) + guard
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, bound, -math.inf, False,
                                    "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            note = f"incl FAR_L4_GUARD {guard:g}mm" if guard else ""
            out.append(TermEval(t, d, bound, round(d - bound, 4),
                                d >= bound, note))
        elif t.kind == "facing":
            czone = centroid_of(t.subject)
            cout = (predicted_centroid(poses[t.subject], metrics[t.subject],
                                       refs=set(t.out_refs))
                    if t.subject in poses and t.subject in metrics else None)
            cdown = centroid_of(t.target)
            if czone is None or cout is None or cdown is None:
                out.append(TermEval(t, 180.0, 90.0, -90.0, False,
                                    "UNRESOLVED"))
                continue
            dot, angle = facing_dot(czone, cout, cdown)
            if far_guard.get(t.subject) or far_guard.get(t.target):
                out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                    True,
                                    f"dot={dot:+.2f} L4-guarded participant "
                                    f"- gate-arbitrated"))
            else:
                out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                    dot > 0.0, f"dot={dot:+.2f}"))
        else:
            raise ValueError(f"unknown term kind {t.kind!r}")
    return out


def evaluate_terms(board_w: float, board_h: float,
                   som_core: tuple[float, float, float, float] | None,
                   poses: dict[str, tuple[float, float]],
                   metrics: dict[str, LocalMetrics],
                   index: TermIndex,
                   far_guard: dict[str, float] | None = None,
                   som_j_rects: dict[str, tuple[float, float, float, float]]
                   | None = None) -> list[TermEval]:
    if far_guard is None:
        far_guard = FAR_L4_GUARD_MM
    if not _nat.loaded():
        raise RuntimeError("native evaluate_terms required")
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    term_rows = [
        (t.kind, t.subject, t.target, t.bound, list(t.out_refs))
        for t in index.terms]
    metric_rows = [
        (name, list(m.offsets), list(m.pad_union))
        for name, m in metrics.items()]
    pose_rows = list(poses.items())
    jack_rows = list((som_j_rects or {}).items())
    guard_rows = list(far_guard.items())
    rows = _nat.module().evaluate_terms(
        board_w, board_h, som_core, pose_rows, metric_rows, term_rows,
        guard_rows, jack_rows, ORIGIN_X, ORIGIN_Y)
    got = [TermEval(t, measured, bound, margin, ok, note)
           for t, (measured, bound, margin, ok, note)
           in zip(index.terms, rows, strict=True)]
    if _nat.trace():
        ref = evaluate_terms_py(
            board_w, board_h, som_core, poses, metrics, index, far_guard,
            som_j_rects)
        got_t = [(e.term.key, e.measured, e.bound, e.margin, e.ok, e.note)
                 for e in got]
        ref_t = [(e.term.key, e.measured, e.bound, e.margin, e.ok, e.note)
                 for e in ref]
        if got_t != ref_t:
            raise AssertionError(
                f"native evaluate_terms DIVERGENCE: cpp={got_t} "
                f"python={ref_t}")
    return got


def measure_terms(model, index: TermIndex | None = None) -> list[TermEval]:
    from schgen.verify.placement_contract_gate import _board_refs_by_sheet
    from schgen.verify.placement_flow_gate import (
        _members_centroid,
        bbox_gap,
        facing_dot,
        flow_budget,
        zone_bboxes,
        zone_centroids,
    )
    if index is None:
        index = build_term_index(
            sorted({i.sheet for i in model.insts}))
    centroids = zone_centroids(model)
    bboxes = zone_bboxes(model)
    budget = flow_budget(model.board_w, model.board_h, model.som_core)

    def centroid_of(name: str) -> tuple[float, float] | None:
        if name == _SOM_TOKEN:
            if model.som_core is None:
                return None
            x0, y0, x1, y1 = model.som_core
            return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))
        return centroids.get(name)

    def bbox_of(name: str) -> tuple[float, float, float, float] | None:
        if name == _SOM_TOKEN:
            return model.som_core
        return bboxes.get(name)

    out: list[TermEval] = []
    for t in index.terms:
        if t.kind == "flow_hop":
            ca, cb = centroid_of(t.subject), centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, round(budget, 4), -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            out.append(TermEval(t, d, round(budget, 4),
                                round(budget - d, 4), d <= budget))
        elif t.kind in ("near_max", "near_intent"):
            ba, bb = bbox_of(t.subject), bbox_of(t.target)
            if ba is None or bb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    t.kind == "near_intent", "UNRESOLVED"))
                continue
            g = bbox_gap(ba, bb)
            if t.kind == "near_intent":
                out.append(TermEval(t, g, 0.0, 0.0, True, "advisory"))
            else:
                out.append(TermEval(t, g, t.bound or 0.0,
                                    round((t.bound or 0.0) - g, 4),
                                    g <= (t.bound or 0.0)))
        elif t.kind == "far_min":
            ca, cb = centroid_of(t.subject), centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            out.append(TermEval(t, d, t.bound or 0.0,
                                round(d - (t.bound or 0.0), 4),
                                d >= (t.bound or 0.0)))
        elif t.kind == "facing":
            czone = centroid_of(t.subject)
            cdown = centroid_of(t.target)
            ref_map = _board_refs_by_sheet(t.subject)
            brefs = set(t.out_refs) or {
                ref_map[r] for r in t.output_roles if r in ref_map}
            cout = _members_centroid(model, t.subject, brefs)
            if czone is None or cout is None or cdown is None:
                out.append(TermEval(t, 180.0, 90.0, -90.0, False,
                                    "UNRESOLVED"))
                continue
            dot, angle = facing_dot(czone, cout, cdown)
            out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                dot > 0.0, f"dot={dot:+.2f}"))
    return out


def cross_airwires_by_pair(model, npp: dict | None = None,
                           mst: dict | None = None
                           ) -> dict[tuple[str, str], tuple[int, float]]:
    from schgen.generate.pcb import net_pad_positions
    from schgen.generate.ratsnest import net_mst_edges
    pairs: dict[tuple[str, str], list[float]] = {}
    if npp is None:
        npp = net_pad_positions(model)
    if mst is None:
        mst = net_mst_edges(model, npp)
    for _net, pts in sorted(npp.items()):
        for a, b in mst[_net]:
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            if sa == sb:
                continue
            key = (sa, sb) if sa < sb else (sb, sa)
            pairs.setdefault(key, []).append(math.hypot(xa - xb, ya - yb))
    return {k: (len(v), round(sum(v), 1)) for k, v in sorted(pairs.items())}


def channel_demand_mm_py(n_airwires: int) -> float:
    if n_airwires < CHANNEL_MIN_NETS:
        return 0.0
    return CHANNEL_FLOOR_MM + CHANNEL_PER_NET_MM * n_airwires


def channel_demand_mm(n_airwires: int) -> float:
    if not _nat.loaded():
        raise RuntimeError("native channel_demand_mm required")
    got = _nat.module().channel_demand_mm(
        n_airwires, CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM,
        CHANNEL_PER_NET_MM)
    if _nat.trace():
        ref = channel_demand_mm_py(n_airwires)
        if got != ref:
            raise AssertionError(
                "native channel_demand_mm DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def compose_report(model, index: TermIndex | None = None,
                   npp: dict | None = None, mst: dict | None = None) -> str:
    if index is None:
        index = build_term_index(sorted({i.sheet for i in model.insts}))
    evals = measure_terms(model, index)
    hard = [e for e in evals if e.term.enforced]
    soft = [e for e in evals if not e.term.enforced]
    n_red_hard = sum(1 for e in hard if not e.ok)
    n_red_soft = sum(1 for e in soft if not e.ok)
    finite = [e.margin for e in hard if math.isfinite(e.margin)]
    agg = round(sum(finite), 2) if finite else 0.0
    mn = round(min(finite), 2) if finite else 0.0
    L = [f"FLOORPLAN COMPOSITION (T1): {len(index.hard)} hard / "
         f"{len(index.soft)} soft terms; hard RED {n_red_hard}, "
         f"soft RED {n_red_soft} (advisory)",
         f"  aggregate hard margin: sum {agg} mm, min {mn} mm "
         f"(informational)"]
    L.append("  hard terms:")
    for e in sorted(hard, key=lambda e: e.term.key):
        L.append("    " + e.line())
    L.append("  soft terms (advisory ledger — repair triggers, never gates):")
    for e in sorted(soft, key=lambda e: e.term.key):
        L.append("    " + e.line())
    if index.na:
        L.append("  n/a terms (endpoint subsystem not instantiated by this "
                 "project — project-scoped resolution):")
        for t in sorted(index.na, key=lambda t: t.key):
            L.append(f"    n/a {t.kind} {t.subject}->{t.target_raw} "
                     f"[{t.basis}]")
    unmanaged, managed = corridor_intrusions(model)
    ncorr = len(escape_corridors())
    L.append(f"  T2 escape corridors (D13 never-close): {ncorr} loaded, "
             f"{len(unmanaged)} UNMANAGED part intrusion(s), "
             f"{len(managed)} T2-coexistence-managed")
    for x in unmanaged:
        L.append(f"    UNMANAGED INTRUSION {x}")
    for x in managed:
        L.append(f"    managed {x}")
    ch = [(k, v) for k, v in cross_airwires_by_pair(model, npp, mst).items()
          if channel_demand_mm(v[0]) > 0.0
          and not (k[0].startswith("som_j") or k[1].startswith("som_j"))]
    L.append(f"  D13 channel hotspots (>= {CHANNEL_MIN_NETS} cross-airwires; "
             f"corridor = {CHANNEL_FLOOR_MM:g} + {CHANNEL_PER_NET_MM:g}/net mm):")
    for (a, b), (n, mm) in sorted(ch, key=lambda kv: (-kv[1][0], kv[0])):
        L.append(f"    {a} | {b}: {n} airwires ({mm:.1f} mm) -> "
                 f"corridor >= {channel_demand_mm(n):.1f} mm")
    return "\n".join(L)


@dataclass
class LegalizeVar:
    name: str
    w: float
    h: float
    seed: tuple[float, float]
    x: float
    y: float


@dataclass
class _Sep:
    axis: str
    lo: str
    hi: str
    gap: float
    basis: str
    flippable: bool


def _pair_axis_py(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> tuple[str, bool]:
    gx = max(b[0] - a[2], a[0] - b[2])
    gy = max(b[1] - a[3], a[1] - b[3])
    nx = gx / max(1.0, ((a[2] - a[0]) + (b[2] - b[0])) / 2.0)
    ny = gy / max(1.0, ((a[3] - a[1]) + (b[3] - b[1])) / 2.0)
    if nx >= ny:
        return "x", a[0] <= b[0]
    return "y", a[1] <= b[1]


def _pair_axis(a: tuple[float, float, float, float],
               b: tuple[float, float, float, float]) -> tuple[str, bool]:
    if not _nat.loaded():
        raise RuntimeError("native pair_axis required")
    got = _nat.module().pair_axis(a, b)
    if _nat.trace():
        ref = _pair_axis_py(a, b)
        if got != ref:
            raise AssertionError(
                f"native pair_axis DIVERGENCE: cpp={got} python={ref}")
    return got


def channel_gap_mm_py(a: str, b: str, demand: dict[frozenset, int],
                      near_max_pairs: set[frozenset], clear: float
                      ) -> tuple[float, str]:
    key = frozenset((a, b))
    if key in near_max_pairs:
        return clear, "near_max-adjacency(terminus)"
    ch = channel_demand_mm(demand.get(key, 0))
    if ch > clear:
        return ch, f"D13-channel({demand.get(key, 0)} nets)"
    return clear, "CLEAR"


def channel_gap_mm(a: str, b: str, demand: dict[frozenset, int],
                   near_max_pairs: set[frozenset], clear: float
                   ) -> tuple[float, str]:
    key = frozenset((a, b))
    if not _nat.loaded():
        raise RuntimeError("native channel_gap_mm required")
    got = _nat.module().channel_gap_mm(
        key in near_max_pairs, demand.get(key, 0), clear,
        CHANNEL_MIN_NETS, CHANNEL_FLOOR_MM, CHANNEL_PER_NET_MM)
    if _nat.trace():
        ref = channel_gap_mm_py(a, b, demand, near_max_pairs, clear)
        if got != ref:
            raise AssertionError(
                f"native channel_gap_mm DIVERGENCE: cpp={got} python={ref}")
    return got


def _bellman_ford_py(nodes: list[str],
                     edges: list[tuple[str, str, float, object]]
                     ) -> tuple[dict[str, float] | None, list[object]]:
    dist = dict.fromkeys(nodes, 0.0)
    pred: dict[str, tuple[str, object]] = {}
    V = len(nodes)
    last = None
    for _sweep in range(V):
        relaxed = False
        for u, v, c, tag in edges:
            if dist[u] + c < dist[v] - 1e-12:
                dist[v] = dist[u] + c
                pred[v] = (u, tag)
                relaxed = True
                last = v
        if not relaxed:
            return dist, []
    node = last
    for _ in range(V):
        node = pred[node][0]
    tags: list[object] = []
    start = node
    while True:
        u, tag = pred[node]
        tags.append(tag)
        node = u
        if node == start or len(tags) > V + 1:
            break
    return None, tags


def _bellman_ford(nodes: list[str],
                  edges: list[tuple[str, str, float, object]]
                  ) -> tuple[dict[str, float] | None, list[object]]:
    if not _nat.loaded():
        raise RuntimeError("native bellman_ford required")
    index = {name: i for i, name in enumerate(nodes)}
    src = [index[u] for u, _v, _c, _tag in edges]
    dst = [index[v] for _u, v, _c, _tag in edges]
    cost = [c for _u, _v, c, _tag in edges]
    ok, dist, cycle = _nat.module().bellman_ford(len(nodes), src, dst, cost)
    if ok:
        got: tuple[dict[str, float] | None, list[object]] = (
            {name: dist[i] for i, name in enumerate(nodes)}, [])
    else:
        got = (None, [edges[i][3] for i in cycle])
    if _nat.trace():
        ref = _bellman_ford_py(nodes, edges)
        if got != ref:
            raise AssertionError(
                f"native bellman_ford DIVERGENCE: cpp={got} python={ref}")
    return got


def legalize_compact(board_w: float, board_h: float,
                     som_core_page: tuple[float, float, float, float],
                     fixed_rects: list[tuple[str, float, float, float, float]],
                     movable: list[LegalizeVar],
                     index: TermIndex,
                     metrics: dict[str, LocalMetrics],
                     fixed_poses: dict[str, tuple[float, float]],
                     channel_demand: dict[frozenset, int],
                     clear: float,
                     compact: bool = False,
                     log: list[str] | None = None,
                     som_j_rects: dict[str, tuple[float, float, float, float]]
                     | None = None) -> bool:
    if som_j_rects:
        fixed_poses = {**fixed_poses,
                       **{n: (r[0], r[1]) for n, r in som_j_rects.items()}}
    if log is None:
        log = []
    hard = [t for t in index.hard]
    if not hard or not movable:
        return True
    names = sorted(v.name for v in movable)
    by_name = {v.name: v for v in movable}
    vset = set(names)

    def hull(sheet: str) -> tuple[float, float, float, float] | None:
        m = metrics.get(sheet)
        if m is None or not m.pad_union:
            return None
        if not _nat.loaded():
            raise RuntimeError("native pad_union_hull required")
        return _nat.module().pad_union_hull(list(m.pad_union))

    def cent_off(sheet: str) -> tuple[float, float]:
        m = metrics.get(sheet)
        if m is None or not m.offsets:
            v = by_name.get(sheet)
            return (v.w / 2, v.h / 2) if v else (0.0, 0.0)
        if not _nat.loaded():
            raise RuntimeError("native centroid_offset required")
        return _nat.module().centroid_offset(list(m.offsets), 0.0, 0.0)

    near_pairs = {frozenset((t.subject, t.target))
                  for t in hard if t.kind == "near_max"}
    frect = {fn: (x0, y0, x1, y1) for fn, x0, y0, x1, y1 in fixed_rects}

    seps: list[_Sep] = []
    seed_rect = {v.name: (v.x, v.y, v.x + v.w, v.y + v.h) for v in movable}

    def _build_seps_py() -> list[_Sep]:
        built: list[_Sep] = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                axis, first = _pair_axis(seed_rect[a], seed_rect[b])
                gap, why = channel_gap_mm(a, b, channel_demand, near_pairs,
                                          clear)
                lo, hi = (a, b) if first else (b, a)
                built.append(_Sep(axis, lo, hi, gap, why, True))
            for fn in sorted(frect):
                axis, first = _pair_axis(seed_rect[a], frect[fn])
                gap, why = channel_gap_mm(a, fn, channel_demand, near_pairs,
                                          clear)
                lo, hi = (a, f"#{fn}") if first else (f"#{fn}", a)
                built.append(_Sep(axis, lo, hi, gap, why, True))
        return built

    if not _nat.loaded():
        raise RuntimeError("native build_seps_py required")
    demand_rows = [(a, b, n) for key, n in channel_demand.items()
                   for a, b in [tuple(key) if len(key) == 2
                                else (next(iter(key)), next(iter(key)))]]
    near_rows = [(a, b) for key in near_pairs
                 for a, b in [tuple(key) if len(key) == 2
                              else (next(iter(key)), next(iter(key)))]]
    rows = _nat.module().legalize_build_seps(
        names, [seed_rect[n] for n in names],
        list(frect.keys()), [frect[n] for n in frect],
        demand_rows, near_rows, clear, CHANNEL_MIN_NETS,
        CHANNEL_FLOOR_MM, CHANNEL_PER_NET_MM)
    seps = [_Sep(axis, lo, hi, gap, why, flip)
            for axis, lo, hi, gap, why, flip in rows]
    if _nat.trace():
        ref = _build_seps_py()
        got_t = [(s.axis, s.lo, s.hi, s.gap, s.basis, s.flippable)
                 for s in seps]
        ref_t = [(s.axis, s.lo, s.hi, s.gap, s.basis, s.flippable)
                 for s in ref]
        if got_t != ref_t:
            raise AssertionError(
                f"native legalize_build_seps DIVERGENCE: "
                f"cpp={got_t} python={ref_t}")
    def build_edges_py(axis: str) -> list[tuple[str, str, float, object]]:
        E: list[tuple[str, str, float, object]] = []
        for n in names:
            v = by_name[n]
            w = v.w if axis == "x" else v.h
            span = board_w if axis == "x" else board_h
            E.append(("#0", n, span - clear - w, ("wall-hi", n)))
            E.append((n, "#0", -clear, ("wall-lo", n)))
        for s in seps:
            if s.axis != axis:
                continue
            lo_f, hi_f = s.lo.startswith("#"), s.hi.startswith("#")
            if lo_f and hi_f:
                continue
            i0, i2 = (0, 2) if axis == "x" else (1, 3)
            if lo_f:
                r = frect[s.lo[1:]]
                E.append((s.hi, "#0", -(r[i2] + s.gap), ("sep", s)))
            elif hi_f:
                r = frect[s.hi[1:]]
                v = by_name[s.lo]
                w = v.w if axis == "x" else v.h
                E.append(("#0", s.lo, r[i0] - s.gap - w, ("sep", s)))
            else:
                v = by_name[s.lo]
                w = v.w if axis == "x" else v.h
                E.append((s.hi, s.lo, -(w + s.gap), ("sep", s)))
        for t in hard:
            if t.kind != "near_max":
                continue
            for e in _near_max_edges(t, axis):
                E.append(e)
        return E

    def _edge_key(e: tuple) -> tuple:
        src, dst, cost, tag = e
        if isinstance(tag, tuple) and tag[0] == "sep":
            return (src, dst, cost, "sep", tag[1].lo, tag[1].hi, tag[1].axis)
        if isinstance(tag, tuple) and tag[0] in ("near_max", "near_max-perp"):
            return (src, dst, cost, tag[0], tag[1].subject, tag[1].target)
        if isinstance(tag, tuple):
            return (src, dst, cost, tag[0], tag[1])
        return (src, dst, cost, str(tag))

    def build_edges(axis: str) -> list[tuple[str, str, float, object]]:
        if not _nat.loaded():
            raise RuntimeError("native wall_sep_edges required")
        span = board_w if axis == "x" else board_h
        sizes = [by_name[n].w if axis == "x" else by_name[n].h for n in names]
        sep_in = [(s.axis == "x", s.lo, s.hi, s.gap) for s in seps]
        frects = [(fn, r) for fn, r in frect.items()]
        rows = _nat.module().wall_sep_edges(
            axis == "x", names, sizes, span, clear, sep_in, frects)
        E: list[tuple[str, str, float, object]] = []
        for src, dst, cost, kind, sep_i, wall_n in rows:
            if kind == "sep":
                E.append((src, dst, cost, ("sep", seps[sep_i])))
            else:
                E.append((src, dst, cost, (kind, wall_n)))
        for t in hard:
            if t.kind != "near_max":
                continue
            E.extend(_near_max_edges(t, axis))
        if _nat.trace():
            ref = build_edges_py(axis)
            if [_edge_key(e) for e in E] != [_edge_key(e) for e in ref]:
                raise AssertionError(
                    "native wall_sep_edges DIVERGENCE: "
                    f"cpp={[ _edge_key(e) for e in E]} "
                    f"python={[ _edge_key(e) for e in ref]}")
        return E

    def _near_max_edges_py(t: Term, axis: str
                           ) -> list[tuple[str, str, float, object]]:
        s, g = t.subject, t.target
        _jr = (som_j_rects or {}).get(g) if g.startswith("som_j") else None
        hs, hg = hull(s), (hull(g) if _jr is None
                           else (0.0, 0.0, _jr[2] - _jr[0], _jr[3] - _jr[1]))
        bound = (t.bound or 0.0) - GUARD_MM
        if hs is None or hg is None or bound < 0 \
                or (s not in vset and g not in vset):
            return []
        sr = (seed_rect[s] if s in vset
              else _abs(fixed_poses[s], hs))
        gr = (_jr if _jr is not None
              else seed_rect[g] if g in vset
              else _abs(fixed_poses[g], hg))
        dom, s_first = _pair_axis(sr, gr)
        lo, hi = (s, g) if s_first else (g, s)
        hlo, hhi = (hs, hg) if s_first else (hg, hs)
        out: list[tuple[str, str, float, object]] = []
        i0, i2 = (0, 2) if dom == "x" else (1, 3)
        if axis == dom:
            c = bound + hlo[i2] - hhi[i0]
            if lo in vset and hi in vset:
                out.append((lo, hi, c, ("near_max", t)))
            elif lo in vset:
                f = fixed_poses[hi][0 if dom == "x" else 1]
                out.append((lo, "#0", -(f + hhi[i0] - bound - hlo[i2]),
                            ("near_max", t)))
            else:
                f = fixed_poses[lo][0 if dom == "x" else 1]
                out.append(("#0", hi, f + hlo[i2] + bound - hhi[i0],
                            ("near_max", t)))
        else:
            j0, j2 = (1, 3) if dom == "x" else (0, 2)
            k = 1 if dom == "x" else 0
            a0, a2 = hs[j0], hs[j2]
            b0, b2 = hg[j0], hg[j2]
            if s in vset and g in vset:
                out.append((s, g, a2 - b0, ("near_max-perp", t)))
                out.append((g, s, b2 - a0, ("near_max-perp", t)))
            elif s in vset:
                f = fixed_poses[g][k]
                out.append((s, "#0", -(f + b0 - a2), ("near_max-perp", t)))
                out.append(("#0", s, f + b2 - a0, ("near_max-perp", t)))
            else:
                f = fixed_poses[s][k]
                out.append((g, "#0", -(f + a0 - b2), ("near_max-perp", t)))
                out.append(("#0", g, f + a2 - b0, ("near_max-perp", t)))
        return out

    def _near_max_edges(t: Term, axis: str
                        ) -> list[tuple[str, str, float, object]]:
        if not _nat.loaded():
            raise RuntimeError("native near_max_edges required")
        s, g = t.subject, t.target
        _jr = (som_j_rects or {}).get(g) if g.startswith("som_j") else None
        hs, hg = hull(s), (hull(g) if _jr is None
                           else (0.0, 0.0, _jr[2] - _jr[0], _jr[3] - _jr[1]))
        bound = (t.bound or 0.0) - GUARD_MM
        if hs is None or hg is None or bound < 0 \
                or (s not in vset and g not in vset):
            return []
        sr = (seed_rect[s] if s in vset
              else _abs(fixed_poses[s], hs))
        gr = (_jr if _jr is not None
              else seed_rect[g] if g in vset
              else _abs(fixed_poses[g], hg))
        rows = _nat.module().near_max_edges(
            s, g, bound, axis, hs, hg, sr, gr,
            s in vset, g in vset,
            None if s in vset else fixed_poses[s],
            None if g in vset else fixed_poses[g])
        got = [(src, dst, cost, (("near_max-perp" if perp else "near_max"), t))
               for src, dst, cost, perp in rows]
        if _nat.trace():
            ref = _near_max_edges_py(t, axis)
            g2 = [(a, b, c, k[0]) for a, b, c, k in got]
            r2 = [(a, b, c, k[0]) for a, b, c, k in ref]
            if g2 != r2:
                raise AssertionError(
                    "native near_max_edges DIVERGENCE: "
                    f"cpp={g2} python={r2}")
        return got

    def _abs(p: tuple[float, float], h: tuple[float, float, float, float]):
        return (p[0] + h[0], p[1] + h[1], p[0] + h[2], p[1] + h[3])

    def _descend(px: dict[str, float], py: dict[str, float],
                 hops: tuple[Term, ...], seed_only: bool) -> None:
        if not _nat.loaded():
            raise RuntimeError("native descend required")
        from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
        edges_x = [(u, v, c) for u, v, c, _tag in build_edges("x")]
        edges_y = [(u, v, c) for u, v, c, _tag in build_edges("y")]
        hop_pairs = [(t.subject, t.target) for t in hops]
        cents = [(n, cent_off(n)) for n in names]
        cents.extend((fn, cent_off(fn)) for fn in frect)
        mid_x = (som_core_page[0] + som_core_page[2]) / 2 - ORIGIN_X
        mid_y = (som_core_page[1] + som_core_page[3]) / 2 - ORIGIN_Y
        nx, ny = _nat.module().legalize_descend_passes(
            names,
            [px[n] for n in names], [py[n] for n in names],
            [by_name[n].seed[0] for n in names],
            [by_name[n].seed[1] for n in names],
            edges_x, edges_y, hop_pairs, cents,
            list(fixed_poses.items()), mid_x, mid_y, True, seed_only,
            W_HOP, W_SEED, MEDIAN_PASSES)
        if _nat.trace():
            keepx, keepy = dict(px), dict(py)
            _descend_py(keepx, keepy, hops, seed_only)
            gotx = {n: nx[i] for i, n in enumerate(names)}
            goty = {n: ny[i] for i, n in enumerate(names)}
            if gotx != {n: keepx[n] for n in names} \
                    or goty != {n: keepy[n] for n in names}:
                raise AssertionError(
                    f"native legalize_descend DIVERGENCE: "
                    f"cpp={(gotx, goty)} python="
                    f"{({n: keepx[n] for n in names}, {n: keepy[n] for n in names})}")
        for i, n in enumerate(names):
            px[n] = nx[i]
            py[n] = ny[i]

    def _descend_py(px: dict[str, float], py: dict[str, float],
                    hops: tuple[Term, ...], seed_only: bool) -> None:
        for _pass in range(MEDIAN_PASSES):
            moved = 0.0
            for n in names:
                v = by_name[n]
                for axis, pos in (("x", px), ("y", py)):
                    edges = build_edges(axis)
                    if not _nat.loaded():
                        raise RuntimeError("native constraint_bounds required")
                    nodes: list[str] = []
                    index: dict[str, int] = {}
                    src: list[int] = []
                    dst: list[int] = []
                    cost: list[float] = []
                    for u, w2, c, _tag in edges:
                        ui = index.get(u)
                        if ui is None:
                            ui = len(nodes)
                            index[u] = ui
                            nodes.append(u)
                        vi = index.get(w2)
                        if vi is None:
                            vi = len(nodes)
                            index[w2] = vi
                            nodes.append(w2)
                        src.append(ui)
                        dst.append(vi)
                        cost.append(c)
                    if n not in index:
                        index[n] = len(nodes)
                        nodes.append(n)
                    posv = [pos.get(nm, 0.0) for nm in nodes]
                    lo, hi = _nat.module().constraint_bounds(
                        index[n], src, dst, cost, posv)
                    if _nat.trace():
                        rlo, rhi = -math.inf, math.inf
                        for u, w2, c, _tag in edges:
                            if w2 == n and u != n:
                                rhi = min(rhi, pos.get(u, 0.0) + c)
                            if u == n and w2 != n:
                                rlo = max(rlo, pos.get(w2, 0.0) - c)
                        if (lo, hi) != (rlo, rhi):
                            raise AssertionError(
                                "native constraint_bounds DIVERGENCE: "
                                f"cpp={(lo, hi)} python={(rlo, rhi)}")
                    if lo > hi:
                        continue
                    i = 0 if axis == "x" else 1
                    pulls: list[tuple[float, float]] = []
                    if not seed_only:
                        co = cent_off(n)
                        for t in hops:
                            other = (t.target if t.subject == n
                                     else t.subject if t.target == n
                                     else None)
                            if other is None:
                                continue
                            if other in vset:
                                oc = cent_off(other)
                                op = (px[other] if axis == "x"
                                      else py[other])
                                pulls.append((W_HOP, op + oc[i] - co[i]))
                            elif other in fixed_poses:
                                oc = cent_off(other)
                                pulls.append((W_HOP,
                                              fixed_poses[other][i]
                                              + oc[i] - co[i]))
                            elif other == _SOM_TOKEN:
                                mid = (som_core_page[i]
                                       + som_core_page[i + 2]) / 2
                                from schgen.generate.pcb.constants import (
                                    ORIGIN_X,
                                    ORIGIN_Y,
                                )
                                mid -= (ORIGIN_X if axis == "x" else ORIGIN_Y)
                                pulls.append((W_HOP, mid - co[i]))
                    pulls.append((W_SEED if not seed_only else 1.0,
                                  v.seed[i]))
                    best = weighted_median(pulls)
                    q = _q.legalize_pose_quantum(best)
                    q = max(lo, min(q, hi))
                    old = pos[n]
                    if abs(q - old) > 1e-12:
                        pos[n] = q
                        moved = max(moved, abs(q - old))
            if moved <= 1e-9:
                break

    def edges_ok(axis: str, pos: dict[str, float]) -> bool:
        edges = build_edges(axis)
        if not _nat.loaded():
            raise RuntimeError("native constraint_edges_ok required")
        nodes: list[str] = []
        index: dict[str, int] = {}
        src: list[int] = []
        dst: list[int] = []
        cost: list[float] = []
        for u, v, c, _tag in edges:
            ui = index.get(u)
            if ui is None:
                ui = len(nodes)
                index[u] = ui
                nodes.append(u)
            vi = index.get(v)
            if vi is None:
                vi = len(nodes)
                index[v] = vi
                nodes.append(v)
            src.append(ui)
            dst.append(vi)
            cost.append(c)
        posv = [pos.get(n, 0.0) for n in nodes]
        got = _nat.module().constraint_edges_ok(src, dst, cost, posv)
        if _nat.trace():
            ref = True
            for u, v, c, _tag in edges:
                if pos.get(v, 0.0) - pos.get(u, 0.0) > c + 1e-9:
                    ref = False
                    break
            if got is not ref:
                raise AssertionError(
                    "native constraint_edges_ok DIVERGENCE: "
                    f"cpp={got} python={ref}")
        return got

    posx = {n: by_name[n].x for n in names}
    posy = {n: by_name[n].y for n in names}
    posx["#0"] = 0.0
    posy["#0"] = 0.0
    seed_feasible = edges_ok("x", posx) and edges_ok("y", posy)

    def _repair_axis_py(axis: str, pos: dict[str, float]) -> bool:
        for _rep in range(REPAIR_MAX + 1):
            E = build_edges(axis)
            dist, cycle = _bellman_ford(["#0"] + names, E)
            if dist is not None:
                base = dist["#0"]
                for n in names:
                    pos[n] = dist[n] - base
                return True
            flipped = False
            for tag in cycle:
                if isinstance(tag, tuple) and tag[0] == "sep" \
                        and tag[1].flippable:
                    sp = tag[1]
                    seps.remove(sp)
                    seps.append(_Sep("y" if sp.axis == "x" else "x",
                                     sp.lo, sp.hi, sp.gap,
                                     sp.basis + "|flipped", False))
                    log.append(f"repair: flip {sp.lo}|{sp.hi} off "
                               f"{sp.axis}")
                    flipped = True
                    break
            if not flipped:
                log.append(
                    "INFEASIBLE " + axis + ": negative cycle ["
                    + ", ".join(
                        (t[1].lo + "|" + t[1].hi if isinstance(t, tuple)
                         and t[0] == "sep" else str(t))
                        for t in cycle[:6]) + "]")
                return False
        log.append(f"INFEASIBLE {axis}: REPAIR_MAX exhausted")
        return False

    def _repair_axis(axis: str, pos: dict[str, float]) -> bool:
        if not _nat.loaded():
            raise RuntimeError("native legalize_repair_axis required")
        span = board_w if axis == "x" else board_h
        sizes = [by_name[n].w if axis == "x" else by_name[n].h for n in names]
        sep_in = [(s.axis == "x", s.lo, s.hi, s.gap, s.flippable) for s in seps]
        frects = [(fn, r) for fn, r in frect.items()]
        extra = [(u, v, c)
                 for t in hard if t.kind == "near_max"
                 for u, v, c, _tag in _near_max_edges(t, axis)]
        keep_seps = list(seps)
        keep_pos = dict(pos)
        keep_log = list(log)
        ok, newpos, newseps, flips, fail = _nat.module().legalize_repair_axis(
            axis == "x", names, sizes, span, clear, sep_in, frects, extra,
            REPAIR_MAX)
        basis_of = {(s.lo, s.hi): s.basis for s in seps}
        flipped_keys = {(lo, hi) for lo, hi, _was in flips}
        seps.clear()
        for ax, lo, hi, gap, flip in newseps:
            basis = basis_of.get((lo, hi), "")
            if (lo, hi) in flipped_keys and not basis.endswith("|flipped"):
                basis = (basis + "|flipped") if basis else "flipped"
            seps.append(_Sep("x" if ax else "y", lo, hi, gap, basis, flip))
        if ok:
            for i, n in enumerate(names):
                pos[n] = newpos[i]
            for lo, hi, was_x in flips:
                log.append(f"repair: flip {lo}|{hi} off "
                           f"{'x' if was_x else 'y'}")
        if _nat.trace():
            seps[:] = keep_seps
            pos.clear()
            pos.update(keep_pos)
            log[:] = keep_log
            ref_ok = _repair_axis_py(axis, pos)
            if ok is not ref_ok:
                raise AssertionError(
                    "native legalize_repair_axis DIVERGENCE: "
                    f"cpp_ok={ok} python_ok={ref_ok} fail={fail}")
            if ok:
                got = {n: newpos[i] for i, n in enumerate(names)}
                refp = {n: pos[n] for n in names}
                if got != refp:
                    raise AssertionError(
                        "native legalize_repair_axis DIVERGENCE: "
                        f"cpp={got} python={refp}")
            return ref_ok
        if not ok:
            if fail == "exhausted":
                log.append(f"INFEASIBLE {axis}: REPAIR_MAX exhausted")
            else:
                log.append(f"INFEASIBLE {axis}: negative cycle")
            return False
        return True

    if not seed_feasible:
        for axis, pos in (("x", posx), ("y", posy)):
            if not _repair_axis(axis, pos):
                return False
        _descend(posx, posy, hops=(), seed_only=True)
        for axis, pos in (("x", posx), ("y", posy)):
            for u, v, c, tag in build_edges(axis):
                if pos.get(v, 0.0) - pos.get(u, 0.0) > c + 1e-9:
                    kind = tag[0] if isinstance(tag, tuple) else str(tag)
                    log.append(f"REJECT: {axis}-edge unsatisfied after axis "
                               f"solve ({kind} {u}|{v}) — repair flip landed "
                               f"on an already-solved axis")
                    return False

    def poses_now() -> dict[str, tuple[float, float]]:
        out = dict(fixed_poses)
        for n in names:
            out[n] = (round(posx[n], 4), round(posy[n], 4))
        return out

    def reds(p) -> list[TermEval]:
        return [e for e in evaluate_terms(board_w, board_h, som_core_page,
                                          p, metrics, index,
                                          som_j_rects=som_j_rects)
                if e.term.enforced and not e.ok]

    r1 = reds(poses_now())
    if r1:
        log.append("REJECT: hard red after legalization: "
                   + "; ".join(f"{e.term.kind} {e.term.subject}->"
                               f"{e.term.target_raw} margin {e.margin}"
                               for e in r1[:4]))
        return False

    if compact:
        keepx, keepy = dict(posx), dict(posy)
        hops = tuple(t for t in hard if t.kind == "flow_hop")
        _descend(posx, posy, hops=hops, seed_only=False)
        if (reds(poses_now()) or not edges_ok("x", posx)
                or not edges_ok("y", posy)):
            posx, posy = keepx, keepy
            log.append("compaction REVERTED (would break a hard term "
                       "or separation)")
        else:
            log.append("compacted (wired hop pulls applied)")

    rect = {n: (round(posx[n], 4), round(posy[n], 4),
                round(posx[n], 4) + by_name[n].w,
                round(posy[n], 4) + by_name[n].h) for n in names}
    for i, n in enumerate(names):
        x0, y0, x1, y1 = rect[n]
        others = ([(m, rect[m]) for m in names[i + 1:]]
                  + sorted(frect.items()))
        if not _nat.loaded():
            raise RuntimeError("native rects_overlap_any required")
        hit = _nat.module().rects_overlap_any(
            [(x0, y0, x1, y1)], [box for _m, box in others], 1e-6)
        if _nat.trace():
            ref = any(min(x1, u1) - max(x0, u0) > 1e-6
                      and min(y1, v1) - max(y0, v0) > 1e-6
                      for _m, (u0, v0, u1, v1) in others)
            if hit is not ref:
                raise AssertionError(
                    f"native rects_overlap_any DIVERGENCE: cpp={hit} "
                    f"python={ref}")
        if hit:
            log.append("REJECT: final rect overlap")
            return False
    for n in names:
        v = by_name[n]
        v.x = round(posx[n], 4)
        v.y = round(posy[n], 4)
    log.append("accept: all hard terms green")
    return True
