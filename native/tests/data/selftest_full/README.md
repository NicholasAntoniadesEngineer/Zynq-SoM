# Full native selftest integration

The native runner executes the original 63 mutations: 11 for `m1_rc`, 34 for
`uart_bridge`, and 18 model proofs. Every invocation rebuilds the schematics,
exports their connectivity with live KiCad, runs ERC, and evaluates the real
native verification gates. Expected test outputs are never read by production
code. No Python subprocess or fake KiCad executable participates in the proof.

## Independent reference

`python_reference.json` was captured on 2026-09-25 from the existing Python
`schgen.verify.selftest.run([])` before replacing any selftest or ratsnest logic.
The reference passed 63/63 using Python 3.14.3 and KiCad 10.0.2. Its provenance
object records source SHA-256 hashes. Recording wrappers observed the normal
build and stack functions without changing their behavior. Several of the
original Python gates already called committed native kernels; this capture
is independent of the new full runner, not an assertion that those dependencies
were still implemented in Python.

Reference SHA-256 (immutable; do not regenerate to satisfy a native mismatch):

```
74eba37bf1dd303d2ce7357722e933a8ecdfdc7f6d7d825910099b76fc67912c
```

The reference preserves the two complete circuit IRs and emitted schematics,
45 mutation descriptions, both geometry mutations for each sheet, all 47 live
stack verdicts, the full Python console report, and three ratsnest summaries.
Random injected UUIDs are intentionally not compared; the baseline schematics
and the two determinism proofs compare every byte including their stable UUIDs.

## Parent-owned integration

Add these six sources to `schgen_core`:

```
src/selftest_full.cpp
src/selftest_full_fixtures.cpp
src/selftest_full_models.cpp
src/selftest_full_json.cpp
src/selftest_full_worker.cpp
src/ratsnest_gate.cpp
```

Compile them with C++17, `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
They link the existing `selftest.cpp`, board/schematic/validation/netlist,
power/thermal/part/design-rule/SPICE/symbol-law, process, and ratsnest kernels.
Additional workstream dependencies are `pcb_checks_model.cpp` (immutable
footprint geometry preparation) and `circuit_helpers.cpp` (the actual public
mounting-hole guard). These dependency files were compiled as supplied, not
edited by this workstream. Link LibXml2 and Threads as the core already does.

Include `schgen/selftest_full.hpp`. Select/resolve the requested circuits in
the parent CLI, then pass ordered `SelftestSheetInput` values. For the default
run use `selftest_rc_fixture()` and the live project's canonical UART circuit
JSON, not the test reference. Preserve their display paths/scratch names as
desired. `selftest_model_fixtures` requires a resolved real
`Resistor_SMD:R_0603_1608Metric` footprint snapshot from
`pcb_check_footprint(source_path, exact_bytes)`; it never invents footprint
geometry. Construct `SymbolLibrary` with the repository/library paths.

Configure `SelftestFullOptions.worker_command` as an argv prefix for the native
executable, e.g. `{absolute_executable, "selftest-worker"}`. The full runner
appends two arguments: a request JSON path and a fresh output directory. Parent
dispatch for this internal command is exactly:

```cpp
std::cout << schgen::selftest_worker_emit(
    schgen::parse_json_file(request_json_path), output_directory);
return 0;
```

Catch exceptions at the ordinary CLI boundary and exit nonzero. Worker stdout
must contain only the returned schematic bytes. It rebuilds from ordered IR
and resolved symbol snapshots carried in the request; it does not search local
libraries or reload circuits. The runner spawns it via shell-free `env` with
`PYTHONHASHSEED=0` and `987654321` for compatibility with the previous proof.
The C++ process uses no Python runtime. It requires fresh files, checks stdout
against each file, compares both child builds, and compares them to the parent
build. Missing commands, child failures/timeouts, empty/stale/mismatched output,
or byte drift cannot pass. A caller's scratch directory for the standalone
hash-seed function must be fresh (the full runner guarantees this).

Call `run_full_selftest(inputs, fixtures, library, options)`; use `exit_code()`
for command status. `options.progress` receives report chunks including final
status; if unset, print `result.report` once. `keep` retains audit files; otherwise
RAII removes only the private scratch directory, including on exceptions.
`selftest_full_result_json` exposes ordered per-mutation and model evidence for
bindings. Python adapter changes and shared module/CLI/CMake edits remain
parent-owned.

`check_ratsnest(PcbCheckInput, optional_nets, optional_edges, cross_k)` is a
normal public gate. It checks real copper bounds, per-subsystem dispersion and
cross-subsystem MST length. It preserves Python finding/report order and
supports precomputed pad positions/MSTs. Missing footprint geometry and invalid
board dimensions throw. Re-prepare `PcbCheckInput` after changing placements.
The result exposes the Python dataclass fields, `summary()`, `cross_ok()`, and
`cross_ratio()`; `ratsnest_dispersion_by_sheet` supplies the keyed view.

## Proven isolated build

No shared build directory, binary, catalog or extension was written. The tested
executable is `/private/tmp/schgen-selftest-native.ISl2B3/selftest_full_contracts`.
It passed 2,318 assertions, including 63/63 live mutations, all 47 exact stack
verdicts, model diagnostic parity, both baseline schematic byte comparisons,
geometry comparisons, ratsnest parity, fresh-process determinism, and negative
worker controls. KiCad failures propagate as errors; they are never counted as
successful mutation kills. Geometry mutants require a visual failure, and the
board-port mutant requires a failure specifically for `SELFTEST_LINK`.

Build an equivalent isolated executable from the repo root (on macOS with the
existing archive, use its deployment target, currently 26.6):

```sh
clang++ -std=c++17 -O1 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -ffp-contract=off -mmacosx-version-min=26.6 -I native/include -I native/src \
  native/tests/selftest_full_contracts.cpp \
  native/src/selftest_full.cpp native/src/selftest_full_fixtures.cpp \
  native/src/selftest_full_models.cpp native/src/selftest_full_json.cpp \
  native/src/selftest_full_worker.cpp native/src/ratsnest_gate.cpp \
  native/src/pcb_checks_model.cpp native/src/circuit_helpers.cpp \
  native/build/standalone/libschgen_core.a -lxml2 -pthread \
  -o /private/tmp/schgen-selftest-native.ISl2B3/selftest_full_contracts
/private/tmp/schgen-selftest-native.ISl2B3/selftest_full_contracts \
  /Users/nicholasantoniades/Documents/GitHub/Zynq-SoM \
  /Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod
```

For CTest, link `tests/selftest_full_contracts.cpp` to the integrated core,
add `native/src` as a private include directory, and pass the repository root
and actual resistor footprint path as the two arguments. Tests require live
KiCad and actual symbol/footprint libraries. The immutable reference came from
KiCad 10.0.2; a different KiCad/library version may legitimately change emitted
bytes or diagnostic text and must be investigated, not silently waived.

The runner retains the original `thermal_waiver` mutation solely as a test of
the existing waiver semantics. It adds no production waiver or success override.
No files from other workstreams were edited and no commit was made; commits
and global integration remain parent-owned. Ledger/fallback/quantize auditing
is a separate follow-up and is not needed to run these 63 mutations.
