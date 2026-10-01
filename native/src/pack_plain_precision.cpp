#include "schgen/pack_plain_precision.hpp"
#include "schgen/occupancy.hpp"

namespace schgen {
double pack_fanout_reach_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_fanout_reach_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_band_sort_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_band_sort_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_contact_column_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_contact_column_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_plane_bound_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_plane_bound_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double pack_isolation_bound_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_isolation_bound_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double pack_ladder_coordinate_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_ladder_coordinate_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_redundancy_candidate_precision6dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_redundancy_candidate_precision6dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 6);
}
double pack_aabb_coordinate_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_aabb_coordinate_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_block_area_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_block_area_precision1dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 1);
}
double pack_xy_coordinate_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_xy_coordinate_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_box_coordinate_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_box_coordinate_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_svg_map_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_svg_map_precision1dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 1);
}
double pack_unique_coordinate_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_unique_coordinate_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_centroid_coordinate_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_centroid_coordinate_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_row_extent_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_row_extent_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pack_halfturn_origin_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_halfturn_origin_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_rotated_origin_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_rotated_origin_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
double pack_named_center_precision(double value, int digits, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pack_named_center_precision";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, digits);
}
} // namespace schgen
