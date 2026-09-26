#include "schgen/occupancy_precision.hpp"
#include "schgen/occupancy.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {

double occupancy_component_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        // Own the long lookup key once; the invocation still owns every count.
        static const std::string key = "occupancy_component_precision4dp";
        checked_quantization_add(*counts, key);
    }
    return py_round(value, 4);
}

double occupancy_reach_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string key = "occupancy_reach_precision4dp";
        checked_quantization_add(*counts, key);
    }
    return py_round(value, 4);
}

double occupancy_frontier_key1dp(double distance, OccupancyFrontierCounter counts) {
    if (counts.counts_) {
        static const std::string key = "occupancy_frontier_key1dp";
        auto* value = counts.slot_ ? counts.slot_->value_ : nullptr;
        if (!value) {
            const auto found = counts.counts_->find(key);
            if (found == counts.counts_->end()) {
                const auto inserted = counts.counts_->emplace(key, 1);
                if (counts.slot_) counts.slot_->value_ = &inserted.first->second;
            } else {
                value = &found->second;
                if (counts.slot_) counts.slot_->value_ = value;
            }
        }
        if (value) {
            if (*value == std::numeric_limits<std::size_t>::max())
                throw std::overflow_error("quantization counter overflow: " + key);
            ++*value;
        }
    }
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
