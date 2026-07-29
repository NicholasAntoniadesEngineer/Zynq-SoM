"""STAGE MANIFEST + MOVEMENT TRIPWIRE for ``build_model`` (governance U3).

The geometry pipeline's stage ORDER is load-bearing: refit_facing once mutated
positions AFTER guards had judged them, and the reorder pass's nothing-moves-
after-me constraint lived only in prose. This module makes the order a DECLARED
artifact: ``PLACEMENT_STAGES`` is the one ordered manifest of build_model's
geometry stages, each entry declaring whether the stage may move parts and
what validates the movement. ``build_model`` drops a ``StageTracker``
checkpoint at every stage boundary; movement observed in a ``may_move=False``
stage raises ``StageMovementError`` LOUDLY, naming the stage and the first
moved refs. Always on, deterministic, one dict snapshot per boundary.

Snapshots are per-DOMAIN (``board`` = the pos/rot dict build_model mutates;
``page`` = the emitted FootprintInst frame): a stage is compared only against
the previous snapshot of its own domain, and the first snapshot of a domain is
its baseline. Checkpoints must arrive in manifest order (stages may be
skipped, never reordered). ``docs/GEOMETRY_PIPELINE.md`` is generated from
this manifest so the map cannot rot.
"""
from __future__ import annotations

from dataclasses import dataclass


class StageMovementError(AssertionError):
    pass


@dataclass(frozen=True)
class Stage:
    name: str
    may_move: bool
    tracked: bool
    domain: str
    validated_by: str
    desc: str


PLACEMENT_STAGES: tuple[Stage, ...] = (
    Stage("zone_pack", True, False, "board",
          "netlist identity + per-zone D13 fan-out reservation + registered "
          "shape metrics; contracted sheets: the stage/proximity template — "
          "NO legacy fallback (an infeasible/unresolvable contract raises "
          "ZoneInfeasible, a loud build failure)",
          "subsystem_zone_geometry — per-subsystem 2-sided packed zones "
          "(offsets in each zone's local frame; no board positions yet)"),
    Stage("plan_lattice", True, False, "board",
          "occupancy-lattice separation + _pairs_hold + composition "
          "legalizer (infeasible candidates rejected) + LAW-5 airwire "
          "budget estimate",
          "fp.build_plan — block poses on the sized outline (smallest-area "
          "search + fine refinement + legalize/compact)"),
    Stage("shape_bind", False, False, "board",
          "apply_chosen_shapes raises on an unregistered shape index",
          "rebind zone views to the plan's chosen per-block shapes"),
    Stage("step3_emission", True, True, "board",
          "exact floorplan pose transfer (no zone snap); every later gate "
          "and DRC measure the emitted result",
          "STEP-3 — absolute positions: MH corners, SoM receptacles, zone "
          "origin + packed offset, som_decoupling grid"),
    Stage("l4_pull", True, True, "board",
          "collision _free set (bottom occupancy + top-THT + armed escape "
          "corridors) + on-board margin + dispersion cap",
          "LEVER L4 — rigid SoM-ward pull of bottom passive clusters"),
    Stage("edge_seat", True, True, "board",
          "EDGE_PAD_CLEAR pad-flush seat on the perpendicular axis only; "
          "placement_mech (LAW 6) judges the result",
          "seat every off-board connector AT its board edge"),
    Stage("breathe", True, True, "board",
          "_free + leash re-validation of every committed snapped delta "
          "(registered breathe_anchor_grid) + per-sheet dispersion "
          "fail-safe revert",
          "FAN-OUT BREATHE — starved movable ICs spread into adjacent "
          "free space (phases A/B)"),
    Stage("refit_facing", True, True, "board",
          "flow-gate facing_dot kernel replica — turns 180 only when the "
          "gate would fail; re-validated by the emitted-board gates "
          "(placement_flow FACING + contract gate + DRC). Measured live: "
          "the carrier power zone turns 180 as one rigid 51-part move",
          "position-aware FACING refit of contracted downstream zones on "
          "the frozen frame"),
    Stage("reorder", True, True, "board",
          "identical-courtyard slot permutation (same footprint/rot/side "
          "class) accepted only on a strict crossing-count drop — the "
          "occupied geometry set is invariant",
          "permute interchangeable parts among their frozen slots to "
          "uncross airwire fans"),
    Stage("corridor_eviction", True, True, "board",
          "corridor collision re-check + bottom/THT/edge guards on every "
          "exit; moved and unmovable strays are registered fallback "
          "events; escape gate (frame-shift caveat: the DF40 "
          "emission-gridify lands AFTER this eviction math — corridor "
          "shift up to 0.59 mm carrier / 0.38 mm devkit vs the 0.25 mm "
          "eviction margin; re-check queued wave-8)",
          "evict bottom strays from the PRE-gridify DF40 stitch corridors "
          "on FINAL board-frame positions"),
    Stage("instantiate", False, True, "board",
          "movement tripwire (this manifest): pos is frozen — the "
          "emission loop only projects it",
          "FootprintInst emission — nothing may move a board-frame "
          "position after corridor_eviction"),
    Stage("emission_frame", True, True, "page",
          "page projection = ORIGIN shift + the registered fixed_part_grid "
          "snap (MH/SoM refs only — measured DF40 shift up to 0.59 mm "
          "carrier / 0.38 mm devkit, the frame-shift the corridor_eviction "
          "caveat names); byte-identity proves inertness",
          "page-frame baseline snapshot of the emitted instances "
          "(+ fiducials)"),
    Stage("escape_copper", False, True, "page",
          "movement tripwire (this manifest): escape derives copper from "
          "the frozen frame and must never move a footprint",
          "DF40 return-stitch copper + Tier-2 lane plan"),
)

