# Native subsystem scaffold integration (parent / Copernicus)

New files only; no shared build, module, CLI, registry, or existing package edits
are made by this worker. The generated package contains C++ source/header/test,
README, SPICE, `subsystem.json`, and opt-in CMake registration. It is deliberately
unimplemented, not a frozen netlist or a green skipped test.

## Proven handoff

- 162 strict C++17 unit/publication/registry/electrical contracts pass, also with
  `PATH=/nonexistent`.
- The same 162 contracts pass with all 18 linked translation units rebuilt with
  ASAN+UBSAN (`-fsanitize=address,undefined -fno-sanitize-recover=all`), without
  suppression or mixed instrumented/uninstrumented core objects.
- 76 isolated generated-source/CMake/CTest assertions pass: two packages
  (`widget`, C++ keyword `class`), paths with spaces, expected stub failure,
  successful live implementations, metadata/interface mutations, missing
  assets, missing explicit registration, duplicate/traversal selections, and
  a deliberately removed production registry hook. Restored implementations
  pass again. These are real compile/run outcomes, not CTest WILL_FAIL/skip gates.
- No shared build or existing package/registry/CLI/CMake file was edited.
  Source registration and CLI publication remain owner-applied integration steps.

Private proof binaries: `/private/tmp/subsystem-scaffold.xqIrYm/contracts`,
`/private/tmp/subsystem-scaffold.xqIrYm/build_contracts`, and
`/private/tmp/subsystem-scaffold-sanitized.snMKYe/contracts`. The build-contract
test deletes its own generated scratch tree on completion. Immutable fixture
hashes are in `subsystem_scaffold_SHA256SUMS`.

## Source list and tests (parent)

Add these four translation units to `schgen_core` with C++17 and
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`:

- `src/subsystem_scaffold_templates.cpp`
- `src/subsystem_scaffold_publish.cpp`
- `src/subsystem_registration.cpp`
- `src/subsystem_package_checks.cpp`

Link `tests/subsystem_scaffold_contracts.cpp` with the core and Threads, register
the executable as `native_subsystem_scaffold_contracts REPOSITORY`. The test
creates/removes only its own temporary directory. It exercises real no-replace
publication, including concurrency and a child-process file-size-limit failure.

`tests/subsystem_scaffold_build_contracts.cpp` is a separate private-build smoke
test. Arguments: `REPOSITORY CORE_ARCHIVE CMAKE_EXECUTABLE`. It copies the current
registry into private scratch, applies the required hook there if not yet
integrated, extracts the exact CMake module below, and compiles generated packages
against the archive. No shared build tree, binaries, catalogs, or sources change.
The untouched generated stub must fail CTest; implemented source must pass;
metadata/interface mutations must fail. No Python is used.

## Authoring API hook (Copernicus, or parent coordinating with Copernicus)

In `src/subsystem_authoring.cpp`, include `schgen/subsystem_registration.hpp`.
Wrap the existing initializer without changing its entries:

```cpp
static const std::vector<SubsystemDefinition> definitions =
    append_configured_subsystem_definitions({
        // all existing built-in definitions, unchanged
    });
```

Do not add mutable global registration or static registration constructors.
The immutable result is initialized on first access. The compiler-generated
header contains explicit references to each selected live package factory, so
static-library dead stripping cannot silently discard a registration. Duplicate
names fail closed; no configured package shadows a built-in. Existing callers
of `subsystem_definitions()`, `subsystem_definition()`, `author_subsystem()`, and
`native_subsystem_factories()` need no API change. Project-specific adapter
registration remains explicit and separate; scaffold never modifies it.

## CMake integration (parent owns applying this)

Save the following exact block as `native/cmake/SubsystemPackages.cmake`. After
`include(CTest)` and after `schgen_core` exists, call:

```cmake
include(cmake/SubsystemPackages.cmake)
schgen_configure_subsystem_packages(schgen_core "${CMAKE_CURRENT_SOURCE_DIR}/..")
```

The module requires the source-list and registry hook above. It never invokes
the scaffold publisher or edits source files. Empty package selection preserves
the built-in-only build. New packages are deliberately opt-in via
`-DSCHGEN_SUBSYSTEM_PACKAGES='widget;another_package'`.

<!-- BEGIN TESTED CMAKE MODULE -->
```cmake
include_guard(GLOBAL)

