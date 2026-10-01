#include "pcb_placement_fixture.hpp"
#include "ledger_accounting_fixture.hpp"
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
 const QuantizationCounts expected=label.find("placement")!=std::string::npos
  ?QuantizationCounts{{"seat_lower_index",6},{"seat_upper_index",6},{"seat_vertical_extent",6},{"seat_coordinate_precision6dp",356},{"seat_coverage_precision4dp",6}}
  :label.find("carrier")!=std::string::npos
   ?QuantizationCounts{{"fallback_axis_count",8},{"fallback_coordinate_precision3dp",6510},{"fallback_rank_precision4dp",3255}}
   :QuantizationCounts{{"fallback_axis_count",6},{"fallback_coordinate_precision3dp",6048},{"fallback_rank_precision4dp",3024}};
 if(actual!=expected)throw std::runtime_error(label+" frozen independently observed scalar entry totals changed");
#endif
 for(const auto& [n,v]:actual)std::cerr<<label<<' '<<n<<' '<<v<<'\n';
 auto prior=search_proof::select(q,false);
 if(label.find("placement")!=std::string::npos)prior=ledger_accounting_fixture::before_initial_receipt_fix(prior);
 for(const auto& [n,v]:prior)std::cout<<std::quoted(n)<<' '<<v<<'\n';
}
int main(int argc,char** argv){try{
 if(argc!=2)throw std::runtime_error("frozen fixture root required");
 for(const std::string name:{"carrier","devkit_mini"}){
  auto f=placement_fixture::load(argv[1],name);
  search_proof::begin();auto result=build_pcb_model(f.input);
  auto accounting=pcb_placement_accounting(result);
  std::cout<<name<<'\n';finish(accounting.quantization_engagements,name+" placement");
  floorplan_precision_fixture::node(std::cout,pcb_model_json(result.model));
  auto plan=result.floorplan.plan;
  plan.accounting.quantization_engagements=search_proof::select(plan.accounting.quantization_engagements,false);
  plan.accounting.quantization_engagements=ledger_accounting_fixture::before_initial_receipt_fix(plan.accounting.quantization_engagements);
  floorplan_precision_fixture::node(std::cout,floorplan_plan_json(plan));
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
 std::cerr<<"search9 complete board/emission bytes and old counts PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
