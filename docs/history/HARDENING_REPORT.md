# HARDENING WAVE REPORT — bottom-mirror convention unification

**Worktree:** `.claude/worktrees/hardening` (detached @ base `9f77031`, uncommitted).
**Author:** Opus successor to the hardening thread. **Date:** 2026-07-03.
**Brief:** `HARDENING_HANDOFF.md` (predecessor's characterization + acceptance checklist).

## 1. Verdict

The bottom-mirror convention landmine (LAW-0 class) is **CLOSED and ACCEPTED**.
Every in-process consumer of bottom-pad geometry is unified to the EMISSION truth
(a footprint's local frame is side-independent; KiCad applies only the placement
rotation at load — no F->B X-mirror anywhere). The board delta is exactly the
predicted 3-via + 1-stub change and nothing else, every gate is green (the master
`gates.txt` verdict is byte-identical to pre-fix), and four permanent guard tests
pin the fix. **No gate flipped red. No softening was applied.**

The partial state left by the predecessor was found **coherent and complete** — no
code work remained; this wave was verification, one bound re-derivation against the
actual gate constant, and the report/guard confirmation.

## 2. The defect (one line)

In-process pad geometry X-mirrored bottom footprints; emission (`embed._flip_to_bottom`)
and KiCad do NOT. Every pad-level *net-at-position* measurement on bottom parts used
the wrong pad; any future polarized bottom part would emit reversed.

## 3. Characterization table — final (every consumer)

| Consumer | Pre-fix convention | Feeds | Final status |
|---|---|---|---|
| `mating_face._rot_pad_bbox` | MIRRORED (px=-px, prot=-prot) | edge-seating, `_inst_pad_bbox` (LAW-5 off-board, connector_spacing gate) | **UNIFIED** — `side` param removed; CW transform, no mirror |
| `mating_face._inst_pad_geom` | MIRRORED | `net_pad_positions` -> ratsnest airwire endpoints, model3d docs | **UNIFIED** |
| `mating_face._inst_courtyard` | MIRRORED bbox | LAW-5 boxes, silk `occupied_bot`, placement_mech, ratsnest boxes | **UNIFIED** (via `_rot_bbox_cw`, side-free) |
| `placement._eff_bbox_for` | MIRRORED bbox | shelf packers, `_pack_connector_zone`, L4 `_eff_box`, stage_templates | **DELETED** (identity under truth); convention comment at placement.py L219 |
| `placement_contract_gate._pad_boxes` | MIRRORED | contract distances, `_inst_pad_boxes` (escape, return_stitch, flow gate, floorplan_compose), stage templates | **UNIFIED** — `side` dropped, cache key `(path, rot)` |
| `escape._emitted_pad_boxes` | UNION of both conventions | `_collect_obstacles` -> lattice, return_stitch `_check_clearance` | **DELETED** — obstacles are `pad_boxes_fn(oi)` directly |
| `return_stitch_gate._check_clearance` | UNION + bottom-GND-kept-foreign | gate verdict | **UNIFIED** — same-net GND exemption now side-symmetric |
| `embed._pad_obstacles`, `embed._corners_rot` | UNMIRRORED (already correct) | thermal vias/zones | unchanged; docstrings clarified |
| `silk._declutter_refdes` | code already correct; comments LIED (claimed `fp+R(-frot)` mirror) | B.SilkS refdes placement | comments fixed; **no code change** |
| `floorplan_compose.zone_local_metrics` | via `_pad_boxes(mod,rot,side)` | T1 evaluator pad unions | signature follow-up (`side` dropped) |
| `stage_templates` (`_Part.pad_boxes/local_box`, `_pad_half`, `_mirror_stage`, `_turn_zone_180`) | via the two helpers + `_eff_bbox_for` | power-zone templates | signature follow-ups; `_eff_bbox_for` import removed |

Files changed (all uncommitted in worktree):
`schgen/generate/pcb/{mating_face,placement,embed,escape,silk,stage_templates}.py`,
`schgen/generate/floorplan_compose.py`,
`schgen/verify/{placement_contract_gate,return_stitch_gate}.py`,
`schgen/tests/{test_stage_templates,test_bottom_convention}.py` (latter NEW),
`AI_LAYOUT_ROUTING_CONCEPT.md`, `HARDENING_HANDOFF.md`, `HARDENING_REPORT.md` (this).

## 4. Verification performed (this wave)

- **Static integrity:** every changed module byte-compiles; all changed public
  symbols import; grep proves **zero dangling references** to the deleted
  `_eff_bbox_for` / `_emitted_pad_boxes` (the two remaining textual hits are the
  convention comment + a test docstring), and **zero** residual `side=`
  arguments passed to the `side`-dropped helpers.
- **Guard tests (all 4 PASS, 159 s):** parity instrument, chiral/polarized
  entry tripwire, red-on-before pin, synthetic side-independence unit
  (`schgen/tests/test_bottom_convention.py`).
- **Board byte-identity:** `python3 -m schgen board` run **twice** ->
  identical sha256 `ee6620b0…`, identical size 2181456. Determinism holds.
- **ruff check schgen/:** All checks passed.
- **Full fast suite:** `python3 -m pytest schgen/tests/ -q` —
  **595 passed, 5 skipped, 0 failed** (2005 s), including the 4 new guards.
- **DRC:** fresh build reports **0 errors**, 499 unrouted (expected pre-route),
  564/564 footprints, LINK 0/0.
- **Renders:** F.Cu+B.Cu+Edge.Cuts crop of the changed region (predecessor's
  `crop_before/fresh.svg.png`, regenerated from the current tree) inspected:
  identical topology, 5 GND stitch vias clear of every bottom pad, stitch trace
  routes cleanly through the hdmi_rx_term keepout band. RATSNEST.svg confirmed a
  pure endpoint-move (same 1771 airwires, same 2416 lines) — no hairball.

## 5. Board delta — before (committed HEAD) vs after (fresh)

The **complete** structural diff of `carrier/Zynq_Carrier.kicad_pcb` is 3 vias +
1 stub, exactly as the handoff predicted; footprints 100% untouched; via count
preserved; file size identical (2181456).

| Item | Before | After | Part-by-part cause |
|---|---|---|---|
| via @ (102.46, 118.11) | 0.4 / 0.25 | **0.45 / 0.3** | preferred VIA_LADDER size regained |
| via @ (106.21, 118.11) | pos 106.21 | **106.26** (size unchanged) | ≤0.05 mm reseat to new lexicographic optimum |
| via @ (108.01, 118.46) | 0.4 / 0.25 @ (108.01,118.46) | **0.45 / 0.3 @ (107.96, 118.51)** | size regained + ≤0.07 mm reseat |
| stub segment | (108.01,118.11)->(108.01,118.46) | **(107.96,118.11)->(107.96,118.51)** | follows its via |

**Root cause (the fix earning its keep):** the OLD union-of-conventions escape
obstacle set doubled every bottom pad into a phantom X-mirrored copy ±(pad
offset×2) away. Those phantoms crowded the band-3 corner-distance windows next to
hdmi_rx_term's bottom resistors (R13001-8), forcing VIA_LADDER down a rung
(0.45/0.3 -> 0.4/0.25 fallback) and v-nudging the seats. Truth-only obstacles
reopen the windows: all affected vias regain the **preferred** 0.45/0.3 size and
seats move to the new optimum. **This is a placement decision that had been made
on wrong (phantom) geometry, now made on the emitted truth** — a strictly better
board, not a regression.

## 6. Scalar shifts — every changed report, with bound analysis (NONE flipped red)

`carrier/reports/gates.txt` (the master verdict) is **byte-identical** pre/post.
Only 4 report files + RATSNEST.svg + the board + manifest changed; all explained.

- **return_stitch.txt / escape_block.json:** worst contact->via
  **1.7772 -> 1.7896 mm**. Gate bound `RETURN_VIA_RADIUS_MM = 2.0` (fixed,
  non-tunable, LAW-4). **1.7896 < 2.0, margin 0.21 mm — GREEN.** Per-contact
  distances moved a few tenths of a mm as the 3 band-3 vias reseated (some up:
  J2.70 1.7513->1.7896; some down: J2.71 1.6841->1.6548). Corrected geometry,
  well inside bound.
- **ratsnest.txt:** cross-subsystem airwire **13567.4 -> 13706 mm**
  (budget 15862, slack 2156 mm), **435 -> 442 edges**. This is the *substantive*
  signal of the fix: bottom-pad net-at-position was wrong on all 650 bottom pads,
  so airwire endpoints were previously drawn to the WRONG pad; corrected, the
  nearest-endpoint graph re-optimized and reclassified 7 edges across subsystem
  boundaries. Drawn airwire count is unchanged (1771). **59.6% of budget — GREEN.**
- **floorplan_composition.txt:** corridor airwire tallies shifted (e.g.
  bringup_modules 12->16, a new `fmc | som_decoupling` pair with 6 airwires).
  Same root cause — corrected bottom-pad positions change which airwires cross
  which subsystem boundary. Every corridor still satisfied; **no violation
  marker — GREEN.**
- **copper_debt.txt:** the ONLY change is a source line-number reference
  (`embed.py:419 -> :426`), a consequence of the ~7-line docstring expansion in
  `_flip_to_bottom`. Cosmetic.
- **RATSNEST.svg:** pure endpoint-coordinate moves (identical element counts) —
  the airwires now terminate on the correct bottom pads.

**No gate flipped red under corrected geometry.** The two candidate flip risks the
handoff flagged (return_stitch worst approaching 2.0; ratsnest cross approaching
15862) both stayed comfortably green (0.21 mm and 2156 mm of margin respectively).

## 7. Judgment calls (flag to Ring-0) — reviewed and endorsed

1. **`_eff_bbox_for` DELETED, not kept as an identity seam.** Endorsed — an
   identity function taking `side` invites "restoring" the mirror. The convention
   note lives at placement.py L219 + `embed._flip_to_bottom` + the guard tests.
2. **return_stitch `_check_clearance`: bottom-GND same-net exemption made
   side-symmetric.** Reviewed as sound, NOT a softening. A stitch via is GND; a
   same-net GND pad (either side) carries no clearance rule against it (same
   copper net) — a via touching it is a legal connection, not a short. The old
   asymmetry's ONLY basis was the mirror split ("bottom side untrusted"); with
   model == emission the position/net binding is trustworthy on both sides. Every
   *other* net's pad, both sides, still counts as a full obstacle — clearance
   discipline is intact.
3. **escape obstacle classification: bottom parts' pads (incl. GND) stay foreign
   obstacles**, symmetric with top-side treatment; only the phantom union copies
   were removed. The generator remains conservative; the same-net exemption is
   applied by the gate, not silently in the obstacle set.
4. **Physical chirality hazard NOT fixed here (by design).** An emitted bottom
   land pattern is the CHIRAL MIRROR of the part's top pattern — a
   polarized/asymmetric bottom part would assemble reversed. This unification does
   NOT make emission mirror; it is now **permanently guarded** by
   `test_bottom_parts_achiral_nonpolarized` (bottom parts must be passive-class,
   non-polarized, pad-multiset achiral; >2-pad parts must be on the proven
   mirror-safe list — currently only `4D03WGJ0330T5E`, with basis). If the
   project ever needs an active/polarized bottom part, emission itself must learn
   to mirror (a separate, deliberate wave) — the guard is the gatekeeper until
   then.

## 8. Guard tests — the permanent instrument

`schgen/tests/test_bottom_convention.py` (all 4 PASS):
1. `test_model_pad_geometry_equals_emitted` — parity instrument:
   `build_model()` + `emit_pcb` + independent pcbnew-pinned file parse; every pad
   position (≤5 µm) AND net-at-position compared, both sides; asserts ≥100 bottom
   pads (≥1000 total) so it can't go inert. Catches anyone reintroducing a
   side-mirror in the model OR emission.
2. `test_bottom_parts_achiral_nonpolarized` — the chirality/polarization entry
   tripwire (see §7.4).
3. `test_red_on_before_old_mirror_convention_was_wrong` — recomputes the OLD
   mirrored transform inline; asserts 100% of bottom parts displaced >0.5 mm and
   worst >2.0 mm (measured 2.96 mm). Pins the pre-fix delta.
4. `test_helpers_side_independent_on_asymmetric_part` — fast synthetic asymmetric
   footprint; `_pad_boxes`/`_inst_pad_geom`/`_rot_pad_bbox` side-independence at
   all four rotations + a rot-90 absolute spot check.

## 9. Acceptance checklist (handoff §6) — status

- [x] Full fast suite green — 595 passed, 5 skipped, 0 failed (2005 s).
- [x] `ruff check schgen/` — All checks passed.
- [x] `python3 -m schgen board` ×2 byte-identical (sha `ee6620b0…`, 2181456 B).
- [x] vs committed board: EXACTLY the 3-via + 1-stub delta of §5 + its knock-ons
      (RATSNEST.svg, 4 reports, escape_block.json, manifest). No other delta.
- [x] `carrier/reports/` diff: return_stitch/escape numbers moved ≤2.0 (1.7896),
      escape band-3 vias regained preferred size, ratsnest cross within budget,
      floorplan corridors satisfied. No gate red.
- [x] DRC: 0 errors, warnings delta-0.
- [x] Renders of the changed region inspected: identical topology, vias clear.
- [x] NOT committed (Ring-0 reviews first). No stash used (fleet protocol).
