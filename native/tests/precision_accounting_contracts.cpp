// Only precision_ops.cpp is compiled with -finstrument-functions -fno-inline.
// This test observer is never linked into production or used as solver census.
#include "pcb_placement_fixture.hpp"
#include "schgen/precision_ops.hpp"
#include "floorplan_precision_fixture.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/experiment_observers.hpp"
#include <array>
#include <atomic>
#include <iomanip>
#include <iostream>

namespace {
using namespace schgen;
using namespace placement_fixture;
const std::array<std::string,6> names{{"estimate_position_precision","estimate_pad_precision",
    "breathe_delta_precision","breathe_commit_precision","breathe_forward_steps","breathe_retreat_steps"}};
std::array<std::atomic<std::size_t>,6> observations{};
std::atomic<bool> enabled{false};
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
void begin(){for(auto& n:observations)n=0;enabled=true;}
QuantizationCounts end(){enabled=false;QuantizationCounts out;for(std::size_t i=0;i<names.size();++i)if(observations[i])out[names[i]]=observations[i].load();return out;}
QuantizationCounts decoded(const JsonNode& node){QuantizationCounts out;for(const auto& [name,n]:node.object_value)out[name]=static_cast<std::size_t>(n.number_value);return out;}
bool added(const std::string& name){return std::find(names.begin(),names.end(),name)!=names.end();}
// Connector, floorplan and occupancy additions are independently entry-instrumented,
// fixture-compared and replay-tested by their dedicated contracts. Keep the
// original twenty and first six additions as immutable migrations here.
QuantizationCounts select(const QuantizationCounts& counts,bool new_only){QuantizationCounts out;for(const auto& [name,n]:counts)if(added(name)==new_only&&name!="mechanical_direction_component"&&name!="stage_direction_component"&&!floorplan_precision_fixture::added(name)&&!occupancy_precision_fixture::added(name)&&!legalize_precision_fixture::added(name)&&!stage_precision_fixture::added(name))out[name]=n;return out;}
void show(const QuantizationCounts& counts){std::cout<<'{';bool first=true;for(const auto& [name,n]:counts){if(!first)std::cout<<',';first=false;std::cout<<std::quoted(name)<<':'<<n;}std::cout<<'}';}
void registry(){
    NativeQuantizations q;register_native_quantizations(q);require(q.declarations().size()==64,"40 prior plus seven legalizer and seventeen stage operations");
    const std::array<std::vector<double>,6> arguments{{{11.24955},{11.24955},{11.24955},{11.24955},{1.7,.25},{1.7,.25}}};
    const std::array<double,6> expected{{estimate_position_precision(11.24955),estimate_pad_precision(11.24955),
        breathe_delta_precision(11.24955),breathe_commit_precision(11.24955),7,6}};
    for(std::size_t i=0;i<names.size();++i){
        const auto declarations=q.declarations();const auto d=std::find_if(declarations.begin(),declarations.end(),[&](const auto& x){return x.name==names[i];});
        require(d!=declarations.end()&&d->arity==arguments[i].size(),"honest callback arity "+names[i]);
        require(d->symbol=="native/src/precision_ops.cpp::schgen::"+names[i],"actual compiled implementation identity");
        begin();const auto result=q.invoke(names[i],arguments[i]);const auto calls=end();
        require(result==expected[i]&&calls==QuantizationCounts{{names[i],1}},"registry invokes exactly its real scalar function");
    }
}
void live(const std::filesystem::path& root,const std::string& board,bool single,const JsonNode& baseline,
          const JsonNode* additions,bool capture,bool& first){
    const auto name=board+(single?"_single":"");auto fixture=load(root,board);if(single)fixture.input.two_side=false;
    begin();auto result=build_pcb_model(fixture.input);const auto measured=end();
    const auto total=pcb_placement_accounting(result);
    const auto& expected=field(baseline,name);
    for(const auto& [label,counts]:std::vector<std::pair<std::string,QuantizationCounts>>{
            {"floorplan",result.floorplan.plan.accounting.quantization_engagements},
            {"placement",result.placement_accounting.quantization_engagements},
            {"zone",result.zone_accounting.quantization_engagements},
            {"aggregate",total.quantization_engagements}})
        require(select(counts,false)==decoded(field(expected,label)),name+" original twenty counters exactly unchanged: "+label);
    require(select(total.quantization_engagements,true)==measured,name+" exported new counters equal independent compiled function entries");
    require(measured.count("estimate_position_precision")&&measured.count("estimate_pad_precision"),name+" actual estimate work observed");
    require(select(result.zone_accounting.quantization_engagements,true).empty(),"zone solve cannot inherit unrelated precision counts");
    if(additions){const auto& row=field(*additions,name);
        require(measured==decoded(field(row,"aggregate")),name+" independent additive count fixture");
        require(select(result.floorplan.plan.accounting.quantization_engagements,true)==decoded(field(row,"floorplan")),name+" exact additive floorplan ownership");
        require(select(result.placement_accounting.quantization_engagements,true)==decoded(field(row,"placement")),name+" exact additive placement ownership");
    }
    if(capture){if(!first)std::cout<<",\n";first=false;std::cout<<std::quoted(name)<<":{\"aggregate\":";show(measured);
        std::cout<<",\"floorplan\":";show(select(result.floorplan.plan.accounting.quantization_engagements,true));
        std::cout<<",\"placement\":";show(select(result.placement_accounting.quantization_engagements,true));std::cout<<'}';}
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
    begin();require(inbox.merge_once("solve",total)&&!inbox.merge_once("solve",total),"one actual invocation imports once");
    require(end().empty(),"accounting import never executes precision callbacks");
    for(const auto& n:names){const auto p=measured.find(n);require(q.engagements().at(n)==AuditInteger(p==measured.end()?0:static_cast<std::int64_t>(p->second)),"new solver census counted once");}
    const auto before=total.quantization_engagements;
    auto input=prepare_pcb_floorplan(fixture.input,build_pcb_zone_geometry(fixture.input));
    const auto input_before=input.accounting.quantization_engagements;
    begin();const auto probe=measure_floorplan_experiment_plan(input,result.floorplan.plan);const auto observed=end();
    require(observed.count("estimate_position_precision")&&observed.count("estimate_pad_precision"),"pure probe really executes separately observed precision");
    require(pcb_placement_accounting(result).quantization_engagements==before&&input.accounting.quantization_engagements==input_before,
            "observer measurement never mutates actual solver/input census");
    require(probe.w==result.floorplan.plan.board_w&&probe.h==result.floorplan.plan.board_h,"probe retains actual dimensions");
}
} // namespace
extern "C" void __cyg_profile_func_enter(void* fn,void*){
    if(!enabled.load(std::memory_order_relaxed))return;
    if(fn==reinterpret_cast<void*>(&schgen::estimate_position_precision))++observations[0];
    else if(fn==reinterpret_cast<void*>(&schgen::estimate_pad_precision))++observations[1];
    else if(fn==reinterpret_cast<void*>(&schgen::breathe_delta_precision))++observations[2];
    else if(fn==reinterpret_cast<void*>(&schgen::breathe_commit_precision))++observations[3];
    else if(fn==reinterpret_cast<void*>(&schgen::breathe_forward_steps))++observations[4];
    else if(fn==reinterpret_cast<void*>(&schgen::breathe_retreat_steps))++observations[5];
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    if(argc<2||argc>3||(argc==3&&std::string(argv[2])!="--capture-additive"))throw std::runtime_error("repo [--capture-additive]");
    const std::filesystem::path root=argv[1];const bool capture=argc==3;registry();
    const auto baseline=parse_json_file((root/"native/tests/data/precision_ops/legacy_counts.json").string());
    JsonNode additions;if(!capture)additions=parse_json_file((root/"native/tests/data/precision_ops/additive_counts.json").string());
    bool first=true;if(capture)std::cout<<"{\n";
    for(const auto* name:{"devkit_mini","carrier"})live(root,name,false,baseline,capture?nullptr:&additions,capture,first);
    live(root,"devkit_mini",true,baseline,capture?nullptr:&additions,capture,first);
    if(capture)std::cout<<"\n}\n";
    std::cerr<<checks<<" independent precision accounting contracts passed\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"Precision accounting FAILED: "<<e.what()<<'\n';return 1;}}
