# Bottom-side placement — wave-9 design

## The right abstraction

NOT two floorplans. One floorplan where SIDE is a per-block degree of freedom:

- The two surfaces share one outline, one edge-connector perimeter, one SoM region,
  and every PUNCH-THROUGH: THT pads block the far side locally, escape/stitch vias
  need both-side landing room, corridors are per-side bands, mounting holes pierce.
  Two independent floorplans are each blind to the other's penetrations; one
  allocator with a top layer + bottom layer + shared punch layer models the truth.
- The ATOM of side assignment is the BLOCK, never the part: contract structures
  (hot loops, terminations) are same-side by datasheet; a zone's existing internal
  top/bot split (`top_off`/`bot_off`) stays intra-block.

## Why the engine is closer than it looks

- Gates are already side-aware: D13 crowding skips opposite-side neighbors; DRC is
  per-layer; corridor eviction is already B.Cu-aware; the SoM bottom face is already
  populated (som_decoupling). The gap is ONLY the block allocator: today a block's
  rectangle claims both surfaces implicitly.
- Wave-4 multi-shape is the natural carrier: a bottom placement is just MORE SHAPE
  VARIANTS — the mirrored (X-flipped) re-pack of the same zone, tagged side=bottom.
  The greedy deterministic chooser, chosen-shape plumbing, estimator-judges-chosen-
  geometry, and P6 legalizer machinery all extend rather than fork.

## Plan

- P1 INFRASTRUCTURE (byte-identity-safe landing): `_Occupancy` becomes two layers +
  punch layer; `Block.side`; `place_near` searches (x, y, side) over each block's
  variant set; bottom variants = mirrored `_pack_one_zone` re-packs; estimator adds
  a per-crossing VIA COST term for nets spanning sides; emission flips sides.
  Eligibility defaults to top-only — with zero blocks opted in, the board must be
  byte-identical (the control that lands the machinery inert).
- P2 ELIGIBILITY (data, not code): floorplan.json per-block `"side": "top" |
  "bottom" | "either"`. Hard rules derived, not asserted: connectors/switches/LEDs/
  displays are user-facing = top; height-capped by the enclosure standoff budget
  (USER DATA NEEDED); second-reflow mass rule (heavy parts top) as a new DFM gate —
  an extension, no existing gate softened. First candidates: faceless blocks —
  hdmi_rx_term, board_services, uart_bridge-class networks, bulk/termination groups.
  Each opt-in lands as a measured A/B (area, airwire, via count).
- P3 HARVEST: the sizing search re-derives the outline as interior demand drops
  toward max(top, bottom) instead of their sum. Edge runs (99mm of 183 today) do
  not bind, so the interior win is real board shrink.

## User decisions (RESOLVED 2026-07-29)

1. Bottom-side height: NO LIMIT.
2. Bottom-eligible: everything EXCEPT connectors, probes/testpoints, LEDs,
   switches (ethernet family, power supply, etc. all eligible). Policy: blocks
   with seated connectors stay top-pinned; TP/LED/SW PARTS carry a face=top
   constraint the zone packer honors inside a bottom-assigned block's variant
   (the internal two-side split flips roles, so a bottom block can still
   present its user-facing parts on the board-top face).
3. Double-sided assembly already paid for — cost accepted.
4. Battery holder (ML1220 coin cell) explicitly bottom-eligible (user 2026-07-29)
   — service access on standoffs, not user-facing.

Sequencing: P1 starts after the wave-8 engine unit lands (same files).

## P2 measured (2026-07-30)

- Side choice is EST-DRIVEN inside the pack search (`_pick_sided`): when a
  block's fitting variants span both faces, the per-face finalists are judged
  by the sizing estimator restricted to that sheet's nets (cross-airwire +
  registered `est_via_cost`) on the partial board — strict 1e-6 win or the
  distance incumbent stays; distance still judges within a face. Zero opt-ins
  means the judge cannot fire (byte-identity control held on both projects).