_STAGE_BY_NAME = {s.name: s for s in PLACEMENT_STAGES}
_STAGE_INDEX = {s.name: i for i, s in enumerate(PLACEMENT_STAGES)}

Snapshot = dict[str, tuple]


class StageTracker:
    """One per ``build_model`` call. ``checkpoint(stage, snap)`` hashes the
    (ref -> pose) snapshot at a stage boundary, enforces manifest order,
    counts movement vs the previous same-domain snapshot into ``moves``, and
    raises ``StageMovementError`` on movement in a ``may_move=False`` stage."""

    def __init__(self) -> None:
        self._last: dict[str, Snapshot] = {}
        self._idx = -1
        self.moves: dict[str, int] = {}

    def checkpoint(self, stage_name: str, snap: Snapshot) -> None:
        stage = _STAGE_BY_NAME.get(stage_name)
        if stage is None:
            raise StageMovementError(
                f"STAGE MANIFEST: {stage_name!r} is not a declared stage — "
                f"add it to PLACEMENT_STAGES (ordered, may_move, "
                f"validated_by) before checkpointing it")
        idx = _STAGE_INDEX[stage_name]
        if idx <= self._idx:
            raise StageMovementError(
                f"STAGE MANIFEST: checkpoint {stage_name!r} arrived out of "
                f"declared order (after "
                f"{PLACEMENT_STAGES[self._idx].name!r})")
        self._idx = idx
        if not stage.tracked:
            return
        prev = self._last.get(stage.domain)
        self._last[stage.domain] = dict(snap)
        if prev is None:
            return
        moved = sorted(r for r in snap
                       if r in prev and snap[r] != prev[r])
        self.moves[stage_name] = len(moved)
        if moved and not stage.may_move:
            first = ", ".join(
                f"{r} {prev[r]} -> {snap[r]}" for r in moved[:3])
            raise StageMovementError(
                f"STAGE MOVEMENT: stage {stage_name!r} declares "
                f"may_move=no but {len(moved)} part(s) moved ({first}) — "
                f"a geometry mutation ran after its declared window; move "
                f"the mutation to a may_move stage in PLACEMENT_STAGES or "
                f"delete it, never widen the manifest silently")
