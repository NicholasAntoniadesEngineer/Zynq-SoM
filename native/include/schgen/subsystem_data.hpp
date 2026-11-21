#pragma once

#include "schgen/subsystem_authoring.hpp"

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* subsystem_data_schema = "schgen.subsystem/1";
inline constexpr const char* subsystem_data_file = "subsystem.json";
inline constexpr const char* subsystem_library_folder = "subsystems";
inline constexpr const char* sheet_region_board = "board";
inline constexpr const char* sheet_region_under_module = "under_module";

enum class SheetRegion : std::uint8_t { board, under_module };

struct SubsystemPlacement {
    SheetRegion region = SheetRegion::board;
    std::optional<std::string> silk_label, escape_basis;
    std::optional<double> far_guard_mm;
    bool escape_escalates = false, reserves_edge = false;
};

struct DividerLimit {
    double volts = 0.0;
    std::optional<double> lo, hi;
    std::string tag;
};

struct SubsystemDivider {
    std::string net, source, why;
    std::vector<DividerLimit> limits;
};

struct IsetWindow {
    double low_ma = 0.0, high_ma = 0.0;
};

struct SubsystemChecks {
    std::vector<SubsystemDivider> dividers;
    std::vector<std::string> divider_sources;
    std::optional<IsetWindow> iset_window_ma;
};

struct SubsystemFacts {
    SubsystemPlacement placement;
    SubsystemChecks checks;
};

SubsystemFacts subsystem_data_facts(const JsonNode& document, const std::string& source);
SubsystemFacts load_subsystem_facts(const std::filesystem::path& library, const std::string& name);

SubsystemDefinition subsystem_data_definition(const JsonNode& document, const std::string& source);
std::vector<SubsystemDefinition> subsystem_data_definitions(const std::filesystem::path& library);
CircuitSheetIr extend_subsystem_data(CircuitSheetIr sheet, const JsonNode& additions, const AuthoringContext& context);
CircuitSheetIr author_subsystem_data(const JsonNode& document, const SubsystemMeta& meta,
                                     const AuthoringContext& context);

}