- Achiral-safe opt-in frontier (unified convention — no chiral IC emission
  yet): hdmi_rx_term + user_io only; 16 interior blocks excluded (ICs, diodes,
  unproven multi-pad inductors or magnetics on the would-be-B.Cu primary;
  conn-class jumpers; MH-only mechanical). Both measured NEUTRAL at 185x166:
  hdmi_rx_term's bottom variant est +48..+65 mm (via cost, no cross win —
  63/63 judgements keep top, including the P1 distance tie at 0.403);
  user_io's variant is vacuous (all 8 parts face-top, primary empty) and the
  judge RESCUED it from 36 distance-preferred bottom placements (up to
  +245 mm worse cross). Boards byte-identical, so the opt-ins are reported,
  not landed (user acceptance rule: measured wins only).
- P3 outline harvest therefore waits on the chirality debt (embed-level local
  mirror + kernel updates for IC-bearing blocks) before interior demand can
  approach max(top, bottom) instead of the sum.

## Chirality PAID (wave-9, 2026-07-30)

- KiCad-EXACT mirrored emission is live: `schgen/generate/pcb/mirror.py`
  materialises each footprint's pcbnew-LEFT_RIGHT-flip twin (stored local
  y -> -y, local angles -> -a; instance rotation t -> (180 - t) % 360; layers
  still flipped by `embed._flip_to_bottom`; `(model ...)` untouched) as a
  real .kicad_mod under `.mirrored_fp/` (gitignored derived cache, outside
  parts/ so the model3d census never sees it). A mirrored instance is an
  instance WHOSE mod_path IS the mirrored document, so every geometry kernel
  (`_pad_boxes`/`_rot_pad_bbox`/`_footprint_bbox`/`_inst_pad_geom`/
  `_mod_pads`/escape/silk/D13/contract/ratsnest) stays side-blind with zero
  mirror branches.
- GROUND TRUTH pinned against pcbnew 10.0.2 itself: a 32-footprint fixture
  (SOT-23-5, QFN24 with rot-90 oval pads, FUSB302 MLP, HX5008 TH magnetics;
  rots 0/37/90/270, both sides) emitted by `embed._embed_footprint` matched
  KiCad's own `FOOTPRINT::Flip` objects pad-for-pad at 0.0 nm (584 pads:
  position, orientation, layer set, shape, size, drill), side-blind loader
  formula residual 0.5 nm, `kicad-cli pcb drc` 0 violations. Placed-pattern
  identity: `R_cw(180 - t) . M_y == M_x . R_cw(t)`.
- Bottom shape variants now carry the TRUE mirror (`_mirror_pack`): primary
  pack = mirrored documents at origin (zw - ox, oy), rotation
  (180 - t) % 360 (`ZoneShape.mirror`); secondary pack (face-top parts,
  presents F.Cu) keeps plain top emission with box-preserving mirrored
  origins. `apply_chosen_shapes` rebinds resolvable/bbox_of to the mirrored
  documents (`ZoneGeom.mirror_refs` -> `FootprintInst.mirror`); the
  estimator, D13 shape reach, occupancy comps, zone metrics and the contract
  re-measure all judge the mirrored geometry. The achiral-swap convention
  remains ONLY for the 2-side classifier population (pushed passives +
  som_decoupling, byte-pinned boards) and its entry guard now scopes to
  inst.mirror=False; mirrored parts of ANY footprint class are legal on
  B.Cu (face-top TP/LED/SW still forced to present top; seated-connector /
  conn-class / no-zone hard raises unchanged).

## Wave-10 — D13 frontier root-caused; class-aware via cost; bringup_rails LANDED (185x163, -555 mm2)

- U1 ROOT CAUSE (fixed): the top-vs-top D13 red that blocked `bringup_rails`
  was never a bottom-side effect and never a frontier/compaction effect —
  BREATHE carried a PRIVATE replica of the fan-out gate's foreign-neighbour
  rule that omitted the TEST-POINT exemption. A TP pad therefore read as a
  crowder, which faked starvation, aimed the away-from-crowder march at a part
  the gate does not count, and neutered the mover's own no-regression floor
  `min(need, current clearance)`. Measured: U5001 (bringup_en_modules, 5 pin,
  TOP) read its clearance as 0.500 to TP5002, marched away from it, and
  collapsed its REAL 2.640 gap to C15002 (lcd, TOP) to 1.380 against a 1.50
  need. Both sides now call ONE predicate, `fanout_gate.counts_as_crowder`; no
  gate softened, no padding added.
