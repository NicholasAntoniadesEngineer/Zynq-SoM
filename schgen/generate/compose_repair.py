"""T1 COMPOSITION — the MEASUREMENT LEDGER (P2) and, from P4, the repair
driver (``schgen compose``).

``measure_ledger`` is the SINGLE measurement instrument (decision D12 scalar
time-series): it runs the REAL gates on an emitted model — the wired
placement_flow gate verbatim, PLUS a discover-injected advisory run over EVERY
authored contract (wired or not), the LAW-5 ratsnest gate, the intra-zone
contract register (``check_all`` counts) and the D13 channel-demand pair table.
Advisory floors below are repair TRIGGERS only — never pass/fail (decision
D-5: no new hard gate; the existing gates remain the sole arbiters).

The contracts injection uses the None-filter (IM2): ``discover_contract``
returns None for uncontracted sheets and the gate would crash on a None
contract — the filter is load-bearing and hermetically tested.

Ledger files (``carrier/reports/compose_ledger.json`` + ``.md``) are written
by the DRIVER only (P4) — a plain ``schgen board`` never touches them (the
board build writes ``floorplan_composition.txt`` instead).

Determinism: sorted iteration, no wall-clock in the measured payload, no RNG.
Lazy imports across the generate<->verify boundary (house pattern).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_JSON = PROJECT_ROOT / "reports" / "compose_ledger.json"
LEDGER_MD = PROJECT_ROOT / "reports" / "compose_ledger.md"

# ---- advisory floors (T1 spec §4 — repair TRIGGERS, never pass/fail) -----------
FLOOR_FLOW_MM = 10.0      # judgment: 2 x OUTLINE_SNAP (5.0) — a flow hop within
#                           two outline quanta of its budget is one board-size
#                           step from red
FLOOR_NEAR_MAX_MM = 2.0   # judgment: 2 x occupancy STEP (1.0)
FLOOR_FAR_MM = 5.0        # judgment: 5 x occupancy STEP (1.0)
FLOOR_FACING_DEG = 15.0   # judgment: half the 30-degree facing cone
FLOOR_CROSS_PCT = 5.0     # judgment: L4 credit granularity (3%) + 2%
FLOOR_DISPERSION = 0.5    # judgment: 2 x observed per-wave dispersion jitter


def measure_ledger(model) -> dict:
    """Measure EVERYTHING the composition program tracks, on one emitted
    ``model``. Pure measurement — no writes, no globals."""
    from schgen.generate import floorplan_compose as fc
    from schgen.verify import placement_contract_gate as pcg
    from schgen.verify import placement_flow_gate as pfg
    from schgen.verify import ratsnest_gate as rg

    ledger: dict = {}
    ledger["board"] = {"w": model.board_w, "h": model.board_h,
                       "area_mm2": round(model.board_w * model.board_h, 1)}

    # --- the WIRED hard gate, verbatim (the arbiter's own numbers) ------------
    fres = pfg.check(model)
    ledger["flow_gate"] = {
        "ok": fres.ok,
        "flow_budget_mm": fres.flow_budget_mm,
        "violations": sorted(fres.violations),
        "unresolved": sorted(fres.unresolved),
        "terms": [
            {"kind": t.kind, "subject": t.subject, "target": t.target,
             "measured": (None if math.isinf(t.measured)
                          else round(t.measured, 4)),
             "bound": t.bound, "ok": t.ok}
            for t in fres.terms],
    }

    # --- discover-injected ADVISORY run over every authored contract ----------
    # None-filter (IM2): discover returns None for contract-less sheets; the
    # gate crashes on a None contract, so filter — hermetically tested.
    sheets = sorted({i.sheet for i in model.insts})
    injected = {s: c for s in sheets
                if (c := pcg.discover_contract(s)) is not None}
    ares = pfg.check(model, contracts=injected)
    ledger["advisory_gate"] = {
        "ok": ares.ok,
        "violations": sorted(ares.violations),
        "unresolved": sorted(ares.unresolved),
        "terms": [
            {"kind": t.kind, "subject": t.subject, "target": t.target,
             "measured": (None if math.isinf(t.measured)
                          else round(t.measured, 4)),
             "bound": t.bound, "ok": t.ok}
            for t in ares.terms],
    }

    # --- the deduped composition TERM table (compose module = same kernels) ---
    index = fc.build_term_index(sheets)
    evals = fc.measure_terms(model, index)
    ledger["terms"] = [
        {"kind": e.term.kind, "subject": e.term.subject,
         "target": e.term.target_raw, "enforced": e.term.enforced,
         "measured": None if math.isinf(e.measured) else round(e.measured, 4),
         "bound": round(e.bound, 4), "margin":
             None if math.isinf(e.margin) else round(e.margin, 4),
         "ok": e.ok, "basis": e.term.basis}
        for e in evals]
    finite = [e.margin for e in evals
              if e.term.enforced and math.isfinite(e.margin)]
    ledger["aggregate_hard_margin"] = {
        "sum": round(sum(finite), 2) if finite else 0.0,
        "min": round(min(finite), 2) if finite else 0.0}

    # --- LAW-5 ---------------------------------------------------------------
    rres = rg.check(model)
    slack = rres.cross_budget_mm - rres.cross_mm
    ledger["law5"] = {
        "ok": rres.ok, "cross_mm": rres.cross_mm,
        "budget_mm": rres.cross_budget_mm,
        "slack_mm": round(slack, 1),
        "slack_pct": round(100.0 * slack / rres.cross_budget_mm, 2)
        if rres.cross_budget_mm else 0.0,
        "off_board": len(rres.off_board),
        "dispersed": len(rres.dispersed),
        "dispersion_by_sheet": {
            k: v for k, v in sorted(rg.dispersion_by_sheet(rres).items())},
    }

    # --- intra-zone contract register (A7 no-worsen counts) -------------------
    call = pcg.check_all(model)
    ledger["contract_violations"] = {
        s: len(r.violations) for s, r in sorted(call.items())}

    # --- D13 channel demand ----------------------------------------------------
    pairs = fc.cross_airwires_by_pair(model)
    ledger["channel_hotspots"] = {
        f"{a}|{b}": {"airwires": n, "mm": mm,
                     "corridor_mm": fc.channel_demand_mm(n)}
        for (a, b), (n, mm) in sorted(pairs.items())
        if fc.channel_demand_mm(n) > 0.0
        and not (a.startswith("som_j") or b.startswith("som_j"))}

    # --- advisory floors -> repair TRIGGERS (never pass/fail) ------------------
    triggers: list[str] = []
    for e in evals:
        if not math.isfinite(e.margin):
            continue
        if e.term.kind == "flow_hop" and e.term.enforced \
                and e.margin < FLOOR_FLOW_MM:
            triggers.append(f"flow {e.term.subject}->{e.term.target_raw}: "
                            f"margin {e.margin:.2f} < floor {FLOOR_FLOW_MM}")
        elif e.term.kind == "near_max" and e.term.enforced \
                and e.margin < FLOOR_NEAR_MAX_MM:
            triggers.append(
                f"near_max {e.term.subject}->{e.term.target_raw}: margin "
                f"{e.margin:.2f} < floor {FLOOR_NEAR_MAX_MM}")
        elif e.term.kind == "far_min" and e.term.enforced \
                and e.margin < FLOOR_FAR_MM:
            triggers.append(f"far {e.term.subject}->{e.term.target_raw}: "
                            f"margin {e.margin:.2f} < floor {FLOOR_FAR_MM}")
        elif e.term.kind == "facing" and e.term.enforced \
                and e.margin < FLOOR_FACING_DEG:
            triggers.append(f"facing {e.term.subject}->{e.term.target_raw}: "
                            f"margin {e.margin:.2f}deg < floor "
                            f"{FLOOR_FACING_DEG}")
        if not e.ok and not e.term.enforced and e.term.kind != "near_intent":
            triggers.append(
                f"ADVISORY-RED {e.term.kind} {e.term.subject}->"
                f"{e.term.target_raw}: {e.measured:.2f} vs {e.bound:.2f} "
                f"(repair-before-wire blocker)")
    if ledger["law5"]["slack_pct"] < FLOOR_CROSS_PCT:
        triggers.append(f"law5 cross slack {ledger['law5']['slack_pct']}% < "
                        f"floor {FLOOR_CROSS_PCT}%")
    ledger["repair_triggers"] = sorted(triggers)

    # --- seat-consistency advisory (decision D-1) ------------------------------
    ledger["seat_consistency"] = _seat_consistency(index)
    return ledger


def _seat_consistency(index) -> list[str]:
    """D-1 advisory: any WIRED near_max term whose SUBJECT is an interior block
    anchored ``{"near": <edge block>}`` in floorplan.json (the exact `_anchor`
    edge-seat precondition) must carry an exclusive PULL in the spec — else the
    seat depends on packing luck. Reports the gap; never a gate."""
    from schgen.generate.floorplan import load_floorplan_spec
    spec = load_floorplan_spec()
    if spec is None:
        return []
    flags: list[str] = []
    edge_names = set(spec.edge_of)
    for t in index.hard:
        if t.kind != "near_max":
            continue
        anchor = spec.interior.get(t.subject)
        if not isinstance(anchor, dict):
            continue
        near_tgt = anchor.get("near")
        if near_tgt is None or near_tgt not in edge_names:
            continue           # not the @edge-block near-anchor precondition
        pull = anchor.get("pull")
        if not (isinstance(pull, dict) and pull.get("exclusive")):
            flags.append(
                f"{t.subject}: WIRED near_max -> {t.target_raw} rides the "
                f"floorplan near-anchor at edge block {near_tgt!r} without an "
                f"exclusive pull in carrier/floorplan.json — seat is "
                f"packing-luck (migrate the seat to the pull knob)")
    return sorted(flags)


# ---- SpecEdits (P4) ---------------------------------------------------------------

@dataclass(frozen=True)
class SpecEdit:
    """One reviewable edit to carrier/floorplan.json. ``intent`` edits (edge
    moves) are RATIFICATION-GATED: the driver proposes them only when named in
    ``--allow-intent`` (IM5) — tuning edits (pulls) never move a block between
    edges. ``target_key`` names the (kind, subject, target) TERM the edit
    repairs — banded acceptance requires that term GREEN-or-improved."""
    intent: bool = False
    target_key: tuple | None = None

    def apply(self, raw: dict) -> dict:  # pragma: no cover — abstract
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover — abstract
        raise NotImplementedError


@dataclass(frozen=True)
class AddPull(SpecEdit):
    block: str = ""
    to: str = ""
    weight: float = 10.0
    face: str = "center"
    exclusive: bool = False
    basis: str = ""

    def apply(self, raw: dict) -> dict:
        import copy
        out = copy.deepcopy(raw)
        entry = out.setdefault("interior", {}).setdefault(self.block, {})
        if "pull" in entry:
            raise ValueError(f"{self.block} already carries a pull "
                             f"(one pull per block — use SetPullWeight)")
        entry["pull"] = {"to": self.to, "weight": self.weight,
                         "face": self.face, "exclusive": self.exclusive,
                         "basis": self.basis}
        return out

    def describe(self) -> str:
        return (f"AddPull {self.block} -> {self.to} w={self.weight:g} "
                f"face={self.face} exclusive={self.exclusive}")


@dataclass(frozen=True)
class SetPullWeight(SpecEdit):
    block: str = ""
    weight: float = 10.0

    def apply(self, raw: dict) -> dict:
        import copy
        out = copy.deepcopy(raw)
        entry = out.get("interior", {}).get(self.block)
        if not entry or "pull" not in entry:
            raise ValueError(f"{self.block} has no pull to re-weight")
        out["interior"][self.block]["pull"]["weight"] = self.weight
        return out

    def describe(self) -> str:
        return f"SetPullWeight {self.block} w={self.weight:g}"


@dataclass(frozen=True)
class MoveEdgeBlock(SpecEdit):
    """INTENT edit (D-1 reviewed-JSON-diff rule): move a block between edge
    lists (appended at the target edge's end). Only reachable via
    ``--allow-intent NAME:FROM->TO`` — never proposed by tuning."""
    name: str = ""
    from_edge: str = ""
    to_edge: str = ""
    intent: bool = True

    def apply(self, raw: dict) -> dict:
        import copy
        out = copy.deepcopy(raw)
        edges = out.setdefault("edges", {})
        src = edges.get(self.from_edge, [])
        if self.name not in src:
            raise ValueError(f"{self.name} not on edge {self.from_edge}")
        src.remove(self.name)
        edges.setdefault(self.to_edge, []).append(self.name)
        return out

    def describe(self) -> str:
        return f"MoveEdgeBlock {self.name}: {self.from_edge}->{self.to_edge}"


@dataclass(frozen=True)
class CompositeEdit(SpecEdit):
    """Atomic composite (IM8): e.g. an edge move + the pull that seats a
    partner against it — evaluated and accepted as ONE candidate."""
    edits: tuple[SpecEdit, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent",
                           any(e.intent for e in self.edits))

    def apply(self, raw: dict) -> dict:
        out = raw
        for e in self.edits:
            out = e.apply(out)
        return out

    def describe(self) -> str:
        return " + ".join(e.describe() for e in self.edits)


PULL_LADDER = (2.0, 5.0, 10.0, 20.0, 40.0, 60.0)   # judgment: doubling ladder
#                bounded by the D11-proven 60.0 seat weight


# ---- candidate evaluation (plan replicas — ORDER only, IM9) -----------------------

def _spec_from_raw(raw: dict, valid_names: set[str] | None):
    """Validate + parse an edited RAW spec dict through the SAME loader the
    build uses (written to a scratch file so every invariant applies — the
    driver can never sneak an invalid spec past the validator)."""
    import json as _json
    import tempfile

    from schgen.generate.floorplan import load_floorplan_spec
    with tempfile.NamedTemporaryFile("w", suffix=".json",
                                     delete_on_close=False) as f:
        f.write(_json.dumps(raw))
        f.close()
        return load_floorplan_spec(Path(f.name), valid_names=valid_names)


def plan_replica_metrics(spec):
    """Poses + evaluator inputs for a CANDIDATE spec, via the real build_plan /
    zone packer with the spec INJECTED (IM1) — no file writes. ORDERING ONLY
    (IM9): the evaluator's mobile-sheet error (mm on big zones, L4/snap) makes
    these margins a ranking signal; the authoritative accept re-measures the
    emitted board. Driver is contractually SINGLE-THREADED — build_plan rebinds
    fp.BOARD_W/H module globals (the 2026-06-19 race class), so candidates are
    evaluated strictly sequentially, never in parallel."""
    from schgen.core.link import (
        all_subsystem_paths,
        link,
        load_som_contract,
        load_subsystem,
    )
    from schgen.generate import floorplan as fp
    from schgen.generate import floorplan_compose as fc
    from schgen.generate import pcb as pcb_mod
    from schgen.generate.pcb.placement import som_core_rect
    from schgen.verify import powertree
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    lr = link(sheets, load_som_contract())
    regs = powertree.analyze(sheets).regs
    plan = fp.build_plan(sheets, lr, regs, spec=spec)
    poses = {b.name: (b.x, b.y) for b in plan.blocks}
    som_rect = som_core_rect(plan.som_x, plan.som_y, plan.som.w, plan.som.h)
    zg = pcb_mod.subsystem_zone_geometry(two_side=True, spec=spec)
    metrics = fc.zone_local_metrics(zg)
    smet = fc.zone_shape_metrics(zg)
    for b in plan.blocks:
        if b.shape_idx:
            metrics[b.name] = smet[(b.name, b.shape_idx)]
    return dict(plan=plan, poses=poses, som=som_rect, metrics=metrics,
                W=fp.BOARD_W, H=fp.BOARD_H,
                area=round(fp.BOARD_W * fp.BOARD_H, 1))


def evaluate_candidate(raw_spec: dict, edit: SpecEdit,
                       valid_names: set[str] | None, index):
    """Apply ``edit`` to the raw spec, validate, replica-evaluate every term.
    Returns (term_evals, area, spilled) or raises on an invalid edit."""
    from schgen.generate import floorplan_compose as fc
    edited = edit.apply(raw_spec)
    spec = _spec_from_raw(edited, valid_names)
    ctx = plan_replica_metrics(spec)
    evals = fc.evaluate_terms(ctx["W"], ctx["H"], ctx["som"], ctx["poses"],
                              ctx["metrics"], index)
    return evals, ctx["area"], list(ctx["plan"].spilled), edited


# ---- banded monotone acceptance (§5 law 3; hermetically testable) ------------------

def _term_map(ledger: dict) -> dict[tuple, dict]:
    return {(t["kind"], t["subject"], t["target"]): t
            for t in ledger.get("terms", [])}


def banded_accept(before: dict, after: dict,
                  target_keys: set[tuple] | None = None,
                  allow_area_growth: bool = False) -> tuple[bool, list[str]]:
    """The banded monotone acceptance over two measure_ledger dicts.

    Clauses (each independently REJECTS with a named reason):
      1. all gates PASS on the rebuilt model;
      2. A' <= A (repair steps; ``allow_area_growth`` only defers the verdict
         to the orchestrator's ratified-intent escalation — IM5 — and is set
         ONLY for --allow-intent edits);
      3. every target term GREEN or strictly improved margin;
      4. no term leaves GREEN;
      5. FRAGILE terms (enforced, below-floor margin before) never lose margin;
      6. non-target RED terms never lose margin (IM3);
      7. per-sheet contract_violations counts no-worsen.
    """
    reasons: list[str] = []
    target_keys = target_keys or set()

    if not after["flow_gate"]["ok"]:
        reasons.append("flow gate FAIL on rebuilt model")
    if not after["law5"]["ok"]:
        reasons.append("LAW-5 ratsnest gate FAIL on rebuilt model")

    a0 = before["board"]["area_mm2"]
    a1 = after["board"]["area_mm2"]
    if a1 > a0 + 1e-6 and not allow_area_growth:
        reasons.append(f"area grew {a0} -> {a1} mm^2 (A' <= A violated)")

    tb = _term_map(before)
    ta = _term_map(after)
    floors = {"flow_hop": FLOOR_FLOW_MM, "near_max": FLOOR_NEAR_MAX_MM,
              "far_min": FLOOR_FAR_MM, "facing": FLOOR_FACING_DEG}
    for key in sorted(tb):
        b = tb[key]
        a = ta.get(key)
        if a is None or b["margin"] is None or a["margin"] is None:
            continue
        kind = key[0]
        if key in target_keys:
            if not a["ok"] and a["margin"] <= b["margin"]:
                reasons.append(f"target {key} not improved "
                               f"({b['margin']} -> {a['margin']})")
            continue
        if b["ok"] and not a["ok"]:
            reasons.append(f"{key} left GREEN ({b['margin']} -> "
                           f"{a['margin']})")
        floor = floors.get(kind)
        fragile = (b.get("enforced") and floor is not None
                   and b["margin"] < floor)
        if fragile and a["margin"] < b["margin"] - 1e-9:
            reasons.append(f"FRAGILE {key} lost margin "
                           f"({b['margin']} -> {a['margin']})")
        if (not b["ok"]) and kind != "near_intent" \
                and a["margin"] < b["margin"] - 1e-9:
            reasons.append(f"non-target RED {key} lost margin "
                           f"({b['margin']} -> {a['margin']})")

    cb = before.get("contract_violations", {})
    ca = after.get("contract_violations", {})
    for sheet in sorted(cb):
        if ca.get(sheet, 0) > cb[sheet]:
            reasons.append(f"contract violations worsened on {sheet}: "
                           f"{cb[sheet]} -> {ca.get(sheet)}")
    return (not reasons), reasons


# ---- the repair driver (P4) --------------------------------------------------------

def _parse_allow_intent(items: list[str]) -> list[MoveEdgeBlock]:
    out: list[MoveEdgeBlock] = []
    for it in items or []:
        try:
            name, rest = it.split(":", 1)
            frm, to = rest.split("->", 1)
        except ValueError as exc:
            raise ValueError(
                f"--allow-intent {it!r} must be NAME:FROM->TO") from exc
        out.append(MoveEdgeBlock(name=name.strip(), from_edge=frm.strip(),
                                 to_edge=to.strip()))
    return out


def propose(ledger: dict, raw_spec: dict,
            allow_intent: list[MoveEdgeBlock]) -> list[SpecEdit]:
    """Deterministic candidate catalog from the ledger's repair triggers.

    - near_max / flow / near_intent triggers whose SUBJECT is an interior
      block: AddPull ladder toward the target (exclusive+inboard offered
      when the block's ``near`` anchor already IS the edge-listed target —
      the seat case); SetPullWeight ladder above an existing pull.
    - a trigger whose subject is an EDGE block is only repairable by an edge
      move — INTENT-gated: proposed IFF named in --allow-intent, else
      reported as intent-gated (the D9 case).
    - every --allow-intent move is also offered as a composite with the
      matching partner pull when a near_max pairs the moved block (IM8).
    """
    interior = raw_spec.get("interior", {})
    edge_names = {n for names in raw_spec.get("edges", {}).values()
                  for n in names}
    allowed = {m.name: m for m in allow_intent}
    out: list[SpecEdit] = []
    gated: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    for t in ledger.get("terms", []):
        margin = t.get("margin")
        floors = {"flow_hop": FLOOR_FLOW_MM, "near_max": FLOOR_NEAR_MAX_MM,
                  "near_intent": 0.0}
        kind = t["kind"]
        if kind not in floors:
            continue
        triggered = (not t["ok"]) or (
            t.get("enforced") and margin is not None
            and margin < floors[kind])
        if not triggered:
            continue
        subj = t["subject"]
        tgt = t["target"].split(".", 1)[0]
        tkey = (kind, subj, t["target"])
        if (subj, tgt) in seen_pairs:
            continue
        seen_pairs.add((subj, tgt))
        if subj in edge_names:
            m = allowed.get(subj)
            if m is None:
                gated.append(f"{kind} {subj}->{tgt}: subject is an EDGE "
                             f"block — repair is an INTENT edge move "
                             f"(--allow-intent {subj}:<FROM>-><TO>)")
                continue
            out.append(MoveEdgeBlock(name=m.name, from_edge=m.from_edge,
                                     to_edge=m.to_edge, target_key=tkey))
            # composite: the move + a partner pull when the TARGET is an
            # interior block that could seat against the moved block
            if tgt in interior and "pull" not in interior[tgt]:
                out.append(CompositeEdit(target_key=tkey, edits=(
                    m, AddPull(block=tgt, to=subj, weight=10.0,
                               basis=f"driver: {kind} {subj}<->{tgt} "
                                     f"composite with {m.describe()}"))))
            continue
        entry = interior.get(subj)
        if entry is None:
            gated.append(f"{kind} {subj}->{tgt}: subject not spec-pinned — "
                         f"add it to floorplan.json first (reviewed edit)")
            continue
        if "pull" in entry:
            cur = float(entry["pull"].get("weight", 0.0))
            for w in PULL_LADDER:
                if w > cur:
                    out.append(SetPullWeight(block=subj, weight=w,
                                             target_key=tkey))
        else:
            seat = (entry.get("near") == tgt and tgt in edge_names)
            for w in PULL_LADDER:
                out.append(AddPull(
                    block=subj, to=tgt, weight=w,
                    face="inboard" if seat else "center",
                    exclusive=seat, target_key=tkey,
                    basis=f"driver: {kind} {subj}->{tgt} repair "
                          f"(margin {margin})"))
    ledger["intent_gated"] = sorted(gated)
    return out


def repair(dry_run: bool = True, allow_intent: list[str] | None = None,
           max_steps: int = 4) -> int:
    """ONE driver invocation = at most ONE applied step (risk table: attended,
    serial). Measures, proposes, replica-ranks; with ``--dry-run`` prints the
    ranked table + records the measurement ledger (driver-scoped) but NEVER
    edits carrier/floorplan.json. Applying (not dry_run) writes the spec,
    reruns the authoritative bar (full ``schgen board``) and REVERTS on any
    banded-acceptance rejection."""
    import json as _json
    import subprocess
    import sys

    from schgen.generate import floorplan_compose as fc
    from schgen.generate.floorplan import FLOORPLAN_SPEC
    from schgen.generate.pcb.placement import build_model

    moves = _parse_allow_intent(allow_intent or [])
    print("compose: measuring the emitted board (build_model + gates) ...")
    model = build_model()
    before = measure_ledger(model)
    raw = _json.loads(FLOORPLAN_SPEC.read_text())
    index = fc.build_term_index(sorted({i.sheet for i in model.insts}))

    cands = propose(before, raw, moves)
    print(f"compose: {len(before['repair_triggers'])} trigger(s), "
          f"{len(cands)} candidate edit(s), "
          f"{len(before.get('intent_gated', []))} intent-gated")
    for g in before.get("intent_gated", []):
        print(f"  INTENT-GATED: {g}")
    if not cands:
        write_ledger(before, "measure (no candidates)")
        return 0

    valid_names = None       # loader skips name validation; build re-validates
    ranked: list[tuple[float, str, SpecEdit, dict]] = []
    for e in cands:
        try:
            evals, area, spilled, edited = evaluate_candidate(
                raw, e, valid_names, index)
        except Exception as exc:  # noqa: BLE001 — an invalid candidate is skipped loudly
            print(f"  candidate {e.describe()}: INVALID ({exc})")
            continue
        if spilled:
            print(f"  candidate {e.describe()}: REJECT (spilled: {spilled})")
            continue
        hard_red = [ev for ev in evals if ev.term.enforced and not ev.ok]
        if hard_red:
            print(f"  candidate {e.describe()}: REJECT (predicts hard RED: "
                  f"{[ev.term.key for ev in hard_red]})")
            continue
        finite = [ev.margin for ev in evals
                  if ev.term.enforced and math.isfinite(ev.margin)]
        agg = sum(finite) if finite else 0.0
        # primary: fix the triggered soft reds (count), then aggregate margin,
        # then smaller area; deterministic tiebreak on describe()
        soft_red = sum(1 for ev in evals
                       if (not ev.term.enforced) and not ev.ok
                       and ev.term.kind != "near_intent")
        score = (soft_red, -agg, area, e.describe())
        ranked.append((score, e.describe(), e, {"area": area, "agg": agg}))
    ranked.sort(key=lambda r: r[0])

    print("compose: ranked candidates (replica ORDER only — emitted board "
          "is the arbiter):")
    for _s, desc, _e, info in ranked[:10]:
        print(f"  {desc}: predicted agg-hard-margin {info['agg']:.1f}, "
              f"area {info['area']}")
    if dry_run or not ranked:
        write_ledger(before, "measure/dry-run")
        return 0

    # ---- apply the best candidate (ONE step), authoritative accept ---------
    best = ranked[0][2]
    print(f"compose: applying {best.describe()}")
    original = FLOORPLAN_SPEC.read_text()
    edited = best.apply(raw)
    FLOORPLAN_SPEC.write_text(_json.dumps(edited, indent=2) + "\n")
    r = subprocess.run([sys.executable, "-m", "schgen", "board"],
                       cwd=str(REPO_ROOT), capture_output=True, text=True)
    ok = r.returncode == 0
    after = None
    if ok:
        after = measure_ledger(build_model())
        # the FULL band always applies (A' <= A included) — IM5: an INTENT
        # edit failing ONLY the area clause is not silently vetoed, it is
        # ESCALATED with the measured growth for the orchestrator's ~+5%
        # wave judgment; the file is still reverted (a human applies the
        # ratified growth deliberately). Tuning edits never escalate.
        accepted, reasons = banded_accept(
            before, after,
            target_keys=({best.target_key} if best.target_key else None),
            allow_area_growth=False)
        if best.intent and not accepted \
                and all("area grew" in x for x in reasons):
            print("compose: intent edit grew the board — ESCALATION to the "
                  "orchestrator's wave judgment (IM5), reverting the file; "
                  "measured growth:")
            for x in reasons:
                print(f"  ESCALATE: {x}")
        ok = accepted
        if not accepted:
            for x in reasons:
                print(f"  REJECT: {x}")
    else:
        print(r.stdout[-2000:])
        print("compose: board build FAILED under the edit")
    if not ok:
        FLOORPLAN_SPEC.write_text(original)
        print("compose: REVERTED carrier/floorplan.json")
        write_ledger(before, f"rejected: {best.describe()}")
        return 1
    write_ledger(after, f"applied: {best.describe()}")
    print("compose: ACCEPTED (ledger updated) — commit is a human review "
          "step (reviewed-JSON-diff rule, D-1)")
    return 0


# ---- ledger writers (DRIVER-written only — P4) -----------------------------------

def write_ledger(ledger: dict, step_label: str,
                 json_path: Path = LEDGER_JSON,
                 md_path: Path = LEDGER_MD) -> None:
    """Append ``ledger`` (as a labelled step) to compose_ledger.json and rewrite
    the .md view. DRIVER-ONLY: a plain board build never calls this."""
    history: list = []
    if json_path.exists():
        history = json.loads(json_path.read_text())
    history.append({"step": step_label, "ledger": ledger})
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(history, indent=1, sort_keys=True) + "\n")

    L = ["# compose ledger (T1) — driver-written measurement time-series", ""]
    for h in history:
        led = h["ledger"]
        b = led["board"]
        agg = led["aggregate_hard_margin"]
        L.append(f"## {h['step']}")
        L.append(f"- board {b['w']:g} x {b['h']:g} = {b['area_mm2']} mm^2")
        L.append(f"- hard margin sum {agg['sum']} / min {agg['min']} mm")
        L.append(f"- LAW-5 slack {led['law5']['slack_pct']}%")
        L.append(f"- repair triggers: {len(led['repair_triggers'])}")
        for t in led["repair_triggers"]:
            L.append(f"  - {t}")
        L.append("")
    md_path.write_text("\n".join(L))
