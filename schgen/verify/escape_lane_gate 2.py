"""ESCAPE-LANE gate — HARD on the Tier-2 lane PLAN (T2 escape wave).

Judges ``model.escape_plan`` (built by escape.build_escape_plan): the
per-contact surface escape-lane plan whose COPPER lands with the routing
phase (a D13-recorded contract — emitting ~270 intentionally-dangling stubs
today would couple build health to kicad-cli warning-count semantics for
zero measurable gain).  The gate FAILS when the plan is missing — that IS
the red-on-before state.

Checks:
  * identity / port-line MONOTONICITY per row (order-preserving straight
    own-column lanes are feasible because the 0.2 mm inter-pad gap forbids
    crossing inside the pad band; identity is the chosen lexicographic
    optimum — uniqueness holds only within the pad band, so the gate asserts
    monotonic ports, not uniqueness);
  * per-lane clearance pre-proof at the declared widths (adjacent outward
    lanes on the 0.4 pitch);
  * ports sit ON the escape line with the corridor margin;
  * the 15 si_triage-GENUINE pairs meet the HARD pair terms (same-row,
    |delta lane| <= 2 — basis: measured maximum over the 15 GENUINE pairs);
    every other PairRec is report-only topology;
  * pinned population scalars (netted contacts 93/100/100, 15 GENUINE
    pairs) — a SoM-interface drift fails LOUDLY here;
  * content_key verification (som_interface + DP footprint + constants +
    the three DF40 poses) — a floorplan move can never reuse a stale plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: pinned population scalars (drift alarm).  Basis: measured 2026-07-02 on
#: the live SoM interface + carrier link (J1 has 7 unnetted signal pads).
NETTED_PINNED = {"J1": 93, "J2": 100, "J3": 100}
N_GENUINE_PAIRS = 15
GENUINE_DLANE_MAX = 2   # basis: measured maximum over the 15 GENUINE pairs
RULE_CLEARANCE = 0.15
PITCH = 0.4


@dataclass
class EscapeLaneResult:
    ok: bool = True
    n_lanes: int = 0
    n_pairs: int = 0
    n_genuine: int = 0
    violations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        L = [f"ESCAPE-LANE GATE (Tier-2 plan): {'PASS' if self.ok else 'FAIL'}",
             f"  lanes: {self.n_lanes}  pair records: {self.n_pairs}  "
             f"GENUINE pairs: {self.n_genuine}",
             "  lane copper lands with the routing phase (D13 contract); "
             "this gate proves the PLAN"]
        for v in self.violations:
            L.append(f"  VIOLATION: {v}")
        return "\n".join(L)


def check(model) -> EscapeLaneResult:
    res = EscapeLaneResult()
    plan = getattr(model, "escape_plan", None)
    if plan is None:
        res.ok = False
        res.violations.append(
            "model.escape_plan is None — build_escape_plan did not run "
            "(this IS the red-on-before state)")
        return res

    lanes = plan.get("lanes", {})
    res.n_lanes = sum(len(v) for v in lanes.values())

    # ---- netted-count pins ----------------------------------------------------
    for ref, n in sorted(NETTED_PINNED.items()):
        live = plan.get("netted_counts", {}).get(ref)
        if live != n:
            res.ok = False
            res.violations.append(
                f"{ref}: netted contacts {live} != pinned {n} — SoM "
                f"interface drift; re-derive the plan deliberately")

    # ---- monotonic ports + clearance pre-proof per row -------------------------
    for ref, lns in sorted(lanes.items()):
        for row in (-1, 1):
            out = [ln for ln in lns if ln["row"] == row
                   and ln["dir"] == "outward"]
            idx = [ln["lane"] for ln in out]
            if idx != sorted(idx):
                res.ok = False
                res.violations.append(f"{ref} row {row}: lane order not "
                                      f"monotonic")
            # port-line monotonicity: ports ordered along the row axis must
            # follow the lane order (identity — no crossings at the line).
            # The row axis is the VARYING port axis (the other is the constant
            # escape-line coordinate; testing it would pass trivially).
            pts = [ln["port"] for ln in out]
            if len(pts) >= 2:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                vals = xs if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else ys
                if not (vals == sorted(vals)
                        or vals == sorted(vals, reverse=True)):
                    res.ok = False
                    res.violations.append(f"{ref} row {row}: ports not "
                                          f"monotonic along the escape line")
            # adjacent-lane clearance at declared widths on the 0.4 pitch
            # (surface lanes only — GND lanes terminate inward, POWER
            # contacts are plane-escaped: neither runs to the escape line)
            for a, b in zip(out, out[1:], strict=False):
                if b["lane"] - a["lane"] != 1:
                    continue    # a GND/POWER lane vacated the slot between
                if a["net"] == b["net"]:
                    continue    # same net — no clearance term
                gap = PITCH * (b["lane"] - a["lane"]) - (a["width"]
                                                         + b["width"]) / 2
                if gap < RULE_CLEARANCE:
                    res.ok = False
                    res.violations.append(
                        f"{ref} {a['net']}|{b['net']}: adjacent-lane gap "
                        f"{gap:.4f} < {RULE_CLEARANCE}")
        # planes own power: every POWER contact is a plane-escape record and
        # contiguous same-net runs share one bus_group
        planes = sorted((ln for ln in lns if ln["dir"] == "plane"),
                        key=lambda ln: (ln["row"], ln["lane"]))
        for a, b in zip(planes, planes[1:], strict=False):
            if (a["row"] == b["row"] and a["net"] == b["net"]
                    and b["lane"] - a["lane"] == 1
                    and (a.get("bus_group") is None
                         or a.get("bus_group") != b.get("bus_group"))):
                res.ok = False
                res.violations.append(
                    f"{ref} {a['net']}: contiguous POWER contacts "
                    f"{a['lane']}/{b['lane']} not bus-grouped")

    # ---- pair terms -------------------------------------------------------------
    pairs = plan.get("pairs", [])
    res.n_pairs = len(pairs)
    genuine = [p for p in pairs if p["si_class"] == "GENUINE"]
    res.n_genuine = len(genuine)
    if sorted({p["base"] for p in genuine}) != sorted(
            plan.get("genuine_pairs", [])):
        res.ok = False
        res.violations.append("genuine_pairs list inconsistent with PairRecs")
    if res.n_genuine != N_GENUINE_PAIRS:
        res.ok = False
        res.violations.append(
            f"GENUINE pair count {res.n_genuine} != pinned "
            f"{N_GENUINE_PAIRS} — pinout drift, re-verify the hard terms")
    for p in genuine:
        if not p["same_row"] or p["delta_lane"] > GENUINE_DLANE_MAX:
            res.ok = False
            res.violations.append(
                f"GENUINE pair {p['base']} ({p['conn']}): same_row="
                f"{p['same_row']} delta_lane={p['delta_lane']} violates the "
                f"hard terms (<= {GENUINE_DLANE_MAX}, same row)")

    # ---- content key -------------------------------------------------------------
    from schgen.generate.pcb import escape as esc_mod
    conns = {}
    for inst in model.insts:
        ref = esc_mod._SHEET2REF.get(inst.sheet)
        if ref:
            conns[ref] = inst
    live_key = esc_mod._content_key(conns)
    if plan.get("content_key") != live_key:
        res.ok = False
        res.violations.append("content_key STALE — the plan does not match "
                              "the live interface/footprint/poses")
    return res
