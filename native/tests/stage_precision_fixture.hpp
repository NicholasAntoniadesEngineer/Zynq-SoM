#pragma once
#include "schgen/execution_accounting.hpp"
#include <array>
#include <algorithm>
namespace stage_precision_fixture {
inline const std::array<std::string,17> names{{"stage_shift_precision4dp",
    "stage_root_pose_precision4dp",
    "stage_connector_alignment_delta_precision4dp",
    "stage_connector_clearance_line_precision4dp",
    "stage_connector_clearance_delta_precision4dp",
    "stage_ldo_pose_precision4dp",
    "stage_power_mirror_pose_precision4dp",
    "stage_layout_width_precision4dp",
    "stage_hot_leftover_pose_precision4dp",
    "stage_hot_extent_precision4dp",
    "stage_proximity_leftover_pose_precision4dp",
    "stage_proximity_rebase_precision4dp",
    "stage_proximity_extent_precision4dp",
    "stage_proximity_face_shift_precision4dp",
    "stage_refit_pad_precision3dp",
    "stage_candidate_radius_trunc",
    "stage_seat_radius_trunc"}};
inline bool added(const std::string& n){return std::find(names.begin(),names.end(),n)!=names.end();}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& all,bool additions=true){
    schgen::QuantizationCounts out;for(const auto& [n,c]:all)if(added(n)==additions)out[n]=c;return out;
}
}
