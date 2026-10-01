#pragma once
#include "schgen/execution_accounting.hpp"
#include "pack_search_precision_fixture.hpp"
#include <array>
#include <algorithm>
#include <stdexcept>
#ifdef SEARCH_CANDIDATE
#include "schgen/pack_search_precision.hpp"
#endif
namespace search_proof {
using pack_search_precision_fixture::names;
inline std::array<std::size_t,9> entries{};
inline bool recording=false;
inline void begin(){entries.fill(0);recording=true;}
inline schgen::QuantizationCounts end(){recording=false;schgen::QuantizationCounts q;for(std::size_t i=0;i<9;++i)if(entries[i])q[names[i]]=entries[i];return q;}
inline bool added(const std::string& n){return std::find(names.begin(),names.end(),n)!=names.end();}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& q,bool wanted=true){schgen::QuantizationCounts out;for(const auto& [k,v]:q)if(added(k)==wanted)out[k]=v;return out;}
inline void receipt(const schgen::QuantizationCounts& q){
 auto actual=end();
#ifdef SEARCH_CANDIDATE
 if(select(q)!=actual)throw std::runtime_error("search9 receipt differs from independent entry");
#endif
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
#ifdef SEARCH_CANDIDATE
 if(!search_proof::recording)return;
 if(fn==reinterpret_cast<void*>(schgen::fallback_axis_count)){++search_proof::entries[0];return;}
 if(fn==reinterpret_cast<void*>(schgen::fallback_coordinate_precision3dp)){++search_proof::entries[1];return;}
 if(fn==reinterpret_cast<void*>(schgen::fallback_rank_precision4dp)){++search_proof::entries[2];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_lower_index)){++search_proof::entries[3];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_upper_index)){++search_proof::entries[4];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_vertical_extent)){++search_proof::entries[5];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_coordinate_precision6dp)){++search_proof::entries[6];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_coverage_precision4dp)){++search_proof::entries[7];return;}
 if(fn==reinterpret_cast<void*>(schgen::seat_split_precision4dp)){++search_proof::entries[8];return;}
#else
 (void)fn;
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
