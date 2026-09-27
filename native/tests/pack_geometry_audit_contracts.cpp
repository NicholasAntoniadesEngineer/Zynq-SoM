#include "pack_geometry_observer.hpp"
#include "schgen/native_audit_state.hpp"
#include <iostream>
#include <regex>
using namespace schgen;
int main(int argc,char** argv){try{
 if(argc!=2&&argc!=3)throw std::runtime_error("[before-root] after-root required");
 auto scan=[](const char* root,const std::vector<CppAuditSource>& files){
  CppAuditOptions o;o.workers=1;o.timeout=std::chrono::milliseconds(120000);
  o.flags={"-I"+(std::filesystem::path(root)/"native/include").string(),
           "-I"+(std::filesystem::path(root)/"native/src").string()};
  return scan_cpp_audit_sources(root,files,o);
 };
 const std::set<std::string> functions{
 "pair_gap","edge_components","som_decoupling_grid","som_decoupling_cells","som_components",
 "cout_column_centers","bulk_cap_pose","zone_components_assemble","rotate_offsets_90",
 "corridor_board_rect","mirror_offset_x"};
 auto selected=[&](const auto& s){for(const auto& f:functions)if(s.function=="native/src/pack.cpp::schgen::"+f)return true;return false;};
 CppSourceCensus before;
 if(argc==3)before=scan(argv[1],{{"native/src/pack.cpp"}});
 auto after=scan(argv[argc-1],{{"native/src/pack.cpp"}});
 std::set<std::tuple<std::string,std::string,std::string>> public_before;
 std::size_t raw=0;
 std::map<std::pair<std::string,std::string>,std::size_t> other_before,other_after;
 auto unrelated=[](const auto& s){return std::make_pair(std::regex_replace(s.function,std::regex("<lambda@[0-9]+>"),"<lambda>"),s.detector);};
 for(const auto& s:before.quantization)if(selected(s)){++raw;public_before.emplace(s.function,s.site,s.detector);}else ++other_before[unrelated(s)];
 for(const auto& s:after.quantization)if(selected(s))throw std::runtime_error("raw target remains "+s.site);else ++other_after[unrelated(s)];
 if(argc==3&&(public_before.size()!=27||raw!=69))throw std::runtime_error("before counts "+std::to_string(public_before.size())+"/"+std::to_string(raw));
 if(argc==3&&other_before!=other_after)throw std::runtime_error("out-of-scope pack operation-family counts changed");
 auto scalars=scan(argv[argc-1],{{"native/src/pack_geometry_precision.cpp"}});
 NativeQuantizations all,r;register_native_quantizations(all);
 if(all.declarations().size()!=122)throw std::runtime_error("expected122 production declarations");
 for(const auto& d:all.declarations())if(geometry_fixture::added(d.name))r.declare(d);
 if(r.declarations().size()!=14)throw std::runtime_error("expected14 exact geometry declarations");
 NativeLedger ledger;
 const auto result=check_native_audits(scalars,ledger,r);
 if(!result.ok)throw std::runtime_error(result.summary());
 if(scalars.quantization.size()!=27)throw std::runtime_error("scalar events "+std::to_string(scalars.quantization.size()));
 for(const auto& d:r.declarations()){
  if(!scalars.functions.count(d.symbol)||!std::any_of(scalars.quantization.begin(),scalars.quantization.end(),[&](const auto& s){return s.function==d.symbol;}))
   throw std::runtime_error("missing scalar boundary "+d.name);
  NativeQuantizations missing;
  for(const auto& other:r.declarations())if(other.name!=d.name)missing.declare(other);
  if(check_native_audits(scalars,ledger,missing).ok)throw std::runtime_error("missing registration not detected "+d.name);
 }
 if(argc==3)std::cout<<"Before: 27 public / 69 raw target findings; unrelated pack families unchanged\n";
 std::cout<<"PASS: zero raw target findings;14 actual scalar symbols /27 raw events;14 missing-registration negatives rejected\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