- VIA COST IS NET-CLASS AWARE (user decree 2026-07-30). The charged set is
  DERIVED, never listed: a net pays the impedance row iff its routing class
  carries a `DiffGeometry` (DP90_USB / DP100_TMDS / DP<imp>_DIFF today, any
  future impedance class for free). Impedance = 7.6 mm (2 legs x 2 layers of
  barrel+annulus + 2 legs of 1.6 mm stackup stub); ordinary = 2.2 mm, 3.45x
  cheaper. The decree's 0.0 endpoint was measured and REFUTED — see the sweep.
- ORDINARY-ROW SWEEP (bringup_rails opt-in, emitted boards, all PASS):
  0.0 -> 188x164 / 30832 mm2 / cross 15558.8; 0.1, 1.0, 2.2 and 3.0 -> the
  IDENTICAL 185x163 / 30155 mm2 / cross 15319.0 (same md5). The response is a
  STEP at 0+, not a curve, so 2.2 is chosen as the physically-derived member of
  the measured plateau rather than a fitted constant. The step is the
  unmodelled emission-time disruption a side flip still costs; per
  `BOTTOM_SIDE_MODEL_DEFECTS.md` that is largely the PUNCH-MODEL defect (edge
  blocks + the SoM keepout reserve BOTH surfaces, falsely denying 41.7 % of the
  bottom face), so the ordinary row is INTERIM and should fall toward its
  physical value once that is fixed.
- LANDED: `bringup_rails` `"layer": "either"` — the est flips U7001 (24-pin,
  now B.Cu) and its rail cluster to the bottom while the switches/TPs still
  present on F.Cu. Carrier 185x166 -> **185x163, 30710 -> 30155 mm2 (-555,
  -1.81 %)**, cross-airwire 15193.0 -> 15319.0 (within the re-derived 17191.5
  budget), 34 vias, 28 gates green, D13 110 subjects 0 starved, and the
  hairline survivors are gone: U5001 -0.120 (STARVED) -> +0.400, SW7002 +0.005
  -> +0.050, U7001 +0.008 -> +0.215. `legalize_only_compaction` ratchets 16 ->
  14.
## Wave-11 — the PUNCH MODEL is fixed (8,155.8 mm² of bottom released) and a MONOTONICITY GUARD makes the freedom free

- P1 — PUNCH ONLY WHAT PIERCES. An edge block's main rect now carries its OWN
  copper face (`OCC_TOP`) and the geometry that genuinely pierces rides as
  PUNCH components. Two fixes, not one: applying the existing
  `_zone_components` path to edge blocks would have released 5,839.6 mm²,
  because that path punched each THT part's whole FOOTPRINT BBOX. The truth is
  the PAD copper — 382.9 mm² union vs 2,699.0 mm² of bbox, so the interior-zone
  punch model was itself ~7x too conservative and is now exact
  (`mating_face.thru_pad_boxes`, one kernel shared with `_rot_pad_bbox`). Each
  punch box is swept OUT to the board edge along the block's edge normal
  because the LAW-6 edge seat slides a connector outward at emission (measured
  1.500 mm on every contracted conn sheet, 1.960 on `rj45_connector`).
  MEASURED: 15 edge blocks 8,548.0 -> 392.2 mm², **8,155.8 mm² released =
  27.0 % of the 30,155 mm² surface**.
- P2 — SoM: OCC_TOP ONLY. The module rect is the TOP keepout; the underside
  carries the REAL content — the 18 `som_decoupling` cells (from the emission
  oracle `placement.som_decoupling_cells`, one function for both the reservation
  and the placement) on `OCC_BOTTOM`, plus the three DF40 escape/return-stitch
  seat bands as PUNCH. The DF40s are SMD (top face only). MEASURED: of the
  2,385 mm² rect, 1,936.1 mm² is genuinely occupied, so 448.9 mm² is released
  inside it; the bands also reserve 291.6 mm² OUTSIDE it that interior bottom
  blocks previously ignored, so P2 is a net +157.3 mm² and, more usefully, a
  SHAPE change: the SoM underside is reachable and the corridor is reserved up
  front instead of relying on `corridor_eviction` (`corridor_evict_moved` stays
  0 on the carrier). The 6 mm `_SEAT_BAND` rects provably contain
  `escape.corridor_board_rect` (true corridor union 217.9 mm²; R_CONSTRUCT 1.8
  and CORRIDOR_V_MARGIN 0.15 both well inside 6.0).
