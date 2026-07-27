# Contract Wiring Plan — enforce the placement contracts

*Living plan. Resumable across sessions. Companion to `PLACEMENT_ALGORITHM_ROADMAP.md`.*

## Why this exists
The board authors **23 per-subsystem placement contracts** (`subsystems/<name>/placement_contract.py`) —
datasheet-cited SI/PI intent: decoupling ≤2 mm from its IC, ESD at the connector, buck hot-loop
tight, terminations at the receiver. But only **3 are WIRED** (`power`, `usb_pd`, `ethernet`): their
template is run by the placer **and** their contract is gated HARD. The other 20 are **INERT** —
`load_contract()` returns `None` for any sheet not in `_WIRED_SHEETS`, so the placer shelf-packs
them (decoupling-blind) and the gate never checks them.

**Result (measured 2026-07-05): 18 of 23 contracts are silently violated** — bypass caps 20–39 mm
from their ICs, a buck hot-loop cap missing, ESD 8–27 mm from connectors. A contract you neither
place nor check is just a comment.

**Accountability already landed (`master fdbefe9`):** the `CONTRACT COVERAGE` report now checks
EVERY authored contract each build (report-only) → `carrier/reports/contract_coverage.txt`, tallying
`wired-gated / inert-met / inert-VIOLATED`. The gap is now visible + tracked, never silent. **This
plan is step two: enforce it** by wiring each violated contract.

## Done-bar (measurable)
`schgen board` prints `CONTRACT COVERAGE: 23 wired(gated) / 0 inert-met / 0 inert-VIOLATED`
(or an explicitly-documented smaller subset if some prove infeasible). Every wired sheet:
PLACEMENT CONTRACT 0 violations + ALL gates green + build-twice byte-identical.

## THE MECHANIC IS BUILT (2026-07-05) — the reusable product

The blocker was never per-sheet effort; it was a **missing engine capability**. The placer only
ever modelled a **single anchor-star** (one IC + its direct members). A real contract is a
**multi-anchor constraint graph** (camera: FFC→ESD, then ESD-IC→terminations with a `min_from`
clearance vs the FFC, then term→term-cluster), so **11 of the 18** violated contracts were
*structurally un-enforceable* — the placer dropped every non-primary-anchor member to an
unconstrained shelf-pack, and no amount of wiring could fix that.

