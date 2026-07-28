"""T1 COMPOSITION — placement-contract TERM INDEX + the exact floorplan-frame
EVALUATOR (spec: T1_COMPOSITION_SPEC.md §3, phase P2).

WHAT THIS SOLVES. The composition gates (:mod:`placement_flow_gate`) judge the
EMITTED board, but the floorplan packer that decides zone poses is blind to the
contract terms it will be judged by — poses satisfy the terms only by luck (the
measured F1/F3/F6/F7 defects). This module gives the ENGINE the same term
vocabulary and an evaluator that predicts, for a candidate set of zone poses,
EXACTLY what the emitted-board gate will measure — including the emit rounding
chain (``_gridify`` zone-origin snap at GRID=1.27, the ``round(·, 4)`` position
writes and the gate's own centroid/bbox rounding), so the P6 legalizer can make
wired terms hold BY CONSTRUCTION.

TWO EVALUATORS, ONE TRUTH: every metric kernel here is IMPORTED from the gates
(:func:`placement_flow_gate.flow_budget` / ``bbox_gap`` / ``facing_dot`` — the
P1 single-oracle publics); nothing is re-derived. The exactness test
(test_floorplan_compose) ties evaluator and gate permanently: <= 1e-6 for
L4-exempt/top-forced sheets, <= GUARD_MM for edge-snap partners, and a printed
residual (FAR_L4_GUARD_MM) for L4-kept far-only participants.

DISCOVERY: terms come from :func:`placement_contract_gate.discover_contract`
over BOTH package roots (``subsystems/`` + ``carrier/subsystems/``) — wired or
not. ``enforced`` mirrors the gate's own ``_WIRED_SHEETS`` scoping. Term ids
are always derived from the live contract data, never a static list. Unknown
external term kinds RAISE (fail-loud — a contract this module cannot express
must never pass silently; ``region_void`` is explicitly unsupported until its
engine lands).

DETERMINISM: argument-pure (never reads ``fp.BOARD_W/BOARD_H`` globals — the
2026-06-19 race class), sorted iteration everywhere, no RNG/env/wall-clock.

All imports across the generate<->verify boundary are lazy (the emit.generate()
house pattern).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---- constants (T1 spec §4 — every threshold carries a basis; none runtime-
# configurable) ---------------------------------------------------------------

# Post-floorplan connector edge-snap travel bound (LAW-6 seat step, the one
# post-pose mover on snap-only sheets). The spec's derivation (EDGE_INSET 1.5
# + EDGE_PAD_CLEAR 0.4 <= 1.9 -> 2.0) was REFUTED by the P5 measurement: the
# snap also absorbs the connector's ZONE-INTERNAL offset, measured max
# pad-bbox travel 3.54 mm (pd_input TYPE-C, P5 residual vector; board_qwiic
# 0.81). GROWN 2.0 -> 4.0 (measured 3.54 + margin) - the constant MAY ONLY
# GROW (never tightened to hide a residual); enforced by the exactness test.
GUARD_MM = 4.0

# Measured emitted-vs-floorplan TERM residual for far-only participants that
# KEEP LEVER-L4 (decision D-2): their bottom passives slide toward the SoM
# after the pose the evaluator sees, so far terms involving them carry a
# measured guard. Values are MEASURED at phase start (P2/P5) and re-measured
# whenever the exactness test's printed residual drifts > 1 mm.
# ethernet guard = 14.0: the spec's measured figure ("ethernet ~= 14 today",
# T1 spec §4, re-verified against this tree 2026-07-02); the P2 exactness run
# prints the live residual next to it (t1_P2 evidence). A larger guard only
# makes far terms HARDER to satisfy — safe direction, LAW-4 compliant.
# power_som guard (P5b, 28f8e15 rebase): power_som KEEPS L4 until its P7
# wave lands the buck template (its bottom caps must keep sliding clear of
# U22004's datasheet thermal-via field — the rebase collision finding).
# Guard = 25.0: measured max L4 centroid travel this tree 23.7 mm
# (P2 residual vector: (12.88, 19.63)) + margin; re-measured at P7.
FAR_L4_GUARD_MM: dict[str, float] = {"ethernet": 14.0, "power_som": 25.0}

W_HOP = 1.0     # judgment:1.0 — hop length IS the contract objective
W_SEED = 0.05   # judgment:0.05 — one order below term cost; uninvolved blocks
#                 keep their LAW-5-shaped seats
Q = 0.5         # quantum for legalized pose write-back; matches the template
#                 engine's _CAND_STEP (stage_templates.py); quantize-then-CLAMP
REPAIR_MAX = 16          # judgment: bounded deterministic termination
CUT_MAX = 8
MEDIAN_PASSES = 8
EPS_FACE = 2.0           # mm — facing half-plane construction margin
EPS_CUT = 0.5            # mm — cutting-plane step
AREA_TARGET_MM2 = 24600.0  # judgment: pre-contract 154x152=23,408 mm^2 + the
#                            recorded ~+5% wave-growth allowance (P10 trigger)

# D13 (Ring-0 injection) — inter-zone escape/channel reservation. Adjacent
# zones with high inter-zone connectivity must keep a routing corridor:
# CHANNEL_FLOOR_MM (judgment:2.0 — D13's per-side floor "2 x 0.1/0.1 mm lanes
# + 1.0 mm clearance" ~= 1.4 mm, rounded up to a full extra lane-pair) plus a
# demand-scaled term CHANNEL_PER_NET_MM per cross-airwire between the pair
# (0.2 mm/net = one 0.1/0.1 trace+space lane per exiting net, D13's per-net
# demand rule). Pairs at/above CHANNEL_MIN_NETS cross-airwires get a HARD
# channel term in the P6 legalizer; below that the floor is CLEAR (0.3) as
# today. Demand counts come from the live ratsnest MST
# (:func:`cross_airwires_by_pair`), never a static table.
CHANNEL_FLOOR_MM = 2.0
CHANNEL_PER_NET_MM = 0.2
CHANNEL_MIN_NETS = 6     # judgment: below ~6 shared airwires two zones are not
#                          a routing channel hotspot (P0 measured pair table:
#                          the hotspot pairs are 7-24 edges, the long tail <=5)

# ``media_faces_near_max`` is a TEMPLATE-orientation flag (T1 P7a), not a
# composition term — it is known-and-ignored here (the proximity template consumes
# it via ``placement._media_facing``; there is no floorplan-frame term to add).
_KNOWN_EXTERNAL_KEYS = {"flow", "downstream", "output_roles", "far", "near_max",
                        "media_faces_near_max"}
_SOM_TOKEN = "@som"


ESCAPE_SIDECAR = PROJECT_ROOT / "escape_block.json"


def escape_corridors(path: Path | None = None
                     ) -> list[tuple[str, float, float, float, float]]:
    """T2's escape-lane corridors from ``carrier/escape_block.json``
    (``t1_constraints.corridors`` — the sidecar names THIS module as the
    consumer): floorplan-frame rects the composition must never close
    (Ring-0 D13 injection, per-IC/DF40 escape headroom). Empty when the
    sidecar is absent (a non-carrier project). The rects currently sit
    inside the SoM core keepout, so zone POSES cannot intrude today — the
    corridors are load-bearing for the legalizer's fixed-rect set (P6-wire)
    and MEASURED in the ledger so any future intrusion is loud."""
    import json as _json
    if path is None:
        path = ESCAPE_SIDECAR
    if not path.exists():
        return []
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    raw = _json.loads(path.read_text())
    out: list[tuple[str, float, float, float, float]] = []
    for name in sorted((raw.get("t1_constraints") or {}).get("corridors",
                                                             {})):
        r = raw["t1_constraints"]["corridors"][name]["rect"]
        out.append((f"escape:{name}", r[0] - ORIGIN_X, r[1] - ORIGIN_Y,
                    r[2] - ORIGIN_X, r[3] - ORIGIN_Y))
    return out


def corridor_intrusions(model, corridors=None
                        ) -> tuple[list[str], list[str]]:
    """(unmanaged, managed) PART-level intrusions into the T2 escape-lane
    corridors — the D13 never-close obligation, measured on the emitted
    model's PAD COPPER (a zone-HULL overlap is meaningless here: the hulls
    sweep the SoM keepout and sliver-overlap the lanes with empty area —
    22 false positives measured at the 4a45f99 reconciliation).

    A part already carried in T2's OWN coexistence ledger
    (``escape_meta.coexistence`` — STAY/CONSTRAINT verdicts, re-derived every
    build against the live via windows) is MANAGED: T2 owns its verdict and
    the eviction protocol. Anything else inside a lane corridor is an
    UNMANAGED intrusion — loud, because no thread has judged it. Advisory
    (the legalizer takes the corridors as fixed rects at P6-wire; T2's
    return-stitch/escape gates protect the copper itself)."""
    import json as _json

    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    from schgen.verify.placement_contract_gate import _inst_pad_boxes
    if corridors is None:
        corridors = escape_corridors()
    if not corridors:
        return [], []
    managed_refs: dict[tuple[str, str], str] = {}
    if ESCAPE_SIDECAR.exists():
        raw = _json.loads(ESCAPE_SIDECAR.read_text())
        for c in (raw.get("escape_meta") or {}).get("coexistence", []):
            managed_refs[(c.get("ref", ""), c.get("sheet", ""))] = \
                c.get("verdict", "?")
    page = [(n, x0 + ORIGIN_X, y0 + ORIGIN_Y, x1 + ORIGIN_X, y1 + ORIGIN_Y)
            for n, x0, y0, x1, y1 in corridors]
    unmanaged: list[str] = []
    managed: list[str] = []
    for i in model.insts:
        if i.sheet.startswith("som_j"):
            continue            # the mezzanine sheets own that space
        try:
            boxes = _inst_pad_boxes(i)
        except Exception:  # noqa: BLE001 — unparsable pads never crash a report
            continue
        hit = None
        for b in boxes.values():
            for n, x0, y0, x1, y1 in page:
                if b[0] < x1 and b[2] > x0 and b[1] < y1 and b[3] > y0:
                    hit = n
                    break
            if hit:
                break
        if hit is None:
            continue
        v = managed_refs.get((i.ref, i.sheet))
        line = f"{i.ref} ({i.sheet}) in {hit}"
        if v is not None:
            managed.append(line + f" [T2 {v}]")
        else:
            unmanaged.append(line)
    return sorted(unmanaged), sorted(managed)


# ---- terms -------------------------------------------------------------------

@dataclass(frozen=True)
class Term:
    """One external composition term, normalized from a placement contract.

    ``kind``       flow_hop | near_max | far_min | facing | near_intent
    ``sheet``      the DECLARING sheet (contract owner)
    ``subject``    the measured subject zone
    ``target_raw`` the RAW dotted target string (``"ethernet.line_side"``,
                   ``"@som"``); resolution uses the gate's own
                   ``split('.', 1)[0]`` coarsening — reports echo the gate.
    ``bound``      mm bound (near_max max / far min); None for flow_hop (the
                   budget is board-size-dependent, computed live per candidate
                   through the gate's ``flow_budget`` kernel) and facing/
                   near_intent.
    ``enforced``   True iff a declaring sheet is ENGINE-WIRED
                   (``placement_contract_gate._WIRED_SHEETS``) — deduped terms
                   OR their enforced flags.
    ``output_roles``/``out_refs`` facing only: the contract's output roles and
                   their resolved BOARD refs."""
    kind: str
    sheet: str
    subject: str
    target_raw: str
    bound: float | None
    basis: str
    enforced: bool
    output_roles: tuple[str, ...] = ()
    out_refs: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        """Gate-coarsened target zone name (``zone.region`` -> ``zone``)."""
        return self.target_raw.split(".", 1)[0]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.subject, self.target_raw)


@dataclass(frozen=True)
class TermIndex:
    hard: tuple[Term, ...]      # enforced (declared by a wired sheet)
    soft: tuple[Term, ...]      # advisory (unwired declarations + near_intent)

    @property
    def terms(self) -> tuple[Term, ...]:
        return self.hard + self.soft


def build_term_index(sheet_names: list[str] | None = None) -> TermIndex:
    """Discover + normalize every external contract term across BOTH contract
    roots, plus the floorplan.json ``near`` intents that carry no contract
    near_max (advisory ``near_intent`` terms). Deterministic: sorted sheets,
    deduped by ``(kind, subject, target_raw)`` keep-min-bound + OR-enforced."""
    from schgen.verify.placement_contract_gate import (  # lazy: verify boundary
        _WIRED_SHEETS,
        _board_refs_by_sheet,
        discover_contract,
    )
    if sheet_names is None:
        from schgen.core.link import all_subsystem_paths
        sheet_names = [p.stem for p in all_subsystem_paths()]

    merged: dict[tuple[str, str, str], Term] = {}

    def _add(t: Term) -> None:
        old = merged.get(t.key)
        if old is None:
            merged[t.key] = t
            return
        # dedupe: keep-min-bound + OR-enforced (IM7). Basis keeps the first
        # declaration; the gate still reports every declaration verbatim.
        bound = old.bound
        if t.bound is not None and (bound is None or t.bound < bound):
            bound = t.bound
        merged[t.key] = Term(
            kind=old.kind, sheet=old.sheet, subject=old.subject,
            target_raw=old.target_raw, bound=bound, basis=old.basis,
            enforced=old.enforced or t.enforced,
            output_roles=old.output_roles or t.output_roles,
            out_refs=old.out_refs or t.out_refs)

    for sheet in sorted(set(sheet_names)):
        contract = discover_contract(sheet)
        if contract is None:
            continue
        ext = contract.get("external") or {}
        unknown = set(ext) - _KNOWN_EXTERNAL_KEYS
        if unknown:
            # fail-loud (E4' discipline): an external key this engine cannot
            # express must never pass silently. region_void is named because
            # the ethernet contract will grow one (its engine is a later unit).
            raise ValueError(
                f"placement contract {sheet!r}: unsupported external term "
                f"kind(s) {sorted(unknown)} — floorplan_compose has no "
                f"engine for them (region_void et al. are separate units); "
                f"refusing to build a term index that silently drops terms")
        enforced = sheet in _WIRED_SHEETS
        basis_default = contract.get("contract", "?")

        flow = list(ext.get("flow", []))
        for a, b in zip(flow, flow[1:], strict=False):
            _add(Term(kind="flow_hop", sheet=sheet, subject=a, target_raw=b,
                      bound=None, basis=f"flow chain [{basis_default}]",
                      enforced=enforced))
        for near in ext.get("near_max", []):
            _add(Term(kind="near_max", sheet=sheet, subject=sheet,
                      target_raw=str(near.get("other", "?")),
                      bound=float(near.get("max_mm", 0.0)),
                      basis=str(near.get("basis", "")), enforced=enforced))
        for far in ext.get("far", []):
            _add(Term(kind="far_min", sheet=sheet, subject=sheet,
                      target_raw=str(far.get("what", "?")),
                      bound=float(far.get("min_mm", 0.0)),
                      basis=str(far.get("basis", "")), enforced=enforced))
        downstream = ext.get("downstream")
        output_roles = tuple(ext.get("output_roles", []))
        if downstream and output_roles:
            roles = contract.get("roles", {})
            out_libs = sorted(r for r, v in roles.items() if v in output_roles)
            ref_map = _board_refs_by_sheet(sheet)
            out_refs = tuple(ref_map[r] for r in out_libs if r in ref_map)
            _add(Term(kind="facing", sheet=sheet, subject=sheet,
                      target_raw=str(downstream), bound=None,
                      basis=f"facing/output_roles [{basis_default}]",
                      enforced=enforced, output_roles=output_roles,
                      out_refs=out_refs))

    # near_intent: floorplan.json {"near": target} entries WITHOUT a contract
    # near_max between the same pair — advisory, never gated (P4 driver scoring).
    from schgen.generate.floorplan import load_floorplan_spec  # same package
    spec = load_floorplan_spec()
    if spec is not None:
        near_max_pairs = {(t.subject, t.target)
                          for t in merged.values() if t.kind == "near_max"}
        for name in sorted(spec.interior):
            anchor = spec.interior[name]
            tgt = anchor.get("near")
            if tgt and (name, tgt) not in near_max_pairs:
                _add(Term(kind="near_intent", sheet=name, subject=name,
                          target_raw=str(tgt), bound=None,
                          basis="carrier/floorplan.json near-intent (advisory)",
                          enforced=False))

    terms = [merged[k] for k in sorted(merged)]
    hard = tuple(t for t in terms if t.enforced)
    soft = tuple(t for t in terms if not t.enforced)
    return TermIndex(hard=hard, soft=soft)


def emit_mobile_sheets(zg, l4_exempt: frozenset[str] | None = None
                       ) -> dict[str, frozenset[str]]:
    """Sheets whose emitted geometry can MOVE after the pose the floorplan
    sees, with the REASON(s): ``{"l4"}`` (LEVER-L4 bottom-pull candidate — >= 2
    bottom-side R/C/L passives, placement.py's mover filter replicated
    verbatim) and/or ``{"snap"}`` (a LAW-6 edge-snapped connector,
    ``zg.conn_edge``; bounded travel <= GUARD_MM).

    ``l4_exempt`` is the P5 per-kind exemption set (default: the live
    ``wired_term_participants()``) — exempt sheets never carry the "l4"
    reason, so the exactness expectation TIGHTENS automatically as waves wire
    more sheets (stale-scalar law: always the same-run model).

    P2 measured truth: only ``usb_pd`` (all-top template) and ``motor_pwm``
    were emit-exact pre-P5 — the spec's "power exact" figure was STALE (power
    carries L4-mobile bottom leftovers; centroid resid ~2.3 mm measured)."""
    if l4_exempt is None:
        from schgen.verify.placement_contract_gate import (
            wired_term_participants,
        )
        l4_exempt, _ = wired_term_participants()
    mobile: dict[str, set[str]] = {}
    for sheet in sorted(set(zg.top_off) | set(zg.bot_off)):
        if sheet in l4_exempt:
            continue
        movers = [r for r in zg.bot_off.get(sheet, {})
                  if zg.side_of.get(r) == "bottom"
                  and r[:1] in ("R", "C", "L")
                  and not r.startswith(("RJ", "LED"))]
        if len(movers) >= 2:
            mobile.setdefault(sheet, set()).add("l4")
    sheet_of = {ref: sheet for sheet, refs in zg.refs_by_sheet.items()
                for ref in refs}
    for ref in zg.conn_edge:
        s = sheet_of.get(ref)
        if s is not None:
            mobile.setdefault(s, set()).add("snap")
    return {s: frozenset(v) for s, v in sorted(mobile.items())}


def wired_term_sheets(index: TermIndex) -> set[str]:
    """Every zone that PARTICIPATES in a hard term (subject or resolved target;
    the ``@som`` token excluded — it is not a zone)."""
    out: set[str] = set()
    for t in index.hard:
        out.add(t.subject)
        if t.target != _SOM_TOKEN and not t.target.startswith("som_j"):
            out.add(t.target)
    return out


# ---- zone-local metrics --------------------------------------------------------

@dataclass(frozen=True)
class LocalMetrics:
    """Per-sheet zone-LOCAL geometry, replaying build_model's local transform so
    the evaluator can predict the emitted-board gate measures from a zone pose.

    ``offsets``   (ref, dx, dy) for every packed part (top + bottom), zone-local.
    ``pad_union`` (ref, x0, y0, x1, y1) per-part PAD-union box, zone-local —
                  the part's packed offset + its pad geometry under
                  ``(conn_rot + zone_extra_rot) % 360`` (side-independent, the
                  SAME transform ``placement_contract_gate._pad_boxes`` uses).
    ``zone_wh``   the packed zone (w, h)."""
    offsets: tuple[tuple[str, float, float], ...]
    pad_union: tuple[tuple[str, float, float, float, float], ...]
    zone_wh: tuple[float, float]

    @property
    def n_parts(self) -> int:
        return len(self.offsets)


def zone_local_metrics(zg=None) -> dict[str, LocalMetrics]:
    """Compute :class:`LocalMetrics` for every packed sheet from the SHARED zone
    geometry (``subsystem_zone_geometry`` — the same packer the floorplan sizes
    blocks from and the PCB places). Deterministic: sorted refs/sheets."""
    from schgen.verify.placement_contract_gate import _pad_boxes  # lazy: verify
    if zg is None:
        from schgen.generate import pcb as _pcb
        zg = _pcb.subsystem_zone_geometry(two_side=True)

    out: dict[str, LocalMetrics] = {}
    for sheet in sorted(set(zg.top_off) | set(zg.bot_off)):
        offs: list[tuple[str, float, float]] = []
        pads: list[tuple[str, float, float, float, float]] = []
        both = dict(zg.top_off.get(sheet, {}))
        both.update(zg.bot_off.get(sheet, {}))
        for ref in sorted(both):
            dx, dy = both[ref]
            offs.append((ref, dx, dy))
            mod = zg.resolvable.get(ref)
            if mod is None:
                continue
            rot = (zg.conn_rot.get(ref, 0.0)
                   + zg.zone_extra_rot.get(ref, 0.0)) % 360.0
            boxes = _pad_boxes(mod, rot)
            if not boxes:
                continue
            x0 = min(b[0] for b in boxes.values()) + dx
            y0 = min(b[1] for b in boxes.values()) + dy
            x1 = max(b[2] for b in boxes.values()) + dx
            y1 = max(b[3] for b in boxes.values()) + dy
            pads.append((ref, x0, y0, x1, y1))
        w, h = zg.zone_box.get(sheet, (0.0, 0.0))
        out[sheet] = LocalMetrics(offsets=tuple(offs), pad_union=tuple(pads),
                                  zone_wh=(w, h))
    return out


# ---- the exact evaluator --------------------------------------------------------

@dataclass(frozen=True)
class TermEval:
    term: Term
    measured: float      # mm (facing: angle in deg)
    bound: float         # resolved bound (flow: the live budget; facing: 90.0)
    margin: float        # > 0 == green (advisory kinds: margin vs their bound)
    ok: bool
    note: str = ""

    def line(self) -> str:
        t = self.term
        flag = "HARD" if t.enforced else "soft"
        state = "ok" if self.ok else "RED"
        return (f"{flag} {t.kind} {t.subject}->{t.target_raw}: "
                f"{self.measured:.2f} vs {self.bound:.2f} "
                f"(margin {self.margin:+.2f}) {state} [{t.basis}]"
                + (f" {self.note}" if self.note else ""))


def _emitted_zone_frame(pose: tuple[float, float]) -> tuple[float, float]:
    """The emit chain's zone-origin transform: ``gz = _gridify(ORIGIN + z) -
    ORIGIN`` (placement.py STEP 3) — the ONE snap between the floorplan pose
    and the copper."""
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    from schgen.generate.pcb.footprint import _gridify
    zx, zy = pose
    return (_gridify(ORIGIN_X + zx) - ORIGIN_X,
            _gridify(ORIGIN_Y + zy) - ORIGIN_Y)


def predicted_centroid(pose: tuple[float, float], m: LocalMetrics,
                       refs: set[str] | None = None
                       ) -> tuple[float, float] | None:
    """The PAGE-frame equal-weight instance centroid the gate will measure for
    this zone at ``pose`` — full rounding chain replicated: per-part
    ``round(ORIGIN + gz + off, 4)`` (the emit write) then the gate's
    ``round(mean, 4)``. ``refs`` restricts to a subset (facing output parts)."""
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    xs: list[float] = []
    ys: list[float] = []
    for ref, dx, dy in m.offsets:
        if refs is not None and ref not in refs:
            continue
        xs.append(round(ORIGIN_X + gzx + dx, 4))
        ys.append(round(ORIGIN_Y + gzy + dy, 4))
    if not xs:
        return None
    return (round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4))


def predicted_bbox(pose: tuple[float, float], m: LocalMetrics
                   ) -> tuple[float, float, float, float] | None:
    """The PAGE-frame pad-union bbox the gate will measure (zone_bboxes) for
    this zone at ``pose`` — per-part rounded page position + pad-union box,
    outer round(·, 4) exactly like the gate."""
    from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
    gzx, gzy = _emitted_zone_frame(pose)
    a: list[float] | None = None
    off = {ref: (dx, dy) for ref, dx, dy in m.offsets}
    for ref, x0, y0, x1, y1 in m.pad_union:
        dx, dy = off[ref]
        px = round(ORIGIN_X + gzx + dx, 4)
        py = round(ORIGIN_Y + gzy + dy, 4)
        b = (px + (x0 - dx), py + (y0 - dy), px + (x1 - dx), py + (y1 - dy))
        if a is None:
            a = list(b)
        else:
            a[0] = min(a[0], b[0])
            a[1] = min(a[1], b[1])
            a[2] = max(a[2], b[2])
            a[3] = max(a[3], b[3])
    if a is None:
        return None
    return (round(a[0], 4), round(a[1], 4), round(a[2], 4), round(a[3], 4))


def evaluate_terms(board_w: float, board_h: float,
                   som_core: tuple[float, float, float, float] | None,
                   poses: dict[str, tuple[float, float]],
                   metrics: dict[str, LocalMetrics],
                   index: TermIndex,
                   far_guard: dict[str, float] | None = None,
                   som_j_rects: dict[str, tuple[float, float, float, float]]
                   | None = None) -> list[TermEval]:
    """EXACT floorplan-frame evaluation of every term at the candidate ``poses``
    (zone top-left origins, floorplan/board frame). Argument-pure: board size,
    SoM rect (the PAGE-frame ``som_core_rect`` — the ``@som`` resolver), poses,
    metrics and the index all arrive as parameters; nothing reads module
    globals. Metric kernels are the gate's own (single oracle).

    ``far_guard`` maps sheet -> extra mm demanded on far terms involving it
    (the L4-kept participants' measured travel, D-2); defaults to
    ``FAR_L4_GUARD_MM``."""
    from schgen.verify.placement_flow_gate import (  # lazy: verify boundary
        bbox_gap,
        facing_dot,
        flow_budget,
    )
    if far_guard is None:
        far_guard = FAR_L4_GUARD_MM

    budget = flow_budget(board_w, board_h, som_core)

    def centroid_of(name: str) -> tuple[float, float] | None:
        if name == _SOM_TOKEN:
            if som_core is None:
                return None
            x0, y0, x1, y1 = som_core
            return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))
        if name.startswith("som_j"):
            r = (som_j_rects or {}).get(name)
            if r is None:
                return None
            from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
            return (round((r[0] + r[2]) / 2.0 + ORIGIN_X, 4),
                    round((r[1] + r[3]) / 2.0 + ORIGIN_Y, 4))
        if name not in poses or name not in metrics:
            return None
        return predicted_centroid(poses[name], metrics[name])

    def bbox_of(name: str) -> tuple[float, float, float, float] | None:
        if name == _SOM_TOKEN:
            return som_core
        if name.startswith("som_j"):
            r = (som_j_rects or {}).get(name)
            if r is None:
                return None
            from schgen.generate.pcb.constants import ORIGIN_X, ORIGIN_Y
            return (r[0] + ORIGIN_X, r[1] + ORIGIN_Y,
                    r[2] + ORIGIN_X, r[3] + ORIGIN_Y)
        if name not in poses or name not in metrics:
            return None
        return predicted_bbox(poses[name], metrics[name])

    out: list[TermEval] = []
    for t in index.terms:
        if t.kind == "flow_hop":
            ca = centroid_of(t.subject)
            cb = centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, round(budget, 4), -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            # L4-kept participants (P5b): the prediction is only good to the
            # measured guard, so the evaluator demands the hop clear the
            # budget MINUS the guards (conservative; the gate keeps judging
            # the raw budget on the emitted board).
            g = (far_guard.get(t.subject, 0.0) + far_guard.get(t.target, 0.0))
            eff = budget - g
            note = f"incl L4 guard {g:g}mm" if g else ""
            out.append(TermEval(t, d, round(eff, 4),
                                round(eff - d, 4), d <= eff, note))
        elif t.kind in ("near_max", "near_intent"):
            ba = bbox_of(t.subject)
            bb = bbox_of(t.target)
            if ba is None or bb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    t.kind == "near_intent", "UNRESOLVED"))
                continue
            g = bbox_gap(ba, bb)
            if t.kind == "near_intent":     # advisory: never red, value scored
                out.append(TermEval(t, g, 0.0, 0.0, True, "advisory"))
            else:
                out.append(TermEval(t, g, t.bound or 0.0,
                                    round((t.bound or 0.0) - g, 4),
                                    g <= (t.bound or 0.0)))
        elif t.kind == "far_min":
            ca = centroid_of(t.subject)
            cb = centroid_of(t.target)
            guard = max(far_guard.get(t.subject, 0.0),
                        far_guard.get(t.target, 0.0))
            bound = (t.bound or 0.0) + guard
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, bound, -math.inf, False,
                                    "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            note = f"incl FAR_L4_GUARD {guard:g}mm" if guard else ""
            out.append(TermEval(t, d, bound, round(d - bound, 4),
                                d >= bound, note))
        elif t.kind == "facing":
            czone = centroid_of(t.subject)
            cout = (predicted_centroid(poses[t.subject], metrics[t.subject],
                                       refs=set(t.out_refs))
                    if t.subject in poses and t.subject in metrics else None)
            cdown = centroid_of(t.target)
            if czone is None or cout is None or cdown is None:
                out.append(TermEval(t, 180.0, 90.0, -90.0, False,
                                    "UNRESOLVED"))
                continue
            dot, angle = facing_dot(czone, cout, cdown)
            if far_guard.get(t.subject) or far_guard.get(t.target):
                # an L4-kept participant makes the angle unpredictable at
                # composition time (P5b): the evaluator ABSTAINS (ok) and the
                # HARD GATE stays the arbiter on the emitted board (D-5) —
                # the term graduates to constructive enforcement at the
                # participant's own wave.
                out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                    True,
                                    f"dot={dot:+.2f} L4-guarded participant "
                                    f"- gate-arbitrated"))
            else:
                out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                    dot > 0.0, f"dot={dot:+.2f}"))
        else:  # pragma: no cover — build_term_index only emits known kinds
            raise ValueError(f"unknown term kind {t.kind!r}")
    return out


# ---- measured (emitted-model) term table + report -------------------------------

def measure_terms(model, index: TermIndex | None = None) -> list[TermEval]:
    """The SAME term table measured on an EMITTED model via the gate's own
    kernels (zone_centroids / zone_bboxes / facing_dot / flow_budget) — the
    measured half of the exactness pairing. This is gate truth by construction:
    every function is the gate's."""
    from schgen.verify.placement_contract_gate import _board_refs_by_sheet
    from schgen.verify.placement_flow_gate import (
        _members_centroid,
        bbox_gap,
        facing_dot,
        flow_budget,
        zone_bboxes,
        zone_centroids,
    )
    if index is None:
        index = build_term_index(
            sorted({i.sheet for i in model.insts}))
    centroids = zone_centroids(model)
    bboxes = zone_bboxes(model)
    budget = flow_budget(model.board_w, model.board_h, model.som_core)

    def centroid_of(name: str) -> tuple[float, float] | None:
        if name == _SOM_TOKEN:
            if model.som_core is None:
                return None
            x0, y0, x1, y1 = model.som_core
            return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))
        return centroids.get(name)

    def bbox_of(name: str) -> tuple[float, float, float, float] | None:
        if name == _SOM_TOKEN:
            return model.som_core
        return bboxes.get(name)

    out: list[TermEval] = []
    for t in index.terms:
        if t.kind == "flow_hop":
            ca, cb = centroid_of(t.subject), centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, round(budget, 4), -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            out.append(TermEval(t, d, round(budget, 4),
                                round(budget - d, 4), d <= budget))
        elif t.kind in ("near_max", "near_intent"):
            ba, bb = bbox_of(t.subject), bbox_of(t.target)
            if ba is None or bb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    t.kind == "near_intent", "UNRESOLVED"))
                continue
            g = bbox_gap(ba, bb)
            if t.kind == "near_intent":
                out.append(TermEval(t, g, 0.0, 0.0, True, "advisory"))
            else:
                out.append(TermEval(t, g, t.bound or 0.0,
                                    round((t.bound or 0.0) - g, 4),
                                    g <= (t.bound or 0.0)))
        elif t.kind == "far_min":
            ca, cb = centroid_of(t.subject), centroid_of(t.target)
            if ca is None or cb is None:
                out.append(TermEval(t, math.inf, t.bound or 0.0, -math.inf,
                                    False, "UNRESOLVED"))
                continue
            d = math.hypot(ca[0] - cb[0], ca[1] - cb[1])
            out.append(TermEval(t, d, t.bound or 0.0,
                                round(d - (t.bound or 0.0), 4),
                                d >= (t.bound or 0.0)))
        elif t.kind == "facing":
            czone = centroid_of(t.subject)
            cdown = centroid_of(t.target)
            ref_map = _board_refs_by_sheet(t.subject)
            brefs = set(t.out_refs) or {
                ref_map[r] for r in t.output_roles if r in ref_map}
            cout = _members_centroid(model, t.subject, brefs)
            if czone is None or cout is None or cdown is None:
                out.append(TermEval(t, 180.0, 90.0, -90.0, False,
                                    "UNRESOLVED"))
                continue
            dot, angle = facing_dot(czone, cout, cdown)
            out.append(TermEval(t, angle, 90.0, round(90.0 - angle, 4),
                                dot > 0.0, f"dot={dot:+.2f}"))
    return out


