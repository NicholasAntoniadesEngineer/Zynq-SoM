"""Usage: python3 scripts/w12_stageprobe.py <tag> [sheet ...] [--cons-only]."""
import inspect
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SPEC = REPO / "carrier" / "floorplan.json"
SPEC_INDENT = 1
MM_DECIMALS = 1
EMIT_DECIMALS = 4  # mirrors the 4-dp round in quantize.fixed_part_grid

ROWS = []


class _Model:
    def __init__(self, insts):
        self.insts = insts


def _cross_of(insts):
    from schgen.generate.pcb.mating_face import net_pad_positions
    from schgen.generate.ratsnest import _mst_edges
    npp = net_pad_positions(_Model(insts))
    cross = total = 0.0
    n = 0
    for _net, pts in sorted(npp.items()):
        for a, b in _mst_edges(pts):
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            d = math.hypot(xa - xb, ya - yb)
            total += d
            if sa != sb:
                cross += d
                n += 1
    return round(cross, MM_DECIMALS), round(total, MM_DECIMALS), n


def _insts_now(fl):
    import schgen.core.quantize as quantize
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y, FootprintInst
    from schgen.generate.pcb.footprint import pad_names
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
            fx, fy = (round(ORIGIN_X + bx, EMIT_DECIMALS),
                      round(ORIGIN_Y + by, EMIT_DECIMALS))
        else:
            fx, fy = (quantize.fixed_part_grid(ORIGIN_X + bx),
                      quantize.fixed_part_grid(ORIGIN_Y + by))
        out.append(FootprintInst(
            ref=ref, value=value, footprint=footprint, x=fx, y=fy,
            rotation=fixed_rot.get(ref, 0.0), pad_nets=pad_nets,
            mod_path=mod, sheet=sheet, side=side,
            mirror=ref in zg.mirror_refs))
    return out


def _plan_row(fl):
    from schgen.generate import floorplan as fp
    plan = fl["plan"]
    ev = fp._cross_estimator(plan, fl["zg"], fl["sheets"])
    blocks = plan.edge_blocks + plan.interior_blocks
    return {
        "est_cross": round(ev(blocks), MM_DECIMALS),
        "board": f"{fp.BOARD_W:g}x{fp.BOARD_H:g}",
        "area": fp.BOARD_W * fp.BOARD_H,
        "punch_free": getattr(plan, "punch_free", None),
        "bottom_blocks": sorted(
            b.name for b in blocks if getattr(b, "side", "top") == "bottom"),
        "shapes": {b.name: b.shape_idx for b in blocks
                   if getattr(b, "shape_idx", 0)},
    }


def _probe_every_stage(stages):
    orig_checkpoint = stages.StageTracker.checkpoint

    def checkpoint(self, stage_name, snap):
        orig_checkpoint(self, stage_name, snap)
        fl = inspect.currentframe().f_back.f_locals
        row = {"stage": stage_name}
        if stage_name == "plan_lattice":
            row.update(_plan_row(fl))
        if fl.get("pos"):
            c, t, n = _cross_of(_insts_now(fl))
            row.update(cross=c, total=t, n_cross=n,
                       moved=self.moves.get(stage_name))
        ROWS.append(row)

    stages.StageTracker.checkpoint = checkpoint


def _forbid_punch_free(fp):
    orig_attempt_pack = fp._attempt_pack

    def attempt_pack(plan, *a, **kw):
        if plan.punch_free:
            raise RuntimeError("w12 probe: conservative-only forced")
        return orig_attempt_pack(plan, *a, **kw)

    fp._attempt_pack = attempt_pack


def _spec_with_either_side(spec_bytes, sheets):
    d = json.loads(spec_bytes)
    for s in sheets:
        d["interior"].setdefault(s, {})["layer"] = "either"
    return json.dumps(d, indent=SPEC_INDENT) + "\n"


def main(tag, sheets, cons_only):
    from schgen.generate.pcb import stages
    _probe_every_stage(stages)
    if cons_only:
        from schgen.generate import floorplan as fp
        _forbid_punch_free(fp)
    orig = SPEC.read_bytes()
    try:
        if sheets:
            SPEC.write_text(_spec_with_either_side(orig, sheets))
        from schgen.generate.pcb.placement import build_model
        m = build_model()
        c, t, _n = _cross_of(m.insts)
        ROWS.append({"stage": "FINAL_MODEL", "cross": c, "total": t,
                     "n_bottom": m.n_bottom, "n_top": m.n_top,
                     "board": f"{m.board_w:g}x{m.board_h:g}"})
    finally:
        SPEC.write_bytes(orig)
    print("W12PROBE " + json.dumps({"tag": tag, "rows": ROWS}))


if __name__ == "__main__":
    main(sys.argv[1],
         [s for s in sys.argv[2:] if not s.startswith("--")],
         "--cons-only" in sys.argv)
