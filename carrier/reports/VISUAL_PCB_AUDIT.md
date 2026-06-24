Both load-bearing claims confirmed: visual_gate.py has no junction parameter (only a docstring trusting the router), and connector_model_gate.py:261 uses `% 180` (accepts 180). Now producing the report.

# Zynq-7000 SoM Carrier — Prioritized Master Audit Report

## Executive Summary

**The design is NOT tape-out clean.** Two infrastructure-level problems dominate: (1) the *generation pipeline's own LAW-0/LAW-6 gates have structural blind spots* — the visual gate never even receives junction dots, and the mating-face oracle uses the opposite rotation handedness from the physical pad transform — so "all gates green" does not currently prove electrical or mechanical correctness; and (2) the board is still **fully unrouted** (499 airwires) with multiple render-visible symbol/wire/text overlaps. The single most alarming finding is the **CCW/CW handedness split**, which is *proven to have shipped a physically wrong LCD connector* (mouth facing inboard) that the gate passes. The good news: KiCad DRC reports **zero copper/clearance/hole/short errors** and ERC reports **zero genuine electrical-defect violations** — the remaining electrical risk is concentrated in the *un-proven gate invariants*, not in any confirmed live short.

---

## Must-fix (CRITICAL / HIGH)

> Fix all of these in the **generator**, never by hand-editing the emitted `.kicad_pcb` / `.kicad_sch`.