def cross_airwires_by_pair(model) -> dict[tuple[str, str], tuple[int, float]]:
    """Per-zone-pair cross-subsystem airwire (count, mm) over the SAME MST the
    LAW-5 gate measures — the D13 channel-demand instrument. Deterministic
    (sorted nets, sorted pair keys)."""
    from schgen.generate.pcb import net_pad_positions
    from schgen.generate.ratsnest import _mst_edges
    pairs: dict[tuple[str, str], list[float]] = {}
    for _net, pts in sorted(net_pad_positions(model).items()):
        for a, b in _mst_edges(pts):
            xa, ya, _ra, sa = pts[a]
            xb, yb, _rb, sb = pts[b]
            if sa == sb:
                continue
            key = (sa, sb) if sa < sb else (sb, sa)
            pairs.setdefault(key, []).append(math.hypot(xa - xb, ya - yb))
    return {k: (len(v), round(sum(v), 1)) for k, v in sorted(pairs.items())}


def channel_demand_mm(n_airwires: int) -> float:
    """D13 channel reservation (mm) for a zone pair with ``n_airwires``
    cross-airwires: floor + per-net demand. 0.0 below the hotspot threshold
    (the ordinary CLEAR applies there)."""
    if n_airwires < CHANNEL_MIN_NETS:
        return 0.0
    return CHANNEL_FLOOR_MM + CHANNEL_PER_NET_MM * n_airwires


