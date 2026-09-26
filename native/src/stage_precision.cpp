#include "schgen/stage_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {

double stage_shift_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_shift_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_root_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_root_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_connector_alignment_delta_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_connector_alignment_delta_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_connector_clearance_line_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_connector_clearance_line_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_connector_clearance_delta_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_connector_clearance_delta_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_ldo_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_ldo_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_power_mirror_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_power_mirror_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_layout_width_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_layout_width_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_hot_leftover_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_hot_leftover_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_hot_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_hot_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_proximity_leftover_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_proximity_leftover_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_proximity_rebase_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_proximity_rebase_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_proximity_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_proximity_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_proximity_face_shift_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_proximity_face_shift_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double stage_refit_pad_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_refit_pad_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}

int stage_candidate_radius_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_candidate_radius_trunc";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("stage_candidate_radius_trunc: finite quotient required");
    const double truncated = std::trunc(value);
    if (truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("stage_candidate_radius_trunc: truncated quotient must fit int");
    return static_cast<int>(value);
}

int stage_seat_radius_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "stage_seat_radius_trunc";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("stage_seat_radius_trunc: finite quotient required");
    const double truncated = std::trunc(value);
    if (truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("stage_seat_radius_trunc: truncated quotient must fit int");
    return static_cast<int>(value);
}

} // namespace schgen
