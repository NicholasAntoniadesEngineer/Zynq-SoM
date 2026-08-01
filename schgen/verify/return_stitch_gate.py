from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

RETURN_VIA_RADIUS_MM = 2.0

V1_PINNED = {"n_pairs": 69, "n_pair_contacts": 138, "n_fail": 29,
             "worst_distance": 4}

RULE_CLEARANCE = 0.15
RULE_HOLE_CLEARANCE = 0.2
RULE_HOLE_TO_HOLE = 0.25

_SHEET2REF = {"som_j1": "J1", "som_j2": "J2", "som_j3": "J3"}
_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ReturnStitchResult:
    ok: bool = True
    radius: float = RETURN_VIA_RADIUS_MM
    n_contacts: int = 0
    n_covered: int = 0
    worst_mm: float = 0.0
    n_vias: int = 0
    violations: list[str] = field(default_factory=list)
    coverage: list[tuple] = field(default_factory=list)
    per_conn: dict[str, tuple[int, int]] = field(default_factory=dict)
    v1_verdict: str = ""
    hash_ok: bool = True
    file_parity: str = "not-checked"

    def summary(self) -> str:
        L = [
            f"RETURN-STITCH GATE (return-path v2): "
            f"{'PASS' if self.ok else 'FAIL'} "
            f"(radius {self.radius} mm, HARD, class-blind)",
            f"  remediation set (v1-failing contacts): {self.n_contacts}",
            f"  covered by som_escape GND vias        : {self.n_covered}",
            f"  worst contact->via distance           : {self.worst_mm:.4f} mm",
            f"  som_escape stitch vias                : {self.n_vias}",
            f"  som_interface hash                    : "
            f"{'ok' if self.hash_ok else 'STALE'}",
            f"  emitted-file parity                   : {self.file_parity}",
        ]
        L.append("  per-connector (contacts, uncovered):")
        for ref in sorted(self.per_conn):
            c, u = self.per_conn[ref]
            L.append(f"    {ref}: {c} contacts, {u} uncovered")
        L.append("  triage-ranked coverage (GENUINE first — ordering only, "
                 "never a waiver):")
        for _rank, klass, ref, pad, fn, dist in sorted(self.coverage):
            d = "NONE" if dist is None else f"{dist:.4f} mm"
            L.append(f"    [{klass:<8}] {ref} pad {pad:>3} {fn:<28} -> {d}")
        if self.violations:
            L.append("  VIOLATIONS:")
            for v in self.violations:
                L.append(f"    {v}")
        L.append("")
        L.append("  ---- return-path v1 verdict (SoM-design fact, quoted "
                 "verbatim; NOT waived by this gate) ----")
        for line in self.v1_verdict.splitlines():
            L.append(f"  | {line}")
        return "\n".join(L)


