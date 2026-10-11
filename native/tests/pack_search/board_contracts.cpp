#include "pcb_placement_fixture.hpp"
#include "pcb_placement_requirements.hpp"
#include "floorplan_precision_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#include "search_proof.hpp"
#include <iostream>
#include <iomanip>
using namespace schgen;
void finish(const QuantizationCounts& q,const std::string& label){
 auto actual=search_proof::end();
#ifdef SEARCH_CANDIDATE
 if(search_proof::select(q)!=actual)throw std::runtime_error(label+" real entries differ from receipt");
 for(const auto& [key,count]:actual){
  (void)count;
  for(bool erase:{false,true}){
   auto bad=q;if(erase)bad.erase(key);else ++bad[key];
   bool rejected=false;try{search_proof::receipt(bad);}catch(const std::runtime_error&){rejected=true;}
   if(!rejected)throw std::runtime_error(label+" corrupted receipt escaped independent observer");
  }
 }
#endif
 for(const auto& [n,v]:actual)std::cerr<<label<<' '<<n<<' '<<v<<'\n';
 for(const auto& [n,v]:q)std::cout<<std::quoted(n)<<' '<<v<<'\n';
}
int main(int argc,char** argv){try{
 if(argc!=2)throw std::runtime_error("frozen fixture root required");
 for(const std::string name:{"carrier","devkit_mini"}){
  auto f=placement_fixture::load(argv[1],name);
  search_proof::begin();auto result=build_pcb_model(f.input);
  auto accounting=pcb_placement_accounting(result);
  std::cout<<name<<'\n';finish(accounting.quantization_engagements,name+" placement");
  const auto require=[](bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);};
  const auto zones=build_pcb_zone_geometry(f.input);
  placement_requirements_test::structure(f.input,zones,result,require);
  placement_requirements_test::physical(f.input,result.model,require);
  floorplan_precision_fixture::node(std::cout,pcb_model_json(result.model));
  floorplan_precision_fixture::node(std::cout,floorplan_plan_json(result.floorplan.plan));
  for(const auto& event:accounting.fallback_events)std::cout<<std::quoted(event)<<'\n';
  auto policy=pcb_emit_policy(f.input.floorplan.project);
  QuantizationCounts emission;
  search_proof::begin();auto rendered=render_pcb(result.model,policy,&emission);
  finish(emission,name+" emission");
  if(!rendered.quantization_engagements.empty())throw std::runtime_error("external/internal emission double receipt");
  search_proof::begin();auto owned=render_pcb(result.model,policy);
  search_proof::receipt(owned.quantization_engagements);
  if(owned.quantization_engagements!=emission||owned.pcb!=rendered.pcb||
     owned.diagnostics!=rendered.diagnostics||owned.fallback_events!=rendered.fallback_events||
     owned.hidden_bottom_references!=rendered.hidden_bottom_references||owned.moved_references!=rendered.moved_references)
   throw std::runtime_error("default result-owned sink changed output or lost actual calls");
  std::cout<<rendered.pcb.size()<<'\n'<<rendered.pcb;
  for(const auto& s:rendered.diagnostics)std::cout<<std::quoted(s)<<'\n';
  for(const auto& s:rendered.fallback_events)std::cout<<std::quoted(s)<<'\n';
  std::cout<<rendered.hidden_bottom_references<<' '<<rendered.moved_references<<'\n';
  search_proof::begin();const auto replay=pcb_placement_accounting(result);
  if(!search_proof::end().empty()||replay.quantization_engagements!=accounting.quantization_engagements)throw std::runtime_error("receipt replay changed work");
 }
 std::cerr<<"search9 board requirements, emission and independently observed receipts PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
