# Placement Algorithm — First-Principles Roadmap

> Produced 2026-07-04 by a 9-agent first-principles analysis (understand → design panel →
> synthesis) working through the ACTUAL implementation in `schgen/generate/pcb/placement.py`,
> `schgen/generate/floorplan.py`, `schgen/generate/pcb/escape.py`, and `schgen/verify/*.py`.
> Companion to `AI_LAYOUT_ROUTING_CONCEPT.md`. Analysis only — this doc changes no code; it
> defines the true objective, the target architecture, and an ordered, individually-shippable
> migration path. Step 1 (fixed-board fan-out spread) is the work currently in flight.

This is an analysis-and-synthesis task. The four designs and understanding passes are already complete — my job is to synthesize the decisive roadmap document. This is my final deliverable (returned verbatim to the calling script), so I'll produce the clean markdown directly. No code modification needed; the code has already been thoroughly traced and cited across the UNDERSTAND/DESIGN passes.

# First-Principles Placement Roadmap — Zynq-SoM Carrier

*Lead layout architect synthesis. Analysis only — no code modified. All line citations verified against the traced implementation in `schgen/generate/floorplan.py`, `schgen/generate/pcb/placement.py`, `schgen/generate/pcb/escape.py`, and `schgen/verify/*.py`.*

---

## 0. The problem in one sentence

The current placer **minimizes board area subject to a slack block-centre-airwire ceiling** (`floorplan.py:1446-1449`), then repairs everything the real objectives care about — fan-out room, congestion, SI/return-path, thermal — with post-hoc patches (BREATHE `placement.py:1254`, L4-pull `:1069`) and hand-calibrated fudge factors (`PROXY_TO_REAL`, `L4_PULL_CREDIT`, `SAFETY`). The gates encode the true cost; placement optimizes a two-term shadow of it and passes the rest by luck. This document defines the true cost, the target architecture, and a shippable migration path.

---

## 1. The ideal cost function

### 1.1 Why area-min was the wrong primary objective

Area-min is actively **adversarial** to the user's stated goals:

- **It fights fan-out headroom.** The search keeps the *smallest* board clearing the airwire budget (`cand < best` on an area tuple, `floorplan.py:1449`). The user wants breathing room; the objective wants the opposite. Fan-out is then bolted on as ratcheted debt — `PLACE_CLEAR=0.5 mm` sits *below* most `fanout_gate` tiers (0.2/0.5/1.0/1.5/2.0), so the board packs below-need by construction and BREATHE claws it back afterward.
- **It produces the "54% empty yet cramped" pathology.** Area-min shrinks the box while greedy anchor-hug (`place_near` first-fit `:1078`, `_anchor` powered centroid `:1713`, `SOM_W=7.0`) collapses all mass to the SoM centroid — dense core, bare periphery, and the empty area is *trapped* between rigid min-area zones that individually cannot expand.
- **It couples sizing to the escape and breaks it.** `plan.som_x = (BOARD_W − som.w)/2` is recomputed for every candidate (`:1436, :1517`); the escape (`build_escape_copper`, `escape.py:462`) runs *last* on those poses and hard-`raise EscapeError`s (`escape.py:451`) when a resize moves the DF40 field off a via seat.
- **It is pathologically expensive.** O(area) lattice × 16 relaxation passes × (80-step aspect grow + 41×41 fine window) = ~thousands of full packs, on a *jagged* feasibility landscape (`:1496`).

Board area is an **output** of a good placement, not its objective. You shrink by tightening a legalizer, not by searching sizes.

### 1.2 The objective, as a priority-ordered weighted sum

Minimize over positions **and sides**, on a **fixed board**, subject to hard constraints:

```
J(pos, side) =  w_wl  · Σ_e W_e · detour_len(e)              # (A) SI-weighted wirelength-to-SoM
              + w_esc · escape_infeasibility(DF40, obstacles) # (B) return-path / T2 seat existence
              + w_fan · Σ_ic max(0, need_ic − clear_ic)²       # (C) fan-out room, by construction
              + w_cong· Σ_cells max(0, demand − supply)²       # (D) congestion / routability
              + w_flow· (flow_hops + facing + FAR penalties)   # (E) power-chain flow & facing
              + w_therm· Σ_hot-pairs 1/dist                    # (F) thermal spread (3× LM61460)
```

