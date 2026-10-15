#include "pack_geometry_observer.hpp"
#include "pack_geometry_adapter_contracts.hpp"
#include "placement_precision_fixture.hpp"
#include "pcb_placement_fixture.hpp"
#include "pcb_placement_requirements.hpp"
#include "schgen/native_audit_state.hpp"
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
std::ostringstream snapshot;
#include <thread>
using namespace schgen;
using namespace geometry_fixture;
void require(bool b,const char* why){if(!b)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t b;std::memcpy(&b,&x,sizeof b);return b;}
void node(const JsonNode& n){
 snapshot<<static_cast<int>(n.kind)<<' ';
 switch(n.kind){
 case JsonKind::Null:break;
 case JsonKind::Bool:snapshot<<n.bool_value;break;
 case JsonKind::Number:snapshot<<bits(n.number_value);break;
 case JsonKind::String:snapshot<<std::quoted(n.string_value);break;
 case JsonKind::Array:snapshot<<n.array_value.size()<<' ';for(const auto& v:n.array_value)node(v);break;
 case JsonKind::Object:snapshot<<n.object_value.size()<<' ';for(const auto& [k,v]:n.object_value){snapshot<<std::quoted(k)<<' ';node(v);}break;
 }snapshot<<'\n';
}
#ifdef PACK_GEOMETRY_CANDIDATE
void scalars(){
 using Op=double(*)(double,QuantizationCounts*);
 const std::array<Op,13> ops{{pack_pair_gap_precision4dp,pack_edge_component_precision4dp,pack_som_grid_precision0dp,pack_som_cell_precision4dp,pack_som_diameter_precision4dp,pack_som_component_pose_precision4dp,pack_som_band_component_precision4dp,pack_cout_pose_precision4dp,pack_bulk_pose_precision4dp,pack_zone_component_precision4dp,pack_rotated_offset_precision4dp,pack_corridor_bound_precision4dp,pack_mirror_offset_precision4dp}};
 for(std::size_t i=0;i<ops.size();++i){
  const int digits=i==2?0:4;
  for(int k=-128;k<=128;++k){
   const double mid=(k+.5)/(digits?10000.:1.);
   for(double x:{std::nextafter(mid,-INFINITY),mid,std::nextafter(mid,INFINITY)}){
    QuantizationCounts q;begin();const auto v=ops[i](x,&q);auto entries=end();
    require(bits(v)==bits(py_round(x,digits)),"round result changed");
    receipt(q,entries);require(entries==QuantizationCounts{{names[i],1}},"missing scalar entry");
   }
  }
  for(double x:{-0.,0.,1e-300,-1e-300,1e300,double(INFINITY),double(-INFINITY),double(NAN)}){
   QuantizationCounts q;begin();auto v=ops[i](x,&q);auto entries=end();receipt(q,entries);
   require(bits(v)==bits(py_round(x,digits)),"IEEE scalar changed");
  }
 }
 for(int n=-10000;n<=10000;++n){
  QuantizationCounts q;begin();const int v=pack_som_grid_trunc(n/16.,&q);auto entries=end();
  require(v==n/16,"independent integer oracle differs");receipt(q,entries);
 }
 for(double v:{double(INFINITY),double(NAN),2147483648.,-2147483649.}){
  QuantizationCounts q;begin();bool rejected=false;try{(void)pack_som_grid_trunc(v,&q);}catch(const std::out_of_range&){rejected=true;}
  auto entries=end();require(rejected,"bad conversion accepted");receipt(q,entries);require(entries==QuantizationCounts{{names[13],1}},"rejected narrowing entry lost");
 }
 // Registry proof uses explicit reviewed declarations, never scanner-derived symbols.
 NativeQuantizations all,r;register_native_quantizations(all);
 require(all.declarations().size()==156,"122 prior plus9 search plus18 plain plus6 grid plus1 edge tick");
 for(const auto& d:all.declarations())if(geometry_fixture::added(d.name))r.declare(d);
 require(r.declarations().size()==14,"declaration count");
 for(const auto& d:r.declarations()){
  require(d.arity==1&&d.symbol=="native/src/pack_geometry_precision.cpp::schgen::"+d.name,"wrong scalar identity");
  begin();const auto v=r.invoke(d.name,{1.23455});auto entries=end();
  const double expected=d.name==names[13]?1.:py_round(1.23455,d.name==names[2]?0:4);
  require(bits(v)==bits(expected)&&entries==QuantizationCounts{{d.name,1}},"registry not genuine");
  const auto q=r.engagements();begin();bool rejected=false;try{r.invoke(d.name,{});}catch(const std::invalid_argument&){rejected=true;}
  require(rejected&&end().empty()&&r.engagements()==q,"wrong arity entered scalar");
 }
 // Large valid grid whose old integer addition would overflow: division rewrite,
 // not a claim of equality against undefined original arithmetic.
 const auto large=som_decoupling_grid(20,20,INT32_MAX,0);
 const int c=std::get<2>(large),rows=std::get<3>(large);
 require(rows==(static_cast<std::int64_t>(INT32_MAX)+c-1)/c,"large row count");
 std::array<QuantizationCounts,2> owned;
 begin();std::array<std::thread,2> threads;
 for(std::size_t i=0;i<2;++i)threads[i]=std::thread([&,i]{
   for(int k=0;k<20;++k)(void)mirror_offset_x(1,2,{0,0,3,4},8,&owned[i]);
 });
 for(auto& t:threads)t.join();auto entries=end();
 require(owned[0]==owned[1]&&owned[0]==QuantizationCounts{{"pack_mirror_offset_precision4dp",20}}
  &&entries==QuantizationCounts{{"pack_mirror_offset_precision4dp",40}},"sink isolation");
}
#endif
int main(int argc,char** argv){try{
 require(argc==2,"repository root required");
 pack_geometry_adapter_contracts::run();
#ifdef PACK_GEOMETRY_CANDIDATE
 scalars();
#endif
 for(const auto* project:{"carrier","devkit_mini"}){
  auto f=placement_fixture::load(argv[1],project);
  begin();auto result=build_pcb_model(f.input);auto entries=end();
  const auto q=pcb_placement_accounting(result);
  receipt(q.quantization_engagements,entries);
  // Keep primitive scalar fixtures immutable, but qualify whole-board output
  // against source identity/physical constraints and repeatability of CURRENT
  // inputs. Historical optimizer coordinates and work counts are not laws.
  const auto zones=build_pcb_zone_geometry(f.input);
  const auto checked=[](bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);};
  placement_requirements_test::structure(f.input,zones,result,checked);
  placement_requirements_test::physical(f.input,result.model,checked);
  snapshot.str("");snapshot.clear();node(pcb_model_json(result.model));node(floorplan_plan_json(result.floorplan.plan));
  const auto first=snapshot.str();
  begin();const auto repeated=build_pcb_model(f.input);const auto repeated_entries=end();
  const auto repeated_counts=pcb_placement_accounting(repeated);
  receipt(repeated_counts.quantization_engagements,repeated_entries);
  require(entries==repeated_entries&&q.quantization_engagements==repeated_counts.quantization_engagements&&
          q.fallback_events==repeated_counts.fallback_events,"identical current inputs changed actual work receipts");
  snapshot.str("");snapshot.clear();node(pcb_model_json(repeated.model));node(floorplan_plan_json(repeated.floorplan.plan));
  require(first==snapshot.str(),"identical current inputs changed model/plan/ledger bytes");
  if(!entries.empty()) {
    auto bad=q.quantization_engagements;bad.erase(entries.begin()->first);
    bool rejected=false;try{receipt(bad,entries);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"missing geometry work escaped observer");
    bad=q.quantization_engagements;++bad[entries.begin()->first];
    rejected=false;try{receipt(bad,entries);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"invented geometry work escaped observer");
  }
  for(const auto& [n,v]:entries)std::cerr<<project<<" entry "<<n<<' '<<v<<'\n';
  begin();auto again=pcb_placement_accounting(result);
  require(end().empty()&&again.quantization_engagements==q.quantization_engagements,"replay created work");
 }
 std::cerr<<"geometry14 both-board physical requirements, current reproducibility, registry and scalar entries PASS\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
