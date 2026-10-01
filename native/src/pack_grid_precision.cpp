#include "schgen/pack_grid_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {
int silk_cell_floor(double value, double cell, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "silk_cell_floor";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value) || !std::isfinite(cell) || cell <= 0)
        throw std::invalid_argument("silk_cell_floor: finite coordinate and positive cell required");
    const double result = std::floor(value / cell);
    if (!std::isfinite(result) || result < std::numeric_limits<int>::min() ||
        result > std::numeric_limits<int>::max())
        throw std::out_of_range("silk_cell_floor: cell must fit int");
    return static_cast<int>(result);
}
int breathe_grid_extent(double extent, double cell, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "breathe_grid_extent";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(extent) || !std::isfinite(cell) || cell <= 0)
        throw std::invalid_argument("breathe_grid_extent: finite extent and positive cell required");
    const double quotient = extent / cell;
    // These comparisons are equivalent to bounds on trunc(quotient), without
    // introducing a second rounding operation into the source census.
    if (!std::isfinite(quotient) || quotient <= -2.0 ||
        quotient >= static_cast<double>(std::numeric_limits<int>::max()) - 1.0)
        throw std::out_of_range("breathe_grid_extent: positive truncated extent plus two must fit int");
    return static_cast<int>(quotient) + 2;
}
int breathe_stamp_index(double quotient, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "breathe_stamp_index";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(quotient))
        throw std::invalid_argument("breathe_stamp_index: finite quotient required");
    if (quotient <= static_cast<double>(std::numeric_limits<int>::min()) - 1.0 ||
        quotient >= static_cast<double>(std::numeric_limits<int>::max()) + 1.0)
        throw std::out_of_range("breathe_stamp_index: truncated quotient must fit int");
    return static_cast<int>(quotient);
}
int breathe_free_index(double quotient, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "breathe_free_index";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(quotient))
        throw std::invalid_argument("breathe_free_index: finite quotient required");
    if (quotient <= static_cast<double>(std::numeric_limits<int>::min()) - 1.0 ||
        quotient >= static_cast<double>(std::numeric_limits<int>::max()) + 1.0)
        throw std::out_of_range("breathe_free_index: truncated quotient must fit int");
    return static_cast<int>(quotient);
}
double refdes_size_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "refdes_size_precision3dp";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("refdes_size_precision3dp: finite size required");
    return py_round(value, 3);
}
double refdes_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "refdes_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("refdes_pose_precision4dp: finite coordinate required");
    return py_round(value, 4);
}
}
