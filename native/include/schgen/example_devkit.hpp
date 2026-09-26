#pragma once

#include "schgen/subsystem_authoring.hpp"
#include "schgen/subsystem_build.hpp"
#include <map>

namespace schgen {
// This is examples/devkit_mini: four bound reusable-library sheets, NOT the
// separate twelve-sheet devkit_mini project and not a project.json loader.
struct ExampleDevkitDefinition {
    std::string name;
    JsonNode metadata;
};
const std::vector<ExampleDevkitDefinition>& example_devkit_definitions();
const std::vector<std::string>& example_devkit_shared_rails();
CircuitSheetIr author_example_devkit_subsystem(const std::string& name,
    const AuthoringContext& context = {}, const std::optional<JsonNode>& metadata = std::nullopt);
std::vector<CircuitSheetIr> author_example_devkit(const AuthoringContext& context = {},
    const std::map<std::string,JsonNode>& metadata_overrides = {});

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
