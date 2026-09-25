Native subsystem authoring and package gates
============================================

This work owns `circuit_helpers`, authoring/gate sources and contracts, and the
subsequently authorized Python authoring adapters. The parent owns shared builds,
CMake/module/CLI wiring, catalogs, and commits; none are changed by this worker.

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

The parent has integrated these sources and both contract targets. The following
is the source/target inventory, not an instruction to add duplicate entries.
`circuit_helpers.cpp` is separately in `schgen_core` from the selftest integration;
do not add it again. Native-package mode uses the existing `authoring_gates.cpp`
and existing contract target, with no additional source or registration entry:

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

For standalone operation without Python package files, explicitly pass
`AuthoringPackageMode::native_assets` as the final argument of both checks:

```cpp
const auto mode = schgen::AuthoringPackageMode::native_assets;
auto libraries = schgen::check_subsystem_structure(
    library_root, schgen::native_subsystem_factories(context), mode);
auto project = schgen::check_carrier_structure(
    subsystems, library_root, schgen::native_project_factories(project_kind, input), mode);
```

This is a real asset contract, not a waiver of the legacy gate. Discovery unions
the registry with visible asset folders, catching both missing registered
packages and unregistered packages. Libraries require regular `README.md` and
`<name>.cir` files, a parameterized factory, semantically valid IR and matching
nonduplicated interface. Optional library `circuit.json` is compared against the
live factory. Every project package requires regular `circuit.json` matching its
independent factory. Local project packages also require their own README/.cir;
adapters require valid native metadata and those assets in the generic library.
No `.py`, Python test, or `__init__.py` is required or evaluated. Both native-mode
gates fail empty discovery and return a hard failure through `exit_code()`.
Native summaries describe this contract, and JSON reports add
`"package_mode": "native_assets"`. Omitting the mode retains the original Python
shape, report-first library policy, and exact legacy summary/JSON bytes.

Transitional bindings (parent only)
----------------------------------

Include `schgen/authoring_bindings.hpp` in module.cpp and call
`schgen::bind_authoring(m)` once. It exposes:

* `author_subsystem_interface(name)`
* `author_subsystem(name, meta, repository)` — meta accepts None or a dictionary.
* `author_project_subsystem(project_kind, name, repository, project_root, meta=None)`
* `author_som_connector(project, ref, name, title, pins, mapping, policy, repository)`
* `authoring_subsystem_structure(library_root, repository)`
* `authoring_carrier_structure(base, library_root, project_kind, repository, project_root)`
* `authoring_bind(current_ir, mapping)` and
  `authoring_mounting_hole(current_ir, net="CHASSIS_GND", ref=None)`.

The gate bindings retain legacy package mode for adapter compatibility. Standalone
native callers select native-assets mode directly through the C++ API above.
The connector binding carries live pins and a `schgen.som_mapping.v1` dictionary.
Its policy supports `part`, `module_draw_a`, `sdio_level_v`, `sd_bus`, and `pairs`
(four-element positive/negative/kind/optional-impedance rows). Unspecified policy
fields retain the chosen project's declared defaults.

Python adapters now use `schgen/core/authoring.py` for transport:
all 17 library `circuit(meta)` functions and `INTERFACE`s, 43 non-SoM project
constructors (34 carrier, nine devkit), and both `som_conn_gen.py` generators
serving the remaining six project sheets. Module paths, constants, public
signatures, `Meta` objects and mutable live `META` dictionaries are preserved.
The connector adapters transport live module policies and `contract_pins()`
results, including custom names/titles and edited maps/current budgets.
`Circuit.bind` and `mounting_hole` use native edits while retaining borrowed
`Part`/`Net` identity, pin lists, counter reservations and failed-edit rollback.

Legacy constructor/helper bodies remain under explicit `_legacy_*` names for
equivalence checks and the existing Python-source component-basis census. They
are not production fallbacks. Do not delete them or their module-level basis
declarations until that census has a native implementation and equivalence has
been validated. The generic Python `Circuit` DSL outside bind/mount remains a
compatibility surface; production library/project constructors execute C++.

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

Adapter validation passed 927 focused tests, plus independent checks of all 88
library parameter/error fixtures (including `Meta` object transport), all 49
project fixtures, eight dynamic connector fixtures and object-identity/counter
mutations. Re-run the unchanged focused suite after the parent module rebuild:

```sh
.venv/bin/python -m pytest -o addopts= -q \
    schgen/tests/test_model.py schgen/tests/test_subsystem_lib.py \
    schgen/tests/test_circuit_ir.py subsystems carrier/subsystems devkit_mini/subsystems
```

The native gate contract additionally assembles a private tree of all 17 library
and 49 project packages with no Python files, verifies both modes independently,
and exercises missing/malformed assets, registry omissions/duplicates, metadata,
interface drift, snapshot divergence and constructor errors. Fixtures in
`data/authoring` remain unchanged; these package mutations exist only in scratch.
