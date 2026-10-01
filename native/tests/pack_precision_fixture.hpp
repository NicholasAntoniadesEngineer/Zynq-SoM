#include "pack_search_precision_fixture.hpp"
#include "pack_plain_precision_fixture.hpp"
#include "pack_grid_precision_fixture.hpp"
#pragma once
#include "pack_geometry_precision_fixture.hpp"
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
namespace pack_precision_fixture {
inline const std::array<std::string,6> names{{"pack_shelf_pose_precision4dp",
    "pack_shelf_extent_precision4dp","pack_control_fit_trunc",
    "pack_control_pose_precision4dp","pack_edge_pose_precision4dp",
    "pack_hf_cap_pose_precision4dp"}};
inline bool added(const std::string& name) {
    return std::find(names.begin(),names.end(),name)!=names.end();
}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& all,bool additions=true) {
    schgen::QuantizationCounts result;
    for(const auto& [name,n]:all)if(added(name)==additions&&!pack_geometry_precision_fixture::added(name)&&!pack_search_precision_fixture::added(name)&&!pack_plain_precision_fixture::added(name)&&!pack_grid_precision_fixture::added(name))result[name]=n;
    return result;
}
}
