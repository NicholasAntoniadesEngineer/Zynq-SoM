# AI Platform Roadmap — schgen as a multi-variant, AI-native hardware platform

*2026-07-09. First-principles refinement plan: how the schematic-generation + board-layout
implementation evolves so future board variants are cheap and AI tooling performs at full
capability. No backwards compatibility. Grounded in measurements of this repo and in the
direct experience of ~35 build iterations across the floorplan/solver/refit campaigns.*

## Principle 0 — the VISUAL product is ground truth (foundational, user-decreed)

The render+inspect pipeline exists because AI tools **consistently failed** to produce
readable schematics and reasonable layouts on numeric checks alone — green ERC/DRC with
shorted nets (LAW 0's origin), an unbuildable board passing every gate (LAW 6's origin).
Rendering the final product and visually checking it is the **only mechanism proven
effective**. Therefore:

1. **Full-render + visual inspection remains mandatory before every landing.** Inner-loop
   accelerators (`--no-render`, synthetic harnesses) never substitute for the landing check.
2. **Promotion protocol.** Before any faster check may stand in for a visual check even in
   the inner loop, it must be **tested and validated multiple times against the visual
   solution**: run both on a battery of changes *including deliberately injected defects of
   the historically eye-caught classes*, and demonstrate **zero false-negatives vs the
   visual verdict, repeatedly**. Evidence recorded; anything unproven stays advisory.
3. **The ratchet.** Eye discovers a defect class → mechanize it as a gate → mutation-prove
   the gate fires on injected defects → the gate guards that class forever → the eye moves
   to the frontier. Gates accumulate; the eye is never retired.