def compose_report(model, index: TermIndex | None = None) -> str:
    """The HARD+SOFT composition term ledger for the emitted ``model`` — one
    line per term (measured, bound, margin, basis) + the aggregate-margin
    scalar (informational, IM10) + the D13 channel-demand hotspot table.
    Deterministic text; written to carrier/reports/floorplan_composition.txt
    by ``schgen board``."""
    if index is None:
        index = build_term_index(sorted({i.sheet for i in model.insts}))
    evals = measure_terms(model, index)
    hard = [e for e in evals if e.term.enforced]
    soft = [e for e in evals if not e.term.enforced]
    n_red_hard = sum(1 for e in hard if not e.ok)
    n_red_soft = sum(1 for e in soft if not e.ok)
    # aggregate margin (IM10): sum of HARD margins, min HARD margin — a single
    # scalar time-series for the ledger; informational, never a gate.
    finite = [e.margin for e in hard if math.isfinite(e.margin)]
    agg = round(sum(finite), 2) if finite else 0.0
    mn = round(min(finite), 2) if finite else 0.0
    L = [f"FLOORPLAN COMPOSITION (T1): {len(index.hard)} hard / "
         f"{len(index.soft)} soft terms; hard RED {n_red_hard}, "
         f"soft RED {n_red_soft} (advisory)",
         f"  aggregate hard margin: sum {agg} mm, min {mn} mm "
         f"(informational)"]
    L.append("  hard terms:")
    for e in sorted(hard, key=lambda e: e.term.key):
        L.append("    " + e.line())
    L.append("  soft terms (advisory ledger — repair triggers, never gates):")
    for e in sorted(soft, key=lambda e: e.term.key):
        L.append("    " + e.line())
    unmanaged, managed = corridor_intrusions(model)
    ncorr = len(escape_corridors())
    L.append(f"  T2 escape corridors (D13 never-close): {ncorr} loaded, "
             f"{len(unmanaged)} UNMANAGED part intrusion(s), "
             f"{len(managed)} T2-coexistence-managed")
    for x in unmanaged:
        L.append(f"    UNMANAGED INTRUSION {x}")
    for x in managed:
        L.append(f"    managed {x}")
    ch = [(k, v) for k, v in cross_airwires_by_pair(model).items()
          if channel_demand_mm(v[0]) > 0.0
          and not (k[0].startswith("som_j") or k[1].startswith("som_j"))]
    L.append(f"  D13 channel hotspots (>= {CHANNEL_MIN_NETS} cross-airwires; "
             f"corridor = {CHANNEL_FLOOR_MM:g} + {CHANNEL_PER_NET_MM:g}/net mm):")
    for (a, b), (n, mm) in sorted(ch, key=lambda kv: (-kv[1][0], kv[0])):
        L.append(f"    {a} | {b}: {n} airwires ({mm:.1f} mm) -> "
                 f"corridor >= {channel_demand_mm(n):.1f} mm")
    return "\n".join(L)
