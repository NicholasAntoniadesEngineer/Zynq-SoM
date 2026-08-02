from __future__ import annotations

import argparse
import json
from pathlib import Path

from schgen.core import sexpr
from schgen.core.quantize import STACK_THICKNESS_MM
from schgen.core.sexpr import Sym
from schgen.output.emit import stable_uuid

from .constants import (
    CARRIER,
    DEFAULT_CLEARANCE_MM,
    DEFAULT_TRACK_MM,
    FIDUCIAL_FOOTPRINT,
    HOLE_TO_HOLE_DRC_MARGIN,
    HOLE_TO_HOLE_FAB,
    HOLE_TO_HOLE_THERMAL_MARGIN,
    MIN_HOLE_TO_HOLE,
    ORIGIN_X,
    ORIGIN_Y,
    POWER_CLASS,
    POWER_CLEARANCE_MM,
    POWER_TRACK_MM,
    REPO_ROOT,
    THERMAL_VIA_H2H,
    PcbModel,
)
from .embed import (
    _edge_rect,
    _embed_footprint,
    _gnd_plane_zone,
    _iso_void_zones,
    _layers_node,
    _segment_node,
    _som_body_silk,
    _som_keepout_zone,
    _stackup_node,
    _thermal_copper_nodes,
    _via_node,
)
from .footprint import board_parts
from .placement import build_model
from .silk import (
    _connector_descriptors,
    _declutter_refdes,
    _hide_undersom_bottom_refs,
)


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


