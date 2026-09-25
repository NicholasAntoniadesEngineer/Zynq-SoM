# Frozen floorplan contracts

Captured on 2026-09-18 by temporary, inline execution of the original
`schgen/generate/floorplan.py` orchestration (last changed in `44b76af6`). Its existing native kernels were
enabled. No new Python source was added, and the native floorplan implementation
was not the oracle. Source documents and all generated/mirrored intermediate
files were captured under `/private/tmp`, not shared project outputs.

`carrier.json` and `devkit_mini.json` contain complete resolved footprint source
documents, circuit IR, zone/shape geometry, project/spec inputs, researched SI
rows, compose contracts/metrics, prior zone accounting, and independently
captured expected placement, decisions, fallback events and quantization counts.
The companion SVG and Markdown files are the original rendered bytes.
`*_geometry.json` separately freezes every real zone-shape fanout and both
punch policies (116 variants total); `*_export.json` freezes the declarative
seed generated from each saved plan. These expectations also come from the
original Python orchestration, not the new native implementation. Tests
need neither KiCad nor a Python interpreter nor an installed footprint library.

On 2026-09-25, before implementing native compose, `compose.json` was captured
by calling the unchanged Python `floorplan_compose.legalize_compact` with native
kernels enabled. Each row uses two 10 x 10 movable boxes: a at (5,5), b at
(60,5), their seeds equal those poses, one `p` offset at (5,5) per box, a
(0,0,10,10) pad union, a 100 mm board height, SoM page core (65,65,85,85),
origin (25,25), and clearance 0.3. The row supplies width, compact flag, hard
term tuples (kind,target,bound), optional a/b channel demand, and an optional
full-board fixed obstacle. The jack row adds som_j1=(40,5,50,15). Every term
is enforced, belongs to sheet a, has subject a, output ref p, and basis
`independent native migration fixture`. These independent results cover repair,
successful compaction, compaction rollback, channel spacing, SoM-jack targets,
unresolved terms, and infeasible geometry, including exact rejection logs.

`*_seed.json` was captured on 2026-09-25 by calling the original Python
`export_floorplan_spec` on the independently frozen plans, explicitly writing
only into `/private/tmp`. These are the actual indented ASCII-escaped export
bytes, including floating pull weights and final LF. Existing `*_export.json`
files remain unchanged as semantic JSON expectations. `SHA256SUMS` records
every frozen fixture; no expected value comes from native output.

The real expected boards are carrier **168 x 163 mm** and devkit **100 x 100
mm**. Those dimensions occur only in captured data, not solver policy.

Validated on 2026-09-25: **17,378 checks passed** in both the strict C++17
release run and the fully instrumented AddressSanitizer/UndefinedBehaviorSanitizer
run, including both complete board searches. All ten pre-existing oracle-file
SHA-256 hashes are unchanged. No shared CMake, module, CLI, Python adapter, or
build output was edited by the floorplan work; integration and commits remain
parent-owned.

The contract executable also contains small frozen Python seating vectors and
hand-computed geometry tests. They exercise complete pack attempts, edge width
floors, connectivity-before-area ordering, fixed and automatic sizing, both
reservation policies, fallback rollback, per-net via pricing, missing pad
geometry, source mutations, independent render-stage snapshots and malformed
typed inputs. The automatic synthetic case checks every candidate tally and
every nonzero quantization engagement, not source-code strings.

Do not replace expected outputs with results from the native implementation.
Any intentional policy change must explain its physical and accounting deltas.
For this migration, SVG, Markdown and decision-ledger text retain their legacy
wording (including historical Python-module source citations). Malformed
non-finite dimensions/coordinates now fail explicitly before reaching numeric
kernels or integer SVG extents; opaque footprint keys no longer masquerade as
source identity. SVG text sizing counts Unicode code points, as Python did.
The JSON result
adds explicit board dimensions, outline text and accounting to eliminate global
render context; legacy Plan fields retain their values.

## Parent integration

Add these owned sources to `schgen_core`:

```cmake
set(SCHGEN_FLOORPLAN_SOURCES
    src/floorplan_spec.cpp
    src/floorplan_geometry.cpp
    src/floorplan_cross.cpp
    src/floorplan_pack.cpp
    src/floorplan_compose.cpp
    src/floorplan_build.cpp
    src/floorplan_ledger.cpp
    src/floorplan_json.cpp
    src/floorplan_notes.cpp
    src/floorplan_svg.cpp
    src/floorplan_md.cpp
    src/floorplan_output.cpp
    src/floorplan_export.cpp)
target_sources(schgen_core PRIVATE ${SCHGEN_FLOORPLAN_SOURCES})
set_source_files_properties(${SCHGEN_FLOORPLAN_SOURCES} PROPERTIES
    COMPILE_OPTIONS "-ffp-contract=off")
```

Use C++17 and `-ffp-contract=off`, as for the existing deterministic placement
sources. The implementation reuses core packing, occupancy, legalization,
quantization, footprint scans, turns, JSON, atomic publication, board ref
renaming, power rail parsing and constraints APIs. There is no additional
external library requirement and no Python runtime dependency.

The compose entry point is now implemented in `floorplan_compose.cpp`:

```cpp
bool schgen::floorplan_legalize_compact(
    const schgen::FloorplanLegalizeInput&,
    std::vector<schgen::FloorplanLegalizeVar>&,
    std::vector<std::string>&);
```

