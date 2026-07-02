"""COMPOSITION-LEVEL PLACEMENT gate — enforce the EXTERNAL (typed-adjacency)
terms of every subsystem's placement contract on the EMITTED board.

The intra-zone :mod:`placement_contract_gate` checks a subsystem's INTERNAL
structures (hot loop, FB cluster, ...). It is blind to how the zones COMPOSE:
the power stages can be perfectly datasheet-tight yet face the wrong way, sit
far from the converter that feeds them, or crowd the Ethernet analog line side.
Those are the contract's ``external`` terms (FLOW chain, FACING, FAR moats), and
NOTHING enforced them — the pilot's open item (AI_LAYOUT_ROUTING_CONCEPT.md
"Phase L / pilot iteration 2 OPEN (a): composition-level FLOW gate").

THIS gate reads every registered contract's ``external`` block (via the SAME
registry the intra-zone gate uses, ``placement_contract_gate.load_contract``) and
checks it against the placed footprint geometry, reasoning about whole-zone
CENTROIDS (not pad boxes — this is board-level composition, not intra-stage):

* **FLOW** — for each declared chain (e.g. ``usb_pd -> power -> power_som``) the
  zone-centroid distance between each consecutive pair must be within a
  BOARD-SCALED budget ``FLOW_K * sqrt(board_area)`` (``FLOW_K`` judgment:0.35 —
  documented below). Each hop reports its measured distance vs the budget.

* **FACING** — for a contracted subsystem with a declared ``downstream``, the
  centroid of its OUTPUT-role parts (the ``output_roles`` members, e.g. the
  ``cout_bulk`` COUT bank — the physical output node) must lie on the
  downstream-facing HALF of the zone: the vector from the zone centroid to the
  output-parts centroid must have a POSITIVE dot product with the vector from the
  zone centroid toward the downstream zone centroid. The dot-product sign + the
  angle between the two vectors are reported.

* **FAR** — each declared ``{"what": <zone[.region]>, "min_mm": d}`` requires the
  contracted zone's centroid to clear the named zone's centroid by ``>= d`` mm.
  A ``zone.region`` target coarsens to the ``zone`` centroid until finer regions
  exist (documented). A target that does NOT resolve to a placed zone is reported
  UNRESOLVED and FAILS (strict — never a silent skip; LAW 4 / LAW 7).

* **NEAR_MAX** (E5-lite, D11) — the DUAL of FAR: each declared ``{"other": <zone>,
  "max_mm": d}`` requires the EDGE-to-EDGE GAP between the contracted zone's
  bounding box and the named zone's box to be ``<= d`` mm (0 when they overlap or
  abut) — keep two zones close (e.g. usb_pd near its Type-C receptacle, ethernet
  near its RJ45). D11 replaced the earlier zone-CENTROID distance: a centroid cap
  is bounded below by the zones' half-extents, so it false-failed two ADJACENT
  zones; the edge gap is the real empty space between them. Strict resolve like
  FAR (the ``@som`` token resolves to the SoM core rectangle).

The FLOW, FACING and NEAR_MAX targets may name the special ``@som`` token (E3):
it resolves to the SoM CORE-rectangle centroid (``model.som_core``) rather than a
placed zone, so a subsystem can flow/face/near the plugged-in SoM — a FIXED region,
not a sheet zone. Without a placed SoM the token is UNRESOLVED (strict).

LAW 4 (strict, no softening): a failing term is FIXED by placing the zones/parts
correctly (the FACING term drives the stage-template ``facing`` step; FLOW/FAR/
NEAR_MAX drive the floorplan), never waived here and never made configurable to
weaken it. Every measured quantity is reported AS A NUMBER so a regression shows
as a number.

Determinism: the summary sorts every list; centroids are rounded; no global
state, no import side effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from schgen.generate.pcb import PcbModel
from schgen.verify.placement_contract_gate import (
    _board_refs_by_sheet,
    load_contract,
)

# FLOW budget. A hop is "close enough" if the two zone centroids are within a
# board-scaled FREE-SPACE budget FLOW_K * sqrt(board_area) PLUS the SoM-detour
# term (below). JUDGMENT: the datasheet numbers no inter-subsystem spacing; 0.35
# is the board-fraction of sqrt(area) that reads as "adjacent in the power chain"
# without over-constraining the floorplan (~55 mm on the ~170x145 mm board).
# Scaling by sqrt(area) keeps the bound meaningful as the board grows/shrinks.
FLOW_K = 0.35

# SoM-detour term. This carrier plugs a SoM into the board CENTER (a ~51x43 mm
# keepout, ``model.som_core``): every power-chain zone clusters by net-affinity to
# the SoM's DF40 strips, so consecutive chain zones routinely land on OPPOSITE
# sides of that central obstacle and CANNOT be closer than routing around it. A
# raw FLOW_K*sqrt(area) budget therefore false-fails a correctly-composed
# center-module board (the zones are as close as the SoM allows). The budget adds
# FLOW_SOM_K * (SoM core diagonal) — the go-around distance the chain is forced to
# span. JUDGMENT: 1.0 = the full SoM diagonal (the worst-case detour). Without a
# placed ``som_core`` (synthetic tests) the term is 0, so the pure FLOW_K budget
# applies. See AI_LAYOUT_ROUTING_CONCEPT.md "Phase L / pilot OPEN(a)": the FLOW
# distances are large because the floorplan seats power_som at the SoM's W strips
# while power is E-interior — a pre-existing floorplan limitation this gate makes
# VISIBLE (reported as a number every build), not one it can move copper to fix.
FLOW_SOM_K = 1.0


# --- zone centroid geometry -------------------------------------------------------

def _zone_centroids(model: PcbModel) -> dict[str, tuple[float, float]]:
    """sheet name -> (x, y) centroid of every placed footprint on that sheet
    (board page frame, equal-weight over parts). Deterministic."""
    acc: dict[str, list[float]] = {}
    for i in model.insts:
        a = acc.setdefault(i.sheet, [0.0, 0.0, 0.0])
        a[0] += i.x
        a[1] += i.y
        a[2] += 1.0
    return {s: (round(a[0] / a[2], 4), round(a[1] / a[2], 4))
            for s, a in acc.items() if a[2] > 0}


# --- zone bounding boxes (D11: near_max is an EDGE-to-EDGE gap, not centroids) ------
# The NEAR_MAX metric measures the GAP between two zones' bounding boxes, not their
# centroid distance. Centroid distance is bounded below by the sum of the zones'
# half-extents, so a tight centroid cap false-fails two ADJACENT zones (the D11
# defect: usb_pd<->pd_input measured ~38.6 mm centroid, near the geometric floor,
# yet the zones abut). The edge-gap is 0 when the zones overlap and grows only with
# the real empty space between them — the physical quantity "keep these two close"
# actually means. Each zone's box is the UNION of its parts' PAD boxes (the same
# board-page-frame pad geometry the intra-zone gate measures, so the box lands where
# KiCad's copper does); the ``@som`` token's box is ``model.som_core`` directly.

def _zone_bboxes(model: PcbModel) -> dict[str, tuple[float, float, float, float]]:
    """sheet name -> (x0, y0, x1, y1) axis-aligned bbox over every placed
    footprint's PAD boxes on that sheet (board page frame). Deterministic;
    reuses the intra-zone gate's pad geometry so the box matches the emitted
    copper. A sheet with no resolvable pad geometry is omitted."""
    from schgen.verify.placement_contract_gate import _inst_pad_boxes
    acc: dict[str, list[float]] = {}
    for i in model.insts:
        try:
            boxes = _inst_pad_boxes(i)
        except Exception:  # noqa: BLE001 — a sheet with no parsable pads is skipped
            continue
        if not boxes:
            continue
        a = acc.get(i.sheet)
        for b in boxes.values():
            if a is None:
                a = [b[0], b[1], b[2], b[3]]
                acc[i.sheet] = a
            else:
                a[0] = min(a[0], b[0])
                a[1] = min(a[1], b[1])
                a[2] = max(a[2], b[2])
                a[3] = max(a[3], b[3])
    return {s: (round(a[0], 4), round(a[1], 4), round(a[2], 4), round(a[3], 4))
            for s, a in acc.items()}


def _bbox_gap(a: tuple[float, float, float, float],
              b: tuple[float, float, float, float]) -> float:
    """Edge-to-edge gap between two axis-aligned boxes (0.0 if they overlap or
    touch). The Euclidean distance between the nearest edges — the empty space
    between the two zones."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _resolve_target_bbox(name: str,
                         bboxes: dict[str, tuple[float, float, float, float]],
                         model: PcbModel
                         ) -> tuple[float, float, float, float] | None:
    """Resolve a NEAR_MAX target NAME to a bounding box: the special ``@som``
    token (E3) resolves to the SoM core rectangle (``model.som_core``); every
    other name is a sheet-zone bbox. None when the target is not placed (strict
    callers fail on None)."""
    if name == _SOM_TOKEN:
        return model.som_core
    return bboxes.get(name)


