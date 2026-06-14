# schgen — netlist-first KiCad schematic generator

`schgen` turns hand-authored Python **netlists** into electrically-correct,
visually-clean KiCad schematics for the Zynq-7000 SoM **carrier** board. You
author one subsystem (an active part + all its passives) as a single `.py` file
that declares every part and every pin→net assignment; `schgen` places, routes,
emits the `.kicad_sch`, and **gates** it against three immutable judges.

It is the source of truth for the board: the committed `carrier/` schematics,
BOM, FPGA constraints, firmware contract, bring-up manual, power tree, and
renders are all **generated** — never hand-edited.

> Deep architecture & rationale: [`DESIGN.md`](DESIGN.md). This README is the
> entry point — what it is, how to run it, and where things live.

---

## The laws (immutable — the gates are judges, not knobs)

1. **LAW 0 — electrical integrity.** The netlist is sacred. The netlist KiCad
   extracts from the emitted sheet must be **graph-identical** to the netlist
   the `.py` declared — net-by-net, pin-by-pin (`kicad-cli sch export netlist`,
   not gameable "ERC=0"). A short or an open is the worst possible defect. An
   exposed/thermal pad is a **real pad + pin + GND net**, never a prose layout
   note.
2. **LAW 1 — visual correctness.** Datasheet-reference-circuit style, wire-heavy,
   hand-drawn quality. **Zero** overlap of anything; **zero** wire crossings.
3. **LAW 4 — never soften a validator.** If a route/label/derate fails, place or
   route it better, or expand the candidate set — never suppress, exempt, or
   relax the rule. Improving the algorithm is the work. Every waiver is explicit,
   author-declared, and printed verbatim in the gate report.

A change is done only when **every focused sheet is hand-drawn-clean in the
render AND every gate is green.**

---

## Quickstart

```bash
# Build + gate ONE subsystem sheet into a throwaway dir (preview/CI of one sheet):
python3 -m schgen build power            # model -> place -> route -> emit -> 3 gates -> render

# Build the WHOLE board (the authoritative regen of everything committed under carrier/):
python3 -m schgen board                  # every sheet gated + link + KiCad project + BOM
                                         # + xdc + firmware + manual + power tree + renders ...

# The full regression bar (run before every commit — see scripts/check.sh):
scripts/check.sh                         # board + selftest (mutation+determinism) + m1_rc + pytest
```

`build` persists nothing (transient tempdir, auto-removed) — pass `-o OUTDIR` to
keep its artifacts. Only `schgen board` writes the committed `carrier/` tree.

---

## Authoring model

A subsystem lives in `carrier/subsystems/<name>.py` and returns a `Circuit`.
Every part and net is explicit; helper macros expand to parts+nets so authoring
stays concise but the result is always a fully-explicit netlist:

```python
def circuit() -> Circuit:
    c = Circuit("power", "+VIN -> +5V buck")
    c.use_part("LMR33630ADDAR", ref="U1",            # stock symbol + faithful footprint
               lib_id="Regulator_Switching:LMR33640ADDA",
               footprint="LMR33630ADDAR:LMR33630ADDAR")
    c.net("+VIN_SYS", "U1.2")                         # VIN pin -> rail
    c.net("GND", "U1.1", "U1.9")                      # GND + EP pad -> GND (LAW 0)
    c.port("EN_5V0", "U1.3", expect=EXPECT_BRINGUP)   # external interface -> hier label
    c.decouple("U1.2", "10u")                         # macro: cap pin->GND
    return c
```

Net classes drive everything downstream: `POWER` (+3V3, +VIN…), `GROUND` (GND
family), `SIGNAL` (internal), `PORT` (external interface → hier label + the
board-level link graph). `port(..., expect=...)` declares which other sheet (or
the SoM J-connector) supplies the peer — the linker and the board's
undriven-input gate honor it.

---

## The pipeline (correct by construction)

```
 model.py        place.py            route.py          emit.py           verify/
 ────────        ────────            ────────          ───────           ───────
 Circuit  ──▶  feasibility-loop ──▶  exclusive-grid ──▶ .kicad_sch  ──▶  3 gates:
 (explicit     placement            wire router        (content-          netlist == declared
  netlist)     (templates per       (no two nets        derived            ERC errors == 0
               part topology)        share a track)     uuid5 ids)         visual zero-overlap
```

Geometry is **derived from** the netlist, never the source of electrical truth
(the failure mode of the old generator — see `DESIGN.md`). Emission is
deterministic: ids are content-derived `uuid5`, so the same model emits
byte-identical output across runs and `PYTHONHASHSEED`s.

---

## Command surface

Run `python3 -m schgen <cmd> --help` for any command.

**Build / board**
| command | does |
|---|---|
| `build <sheet>` | generate + 3-gate one subsystem (preview; writes nothing unless `-o`) |
| `board` | the authoritative whole-board regen: every sheet gated + link + KiCad project + all downstream artifacts (`--bless` rebaselines the render goldens) |
| `link` | board-level port graph + constraints + block diagram + hierarchical root |
| `nets` | regenerate `carrier/nets.py` (the cross-sheet net-name contract) |

