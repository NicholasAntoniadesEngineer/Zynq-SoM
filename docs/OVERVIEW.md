# Zynq-SoM

A Zynq-7000 system-on-module + carrier board, with `schgen` — a netlist-first
KiCad schematic **and PCB** generator using C++ netlist definitions
to produce checked schematics and placed boards with component models and
multi-angle renders. Routing is deferred; these are not fabrication-ready boards.

The current published placement review is a **162×151 mm carrier** and
**98×98 mm devkit**. See the [release generation recipe and limitations](docs/RELEASE-2026-10-16.md)
to reproduce the committed images; the default commands below do not select
the carrier's qualified compact-placement recipe.

## Native build and test entry point

The C++ migration's Python-free build, dependency bootstrap and complete native
CTest entry point are documented in [`native/ci/README.md`](native/ci/README.md).
Use that path for native production builds. The transitional Python extension
and its build script are retired. Native `schgen check --tests-dir BUILD` runs
the full board, mutation/determinism selftest and complete CTest inventory.
All 393 inventoried tracked Python sources and tests are retired, along with
their dependency and lint configuration. Clean-tree acceptance is still in
progress; the commands below use the native executable.
All verification remains local, as required by the repository's no-CI policy.
No hosted workflow or gate bypass is introduced.

## The layers

1. **`parts/`** — one folder per physical part, named by MPN, GENERATED from
   LCSC/EasyEDA (`native/bin/schgen part-import --parts-root parts --lcsc C…`):
   pin table, symbol, footprint, 3D. Courtyards enclose body and pads with
   the KiCad Library Convention clearance (`schgen part-courtyard`).
   See `parts/README.md`.
2. **`subsystems/`** — project-agnostic subsystem assets: interface contracts
   and independent reference data. C++ netlist
   factories live in `native/src/authoring_*.cpp`; project adapters supply
   `bind`/`expects`/`buses`/`notes` metadata through the native registry.
   Scaffold a new one with `native/bin/schgen subsystem-new <name>`.
3. **`carrier/subsystems/`** — board subsystem assets and generated circuit
   projections. C++ project factories and adapters in `native/src/project_*.cpp`
   define the netlists; the J1/J2/J3 connector contract is extracted live from
   the SoM. Parts are resolved by library identity and named pins. See
   `carrier/README.md`.
4. **The board** — `schgen` derives ALL geometry from netlist topology,
   proves it (netlist-equivalence + ERC + zero-overlap visual gates) and
   links the sheets into one KiCad project.

Plus `som/` — the hand-authored Zynq SoM KiCad project (open
`som/Zynq_SoM.kicad_pro`, KiCad 9+; its custom libs live in `som/lib/`).
The SoM↔carrier contract `carrier/som_interface.json` is extracted
programmatically (`schgen som-interface`), never hand-edited.

## Native regeneration

```bash
native/bin/schgen board --project carrier --timing
native/bin/schgen board --project devkit_mini --timing
# Diagnostic generation without output renders:
native/bin/schgen board --project carrier --no-render --timing
```

`--no-render` is diagnostic: it skips output renders, not mandatory electrical,
geometry or source-policy gates. Omit it for rendered acceptance. Use `--timing`
to measure this native implementation; historical Python timings do not apply.

`schgen build <name>` gates a single sheet (preview into a tempdir, nothing
committed). `schgen board` regenerates the committed outputs in place:
`carrier/Zynq_Carrier.kicad_pro` (open in KiCad), `schematic/`, `renders/`
(golden-snapshot drift detection), `reports/`,
`manufacturing/` (JLC BOM + layout constraints), and
`fpga/Zynq_Carrier_pins.xdc` — Vivado PACKAGE_PIN + IOSTANDARD for every
carrier port on a Zynq PL ball, ball map live-extracted from the SoM and
cross-checked against `som_interface.json` (also standalone: `schgen xdc`).

## The gate model

Every build fails unless every gate passes — the gates are judges, not knobs.
Schematic gates: **netlist** (KiCad's extracted netlist == the declared netlist,
pin for pin, so a junction that merges two nets is caught as a short), **ERC**
(zero errors), **visual** (zero overlap, zero wire crossings, junction-aware
short detection, fits the page). PCB gates: **DRC** (zero KiCad errors),
**3D-model** coverage + placement, **ratsnest** subsystem clustering, and
**connector** mating-face / spacing (off-board mouths, edge-flush). Architecture
+ gate definitions: `schgen/DESIGN.md`.