Its shared typed inputs and declaration live in `schgen/floorplan.hpp`.
Floorplan owns candidate/fallback rollback and supplies selected-shape metrics;
compose applies its hard gates and returns its ordered decision log. Failed
compose calls leave the caller's movable variables untouched. Malformed input
throws. There is no missing compose dependency or stub to supply. The public
`floorplan_evaluate_terms` wrapper exposes the same typed hard/soft evaluation.

Build `native/tests/floorplan_contracts.cpp`, link `schgen_core`, and run with
this fixture directory as argument. The default mode runs the complete real
search, placement/accounting/ledger comparisons, and exact SVG, Markdown,
ledger, and exported-seed bytes from the newly solved plans. It also exercises
atomic publication/replacement and failure paths in an independently allocated
temporary directory. The explicit
`--geometry-only` mode is a diagnostic slice: it still runs synthetic full
searches and real report/estimator/ledger-replay checks, but does **not** verify
the real compose-dependent search. It must not replace the default CTest.

After adding the source list above and its `-ffp-contract=off` source property,
the parent can register the contract target inside `if(BUILD_TESTING)`:

```cmake
add_executable(schgen_floorplan_contracts tests/floorplan_contracts.cpp)
target_link_libraries(schgen_floorplan_contracts PRIVATE schgen_core)
target_compile_options(schgen_floorplan_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_floorplan_contracts COMMAND schgen_floorplan_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/floorplan")
```

Isolated verification used the existing archive, without invoking shared CMake
or changing module/CLI outputs. From the repository root, with an independently
allocated `/private/tmp` output directory:

```sh
floorplan_build=$(mktemp -d /private/tmp/floorplan-native.XXXXXX)
c++ -std=c++17 -O2 -mmacosx-version-min=26.6 \
  -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -I native/include \
  native/src/floorplan_*.cpp native/tests/floorplan_contracts.cpp \
  native/build/libschgen_core.a -lxml2 -o "$floorplan_build/floorplan_contracts"
"$floorplan_build/floorplan_contracts" native/tests/data/floorplan
```

The macOS minimum matches this existing archive's deployment target; use the
parent toolchain's target on other platforms. The release executable also runs
from `/private/tmp` with `PATH=/nonexistent`: neither Python nor KiCad is used.

Address/undefined-behavior sanitizer verification adds
`-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` and compiles every
linked core translation unit into private objects with the same flags. Mixing
the existing uninstrumented archive's inline container operations with ASan
objects causes incompatible container annotations; no ASan check is disabled
to work around that. The complete linked core dependency set for this target
is:

```
atomic_file board_schematic circuit constraints embed_fp emit json legalize
netlist_gate occupancy pack pack_anchor pack_edges pack_refine pcb_scan
place_geom place_search power_checks project project_catalog quantize route
schematic schematic_place_chain schematic_place_core schematic_place_fanout
schematic_place_pages schematic_place_templates schematic_route seat sexpr
som_interface symbols turn validation
```

Each name is `native/src/<name>.cpp`; compile these alongside all floorplan
sources and the contract source, with the toolchain's libxml2 include path.
Link the resulting private objects with `-fsanitize=address,undefined -lxml2`.
The link map must contain instrumented private objects for every core source.
Use `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1` for the full contract run.
LeakSanitizer's `detect_leaks=1` is unavailable in this macOS runtime; it is
not part of the address/undefined-behavior result.

Public API:

```cpp
auto plan = schgen::build_floorplan(input);        // physical solve once
auto docs = schgen::render_floorplan_documents(plan, input);
// Or produce a value-owned plan + rendered-document snapshot in one call:
auto stage = schgen::generate_floorplan(input);
auto paths = schgen::write_floorplan_documents(stage.documents, output_dir);
auto exported_seed = schgen::export_floorplan_spec(stage.plan); // JsonNode
auto seed_bytes = schgen::render_floorplan_spec_json(stage.plan);
auto seed_path = schgen::write_floorplan_spec(stage.plan, explicit_seed_path);
```

The PCB provider resolves footprint sources and zone geometry once, including
mirrored documents produced by `mirrored_footprint()`. Pool keys are opaque;
source identity is retained separately. Floorplan neither reopens footprints
nor transforms mirrored geometry a second time. `FloorplanRegulator` and
`FloorplanSiPair` alias the shared `PowerReg` and `PairSignalSpec` types.
Consumers can copy a stage's plan for downstream PCB placement; captured report
bytes remain independent of those mutations. Rendering has no filesystem side
effects. Publication replaces each document atomically, but is not a two-file
transaction.

Provider details: source footprint names map through `footprint_of` into the
resolved `footprints` pool; `courtyard_dims` is keyed by the library segment
before `:`. Supply source sheet insertion order, the board-ref `sheet_index`,
complete selected-shape metrics, researched `si_pairs`, prior zone accounting,
and explicit spec/project data. Compose poses, fixed rectangles, escape
corridors, and SoM-jack rectangles are board-local; `som_core_page` is in the
page frame, and `origin` is its translation from board-local coordinates.
The full builder derives its channel demand from the circuit nets as Python
did; `FloorplanLegalizeInput::channel_demand` is used by direct compose calls.
Report rendering and seed export require no Python bindings or fixture access.
