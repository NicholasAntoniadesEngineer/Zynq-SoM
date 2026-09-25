from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from .constants import (
    CARRIER,
    FIDUCIAL_FOOTPRINT,
    HOLE_TO_HOLE_DRC_MARGIN,
    HOLE_TO_HOLE_FAB,
    HOLE_TO_HOLE_THERMAL_MARGIN,
    MIN_HOLE_TO_HOLE,
    REPO_ROOT,
    THERMAL_VIA_H2H,
    PcbModel,
)
from .footprint import board_parts
from .placement import FloorplanStageResult, build_model


def _check_wired_contracts(model: PcbModel, gate_mod):
    wired = sorted(gate_mod._WIRED_SHEETS)
    per = [gate_mod.check(model, sheet_name=s) for s in wired]
    if not per:
        return gate_mod.check(model, sheet_name="power")
    if len(per) == 1:
        return per[0]
    merged = gate_mod.PlacementContractResult(
        sheet="+".join(wired), have_contract=any(r.have_contract for r in per))
    merged.ok = all(r.ok for r in per)
    _counts = ("checked", "hot_loop_fail", "same_side_fail", "bulk_fail",
               "bulk_out_fail", "sw_node_fail", "fb_fail", "boot_fail",
               "vcc_fail", "bias_fail", "rt_fail", "ldo_fail", "proximity_fail",
               "unknown_fail")
    for attr in _counts:
        setattr(merged, attr, sum(getattr(r, attr) for r in per))
    for r in per:
        merged.violations.extend(r.violations)
        merged.missing_refs.extend(r.missing_refs)
    merged._sheet_summaries = [r.summary() for r in per]  # type: ignore[attr-defined]
    merged.summary = (  # type: ignore[method-assign]
        lambda: "\n\n".join(merged._sheet_summaries))
    return merged


def emit_pcb(model: PcbModel, out_path: Path, *, prepared=None) -> Path:
    from ._native_emit import write
    write(model, out_path, "pcb", prepared)
    return out_path


def write_project(model: PcbModel, pro_path: Path, *, prepared=None) -> None:
    from ._native_emit import write
    write(model, pro_path, "project", prepared)


def write_dru(model: PcbModel, dru_path: Path, *, prepared=None) -> None:
    from ._native_emit import write
    write(model, dru_path, "rules", prepared)


def generate(*, run_drc: bool = True, two_side: bool = True,
             ratsnest: bool = True,
             plan_sink: Callable[[FloorplanStageResult], None] | None = None
             ) -> dict:
    from schgen.core import ledger as _led
    from schgen.core import timing as _tim
    with _tim.span("pcb.build_model"):
        if plan_sink is None:
            model = build_model(two_side=two_side)
        else:
            model = build_model(two_side=two_side, plan_sink=plan_sink)

    with _led.step("pcb.emission"):
        _led.calc("min_hole_to_hole", MIN_HOLE_TO_HOLE,
                  fab_floor=HOLE_TO_HOLE_FAB,
                  drc_margin=HOLE_TO_HOLE_DRC_MARGIN)
        _led.calc("thermal_via_h2h", THERMAL_VIA_H2H,
                  fab_floor=HOLE_TO_HOLE_FAB,
                  thermal_margin=HOLE_TO_HOLE_THERMAL_MARGIN)
        pcb_path = CARRIER / "Zynq_Carrier.kicad_pcb"
        from ._native_emit import prepare as prepare_emission
        emission_input = prepare_emission(model)
        emit_pcb(model, pcb_path, prepared=emission_input)

        pro_path = CARRIER / "Zynq_Carrier.kicad_pro"
        write_project(model, pro_path, prepared=emission_input)

        dru_path = CARRIER / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
        write_dru(model, dru_path, prepared=emission_input)
        _led.calc("board_emission", model.placed, board_w=model.board_w,
                  board_h=model.board_h, placed=model.placed,
                  n_top=model.n_top, n_bottom=model.n_bottom,
                  nets=len([n for n in model.net_numbers if n]))

    n_fid = sum(1 for i in model.insts
                if i.footprint == FIDUCIAL_FOOTPRINT)
    result = {
        "pcb": pcb_path, "pro": pro_path, "dru": dru_path,
        "board_w": model.board_w, "board_h": model.board_h,
        "placed": model.placed, "total": len(board_parts()) + n_fid,
        "nets": len([n for n in model.net_numbers if n]),
        "classes": sorted(model.classes), "deferred": model.deferred,
        "n_top": model.n_top, "n_bottom": model.n_bottom,
        "two_side": model.two_side, "som_keepout": model.som_keepout,
        "som_core": model.som_core,
        "drc": None, "ratsnest": None, "ratsnest_gate": None,
        "placement_mech": None,
        "connector_model": None, "connector_spacing": None,
        "refdes_silk": None,
        "placement_contract": None, "placement_flow": None,
        "return_stitch": None, "escape_lanes": None, "return_path": None,
        "fanout": None,
    }
    from schgen.core import fallbacks as _fbk
    result["fallbacks"] = _fbk.census()
    result["stage_movement"] = dict(model.stage_moves)
    from schgen.verify import fanout_gate
    from schgen.verify._native_pcb import prepare
    check_input = prepare(model)
    result["fanout"] = fanout_gate.check(model, prepared=check_input)
    from schgen.verify import escape_lane_gate, return_path_gate, return_stitch_gate
    result["return_path"] = return_path_gate.check()
    result["return_stitch"] = return_stitch_gate.check(
        model, pcb_path, prepared=check_input, return_path=result["return_path"])
    result["escape_lanes"] = escape_lane_gate.check(model, prepared=check_input)
    if model.escape_plan is not None:
        block_path = CARRIER / "escape_block.json"
        payload = dict(model.escape_plan)
        payload["escape_meta"] = {
            k: model.escape_meta.get(k)
            for k in ("worst_cover_mm", "vias", "coverage_mm",
                      "escape_region", "plane", "coexistence",
                      "som_interface_sha256", "constants")}
        block_path.write_text(json.dumps(payload, indent=1, sort_keys=True,
                                         default=list) + "\n")
        result["escape_block"] = block_path
    if ratsnest:
        from schgen.generate import ratsnest as rn_mod
        from schgen.verify import (
            connector_model_gate,
            connector_spacing_gate,
            placement_mech,
            ratsnest_gate,
        )

        from .mating_face import net_pad_positions
        npp = net_pad_positions(model)
        mst = rn_mod.net_mst_edges(model, npp)
        result["ratsnest"] = rn_mod.generate(model, npp, mst)
        result["ratsnest_gate"] = ratsnest_gate.check(model, npp, mst, prepared=check_input)
        result["placement_mech"] = placement_mech.check(model, prepared=check_input)
        result["connector_model"] = connector_model_gate.check(model, prepared=check_input)
        result["connector_spacing"] = connector_spacing_gate.check(model, prepared=check_input)
        from schgen.verify import refdes_overlap_gate
        result["refdes_silk"] = refdes_overlap_gate.check(
            pcb_path, enforce_bottom=True)
        from schgen.verify import placement_contract_gate, placement_flow_gate
        result["placement_contract"] = _check_wired_contracts(
            model, placement_contract_gate)
        result["placement_flow"] = placement_flow_gate.check(model)
        from schgen.generate import floorplan_compose
        result["floorplan_composition"] = floorplan_compose.compose_report(
            model, npp=npp, mst=mst)
        result["contract_coverage"] = placement_contract_gate.coverage(model)
    from schgen.core import fallbacks as _fb_asm
    from schgen.generate import assembly as asm_mod
    try:
        result["assembly"] = asm_mod.generate(model)
    except Exception as exc:  # noqa: BLE001
        _fb_asm.record("assembly_generation_failed")
        result["assembly"] = {"ok": False, "error": str(exc)}
    if run_drc:
        with _tim.span("pcb.drc"):
            result["drc"] = run_pcb_drc(pcb_path)
    return result