**Priority ordering (which weight dominates), derived from the laws:**

| Rank | Term | Why it ranks here | Gate that measures it |
|---|---|---|---|
| **HARD** | No-overlap, on-board, SoM keepout, edge-seat | LAW-0/1/5/6 — never trade away | `placement_mech`, `ratsnest_gate` (a)(b) |
| **1 — (B)** | Return-path / escape feasibility | LAW-0 electrical integrity; a broken T2 seat is board-dead | `return_stitch_gate`, `escape_lane_gate` |
| **2 — (A)** | SI-weighted detour wirelength | LAW-5 real objective; DDR/diff/high-speed nets first | `ratsnest_gate` cross-airwire `:173` |
| **3 — (C)** | Fan-out room | User's stated end-goal; today it's debt | `fanout_gate` tiers `:77` |
| **4 — (D)** | Congestion spread | Fixes the 54%-empty-cramped symptom | (currently none — new) |
| **5 — (E)** | Flow / facing / FAR | Power-chain quality | `placement_flow_gate` |
| **6 — (F)** | Thermal spread | Softest; part-selection carries most of it | `thermal.py` |

**Net weight `W_e`** comes from the netclass the code already knows — heavy for DDR / differential / GENUINE DF40 escape pairs (the `si_triage` at `escape.py:469`), demoted for bulk GND/rails (already down-weighted by fan-out at `floorplan.py:1256`). This makes SI a *first-class objective term*, not a post-hoc gate — the single biggest correctness win beyond area.

**`detour_len`** is wirelength with a SoM-keepout detour penalty (the flow gate already bolts a `+SoM-diagonal` term on, `placement_flow_gate.py:98`) — because every net routes *around* the central mezzanine, so Euclidean HPWL understates real length.

---

## 2. Target architecture

**Chosen hybrid: analytical global placement (DESIGN-1) as the engine, escape-as-constraint (DESIGN-3) folded into it, min-displacement legalization (DESIGN-1/4) as the closer, and low-temperature SA (DESIGN-2) as an optional discrete-refinement polish.** Rationale: this board is a **star topology into one fixed hub** — the textbook case where a quadratic solve is near-optimal and near-free, while SA alone would be slower to converge and min-cut partitioning is redundant against the given schematic clustering.

### 2.1 The pipeline that replaces `zone-shelf-pack + place_near + area-min-search`

**Stage 0 — Freeze the invariant core (board-size-independent).**
DF40 poses, SoM keepout (`placement.py:1008`), escape region (`escape.py:1035`), corner mounting holes. Anchor the SoM origin to a **fixed datum**, not `(BOARD_W − som.w)/2`. This alone decouples T2 from sizing — `escape._content_key` (`escape.py:1106`) stays stable across the whole solve.

**Stage 1 — Edge/side assignment.** Connectors → edges by LAW-6 mechanics (keep `_pack_edges` seating). Subsystems → quadrant + side by an affinity pass around the SoM (subsumes `_dominant_j` `:595` and `_classify_side` `:277`). Discrete, cheap.

**Stage 2 — Analytical global placement.** One weighted-Laplacian quadratic solve: `min ½ pᵀLp` with DF40 J-strips (`plan.som.js`, `floorplan.py:1573`) and edge connectors as **fixed boundary rows**, SoM as an obstacle penalty, spring weights = `W_e` (SI class) and the existing `som_pull` (`:1261`). Solved by conjugate gradient — ~150 lines, no external deps, sub-millisecond for ~30 nodes. This is exactly `_cross_proxy`'s star (`:1556`) **minimized instead of measured**. A **density/spreading term** (ePlace-style, or cheap bin-overflow quadratic) pushes overlapping mass into the empty periphery — the direct cure for 54%-empty-yet-cramped.