**Landed:** a general **multi-anchor constraint-graph solver** (`_solve_contract` in
`stage_templates.py`) — parses any contract's proximity structures into attractors
(pad-edge ≤ `max_mm` to an anchor's pins) + repulsors (pad-edge ≥ `min_mm` from *any* part) +
same_side, splits into connected components, seats each greedily in topological order with
widen-on-infeasible, and **respects fan-out clearance** (mirrors `fanout_gate` exactly — non-passive
members keep ≥ `intelligent_need` from multi-pin ICs; plain decoupling stays exempt). Deterministic,
no randomness. The two pilot sheets (usb_pd/ethernet) keep the byte-identical legacy path.
**Proven:** a data-driven parametrized test (`test_proximity_contract_is_solved`) shows **all 19
proximity contracts now satisfy their own gate** (were 18-violated); camera is the multi-anchor
archetype test. Three real bugs were found+fixed via the fast (1 s) test loop: grid-radius sizing,
independent-cluster jamming (→ per-component isolation), and per-node backtracking blow-up (→ greedy).

## WIRING IS A DELICATE BOARD-INTEGRATION FOLLOW-UP (not a mechanic gap)

Flipping contracts into `_WIRED_SHEETS` is electrically correct (the contract gate + fan-out gate
both pass for the wired sheets) but **perturbs a hand-optimised board**, and each perturbation trips
a *different* delicate constraint — measured, not theorised:
- **Batch of 5** (fmc/motor_pwm/power_mon/uart_bridge/usb_jtag): contract gate PASS (59 structures,
  0 viol), coverage 18→13, DRC 0 — but the board grew 178→**188 mm** because motor_pwm + usb_jtag
  are known **cramped clusters** (breathe.py), and that growth repacked the *unrelated* bringup zone
  under the fan-out floor (12→6 starved after the fan-out-aware fix).
- **Batch of 3** (fmc/power_mon/uart_bridge): fan-out back to **0 starved**, but the layout shift
  moved a bringup B.Cu cap (C5009) into the **DF40 stitch-via corridor** → a **LAW-0 return-path**
  failure (`no feasible stitch-via seat for J2.92`), thermal cascading from the aborted pour.

**Lesson:** the board is a tight optimum; enforcing new datasheet clustering on it cascades into
fan-out (cramped clusters), the DF40 return-stitch corridor (LAW-0, *untouchable*), and thermal.
Wiring therefore needs a **staged campaign** with real dependencies, NOT a one-shot flip:
1. floorplan **compaction** so a solved cluster is ≤ its old scattered footprint (no board growth), OR
   a conscious board-growth budget the user signs off on;
2. the **queued bottom-channel-keepout unit** (move blocking B.Cu strays out of the DF40 corridor);
3. thermal-pour re-credit after any layout shift;
4. then wire, one sheet at a time, each build-verified green.

## Current state / resume point
- **master = e55d854** (coverage report). Board 178×163, all gates green.
- **MECHANIC:** the multi-anchor solver is committed (inert — `_WIRED_SHEETS` still the 3 pilots — so
  the shipping board is **byte-identical**; the solver only activates when a sheet is wired).
- **WIRED (3):** power, usb_pd, ethernet. **INERT-VIOLATED (13 after the coverage report's own count;
  18 by structure).** Wiring is the staged campaign above; **0 sheets wired past the pilots** (each
  attempt tripped a delicate board constraint — see the measured batches).

## The per-sheet wiring procedure (the repeatable unit — do ONE sheet at a time)
For each sheet `<S>`:
1. Add `"<S>"` to `_WIRED_SHEETS` in `schgen/verify/placement_contract_gate.py`.
2. `python3 -m schgen board`.
3. **VERIFY (all must hold):**
   - `PLACEMENT CONTRACT`: PASS — the newly-wired sheet's contract → **0 violations**.
   - `CONTRACT COVERAGE`: inert-VIOLATED count drops by 1 (`<S>` → wired-gated).
   - ALL other gates green: RATSNEST LAW-5, THERMAL, RETURN STITCH 29/29, ESCAPE LANES, FAN-OUT
     0-starved, DRC 0, FAB PROFILE, REFDES-SILK, PLACEMENT MECH/FLOW.
   - **build-twice byte-identical** (determinism).
   - No contract member of ANOTHER sheet moved (spot-check positions).
4. **GREEN →** commit `feat(contract): wire <S> — <SI/PI intent enforced>`, push. Tick the box below.
5. **TRIPS a gate** (fan-out/DRC/silk/contract-self-violation — as camera did) → diagnose:
   - *Fixable placement* (template placed it, a neighbour got tight) → adjust + re-verify.
   - *Template-builder gap* (builder can't satisfy the structure — multi-group / `min_from` / facing)
     → **DEFER to Wave C**, record which capability it needs. **NEVER soften a gate (LAW 4).**

## Ordered backlog

### Wave A — the buck (highest PI severity; existing `_build_buck_stage` builder)
- [ ] **power_som** — buck hot-loop cap missing at U4 (VIN/PGND, 39 struct viol). The buck-stage
  builder EXISTS (power uses it). Re-attempt now that the escape-corridor keepout + L4 same-side
  handling landed (earlier power_som wiring hit the thermal-via/escape-graze — recheck). If it
  re-trips → Wave C.

### Wave B — simple decoupling / ESD proximity, worst-first (existing `_build_proximity_zone`)
Wire-able like usb_pd (proximity-only, single anchor family, no `min_from`). One at a time:
- [ ] usbc_otg — bypass 26 mm (U1→C1)
- [ ] power_mon — bypass 20 mm
- [ ] pmod_expansion — 19 mm
- [ ] lcd — 14 mm
- [ ] pmod — ESD 14 mm (J1→U1)
- [ ] hdmi_tx — ESD 8 mm (13 viol)
- [ ] hdmi_rx — ESD 8 mm
- [ ] fmc — 7.5 mm
- [ ] usb_jtag_connector — ESD 6.4 mm
- [ ] usb_uart_connector — ESD 6.4 mm
- [ ] pd_input — 4.5 mm (barely)
- [ ] uart_bridge — 3.8 mm (barely)

### Wave C — complex (build the builder capability FIRST, then wire)
These carry multi-group / `min_from` / receiver-facing the current proximity-cluster builder can't
satisfy (the camera build proved it: it jammed a term 2 mm from the FFC + starved fan-out).
**Capability to build:** proximity-cluster MULTI-BAND placement (ESD ≤5 mm at the connector AND terms
≥8 mm inboard, honouring `min_from`) + receiver-end FACING (the "future work" the camera/lcd contracts
flag). Then wire:
- [ ] camera (ESD ≤5 mm + D-PHY terms ≥8 mm `min_from` + facing)
- [ ] microsd (multi-anchor, 10 viol)
- [ ] motor_pwm (39 mm, 17 viol)
- [ ] motor_sense (30 mm, 11 viol)
- [ ] usb_jtag (15 viol; contains crystal Y28001 — a proximity + keep-away)

### Wave D — optional lock-in (already met)
- [ ] board_qwiic, hdmi_rx_term — inert-MET today; wiring GATES them (prevents future regression). Low priority.

## Risks & policy
- **LAW-0:** never touch `escape.py` / DF40 / return-path copper. The escape-corridor keepout (landed)
  protects the stitch corridor during any re-pack.
- **LAW-4:** never soften a gate — if a wiring trips a gate, fix the placement or defer, never relax the check.
- **Determinism:** each wiring must build byte-identical twice.
- **Board size:** wiring should keep the board sane (~178×163); if a wiring inflates it, that's a red
  flag → defer.
- **Per-sheet commit + push** (resumable); update the checkbox + `Progress` line each time.

## Progress
**0 / 18 wired.** Next: Wave A (power_som) → then Wave B worst-first. Track live via
`carrier/reports/contract_coverage.txt` (`inert-VIOLATED` count must trend to 0).
