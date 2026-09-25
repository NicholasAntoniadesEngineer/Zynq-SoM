# Native PCB emission handoff

The five emission translation units consume a placed `PcbModel` and immutable
footprint documents. They generate PCB bytes, project settings, and design rules
from live input. They do not invoke Python, resolve installed libraries, or read
golden outputs. The parent owns CMake, module/CLI integration, adapters, and commits.

The recovered WIP could not compile because `PcbCheckCopper` has no `locked`
member. `PcbModel::copper_locks` now carries emission-only overrides by copper
index, preserving the shared checker API. An absent override locks an escape via;
thermal vias remain unlocked. Keep overrides aligned when replacing/reordering
the copper vector; clear them when installing newly generated escape copper.

Other completed fixes preserve unrelated project integers above 2^53, match
Python Unicode whitespace stripping when shortening header/switch labels, retain
escape metadata whose interface hash is missing, and reject nonfinite typed
geometry before the spatial index. Source and contract files have been formatted.

## Parent integration

Add these sources to `schgen_core` exactly once:

```cmake
target_sources(schgen_core PRIVATE
    src/pcb_model.cpp src/pcb_embed.cpp src/pcb_emit.cpp
    src/pcb_project.cpp src/pcb_silk.cpp)
set_source_files_properties(
    src/pcb_model.cpp src/pcb_embed.cpp src/pcb_emit.cpp
    src/pcb_project.cpp src/pcb_silk.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
```

The checks stage must supply `src/pcb_checks_model.cpp` and
`src/pcb_checks_escape.cpp` (footprint snapshots and escape-plan transport).
All remaining kernels are already in the existing core archive. Public headers
are `schgen/pcb_model.hpp` and `schgen/pcb_emit.hpp`; internal headers are
`pcb_emit_internal.hpp` and `pcb_project_defaults.hpp`.

Register the contract executable with two explicit paths:

```cmake
add_executable(schgen_pcb_emit_contracts tests/pcb_emit_contracts.cpp)
target_link_libraries(schgen_pcb_emit_contracts PRIVATE schgen_core)
target_compile_options(schgen_pcb_emit_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_pcb_emit_contracts COMMAND schgen_pcb_emit_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/pcb_emit"
    "${CMAKE_CURRENT_BINARY_DIR}/pcb-emit-contract-output")
```

Pass the selected project's `ProjectConfig` to `pcb_emit_policy(config)` so its
header/switch descriptions are explicit. The default policy has no project
descriptions. Native placement can populate `PcbModel` directly; transitional
transport uses `pcb_model_from_json(json, pool)`, where each pool key is the
snapshot's `source` string and each snapshot comes from
`pcb_check_footprint(source, exact_bytes)`. Mirrored instances require a bottom
side and a snapshot source whose parent directory is `.mirrored_fp`.

Call `write_pcb(model, pcb_path, policy)`,
`write_pcb_project(model, pro_path, policy)`, and
`write_pcb_design_rules(model, dru_path, policy)`. The corresponding render
functions return bytes without writing. Each writer publishes atomically;
rendering failure leaves an existing destination intact. A project read uses the
shared strict JSON parser plus token metadata, so unchanged fields preserve
integer/float spelling and integers beyond double's exact precision. Callers
editing `PcbProjectDocument::data` should remove the edited path's integer token.
The shared parser's finite-double numeric range still applies when reading JSON.

Print `PcbEmissionResult::diagnostics` in order and merge each `fallback_events`
entry into the caller's fallback census once. Each `thermal_via_lattice` entry
means one actually seated lattice via. The result also reports hidden/moved
reference counts. Placement, escape generation, verification gates, external
KiCad DRC/fill, manufacturing reports, and CLI exit policy remain caller stages;
emission does not claim any of those gates passed. The model still derives from
`PcbCheckModel`, so checks consume the same poses, sources, and copper.

## Independent fixtures and verification

