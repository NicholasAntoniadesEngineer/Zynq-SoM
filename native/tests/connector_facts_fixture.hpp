#pragma once

#include "schgen/part_facts.hpp"

#include <filesystem>

inline schgen::ConnectorFacts repository_connector_facts() {
    return schgen::load_connector_facts(
        std::filesystem::path(__FILE__).parent_path().parent_path().parent_path() / "parts");
}
