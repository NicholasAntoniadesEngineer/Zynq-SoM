#include "schgen/pack_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {
double pack_shelf_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_shelf_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_shelf_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_shelf_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
int pack_control_fit_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_control_fit_trunc";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("pack_control_fit_trunc: finite quotient required");
    const double truncated = std::trunc(value);
    if (truncated < std::numeric_limits<int>::min() || truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("pack_control_fit_trunc: truncated quotient must fit int");
    return static_cast<int>(value);
}
double pack_control_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_control_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_edge_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_edge_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_edge_lower_tick_ceil(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "pack_edge_lower_tick_ceil");
    const double scaled = value * 10000.0;
    if (!std::isfinite(scaled))
        throw std::invalid_argument("pack_edge_lower_tick_ceil: finite scaled coordinate required");
    return std::ceil(scaled);
}
double pack_hf_cap_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_hf_cap_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
}
