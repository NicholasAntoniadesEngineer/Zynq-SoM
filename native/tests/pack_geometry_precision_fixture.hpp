#include "pack_search_precision_fixture.hpp"
#pragma once
#include "schgen/execution_accounting.hpp"
#include <array>
#include <algorithm>
namespace pack_geometry_precision_fixture {
inline const std::array<std::string,14> names{{"pack_pair_gap_precision4dp","pack_edge_component_precision4dp","pack_som_grid_precision0dp","pack_som_cell_precision4dp","pack_som_diameter_precision4dp","pack_som_component_pose_precision4dp","pack_som_band_component_precision4dp","pack_cout_pose_precision4dp","pack_bulk_pose_precision4dp","pack_zone_component_precision4dp","pack_rotated_offset_precision4dp","pack_corridor_bound_precision4dp","pack_mirror_offset_precision4dp","pack_som_grid_trunc"}};
inline bool added(const std::string& name){return std::find(names.begin(),names.end(),name)!=names.end();}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& counts,bool additions=true){
    schgen::QuantizationCounts out;
    for(const auto& [name,count]:counts)if(added(name)==additions&&!pack_search_precision_fixture::added(name))out[name]=count;
    return out;
}
}
