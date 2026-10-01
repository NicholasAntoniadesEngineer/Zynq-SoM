#pragma once
#include "schgen/execution_accounting.hpp"
#include <algorithm>
#include <array>
namespace pack_search_precision_fixture {
inline const std::array<std::string,9> names{{"fallback_axis_count","fallback_coordinate_precision3dp","fallback_rank_precision4dp","seat_lower_index","seat_upper_index","seat_vertical_extent","seat_coordinate_precision6dp","seat_coverage_precision4dp","seat_split_precision4dp"}};
inline bool added(const std::string& n){return std::find(names.begin(),names.end(),n)!=names.end();}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& q,bool wanted=true){schgen::QuantizationCounts out;for(const auto& [n,c]:q)if(added(n)==wanted)out[n]=c;return out;}
}
