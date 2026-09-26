#include "schgen/subsystem_scaffold.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace schgen {
namespace {
std::string substitute(std::string text, const std::string& name) {
    const std::string token = "@NAME@";
    for (std::size_t pos = 0; (pos = text.find(token, pos)) != std::string::npos;) {
        text.replace(pos, token.size(), name);
        pos += name.size();
    }
    return text;
}
bool device_name(const std::string& name) {
    return name == "con" || name == "prn" || name == "aux" || name == "nul" ||
        (name.size() == 4 && (name.substr(0, 3) == "com" || name.substr(0, 3) == "lpt") &&
         name[3] >= '1' && name[3] <= '9');
}
constexpr const char* header = R"scaffold(#pragma once

#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_packages {
// PROJECT-AGNOSTIC: abstract rails and ports, never board net names.
inline const std::vector<std::string> @NAME@_rails = {"+VDD", "GND"};
inline const std::vector<std::string> @NAME@_ports = {}; // e.g. "MY_SIGNAL"

CircuitSheetIr build_@NAME@(const SubsystemMeta& meta = SubsystemMeta{},
                           const AuthoringContext& context = {});
SubsystemDefinition define_@NAME@();
} // namespace schgen::subsystem_packages
)scaffold";
constexpr const char* source = R"scaffold(#include "@NAME@.hpp"

#include <utility>

namespace schgen::subsystem_packages {
CircuitSheetIr build_@NAME@(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("@NAME@", "<title>", context);
    // Active parts are referenced from global parts/<MPN>/, never vendored:
    // AuthoringPartSelection selection; selection.ref = "U1";
    // c.use_part("MPN_IN_PARTS_DIR", selection);
    // c.net("+VDD", {"U1.VDD"});
    // c.decouple("U1.VDD", {"100n"});
    // c.net("GND", {"U1.GND"});
    // c.port("MY_SIGNAL", {"U1.OUT"}, meta.expect_kw("MY_SIGNAL"));
    // meta.bus("i2c", "DEFAULT_I2C") and meta.note("draws", "datasheet note")
    // let a project override house style without introducing board names.
    throw CircuitAuthoringError("fill in the @NAME@ netlist");
    return meta.finish(c); // applies abstract -> project bind; keep this return
}

SubsystemDefinition define_@NAME@() {
    auto interface = @NAME@_rails;
    interface.insert(interface.end(), @NAME@_ports.begin(), @NAME@_ports.end());
    return {"@NAME@", std::move(interface), build_@NAME@};
}
} // namespace schgen::subsystem_packages
)scaffold";
constexpr const char* test = R"scaffold(#include "@NAME@.hpp"
#include "schgen/catalog.hpp"
#include "schgen/subsystem_package_checks.hpp"

#include <iostream>

// No skip or expected-failure property: the unimplemented scaffold is RED.
// Board-level link/ERC/power-tree checks remain in the board pipeline.
int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: test_@NAME@ REPOSITORY PART_CATALOG");
        if (!schgen::open_part_catalog(argv[2]))
            throw std::runtime_error("cannot open live part catalog");
        schgen::SymbolLibrary symbols{std::filesystem::path(argv[1])};
        schgen::AuthoringContext context;
        context.pins = [&](const std::string& lib) -> std::optional<std::set<std::string>> {
            return symbols.pin_numbers(lib);
        };
        const auto& registered = schgen::subsystem_definition("@NAME@");
        const auto declared = schgen::subsystem_packages::define_@NAME@();
        if (registered.name != declared.name || registered.interface != declared.interface)
            throw std::runtime_error("configured native registry differs from package declaration");
        const auto result = schgen::check_subsystem_local(registered, context,
            [&](const std::string& lib) -> const schgen::SymbolDef& { return symbols.get(lib); });
        std::cout << result.summary() << '\n';
        schgen::close_part_catalog();
        return result.ok() ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
)scaffold";
constexpr const char* cmake = R"scaffold(# Selected explicitly by SCHGEN_SUBSYSTEM_PACKAGES, never auto-discovered.
# The repository's native/cmake/SubsystemPackages.cmake owns this function.
if(NOT COMMAND schgen_register_subsystem_package)
    message(FATAL_ERROR "Configure the native project with -DSCHGEN_SUBSYSTEM_PACKAGES=@NAME@")
endif()
schgen_register_subsystem_package(@NAME@)
)scaffold";
constexpr const char* metadata = R"scaffold({
  "schema": "schgen.native-subsystem/1",
  "name": "@NAME@",
  "source": "@NAME@.cpp",
  "header": "@NAME@.hpp",
  "factory": "schgen::subsystem_packages::define_@NAME@",
  "test": "test_@NAME@.cpp",
  "spice": "@NAME@.cir",
  "default_meta": {"bind": {}, "expects": {}, "buses": {}, "notes": {}}
}
)scaffold";
constexpr const char* spice = R"scaffold(* @NAME@.cir — SPICE subckt for the @NAME@ subsystem.
*
* PROJECT-AGNOSTIC: the subckt pins are the subsystem's ABSTRACT interface, NOT
* any board net. Values mirror @NAME@.cpp one-for-one (parse_si compatible).
*
* Port order: VDD GND   (GND last by convention; add the rest)

