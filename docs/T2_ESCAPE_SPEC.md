All anchors verified live (untracked gate files present; emit.py:38 circular-import hazard, uid:85, declutter:151, annular:321, run_pcb_drc:580; __main__:318/:1113; K=2 @ return_path_gate.py:70 with the "HARD-FAILS/never waived" docstring at :38/:45; PcbModel @ constants.py:89; build_model tail @ placement.py:1109; permissive SoM keepout @ embed.py:355). Synthesizing the final spec.

# ESCAPE-BLOCK — FINAL IMPLEMENTATION SPEC (wave T2: DF40 escape / J2 return-path remediation)

**Provenance.** Composite of the three judged escape-bracket winners with every mandatory graft and surviving amendment folded in: **return-path-first** (spine: two-stage return-before-signal architecture, construct-tighter-than-gate, additive byte-superset emission; composite 8.6) + **toolchain-pragmatist** (emit mechanics: probe-verified kicad-cli 10.0.2 semantics, unfilled In1 plane + `--refill-zones`, invariant-pins-not-count-pins, unrounded-margin policy) + **lane-assignment** (two-tier lane architecture, si_triage, 15-GENUINE pair scoping, coverage-aware seat feasibility, L0 probe). Where the winners conflicted, §12 records the synthesizer's resolution and rationale. All laws apply: LAW-0 (netlist sacred, proven twice), LAW-1 (render verdict final), LAW-4 (no gate softened, every threshold carries a basis string), LAW-5/6 (no part moves, no seat moves), LAW-7 (fail loud, never defer without a named consuming phase), red-on-before, byte-determinism.

---

## 1. Problem and measured baseline (derive-live rule)

Three DF40C-100DP receptacles carry the SoM interface: `J24001`/`J25002`/`J26003` = sheets `som_j1/2/3`, poses (105.41, 82.55) r0 / (105.41, 118.11) r0 / (87.63, 100.33) r90. Footprint truth (parts/DF40C-100DP-0.4V_51): 0.4 mm pitch, two rows at local y = ±1.355 (pads 0.2×0.66, inner tips |y| = 1.025 → 2.05 mm top-empty inter-row channel), 100 signal pads x ∈ [−9.8, +9.8] + 4 mech pads at ±10.265; **netted contacts 93/100/100** (J1 has 7 unnetted signal pads — derive lane counts from `pad_nets`, never the pad total).

`schgen/verify/return_path_gate.py` (v1, **K = 2**, untracked today — landed by P1) measures the MATED interface: 69 HS-capable pairs, 138 contacts, **29 failing** = J1: 1 (FMC_LA10_P, pad 90) + **J2: 28** (banks 13/33, incl. all 8 GENUINE TMDS/HDMI_RX halves) + J3: 0, worst distance 4 contact-steps. *The orchestrator brief's "28" is the J2-only tally; the remediation set is all 29.* The SoM pinout is FIXED, so v1 is red **by module design**; the carrier's duty is escape-fanout return stitching, judged by a new gate over copper the carrier controls.

The emitted board is **copperless** today (0 `segment`/`via` nodes; In1.Cu is only *labelled* GND; the sole zone is the permissive SoM keepout, embed.py:355 — tracks/vias/pour all `allowed`). Board 170×151; this wave: **board growth 0 mm, part movement 0, floorplan.json unread.**