**Generated artifacts** (all netlist-derived, all under `carrier/`)
| command | output |
|---|---|
| `bom` | JLCPCB assembly CSV (Comment,Designator,Footprint,LCSC) |
| `xdc` | `fpga/Zynq_Carrier_pins.xdc` — PACKAGE_PIN + IOSTANDARD per port (Zynq ball map live-extracted from the SoM) |
| `vivado` | `fpga/create_project.tcl` |
| `firmware` | `firmware/zynq_carrier_contract.h` — SC-firmware HW contract (J1 pins, STM32 GPIOs, BOOTSEL decode, I2C map, rail/module EN map) |
| `devicetree` | `firmware/carrier_pl.dtsi` |
| `manual` | `docs/BRINGUP.md` — ordered bring-up procedure derived from the netlists |
| `floorplan` | `docs/FLOORPLAN.svg` + `.md` — to-scale 2D placement suggestion |
| `manifest` | `manifest.json` |
| `testplan` | `docs/TEST_PLAN.md` — probe/measure plan from the spice gate |
| `gallery` | render-gallery sections in `README.md` + `carrier/README.md` |

**Gates** (also run inside `board`; standalone for focused checks)
| command | judges |
|---|---|
| `design-rules` | completeness: every IC supply pin bypassed, every i2c bus pulled, every reset has its RC, no floating config strap, **every exposed pad netted to GND** |
| `part-rules` | per-part datasheet ratings: CAP_VOLTAGE derate, IC_VIN abs-max, RES_POWER |
| `powertree` | rail budget: every rail sourced, no regulator/eFuse over its current limit (series-shunt-aware) |
| `thermal` | per-device junction temperature vs guard band |
| `spice` | analytic + ngspice `.op` cross-check on every divider (1% agreement) |
| `selftest` | **gate mutation testing** (every injected fault must be killed) + cross-`PYTHONHASHSEED` build determinism |
| `preflight` | consolidated readiness report |

**Parts pipeline**
| command | does |
|---|---|
| `part add <LCSC>` | import a part from LCSC/EasyEDA into `parts/<MPN>/` (symbol + footprint + 3D + pins), with allowlist-keyed EP-pad and polarity-silk synthesis |

---

## Package layout (by concern)

The modules are physically flat in `schgen/` today; grouped by role:

- **Core model** — `model.py` (`Circuit`, parts, nets, macros, waivers, `subset`),
  `symbols.py` (KiCad symbol library + pin tables), `link.py` (board port graph),
  `sexpr.py` (S-expression read/write), `som_interface.py` (SoM J-connector contract).
- **Placement & routing** — `place.py` (`_Engine`, per-topology templates:
  regulator / stack-columns / chain / connector-fan / shunt cells; congestion
  auto-pagination), `route.py` (exclusive-grid router), `textmetrics.py`.
- **Emission & render** — `emit.py` (deterministic content-derived uuid5),
  `render.py` (kicad-cli PNG), `diagram.py` (block diagram).
- **Verification** — `verify/{netlist_gate,design_rules,part_rules}.py`,
  `powertree.py`, `thermal.py`, `spice.py`, `ratings.py` (LCSC-keyed datasheet
  limits), `selftest.py` (mutation + determinism), `preflight.py`.
- **Generators** — `board.py` (whole-board orchestrator), `firmware.py`,
  `manual.py`, `testplan.py`, `floorplan.py`, `gallery.py`, `devicetree.py`,
  `manifest.py`, `xdc.py`, `vivado.py`, `constraints.py`, `bringup_facts.py`
  (shared netlist-derived facts the firmware/manual/testplan generators consume).
- **Parts** — `part_gen.py` (LCSC/EasyEDA → `parts/<MPN>/` conversion).
- **CLI** — `__main__.py`.

---

## Determinism & the regression bar

`scripts/check.sh` is the bar that must be green before every commit:

1. **board** — every sheet gated (netlist==declared, ERC=0, visual zero-overlap)
   + the board-level cross-sheet link/merge gate + a geometry-only connected-
   components short/open detector.
2. **selftest** — gate mutation testing (every injected defect must be killed by
   a gate) + byte-identical determinism across `PYTHONHASHSEED ∈ {0, …}`.
3. **m1_rc** — the M1 RC-spine smoke sheet (engine sanity).
4. **pytest** — unit tests (model, gates, part_gen EP synthesis, pagination, …).

Local only — no online CI by project policy.

---

## Where things are

- `carrier/subsystems/*.py` — the authored subsystems (the input).
- `carrier/research/*.md` — per-subsystem engineering dossiers (the "why").
- `carrier/` — the generated, committed output (schematics, BOM, fpga, firmware,
  docs, reports, renders).
- `parts/<MPN>/` — the imported part library (symbol, footprint, 3D, pins).
- `schgen/tests/` — pytest suite.
