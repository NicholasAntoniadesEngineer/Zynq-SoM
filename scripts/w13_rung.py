"""WAVE-13 LADDER SCREEN — one rung, measured on the PLACED model.

``python3 scripts/w13_rung.py <sheet> [<sheet> ...]`` declares each named
sheet ``"layer": "either"`` on top of the live ``carrier/floorplan.json`` (the
spec is patched IN MEMORY — the committed file is never touched) and reports
the rung's first-class metrics: board box + area, LAW-5 cross-airwire, the
BOTTOM-SIDE part count, the per-sheet side the est-driven chooser picked, and
the placement gates that judge geometry (LAW-6 mech incl. the wave-13
face-down rule, the placement contract, D13 fan-out). ``--base`` measures the
committed spec unchanged; ``--cons-only`` forces the wave-11 monotonicity
guard's CONSERVATIVE reservation pass (the freed pass is made to fail), which
attributes a rung's delta between its own side flip and the guard's choice of
plan. Neither flag changes the engine — the probe patches its own process.

This is a SCREEN, not a verdict: DRC/ERC/escape/return-stitch/census/ratchet
still need the full ``schgen board`` run on the landed spec.
"""
from __future__ import annotations

import csv
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schgen.core import fallbacks as _fb  # noqa: E402
from schgen.generate import floorplan as fp  # noqa: E402
from schgen.generate import ratsnest as rn_mod  # noqa: E402
from schgen.generate.pcb import placement as pl  # noqa: E402
from schgen.generate.pcb.mating_face import net_pad_positions  # noqa: E402
from schgen.verify import (  # noqa: E402
    fanout_gate,
    placement_contract_gate,
    placement_mech,
    ratsnest_gate,
)


def _patched(names: list[str]):
    base = fp.load_floorplan_spec()
    interior = dict(base.interior)
    for n in names:
        if n not in interior:
            raise SystemExit(f"w13_rung: {n} is not an interior block")
        interior[n] = {**interior[n], "layer": "either"}
    return dataclasses.replace(base, interior=interior)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec = _patched(args)
    if "--cons-only" in sys.argv:
        _oap = fp._attempt_pack

        def _ap(plan, *a, **k):
            if plan.punch_free:
                raise RuntimeError("w13_rung: conservative-only forced")
            return _oap(plan, *a, **k)

        fp._attempt_pack = _ap
    _fb.reset()
    zg_seen: dict[str, object] = {}
    _orig = pl.subsystem_zone_geometry

    def _cap(*a, **k):
        r = _orig(*a, **k)
        zg_seen["zg"] = r
        return r

    pl.subsystem_zone_geometry = _cap
    plan_seen: dict[str, object] = {}
    _obp = fp.build_plan

    def _bp(*a, **k):
        p = _obp(*a, **k)
        plan_seen.setdefault("plan", p)
        return p

    fp.build_plan = _bp
    try:
        model = pl.build_model(two_side=True, spec=spec)
    finally:
        pl.subsystem_zone_geometry = _orig
        fp.build_plan = _obp

    npp = net_pad_positions(model)
    mst = rn_mod.net_mst_edges(model, npp)
    rg = ratsnest_gate.check(model, npp, mst)
    mg = placement_mech.check(model)
    fo = fanout_gate.check(model)
    plan = plan_seen["plan"]
    zg = zg_seen["zg"]

    n_bot = sum(1 for i in model.insts if i.side == "bottom")
    area = round(model.board_w * model.board_h, 1)
    print(f"RUNG {'+'.join(args) or 'BASE'}"
          f"{' [cons-only]' if '--cons-only' in sys.argv else ''}")
    print(f"  board       {model.board_w:g} x {model.board_h:g} = {area} mm2")
    print(f"  cross       {rg.cross_mm:.1f} / {rg.cross_budget_mm:.1f} "
          f"({'OK' if rg.ok else 'FAIL'})")
    print(f"  bottom      {n_bot} of {len(model.insts)} parts")
    print(f"  mech        {'PASS' if mg.ok else 'FAIL'} "
          f"(face-down {len(mg.face_top_on_bottom)}/{mg.n_face_top}, "
          f"bad-conn {len(mg.bad_connectors)}, "
          f"top-under-SoM {len(mg.top_under_som)})")
    print(f"  D13         {fo.n_subjects} subjects, {fo.n_starved} starved")
    print(f"  fallbacks   "
          f"{ {k: v for k, v in _fb.census().items() if v} }")
    for b in sorted(plan.edge_blocks + plan.interior_blocks,
                    key=lambda x: x.name):
        shp = zg.shapes.get(b.name)
        if not shp or not b.shape_idx:
            continue
        s = shp[b.shape_idx]
        if s.side != "bottom":
            continue
        print(f"  BOTTOM-SIDE {b.name}: shape {b.shape_idx} ({s.tag}) "
              f"{s.w:g}x{s.h:g}, primary {len(s.top_off)} -> B.Cu, "
              f"secondary {len(s.bot_off)} -> F.Cu")
    for sheet in sorted(args):
        c = placement_contract_gate.discover_contract(sheet)
        if c is None:
            continue
        r = placement_contract_gate.check(model, sheet)
        print(f"  CONTRACT {sheet}: {'PASS' if r.ok else 'FAIL'} "
              f"({r.checked} structures, {len(r.violations)} violations)")
    cpl = ROOT / "carrier" / "manufacturing" / "Zynq_Carrier_cpl.csv"
    if cpl.exists():
        with cpl.open() as fh:
            rows = list(csv.DictReader(fh))
        print(f"  (last-built CPL on disk: {len(rows)} placements, "
              f"{sum(1 for r in rows if r['Side'] == 'bottom')} bottom)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
