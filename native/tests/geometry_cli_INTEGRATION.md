# Native floorplan / compose CLI handoff

Owned new files only: `include/schgen/geometry_cli.hpp`, `src/geometry_cli.cpp`,
`tests/geometry_cli_contracts.cpp`, and `tests/data/geometry_cli/legacy_cli.json`.
No existing solver, gate, project loader, CLI, CMake, board pipeline, fixture or
generated project artifact is edited by this family.

## Parent integration

Add `src/geometry_cli.cpp` to `schgen_core` with C++17 and
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`. It uses only existing native
core dependencies (board authoring, schematic extraction, board inputs, floorplan,
compose repair and full board pipeline). No new library or existing ABI change.

In `main.cpp`, include `schgen/geometry_cli.hpp` and dispatch **before**
`run_project_command`, whose leading `--repo`/`--project` handling would otherwise
claim geometry invocations:

```cpp
if (const auto status = schgen::run_geometry_command(argc, argv)) return *status;
```

Add main help entries for `floorplan [--export]` and
`compose [--measure | --repair [--dry-run] [--allow-intent NAME:FROM->TO] ...]`.
The new dispatcher owns command-specific parser/help. It throws normal exceptions
for the existing main error boundary, returns nullopt for other commands, and does
not need a module binding or modifications inside project_cli.

```cmake
add_executable(schgen_geometry_cli_contracts tests/geometry_cli_contracts.cpp)
target_link_libraries(schgen_geometry_cli_contracts PRIVATE schgen_core)
target_compile_options(schgen_geometry_cli_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_geometry_cli_contracts COMMAND schgen_geometry_cli_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/.."
    --system-temp)
add_test(NAME native_geometry_cli_live_contracts COMMAND schgen_geometry_cli_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/.."
    --system-temp --live-kicad)
add_test(NAME native_geometry_cli_apply_contracts COMMAND schgen_geometry_cli_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/.."
    --system-temp --live-apply)
set_tests_properties(native_geometry_cli_live_contracts
    native_geometry_cli_apply_contracts PROPERTIES LABELS "live-kicad")
