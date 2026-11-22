#pragma once
#include "schgen/sexpr.hpp"
#include "schgen/manufacturing_exports.hpp"
#include <filesystem>
#include <optional>
#include <tuple>

namespace schgen {
struct ManufacturingFabProfile {
    std::string name;
    double min_trace_mm, min_clearance_mm, min_drill_mm, min_via_dia_mm,
        min_via_annular_mm, min_hole_to_hole_mm, min_pad_annular_mm, min_npth_drill_mm,
        min_slot_width_mm, min_slot_ratio, min_silk_height_mm, min_silk_line_mm;
    std::string source;
};
ManufacturingFabProfile manufacturing_fab_profile();
struct ManufacturingMinimums {
    double min_trace_mm, min_clearance_mm;
};
ManufacturingMinimums manufacturing_fab_minimums();
struct ManufacturingFabItem {
    std::string kind, owner, detail;
    double value = 0;
};
struct ManufacturingBoardDemand {
    std::optional<double> min_trace_mm, min_clearance_mm, min_drill_mm,
        min_via_dia_mm, min_via_annular_mm, min_hole_to_hole_mm, pro_via_annular_mm,
        min_pad_annular_mm, min_npth_drill_mm, min_slot_width_mm, min_slot_ratio,
        min_silk_height_mm, min_silk_line_mm;
    std::size_t n_segments = 0, n_vias = 0, n_drills = 0;
    std::vector<ManufacturingFabItem> items;
};
struct ManufacturingFabRow {
    std::string label;
    std::optional<double> value;
    double floor = 0;
    bool pass = true;
    std::string unit, kind;
};
struct ManufacturingFabResult {
    bool ok = true;
    ManufacturingFabProfile profile;
    ManufacturingBoardDemand demand;
    std::vector<ManufacturingFabRow> rows;
    std::vector<std::string> errors;
    std::string report() const; // No final newline.
};
ManufacturingBoardDemand measure_manufacturing_board(const Sexpr& pcb,
    const std::string& dru, const std::string& project);
ManufacturingBoardDemand measure_manufacturing_board(const std::filesystem::path& pcb,
    const std::filesystem::path& dru, const std::filesystem::path& project);
ManufacturingFabResult check_manufacturing_fab(const ManufacturingBoardDemand&,
    const ManufacturingFabProfile& = manufacturing_fab_profile());
ManufacturingFabResult run_manufacturing_fab(const std::filesystem::path& reports,
    const std::filesystem::path& pcb, const std::filesystem::path& dru,
    const std::filesystem::path& project,
    const ManufacturingFabProfile& = manufacturing_fab_profile());
struct ManufacturingFallbackResult {
    bool ok = true, pinned = false;
    std::size_t n_names = 0, n_fired = 0;
    std::vector<std::string> regressions;
    std::string summary() const;
};
ManufacturingFallbackResult check_manufacturing_fallbacks(const ManufacturingCounts&,
    const std::optional<ManufacturingCounts>& baseline);
// Preserves the legacy first-run pin / corrupt-baseline recovery and monotonic
// ceiling reduction. A failing check never writes the baseline.
ManufacturingFallbackResult run_manufacturing_fallbacks(const ManufacturingCounts&,
    const std::filesystem::path& baseline);
} // namespace schgen
