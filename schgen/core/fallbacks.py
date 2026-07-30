"""FALLBACK EVENT REGISTRY — every degraded/fallback path in the placement
pipeline is a NAMED event recorded HERE when it fires (governance U2).

The defect class this closes: silent fallbacks. motor_sense sat on the legacy
zone packer for WEEKS (its template solver was infeasible and the None return
fell through without a trace, 12 contract terms adrift). That legacy branch is
now DELETED — a solver-infeasible contract zone raises ``ZoneInfeasible``
(stage_templates), a loud build failure, per the user law: no backwards
compatibility, no legacy, no silent fallbacks. What REMAINS registered here
are the surviving alternate paths that are legitimate correctness choices
(rejecting an ILLEGAL compaction) or bounded-search caps — and every one must
be LOUD: ``schgen board`` prints the census, writes it into
``board_verdicts.json`` and the ratchet gate
(``schgen/verify/fallback_gate.py``) FAILS the build the moment any count
exceeds its committed per-project baseline — a path silently degrading more
often becomes a same-day build failure.

Recording an UNREGISTERED name raises: a new fallback path must be declared
here (name, stage, meaning) before it may fire. ``build_model`` resets the
recorder at entry; the census is read after board emission, so events fired
anywhere in the build_model -> emit_pcb window are counted. Single writer
(the build runs the placement pipeline on one thread), deterministic order,
no caching.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fallback:
    name: str
    stage: str
    meaning: str


REGISTRY: dict[str, Fallback] = {}


def _register(name: str, stage: str, meaning: str) -> None:
    if name in REGISTRY:
        raise AssertionError(f"fallbacks: duplicate registration {name!r}")
    REGISTRY[name] = Fallback(name=name, stage=stage, meaning=meaning)


_register(
    "legalize_only_compaction", "plan_lattice",
    "The composition legalizer's COMPACTION objective could not keep every "
    "D13 pair gap; the board kept the legalize-only form the outline scan "
    "accepted (wired hop pulls forgone). Measured cause (scan B, L2): the "
    "compacted form passes the legalizer's own L5 accept but _pairs_hold "
    "rejects it — the legalizer moves blocks at flat CLEAR, blind to "
    "reach/inset. Counted PER COMPACT PACK: the wave-8 U3 conn-shape "
    "chooser re-runs the full compact pack per mirror trial, so the count "
    "scales with trials (carrier 10 = final 2 + 4 trials x 2; the per-pack "
    "behavior is unchanged).")
_register(
    "seat_node_budget", "zone_pack",
    "A template seat DFS exceeded its 300k node budget and was treated as "
    "infeasible at that pad (the widen loop retries; repeated firing means "
    "the template is effectively unsolvable and headed for legacy fallback).")
_register(
    "cand_cap_truncated", "zone_pack",
    "A ranked candidate-pose list exceeded _CAND_CAP (400) and was "
    "truncated — the seat search never saw the tail poses (counted per "
    "truncating candidate-generation call). Measured (scan B, F5/L4): binds "
    "on 6 carrier solves — ethernet C10001/C10005 (max 992), power "
    "R20011/R20013 (max 1301), power_som R22017, usb_pd C30002; benign "
    "today (nearest-first keeps the best 400, all seats found).")
_register(
    "thermal_via_lattice", "emission",
    "A thermal via seated from the exhaustive 0.25 mm lattice over the "
    "part's own pour because a curated preferred site was blocked by a "
    "neighbour (per via; also printed loud per part). Measured (scan B, "
    "F11/L5): fmc U11001 (VADJ LDO) is 3/3 lattice-seated on the carrier.")
_register(
    "bottom_variant_contract_reject", "zone_pack",
    "A sheet DECLARED bottom-eligible (floorplan.json interior side "
    "\"bottom\"/\"either\") whose X-mirrored bottom shape failed the re-measure "
    "of its authored placement contract (_mirror_contract_holds on the "
    "mirrored offsets) — the bottom variant is NOT offered and the block "
    "keeps its top-side shape set (a correctness choice, never a silent "
    "degrade). Counted per zone-geometry pass; the board flow runs the "
    "shared packer twice, so one rejected sheet counts 2.")
_register(
    "corridor_evict_moved", "corridor_eviction",
    "A bottom-side stray inside a DF40 stitch corridor was evicted to the "
    "nearest legal exit (per part moved). Measured (scan B, F13): carrier "
    "0, devkit 33 (power/power_som bands). The scan-L1 frame-shift caveat "
    "is CLOSED (wave-8 U1): corridors are measured at the POST-gridify "
    "DF40 centres (registered evict_corridor_grid), the same frame the "
    "emitted board and the escape solver share.")
_register(
    "corridor_stray_unmovable", "corridor_eviction",
    "A bottom-side stray inside a DF40 stitch corridor found no legal exit "
    "and stayed put — the escape solver must then prove coexistence or fail "
    "the build loudly (loud only on TOTAL infeasibility; partial seat "
    "degradation is absorbed by the ladder/coexistence machinery).")


_EVENTS: list[str] = []


def reset() -> None:
    _EVENTS.clear()


def record(name: str) -> None:
    if name not in REGISTRY:
        raise AssertionError(
            f"fallbacks: {name!r} fired but is not a registered fallback — "
            f"declare it in schgen/core/fallbacks.py (name, stage, meaning) "
            f"before it may fire")
    _EVENTS.append(name)


def census() -> dict[str, int]:
    counts = {name: 0 for name in sorted(REGISTRY)}
    for name in _EVENTS:
        counts[name] += 1
    return counts
