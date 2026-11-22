#pragma once

#include "schgen/json.hpp"

#include <filesystem>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

class FabricatorUnverified : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct FabricatorValue {
    JsonNode value;
    std::string unit, source_url, read_utc, quote, unverified;
    bool known() const { return unverified.empty(); }
};

struct FabricatorProfile {
    std::string name, file;
    std::map<std::string, FabricatorValue> values;
    const FabricatorValue& at(const std::string& path) const;
    bool known(const std::string& path) const;
    double number(const std::string& path) const;
    std::vector<double> numbers(const std::string& path) const;
    std::string text(const std::string& path) const;
    std::vector<std::string> texts(const std::string& path) const;
    bool flag(const std::string& path) const;
    double for_copper(double oz, const std::string& key) const;
};

struct FabricationConfig {
    std::string fabricator, finish, assembly_service;
    double outer_oz = 0.0, inner_oz = 0.0;
    int build_count = 0;
};

struct FabricationSelection {
    FabricationConfig config;
    FabricatorProfile profile;
    double outer_value(const std::string& key) const { return profile.for_copper(config.outer_oz, key); }
};

FabricatorProfile parse_fabricator(const JsonNode& document, const std::string& file);
FabricatorProfile load_fabricator(const std::filesystem::path& file);
std::filesystem::path fabricator_file(const std::string& fabricator);
std::string fabricator_copper_key(double oz);
void validate_fabrication(const FabricationConfig& config, const FabricatorProfile& profile, std::size_t copper_layers,
                          double stackup_outer_oz, double stackup_inner_oz, const std::string& board);
void select_fabrication(FabricationSelection selection);
const FabricationSelection& board_fabrication();

namespace fabricator_key {
inline constexpr const char* trace = "trace_mm";
inline constexpr const char* space = "space_mm";
inline constexpr const char* mask_bridge = "mask_bridge_mm";
inline constexpr const char* annular_min = "pth_annular_min_mm";
inline constexpr const char* annular_recommended = "pth_annular_recommended_mm";
inline constexpr const char* hole_via = "fab.hole_to_hole.via_mm";
inline constexpr const char* hole_pad = "fab.hole_to_hole.pad_mm";
inline constexpr const char* npth_min = "fab.npth_min_mm";
inline constexpr const char* via_hole_min = "fab.via.min_hole_mm";
inline constexpr const char* via_over_hole_preferred = "fab.via.diameter_over_hole_preferred_mm";
inline constexpr const char* via_diameter_min = "fab.via.min_diameter_mm";
inline constexpr const char* slot_width_min = "fab.plated_slot.width_min_mm";
inline constexpr const char* slot_ratio_min = "fab.plated_slot.length_ratio_min";
inline constexpr const char* npth_slot_min = "fab.npth_slot_min_mm";
inline constexpr const char* copper_to_edge = "fab.copper_to_edge_mm";
inline constexpr const char* silk_height = "fab.silk.text_height_min_mm";
inline constexpr const char* silk_line = "fab.silk.line_min_mm";
inline constexpr const char* silk_pad = "fab.silk.pad_clearance_mm";
inline constexpr const char* bom_columns = "order_files.bom_columns";
inline constexpr const char* cpl_columns = "order_files.cpl_columns";
inline constexpr const char* layer_tokens = "order_files.layer_tokens";
inline constexpr const char* coordinate_suffix = "order_files.coordinate_suffix";
inline constexpr const char* designators_per_line = "assembly.max_designators_per_line";
inline constexpr const char* cpl_point_spacing = "assembly.cpl_point_spacing_mm";
}

}