def emit_pcb(model: PcbModel, out_path: Path) -> Path:
    board_uuid = stable_uuid("Zynq_Carrier", "pcb")
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return stable_uuid(board_uuid, "pcb-id", kind, n)

    doc: list = [
        Sym("kicad_pcb"),
        [Sym("version"), 20260206],
        [Sym("generator"), "schgen"],
        [Sym("generator_version"), "1.0"],
        [Sym("general"), [Sym("thickness"), STACK_THICKNESS_MM],
         [Sym("legacy_teardrops"), Sym("no")]],
        [Sym("paper"), "A3"],
        [Sym("title_block"),
         [Sym("title"), "Zynq Carrier — PCB foundation (schgen)"],
         [Sym("company"), "Zynq SoM Carrier"],
         [Sym("comment"), 1,
          "FOUNDATION: derived outline + SoM-body keep-out + 4L stackup + net "
          "classes + 2-side placement (SoM-mirror mezzanine, per-subsystem "
          "ratsnest bundles). NOT routed — schgen-generated (do not hand-edit)."]],
        _layers_node(),
    ]

    doc.append([Sym("setup"),
                _stackup_node(),
                [Sym("pad_to_mask_clearance"), 0],
                [Sym("allow_soldermask_bridges_in_footprints"), Sym("yes")],
                [Sym("aux_axis_origin"), ORIGIN_X, ORIGIN_Y]])

    by_num = sorted(model.net_numbers.items(), key=lambda kv: kv[1])
    for name, num in by_num:
        doc.append([Sym("net"), num, name])

    x0, y0 = ORIGIN_X, ORIGIN_Y
    x1, y1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    doc.extend(_edge_rect(x0, y0, x1, y1, uid))

    if model.som_keepout is not None:
        doc.append(_som_keepout_zone(model.som_keepout, uid))

    plane = _gnd_plane_zone(model, uid)
    if plane is not None:
        doc.append(plane)
    doc.extend(_iso_void_zones(model, uid))
    thermal_zones, thermal_vias = _thermal_copper_nodes(model, uid)
    doc.extend(thermal_zones)

    if model.som_core is not None:
        doc.extend(_som_body_silk(model.som_core, uid))

    for inst in model.insts:
        doc.append(_embed_footprint(inst, uid))

    _hide_undersom_bottom_refs(model, doc)

    doc.extend(_connector_descriptors(model, uid, doc))

    _declutter_refdes(model, uid, doc)

    doc.extend(thermal_vias)

    for c in getattr(model, "copper", None) or []:
        if c["kind"] == "via":
            doc.append(_via_node(c, uid))
        elif c["kind"] == "segment":
            doc.append(_segment_node(c, uid))
        else:
            raise ValueError(f"unknown escape copper kind {c['kind']!r}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sexpr.dumps(doc) + "\n")
    return out_path


def _design_settings() -> dict:
    return {
        "defaults": {
            "apply_defaults_to_fp_barcodes": False,
            "apply_defaults_to_fp_dimensions": False,
            "apply_defaults_to_fp_fields": False,
            "apply_defaults_to_fp_shapes": False,
            "apply_defaults_to_fp_text": False,
            "board_outline_line_width": 0.1,
            "copper_line_width": 0.2,
            "copper_text_italic": False,
            "copper_text_size_h": 1.5,
            "copper_text_size_v": 1.5,
            "copper_text_thickness": 0.3,
            "copper_text_upright": False,
            "courtyard_line_width": 0.05,
            "dimension_precision": 4,
            "dimension_units": 3,
            "dimensions": {
                "arrow_length": 1270000,
                "extension_offset": 500000,
                "keep_text_aligned": True,
                "suppress_zeroes": False,
                "text_position": 0,
                "units_format": 1,
            },
            "fab_line_width": 0.1,
            "fab_text_italic": False,
            "fab_text_size_h": 1.0,
            "fab_text_size_v": 1.0,
            "fab_text_thickness": 0.15,
            "fab_text_upright": False,
            "other_line_width": 0.15,
            "other_text_italic": False,
            "other_text_size_h": 1.0,
            "other_text_size_v": 1.0,
            "other_text_thickness": 0.15,
            "other_text_upright": False,
            "pads": {"drill": 0.0, "height": 1.8, "width": 1.0},
            "silk_line_width": 0.15,
            "silk_text_italic": False,
            "silk_text_size_h": 1.0,
            "silk_text_size_v": 1.0,
            "silk_text_thickness": 0.15,
            "silk_text_upright": False,
            "zones": {
                "border_display_style": 2,
                "border_hatch_pitch": 0.5,
                "corner_radius": 0.0,
                "corner_smoothing": 0,
                "fill_mode": 0,
                "hatch_gap": 1.5,
                "hatch_orientation": 0.0,
                "hatch_smoothing_level": 0,
                "hatch_smoothing_value": 0.1,
                "hatch_thickness": 1.0,
                "min_clearance": 0.127,
                "min_island_area": 10.0,
                "min_thickness": 0.25,
                "pad_connection": 1,
                "remove_islands": 0,
                "thermal_relief_gap": 0.5,
                "thermal_relief_spoke_width": 0.5,
            },
        },
        "diff_pair_dimensions": [
            {"gap": 0.0, "via_gap": 0.0, "width": 0.0},
            {"gap": 0.2, "via_gap": 0.5, "width": 0.1},
            {"gap": 0.25, "via_gap": 0.5, "width": 0.1},
            {"gap": 0.25, "via_gap": 0.5, "width": 0.104},
            {"gap": 0.3, "via_gap": 0.5, "width": 0.11},
            {"gap": 0.2, "via_gap": 0.5, "width": 0.12},
        ],
        "drc_exclusions": [],
        "meta": {"version": 2},
        "rule_severities": {
            "annular_width": "error",
            "clearance": "error",
            "connection_width": "warning",
            "copper_edge_clearance": "error",
            "copper_sliver": "warning",
            "courtyards_overlap": "error",
            "creepage": "error",
            "diff_pair_gap_out_of_range": "error",
            "diff_pair_uncoupled_length_too_long": "error",
            "drill_out_of_range": "error",
            "duplicate_footprints": "warning",
            "extra_footprint": "warning",
            "footprint": "error",
            "footprint_filters_mismatch": "ignore",
            "footprint_symbol_field_mismatch": "warning",
            "footprint_symbol_mismatch": "warning",
            "footprint_type_mismatch": "ignore",
            "hole_clearance": "error",
            "hole_near_hole": "error",
            "hole_to_hole": "error",
            "holes_co_located": "warning",
            "invalid_outline": "error",
            "isolated_copper": "warning",
            "item_on_disabled_layer": "error",
            "items_not_allowed": "error",
            "length_out_of_range": "error",
            "lib_footprint_issues": "warning",
            "lib_footprint_mismatch": "warning",
            "malformed_courtyard": "error",
            "microvia_drill_out_of_range": "error",
            "mirrored_text_on_front_layer": "warning",
            "missing_courtyard": "ignore",
            "missing_footprint": "warning",
            "missing_tuning_profile": "warning",
            "net_conflict": "warning",
            "nonmirrored_text_on_back_layer": "warning",
            "npth_inside_courtyard": "ignore",
            "padstack": "warning",
            "pth_inside_courtyard": "ignore",
            "shorting_items": "error",
            "silk_edge_clearance": "warning",
            "silk_over_copper": "warning",
            "silk_overlap": "warning",
            "skew_out_of_range": "error",
            "solder_mask_bridge": "error",
            "starved_thermal": "error",
            "text_height": "warning",
            "text_on_edge_cuts": "error",
            "text_thickness": "warning",
            "through_hole_pad_without_hole": "error",
            "too_many_vias": "error",
            "track_angle": "error",
            "track_dangling": "warning",
            "track_not_centered_on_via": "ignore",
            "track_on_post_machined_layer": "error",
            "track_segment_length": "error",
            "track_width": "error",
            "tracks_crossing": "error",
            "tuning_profile_track_geometries": "ignore",
            "unconnected_items": "error",
            "unresolved_variable": "error",
            "via_dangling": "warning",
            "zones_intersect": "error",
        },
        "rules": {
            "max_error": 0.005,
            "min_clearance": 0.09,
            "min_connection": 0.0,
            "min_copper_edge_clearance": 0.3,
            "min_groove_width": 0.0,
            "min_hole_clearance": 0.2,
            "min_hole_to_hole": MIN_HOLE_TO_HOLE,
            "min_microvia_diameter": 0.2,
            "min_microvia_drill": 0.1,
            "min_resolved_spokes": 2,
            "min_silk_clearance": 0.0,
            "min_text_height": 0.8,
            "min_text_thickness": 0.08,
            "min_through_hole_diameter": 0.2,
            "min_track_width": 0.09,
            "min_via_annular_width": 0.05,
            "min_via_diameter": 0.3,
            "solder_mask_clearance": 0.0,
            "solder_mask_min_width": 0.0,
            "solder_mask_to_copper_clearance": 0.0,
            "use_height_for_length_calcs": True,
        },
        "teardrop_options": [{
            "td_onpthpad": True,
            "td_onroundshapesonly": False,
            "td_onsmdpad": True,
            "td_ontrackend": False,
            "td_onvia": True,
        }],
        "teardrop_parameters": [
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_round_shape",
             "td_width_to_size_filter_ratio": 0.9},
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_rect_shape",
             "td_width_to_size_filter_ratio": 0.9},
            {"td_allow_use_two_tracks": True, "td_curve_segcount": 0,
             "td_height_ratio": 1.0, "td_length_ratio": 0.5,
             "td_maxheight": 2.0, "td_maxlen": 1.0, "td_on_pad_in_zone": False,
             "td_target_name": "td_track_end",
             "td_width_to_size_filter_ratio": 0.9},
        ],
        "track_widths": [0.0, 0.1, 0.11, 0.135, 0.15, 0.2, 0.25, 0.3, 0.5],
        "tuning_pattern_settings": {
            "diff_pair_defaults": {
                "corner_radius_percentage": 50, "corner_style": 0,
                "max_amplitude": 1.2, "min_amplitude": 0.1,
                "single_sided": True, "spacing": 0.6},
            "diff_pair_skew_defaults": {
                "corner_radius_percentage": 100, "corner_style": 1,
                "max_amplitude": 1.0, "min_amplitude": 0.05,
                "single_sided": False, "spacing": 0.3},
            "single_track_defaults": {
                "corner_radius_percentage": 50, "corner_style": 0,
                "max_amplitude": 1.0, "min_amplitude": 0.1,
                "single_sided": True, "spacing": 0.4},
        },
        "via_dimensions": [
            {"diameter": 0.0, "drill": 0.0},
            {"diameter": 0.3, "drill": 0.2},
            {"diameter": 0.35, "drill": 0.2},
            {"diameter": 0.4, "drill": 0.25},
            {"diameter": 0.4, "drill": 0.3},
            {"diameter": 0.45, "drill": 0.3},
            {"diameter": 0.55, "drill": 0.4},
        ],
        "zones_allow_external_fillets": True,
    }


