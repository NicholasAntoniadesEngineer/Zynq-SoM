from __future__ import annotations

import importlib
from dataclasses import dataclass

STEP_KIND = "STEP"
CALC_KIND = "CALC"
ASSUME_KIND = "ASSUME"
REPLAY_KIND = "REPLAY"

SOURCE_CLASSES = ("physical", "datasheet", "standard", "policy", "fitted")
BASIS_MAX_CHARS = 88
NAME_WIDTH = 30
VALUE_WIDTH = 13
INDENT_UNIT = "  "
DECIMALS = 4
FIRST_INDEX = 0
SHADOW_BUFFER = 1

MODULE_ALIAS: dict[str, str] = {
    "config": "schgen.core.config",
    "quantize": "schgen.core.quantize",
    "floorplan": "schgen.generate.floorplan",
    "pcbconst": "schgen.generate.pcb.constants",
    "placement": "schgen.generate.pcb.placement",
    "stagetpl": "schgen.generate.pcb.stage_templates",
    "escape": "schgen.generate.pcb.escape",
    "fanout": "schgen.verify.fanout_gate",
    "ratsnest": "schgen.verify.ratsnest_gate",
}

STEP_PARENT: dict[str, tuple[str, ...]] = {
    "netlist": ("",),
    "link": ("",),
    "floorplan.sizing": ("", "docs.floorplan"),
    "sizing.pass": ("floorplan.sizing",),
    "pcb.placement": ("",),
    "pcb.escape": ("",),
    "pcb.emission": ("",),
    "gates": ("",),
    "docs.floorplan": ("",),
    "census": ("",),
}

REPLAYABLE = ("floorplan.sizing",)


@dataclass(frozen=True)
class Declaration:
    name: str
    kind: str
    step: str
    unit: str
    basis: str
    source: str = ""
    covers: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    expr: str = ""
    repeated: bool = False


@dataclass(frozen=True)
class Entry:
    kind: str
    depth: int
    name: str
    text: str


REGISTRY: dict[str, Declaration] = {}
ORDER: list[str] = []


def _check(name: str, step: str, basis: str) -> None:
    if name in REGISTRY:
        raise AssertionError(f"ledger: duplicate declaration {name!r}")
    if step not in STEP_PARENT:
        raise AssertionError(f"ledger: {name!r} declares unknown step {step!r}")
    if len(basis) > BASIS_MAX_CHARS:
        raise AssertionError(
            f"ledger: {name!r} basis is {len(basis)} chars > "
            f"{BASIS_MAX_CHARS} — the ledger carries data, not prose")


def _assume(name: str, step: str, covers: str, unit: str, source: str,
            basis: str) -> None:
    _check(name, step, basis)
    if source not in SOURCE_CLASSES:
        raise AssertionError(
            f"ledger: {name!r} declares source class {source!r}, not one of "
            f"{SOURCE_CLASSES} — a policy number may not present as physical")
    REGISTRY[name] = Declaration(name=name, kind=ASSUME_KIND, step=step,
                                 unit=unit, basis=basis, source=source,
                                 covers=(covers,))
    ORDER.append(name)


def _calc(name: str, step: str, unit: str, inputs: tuple[str, ...], expr: str,
          basis: str, covers: tuple[str, ...] = (),
          repeated: bool = False) -> None:
    _check(name, step, basis)
    if not inputs or not expr:
        raise AssertionError(
            f"ledger: calculation {name!r} needs named inputs and an "
            f"expression — a result nobody can recompute is not a ledger line")
    REGISTRY[name] = Declaration(name=name, kind=CALC_KIND, step=step,
                                 unit=unit, basis=basis, covers=covers,
                                 inputs=inputs, expr=expr, repeated=repeated)
    ORDER.append(name)


