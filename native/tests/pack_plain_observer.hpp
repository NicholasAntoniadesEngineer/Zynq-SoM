#pragma once
#include "pack_plain_precision_fixture.hpp"
#include "schgen/pack_plain_precision.hpp"
#include <atomic>
#include <stdexcept>
namespace plain_fixture {
using pack_plain_precision_fixture::names;
using pack_plain_precision_fixture::select;
inline std::array<std::atomic<std::size_t>,18> entries{};
inline std::atomic<bool> recording{false};
inline void begin(){for(auto& n:entries)n=0;recording=true;}
inline schgen::QuantizationCounts end(){recording=false;schgen::QuantizationCounts out;for(std::size_t i=0;i<entries.size();++i)if(entries[i])out[names[i]]=entries[i].load();return out;}
inline void receipt(const schgen::QuantizationCounts& q,const schgen::QuantizationCounts& observed){if(select(q)!=observed)throw std::runtime_error("plain precision receipt != actual scalar entries");}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    if(!plain_fixture::recording.load(std::memory_order_relaxed))return;
    if(fn==reinterpret_cast<void*>(schgen::pack_fanout_reach_precision4dp)){++plain_fixture::entries[0];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_band_sort_precision4dp)){++plain_fixture::entries[1];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_contact_column_precision4dp)){++plain_fixture::entries[2];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_plane_bound_precision3dp)){++plain_fixture::entries[3];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_isolation_bound_precision3dp)){++plain_fixture::entries[4];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_ladder_coordinate_precision4dp)){++plain_fixture::entries[5];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_redundancy_candidate_precision6dp)){++plain_fixture::entries[6];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_aabb_coordinate_precision)){++plain_fixture::entries[7];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_block_area_precision1dp)){++plain_fixture::entries[8];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_xy_coordinate_precision)){++plain_fixture::entries[9];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_box_coordinate_precision)){++plain_fixture::entries[10];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_svg_map_precision1dp)){++plain_fixture::entries[11];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_unique_coordinate_precision)){++plain_fixture::entries[12];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_centroid_coordinate_precision)){++plain_fixture::entries[13];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_row_extent_precision4dp)){++plain_fixture::entries[14];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_halfturn_origin_precision)){++plain_fixture::entries[15];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_rotated_origin_precision)){++plain_fixture::entries[16];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_named_center_precision)){++plain_fixture::entries[17];return;}
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