# ---- T1 P6: the composition LEGALIZER (P6-core) -----------------------------------
# Appended verbatim to schgen/generate/floorplan_compose.py once the rebase-gate
# builds release the module. See docstrings for the stage map + v1 scoping.


@dataclass
class LegalizeVar:
    """One movable block's solver state (floorplan frame, top-left origin)."""
    name: str
    w: float
    h: float
    seed: tuple[float, float]
    x: float
    y: float


@dataclass
class _Sep:
    """One L1 separation relation: ``lo`` precedes ``hi`` on ``axis`` by at
    least ``gap`` mm. ``basis`` records why the gap is what it is (CLEAR or a
    D13 channel). ``flippable`` relations may have their axis flipped by the
    L3 repair loop (once each — determinism/termination)."""
    axis: str
    lo: str
    hi: str
    gap: float
    basis: str
    flippable: bool


def _pair_axis(a: tuple[float, float, float, float],
               b: tuple[float, float, float, float]) -> tuple[str, bool]:
    """Separating AXIS for two seed rects: larger NORMALIZED gap (gap / mean
    extent); ties x-then-lex. Returns (axis, a_precedes_b)."""
    gx = max(b[0] - a[2], a[0] - b[2])
    gy = max(b[1] - a[3], a[1] - b[3])
    nx = gx / max(1.0, ((a[2] - a[0]) + (b[2] - b[0])) / 2.0)
    ny = gy / max(1.0, ((a[3] - a[1]) + (b[3] - b[1])) / 2.0)
    if nx >= ny:
        return "x", a[0] <= b[0]
    return "y", a[1] <= b[1]


