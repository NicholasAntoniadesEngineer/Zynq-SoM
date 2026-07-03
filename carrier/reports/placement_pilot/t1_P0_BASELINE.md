# T1 P0 — committed baseline (measured live @ 198636b, 2026-07-02)

Instrument: one in-process `build_model()` + the real gates + discover-injected
contracts; ledger entry appended to `carrier/reports/ledger.jsonl` (GAP4 —
created this phase, the file did not exist). Full `schgen board` re-run PASS
(391.8s, DRC 0 errors) and **byte-identical** to the committed tree on
`{Zynq_Carrier.kicad_pcb, FLOORPLAN.svg, FLOORPLAN.md, manifest.json}`
(hashes in `t1_p0_hashes_pre.txt` scratch; pcb = 9a375217...). Only the
raytraced 3d_*.png renders churned (known PNG byte-noise, manifest-excluded).

## Scalar table (re-measured; spec §1 corrections flagged)

| Scalar | Live value | vs spec §1 |
|---|---|---|
| Board | 170 x 151 = 25,670 mm² | = |
| flow_budget | 123.33 mm | = |
| usb_pd→power (tightest wired hop) | 110.37 / 123.33 (12.9 mm margin) | = (double-declared, honest) |
| power→power_som | 60.40 / 123.33 | = |
| pd_input→usb_pd | 4.01 mm | = |
| power_mon→power_som (unwired) | 47.19 / 123.33 | new datum |
| near_max usb_pd↔pd_input | 0.00 mm / ≤10 | = |
| near_max ethernet↔rj45 (unwired) | 0.00 mm gap / ≤20 (zone-bbox metric GREEN; F1 is part-level + corridor squatters) | new datum |
| **near_max motor_sense↔motor_pwm** | **68.65 mm gap > 20 — RED** (regenerated; threshold-relative only) | = (matches session figure) |
| far power↔ethernet.line_side | 80.94 / ≥10 | = |
| facing power→power_som | 7.0° | = |
| facing power_som→@som (unwired) | 9.9° GREEN | new datum |
| LAW-5 cross | 13,557.2 / 15,861.6 → slack 2,304.4 mm = 14.53% | = (0.4mm rounding) |
| som_decoupling dispersion | 8.85 / 9.0 | = |
| **Contract reds (check_all, unwired)** | **ethernet 23 / hdmi_rx 3 / motor_sense 11 / power_som 34** (power 0, usb_pd 0) | **SPEC §1 FIGURES (9/3/5) STALE — A7 baseline is THESE counts** |
| DRC | 0 errors | = |

## D13 channel demand (per-zone-pair cross-airwire counts, MST)

Top non-SoM pairs: bringup_en_modules|bringup_rails 24, bringup_en_modules|
bringup_modules 12, pd_input|usb_pd 8, ethernet|rj45_connector 8,
motor_sense|power_mon 7. (Full table in ledger.jsonl `cross_pairs_top20`.)
These are the demand inputs for the P6 legalizer CHANNEL terms (Ring-0 D13
injection): corridor ≥ 2.0mm (judgment:2.0, D13 floor "2x 0.1/0.1mm lanes +
1.0mm clearance" ≈ 1.4mm, rounded up to one lane-pair of margin) + demand
scaling, folded in as HARD difference-constraint terms at P6.

## GAP4 cumulative AREA CAP (proposed, binding for T1 acceptance)

- **HARD cumulative cap: area ≤ 25,670 mm² at EVERY T1-accepted commit.**
  Basis: the T1-entry area (this baseline). GAP4's defect is sqrt(area)
  budgets self-legitimizing growth; pinning the cumulative cap at entry means
  per-wave "~+5%" judgments can never compound past the baseline — a wave may
  spend area only after an earlier phase recovered it (F6 mandate).
- **Recovery target: area ≤ 24,600 mm² by end of P9** (spec AREA_TARGET_MM2:
  pre-contract 154x152 = 23,408 mm² + the recorded ~+5% wave-growth
  allowance). Missing the target fires the P10 `_rotate_zone_90` trigger.
- Repair steps: `A' ≤ A` always (spec §5 law 3, unchanged).

## Task #5 — usb_pd +4.1% growth RENDER VERDICT (T1 render loop; Ring-0 to ratify)

Evidence: `t1_p0_board_top.png`, `t1_p0_board_bottom.png`,
`t1_p0_usbpd_seat_top.png` (30 px/mm crop).

- The usb_pd seat is CORRECT: FUSB302 + all 6 contract parts one tight
  template cluster directly inboard of the pd_input eFuse/TVS block, zones
  abutting (near_max 0.00mm), CC path receptacle→PHY short. No crowding, no
  silk collision at the seat; silk ≥0.8mm everywhere (DFM floor landed).
- The growth cost (170x145 → 170x151) shows as INTERIOR whitespace (F6):
  visible voids left-center (SWD/JTAG band), S of the SoM, and the E band
  above power. Nothing about the growth is wrong per se — it is un-recovered
  slack, and area recovery is exactly this thread's A3/F6 mandate.
- **VERDICT: ACCEPT the usb_pd wave baseline** (composition-correct, growth
  = recoverable slack owned by T1). P5+ may stack on it once Ring-0 ratifies.

## Findings register spot-check (render, 30 px/mm)

- **F1/F7 CONFIRMED** (`t1_p0_eth_rj45_top.png`): motor_pwm's U21001/U21002
  QFNs sit INSIDE the T10001-magnetics → ETH-jack line-side corridor; the
  ethernet↔rj45 zone-bbox gap is 0.00mm yet the corridor is squatted —
  zone-level near_max cannot see it; the ethernet wave + D9 move are ONE
  composition move (F7) and the corridor needs the region/channel treatment.
- **F3 CONFIRMED**: motor_sense zone (E, 48.9x33.1) vs motor_pwm (W edge) —
  68.65mm gap; sense cluster far from both connectors' partner.
- Bottom side orderly: som_decoupling grid + L4 sub-clusters, no off-board.

## Sequencing gates

- Worktree tracked-file state clean at 198636b (untracked iCloud " 2" conflict
  copies at repo root — inert, left untouched).
- Task #5: verdict above — Ring-0 ratification is the P5 BARRIER.
- No commits from this thread (Ring-0 merge review owns landing).
