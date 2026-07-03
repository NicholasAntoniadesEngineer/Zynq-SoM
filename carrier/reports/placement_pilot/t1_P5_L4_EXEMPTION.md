# T1 P5 — L4 per-kind exemption (evidence; first board-delta phase)

BARRIER NOTE (spec P0/P4): the task-#5 usb_pd growth render verdict was
produced by this thread at P0 (ACCEPT — see t1_P0_BASELINE.md) and awaits
Ring-0 ratification. P5 work is delivered against that recorded verdict; if
Ring-0 overturns it, P5+ artifacts are void and the exemption flip must be
re-gated on the corrected baseline.

Delivered (uncommitted):
- `placement_contract_gate.discover_all()` + `wired_term_participants()` —
  the per-KIND participant partition (D-2): WIRED flow/near_max/facing
  participants -> L4-EXEMPT; far-only participants -> FAR_L4_GUARD_MM.
  SPEC CORRECTION carried in the docstring: exempt =
  {pd_input, power, power_som, usb_pd} (live-pinned test) — the spec's
  "{pd_input, power_som}" figure predates the P2 measurement (power carries
  L4-mobile bottom leftovers, 2.3mm centroid travel measured; edge-pinned
  sheets are NOT excluded because their bottom passives are L4-mobile even
  though their poses are fixed — pd_input measured 10.8mm).
- `placement.py` LEVER-L4 loop: exempt sheets `continue` (the one-liner at
  the sorted(zorigin) loop head, lazy import).
- `floorplan_compose.emit_mobile_sheets` now returns {sheet: reasons
  ("l4"/"snap")} and consults the SAME exemption — the exactness test
  tightens AUTOMATICALLY: post-P5 pd_input/power/power_som leave the
  L4-mobile set; pd_input stays "snap" (GUARD_MM-bounded); usb_pd<->pd_input
  near_max graduates from one-sided-conservative to GUARD-bounded (A4).
- Red-on-before: the P2 residual vector (archived in t1_P2 evidence + the
  session log) shows pd_input 10.8mm / power_som 23mm / power 2.3mm
  centroid residuals under 1e-6-failing conditions BEFORE this flip; the
  same test asserts them exact/GUARD-bounded after.

## Measured at the P5 gate (appended below after the runs)

- board size + area delta vs 170x151 = 25,670 mm^2 (cumulative cap).
- LAW-5 cross delta (exemption removes some L4 shortening; slack was
  2,304.4mm = 14.53%).
- L4_PULL_CREDIT safety: needed-credit = real/proxy measured; constant may
  only move toward 1.0.
- FAR_L4_GUARD (ethernet) residual re-measure.
- Full board-scale test suite (exactness + build-twice + participants +
  driver dry-run) green.
- Render verdict (bottom-side crops: power / power_som / pd_input zones).

## Measured (P5 flip ON, in-process instrument)

- Board UNCHANGED 170x151 = 25,670 mm^2 (A' == A; cumulative cap intact —
  the exemption does not touch build_plan sizing).
- **power / power_som / usb_pd residuals -> 0.000000 (EXACT)** — the D-2
  emit-faithfulness objective delivered; pd_input is snap-only
  (centroid 0.27mm, pad-bbox 3.54mm).
- **LAW-5 cross IMPROVED: 13,557.2 -> 13,506.3 mm (slack 14.53% -> 14.85%)**
  — the SoM-ward L4 pull was net-LENGTHENING these sheets' cross airwires;
  exemption is a free win here.
- L4_PULL_CREDIT safety: needed credit = real/proxy = 0.8884 <= 0.97 —
  est_real (14,746) remains a safe UPPER bound on real (13,506); the 0.97
  constant is UNCHANGED (it may only move toward 1.0 and does not need to).
- FAR_L4_GUARD (ethernet): residual ~1.8mm (1.24, 1.30) << 14.0 — guard
  stays conservative.
- **GUARD_MM REFUTATION + GROWTH: 2.0 -> 4.0.** Measured max snap-only
  pad-bbox travel = 3.54mm (pd_input TYPE-C): the spec's EDGE_INSET+
  EDGE_PAD_CLEAR <= 1.9 derivation under-counts the connector's
  zone-internal offset that the LAW-6 seat step also absorbs. Constant may
  only grow (LAW-4-safe direction); A4's hard window at P6 becomes
  bound - GUARD = 6mm.
- Participant sets (live-pinned test): exempt = {pd_input, power,
  power_som, usb_pd}; far-guarded = {ethernet}.

## Phase gate results

- Board-scale suite (SCHGEN_BOARD_TESTS=1): **34/34 PASS** (exactness with
  the exempt sheets now 1e-6-exact + pd_input GUARD-bounded, no-snap red
  half, mutation twins, pinned participants, in-process build-twice, driver
  dry-run intent-gating).
- Double `schgen board`: both builds byte-identical (pcb c01695f6..., all
  reports identical across builds) — cross-process determinism at the P5
  board. All gates PASS, DRC 0. FLOORPLAN.svg UNCHANGED (57533a49... — the
  poses are identical; only emitted part positions moved).