def _class_dict(name: str, geo, *, is_power: bool, is_default: bool) -> dict:
    track = DEFAULT_TRACK_MM
    clearance = DEFAULT_CLEARANCE_MM
    dp_w = 0.2
    dp_g = 0.2
    if is_power:
        track = POWER_TRACK_MM
        clearance = POWER_CLEARANCE_MM
    elif geo is not None:
        track = geo.width_mm
        dp_w = geo.width_mm
        dp_g = geo.gap_mm
    return {
        "bus_width": 12,
        "clearance": round(clearance, 4),
        "diff_pair_gap": round(dp_g, 4),
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": round(dp_w, 4),
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": name,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "priority": 2147483647 if is_default else (10 if is_power else 5),
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": round(track, 4),
        "tuning_profile": "",
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "wire_width": 6,
    }


def write_project(model: PcbModel, pro_path: Path) -> None:
    data: dict = {}
    if pro_path.exists():
        data = json.loads(pro_path.read_text())
    data.setdefault("meta", {"filename": pro_path.name, "version": 3})
    data.setdefault("erc", {"rule_severities": {"pin_not_driven": "warning"}})

    data["board"] = data.get("board", {})
    data["board"]["design_settings"] = _design_settings()

    classes = [_class_dict("Default", None, is_power=False, is_default=True)]
    for name in sorted(model.classes):
        geo = model.classes[name]
        classes.append(_class_dict(name, geo, is_power=(name == POWER_CLASS),
                                   is_default=False))
    patterns = [{"netclass": cls, "pattern": net}
                for net, cls in sorted(model.netclass_of.items())]
    data["net_settings"] = {
        "classes": classes,
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    data.setdefault("pcbnew", {"last_paths": {}, "page_layout_descr_file": ""})
    pro_path.write_text(json.dumps(data, indent=2) + "\n")


def write_dru(model: PcbModel, dru_path: Path) -> None:
    L = [
        "(version 1)",
        "",
        "# Generated by schgen/generate/pcb.py — board-level design rules for",
        "# the PCB foundation. Stackup: JLCPCB JLC04161H-7628 (4L 1.6mm).",
        "# Net classes + per-net assignment live in the .kicad_pro net_settings;",
        "# these rules pin the geometry KiCad's DRC enforces.",
        "",
        "(rule \"minimum_clearance\"",
        f"  (constraint clearance (min {DEFAULT_CLEARANCE_MM}mm))",
        ")",
        "",
        "(rule \"minimum_track\"",
        f"  (constraint track_width (min {DEFAULT_TRACK_MM}mm))",
        ")",
        "",
        "(rule \"POWER_track\"",
        "  (condition \"A.NetClass == 'POWER'\")",
        f"  (constraint track_width (min {POWER_TRACK_MM}mm) (opt {POWER_TRACK_MM}mm))",
        ")",
        "",
    ]
    for name in sorted(model.classes):
        geo = model.classes[name]
        if geo is None:
            continue
        L += [
            f'(rule "{name}_geometry"',
            f"  (condition \"A.NetClass == '{name}'\")",
            f"  (constraint track_width (min {geo.width_mm}mm) "
            f"(opt {geo.width_mm}mm) (max {geo.width_mm}mm))",
            f"  (constraint diff_pair_gap (min {geo.gap_mm}mm) "
            f"(opt {geo.gap_mm}mm))",
            ")",
            "",
        ]
    dru_path.parent.mkdir(parents=True, exist_ok=True)
    dru_path.write_text("\n".join(L))


def generate(*, run_drc: bool = True, two_side: bool = True,
             ratsnest: bool = True) -> dict:
    from schgen.core import ledger as _led
    model = build_model(two_side=two_side)

    with _led.step("pcb.emission"):
        _led.calc("min_hole_to_hole", MIN_HOLE_TO_HOLE,
                  fab_floor=HOLE_TO_HOLE_FAB,
                  drc_margin=HOLE_TO_HOLE_DRC_MARGIN)
        _led.calc("thermal_via_h2h", THERMAL_VIA_H2H,
                  fab_floor=HOLE_TO_HOLE_FAB,
                  thermal_margin=HOLE_TO_HOLE_THERMAL_MARGIN)
        pcb_path = CARRIER / "Zynq_Carrier.kicad_pcb"
        emit_pcb(model, pcb_path)

        pro_path = CARRIER / "Zynq_Carrier.kicad_pro"
        write_project(model, pro_path)

        dru_path = CARRIER / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
        write_dru(model, dru_path)
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
    result["fanout"] = fanout_gate.check(model)
    from schgen.verify import escape_lane_gate, return_path_gate, return_stitch_gate
    result["return_stitch"] = return_stitch_gate.check(model, pcb_path)
    result["escape_lanes"] = escape_lane_gate.check(model)
    result["return_path"] = return_path_gate.check()
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
        result["ratsnest_gate"] = ratsnest_gate.check(model, npp, mst)
        result["placement_mech"] = placement_mech.check(model)
        result["connector_model"] = connector_model_gate.check(model)
        result["connector_spacing"] = connector_spacing_gate.check(model)
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