def channel_gap_mm(a: str, b: str, demand: dict[frozenset, int],
                   near_max_pairs: set[frozenset], clear: float
                   ) -> tuple[float, str]:
    """The L1 gap for pair (a, b): the D13 channel corridor when the pair is
    a connectivity hotspot, else CLEAR. PRECEDENCE (judgment, recorded): a
    HARD near_max on the same pair declares an intended tight adjacency whose
    mutual nets TERMINATE at each other (D13's own 'terminus != obstruction'
    nuance — the usb_pd seat's CC nets today, the ethernet|rj45 MDI pairs at
    their wave), so the CITED/near_max adjacency WINS over the
    judgment-grounded channel floor."""
    key = frozenset((a, b))
    if key in near_max_pairs:
        return clear, "near_max-adjacency(terminus)"
    ch = channel_demand_mm(demand.get(key, 0))
    if ch > clear:
        return ch, f"D13-channel({demand.get(key, 0)} nets)"
    return clear, "CLEAR"


def _bellman_ford(nodes: list[str],
                  edges: list[tuple[str, str, float, object]]
                  ) -> tuple[dict[str, float] | None, list[object]]:
    """Difference-constraint feasibility: edge (u, v, c) means x_v - x_u <= c.
    ALL-ZERO init (virtual source). V sweeps — a relaxation in sweep V flags
    infeasibility (spec §4: V, not V-1); the predecessor walk then runs V
    steps to land ON the negative cycle and returns its edge tags."""
    dist = dict.fromkeys(nodes, 0.0)
    pred: dict[str, tuple[str, object]] = {}
    V = len(nodes)
    last = None
    for _sweep in range(V):
        relaxed = False
        for u, v, c, tag in edges:
            if dist[u] + c < dist[v] - 1e-12:
                dist[v] = dist[u] + c
                pred[v] = (u, tag)
                relaxed = True
                last = v
        if not relaxed:
            return dist, []
    node = last
    for _ in range(V):
        node = pred[node][0]
    tags: list[object] = []
    start = node
    while True:
        u, tag = pred[node]
        tags.append(tag)
        node = u
        if node == start or len(tags) > V + 1:
            break
    return None, tags