set_tests_properties(native_geometry_cli_apply_contracts PROPERTIES TIMEOUT 300)
```

Each invocation makes a unique child scratch directory; proof outputs are retained.
Use `--system-temp` for CTest, since native builds inside the repository are
correctly forbidden production geometry output roots. Explicit private scratch
parents outside the repository remain supported for independent runs.
Offline mode does not open a catalog or run KiCad. Live modes require the normal
already-built catalog, KiCad and installed symbol/footprint assets. The bounded
`--live-apply` negative proof requires real ngspice, selects the real KiCad executable
by absolute path, and deliberately makes the trusted audit compiler unavailable.
It verifies the actual compiler-spawn error is a mandatory failure and the edit is
rolled back. This is NOT full-board acceptance or a substitute for the parent's
future green source-audit/full-apply proof. Missing prerequisites in other modes
are failures, never successful skips. `--live-apply` includes the read-only tests.

## Production input and output contract

`load_geometry_board_inputs(paths, extraction)` is reusable by the parent's probe
CLI: replace its local author/link/private-schematic block with this function.
The caller must open and retain `paths.part_catalog_file`. The geometry command
does that itself. It returns a value-owned `PcbPlacementInput` after:

1. `author_board_pipeline_inputs(paths)` executes every registered native project
   factory. Native authoring validates the fresh IR; canonical circuit.json is NOT
   loaded as a circuit source.
2. Stable sheet bands are extended in memory, never written back.
3. Actual authored sheets are linked against selected SoM contract/mapping; invalid
   links throw before schematic emission.
4. `build_board_schematic` emits, extracts and gates a fresh hierarchy in a mode-700
   mkdtemp directory, with RAII cleanup on success and failure.
5. Its root is independently extracted, passed with the authored circuits/valid
   link to the existing `load_board_inputs`, and the extended bands are retained.

No cached schematic, netlist, placed board, fixture model or gate callback exists.
The existing loader supplies config, SoM outline, exact footprint documents,
contracts, signal specs, return-path dossiers and prior escape sidecar. No loader
field additions or schema changes are required. Floorplan uses the existing
zone/prepare/build/report APIs; compose uses the existing full placement builder.

Artifact root is `--output DIRECTORY`, default selected project:

- `floorplan`: `docs/FLOORPLAN.svg` and `docs/FLOORPLAN.md`.
- `floorplan --export`: `floorplan.json` only, derived from the CURRENT spec/inputs.
- `compose`: `reports/compose_ledger.json` and `.md`.
- `compose --repair` without dry-run: spec mutation is ALWAYS the selected
  **PROJECT/floorplan.json**, even with a separate artifact root. The existing
  driver performs optimistic concurrency checks and exact rollback. Full-board
  outputs go to the selected artifact root. This distinction is stated in help.

Output directories and individual destinations are preflighted before expensive
work and rechecked before publication. Symlinks, special files, hard-linked output
files, source-tree overlaps, ancestors of inputs and other project roots are
rejected. Full apply preflights the complete existing board output tree. Output
replacement is explicit, individually atomic, not an all-files transaction. Failed
repairs restore the spec, NOT artifacts already emitted by the full board pipeline.

The fixed apply host calls `run_board_pipeline` with `native_policy=true`, no
blessing, no supplied declarations/verdicts, no conditional mandatory-gate bypass.
`--no-render` has the same optional-render meaning as the existing board command
and is valid only for apply. In-place board generation retains the existing common
carrier fanout ratchet behavior; isolated output preserves that source baseline.
The common in-place ratchet path is also preflighted and disclosed in help.

## Legacy semantics / explicit native differences

Original `cmd_floorplan`, nested `_cmd_compose`, parser registration and existing
native compose driver were inspected before implementation. The unmodified old
compose argparse registration was independently AST-executed for eleven cases.
Reference SHA-256:
`e2ae44430d9e1b471d27f952453642cbe77653c4df20a7c4143a93e2c9453911`.

Preserved: default measure; repair wins over measure; dry-run records ledgers but
does not apply; repeated intent order; intent/dry-run flags are inert without
repair; max-steps remains reserved (ONE selected edit); original terminal floorplan
notices; current-plan export; advisory floors trigger repairs but do not become hard
gates. The existing independent compose fixtures/contracts retain edit, prediction,
ranking, measurement, acceptance, concurrent-edit and rollback coverage unchanged.

Explicit native parser differences: duplicates (except repeatable intent/help),
unknown/cross-command options and empty values reject; max-steps is a checked signed
32-bit decimal token (no overflow, Python underscore/Unicode numeral coercion).
Help works without project/catalog/KiCad inputs. Printed artifact paths are absolute
so private `--output` roots remain usable outside the repository. Fresh private
schematic gating is stricter than relying on the old previously built schematic.

## Proof checkpoint

Strict isolated compilation passed against a private copy of the parent's coherent
fast archive (precision + bulk process update), SHA-256
`22d1dcf3745f89d87da370f93228d4b33118ccb313595aa5993cb92a953dab6b`.
No shared build or artifact regeneration was invoked.

Offline: **182 assertions PASS**. Live render/export/measure/dry-run passed with all
canonical circuit JSON and cached schematic/PCB/netlist inputs poisoned, preserving
all source bytes. A live advisory-contract mutation produces six eligible ranked
repair candidates; no fixture model or predicted verdict is used as board proof.

The two old-archive, unbounded source-audit runs were terminated (private scratch
only); neither is claimed as successful proof. The coherent-archive bounded live
suite completed: **935 assertions PASS**, including both real full-pipeline negative
runs, missing trusted-compiler hard failures, exact spec rollback, unchanged source
and shared baseline bytes, and retained failed-board artifacts. This is negative
rollback proof, NOT positive full-board acceptance. Positive apply remains with the
parent after its complete source audit is green.

Proof directory:
`/private/tmp/geometry-cli.aNcCw8/current-proof/geometry-contracts-fqGz5h`.
The executable was `contracts-current` in that same private family root. Offline
mode also passed all 182 assertions with `PATH=/nonexistent`. Independent carrier
measurement passed at 168x163 mm and retained both real advisory triggers.

**Geometry source/header/tests are frozen for parent integration.** No further
shared-source work or builds were performed; old private evidence is preserved.