.subckt @NAME@ VDD GND
* <passives mirroring the netlist, e.g.:>
* C1 VDD GND 100n
.ends @NAME@

.end
)scaffold";
constexpr const char* readme = R"scaffold(# @NAME@ — <one-line purpose> (reusable subsystem)

A project-agnostic, self-contained native schgen subsystem. Its interface uses
abstract port and rail names; a project supplies an abstract -> real bind map.
Active parts are referenced from global `parts/<MPN>/`, never vendored.

## Package contents

- `@NAME@.cpp`: live C++ netlist builder with `SubsystemMeta` and `AuthoringContext`.
- `@NAME@.hpp`: abstract rails/ports and the explicit factory declaration.
- `@NAME@.cir`: SPICE passive network with abstract subcircuit pins.
- `test_@NAME@.cpp`: local electrical acceptance, with no skipped tests.
- `subsystem.json`: native asset/metadata contract, NOT frozen circuit output.
- `CMakeLists.txt`: opt-in source, factory registration, and test build hookup.
- `README.md`: this file.

## Abstract interface

Default rails are `+VDD` (POWER, <supply>) and `GND` (GROUND). Add real abstract
ports to `@NAME@_ports` in the header, then declare them with `c.port(...)` in
the implementation. Internal SIGNAL nets are not bindable. Update the SPICE
port order and passive values to mirror the live C++ builder.

## Implement and register

Fill in `build_@NAME@`, remove its explicit not-implemented throw, and retain
`return meta.finish(c)`. The untouched template compiles but fails its test;
an empty netlist is not an implementation. Add datasheet/dossier design notes
here and local electrical assertions to `test_@NAME@.cpp` as needed.

From the repository root, after the native scaffold integration is installed:

```sh
cmake -S native -B /private/tmp/schgen-@NAME@-build -DBUILD_TESTING=ON \
  -DSCHGEN_SUBSYSTEM_PACKAGES=@NAME@
cmake --build /private/tmp/schgen-@NAME@-build --target schgen_subsystem_@NAME@_test
ctest --test-dir /private/tmp/schgen-@NAME@-build -R '^native_subsystem_@NAME@$' --output-on-failure
```

Supply the complete semicolon-separated opt-in list when selecting several
packages, e.g. `-DSCHGEN_SUBSYSTEM_PACKAGES='@NAME@;other_package'`. The native
project's existing catalog must be available, or set `SCHGEN_SUBSYSTEM_PART_CATALOG`
to an explicitly built catalog. Building this test does not regenerate catalogs.
The generated header/build artifacts stay in the chosen binary directory.
No source edit, package publication, or registry-file rewrite occurs at build time.

The configured factory joins `subsystem_definitions()` and is therefore used by
`author_subsystem`, `native_subsystem_factories`, and native package checks.
Run the native subsystem structure check after the local test. Existing project
factory selection is separate: explicitly add a thin project adapter in the
project authoring registry; this scaffold never edits an existing project.

## Consume from native project code

```cpp
#include "schgen/subsystem_authoring.hpp"

const auto meta = schgen::parse_json_text(R"json({
  "bind": {"+VDD": "+3V3", "GND": "GND"},
  "expects": {}, "buses": {}, "notes": {}
})json");
auto circuit = schgen::author_subsystem("@NAME@", schgen::SubsystemMeta(meta), context);
```

Use `expects` for per-port linker deferrals, `buses` for bus-role overrides, and
`notes` for house-style annotations. These inputs go to the live factory, not
an archived circuit. The local test checks exact externals, symbol/pin coverage,
decoupling/EP/strap rules, unknown-name rejection, and positive metadata binds.
Board-wide link, full power tree, and board ERC remain aggregated board gates.

## Design notes

- <datasheet / dossier notes>
)scaffold";
} // namespace

SubsystemScaffold render_subsystem_scaffold(const std::string& name) {
    if (name.empty() || name.size() > 63 || name.front() < 'a' || name.front() > 'z' ||
        name.find("__") != std::string::npos || device_name(name) ||
        !std::all_of(name.begin(), name.end(), [](unsigned char c) {
            return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
        }))
        throw std::invalid_argument("subsystem name must be a portable lowercase identifier "
                                    "(1..63 characters, no double underscore or device name)");
    SubsystemScaffold result{name, {}};
    for (const auto& entry : std::vector<std::pair<std::string, const char*>>{
             {"CMakeLists.txt", cmake}, {"README.md", readme}, {"subsystem.json", metadata},
             {name + ".hpp", header}, {name + ".cpp", source}, {name + ".cir", spice},
             {"test_" + name + ".cpp", test}})
        result.files.push_back({entry.first, substitute(entry.second, name)});
    return result;
}
} // namespace schgen