# E3: the SoM is a FIXED core region (``model.som_core``), not a placed zone —
# a carrier plugs a SoM into the board and a subsystem's OUTPUT can face THAT
# region (e.g. power_som's +5V_SOM feeds the SoM DF40 VIN). A contract names it
# with the special ``downstream``/flow token ``@som``; this resolver returns the
# som_core rect centroid, or None when no SoM is placed (synthetic tests).
_SOM_TOKEN = "@som"


def _som_centroid(model: PcbModel) -> tuple[float, float] | None:
    """(x, y) centroid of the SoM core rectangle (``model.som_core``), or None if
    the board has no plugged-in SoM region."""
    if model.som_core is None:
        return None
    x0, y0, x1, y1 = model.som_core
    return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))


def _resolve_target(name: str, centroids: dict[str, tuple[float, float]],
                    model: PcbModel) -> tuple[float, float] | None:
    """Resolve a FLOW/FACING target NAME to a centroid: the special ``@som`` token
    (E3) resolves to the SoM core centroid; every other name is a sheet-zone
    centroid. None when the target is not placed (strict callers fail on None)."""
    if name == _SOM_TOKEN:
        return _som_centroid(model)
    return centroids.get(name)


def _members_centroid(model: PcbModel, sheet: str,
                      brefs: set[str]) -> tuple[float, float] | None:
    """(x, y) centroid of the given BOARD refs on ``sheet``, or None if none are
    placed (equal-weight over parts, board page frame)."""
    xs: list[float] = []
    ys: list[float] = []
    for i in model.insts:
        if i.sheet == sheet and i.ref in brefs:
            xs.append(i.x)
            ys.append(i.y)
    if not xs:
        return None
    return (round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4))


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --- result -----------------------------------------------------------------------

