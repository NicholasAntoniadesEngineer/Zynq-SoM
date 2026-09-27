#include "schgen/output_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>

namespace schgen {
int floorplan_svg_extent_trunc(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "floorplan_svg_extent_trunc");
    const double truncated=std::trunc(value);
    if (!std::isfinite(value) || truncated < std::numeric_limits<int>::min() || truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("floorplan SVG extent outside integer range");
    return static_cast<int>(value);
}
int floorplan_svg_grid_trunc(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "floorplan_svg_grid_trunc");
    const double truncated=std::trunc(value);
    if (!std::isfinite(value) || truncated < std::numeric_limits<int>::min() || truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("floorplan SVG grid extent outside integer range");
    return static_cast<int>(value);
}
double floorplan_svg_coordinate_precision1dp(double value, double origin, double scale,
                                             QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "floorplan_svg_coordinate_precision1dp");
    return py_round(origin + value * scale, 1);
}
double pcb_project_integer_trunc(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pcb_project_integer_trunc");
    return std::trunc(value);
}
double pcb_project_class_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pcb_project_class_precision4dp");
    return py_round(value, 4);
}
double pcb_silk_position_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pcb_silk_position_precision3dp");
    return py_round(value, 3);
}
double pcb_silk_stroke_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pcb_silk_stroke_precision3dp");
    return py_round(value, 3);
}
double ratsnest_pad_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "ratsnest_pad_precision3dp");
    return py_round(value, 3);
}
double ratsnest_area_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "ratsnest_area_precision1dp");
    return py_round(value, 1);
}
double ratsnest_dispersion_precision2dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "ratsnest_dispersion_precision2dp");
    return py_round(value, 2);
}
double ratsnest_budget_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "ratsnest_budget_precision1dp");
    return py_round(value, 1);
}
double escape_ground_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_ground_precision4dp");
    return py_round(value, 4);
}
double escape_scan_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_scan_precision3dp");
    return py_round(value, 3);
}
double escape_copper_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_copper_precision4dp");
    return py_round(value, 4);
}
double escape_coverage_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_coverage_precision4dp");
    return py_round(value, 4);
}
double escape_region_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_region_precision4dp");
    return py_round(value, 4);
}
double escape_port_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_port_precision4dp");
    return py_round(value, 4);
}
double escape_width_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_width_precision4dp");
    return py_round(value, 4);
}
double escape_corridor_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "escape_corridor_precision4dp");
    return py_round(value, 4);
}
} // namespace schgen