def run_pcb_drc(pcb_path: Path) -> dict:
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="schgen_drc_") as td:
        rpt = Path(td) / "drc.json"
        proc = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "--severity-warning", "--refill-zones",
             "-o", str(rpt), str(pcb_path)],
            capture_output=True, text=True)
        data = {}
        if rpt.exists():
            try:
                data = json.loads(rpt.read_text())
            except Exception:  # noqa: BLE001
                data = {}
    viols = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    by_type: dict[str, int] = {}
    other: list[str] = []
    for v in viols:
        t = v.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        if t not in ("silk_overlap", "silk_over_copper",
                     "courtyards_overlap", "footprint_type_mismatch"):
            if len(other) < 12:
                other.append(t)
    return {
        "returncode": proc.returncode,
        "n_violations": len(viols),
        "n_unconnected": len(unconnected),
        "by_type": by_type,
        "other_sample": other,
        "stderr": proc.stderr[-400:],
    }


def cmd_pcb(args: argparse.Namespace) -> int:
    res = generate(run_drc=not args.no_drc,
                   two_side=not getattr(args, "single_side", False))
    print(f"PCB: {res['pcb'].relative_to(REPO_ROOT)} "
          f"({res['board_w']:g} x {res['board_h']:g} mm outline, "
          f"4-layer Sig/GND/PWR/Sig stackup)")
    side = (f"2-side (top {res['n_top']} / bottom {res['n_bottom']})"
            if res["two_side"] else "single-side (all top)")
    print(f"  footprints placed: {res['placed']}/{res['total']}  "
          f"nets: {res['nets']}  net classes: {len(res['classes'])} "
          f"({', '.join(res['classes'])})")
    print(f"  assembly: {side}")
    print(f"  net classes + patterns -> {res['pro'].relative_to(REPO_ROOT)}")
    print(f"  design rules -> {res['dru'].relative_to(REPO_ROOT)}")
    if res["deferred"]:
        print(f"  DEFERRED ({len(res['deferred'])} footprints unresolved):")
        for d in res["deferred"]:
            print(f"    {d}")
    drc = res["drc"]
    if drc is not None:
        print(f"  DRC: {drc['n_violations']} violations, "
              f"{drc['n_unconnected']} unconnected (unrouted — expected)")
        for t, n in sorted(drc["by_type"].items()):
            print(f"    {t}: {n}")
    return 0


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser(prog="schgen pcb")
    p.add_argument("--no-drc", action="store_true")
    p.add_argument("--single-side", action="store_true",
                   help="force all footprints on top (default: 2-side, "
                        "decoupling/small passives on the bottom)")
    sys.exit(cmd_pcb(p.parse_args()))