Local generation always runs its gates; native CTest is an additional check,
not a replacement. `schgen selftest` mutation-tests the gates themselves:
it injects one defect per class (pin swap, deleted wire, relabel, stray
no-connect, foreign-net junction short) and proves a gate kills each, then
builds twice and byte-compares for determinism.

```bash
native/bin/schgen selftest
```

## Adding a board

A board is a folder of data; the compiled application builds it unchanged. Write these, in the order
`schgen board-check` checks them (its rows name each file and key):

1. `<board>/board.json`: `schema`, `name` (= the folder name), `files.stem`, `root_readme`, `owned_groups`,
   `module.folder`/`pairs`/`loads`, `power.sources`/`rails`/`inlet`, and `sheets` (library subsystems by
   name with `settings`/`additions`, or module-connector sheets with `module_connector` and `title`). A sheet
   row may state `density` (a whole number from 1 to 10) to give that subsystem its own layout density in
   place of the board's.
2. The module folder named by `module.folder` (`som/` today: `module.json`, `som_interface.json`); shared,
   written once per module.
3. `<board>/project.json`: `name`, `placement` (five keys), `placement_requirements`, `fpga.bank_rails`;
   optional `silk_labels`, `escape.genuine_pairs`. Unknown keys fail.
4. `schgen.json`: the board in `boards`, a `stackup` entry from `native/stackups.json`, a `density`
   entry (1 to 10; 10 is the densest and lets courtyards touch), an
   `overmold_parts` entry, and a `fabrication` entry (`fabricator`, `copper.outer_oz`/`inner_oz` equal to
   what the stack-up was published for, `finish`, `assembly_service`, `build_count`); see
   [FABRICATION.md](FABRICATION.md).
5. `<board>/som_mapping.json` (`schema`, `function_map`, `pudc_straps`, `vcco_rail_map`,
   `rebound_som_rails`, `isolated_som_rails`; optional `rail_aliases`).
6. `<board>/escape_triage.json`.
7. `<board>/research/si_spec.json` when any sheet declares a pair; optional `floorplan.json` and
   `sheet_index.json`.
8. `<board>/component_basis.json` covering every sheet and value of the board.
9. `parts/part_facts.json` rows (class, I2C devices) for any new part; power homes come from `power` in
    `board.json` and the netlist.

Then `native/bin/schgen board-check --project <board>` (non-zero until every row is present) and
`native/bin/schgen run <board>`. A first build needs no earlier output: stored ratchet baselines are
absent (fan-out held to 0, every non-search fallback to zero firings) until a person promotes the
published `reports/fanout_baseline.json` and `reports/fallback_baseline.json` into the board folder, and
the derived GENUINE pair count is printed in `reports/escape_lanes.txt` until `escape.genuine_pairs`
states it. `schgen basis-check` audits the component basis of every board folder together.

## Process + where to read more

- The working rules and process contract (the immutable LAWs, the gate stack,
  the worktree/commit discipline) live in
  [`WORKING_GUIDELINES.txt`](docs/WORKING_GUIDELINES.txt).
- Layer guides: [`parts/README.md`](parts/README.md),
  [`carrier/README.md`](carrier/README.md),
  and the engine contract [`schgen/DESIGN.md`](schgen/DESIGN.md).

<!-- schgen:gallery -->
<!-- GENERATED by `schgen gallery` — edits between these markers are overwritten -->
## Generated board + schematics

`schgen board` regenerates the placed-board 3D views, the block diagram and all 37 carrier sheets,
each PNG passing the netlist, ERC and visual gates.

<img src="carrier/renders/3d_persp.png" alt="Generated 3D board render (perspective)" width="900">

<img src="carrier/docs/block_diagram.svg" alt="Generated block diagram" width="900">

[<img src="carrier/renders/ratsnest_top.png" alt="Board ratsnest (top)" width="420">](carrier/README.md#ratsnest-views)<br>**[Ratsnest views](carrier/README.md#ratsnest-views)** — airwires per subsystem.

See **[carrier/README.md](carrier/README.md#generated-3d-board-views)** for all 8 board views + the full sheet gallery (thumbnails + descriptions).
<!-- /schgen:gallery -->
