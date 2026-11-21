#pragma once

#include "schgen/land_spacing.hpp"
#include "schgen/part_facts.hpp"

#include <filesystem>

inline schgen::LandSpacingPolicy repository_land_spacing(const schgen::KicadNetlist& netlist) {
    return schgen::board_land_spacing(schgen::load_part_facts(
        std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "parts" / "part_facts.json"), netlist);
}

inline schgen::ConnectorFacts repository_connector_facts() {
    return schgen::load_connector_facts(
        std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "parts");
}
