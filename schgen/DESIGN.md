# schgen — netlist-first KiCad schematic generator (greenfield)

## Goal
One subsystem (an active component + all its passives) is authored as a single
`.py` file. `schgen` generates a `.kicad_sch` that is:
1. **Electrically correct** — the netlist KiCad extracts from the emitted sheet is
   GRAPH-IDENTICAL to the netlist declared in the `.py`. Not "ERC=0" (gameable —
   the old generator once "passed" by marking the FUSB302's power pins No-Connect);
   actual net-by-net, pin-by-pin equivalence proven via `kicad-cli sch export netlist`.
2. **Visually correct** — datasheet-reference-circuit style, wire-heavy: drawn wires
   within the subsystem, power symbols for rails, hier labels only for the external
   interface. Zero overlap of anything, zero wire crossings, hand-drawn quality.

## Why the old generator failed (lessons encoded here)
The old pipeline made GEOMETRY the source of electrical truth: place parts, draw
wires with a router, then patch (junction rules, touch-guards, net-token floods,
repair passes). Electrical truth depended on line segments touching within an eps —
so every fix traded shorts for opens, and in-memory "opens=0" disagreed with KiCad's
real ERC (stubs landed NEAR pins, not ON them). Validators became targets to satisfy
instead of ground truth (the No-Connect cheat).

## Architecture (correct by construction)

### 1. Netlist model (`model.py`) — the single source of truth
The `.py` declares every part and every pin→net assignment explicitly. Helper
macros (`decouple`, `pullup`, `series`) expand into parts+nets, so authoring stays
concise but the result is always a fully-explicit netlist. Nets are classified:
`POWER` (+3V3, +VIN…), `GROUND` (GND family), `SIGNAL` (internal), `PORT`
(external interface → hier label at sheet edge).

### 2. Symbols (`symbols.py`)
Symbols are loaded from KiCad libs / the local lib, with a hard invariant enforced
at load: every pin connection point lies on the 1.27 mm grid. Cramped stock symbols
get local re-pinned copies (the proven lever: CP2102N_UART, TPS2051CDBV_OTG).

### 3. Placement (`place.py`) — datasheet templates, channels reserved
Deterministic per-pattern layout: IC centered; decoupling caps in a tidy row with a
shared rail wire above and GND symbols below; pull-ups vertical to rail symbols;
series/inline elements on the signal path; signals fan left/right. Placement
RESERVES routing corridors as first-class geometry. Output: part positions +
corridor map. If routing later fails, placement EXPANDS spacing and re-runs —
the feasibility loop lives here, never in relaxed checks.

### 4. Routing (`route.py`) — exclusive ownership, no eps
Integer grid (1.27 mm). Each net routes as a Steiner tree. INVARIANTS:
- A cell is owned by AT MOST ONE net, ever (vertex-disjoint ⇒ no touching AND no
  crossing, structurally — not checked after the fact, impossible during).
- Wire endpoints land EXACTLY on pin coordinates (integer grid, no eps anywhere).
- Junction dots only at degree≥3 vertices INSIDE one net's own tree.
- Power/GND pins terminate at a power symbol placed pin-exact; PORT nets terminate
  at a hier label placed pin-exact on a stub.
A net that cannot route → placement expands. Never a label fallback for an
internal net (wire-heavy mandate), never a relaxed rule.

### 5. Emit (`emit.py`)
S-expression writer. Pins/wires/junctions written at exact integer-grid coords.
Reference/Value text placed by the same overlap rules as everything else.

### 6. Gates (`verify/`) — written FIRST, immutable during implementation
- `netlist_gate.py`: emit → `kicad-cli sch export netlist` → parse → compare to the
  declared netlist as a labeled bipartite graph (net↔pins). PASS = isomorphic with
  matching net names for POWER/GROUND/PORT nets and matching pin sets for all nets.
  Any single-pin `unconnected-(...)` net for a pin that has a declared net = FAIL.
  Any No-Connect on a pin with a declared net = FAIL (the cheat is structurally caught).
- `visual_gate.py`: zero bbox overlap of any two of {body, pin-name, pin-number,
  Reference, Value, label, wire}, zero perpendicular wire crossings, zero collinear
  same-axis overlaps between different nets' wires (ports of this session's
  /tmp/audit.py + /tmp/gate.py detectors).