def _som_interface_sha256() -> str:
    p = PROJECT_ROOT / "som_interface.json"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check(model, pcb_path: Path | None = None) -> ReturnStitchResult:
    from schgen.verify import return_path_gate as rpg
    from schgen.verify import si_triage
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    res = ReturnStitchResult()

    v1 = rpg.check()
    res.v1_verdict = v1.summary()
    live = {"n_pairs": v1.n_pairs, "n_pair_contacts": v1.n_pair_contacts,
            "n_fail": v1.n_fail, "worst_distance": v1.worst_distance}
    if live != V1_PINNED:
        res.ok = False
        res.violations.append(
            f"v1 population drift: live {live} != pinned {V1_PINNED} — the "
            f"SoM interface moved; re-derive the stitching deliberately "
            f"(update the pin in the same reviewed unit)")

    conns = {}
    for inst in model.insts:
        ref = _SHEET2REF.get(inst.sheet)
        if ref:
            conns[ref] = inst
    if set(conns) != {"J1", "J2", "J3"}:
        res.ok = False
        res.violations.append(f"DF40 receptacles missing: found "
                              f"{sorted(conns)}")
        return res

    copper = list(getattr(model, "copper", None) or [])
    esc = [c for c in copper if c.get("group") == "som_escape"]
    vias = [c for c in esc if c["kind"] == "via"]
    segs = [c for c in esc if c["kind"] == "segment"]
    res.n_vias = len(vias)

    gnd_num = model.net_numbers.get("GND")

    for c in esc:
        if c.get("net") != gnd_num or c.get("net_name") != "GND":
            res.ok = False
            res.violations.append(
                f"som_escape {c['kind']} carries net "
                f"{c.get('net')}/{c.get('net_name')!r}, expected "
                f"{gnd_num}/'GND' (LAW 0)")

    res.n_contacts = len(v1.violations)
    uncovered_by_conn: dict[str, int] = {r: 0 for r in ("J1", "J2", "J3")}
    contacts_by_conn: dict[str, int] = {r: 0 for r in ("J1", "J2", "J3")}
    for viol in v1.violations:
        inst = conns[viol.ref]
        boxes = _inst_pad_boxes(inst)
        bb = boxes.get(viol.pad)
        if bb is None:
            res.ok = False
            res.violations.append(f"{viol.ref} pad {viol.pad}: no pad box")
            continue
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        best = None
        for via in vias:
            d = math.hypot(via["x"] - cx, via["y"] - cy)
            best = d if best is None else min(best, d)
        kl = si_triage.classify(viol.net)
        res.coverage.append((si_triage.RANK[kl.klass], kl.klass, viol.ref,
                             viol.pad, kl.function, best))
        contacts_by_conn[viol.ref] += 1
        if best is None or best > RETURN_VIA_RADIUS_MM:
            res.ok = False
            uncovered_by_conn[viol.ref] += 1
            res.violations.append(
                f"{viol.ref} pad {viol.pad} ({kl.function}, {kl.klass}): "
                f"nearest som_escape GND via "
                f"{'absent' if best is None else f'{best:.4f} mm'} "
                f"> bound {RETURN_VIA_RADIUS_MM}")
        else:
            res.n_covered += 1
            res.worst_mm = max(res.worst_mm, best)
    res.per_conn = {r: (contacts_by_conn[r], uncovered_by_conn[r])
                    for r in sorted(contacts_by_conn)}

    if vias or segs:
        _check_network(model, conns, vias, segs, res)

    _check_clearance(model, conns, vias, segs, res)

    meta = getattr(model, "escape_meta", None) or {}
    if meta:
        res.hash_ok = (meta.get("som_interface_sha256")
                       == _som_interface_sha256())
        if not res.hash_ok:
            res.ok = False
            res.violations.append("escape_meta som_interface sha256 is STALE "
                                  "vs the live contract")

    if pcb_path is not None:
        msg = file_parity(Path(pcb_path), esc)
        res.file_parity = msg
        if msg != "ok":
            res.ok = False
            res.violations.append(f"file parity: {msg}")

    return res


def _check_network(model, conns, vias, segs, res) -> None:
    from schgen.generate.pcb.escape import _canonical_plane
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    rect, void_rects = _canonical_plane(model)

    by_conn: dict[str, dict] = {}
    for via in vias:
        by_conn.setdefault(via["conn"], {"vias": [], "segs": []})[
            "vias"].append(via)
    for seg in segs:
        by_conn.setdefault(seg["conn"], {"vias": [], "segs": []})[
            "segs"].append(seg)

    for ref, group in sorted(by_conn.items()):
        inst = conns[ref]
        boxes = _inst_pad_boxes(inst)
        gnd_pads = [(p, b) for p, b in sorted(boxes.items())
                    if inst.pad_nets.get(p, (0, ""))[1] == "GND"]
        nodes: list[tuple[str, object]] = (
            [("via", v) for v in group["vias"]]
            + [("seg", s) for s in group["segs"]]
            + [("pad", b) for _p, b in gnd_pads])
        parent = list(range(len(nodes)))

        def find(i, parent=parent):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j, parent=parent):
            parent[find(i)] = find(j)

        def seg_box(s):
            return (min(s["x1"], s["x2"]) - s["width"] / 2,
                    min(s["y1"], s["y2"]) - s["width"] / 2,
                    max(s["x1"], s["x2"]) + s["width"] / 2,
                    max(s["y1"], s["y2"]) + s["width"] / 2)

        def boxes_touch(a, b):
            return (a[0] <= b[2] + 1e-9 and b[0] <= a[2] + 1e-9
                    and a[1] <= b[3] + 1e-9 and b[1] <= a[3] + 1e-9)

        def node_box(n):
            k, v = n
            if k == "via":
                r = v["size"] / 2
                return (v["x"] - r, v["y"] - r, v["x"] + r, v["y"] + r)
            if k == "seg":
                return seg_box(v)
            return v

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if nodes[i][0] == "pad" and nodes[j][0] == "pad":
                    continue
                if boxes_touch(node_box(nodes[i]), node_box(nodes[j])):
                    union(i, j)
        roots = {find(i) for i, n in enumerate(nodes)
                 if n[0] in ("via", "seg")}
        if len(roots) != 1:
            res.ok = False
            res.violations.append(
                f"{ref}: ladder+vias form {len(roots)} components (expected "
                f"ONE GND-only component)")
        for v in group["vias"]:
            if not any(boxes_touch(node_box(("via", v)), seg_box(s))
                       for s in group["segs"]):
                res.ok = False
                res.violations.append(
                    f"{ref}: via at ({v['x']},{v['y']}) touches no F.Cu "
                    f"ladder copper (fill-dependent connectivity — LAW 0)")
            if not (rect[0] <= v["x"] <= rect[2]
                    and rect[1] <= v["y"] <= rect[3]):
                res.ok = False
                res.violations.append(
                    f"{ref}: via at ({v['x']},{v['y']}) outside the canonical "
                    f"In1 GND plane {rect}")
            for vr, label in void_rects:
                if vr[0] <= v["x"] <= vr[2] and vr[1] <= v["y"] <= vr[3]:
                    res.ok = False
                    res.violations.append(
                        f"{ref}: via at ({v['x']},{v['y']}) inside In1 plane "
                        f"VOID {label} — no plane to land on")
        n_stubs = sum(1 for s in group["segs"]
                      if s.get("role", "").startswith("stub")
                      and s.get("role") != "stub_via")
        if n_stubs < 2:
            res.ok = False
            res.violations.append(f"{ref}: {n_stubs} GND-pad stub(s) < 2")


