# T1 P6-wire — legalizer live in the packer (evidence)

Base: 9f77031 (the merged T1 unit). Delivered (uncommitted):

- `floorplan.py`: composition inputs computed ONCE per `build_plan`
  (TermIndex + zone-local metrics + D13 channel-demand map + T2 escape
  corridors; demand proxy = EXCLUSIVE pair nets — position-independent,
  deterministic, equals the measured MST count on the hotspot pairs, e.g.
  pd_input|usb_pd 8==8); threaded into all four `_attempt_pack` call sites;
  `legalize_compact` at the pack tail — REJECT -> outer grow (LAW 4);
  `compact=True` only at the fixed-outline call + the final re-pack;
  `Plan.composition` log.
- Movable set = hard-term participants ∩ interior ∩ **l4_exempt** (pose-
  predictable). REFINED DURING THE GATE by a caught regression (below).

## Timing proof (spec: <= +10s)

- A/B in one process (same caches): build_plan wired 66.9s vs baseline
  (compose forced off) 66.5s -> **+0.4s**.
- End-to-end `schgen board --timing`: total ~254.4s vs baseline ~251.8s ->
  **+2.6s**; the pcb lap 115.75 vs 114.77. Seed-first short-circuit +
  once-per-plan inputs are the mechanism.

## The gate-caught regression (red evidence for the movable rule)

First wiring let power_som (L4-GUARDED, un-templated) move: compaction
pulled it 3.65mm toward its hop partners — power->power_som hop 63.1 ->
45.3mm (margin +17.8) and LAW-5 cross IMPROVED 13,567 -> 13,501mm... but
its L4 bottom slide re-rolled and ONE intra-zone proximity flipped 34 -> 35.
**banded_accept REJECT ("contract violations worsened on power_som") — the
no-worsen band caught exactly the class it exists for.** Fix: movables must
be POSE-PREDICTABLE (l4_exempt) — guarded sheets stay fixed rects and gain
their solver DOF at their own wave (power_som at P7, where the template
makes its geometry deterministic and the via-field keepout lands). The
rejected attempt is preserved in ledger.jsonl (banded_accept false entry)
as red-on-before for the rule.

## A1 verdict (usb_pd->power margin 10.06mm)

With today's DOF (usb_pd window-bound at its ratified seat; power
separation-bound in the E band), the hop CANNOT materially improve by pose
motion: **the binding window is power's E-band separations** (fmc /
power_mon / bringup neighbors + board wall; the compaction's weighted
median clamps at the window edge, moving power only the ~0.02mm of
quantization slack). The spec's A1 alternative applies: binding window
NAMED; the real margin unlock is the P7 waves (power_som DOF + ethernet/
motor area recovery). Margins, measured before -> after (accept run):
usb_pd->power 10.0645 -> (gate run appended below); power->power_som and
LAW-5 improvements deferred with power_som's DOF.

## Gate results (appended after the re-gate — OPUS SUCCESSOR, 2026-07-03)

The predecessor died mid-verification after a power loss; the worktree held a
STALE board where `power_som` had been moved by an EARLIER (buggy) wiring that
let a guarded sheet compact — the very regression the movable rule was added to
prevent. The code on disk already carried the fix (`movable = parts_ & inames &
set(_exempt)` with `_exempt = {pd_input, power, usb_pd}`, power_som GUARDED). A
clean rebuild REVERTED the stale artifacts to baseline.

- **movable partition (verified live):** `wired_term_participants()` -> exempt
  `{pd_input, power, usb_pd}`, guarded `{ethernet, power_som}`. After
  `& interior & exempt`, the movable set is `{power, usb_pd}` (pd_input is an
  edge block). power_som is correctly a FIXED rect. `plan.composition` log =
  `["compacted (wired hop pulls applied)", "accept: all hard terms green"]` —
  the legalizer runs the FULL L1-L5 + L4' compaction + exact-accept path.
- **build-twice byte-identical:** pcb `ea3260e7…`, manifest `415ecb7d…`,
  floorplan_composition `dc4aa02c…` — IDENTICAL across two `python3 -m schgen
  board` runs.
- **board byte-identical to the 9f77031 baseline:** the emitted
  `Zynq_Carrier.kicad_pcb` is UNCHANGED (`ea3260e7…` == the merge-unit hash).
  Every gate report (placement_flow, ratsnest, floorplan_composition,
  return_stitch, thermal, copper_debt) diffs IDENTICAL to base — the strongest
  possible banded no-worsen: not one scalar moved. Only the FLOORPLAN.md/svg
  carry the composition delta (power x 145.00 -> 144.98, the 0.02mm compaction
  pull) + the manifest lines that hash them.
- **all gates green together:** DRC 0; RATSNEST cross 13567.4/15862; PLACEMENT
  CONTRACT 0 viol; PLACEMENT FLOW 0 fails; COMPOSITION 6 hard/10 soft, hard RED
  0; **RETURN STITCH (T2 v2) 29/29 covered, worst 1.777/2.0mm, parity ok**;
  ESCAPE LANES 293/40/15; **THERMAL 20 dev, 0 over-limit**; RETURN PATH v1
  report-only FAIL by design. escape_block.json + return_stitch.txt byte-
  identical to base — T1's `{power, usb_pd}` movers do NOT collide with T2's
  locked escape nodes.
- **timing proof (A/B, one process, warm caches, median of 3):** build_plan
  BASELINE (compose forced off, L0 path) 105.15s vs WIRED (legalizer live)
  106.49s -> **+1.33s** (spec bound <= +10s). Full `schgen board` ~7:19 both
  runs, no meaningful lap regression.
- **A1 verdict (usb_pd->power):** 113.27/123.3 -> margin **10.03mm**, ABOVE the
  10.0mm driver floor, UNCHANGED from baseline. The predecessor's binding-window
  verdict holds: `power` is separation-bound in the E band (fmc/power_mon/
  bringup neighbors + board wall); the weighted-median compaction clamps it at
  the window edge, moving it only the ~0.02mm of quantization slack, which
  rounds away at emit (GRID=1.27) -> byte-identical board. The hop CANNOT
  materially improve by pose motion at today's DOF; the real unlock is the P7
  waves (power_som DOF).
- **A4 usb_pd<->pd_input:** 1.92mm gap, unchanged, within bound-GUARD (8mm).
- ruff green; targeted suites green (test_p6_legalizer + test_floorplan_compose
  + test_placement_contract_gate + test_stage_templates 62p/3s; test_build_twice
  + test_floorplan_pull + test_compose_repair 29p); full fast suite **591
  passed, 5 skipped**.
- **renders (t1_p6w_*):** whole board top/bottom, power zone top/bottom, usb_pd
  seat top (30 px/mm crop recipe), FLOORPLAN composition frame. All read clean —
  SoM centered, connectors edge-flush, the two LM61460 buck stages + FUSB302
  network + power via-fields intact, zero overlaps, zero off-board parts. The
  board matches P5's renders (byte-identical); the composition effect is the
  0.02mm floorplan-frame pull, sub-pixel at whole-board scale (itself the visual
  proof of the A1 binding-window verdict).

**P6-wire VERIFIED COMPLETE.** Board delta = 0 (byte-identical to 9f77031);
composition delta = the 0.02mm power compaction pull in the floorplan frame.
Source delta = floorplan.py only (105 insertions, spec §3 item 1). Uncommitted
per fleet protocol. Stopped here — P7 not started.