- Ledger (P5-l4-exemption entry): area 25,670 (A' == A, cap intact); LAW-5
  slack 14.85% (improved); contract counts no-worsen — power_som IMPROVED
  34 -> 32 (its bottom parts back at the zone tightened intra distances).
- Emitted flow-gate deltas (HONEST re-measure — the pre-P5 figures were
  seen through L4-distorted centroids):
  - usb_pd->power 110.37 -> 113.27 (margin 12.97 -> 10.06mm; 0.06 above the
    10.0 driver floor — the P6 legalizer's PRIMARY improvement target, A1).
  - pd_input->usb_pd 4.01 -> 15.07; power->power_som 60.40 -> 47.77
    (improved); facing 7.0 -> 16.9 deg (margin 73.1 >= 15 floor).
  - **A4 seat regression, explicitly reported: near_max usb_pd<->pd_input
    gap 0.00 -> 1.92mm** (pd_input's bottom caps no longer intrude south
    under L4; the TOP-side PHY seat is visually unchanged — see
    t1_p5_usbpd_seat_top.png). 1.92 <= bound-GUARD = 6mm hard window.
- RENDER VERDICT (T1 loop): **PASS** — t1_p5_board_{top,bottom}.png +
  t1_p5_power_zone_bottom.png + t1_p5_powersom_bot_bottom.png: all three
  exempted sheets' bottom passives sit INSIDE their floorplan zones
  (pd_input R17xxx/C17xxx at the N-edge zone; power R20xxx straps in the
  power zone S band; power_som C22xxx exactly filling its (106,107) 12x16
  box), bottom side orderly, no off-board, DRC 0, dispersion max unchanged
  (som_decoupling 8.85 — A6 intact).

## Blast radius (positional diff, P0 board -> P5 board)

52 of 564 footprints moved, 6 sheets: power_som 18 (max 30.0mm — back into
its zone), pd_input 6 (max 24.0), power 5 (max 30.0) = the exempted set;
second-order L4 re-slides from the changed bottom occupancy: user_io 9
(max 9.0), uart_bridge 7 (max 8.0), usbc_otg 7 (max 2.0). **hdmi_rx did NOT
move** — the T2 escape-thread coupling obligation (re-run after any wave
that re-places hdmi_rx) does not fire at P5.

## P5b — 28f8e15 rebase reconciliation (exemption partition refined)

Rebase state: my stash applied CLEAN onto 28f8e15 (zero textual conflicts;
__main__ carries both my composition block and main's copper_debt chain;
emit.py carries both the GAP1 zone/via emission and my compose_report).
Board-scale suite on the rebased tree: 34/34 PASS. But the double build
FAILED deterministically (identical hashes both builds):

**REBASE COLLISION FINDING (cross-thread, flagged for Ring-0): THERMAL FAIL
— my P5 exemption vs main's GAP1 copper.** Exempting power_som parked its
un-templated bottom caps back inside U22004's DATASHEET thermal-via field
(SNVSBD5D 11.1.1): the via placer's obstacle filter dropped 6 of 8 sites
(2/6 min vias), the pour credit was denied, and ALL bucks fell back to the
bare 58.7 C/W (power:U1 Tj 192.1, power_som:U4 153.8 — board-dead red).
Pre-P5, LEVER-L4 was ACCIDENTALLY clearing that space. Latent truth: any
emit-faithful placement collides with the via fields until the zone packer
reserves the pour rect on the bottom side — spec that keepout INTO the P7
power_som wave (the buck template's same_side override also empties the
bottom there, which is the durable fix).

Partition refinement (P5b, red-proven by the failing rebase build):
- l4_exempt = near_max participants + the templated WIRED sheets
  = {pd_input, power, usb_pd} (power measured via-field-safe: 8/8 vias).
- l4_guarded = {ethernet: 14.0, power_som: 25.0 (measured max travel 23.7mm
  + margin)} — evaluator tightens flow budgets by the guards and ABSTAINS on
  facing terms with a guarded participant (the HARD gate remains the sole
  arbiter, D-5); each sheet graduates to exempt at its own wave.
- Participants test re-pinned; every guarded sheet must carry a measured
  guard (asserted).

Gate results appended below (build-scale suite + double build + scalars).

## P5b gate results (rebased tree, exemption partition refined)

- Board-scale suite 34/34 PASS; fast T1+main sweep 105 PASS; ruff green.
- Double `schgen board`: **BOARD PASS, THERMAL PASS (0 over-limit — the
  U22004 via field restored by power_som's L4)**; byte-identical builds
  (pcb c7e8fdcf... both). DRC 0.
- Scalars (ledger P5b-rebased@28f8e15): area 25,670 (cap intact); LAW-5
  slack 14.46%; usb_pd->power 113.27/123.3 (margin 10.06 — the P6 target);
  seat gap 1.92mm; contract register now includes the 9 lightweight-tier
  contracts' red-on-before counts (camera 2, hdmi_tx 7, lcd 7, microsd 10,
  pd_input 6, pmod 4, uart_bridge 12, usb_jtag 16, usbc_otg 4) alongside the
  unchanged originals (ethernet 23, hdmi_rx 3, motor_sense 11, power_som 34,
  power 0, usb_pd 0).
