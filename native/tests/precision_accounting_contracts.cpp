#include "pack_search_precision_fixture.hpp"
#include "pack_plain_precision_fixture.hpp"
#include "pack_grid_precision_fixture.hpp"
// Only precision_ops.cpp is compiled with -finstrument-functions -fno-inline.
// This test observer is never linked into production or used as solver census.
#include "pcb_placement_fixture.hpp"
#include "pcb_placement_requirements.hpp"
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
bool added(const std::string& name){return std::find(names.begin(),names.end(),name)!=names.end();}
// Connector, floorplan and occupancy additions are independently entry-instrumented,
// fixture-compared and replay-tested by their dedicated contracts. Keep the
// unrelated operation families out of this observer's ownership checks.
QuantizationCounts select(const QuantizationCounts& counts,bool new_only){QuantizationCounts out;for(const auto& [name,n]:counts)if(added(name)==new_only&&name!="mechanical_direction_component"&&name!="stage_direction_component"&&!floorplan_precision_fixture::added(name)&&!occupancy_precision_fixture::added(name)&&!legalize_precision_fixture::added(name)&&!stage_precision_fixture::added(name)&&!placement_precision_fixture::added(name)&&!output_precision_fixture::added(name)&&!pack_precision_fixture::added(name)&&!pack_geometry_precision_fixture::added(name)&&!pack_search_precision_fixture::added(name)&&!pack_plain_precision_fixture::added(name)&&!pack_grid_precision_fixture::added(name))out[name]=n;return out;}
void show(const QuantizationCounts& counts){std::cout<<'{';bool first=true;for(const auto& [name,n]:counts){if(!first)std::cout<<',';first=false;std::cout<<std::quoted(name)<<':'<<n;}std::cout<<'}';}
void registry(){
    const QuantizationCounts prior{{"fixed_part_grid",1},{"placement_unknown_future_precision",2},
        {"placement_turn_offset_precision4dp_typo",3},{"escape_unknown_precision",7},
        {"pack_shelf_pose_precision4dp_typo",11}};
    auto mixed=prior;for(const auto& name:placement_precision_fixture::names)mixed[name]=5;
    for(const auto& name:output_precision_fixture::names)mixed[name]=13;
    for(const auto& name:pack_precision_fixture::names)mixed[name]=17;
    require(select(mixed,false)==prior,"historical precision adapter removes only exact reviewed additions");
    NativeQuantizations q;register_native_quantizations(q);require(q.declarations().size()==156,"122 prior plus9 search plus18 plain plus6 grid plus1 edge tick operations");
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
void live(const std::filesystem::path& root,const std::string& board,bool single,bool capture,bool& first){
    const auto name=board+(single?"_single":"");auto fixture=load(root,board);if(single)fixture.input.two_side=false;
    begin();auto result=build_pcb_model(fixture.input);const auto measured=end();
    const auto total=pcb_placement_accounting(result);
    require(select(total.quantization_engagements,true)==measured,name+" exported new counters equal independent compiled function entries");
    require(measured.count("estimate_position_precision")&&measured.count("estimate_pad_precision"),name+" actual estimate work observed");
    require(select(result.zone_accounting.quantization_engagements,true).empty(),"zone solve cannot inherit unrelated precision counts");
    // These two estimator functions belong to floorplan_cross; the other four
    // are the placement breathe stage. Independently observed entries pin the
    // current owner, not the number of attempts a historical solver required.
    QuantizationCounts expected_plan,expected_placement;
    for(const auto& [op,n]:measured)
        (op==names[0]||op==names[1]?expected_plan:expected_placement)[op]=n;
    require(select(result.floorplan.plan.accounting.quantization_engagements,true)==expected_plan,name+" exact observed floorplan ownership");
    require(select(result.placement_accounting.quantization_engagements,true)==expected_placement,name+" exact observed placement ownership");
    const auto validate=[&](const QuantizationCounts& counts){require(select(counts,true)==measured,"independent receipt mismatch");};
    for(bool missing:{true,false}) {
        auto bad=total.quantization_engagements;
        if(missing)bad.erase(measured.begin()->first);else ++bad[measured.begin()->first];
        bool rejected=false;try{validate(bad);}catch(const std::runtime_error&){rejected=true;}
        require(rejected,"missing/invented precision work escaped actual-entry observer");
    }
    placement_requirements_test::structure(fixture.input,build_pcb_zone_geometry(fixture.input),result,require);
    placement_requirements_test::physical(fixture.input,result.model,require);
    std::cerr<<name<<" physical PASS "<<result.model.board_w<<'x'<<result.model.board_h
             <<" top="<<result.model.n_top<<" bottom="<<result.model.n_bottom<<'\n';
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
    bool first=true;if(capture)std::cout<<"{\n";
    for(const auto* name:{"devkit_mini","carrier"})live(root,name,false,capture,first);
    live(root,"devkit_mini",true,capture,first);
    if(capture)std::cout<<"\n}\n";
    std::cerr<<checks<<" independent precision accounting contracts passed\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"Precision accounting FAILED: "<<e.what()<<'\n';return 1;}}
