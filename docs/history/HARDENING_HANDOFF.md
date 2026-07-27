# HARDENING WAVE HANDOFF — bottom-mirror convention unification

**Worktree:** `.claude/worktrees/hardening` @ base `9f77031` (branch state: 11 modified
files + 2 new, ALL uncommitted — do NOT stash, fleet protocol). Written for a successor
agent with NO access to the prior context. The defect is registered in
`AI_LAYOUT_ROUTING_CONCEPT.md` ("T2 COMPLETE + two engine discoveries", the D13
sections, and the new "BOTTOM-MIRROR CONVENTION UNIFIED" section appended at the end —
read those first).

## 0. The defect and the decree

The in-process pad-geometry model **X-mirrored bottom-side footprints**; EMISSION
(`embed._flip_to_bottom`) keeps local coordinates unchanged and swaps only layer
tokens, and KiCad loads a B.Cu footprint applying **only the placement rotation** —
the stored local frame IS the final front-view frame. Direction ordered: **unify every
in-process consumer to the EMISSION truth (unmirrored)**, prove red-on-before, guard
with tests, report every scalar shift loudly (LAW 4: a gate flipping red under
corrected geometry is a REAL hidden violation — never soften).

## 1. Ground truth (re-proven this wave, not assumed)

- **pcbnew 10.0.2** (KiCad.app's own Python:
  `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`,
  `import pcbnew`) loaded the emitted board: **every pad of all 564 footprints
  (2387 pads, both sides) sits at `fp_at + R_cw(rot)·(px,py)`** — worst residual
  0.7 µm (rounding). R_cw on the +y-down page: `gx = x + px·cos + py·sin,
  gy = y − px·sin + py·cos`. NO side-dependent mirror anywhere.
- Pad angle in the emitted file = fp_rot + pad_rot (embed `_rotate_pad`); pad local
  x/y are stored UNROTATED. Position math must ignore the stored pad angle.
