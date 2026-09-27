#pragma once
#include "pack_geometry_precision_fixture.hpp"
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
#include <string>
namespace output_precision_fixture {
inline const std::array<std::string,19> names{{
    "floorplan_svg_extent_trunc",
    "floorplan_svg_grid_trunc",
    "floorplan_svg_coordinate_precision1dp",
    "pcb_project_integer_trunc",
    "pcb_project_class_precision4dp",
    "pcb_silk_position_precision3dp",
    "pcb_silk_stroke_precision3dp",
    "ratsnest_pad_precision3dp",
    "ratsnest_area_precision1dp",
    "ratsnest_dispersion_precision2dp",
    "ratsnest_budget_precision1dp",
    "escape_ground_precision4dp",
    "escape_scan_precision3dp",
    "escape_copper_precision4dp",
    "escape_coverage_precision4dp",
    "escape_region_precision4dp",
    "escape_port_precision4dp",
    "escape_width_precision4dp",
    "escape_corridor_precision4dp"
}};
inline bool added(const std::string& name) {
    return std::find(names.begin(),names.end(),name)!=names.end();
}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& values,bool new_only=true) {
    schgen::QuantizationCounts out;
    for(const auto& [name,count]:values)if(added(name)==new_only&&!pack_geometry_precision_fixture::added(name))out[name]=count;
    return out;
}
}