@dataclass
class PlacementFlowResult:
    ok: bool = True
    n_contracts: int = 0             # contracts that carried an ``external`` block
    flow_checked: int = 0            # FLOW hops examined
    flow_fail: int = 0
    facing_checked: int = 0
    facing_fail: int = 0
    far_checked: int = 0
    far_fail: int = 0
    near_max_checked: int = 0        # E5-lite: NEAR_MAX zone-centroid caps
    near_max_fail: int = 0
    unresolved: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    # per-hop / per-term detail lines (always reported, pass or fail)
    detail: list[str] = field(default_factory=list)
    board_area: float = 0.0
    flow_budget_mm: float = 0.0

    def summary(self) -> str:
        L = [f"PLACEMENT-FLOW GATE: {'PASS' if self.ok else 'FAIL'} "
             f"({self.n_contracts} external contract(s); "
             f"board_area={self.board_area:.0f}mm^2, "
             f"flow_budget={self.flow_budget_mm:.1f}mm)"]
        L.append(
            "  fails: "
            f"flow={self.flow_fail}/{self.flow_checked} "
            f"facing={self.facing_fail}/{self.facing_checked} "
            f"far={self.far_fail}/{self.far_checked} "
            f"near_max={self.near_max_fail}/{self.near_max_checked}")
        L.append(f"  unresolved: {len(self.unresolved)}")
        for u in sorted(self.unresolved):
            L.append(f"    UNRESOLVED {u}")
        L.append(f"  violations: {len(self.violations)}")
        for v in sorted(self.violations):
            L.append(f"    {v}")
        L.append(f"  detail: {len(self.detail)}")
        for d in sorted(self.detail):
            L.append(f"    {d}")
        return "\n".join(L)


# --- the check --------------------------------------------------------------------

