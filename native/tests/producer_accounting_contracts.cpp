// Independently observes math-function entry, not producer counter increments.
// Compile quantize.cpp and native_audit_quantize.cpp with -finstrument-functions
// -fno-inline for this executable ONLY. Do not instrument this test TU.
#include "pcb_placement_fixture.hpp"
#include "pcb_placement_internal.hpp"
#include "native_audit_quantize_internal.hpp"
#include "schgen/legalize.hpp"
#include "schgen/native_audit_state.hpp"
#include <iostream>

namespace {
using namespace schgen;
struct Calls { std::size_t fixed=0, corridor=0, credit=0, legal=0, refit=0; } calls;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
template<class Error,class F> void rejects(F fn,const std::string& why){
    bool yes=false;try{fn();}catch(const Error&){yes=true;}require(yes,why);
}
std::size_t count(const QuantizationCounts& q,const std::string& name){
    const auto p=q.find(name);return p==q.end()?0:p->second;
}
void measured(const QuantizationCounts& q,const Calls& observed,const std::string& context){
    require(count(q,"fixed_part_grid")+count(q,"breathe_anchor_grid")+count(q,"evict_corridor_grid")==observed.fixed,context+" independent fixed-grid calls, including nested corridor helper");
    require(count(q,"evict_corridor_grid")==observed.corridor,context+" independent corridor calls");
    require(count(q,"quant_credit")==observed.credit,context+" independent credit calls: reported="+std::to_string(count(q,"quant_credit"))+" observed="+std::to_string(observed.credit));
    require(count(q,"legalize_pose_quantum")==observed.legal,context+" independent attempted legalizer snaps");
    require(count(q,"refit_pose_precision")==observed.refit,context+" independent attempted refit snaps");
}
void overflow(){
    QuantizationCounts q{{"fixed_part_grid",SIZE_MAX}};auto before=q;
    rejects<std::overflow_error>([&]{checked_quantization_add(q,"fixed_part_grid");},"producer single-add overflow");
    require(q==before,"producer single overflow preserves state");
    rejects<std::overflow_error>([&]{checked_quantization_merge(q,{{"est_via_cost",7},{"fixed_part_grid",1}});},"producer batch overflow");
    require(q==before,"producer batch has no partial valid-prefix write");
    checked_quantization_add(q,"fixed_part_grid",0);require(q==before,"producer exact maximum accepts zero");
    PcbStageInput in;pcb_stage::Engine e(in);e.quantization["quant_credit"]=SIZE_MAX;
    rejects<std::overflow_error>([&]{e.credit(1);},"stage actual credit boundary rejects overflow");
    q={{"quant_credit",SIZE_MAX}};
    rejects<std::overflow_error>([&]{spatial_bounds_accounted(0,0,.3,.5,20,2,&q);},"spatial source checks overflow");
    const std::vector<std::tuple<double,double,double,double,double,double,double,int>> rows{{0,0,-1,-1,1,1,0,3}};
    rejects<std::overflow_error>([&]{zone_fanout_members_rows_accounted(rows,3,{{8,1.5}},2,&q);},"fanout source checks overflow");
    const auto below=zone_fanout_members_rows_accounted(rows,4,{{8,1.5}},2,&q);
    require(std::get<5>(below.at(0))==0&&q.at("quant_credit")==SIZE_MAX,"caller pin threshold preserved; no credit for unqualified row");
    q.clear();calls={};const auto qualified=zone_fanout_members_rows_accounted(rows,3,{{8,1.7}},2,&q);
    require(std::get<5>(qualified.at(0))==quant_credit(1.7),"caller fanout tier retained");
    require(q.at("quant_credit")==1,"one qualifying row calls and counts exactly once");
}
void legalizer(){
    auto run=[](const std::vector<double>& seed_x,const std::vector<double>& seed_y,QuantizationCounts& q){
        return legalize_descend_passes_accounted({"a"},{1},{2},seed_x,seed_y,{}, {}, {}, {}, {},0,0,false,true,1,.05,8,&q);
    };
    calls={};QuantizationCounts q;auto still=run({1.1},{2.2},q);
    require(still==std::make_pair(std::vector<double>{1},std::vector<double>{2}),"unchanged legalizer coordinates");
    require(q.at("legalize_pose_quantum")==2,"unchanged coordinates each still snapped once");measured(q,calls,"unchanged legalizer");
    q.clear();calls={};auto moved=run({2.7},{3.7},q);
    require(moved==std::make_pair(std::vector<double>{2.5},std::vector<double>{3.5}),"legalizer arithmetic unchanged");
    require(q.at("legalize_pose_quantum")==4,"changed pass plus no-motion trial pass counted");measured(q,calls,"moving legalizer");
    q={{"legalize_pose_quantum",SIZE_MAX}};
    rejects<std::overflow_error>([&]{run({1},{2},q);},"legalizer source rejects overflow before snap");
    // Existing independent fixture deliberately reverts compaction after snaps.
    FloorplanLegalizeInput in;in.board_w=100;in.board_h=100;in.som_core_page={65,65,85,85};in.compact=true;
    for(const auto& name:{"a","b"})in.metrics[name]={{{"p",5,5}},{{"p",0,0,10,10}},{10,10}};
    in.index.hard.push_back({"flow_hop","a","a","b",{},"test",true,{},{}});
    in.index.hard.push_back({"far_min","a","a","b",30.,"test",true,{},{}});
    std::vector<FloorplanLegalizeVar> vars{{"a",10,10,{5,5},5,5},{"b",10,10,{60,5},60,5}};
    std::vector<std::string> log;q.clear();calls={};
    require(floorplan_legalize_compact_accounted(in,vars,log,q),"reverted compact solve remains feasible");
    require(std::find(log.begin(),log.end(),"compaction REVERTED (would break a hard term or separation)")!=log.end(),"actual compact trial reverted");
    require(!q.empty()&&q.at("legalize_pose_quantum")>0,"reverted trial retains engagements");measured(q,calls,"reverted compaction");
}
void refit(){
    auto fp=pcb_check_footprint("precision.kicad_mod","(footprint precision (layer F.Cu) (pad 1 smd rect (at 0 0) (size 1 1) (layers F.Cu F.Paste F.Mask)))");
    PcbStageInput in;in.sheet="test";in.refs={"C1","C2"};in.board_refs={{"IN","C1"},{"OUT","C2"}};
    in.footprints={{"C1",fp},{"C2",fp}};in.bbox_of={{"C1",{-1,-1,1,1}},{"C2",{-1,-1,1,1}}};
    in.contract=parse_json_text("{\"roles\":{\"OUT\":\"output\"},\"external\":{\"output_roles\":[\"output\"]}}");
    FloorplanOffsets xy{{"C1",{10.12345,10}},{"C2",{20.12345,10}}};
    calls={};const auto rejected=refit_pcb_stage_facing_accounted(in,xy,{}, {100,10},{},{});
    require(!rejected.poses,"incumbent already faces downstream");require(rejected.quantization_engagements.at("refit_pose_precision")==4,"two coordinates per rejected refit member");measured(rejected.quantization_engagements,calls,"rejected refit");
    calls={};const auto accepted=refit_pcb_stage_facing_accounted(in,xy,{}, {0,10},{},{});
    require(accepted.poses.has_value(),"opposite downstream accepts half-turn");require(accepted.quantization_engagements.at("refit_pose_precision")==4,"accepted refit same candidate work");measured(accepted.quantization_engagements,calls,"accepted refit");
    const double cx=(9.62345+20.62345)/2;
    for(const auto& [name,p]:xy){const auto old=turn_origin_180(cx,10,p.first,p.second,0,0,4);
        require(std::get<0>(accepted.poses->at(name))==old.first&&std::get<1>(accepted.poses->at(name))==old.second,"refit exact pre-instrumentation half-turn math");}
    in.contract=parse_json_text("{\"external\":{\"output_roles\":[]}}");calls={};
    const auto early=refit_pcb_stage_facing_accounted(in,xy,{}, {0,10},{},{});
    require(!early.poses&&early.quantization_engagements.empty()&&calls.refit==0,"no fabricated refit snaps when no output exists");
}
void ownership(){
    PcbPlacementResult r;r.floorplan.plan.accounting.quantization_engagements={{"quant_credit",7}};
    r.floorplan.plan.accounting.fallback_events={"cand_cap_truncated"};
    r.zone_accounting={{{"quant_credit",3}},{"seat_node_budget"}};
    r.placement_accounting={{{"quant_credit",2}},{"corridor_evict_moved"}};
    rejects<std::logic_error>([&]{pcb_placement_accounting(r);},"unknown floorplan ancestry must not guess");
    r.zone_accounting_ownership=PcbZoneAccountingOwnership::IncludedInFloorplan;auto once=pcb_placement_accounting(r);
    require(once.quantization_engagements.at("quant_credit")==9,"included zone work not recounted");
    require(once.fallback_events==std::vector<std::string>{"cand_cap_truncated","corridor_evict_moved"},"included zone events not recounted");
    r.zone_accounting_ownership=PcbZoneAccountingOwnership::SeparateFromFloorplan;auto twice=pcb_placement_accounting(r);
    require(twice.quantization_engagements.at("quant_credit")==12,"independent placement and planning zones both count");
    require(twice.fallback_events==std::vector<std::string>{"seat_node_budget","cand_cap_truncated","corridor_evict_moved"},"separate zone events keep execution order");
    r.placement_accounting.quantization_engagements["quant_credit"]=SIZE_MAX;
    rejects<std::overflow_error>([&]{pcb_placement_accounting(r);},"aggregate overflow rejects");
}
void live(const std::filesystem::path& root,const std::string& name){
    auto f=placement_fixture::load(root,name);const auto zones=build_pcb_zone_geometry(f.input);
    pcb_placement::Placer p(f.input,zones,f.stage);p.seed();
    auto step=[&](const std::string& label,auto action){
        const auto before=p.ctx.quantization;calls={};action();const auto observed=calls;
        auto delta=p.ctx.quantization;for(const auto& [k,v]:before)delta[k]-=v;
        measured(delta,observed,name+"/"+label);
    };
    step("l4",[&]{p.l4_pull();});step("edge",[&]{p.edge_seat();});
    step("breathe-A",[&]{p.breathe("A");});step("breathe-B",[&]{p.breathe("B");});
    step("refit",[&]{p.refit();});step("reorder",[&]{p.reorder();});step("evict",[&]{p.evict();});
    p.checkpoint("corridor_eviction"); // same freeze boundary as production
    std::size_t fixed_coordinates=0;for(const auto& [r,key]:p.geometry.resolvable){(void)key;if(!p.grid_placed.count(r))fixed_coordinates+=2;}
    step("instantiate",[&]{p.instantiate();});
    require(count(p.ctx.quantization,"fixed_part_grid")==fixed_coordinates,name+" exactly two coordinate snaps per non-grid-placed instance");
    require(count(p.ctx.quantization,"breathe_anchor_grid")>0,name+" actual breathing trials occurred");
    calls={};const auto result=build_pcb_model(f.input);const auto observed=calls;
    require(result.zone_accounting_ownership==PcbZoneAccountingOwnership::IncludedInFloorplan,name+" production normal ownership explicit");
    require(result.placement_accounting.quantization_engagements==p.ctx.quantization,name+" every placement-local engagement exported");
    auto legacy=result.zone_accounting.fallback_events;legacy.insert(legacy.end(),result.placement_accounting.fallback_events.begin(),result.placement_accounting.fallback_events.end());
    require(result.fallback_events==legacy,name+" legacy zone prefix plus explicit placement-only events");
    const auto total=pcb_placement_accounting(result);measured(total.quantization_engagements,observed,name+" full build aggregate");
    NativeQuantizations q;NativeFallbacks fallbacks;register_native_quantizations(q);register_native_fallbacks(fallbacks);NativeAccountingInbox inbox(q,fallbacks);
    require(inbox.merge_once("actual-build",total)&&!inbox.merge_once("actual-build",total),name+" final aggregate imports once with no replay math");
    if(name=="devkit_mini"){
        f.input.two_side=false;calls={};const auto single=build_pcb_model(f.input);const auto separate=calls;
        require(single.zone_accounting_ownership==PcbZoneAccountingOwnership::SeparateFromFloorplan,"top-preferred build exposes separate actual zone solve");
        const auto all=pcb_placement_accounting(single);measured(all.quantization_engagements,separate,"top-preferred two-zone aggregate");
    }
}
} // namespace
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    if(fn==reinterpret_cast<void*>(&schgen::fixed_part_grid))++calls.fixed;
    else if(fn==reinterpret_cast<void*>(&schgen::evict_corridor_grid))++calls.corridor;
    else if(fn==reinterpret_cast<void*>(&schgen::quant_credit))++calls.credit;
    else if(fn==reinterpret_cast<void*>(&schgen::legalize_pose_quantum))++calls.legal;
    else if(fn==reinterpret_cast<void*>(&schgen::native_refit_pose_precision))++calls.refit;
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
int main(int argc,char** argv){try{
    require(argc==2,"usage: producer_accounting_contracts <repo-root>");
    calls={};legalize_pose_quantum(0);require(calls.legal==1,"independent observer missing: compile quantize.cpp with -finstrument-functions -fno-inline");
    overflow();legalizer();refit();ownership();live(argv[1],"devkit_mini");live(argv[1],"carrier");
    std::cout<<"Producer accounting: "<<checks<<" independent call-entry contracts passed\n";return 0;
}catch(const std::exception& e){std::cerr<<"Producer accounting FAILED: "<<e.what()<<'\n';return 1;}}
