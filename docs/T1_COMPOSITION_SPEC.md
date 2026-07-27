# COMPOSITION (T1) — FINAL IMPLEMENTATION SPEC
**Zone-pose composition against the Phase-L contract objectives: instrument → data migration → repair driver → in-engine legalizer → ratified intent edits → wiring waves → area recovery.**

Repo: `/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM`. Read `AI_LAYOUT_ROUTING_CONCEPT.md` (repo root) before starting; this spec appends to its D1–D12 history as decision T1. All line anchors below were re-verified against the live tree on 2026-07-02.

---

## 0. Synthesis verdict — what this spec is built from

Three composition designs each survived their bracket. This spec composes them by judged score and verified fit:

| Design | Judge score | Role in this spec |
|---|---|---|
| **incremental-migration** | 8.5 | **Program spine**: instrument-first, byte-identical data migration (pull knob), repair driver, ratified-intent edits, authoritative acceptance, banded no-worsen rule. All 12 of its grafts folded in. |
| **constraint-legalizer** | 8.0 | **Engine mechanism**: LEGALIZE+COMPACT stage inside `_attempt_pack` — difference-constraint feasibility (Bellman–Ford), weighted-median compaction, exact-evaluator accept loop. Makes wired terms hold **by construction** and lets the existing outer smallest-area scan recover area. All 10 of its grafts folded in. |
| **deterministic-local-search** | 6.0 (conditional) | **Superseded — its search engine (descent/restarts/shrink loop) is NOT built.** Its judged-fatal instrument premise (pre-L4 evaluator parity) is solved here by the legalizer's per-kind L4 exemption instead of L4-kernel replication (decision D-2 below). Its surviving amendments are absorbed: single-oracle kernels, guard bands, end-to-end build-twice test, manifest scoping, never-pin-scalars rule, per-candidate budget recompute, mechanical-sheet exclusion, near-intent scoring. |

**Binding synthesis decisions (no open questions):**

