#include "schgen/output_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>

namespace schgen {
int floorplan_svg_extent_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "floorplan_svg_extent_trunc";
        checked_quantization_add(*counts, name);
    }
    const double truncated=std::trunc(value);
    if (!std::isfinite(value) || truncated < std::numeric_limits<int>::min() || truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("floorplan SVG extent outside integer range");
    return static_cast<int>(value);
}
int floorplan_svg_grid_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "floorplan_svg_grid_trunc";
        checked_quantization_add(*counts, name);
    }
    const double truncated=std::trunc(value);
    if (!std::isfinite(value) || truncated < std::numeric_limits<int>::min() || truncated > std::numeric_limits<int>::max())
        throw std::out_of_range("floorplan SVG grid extent outside integer range");
    return static_cast<int>(value);
}
double floorplan_svg_coordinate_precision1dp(double value, double origin, double scale,
                                             QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "floorplan_svg_coordinate_precision1dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(origin + value * scale, 1);
}
double pcb_project_integer_trunc(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pcb_project_integer_trunc";
        checked_quantization_add(*counts, name);
    }
    return std::trunc(value);
}
double pcb_project_class_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pcb_project_class_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double pcb_silk_position_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pcb_silk_position_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double pcb_silk_stroke_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "pcb_silk_stroke_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double ratsnest_pad_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "ratsnest_pad_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double ratsnest_area_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "ratsnest_area_precision1dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 1);
}
double ratsnest_dispersion_precision2dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "ratsnest_dispersion_precision2dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 2);
}
double ratsnest_budget_precision1dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "ratsnest_budget_precision1dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 1);
}
double escape_ground_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_ground_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_scan_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_scan_precision3dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 3);
}
double escape_copper_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_copper_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_coverage_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_coverage_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_region_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_region_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_port_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_port_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_width_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_width_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
double escape_corridor_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) {
        static const std::string name = "escape_corridor_precision4dp";
        checked_quantization_add(*counts, name);
    }
    return py_round(value, 4);
}
} // namespace schgen
