#include "pack_geometry_observer.hpp"
#include "pack_geometry_adapter_contracts.hpp"
#include "placement_precision_fixture.hpp"
#include "pcb_placement_fixture.hpp"
#include "ledger_accounting_fixture.hpp"
#include "schgen/native_audit_state.hpp"
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
std::ostringstream legacy;
#include <thread>
using namespace schgen;
using namespace geometry_fixture;
void require(bool b,const char* why){if(!b)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t b;std::memcpy(&b,&x,sizeof b);return b;}
void node(const JsonNode& n){
 legacy<<static_cast<int>(n.kind)<<' ';
 switch(n.kind){
 case JsonKind::Null:break;
 case JsonKind::Bool:legacy<<n.bool_value;break;
 case JsonKind::Number:legacy<<bits(n.number_value);break;
 case JsonKind::String:legacy<<std::quoted(n.string_value);break;
 case JsonKind::Array:legacy<<n.array_value.size()<<' ';for(const auto& v:n.array_value)node(v);break;
 case JsonKind::Object:legacy<<n.object_value.size()<<' ';for(const auto& [k,v]:n.object_value){legacy<<std::quoted(k)<<' ';node(v);}break;
 }legacy<<'\n';
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
 require(all.declarations().size()==131,"122 prior plus nine search");
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
  auto plan=result.floorplan.plan;
  auto old_counts=q.quantization_engagements;
#ifdef PACK_GEOMETRY_CANDIDATE
  old_counts=ledger_accounting_fixture::before_initial_receipt_fix(old_counts);
  plan.accounting.quantization_engagements=ledger_accounting_fixture::before_initial_receipt_fix(plan.accounting.quantization_engagements);
#endif
  plan.accounting.quantization_engagements=placement_precision_fixture::select(select(plan.accounting.quantization_engagements,false),false);
  legacy<<project<<'\n';node(pcb_model_json(result.model));node(floorplan_plan_json(plan));
  for(const auto& [n,v]:placement_precision_fixture::select(select(old_counts,false),false))legacy<<std::quoted(n)<<' '<<v<<'\n';
  for(const auto& [n,v]:entries)std::cerr<<project<<" entry "<<n<<' '<<v<<'\n';
  begin();auto again=pcb_placement_accounting(result);
  require(end().empty()&&again.quantization_engagements==q.quantization_engagements,"replay created work");
 }
 require(legacy.str()==placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/pack_geometry_precision/legacy-board-output.txt"),"frozen geometry14 board bytes and old counts changed");
 std::cerr<<"geometry14 boards, registry, scalar entries PASS\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
