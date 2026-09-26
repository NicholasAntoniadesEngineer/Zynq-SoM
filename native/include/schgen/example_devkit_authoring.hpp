#pragma once

#include "schgen/subsystem_authoring.hpp"
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
} // namespace schgen
