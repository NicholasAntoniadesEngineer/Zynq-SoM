# Authoring dependency separation — stable handoff

This is a dependency-boundary refactor, not a hardware, schema,
or generated-output change. Existing public signatures and result layouts are
unchanged. No immutable fixtures, geometry files, shared build products, CMake,
CLI, registry, decision manifest, or purity policy were edited by this worker.

## Owned changes

* `src/authoring.cpp`, `src/authoring_ir.cpp`, `src/circuit_helpers.cpp` now use
  new `src/authoring_values.hpp` rather than `model_checks_internal.hpp`.
  This small header contains only their string/JSON value helpers. The old
  fixed general/17-digit formatting call has an equally fixed `number17` helper;
  the 768-byte buffer exceeds the maximum representation of every double.
* New `src/authoring_context.cpp` contains
  `make_authoring_context(const std::filesystem::path&)`. The owning
  `SymbolLibrary` and pin-resolver callback are host-side setup, outside pure
  constructor translation units. Its signature remains in `authoring.hpp`;
  no edit to that Copernicus-owned header is required. The follow-up below
  replaces its anonymous callback with an equivalent named native resolver and
  adds an explicit native-policy target validator.
* `src/example_devkit.cpp` retains all original metadata and constructor bodies,
  in the same file and with the same identities. It now includes new slim
  `include/schgen/example_devkit_authoring.hpp`.
* New `src/example_devkit_build.cpp` contains `ExampleDevkitResult::ok()` and
  `build_example_devkit()` with byte-for-byte unchanged bodies.
  `include/schgen/example_devkit.hpp` remains the compatible public build
  umbrella, including both the slim authoring header and `subsystem_build.hpp`.
* New `tests/authoring_values_contracts.cpp` is a standalone, core-independent
  137-assertion contract. It covers quoting/escapes, all 29 recognized Unicode
  whitespace characters, non-whitespace/truncated/malformed UTF-8 behavior,
  floating-point diagnostic edges, lookup semantics, overloads, and exact JSON
  field/element order. NaN tokens follow the actual standard library, without
  normalizing its spelling (Apple libc++ negative quiet NaN is `-nan(ind)`).

## Parent integration required

Add these sources exactly once to `schgen_core`; the pre-existing authoring and
example source entries stay in place:

```cmake
target_sources(schgen_core PRIVATE
    src/authoring_context.cpp
    src/example_devkit_build.cpp)
set_source_files_properties(src/authoring_context.cpp src/example_devkit_build.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")

add_executable(schgen_authoring_values_contracts tests/authoring_values_contracts.cpp)
target_include_directories(schgen_authoring_values_contracts PRIVATE include)
target_compile_features(schgen_authoring_values_contracts PRIVATE cxx_std_17)
target_compile_options(schgen_authoring_values_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_authoring_values_contracts COMMAND schgen_authoring_values_contracts)
```

Do not link the new helper contract against `schgen_core`: its standalone build
is intentional. Existing subsystem/example contract targets need no source
changes. Existing `tests/run_authoring_contracts.sh`, if retained, must include
`src/authoring_context.cpp` in its explicit private source list. Otherwise an old
archive can extract the pre-split authoring member to resolve context setup,
leading to duplicate definitions. This script is not edited in this handoff.

Rebuild the changed objects and new sources coherently. Do not hot-mix a new
authoring object with an old library's still-combined example/context object.

## Copernicus purity integration boundary

Register these new helper headers under their actual paths:

* `native/src/authoring_values.hpp`
* `native/include/schgen/example_devkit_authoring.hpp`

Keep `native/src/example_devkit.cpp` covered as constructor code; all reviewed
constructor identities remain unchanged. Keep host-only `authoring_context.cpp`
and `example_devkit_build.cpp` outside the pure-unit set, while retaining normal
repository census coverage. Do not allow their symbol/build/render/publication
headers into the pure constructor closure. This handoff neither modifies nor
claims a PASS from the semantic purity scanner. Callback authority and the
existing value-parser edge remain Copernicus's policy/proof responsibility.

## Completed private proof

Private directory: `/private/tmp/authoring-boundary.tigIeb`.
The pre-edit coherent core archive was copied here, never rebuilt or modified:

`e26211c85bc7434300e96d5f0be26db2fa71998f32aaf2ffdf26eda9e8832786`

All changed/new sources compiled with C++17, `-O3 -Wall -Wextra -Wpedantic
-Werror -ffp-contract=off`, and deployment target 26.6. The after binaries link
all six split/changed source objects before that copied archive. No shared
CMake build, module, or catalog generation occurred.

Results:

* Before and after: 88 independent original-Python authoring cases, all 17
  library interfaces, live catalog/provider and helper mutation contracts PASS.
* Before offline: 14,644 example assertions, all 19 original families PASS.
* Before and after live: 14,677 example assertions, all 19 original families,
  actual four-sheet KiCad standalone/hierarchy gates, and corrupted emitted
  label rejection PASS. Real missing-wire, missing-part and geometric-short
  mutants remain exercised by these existing tests.
* Standalone helper contract: 137 assertions PASS, also under ASan/UBSan.
* Private direct comparison with the unchanged legacy model helper: 100,009
  double bit patterns/edges, 10,000 arbitrary byte strings, and every Unicode
  codepoint's whitespace classification match exactly.
* Real build before/after at the same private output path: all 27 files
  (five schematic documents, project/local settings, ERC and gate reports) and
  report stdout are byte-identical. Raw `diff -rq` and `cmp` passed; no timestamp,
  path, numeric, UUID, or text normalization was applied by the proof.
