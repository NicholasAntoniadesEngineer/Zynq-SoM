#include "schgen/legalize_precision.hpp"
#include "schgen/occupancy.hpp"

namespace schgen {
double legalize_position_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_position_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_centroid_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_centroid_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_bbox_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_bbox_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_anchor_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_anchor_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_bound_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_bound_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_margin_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_margin_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double legalize_trial_pose_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "legalize_trial_pose_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
} // namespace schgen