`carrier` and `devkit_mini` contain real placed models, exact footprint bytes,
original project input, and Python-produced `.kicad_pcb/.kicad_pro/.kicad_dru`
outputs. `mutations.json` has 47 frozen cases covering rotated/mirrored/bottom
geometry, thermal lattice/shortfall/overlap, no GND, escape obstacles, PMOD
ordering, descriptions, keepouts, and JSON number types. These original nine
files retain their recovered bytes.

`edge_cases.json` adds independently captured Python outputs for large project
integers and mixed via lock states. `unicode_strip.json` adds a real LDO with two
synthetic courtyard obstacles that force the shortening branch: the original
case named `header-shortening` did not actually shorten its label. The new input
checks NBSP, em space, an ASCII information separator, and ideographic space.
Expected bytes were captured before the corresponding native fix.

`SHA256SUMS` pins all eleven data files. The C++ contract checks these hashes,
full byte equality, diagnostic/fallback/stat parity, model metadata round trips,
fresh pose mutation, immutable source documents, all three writers, and invalid
input/failure preservation. It never regenerates expected data.

Run the original Python authoring orchestration without changing any golden file:

```sh
cd /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM
pcb_reference_dir=$(mktemp -d /private/tmp/pcb-emission-reference.XXXXXX)
PYTHONPATH=. .venv/bin/python native/tests/data/pcb_emit/audit_reference.py "$pcb_reference_dir"
```

The audit verifies the six Python source hashes and substitutes only captured
footprint reads and reference-count instrumentation. It uses the existing native
geometry kernels called by the original Python emitter; it does not call the new
C++ emission orchestration. All 52 models match PCB/project/rules bytes and
diagnostics/fallbacks (and mutation stats).

Isolated strict build against the existing archive, from the repository root:

```sh
pcb_emit_build=$(mktemp -d /private/tmp/pcb-emission-contracts.XXXXXX)
clang++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -mmacosx-version-min=26.6 -O1 -g -I native/include \
  native/src/pcb_model.cpp native/src/pcb_embed.cpp native/src/pcb_emit.cpp \
  native/src/pcb_project.cpp native/src/pcb_silk.cpp \
  native/src/pcb_checks_model.cpp native/src/pcb_checks_escape.cpp \
  native/tests/pcb_emit_contracts.cpp native/build/libschgen_core.a \
  -lxml2 -pthread -o "$pcb_emit_build/contracts"
"$pcb_emit_build/contracts" native/tests/data/pcb_emit "$pcb_emit_build/output"
```

The macOS deployment flag matches the supplied archive. Omit it for a Linux
archive. No shared CMake build is needed for this validation.

For ASan+UBSan, use the same compile/link command with
`-fsanitize=address,undefined -fno-omit-frame-pointer`, a separate executable, and
these extra source arguments **before** the archive so the entire linked core
closure is instrumented:

```text
native/src/occupancy.cpp native/src/seat.cpp native/src/sexpr.cpp
native/src/emit.cpp native/src/quantize.cpp native/src/turn.cpp native/src/pack.cpp
native/src/embed_fp.cpp native/src/pcb_scan.cpp native/src/json.cpp
native/src/atomic_file.cpp native/src/schematic.cpp native/src/power_checks.cpp
native/src/thermal_checks.cpp
```

Run with `ASAN_OPTIONS=halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1`.
The validation executables and generated outputs for this handoff are under
`/private/tmp/pcb-emit-finish.ykO650`. Both builds must report **473 checks passed**.
The ASan linker map confirms every linked project object was instrumented.

Separate existing issue: `SCHGEN_NATIVE_TRACE=1` passes `devkit_mini` but the
retained Python oracle inside `silk.py::_place_clear_label` rejects `carrier` at
an exact intermediate float comparison (`171.71300000000002` versus `171.713`).
This is in the shared label-placement kernel/oracle, outside these owned files.
It was not suppressed or used as a passing gate. Ordinary original-Python
emission and the native emitter match all frozen final bytes exactly.
