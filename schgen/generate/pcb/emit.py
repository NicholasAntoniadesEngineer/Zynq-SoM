"""Board serialisation (emit_pcb), the .kicad_pro net-settings / design-settings
writer, the .kicad_dru writer and the ``schgen pcb`` entry point (generate /
run_pcb_drc / cmd_pcb). PURE MOVE out of the old monolithic
``schgen/generate/pcb.py`` — no behaviour change.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.output.emit import stable_uuid

from .constants import (
    CARRIER,
    DEFAULT_CLEARANCE_MM,
    DEFAULT_TRACK_MM,
    ORIGIN_X,
    ORIGIN_Y,
    POWER_CLASS,
    POWER_CLEARANCE_MM,
    POWER_TRACK_MM,
    REPO_ROOT,
    PcbModel,
)
from .embed import (
    _edge_rect,
    _embed_footprint,
    _layers_node,
    _som_body_silk,
    _som_keepout_zone,
    _stackup_node,
)
from .footprint import board_parts
from .placement import build_model
from .silk import (
    _connector_descriptors,
    _declutter_refdes,
    _hide_undersom_bottom_refs,
)


def emit_pcb(model: PcbModel, out_path: Path) -> Path:
    """Serialise the .kicad_pcb."""
    board_uuid = stable_uuid("Zynq_Carrier", "pcb")
    seqs: dict[str, int] = {}

    def uid(kind: str) -> str:
        n = seqs.get(kind, 0)
        seqs[kind] = n + 1
        return stable_uuid(board_uuid, "pcb-id", kind, n)

    doc: list = [
        Sym("kicad_pcb"),
        [Sym("version"), 20241229],
        [Sym("generator"), "schgen"],
        [Sym("generator_version"), "1.0"],
        [Sym("general"), [Sym("thickness"), 1.6],
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

    # setup: stackup + a couple of standard knobs. allow_soldermask_bridges_
    # in_footprints=yes accepts the intra-footprint mask apertures shared by a
    # faithful part's EP/thermal-via group (e.g. the TPS26631 EP + its thermal
    # vias) — a footprint-internal property, never a placement defect.
    doc.append([Sym("setup"),
                _stackup_node(),
                [Sym("pad_to_mask_clearance"), 0],
                [Sym("allow_soldermask_bridges_in_footprints"), Sym("yes")],
                [Sym("aux_axis_origin"), ORIGIN_X, ORIGIN_Y]])

    # net table (net 0 first, then by number)
    by_num = sorted(model.net_numbers.items(), key=lambda kv: kv[1])
    for name, num in by_num:
        doc.append([Sym("net"), num, name])

    # board outline rectangle on Edge.Cuts
    x0, y0 = ORIGIN_X, ORIGIN_Y
    x1, y1 = ORIGIN_X + model.board_w, ORIGIN_Y + model.board_h
    doc.extend(_edge_rect(x0, y0, x1, y1, uid))

    # SoM body keep-out (A1) — nothing routes/places under the mezzanine.
    if model.som_keepout is not None:
        doc.append(_som_keepout_zone(model.som_keepout, uid))

    # SoM module-body OUTLINE on the top silk (LAW 6 documentation) — the
    # rectangle around the DF40 receptacles the user expected to see.
    if model.som_core is not None:
        doc.extend(_som_body_silk(model.som_core, uid))

    # footprints (fixed ref order — determinism)
    for inst in model.insts:
        doc.append(_embed_footprint(inst, uid))

    # LAW 1 (bottom silk): hide the refs of the under-SoM bottom-cap grid (no room
    # for a legible ref on a ~2mm pitch) BEFORE the declutter pass sees them.
    _hide_undersom_bottom_refs(model, doc)

    # short function label beside each connector, header + switch (self-documenting
    # board); interior labels are placed overlap-aware against the emitted designators
    doc.extend(_connector_descriptors(model, uid, doc))

    # LAW 1: relocate any interior refdes that overprints another (dense diode/IC
    # strings). Runs last so it clears every courtyard AND the labels just placed.
    _declutter_refdes(model, uid, doc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sexpr.dumps(doc) + "\n")
    return out_path


# ---- .kicad_pro net classes + .kicad_dru ----------------------------------------

def _design_settings() -> dict:
    """The COMPLETE KiCad-10 board.design_settings block. KiCad's GUI writes
    every one of these keys on save; emitting them all here means opening the
    project in KiCad changes nothing (build twice -> clean .kicad_pro). Carrier-
    specific rule minimums are kept; all other values are the KiCad 10 defaults
    so the block round-trips byte-stable."""
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
            "min_hole_to_hole": 0.25,
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
    """A KiCad net_settings class dict. Diff classes carry the impedance
    geometry; POWER widens the track; Default is the JLC minimum."""
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
    """Add net_settings (classes + per-net patterns) to the carrier .kicad_pro,
    preserving the existing keys (ERC severities). The schematic flow owns the
    rest of the project file; this is additive."""
    data: dict = {}
    if pro_path.exists():
        data = json.loads(pro_path.read_text())
    data.setdefault("meta", {"filename": pro_path.name, "version": 3})
    data.setdefault("erc", {"rule_severities": {"pin_not_driven": "warning"}})

    # board.design_settings — the COMPLETE KiCad-10 design-settings block, not a
    # minimal subset. KiCad's GUI rewrites the WHOLE block (defaults / severities
    # / rules / teardrops / track+via+diff-pair tables / tuning / zones) on the
    # first save, so a partial emit shows the project DIRTY after every build/
    # open. Emitting the full block (the values KiCad would write) makes a GUI
    # open a no-op: build twice -> git diff empty on the .kicad_pro. The carrier
    # rules (min_hole_clearance 0.2 for USB-C NPTH posts, min_hole_to_hole 0.25)
    # are kept; every other key matches the KiCad 10 default so it round-trips.
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
    # a minimal pcbnew block so KiCad does not complain about a bare project
    data.setdefault("pcbnew", {"last_paths": {}, "page_layout_descr_file": ""})
    pro_path.write_text(json.dumps(data, indent=2) + "\n")


def write_dru(model: PcbModel, dru_path: Path) -> None:
    """A board-level .kicad_dru: default clearance/width minimums + the
    impedance-controlled diff geometry per class + a POWER track-width floor.
    Distinct from the schematic-flow layout_constraints.kicad_dru (which is the
    typed-port table); this one is keyed on the PCB net classes."""
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


# ---- entry point -----------------------------------------------------------------

def generate(*, run_drc: bool = True, two_side: bool = True,
             ratsnest: bool = True) -> dict:
    """Build + write the PCB foundation. Returns a result dict (paths, counts,
    drc verdict, LAW-5 ratsnest gate + images). ``two_side`` (default ON, the
    JLCPCB both-sides assembly policy) pushes decoupling/small passives to the
    bottom; set False for a forced single-side build (everything on top).
    ``ratsnest`` (default ON) emits the per-side ratsnest images + runs the
    LAW-5 placement gate on the SAME model (no rebuild)."""
    model = build_model(two_side=two_side)

    pcb_path = CARRIER / "Zynq_Carrier.kicad_pcb"
    emit_pcb(model, pcb_path)

    pro_path = CARRIER / "Zynq_Carrier.kicad_pro"
    write_project(model, pro_path)

    dru_path = CARRIER / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
    write_dru(model, dru_path)

    result = {
        "pcb": pcb_path, "pro": pro_path, "dru": dru_path,
        "board_w": model.board_w, "board_h": model.board_h,
        "placed": model.placed, "total": len(board_parts()),
        "nets": len([n for n in model.net_numbers if n]),
        "classes": sorted(model.classes), "deferred": model.deferred,
        "n_top": model.n_top, "n_bottom": model.n_bottom,
        "two_side": model.two_side, "som_keepout": model.som_keepout,
        "som_core": model.som_core,
        "drc": None, "ratsnest": None, "ratsnest_gate": None,
        "placement_mech": None,
        "connector_model": None, "connector_spacing": None,
        "refdes_silk": None,
    }
    if ratsnest:
        from schgen.generate import ratsnest as rn_mod
        from schgen.verify import (
            connector_model_gate,
            connector_spacing_gate,
            placement_mech,
            ratsnest_gate,
        )
        result["ratsnest"] = rn_mod.generate(model)
        result["ratsnest_gate"] = ratsnest_gate.check(model)
        # LAW-6 mechanical/use-case gate — runs on the SAME placed model (no
        # rebuild) so its connector-edge/orientation + SoM-keepout verdict is
        # exactly the board just emitted.
        result["placement_mech"] = placement_mech.check(model)
        # LAW-6 connector hardening (catch the recurring orientation + spacing
        # bug classes the other gates miss): 3D-model rotate must not flip the
        # rendered opening vs the pads, and simultaneous-mate cable connectors
        # (HDMI TX+RX) need an overmold gap.
        result["connector_model"] = connector_model_gate.check(model)
        result["connector_spacing"] = connector_spacing_gate.check(model)
        # LAW-1 silk: no two VISIBLE refdes overprint on EITHER side (the
        # _declutter_refdes invariant), proven on the just-emitted board file.
        from schgen.verify import refdes_overlap_gate
        result["refdes_silk"] = refdes_overlap_gate.check(
            pcb_path, enforce_bottom=True)
    if run_drc:
        result["drc"] = run_pcb_drc(pcb_path)
    return result


def run_pcb_drc(pcb_path: Path) -> dict:
    """Run kicad-cli pcb drc; classify violations. Unrouted-net violations are
    expected (no routing); clearance/overlap errors are not."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="schgen_drc_") as td:
        rpt = Path(td) / "drc.json"
        proc = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--format", "json",
             "--severity-error", "--severity-warning",
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
            # collect a few non-silk violation descriptions for the report
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
