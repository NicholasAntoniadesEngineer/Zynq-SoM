#pragma once
#include "schgen/quantize.hpp"
#include <algorithm>
#include <array>
#include <string>

namespace occupancy_precision_fixture {
inline const std::array<std::string,6> names{{
    "occupancy_component_precision4dp","occupancy_reach_precision4dp",
    "occupancy_frontier_key1dp","occupancy_shape_key4dp",
    "occupancy_cell_index","occupancy_axis_count"}};
inline bool added(const std::string& name) {
    return std::find(names.begin(),names.end(),name)!=names.end();
}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& values,bool new_only=true) {
    schgen::QuantizationCounts out;
    for(const auto& [name,count]:values)if(added(name)==new_only)out[name]=count;
    return out;
}
}
