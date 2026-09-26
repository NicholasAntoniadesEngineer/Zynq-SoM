#pragma once

#include "schgen/example_devkit_authoring.hpp"
#include "schgen/subsystem_build.hpp"

namespace schgen {
// Compatibility/build umbrella. Pure constructor code includes only
// example_devkit_authoring.hpp, never this orchestration header.
struct ExampleDevkitOptions {
    NetlistExtractOptions extraction;
    bool no_render = false;
    std::size_t netlist_workers = 0;
};
struct ExampleDevkitResult {
    std::vector<SubsystemBuildResult> standalone;
    BoardSchematicResult hierarchy;
    std::string report;
    // Default/unexecuted results cannot pass; all four standalone and hierarchy
    // checks must have actually run. Rendering retains advisory semantics.
    bool ok() const;
};
// Consumes live authored IR, never saved placement, schematic, gate verdict or
// frozen circuit output. Explicit output directory only. The four sheet names
// and ordering form the example's positional reference-band contract.
ExampleDevkitResult build_example_devkit(const std::vector<CircuitSheetIr>& sheets,
    SymbolLibrary& library, const std::filesystem::path& output,
    const ExampleDevkitOptions& options = {});
} // namespace schgen
