#include "schgen/pack_geometry_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {

double pack_pair_gap_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_pair_gap_precision4dp");
    return py_round(value, 4);
}

double pack_edge_component_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_edge_component_precision4dp");
    return py_round(value, 4);
}

double pack_som_grid_precision0dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_grid_precision0dp");
    return py_round(value, 0);
}

double pack_som_cell_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_cell_precision4dp");
    return py_round(value, 4);
}

double pack_som_diameter_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_diameter_precision4dp");
    return py_round(value, 4);
}

double pack_som_component_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_component_pose_precision4dp");
    return py_round(value, 4);
}

double pack_som_band_component_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_band_component_precision4dp");
    return py_round(value, 4);
}

double pack_cout_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_cout_pose_precision4dp");
    return py_round(value, 4);
}

double pack_bulk_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_bulk_pose_precision4dp");
    return py_round(value, 4);
}

double pack_zone_component_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_zone_component_precision4dp");
    return py_round(value, 4);
}

double pack_rotated_offset_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_rotated_offset_precision4dp");
    return py_round(value, 4);
}

double pack_corridor_bound_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_corridor_bound_precision4dp");
    return py_round(value, 4);
}

double pack_mirror_offset_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_mirror_offset_precision4dp");
    return py_round(value, 4);
}

int pack_som_grid_trunc(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_som_grid_trunc");
    if (!std::isfinite(value) ||
        value <= static_cast<double>(std::numeric_limits<int>::min()) - 1.0 ||
        value >= static_cast<double>(std::numeric_limits<int>::max()) + 1.0)
        throw std::out_of_range("pack_som_grid_trunc: integer result out of range");
    return static_cast<int>(value);
}
} // namespace schgen
