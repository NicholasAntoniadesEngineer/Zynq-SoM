#include "schgen/placement_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {
double placement_turn_dimension_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_turn_dimension_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_turn_offset_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_turn_offset_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_connector_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_connector_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_behind_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_behind_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_pack_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_pack_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_edge_mirror_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_edge_mirror_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_variant_dimension_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_variant_dimension_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_member_box_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_member_box_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_member_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_member_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_bottom_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_bottom_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_lift_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_lift_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_shape_key_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_shape_key_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_l4_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_l4_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_edge_seat_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_edge_seat_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_foreign_pad_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_foreign_pad_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}

double placement_evict_trial_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_evict_trial_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_emission_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_emission_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

double placement_fiducial_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_fiducial_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}

int placement_l4_distance_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "placement_l4_distance_trunc";
        checked_quantization_add(*counts, name);
    }
    if (!std::isfinite(value))
        throw std::invalid_argument("placement_l4_distance_trunc: finite distance required");
    const double truncated = std::trunc(value);
    if (truncated < std::numeric_limits<int>::min() ||
        truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("placement_l4_distance_trunc: truncated distance must fit int");
    return static_cast<int>(value);
}

} // namespace schgen
