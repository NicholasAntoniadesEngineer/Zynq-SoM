#pragma once
#include "schgen/authoring_gates.hpp"
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
    std::string part;
    double module_draw_a = 2.15, sdio_level_v = 1.8;
    std::vector<std::string> sd_bus;
    std::vector<ConnectorAuthoringPair> pairs;
    std::vector<ConnectorAuthoringLoad> loads;
};
struct ProjectAuthoringInput {
    // Required only for connectors when an in-memory contract/mapping is absent.
    std::filesystem::path project_root;
    AuthoringContext context;
    std::optional<SomInterface> som;
    std::optional<LinkMapping> mapping;
    std::optional<ConnectorAuthoringPolicy> connector_policy;
    // Whole meta dictionaries, not shallow overrides. Locals default to no meta.
    // Adapter-specific post-construction additions still run after library binds.
    std::map<std::string, JsonNode> metadata;
};
struct ProjectSubsystemDefinition {
    std::string project, name;
    bool adapter = false;
    JsonNode meta;
    std::function<CircuitSheetIr(const SubsystemMeta&, const AuthoringContext&)> circuit;
    std::string connector_ref, connector_title;
};
const std::vector<ProjectSubsystemDefinition>& project_subsystem_definitions();
// The production dispatch remains compiler-visible: check the stored callable
// against its named registry target, then call that target directly. A copied or
// substituted std::function is never granted netlist capability by its type.
CircuitSheetIr author_registered_project_definition(const ProjectSubsystemDefinition&,
    const SubsystemMeta&, const AuthoringContext&);
ConnectorAuthoringPolicy project_connector_policy(const std::string& project);
CircuitSheetIr author_som_connector(const std::string& ref, const std::string& name,
    const std::string& title, const SomInterface& som, const LinkMapping& mapping,
    const ConnectorAuthoringPolicy& policy, const AuthoringContext& context = {});
CircuitSheetIr author_project_subsystem(const std::string& project, const std::string& name,
                                       const ProjectAuthoringInput& input = {});
std::vector<CarrierPackageFactory> native_project_factories(const std::string& project,
                                                           const ProjectAuthoringInput& input = {});
} // namespace schgen
