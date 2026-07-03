# AI-in-the-Loop Layout & Routing — Concept & Implementation Design

> **Status:** Living design document. Concept phase — no system built yet.
> **Goal:** get an AI to place *and route* this board (Zynq SoM carrier) with best
> practices implemented well, and structure that concept so it can actually be built.
>
> **Anti-churn rule for this doc:** every entry must (a) resolve a belief, (b) spec a
> buildable piece, or (c) record a decision. If an edit only re-declares a new "center
> of gravity," it is churn — delete it. (This rule exists because the thinking that
> produced this doc kept re-centering every pass; the doc is the cure.)

---

## 1. First principles (durable — these held across every pass)

1. **The model cannot hold whole-board spatial state in its head.** Durable working
   memory must be *exact structured state* (JSON: per-part pose, per-net length, per-gate
   scalar), returned every step. The **render is a rationed sensor** for gestalt the
   numbers can't express — not the memory.
2. **Electrical integrity is a global invariant.** A connected-components short/open
   check over emitted geometry runs on *every* mutating step, symbolically — never
   delegated to the eye. This is what makes local views / crops safe.
3. **The model is the art director; the engine is the pixel-pusher.** The model issues
   *coarse* redirects; the deterministic engine does the thousands of micro-placements
   it is competent at and the model is bad at.
4. **Best practices are rules over netlist + placement + copper.** Encode each as a
   strict gate, or it will not survive iteration. A "best practice" that isn't a gate is
   a wish.

---

## 2. What exists today (grounded in the code, not the memory)

- **Placement is a deterministic feed-forward pipeline**, not an optimizer:
  `subsystem_zone_geometry()` shelf-packs each subsystem into a local-frame **zone
  (already a "block")** → `floorplan.build_plan()` positions the blocks (edge pins from
  `floorplan.json`; interior blocks dropped at a one-shot affinity centroid) → two
  hand-coded levers patch quality (**L1** rotate tall zones to the SoM band; **L4**
  greedy bottom-passive pull toward the SoM).
- **Board size is a dependent variable.** The floorplan *grows* the outline until a
  *fixed* arrangement fits and meets the airwire budget. Nothing searches block
  positions against the objective.
- **~20 strict gates.** The placement objective is a **proxy**: `ratsnest_gate`'s
  cross-subsystem airwire budget `cross_mm ≤ CROSS_K·√area·n_sub`, plus dispersion and
  off-board checks. Deterministic PIL raster (`ratsnest.py`, SCALE=4 px/mm) is the
  single source of truth shared by PNG, SVG, and the scalars.
- **There is no router.** The pipeline stops at placement + ratsnest. **The real
  objective — does it route, at what layer count, with good return paths — has never
  been measured.**
- **Grounded board facts (from the netlist/footprints):**
  - 3 × `DF40C-100` mezzanine connectors @ 0.4 mm pitch, dual-row = **300 contacts**,
    each body 19.6 × 7.2 mm, clustered at board centre.
  - Contact split: **~215 signal (72%) / 63 ground (21%) / 19 power (6%)**.
  - **48 differential-pair nets** (~20 distinct physical HS interfaces: HDMI-TX/RX
    TMDS, GbE MDI, MIPI CSI, USB, FMC clocks/LA).
  - **4-layer** stack (`_FOUR_LAYER`). ~592 nets total.
  - SoM pinout is **fixed by the module**; the carrier is a pass-through and cannot
    re-assign contacts.

---

## 3. Corrected problem framing (the beliefs resolved so far)

- **B1 — There is no real objective in the system.** Everything optimised to date
  (airwire, board area) is a proxy that has never been checked against routability.
  *This is the root cause of the circling.*
- **B2 — The binding constraint is mezzanine escape, not global placement.** Escape
  feasibility = (signals to escape) ÷ (SoM-perimeter × signal-layers × lanes/pitch).
  Every term lives *under the SoM*; board area outside it does not appear. 215 signals,
  72% signal fraction, 0.4 mm dual-row on 2 signal layers → the classic case that
  pushes layer count / via technology up, and it is **geometrically orthogonal to the
  airwire proxy.**
- **B3 — Best-practice defects are invisible to the proxy.** With only 21% ground,
  many HS pairs lack an adjacent ground return through the DF40 — a real SI risk that no
  placement metric or board-shrink can see or fix.
- ~~**Decision D1 (provisional): 6-layer HDI, via-in-pad.**~~ **SUPERSEDED — see
  Addendum B4.** The "trapped inner row needs via-in-pad" reasoning was BGA-thinking
  misapplied to a two-row connector (both DF40 rows escape on the surface). Stackup is
  **open**; P0 measures it, routing at 4 layers first. B2's core survives (escape
  congestion ≠ airwire proxy) but its layer-count implication is unproven.

---

## 4. Target architecture (the 5-layer loop, made concrete)

| Layer | Concrete component | State today |
|---|---|---|
| **Intent** | `floorplan.json` + a stackup spec + a critical-net list | floorplan exists; stackup/critical-net list new |
| **Actuation** | Stateful, single-writer/transactional **board service**: `state() / move() / lock() / render(scope,overlay) / route() / run_drc()`; committed **action-log = the deterministic build artifact** | not built |
| **Engine** | (a) existing packer = intra-block; (b) block-pose composition; (c) **Freerouting** = copper; (d) **escape-block designer** = the mezzanine fanout | (a) exists; (b),(c),(d) new |
| **Verification** | existing gates + the **best-practice gate suite** (§5); LAW-0 floor every step | ~20 gates exist; best-practice gates new |
| **Perception** | gate findings drawn as **overlays** on the deterministic raster; JSON state as memory; render rationed | raster exists; overlay/sidecar new |

Reuse note: the board service must be transactional so `render == pure(committed state)`
(the repo already hit a `BOARD_W/BOARD_H` data race — a model-driven loop makes this
mandatory), and the action-log keeps a stochastic-trajectory board regression-testable.

---

## 5. The real objective, made measurable (the near-term core)

Two pieces. Half of this needs **no router** and is buildable now.

### 5a. Router integration — the "route-once" harness (the master measurement)
- **Export DSN** from the emitted board: net classes exist (`_net_classes`), clearances
  exist (`design_rules.py`); add a **stackup** definition and the exporter.
- **Run stock Freerouting** headless → read **completion %, layer usage, DRC**.
- **Pre-committed "acceptable" bar** (decide before routing, or the result is another
  proxy):
  - *Hard (feasibility):* 100% completion; ≤ target layers; DRC-clean at manufacturable
    rules; **reference-plane continuity on every HS net**.
  - *Soft (quality):* via count, diff-pair length-match, layer changes on critical nets.
