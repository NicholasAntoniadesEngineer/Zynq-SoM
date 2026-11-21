#pragma once

#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <filesystem>

inline std::filesystem::path repository_parts_directory() {
    return std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "parts";
}

inline schgen::ConnectorFacts repository_connector_facts() {
    return schgen::load_connector_facts(repository_parts_directory());
}

inline schgen::PartFacts repository_part_facts() {
    return schgen::load_part_facts(repository_parts_directory() / "part_facts.json");
}

inline void use_repository_part_facts(schgen::ProjectConfig& project) {
    const schgen::PartFacts facts = repository_part_facts();
    project.connectors = facts.connectors;
    project.isolation = facts.isolation;
    project.thermal_copper = facts.thermal_copper;
    project.regulators = facts.regulators;
    project.model_overrides = facts.model_overrides;
    project.footprint_aliases = facts.footprint_aliases;
    project.control_grid = facts.control_grid;
}