- Two pcbnew quirks discovered (benign, documented in the parity test):
  - **F.Paste-only pads** (paste apertures of multi-piece pads: BT3001, L20001/2,
    L22003, U16001/17001/21001/2, U27001, U37002, D37001, J15001) get their number
    AND net **blanked by pcbnew on load** (copper-less pads can't carry nets). In the
    FILE they are numbered+netted. Not a defect.
  - **U17001's 4 blank EP thermal-via pads**: model `pad_nets` says `""`, emitted file
    says `GND` — `embed._thermal_via_nets` assigns the EP net at EMBED time,
    downstream of the model. Pre-existing, conservative, documented.

## 2. Red-on-before (MEASURED, pre-fix)

Method: `build_model()` in-process → `_inst_pad_geom` dump vs pcbnew dump of the
byte-identical emitted board (scripts survive at
`/private/tmp/claude-501/-Users-nicholasantoniades-Documents-GitHub-Zynq-SoM-som/7d661532-7b13-4bb9-8af6-1ea94d8323a5/scratchpad/dump_model.py`
and `dump_pcbnew.py`; artifacts `board_before.kicad_pcb`, `pcbnew_pads.json`,
`reports_before/`).

- Board population: 564 footprints — 245 top, **319 bottom** (140 C, 172 R, 5 RS
  RLM12 2-pad shunts, 2 RN 4D03WGJ0330T5E 8-pad arrays). Rotations: 314×0°, 5×90°
  (C11001–05, fmc).
- **Pad POSITION multisets agreed** (every bottom footprint bbox/pad-set is exactly
  X-symmetric — measured asymmetry 0.000000 on all 8 distinct bottom footprints), so
  packing/courtyard consumers had NO live geometric error.
- **NET-at-position was wrong on 319/319 bottom parts — all 650 bottom pads.**
  Per-pad displacement histogram (mm→pads): 0.79×8, 1.55×208, 1.65×344, 1.9×58,
  2.4×8, 2.95/2.96×24. Examples: C16003 (microsd 0805) `+3V3_SD` modeled at its GND
  pad's true spot (ΔX +1.90); RN36001 `ESC_SIG0` 2.40 mm off; worst RS37001 2.958 mm.
- TOP side: zero geometry deltas, zero net-at-position errors (the 11 apparent ones
  were the pcbnew paste-aperture quirk above).
- Entry-guard premise CONFIRMED: zero polarized/active/chiral bottom parts today.
  The 4D03 array is mirror-safe (elements 1-8/2-7/3-6/4-5 straight across, all 33Ω).

## 3. Characterization table — every consumer of bottom-pad geometry

| Consumer (pre-fix) | Convention assumed | Fed | Status |
|---|---|---|---|
| `mating_face._rot_pad_bbox` | MIRRORED (px=-px, prot=-prot) | edge-seating (placement.py ~L1089), `_inst_pad_bbox` (LAW-5 off-board, connector_spacing gate) | **UNIFIED** — `side` param removed |
| `mating_face._inst_pad_geom` | MIRRORED | `net_pad_positions` → ratsnest airwire endpoints (image + LAW-5 cross_mm), model3d docs | **UNIFIED** |
| `mating_face._inst_courtyard` | MIRRORED bbox | LAW-5 boxes, silk `occupied_bot`, placement_mech, ratsnest boxes | **UNIFIED** |
| `placement._eff_bbox_for` | MIRRORED bbox | shelf packers, `_pack_connector_zone`, L4 `_eff_box` collision/dispersion, stage_templates `_Part.local_box` + leftovers | **DELETED** (identity under truth); convention comment left at placement.py ~L219 |
| `placement_contract_gate._pad_boxes` | MIRRORED | contract gate distances, `_inst_pad_boxes` (escape, return_stitch, flow gate, floorplan_compose), stage templates | **UNIFIED** — `side` param removed, cache key `(path, rot)` |
| `escape._emitted_pad_boxes` | UNION of both | `_collect_obstacles` (via lattice), return_stitch `_check_clearance` | **DELETED** — single truth; obstacles now `pad_boxes_fn(oi)` directly |
| `return_stitch_gate._check_clearance` | UNION + bottom-GND-kept-foreign | gate verdict | **UNIFIED** — same-net GND exemption now side-symmetric (the asymmetry's only documented basis was the split) |
| `embed._pad_obstacles`, `embed._corners_rot` | UNMIRRORED (already correct, pcbnew-verified by GAP1) | thermal vias/zones | unchanged |
| `silk._declutter_refdes` | CODE already unmirrored-correct (both branches identical); docstring/comments CLAIMED `fp + R(-frot)` mirror | B.SilkS refdes placement | comments fixed; **no code change** |
| `floorplan_compose.zone_local_metrics` | via `_pad_boxes(mod, rot, side)` | T1 evaluator pad unions | signature follow-up (side dropped) |
| `stage_templates` (`_Part.pad_boxes/local_box`, `_pad_half`, `_mirror_stage`, `_turn_zone_180`) | via the two helpers | power-zone templates | signature follow-ups |

Files changed (all in worktree, uncommitted):
`schgen/generate/pcb/{mating_face,placement,embed,escape,silk,stage_templates}.py`,
`schgen/generate/floorplan_compose.py`,
`schgen/verify/{placement_contract_gate,return_stitch_gate}.py`,
`schgen/tests/{test_stage_templates,test_bottom_convention}.py` (latter NEW),
`AI_LAYOUT_ROUTING_CONCEPT.md` (resolution section appended),
`HARDENING_HANDOFF.md` (this file).
**Every consumer is unified — no code work remains. What remains is acceptance
verification (§6).**

## 4. Scalar shifts / board delta observed (post-fix, measured)

- **Board bytes:** fresh emit vs pre-fix committed board differs ONLY in the J2
  south-row escape stitch copper (y≈118, next to hdmi_rx_term bottom resistors
  R13001–8 — the F5 CONSTRAINT-flagged parts):
  - via (102.46, 118.11): 0.4/0.25 → **0.45/0.3 in place**
  - via (106.21, 118.11) → **(106.26, 118.11)**, stays 0.45/0.3
  - via (108.01, 118.46) → **(107.96, 118.51)** and 0.4/0.25 → **0.45/0.3**
    (+ its via-stub segment endpoints follow)
  - Explanation (part-by-part): the union convention doubled every bottom pad into a
    phantom X-mirrored copy ±(pad-offset×2) away; those phantoms crowded the band-3
    corner-distance windows, forcing VIA_LADDER (escape.py L72: preferred 0.45/0.3,
    fallback 0.4/0.25) down a rung and v-nudging seats. Truth-only obstacles reopen
    the windows: all three vias regain the preferred size; seats move ≤0.07 mm to the
    new lexicographic optimum. This is exactly "a placement decision made on wrong
    geometry". Everything else byte-identical (footprints untouched; total 34 vias
    before/after; file size identical 2181456).
  - New seats re-measured against real copper: nearest pad center ≥0.956 mm
    (J25002.LCD_CTP_INT), R13004 ≥1.003 mm — comfortably above rule+annulus; DRC in
    the full build is the arbiter and MUST be re-run (§6).
- **Gate flips observed so far: NONE.** Ratsnest pre-fix: cross 13567.4 mm vs budget
  15862 (slack 2295 mm; worst-case endpoint-correction shift ±1305 mm over 435 cross
  edges — unlikely to flip, but the full build decides). return_stitch worst
  contact→via was 1.7772 mm; band-3 seats moved so expect a (small) change in the
  reported per-contact distances — new value must be ≤2.0 gate bound (construct
  bound is 1.8).
- Contract-gate measured distances involving bottom parts will shift by up to one
  pad pitch (the gate measured the wrong pad before). Pre-fix reports snapshot:
  scratchpad `reports_before/` (diff after the build).

## 5. Guard tests (NEW: `schgen/tests/test_bottom_convention.py`) — state

All four PASSED on the fixed tree before the interruption (92 s run):
1. `test_model_pad_geometry_equals_emitted` — the permanent parity instrument:
   `build_model()` + `emit_pcb` + independent file parse with the pcbnew-pinned
   loader math; every pad position (≤5 µm) AND net-at-position compared, both sides;
   exemption only for model-net-`""` (thermal-via inheritance). Asserts ≥100 bottom
   pads so it can't go inert.
2. `test_bottom_parts_achiral_nonpolarized` — the polarized/chiral-bottom entry
   tripwire: passive ref classes only, no polarized footprint tokens, pad
   (position,size) multiset must equal its own X-mirror, >2-pad parts must be in
   `_MIRROR_SAFE_MULTIPAD` (currently only `4D03WGJ0330T5E`, basis included).
3. `test_red_on_before_old_mirror_convention_was_wrong` — pins the pre-fix delta:
   recomputes the OLD mirrored transform inline; asserts 100% of bottom parts
   displaced >0.5 mm and worst >2.0 mm (measured 2.96).
4. `test_helpers_side_independent_on_asymmetric_part` — fast synthetic asymmetric
   footprint: `_pad_boxes`/`_inst_pad_geom`/`_rot_pad_bbox` side-independence at all
   four rotations + absolute rot-90 spot check.

## 6. Acceptance still to run (the successor's checklist)

A fresh full-suite run was IN FLIGHT at handoff:
`nohup python3 -m pytest schgen/tests/ -q > <scratchpad>/pytest_full.log` (pid 80283,
detached, survives; scratchpad =
`/private/tmp/claude-501/-Users-nicholasantoniades-Documents-GitHub-Zynq-SoM-som/7d661532-7b13-4bb9-8af6-1ea94d8323a5/scratchpad`).
Check its tail; if dead, re-run. NOTE: another fleet agent runs pytest in
`.claude/worktrees/t1-continue` — unrelated, do not kill.

From the worktree root, in order:
1. `python3 -m pytest schgen/tests/ -q` — full fast suite green (earlier partial run:
   53 dots green before it was superseded; the 4 new guards passed individually).
2. `ruff check schgen/` — was green at handoff.
3. `python3 -m schgen board` **twice**; the two runs must be byte-identical to each
   other. vs the COMMITTED board expect EXACTLY the 3-via + 1-stub delta of §4 (and
   its knock-ons: reports/escape ledger/escape_block.json/ledger.jsonl/manifest).
   Any OTHER delta is unexplained — stop and investigate.
4. Diff `carrier/reports/` against scratchpad `reports_before/`: expect
   return_stitch.txt per-contact numbers to move slightly (all ≤2.0), escape ledger
   band-3 entries to lose the 0.4/0.25 fallback, ratsnest cross_mm to move within
   budget, placement_contract.txt distances involving bottom caps to shift ≤ pad
   pitch. ANY gate that flips red = a real hidden violation: report loudly, never
   soften (LAW 4).
5. DRC: build output must show 0 errors, warnings delta-0 vs baseline.
6. Renders of the changed region already produced and inspected (scratchpad
   `crop_before.svg.png` / `crop_fresh.svg.png`, F.Cu+B.Cu+Edge.Cuts crop of page
   (100..114, 111..123)): identical topology, three uniform 0.45 vias after, clear of
   bottom pads. Re-generate at will:
   `kicad-cli pcb export svg --mode-single --layers F.Cu,B.Cu,Edge.Cuts
   --page-size-mode 2 -o out.svg carrier/Zynq_Carrier.kicad_pcb`, crop viewBox
   `"75 86 14 12"` (page minus ORIGIN 25,25).
7. Do NOT commit (Ring-0 reviews first). No stash ever (fleet protocol).

## 7. Judgment calls made (flag to Ring-0)

- `_eff_bbox_for` DELETED rather than kept as an identity seam — an identity function
  taking `side` invites "fixing" the mirror back in; the convention note lives at its
  old site (placement.py ~L219) + `embed._flip_to_bottom` + the guard tests.
- return_stitch `_check_clearance`: bottom GND pads are now same-net-EXEMPT like top
  GND pads. Not a softening: the asymmetry's only documented basis was the mirror
  split ("their side untrusted"); the GENERATOR still treats every other part's pad
  (any net, any side) as a full obstacle, so emitted seats keep full clearance.
- escape obstacle classification: bottom parts' pads (incl. GND) stay foreign
  obstacles — symmetric with top-side treatment; only the phantom union copies were
  removed.
- The physical chirality hazard (an emitted bottom land pattern is the mirror image
  of the part's top pattern — a polarized/asymmetric part would assemble reversed) is
  NOT fixed by this unification and is now permanently guarded by test 2. If the
  project ever NEEDS an active/polarized bottom part, emission itself must learn to
  mirror (pcbnew-style coordinate rewrite in `_flip_to_bottom`) — a separate,
  deliberate wave; the guard test is the gatekeeper until then.
