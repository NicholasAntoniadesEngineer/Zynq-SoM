#include "ledger_accounting_fixture.hpp"
#include "pack_plain_observer.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "pack_plain_adapter_contracts.hpp"
#include "placement_precision_fixture.hpp"
#include "pcb_placement_fixture.hpp"
#include "schgen/native_audit_state.hpp"
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
std::ostringstream legacy;
#include <thread>
using namespace schgen;
using namespace plain_fixture;
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

int main(int argc,char** argv){try{
 require(argc==2,"repository root required");
 pack_geometry_adapter_contracts::run();
 pack_plain_adapter_contracts::run();

 for(const auto* project:{"carrier","devkit_mini"}){
  auto f=placement_fixture::load(argv[1],project);
  begin();auto result=build_pcb_model(f.input);auto entries=end();
  const auto q=pcb_placement_accounting(result);
  receipt(q.quantization_engagements,entries);
  auto plan=result.floorplan.plan;
  plan.accounting.quantization_engagements=placement_precision_fixture::select(select(plan.accounting.quantization_engagements,false),false);
  plan.accounting.quantization_engagements=ledger_accounting_fixture::before_initial_receipt_fix(plan.accounting.quantization_engagements);
  legacy<<project<<'\n';node(pcb_model_json(result.model));node(floorplan_plan_json(plan));
  for(const auto& [n,v]:ledger_accounting_fixture::before_initial_receipt_fix(placement_precision_fixture::select(select(q.quantization_engagements,false),false)))legacy<<std::quoted(n)<<' '<<v<<'\n';
  for(const auto& [n,v]:entries)std::cerr<<project<<" entry "<<n<<' '<<v<<'\n';
  begin();auto again=pcb_placement_accounting(result);
  require(end().empty()&&again.quantization_engagements==q.quantization_engagements,"replay created work");

  // Independently frozen complete emitted PCB bytes, not a new candidate golden.
  const auto frozenModel=pcb_model_from_json(f.model,f.expected_pool);
  QuantizationCounts emittedCounts;begin();
  const auto emission=render_pcb(frozenModel,pcb_emit_policy(f.input.floorplan.project),&emittedCounts);
  receipt(emittedCounts,end());
  const auto frozen=placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/output_precision_legacy.txt");
  const auto boardStart=frozen.find(std::string("BOARD ")+project+'\n');
  require(boardStart!=std::string::npos,"frozen board section absent");
  const auto sizeStart=frozen.find("\npcb ",boardStart);
  require(sizeStart!=std::string::npos,"frozen PCB absent");
  const auto payloadStart=frozen.find('\n',sizeStart+1)+1;
  const auto size=std::stoull(frozen.substr(sizeStart+5,payloadStart-sizeStart-6));
  require(emission.pcb==frozen.substr(payloadStart,size),"complete frozen emitted PCB bytes changed");
  QuantizationCounts verificationCounts;begin();
  const auto gates=check_pcb_placement_gates(f.input,result.model,&verificationCounts);
  receipt(verificationCounts,end());
  const auto retained=verificationCounts;begin();(void)gates.composition.text();(void)gates.placement_flow.summary();
  require(end().empty()&&retained==verificationCounts,"report replay manufactured counts");

 }
 require(legacy.str()==placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/pack_geometry_precision/legacy-board-output.txt"),"frozen geometry14 board bytes and old counts changed");
 std::cerr<<"plain18 actual board/verification/emission receipts and frozen full bytes PASS\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
