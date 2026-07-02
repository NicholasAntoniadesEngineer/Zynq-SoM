"""PLACEMENT-CONTRACT gate — enforce a subsystem's datasheet layout contract on
the EMITTED board.

The defect this closes is invisible to ERC, DRC, the netlist gate AND the LAW-5
ratsnest/grouping gate: the PCB packer sorts a subsystem's passives by footprint
SIZE, so a buck's 100 nF hot-loop cap, its bulk input caps and its whole FB
divider land in a value-sorted grid on the BOTTOM side, far from the IC and its
switch node. The netlist is perfectly connected, every courtyard is on-board and
the cluster is contiguous — so no existing gate fires — yet the hot loop is
smeared across vias and the FB sense sits under the switching node. The layout
is electrically wrong in exactly the way the datasheet's layout section forbids.

A PLACEMENT CONTRACT (``subsystems/<name>/placement_contract.py``) encodes those
requirements as data — per structure (hot loop, bulk-in, bulk-out, SW node, FB
cluster, boot, VCC, BIAS, RT, LDO, same-side), each with a distance limit and a
``basis`` string (an SNVSBD5D citation or ``judgment:<value>``). THIS gate reads the
contract, maps its LIBRARY refs to the emitted board refs via the same per-sheet
band rename the netlist uses, and checks every structure against the placed
footprint geometry, reporting each violation with its refs/pins, the measured mm
and the basis.

DISTANCE MEASURE: pad-edge-to-pad-edge. Every pad of every relevant footprint is
transformed to an axis-aligned BOUNDING BOX in the board page frame (the
footprint placement rotation in KiCad's true CLOCKWISE / +y-down sign, plus the
F->B X-mirror for a bottom-side part — the SAME transform ``_inst_pad_geom`` /
``_rot_pad_bbox`` use, so the boxes land where KiCad's copper does, pad size and
rotation included). The distance between two pads is the gap between their boxes
(0 if they overlap). A part-to-pin distance is the MIN over the part's pads to
the target pin's box; a part-to-part distance the MIN over both pad sets.

HOT-LOOP is EXISTENTIAL PER PIN-PAIR: each buck's VIN/PGND pin-pair must have
SOME contract-listed 100 nF cap within the limit, on the same side as the IC.
The interchangeable HF caps are never checked per-ref (a valid swapped layout
must pass) — the gate checks the electrical requirement, not the ref binding.

LAW 4 (strict, no softening): a structure that fails is FIXED in the placer /
template (place the part where the datasheet requires), never waived here and
never made configurable to weaken it. Every measured distance is reported AS A
NUMBER in the verdict so a regression shows as a number, not a silent binary.

The module has NO import side effects and touches no global state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.generate.pcb import PcbModel

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBSYSTEMS_DIR = _REPO_ROOT / "subsystems"
_CARRIER_SUBSYSTEMS_DIR = _REPO_ROOT / "carrier" / "subsystems"

# The two package roots a placement contract can live under, tried in order: the
# portable top-level library first, then the carrier-local package (E1). A sheet
# name is unique across both (the sheet_index / discovery order proves it), so a
# name resolves to at most one contract.
_CONTRACT_ROOTS: tuple[tuple[Path, str], ...] = (
    (_SUBSYSTEMS_DIR, "subsystems"),
    (_CARRIER_SUBSYSTEMS_DIR, "carrier.subsystems"),
)

# ENGINE-WIRED sheets. A placement contract that merely EXISTS is authored data;
# it is only ENGINE-ACTIVE (drives the stage-template placer + the emit gate
# chain) once its sheet is listed here. This mirrors the SAME "power is the pilot"
# scoping already hard-wired in two peers: ``stage_templates.build_zone`` returns
# None unless ``subsystem == "power"``, and ``emit`` checks ``sheet_name="power"``.
# WHY: ``load_contract`` is consumed by the placer's same-side override (it forces
# every contract member to the IC side BEFORE packing). Until a sheet's TEMPLATE
# is wired, that override would perturb an un-templated zone's geometry for no
# gain (34 passives flip bottom->top, inflating the board) — so a contract stays
# INERT to the placer/emit until it is wired here. The FULL set of authored
# contracts is still discoverable for offline verification via ``discover_contract``
# / ``check_all`` (the red-on-before proof), which do NOT consult this gate.
#
# ``usb_pd`` (D11 wiring): the FUSB302B bypass/CC-filter network is a PROXIMITY-only
# contract driven by the generic proximity-cluster template (stage_templates
# ``_build_proximity_zone``); all 6 parts are contracted so its stage template is
# active and its intra-zone gate + external near_max (D11 edge-gap) are enforced.
_WIRED_SHEETS: frozenset[str] = frozenset({"power", "usb_pd"})


# --- contract registry ------------------------------------------------------------
# ``discover_contract(sheet)`` resolves the plain-data CONTRACT dict for ANY sheet
# that carries a ``placement_contract.py`` under either root (E1) — pure authored
# data, no wiring gate. ``load_contract(sheet)`` is the ENGINE-FACING entry: it
# returns the contract ONLY for an engine-WIRED sheet (see ``_WIRED_SHEETS``), so
# the placer/emit stay byte-identical to the pilot until a sheet is wired. Both
# import ``<root>.<sheet>.placement_contract`` and read its ``CONTRACT`` constant.

def discover_contract(sheet_name: str) -> dict | None:
    """Resolve ``<root>/<sheet>/placement_contract.py``'s ``CONTRACT`` dict for
    ANY authored contract (no wiring gate), or None if no root carries one. Both
    the portable ``subsystems/`` library and the carrier-local
    ``carrier/subsystems/`` package are searched (E1). Used by ``check_all`` and
    the offline red-on-before proof — sheets need NOT be engine-wired to be
    discovered here."""
    import importlib
    for root_dir, pkg_prefix in _CONTRACT_ROOTS:
        pkg = root_dir / sheet_name / "placement_contract.py"
        if not pkg.exists():
            continue
        mod = importlib.import_module(
            f"{pkg_prefix}.{sheet_name}.placement_contract")
        return getattr(mod, "CONTRACT", None)
    return None


def load_contract(sheet_name: str) -> dict | None:
    """ENGINE-FACING loader: the CONTRACT dict for ``sheet_name`` IFF it is an
    engine-WIRED sheet (``_WIRED_SHEETS``), else None. This keeps the stage-template
    placer and the emit gate chain scoped to the pilot exactly as
    ``stage_templates.build_zone`` / ``emit`` already are — an authored-but-unwired
    contract is INERT here (it neither perturbs the placer nor gates the build)
    until its template is wired. Use ``discover_contract`` to read a contract
    regardless of wiring (offline verification / the red-on-before proof)."""
    if sheet_name not in _WIRED_SHEETS:
        return None
    return discover_contract(sheet_name)


# --- pad geometry (pad-edge-to-pad-edge) ------------------------------------------

_pad_box_cache: dict[tuple[str, float, str], dict[str, tuple]] = {}


def _pad_boxes(
    mod_path: Path, rotation: float, side: str
) -> dict[str, tuple[float, float, float, float]]:
    """pad name -> axis-aligned board-local bbox (min_x,min_y,max_x,max_y),
    relative to the footprint origin, after the placement ``rotation`` (KiCad
    CLOCKWISE, +y-down) and, for a bottom part, the F->B X-mirror. Mirrors the
    transform in ``mating_face._inst_pad_geom`` / ``_rot_pad_bbox`` (pad size +
    the pad's own rotation included). Cached by (path, rotation, side)."""
    key = (str(mod_path), round(rotation or 0.0, 3), side)
    hit = _pad_box_cache.get(key)
    if hit is not None:
        return hit
    doc = sexpr.loads(mod_path.read_text())
    R = math.radians(rotation or 0.0)
    cs, sn = math.cos(R), math.sin(R)
    out: dict[str, tuple[float, float, float, float]] = {}
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        name = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3):
            continue
        px, py = float(at[1]), float(at[2])
        prot = math.radians(
            float(at[3]) if len(at) > 3 and isinstance(at[3], (int, float))
            else 0.0)
        sw, sh = (float(sz[1]), float(sz[2])) if sz and len(sz) >= 3 else (0.0, 0.0)
        if side == "bottom":
            px = -px                          # F->B mirror about origin X
            prot = -prot
        cx = px * cs + py * sn                # CW footprint rotation (+y-down)
        cy = -px * sn + py * cs
        tot = R + prot                        # pad-own rotation folded in
        ct, st = abs(math.cos(tot)), abs(math.sin(tot))
        hx = ct * sw / 2 + st * sh / 2
        hy = st * sw / 2 + ct * sh / 2
        # a pad name may repeat (a split GND net); keep the UNION box so the
        # per-pin box covers every copy of that pin.
        b = (cx - hx, cy - hy, cx + hx, cy + hy)
        if name in out:
            o = out[name]
            b = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
        out[name] = b
    _pad_box_cache[key] = out
    return out