- **Known refinement** if Freerouting chokes on the mezzanine (it isn't BGA-escape
  smart): hand-guide + **lock** the escape, autoroute the rest ("critical nets first,
  lock, then autoroute").

### 5b. Best-practice gate suite
Netlist/placement-time (no router) — **buildable today**, same shape as existing gates:

| # | Gate | Data source | Fails on |
|---|---|---|---|
| 1 | Decoupling completeness & proximity | netlist (`_decoupling_caps`) + placed XY | missing rail bypass; cap > ~2 mm from its pin |
| 2 | Diff-pair integrity & DF40 contact adjacency | `som_interface.json` pin map | `_P` w/o `_N`; pair on non-adjacent contacts |
| 3 | **Pair return-path budget** | contact→class map | HS pair with no ground contact within *k* — *catches B3* |
| 4 | Termination / pull presence | net-role rules | TMDS/RGMII w/o series R; I²C/reset w/o pull |
| 5 | Power-delivery contact adequacy | `powertree` + contact count | rail current vs its DF40 contact count under-provisioned |

Post-route (needs copper, gated on 5a): 6 reference continuity · 7 length match ·
8 via/layer budget · 9 thermal vias under power pads.

---

## 6. The unit of placement: blocks, and the portable escape block

- **Blocks already half-exist** (`subsystem_zone_geometry` = frozen local-frame zones).
  Composition = choosing block **poses**. A block's **ports** = the nets crossing its
  boundary (direction-agnostic — some rails are SoM-sourced *into* a block).
- **The escape block (the key new object).** Because the SoM pinout is fixed, the
  under-SoM fanout — microvia positions, layer assignment, breakout ordering, and the
  **ground-via placement that fixes B3** — is a **design-once, carrier-independent,
  portable artifact.** It mirrors the portable-subsystem invariant exactly:
  - It is where the hardest routing on the board lives (inner-row 0.4 mm escape).
  - Its perimeter *is* the real, concrete home of the "ports" abstraction.
  - It converts the mezzanine from "re-solved per carrier" into "solved once, inherited."

---

## 7. Where the AI actually adds value (right-sized)

- **Not** global block choreography — the engine does that; the airwire proxy the model
  would optimise is orthogonal to the real (escape) bottleneck.
- **Yes:**
  1. **Author/maintain the best-practice gates** (§5b) — the first-turn ask, made real.
  2. **Design the escape block once** — ~100 contacts is a *bounded, holdable* spatial
     problem: the perceive→act→verify loop is *right-sized* here (where it fails at
     whole-board scale), and it's high-value + reused. This is the correct pilot of the
     whole AI-in-the-loop idea.
  3. **Review routed output against the gates** — turn "it routed" into "it routed well."
  4. **Coarse art-director redirects** — only where the *real objective* (a routing
     attempt) shows a genuinely placement-driven failure.

---

## 8. Phased, decision-gated roadmap (the anti-circling spine)

Each phase resolves a belief and gates the next; do the cheapest thing that gates the
most. **The AI placement machine is the last leaf, reached only if earlier phases prove
it's needed.**

- **P0 — Measure the real objective.** Route the current board once, generous layers.
  Fork: *routes clean* → placement-optimisation program is unnecessary; *fails locally
  (mezzanine)* → escape-block + stackup; *fails globally* → placement-bound.
- **P1 — Best-practice gates 1–5.** Independent of P0. Immediate value; catches real
  defects (B3) today. **Highest value-per-effort; start here regardless.**
- **P2 — Stackup decision.** From P0, commit 4 / 6 / HDI (D1 says 6-layer HDI).
- **P3 — Portable escape block.** Design the fanout once — the AI-loop pilot at the
  right scale; also fixes B3 in copper, once.
- **P4 — Best-practice gates 6–9.** Once copper exists.
- **P5 — Block-pose search / AI art director.** ONLY if P0 proves global placement-bound
  AND a deterministic optimiser leaves reachable slack AND an AI beats it. The
  pixels-vs-JSON ablation lives here, scoped to blocks/escape (~tens of entities).

---

## 9. Open experiments (each converts a belief to a fact)

- **Route-once (P0)** — the master fork.
- **Escape feasibility 4-layer THT vs HDI** — mostly answered by the contact math;
  confirm with one fanout sketch under a DF40.
- **Lower-bound on escape-boundary congestion** — is there any placement slack, or is it
  constraint-bound? A relaxation calc, not an engine.
- **Pixels-vs-JSON ablation** — scoped to the escape block (~100 entities), the one place
  the answer matters and is cheap.
- **Frozen-intra area cost vs flat solve** — the block thesis's linchpin; measurable on
  today's board.

---

## 10. Decision log

- **D1 (REVISED — see Addendum):** stackup is **open**; P0 decides. The original
  "6-layer HDI mandatory" rationale was wrong (BGA-thinking applied to a two-row
  connector — both DF40 rows are edge-escapable on the surface, no per-pin via needed).
  P0 protocol flips: **route at 4 layers first**, escalate only on measured failure.
- **D2:** Start with P1 (netlist-time best-practice gates) + P0 (route-once) in parallel
  — the two cheapest things that gate the most, and neither needs the AI machine.

---

## Appendix A — P1 gate specs (implementation-ready, still no router)

These follow the existing gate shape (`schgen/verify/*.py`, deterministic, strict,
returning a scalar-bearing result; mutation-tested via `test_pcb_gate_mutation.py`).

### A.3 Return-path budget gate — the flagship (`verify/return_path_gate.py`)
*The single highest-value near-term piece: ~one module, catches B3, needs only the netlist.*
- **Inputs:** `som_interface.json` (contact→net for J1/J2/J3); the DF40 footprint pad
  geometry (contact→physical (row, index)); the net-class map (which nets are the 48 HS
  pairs).
- **Build:** a per-connector ordered contact list with (row, along-row index) so
  "physical neighbours" is well-defined (same-row ±1, and the facing contact in the other
  row).
- **Algorithm:** for every HS-pair contact, scan its physical neighbourhood out to radius
  `k` (default **k = 2** contacts) for a `GND` contact; record the nearest-ground distance.
- **Pass/fail:** FAIL if any HS pair has a member with no ground within `k`. Report the
  worst distance and the count of failing pairs as scalars (so regressions show as numbers).
- **Consumer:** primarily **P3** (the escape-block ground-via strategy) and the
  stackup/SoM conversation — it flags a defect the carrier can only fix in the fanout.

### A.2 Diff-pair integrity & adjacency (`verify/diffpair_gate.py`)
- Every `_P` has a matching `_N` (start from the 48), same net class, both landing on the
  DF40. **Adjacency:** P and N on physically adjacent contacts (shares A.3's geometry map).
- FAIL on: unmatched pair member; mismatched class; pair split across non-adjacent contacts
  (kills coupling before it even escapes).

### A.1 Decoupling proximity (extends existing `_decoupling_caps`)
- `_decoupling_caps()` → cap→rail. For each cap, distance from its **placed** position
  (`build_model` output) to the nearest pin of the IC it bypasses on that rail.
- FAIL on: missing rail bypass; cap farther than a per-package threshold (~2 mm), or on the
  wrong side vs its pin.

### A.4 Termination / pull presence (`verify/termination_gate.py`)
- Rule table by net role: TMDS / RGMII-clk expect a series R in-path; I²C SCL/SDA expect a
  pull-up to their rail; reset / config-strap nets expect a pull. Check the netlist for the
  expected passive on the net. FAIL on absence.

### A.5 Power-delivery contact adequacy (`verify/power_contacts_gate.py`)
- `powertree` → per-rail current estimate. Count DF40 contacts assigned to each rail
  (from `som_interface.json`). FAIL if `rail_current / (n_contacts × per_contact_ampacity)`
  exceeds 1 (0.4 mm DF40 contact ≈ 0.3–0.5 A each).

## Appendix B — Route-once harness spec (P0)

- **Emit** the board (`schgen board`) → `kicad_pcb`.
- **Export DSN (Specctra):** net classes (`_net_classes`) + clearance rules
  (`design_rules.py`) + **a stackup definition** (new: layer count + which layers are
  signal vs plane) + the existing SoM keepout → `.dsn`.
- **Route:** stock **Freerouting** headless (`.dsn → .ses`).
- **Import `.ses`** back; run **kicad-cli DRC**.
- **Read:** completion (unrouted count → %), via count, layers used, DRC violations.
- **Protocol (revised per Addendum):** route at **4 layers first** — the dual-row DF40
  escapes on the surface, so 4-layer is genuinely on the table; escalate to 6 only on
  measured failure. If the mezzanine region defeats the autorouter, **generate + lock**
  the escape routes (they are formulaic geometry) and re-run for the remainder.
- **Verdict** against the §5a pre-committed bar → routes the P0 fork in §8.

## Appendix C — Portable escape block (P3, the AI-loop pilot)

*The novel keystone: the hardest routing on the board, turned into a design-once artifact.*

- **What it is:** a locked, portable sub-layout occupying the shadow of one DF40 — the
  **microvia-in-pad fanout pattern**, the outer-row-on-top / inner-row-to-inner-layer
  assignment, the breakout ordering, and the **ground-via placement that satisfies the
  A.3 return-path gate** for every HS pair.
- **Representation:** a new subsystem-like package, **content-hash keyed on the SoM
  pinout** (`som_interface.json`), cached. Its output is a *fixed relative* set of
  vias + short trace stubs + a set of **port endpoints at its perimeter**:
  `net → (x, y, layer)`. Portable: identical on every carrier for this SoM; regenerate
  only if the module changes.
- **Interface = ports:** the rest of the board routes to these ~200 perimeter ports, not
  to the 300 buried 0.4 mm contacts. This is where the "ports" abstraction is *real*.
- **Why it's the right AI-loop pilot:** ~100 contacts per connector is a **bounded,
  holdable** spatial problem — the scale at which perceive→act→verify (render as sensor,
  LAW-0 floor every step, gate findings as overlays) *works*, where it drowns at
  whole-board scale. High value, reused across carriers, and its success is *measurable*
  (A.3 passes + the router completes the escape region).
- **Verification:** A.3 return-path gate over the escape; a local DRC; Freerouting
  completing the escape region in isolation (a scoped version of P0).
- **Dependency:** needs the stackup (D1/P2) fixed first — the layer assignment is a
  function of the stack.

## Appendix D — Board service interface sketch (Actuation, for P5)

*Deferred behind P0's fork, but recorded so the target is concrete.*

- `state()` → the ledger + latest observation (JSON; never a pile of images).
- `move(block, region) / rotate / mirror / reseat_at_edge / lock(net) / relieve(region)`
  → returns the pre+post geometry union (so perception can crop the delta).
- `render(scope, overlay)` → one transient image + machine-extracted observation +
  an appended scalar-ledger row + a coordinate **sidecar** (id + board-mm + image-px +
  gate + severity per mark; the model points by id, never transcribes a coordinate).
- `route() / run_drc()` → the real-objective verbs (§5a).
- **Invariants:** single-writer / transactional (`render == pure(committed state)`); the
  committed **action-log is the deterministic build artifact** (board = seed floorplan +
  replay), keeping a model-driven board regression-testable.



---

## Addendum (2026-07-02) — full-thread review: one correction, one reframe

### Correction (resolves a belief with the doc's own discipline)
- **B4 — The "trapped inner row → HDI mandatory" escape analysis was WRONG.** The DF40
  is a **two-row** connector: both rows are edge rows, each fans outward on the surface;
  no per-pin via is required for escape. The real 4-vs-6-layer question is aggregate
  post-escape crossing density (three 100-pin fields converging across the board), which
  armchair arithmetic cannot settle — **only P0 can**. D1 accordingly revised; P0 routes
  at 4 layers first. *Meta-lesson: this confident claim was itself unverified proxy
  reasoning — the exact failure mode this doc diagnoses. Adversarial re-verification of
  analytical claims (the audit-reverify discipline) belongs IN the tooling (Tool 4 below),
  not in good intentions.*

### The authorship principle (added to first principles)
5. **The AI is an author and critic, never an operator. There is no manual mode — only
   authoring at different granularities.** Every success in this repo (27 render-clean
   sheets, byte-identical builds, the gate suite) came from: AI writes deterministic
   machinery → build → rendered evidence → AI improves the machinery. The founding
   anecdote re-read: the render didn't teach the model to place — it let the model
   **debug its placement program**. Pixels closed the loop on code, not on moves.
   Consequences: `floorplan.json` = authored judgment at block granularity; a routing
   strategy file = net-class granularity; a locked escape generator = fanout granularity.
   The Appendix-D board service is reframed as the API the *generator and critique
   tooling* consume — not a console for hand-nudging. Per-move perception is dead;
   **per-build perception** (evidence bundle) is the living version of the whole
   perception thread.

### The tooling stack (the "best tooling" answer — routing gets the netlist treatment)
schgen's proven formula — source → compiler → strict gates → rendered evidence → AI
critiques the source — extended down the stack:

1. **Routing-intent source** (`routing.json`): per net-class layers/impedance/matching/
   reference-plane/escape-pattern + per-net exceptions. Judgment as data.
2. **Routing compiler:** formulaic critical routes (escape fans, pair breakouts)
   **generated + locked**; Freerouting fills the rest under compiled constraints.
3. **Real objective in CI:** the P0 harness run on every change — completion %, via
   count, DRC deltas as regression numbers. Kills the proxy-objective failure class.
4. **Best-practices pipeline:** AI mines datasheet/IPC/app-note → proposes gate +
   parameters + **citation** → adversarial re-verify → mutation-tested gate lands.
   Practice count becomes a monotonic function of research effort.
5. **Evidence bundle (per BUILD, not per move):** renders + per-layer copper + gate
   overlays with coordinate sidecar + **scalar time-series ledger across builds** (the
   anti-circling instrument — trends become undeniable).
6. **Critique protocol:** structured bundle read → worst-issue-first → hypothesis →
   proposed change **to source, never to a part position**.

**Build order:** 3 + the five P1 gates first (independent; each kills a blindness class),
then 1+2 for critical nets, 5 alongside, 6 emerges from use. The pixels-vs-JSON ablation
shrinks to a non-load-bearing tuning question: "which bundle composition makes critique
most accurate."

### Decisions D3–D5 (2026-07-02, user-ratified)
- **D3 — Mission: tooling-first.** The carrier is the proving ground; the board ships as
  a byproduct of the methodology.
- **D4 — Routing philosophy: hybrid.** Critical/formulaic routes (escape fans, pair
  breakouts) generated + locked as code; Freerouting fills the rest under compiled
  constraints; gates judge everything.
- **D5 — Exit concept phase: build P0 + P1 in parallel**, under the orchestrator/worker
  model: Fable 5 authors specs + acceptance criteria and reviews/verifies every diff;
  cheaper workers (Opus 4.8 implementation, Haiku recon) execute pieces whose acceptance
  is mechanically checkable BEFORE work starts. Judgment is never delegated.

---

## Phase L — Layout-first redirect (2026-07-02, user-directed)

**User decree:** no routing focus until layout + fanout are right. One thing at a time.
Routing artifacts parked (baseline run may finish; it is NOT interpreted). Connector/edge
organization is satisfactory and stays.

### The measured defect (autopsy of the current packer)
The intra-zone shelf-packer sorts by footprint size class → parts land next to
similarly-SIZED parts, not their electrical partners. Measured in the emitted zones:
- `power`: both bucks' inductors packed side-by-side away from their ICs (hot loop
  smeared 7.6–15 mm); input bulk caps ~18 mm from ICs; ALL FB resistors in a uniform
  bottom-side grid under the switch-node region. The most layout-critical structure on
  the board is the most scrambled.
- `ethernet`: MDI termination in a bottom-side grid; magnetics top — via transitions in
  the line-side path.
- `usb_pd`: every FUSB302 decoupling cap on the opposite side from the IC.
Root cause: the PCB packer has NO concept of circuit. The schematic engine (place.py)
already solved topology-driven layout ("REGULATOR STAGES ... recognised from part roles,
stacked as datasheet stage rows — detected, not scripted") — the idea was never carried
to the PCB side.

### The concept: PLACEMENT CONTRACTS (per-subsystem, portable, datasheet-grounded)
Each subsystem package carries a placement contract, like its netlist/README/SPICE/tests
— because the electrical truths (hot loop tightness, isolation moats) are properties of
the SUBSYSTEM, portable across carriers.

Contract levels:
- **Internal** (drives intra-zone layout): netlist-derived ROLES (buck pattern: IC-with-
  SW-pin → L → Vout; Cin across VIN/PGND; FB divider — same derivation style as
  `_decoupling_caps`); CRITICAL STRUCTURES with electrical objectives (hot_loop
  max-perimeter + same-side, sw_node min-area + FB keepout, per-pin decoupling distance,
  line-side moat, thermal spreading); engine places critical structures FIRST as rigid
  clusters, shelf-packs only the leftovers (LEDs, TPs, straps).
- **External** (drives composition): typed adjacency — FLOW (pd_input→usb_pd→power→
  power_som→SoM as a chain), NEAR, FAR (bucks vs magnetics line side), SPREAD (thermal),
  MOAT; port-bank facing. floorplan.json keeps USER intent (edges, ergonomics);
  contracts supply the ELECTRICAL constraints satisfied within it.
- **Every contract term becomes a placement GATE** (hot-loop area, FB-SW separation,
  decoupling distance, moat, adjacency) — strict, mutation-tested, citation-backed
  (LAW 7). P1 gate energy redirects here. Fanout templates (DF40 escape block, buck
  thermal vias, QFN stitching) are contract items built AFTER placement settles;
  routing last.

### Decisions D6–D9 (user-ratified)
- **D6 — Scope: critical-first.** Deep contracts for ~6: power, power_som, usb_pd,
  ethernet(+rj45), hdmi_rx, motor_sense. Lightweight contracts for the rest later.
- **D7 — Mechanical: no enclosure yet.** Bench board; electrical best practice drives
  thermal/side choices; no enclosure constraints encoded.
- **D8 — Pilot: `power` (2× LM61460).** Worst measured offender; datasheet has an
  explicit layout section to ground every number; end-to-end loop = research → contract
  → engine consumes → gate enforces → render review.
- **D9 — Motor: CLUSTER.** motor_sense moves next to motor_pwm (one motor corner: PWM,
  current sense, future XT60 ESC inlet; short heavy paths, single star-ground point).
  Floorplan edge lists change accordingly at implementation time.

### Pilot done-bar (power)
Re-rendered power zone reads as two datasheet-style buck stages (IC+Cin+L+Cout tight,
same side; FB beside its IC, away from SW); placement gates for hot_loop/fb/decoupling
green with citation-backed thresholds; ratsnest/render reviewed (LAW 1); no silent
regression in other zones (gates + render, since zone resize forbids byte-identity).

### Pilot contract v0 — `power` (2× LM61460) — DRAFT FOR USER REVIEW

**Verification status (orchestrator-checked):** research fact sheet (SNVSBD5D Rev. D)
pin-map matches the repo dossier EXACTLY (14/14 pins). BOM verified complete: every
TI-required part already exists in subsystems/power (C1/C25 100nF X7R 50V flanking caps,
C2/C3 10µF bulk, C24 VCC 1µF, R11+C28 BIAS tie, BOOT_5V0 = RBOOT-shorted CBOOT, RT 22k).
**Smoking gun:** power.py:226 — "the placer/PCB fans one [100nF] to each VIN pad; the
split is a layout/footprint property" — the requirement was authored as a PROSE COMMENT
the placer cannot read. The contract is the mechanism that comment assumed existed.

**Structures (per buck stage; citations = SNVSBD5D unless marked JUDGMENT):**
| Structure | Members | Rule | Basis |
|---|---|---|---|
| hot_loop_1 | Cin_HF1 ↔ VIN1(8)/PGND1(9) | cap immediately adjacent, same side as IC; pad-to-pin ≤ 1.5 mm | §9.2.2.5, §11.1 Fig 11-1; distance = JUDGMENT |
| hot_loop_2 | Cin_HF2 ↔ VIN2(12)/PGND2(11) | symmetric mirror of hot_loop_1 | §9.2.2.5, §11.1 |
| bulk_in | C_bulk ×2 | same side, behind HF caps, ≤ 5 mm | §9.2.2.5; distance = JUDGMENT |
| sw_node | SW(10) → L | L adjacent to SW; SW copper minimal | §11.1, Fig 11-2; L-pin ≤ 3 mm = JUDGMENT |
| fb_cluster | RFBT/RFBB/CFF → FB(4), AGND(3) | ≤ 3 mm of FB; ≥ 3 mm from sw_node/L | §11.1; distances = JUDGMENT |
| boot | CBOOT 100n → pins 13/14 | ≤ 2 mm | §9.2.2.6, §11.1; distance = JUDGMENT |
| vcc_cap | C 1µ → VCC(2)/AGND(3) | at pins, short+wide | §9.2.2.8, §11.1 |
| bias_cap | R+C → BIAS(1) | close to pin 1 | §9.2.2.9 |
| same_side | ALL structures above | TOP with the IC — **overrides the 2-side small-passive policy for contract members** | §11.1 (loop area), Fig 11-2 |
| thermal | pours + stitch vias near VIN/GND pins | fanout-phase item; 2 oz outer copper note → fab spec | §11.1.1; via count = JUDGMENT (pull SLUA271/EVM guide) |
| stage_zone | one full stage | ~15–20 × 12–18 mm target | JUDGMENT (Fig 11-2 has no scale; refine from LM61460EVM guide) |

**External terms:** FLOW pd_input→usb_pd→power→power_som; FAR from ethernet line side /
hdmi_rx analog (≥ ~10 mm, JUDGMENT); two-converter spacing = JUDGMENT (datasheet silent).

**Schema sketch (what the package will carry):**
```json
{ "contract": "placement/v0", "citations": ["SNVSBD5D Rev D"],
  "roles": {"U1": "buck_ic", "C1": "cin_hf@VIN1", "C25": "cin_hf@VIN2",
             "C2": "cin_bulk", "C3": "cin_bulk", "L1": "sw_inductor", "...": "..."},
  "structures": [
    {"type": "hot_loop", "ic": "U1", "cap": "C1", "pins": ["8","9"],
     "max_pad_to_pin_mm": 1.5, "same_side": true, "basis": "SNVSBD5D 9.2.2.5|judgment:1.5"}
  ],
  "external": {"flow": ["usb_pd", "power_som"], "far": [{"what": "ethernet.line_side", "min_mm": 10}]}}
```
Roles for the pilot are DECLARED (they're already documented per-part in the netlist
comments); netlist DERIVATION of roles becomes the generalization step for the other
five critical subsystems.

**Gates that fall out (placement-time, no copper):** hot-loop proximity+same-side;
bulk proximity; fb-to-FB distance + fb-to-SW separation; boot/vcc/bias proximity;
stage-zone fit; FLOW/FAR adjacency at composition level. Every threshold carries its
basis string (citation or "judgment:<value>") — auditable, LAW-4 strict.

**Open refinements:** pull LM61460EVM user's guide for a CITED stage size + via counts;
decide two-converter spacing; fab-spec note (2 oz outer vs current stackup default).

### Pilot contract v1 — self-review amendments (orchestrator adversarial pass)

User delegated concept correctness/quality to the orchestrator; v0 reviewed adversarially.
Defects found and fixed:
1. **Coverage**: v0 contracted 2 of 3 stages — added `ldo_stage` (the +1V8 LDO: Cin/Cout
   at pins, thermal note). Subsystem = buck(+5V) → buck(+3V3) → LDO(+1V8).
2. **Missing structures**: added `rt_r` (RT pin 6 — fSW-set resistor, short AGND-referenced)
   and `stage_order` (intra-subsystem FLOW: stages arranged as a left-to-right power chain,
   VIN entry → +1V8 exit, matching the schematic's stage rows).
3. **Gate formulation**: hot-loop gate is EXISTENTIAL PER PIN-PAIR (each VIN/PGND pair has
   *a* 100nF within threshold, same side) — NOT per-ref. C1/C25 are interchangeable; a
   per-ref gate would false-fail a valid swapped layout. (General rule recorded: role
   assignment among identical parts happens at template time; gates check the electrical
   requirement, not the ref binding.)
4. **Two-converter terms made concrete**: `fb_vs_foreign_sw ≥ 5 mm` (each buck's FB cluster
   vs the OTHER buck's SW node/L; judgment, defensible), stages oriented FB-sides away from
   each other's switching sides.
5. **stage_zone demoted** from contract term to advisory note — zone size derives bottom-up
   from placed structures; a target rectangle as a gate would be a new proxy objective
   (the airwire-budget mistake, re-learned). EVM-guide pull now optional.

**Threshold revisions**: HF flanking cap pad-to-pin tightened 1.5 → **1.0 mm** (TI EVMs
place them essentially touching; the hot loop is the one structure that matters most).
Bulk ≤5, FB ≤3, BOOT ≤2, FB-vs-own-SW ≥3, FB-vs-foreign-SW ≥5 (all judgment-marked).

**Engine-consumption model (upgraded)**: per-structure-type **STAGE TEMPLATES**, not a
constraint solver — the buck template deterministically constructs Fig 11-2 (IC centered;
HF caps flanking the VIN/PGND pairs; L on the SW side; bulk behind HF; FB cluster at pins
3/4 — AGND tie adjacency comes free; BOOT at 13/14; VCC/BIAS at pins 1/2). Contract =
the template's checkable constraints; gates verify the emitted result; shelf-pack keeps
only true leftovers (LEDs, TPs, PGOOD strap). Deterministic generation + strict gates —
consistent with the project constitution; no optimizer introduced.

**Portability note**: contracts bind LIBRARY refs; the existing `_renamed_ref` band map
carries them to board refs (same mechanism the netlist uses).

**Verdict (orchestrator, owning the quality call):** with these amendments the concept is
CORRECT and BUILD-READY at concept level. Remaining before code: engine-consumption
design detail (template geometry mechanics, leftover packing, gate wiring) — next unit.

### Engine-consumption design (completes the pilot concept package)

**Template = deterministic function** `(contract, footprints, real pin positions) → local-frame placements`.
It reads pad centers from the resolved IC footprint (parsing exists in `footprint.py`) —
no hardcoded coordinates; the template adapts if a footprint revs.

**Buck-stage construction (Fig 11-2, mechanized):** IC at local origin rot 0 → per
VIN/PGND pair: place the assigned 100nF with pads facing the pair midpoint at construction
gap ~0.4 mm (gate bound stays 1.0 mm — construct tighter than the gate) → bulk caps
outboard on the same axis → L centered on the SW-pad side → FB cluster (RFBB/RFBT/CFF)
stacked at the pins-3/4 side (AGND adjacency free) → BOOT cap at pins 13/14 → VCC/BIAS
at pins 1/2. Passive rotations from {0,90,180,270} chosen to face target pads. QFN's
four sides ≈ four quadrants → members collision-free by construction; if a part grows,
the template WIDENS gaps (place.py's feasibility discipline: whitespace grows, rules
never relax).

**Composition:** each stage is a rigid unit; stages arranged by `stage_order` left→right
(power flows VIN → +1V8), stage 2 mirrored so FB sides face away from each other's SW
sides; inter-stage gap satisfies `fb_vs_foreign_sw ≥ 5`. LDO stage appended as the third
unit. Output shape = exactly what `_pack_one_zone` returns (top_off/bot_off, zone w×h) —
the template REPLACES the shelf-pack for contracted subsystems; true leftovers (LEDs,
TPs, PGOOD strap) shelf-pack into the remaining band with template extents as blockers
(existing `blockers` mechanism).

**Integration:** `subsystem_zone_geometry` consults a contract registry — contracted
subsystem → template path; everything else → legacy shelf-pack, **byte-identical**
(regression discipline preserved). The 2-side classifier consults the contract FIRST:
contract members are exempt from bottom relocation (the same_side override).

**Gates:** read the EMITTED board, never the template's intent (the gate must catch a
broken template). One checker per structure type; existential-per-pin-pair for hot loops;
wired into the verify chain; mutation-tested per `test_pcb_gate_mutation` pattern.

**Pilot implementation unit (next):** contract file in `subsystems/power/` + buck/LDO
templates + contract registry hook + 4 gates (hot-loop, fb-separation, proximity set,
same-side) + render review of the re-emitted power zone against the done-bar.

### Render instrument + BEFORE evidence (Phase L step 0 — instrument validated first)
- **Instrument:** `kicad-cli pcb export svg --page-size-mode 2` → cairosvg raster at
  30 px/mm → PIL crop to zone bbox (+2 mm pad). Pad-level detail legible. Refinement:
  drop F.Fab from the layer list (fab text clutters); keep F.Cu/F.SilkS/Edge.Cuts.
- **BEFORE renders (archived: carrier/reports/placement_pilot/power_before_{top,bot}.png):**
  TOP — both 10 µH inductors stacked together, U20001 beside them, U20002 far bottom-left,
  near-zero capacitors on the IC side. BOTTOM — ALL electrically-critical passives
  (100n flanking caps, 22µ/10µ bulk, full FB divider set, VCC 1µ) in a value-sorted grid:
  every hot loop crosses the board through vias. The canonical proxy-blind failure.
- **Wave-A acceptance rule derived from the render:** the four placement gates MUST FAIL
  on the current board, naming these parts/pins (red-on-before proves the gate bites;
  a gate that passes the before-board is itself defective). Waves sequenced A → B
  (gates define red/green before the template exists).

### Pilot iteration 1 — render verdict (orchestrator visual review)
Wave B accepted (gate 0/59 violations, byte-identity elsewhere, 412 tests, deterministic).
AFTER renders (carrier/reports/placement_pilot/power_after_v1_*.png) confirm the stage
row reads per Fig 11-2: FB-west | HF-flanked U1 | L1 | L2 | U2 HF-flanked | FB-east | LDO.
Bottom under stages clean. THREE defects found by MY review that the green gate could not see:
(1) contract v1 has no bulk_out — output 22µF caps landed as bottom-side leftovers 10mm
away (half the power loop uncontracted); (2) stage row 65mm wide (LDO given a buck-grade
13mm gap) inflated the BOARD 154x152 → ~175x167 (+24% area, visible voids); (3) render
instrument needs --exclude-drawing-sheet. → v2: bulk_out structure + row compaction/wrap
with acceptance pinned to board-area recovery (≤ ~+5% of pre-pilot).
Lesson recorded: a green contract gate is silent about what the contract omits — the
render loop is what catches contract INCOMPLETENESS (LAW-1 for contracts).

### Pilot iteration 2 — FINAL VERDICT: PASS (orchestrator visual review)
v2 (worker died at session limit mid-run; state verified + completed by orchestrator):
bulk_out landed (gate 20 structures, 0 violations), row rotated VERTICAL 24.2x46.6mm
(fits the E band), 37/37 targeted tests green (byte-identity elsewhere, determinism),
full board emit BOARD: PASS. Render review (carrier/reports/placement_pilot/power_v2_*):
two clean vertical datasheet stages — FB/BOOT/VCC/RT cloud on the non-SW side, HF caps
at the VIN pairs, L at SW, OUTPUT caps in a column at each L's output edge — LDO stage
below, leftovers banded, bottom side EMPTY under the stages. Board 170x145 = 24,650mm²:
50mm² (0.2%) over the judgment bound, ACCEPTED — the render shows tight packing, no
voids; +5.3% vs pre-pilot is the physical cost of 26 critical parts moving to the top
side with datasheet adjacency (the old board was smaller by being electrically wrong).
OPEN (next Phase-L steps, not pilot blockers): (a) composition-level FLOW gate — the
stages face the E edge, not the power_som/SoM flow direction; external contract terms
are still unenforced; (b) remaining 5 critical-subsystem contracts (D6); (c) parked
return-path gate fix (Xilinx IO_LxxP/N pair naming).
PILOT CONCLUSION: the contract→template→gate→render loop WORKS — two render-loop
iterations caught three defects no gate could see (contract omission, board inflation,
instrument artifact) and drove them to fixed. The methodology is validated end-to-end.

### Phase L expansion — extraction verified, spec errors caught (orchestrator log)
Haiku netlist extraction (6 subsystems) landed and CORRECTED two of my research specs
before they hardened: motor_sense uses an **INA3221** (not INA226; shunt in-line between
two XT60s), hdmi_rx's ESD is **TPD4E02B04 x2 + TPD4E05U06** (not TPD12S016). Research
agent redirected to the correct datasheets. **Process lesson recorded: extraction
precedes research targeting — never spec research from memory.**
Key extraction facts for the contracts: power_som is a THIRD LM61460 buck (U4) — the
pilot's structures + SNVSBD5D citations transfer wholesale (plus one new en_cluster
structure: R12 series + D5 zener clamp + C20 at EN pin 7); ethernet's line side is
fully characterized (HX5008 MDI=PHY-side / MX=line-side; Bob-Smith 75R||1n per MCT →
BS_COMMON → single 2kV barrier cap → CHASSIS_GND) — the moat contract can bind exact
nets; usb_pd is a 6-part proximity contract (VDD/VBUS caps + CC 200p filters at the
FUSB302); rj45's LED resistors legitimately bridge the moat (+VLED logic rail to
in-jack LEDs) — the contract must place them on the LOGIC side of the boundary.

### Return-path gate landed — SI FINDING on J2 (orchestrator-verified)
Xilinx pair-naming fixed (IO_L<n>_<P|N>_<bank> + capability-token variants): 69 HS-capable
pairs detected across the DF40s (was 5; J2/J3 were silently 0). REAL-BOARD VERDICT: FAIL
at K=2 — 29/138 HS contacts lack a ground within 2 steps, 28 concentrated on J2 banks
13/33 (FMC-class IO), worst distance 4. Caveats recorded: detection is conservative
(every IO pair treated as HS; per-pair criticality triage = follow-up); SoM pinout is
fixed → remediation lives in the mezzanine ESCAPE FANOUT (ground-via placement — feeds
the escape-block design) + routing-phase return vias. Also a SoM-design data point.
Ethernet line-side research landed (Pulse v7 + TI SNLA079D/387 + Micrel/Microsemi,
pdftotext-verified): magnetics↔RJ45 <25mm; PHY↔magnetics ≥25mm (measured ACROSS the
mezzanine — remote-PHY caveat); moat = NO plane under discrete magnetics/RJ45/between,
boundary across the transformer body (pins 1-12 vs 13-24); 20mil keep-outs + 50mil
arcing clearance as the citable width bounds; BST 75Ω+1nF≥2kV at MEDIA CTs; 2×1206
bridges at the RJ45; MDI 49.9Ω termination belongs on the SoM (PHY) side — carrier
correctly has none. Magnetics↔RJ45 <25mm is a COMPOSITION-level term (two sheets).
power_som contract v1 drafted (orchestrator): third LM61460, pilot structures + new
en_cluster type; pending engine extensions E1-E4 flagged in the file header.

### Decision D10 — generic structure vocabulary (stops per-part gate branches)
Drafting power_som + ethernet back-to-back exposed a scaling flaw: each new subsystem
was minting bespoke structure types (en_cluster, next bst_cluster, esd_cluster...) each
needing its own gate branch forever. CORRECTION: the gate grows ONE generic intra-zone
type — **proximity** {members, anchor_part, anchor_pin(s), max_mm, same_side, min_from
(optional list of {part/pin, min_mm})} — which expresses EN clusters, BST networks, ESD
arrays, LDO caps, kelvin filters alike. Buck-specific types (hot_loop existential,
fb_cluster, sw_node, bulk_in/out) stay bespoke — their semantics are genuinely special.
power_som's en_cluster converts to proximity when the generic type lands (E4 → E4').
COMPOSITION vocabulary grows: **near_max** {other_sheet, max_mm, basis} (first CITED
instance: magnetics↔RJ45 ≤ 25mm, Pulse v7 p.1), **far_min** (exists), **region_void**
(the ethernet moat: the corridor between T1's media pin row and the jack must contain
no components but the declared BST/bridge parts — plane voids are routing-phase).

