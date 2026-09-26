# Legacy four-sheet example: native handoff

This batch is `examples/devkit_mini`, **not** the separate twelve-sheet
`devkit_mini` project. No existing Python source, test, schematic, render, report,
catalog, CMake/module/CLI file or tracked board asset was changed.

## Parent-owned integration

Add `src/example_devkit.cpp` once to `schgen_core`. Its public API is in
`include/schgen/example_devkit.hpp`; it reuses the parent's already integrated
`subsystem_build.cpp`, existing live reusable-library factories, native placement,
board schematic/netlist gates and native rendering. No additional dependency or
Python binding is needed by standalone callers.

Add a contract executable from `tests/example_devkit_contracts.cpp`, link it to
`schgen_core`, and run it with the repository root:

```
schgen_example_devkit_contracts REPOSITORY
schgen_example_devkit_contracts REPOSITORY --live
```

The first invocation has no external-process or publication requirements beyond
private temporary directories. It performs real symbol-backed validation and live
placement/routing. The second additionally invokes actual KiCad on generated
standalone sheets and a four-child hierarchy. KiCad absence/failure is an error,
not a passing skip. All output is in an automatically allocated private scratch
directory, deleted after the check; no reference files are modified.

Suggested parent CLI flow, after selecting/opening the existing part catalog:

```cpp
SymbolLibrary symbols(repository);
const auto sheets = author_example_devkit(make_authoring_context(repository));
ExampleDevkitOptions options;
options.no_render = no_render;
options.extraction = extraction_options;
options.netlist_workers = workers;
const auto result = build_example_devkit(sheets, symbols, explicit_output, options);
// Print result.report, return result.ok() ? 0 : 1.
```

Do not route this command through `author_project_subsystem("devkit_mini",...)`:
that is a different design. No global project switch or source-file discovery is
needed. `author_example_devkit_subsystem` accepts an optional full metadata record;
`author_example_devkit` accepts named metadata overrides and rejects unknown names.
Custom `AuthoringContext` providers affect actual library components at runtime.

## Native behavior

Original sheet order and positional reference bands are fixed: usb_pd=1,
usbc_otg=2, microsd=3, uart_bridge=4. All four metadata records match the original
Python wrapper exactly, including expectations, bus names, budgets and the UART
null-modem mapping. Production does not read recorded circuit IR or fixtures.

Standalone sheets use `build_subsystem_sheet`: electrical completeness/inputs,
fresh CC, real emitted-netlist extraction, ERC and visual checks. The hierarchy
uses `build_board_schematic` on live authored IR with no supplied placement or
gate verdict. Root ERC is actually executed and retains that API's original
informational semantics; standalone ERC remains mandatory. Rendering is advisory
and occurs after hierarchy emission, on the final uniquified child sheets, to
`renders/<name>.png`. `--no-render` does not create PNG output.

Output is explicit: `schematic/`, `reports/`, `devkit_mini.kicad_sch`, and
`devkit_mini.kicad_pro` under the caller's directory. No default points to the
tracked example. An empty/unexecuted result cannot pass. Wrong sheet count or
ordering is rejected before publication.

## Proof and fixture provenance

Private strict C++17 optimized build:
`/private/tmp/schgen-example-devkit-ZjQk7s/contracts`.
Flags: `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off -O2`.
Linked a previously copied existing core archive and compiled the new source plus
the parent's `subsystem_build.cpp` into private objects; no shared builds ran.

Final live run passed **14,677 checks / all 19 original test families**, including
actual four-sheet hierarchy export and emitted-label mutation rejection.
The extra checks also change the live part provider, exercise alternate metadata,
erase real routed wires, remove actual placed parts, and physically join distinct
nets with incorrectly annotated segments. These edits must cause real gate
failures; declared net labels do not seed successful connectivity.

The 19 retained families are:

1. Project sheet coverage/order.
2. Actual bound subsystem construction.
3. Bound names, no abstract or carrier leakage.
4. Power/ground/port classification.
5. Unknown bind rejection.
6. Private SIGNAL bind rejection.
7. Collision rejection and failed-bind atomicity.
8. Unknown metadata key rejection.
9. Per-sheet local design rules.
10. Aggregate decoupling rule engagement.
11. Per-sheet component ratings rules.
12. Actual symbol-backed model completeness.
13. Part/NC preservation and ordered net renaming.
14. Renamed-rail load budgets.
15. Shared 3V3/GND classes and ownership.
16. No accidental cross-sheet external-net collision.
17. Same library bound independently to carrier and example.
18. UART crossover belongs to the binding.
19. Fresh placement/routing produces no CC shorts or opens.

`tests/data/example_devkit/README.md` records independent capture provenance;
`SHA256SUMS` pins the four immutable JSON files. Each contains original metadata,
unbound and bound IR, and separately captured alternate metadata/IR. The existing
reusable-library constructor oracles remain under `tests/data/authoring/`.

## Removal boundary

The original `examples/devkit_mini/devkit_mini.py`, its test module, and
`schgen/generate/devkit.py` are intentionally retained pending parent integration.
The native contract target covers their 19 test families; it does not authorize
removing the tests before this target is required in the integrated test suite.
The Python CLI still imports the example generator; route/remove that caller
before deleting its module. Transitional Python compatibility, if retained, needs
data-only binding/adapter wiring to these APIs rather than a second implementation.
No current Python API was deleted in this example batch.