def _check_clearance(model, conns, vias, segs, res) -> None:
    from schgen.verify.placement_contract_gate import _inst_pad_boxes

    if not (vias or segs):
        return
    xs = ([v["x"] for v in vias] + [s["x1"] for s in segs]
          + [s["x2"] for s in segs])
    ys = ([v["y"] for v in vias] + [s["y1"] for s in segs]
          + [s["y2"] for s in segs])
    win = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
    foreign: list[tuple[tuple, str, float, str]] = []
    for oi in sorted(model.insts, key=lambda i: i.ref):
        for pad, bb in sorted(_inst_pad_boxes(oi).items()):
            net = oi.pad_nets.get(pad, (0, ""))[1]
            if net == "GND":
                continue
            rule = 0.2 if model.netclass_of.get(net) == "POWER" else \
                RULE_CLEARANCE
            if (bb[2] < win[0] or bb[0] > win[2] or bb[3] < win[1]
                    or bb[1] > win[3]):
                continue
            foreign.append((bb, oi.side, rule, f"{oi.ref}.{pad}"))

    def box_dist(x, y, b):
        dx = max(b[0] - x, x - b[2], 0.0)
        dy = max(b[1] - y, y - b[3], 0.0)
        return math.hypot(dx, dy)

    for v in vias:
        for bb, _side, rule, label in foreign:
            d = box_dist(v["x"], v["y"], bb)
            if d < v["size"] / 2 + rule:
                res.ok = False
                res.violations.append(
                    f"via ({v['x']},{v['y']}) vs foreign {label}: "
                    f"{d:.4f} < {v['size'] / 2 + rule:.4f}")
    for s in segs:
        sb = (min(s["x1"], s["x2"]), min(s["y1"], s["y2"]),
              max(s["x1"], s["x2"]), max(s["y1"], s["y2"]))
        for bb, side, rule, label in foreign:
            if side != "top":
                continue
            dx = max(bb[0] - sb[2], sb[0] - bb[2], 0.0)
            dy = max(bb[1] - sb[3], sb[1] - bb[3], 0.0)
            d = math.hypot(dx, dy)
            if d < s["width"] / 2 + rule:
                res.ok = False
                res.violations.append(
                    f"segment {s['role']} vs foreign {label}: {d:.4f} < "
                    f"{s['width'] / 2 + rule:.4f}")


def file_parity(pcb_path: Path, esc: list[dict]) -> str:
    if not pcb_path.exists():
        return f"board file missing: {pcb_path}"
    text = pcb_path.read_text()

    def num(x: float) -> str:
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"

    for c in esc:
        if c["kind"] == "via":
            pat = (rf'\(via\s+\(at {re.escape(num(c["x"]))} '
                   rf'{re.escape(num(c["y"]))}\)\s+\(size '
                   rf'{re.escape(num(c["size"]))}\)\s+\(drill '
                   rf'{re.escape(num(c["drill"]))}\)')
            if not re.search(pat, text):
                return f"via at ({c['x']},{c['y']}) absent from {pcb_path.name}"
        elif c["kind"] == "segment":
            pat = (rf'\(segment\s+\(start {re.escape(num(c["x1"]))} '
                   rf'{re.escape(num(c["y1"]))}\)\s+\(end '
                   rf'{re.escape(num(c["x2"]))} {re.escape(num(c["y2"]))}\)')
            if not re.search(pat, text):
                return (f"segment ({c['x1']},{c['y1']})-({c['x2']},{c['y2']}) "
                        f"absent from {pcb_path.name}")
    if '(name "GND_plane_In1")' not in text:
        return f"canonical GND_plane_In1 zone absent from {pcb_path.name}"
    return "ok"
