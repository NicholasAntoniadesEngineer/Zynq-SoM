#include "schgen/native_audit_state.hpp"
#include "schgen/pack_search_precision.hpp"
#include <iostream>
#include <regex>
#include <fstream>
#include "pack_search_precision_fixture.hpp"
using namespace schgen;
int main(int argc,char** argv){try{
 if(argc!=3)throw std::runtime_error("repository root and private scratch root required");
 const std::filesystem::path root=argv[1],scratch=argv[2];
 if(std::filesystem::exists(scratch))throw std::runtime_error("source proof scratch must be fresh");
 std::filesystem::create_directories(scratch/"native");
 // Frozen prechange source uses the same full header context, with its own
 // original declarations restored. Never mutate the source checkout.
 std::filesystem::copy(root/"native/include",scratch/"native/include",std::filesystem::copy_options::recursive);
 std::filesystem::copy(root/"native/src",scratch/"native/src",std::filesystem::copy_options::recursive);
 const auto frozen=root/"native/tests/data/pack_search_precision";
 std::filesystem::copy_file(frozen/"before-pack.cpp.txt",scratch/"native/src/pack.cpp",std::filesystem::copy_options::overwrite_existing);
 std::filesystem::copy_file(frozen/"before-pack.hpp.txt",scratch/"native/include/schgen/pack.hpp",std::filesystem::copy_options::overwrite_existing);
 auto scan=[](const char* root,const std::vector<CppAuditSource>& files){
  CppAuditOptions o;o.workers=1;o.timeout=std::chrono::milliseconds(120000);
  o.flags={"-I"+(std::filesystem::path(root)/"native/include").string(),"-I"+(std::filesystem::path(root)/"native/src").string()};
  return scan_cpp_audit_sources(root,files,o);
 };
 auto selected=[](const auto& s){return s.function=="native/src/pack.cpp::schgen::fallback_via_sites"||s.function=="native/src/pack.cpp::schgen::seat_band";};
 auto before=scan(scratch.c_str(),{{"native/src/pack.cpp"}}),after=scan(root.c_str(),{{"native/src/pack.cpp"}});
 std::size_t events=0;std::set<std::tuple<std::string,std::string,std::string>> pub;
 std::map<std::pair<std::string,std::string>,std::size_t> prior_other,next_other;
 auto key=[](const auto& s){return std::make_pair(std::regex_replace(s.function,std::regex("<lambda@[0-9]+>"),"<lambda>"),s.detector);};
 for(const auto& s:before.quantization)if(selected(s)){++events;pub.emplace(s.function,s.site,s.detector);}else ++prior_other[key(s)];
 for(const auto& s:after.quantization)if(selected(s))throw std::runtime_error("unmigrated target "+s.site);else ++next_other[key(s)];
 if(pub.size()!=14||events!=23)throw std::runtime_error("before identities/events "+std::to_string(pub.size())+"/"+std::to_string(events));
 if(prior_other!=next_other)throw std::runtime_error("unrelated family counts changed");
 auto scalars=scan(root.c_str(),{{"native/src/pack_search_precision.cpp"}});
 NativeQuantizations all,r;register_native_quantizations(all);
 if(all.declarations().size()!=131)throw std::runtime_error("expected131 central declarations");
 for(const auto& d:all.declarations())if(pack_search_precision_fixture::added(d.name))r.declare(d);
 NativeLedger ledger;auto result=check_native_audits(scalars,ledger,r);
 if(!result.ok)throw std::runtime_error(result.summary());
 if(r.declarations().size()!=9)throw std::runtime_error("nine exact scalar declarations required");
 if(scalars.quantization.size()!=18)throw std::runtime_error("eighteen exact raw scalar events required");
 for(const auto& d:r.declarations()){
  if(!scalars.functions.count(d.symbol)||!std::any_of(scalars.quantization.begin(),scalars.quantization.end(),[&](const auto& s){return s.function==d.symbol;}))throw std::runtime_error("fake cover "+d.name);
  NativeQuantizations missing;for(const auto& other:r.declarations())if(other.name!=d.name)missing.declare(other);
  if(check_native_audits(scalars,ledger,missing).ok)throw std::runtime_error("removed cover escaped detection");
 }
 std::cout<<"PASS 14 public / 23 raw target findings -> zero; 9 real scalar symbols; "<<scalars.quantization.size()<<" raw scalar events; all 9 missing-cover negatives fail; unrelated pack families unchanged\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
