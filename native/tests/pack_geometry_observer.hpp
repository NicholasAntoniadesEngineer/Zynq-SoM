#pragma once
#include "pack_geometry_precision_fixture.hpp"
#include "schgen/execution_accounting.hpp"
#include <array>
#include <atomic>
#include <algorithm>
#include <stdexcept>
#ifdef PACK_GEOMETRY_CANDIDATE
#include "schgen/pack_geometry_precision.hpp"
#endif
namespace geometry_fixture {
using pack_geometry_precision_fixture::names;
inline std::array<std::atomic<std::size_t>,14> entries{};
inline std::atomic<bool> recording{false};
using pack_geometry_precision_fixture::added;
using pack_geometry_precision_fixture::select;
inline void begin(){for(auto& n:entries)n=0;recording=true;}
inline schgen::QuantizationCounts end(){recording=false;schgen::QuantizationCounts out;for(std::size_t i=0;i<14;++i)if(entries[i])out[names[i]]=entries[i].load();return out;}
inline void receipt(const schgen::QuantizationCounts& q,const schgen::QuantizationCounts& observed){
#ifdef PACK_GEOMETRY_CANDIDATE
 if(select(q)!=observed)throw std::runtime_error("geometry14 owned receipt differs from actual scalar entries");
#else
 (void)q;(void)observed;
#endif
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
#ifdef PACK_GEOMETRY_CANDIDATE
 if(!geometry_fixture::recording.load(std::memory_order_relaxed))return;
 if(fn==reinterpret_cast<void*>(schgen::pack_pair_gap_precision4dp)){++geometry_fixture::entries[0];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_edge_component_precision4dp)){++geometry_fixture::entries[1];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_grid_precision0dp)){++geometry_fixture::entries[2];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_cell_precision4dp)){++geometry_fixture::entries[3];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_diameter_precision4dp)){++geometry_fixture::entries[4];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_component_pose_precision4dp)){++geometry_fixture::entries[5];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_band_component_precision4dp)){++geometry_fixture::entries[6];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_cout_pose_precision4dp)){++geometry_fixture::entries[7];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_bulk_pose_precision4dp)){++geometry_fixture::entries[8];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_zone_component_precision4dp)){++geometry_fixture::entries[9];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_rotated_offset_precision4dp)){++geometry_fixture::entries[10];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_corridor_bound_precision4dp)){++geometry_fixture::entries[11];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_mirror_offset_precision4dp)){++geometry_fixture::entries[12];return;}
 if(fn==reinterpret_cast<void*>(schgen::pack_som_grid_trunc)){++geometry_fixture::entries[13];return;}
#else
 (void)fn;
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
