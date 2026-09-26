#pragma once
#include "placement_precision_fixture.hpp"
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
#include <string>

namespace legalize_precision_fixture {
// Exactly the seven additive families independently entry-counted by the
// legalizer contracts. Never filter a prefix or the prior pose-quantum count.
inline const std::array<std::string,7> names{{
    "legalize_position_precision4dp","legalize_centroid_precision4dp",
    "legalize_bbox_precision4dp","legalize_anchor_precision4dp",
    "legalize_bound_precision4dp","legalize_margin_precision4dp",
    "legalize_trial_pose_precision4dp"}};
inline bool added(const std::string& name) {
    return std::find(names.begin(),names.end(),name)!=names.end();
}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& values,bool new_only=true) {
    schgen::QuantizationCounts out;
    for(const auto& [name,count]:values)if(added(name)==new_only&&!placement_precision_fixture::added(name))out[name]=count;
    return out;
}
} // namespace legalize_precision_fixture
