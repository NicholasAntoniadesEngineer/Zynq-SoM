#pragma once
#include "schgen/authoring_gates.hpp"
#include "schgen/board_definition.hpp"
#include "schgen/link.hpp"
#include "schgen/som_interface.hpp"

namespace schgen {
struct ConnectorAuthoringPair {
    std::string positive, negative, kind;
    std::optional<int32_t> impedance;
};
struct ConnectorAuthoringLoad {
    std::string connector, rail;
    double amps;
    std::string note;
};
struct ConnectorAuthoringPolicy {
    std::string part, module_draw_connector, module_draw_rail, module_draw_note;
    double module_draw_a = 0.0, sdio_level_v = 0.0;
    std::vector<std::string> sd_bus;
    std::vector<ConnectorAuthoringPair> pairs;
    std::vector<ConnectorAuthoringLoad> loads;
    std::string mate_symbol;
    std::map<std::string, std::string> mate_pad_names;
};
struct ProjectAuthoringInput {
    // Required only for connectors when an in-memory contract/mapping is absent.
    std::filesystem::path project_root;
    AuthoringContext context;
    std::optional<SomInterface> som;
    std::optional<LinkMapping> mapping;
    std::optional<ConnectorAuthoringPolicy> connector_policy;
    std::optional<BoardDefinition> board;
    // Whole meta dictionaries, not shallow overrides. Locals default to no meta.
    // Adapter-specific post-construction additions still run after library binds.
    std::map<std::string, JsonNode> metadata;
};
struct ProjectSubsystemDefinition {
    std::string project, name;
    bool adapter = false;
    JsonNode meta;
    std::string connector_ref, connector_title;
    std::optional<JsonNode> additions;
};
std::vector<ProjectSubsystemDefinition> project_subsystem_definitions(const std::filesystem::path& project_root);
std::vector<ProjectSubsystemDefinition> project_subsystem_definitions(const BoardDefinition& board);
std::vector<std::filesystem::path> board_folders(const std::filesystem::path& repository);
ConnectorAuthoringPolicy connector_policy_of(const BoardDefinition& board);
ConnectorAuthoringPolicy project_connector_policy(const std::filesystem::path& project_root);
CircuitSheetIr author_som_connector(const std::string& ref, const std::string& name,
    const std::string& title, const SomInterface& som, const LinkMapping& mapping,
    const ConnectorAuthoringPolicy& policy, const AuthoringContext& context = {});
CircuitSheetIr author_project_subsystem(const std::string& project, const std::string& name,
                                       const ProjectAuthoringInput& input = {});
std::vector<CarrierPackageFactory> native_project_factories(const std::string& project,
                                                           const ProjectAuthoringInput& input = {});
} // namespace schgen
