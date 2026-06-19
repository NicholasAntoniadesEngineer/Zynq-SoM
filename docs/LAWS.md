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

**3D is also the judge.** Every PCB change MUST also be inspected in 3D
(`schgen render3d` → `carrier/renders/3d_{top,persp}.png`, via `kicad-cli pcb
render`): every component must show a faithful 3D body (or be a DOCUMENTED
unmatched part in the `model3d` coverage gate — never a wrong-size body, which is
worse than none), with nothing floating, mis-oriented, or colliding. The
raytraced PNG is not byte-deterministic, so it is inspected, not golden-checked —
but it is not optional. Open it and look, like a human.

**Every part's 3D model must RESOLVE (HARD) and MATCH the footprint (render
oracle).** "Has a clause" is not enough — swapping the real EasyEDA `.wrl` for
generic stock bodies left them off-center / wrong-size / 90°-rotated. So:
- **HARD** (`model3d` gate fails the board): every custom footprint references a
  3D model FILE that RESOLVES on disk (or is a documented no-faithful-body
  exception). This is the un-fakeable part — it catches the real bug (a
  bare/unresolvable path → an empty 3D viewer).
- **SOFT** (reported, not failed): a size heuristic flags a model whose XY bbox
  is grossly off the `F.Fab` body (e.g. a 90°-rotated FFC flips the aspect). It
  is NOT hard — a connector's housing legitimately exceeds its fab pin-outline
  and `F.Fab` parsing is format-fragile, so a hard size gate false-fails real
  parts.
- **The render is the definitive fit/position/orientation oracle** (`schgen
  render3d` → eyeball it, LAW 5). Prefer the part's own real `.wrl` (model +
  footprint co-generated → matches by construction) over a generic stock body.

## LAW 6 — MECHANICAL & USE-CASE PLACEMENT: the board must be physically buildable and connectable
A board that passes every electrical gate can still be unbuildable or unusable.
`DRC=0` and a passing ratsnest do NOT catch a connector you cannot plug into, a
button you cannot press, or a part crushed under a module. Placement AND
ORIENTATION must match each part's real-world use, judged like a professional PCB
layout engineer:

- **Off-board connectors live on the board EDGE, mating face pointing OFF-BOARD.**
  Every connector that mates with an external cable / plug / card (USB-C, HDMI,
  RJ45, microSD, FFC/FPC ribbon, audio, barrel, an external-loom header, ...)
  MUST sit on a board edge with its opening / slot / cable-exit facing off the
  board, so the mate physically inserts. An off-board connector in the interior,
  or rotated so its mouth faces inward, is WRONG even with every gate green. The
  placer must ROTATE each such connector to its edge (never place it
  axis-aligned) and seat it flush to the edge; the rest of its subsystem packs
  behind it, inward.

- **At the ABSOLUTE edge — the mouth must reach the board edge.** "On the edge"
  is not enough: the connector's outermost PAD seats at the copper-edge clearance
  (~0.4 mm) so the shell / slot / mouth physically reaches or slightly OVERHANGS
  the Edge.Cuts. A connector recessed even ~2 mm inboard cannot mate (the cable's
  overmold hits the board first). The off-board test for "is this part on the
  board" is judged on COPPER (pads), not the courtyard — an edge connector's
  mating area (USB-C shell, SD slot, RJ45 jack, PMOD module outline) legitimately
  overhangs the edge while its copper stays on-board.

- **Mating-face direction is VERIFIED from geometry + the 3D model, never trusted
  from a hand table alone.** Which way a connector's mouth faces in its footprint
  LOCAL frame is determined from the PAD layout (the SMT tails mark the board /
  back side; the opening is the contact/slot side or the side opposite the tails,
  per the part type) AND the 3D model's rotate must match it. A hand-coded
  mating-face value OR a stray model `(rotate)` has repeatedly faced connectors
  INWARD while `placement_mech` passed (camera FFC, USB-C, HDMI, RJ45 each hit
  this). KiCad rotates footprints CLOCKWISE (y-down) — get the handedness right.
  The 3D render is the final judge: eyeball every connector's opening.

- **Connectors that mate SIMULTANEOUSLY need an overmold gap.** Two cables plugged
  at once (HDMI TX + RX, dual USB, stacked RJ45) need a real clear gap between the
  receptacles (>= ~20 mm for HDMI) or only one overmold fits at a time. The edge
  packer reserves this gap beside any wide-overmold cable connector — adjacency
  with the default tight clearance is WRONG for these parts.

- **A module / mezzanine / display footprint is a KEEPOUT STENCIL.** The area a
  plugged-in module overhangs (the SoM on its DF40s; a display over its FFC; any
  board-to-board mezzanine) is reserved: ONLY low-profile passives shorter than
  the module's standoff may sit beneath it. NO connector, IC, button, switch,
  tall part, or test point under a module body -- the module physically covers
  them. Passives there are GOOD (they use otherwise-dead space); anything else is
  wrong.

- **Controls and serviceable parts must be reachable.** A button / switch must be
  pressable (top side, accessible, grouped with its peers); a coin cell / fuse
  must be replaceable; a test point must be probeable. A control under a module,
  or buried in a cluster, is wrong.

- **Orientation follows function + assembly.** Each part's rotation and location
  reflect how it is used and built (polarity marks visible + consistent,
  heat-sensitive parts away from hot ones, decoupling under its IC's pins, ...).

Judged the LAW-1 way: open the 3D + placement render and inspect EVERY connector,
control, and part as a human integrator would -- does the cable plug in? can I
press it? is anything big under the module? is it facing the right way? -- because
`DRC=0` / ratsnest-pass are necessary but NOT sufficient. The mechanizable rules
(off-board connector ON an edge + mating-face-OUT + nothing-big-under-a-module +
controls-accessible) MUST ALSO be a HARD gate (`placement_mech` / equivalent), so
an area or airwire optimizer can never silently trade away connectability. THIS
LAW EXISTS because a densifier shrank the board 36% yet left connectors interior
and inward-facing and parts under the SoM -- every electrical gate passed and the
board was unbuildable.

---

## Standing principles (corollaries of the LAWS)

- **EVERYTHING is PROGRAMMATICALLY GENERATED — never hand-edit the output.** The
  board (`*.kicad_pcb`, `*.kicad_sch`, BOM, renders) is GENERATED by schgen from
  code + source assets. A fix is ALWAYS made in the generator (placer/router/gate
  code) or in a source asset (a `subsystems/<name>` netlist, a `parts/<MPN>`
  footprint/model) and re-emitted — NEVER by hand-editing a generated file (it
  would be silently clobbered on the next build and breaks reproducibility). When
  a rendered part is wrong, fix the rule or the asset that produced it. This is
  foundational: the value of schgen is that the board is reproducible from source.
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
- **Optimizers are re-verified against the mechanical laws.** Any automated
  placement / densification / routing pass that improves area, airwire, or speed
  MUST be re-checked against LAW 6 (connector edge + orientation, module keepout,
  control access) by BOTH the mechanical gate AND a human render inspection. A
  smaller or faster board you cannot plug into, press, or assemble is a
  REGRESSION, not a win — gate-green is never sufficient for a placement change.
