#pragma once

#include "schgen/json.hpp"

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace schgen {

enum class CopperRole : std::uint8_t { signal, ground, power };

struct CopperLayer {
    int ordinal = 0;
    std::string name;
    CopperRole role = CopperRole::signal;
    double thickness_mm = 0.0;
    std::string label;
};

struct DielectricLayer {
    std::string name, kind, material;
    double thickness_mm = 0.0, permittivity = 0.0;
    std::size_t above = 0;
};

struct DifferentialGeometry {
    int impedance = 0;
    double width_mm = 0.0, gap_mm = 0.0;
    std::string source;
};

struct Stackup {
    std::string fabricator, fabricator_name, summary, brief, prepreg, pair_basis;
    double thickness_mm = 0.0;
    std::vector<CopperLayer> copper;
    std::vector<DielectricLayer> dielectric;
    std::vector<DifferentialGeometry> pairs;
    const CopperLayer& reference_of(bool rear) const;
    std::vector<std::string> ground_layers() const;
    std::size_t signal_layers() const;
    bool ground_referenced(bool rear) const;
    const DifferentialGeometry* pair(int impedance) const;
    std::string pair_list(const std::string& label, const std::string& unit, const std::string& joint) const;
    std::string placement_family() const;
};

struct StackupCatalogue {
    std::vector<Stackup> entries;
    const Stackup& named(const std::string& name) const;
};

StackupCatalogue parse_stackups(const JsonNode& document);
StackupCatalogue load_stackups(const std::filesystem::path& file);
std::filesystem::path stackup_catalogue_file();
void select_stackup(Stackup stackup);
const Stackup& board_stackup();
const char* copper_role_name(CopperRole role);

}
