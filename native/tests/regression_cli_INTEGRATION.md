# Native regression command handoff

Only the new regression header, source and tests are owned by this change.
No CMake/main/project CLI changes, shared builds, commits, or full-board runs
were performed. Complete board-command acceptance remains pending the parent's
board audit being green; the process-double tests are not that acceptance.

## Parent integration

Add `src/regression_cli.cpp` to `schgen_core` (uses existing `json`, `process`
and public LibXml2 linkage). Include `schgen/regression_cli.hpp` in main, and
dispatch **before** `run_project_command`, which claims leading `--repo` and
`--project` options:

```cpp
if (const auto status = schgen::run_regression_command(argc, argv))
    return *status;
```

Advertise `check --tests-dir BUILD [--repo ROOT] [--project NAME_OR_PATH]
[-o DIRECTORY]`. `check --help` already has command-specific help without
opening catalogs, configuring/building anything, spawning children, or writing.

Add these targets/tests using the existing strict flags and core linkage:

```cmake
foreach(family regression_cli regression_rc_smoke)
    add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
    target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
    target_compile_options(schgen_${family}_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
endforeach()
add_test(NAME native_regression_cli_contracts
    COMMAND schgen_regression_cli_contracts "${CMAKE_COMMAND}" "${CMAKE_CTEST_COMMAND}")
set_tests_properties(native_regression_cli_contracts PROPERTIES TIMEOUT 120)
add_test(NAME native_regression_rc_smoke
    COMMAND schgen_regression_rc_smoke_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_regression_rc_smoke PROPERTIES
    TIMEOUT 120 LABELS "live-kicad")
```

Do not conditionally omit the RC smoke when KiCad is absent. It is a required
live gate, not a success-by-skip fixture. It accepts `--kicad-cli PATH` after
ROOT if the parent needs to pin the CTest executable configuration.

The regression driver requires these named live/RC entries in the build's
inventory, all enabled and with built executables:

- `native_regression_rc_smoke`
- `native_selftest_full_contracts`
- `native_board_live_contracts`
- `native_board_pipeline_live_contracts`
- `native_render_models_live_contracts`
- `native_example_devkit_live_contracts`
- `native_single_sheet_live`

These are minimum coverage anchors, **not a filter**. Every other test in the
selected configured native build also runs. Adding new contracts needs no driver
change. Missing conditional selftest registration is an explicit preflight
failure, not an excuse to reduce the bar. Configure and build the entire native
suite before invoking `check`; this command never builds it itself.

## Command behavior and evidence

```text
schgen check --tests-dir /absolute/native-build --repo /absolute/repo \
  --project devkit_mini --output /private/tmp/regression-results --timeout 3600
```

The driver creates a unique `regression-XXXXXX` directory under the requested
output parent, or under system temporary storage by default. It never deletes
that evidence or overwrites an older run. Native board output is directed into
its `board/`; native selftest receives `--keep` and writes `selftest.txt` there.
Child commands are the resolved actual `argv[0]`, not a guessed `native/bin`
path. `--repo` becomes the child working directory; project strings remain
literal arguments. Board is not given `--no-render`, selected subsystem names,
or any audit/gate bypass. CTest uses its own configured KiCad paths; a supplied
`--kicad-cli` is forwarded to board and selftest only, as the help states.

Before board publication, CTest's real `--show-only=json-v1` inventory must be
nonempty, its cache must name `ROOT/native` with `BUILD_TESTING` enabled, every
entry must have a built executable, and no entry may be disabled or directly
invoke a shell/Python interpreter. All configured tests run serially, with
`--stop-on-failure --output-on-failure --no-tests=error`, no regex/label filters,
and an explicit JUnit path. A zero CTest exit alone is insufficient: the JUnit
must contain every inventoried name exactly once, all actually run and passing,
with no skipped/disabled/errors/failures. Missing/malformed/DTD/incorrect result
documents fail. The command does not parse human `PASS` tokens as evidence.

Stage order is board, selftest, then all CTest contracts (including RC smoke).
Child nonzero exits stop immediately and propagate. Signals return `128+signal`,
timeouts return 124, launch errors return 126/127, invalid inputs/evidence return
2. The per-stage wall-clock timeout is positive integer seconds 1..86400,
default 3600; inventory is capped at 30 seconds. CTest receives the same default
per-test timeout and also has the independent whole-process bound. Process
groups are killed and reaped on timeout. `--config` is forwarded to both CTest
inventory and execution. There is no production runner-injection API.

Each stage retains exact binary stdout/stderr files (including partial output
on timeout), length-prefixed argv, and exit/timeout/signal status. Console output
is replayed while running; the raw files are authoritative and untruncated.
`result.txt` is created only after all child stages and JUnit verification pass.
CTest's own build-directory logs and the unique run's `ctest-results.xml` remain.

## Independent contracts and isolated proof

Strict flags: C++17, `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`.
ASan/UBSan also use `-fsanitize=address,undefined -fno-omit-frame-pointer`.
Private executables are in `/private/tmp/native-regression.2Daxfx`:

- `driver-strict`, `driver-asan`: **184 assertions**. The test-only executable
  simulates board/selftest only under a private, explicitly marked fixture repo;
  these branches do not exist in production. Real CMake/CTest exercise a private
  test build. Malformed-evidence negatives explicitly select the test executable
  as a mock CTest. Proves CLI validation/dispatch, actual argv0/PATH resolution,
  literal metacharacters, output boundaries, complete inventory (including an
  extra non-anchor test), ordering, real CTest fail-fast, board/selftest/CTest
  and inventory timeouts, killed descendants, signal/launch failures, retained
  binary/partial logs, skip/disabled/missing/unbuilt/shell rejection, and refusal
  of forged/missing/DTD result documents. This is subprocess proof, not a fake
  board or full native-suite acceptance result.
- `rc-strict ROOT`, `rc-asan ROOT`: **39 checks**. Reuses independently captured
  original `m1_rc` input and expected SVG-free schematic bytes from existing
  immutable schematic fixtures. Validates the circuit against live symbols,
  proves all six original pin coordinates, re-emits exact native bytes, and
  invokes actual KiCad netlist extraction and ERC. Physical open/short mutants
  fail connectivity. Removing PWR_FLAG keeps connectivity passing but fails ERC,
  independently proving that ERC has not been silently dropped. Missing KiCad
  fails explicitly. All schematic/gate/ERC evidence is retained in the printed
  `schgen-regression-rc-XXXXXX` directory.

Driver sanitizer proof compiles all its repository dependencies (`regression_cli`,
`json`, `process`, and the test) with instrumentation. RC sanitizer proof freshly
compiles its entire 15-source native closure, not an uninstrumented core archive:
`occupancy`, `seat`, `sexpr`, `emit`, `quantize`, `turn`, `pack`, `json`, `circuit`,
`atomic_file`, `som_interface`, `symbols`, `validation`, `schematic`,
`netlist_gate`, plus the test. System LibXml2/OS libraries are system binaries.
The private reproducible RC build script is
`/private/tmp/native-regression.2Daxfx/build-rc-asan.sh`. LeakSanitizer is not
supported by this macOS runtime; address/undefined sanitizer runs do not claim
leak-check coverage.

No new Python oracle/runtime/deliverable was introduced. The reused independent
fixture hashes remain:

```text
a12b7ce9dccbc2bf0361ca18086897a4b20fc678e273bad0aa28a7e1e8c00985  native/tests/data/schematic/cases.json
0a146084701e4c28830a4a9493a270156f90946bc148ade1d676e6aeab58ad85  native/tests/data/schematic/m1-rc.kicad_sch
```