**Stage 3 — SA refinement (optional).** Anneal the *discrete* choices a QP can't express — side-flips, connector orderings, 90° rotations — against the **full `J`**, seeded by Stage 2 so it converges fast and can't scatter. Deferred until Stage 2 + legalizer prove out.

**Stage 4 — Legalization (the closer).** Min-displacement Abacus/Tetris removes overlap with minimal movement, **preserving the global optimum**. Fan-out clearance becomes per-cell spacing (LAW-5/fan-out *satisfied*, not ratcheted); escape corridors are hard keepouts (LAW-0). **Board area = a byproduct of the tightest legal pack** — this deletes the entire area-min search (`:1428-1514`), `place_near` (`:1078`), the 16-pass relaxation (`:1815`), and the calibration fudges.

**Stage 5 — Escape stitch** on the still-frozen DF40 poses (`build_escape_copper`). Byte-identical to today because the poses never moved after Stage 0.

### 2.2 How the laws stay HARD constraints

- **LAW-0 (electrical integrity / return path):** escape feasibility is term (B) *and* a hard pre-check in acceptance; corridors are legalizer keepouts. The netlist graph is the QP input, never mutated.
- **LAW-1 (visual correctness):** the legalizer guarantees zero overlap exactly — stronger than the current soft packing.
- **LAW-5 (ratsnest grouping / no off-board / airwire budget):** cross-airwire is *minimized* (term A), not gated; a subsystem stays one movable node through global placement so contiguity survives; on-board is a hard clamp; the budget check remains as the acceptance oracle.
- **LAW-6 (mechanical / edge-seating):** edge connectors are fixed boundary conditions — springs pull their subsystem *toward* the edge naturally.
- **LAW-4 (never soften a validator):** the entire gate suite is retained unchanged as the acceptance oracle. Placement now *minimizes* the gate cost; the gates *verify* rather than *repair*.
- **Fixed-board-friendly:** board size is an input; the density term fills whatever board it is given. Optional outer binary-search re-solves the *fast* QP, never the O(area) pack.

---

## 3. Migration path

Ordered, each step individually shippable and gate-clean. Recommended sequence **1 → 2 → 3 → 4 → 5 → 6**, front-loading the in-flight fan-out spread and the cheapest robustness win.

### Step 1 — Fixed-board fan-out spread *(IN FLIGHT — do first)*
- **Touchpoints:** stop the area *search*; take the current smallest-feasible board as fixed. Turn BREATHE (`placement.py:1254`) from a local patch into the **primary spreading operator** — a density-gradient push into slack, bounded by zone keepouts + escape corridor. Widen the fan-out apron in `_shelf_pack` (`placement.py:90`) from `PLACE_CLEAR=0.5` to the *needed* `fanout_gate` tier.
- **Gain:** retires the flagship symptom (54% empty yet cramped) and the fan-out ratchet debt — slack becomes reachable.
- **Effort:** S (~3–4 days). **Risk:** LOW (post-pass, no engine change). **Validated by:** `fanout_gate`, `ratsnest_gate`.
- **Builds toward:** prototypes the *density term* that becomes Stage-2 spreading.

### Step 2 — Escape-aware sizing / freeze the core
- **Touchpoints:** Stage 0. Anchor SoM/DF40 to a fixed datum instead of `(BOARD_W − som.w)/2` (`floorplan.py:1436, 1517`). Emit the escape corridor (`escape.py:1035`) as a placement keepout the existing packer respects. Add a fast `_seat_band` feasibility pre-check (`escape.py:448`, no copper emitted) into acceptance *before* the airwire test (`floorplan.py:1446`).
- **Gain:** kills the resize-breaks-T2 fragility — the user's fixed-board end-goal becomes robust.
- **Effort:** S (~2–3 days). **Risk:** LOW, high value. **Validated by:** `return_stitch_gate`, `escape_lane_gate`.
- **Builds toward:** the frozen core every later stage assumes.