def _num(v: object) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{round(v, DECIMALS):.{DECIMALS}f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-") else "0"
    return str(v)


_ENTRIES: list[Entry] = []
_STACK: list[tuple[str, int]] = []
_DONE: dict[str, tuple[str, ...]] = {}
_SHADOW: list[object] = ["", []]
_SEEN: set[str] = set()
_PROBLEMS: list[str] = []


def reset() -> None:
    _ENTRIES.clear()
    _STACK.clear()
    _DONE.clear()
    _SEEN.clear()
    _PROBLEMS.clear()
    _SHADOW[:] = ["", []]


def _sink() -> list[Entry]:
    return (_SHADOW[SHADOW_BUFFER] if _SHADOW[FIRST_INDEX]
            else _ENTRIES)  # type: ignore[return-value]


def _depth() -> int:
    return len(_STACK)


def _append(kind: str, name: str, body: str) -> None:
    d = _depth()
    _sink().append(Entry(kind=kind, depth=d, name=name,
                         text=f"{INDENT_UNIT * d}{kind:<6} {body}"))


def _resolve(path: str) -> object:
    alias, _dot, attr = path.partition(".")
    module = MODULE_ALIAS.get(alias)
    if module is None:
        raise AssertionError(f"ledger: unknown module alias in {path!r}")
    return getattr(importlib.import_module(module), attr)


def _emit_assumptions(step: str) -> None:
    for name in ORDER:
        d = REGISTRY[name]
        if d.kind != ASSUME_KIND or d.step != step:
            continue
        value = _num(_resolve(d.covers[FIRST_INDEX]))
        _SEEN.add(name)
        _append(ASSUME_KIND, name,
                f"{name:<{NAME_WIDTH}} = {value:<{VALUE_WIDTH}} {d.unit:<10} "
                f"[{d.source}] {d.covers[FIRST_INDEX]} — {d.basis}")


def open_step(name: str, label: str = "") -> None:
    parents = STEP_PARENT.get(name)
    if parents is None:
        raise AssertionError(f"ledger: undeclared step {name!r}")
    here = _STACK[-1][FIRST_INDEX] if _STACK else ""
    if here not in parents:
        raise AssertionError(
            f"ledger: step {name!r} declares parents {parents} but opened "
            f"under {here!r} — the ledger order is the execution order")
    if not _SHADOW[FIRST_INDEX] and name in _DONE and name in REPLAYABLE:
        _SHADOW[:] = [name, []]
    _append(STEP_KIND, name, f"{name}{'  ' + label if label else ''}")
    _STACK.append((name, len(_sink())))
    _emit_assumptions(name)


def _first_diff(a: tuple, b: tuple) -> str:
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return f"line {i}: pass1 {x!r} vs pass2 {y!r}"
    return f"length {len(a)} vs {len(b)}"


def close_step(name: str) -> None:
    if not _STACK or _STACK[-1][FIRST_INDEX] != name:
        raise AssertionError(f"ledger: close {name!r} with stack {_STACK}")
    _open_name, start = _STACK.pop()
    base = _depth()
    body = tuple((e.depth - base, e.text.lstrip())
                 for e in _sink()[start:])
    if _SHADOW[FIRST_INDEX] == name:
        first = _DONE[name]
        same = body == first
        _SHADOW[:] = ["", []]
        if not same:
            _PROBLEMS.append(
                f"replay of step {name!r} diverged from its first pass — the "
                f"doc pass and the shipped pass do not agree: "
                f"{_first_diff(first, body)}")
        _append(REPLAY_KIND, name,
                f"{name} pass=2 identical={'yes' if same else 'NO'} "
                f"lines={len(body)}")
        return
    if name not in _DONE:
        _DONE[name] = body


class _Step:
    def __init__(self, name: str, label: str) -> None:
        self.name, self.label = name, label

    def __enter__(self) -> _Step:
        open_step(self.name, self.label)
        return self

    def __exit__(self, *exc: object) -> None:
        close_step(self.name)


def step(name: str, label: str = "") -> _Step:
    return _Step(name, label)


def calc(name: str, result: object, label: str = "", **inputs: object) -> None:
    d = REGISTRY.get(name)
    if d is None or d.kind != CALC_KIND:
        raise AssertionError(
            f"ledger: {name!r} was recorded but is not a declared calculation "
            f"— declare it in schgen/core/ledger.py before it may influence "
            f"the board")
    here = _STACK[-1][FIRST_INDEX] if _STACK else ""
    if here != d.step:
        raise AssertionError(
            f"ledger: calculation {name!r} is declared under step {d.step!r} "
            f"but was recorded under {here!r}")
    if tuple(inputs) != d.inputs:
        raise AssertionError(
            f"ledger: calculation {name!r} declares inputs {d.inputs} but was "
            f"recorded with {tuple(inputs)} — inputs may not drift silently")
    if name in _SEEN and not d.repeated and not _SHADOW[FIRST_INDEX]:
        _PROBLEMS.append(f"calculation {name!r} recorded more than once")
    _SEEN.add(name)
    shown = f"{name}[{label}]" if label else name
    ins = " ".join(f"{k}={_num(v)}" for k, v in inputs.items())
    _append(CALC_KIND, name,
            f"{shown:<{NAME_WIDTH}} = {_num(result):<{VALUE_WIDTH}} "
            f"{d.unit:<10} <- {ins}  ::  {d.expr}")


def entries() -> tuple[Entry, ...]:
    return tuple(_ENTRIES)


def problems() -> tuple[str, ...]:
    return tuple(_PROBLEMS) + tuple(
        f"step {n!r} was never closed" for n, _i in _STACK)


def recorded() -> frozenset[str]:
    return frozenset(_SEEN)


def render() -> str:
    return "\n".join(e.text for e in _ENTRIES)


_assume("schematic_char_width", "netlist", "config.CHAR_W", "mm/char",
        "policy", "symbol-text advance used by the schematic placer")
_assume("schematic_overlap_max", "netlist", "config.MISPLACED_OVERLAP", "mm",
        "policy", "largest symbol-body overlap the schematic gate tolerates")
_assume("schematic_clearance", "netlist", "config.VISUAL_CLEARANCE_MM", "mm",
        "policy", "wire-to-body clearance the visual gate enforces")
_assume("route_factor", "netlist", "floorplan.ROUTE_FACTOR", "x", "policy",
        "small-part area inflation that turns schematic area into zone area")
_assume("big_part_area", "netlist", "floorplan.BIG_PART_MM2", "mm^2", "policy",
        "footprint area above which route_factor no longer inflates")

_calc("sheet_census", "netlist", "sheets",
      ("n_sheets", "n_som_j", "n_decoupling"),
      "n_sheets - n_som_j - n_decoupling",
      "subsystem sheets the board is assembled from")

_calc("board_net_census", "link", "nets",
      ("n_sheet_nets", "n_som_contract_nets", "n_cross_sheet"),
      "len(union(sheet nets, som contract nets))",
      "net population the estimator and the ratsnest gate both walk")

_assume("edge_margin", "floorplan.sizing", "floorplan.EDGE_MARGIN", "mm",
        "policy", "edge-run keep-in from each board corner")
_assume("mh_corner_keepout", "floorplan.sizing", "floorplan.MH_CORNER_KO",
        "mm", "policy", "M3 corner mounting-hole exclusion square")
_assume("edge_depth_cap", "floorplan.sizing", "floorplan.EDGE_DEPTH_CAP", "mm",
        "policy", "deepest inboard reach allowed to an edge block")
_assume("edge_band_relief", "floorplan.sizing", "floorplan.EDGE_BAND_RELIEF",
        "mm", "policy", "seed-outline relief subtracted from edge_depth_cap")
_assume("edge_inset", "floorplan.sizing", "floorplan.EDGE_INSET", "mm",
        "policy", "connector face inset from the board outline")
_assume("cable_neighbor_gap", "floorplan.sizing",
        "floorplan.CABLE_NEIGHBOR_GAP", "mm", "physical",
        "clear span between two overmolded cable plugs, charged ONCE per pair")
_assume("overmold_plug_width", "floorplan.sizing",
        "floorplan.OVERMOLD_PLUG_W_MAX", "mm", "physical",
        "widest HDMI overmold shell a mated cable presents")
_assume("overmold_copper_half_width", "floorplan.sizing",
        "floorplan.OVERMOLD_COPPER_HALF_W", "mm", "physical",
        "half the receptacle copper footprint the shell overhangs")
_assume("block_clearance", "floorplan.sizing", "floorplan.CLEAR", "mm",
        "policy", "minimum gap between two packed subsystem zones")
_assume("perimeter_keepout", "floorplan.sizing", "floorplan.PERIM_KEEPOUT",
        "mm", "policy", "seed-outline perimeter band added on every side")
_assume("som_halo", "floorplan.sizing", "floorplan.SOM_HALO", "mm", "policy",
        "keepout ring around the SoM body in the floorplan frame")
_assume("pack_efficiency", "floorplan.sizing", "floorplan.PACK_EFFICIENCY",
        "ratio", "fitted", "seed-outline area fill; the real pack re-proves it")
_assume("occ_top_mask", "floorplan.sizing", "floorplan.OCC_TOP", "bitmask",
        "policy", "occupancy bit for the top copper face")
_assume("occ_bottom_mask", "floorplan.sizing", "floorplan.OCC_BOTTOM",
        "bitmask", "policy", "occupancy bit for the bottom copper face")
_assume("occ_step", "floorplan.sizing", "floorplan.OCC_STEP_MM", "mm",
        "policy", "candidate-pose lattice step of the occupancy search")
_assume("frontier_half", "floorplan.sizing", "floorplan.FRONTIER_HALF_MM",
        "mm", "policy", "half-width of the place_near frontier bucket")
_assume("som_seat_band", "floorplan.sizing", "floorplan.SOM_SEAT_BAND_MM",
        "mm", "policy", "band reserved around each DF40 receptacle")
_assume("som_occ_pad", "floorplan.sizing", "floorplan.SOM_OCC_PAD_MM", "mm",
        "policy", "pad grown around the SoM body rectangle when occupied")
_assume("anchor_zone_weight", "floorplan.sizing", "floorplan.ANCHOR_ZONE_W",
        "weight", "policy", "zone-centroid term of the interior seat anchor")
_assume("anchor_som_weight", "floorplan.sizing", "floorplan.ANCHOR_SOM_W",
        "weight", "policy", "SoM-pull term of the interior seat anchor")
_assume("anchor_affinity_power", "floorplan.sizing",
        "floorplan.ANCHOR_AFF_POW", "exponent", "policy",
        "exponent applied to net affinity in the seat anchor")
_assume("reseat_evict_budget", "floorplan.sizing",
        "floorplan._RESEAT_EVICT_BUDGET", "evictions", "policy",
        "successful eviction episodes one pack attempt may spend")
_assume("affinity_floor", "floorplan.sizing", "floorplan.AFFINITY_FLOOR",
        "affinity", "policy",
        "floor on every edge block's weight; it orders the zero-affinity ones")
_assume("placeholder_aspect", "floorplan.sizing",
        "floorplan.PLACEHOLDER_ASPECT", "w/h", "policy",
        "target width/height of a reservation-only block's landing rectangle")
_assume("placeholder_min", "floorplan.sizing", "floorplan.PLACEHOLDER_MIN_MM",
        "mm", "policy", "shortest side a placeholder landing rectangle may take")
_assume("placeholder_max", "floorplan.sizing", "floorplan.PLACEHOLDER_MAX_MM",
        "mm", "policy",
        "tallest a placeholder rectangle grows before it is widened instead")
_assume("cross_k", "floorplan.sizing", "config.CROSS_K",
        "mm/mm/subsystem", "fitted",
        "LAW-5 airwire coefficient, fitted from two boards; NOT a physical law")
_assume("dispersion_max", "floorplan.sizing", "ratsnest.DISPERSION_MAX", "x",
        "policy", "worst cluster bbox/ideal ratio the LAW-5 gate accepts")
_assume("dispersion_small_n", "floorplan.sizing", "ratsnest.SMALL_N", "parts",
        "policy", "cluster size below which dispersion is not judged")

_assume("place_grid", "floorplan.sizing", "quantize.GRID_MM", "mm", "standard",
        "KiCad placement grid the emitted SoM-J and MH poses snap to")
_assume("half_grid", "floorplan.sizing", "quantize.HALF_MM", "mm", "policy",
        "coarse 0.5 mm quantum of the legalizer and the SoM pose")
_assume("quant_credit", "floorplan.sizing", "quantize.CREDIT_MM", "mm",
        "policy", "credit that keeps a proven reach from rounding away")
_assume("snap_erosion", "floorplan.sizing", "quantize.SNAP_EROSION_MM", "mm",
        "policy", "declared margin on template bounds >= 5 mm")
_assume("seat_slide", "floorplan.sizing", "quantize.SEAT_SLIDE_MM", "mm",
        "policy", "edge-seat courtyard-to-pad-flush slide allowance")
_assume("outline_snap", "floorplan.sizing", "quantize.OUTLINE_SNAP_MM", "mm",
        "policy", "coarse outline grid every candidate board rounds up to")
_assume("refine_span", "floorplan.sizing", "quantize.REFINE_SPAN_MM", "mm",
        "policy", "window below the aspect-best that the fine scan sweeps")
_assume("fine_snap", "floorplan.sizing", "quantize.FINE_SNAP_MM", "mm",
        "policy", "fine outline grid; packing feasibility is jagged at 1 mm")
_assume("via_size", "floorplan.sizing", "quantize.VIA_SIZE_MM", "mm",
        "physical", "via barrel diameter charged by the sizing estimator")
_assume("via_clearance", "floorplan.sizing", "quantize.VIA_CLEAR_MM", "mm",
        "physical", "annulus each via barrel takes out of a routing channel")
_assume("stack_thickness", "floorplan.sizing", "quantize.STACK_THICKNESS_MM",
        "mm", "datasheet", "JLC04161H-7628 4-layer finished thickness")

_assume("zone_pad", "floorplan.sizing", "pcbconst.ZONE_PAD", "mm", "policy",
        "pad kept between a zone box and the parts packed inside it")
_assume("place_clear_baseline", "floorplan.sizing",
        "pcbconst.PLACE_CLEAR_BASELINE", "mm", "policy",
        "shipped part-to-part clearance floor inside a zone")
_assume("place_clear", "floorplan.sizing", "pcbconst.PLACE_CLEAR", "mm",
        "policy", "part-to-part clearance in force (SCHGEN_PLACE_CLEAR)")
_assume("zone_pack_fill", "floorplan.sizing", "pcbconst.ZONE_PACK_FILL",
        "ratio", "fitted", "shelf-pack target fill that sets each zone aspect")
_assume("zone_step", "floorplan.sizing", "pcbconst.ZONE_STEP", "mm",
        "standard", "0.1 inch zone lattice pitch")
_assume("edge_zone_aspect", "floorplan.sizing", "pcbconst.EDGE_ZONE_ASPECT",
        "w/h", "policy", "target width/height of a connector-bearing zone")
_assume("interior_zone_aspect", "floorplan.sizing",
        "pcbconst.INTERIOR_ZONE_ASPECT", "w/h", "policy",
        "target width/height of an interior zone")
_assume("interior_band_target", "floorplan.sizing",
        "pcbconst.INTERIOR_ZONE_BAND_TARGET", "mm", "policy",
        "band height an interior zone aims to fit")
_assume("som_side_band", "floorplan.sizing", "pcbconst.SOM_SIDE_BAND_MM", "mm",
        "policy", "usable band beside the SoM body")
_assume("som_decoupling_inset", "floorplan.sizing",
        "placement.SOM_DECOUPLING_INSET", "mm", "policy",
        "inset of the bottom-side decoupling grid inside the SoM shadow")
_assume("d13_min_subject_pins", "floorplan.sizing", "fanout.MIN_SUBJECT_PINS",
        "pins", "policy", "pin count below which a part gets no D13 reach")
_assume("d13_df40_min_pins", "floorplan.sizing", "fanout.DF40_MIN_PINS",
        "pins", "physical", "pin count that identifies a DF40 receptacle")

_calc("overmold_side_gap", "floorplan.sizing", "mm",
      ("plug_width", "copper_half_width"),
      "plug_width / 2 - copper_half_width",
      "shell overhang beside a single receptacle",
      covers=("floorplan.OVERMOLD_SIDE_GAP",))
_calc("edge_band", "floorplan.sizing", "mm",
      ("edge_depth_cap", "edge_band_relief"),
      "edge_depth_cap - edge_band_relief",
      "connector band width used by the seed outline",
      covers=("floorplan.EDGE_BAND",))
_calc("occ_punch_mask", "floorplan.sizing", "bitmask",
      ("occ_top", "occ_bottom"), "occ_top | occ_bottom",
      "occupancy bits of geometry that pierces both faces",
      covers=("floorplan.OCC_PUNCH",))
_calc("est_via_ordinary", "floorplan.sizing", "mm",
      ("via_size", "via_clearance"), "2 * (via_size + 2 * via_clearance)",
      "channel an ordinary layer change costs the sizing estimator",
      covers=("quantize.EST_VIA_ORDINARY_MM",))
_calc("est_via_impedance", "floorplan.sizing", "mm",
      ("via_size", "via_clearance", "stack_thickness"),
      "2 * 2 * (via_size + 2 * via_clearance) + 2 * stack_thickness",
      "channel a controlled-impedance pair change costs the estimator")
_calc("est_via_class_split", "floorplan.sizing", "nets",
      ("n_cross_nets", "n_impedance", "n_ordinary", "impedance_classes"),
      "n_impedance = count(net whose class carries a DiffGeometry)",
      "which nets are charged the impedance via row, and which are not")
_calc("subsystem_count", "floorplan.sizing", "subsystems",
      ("n_sheets", "n_som_j", "n_mechanical_only"),
      "n_sheets - n_som_j - n_mechanical_only",
      "LAW-5 budget multiplier; a sheet miscount rescales the whole budget")
_calc("seed_outline", "floorplan.sizing", "mm",
      ("som_w", "som_h", "som_halo", "edge_band", "component_area",
       "pack_efficiency", "perimeter_keepout", "seed_w", "seed_h"),
      "max(som+2*halo+2*band, sqrt(area/fill + keepout_area) * aspect) "
      "+ 2 * perimeter_keepout, snapped up to outline_snap",
      "starting outline the aspect search grows from")
_calc("d13_tier_population", "floorplan.sizing", "parts",
      ("n_subjects", "tier_le2_0p20", "tier_le8_1p50", "tier_ge9_2p00"),
      "intelligent_need(pins): pins<=2 -> 0.20, pins<=8 -> 1.50, else 2.00",
      "how many parts each D13 fan-out tier actually governed")
_calc("decoupling_grid", "floorplan.sizing", "caps",
      ("n_caps", "som_w", "som_h", "inset", "grid_w", "grid_h", "cols",
       "rows"),
      "grid = som - 2*inset; cols = max(1, min(n, round(sqrt(n*gw/gh)))); "
      "rows = ceil(n / cols)",
      "the decoupling grid the sizing estimator prices under the SoM")

_calc("outline_candidates", "sizing.pass", "candidates",
      ("generated", "reject_aspect", "reject_min_area", "reject_not_smaller",
       "reject_pack", "reject_law5_budget", "accepted"),
      "generated = reject_aspect + reject_min_area + reject_not_smaller "
      "+ reject_pack + reject_law5_budget + accepted",
      "every candidate outline this pass judged, and why each was dropped",
      repeated=True)
_calc("law5_airwire_budget", "sizing.pass", "mm",
      ("cross_k", "board_w", "board_h", "n_subsystems"),
      "cross_k * (board_w * board_h) ** 0.5 * n_subsystems",
      "LAW-5 budget at the winning outline of this pass", repeated=True)
_calc("pass_winner", "sizing.pass", "mm",
      ("board_w", "board_h", "area", "est_cross", "budget", "headroom"),
      "headroom = budget - est_cross",
      "smallest-area outline this pass could prove", repeated=True)

_calc("side_choice", "floorplan.sizing", "side",
      ("offered", "est_incumbent", "est_challenger", "margin"),
      "challenger wins iff est_challenger < est_incumbent - 1e-6",
      "per-block copper-face decision, judged by the airwire estimator",
      repeated=True)
_calc("side_fixed", "floorplan.sizing", "side",
      ("offered", "shape_idx"),
      "one face survived place_near, so no estimator judgement was made",
      "per-block face that had no alternative to weigh", repeated=True)
_calc("side_census", "floorplan.sizing", "blocks",
      ("n_blocks", "n_two_face", "n_chose_bottom", "n_single_face"),
      "n_blocks = n_two_face + n_single_face",
      "how many blocks were offered a second copper face, and what won")
_calc("plan_choice", "floorplan.sizing", "plan",
      ("conservative_area", "conservative_est", "free_area", "free_est"),
      "keep free iff free_area < conservative_area or (equal area and "
      "free_est < conservative_est)",
      "which bottom-surface reservation model sized the shipped board")
_calc("sizing_winner", "floorplan.sizing", "mm",
      ("board_w", "board_h", "area", "est_cross", "budget", "headroom",
       "plan"),
      "headroom = budget - est_cross",
      "the outline the shipped board is built on",
      covers=("floorplan.BOARD_W", "floorplan.BOARD_H"))

_assume("origin_x", "pcb.placement", "pcbconst.ORIGIN_X", "mm", "policy",
        "page-frame origin the board rectangle is drawn from")
_assume("origin_y", "pcb.placement", "pcbconst.ORIGIN_Y", "mm", "policy",
        "page-frame origin the board rectangle is drawn from")
_assume("mh_inset", "pcb.placement", "pcbconst.MH_INSET", "mm", "policy",
        "corner mounting-hole centre inset from the board edge")
_assume("mh_keepout", "pcb.placement", "pcbconst.MH_KEEPOUT", "mm", "policy",
        "copper keepout radius around a mounting hole")
_assume("fiducial_inset", "pcb.placement", "pcbconst.FID_INSET", "mm",
        "policy", "fiducial centre inset from the board corner")
_assume("perimeter_band", "pcb.placement", "pcbconst.PERIM", "mm", "policy",
        "PCB-frame perimeter band kept clear of parts")
_assume("som_halo_pcb", "pcb.placement", "pcbconst.SOM_HALO_PCB", "mm",
        "policy", "keepout ring around the SoM body in the PCB frame")
_assume("som_core_clearance", "pcb.placement", "pcbconst.SOM_CORE_CLEARANCE",
        "ratio", "policy", "fractional grow of the SoM core rectangle")
_assume("edge_band_pcb", "pcb.placement", "pcbconst.EDGE_BAND_PCB", "mm",
        "policy", "PCB-frame band reserved for edge-seated blocks")
_assume("board_edge_margin", "pcb.placement", "pcbconst.BOARD_EDGE_MARGIN",
        "mm", "policy", "part-body keep-in from the board outline")
_assume("som_zone_grow", "pcb.placement", "pcbconst.SOM_ZONE_GROW", "mm",
        "policy", "grow applied to the SoM keepout by breathe and escape")
_assume("outline_grow_pcb", "pcb.placement", "pcbconst.OUTLINE_GROW", "mm",
        "policy", "PCB-frame outline grow step")
_assume("edge_pad_clear", "pcb.placement", "pcbconst.EDGE_PAD_CLEAR", "mm",
        "policy", "copper-to-outline clearance at a seated connector pad")
_assume("button_gap", "pcb.placement", "pcbconst.BUTTON_GAP", "mm", "policy",
        "finger clearance kept around a user-pressed button")
_assume("top_area_max", "pcb.placement", "pcbconst.TOP_AREA_MM2", "mm^2",
        "policy", "footprint area above which a part stays on the top face")
_assume("iso_void_margin", "pcb.placement", "pcbconst.ISO_VOID_MARGIN", "mm",
        "policy", "plane void margin around an isolation barrier part")
_assume("conn_rest_gap", "pcb.placement", "placement.CONN_REST_GAP", "mm",
        "policy", "gap behind a connector row before the rest of the zone")
_assume("disp_cap_l4", "pcb.placement", "placement.DISP_CAP_L4", "x",
        "policy", "dispersion ceiling the L4 bottom pull may not exceed")
_assume("l4_pull_step", "pcb.placement", "placement.L4_PULL_STEP", "mm",
        "policy", "step the L4 pull walks a part inboard by")
_assume("l4_pull_span", "pcb.placement", "placement.L4_PULL_SPAN", "mm",
        "policy", "furthest the L4 pull will move a part")
_assume("d13_touch_eps", "pcb.placement", "fanout._TOUCH_EPS", "mm", "policy",
        "tolerance below which a D13 clearance counts as met")
_assume("edge_flush_relief", "pcb.placement", "pcbconst.EDGE_FLUSH_RELIEF",
        "mm", "policy", "body relief added to edge_pad_clear when seating")
_assume("nonsw_relief", "pcb.placement", "stagetpl._NONSW_RELIEF", "mm",
        "policy", "gap added to template_clear between two non-switching stages")
_assume("candidate_radius", "pcb.placement", "stagetpl._CAND_RADIUS", "mm",
        "policy", "reach of the template candidate lattice around its pin box")
_assume("relax_step", "pcb.placement", "stagetpl._RELAX_STEP", "mm", "policy",
        "clearance a template solve adds per failed attempt before it retries")
_assume("ind_body_gap", "pcb.placement", "stagetpl._IND_BODY_GAP", "mm",
        "policy", "gap from the buck IC courtyard to the inductor body")
_assume("ldo_cap_gap", "pcb.placement", "stagetpl._LDO_GAP", "mm", "policy",
        "gap from an LDO pin box to its input or output capacitor")
_assume("cout_column_gap", "pcb.placement", "stagetpl._COUT_GAP", "mm",
        "policy", "gap from the inductor output pad to the output-cap column")
_assume("leftover_band_gap", "pcb.placement", "stagetpl._LEFTOVER_BAND_GAP",
        "mm", "policy", "gap below the stage rows where leftover parts are banded")
_assume("interstage_sw_gap", "pcb.placement", "stagetpl._INTERSTAGE_GAP0", "mm",
        "policy", "gap between two adjacent stages that BOTH carry a switching node")
_assume("row_width_budget", "pcb.placement", "stagetpl._ROW_WIDTH_BUDGET", "mm",
        "policy", "width above which a candidate stage-row layout is rejected")
_assume("interrow_buck_gap", "pcb.placement", "stagetpl._INTERROW_BUCK_GAP",
        "mm", "policy", "row-to-row gap when both rows contain a switching stage")
_assume("candidate_step", "pcb.placement", "stagetpl._CAND_STEP", "mm",
        "policy", "lattice step the template candidate search walks")
_assume("candidate_cap", "pcb.placement", "stagetpl._CAND_CAP", "candidates",
        "policy", "length the scored candidate list is truncated to")
_assume("template_node_budget", "pcb.placement", "stagetpl._NODE_BUDGET",
        "nodes", "policy",
        "search nodes one template backtrack may spend before it gives up")
_assume("root_row_gap", "pcb.placement", "stagetpl._ROOT_GAP", "mm", "policy",
        "gap between two consecutive ordinary parts in the root row")
_assume("conn_root_cable_gap", "pcb.placement",
        "stagetpl._CONN_ROOT_CABLE_GAP", "mm", "physical",
        "clear span between two overmolded plugs; independent of floorplan by test")
_assume("net_align_weight", "pcb.placement", "stagetpl._NET_W", "weight",
        "policy", "weight on the net-alignment term of the candidate score")
_assume("grid_max_steps", "pcb.placement", "stagetpl._GRID_MAX_N", "steps",
        "policy", "cap on the half-width, in steps, of the candidate lattice")
_assume("flip_min_pins", "pcb.placement", "stagetpl._FLIP_MIN_PINS", "pins",
        "policy", "pin count below which the SoM-facing flip heuristic does not run")
_assume("flip_symmetry_tol", "pcb.placement", "stagetpl._FLIP_SYM_TOL", "mm",
        "policy", "tolerance for judging a pad set 180-degree symmetric")
_assume("flip_dominance_pct", "pcb.placement", "stagetpl._FLIP_DOM_PCT",
        "percent", "policy",
        "share of inter-sheet nets one DF40 must own to be called the flip partner")

_calc("edge_flush", "pcb.placement", "mm",
      ("edge_pad_clear", "flush_relief"), "edge_pad_clear + flush_relief",
      "body-to-outline offset of a pad-flush seated connector",
      covers=("pcbconst.EDGE_FLUSH_MM",))
_calc("template_clear", "pcb.placement", "mm", ("place_clear_baseline",),
      "place_clear_baseline",
      "clearance the rigid stage templates are solved at",
      covers=("pcbconst.TEMPLATE_CLEAR",))
_calc("nonsw_stage_gap", "pcb.placement", "mm",
      ("template_clear", "nonsw_relief"), "template_clear + nonsw_relief",
      "gap between two adjacent stages when at most one carries a switching node",
      covers=("stagetpl._NONSW_STAGE_GAP",))
_calc("stage_movement", "pcb.placement", "parts",
      ("l4_pull", "edge_seat", "breathe", "refit_facing", "reorder",
       "corridor_eviction"),
      "parts whose pose a stage changed, counted per stage",
      "which post-plan stage moved how many parts")

_assume("obstacle_margin", "pcb.escape", "escape.OBSTACLE_MARGIN", "mm",
        "policy", "how far past the DF40 contact row the solver reads obstacles")
_assume("corridor_lip", "pcb.escape", "escape.CORRIDOR_LIP", "mm", "policy",
        "outer lip past the escape depth when the lane corridor is cut")
_assume("escape_construct_radius", "pcb.escape", "escape.R_CONSTRUCT", "mm",
        "policy", "reach from a DF40 contact within which a via counts as covering it")
_assume("escape_lattice", "pcb.escape", "escape.LATTICE_MM", "mm", "policy",
        "step of the lattice the escape solver searches via positions on")
_assume("escape_clearance_margin", "pcb.escape", "escape.CLR_MARGIN", "mm",
        "policy", "margin added over the net-class rule when testing a foreign box")
_assume("hole_to_foreign_pad", "pcb.escape", "escape.CLR_HOLE_FOREIGN", "mm",
        "policy", "house floor from an escape via hole to a foreign pad")
_assume("clr_hole_hole_relief", "pcb.escape", "escape.CLR_HOLE_HOLE_RELIEF",
        "mm", "policy",
        "relief the escape solver adds over the thermal via hole-to-hole floor")
_assume("track_to_foreign", "pcb.escape", "escape.CLR_TRACK_FOREIGN", "mm",
        "policy", "house floor from an escape track edge to foreign copper")
_assume("escape_edge_clearance", "pcb.escape", "escape.CLR_EDGE", "mm",
        "policy", "copper-to-edge figure REPORTED in the escape audit, never enforced")
_assume("via_to_contact_row", "pcb.escape", "escape.CLR_VIA_ROW", "mm",
        "policy", "house floor from an escape via to the DF40 contact row")
_assume("coexistence_margin", "pcb.escape", "escape.COEX_MARGIN", "mm",
        "policy",
        "margin grown around the DF40 body when testing bottom-side coexistence")
_assume("contact_pitch_tolerance", "pcb.escape", "escape.PITCH_TOL_MM", "mm",
        "fitted",
        "set from measured DF40 column gaps straying 2e-4 on the 1e-4 export grid")
_assume("escape_spine_width", "pcb.escape", "escape.SPINE_W", "mm", "policy",
        "track width of the GND spine the escape copper lays")
_assume("escape_stub_pair_width", "pcb.escape", "escape.STUB_W_PAIR", "mm",
        "policy", "track width of an escape stub serving a differential pair")
_assume("escape_stub_single_width", "pcb.escape", "escape.STUB_W_SINGLE", "mm",
        "policy", "track width of an escape stub serving a single-ended contact")
_assume("min_vias_per_connector", "pcb.escape", "escape.MIN_VIAS_PER_CONN",
        "vias", "policy", "return vias below which a DF40 gets a redundancy search")
_assume("redundancy_offset", "pcb.escape", "escape.REDUNDANCY_OFFSET", "mm",
        "policy", "offset each way the redundancy search walks to find a second via")
_assume("lane_handle", "pcb.escape", "escape.LANE_HANDLE", "mm", "policy",
        "escape depth past the outer contact-pad tip that a lane reserves")
_assume("corridor_v_margin", "pcb.escape", "escape.CORRIDOR_V_MARGIN", "mm",
        "policy",
        "margin past the outermost obstacle when the corridor half-height is set")

_calc("clr_hole_hole", "pcb.escape", "mm", ("thermal_via_h2h", "relief"),
      "thermal_via_h2h + relief",
      "escape-solver hole-to-hole floor; TIGHTEST of the three, placer-enforced",
      covers=("escape.CLR_HOLE_HOLE",))
_calc("escape_coverage", "pcb.escape", "mm",
      ("contacts", "worst_cover", "vias", "coverage"),
      "worst_cover = max over DF40 contacts of the uncovered span",
      "DF40 escape solve outcome that the return-stitch gate then judges")

_assume("power_track", "pcb.emission", "pcbconst.POWER_TRACK_MM", "mm",
        "policy", "POWER net-class track width written to the board")
_assume("power_clearance", "pcb.emission", "pcbconst.POWER_CLEARANCE_MM", "mm",
        "policy", "POWER net-class clearance written to the board")
_assume("default_track", "pcb.emission", "pcbconst.DEFAULT_TRACK_MM", "mm",
        "policy", "Default net-class track width written to the board")
_assume("default_clearance", "pcb.emission", "pcbconst.DEFAULT_CLEARANCE_MM",
        "mm", "policy", "Default net-class clearance written to the board")
_assume("gnd_plane_edge_back", "pcb.emission", "pcbconst.GND_PLANE_EDGE_BACK",
        "mm", "policy", "plane pull-back from the board outline")
_assume("gnd_plane_clearance", "pcb.emission", "pcbconst.GND_PLANE_CLEARANCE",
        "mm", "policy", "plane-to-copper clearance in the poured zones")
_assume("pour_clearance", "pcb.emission", "pcbconst.POUR_CLEARANCE", "mm",
        "policy", "thermal-pour clearance around a device pad")
_assume("zone_min_thickness", "pcb.emission", "pcbconst.ZONE_MIN_THICKNESS",
        "mm", "standard", "minimum poured copper sliver the fab will hold")
_assume("thermal_via_size", "pcb.emission", "pcbconst.THERMAL_VIA_SIZE", "mm",
        "standard", "thermal via pad diameter")
_assume("thermal_via_drill", "pcb.emission", "pcbconst.THERMAL_VIA_DRILL",
        "mm", "standard", "thermal via drill diameter")
_assume("thermal_via_clear", "pcb.emission", "pcbconst.THERMAL_VIA_CLEAR",
        "mm", "standard", "clearance ring around a thermal via")
_assume("hole_to_hole_fab", "pcb.emission", "pcbconst.HOLE_TO_HOLE_FAB", "mm",
        "datasheet",
        "JLCPCB 4-layer hole-to-hole floor; the ONE cited figure, see fab_profile")
_assume("hole_to_hole_drc_margin", "pcb.emission",
        "pcbconst.HOLE_TO_HOLE_DRC_MARGIN", "mm", "policy",
        "house margin over the fab floor carried by the board-wide DRC rule")
_assume("hole_to_hole_thermal_margin", "pcb.emission",
        "pcbconst.HOLE_TO_HOLE_THERMAL_MARGIN", "mm", "policy",
        "house margin over the fab floor carried by the thermal via field")
_assume("thermal_via_edge", "pcb.emission", "pcbconst.THERMAL_VIA_EDGE", "mm",
        "policy", "thermal via keep-in from the pour edge")
_assume("thermal_via_spacing", "pcb.emission", "pcbconst.THERMAL_VIA_SPACING",
        "mm", "policy", "preferred pitch of a thermal via field")
_assume("thermal_via_lattice", "pcb.emission",
        "pcbconst.THERMAL_VIA_LATTICE_PITCH", "mm", "policy",
        "exhaustive lattice pitch used when a curated site is blocked")
_assume("hole_to_samenet_pad", "pcb.emission", "pcbconst.CLR_HOLE_SAMENET_PAD",
        "mm", "standard", "hole-to-same-net-pad clearance rule")

_calc("min_hole_to_hole", "pcb.emission", "mm", ("fab_floor", "drc_margin"),
      "fab_floor + drc_margin",
      "emitted DRC floor; LOOSEST of the three — vendor footprints cap it at 0.3354",
      covers=("pcbconst.MIN_HOLE_TO_HOLE",))
_calc("thermal_via_h2h", "pcb.emission", "mm",
      ("fab_floor", "thermal_margin"), "fab_floor + thermal_margin",
      "placer floor for a thermal via field; tighter than the emitted DRC rule",
      covers=("pcbconst.THERMAL_VIA_H2H",))

_calc("board_emission", "pcb.emission", "footprints",
      ("board_w", "board_h", "placed", "n_top", "n_bottom", "nets"),
      "placed = n_top + n_bottom",
      "what the emitted kicad_pcb actually contains")

_calc("law5_airwire_measured", "gates", "mm",
      ("cross_mm", "budget_mm", "headroom_mm", "n_cross", "n_subsystems",
       "board_w", "board_h"),
      "budget_mm = cross_k * (board_w * board_h) ** 0.5 * n_subsystems",
      "the LAW-5 gate measured on the emitted board, not on an estimate")
_calc("fanout_d13_gate", "gates", "subjects",
      ("n_subjects", "n_starved", "baseline"),
      "starved = clearance < intelligent_need(pins) - touch_eps",
      "D13 fan-out verdict on the emitted board")

_assume("floorplan_svg_scale", "docs.floorplan", "floorplan.SCALE", "px/mm",
        "policy", "pixel scale of the FLOORPLAN.svg drawing")
_assume("floorplan_svg_origin_x", "docs.floorplan", "floorplan.OX", "px",
        "policy", "left origin the FLOORPLAN.svg board rectangle is drawn from")
_assume("floorplan_svg_origin_y", "docs.floorplan", "floorplan.OY", "px",
        "policy", "top origin the FLOORPLAN.svg board rectangle is drawn from")
_assume("svg_right_pad", "docs.floorplan", "floorplan.SVG_RIGHT_PAD", "px",
        "policy", "canvas padding right of the board before the legend column")
_assume("svg_legend_width", "docs.floorplan", "floorplan.SVG_LEGEND_W", "px",
        "policy", "width of the FLOORPLAN.svg legend column")
_assume("svg_bottom_pad", "docs.floorplan", "floorplan.SVG_BOTTOM_PAD", "px",
        "policy", "canvas padding below the board rectangle")
_assume("svg_legend_top", "docs.floorplan", "floorplan.SVG_LEGEND_TOP", "px",
        "policy", "y at which the legend rows start")
_assume("svg_legend_row", "docs.floorplan", "floorplan.SVG_LEGEND_ROW", "px",
        "policy", "height of one legend row")
_assume("svg_legend_tail", "docs.floorplan", "floorplan.SVG_LEGEND_TAIL", "px",
        "policy", "canvas padding below the last legend row")

_calc("quantize_engagement", "census", "calls", ("klass", "value"),
      "count of calls that ran this registered transform",
      "which registered quantizations actually engaged", repeated=True)
_calc("fallback_engagement", "census", "firings", ("stage", "ceiling"),
      "count of times this registered degraded path bound",
      "which registered fallbacks actually fired", repeated=True)
_calc("register_silence", "census", "registrations",
      ("quantize_registered", "quantize_engaged", "fallback_registered",
       "fallback_fired"),
      "registered - engaged = declared machinery this build never used",
      "declared-but-idle machinery, the other half of the census")