- **D-1 — Seat authority = spec data, derivation = consistency check.** The `_EDGE_SEAT_BLOCKS` hack is promoted to the validated floorplan.json `pull` knob (the code's own request at `floorplan.py:1489–1491`; IM P1). The constraint-legalizer's "derive seats from wired near_max terms" is recast as an **advisory ledger check**: any WIRED near_max term whose subject is an interior block carrying an `@edge-block` near-anchor (the exact `:1492–1493` precondition, scoped per CL graft 8) must have an exclusive pull in the spec, else the ledger flags it. Ethernet's seat at its wave is therefore a reviewed one-line spec diff, not silent behavior.
- **D-2 — Emit-faithfulness via L4 exemption, not L4 replication.** DLS's mandatory graft (shared L4 kernel in the evaluator) and CL's per-kind L4 exemption solve the same defect (LEVER-L4 at `placement.py:906–1035` moves copper 10–37mm after the pose the floorplan sees). The legalizer's difference-constraint system **requires** predictable positions, so the exemption route is adopted: flow/near_max/facing participants of wired contracts are L4-exempt; far-only participants (ethernet today, 80.94mm vs ≥10) keep L4 and get a measured far-guard. The exactness test then holds at ≤1e-6 for exempt sheets, GUARD_MM for edge-partner sheets.
- **D-3 — Area recovery = legalizer + existing outer scan, with a measured trigger for the rotation operator.** No separate shrink loop: the legalizer runs inside `_attempt_pack`, so every candidate `(W,H)` in the existing smallest-area search (aspects `:1186`, grow `:1190–1211`, fine window `:1253–1275`) is legalized with budgets recomputed at that candidate's area — DLS's "shrink strictness" absorbed with zero grandfather anywhere. If area does not recover to target by end of the waves, P10 schedules the sanctioned `_rotate_zone_90` unit (IM judge graft).
- **D-4 — D9 ordering.** Per the doc's recorded blast-radius ruling (`AI_LAYOUT_ROUTING_CONCEPT.md:758`): ethernet/hdmi_rx/power_som waves first, then the D9 edge edit (own commit, advisory-green), then the motor_sense wave hardens it. Named contingency: the doc couples D9 with the ethernet corridor (`:807–808`) — if the ethernet wave hits E-edge congestion, resequence the D9 edit ahead of it (both orderings satisfy repair-before-wire).
- **D-5 — No new hard gate.** `placement_flow_gate`/`placement_contract_gate`/`ratsnest_gate` remain the sole emitted-board enforcers. The ledger's floors are repair **triggers**; the legalizer is engine-internal. LAW-4 posture: infeasibility → candidate rejected → outer grow → existing `RuntimeError`. Nothing is ever waived or relaxed.

---

## 1. Measured baseline (re-verified live; stale figures corrected)

From `carrier/reports/placement_flow.txt`, `ratsnest.txt`, `placement_contract.txt`, `carrier/floorplan.json`:

| Scalar | Live value | Note |
|---|---|---|
| Board | **170×151mm = 25,670mm²** | pre-contract class was 154×152 = 23,408mm² (+9.7%) |
| flow_budget | 123.3mm | `FLOW_K·√(WH)+FLOW_SOM_K·som_diag`, `placement_flow_gate.py:278–286` |
| **Tightest wired hop: usb_pd→power** | **110.37/123.3 = 12.9mm margin** | double-declared by two contracts (both honest; dedupe is internal only) |
| power→power_som | 60.40/123.3 (≈62.9mm margin) | **ORCHESTRATOR BRIEF FIGURE "1.9mm of 122.2" IS STALE** — do not act on it |
| pd_input→usb_pd | 4.01mm | |
| near_max usb_pd↔pd_input | 0.00mm / ≤10 | via the edge-seat override being migrated in P3 |
| far power↔ethernet.line_side | 80.94mm / ≥10 | proves ethernet is a wired-term (far) target TODAY |
| facing power→power_som | 7.0° | |
| **motor_sense↔motor_pwm near_max** | **RED, >20mm** (advisory) | measured ~68.65mm edge-gap this session; doc `:759` records 132mm (centroid-era). **Rule: regenerate, assert only `>20 RED` / `≤20 GREEN`, never pin the value** |
| LAW-5 cross | 13,557.2/15,862mm → slack 2,304.8mm = 14.53% | |
| som_decoupling dispersion | 8.8 / 9.0 max | one jitter from red — protected below |
| Contract reds (unwired, red-proven) | ethernet 9 / hdmi_rx 3 / motor_sense 5 | mostly intra-zone; owned by wiring-wave templates, not poses |
| floorplan.json edges | N=[microsd,pd_input,usbc_otg,usb_jtag,usb_uart] E=[rj45_connector,board_qwiic,**motor_sense**] S=[hdmi_rx,hdmi_tx,pmod,pmod_expansion] W=[camera,lcd,**motor_pwm**] | D9 moves motor_sense E→W |
| `_WIRED_SHEETS` | `{power, usb_pd}` (`placement_contract_gate.py:84`) | |

**Global rule (stale-scalar law):** every phase re-measures at step 0; no test or acceptance criterion pins a raw scalar from this table — assertions are threshold-relative, and parity/exactness expectations are computed from the same-run model.

---

## 2. Architecture

```
                         ┌──────────────────────────────────────────────────────────┐
   carrier/floorplan.json│  USER INTENT (edges, order, side, near, PULL knob)       │ ← reviewed JSON diffs only
                         └──────────────┬───────────────────────────────────────────┘
                                        ▼
 build_plan ── seed pack (_pack_edges + anchor first-fit + Lloyd, UNTOUCHED)
                    │
                    ▼  tail of _attempt_pack (:1557–1573)
            LEGALIZE+COMPACT  (floorplan_compose.legalize_compact — wired terms only, L0 short-circuit)
                    │   difference graphs → Bellman–Ford → repair flips → weighted-median (BF-potential init)
                    │   → EXACT evaluator accept / cutting planes → write-back
                    ▼
 build_model (L4 with per-kind exemption; som_core_rect shared) ──► emit ──► HARD GATES (unchanged arbiters)
                    │
                    ▼
   ADVISORY LEDGER (measure_ledger: real gates + discover-injected contracts on the emitted model)
                    │  floors = repair TRIGGERS only
                    ▼
   `schgen compose` REPAIR DRIVER — proposes floorplan.json SpecEdits (pull / ratified edge moves),
   authoritative accept (full rebuild + all gates + full `schgen board`), lands as reviewed commits
```

**Division of labor:** the **legalizer** satisfies WIRED terms by construction within a fixed spec; the **driver** edits the SPEC when poses cannot (intent edits like D9, tuning pulls, pre-wave advisory repairs); the **ledger** is the single measurement instrument (D12 scalar time-series). Two evaluators, one truth: `evaluate_terms` (floorplan-frame, exact by the P5 exemption + GUARD, used inside the legalizer) and `measure_ledger` (emitted-model gate truth); the exactness test ties them permanently.

**Immovables (structurally outside every variable set):** edge blocks (`_pack_edges` `:739–843` stays sole author), connector seats/mating rotations/`EDGE_PAD_CLEAR`, floorplan.json edge lists/order (edits only via `--allow-intent` ratification; D9 is pre-ratified at doc `:426/:684/:758`), SoM+`_SOM_OCC_PAD` rect, corner keepouts, `som_j*`/mounting holes/som_decoupling (ADD-don't-relocate), mounting-hole-only sheets (e.g. `mechanical`, corner-forced at `placement.py:853–858` — fixed rects, never variables), all gate thresholds and contract bounds (imported, never redefined), `GRID=1.27`, rotation (stays in the `zone_extra_rot` channel; the only sanctioned pose-rotation path is `_rotate_zone_90`, P10-triggered as its own unit).

---

## 3. Modules and exact integration points

**NEW `schgen/generate/floorplan_compose.py`** (~600 lines)
- `build_term_index(sheets)` → `TermIndex{hard, soft}`; `Term{kind ∈ {flow_hop, near_max, far_min, facing, near_intent}, subject, target_raw, bound, basis, enforced}`. Discovery via `placement_contract_gate.discover_contract` (lazy import — CROSS_K precedent `floorplan.py:1084`) over **both** `subsystems/` and `carrier/subsystems/` (motor_sense, power_som, power_mon live under carrier/). `enforced` ⇔ declaring sheet ∈ `_WIRED_SHEETS`. `Term.target_raw` carries the **raw dotted string** (`"ethernet.line_side"`), resolved by the gate's own `split('.',1)[0]` coarsening (`placement_flow_gate.py:343`); reports echo the gate's violation text verbatim. `near_intent` terms come from floorplan.json `{"near": target}` entries without a contract near_max (hdmi_rx_term→hdmi_rx, uart_bridge→rj45_connector) — advisory, never gated. Unknown external term kinds RAISE (mirrors `:605–612`); `region_void` unsupported → loud error. Term ids always derived from live `discover/check_all` output, never a static list.
- `zone_local_metrics(zg)` → per-sheet (n_parts, equal-weight instance-centroid offset, pad-union bbox offset via `placement_contract_gate._pad_boxes` with `(conn_rot+zone_extra_rot)%360` and `side_of`, output-role centroid offset), replaying build_model's local transform **including the emit rounding chain**: `gz = _gridify(ORIGIN+z) − ORIGIN` at `GRID=1.27` (`constants.py:54`), ORIGIN offsets, `round(·,4)`.
- `evaluate_terms(...)` — the exact floorplan-frame evaluator; `@som` resolves to the **grown** `som_core_rect()` (shared helper).
- `legalize_compact(...)` — stages L0–L6 (§6 P6), argument-pure: takes `W, H, som rect, blocks, TermIndex, LocalMetrics` as parameters, **never reads `fp.BOARD_W/BOARD_H` globals** (the 2026-06-19 race class).
- `compose_report(model)` — HARD+SOFT term ledger table.
- All constants with basis strings (§4).

**NEW `schgen/generate/compose_repair.py`** — `SpecEdit` ops (`AddPull`, `SetPullWeight`, `MoveEdgeBlock`, composite move+pull), `measure_ledger(model, plan)`, `plan_replica_metrics(plan)` (ordering only), `repair(...)`, canonical-JSON spec writer, ledger writers (`carrier/reports/compose_ledger.json` + `.md`, driver-written only).

**CHANGED (all lazy-import across the generate↔verify boundary, per the emit.generate() house pattern):**
1. `schgen/generate/floorplan.py` — loader `:556–656`: interior keys become `{"side","near","pull"}` (rejection today at the `keys - {"side","near"}` check ≈ `:635–639` = the P3 red-on-before); pull schema + invariants (§6 P3); `FloorplanSpec` (`:512–530`) + `export_floorplan_spec` (`:659+`) round-trip; `Block.pull`; `_anchor` `:1464–1521` seat branch `:1492–1507` replaced by pull semantics; packing key `:1530–1534` keys on `pull.exclusive`; DELETE `_EDGE_SEAT_BLOCKS`/`_EDGE_SEAT_ZONE_W` (`:58–59`; grep-verified floorplan.py-only). `build_plan` computes TermIndex+LocalMetrics after the zg import at `:1066` and threads them into `_attempt_pack`'s four call sites (`:1156, :1199, :1235 (_passes), :1282`); `_attempt_pack` (`:1371`) gains two params + ~6 lines after the relaxation loop (`:1557–1573`): `if not legalize_compact(...): return False`; `Plan.composition` field; `render_md` (`:2147`) adds the term table. `build_plan` and the spec loader gain an **additive default-None `spec` parameter** (IM graft 1, preferred form) threaded through to `subsystem_zone_geometry`/`_declared_edges`/`_downstream_facing` (`pcb/placement.py:477–512` re-read the file) and `build_model`; default path byte-identical.
2. `schgen/verify/placement_flow_gate.py` — pure refactor: extract/publish `flow_budget(w,h,som_core)`, `bbox_gap`, `_zone_centroids`, `_zone_bboxes`, facing-dot; additive `FlowTerm`/`.terms` on the result; `summary()` text byte-identical (identity-tested).
3. `schgen/verify/placement_contract_gate.py` — thin pure helpers `discover_all()`, `wired_term_participants()` (per-KIND, §6 P5).
4. `schgen/generate/pcb/placement.py` — L4 exemption one-liner after `for sheet in sorted(zorigin):` at `:972` (lazy import of the participants helper); extract `som_core_rect()` from `:1104–1108`, used by build_model AND evaluator.
5. `schgen/generate/floorplan.py` `L4_PULL_CREDIT` (`:1145`, 0.97) — re-measured at P5 (safe direction only: estimate oversizes).
6. `schgen/verify/ratsnest_gate.py` — additive `dispersion_by_sheet` (~`:152`); summary unchanged.
7. `schgen/__main__.py` — write `carrier/reports/floorplan_composition.txt` next to the placement_flow block (`:1113–1130`); new `compose` subparser beside `floorplan` (~`:1421`): `--measure | --repair, --dry-run, --allow-intent NAME:FROM->TO, --max-steps N=4`.
8. `carrier/floorplan.json` — P3: usb_pd gains the pull entry (keeps `"near":"pd_input"`); P8: the D9 edge move.

**Manifest note (DLS graft):** `manifest.py:202–213` hashes `reports/*.txt`, so the new report churns `carrier/manifest.json` even on byte-identical-board phases. All byte-identity claims in this spec are scoped to `{.kicad_pcb, .kicad_sch, FLOORPLAN.svg, FLOORPLAN.md, all pre-existing reports}`; the one-line manifest delta is recorded in phase evidence.

**Tests:** `test_floorplan_compose.py`, `test_floorplan_pull.py`, `test_compose_repair.py`, extensions to `test_placement_flow_gate.py` (identity + terms mutation twin) and `test_pcb_gate_mutation.py`; pinned per-kind participants test; **new end-to-end build-twice hash test** (marked `board`/slow — not in the default 18.5s run, but MANDATORY in every phase's regression bar).

---

## 4. Constants (every threshold carries a basis string; none runtime-configurable)

| Constant | Value | Basis |
|---|---|---|
| `GUARD_MM` | 2.0 | measured max post-floorplan connector edge-snap travel = EDGE_INSET 1.5 + EDGE_PAD_CLEAR 0.4 ≤ 1.9; enforced by the exactness test; **may only grow** |
| `FAR_L4_GUARD_MM[sheet]` | measured (ethernet ≈ 14 today) | measured emitted-vs-floorplan centroid delta for far-only L4-kept participants; re-measured whenever the exactness test's printed residual drifts >1mm |
| `W_HOP` | 1.0 | judgment:1.0 — hop length is the contract objective; shorter buys gate margin |
| `W_SEED` | 0.05 | judgment:0.05 — one order below term cost so terms win; nonzero so uninvolved blocks keep LAW-5-shaped seats |
| `Q` | 0.5mm | matches `_CAND_STEP`; **quantize-then-CLAMP into the feasible window** (off-grid allowed, round-4) |
| `REPAIR_MAX / CUT_MAX / MEDIAN_PASSES` | 16 / 8 / 8 | judgment: bounded deterministic termination |
| `EPS_FACE / EPS_CUT` | 2.0mm / 0.5mm | judgment; exact dot re-checked at accept |
| BF sweeps | **V** (not V−1) | relaxation in sweep V flags infeasibility; predecessor-walk V times to land ON the cycle |
| Exactness tolerance | ≤1e-6 with the emit rounding chain replicated; else 5e-4 documented | CL graft 9 |
| Driver floors (triggers only, never pass/fail) | flow 10.0mm; near_max 2.0mm; far 5.0mm; facing 15°; cross 5% of budget; dispersion 0.5 | judgment: 2×OUTLINE_SNAP; 2×STEP; 5×STEP; half the 30° cone; 3% credit granularity + 2%; 2× per-wave jitter |
| Weighted-median tie-break | lower endpoint of the minimizing interval | determinism (shuffled-input test honest) |
| `AREA_TARGET_MM2` | 24,600 | judgment: pre-contract 154×152 = 23,408mm² + the recorded ~+5% wave-growth allowance (P10 trigger) |

---

## 5. Program laws (hold at every phase)

1. **LAW-4:** gates/bounds imported, never redefined/relaxed; legalizer infeasibility → reject → grow → RuntimeError; floors trigger repairs only; contract-bound edits require a new basis and review.
2. **Repair-before-wire (IM graft 4):** any term about to be enforced by a `_WIRED_SHEETS` flip must first measure GREEN on the advisory ledger; the wiring commit is blocked otherwise.
3. **Banded monotone acceptance** for every driver step and the P6 flip: all gates PASS on the rebuilt model; `A' ≤ A` (repair steps); target term GREEN; no term leaves GREEN; FRAGILE (below-floor) terms never lose margin; **non-target RED terms never lose margin (IM graft 3)**; per-sheet `check_all` counts no-worsen; confirmed by a full `schgen board` (DRC severity-error 0, hashes, renders) before any commit.
4. **Ratified-intent escalation (IM graft 5):** a `--allow-intent` edit failing ONLY `A' ≤ A` is reported with measured growth and deferred to the orchestrator's ~+5% wave judgment — never silently vetoed, never available to tuning edits.
5. **Determinism:** no RNG/wall-clock/env reads; sorted iteration everywhere; fixed caps; round-4 write-back; compose module argument-pure; driver strictly single-threaded (the `fp.BOARD_W/H` mutation at `:922–924` forbids parallel candidate evaluation); build-twice byte-equal + shuffled-dict tests.
6. **Renders are the final arbiter (LAW-1):** every board-changing commit ends in an orchestrator render verdict (FLOORPLAN.svg + top/bottom + ratsnest crops).
7. **Commit + push per verified unit.** Position-pinned fixtures are grep-enumerated before each board-changing phase and updated in-wave with rendered evidence — never silently skipped.

---

## 6. Phased build plan

**P0 — Baseline + sequencing gates (no code).** Verify clean tree; re-run `schgen board`; record the §1 scalar table + report hashes as the committed baseline; confirm status of **task #5 (usb_pd +4.1% growth render verdict)** — P5 and everything after is BLOCKED until it resolves. Verify: baseline ledger committed.

**P1 — Single-oracle metric kernels (pure refactor, byte-identical).** Gate publics + `som_core_rect()`; identity tests; land the end-to-end build-twice hash test (red-proves nothing — it is the determinism instrument every later phase cites; today only component-level determinism exists at `test_pcb.py:65`). Verify: full suite green; `placement_flow.txt` byte-identical; board hash unchanged. Commit+push.

**P2 — Terms + exact evaluator + advisory ledger (board byte-identical).** `floorplan_compose.py` (term index, local metrics, evaluate_terms, compose_report) + `measure_ledger` with the contracts-injection **None-filter** `{s: c for s in sheets if (c := discover_contract(s)) is not None}` (crash otherwise at `placement_flow_gate.py:296`; hermetic None test) + duplicate-hop **dedupe = keep-min-budget + OR-enforced** with hermetic test + additive `FlowTerm`s/`dispersion_by_sheet` + `__main__` report + informational **aggregate-margin scalar**.
Red-on-before: (a) exactness test RED without the grid-snap/rounding replication, GREEN with it — asserts ≤1e-6 for term-participating top-forced sheets (power, usb_pd), ≤GUARD_MM for edge-partner sheets; documents (prints) measured residuals for L4-mover participants (pd_input, power_som, ethernet — they become exact/guarded at P5); mutation twin (0.7mm perturbation → fail). (b) The committed ledger archives **near_max motor_sense↔motor_pwm REGENERATED-VALUE > 20 RED** — the D9 red evidence (assert threshold-relative only; resolves the 68.65 vs doc-:759 132mm conflict by never pinning). Verify: board + FLOORPLAN.svg/MD + all pre-existing reports byte-identical (manifest delta recorded); full suite. Commit+push.

**P3 — Pull-knob migration (byte-identical, atomic code+json commit).** Pull schema `{to: existing-block, weight>0, face: inboard|center, exclusive: bool, basis: non-empty}`; loader invariants: `exclusive` requires the entry's near/zone target `== pull.to` AND edge-resolvable (matching the `:1492–1493` trigger; named `FloorplanSpecError`, not a hash hunt); `inboard` only when `to` is on an edge list; **usb_pd KEEPS `"near":"pd_input"`** and gains `pull {to: pd_input, weight: 60.0, face: inboard, exclusive: true, basis: "D11 edge-seat override, migrated from _EDGE_SEAT_BLOCKS"}`; `_anchor` exclusive branch reproduces `:1492–1507` geometry verbatim (`zw=weight, sp=0.0`, inboard aim; the `else: keep centroid` arm survives); non-exclusive pull adds one weighted point to the accumulation; one pull per block. Delete `_EDGE_SEAT_BLOCKS`/`_EDGE_SEAT_ZONE_W`. Ledger gains the **seat-consistency advisory** (decision D-1). Red-on-before: `test_pull_parses` is RED today (loader rejects `pull` at the `:635–639` key check); typo/weight/inboard/basis rejection tests. Proof: `Zynq_Carrier.kicad_pcb` + FLOORPLAN.svg/MD hashes identical. Commit+push.

**P4 — Repair driver (no board change).** `compose_repair.py` + `schgen compose`. Spec-injection via the default-None parameter (P3/§3 item 1); candidates evaluated sequentially, single-threaded; F1 plan-rect replicas ORDER only (honest zone-shape-dependent error bound — several mm on big zones); F2 authoritative accept per §5 law 3; catalogs: `MoveEdgeBlock` (ratified only), `AddPull` ladder (2, 5, 10, 20, 40, 60), `SetPullWeight`, **composite move+one-pull evaluated atomically**; near_intent terms are repairable via the pull operators (DLS graft 7 absorbed). Hermetic red tests: each acceptance clause has a violating candidate that is REJECTED (band drop, area growth, RED-deepening, unratified intent); dedupe; determinism-twice; dry-run on the carrier proposes ZERO unratified edits and reports D9 as intent-gated. Commit+push.

--- **BARRIER: task #5 usb_pd growth render verdict must be resolved; waves never stack on an un-verdicted baseline.** ---

**P5 — L4 per-kind exemption + credit re-measure (first board-delta commit).** `wired_term_participants()`: subjects ∪ resolved targets of `_WIRED_SHEETS` external **flow/near_max/facing** terms are L4-EXEMPT (excluding `@som` and edge blocks); **far-only** participants KEEP L4 and get `FAR_L4_GUARD_MM` in the evaluator. Pinned test: exempt == `{pd_input, power_som}`, far-guarded == `{ethernet}` today. `placement.py:972` continue-line. Re-measure `L4_PULL_CREDIT` against the enumerated set (basis "judgment:measured"; may only move toward 1.0). Red-on-before: the P2 exactness assertions for pd_input/power_som fail at ≤1e-6 before this commit, pass after. Verify: all gates green; build-twice; area/cross delta reported; render verdict. Commit+push.

**P6 — Legalizer live (board-delta wave).** `legalize_compact` wired into `_attempt_pack` behind the L0 term-presence short-circuit (term-free projects byte-identical). Stages: L1 relation extraction (larger normalized seed gap; ties x-then-lex; CLEAR=0.3; fixed rects = edge blocks + SoM+pad + corner KOs + walls, `_Occupancy.fits` semantics verbatim); L2 wired near_max windows (dominant-axis gap ≤ bound−GUARD + perpendicular overlap ≥ 0) and facing half-planes (EPS_FACE); L3 Bellman–Ford **V sweeps** + predecessor-walk-V cycle naming → ≤REPAIR_MAX deterministic relation flips → else candidate REJECTED (outer grows); L4′ Gauss–Seidel weighted median **initialized from the BF shortest-path potentials** (a feasible point — never the possibly-infeasible seed), empty-window = deterministic clamp-to-nearest-bound, fixed tie-break, quantize-Q-then-CLAMP; L5 exact-evaluator accept over all hard terms (flow ≤ `flow_budget(W,H)` **recomputed per candidate**; far ≥ min + FAR_L4_GUARD where applicable; facing exact dot) with cutting planes ≤CUT_MAX — **facing cuts emit the exact linearized two-axis constraint, other axis frozen per round and recorded in the cut**; L6 write-back round-4, `plan.composition` stashed. Cost `C = Σ deduped wired hops W_HOP·L1 + Σ W_SEED·|Δseed|`; unwired terms contribute ZERO (inertness invariant preserved).
Red-on-before: (i) synthetic plan whose seed violates a wired near_max — gate FAILS on the seed-built model, PASSES post-legalize; (ii) **real-board red** via `contracts=` injection of power_som's flow/facing on the current board (instrument sees a movable defect); (iii) contradictory-windows test → named negative cycle → `_attempt_pack` False → existing RuntimeError; (iv) L4′-feasibility-from-red-seed unit. Timing: demonstrate **≤ +10s on `schgen board --timing`** with once-per-build TermIndex/LocalMetrics caching and cheap-first L0 BEFORE this commit.
Acceptance (measured): all gates PASS; banded no-worsen vs P5 baseline; **usb_pd→power margin ≥ 12.9mm and strictly improved, OR the compose report names the binding window**; usb_pd↔pd_input stays within bound−GUARD (=8mm) with any seat regression from 0.00 explicitly reported for the render verdict; **area ≤ 25,670mm²** (the legalizer must never grow the board; the outer scan may now find smaller — report the delta); build-twice; FLOORPLAN.svg/MD + manifests regenerated; render verdict. Commit+push.

**P7 — Wiring waves: ethernet → hdmi_rx → power_som (each its own commit; existing task #6, de-risked).** Per wave: step-0 re-measure; **repair-before-wire** (advisory ledger green first — driver repairs if needed; ethernet's exclusive pull lands as a reviewed spec diff, seat-consistency check goes green); flip `_WIRED_SHEETS`; legalizer enforces the new hard terms by construction (power_som flow power_mon→power_som + facing `@som` are the multi-axis cases the exact facing cuts exist for; hdmi_rx external is empty — composition-neutral, intra template only); per-kind participants set re-pinned and `L4_PULL_CREDIT` re-checked; exactness re-verified; red-on-before = the recorded `check_all` evidence (ethernet 9 / hdmi_rx 3) flipping green; gates + area (~+5% judgment) + render verdict. Commit+push per wave.

**P8 — D9 motor intent edit (ratified, own commit).** PRE-MEASURE: the four W-edge packed-zone spans + CLEAR gaps vs `BOARD_H − 2·EDGE_MARGIN` (≈131mm at H=151; motor_sense parts span ~79×32mm today — the packed zone is what counts). Execute via `schgen compose --repair --allow-intent motor_sense:E->W` → `edges.E = [rj45_connector, board_qwiic]`, `edges.W = [camera, lcd, motor_pwm, motor_sense]`. Acceptance: **`plan.spilled` containing motor_sense = FAIL** (the silent S-spill at `:774–778` is a failed criterion, not a render note); ledger flips the archived P2 RED → **regenerated gap ≤ 20mm GREEN with the engine untouched between the two ledger commits**; escalation clause applies if only `A'≤A` fails; gates + render verdict (cross-edge corner check judges the new SW adjacency). **Fallback if W-edge overflows:** land motor_sense's zone-shrinking intra template FIRST (template without the `_WIRED_SHEETS` flip — enforcement stays off), then retry the edit; or accept board-H growth explicitly in the wave verdict. Commit+push.

**P9 — motor_sense wiring wave (last; biggest blast radius per doc `:758`).** Repair-before-wire already satisfied by P8's green advisory line (both endpoints are legalizer-FIXED edge rects — zero solver DOF, which is why P8 must precede). Flip `_WIRED_SHEETS`; the flow gate now enforces the near_max; red-on-before = the recorded 5-violation `check_all` evidence + P2's archived advisory RED; gates + render verdict. Commit+push.

**P10 — Area verdict + documentation.** Record the full area trajectory in the ledger. **Trigger:** if board area > `AREA_TARGET_MM2` (24,600mm²), schedule the 90° whole-zone pose operator through the sanctioned `subsystem_zone_geometry`/`_rotate_zone_90` channel as its **own designed, red-proven unit** (explicitly outside this spec's implementation; its trigger, channel, and byte-identity obligations are pinned here). Append the T1 decision entry to `AI_LAYOUT_ROUTING_CONCEPT.md` (decisions only — anti-churn rule): composed architecture, constants, the exemption sets, the D9 flip evidence, the area verdict. Commit+push.

---

## 7. Acceptance criteria — the measured numbers this program must move

| # | Number | Baseline (live) | Requirement |
|---|---|---|---|
| A1 | **Flow margin, tightest wired hop (usb_pd→power)** | 12.9mm (110.37/123.3) | Never below 12.9mm at any accepted commit from P5 on; **strictly improved at P6** (or binding-window verdict in the ledger); driver floor 10.0mm triggers repair forever after. Stale-figure correction on record: power→power_som is 60.40/123.3, not 1.9/122.2. |
| A2 | **Motor gap (near_max motor_sense↔motor_pwm)** | RED, regenerated >20mm (≈68.65 edge-gap; doc records 132 centroid-era — never pinned) | Archived RED at P2 → **≤20mm GREEN at P8 with engine untouched** → gate-ENFORCED green at P9. `plan.spilled ∌ motor_sense`. |
| A3 | **Board area** | 25,670mm² (170×151) | Repair steps: `A' ≤ A` always. P6 flip: ≤ 25,670. Each wave: ≤ ~+5% orchestrator judgment. **End of P9 target: ≤ 24,600mm²**, else P10 schedules the rotation-operator unit. |
| A4 | usb_pd↔pd_input near_max | 0.00mm | Byte-identical 0.00 through P3–P4 (migration proof); ≤ bound−GUARD (8mm) hard window thereafter, seat regression explicitly reported. |
| A5 | LAW-5 cross | slack 2,304.8mm (14.53%) | `est_real ≤ CROSS_K·√(WH)·n_sub` on LEGALIZED poses at every candidate (hard); 5% slack floor triggers driver attention. |
| A6 | som_decoupling dispersion | 8.8/9.0 | Below-floor: zero margin loss permitted on any accepted step (operators never touch under-SoM parts). |
| A7 | Contract violation counts | ethernet 9 / hdmi_rx 3 / motor_sense 5 | No-worsen by any composition step; → 0 only at their own wiring waves (red-on-before evidence per wave). |
| A8 | Determinism | — | Build-twice byte-equal at every landed phase (new end-to-end test); shuffled-input equality for compose. |
| A9 | Gates + renders | all PASS today | Every existing hard gate PASS + LAW-1 render verdict at every landed commit; no new hard gate added. |

---

## 8. Risk register

| Risk | Mitigation |
|---|---|
| Evaluator-vs-emit residual (LEVER-L4 moves copper 10–37mm post-pose) | Per-kind L4 exemption (P5) + GUARD_MM for edge-snap + FAR_L4_GUARD for L4-kept far participants; exactness test with printed residual vector as loud alarm; emitted-board gates remain sole arbiter. |
| W-edge overflow on D9 → silent S-spill (`:774–778`) | P8 pre-measure vs ≈131mm cap; spill-as-FAIL; template-first fallback; explicit growth acceptance path. |
| Legalizer conservatism (axis decomposition + GUARD) inflates area | Exact-evaluator accept + cutting planes recover diagonal arrangements; ledger area line watched per wave against ~+5%. |
| Facing cut non-convergence (multi-axis `@som` case) | Exact two-axis linearized cuts with recorded freezes; CUT_MAX fail-loud; repeated facing cuts = signal the contract needs a finer `output_roles` region (reviewed contract edit with basis, never a weaker bound). |
| Runtime (up to 1,681 fine-scan calls × ≤25 BF solves) | Cheap-first L0; once-per-build TermIndex/LocalMetrics caches; +10s `--timing` bound demonstrated BEFORE the P6 commit; budgets re-based by reviewed constant change if exceeded. |
| Stale scalars (the brief itself carries two) | Step-0 re-measure law; threshold-relative assertions; same-run parity expectations. |
| `fp.BOARD_W/H` global race | Compose argument-pure; driver contractually single-threaded; no parallel candidate evaluation (comment in code). |
| Pull-knob creep | One pull per block; mandatory basis; driver proposes, humans review commits; weights are code constants. |
| Double-declared usb_pd→power hop | Dedupe internal only (min-budget + OR-enforced, tested); the gate's double report is two honest declarations — never "fixed". |
| Un-verdicted baseline stacking | Hard barrier before P5 on task #5's render verdict. |
| Manifest/golden churn | Byte-identity scoping (§3); grep-enumerated fixture updates in-wave with rendered evidence. |
| som_decoupling one jitter from LAW-5 red | A6 protection clause; no operator addresses under-SoM parts. |
| Cross-thread coupling with the ESCAPE wave (hdmi_rx bottom straps under J2 feed its via windows) | Escape builder derives live and fails loud by design; re-run the escape gate/build after any composition wave that re-places hdmi_rx (P7b) and record it in that wave's evidence. |
| iCloud eviction mid-build (recorded ENV hazard) | Calibration/timing builds run serially and attended; one driver step per invocation. |

---

## 9. Graft traceability (every surviving amendment, where it landed)

**Incremental-migration grafts:** IM1 spec-injection param → §3.1/P4 · IM2 None-filter → P2 · IM3 RED no-worsen → §5.3 · IM4 repair-before-wire → §5.2/P7/P9 · IM5 intent escalation → §5.4/P8 · IM6 exclusive-pull loader invariant + usb_pd keeps near → P3 · IM7 dedupe semantics → P2 · IM8 composite candidates → P4 · IM9 honest replica bound → P4 · IM10 aggregate-margin scalar → P2/P4 · IM11 (judge) term ids from check_all → §3 floorplan_compose · IM12 (judge) F6 rotation trigger → P10/A3.

**Constraint-legalizer grafts:** CL1 per-kind participants + credit re-measure → P5 · CL2 BF-potential init + clamp + feasibility unit → P6 · CL3 exact two-axis facing cuts → P6 · CL4 quantize-then-clamp → §4/P6 · CL5 raw dotted targets + verbatim gate strings → P2 · CL6 regenerate-don't-pin (68.65/132; 1.9mm stale) → §1/§5/A2 · CL7 W-edge pre-measure + spill-as-FAIL + soft-green-before-hard → P8/P9 · CL8 seat-derivation scoped to interior `@`-anchored subjects → D-1/P3 · CL9 rounding-chain exactness + median tie-break → §4/P2 · CL10 V-sweep BF + demonstrated timing → §4/P6. Implementability note (both-directory contract discovery) → §3.

**Deterministic-local-search surviving amendments (engine not built):** emit-faithful evaluation → D-2/P5 · guard bands + wired-slack pressure + grown som_core → GUARD/W_HOP/`som_core_rect` · shrink strictness + rebind pattern → D-3 (per-candidate budget recompute; no grandfather; global rebind stays in `_passes`) · mechanical-sheet exclusion → §2 immovables · same-run expectations, build-twice test, manifest scoping, "strictly-improved-or-verdict" wording, movable-term real-board red → §5/P1/P2/§3/P6 · budgets from measurement → P6 timing · near_intent scoring → P2 terms + P4 operators.

---

## 10. Out of scope (owned elsewhere, referenced for sequencing only)

- **ESCAPE thread** (J2/J1 DF40 return stitching, escape lanes, return_stitch gate): separate spec/thread; composition owes it only the P7b re-verification hook (risk table).
- `return_path_gate`'s 29-contact red: SoM-pinout-fixed, module-level truth — never touched here.
- `_rotate_zone_90` operator implementation: designed as its own red-proven unit if and only if the P10 trigger fires.
- Contract-bound or gate-threshold changes of any kind.