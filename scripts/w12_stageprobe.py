"""WAVE-12 per-stage est/emission gap probe (scratch tooling, worktree-local).

Runs build_model once with StageTracker.checkpoint wrapped so that at EVERY
stage boundary the LAW-5 ratsnest kernel (mating_face.net_pad_positions +
ratsnest._mst_edges + the gate's cross sum) is evaluated on the CURRENT board
state, replicating the emission projection exactly. Also evaluates the sizing
estimator on the committed plan. Prints one JSON line.

Usage: python3 scripts/w12_stageprobe.py <tag> [sheet ...]
"""
import inspect
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import schgen.core.quantize as _q  # noqa: E402
from schgen.generate.pcb import stages as _stages  # noqa: E402
from schgen.generate.pcb.constants import (  # noqa: E402
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
)
from schgen.generate.pcb.footprint import pad_names  # noqa: E402
from schgen.generate.pcb.mating_face import net_pad_positions  # noqa: E402
from schgen.generate.ratsnest import _mst_edges  # noqa: E402

ROWS = []


class _M:
    def __init__(self, insts):
        self.insts = insts


def _cross_of(insts):
    npp = net_pad_positions(_M(insts))
    cross = total = 0.0
    n = 0
    for _net, pts in sorted(npp.items()):
        for a, b in _mst_edges(pts):
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            d = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
            total += d
            if sa != sb:
                cross += d
                n += 1
    return round(cross, 1), round(total, 1), n


def _insts_now(fl):
    pos = fl["pos"]
    parts = fl["parts"]
    resolvable = fl["resolvable"]
    side_of = fl["side_of"]
    fixed_rot = fl["fixed_rot"]
    pin_net = fl["pin_net"]
    zg = fl["zg"]
    grid_placed = fl.get("grid_placed", set())
    fixed = fl.get("fixed") or (set(fl["mh_refs"]) | set(fl["som_j_refs"]))
    out = []
    for ref in sorted(resolvable):
        if ref not in pos:
            continue
        sheet, footprint, value, _lib = parts[ref]
        mod = resolvable[ref]
        bx, by = pos[ref]
        side = "top" if ref in fixed else side_of[ref]
        pad_nets = {p: pin_net.get((ref, p), (0, "")) for p in pad_names(mod)}
        if ref in grid_placed:
            fx, fy = round(ORIGIN_X + bx, 4), round(ORIGIN_Y + by, 4)
        else:
            fx, fy = (_q.fixed_part_grid(ORIGIN_X + bx),
                      _q.fixed_part_grid(ORIGIN_Y + by))
        out.append(FootprintInst(
            ref=ref, value=value, footprint=footprint, x=fx, y=fy,
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side,
            mirror=ref in zg.mirror_refs))
    return out


_orig = _stages.StageTracker.checkpoint


def _patched(self, stage_name, snap):
    _orig(self, stage_name, snap)
    fl = inspect.currentframe().f_back.f_locals
    row = {"stage": stage_name}
    if stage_name == "plan_lattice":
        from schgen.generate import floorplan as fp
        plan = fl["plan"]
        ev = fp._cross_estimator(plan, fl["zg"], fl["sheets"])
        blocks = plan.edge_blocks + plan.interior_blocks
        row["est_cross"] = round(ev(blocks), 1)
        row["board"] = f"{fp.BOARD_W:g}x{fp.BOARD_H:g}"
        row["area"] = fp.BOARD_W * fp.BOARD_H
        row["punch_free"] = getattr(plan, "punch_free", None)
        row["bottom_blocks"] = sorted(
            b.name for b in blocks if getattr(b, "side", "top") == "bottom")
        row["shapes"] = {b.name: b.shape_idx for b in blocks
                         if getattr(b, "shape_idx", 0)}
    if fl.get("pos"):
        c, t, n = _cross_of(_insts_now(fl))
        row.update(cross=c, total=t, n_cross=n,
                   moved=self.moves.get(stage_name))
    ROWS.append(row)


_stages.StageTracker.checkpoint = _patched

tag = sys.argv[1]
sheets = [s for s in sys.argv[2:] if not s.startswith("--")]
if "--cons-only" in sys.argv:
    from schgen.generate import floorplan as _fp
    _orig_ap = _fp._attempt_pack

    def _ap(plan, *a, **kw):
        if plan.punch_free:
            raise RuntimeError("w12 probe: conservative-only forced")
        return _orig_ap(plan, *a, **kw)

    _fp._attempt_pack = _ap
SPEC = REPO / "carrier" / "floorplan.json"
orig = SPEC.read_bytes()
try:
    if sheets:
        d = json.loads(orig)
        for s in sheets:
            d["interior"].setdefault(s, {})["layer"] = "either"
        SPEC.write_text(json.dumps(d, indent=1) + "\n")
    from schgen.generate.pcb.placement import build_model
    m = build_model()
    c, t, _n = _cross_of(m.insts)
    ROWS.append({"stage": "FINAL_MODEL", "cross": c, "total": t,
                 "n_bottom": m.n_bottom, "n_top": m.n_top,
                 "board": f"{m.board_w:g}x{m.board_h:g}"})
finally:
    SPEC.write_bytes(orig)

print("W12PROBE " + json.dumps({"tag": tag, "rows": ROWS}))
