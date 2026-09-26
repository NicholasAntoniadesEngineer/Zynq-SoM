#pragma once
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
namespace placement_precision_fixture {
inline const std::array<std::string,19> names{{"placement_turn_dimension_precision4dp",
    "placement_turn_offset_precision4dp",
    "placement_connector_pose_precision4dp",
    "placement_behind_pose_precision4dp",
    "placement_pack_extent_precision4dp",
    "placement_edge_mirror_pose_precision4dp",
    "placement_variant_dimension_precision4dp",
    "placement_member_box_precision4dp",
    "placement_member_pose_precision4dp",
    "placement_bottom_pose_precision4dp",
    "placement_lift_extent_precision4dp",
    "placement_shape_key_precision4dp",
    "placement_l4_pose_precision4dp",
    "placement_edge_seat_precision4dp",
    "placement_foreign_pad_precision3dp",
    "placement_evict_trial_precision4dp",
    "placement_emission_pose_precision4dp",
    "placement_fiducial_precision4dp",
    "placement_l4_distance_trunc"}};
inline bool added(const std::string& name){return std::find(names.begin(),names.end(),name)!=names.end();}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& counts,bool additions=true){
    schgen::QuantizationCounts out;for(const auto& [name,count]:counts)if(added(name)==additions)out[name]=count;return out;
}
}