def _inst_pad_boxes(inst) -> dict[str, tuple[float, float, float, float]]:
    """pad name -> board-page-frame bbox for a placed FootprintInst."""
    rel = _pad_boxes(inst.mod_path, inst.rotation or 0.0, inst.side)
    return {n: (inst.x + b[0], inst.y + b[1], inst.x + b[2], inst.y + b[3])
            for n, b in rel.items()}


def _box_gap(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> float:
    """Edge-to-edge gap between two axis-aligned boxes (0 if they overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _pins_to_part(pin_boxes: dict[str, tuple], part_boxes: dict[str, tuple],
                  pins: list[str]) -> float | None:
    """MIN pad-edge-to-pad-edge gap from any of the IC pins ``pins`` to any pad
    of the part. None if no pin/part box is available."""
    best: float | None = None
    part = list(part_boxes.values())
    if not part:
        return None
    for p in pins:
        pb = pin_boxes.get(p)
        if pb is None:
            continue
        for qb in part:
            g = _box_gap(pb, qb)
            best = g if best is None else min(best, g)
    return best


def _part_to_part(a_boxes: dict[str, tuple], b_boxes: dict[str, tuple]
                  ) -> float | None:
    best: float | None = None
    for ab in a_boxes.values():
        for bb in b_boxes.values():
            g = _box_gap(ab, bb)
            best = g if best is None else min(best, g)
    return best


# --- ref mapping ------------------------------------------------------------------

def _board_refs_by_sheet(sheet_name: str) -> dict[str, str]:
    """LIBRARY ref -> board-unique ref for ``sheet_name``, via the SAME per-sheet
    band rename the netlist/board flow uses (``board._renamed_ref`` + the frozen
    ``carrier/sheet_index.json`` band). So the contract's U1 resolves to the same
    U20001 KiCad extracted, exactly like ``footprint.board_parts``."""
    import json

    from schgen.core.link import load_subsystem
    from schgen.generate.board import _renamed_ref
    idx_path = _REPO_ROOT / "carrier" / "sheet_index.json"
    sheet_index = (json.loads(idx_path.read_text())
                   if idx_path.exists() else {})
    idx = sheet_index.get(sheet_name)
    if idx is None:
        # fall back to the 1-based discovery order (legacy / selftest); matches
        # board_parts' own fallback so the two never disagree.
        from schgen.core.link import all_subsystem_paths
        order = [p.stem for p in all_subsystem_paths()]
        idx = order.index(sheet_name) + 1 if sheet_name in order else 1
    sc = load_subsystem(sheet_name)
    return {ref: _renamed_ref(ref, idx, sheet=sheet_name)
            for ref in sc.circuit.parts}


# --- result -----------------------------------------------------------------------

@dataclass
class PlacementContractResult:
    ok: bool = True
    sheet: str = ""
    have_contract: bool = False
    checked: int = 0                 # structures examined
    violations: list[str] = field(default_factory=list)
    # per-type counts, for a scalar regression signal
    hot_loop_fail: int = 0
    same_side_fail: int = 0
    bulk_fail: int = 0
    bulk_out_fail: int = 0
    sw_node_fail: int = 0
    fb_fail: int = 0
    boot_fail: int = 0
    vcc_fail: int = 0
    bias_fail: int = 0
    rt_fail: int = 0
    ldo_fail: int = 0
    proximity_fail: int = 0
    unknown_fail: int = 0
    missing_refs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"PLACEMENT-CONTRACT GATE ({self.sheet or '?'}): "
             f"{'PASS' if self.ok else 'FAIL'} "
             f"(contract={'yes' if self.have_contract else 'none'}, "
             f"{self.checked} structures)"]
        L.append(
            "  fails: "
            f"hot_loop={self.hot_loop_fail} same_side={self.same_side_fail} "
            f"bulk={self.bulk_fail} bulk_out={self.bulk_out_fail} "
            f"sw_node={self.sw_node_fail} "
            f"fb={self.fb_fail} boot={self.boot_fail} vcc={self.vcc_fail} "
            f"bias={self.bias_fail} rt={self.rt_fail} ldo={self.ldo_fail} "
            f"proximity={self.proximity_fail} unknown={self.unknown_fail}")
        L.append(f"  unresolved refs: {len(self.missing_refs)}")
        for r in sorted(self.missing_refs):
            L.append(f"    MISSING {r}")
        L.append(f"  violations: {len(self.violations)}")
        for v in sorted(self.violations):
            L.append(f"    {v}")
        return "\n".join(L)


# --- the check --------------------------------------------------------------------

def check(model: PcbModel, sheet_name: str = "power",
          contract: dict | None = None,
          ref_map: dict[str, str] | None = None) -> PlacementContractResult:
    """Check the EMITTED board ``model`` against ``sheet_name``'s placement
    contract. ``contract`` may be passed directly (tests); otherwise loaded from
    the subsystem package. ``ref_map`` (LIBRARY ref -> board ref) may be injected
    (synthetic unit tests use an identity map on a synthetic sheet); otherwise it
    is derived from the frozen per-sheet band the real board uses. A subsystem
    with no contract passes vacuously."""
    res = PlacementContractResult(sheet=sheet_name)
    if contract is None:
        contract = load_contract(sheet_name)
    if contract is None:
        res.have_contract = False
        res.ok = True
        return res
    res.have_contract = True

    if ref_map is None:
        ref_map = _board_refs_by_sheet(sheet_name)
    # board refs for THIS sheet only
    inst_by_bref = {i.ref: i for i in model.insts if i.sheet == sheet_name}

    def inst(lib_ref: str):
        """Placed FootprintInst for a LIBRARY ref, or None (and record it)."""
        bref = ref_map.get(lib_ref)
        if bref is None or bref not in inst_by_bref:
            miss = f"{lib_ref}->{bref or '?'}"
            if miss not in res.missing_refs:
                res.missing_refs.append(miss)
            return None
        return inst_by_bref[bref]

    def boxes(lib_ref: str) -> dict[str, tuple] | None:
        it = inst(lib_ref)
        return None if it is None else _inst_pad_boxes(it)

    def add(v: str) -> None:
        res.violations.append(v)

    for st in contract.get("structures", []):
        typ = st.get("type")
        res.checked += 1

        if typ == "hot_loop":
            ic = st["ic"]
            ic_it = inst(ic)
            ic_boxes = None if ic_it is None else _inst_pad_boxes(ic_it)
            lim = float(st["max_pad_to_pin_mm"])
            basis = st["basis"]
            cap_data = [(cref, inst(cref), boxes(cref)) for cref in st["caps"]]
            for pair in st["pin_pairs"]:
                # existential: SOME listed 100 nF within lim of the pin-pair,
                # same side as the IC.
                best_ref, best_d = None, None
                for cref, cit, cboxes in cap_data:
                    if ic_boxes is None or cboxes is None or cit is None:
                        continue
                    if st.get("same_side") and ic_it is not None \
                            and cit.side != ic_it.side:
                        continue                # wrong side: cannot satisfy
                    d = _pins_to_part(ic_boxes, cboxes, pair)
                    if d is None:
                        continue
                    if best_d is None or d < best_d:
                        best_ref, best_d = cref, d
                if best_d is None or best_d > lim:
                    res.hot_loop_fail += 1
                    detail = (f"none within {lim:g}mm same-side"
                              if best_d is None
                              else f"nearest {best_ref} {best_d:.2f}mm")
                    add(f"hot_loop {ic} pins {'/'.join(pair)} (VIN/PGND): "
                        f"{detail} > {lim:g}mm [{basis}]")

        elif typ == "bulk_in":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lim = float(st["max_pad_to_pin_mm"])
            for cref in st["caps"]:
                cb = boxes(cref)
                if ic_boxes is None or cb is None:
                    continue
                d = _pins_to_part(ic_boxes, cb, st["vin_pins"])
                if d is None or d > lim:
                    res.bulk_fail += 1
                    add(f"bulk_in {ic} {cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to VIN {st['vin_pins']} [{st['basis']}]")

        elif typ == "bulk_out":
            # Universal (NOT existential): EVERY listed COUT must sit within the
            # limit of the inductor's OUTPUT pad, on the same side as the IC — so a
            # stray output cap cannot hide behind a compliant sibling. The distance
            # is measured to the INDUCTOR's output pad (pad 2), not an IC pin,
            # because that pad IS the output node the L->COUT->GND loop closes at.
            ic = st["ic"]
            ic_it = inst(ic)
            l_it = inst(st["inductor"])
            l_boxes = None if l_it is None else _inst_pad_boxes(l_it)
            lim = float(st["max_pad_to_pin_mm"])
            out_pin = st["inductor_out_pin"]
            for cref in st["caps"]:
                cit = inst(cref)
                cb = boxes(cref)
                if l_boxes is None or cb is None or cit is None:
                    continue
                if st.get("same_side") and ic_it is not None \
                        and cit.side != ic_it.side:
                    res.bulk_out_fail += 1
                    add(f"bulk_out {ic} {cref}: on {cit.side} but IC is "
                        f"{ic_it.side} (same_side) [{st['basis']}]")
                    continue
                d = _pins_to_part(l_boxes, cb, [out_pin])
                if d is None or d > lim:
                    res.bulk_out_fail += 1
                    add(f"bulk_out {ic} {cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to L={st['inductor']} out pad {out_pin} "
                        f"[{st['basis']}]")

        elif typ == "sw_node":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lb = boxes(st["inductor"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and lb is not None:
                d = _pins_to_part(ic_boxes, lb, [st["sw_pin"]])
                if d is None or d > lim:
                    res.sw_node_fail += 1
                    add(f"sw_node {ic} L={st['inductor']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to SW pin {st['sw_pin']} [{st['basis']}]")

        elif typ == "fb_cluster":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            own_l = boxes(st["own_inductor"])
            # E2: a single-buck sheet (e.g. power_som) has NO foreign switcher —
            # the foreign_* keys are absent and the foreign-SW guard is an
            # inter-zone concern carried by the composition gate, not intra-zone
            # geometry. Tolerate their absence (no foreign check), never KeyError.
            foreign_ic_ref = st.get("foreign_ic")
            for_ic = boxes(foreign_ic_ref) if foreign_ic_ref else None
            foreign_l_ref = st.get("foreign_inductor")
            for_l = boxes(foreign_l_ref) if foreign_l_ref else None
            foreign_sw_pin = st.get("foreign_sw_pin")
            to_fb = float(st["max_to_fb_mm"])
            min_own = float(st["min_to_own_sw_mm"])
            min_for = float(st.get("min_to_foreign_sw_mm", 0.0))
            for mref in st["members"]:
                mb = boxes(mref)
                if mb is None:
                    continue
                # <= max_to_fb of the FB pin
                if ic_boxes is not None:
                    d = _pins_to_part(ic_boxes, mb, [st["fb_pin"]])
                    if d is None or d > to_fb:
                        res.fb_fail += 1
                        add(f"fb_cluster {ic} {mref}: "
                            f"{'n/a' if d is None else f'{d:.2f}mm'} > {to_fb:g}mm "
                            f"to FB pin {st['fb_pin']} [{st['basis']}]")
                # >= min from own SW pad / inductor
                own_d = None
                if ic_boxes is not None:
                    own_d = _pins_to_part(ic_boxes, mb, [st["own_sw_pin"]])
                if own_l is not None:
                    dl = _part_to_part(mb, own_l)
                    own_d = dl if own_d is None else (
                        dl if dl is not None and dl < own_d else own_d)
                if own_d is not None and own_d < min_own:
                    res.fb_fail += 1
                    add(f"fb_cluster {ic} {mref}: {own_d:.2f}mm < {min_own:g}mm "
                        f"from own SW/L (too close) [{st['basis']}]")
                # >= min from the OTHER buck's SW pad / inductor. E2: skipped
                # entirely on a single-buck sheet (no foreign_* keys declared).
                if foreign_ic_ref is not None:
                    for_d = None
                    if for_ic is not None and foreign_sw_pin is not None:
                        for_d = _pins_to_part(for_ic, mb, [foreign_sw_pin])
                    if for_l is not None:
                        dl = _part_to_part(mb, for_l)
                        for_d = dl if for_d is None else (
                            dl if dl is not None and dl < for_d else for_d)
                    if for_d is not None and for_d < min_for:
                        res.fb_fail += 1
                        add(f"fb_cluster {ic} {mref}: {for_d:.2f}mm < "
                            f"{min_for:g}mm from foreign {foreign_ic_ref} SW/L "
                            f"[{st['basis']}]")

        elif typ == "boot":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, st["pins"])
                if d is None or d > lim:
                    res.boot_fail += 1
                    add(f"boot {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to pins {st['pins']} [{st['basis']}]")

        elif typ == "vcc_cap":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, [st["pin"]])
                if d is None or d > lim:
                    res.vcc_fail += 1
                    add(f"vcc_cap {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to VCC pin {st['pin']} [{st['basis']}]")

        elif typ == "bias_cap":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            cb = boxes(st["cap"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and cb is not None:
                d = _pins_to_part(ic_boxes, cb, [st["pin"]])
                if d is None or d > lim:
                    res.bias_fail += 1
                    add(f"bias_cap {ic} {st['cap']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to BIAS pin {st['pin']} [{st['basis']}]")

        elif typ == "rt_r":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            rb = boxes(st["resistor"])
            lim = float(st["max_pad_to_pin_mm"])
            if ic_boxes is not None and rb is not None:
                d = _pins_to_part(ic_boxes, rb, [st["pin"]])
                if d is None or d > lim:
                    res.rt_fail += 1
                    add(f"rt_r {ic} {st['resistor']}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to RT pin {st['pin']} [{st['basis']}]")

        elif typ == "ldo_stage":
            ic = st["ic"]
            ic_boxes = boxes(ic)
            lim = float(st["max_pad_to_pin_mm"])
            for role, cref, pin in (("Cin", st["cin"], st["cin_pin"]),
                                    ("Cout", st["cout"], st["cout_pin"])):
                cb = boxes(cref)
                if ic_boxes is None or cb is None:
                    continue
                d = _pins_to_part(ic_boxes, cb, [pin])
                if d is None or d > lim:
                    res.ldo_fail += 1
                    add(f"ldo_stage {ic} {role}={cref}: "
                        f"{'n/a' if d is None else f'{d:.2f}mm'} > {lim:g}mm "
                        f"to pin {pin} [{st['basis']}]")

        elif typ == "proximity":
            # E4' — the GENERIC intra-zone structure (Decision D10): every member
            # part must sit within ``max_mm`` pad-edge of the ANCHOR (a specific
            # part), measured either to a set of the anchor's ``anchor_pins`` (if
            # given) or to ANY pad of the anchor (absent). ``same_side`` (optional)
            # requires each member on the anchor's PCB side. ``min_from`` (optional)
            # is a list of {part, pin(optional), min_mm} clearances each member
            # must respect. Universal per-member (every member checked); every
            # measured distance is reported AS A NUMBER. Expresses EN clusters,
            # BST networks, ESD arrays, kelvin filters alike (D10 vocabulary).
            _proximity(st, res, inst, boxes, add)

        elif typ == "same_side":
            roles = contract.get("roles", {})
            for ic in st["ics"]:
                ic_it = inst(ic)
                if ic_it is None:
                    continue
                # members = every role bound to this IC's stage. Stage membership
                # is derived from the structures naming this IC (so a role that
                # is not near any structure is still covered): union the caps /
                # members / parts across every structure with ic==this.
                members: set[str] = set()
                for s2 in contract.get("structures", []):
                    if s2.get("type") == "same_side":
                        continue
                    # buck-style structures key on ``ic``; the generic proximity
                    # type keys on ``anchor`` — collect members from BOTH when the
                    # anchoring part is this same_side ref, so a proximity-based
                    # contract (E4') gets the same-side override too.
                    if s2.get("ic") != ic and s2.get("anchor") != ic:
                        continue
                    for k in ("cap", "inductor", "resistor", "cin", "cout"):
                        if k in s2:
                            members.add(s2[k])
                    for k in ("caps", "members"):
                        members.update(s2.get(k, []))
                # also anything whose role text is bound to this IC via roles is
                # covered by the structures above; that is sufficient for v1.
                for mref in sorted(members):
                    mit = inst(mref)
                    if mit is None:
                        continue
                    if mit.side != ic_it.side:
                        res.same_side_fail += 1
                        add(f"same_side {ic} {mref}: on {mit.side} but IC is "
                            f"{ic_it.side} [{st['basis']}]")
                # keep roles referenced so a future template can rely on it
                _ = roles

        else:
            # E4' FAIL LOUD: an unimplemented structure type is a VIOLATION, never
            # a silent skip. A contract that declares a type this gate cannot check
            # would otherwise pass vacuously (a false green — LAW 4). The count +
            # the violation line name the type and the sheet.
            res.unknown_fail += 1
            add(f"UNKNOWN structure type {typ!r} — gate has no branch to check "
                f"it (fail-loud) [{st.get('basis', '')}]")

    res.ok = (not res.violations)
    return res


# --- proximity (E4' / Decision D10 generic intra-zone type) ------------------------

def _proximity(st: dict, res: PlacementContractResult, inst, boxes, add) -> None:
    """Check ONE ``proximity`` structure against the placed geometry.

    Schema (all distances pad-edge-to-pad-edge, mm):
      ``members``      list of member part refs (LIBRARY refs). Universal — EVERY
                       member is checked, so a stray one cannot hide behind a
                       compliant sibling.
      ``anchor``       the part the members cluster around.
      ``anchor_pins``  optional list of anchor pin names; when given the distance
                       is measured to those pins only, else to ANY pad of the
                       anchor (absent = whole-part proximity).
      ``max_mm``       each member must be within this of the anchor (pins).
      ``same_side``    optional bool; each member must share the anchor's side.
      ``min_from``     optional list of {part, pin (optional), min_mm}; each member
                       must clear each named part (pin, or any pad) by >= min_mm.

    Every measured distance is reported AS A NUMBER (LAW 4). The single
    ``proximity_fail`` counter aggregates every failing (member, constraint) pair.
    """
    anchor = st.get("anchor")
    anchor_it = inst(anchor) if anchor else None
    anchor_boxes = boxes(anchor) if anchor else None
    anchor_pins = st.get("anchor_pins")     # None -> any pad of the anchor
    max_mm = float(st["max_mm"])
    same_side = bool(st.get("same_side", False))
    basis = st.get("basis", "")

    for mref in st.get("members", []):
        mb = boxes(mref)
        mit = inst(mref)
        if mb is None or anchor_boxes is None:
            continue
        # --- max_mm to the anchor (pins if given, else any pad) ----------------
        if anchor_pins:
            d = _pins_to_part(anchor_boxes, mb, anchor_pins)
        else:
            d = _part_to_part(anchor_boxes, mb)
        tgt = (f"pins {'/'.join(anchor_pins)}" if anchor_pins else "any pad")
        if d is None or d > max_mm:
            res.proximity_fail += 1
            add(f"proximity {anchor} {mref}: "
                f"{'n/a' if d is None else f'{d:.2f}mm'} > {max_mm:g}mm "
                f"to {anchor} {tgt} [{basis}]")
        # --- same_side (each member shares the anchor's PCB side) --------------
        if same_side and anchor_it is not None and mit is not None \
                and mit.side != anchor_it.side:
            res.proximity_fail += 1
            add(f"proximity {anchor} {mref}: on {mit.side} but anchor "
                f"{anchor} is {anchor_it.side} (same_side) [{basis}]")
        # --- min_from clearances ----------------------------------------------
        for mf in st.get("min_from", []):
            other = mf.get("part")
            ob = boxes(other) if other else None
            if ob is None:
                continue
            mm = float(mf.get("min_mm", 0.0))
            opin = mf.get("pin")
            fd = (_pins_to_part(ob, mb, [opin]) if opin
                  else _part_to_part(ob, mb))
            otgt = (f"pin {opin}" if opin else "any pad")
            if fd is not None and fd < mm:
                res.proximity_fail += 1
                add(f"proximity {anchor} {mref}: {fd:.2f}mm < {mm:g}mm from "
                    f"{other} {otgt} (too close) [{basis}]")


# --- check_all (discover + check every registered contract) ------------------------

def check_all(model: PcbModel) -> dict[str, PlacementContractResult]:
    """Run :func:`check` for EVERY authored placement contract present in the
    board ``model`` (every sheet with a placed footprint that carries a contract),
    WIRED OR NOT — it discovers via :func:`discover_contract`, bypassing the
    engine-wiring gate, so it sees the full authored set (the red-on-before proof
    needs the unwired sheets). Returns ``{sheet: PlacementContractResult}`` — the
    intra-zone verdict per contracted subsystem. Deterministic: sheets are
    iterated in sorted order."""
    out: dict[str, PlacementContractResult] = {}
    for sheet in sorted({i.sheet for i in model.insts}):
        c = discover_contract(sheet)
        if c is None:
            continue
        out[sheet] = check(model, sheet_name=sheet, contract=c)
    return out
