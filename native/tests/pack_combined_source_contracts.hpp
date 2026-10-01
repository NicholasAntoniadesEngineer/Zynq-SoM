#pragma once
#include "schgen/native_audit_state.hpp"
#include "schgen/pcb_checks.hpp"
#include "pack_search_precision_fixture.hpp"
#include "pack_plain_precision_fixture.hpp"
#include "pack_grid_precision_fixture.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <regex>
namespace pack_combined_source {
using namespace schgen;
inline std::string read(const std::filesystem::path& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing frozen source "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
inline CppSourceCensus scan(const std::filesystem::path& root,const std::string& source){
 CppAuditOptions options;options.workers=1;options.timeout=std::chrono::milliseconds(120000);
 options.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
 return scan_cpp_audit_sources(root,{{source}},options);
}
inline int family(const std::string& symbol){
 const std::string prefix="native/src/pack.cpp::schgen::";
 const std::array<std::set<std::string>,3> owned{{
 {"fallback_via_sites","seat_band"},
 {"zone_fanout_reach","band_cover","contact_geometry","canonical_plane_rect","isolation_void_rect","escape_ladder_plan","escape_redundancy_u","aabb_from_corners","block_area","round_xy","round_box","svg_map","rounded_unique_sorted","rounded_centroid","row_extent","turn_origin_180","rotate_origin","named_box_center_sigs"},
 {"SilkBoxIndex::cell_of","BreatheGrid::BreatheGrid","BreatheGrid::stamp","BreatheGrid::free","place_refdes"}}};
 for(std::size_t i=0;i<owned.size();++i)for(const auto& name:owned[i]){
  const auto full=prefix+name;
  if(symbol==full||(name=="band_cover"&&symbol.compare(0,full.size()+10,full+"::<lambda@")==0))return static_cast<int>(i);
 }
 return -1;
}
inline void run(const std::filesystem::path& root,const std::filesystem::path& scratch,
                const std::filesystem::path& explicit_before={}){
 const auto fixtures=root/"native/tests/data/pack_search_precision";
 constexpr const char* source_hash="e6656c2b5022471c6e59d8ad1ecf3c40e2ae62476ed5ec4e7a3364c9d0e6cb2d";
 constexpr const char* header_hash="17b1119a8fc4b0ac9078ce92c238970d64febe15a2a0cb73636e8b8e9645704d";
 if(pcb_sha256(read(fixtures/"before-pack.cpp.txt"))!=source_hash||pcb_sha256(read(fixtures/"before-pack.hpp.txt"))!=header_hash)throw std::runtime_error("immutable before source changed");
 if(!explicit_before.empty()&&(pcb_sha256(read(explicit_before/"native/src/pack.cpp"))!=source_hash||pcb_sha256(read(explicit_before/"native/include/schgen/pack.hpp"))!=header_hash))throw std::runtime_error("explicit before is not frozen original source");
 if(std::filesystem::exists(scratch))throw std::runtime_error("fresh source scratch required");
 std::filesystem::create_directories(scratch/"native");
 std::filesystem::copy(root/"native/include",scratch/"native/include",std::filesystem::copy_options::recursive);
 std::filesystem::copy(root/"native/src",scratch/"native/src",std::filesystem::copy_options::recursive);
 std::filesystem::copy_file(fixtures/"before-pack.cpp.txt",scratch/"native/src/pack.cpp",std::filesystem::copy_options::overwrite_existing);
 std::filesystem::copy_file(fixtures/"before-pack.hpp.txt",scratch/"native/include/schgen/pack.hpp",std::filesystem::copy_options::overwrite_existing);
 const auto before=scan(scratch,"native/src/pack.cpp"),after=scan(root,"native/src/pack.cpp");
 using Site=std::tuple<std::string,std::string,std::string>;
 std::array<std::set<Site>,3> public_before;
 std::array<std::size_t,3> raw_before{};
 std::map<std::pair<std::string,std::string>,std::size_t> other_before,other_after;
 auto identity=[](const auto& s){return std::make_pair(std::regex_replace(s.function,std::regex("<lambda@[0-9]+>"),"<lambda>"),s.detector);};
 for(const auto& s:before.quantization){const int f=family(s.function);if(f<0)++other_before[identity(s)];else{public_before[f].emplace(s.function,s.site,s.detector);++raw_before[f];}}
 for(const auto& s:after.quantization){if(family(s.function)>=0)throw std::runtime_error("unmigrated approved boundary "+s.site);++other_after[identity(s)];}
 if(public_before[0].size()!=14||public_before[1].size()!=34||public_before[2].size()!=16||raw_before[0]!=23||raw_before[1]!=92)throw std::runtime_error("independent before14/34/16 census changed");
 if(other_before!=other_after)throw std::runtime_error("remaining unowned families changed");
 if(!after.quantization.empty())throw std::runtime_error("combined pack retains raw boundary");
 NativeQuantizations all;register_native_quantizations(all);
 if(all.declarations().size()!=155)throw std::runtime_error("expected155 central declarations");
 const std::array<std::string,3> files{{"pack_search_precision.cpp","pack_plain_precision.cpp","pack_grid_precision.cpp"}};
 const std::array<std::size_t,3> expected{{9,18,6}};
 for(std::size_t i=0;i<files.size();++i){
  NativeQuantizations selected;for(const auto& d:all.declarations()){
   const bool owned=i==0?pack_search_precision_fixture::added(d.name):i==1?pack_plain_precision_fixture::added(d.name):pack_grid_precision_fixture::added(d.name);
   if(owned){if(d.symbol!="native/src/"+files[i]+"::schgen::"+d.name)throw std::runtime_error("wrong scalar source identity");selected.declare(d);}
  }
  if(selected.declarations().size()!=expected[i])throw std::runtime_error("missing exact family");
  const auto scalar=scan(root,"native/src/"+files[i]);NativeLedger ledger;
  std::set<Site> public_scalar;for(const auto& s:scalar.quantization)public_scalar.emplace(s.function,s.site,s.detector);
  if((i==0&&scalar.quantization.size()!=18)||(i==1&&scalar.quantization.size()!=36)||(i==2&&public_scalar.size()!=7))throw std::runtime_error("scalar census changed");
  const auto result=check_native_audits(scalar,ledger,selected);if(!result.ok)throw std::runtime_error(result.summary());
  for(const auto& d:selected.declarations()){
   if(!scalar.functions.count(d.symbol)||!std::any_of(scalar.quantization.begin(),scalar.quantization.end(),[&](const auto& s){return s.function==d.symbol;}))throw std::runtime_error("no real scalar body "+d.name);
   NativeQuantizations missing;for(const auto& other:selected.declarations())if(other.name!=d.name)missing.declare(other);
   if(check_native_audits(scalar,ledger,missing).ok)throw std::runtime_error("missing-registration mutation accepted "+d.name);
  }
 }
 std::cout<<"PASS original14/34/16 reported sites ->0;155 registrations;9/18/6 genuine scalar families;33 missing-registration mutations rejected; remaining unowned invariants unchanged\n";
}
inline std::filesystem::path scratch_path(){return std::filesystem::temp_directory_path()/("pack-combined-source-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));}
}