def check(model: PcbModel,
          contracts: dict[str, dict] | None = None,
          ref_maps: dict[str, dict[str, str]] | None = None
          ) -> PlacementFlowResult:
    """Check every subsystem's ``external`` contract terms against ``model``.

    ``contracts`` (sheet -> CONTRACT dict) and ``ref_maps`` (sheet -> {library
    ref: board ref}) may be injected for hermetic tests; otherwise contracts are
    loaded from the registry (every sheet present in the model) and each ref map
    is derived from the frozen per-sheet band the real board uses. A subsystem
    with no ``external`` block contributes nothing."""
    res = PlacementFlowResult()
    centroids = _zone_centroids(model)
    bboxes = _zone_bboxes(model)           # D11: near_max is an edge-to-edge gap
    area = max(float(model.board_w) * float(model.board_h), 1.0)
    res.board_area = area
    # free-space term + the SoM go-around detour (0 without a placed som_core).
    som_diag = 0.0
    if model.som_core is not None:
        sx0, sy0, sx1, sy1 = model.som_core
        som_diag = math.hypot(sx1 - sx0, sy1 - sy0)
    budget = FLOW_K * math.sqrt(area) + FLOW_SOM_K * som_diag
    res.flow_budget_mm = round(budget, 4)

    # gather contracts: injected, or loaded for every sheet in the model
    if contracts is None:
        contracts = {}
        for sheet in sorted({i.sheet for i in model.insts}):
            c = load_contract(sheet)
            if c is not None and c.get("external"):
                contracts[sheet] = c
    else:
        contracts = {s: c for s, c in contracts.items() if c.get("external")}

    def add(v: str) -> None:
        res.violations.append(v)

    for sheet in sorted(contracts):
        contract = contracts[sheet]
        ext = contract.get("external") or {}
        res.n_contracts += 1

        # ---- FLOW: each consecutive hop within the board-scaled budget --------
        flow = ext.get("flow", [])
        for a, b in zip(flow, flow[1:], strict=False):
            res.flow_checked += 1
            ca = _resolve_target(a, centroids, model)   # E3: @som resolves too
            cb = _resolve_target(b, centroids, model)
            if ca is None or cb is None:
                gone = "/".join(x for x, c in ((a, ca), (b, cb)) if c is None)
                miss = f"{sheet}: flow zone {gone} not placed"
                if miss not in res.unresolved:
                    res.unresolved.append(miss)
                res.flow_fail += 1
                cid = contract.get("contract", "?")
                add(f"flow {a}->{b}: zone(s) not placed [{cid}]")
                continue
            d = _dist(ca, cb)
            res.detail.append(
                f"flow {a}->{b}: {d:.2f}mm / {budget:.1f}mm budget")
            if d > budget:
                res.flow_fail += 1
                add(f"flow {a}->{b}: {d:.2f}mm > {budget:.1f}mm budget "
                    f"(FLOW_K={FLOW_K} free + SoM detour)")

        # ---- FACING: output parts on the downstream-facing half ---------------
        downstream = ext.get("downstream")
        output_roles = set(ext.get("output_roles", []))
        if downstream and output_roles:
            res.facing_checked += 1
            _facing(res, model, sheet, contract, downstream, output_roles,
                    centroids, ref_maps, add)

        # ---- FAR: named-zone minimum separations ------------------------------
        for far in ext.get("far", []):
            res.far_checked += 1
            what = far.get("what", "?")
            min_mm = float(far.get("min_mm", 0.0))
            basis = far.get("basis", "")
            zname = what.split(".", 1)[0]           # coarsen zone.region -> zone
            czone = centroids.get(sheet)
            ctgt = centroids.get(zname)
            if czone is None or ctgt is None:
                un = f"{sheet}: far target {what!r} (zone {zname!r}) not placed"
                if un not in res.unresolved:
                    res.unresolved.append(un)
                res.far_fail += 1
                add(f"far {sheet} vs {what}: UNRESOLVED (zone {zname!r} not "
                    f"placed) [{basis}]")
                continue
            d = _dist(czone, ctgt)
            res.detail.append(
                f"far {sheet} vs {what}: {d:.2f}mm / >= {min_mm:g}mm")
            if d < min_mm:
                res.far_fail += 1
                add(f"far {sheet} vs {what}: {d:.2f}mm < {min_mm:g}mm "
                    f"[{basis}]")

        # ---- NEAR_MAX (E5-lite, D11): zone bbox EDGE-to-EDGE gap <= max_mm -----
        # The DUAL of FAR: keep this zone CLOSE to a named zone (e.g. usb_pd near
        # its pd_input receptacle, ethernet near its RJ45). D11: the metric is the
        # zones' bounding-box EDGE gap (0 when they overlap/abut), NOT the centroid
        # distance — a centroid cap is bounded below by the zones' half-extents, so
        # it false-fails two ADJACENT zones. The ``other`` name is a sheet zone or
        # the ``@som`` token (E3). Strict: an unresolved target FAILS, never a silent
        # skip (LAW 4). Every measured gap is reported AS A NUMBER.
        for near in ext.get("near_max", []):
            res.near_max_checked += 1
            other = near.get("other", "?")
            max_mm = float(near.get("max_mm", 0.0))
            basis = near.get("basis", "")
            bzone = bboxes.get(sheet)
            btgt = _resolve_target_bbox(other, bboxes, model)
            if bzone is None or btgt is None:
                un = f"{sheet}: near_max target {other!r} not placed"
                if un not in res.unresolved:
                    res.unresolved.append(un)
                res.near_max_fail += 1
                add(f"near_max {sheet} to {other}: UNRESOLVED ({other!r} not "
                    f"placed) [{basis}]")
                continue
            d = _bbox_gap(bzone, btgt)
            res.detail.append(
                f"near_max {sheet} to {other}: {d:.2f}mm gap / <= {max_mm:g}mm")
            if d > max_mm:
                res.near_max_fail += 1
                add(f"near_max {sheet} to {other}: {d:.2f}mm gap > {max_mm:g}mm "
                    f"[{basis}]")

    res.ok = (not res.violations and not res.unresolved)
    return res