- `erc_gate.py`: `kicad-cli sch erc` errors == 0 (necessary, not sufficient).
  Fragment-sheet policy (M3): `pin_not_driven` runs at WARNING — the same
  policy as the hand-audited carrier project — because a standalone
  subsystem's PORT-net inputs are by construction driven only after
  hierarchical assembly, and KiCad counts no global-label shape as a driver
  (verified empirically). The build compensates with a STRICTER schgen-side
  check (`_check_inputs_driven`): every `input` pin must sit on a net with a
  real same-sheet driver-class pin, a power rail, or an explicit PORT net.
  Unlike KiCad's check it cannot be silenced by a stray passive on an
  internal net. Everything else stays at kicad-cli factory severity.
- Render PNG for human review on every build.

### Emit invariant learned the hard way (M3)
The root sheet uuid MUST be reused as the symbol-instance path
(`/<root-uuid>`, not `/`): otherwise KiCad cannot resolve instance
references, and every net whose name would be pad-derived (no label, no
power symbol — i.e. every plain internal wired net) silently drops out of
both ERC and the exported netlist while the file still LOOKS perfect.

## CLI
`python -m schgen build eda/src/schgen/subsystems/usb_pd.py -o out/`
→ writes `usb_pd.kicad_sch`, `usb_pd.png`, prints the three gate verdicts.
Build FAILS (non-zero exit) unless ALL gates pass.

## Board linker (`schgen link`, P3)
`python -m schgen link [subsystems...]` (default: all of `carrier/subsystems/`).
- **Typed ports** (`model.py`): `c.port(..., kind=...)` / `c.port_type(net, ...)` —
  kinds `single | diff_pair | usb_hs_pair | tmds_pair | i2c | sd_bus`. Pair kinds
  carry `pair_with` + differential impedance (90R default USB, 100R default TMDS);
  i2c carries role/bus/speed; sd_bus carries `level_v`. Untyped ports stay `single`.
  `expect="..."` is the EXPLICIT deferral for ports whose binding subsystem lands in
  a later wave — never a silent skip.
- **Linking** (`link.py`): every PORT must resolve to a same-named PORT on another
  sheet or a SoM net in `carrier/som_interface.json`. One enumerated alias map for
  rail spellings only (`+VIN`<->`VIN`); signals never fuzz — near-misses are
  name-drift ERRORS (the detector caught the real `ZYNQ_ETH_MDI_0_P` vs
  `ETH_PHY_MDI0_P` drift). Errors: undefined port, name drift, pair polarity,
  kind/impedance/sd-level mismatch. Warnings: deferred ports, unbound SoM nets.
- **Board gate** (`board.py`): re-emits each sheet with true hierarchical labels and
  board-unique references (U1 -> U101/U201), generates a root `board.kicad_sch`
  (sheet symbols + hier pins mirroring each sub-sheet label's shape, stub + GLOBAL
  label per port — a root LOCAL label on a multi-pin sub-sheet net trips a
  kicad-cli label_dangling false positive, minimal-repro'd), keeps ONE PWR_FLAG per
  rail board-wide, then PROVES via `kicad-cli sch export netlist` on the root that
  every port net and rail comes back as ONE net with every expected pin. Root
  ERC = 0 (same `pin_not_driven`-as-warning fragment policy as single sheets).
- **Constraints** (`constraints.py`): `carrier/out/layout_constraints.kicad_dru` +
  `.csv` — JLC04161H-7628 geometry (90R diff 0.2611/0.2032 mm, 100R diff
  0.2052/0.2032 mm, JLCPCB calculator values for THIS stackup; the 0.127/0.127
  figures circulating belong to the thinner 3313 prepreg), net classes per typed
  port, length-match groups per pair/bus.
- **Diagram** (`diagram.py`): `carrier/out/block_diagram.svg` from the port graph.

## Milestones
M1: model + gates + emit a hand-placed trivial RC subsystem end-to-end (proves the
    gates + emitter). M2: FUSB302 (usb_pd) — the hardest cluster — fully generated,
    all gates green, render eyeballed. M3: CP2102N, ethernet magnetics. M4: the
    remaining carrier subsystems; multi-sheet assembly is a later, separate stage.
