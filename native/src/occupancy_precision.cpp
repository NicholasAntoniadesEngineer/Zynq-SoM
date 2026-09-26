#include "schgen/occupancy_precision.hpp"
#include "schgen/occupancy.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {

double occupancy_component_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_component_precision4dp");
    return py_round(value, 4);
}

double occupancy_reach_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_reach_precision4dp");
    return py_round(value, 4);
}

double occupancy_frontier_key1dp(double distance, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_frontier_key1dp");
    return py_round(distance, 1);
}

double occupancy_shape_key4dp(double distance, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_shape_key4dp");
    return py_round(distance, 4);
}

int occupancy_cell_index(double coordinate, double bucket, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_cell_index");
    if (!std::isfinite(coordinate) || !std::isfinite(bucket) || bucket == 0)
        throw std::invalid_argument("occupancy_cell_index: finite coordinate and finite nonzero bucket required");
    const double cell = std::floor(coordinate / bucket);
    if (!std::isfinite(cell) || cell < std::numeric_limits<int>::min() ||
        cell > std::numeric_limits<int>::max())
        throw std::out_of_range("occupancy_cell_index: floored quotient must fit int");
    return static_cast<int>(cell);
}

int occupancy_axis_count(double extent, double step, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "occupancy_axis_count");
    if (!std::isfinite(extent) || !std::isfinite(step) || step == 0)
        throw std::invalid_argument("occupancy_axis_count: finite extent and finite nonzero step required");
    const double quotient = extent / step;
    const double truncated = std::trunc(quotient);
    if (!std::isfinite(quotient) || truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max() - 1)
        throw std::out_of_range("occupancy_axis_count: truncated quotient plus one must fit int");
    return static_cast<int>(quotient) + 1;
}

} // namespace schgen