### Ethernet + rj45 contract content (ready to instantiate once D10 types land)
ethernet sheet: proximity(BST R+C pairs → their MCT pins 24/21/18/15, ≤4mm judgment,
media side); proximity(C5 barrier → media row, ≤8mm judgment); same_side(T1).
COMPOSITION: near_max(rj45_connector, 25mm, CITED Pulse v7 p.1); region_void(T1 media
row ↔ jack, allow BST/C5/bridge parts only); far_min(power/power_som switching, 10mm);
min distance T1→SoM region ≥25mm (Pulse v7 p.2, measured across mezzanine — remote-PHY
caveat recorded); advisory total path <100mm. rj45 sheet: LED resistors R1/R2 on the
LOGIC side of the moat boundary.

### Research wave COMPLETE (5/5 verified) — remaining contract content (D10 vocabulary)
FUSB302B research falsified two secondary-source values (VCONN=10nF per EVBUM2509 not
0.1µF; VDD value UNSTATED by onsemi) — only CC 200-600pF is primary-cited (AN-5086).
Two netlist FINDINGS spawned as task chips: INA3221 input RC filter absent (SBOS576C
7.4.3 conditional, plausible with 8 ESCs); CC1/CC2 have NO ESD element at the
user-touchable receptacle (AN-5086 TVS, cReceiver budget constraint with existing 200p).