**STALE-SCALAR RULE (binding):** every coordinate, band table, column index, and clearance figure in this spec is illustration. The implementation derives everything from the live build (v1 output + placed DP pad geometry + measured B.Cu obstacles). Fixtures pin **counts and invariants only** — never coordinates, never band/column indices (the two refuters' "conflicting" J2 band tables were the same physical copper indexed from opposite row ends; an index-pinned fixture would have stepped straight into that trap).

## 2. Architecture — two tiers

**Tier-1 (this wave, emitted locked copper):** the complete GND return network for the failing contacts —
banded **GND stitch vias** in the inter-row channels (triage-ordered), an **F.Cu ladder** (channel spine + GND-pad stubs, incl. the single-pad variant), and an **In1.Cu GND plane zone** (outline only in the file; filled in kicad-cli memory via `--refill-zones`). All nodes `(locked yes)` for later Freerouting fixed-preroute (Phase-L 5a). Emission is additive-by-construction: pre-wave board == post-wave board minus appended nodes (byte-superset proof).

**Tier-2 (planned and gate-proven this wave; copper lands with the routing phase):** per-contact surface **escape lanes** (identity order, both rows, all 3 connectors) + perimeter **ports** + full GND-contact cluster stitching, shipped as the portable `carrier/escape_block.json` artifact (Appendix-C escape block made real) and judged by a hard `escape_lane` gate on the **plan**. Lane copper is deliberately deferred: emitting ~270 intentionally-dangling signal stubs would couple build health to kicad-cli warning-count semantics for zero measurable gain today. This deferral is a **routing-phase contract with a named consumer** (D13 entry, §10), not a dropped thread — LAW-7 compliant.

**Scoping honesty (non-negotiable wording):** v1 stays red at 29 and its verdict is quoted verbatim in every build report; nothing anywhere claims "return path fixed." The deliverable is named **"carrier escape-fanout return stitching."**

## 3. Tier-1 algorithm — `schgen/generate/pcb/escape.py :: build_escape_copper(model)`

Runs at the `build_model()` tail (placement.py:1109, after the model dict is fully placed), single-threaded, pure function of (som_interface.json bytes, DP `.kicad_mod` bytes, placed PcbModel, module constants).

**3.0 Imports (blocking rule).** `return_path_gate` / `placement_contract_gate` are imported **inside** `build_escape_copper()` — the emit.generate() function-level-import house pattern. A module-level import provably deadlocks `schgen.generate.pcb` package init (emit.py:38 `from .placement import build_model` + the gate's module-level `from schgen.generate.pcb import PcbModel`). Alternative: reuse in-package pad helpers (`mating_face` pad geometry + `FootprintInst.pad_nets`).

**3.1 Failing set + frames.** Call `return_path_gate.check()` (K=2 untouched) → Violations(ref ∈ {J1,J2,J3}, pad). Map ref→carrier inst via the `som_j<n>` sheet convention; **pad NUMBER** → board pad box via the gate's `_pad_boxes`/`_inst_pad_boxes` cached CW transform (cx=px·cos+py·sin, cy=−px·sin+py·cos — never the CCW form). Pad numbers are identical DS/DP; geometry is the mirror — indexing by number in the placed DP frame defuses the mirror trap by construction. Inverse-transform to connector-local (u along row, v = ±1.355).

**3.2 Triage — `schgen/verify/si_triage.py`.** Basis-carrying regex classes: GENUINE = `HDMI_RX_(D\d|CLK)_[PN] | ZYNQ_HDMI_TX_TMDS_.* | ETH_PHY_MDI\d_[PN] | CAM_(D\d|CLK)_[PN]`; MODERATE = `FMC_.* | STM32_USB_D_[PN] |` LCD RGB/PCLK/sync; LOW = PMOD/UART/I2C/PWM/LED/CTP/SDIO/etc. (CTP touch-I2C = LOW; LCD parallel RGB = MODERATE). Unmatched SIGNAL net ⇒ **raise** (fail loud, never a silent default). Scope for Tier-1: the table must classify the 29 failing contacts' nets (small set, curated in P1); the full 204-net DF40 population — including leaked raw `IO_*` names such as IO_L10_N_13 on J25002 pad 51, itself a failing contact — is completed in P4 before the lane gate wires (its report dumps the full classified list). **Triage is ORDERING + REPORTING only. It is never a waiver: all 29 contacts are covered regardless of class** (banding makes full coverage cheaper than any waiver machinery — LAW 4 keeps the gate class-blind).

**3.3 Banding — the corrected 1-D covering greedy (mandatory graft; the literal absorb-greedy is WRONG).** Per connector, project both rows' failing contacts to the channel axis; sort by `(round(u,4), int(pad))` (explicit tie-break — facing-row pads share u exactly). With reach r = √(R_CONSTRUCT² − 1.355²) = **1.185 mm**: band = all contacts within `[u_first, u_first + 2r]`; via feasibility window = intersection of per-contact reach intervals = `[u_last − r, u_first + r]`, **nonempty by construction**. This is the optimal covering for uniform reach; on today's board it yields **J2 = 5 bands, J1 = 1 (+1 redundancy partner), J3 = 0** — the literal "absorb ≤ r from the via" rule splits the two 1.2 mm-span 8-contact bands (1.2 > r) into 7 J2 vias and fails its own fixtures; arithmetic confirmed by both judges.

**3.4 Via seating — deterministic 2D lattice with coverage as a HARD feasibility term.** Candidates (u, v): u on a 0.05 mm grid over the band window, v in fixed order 0, ±0.05 … ±v_max, where v_max = 1.025 − via_radius − 0.15 (0.65 for the 0.45 via); enumeration ordered **(|v| asc, |u − window_center| asc, + before −)** — on-axis preferred: v moves toward the clearance-critical pad tips, u slides the free channel (this lexicographic key IS the realized optimum; do not describe it as an L1 argmin). Via size ladder, larger first (thermal/inductance preference, judgment): **0.45/0.3 → 0.4/0.25 → 0.35/0.2**. The 0.3/0.2 rung is FORBIDDEN: its annular width equals the emitted `min_via_annular_width` 0.05 exactly (emit.py:321) — zero margin at a boundary equality; 0.35/0.2 gives 0.075 and satisfies `min_via_diameter` 0.3.

A candidate is feasible iff ALL hold (basis: emitted DRC minimum + build margin, judgment):
- F.Cu annulus → foreign copper ≥ 0.25 (rule clearance 0.15 + 0.10);
- hole → any copper ≥ 0.3 (min_hole_clearance 0.2 + 0.10); hole ↔ hole ≥ 0.5 (0.25 + 0.25);
- **B.Cu annulus → bottom-side pad boxes ≥ 0.25** — pad-accurate boxes of every B.Cu inst within channel bbox + 2 mm, measured from the model with the same CW transform (today's obstacle set: the hdmi_rx straps R13003–R13006 at u ≈ 104.19/108.0 inside J2's channel, C22025/R22015 at u ≈ 116.4, plus J3's axis-straddling R9001/R9005);
- board edge ≥ 0.3; inside the channel and the In1 zone rect;
- **per-row coverage of EVERY band contact ≤ R_CONSTRUCT, computed per row as hypot(du, |±1.355 − v|), compared UNROUNDED** (a +v nudge helps the near row and hurts the far row — the coverage term is what makes v-nudges safe; its omission was a judged major);
- **against every already-accepted escape via AND its ladder copper** (accepted primitives join the obstacle set before the next seat — this is what makes hole-to-hole real and the genuine-first ordering meaningful).

**Seat order:** bands containing GENUINE contacts first, then MODERATE, then LOW; within a class, sorted by (ref, band u). Any escalation-forced degradation therefore lands on LOW bands.

**Escalation ladder (LAW 7 — a dropped via is never an outcome):** (1) full 2D lattice at 0.45/0.3; (2) re-scan at 0.4/0.25 then 0.35/0.2; (3) **SPLIT the band at its widest internal gap** (midpoint on tie), recurse per sub-band; (4) off-channel slot beyond the escape line with a straight clearance-checked B.Cu tie to the nearest som_decoupling GND pad (≤ 6 candidates ordered (distance, ref) — ADD-don't-relocate: connect to, never move); (5) **RuntimeError with the full candidate audit** — a red build, never a squeezed threshold, never a silently perturbed neighbor. Single-band connectors with failures (J1 today) get a second via ~1.0 mm along the channel (basis judgment:2 — a lone stitch via is a single point of failure for that connector's only remediation).

Expected landing on today's board (illustration, not fixture): **J2 = 5 vias (incl. the slide off R13004 to board-x ≈ 107.0, worst covered contact ≈ 1.69 mm), J1 = 2, J3 = 0 — ~7 total.** If the coverage-hard 2D search forces a split (as it did at the rejected 1.7 mm bound), the ledger documents which escalation fired; that is a legal outcome, not a failure.

**3.5 Ladder copper (F.Cu, all widths ≥ dru minimum_track 0.2032).** Per connector with failures: one contiguous **spine** (width 0.3) along the channel axis v=0 spanning the leftmost→rightmost attach point (clearing pad inner tips by 1.025 − 0.15 = 0.875 — state the rule, derive the number); **stubs** from GND pads down to the spine, three variants: (a) preferred **pair-gap stub** (width 0.3, centered in the 0.2 mm gap of an adjacent-GND-column pair, spanning row-to-row — connects 4 GND pads; pairs exist only on J2: {4,5},{14,15},{24,25},{34,35},{44,45} today); (b) **single-column row-to-row stub** (width 0.25) where one column is GND in both rows; (c) **single-GND-PAD stub** (width 0.25, pad center → spine; clearance to flanking signal pads 0.175, margin 0.025 over the 0.15 rule — thin but measured-pass) — **mandatory for J1**, whose only both-rows GND column (38) is ~11.2 mm from the failing band while single-row GND pads sit ≤ 1.6 mm away (col 13 bottom / col 14 top). Rule: every via connects through the spine to ≥ 2 GND-pad stubs per connector (nearest on each side where available; J1 one-sided is legal via two single-pad stubs).

**3.6 In1.Cu GND plane.** One zone, net = `model.net_numbers["GND"]` (looked up by NAME, RuntimeError if absent — never net-0 copper), rectangle = SoM keepout grown +2.0 → (82, 76.5)–(138, 124.5) (basis: covers all 3 channels + escape lines + slots with ≥ 0.5 mm margin; ≥ 20 mm from Edge.Cuts vs copper-edge 0.3), solid `connect_pads` (avoids starved_thermal ERRORs; DFM tradeoff recorded), **emitted UNFILLED** — fills exist only inside kicad-cli memory via `--refill-zones` (probe-verified on 10.0.2: in-memory evaluation, input file hash unchanged) — so byte-determinism needs no hand-rolled fill. **Precondition, hard-checked every build: ZERO foreign thru/NPTH barrels inside the zone rect** (measured true today); the octagonal carve-out (r = hole/2 + 0.2 + 0.1) is the documented future path should one appear. The permissive SoM keepout is exactly the marker that makes this legal; no new restrictive zone is added.

**3.7 LAW-0 generator self-check (first proof).** Connected components over {spine ∪ stubs ∪ vias ∪ all DF40 pads ∪ nearby bottom pads}: each connector's ladder = ONE component containing ONLY GND-net pads; every via touches the spine (F.Cu file-visible copper) and lies inside the GND zone rect (In1 plane connection, modeled fill-independently); every emitted primitive carries the GND net number; pairwise emitted-primitive vs foreign-pad clearance ≥ DRC minimums. Any breach ⇒ RuntimeError. (Second, independent proof: §6 gate. Third: kicad-cli DRC error-severity backstop, mutation-proven.)

## 4. Tier-2 lane plan — `build_escape_plan(model)` (same module; artifact + gate this wave, copper at routing)

- **Identity order** per row: the inter-pad gap 0.2 < 0.39 (= 0.09 track + 2×0.15 clearance) forbids crossing inside the pad band, so order-preserving straight own-column stubs are feasible; state identity as the **chosen lexicographic optimum** (uniqueness holds only within the pad band — the 1.015 mm annulus before the escape line admits ~2 crossing levels); the gate asserts **port-line monotonicity**, not uniqueness.
- **Geometry:** SIGNAL/POWER lanes run outward from pad center to the escape line at pad_outer_tip 1.685 + LANE_HANDLE 1.0 = 2.685 mm from the connector axis (≈1.33 past row center; measured corridors to the SoM keepout today 2.275/2.695/3.035 from row — per-connector clearance ≥ 0.3 asserted at build); GND lanes terminate INWARD to the spine (vacating the middle lane of GND-interleaved pairs); contiguous POWER runs group into one bus_group (VIN's 0.4 class floor cannot fit 0.4 pitch — planes own power).
- **Width fail-loud:** net → class → `geo.width_mm` via `model.netclass_of`/`model.classes`; a diff-class net with no geometry raises. The emitted `.kicad_dru` pins each diff class's track_width min=max at ERROR severity — and note the dru lands at `carrier/manufacturing/…kicad_dru`, which kicad-cli does **not** auto-load: the effective 0.15 clearance authority is `DEFAULT_CLEARANCE_MM`/the Default netclass (basis strings cite THAT; the L0 probe pins which rule source kicad-cli enforces).
- **Pair records:** hard terms (same-row membership, |Δlane| ≤ 2, exactly-symmetric equal-direction stubs, GND-interleaved middle-lane vacate) apply to the **15 si_triage-GENUINE pairs ONLY** — measured true for all 15, incl. the mutually-interleaved TMDS quads 67/69↔68/70 and 71/73↔72/74; basis string: "measured maximum over the 15 GENUINE pairs = 2". Every other detected pair gets a report-only PairRec recording MEASURED topology (Δlane as-found; convergence classes `immediate|deferred|quad|row_wrap|split` — row_wrap = the u-wrap corner pairs 49/51 & 50/52, split = FMC_LA08-style gap-18). A pinned test freezes the 15-GENUINE fact + the known exempt set so pinout drift fails loud. (The old "over all 69 pairs" claim is refuted 15× by the fixed pinout — a permanent LAW-4 dead-end had it shipped.)
- **Full GND cluster stitching** (every GND contact within 2.0 of a plane via; clusters split by gap > 0.85 AND u-span cap 2·√(2.0²−1.355²) = 2.94 — span, not gap, bounds coverage; measured worst today 1.81 mm on J1's 7-tap cluster) **travels with Tier-2 copper**, not this wave.
- **Artifact:** `carrier/escape_block.json` — schema `escape/v1`, ports {net → (x, y, layer, width, si_class, bus_group)}, PairRecs, triage table, `content_key = sha256(som_interface.json bytes + DP .kicad_mod bytes + rule constants + the three DF40 poses rounded/sorted-by-ref)` (poses included so a floorplan move can never reuse a stale plan), `json.dumps(sort_keys=True)`.

## 5. Emit-pipeline extension (locked copper)

| File | Change |
|---|---|
| `schgen/generate/pcb/constants.py` | `PcbModel` (:89) gains `copper: list = field(default_factory=list)`, `escape_meta: dict = field(default_factory=dict)`, `escape_plan: object|None = None` — appended, default-valued; every constructor site unchanged. |
| `schgen/generate/pcb/escape.py` | NEW — §3 + §4; constants (R_CONSTRUCT, margins, widths, LANE_HANDLE) each with a basis string; lazy verify-imports only. |
| `schgen/generate/pcb/placement.py` | `build_model()` tail (:1109): construct model → `model.copper, model.escape_meta = build_escape_copper(model)`; `model.escape_plan = build_escape_plan(model)` (P4). |
| `schgen/generate/pcb/embed.py` | `_via_node`/`_segment_node`/`_gnd_plane_zone` helpers (pattern of `_som_keepout_zone` :355). `(via (at…)(size…)(drill…)(layers "F.Cu" "B.Cu")(locked yes)(net N)(uuid u))`; `(locked yes)` validated by the P0/P2 KiCad-10 round-trip, dropped-with-artifact-note if rejected. |
| `schgen/generate/pcb/emit.py` | `emit_pcb`: append copper nodes AFTER the footprint loop and after `_declutter_refdes` (:151) — segment/via/zone nodes are invisible to the silk/refdes/descriptor scans (dedicated transparency test). New per-kind uids (`stitch-via`, `stitch-seg`, `gnd-plane`) via the existing `uid()` sequencer (:85) → every pre-existing uuid stream byte-identical. `run_pcb_drc` (:580) adds `--refill-zones`. `generate()`: `results["return_stitch"]` (+`"escape_lanes"`, +report-only `"return_path"`); write `carrier/escape_block.json`. |
| `schgen/__main__.py` | `_pcb_error_count` (:318) adds `--refill-zones` (these are the two and only two DRC sites). After the placement_flow block (:1113–1130): write+print `carrier/reports/return_stitch.txt` (quoting the v1 verdict verbatim), `escape_lanes.txt`, and a **report-only** `return_path.txt` with the printed module-fixed rationale; `ok_all &=` return_stitch (P3) and escape_lane (P4); dangling ledger assertion (§7). |
| `schgen/verify/return_stitch_gate.py`, `escape_lane_gate.py`, `si_triage.py` | NEW gates + triage (§6). |
| `schgen/verify/return_path_gate.py` + `schgen/tests/test_return_path_gate.py` | Currently UNTRACKED — landed in P1 **with the same-commit docstring amendment** (§6). |

**LAW-0 connectivity proof of the extension** = three independent layers: generator self-check (§3.7) → gate re-check on the emitted model + file-parity crosscheck (§6) → kicad-cli DRC at error severity on the written file (clearance/shorting_items/track_width are error class), with a mutation test proving the backstop bites (via emitted at a TMDS pad center ⇒ DRC errors > 0).

## 6. Gates

**`return_stitch_gate` (return-path v2) — HARD, ANDed into ok_all (P3).**
`RETURN_VIA_RADIUS_MM = 2.0`, fixed, non-tunable. Basis: "K=2 admits a ground at ~2 contact-steps; channel geometry bounds the equivalent carrier-side spur at √(1.47²+1.355²) ≈ 2.0 | judgment:2.0". Construct target R_CONSTRUCT = 1.8 ("construct tighter than gate | judgment:1.8"). `check(model)`:
1. Recompute the failing set from v1 (never cached) and cross-check its scalars (69/138/29/worst-4) — the two gates can never drift;
2. every failing contact: nearest `group=="som_escape"` GND via ≤ 2.0, **unrounded compare** (round only at emission — the amended-solution margins live in sub-0.01 mm territory at tighter bounds);
3. via nets == GND; independent connectivity re-check (union-find, different code path from §3.7): one GND-only ladder component per connector, every via spine-touched + zone-rect-contained, ≥ 2 GND-pad stubs per ladder; plane present, on GND, zero foreign barrels inside;
4. clearance re-check vs DRC minimums; `hash_ok` (escape_meta sha256 vs recomputed som_interface.json);
5. `summary()` **quotes the v1 red verdict verbatim** (the SoM-design finding is never buried) and prints the triage-ranked (genuine-first) coverage table + per-class counts.
Reads copper via `getattr(model, "copper", [])` so the P1 red-on-before fixture runs before the P2 dataclass field exists.

**`escape_lane_gate` — HARD on the plan (P4).** FAILS when `model.escape_plan is None` (that IS the red-on-before state). Checks: identity/port-line monotonicity per row; per-lane clearance pre-proof at declared widths; ports inside corridors with ≥ 0.3 margin; 15-GENUINE pair terms (§4) + PairRec-vs-live-pinout consistency for all others; netted counts 93/100/100; content_key verification.

**`return_path_gate` v1 — REPORT-only, permanently.** K=2 and every threshold untouched. **Same-commit docstring amendment (P1, mandatory):** rewrite the ":38 INVARIANT (any failure HARD-FAILS…) / :45 never waived" text to codify the two-gate split — the contact-level result is a measured fact of the FIXED mated SoM pinout (reported, pinned scalars, consumed by escape.py as build input); the carrier-side hard obligation is `return_stitch_gate`. Plus a **test asserting v1 is absent from ok_all** with the rationale — the exclusion is a tested design decision from commit one, never a wiring accident that could later read as LAW-4 softening. Pinned pytest scalars (69 pairs / 138 contacts / 29 failing / worst 4) alarm on any SoM-interface drift.

**No triage exemption exists in any gate.** Triage severities appear in reports only.

## 7. Tests, proofs, regression bar

**Red-on-before (both forms):**
- Permanent pytest: v2 gate on the copper-suppressed model ⇒ FAIL with exactly **29** uncovered (J1=1/J2=28/J3=0), naming the 8 TMDS/HDMI halves GENUINE; escape_lane FAIL plan-missing.
- Commit sequence: commit A = gates wired, generator not called → a real `schgen board` goes RED with those numbers captured into `carrier/reports/return_stitch.txt` + the commit message; commit B flips green. Master merges only the green unit with the red evidence in history.

**Mutation battery (extend `test_pcb_gate_mutation.py`):** delete one via → coverage red naming the contact; shift a via so its worst covered contact > 2.0 (assert "> bound", never a fabricated distance) → red; re-net a via to +3V3 → net-identity red; delete a spine segment → connectivity red; drop the zone → plane red; inject a synthetic foreign barrel in the zone rect → precondition red; tamper the artifact hash → red; strip one emitted node from the board text → file-parity red; via at a TMDS pad center → kicad-cli DRC errors > 0 (backstop proof); synthetic unequal-length GENUINE pair stubs → symmetry red; non-monotonic lane order → planarity red.

**Generator tests:** covering-greedy on synthetic maps (row-end band, single-contact band, span > 2r split, window-intersection nonemptiness); coverage-hard candidate rejection (a v-nudge that breaks far-row coverage is rejected into the ladder); obstacle accumulation (second via respects the first); RuntimeError on a synthetic fully-blocked channel; double-run byte-equality of copper + artifact; explicit-sort-key determinism under shuffled input dicts.

**Regression bar (every landing phase):** full pytest green; `schgen board` twice **byte-identical**; **byte-superset proof** vs the pre-wave board; DRC severity-errors == 0 AND `n_violations` (warnings incl.) **delta == 0** for Tier-1, with warning-by-type counts (isolated_copper, starved_thermal, track_dangling) pinned as report scalars; FLOORPLAN.svg/MD + ratsnest/contract/flow/mech reports byte-identical (zero part movement proven); ruff/mypy/check.sh green; LAW-1 render verdict (§8 crops); commit + push per verified unit.

**Fixture policy:** permanent tests pin the 29-contact set, coverage/connectivity/clearance invariants, and the 15-GENUINE pair set. **Via count is NOT a permanent pin** — it is a ledger scalar asserted only self-consistent with the live greedy (the queued hdmi_rx wave and the D9 motor move re-place the exact B.Cu straps that force splits, so the count will legitimately drift). One-time P2 acceptance expects J2=5/J1=2/J3=0 absent splits, with any fired escalation documented.

## 8. Phased build plan

- **P0 — Toolchain probe (scratchpad only, no repo writes).** On a COPY of the board with kicad-cli 10.0.2: `(locked yes)` on segment/via round-trips; segment on In1.Cu (a power-TYPE layer) round-trips/renders/DRC-parses; zone `(fill yes)` unfilled-in-file + `--refill-zones` in-memory semantics + input-hash invariance; dangling/isolated warning accounting; **which rule source DRC enforces (Default netclass vs the non-auto-loaded manufacturing dru)**. Probe results become basis strings in escape.py docstrings.
- **P1 — Gates first, red-proven.** Track v1 + its test (with the docstring amendment + absent-from-ok_all test); land si_triage (29-contact scope) + return_stitch_gate (`getattr` copper) + red-on-before fixture + v1 cross-check. NOT in ok_all yet. Verify: pytest green; standalone gate run prints FAIL 29 on the real model.
- **P2 — Generator + emission, additive-proven.** escape.py Tier-1, PcbModel fields, embed helpers, emit append, `--refill-zones` at both DRC sites, artifact writer. Verify mechanically: DRC errors 0; warnings delta 0 (by-type ledger); build-twice byte-identical; byte-superset vs pre-wave board; v2 gate PASSES standalone — all 29 ≤ 2.0 (construct ≤ 1.8, worst ≈ 1.69 expected), silk-pass transparency test green.
- **P3 — Wire hard.** `generate()` result + `__main__` report/print/ok_all + mutation battery. Verify: full `schgen board` → BOARD GATE: PASS with the new line; every other report byte-identical; commit A/B red→green history recorded.
- **P4 — Tier-2 plan + lane gate.** Complete si_triage against the live 204-net population (classified dump into escape_lanes.txt); build_escape_plan + escape_lane_gate wired into ok_all; PairRec pinned tests; artifact with poses-inclusive content_key.
- **P5 — Evidence + docs.** NEW crop renderer (no reusable instrument exists — kicad-cli render + crop around the three known DF40 poses) → `carrier/reports/escape/j{1,2,3}_top.png` + an In1.Cu layer SVG; orchestrator LAW-1 verdict on ladder + channels; AI_LAYOUT_ROUTING_CONCEPT.md **D13** entry: banded-via decision, two-tier decision, v1-red-by-module-design statement, port ledger, and the named follow-ons. Commit + push.

**Queued follow-ons (each its own red-on-before unit, consumer named):** Tier-2 lane copper + full GND cluster stitch (consumer: routing phase / Freerouting locked-preroute); bottom-channel keepout under the DF40s if L4/som_decoupling drift ever closes a via window (deliberate byte-diff, reviewed); deterministic In1 fill-in-file if the in-memory posture ever fails a probe. **Sequencing:** this wave moves zero parts, so it does NOT wait on the pending usb_pd growth verdict; it must simply re-derive after any placement wave lands (fail-loud covers drift).

## 9. Acceptance criteria — which failing contacts, measured how

1. **All 29 v1-failing contacts are remediated** (the brief's "28" = J2 only): J2's 28 — including the 8 GENUINE TMDS/HDMI_RX halves — and J1's FMC_LA10_P (pad 90). J3 has none. No class is exempted; LOW riders are covered by the same bands.
2. **Measure:** Euclidean pad-center → stitch-via-center, per-row hypot(du, |±1.355 − v|), unrounded: every contact ≤ 2.0 mm (gate), constructed ≤ 1.8 mm; verified on the in-memory model AND parity-checked against the written .kicad_pcb.
3. **Return network integrity:** one GND-only component per remediated connector (F.Cu spine + ≥2 GND-pad stubs + vias), every via plane-connected (zone-rect + `--refill-zones` DRC clean), zero dangling/isolated copper (warnings delta 0).
4. **Immutability:** board 170×151 unchanged, growth 0 mm; zero part/seat/floorplan movement (all placement reports byte-identical); v1 still reports 29 (proof no gate was softened).
5. **Determinism:** build-twice byte-identical; byte-superset proof holds.
6. **Tier-2:** escape_lane gate green on the plan; 15-GENUINE pairs recorded with hard terms met; ports artifact hash-keyed.
7. **LAW-1:** orchestrator render verdict PASS on the three channel crops + In1 SVG.

## 10. Risks

1. **KiCad-10 grammar variance** — `(locked yes)`, segment-on-power-type-In1, zone tokens: front-loaded into P0/P2 round-trips; locking dropped-with-note if rejected.
2. **`--refill-zones` DRC wall-time** on 170×151 (+ KiCad-10 toolchain floor, already implied by the 20260206 epoch): measured at P2; floor documented in check.sh/docs.
3. **Warning-semantics coupling** — kicad-cli version drift in dangling/isolated accounting turns the delta-0 ledger red LOUDLY; by-type pins localize it.
4. **B.Cu drift closes via windows** — the hdmi_rx contract wave and D9 motor move re-place R13003–R13008; generator fails loud; remedy = the queued bottom-channel keepout unit (never a threshold relax, never a silent nudge of som_decoupling).
5. **Sub-band margins near bounds** — unrounded-compare policy + the 2.0/1.8 gate/construct gap keep micrometer noise out of verdicts.
6. **Solid connect_pads DFM tradeoff** (THT rework) — recorded judgment:assembled-board; revisit at DFM review.
7. **si_triage curation** — fail-loud means an uncurated net reds the first build; scoped 29-net table (P1) then full 204-net completion (P4) sequences the work before each gate wires.
8. **Scope inflation** — 20 of 29 are LOW riders; a green v2 gate must never be read as "return path fixed"; v1 quote + naming discipline enforce it.
9. **Plane performance is partial** — stitch + plane is the carrier-side best; the mated-connector discontinuity is SoM-fixed (D13 states the residual).
10. **iCloud eviction** during P2/P3 build loops (recorded ENV hazard) — run serially, attended.
11. **Stale scalars** — everything derives live each build; this spec's numbers are illustrations (§1 rule).

## 11. Constants table (all fixed, basis-carrying, non-configurable)

| Constant | Value | Basis |
|---|---|---|
| RETURN_VIA_RADIUS_MM (gate) | 2.0 | K=2 admission geometry √(1.47²+1.355²)≈2.0; judgment:2.0 |
| R_CONSTRUCT | 1.8 | construct tighter than gate; judgment:1.8 |
| via ladder | 0.45/0.3 → 0.4/0.25 → 0.35/0.2 | via_dimensions table; smallest rung keeps annular 0.075 > min 0.05 |
| annulus→foreign / hole→copper / hole↔hole | 0.25 / 0.3 / 0.5 | DRC min (0.15/0.2/0.25) + margin; judgment |
| SPINE_W / STUB_W_PAIR / STUB_W_SINGLE | 0.3 / 0.3 / 0.25 | ≥ dru minimum_track 0.2032; single-pad flank clearance 0.175 measured-pass |
| v_max | 1.025 − via_r − 0.15 | pad inner tip − annulus − clearance (derived live) |
| CLUSTER split (Tier-2) | gap > 0.85 AND span > 2.94 | 2 pitches; 2·√(2.0²−1.355²) span cap (measured worst 1.81 today) |
| LANE_HANDLE | 1.0 | router handle past pad tip 1.685; corridor margin ≥ 0.3 asserted per connector |
| zone rect | keepout +2.0 | covers channels/lines/slots ≥ 0.5; zero-foreign-barrel precondition |
| min vias per remediated connector | 2 | single-via SPOF; judgment:2 |

## 12. Synthesizer decision log (conflict resolutions)

1. **"28" → 29.** The brief's 28 is the J2-only tally; live v1 (triple-verified) = 29 incl. J1 FMC_LA10_P. Remediation covers all 29.
2. **Bound 2.0/1.8, not 1.7.** TP's 1.7 was judged basis-stale (its K=2 citation assumed 1.6 mm row spacing; placed DP rows are 2.71 apart) and left 2 µm margins; RPF's 2.0-gate/1.8-construct was judge-verified feasible with x-only slides and honors construct-tighter-than-gate. TP's real contributions — 2D seat search, coverage-as-hard-term, band split, unrounded compares — are all retained.
3. **Covering greedy, not absorb-greedy or gap-clustering.** Both judges' arithmetic converged: only the window-intersection greedy reproduces the optimal 5-band J2 cover.
4. **Plane IN scope** (TP/LA) via unfilled-zone + `--refill-zones` (probe-verified, byte-deterministic); RPF's In1 via-to-via link segments are superseded (plane is strictly stronger; F.Cu ladder still gives every via file-visible copper).
5. **Lanes plan-now / copper-at-routing** (LA two-tier), overriding RPF's lanes-as-copper: no failing gate demands lane copper today, and ~270 asserted-dangling warnings couple build health to kicad-cli warning semantics — RPF's own judge flagged that ledger as its most fragile piece. The deferral is a D13-recorded contract with the routing phase (LAW-7 clean); RPF's lane geometry and fail-loud width lookup are absorbed into the plan spec so Tier-2 copper is a pure emission step.
6. **Via count = ledger scalar, not permanent fixture** (TP), with RPF's expected 5/2/0 kept as one-time P2 acceptance; permanent pins are the 29-contact set + invariants. Rationale: queued placement waves move the exact blockers that determine splits.
7. **Uniform coverage of all 29 at one bound**; LA's R3=4.5 LOW tier dropped (judged near-vacuous) — triage stays ordering/reporting only.
8. **Full 63-GND-contact cluster stitch moved to Tier-2** — its electrical purpose (GND lane terminations) travels with lane copper; Tier-1 stays scoped to the measured defect.
9. **Single module `escape.py`, built at build_model tail** (TP/RPF placement) with LA's plan builder co-located; all verify-imports lazy (RPF mandatory graft — emit.py:38 cycle confirmed live).