**Injected-defect corpus (the validation battery, from this repo's history):** junctioned
crossing on foreign nets (short under ERC=0); courtyard overlap; off-board connector
interior / mouth inward; part on the SoM-top keepout; control under the module; dispersed
subsystem cluster; silk refdes overprint; starved multi-pin fan-out; B.Cu stray in a DF40
stitch corridor; output facing away from downstream; scattered decoupling (>contract
distance); unreadable schematic (label collision, wire crossing).

## Measured state (2026-07-09)

**Fused engine+project — a second variant today forks the engine:**
- 59 engine files reference `carrier`; `CARRIER = REPO_ROOT / "carrier"` baked into
  `pcb/constants.py`.
- Board names inside engine code: `power_som` ×12 files, `som_j` ×15, `usb_pd` ×14,
  `ethernet` ×13, `LM61460` (one buck MPN) ×10, `Zynq` ×20.
- ~107 board-tuned module-level constants (floorplan.py 35, pcb/constants.py 60,
  stage_templates.py 12) — pose, bands, budgets, gaps, calibrations.
- Literal-name special-cases in the placer: `_WIRED_SHEETS`, `_PILOT_PROX_SHEETS`,
  `b.name == "power_som"`, `b.name.startswith(("bringup", "power"))`. Each was the
  locally-correct move under the current architecture — the architecture *forces* the
  pattern.

**The healthy foundation (keep, build on):**
- `subsystems/` portable library: 20 packages, **zero code coupling** to the carrier
  (verified — all mentions are docstring prose). Subsystem-as-package + thin adapter
  binding is the right atom.
- The module-interface abstraction seed: `som_interface.json`/`SomGeom` (7 consumers) —
  the pattern for a generic "module contract".
- Determinism discipline (byte-identical builds, md5 protocol) — the refactor safety net
  that made this session's engine surgery safe.
- The gate corpus: 34 verify modules encoding ~2 months of eye-caught defect classes.
- `partlib` (LCSC/EasyEDA fetch + verified real parts) — variant-agnostic already.

**The AI-leverage bottleneck (receipts):** 21 of 55 test files require a full 4–9 min
board build. Where a 1-second synthetic harness existed (stage-template zone tests), the
multi-anchor solver landed in 3 tight iterations; where none existed (flow-gate facing),
the refit took **4 blind 10-minute build iterations**. Feedback latency is worth more
than any single algorithm improvement — *subject to Principle 0*.

## The two products (the point of all of it)

The end goal is exactly two artifacts, each at advanced-human-engineer quality: a
**visually coherent schematic** and an **electrically logical PCB layout**. The system
achieves both today through hand-tuning accumulated on this one board; the refinement is
achieving them **by construction, on any project**. Mechanism: every quality the eye
judges becomes (a) explicit knowledge-as-data and (b) a checkable metric promoted under
Principle 0.

**S-track (schematic): PRESERVE + TRANSFER — not improve.** USER JUDGMENT (2026-07-09):
the current sheets ARE golden-reference quality. Schematic generation is a SOLVED
problem on this project; the 27 rendered sheets are the standard itself. The S-track
therefore has exactly two legitimate jobs, and neither changes current output:
  - **Preserve**: the golden-render drift checks already lock today's look — they stay,
    and any S-track mechanism must be RENDER-IDENTICAL on this project.
  - **Transfer**: make a FUTURE project's sheets come out at this same standard
    automatically. Means: the layout engine's quality must not depend on this-board
    tuning — where it does, extract the tuning into part-keyed / pattern-keyed data
    (idiom knowledge) validated by reproducing the CURRENT golden sheets exactly, then
    reusable on new circuits. Style metrics, if ever added, exist only as regression
    armor calibrated to today's goldens — never as a pressure to change them.

**L-track (layout).** An expert's placement simultaneously satisfies all the physics
(hot loops, decoupling at pins, terminations at receivers, return continuity, thermal
spread, mechanics). The expert knowledge is ALREADY SERIALIZED — 23 datasheet-cited
placement contracts — and the engine obeys 3. Closing 3/23 → 23/23 via P3 is the single
largest step toward advanced-human placement, because it activates written knowledge;
then the contract vocabulary grows toward what humans do implicitly (analog/noisy zoning
classes, star-ground points, length-match groups as first-class contract types).

**The scalability thesis.** The portable subsystem package (circuit + contract + idiom
template + tests, datasheet-cited, zero project coupling — verified) is the UNIT OF
ACCUMULATED ENGINEERING KNOWLEDGE. The engine is the solver that composes packages; a
project is just data (floorplan spec + module contract + adapter binds). Every board
built enriches the library, so each next board starts smarter — knowledge compounds in
data, not in tuning.

## Phases

### P1 — Engine/Project separation (the variant enabler)
Everything project-specific becomes **data in the project**; the engine becomes pure
mechanism. A project owns: its paths; its module-interface contract (generalized
`SomGeom` — any mezzanine/module, not "the SoM"); its floorplan spec (already good);
its **wired-sheet set** (out of the gate module, into project data); its declarative
anchors (`power_som: {"anchor": "module_face:E"}` replaces `b.name == "power_som"`);
its connector mating-face registry + edge families; its pose + tuned-constant overrides;
its datasheet templates keyed by **MPN** (the LM61460 buck template binds to the part,
not to a sheet name). CLI: `schgen board --project <name>` (default: the sole project).
**Done-bar:** carrier builds **byte-identical** (md5 e405097b) through the project-spec
path; a second minimal project (seed: `examples/devkit_mini`) builds a green board with
**zero engine edits**.

### P2 — Fast feedback everywhere, under Principle 0
Extend the synthetic-harness pattern (build_zone → synthesized PcbModel → gate check, ~1 s)
to the expensive gates: flow/facing kernels, mech, ratsnest MST on zone deltas,
incremental per-sheet re-evaluation (only rebuilt zones re-checked). Each harness enters
service **advisory-only** until it passes the promotion protocol against the visual
solution on the injected-defect corpus, multiple rounds, zero false-negatives. The
defect corpus itself becomes a first-class library (reused by gate mutation tests).
**Done-bar:** median inner-loop iteration < 30 s for placement work; every promoted
harness carries its recorded equivalence evidence; full-render landing checks unchanged.

### P3 — Constraint-first placement (kills the cascade class)
Today placement is a pipeline of local heuristics (shelf-pack → zone anchors → L4 pull →
edge-seat → BREATHE → facing refit) with gates as post-hoc arbiters; enforcing any new
constraint cascades (contract wiring broke fan-out → DF40 corridor → thermal, measured).
Invert: ONE constraint model — contracts (the multi-anchor solver is built and banked),
fan-out needs, stitch corridors, thermal spreads, mech rules — **consumed by the placer
and checked by the gates from the same single-oracle kernels** (precedent: `facing_dot`
extraction; templates already read the gate's pad boxes). Gates remain the arbiter
(Principle 0); the placer just stops being blind to what the gates will demand.
**Done-bar:** the shelved contract-wiring campaign becomes tractable — wire sheets without
cascades; CONTRACT COVERAGE inert-VIOLATED trends toward 0.

### P4 — Machine-readable verdicts (the AI interface)
Every gate returns structured data (verdict, violations with geometry, measured-vs-bound,
suggested slack) alongside the human report — precedent: `coverage()`. The AI consumes
structure instead of grepping prose; a `schgen board --json` summary emits the full gate
state. Renders remain the human/AI *visual* channel per Principle 0.

### Out of scope — routing (user decree)
Routing is NOT addressed by this roadmap, at all. "Layout" throughout means PLACEMENT —
and placement is a primary concern of this plan (the L-track and P3 are its backbone).

## Sequencing & safety
P1 → P2 → P3 → P4 (P4 items can ride along earlier phases opportunistically). Every
refactor step proves **byte-identity** on the carrier (the session-proven md5 protocol);
every landing gets the full-render visual check. The laws (0/1/2/4/5/6/7) are invariant
throughout — this roadmap changes the *mechanism*, never the *bar*.