### 1. [CRITICAL] Mating-face oracle and physical pad transform disagree at 90°/270° — ships connectors facing inboard
- **Artifact / location:** `schgen/generate/pcb.py:494-507` (`_mating_face_out_dir`, CCW matrix) vs `:566-583` / `:1656-1684` (`_rot_pad_bbox` / `_inst_pad_geom`, CW matrix); rotation tables `:476-491`; gate at `schgen/verify/placement_mech.py:147-150`.
- **Defect:** The mouth-direction oracle uses a math-CCW matrix; the emitted footprint pads/courtyard use the CW ("TRUE KiCad") matrix. For a ±Y-face connector on the E/W edge, the emitted rotation (90/270) makes the physical mouth point **inboard**. **Proven on the shipped board:** LCD `J15001` (AFC07-S40FCA-00) emitted at rot 270 on the W edge — its FPC contact row lands at x=29.94 while the W edge is at x=25.0, so the cable slot opens *toward +X (inboard)*. The gate passes because its check uses the CCW oracle. Same class hits camera (SFW15R/W), `rj45_connector` (KH-5224/E), `board_qwiic` (E).
- **LAW:** LAW 6 (mating face must point off-board) + LAW 4 (gate oracle is unsound, not strict).
- **Fix:** Unify on **one** transform. Make `_mating_face_out_dir` (and `placement_mech.py`'s mouth check) use the *same* CW matrix that `_inst_pad_geom`/`_rot_pad_bbox` use to emit geometry, then regenerate the rotation tables `_ROT_FACE_*` against that corrected oracle. Add a gate assertion that derives the mouth direction *from the emitted pad geometry* (not from a table) so oracle and physical part can never diverge again.

### 2. [CRITICAL] Visual gate never receives junction dots — its headline LAW-0 short class is structurally invisible
- **Artifact / location:** `schgen/verify/visual_gate.py` (no junction primitive — **confirmed**); fed by `schgen/layout/place.py:4954,4980-4981` which builds `SheetGeometry(boxes=…, wires=routed.segs)` and omits `routed.junctions`.
- **Defect:** `route.py` computes junctions and emits them to the `.kicad_sch`, but they are never placed into the `SheetGeometry` the gate inspects. A junction dot dropped at a crossing of two *different* nets — the exact short the file's own docstring claims to defend against — cannot be detected: there is no junction in `geo`, and net-identity is never compared at the junction coordinate. Gate correctness rests entirely on an *unverified* router invariant (see Finding 4).
- **LAW:** LAW 0 (cross-net junction = short that ERC/overlap=0 miss).
- **Fix:** Add a `Junction` primitive + parameter to `visual_gate.check()`; pass `routed.junctions` into `SheetGeometry` at `place.py:4954/4980`. In the gate, for every junction coordinate assert that *all* segments incident at that point share one net (flag any cross-net junction as a SHORT).

### 3. [HIGH] Latent N/S handedness variant — same root as Finding 1, dormant only by current pinning
- **Artifact / location:** `schgen/generate/pcb.py:460-464,481-482` (`_ROT_FACE_POS_X`), same CCW/CW split.
- **Defect:** XT60PW-M (`motor_sense`, +X face) gets rot 270 on N / rot 90 on S; under the CW transform those point the mouth inboard. It ships correct *today* only because it's pinned to E (rot 0, where CW==CCW). Any re-pin of a ±X connector to N/S faces inboard and the gate passes it.
- **LAW:** LAW 6.
- **Fix:** Same as Finding 1 — fixing the unified transform + geometry-derived oracle closes this automatically. (Group with #1.)

### 4. [HIGH] Visual gate trusts an unverified router invariant; post-route rounding can defeat it
- **Artifact / location:** `visual_gate.py:9-14` (docstring), `:120-138`; `place.py:4973-4979` post-route translate + `round(…,3)`.
- **Defect:** The gate's only cross-net contact tests are `_cross` and `_foreign_t_touch`; it never proves the "no two nets share a cell" claim. The post-route coordinate translate/round runs on segs *and* junctions independently of the grid's cell-ownership check — rounding can collapse two near-coincident different-net points onto one mm coordinate *after* routing claimed them distinct, with no re-validation.
- **LAW:** LAW 0 / LAW 4.
- **Fix:** After the final round, run an independent connected-components net-identity check over the emitted geometry (the SHORT/OPEN detector mandated by LAW 0) before any pass claim. (Naturally satisfied by the Finding 2 junction-aware check if it operates on post-round coordinates.)

### 5. [HIGH] Same-net wire-over-wire overlap is never flagged
- **Artifact / location:** `visual_gate.py:87-95` `_collinear_overlap`, gated at `:190` by `a.net != b.net`.
- **Defect:** Collinear-overlap is only tested for *foreign* nets, so two same-net segments drawn directly on top of each other (a doubled-back/duplicated trace) pass silently — a visible LAW-1 "no wire over a wire" defect the router's BFS-join can plausibly produce.
- **LAW:** LAW 1.
- **Fix:** Call `_collinear_overlap` for *all* pairs; for same-net pairs flag coincident overlap as a wire-over-wire defect (keep cross-net as the short check).

### 6. [HIGH] Router appends BFS-completion legs after planarization — same-net T/cross/over-draw with no junction dot
- **Artifact / location:** `route.py:321-328` (BFS completion) → `_bfs_join:391-439`, vs planarization/residual at `:214-289`.
- **Defect:** BFS legs are appended *after* same-net planarization and self-overlap checks already ran, and are never re-checked. `_bfs_join` reuses own-net cells freely, so a BFS path can run collinear over an existing leg or land its interior on another leg's endpoint (a real 3-way node) — but the degree count tallies only endpoints, so **no junction dot is emitted** at that node (a LAW-0 open/short-risk), and the visual gate is same-net-exempt downstream.
- **LAW:** LAW 0 (missing junction at ≥3 merge) / LAW 1.
- **Fix:** Re-run planarization + endpoint-on-interior splitting over `g.legs` *after* BFS completion; recount degree including interior incidences so a junction dot is emitted at every real ≥3 node. (Pairs with #5; both are facets of "post-completion geometry isn't re-validated.")

### 7. [HIGH] Connector descriptor placement is blind to all 288 component refdes (dead code path)
- **Artifact / location:** `schgen/generate/pcb.py:2197-2216` (`_emitted_text_boxes`), consumed at `:2300`.
- **Defect:** `_emitted_text_boxes` scans only `fp_text reference/value`, but `_embed_footprint` writes refdes as modern `property "Reference"` nodes. **Confirmed:** board has 288 `property "Reference"` and **zero** `fp_text reference`. So the reference/value branch is dead; the function returns only the title `gr_text` box. Every connector function label (PWR/HDMI/ETH/USB/JTAG…) is placed without seeing any of the 288 visible designators → can overprint neighboring refdes silk.
- **LAW:** LAW 1 (zero text-over-text).
- **Fix:** Rewrite `_emitted_text_boxes` to read `property "Reference"`/`"Value"` nodes (transform local→board), so `occupied` includes all designator boxes before descriptors are placed.

### 8. [HIGH] connector_model_gate accepts model-Z = 180 — the exact USB-C inward-mouth bug it was built to catch
- **Artifact / location:** `schgen/verify/connector_model_gate.py:261` `elif round(z) % 180 != 0:` (**confirmed**); contradicts docstring invariant (1) at `:23-28` ("non-zero Z FAILS").
- **Defect:** `% 180` accepts both 0 and 180. TYPE-C-31-M-12 returns Z=180 and passes; a 180° Z flips the rendered shell in-plane (which end the cavity points) — the documented failure mode. The geometry cross-check inspects pad rows, not the model rotate node, so it cannot re-catch a model-only flip.
- **LAW:** LAW 6 / LAW 1.
- **Fix:** Change `:261` to `round(z) % 360 != 0` per the gate's own invariant. Verify the TYPE-C-31-M-12 part's model rotate is corrected to 0 in `parts/` (and that the connector still renders mouth-out) rather than relying on the 180 fudge.

### 9. [HIGH] Text-width model under-estimates wide glyphs (W/M/X/D) — overlap gate can pass touching text
- **Artifact / location:** `schgen/layout/textmetrics.py:8-9,17` (`CHAR_W=0.95`); consumed at `place.py:194` (pin numbers, no slack), `:204`, `centered_box()` callers, and `visual_gate.py:147-162` (0.2 mm clearance).
- **Defect:** `CHAR_W=0.95` is the *average* advance, but the overlap gate needs *worst-case*. Widest Newstroke glyphs advance ~1.21–1.25× size; "MMMMMMMMMM" renders 14.05 mm vs the model's 12.06 mm (1.99 mm short = 10× the 0.2 mm clearance). A W/M/X/D-heavy pin name/value/label can render touching a neighbor while the gate reports overlap=0. *(Latent on the two shipped designs — Finding L-x confirms 0/261 labels currently under-bound — but a live LAW-1 hole the moment such a string appears.)*
- **LAW:** LAW 1 + the module's own "never under-estimate" invariant.
- **Fix:** Use a per-glyph max-advance table (or set `CHAR_W` to the worst-case ~1.25), keeping the estimate a true over-bound. Re-verify against kicad-cli ink-bbox for W/M/X/D runs.

### 10. [HIGH] Netlist gate never sanity-checks the *declared* netlist — capshort (both pins one net) class uncovered
- **Artifact / location:** `schgen/verify/netlist_gate.py:104-186`; net builder `schgen/core/model.py:272-295`.
- **Defect:** The gate is a declared-vs-extracted equivalence checker only. A 2-pin part with both pins declared on one net (e.g. `C5.1`+`C5.2` on `GND`) is electrically dead, but every branch is green (SHORT needs ≥2 distinct declared names; OPEN needs a split; NAME matches). `Circuit.net()` has no degenerate-net guard, and the selftest mutator set has no both-pins-same-net mutant. This is the exact historical capshort class.
- **LAW:** LAW 0.
- **Fix:** Add a declared-side rule rejecting both terminals of a Device:C/Device:R on the same net (in `model.py` net build, or as a netlist_gate pre-check). Add a `mutate_both_pins_same_net` mutant to `selftest.py` to prove it.

### 11. [HIGH] ESC PWM 3×8 header (HX_PZ2.54-3x8P_ZZ) renders as bare pads / half-missing body — model mis-rotated 90°
- **Artifact / location:** `parts/HX_PZ2.54-3x8P_ZZ/HX_PZ2.54-3x8P_ZZ.kicad_mod:359-376` (three `PinHeader_1x08…Vertical.step` models, each `(rotate (xyz 0 0 90))`); visible in `3d_top.png`, `3d_persp.png`.
- **Defect:** Pads span X=−8.89..+8.89 (8 columns along X) at Y rows −2.54/0/+2.54. A 1×08 vertical-header STEP runs its 8 pins along local +X; rotating 90° about Z lays each row-body along Y (perpendicular to the pad row), collapsing each body onto the left columns and leaving the right ~4 columns as bare gold pads. The recent "give it a body" commit did *not* take.
- **LAW:** LAW 6 / LAW 1.
- **Fix:** Change the three model `(rotate …)` from `0 0 90` to `0 0 0` so each body spans its row. *(This is a `parts/` footprint asset, not a generated board — editing the `.kicad_mod` is correct here. Re-render and inspect.)* **Note:** Findings "3d_persp/3d_top bare body" and "3d_bottom floating body" are the **same component, same root cause** — dedup as one fix.

### 12. [HIGH] Board is fully unrouted — 499 airwires + 130 schematic-parity pad-missing-net gaps
- **Artifact / location:** `electrical:drc` — 499 `unconnected_items`; 130 "Pad missing net given by schematic" (SW1001 pads 2/4/6, SW7006 4/6, U3002 CLKOUT pad1, U8001 NC pad6, etc.).
- **Defect:** Per LAW 5 these are airwires, *not* DRC clearance errors — but the board cannot tape out unrouted. The 130 pad-missing-net entries are completeness gaps (pads carrying `<no net>` vs the schematic), not shorts.
- **LAW:** LAW 5 + schematic-parity completeness.
- **Fix:** Routing is downstream of the gate/orientation fixes above (don't route a board whose connectors face inboard). Reconcile the 130 unconnected pads in the relevant subsystem authoring (likely NC/mechanical pads needing explicit net or `unconnected` declaration). **Sequence after #1, #2.**

### 13. [HIGH] Ratsnest/clustering gate is a rubber stamp — four compounding metric flaws
> **Grouped as one root-cause cluster: the LAW-5 grouping/airwire gate does not meaningfully bound a hairball.**
- **Artifact / location:** `schgen/verify/ratsnest_gate.py`.
  - **(a) Back-fit budget** (`:46-51,156-163`): live cross_mm=14038.5 vs budget=15146.7 → **92.7% consumed**, ~7.3% headroom; threshold clearly fitted to barely pass.
  - **(b) Budget scales with `n_subsystems`** (`:158-161`), counted as distinct `inst.sheet` values; fragmenting one logical subsystem across sheets (usb_jtag+connector, ethernet+rj45, hdmi_tx/rx/term, power+power_som, bringup×4 → live n=33 from 37 sheets) *inflates the allowance* — rewards the very fragmentation a hairball exhibits.
  - **(c) Dispersion = bbox_area / Σcourtyard** (`:140-153`): scales with part *size*, not absolute scatter; a single axis-aligned bbox can't see a subsystem split into two tight clusters; no contiguity/connected-component check. (Hand calc: two tight groups 100 mm apart → disp 0.88, PASS.)
  - **(d) MST built under L1 (Manhattan) but summed under L2 (Euclidean)** (`generate/ratsnest.py:84,103` vs `:139`): the scored tree is not minimal for the metric scored — pass/fail hinges on an inconsistent estimator.
- **LAW:** LAW 5.
- **Fix:** (a) Set an absolute, design-justified budget, not a fraction of current state. (b) Count *logical* subsystems (collapse `_connector`/`_term`/family suffixes) before scaling. (c) Add a per-subsystem connected-component / max-pairwise-distance contiguity check independent of part size. (d) Build the MST under the *same* metric (Euclidean) used to sum it. *(MEDIUM-severity items DISPERSION_MAX=9.0, SMALL_N exemption, and courtyard-vs-pad-bbox mismatch below are facets of this same gate — fix together.)*

### 14. [HIGH] Three render-visible symbol-over-wire overlaps that read as shorts (schematic)
> **Grouped: power/ground symbol graphic coincident with a *different*-net wire — a LAW-1 overlap that also presents as a LAW-0 short to a human reviewer. Root cause is shared (power-symbol placement collides with an adjacent foreign-net wire row); fix the symbol/wire placement logic, not each sheet.**
  - **lcd / U2 (USBLC6-2SC6):** LCD_CTP_RST wire runs collinear along U2's bottom body border (`/tmp/lcd_thru.png`). LAW 1 + LAW 0 risk (obscures whether it ties a pin).
  - **power_mon / U2 (INA3221):** GND triangle tip lands on the +3V3_SC wire at y≈66.0 mm; GND value text straddles the +3V3_SC/A0 rows. Different nets → reads as GND/3V3 short.
  - **usb_jtag_connector / CHASSIS_GND:** CHASSIS_GND hatch strokes descend onto the lower CC2 wire (R2→J1.B5) passing beneath. Two different nets graphically coincident at a ground symbol.
- **LAW:** LAW 1 (+ LAW 0 readability/short-appearance).
- **Fix:** This is also the symptom the *gate blind spots* (Findings 2, "wire-over-body" MED, Finding 7) fail to catch. In the placer/router: (i) treat power/ground symbol bodies as wire keepouts (segment-vs-body, not center-containment — see MED `route.py:78-89`); (ii) add the missing wire-vs-body check to `visual_gate.py:164-178`. Re-render and inspect all three.

---

## Should-fix (MEDIUM)

| # | Artifact / Location | Defect | LAW | Recommended fix (generator) |
|---|---|---|---|---|
| M1 | `board_qwiic` GND #PWR2003 @ (168.91,91.44) vs QWIIC_SCL wire @ y=93.98 | GND triangle apex + "GND" label sit on the QWIIC_SCL (foreign-net) wire; reads as short | L1+L0 | Power-symbol-vs-foreign-wire keepout in placer (same as #14) |
| M2 | `board_qwiic` lower-center stubs (GND/+3V3_AUX/+3V3) | Three dangling power stubs ending in open diamonds; **not in current source** — render shows stale/dangling ends | L1/L0 OPEN | Confirm render is built from current `.kicad_sch`; if stubs persist, fix the emitter that leaves unterminated power stubs |
| M3 | `hdmi_rx` U4 (TPD4E05U06DQAR) pins 9/10 | Value text "TPD4E05U06DQAR" overprints rotated pin-number "10" and NC "X" markers (U2/U3 place it correctly) | L1 | Value-text placement must clear NC markers/pin numbers (per-part offset bug) |
| M4 | `pd_input` U1 (TPS26631PWPR) pins 4/5 | "+VBUS_IN" label overprints the two NC "X" markers on B_GATE/DRV | L1 | Label placer must avoid NC-marker boxes (two findings, same node — dedup) |
| M5 | `bringup_en_modules` C10/C11 GND @ y=252.73 | Two right-most cap GND symbols + stubs overrun into the title-block frame | L1 | Title-block keepout in power-symbol placement; or move cap bank left of title block |
| M6 | `mechanical`, `usb_jtag_connector`, `pmod_expansion`, `power_som`, `board_services`(LOW), `usb_jtag`(LOW) title fields | Long Title strings overflow the title-block cell, cross the border rule / zone markers | L1 | **Shared root cause** — title-string-too-long. Truncate/wrap/auto-shrink title text to fit the cell in the title-block emitter |
| M7 | `motor_sense` below RS1 | Two orphan power stubs (GND, +3V3_SC) ending in open diamonds | L0/L1 | Same emitter as M2 — eliminate dangling power stubs |
| M8 | `electrical:high-risk-net-trace` CAM_* pairs, R8001/2/3 (100R) | 100R differential termination sits at the *camera* (J8001/TX) end, not the Zynq (J26003/RX) end — plausible root of "dead MIPI camera" | L0 (net sense) | Confirm Zynq PL MIPI/LVDS termination strategy; if external term needed, move it to the J26003 end in the camera subsystem authoring. *(conf 0.55 — verify before moving)* |
| M9 | `electrical:drc` F.Silkscreen | 75 silk_overlap (20 refdes-over-refdes e.g. U18001/U18002) + 37 silk_over_copper + 34 silk_edge_clearance (HDMI J12001 dominates) | L1 | `_declutter_refdes` + silk-vs-edge/pad clearance in the silk emitter |
| M10 | `visual_gate.py` blind spots (3 facets) | `_cross` exempts diagonals (`:79-80`); wire-vs-**body** never flagged (`:168/176`); own-label `-0.14` magic negative pad (`:174`) | L1/L4 | Add diagonal handling; add wire-vs-body (kind=='body') check; remove negative pad fudge |
| M11 | `route.py:78-89` `block_box` | Cell blocked only on center-strict-interior → wire can run flush along a body edge; no segment-vs-box test | L1 | Use segment/silhouette coverage, not center containment |
| M12 | `pcb.py:2304-2329` off-board descriptors | Placed at fixed offset with **no** `occupied` clearance check (unlike interior labels) | L1 | Route off-board descriptors through `_place_clear_label` too (compounds #7) |
| M13 | `pcb.py:974/1051/1069` (CCW zone) vs `:1471/1694` (CW courtyard) | Zone reservation uses CCW bbox, emitted courtyard uses CW — differ for asymmetric rotated connectors → under/over-reserve | L6/L1 | Unify on CW (same fix as #1) |
| M14 | `model3d_gate.py:218-260` `_fab_xy` | Size-fit heuristic returns None (vacuous) for TYPE-C/HDMI/DS1024/SWPA — F.Fab has only text, outline on SilkS/CrtYd | L1 | Fall back to F.SilkS/F.CrtYd outline geometry when F.Fab has no body lines |
| M15 | `connector_spacing_gate.py:144-156` | Staggered same-edge wide connectors with <50% perpendicular band overlap escape the overmold-gap check | L6 | Classify "same edge" by edge-proximity, not band overlap; check along-edge gap regardless of stagger |
| M16 | `ratsnest_gate.py:45/150/52-55/130-134` | DISPERSION_MAX=9.0 dead band (som_decoupling already 8.85); SMALL_N≤3 fully exempt (rj45_connector n=3, board_qwiic n=2); courtyard-vs-pad-bbox mismatch inflates disp for edge connectors | L5 | Facets of #13 — tighten threshold to doc's 1–3×, remove blanket small-N exemption (use max-pairwise-distance), reconcile bbox source |

---

## Minor (LOW)

- **Title-block overflow (LOW siblings of M6):** `board_services` ("…QWIIC on" bisected by divider), `usb_jtag` ("isolated" off the frame) — same root as M6.
- **NC-marker over pin-number text:** `debug_boot` J1 pins 14/12; `usb_pd` U1 (FUSB302) pins 12/13 — NC "X" strokes touch pin-number digits. Nudge NC marker offset in the symbol/pin emitter.
- **`motor_pwm` D1 & D2 (SRV05-4):** pin-number "2" overlaps the "S" of value "SRV05-4" (identical defect, both diodes). Value-text offset for this symbol.
- **`visual_gate.py:155-158`:** same-owner text-vs-own-body fully exempt — a pin/value label over its own body outline is never flagged (LAW-1 readability hole).
- **`pcb.py:1184-1187` / `placement_mech.py:144-149`:** un-pinned connector left un-seated and relies solely on the (unsound) CCW mouth gate — closed by #1.
- **`route.py:309-319`:** bridged-PORT branch accepts a lone-label islet attached to no pin → dangling label (conf 0.45).
- **`ratsnest_gate.py:107-134`:** off-board check assumes a rectangular Edge.Cuts; a part in an L-shape/cutout would pass (latent — board is rectangular).
- **`connector_spacing_gate.py:121-130/44-51`:** overmold policing family-gated to a hand table containing only HDMI-019S; XT60PW-M / USB-C not enforced. Add an assertion forcing wide connectors into the table.
- **`textmetrics.py` (latent):** 0/261 real labels currently under-bound — confirms #9 is latent, not live, in this repo.
- **`carrier/nets.py` stale (conf 0.97):** missing +3V3_DBG, +3V3_PMODX, +5V_DBG, +5V_MOTOR_IO; **but zero real importers** (every subsystem uses raw string literals), so dead-letter today. Regenerate via `python -m schgen nets` and add a CI freshness gate.
- **`electrical:powertree`:** VADJ LDO (fmc U1 TLV75725) at **exactly 100%** of its 0.400 A derate (Tj fine, 35°C margin) — zero current headroom, single tightest node. Track, not a defect.

### Confirmed NON-defects / false-positive guards (do not "fix")
- **ERC:** 0 genuine electrical violations. The 562 `--severity-all` hits are environmental (lib/fp-link config), `same_local_global_label`, and benign dangling stubs — no `pin_not_driven`, no conflicting outputs, no `no_connect_connected`.
- **DRC:** 0 ERROR-severity, **zero** clearance/hole/short violations (those checks ran and passed). 296 are all warnings (silk/text/lib).
- **net_conflict (5):** pure `/` vs `{slash}` escaping artifact — **not** a cross-net short.
- **isolated_pin_label (34):** by-design single-pin SoM-connector breakouts.
- **render.py / diagram.py:** sound — single KiCad draw path, no netlist divergence; diagram.py carries no electrical meaning.

---

## Recommended Fix Order

1. **Finding 1 + 3 + M13 (handedness unification).** Highest impact, *proven shipped defect*, and blocks routing — never route a board whose edge connectors face inboard. Fix the transform + geometry-derived mouth oracle first.
2. **Finding 2 + 4 (junction-aware visual gate + post-round net-identity check).** Restores LAW-0 trust so every subsequent change can be *believed* when gates go green.
3. **Findings 5 + 6 (router post-completion re-planarization).** Eliminates same-net over-draw and missing-junction nodes before any routing pass is run/believed.
4. **Findings 8, 9, 10 (gate soundness: model-Z, text-width, capshort + mutant).** Cheap, close known blind spots; do before trusting layout/netlist passes.
5. **Finding 11 (ESC PWM model rotate 90→0).** Self-contained `parts/` asset fix; re-render.
6. **Finding 7 + M12 (descriptor sees real refdes + clearance).** Unblocks clean silk/label placement.
7. **Finding 13 + M16 (ratsnest gate overhaul).** Make the LAW-5 guard meaningful before relying on it to bless placement.
8. **Finding 14 + M1/M11/M10 (symbol-over-wire keepouts + wire-vs-body gate).** Clears the render-visible schematic shorts-by-appearance.
9. **M3–M7, M9 + LOW title/NC/value overlaps (incl. M6 title-block auto-fit).** Render-cleanliness sweep.
10. **Finding 12 (route the board) + M8 (MIPI termination verify) + nets.py regen.** Routing last, on a board that is now mechanically and electrically trustworthy; M8 needs datasheet verification before moving the resistors.