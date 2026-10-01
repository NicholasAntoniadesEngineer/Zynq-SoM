#pragma once
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
namespace pack_plain_precision_fixture {
inline const std::array<std::string,18> names{{"pack_fanout_reach_precision4dp","pack_band_sort_precision4dp","pack_contact_column_precision4dp","pack_plane_bound_precision3dp","pack_isolation_bound_precision3dp","pack_ladder_coordinate_precision4dp","pack_redundancy_candidate_precision6dp","pack_aabb_coordinate_precision","pack_block_area_precision1dp","pack_xy_coordinate_precision","pack_box_coordinate_precision","pack_svg_map_precision1dp","pack_unique_coordinate_precision","pack_centroid_coordinate_precision","pack_row_extent_precision4dp","pack_halfturn_origin_precision","pack_rotated_origin_precision","pack_named_center_precision"}};
inline bool added(const std::string& name) { return std::find(names.begin(),names.end(),name)!=names.end(); }
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& values,bool additions=true) {
    schgen::QuantizationCounts out;
    for(const auto& [name,n]:values)if(added(name)==additions)out[name]=n;
    return out;
}
}