### Step 3 — Global relaxation solver (QP miniature)
- **Touchpoints:** replace the 16-pass sequential first-fit relaxation (`floorplan.py:1815`) with **one CG quadratic solve** on interior block centroids — Laplacian from the existing `affinity`/`som_pull`/`som_j_of_net` (`:1250-1266`), J-strips as fixed anchors — then feed into the *existing* `place_near`/legalize. Fold `W_e` SI weights in here.
- **Gain:** lower real airwire; escapes order-dependence and the non-monotonic-valley fragility forcing the 41×41 fine scan; first time SI is *optimized*.
- **Effort:** M (~1 week). **Risk:** MEDIUM (new solver, caged in `_attempt_pack`; determinism via fixed iterations + sorted assembly). **Validated by:** `ratsnest_gate` cross-airwire.
- **Builds toward:** Stage 2, proven on ~30 centroids before scaling.

### Step 4 — Global placer + min-displacement legalizer *(the structural win)*
- **Touchpoints:** retire `place_near` (`:1078`) **and** the aspect-grow/fine-window search (`:1428-1514`). Global step = Step-3 solver over *all* blocks (overlaps allowed) → Abacus/Tetris legalizer into rows, fan-out clearance as per-cell spacing, escape corridors as hard keepouts. Delete `PROXY_TO_REAL`/`L4_PULL_CREDIT`/`SAFETY`.
- **Gain:** optimizes wirelength directly; near-constant runtime w.r.t. board size; board area becomes a byproduct. Largest net *simplification* of the codebase.
- **Effort:** L (~1–2 weeks). **Risk:** MEDIUM-HIGH (correctness lives in the legalizer). **Validated by:** full suite (`placement_mech`, `ratsnest_gate`, `fanout_gate`).

### Step 5 — Congestion + thermal terms
- **Touchpoints:** add a coarse RUDY demand grid (or reuse the `_channels` exclusive-pair map, `placement.py:1321`) as term (D); add the LM61460 inverse-distance term (F). Retire BREATHE and L4-pull — spreading is now first-class in the objective.
- **Gain:** deliberate use of the empty 54%; thermal spread the placer was blind to.
- **Effort:** M (~3–4 days once Step 4 lands). **Risk:** MEDIUM (λ tuning). **Validated by:** `thermal.py`, `fanout_gate`.

### Step 6 — SA discrete-refinement layer *(only if needed)*
- **Touchpoints:** anneal side-flips / connector orderings / rotations against full `J`, seeded by Stage 2.
- **Gain:** residual flow/facing/FAR improvements a QP can't express.
- **Effort:** M (~1 week). **Risk:** LOW (optional, seeded). **Validated by:** `placement_flow_gate`.

### ⟵ Point of diminishing returns: after Step 4 (optionally Step 5)

**Steps 1–4 capture the structural wins**: the flagship symptom is gone (1, then 5), T2 is robust (2), SI is optimized and airwire minimized (3), and the O(area)×thousands search plus all fudge factors are deleted (4). **Step 5** is cheap and worth it once 4 lands. **Step 6 (SA)** is the clearest diminishing return — it is the slowest runtime component, the most tuning-heavy, and only earns its keep if measurable flow/facing failures survive Steps 1–5. Do not build it speculatively.

---

## 4. Honest tradeoffs

### 4.1 The current heuristic works
It **passes every gate on the real board today.** The case for the rewrite is *not* "it's broken" — it is: it optimizes a two-term shadow of the true cost, repairs the rest by luck, runs at O(area)×~thousands cost, and carries a fragile size↔escape coupling. That is a *quality-and-robustness* argument, not a *correctness-is-failing* one. Sequence accordingly: cheapest, highest-value steps first, and stop when the marginal gate-score gain flattens.

### 4.2 Where the ambitious rewrite is NOT worth it
- **Full nonlinear ePlace / RePlAce with FFT electrostatics** — overkill for ~30 nodes; a coarse quadratic + simple spreading captures nearly all of it.
- **hMETIS / min-cut partitioning** — the subsystems are *already* clustered by schematic sheet; the partition is given. Only worth it if you go to *part-level* placement (Step 5+ of DESIGN-4), which is not currently needed.
- **RL macro placement** — no.
- **The SA layer (Step 6)** — genuinely optional; defer indefinitely unless flow gates fail.