- THE FINDING: **the greedy search is NOT monotone in free area.** P1+P2 alone
  emitted the same 185x163 board with cross-airwire 15,319 -> 16,536.1
  (+1,217) — freeing the bottom moved the two already-bottom blocks, which
  moved the `centers` map every later anchor reads, and two top blocks switched
  shapes. A degree of freedom that can make the result worse is noise. So
  `build_plan` now runs the outline search under BOTH reservation policies —
  the wave-11 truth and the CONSERVATIVE SUPERSET (whole rects on both faces,
  i.e. master's model) — and keeps the strictly better plan on
  `(area, est_cross)`, ties to the conservative incumbent. Both are legal (a
  superset reservation can only forbid placements), so this is a measurement,
  not a degrade; the rejection is the registered, ratcheted fallback
  `punch_free_plan_rejected`. Exactly two `_search(pad_punch)` calls per
  `build_plan`, each a pure function of the flag over the same fixed grids; the
  rejected search is rolled back (`_plan_restore` + `fallbacks.restore`) and
  `_reset_shapes` re-arms the pre-search shape state so `_choose_conn_shapes`
  can never restore the other search's mirror as its incumbent.
- MEASURED, both projects: carrier **185x163 / 30,155 mm² / cross 15,319.0, md5
  `8c093a49db4c7fc71edb1acc91ce756a` — the pin, byte-for-byte**, 28 gates
  green; devkit **123x100, md5 `37bd122b3463b00e4b2d95d1e788b18b` — the pin**.
  The whole wave is byte-inert because on every rung measured the freed surface
  did not pay.
- LADDER (9 rungs + the combination, ordinary via 2.2): `board_services`,
  `bringup_en_modules`, `bringup_modules`, `hdmi_rx_term`, `usb_pd` and
  `user_io` are byte-identical to the pin; `bringup_en` is +0.9 mm cross;
  `power_mon` and the 8-block combination emit 185x163 with cross 16,536.1
  (+1,217). `ethernet` is still NOT MEASURABLE. Nothing lands.
- THE EST/EMISSION GAP SURVIVES — wave-10's hypothesis is REFUTED. `power_mon`
  is the clean case: the guard's judge IS the sizing estimator, it preferred the
  freed plan, and the emitted cross came out +1,217 mm worse. The gap is
  therefore downstream of the lattice (the post-floorplan movers `l4_pull` /
  `breathe` / `refit_facing` / `reorder` and pad-level geometry the block proxy
  cannot see), not the punch model. That is the next lever.
  **[WAVE-12: REFUTED — see the wave-12 section. The guard preferred the freed
  plan on AREA (30,155 vs 30,340), not on the estimator, which correctly priced
  the freed plan +1,092 mm worse. No mover destroys the win; the movers are a
  net −77 to −172 mm.]**
- ORDINARY-VIA ROW: the wave-10 STEP at 0+ is GONE — 0.0 and 2.2 now emit the
  IDENTICAL best board (md5 `8c093a49…`). The whole swept range is one plateau,
  so there is no measured reason to move the constant: **2.2 STAYS** as its
  physically-derived member. Its registered basis is re-based on this
  measurement; it remains INTERIM for the est/emission gap alone
  **[WAVE-12: re-based again — INTERIM because it is unmeasurable by area while
  the search is pack-bound]**. (0.0 with the
  wave-10 re-test set `power_mon`+`usb_pd`+`bringup_en` emits 185x163 with cross
  16,526.7 — still negative.)

- LADDER, everything else (one at a time + the full combination): under the
  0.0-ordinary model the est took bottom for `power_mon`, `usb_pd` and
  `bringup_en` and every one of those emitted boards was WORSE on both axes
  (185x175 / 185x169 / 185x166, cross +714 / +543 / +115); the 5 blocks the est
  keeps top were byte-identical to the control; the 9-block combination was
  185x179 with 7 DRC errors. `hdmi_rx_term` is the impedance row working as
  intended — 8 high-speed nets, est +140 for bottom, keeps top. `ethernet` is
  NOT MEASURABLE: its declaration makes the sizing search run >56 min at 98 %
  CPU (heapq-dominated, no board emitted) vs 3.2 min. None of these land; they
  are re-runnable once the punch model is fixed.

## Wave-12 — the est/emission gap REFUTED; the board proven PACK-bound in both axes

The wave-10/11 hypothesis (the sizing estimate misleads the search, so bottom
opt-ins price well and emit badly) was measured at every stage boundary and is
**wrong**. Instruments: `scripts/w12_stageprobe.py` (LAW-5 ratsnest kernel at
every `StageTracker` boundary — its FINAL row reads the pinned 15,319.0),
`w12_bound.py` (every outline candidate: packed? est? budget?),
`w12_chain.py` (every `_attempt_pack` call classified by rejecter),
`w12_order.py` (all edge-run orderings), `w12_why.py` (line-traced rejection
site), `w12_shapes.py` (registered shape sets), `w12_patchrun.py`
(byte-exact source-patch experiment runner).

- **The estimator is honest.** It is a near-constant upper bound over the
  emitted cross: +315.0 / +315.0 / +321.7 / +314.9 mm (2.06 % ± 0.03 %) on four
  conservative plans, +199.9 on the freed plan; ranking agreement 4/4.
- **No mover destroys a win.** Per stage, `l4_pull` + `edge_seat` + `breathe` +
  `refit_facing` + `reorder` NET −171.9 / −170.9 / −171.5 / −76.6 mm. Only
  `reorder` (±10 mm) accepts on a different objective (crossing count) than the
  one being optimised; `edge_seat` is already replicated inside the estimator.
- **Wave-11's "+1,217 mm at unchanged area" was a comparison-frame artefact.**
  With `power_mon` eligible: conservative = 185x164 / est 15,643.8 / emitted
  15,328.9; freed = 185x163 / est 16,736.0 / emitted 16,536.1. The guard's key
  is `(area, est_cross)`, area strictly first — it bought 185 mm² for +1,207 mm
  exactly as declared, and the estimator predicted that cost correctly.
- **Airwire has never sized this board.** 2,868 candidate outlines tried, 14
  packed, LAW-5 budget rejected 0.
- **W = 185 is a proven geometric floor** (S-edge connector run: 184.669 mm
  needed, 184.269 under the best of all 24 orderings, next grid point 184).
  2,186 sub-185 candidates, 100 % rejected by the edge-run fit guard, none
  reaching the interior packer. No edge block has a narrower variant; a side
  flip cannot compress a perimeter run.
- **H = 163 is set by `power`** — largest interior block, placed LAST because
  the order key is `(priority, −connectivity, −area, name)`. It is provably
  top-pinned (user-facing LEDs + test points).
- **The bottom-eligibility ladder is EXHAUSTED.** `power`, `usb_jtag`,
  `power_som`, `uart_bridge` refuse on face-up parts; `fmc`, `debug_boot` on
  seated connectors; `mechanical` has no packable zone. Every refusal is LOUD.
- **The one lever that moves the board (measured, NOT landed):** area-first
  interior pack order emits **185x160 = 29,600 mm² (−1.84 %)** at cross
  16,699.2 (+9.0 %), LAW-5 utilisation 89.1 % → 98.0 %, sizing estimate at
  99.94 % of its own budget. An area-vs-airwire trade at the wall — the user's
  call. Clean landing form if wanted: a registered `pack_order_retry` fallback
  (retry area-first only when the connectivity order fails to pack), byte-inert
  wherever the primary order succeeds.
- ORDINARY-VIA ROW: still 2.2, still INTERIM, but for a RE-BASED reason — it is
  **unmeasurable by area** while the search is pack-bound. No via cost can move
  a board whose size no airwire term constrains.
