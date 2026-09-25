Native subsystem authoring and package gates
============================================

This work owns only `circuit_helpers` and the new authoring/gate sources, headers,
and contracts. No shared build, CMake, module, CLI, Python adapter, catalog, or
commit was changed. The parent owns integration and commits.

Production coverage
-------------------

* `CircuitAuthor`: part selection and live catalog fields/pin aliases, automatic
  references, net classification and ownership, NC, differential/I2C/SD port
  types, simultaneous binding with collision checks, probes, mounting holes,
  decoupling/pull/series components, loads, hints, explicit authored waivers,
  subset pages, and caller-supplied pin coverage validation.
* `SubsystemMeta`: `bind`, `expects`, `buses`, `notes`; absent versus empty
  expectations and `expects.get(default)` versus `expect_kw` remain distinct.
* All 17 reusable `circuit(meta)` implementations and declared `INTERFACE`s.
* All 37 carrier and 12 devkit_mini circuits: 21 project adapters, 22 native
  local constructors, and six SoM connector instances built from current inputs.
  devkit_mini power retains its three additional enable testpoints.
* Both structure gates, their exact existing summary text, package discovery,
  required-file checks, companion restrictions, interface drift, build failures,
  and report-first/strict versus hard-fail exit policies.

The translated C++ executes authoring operations and current catalog lookups;
it never returns a compiled or checked-in default circuit.json. All exposed
metadata remains a runtime argument. The project registry contains authored
metadata defaults, not circuit snapshots. SoM pins and mapping are loaded from
the selected project at each call, unless the caller supplies in-memory inputs.
`ProjectAuthoringInput` also permits metadata and connector-policy overrides.

The existing Python rejects some `expects` overrides in microsd,
usb_uart_connector, and usbc_otg because a later port retype conflicts. Those
errors are retained and independently tested rather than silently dropping the
parameter. Typed metadata values must be strings; individual expectations also
accept null. Invalid shape/type, duplicate keys, and empty binding targets fail.

CMake integration (parent only)
------------------------------

`circuit_helpers.cpp` is already in `schgen_core` from the parent's selftest
integration; do not add it again. Add only these remaining sources; the patterns
match only this implementation:

```cmake
file(GLOB authoring_builders CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/subsystem_authoring*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/project_authoring*.cpp")
set(authoring_sources src/authoring.cpp
    src/authoring_ir.cpp src/authoring_gates.cpp ${authoring_builders})
target_sources(schgen_core PRIVATE ${authoring_sources})
set_source_files_properties(${authoring_sources} PROPERTIES
    COMPILE_OPTIONS "-ffp-contract=off")
foreach(family subsystem_authoring authoring_gates)
    add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
    target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
    target_compile_options(schgen_${family}_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_${family}_contracts COMMAND schgen_${family}_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
endforeach()
```

Native/CLI calls
----------------

Open the existing part catalog through the established boundary, then create
`make_authoring_context(repository)` to retain a symbol-library snapshot for pin
checking. Call `author_subsystem(name, SubsystemMeta(meta), context)` for a generic
library and `subsystem_definition(name).interface` for its declared interface.
`authored_circuit_json(circuit)` returns complete canonical transport data.

For project authoring, set `ProjectAuthoringInput.project_root` and `.context`,
then call `author_project_subsystem(project_kind, name, input)`. Project kinds
are `carrier` and `devkit_mini`; unsupported projects fail explicitly. A copied
project can retain its kind while supplying another project_root. A new project
can register its own factories using the public gate factory types.

Evaluate `check_subsystem_structure(library_root,
native_subsystem_factories(context))` and `check_carrier_structure(subsystems,
library_root, native_project_factories(project_kind, input))`. Publish via
`write_authoring_gate_report(path, result.summary())`. Return
`SubsystemStructureResult::exit_code(strict)` (default report-first) and
`CarrierStructureResult::exit_code()` (always hard). Empty carrier discovery
fails; empty library discovery retains Python's vacuous report-first PASS.

Gates retain the repository's current .py/README/test/.cir package-shape contract
while obtaining callable/signature/metadata declarations from native factories.
They do not parse or execute retained Python source. Unregistered packages fail
with an explicit missing-native-factory diagnostic. An adapter's companion JSON
is compared against an independent native constructor; never register a loader
of that same companion as its own authoring factory.

Transitional bindings (parent only)
----------------------------------

Include `schgen/authoring_bindings.hpp` in module.cpp and call
`schgen::bind_authoring(m)` once. It exposes:

* `author_subsystem_interface(name)`
* `author_subsystem(name, meta, repository)` — meta accepts None or a dictionary.
* `author_project_subsystem(project_kind, name, repository, project_root, meta=None)`
* `authoring_subsystem_structure(library_root, repository)`
* `authoring_carrier_structure(base, library_root, project_kind, repository, project_root)`
* `authoring_bind(current_ir, mapping)` and
  `authoring_mounting_hole(current_ir, net="CHASSIS_GND", ref=None)`.

The gate bindings return all package fields, counts, status, and exact summary.
Keep Python wrappers as transport only (`Circuit.from_ir(native_result)`), while
preserving their public signatures and result dataclasses. No adapter edits were
authorized in this worker, so those edits remain with the parent. Mounting-hole
callers retaining Python authoring counters should pass their selected ref.

Verification and immutable fixtures
-----------------------------------

Run without touching shared build outputs:

```sh
bash native/tests/run_authoring_contracts.sh "$PWD"
AUTHORING_SANITIZE=1 bash native/tests/run_authoring_contracts.sh "$PWD"
shasum -a 256 -c native/tests/data/authoring/SHA256SUMS
```

The script copies the existing archive into a fresh /private/tmp directory,
compiles owned sources in four parallel jobs with C++17, strict warnings,
`-ffp-contract=off`, and `NDEBUG`, then runs both standalone contracts. It does
not run shared CMake or publish a module, CLI, or catalog. Sanitizer mode adds
ASan/UBSan to the owned sources and tests and privately recompiles the 11 archive
members used by the contracts. This keeps libc++ vector annotations consistent
across translation units; mixed instrumented/uninstrumented objects produce a
container-overflow diagnostic in the archive JSON parser. No sanitizer checks
are disabled, and the original archive is never replaced.

Independent original Python output was captured before the native changes:
88 library parameter/error cases, all 49 original project circuits, 66 package
reports and three summaries, plus eight altered SoM connector cases. These are
checked-in, immutable test inputs. The production code never loads them.
The temporary capture and translation scripts have been removed; no migration
Python tools are deliverables or build/runtime dependencies. The native contracts
consume these preserved fixture bytes directly. Do not regenerate reference
bytes to make a failing test pass.

Additional contracts verify current catalog changes, stacked pin aliases,
counter restoration/reservation, electrical ownership, binding collisions,
pair reciprocity, metadata/testpoint renaming, subset/coverage checks, real
companion drift in both directions, malformed IR, missing files/factories/meta,
extra companion code, sync duplicates, callback failures, current-report
mutation, and report publication bytes.
