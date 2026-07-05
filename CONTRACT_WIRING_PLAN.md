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

## Current state / resume point
- **master = fdbefe9** — coverage report live; thermal buck-spread + place_near speedup + escape-safe
  growth enabler all landed. Board 178×163, all gates green.
- **WIRED (3):** power, usb_pd, ethernet.
- **INERT-MET (2)** — coincidentally OK, no wiring needed (optionally gate for lock-in): board_qwiic, hdmi_rx_term.
- **INERT-VIOLATED (18)** — the backlog below. **0 / 18 done.**

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