def legalize_compact(board_w: float, board_h: float,
                     som_core_page: tuple[float, float, float, float],
                     fixed_rects: list[tuple[str, float, float, float, float]],
                     movable: list[LegalizeVar],
                     index: TermIndex,
                     metrics: dict[str, LocalMetrics],
                     fixed_poses: dict[str, tuple[float, float]],
                     channel_demand: dict[frozenset, int],
                     clear: float,
                     compact: bool = False,
                     log: list[str] | None = None,
                     som_j_rects: dict[str, tuple[float, float, float, float]]
                     | None = None) -> bool:
    """T1 P6-core: make every WIRED composition term hold BY CONSTRUCTION for
    one candidate board (spec §6 P6 + the Ring-0 D13 channel injection).

    Stages (v1 scope — cutting planes for flow/facing windows are the pinned
    follow-up; they are exact-checked here and reject when red):
      L0  no hard term / no movable participant -> True, untouched.
      L1  pairwise separations on the seed arrangement's axis, gap = CLEAR or
          the D13 channel corridor (``channel_gap_mm`` precedence).
      L2  HARD near_max windows: dominant-axis gap <= bound - GUARD_MM,
          perpendicular overlap >= 0 (so the emitted bbox_gap is the
          dominant component alone).
      L3  seed-first: if the seeds already satisfy every edge, poses = seeds
          (zero perturbation — the outer search's behavior is byte-identical
          for green candidates, which is also the timing story). Else
          Bellman-Ford feasibility; infeasible -> <= REPAIR_MAX deterministic
          axis flips of cycle separations -> else False (candidate rejected,
          outer grow — LAW 4). Feasible potentials seed a Gauss-Seidel
          window pass that pulls every variable back toward its SEED (the
          minimal-perturbation point of the polytope).
      L5  EXACT accept: ``evaluate_terms`` (full emit rounding chain, GUARD +
          FAR_L4_GUARD) over ALL hard terms; any red -> False with the
          binding term named in ``log``.
      L4' optional COMPACTION (``compact=True``, the final pack only): the
          weighted-median coordinate descent over deduped wired hop pulls
          (W_HOP) + the seed anchor (W_SEED), quantize-Q-then-CLAMP,
          MEDIAN_PASSES; GUARDED — if compaction turns any hard term red it
          is REVERTED wholesale (compaction is an optimizer, never a risk).
      L6  write-back round-4 into the vars.

    Argument-pure: never reads ``fp.BOARD_W/BOARD_H`` (the 2026-06-19 race
    class). Deterministic: sorted iteration, fixed caps, no RNG."""
    if som_j_rects:
        # DF40 receptacle targets resolve like FIXED participants: pose =
        # rect top-left (hull dims come from the rect in _near_max_edges).
        fixed_poses = {**fixed_poses,
                       **{n: (r[0], r[1]) for n, r in som_j_rects.items()}}
    if log is None:
        log = []
    hard = [t for t in index.hard]
    if not hard or not movable:
        return True                                             # L0
    names = sorted(v.name for v in movable)
    by_name = {v.name: v for v in movable}
    vset = set(names)

    def hull(sheet: str) -> tuple[float, float, float, float] | None:
        m = metrics.get(sheet)
        if m is None or not m.pad_union:
            return None
        return (min(b[1] for b in m.pad_union),
                min(b[2] for b in m.pad_union),
                max(b[3] for b in m.pad_union),
                max(b[4] for b in m.pad_union))

    def cent_off(sheet: str) -> tuple[float, float]:
        m = metrics.get(sheet)
        if m is None or not m.offsets:
            v = by_name.get(sheet)
            return (v.w / 2, v.h / 2) if v else (0.0, 0.0)
        xs = [dx for _r, dx, _dy in m.offsets]
        ys = [dy for _r, _dx, dy in m.offsets]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    near_pairs = {frozenset((t.subject, t.target))
                  for t in hard if t.kind == "near_max"}
    frect = {fn: (x0, y0, x1, y1) for fn, x0, y0, x1, y1 in fixed_rects}

    # ---- L1: separations (seed arrangement; D13 channel gaps) --------------
    seps: list[_Sep] = []
    seed_rect = {v.name: (v.x, v.y, v.x + v.w, v.y + v.h) for v in movable}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            axis, first = _pair_axis(seed_rect[a], seed_rect[b])
            gap, why = channel_gap_mm(a, b, channel_demand, near_pairs, clear)
            lo, hi = (a, b) if first else (b, a)
            seps.append(_Sep(axis, lo, hi, gap, why, True))
        for fn in sorted(frect):
            axis, first = _pair_axis(seed_rect[a], frect[fn])
            gap, why = channel_gap_mm(a, fn, channel_demand, near_pairs,
                                      clear)
            lo, hi = (a, f"#{fn}") if first else (f"#{fn}", a)
            seps.append(_Sep(axis, lo, hi, gap, why, True))

    # ---- constraint edges (x_v - x_u <= c), rebuilt after each repair ------
    def build_edges(axis: str) -> list[tuple[str, str, float, object]]:
        E: list[tuple[str, str, float, object]] = []
        for n in names:
            v = by_name[n]
            w = v.w if axis == "x" else v.h
            span = board_w if axis == "x" else board_h
            E.append(("#0", n, span - clear - w, ("wall-hi", n)))
            E.append((n, "#0", -clear, ("wall-lo", n)))
        for s in seps:
            if s.axis != axis:
                continue
            lo_f, hi_f = s.lo.startswith("#"), s.hi.startswith("#")
            if lo_f and hi_f:
                continue
            i0, i2 = (0, 2) if axis == "x" else (1, 3)
            if lo_f:
                r = frect[s.lo[1:]]
                E.append((s.hi, "#0", -(r[i2] + s.gap), ("sep", s)))
            elif hi_f:
                r = frect[s.hi[1:]]
                v = by_name[s.lo]
                w = v.w if axis == "x" else v.h
                E.append(("#0", s.lo, r[i0] - s.gap - w, ("sep", s)))
            else:
                v = by_name[s.lo]
                w = v.w if axis == "x" else v.h
                E.append((s.hi, s.lo, -(w + s.gap), ("sep", s)))
        # L2: HARD near_max windows
        for t in hard:
            if t.kind != "near_max":
                continue
            for e in _near_max_edges(t, axis):
                E.append(e)
        return E

    def _near_max_edges(t: Term, axis: str
                        ) -> list[tuple[str, str, float, object]]:
        s, g = t.subject, t.target
        _jr = (som_j_rects or {}).get(g) if g.startswith("som_j") else None
        hs, hg = hull(s), (hull(g) if _jr is None
                           else (0.0, 0.0, _jr[2] - _jr[0], _jr[3] - _jr[1]))
        bound = (t.bound or 0.0) - GUARD_MM
        if hs is None or hg is None or bound < 0 \
                or (s not in vset and g not in vset):
            return []
        sr = (seed_rect[s] if s in vset
              else _abs(fixed_poses[s], hs))
        gr = (_jr if _jr is not None
              else seed_rect[g] if g in vset
              else _abs(fixed_poses[g], hg))
        dom, s_first = _pair_axis(sr, gr)
        lo, hi = (s, g) if s_first else (g, s)
        hlo, hhi = (hs, hg) if s_first else (hg, hs)
        out: list[tuple[str, str, float, object]] = []
        i0, i2 = (0, 2) if dom == "x" else (1, 3)
        if axis == dom:
            # (x_hi + hhi[i0]) - (x_lo + hlo[i2]) <= bound
            c = bound + hlo[i2] - hhi[i0]
            if lo in vset and hi in vset:
                out.append((lo, hi, c, ("near_max", t)))
            elif lo in vset:
                f = fixed_poses[hi][0 if dom == "x" else 1]
                # x_lo >= f + hhi[i0] - bound - hlo[i2]
                out.append((lo, "#0", -(f + hhi[i0] - bound - hlo[i2]),
                            ("near_max", t)))
            else:
                f = fixed_poses[lo][0 if dom == "x" else 1]
                # x_hi <= f + hlo[i2] + bound - hhi[i0]
                out.append(("#0", hi, f + hlo[i2] + bound - hhi[i0],
                            ("near_max", t)))
        else:
            # perpendicular overlap >= 0 on the NON-dominant axis
            j0, j2 = (1, 3) if dom == "x" else (0, 2)
            k = 1 if dom == "x" else 0
            a0, a2 = hs[j0], hs[j2]
            b0, b2 = hg[j0], hg[j2]
            if s in vset and g in vset:
                out.append((s, g, a2 - b0, ("near_max-perp", t)))
                out.append((g, s, b2 - a0, ("near_max-perp", t)))
            elif s in vset:
                f = fixed_poses[g][k]
                out.append((s, "#0", -(f + b0 - a2), ("near_max-perp", t)))
                out.append(("#0", s, f + b2 - a0, ("near_max-perp", t)))
            else:
                f = fixed_poses[s][k]
                out.append((g, "#0", -(f + a0 - b2), ("near_max-perp", t)))
                out.append(("#0", g, f + a2 - b0, ("near_max-perp", t)))
        return out

    def _abs(p: tuple[float, float], h: tuple[float, float, float, float]):
        return (p[0] + h[0], p[1] + h[1], p[0] + h[2], p[1] + h[3])

    def _descend(px: dict[str, float], py: dict[str, float],
                 hops: tuple[Term, ...], seed_only: bool) -> None:
        for _pass in range(MEDIAN_PASSES):
            moved = 0.0
            for n in names:
                v = by_name[n]
                for axis, pos in (("x", px), ("y", py)):
                    lo, hi = -math.inf, math.inf
                    for u, w2, c, _tag in build_edges(axis):
                        if w2 == n and u != n:
                            hi = min(hi, pos.get(u, 0.0) + c)
                        if u == n and w2 != n:
                            lo = max(lo, pos.get(w2, 0.0) - c)
                    if lo > hi:
                        continue           # transiently empty: keep position
                    i = 0 if axis == "x" else 1
                    pulls: list[tuple[float, float]] = []
                    if not seed_only:
                        co = cent_off(n)
                        for t in hops:
                            other = (t.target if t.subject == n
                                     else t.subject if t.target == n
                                     else None)
                            if other is None:
                                continue
                            if other in vset:
                                oc = cent_off(other)
                                op = (px[other] if axis == "x"
                                      else py[other])
                                pulls.append((W_HOP, op + oc[i] - co[i]))
                            elif other in fixed_poses:
                                oc = cent_off(other)
                                pulls.append((W_HOP,
                                              fixed_poses[other][i]
                                              + oc[i] - co[i]))
                            elif other == _SOM_TOKEN:
                                mid = (som_core_page[i]
                                       + som_core_page[i + 2]) / 2
                                # som rect is page-frame; poses are
                                # floorplan-frame — shift by the page origin
                                from schgen.generate.pcb.constants import (
                                    ORIGIN_X,
                                    ORIGIN_Y,
                                )
                                mid -= (ORIGIN_X if axis == "x" else ORIGIN_Y)
                                pulls.append((W_HOP, mid - co[i]))
                    pulls.append((W_SEED if not seed_only else 1.0,
                                  v.seed[i]))
                    pulls.sort(key=lambda pp: pp[1])
                    tot = sum(w for w, _ in pulls)
                    acc = 0.0
                    best = pulls[0][1]
                    for w2, p2 in pulls:
                        acc += w2
                        if acc >= tot / 2 - 1e-12:
                            best = p2       # tie -> LOWER endpoint (sorted)
                            break
                    q = round(round(best / Q) * Q, 4)
                    q = max(lo, min(q, hi))
                    old = pos[n]
                    if abs(q - old) > 1e-12:
                        pos[n] = q
                        moved = max(moved, abs(q - old))
            if moved <= 1e-9:
                break


    # ---- L3: seed-first feasibility, else BF + repair, then seed-restore ---
    def edges_ok(axis: str, pos: dict[str, float]) -> bool:
        for u, v, c, _tag in build_edges(axis):
            pu = pos.get(u, 0.0)
            pv = pos.get(v, 0.0)
            if pv - pu > c + 1e-9:
                return False
        return True

    posx = {n: by_name[n].x for n in names}
    posy = {n: by_name[n].y for n in names}
    posx["#0"] = 0.0
    posy["#0"] = 0.0
    seed_feasible = edges_ok("x", posx) and edges_ok("y", posy)

    if not seed_feasible:
        for axis, pos in (("x", posx), ("y", posy)):
            for _rep in range(REPAIR_MAX + 1):
                E = build_edges(axis)
                dist, cycle = _bellman_ford(["#0"] + names, E)
                if dist is not None:
                    base = dist["#0"]
                    for n in names:
                        pos[n] = dist[n] - base
                    break
                flipped = False
                for tag in cycle:
                    if isinstance(tag, tuple) and tag[0] == "sep" \
                            and tag[1].flippable:
                        sp = tag[1]
                        seps.remove(sp)
                        seps.append(_Sep("y" if sp.axis == "x" else "x",
                                         sp.lo, sp.hi, sp.gap,
                                         sp.basis + "|flipped", False))
                        log.append(f"repair: flip {sp.lo}|{sp.hi} off "
                                   f"{sp.axis}")
                        flipped = True
                        break
                if not flipped:
                    log.append(
                        "INFEASIBLE " + axis + ": negative cycle ["
                        + ", ".join(
                            (t[1].lo + "|" + t[1].hi if isinstance(t, tuple)
                             and t[0] == "sep" else str(t))
                            for t in cycle[:6]) + "]")
                    return False
            else:
                log.append(f"INFEASIBLE {axis}: REPAIR_MAX exhausted")
                return False
        # seed-restore: coordinate descent, each var clamped to its window's
        # nearest point to the SEED (minimal perturbation), MEDIAN_PASSES.
        _descend(posx, posy, hops=(), seed_only=True)

    # ---- L5: exact accept (pre-compaction) ----------------------------------
    def poses_now() -> dict[str, tuple[float, float]]:
        out = dict(fixed_poses)
        for n in names:
            out[n] = (round(posx[n], 4), round(posy[n], 4))
        return out

    def reds(p) -> list[TermEval]:
        return [e for e in evaluate_terms(board_w, board_h, som_core_page,
                                          p, metrics, index,
                                          som_j_rects=som_j_rects)
                if e.term.enforced and not e.ok]

    r1 = reds(poses_now())
    if r1:
        log.append("REJECT: hard red after legalization: "
                   + "; ".join(f"{e.term.kind} {e.term.subject}->"
                               f"{e.term.target_raw} margin {e.margin}"
                               for e in r1[:4]))
        return False

    # ---- L4': guarded compaction (final pack only) --------------------------
    if compact:
        keepx, keepy = dict(posx), dict(posy)
        hops = tuple(t for t in hard if t.kind == "flow_hop")
        _descend(posx, posy, hops=hops, seed_only=False)
        if reds(poses_now()):
            posx, posy = keepx, keepy
            log.append("compaction REVERTED (would break a hard term)")
        else:
            log.append("compacted (wired hop pulls applied)")

    # ---- L6: write-back ------------------------------------------------------
    for n in names:
        v = by_name[n]
        v.x = round(posx[n], 4)
        v.y = round(posy[n], 4)
    log.append("accept: all hard terms green")
    return True