function(schgen_register_subsystem_package name)
    if(NOT DEFINED _schgen_expected_package OR NOT "${name}" STREQUAL "${_schgen_expected_package}")
        message(FATAL_ERROR "Subsystem registration is only valid inside explicit package selection")
    endif()
    get_property(registered TARGET "${_schgen_package_target}" PROPERTY SCHGEN_PACKAGE_NAMES)
    if("${name}" IN_LIST registered)
        message(FATAL_ERROR "Duplicate subsystem package registration: ${name}")
    endif()
    foreach(asset "${name}.cpp" "${name}.hpp" "test_${name}.cpp" "${name}.cir" README.md subsystem.json)
        if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${asset}" OR IS_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/${asset}")
            message(FATAL_ERROR "Missing native subsystem asset: ${CMAKE_CURRENT_SOURCE_DIR}/${asset}")
        endif()
    endforeach()
    target_sources("${_schgen_package_target}" PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/${name}.cpp")
    set_property(TARGET "${_schgen_package_target}" APPEND PROPERTY SCHGEN_PACKAGE_NAMES "${name}")
    set_property(TARGET "${_schgen_package_target}" APPEND PROPERTY SCHGEN_PACKAGE_HEADERS "${CMAKE_CURRENT_SOURCE_DIR}/${name}.hpp")
    if(BUILD_TESTING)
        add_executable("schgen_subsystem_${name}_test" "${CMAKE_CURRENT_SOURCE_DIR}/test_${name}.cpp")
        target_link_libraries("schgen_subsystem_${name}_test" PRIVATE "${_schgen_package_target}")
        target_compile_features("schgen_subsystem_${name}_test" PRIVATE cxx_std_17)
        target_compile_options("schgen_subsystem_${name}_test" PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME "native_subsystem_${name}" COMMAND "schgen_subsystem_${name}_test"
            "${_schgen_package_repository}" "${SCHGEN_SUBSYSTEM_PART_CATALOG}")
    endif()
endfunction()

function(schgen_configure_subsystem_packages target repository)
    get_property(already TARGET "${target}" PROPERTY SCHGEN_PACKAGES_CONFIGURED)
    if(already)
        message(FATAL_ERROR "Subsystem packages already configured for ${target}")
    endif()
    set_property(TARGET "${target}" PROPERTY SCHGEN_PACKAGES_CONFIGURED TRUE)
    get_filename_component(_schgen_package_repository "${repository}" ABSOLUTE)
    set(SCHGEN_SUBSYSTEM_PACKAGES "" CACHE STRING "Explicit native subsystem package names (semicolon separated)")
    set(SCHGEN_SUBSYSTEM_LIBRARY_ROOT "${_schgen_package_repository}/subsystems" CACHE PATH "Native subsystem asset library")
    set(SCHGEN_SUBSYSTEM_PART_CATALOG "${_schgen_package_repository}/native/catalog.bin" CACHE FILEPATH "Existing live part catalog for local tests")
    if(NOT SCHGEN_SUBSYSTEM_PACKAGES)
        return()
    endif()
    set(_schgen_package_target "${target}")
    set(seen "")
    foreach(name IN LISTS SCHGEN_SUBSYSTEM_PACKAGES)
        string(LENGTH "${name}" name_length)
        if(NOT name MATCHES "^[a-z][a-z0-9_]*$" OR name MATCHES "__" OR name_length GREATER 63 OR
           name MATCHES "^(con|prn|aux|nul|com[1-9]|lpt[1-9])$")
            message(FATAL_ERROR "Invalid portable subsystem package name: ${name}")
        endif()
        if("${name}" IN_LIST seen)
            message(FATAL_ERROR "Duplicate selected subsystem package: ${name}")
        endif()
        list(APPEND seen "${name}")
        set(package "${SCHGEN_SUBSYSTEM_LIBRARY_ROOT}/${name}")
        if(NOT IS_DIRECTORY "${package}" OR IS_SYMLINK "${package}" OR NOT EXISTS "${package}/CMakeLists.txt")
            message(FATAL_ERROR "Missing native subsystem package: ${package}")
        endif()
        if(package MATCHES "[\";\n\r]")
            message(FATAL_ERROR "Unsupported character in native package path")
        endif()
        set(_schgen_expected_package "${name}")
        add_subdirectory("${package}" "${CMAKE_CURRENT_BINARY_DIR}/subsystem-packages/${name}")
        get_property(registered TARGET "${target}" PROPERTY SCHGEN_PACKAGE_NAMES)
        if(NOT "${name}" IN_LIST registered)
            message(FATAL_ERROR "Package did not explicitly register a live factory: ${name}")
        endif()
    endforeach()
    get_property(headers TARGET "${target}" PROPERTY SCHGEN_PACKAGE_HEADERS)
    set(header "#pragma once\n#include \"schgen/subsystem_authoring.hpp\"\n")
    foreach(path IN LISTS headers)
        file(TO_CMAKE_PATH "${path}" path)
        string(APPEND header "#include \"${path}\"\n")
    endforeach()
    string(APPEND header "namespace schgen {\ninline std::vector<SubsystemDefinition> configured_subsystem_packages() {\nreturn {\n")
    foreach(name IN LISTS registered)
        string(APPEND header "subsystem_packages::define_${name}(),\n")
    endforeach()
    string(APPEND header "};\n}\n}\n")
    set(generated "${CMAKE_CURRENT_BINARY_DIR}/subsystem-registration")
    file(MAKE_DIRECTORY "${generated}")
    file(CONFIGURE OUTPUT "${generated}/schgen_configured_subsystems.hpp" CONTENT "${header}" @ONLY)
    target_include_directories("${target}" PRIVATE "${generated}")
    target_compile_definitions("${target}" PRIVATE SCHGEN_CONFIGURED_SUBSYSTEMS=1)
endfunction()
```
<!-- END TESTED CMAKE MODULE -->

If enabling additional packages in the full suite, the existing baseline
`subsystem_authoring_contracts.cpp` assumes exactly 17 built-ins and a saved
oracle for every registry entry. Preserve its 17 baseline comparisons, but
filter that fixture loop to the original built-in names; run each configured
package's C++ electrical test separately. Do not generate reference fixtures for
new package output or silently exclude it from native structure checks.

## Explicit CLI publication (parent)

Expose a dedicated `subsystem-new NAME` dispatch, not a board build side effect:

```cpp
#include "schgen/subsystem_scaffold.hpp"
const auto result = schgen::scaffold_subsystem(repository_root / "subsystems", name);
std::cout << schgen::subsystem_scaffold_summary(result);
```

Reject `--force` before calling the function. Publication accepts no force mode;
every existing destination, including empty directories and symlinks, is a
collision. Validate arguments before publication, catch exceptions with nonzero
exit, and do not invoke publication in dry-run/check paths. Pure previews use
`render_subsystem_scaffold(name)` and write nothing. The library root must already
exist; the library root itself cannot be a symlink. Source names use portable
lowercase identifiers (1–63 bytes, no double underscore or DOS device name).
These are deliberate safety changes from Python `isidentifier()` / `--force`.

The publisher stages a complete package privately in the same library directory
and uses Darwin `renameatx_np(RENAME_EXCL)` / Linux `renameat2(RENAME_NOREPLACE)`.
It never uses overwrite-capable rename as a fallback. Failure before publication
cleans only owned staging files. Failure to fsync the parent after successful
publication is reported as a durability warning, not a false rollback. A process
crash can leave an identifiable hidden staging directory; subsequent calls do
not delete or reuse it. No interpreter, subprocess, model snapshot, or shared
catalog build is involved in production scaffold rendering/publication.

## Asset and policy compatibility

`data/subsystem_scaffold/python_reference.json` captures original Python output
before migration. SPICE bytes are preserved except for the source filename
extension `.py` -> `.cpp`. Abstract default rails remain `+VDD`, `GND`; the same
four metadata channels (`bind`, `expects`, `buses`, `notes`) reach `SubsystemMeta`.
The README is intentionally rewritten for real native commands/APIs. The old
skipped Python tests are replaced by executed C++ acceptance. Local hard policy
remains decap/EP/strap; I2C/reset board-context findings are advisory locally.
Missing symbols, pin incompleteness, empty builders, metadata loss, and interface
drift fail rather than exploiting legacy symbol-resolution skips. The existing
`AuthoringPackageMode::native_assets` structure gate already accepts retained
README/SPICE assets and independently calls the registered live factory.
