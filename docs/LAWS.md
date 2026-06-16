# schgen LAWS

The non-negotiable rules that govern every change to this repo. They outrank
convenience, speed, and cleanliness. A change that violates a LAW is wrong even
if every gate is green.

## LAW 0 — ELECTRICAL INTEGRITY outranks everything
The **netlist is sacred**. A render that shorts or opens nets is worse than
useless, no matter how clean it looks. A junction is legal ONLY where the *same*
net merges; a junction at the crossing of two *different* nets is a short, and
ERC/overlap=0 do **not** catch it. Prove the netlist with a short/open detector
(connected-components of the emitted geometry vs the intended nets) before any
visual claim. A text/bbox change must never move a wire or junction. An
exposed/thermal pad is a real pad+pin+net (usually GND), never a prose "layout
note".

## LAW 1 — VISUAL CORRECTNESS is the only judge (schematic)
The rendered PNG is the supreme arbiter. **Zero overlap of anything**: no wire
over a wire, no label over a label / pin-name / value / reference, no text over
text, no symbol over symbol. **No wire crossings at all** — never "resolved" by a
junction dot (that's a short risk, LAW 0). `overlap=0` / `ERC=0` are necessary
but NOT sufficient — they exempt cases (intrinsic pin text vs label, junctioned
crossings) that are still visually broken and can hide shorts. Open and inspect
every render like a human PCB engineer. If two things touch in the render, it is
wrong.

## LAW 2 — NEVER STOP until it is actually, fully complete
Execute continuously to the done-bar — no status checkpoints, no permission
requests, no stopping early. Done = every focused sheet is hand-drawn-clean
(LAW 1) AND ERC=0 AND the netlist is proven (LAW 0). Token/time cost is not a
constraint; only completeness is.

## LAW 3 — FOCUS on the chosen sheets first
When the user names the N most complex sheets, drive ONLY those to 100% visual
perfection before touching the rest.

## LAW 4 — NEVER soften a validator
Validators only ever get stricter. If a route/label/placement fails, place or
route it better, expand the candidate set, or improve the engine — never
suppress, exempt, relax, or fabricate a threshold. A gate that masks reality
(e.g. an optimistic RθJA) is a LAW-4 violation in the *lenient* direction: make
it honest. Improving the algorithm is the work.

## LAW 5 — PCB RATSNEST: grouped by subsystem + image-checked
Every PCB change MUST emit a **ratsnest image** (the unrouted airwires over the
placed footprints, colored by subsystem) and it MUST be visually inspected — the
LAW-1 discipline extended to the PCB. Components MUST cluster **by subsystem**
(tight per-subsystem bundles, not a board-spanning hairball). **No off-board
parts** — every footprint inside Edge.Cuts. `DRC=0` is necessary but NOT
sufficient: airwires, subsystem grouping, and off-board placement are not DRC
errors, so a ratsnest image + a hard gate (off-board / dispersion / cross-airwire
budget) are mandatory.

---

## Standing principles (corollaries of the LAWS)

- **NEVER redraw or bend a part to fit the tool.** The faithful `parts/<MPN>/`
  symbol + footprint are the source of truth. If the placer/router can't handle a
  faithful symbol, fix the *engine*, not the part. (Corollary of LAW 0/4.)
- **0 hand-built real-part symbols.** Every board part draws a faithful dossier
  (or stock-KiCad) symbol; schgen-local hand-drawn real-part symbols are
  forbidden (the `symbol_law` gate enforces it). Stock KiCad library symbols are
  fine — they're faithful, not hand-built by us.
- **Auto-paginate, never block.** Sheet density must never block the build:
  detect congestion and auto-split parts onto new page(s), cutting ONLY along a
  POWER/GROUND/PORT (merging) net — never a local SIGNAL net (a LAW-0 open).
- **Reuse, don't duplicate.** A subsystem's netlist lives ONCE in
  `subsystems/<name>/`; a consuming project references it via a thin binding, not
  a copy.
- **Per-unit, byte-identical.** A pure refactor keeps the golden renders
  byte-identical; ship per unit with `schgen check` green; a new gate/law lands
  with a mutant that proves the kill.
