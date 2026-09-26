#include "schgen/precision_ops.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {

double estimate_position_precision(double value) { return py_round(value, 4); }
double estimate_pad_precision(double value) { return py_round(value, 3); }
double breathe_delta_precision(double value) { return py_round(value, 4); }
double breathe_commit_precision(double value) { return py_round(value, 4); }

int breathe_forward_steps(double distance, double step) {
    if (!std::isfinite(distance) || !std::isfinite(step) || step <= 0)
        throw std::invalid_argument("breathe_forward_steps: finite distance and positive finite step required");
    const double quotient = distance / step;
    const double truncated = std::trunc(quotient);
    if (!std::isfinite(quotient) || truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max() - 1)
        throw std::out_of_range("breathe_forward_steps: truncated quotient plus one must fit int");
    return static_cast<int>(quotient) + 1;
}

int breathe_retreat_steps(double distance, double step) {
    if (!std::isfinite(distance) || !std::isfinite(step) || step <= 0)
        throw std::invalid_argument("breathe_retreat_steps: finite distance and positive finite step required");
    const double quotient = distance / step;
    const double truncated = std::trunc(quotient);
    if (!std::isfinite(quotient) || truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("breathe_retreat_steps: truncated quotient must fit int");
    return static_cast<int>(quotient);
}

int mechanical_direction_component(double value) {
    const double rounded = py_round(value, 0);
    if (!std::isfinite(rounded))
        throw std::invalid_argument("mechanical_direction_component: finite direction required");
    if (rounded < std::numeric_limits<int>::min() ||
        rounded > std::numeric_limits<int>::max())
        throw std::out_of_range("mechanical_direction_component: rounded direction must fit int");
    return static_cast<int>(rounded);
}

double stage_direction_component(double value) { return std::round(value); }

} // namespace schgen