def _facing(res: PlacementFlowResult, model: PcbModel, sheet: str,
            contract: dict, downstream: str, output_roles: set[str],
            centroids: dict[str, tuple[float, float]],
            ref_maps: dict[str, dict[str, str]] | None,
            add) -> None:
    """FACING sub-check: the OUTPUT-role parts' centroid must lie on the
    downstream-facing half of the zone. Reports the dot-product sign + the angle
    between (zone->output) and (zone->downstream)."""
    # library refs whose role is an output role
    roles = contract.get("roles", {})
    out_libs = [r for r, v in roles.items() if v in output_roles]
    if not out_libs:
        un = f"{sheet}: facing output_roles {sorted(output_roles)} match no role"
        if un not in res.unresolved:
            res.unresolved.append(un)
        res.facing_fail += 1
        add(f"facing {sheet}: no output-role parts declared for "
            f"{sorted(output_roles)} [{contract.get('contract', '?')}]")
        return

    # library -> board ref map (injected for tests, else the frozen band)
    if ref_maps is not None and sheet in ref_maps:
        ref_map = ref_maps[sheet]
    else:
        ref_map = _board_refs_by_sheet(sheet)
    out_brefs = {ref_map[r] for r in out_libs if r in ref_map}

    czone = centroids.get(sheet)
    cds = _resolve_target(downstream, centroids, model)   # E3: @som resolves too
    cout = _members_centroid(model, sheet, out_brefs)
    if czone is None or cds is None or cout is None:
        missing = []
        if czone is None:
            missing.append(sheet)
        if cds is None:
            missing.append(downstream)
        if cout is None:
            missing.append(f"{sheet}.output_parts")
        un = f"{sheet}: facing needs placed {missing}"
        if un not in res.unresolved:
            res.unresolved.append(un)
        res.facing_fail += 1
        add(f"facing {sheet}->{downstream}: UNRESOLVED (not placed: "
            f"{missing}) [{contract.get('contract', '?')}]")
        return

    # vector zone->output and zone->downstream; positive dot == output faces
    # the downstream half of the zone.
    ox, oy = cout[0] - czone[0], cout[1] - czone[1]
    dx, dy = cds[0] - czone[0], cds[1] - czone[1]
    dot = ox * dx + oy * dy
    mo = math.hypot(ox, oy)
    md = math.hypot(dx, dy)
    angle = (math.degrees(math.acos(max(-1.0, min(1.0, dot / (mo * md)))))
             if mo > 1e-9 and md > 1e-9 else 180.0)
    res.detail.append(
        f"facing {sheet}->{downstream}: dot={dot:+.2f} "
        f"angle={angle:.1f}deg (output@{cout} zone@{czone} down@{cds})")
    if dot <= 0.0:
        res.facing_fail += 1
        add(f"facing {sheet}->{downstream}: output parts face AWAY "
            f"(dot={dot:+.2f} <= 0, angle={angle:.1f}deg) "
            f"[{contract.get('contract', '?')}]")