### 4.3 The smallest change that captures ~80% of the benefit

**Ship Step 1 + Step 2 only** (both size S, both LOW risk, ~1 week combined, no engine change):

1. **Fix the board and make BREATHE the primary spreader with correct-tier fan-out aprons** — retires the 54%-empty-yet-cramped symptom and the fan-out ratchet debt (the two most-visible complaints).
2. **Freeze the SoM/DF40 datum and add the escape seat pre-check to acceptance** — makes T2 robust on the fixed board (the user's stated end-goal).

Together these fix the **three headline symptoms** (empty-yet-cramped, fan-out debt, T2 fragility) *without* touching `place_near`, the relaxation, or the search structure, and ship entirely behind the existing gate suite (LAW-4-clean). Everything past Step 2 is real engineering (M/L, medium+ risk) buying *objective quality and runtime*, not fixing a broken board — so it should be justified by measured gate-score headroom, not built on principle.

---

*Total to full target (Steps 1–5): ~4–6 weeks, medium aggregate risk, best sequenced so the two size-S steps land first and de-risk the rest. Minimum-viable (Steps 1–2): ~1 week, low risk, captures the 80%.*
---

## MEASURED RESULTS (2026-07-04) — the empirical verdict

Four independent experiments (3 workflows + a hands-on airwire decomposition), all on the FIXED 178×163 board, all gate-verified, master-safe:

**1. Airwire decomposition (hands-on).** The 15,186 mm cross-airwire = **58% HUB** (part↔SoM DF40; packing-bound, near-irreducible) + **42% PEER** (subsystem↔subsystem, 6,462 mm — the only improvable part). Peer airwire concentrates in a few mis-placed coupled pairs: `hdmi_rx↔hdmi_rx_term` 68 mm apart (also an **SI defect** — TMDS stub), `usb_jtag↔connector` 110 mm, the bringup cluster — while `ethernet↔rj45` is 16 mm.

**2. Global QP relaxation (Step 3) — NEGATIVE.** CG solve on block centroids: **15,705 mm, +3.4% WORSE**. Minimizes squared (not linear) wirelength + hands off to the same `place_near` legalizer → net loss. Needs Step-4 (min-displacement legalizer) to pay off. Banked `wip/global-qp`.

**3. `AFF_POW` sweep — greedy is a genuine concave optimum.** 1.0 (undistorted) = **+2.4% worse**; 2.0 = +2.4% worse AND breaks fan-out; 1.6 (current) is the minimum. The objective "distortion" is load-bearing, not obsolete.

**4. Surgical clustering fix — diagnosis CONFIRMED, blocked on the fixed board.** Root cause: `ethernet`/`usb_pd` carry exclusive weight-60 connector pulls in `floorplan.json`; `usb_jtag`/`hdmi_rx_term` **lack them** (a data gap, not a bug). Adding them proves the 42% peer is improvable: best **−4.1% (→14,558 mm)**, and `hdmi_rx↔term` **68→8 mm (SI defect fixed)**. BUT every co-location either **grows the board** (usb_jtag's n=19 zone needs ≥180 mm width) or **trips the J2 stitch-via gate** (a B.Cu passive shifts into the stitch corridor — the baseline is on a knife-edge). Banked `wip/clustering-fix` (report-only; source left at baseline).

### Conclusion
**Fixed-board cross-airwire is near-saturated by the greedy Lloyd** — proven three ways. The 42% peer *is* improvable (~4% + a real SI fix), but only by unblocking one of two structural gates:
- **A — bottom-channel-keepout unit**: make the J2 stitch-via corridor a HARD placement keepout so passives never intrude → removes the knife-edge fragility AND unlocks the `hdmi_rx_term` co-location (SI fix + airwire). Fixed board, no growth. *(LAW-0-adjacent: return-path corridor.)*
- **B — board growth** (escape-safe via the Step-2 datum-freeze): the unbounded path to real fan-out + the `usb_jtag` co-location.

### Landed
`place_near` expanding-ring speedup (I2) — byte-identical, faster engine (`75fa591`).
