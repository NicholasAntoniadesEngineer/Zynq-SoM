#pragma once
#include "schgen/quantize.hpp"
#include "legalize_precision_fixture.hpp"
#include "stage_precision_fixture.hpp"
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
    // Independently proven legalizer, stage and placement additions are absent
    // from this historical snapshot. Every other prior/unknown name stays visible.
    for(const auto& [name,count]:values)
        if(added(name)==new_only&&!legalize_precision_fixture::added(name)&&!stage_precision_fixture::added(name)&&!placement_precision_fixture::added(name))out[name]=count;
    return out;
}
}
