#pragma once

#include "schgen/board_power.hpp"
#include "schgen/land_spacing.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <filesystem>

inline std::filesystem::path repository_parts_directory() {
    return std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "parts";
}

inline schgen::PowerPolicy repository_power_policy(const std::filesystem::path& root, const std::string& project) {
    const auto paths = schgen::resolve_project_paths(root, project);
    const auto circuits = schgen::load_project_circuits(paths);
    return schgen::load_board_power_policy(paths, circuits, schgen::load_sheet_roles(paths, circuits));
}

inline schgen::LandSpacingPolicy repository_land_spacing(const schgen::KicadNetlist& netlist, const schgen::PowerPolicy& power) {
    return schgen::board_land_spacing(schgen::load_part_facts(repository_parts_directory() / "part_facts.json"), netlist, power);
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
    project.model_overrides = schgen::model_overrides_by_part_number(facts);
    project.footprint_aliases = facts.footprint_aliases;
    project.control_grid = facts.control_grid;
}