**usb_pd**: proximity(C1→U1 pins3/4 ≤2mm judgment — onsemi states no value/distance;
C2 10µ ≤5mm; C3→pin2 ≤3mm; C4/C5 200p→CC pins 10/11,14/1 ≤3mm, basis AN-5086 cReceiver
+ EVB topology); same_side(U1); EP→GND (DS Fig.5) via array = fanout-phase judgment.
external: flow [pd_input, usb_pd, power] (consistent with pilot); near_max(pd_input,
15mm judgment — keeps the CC net short end-to-end). VCONN NC = correct (sink-only).

**motor_sense**: proximity(C2 0.1µ→U2 VS pin4 ≤2mm, SBOS576C 8.2/8.3 "close as
possible"|judgment:2.0; C3 10µ ≤5mm); proximity(U2→RS1 ≤10mm, SBOS576C 7.4.1 "close as
possible"|judgment:10.0); proximity(D1 TVS→J2 pads ≤5mm judgment — clamp at entry);
proximity(C4 470µ→J3 ≤8mm judgment — load-side bulk per README); advisory in-line order
J2→RS1→J3 (kelvin tap geometry itself = routing-phase); same_side(U2 with RS1).
external: near(motor_pwm) per D9 (floorplan edge move W — connectors change edges!);
far_min(power/power_som switching 10mm judgment; SBOS576C 7.4.1 noise-coupling basis).

**hdmi_rx**: proximity(U2,U3→J1 pads ≤5mm, SLVSD85B 10.1 "close to connector as
possible"|judgment:5.0); proximity(U4→J1 ≤6mm, SLVSBO7O 7.4.1 + per-pin footnote);
region: no other hdmi_rx part between J1 and U2/U3 (implication basis — "protected
traces between TVS and connector"); flow-through orientation (IO row perpendicular to
pair direction, NC row completes pass-through — SLVSD85B 5/7.3.10) = template term,
advisory in gate v1; same_side(U2,U3,U4 with J1); no decoupling (passive parts, cited).
external: advisory flow [hdmi_rx → som].

NEXT ENGINE WAVE (blocked on FLOW worker landing): E1 carrier-local registry, E2
foreign-less fb_cluster, E3 @som downstream, E4' generic proximity type (+ fail-loud on
unknown types), E5 composition near_max/region_void; then instantiate the 4 contracts +
templates; render loop per subsystem (orchestrator).

### Composition wave landed — FLOW/FACING/FAR gate + power re-faced (orchestrator verdict: PASS)
Both new gates wired into the build (HARD-FAIL, LAW 4): placement_contract + placement_flow
reports in carrier/reports/. Board build PASS, byte-deterministic (hash-verified by
orchestrator), 52 targeted tests green. Render verdict (power_v3_top.png): the 180° turn
lands COUT banks on the W column — power flows E→W toward power_som/SoM (facing 3.0°,
was 152.6°). Pilot OPEN item (a) CLOSED.
Orchestrator rulings on worker-flagged decisions: (1) SoM-detour FLOW term ACCEPTED —
the bare sqrt(area) budget mis-modeled a center-module board; fixing the model is
improve-the-algorithm, not soften-the-gate. (2) The 1.9mm flow margin (power→power_som
120.3/122.2) is REAL signal: the floorplan holds these zones apart — floorplan
improvement queued with the composition work, gate left strict. (3) zone-centroid vs
stage-centroid facing divergence risk noted for multi-contract future — revisit when a
leftover-heavy zone gets a contract.

### Engine wave 1 landed (61184b6) + Decision D11
E1-E5 + 4 contracts committed; red-on-before proven (usb_pd 4 / ethernet 9 / hdmi_rx 3 /
motor_sense 5 violations on the scattered board, power green, build PASS, board
byte-identical via the _WIRED_SHEETS discover/load split — orchestrator-accepted as the
correct generalization of the pilot's own scoping).
**D11 — near_max metric corrected: zone-EDGE gap, not centroid distance.** Centroid
distance is bounded below by the zones' half-extents, so a tight centroid bound
false-fails adjacent zones (usb_pd↔pd_input measured 38.6mm centroid ≈ near the
geometric floor). near_max v2 = bbox edge-to-edge gap, thresholds re-judged: usb_pd↔
pd_input ≤ 10mm gap (judgment), ethernet↔rj45 25mm stays CITED but re-expressed as the
Pulse magnetics-body↔jack-body distance intent (edge gap ≤ 20mm judgment as the
conservative proxy for the ≤25mm part-to-part rule). Floorplan facts to fix in wiring
waves: motor cluster (D9) and any residual usb_pd adjacency after the metric fix.

### usb_pd wave — partial accept + silk REJECTION (orchestrator review)
usb_pd end-to-end GREEN (near_max edge-gap 0.00mm — zones abut; all 6 parts clustered
at the PHY top-side; D11 metric landed; edge-seat floorplan override for usb_pd used
and loudly flagged per spec). Board 170×145 → 170×151 (+4.1%) — render verdict pending
rework. **REJECTED: the silk declutter font-shrink** — evidence: 17 refdes emitted at
0.5mm + 7 at 0.62mm incl. sheets outside the wave (pen>0 trigger applied board-wide);
0.5mm is below the ~0.8mm fab-legibility floor. PRINCIPLE RECORDED (silk LAW-4 analog):
**declutter may never shrink below the 0.8mm fab floor — when no clear spot exists at
floor size, WIDEN the relocation search, never the shrink ladder.** Rework ordered:
0.8mm absolute floor (retro-fixing the pre-existing 0.62 tier = deliberate board-wide
DFM upgrade), wider-radius relocation for the 3 motivating overlaps, size-distribution
proof in acceptance.

### Next-wave spec: connector-zone proximity (ethernet + hdmi_rx + power_som wiring)
Design ruling for connector-anchored proximity (hdmi_rx): the LAW-6 connector seat is
IMMOVABLE (edge-flush, mating face off-board) — the proximity builder therefore treats
the connector as a FIXED anchor: J1 seats first via _pack_connector_zone exactly as
today; contract members (U2/U3 TMDS ESD ≤5mm, U4 ≤6mm) then seat INBOARD of the
connector's inner pad row by the ranked-candidate CSP, honoring the flow-through
advisory (ESD IO rows aligned between J1 pads and the zone-interior/mezzanine
direction); remaining hdmi_rx parts (EEPROM, pulls, dividers) shelf-pack behind.
Zone extents/edge seating unchanged — the template composes WITH the connector packer,
never re-seats the connector.
ethernet: T1 interior anchor (proximity builder as usb_pd) + BST pairs at MCT pins;
near_max(rj45 edge-gap ≤20mm) likely needs ethernet added to _EDGE_SEAT_BLOCKS
(same flagged mechanism as usb_pd — seat against the jack block).
power_som: near-free wiring — it is a 1-stage buck; the existing buck template handles
it (hot_loop dispatch). Add to _WIRED_SHEETS + facing derivation (interior side E →
downstream @som is W-ish; verify with the flow gate's E3 resolution). Render check after.
Sequencing: silk rework lands → orchestrator render verdict on usb_pd + board growth →
commit → THIS wave → motor_sense last (D9 edge-list move = biggest blast radius, its
near_max(motor_pwm) currently 132mm — the floorplan move is the fix, contract already
red-proven).

### Decision D12 — two-ring Fable-thread architecture (2026-07-02 evening, user-directed)
Ring 0 = main orchestrator (strategy, merge authority, final verdicts). Ring 1 = FABLE
problem-owner threads, each owning one hard judgment-heavy problem end-to-end incl. its
OWN render loop (parallelizes the perception bottleneck), delivering evidence-backed
units for Ring-0 merge review; plus Fable adversarial panels (EE/DFM/SI lenses) at major
merges. Ring 2 = Opus/Haiku spec-gated workers (unchanged). Problem owners: T1
composition (zone-pose optimization against the now-real contract objectives — the
deep-placement problem reborn with an honest cost function), T2 escape/fanout (DF40
escape block + J2 return-path remediation + pair triage), T3 routing-intent (queued
behind T2 per the layout-first decree). Rationale: today's error log proves
single-threaded judgment fails predictably; every catch was more judgment applied later.

### D12 amendment — ALL-FABLE fleet (user decree, time-limited window)
Every agent at every ring runs Fable 5 while access lasts. Tier-splitting suspended;
Opus/Haiku = fallback only. Two in-flight Opus workers (silk rework, lightweight
contracts) grandfathered to completion — their work is gate-checked.

### Whole-board render audit — findings register (orchestrator, LAW-1 sweep of unaudited zones)
Renders from the live board (silk-rework-intermediate hash 1812bc53; zone geometry valid).
- **F1 ethernet/rj45 (HIGH):** magnetics↔jack ≥27mm (CITED Pulse ≤25 violated); TWO
  FOREIGN QFNs (U21001/U21002) sit IN the line-side isolation corridor; Bob-Smith network
  absent from the line side entirely; T1's pin rows face N/S while the jack is E
  (media row must face the jack). → ethernet wave: orient T1, region_void the corridor,
  near_max adjacency, BST at MCT pins.
- **F2 hdmi_rx (MED-HIGH):** ESD arrays 8-10mm from J1 (bounds 5/6mm), arranged as a
  size-row not per-pair opposite their TMDS pins, rotated 90° off the flow-through axis.
  → wave adds pair-alignment + rotation to the template; contract orientation term
  graduates from advisory to gated.
- **F3 motor_sense (HIGH):** XT60s edge-seated ✓ but the sense cluster (INA3221, SMBJ
  TVS, 470µF) sits ~50mm away; TVS not at the inlet, bulk not at the outlet; the in-line
  battery→shunt→ESC path traverses half the board with foreign zones interleaved.
  79x32mm zone bbox. → D9 move + contract wiring; render quantified the before.
- **F4 camera (MED):** CSI ESD parts ~15mm north of the CAM FFC — port-entry parts
  belong at the port (same class as F2). The lightweight wave's camera contract will
  red-flag exactly this.
- **F5 SoM shadow (NOTE for T2):** bottom shadow = som_decoupling grid + foreign L4
  strays; the escape block will claim this space — needs an eviction/coexistence rule.
- **F6 interior sparseness (NOTE for T1):** visible scatter/whitespace = the measured
  board growth; composition thread owns recovery.

### Render audit pass 2 (orchestrator)
- **F7 motor_pwm (HIGH, compounds F1+F3):** sheet-21 buffers/ICs (U21001/U21002) and
  RS21xxx networks sit at the E side — INSIDE ethernet's isolation corridor — while the
  ESC PWM connector is at the W edge. The corridor squatters and the motor smear are ONE
  defect: relocating motor_pwm's electronics to its W connector clears the ethernet moat
  nearly for free. The D9 motor wave and the ethernet wave are therefore COUPLED — spec
  them as one composition move (motor cluster W: pwm buffers + sense + XT60s per D9;
  ethernet corridor voided).
- Minor: Y28001 crystal ~8mm from its usb_jtag IC (wants ≤5mm) — add to usb_jtag
  lightweight contract. N-edge connectors verified seated (whole-board view). Bottom
  side globally orderly: clusters hold, no off-board, mounting holes clear; big uniform
  bringup passive grid center-left is electrically benign (straps/LEDs), low priority.

### Decision D13 — ESCAPE HEADROOM (user input: dense many-pin ICs starve routing)
Measured on the live board (per-side courtyard gaps): FUSB302 ENTOMBED 0.5-0.7mm on all
4 sides with CC/I2C/INT exiting (F8, HIGH — my proximity template's defect); bucks
equally tight but ACCEPTABLE (self-terminating cluster: only EN escapes — the TI
reference layout is itself tight); T10001 magnetics walled 0.8mm E/S by foreign parts
with 8 diff pairs needing through (F9, folds into F1/F7).
**The rule (nuanced):** escape demand is PER SIDE, PER NET — count the nets on a side's
pins that EXIT the cluster; that side needs a reserved corridor ≥ exit_nets × (trace+
space) × margin, with a floor (judgment: 2x 0.1/0.1mm lanes minimum + 1.0mm clearance).
A side fully TERMINATED by cluster members may be tight (terminus ≠ obstruction).
**Consequences (queued):** (1) NEW `escape_headroom` placement gate — per multi-pin IC,
per side: free corridor depth vs exit-net demand; the routability proxy placement always
lacked. (2) Proximity-builder fix: exit-side reservation as a HARD CSP constraint —
members may occupy a side only if all that side's pins terminate at members; usb_pd
re-runs red→green under the new gate. (3) T1 composition spec review will require
inter-zone channel reservation (the deep-dive constraint-legalizer lens already carries
it). (4) Buck-template exemption documented (self-terminating rationale).
Wave queued directly behind the silk landing (same main-tree unit; avoids concurrent
build races).

### Deep-dive landed (32 Fable agents, 4.0M tokens) — specs + critique triage
T1_COMPOSITION_SPEC.md + T2_ESCAPE_SPEC.md saved at repo root (synthesis of judged
design brackets; T1 = incremental-migration spine + constraint-legalizer engine; T2 =
return-path-first + toolchain-pragmatist). The panel CAUGHT a stale orchestrator figure
(the "1.9mm flow margin" was pre-facing-turn; live margin ~63mm) — re-measure-don't-
trust institutionalized. Ring-0 spec review will inject D13 channel-reservation into T1
(thin: 3 refs) before launch; T2 carries it natively (19 refs).
**Completeness critique triage (orchestrator):**
- **GAP1 (CRITICAL-class): thermal gate PASSES on unemitted copper** — LM61460 RthJA
  credit (58.7→30 C/W) assumes pours+via fields that do not exist (0 zones/vias/segments
  emitted); backed-out Tj without them ≈192°C vs the 140°C bound. QUEUED FIRST: the
  one-day zone-emission spike (deterministic In1.Cu GND zone via the embed.py template
  path, build-twice proof) + a copper-debt report enumerating every basis string
  predicated on unemitted copper. Unblocks T2; unfictionalizes thermal.
- **GAP5: return_path_gate not in the build chain** — wire report-first with the
  29-failing-contact count as a RATCHET baseline (may only decrease); build A.5
  (rail-vs-contact ampacity) verbatim; TP probe-access scalar.
- **GAP4: ledger.jsonl per build** (W×H, area, per-gate worst margins, DRC count, silk
  distribution) + pre-committed cumulative AREA CAP with basis — kills the measured
  perverse incentive (sqrt(area) budgets self-legitimize growth). Backfill from git.
- **GAP2: DSN/Freerouting harness as repo code** (numbers-only, interpretation deferred
  — decree-compliant); gives T2 its escape-region routability probe.
- **GAP3: DFM closure wave** (fiducials emitted+registered, CPL/pos export, fab-profile
  gate, ASSEMBLY_NOTES refresh, double-sided-SMT ratification ask).
- Below-fold items adopted: DF40 mated-height scalar gate; region_void fail-loud check
  at ethernet wave; D7 EMC scoping gets a basis string; sequencing analysis note.

### T2 COMPLETE (parked for merge) + two engine discoveries
T2 delivered in worktree: 29/29 J-contact remediation (worst 1.78mm vs 2.0 gate), 8
stitch vias, F.Cu ladder + In1.Cu GND zone EMITTED (first real copper), zero part
movement, byte-deterministic x2, 530 tests, red-on-before pinned as pytest fixture,
si_triage (29 = 8 GENUINE TMDS/HDMI + 1 MODERATE + 20 LOW), T1 corridor sidecar
(carrier/escape_block.json), F5 coexistence data, GAP1 reconciliation surface flagged.
Merge order: AFTER GAP1 lands (shared embed/emit surface).
**DEFECT REGISTERED — bottom-mirror convention split (LAW-0-class landmine):**
in-process pad geometry X-mirrors bottom footprints; EMISSION does not; kicad-cli reads
unmirrored (T2 DRC-proved on C22025). Contained TODAY (verified: zero polarized/active
bottom parts; swapped pads on non-polar 2-pin passives are electrically identical) but
(a) any future bottom active/polarized part would emit REVERSED, (b) bottom pad-level
gate measurements use the wrong convention. FIX QUEUED behind GAP1 (same files):
unify to ONE convention + a guard test (no asymmetric/polarized bottom part until
unified) + re-run all pad-geometry gates. T2's union-of-conventions workaround is safe.
**DFM rule adopted:** CLR_HOLE_SAMENET_PAD=0.10 (via-in-pad kills solder pads even
same-net — T2's honest lattice found off-pad seats instead).

### T2 ESCAPE wave LANDED (2026-07-02, worktree t2-escape) — D13 native entry
**Deliverable: carrier escape-fanout return stitching.** Nothing here claims "return
path fixed": v1 (return_path_gate, K=2) is RED BY MODULE DESIGN — the SoM pinout is
fixed, 29 HS-capable contacts (J1=1, J2=28, J3=0; 8 GENUINE TMDS/HDMI_RX halves) have
no ground contact within K=2 steps and no carrier copper can change that. v1 is now
REPORT-only permanently (docstring codifies the two-gate split; pytest pins 69/138/29/4
and asserts v1 is ABSENT from ok_all as a TESTED decision). The carrier-side HARD
obligation is `return_stitch_gate` (v2): every v1-failing contact ≤ 2.0 mm from a
carrier GND stitch via on a file-visible F.Cu ladder under the In1 GND plane — ANDed
into ok_all, class-blind (triage orders, never waives).
**Landed copper (derived live, stale-scalar law):** 8 stitch vias (J2=6, J1=2 incl.
the judgment:2 redundancy partner), worst contact→via 1.7772 mm (construct bound 1.8,
gate 2.0); F.Cu ladder = 2 spines + 5 pair-gap stubs (J2) + 2 single-pad stubs (J1) +
1 via-stub; one In1.Cu GND zone (SoM keepout +2.0), emitted UNFILLED + `--refill-zones`
at the two and only two DRC sites (P0 probe: kicad-cli 10.0.2 fills in memory, input
hash unchanged; `(locked yes)` parses clean; project netclasses are the effective
clearance authority — the manufacturing .kicad_dru is NOT auto-loaded).
DRC ledger delta vs pre-wave board = 0 (errors 0, warnings by-type identical);
build-twice byte-identical; byte-superset proven (pre-board == post-board minus
appended nodes). One escalation fired and is ledgered: band 3 (8 contacts, TMDS)
split at u=2.0 by the hdmi_rx_term B.Cu wall; the 3R seat lives at (2.60, 0.30)
local via exact corner-distance windows the 0.05 lattice found.
**Two-tier decision:** Tier-2 lane COPPER deferred to the routing phase (consumer
named: Freerouting locked-preroute; ~270 asserted-dangling stubs would couple build
health to kicad-cli warning semantics for zero gain). The PLAN is landed + HARD-gated
today (`escape_lane_gate`): identity/monotonic ports, adjacent-lane clearance
pre-proof, 15-GENUINE pair hard terms (same-row, |Δlane|≤2 — measured), netted pins
93/100/100, poses-inclusive content_key. PLANES OWN POWER: power contacts are
plane-escape records (bus-grouped runs), never 0.4-wide surface lanes at 0.4 pitch.
**Port ledger:** carrier/escape_block.json (schema escape/v1) — 293 lanes, 40
function-level PairRecs (v1's 69 is the interface-level HS-capable overcount over raw
IO_L*_P/N names; both quoted), triage table, coexistence verdicts, and
`t1_constraints.corridors`: 6 machine-readable escape-corridor rects (J1/J2/J3 × N/S)
the T1 composition legalizer must keep clear — the D13 sidecar, consumable as-is.
**F5 coexistence rule (data, never silent deletion):** bottom-shadow parts inside the
escape region get STAY / CONSTRAINT / EVICT verdicts with basis strings.
Today: som_decoupling + power_som = STAY (function); hdmi_rx_term R13001–R13008 =
CONSTRAINT (their pads closed band-3's v=0 window and forced the split + v-nudged
seats); EVICT list EMPTY — it fires only when a failing contact becomes
unconstructable, and its named consumer is the queued bottom-channel-keepout unit.
**Engine finding (for the placement/emission owners, F5-adjacent):** the in-process
pad-box convention X-MIRRORS bottom footprints (placement_contract_gate._pad_boxes)
but embed._flip_to_bottom emits local coordinates UNCHANGED and kicad-cli reads them
unmirrored — DRC proved C22025 pad 1 [+VIN_SYS] lands at the model's pad-2 spot. For
symmetric passives only the NET assignment swaps sides, so ratsnest/contract gates see
mirrored nets on every bottom part. T2 works around it (obstacles = union of both
conventions; netclass-aware clearances 0.15/0.2); the RECONCILIATION belongs to the
engine owners — flagged, not silently fixed.
**DFM finding:** a 0.3 mm drill centered in the 0.2 mm DF40 GND pair-gap would cut
both solder-pad edges (via-in-pad on a fine-pitch connector = reflow wicking risk) —
codified as CLR_HOLE_SAMENET_PAD = 0.10 (drill stays off ALL pad copper, same-net
included; annulus overlap of same-net copper stays legal).
**Queued follow-ons (each red-on-before, consumer named):** Tier-2 lane copper + full
GND-cluster stitch (routing phase); bottom-channel keepout if a via window closes
(consumer of EVICT verdicts); deterministic in-file In1 fill if the in-memory posture
ever fails a probe; bottom-mirror emission reconciliation (engine owners).

### T2 x GAP1 RECONCILIATION (2026-07-03, worktree t2-escape, base 28f8e15)
Executed per Ring-0 direction. Interface decisions (flagged for review):
1. **ONE In1 plane — GAP1's is canonical** (board-interior inset 0.5, thermal-relief
   pads, clearance 0.3, ethernet ISO voids). T2 emits NO zone; escape.py now VERIFIES
   the canonical plane covers the escape region (SoM keepout +2.0), that no ISO void
   intersects it (fail-loud — live voids sit at J23001/T10001, far from the DF40s),
   and the barrel precondition is scoped to that region. return_stitch_gate re-derives
   the same plane/void geometry independently (vias in-plane, outside every void) and
   file-parity asserts the canonical plane is in the written board.
2. **Unified via emission — T2's builder is the general one**: embed._via_node is now
   dict-driven (any size/drill/net, optional `(locked yes)`, caller-chosen uid key);
   GAP1's thermal-via emission routes through it with locked=False + its original
   `thvia:` uid keys — BYTE-IDENTICAL to the inline construction it replaces (proven:
   the reconciled board is an exact byte-superset of GAP1's committed board + the 18
   locked escape nodes). Segments: _segment_node (T2, sole user). Zones: GAP1's
   _fill_zone family (T2's zone builder deleted). Thermal vias stay UNLOCKED (their
   seats re-derive per placement); only the T2 escape preroute is locked.
3. **CLR_HOLE_SAMENET_PAD single-sourced** from constants.py (GAP1 adopted the T2 DFM
   rule board-wide; escape.py imports it).
4. **Convention note:** GAP1 independently confirmed the bottom-mirror emission split
   (their _pad_obstacles: "NO bottom mirror — pcbnew-verified") and uses unmirrored
   obstacles; T2 keeps the UNION of both conventions for escape feasibility (safe
   under either) until the engine owners reconcile the in-process gates that still
   mirror (ratsnest/contract). Same physics, different conservatism — both documented.
Re-verified on the merged tree: 29/29 covered, worst 1.7772 mm UNCHANGED against the
merged plane, 8 vias + 10 segments, DRC errors 0 + warnings delta-0 vs the GAP1
baseline, byte-superset of 28f8e15's board, emit-twice byte-identical, ruff green.

### T1 rebase + P5b + P6-core — Ring-0 rulings
RATIFIED (all four): (1) P5b exemption partition {pd_input, power, usb_pd} exempt /
{ethernet:14.0, power_som:25.0} guarded — measured bases; the rebase-caught coupling
(L4 exemption parked power_som caps into U22004's thermal-via field → 6/8 sites lost →
honest-thermal board-dead red) is the serialized-merge discipline earning its cost;
(2) P7 power_som wave carries the packer bottom-keepout-under-THERMAL_COPPER item (the
durable fix); (3) D13 terminus-precedence (channel floor yields to hard near_max pairs
— an abutted pair IS the terminus, same logic as decoupling-at-pins); (4) stash incident
closed — T2's merged work verified on MAIN independent of its worktree.
**FLEET PROTOCOL (new, binding): worktree threads NEVER use `git stash` (the stash list
is repo-shared) — checkpoint via temp branches or explicit stash-ref-by-hash only.**
T1 merge point set: rebase onto 4a45f99 (T2's escape now on main — new interaction
surface: T2's channel vias + return_stitch/escape_lane gates in the chain; the rebased
build must prove coexistence), deliver P0–P6core as the merge unit, then continue
P6-wire → P7 (ethernet corridor+F1/F7) → P8 (D9) → P9 → P10 (area verdict vs 24,600).