* Compiler `-MM` dependency closure for `authoring.cpp`, `authoring_ir.cpp`,
  `circuit_helpers.cpp`, and `example_devkit.cpp` contains none of symbols,
  occupancy, thermal checks, model checks, subsystem build, native render,
  board pipeline, or project output headers.
* All authoring and example immutable fixture SHA256 checks PASS unchanged.

Evidence retained:

* `subsystems-after.log`
* `example-before-live.log`, `example-after-live.log`
* `authoring-values.log`, `authoring-values-sanitized.log`, `helper-parity.log`
* `example-byte-before.log`, `example-byte-after.log`, `example-byte-diff.log`
* `example-byte-before-output/`, `example-byte-output/`
* `authoring.deps`, `authoring_ir.deps`, `circuit_helpers.deps`, `example_devkit.deps`

The before sources, archive, private C++ harnesses, and executables are retained
beside these logs. No Python implementation, fixture recapture, gate waiver,
frozen-only production output, or geometry acceptance claim is involved.

For a core-independent rerun of the new test:

```sh
c++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -I native/include native/tests/authoring_values_contracts.cpp \
  -o /private/tmp/schgen-authoring-values-contracts
/private/tmp/schgen-authoring-values-contracts
```

Authoring and example source/API files are frozen for parent integration as of
this handoff; all private proof processes have completed and been reaped.

## Follow-up: concrete closure findings and actual callback targets

Ready/frozen after the parent's bounded follow-up authorization:

* `authoring.cpp`: four concrete `by_net` overloads for mutable/const
  `CircuitPortIr` and `CircuitHintIr` vectors replace the dependent template.
  The two NC membership lambdas now take `const CircuitPinRefIr&`, resolving
  the intended `same` overload to the compiler. Algorithms/order are unchanged.
* `authoring_ir.cpp`: the NC sort lambda has two explicit
  `const CircuitPinRefIr&` arguments; the lexical tuple comparison is unchanged.
* New `include/schgen/authoring_context.hpp` declares the final named
  `NativeAuthoringPinResolver`. Only `make_authoring_context` can construct its
  private `shared_ptr<SymbolLibrary>` owner. Copies preserve the prior captured
  lambda's shared lifetime and lazy resolution. `SymbolError` still becomes
  `nullopt`; successful pin sets are identical. A moved-from resolver fails
  explicitly instead of dereferencing a null owner.
* `void require_native_authoring_context(const AuthoringContext&)` examines the
  **actual** stored targets. `part.target<CatalogPart (*)(const std::string&)>()`
  must exist and its value must equal `&lookup_part_catalog`.
  `pins.target<NativeAuthoringPinResolver>()` must exist and own a non-null
  private library. Empty targets, forwarding lambdas, same-signature foreign
  function pointers, `std::ref`, `std::bind`, and moved-from owners fail. The
  validator never executes callbacks or trusts a caller-supplied status flag.
* Existing `AuthoringContext` member types/layout, construction signatures,
  default catalog lookup, and explicit custom-provider API are unchanged.
  Validation proves native callback identity, not catalog/input readiness;
  actual loading/construction checks still must run.

### Required parent/Copernicus integration — not yet a purity PASS

Parent must include `schgen/authoring_context.hpp` at native-policy host entry
points and validate the exact context before it is captured/passed to factories:

```cpp
input.context = make_authoring_context(paths.repository_root);
require_native_authoring_context(input.context);
// Then capture/pass this context to the real authored factories.
```

In particular this applies before `native_project_factories` in
`author_board_pipeline_inputs`; apply equivalent enforcement to any other
native-policy context entry point. Do not validate one context and execute
another, mutate the context after validation, or reuse a previous acceptance
as a cache. Copies of a validated context preserve targets and ownership.
The separate public custom-provider APIs remain intentionally available for
non-native-policy callers and mutation/parameterization contracts.

Copernicus owns the semantic policy integration for these two actual-context
callback sites and `subsystem_authoring.cpp` named dispatch. Do not globally
exempt `std::function::operator()` or arbitrary callback fields. All unrelated
indirect-call mutants must remain red; runtime native validation must be wired,
not inferred from the presence of this helper. Symbol loading remains host/input
provider work, not a reason to allow geometry headers into constructor units.
Direct worker messaging was unavailable; the exact names/boundary were relayed
to the parent and recorded here for Copernicus. No purity manifest or scanner
source was changed by this worker, and no all-ten-findings PASS is claimed.

No extra production source beyond the already-listed `authoring_context.cpp`
is needed. Parent should additionally register:

```cmake
add_executable(schgen_authoring_context_contracts tests/authoring_context_contracts.cpp)
target_link_libraries(schgen_authoring_context_contracts PRIVATE schgen_core)
target_compile_options(schgen_authoring_context_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_authoring_context_contracts COMMAND schgen_authoring_context_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/..")
```

Follow-up proof: `/private/tmp/authoring-targets.HrwjK2`.
Strict C++17/-Werror/-ffp-contract=off builds PASS. New target validator tests:
46 assertions PASS (`context-contracts.log`), covering actual type/pointer/owner,
mutation-after-validation, no invocation of rejected callbacks, retained custom
providers, copied snapshot lifetime, actual native pins and unknown symbols.
Existing authoring contracts again PASS all 88 cases/17 interfaces
(`subsystems.log`); existing real-KiCad example contracts again PASS 14,677
assertions/19 families (`example-live.log`). All 27 real example output files
and raw stdout again match the pre-refactor private baseline byte-for-byte
(`example-byte-diff.log`, `example-byte-after.log`); no normalization was used.
The authoring translation units' include closures still exclude model/geometry
headers. All follow-up proof processes are complete and reaped; no shared build
or CMake/CLI/pipeline/registry edit was performed by this worker.
