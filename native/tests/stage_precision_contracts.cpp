// Independent compiled-entry observer: instrument stage_precision.cpp ONLY.
// Baseline builds link the pre-extraction stage sources and capture all old
// geometry/counters. The same legacy fixtures execute through a narrow adapter.
#include "schgen/pcb_stage_templates.hpp"
namespace schgen { PcbStageResult stage_precision_fixture_build(const PcbStageInput&); }
#define build_pcb_stage_zone stage_precision_fixture_build
#include "stage_precision_reference.hpp"
#undef build_pcb_stage_zone
#include "stage_precision_fixture.hpp"
#include "legalize_precision_fixture.hpp"
#include "pcb_placement_fixture.hpp"
#include "pcb_stage_internal.hpp"
#include "schgen/native_audit_state.hpp"
#ifndef STAGE_PRECISION_BASELINE
#include "schgen/stage_precision.hpp"
#include "buried_policy_fixture.hpp"
#endif
#include <atomic>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <thread>

namespace stage_test {
using namespace schgen;
using namespace stage_precision_fixture;
std::size_t checks=0,serial=0;
std::ostringstream legacy,additive;
JsonNode expected_additive;
bool capture=false,first=true;
std::set<std::string> exercised;
std::array<std::atomic<std::size_t>,17> entries{};
std::atomic<bool> observing{false};
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t u;std::memcpy(&u,&x,sizeof u);return u;}
void begin(){for(auto& n:entries)n=0;observing=true;}
QuantizationCounts end(){observing=false;QuantizationCounts out;for(std::size_t i=0;i<names.size();++i)if(entries[i])out[names[i]]=entries[i].load();return out;}
void node(std::ostream& out,const JsonNode& n){
    out<<static_cast<int>(n.kind)<<' ';
    switch(n.kind){
    case JsonKind::Null:break;
    case JsonKind::Bool:out<<n.bool_value;break;
    case JsonKind::Number:out<<bits(n.number_value);break;
    case JsonKind::String:out<<std::quoted(n.string_value);break;
    case JsonKind::Array:out<<n.array_value.size()<<' ';for(const auto& v:n.array_value)node(out,v);break;
    case JsonKind::Object:out<<n.object_value.size()<<' ';for(const auto& [k,v]:n.object_value){out<<std::quoted(k)<<' ';node(out,v);}break;
    }out<<'\n';
}
void counts(const char* label,const QuantizationCounts& q){
    legacy<<label<<'\n';for(const auto& [n,c]:legalize_precision_fixture::select(select(q,false),false))legacy<<std::quoted(n)<<' '<<c<<'\n';
}
void account(const std::string& label,const QuantizationCounts& owned,const QuantizationCounts& measured){
#ifdef STAGE_PRECISION_BASELINE
    (void)label;(void)owned;(void)measured;
#else
    require(select(owned)==measured,label+" invocation counts equal independent function entries");
    for(const auto& [name,n]:measured)if(n)exercised.insert(name);
    std::cerr<<label<<": "<<measured.size()<<" named operation receipts match compiled entries\n";
    if(capture){
        if(!first)additive<<",\n";first=false;additive<<std::quoted(label)<<":{";
        bool next=false;for(const auto& [n,c]:measured){if(next)additive<<',';next=true;additive<<std::quoted(n)<<':'<<c;}additive<<'}';
    }else{
        const auto& row=placement_fixture::field(expected_additive,label);
        QuantizationCounts expected;for(const auto& [n,c]:row.object_value)expected[n]=static_cast<std::size_t>(c.number_value);
        require(measured==expected,label+" immutable independent additive fixture");
    }
#endif
}
void poses(const PcbStageResult& r){
    for(const auto* offsets:{&r.top,&r.bottom}){
        legacy<<offsets->size()<<'\n';for(const auto& [n,p]:*offsets)legacy<<std::quoted(n)<<' '<<bits(p.first)<<' '<<bits(p.second)<<'\n';
    }
    legacy<<bits(r.w)<<' '<<bits(r.h)<<'\n';
    for(const auto& [n,v]:r.rotations)legacy<<std::quoted(n)<<' '<<bits(v)<<'\n';
    for(const auto& s:r.fallback_events)legacy<<std::quoted(s)<<'\n';
    counts("stage counts",r.quantization_engagements);
}
void parts(const pcb_stage::Parts& ps){for(const auto& p:ps)legacy<<std::quoted(p.ref)<<' '<<bits(p.x)<<' '<<bits(p.y)<<' '<<bits(p.rot)<<'\n';}
PcbStageInput small(){
    PcbStageInput in;in.sheet="synthetic";
    auto fp=pcb_check_footprint("stage-precision.kicad_mod","(footprint probe (layer F.Cu) (pad 1 smd rect (at 0.00015 -0.00025) (size 1 1) (layers F.Cu F.Paste F.Mask)))");
    in.refs={"U","A","B"};for(const auto& n:in.refs){in.board_refs[n]=n;in.footprints[n]=fp;in.bbox_of[n]={-1,-1,1,1};}
    in.contract=parse_json_text("{\"roles\":{\"A\":\"out\",\"B\":\"out\"},\"external\":{\"output_roles\":[\"out\"]}}");
    return in;
}
void trials(){
    auto in=small();
    for(const auto& n:in.refs)in.bbox_of[n]={-100,-100,100,100};
    pcb_stage::Engine ldo(in);begin();const auto ps=ldo.ldo("U","A","1","B","1");const auto measured=end();
    legacy<<"exhausted LDO trials\n";parts(ps);counts("ldo prior",ldo.quantization);account("ldo/exhausted",ldo.quantization,measured);
#ifndef STAGE_PRECISION_BASELINE
    require(measured==QuantizationCounts{{"stage_ldo_pose_precision4dp",48}},"all twelve rejected LDO scales count two coordinates for two capacitors");
#endif
    in=small();pcb_stage::Engine search(in);const pcb_stage::Parts anchored{search.part("U")};
    for(int pass=0;pass<2;++pass){
        auto before=search.quantization;
        begin();auto candidates=search.candidates("A",{{"U",{"1"},2}}, {},anchored,0);auto calls=end();
        QuantizationCounts delta;for(const auto& [n,c]:search.quantization)if(c>before[n])delta[n]=c-before[n];
        account("candidate/cache-pass-"+std::to_string(pass),delta,calls);
        legacy<<"cached candidates "<<pass<<'\n';parts(candidates);counts("candidate prior",delta);
#ifndef STAGE_PRECISION_BASELINE
        require(calls==QuantizationCounts{{"stage_candidate_radius_trunc",1}},"cache reuse executes and counts exactly the real radius conversion");
#endif
    }
    auto prior=search.quantization;begin();(void)search.pads(in.footprints.at("U"));(void)search.pads(in.footprints.at("U"));const auto cache_calls=end();
    require(cache_calls.empty()&&search.quantization==prior,"pad cache reads never replay stage accounting");
}
void refits(){
    auto in=small();in.refs={"A","B"};
    const FloorplanOffsets xy{{"A",{10.12345,10.00005}},{"B",{20.12345,10.00005}}};
    const std::map<std::string,std::vector<std::pair<std::string,std::string>>> nets{{"n",{{"A","1"}}}};
    for(double foreign_x:{0.,30.}){
        begin();const auto r=refit_pcb_stage_facing_accounted(in,xy,{}, {100,10},nets,{{"n",{{foreign_x,10,"other"}}}});const auto calls=end();
        const auto label=std::string("refit/")+(foreign_x==0?"reject":"accept");
        account(label,r.quantization_engagements,calls);
        legacy<<label<<' '<<r.poses.has_value()<<'\n';
        if(r.poses)for(const auto& [n,p]:*r.poses)legacy<<std::quoted(n)<<' '<<bits(std::get<0>(p))<<' '<<bits(std::get<1>(p))<<' '<<bits(std::get<2>(p))<<'\n';
        counts("refit prior",r.quantization_engagements);
        require(r.poses.has_value()==(foreign_x==30),"real airwire gate accepts/rejects the intended half-turn");
#ifndef STAGE_PRECISION_BASELINE
        require(calls==QuantizationCounts{{"stage_refit_pad_precision3dp",4}},"both airwire candidates count each translated pad coordinate");
#endif
        begin();const auto unaccounted=refit_pcb_stage_facing(in,xy,{}, {100,10},nets,{{"n",{{foreign_x,10,"other"}}}});const auto diagnostic=end();
        require(unaccounted==r.poses&&diagnostic==calls,"diagnostic API recomputes same math without mutating prior receipt");
    }
}
void boards(const std::filesystem::path& root){
    for(int variant=0;variant<4;++variant){
        const std::string project=variant==1?"carrier":"devkit_mini";
        auto f=placement_fixture::load(root,project);f.input.two_side=variant!=2;
        if(variant==3){if(!f.input.floorplan.spec)f.input.floorplan.spec=FloorplanSpec{};f.input.floorplan.spec->outline=std::make_pair(100.,100.);}
        const auto label=project+(variant==2?"_single":variant==3?"_fixed":"");
        std::cerr<<"starting board "<<label<<'\n';
        begin();const auto result=build_pcb_model(f.input);const auto calls=end();
        const auto total=pcb_placement_accounting(result);account("board/"+label,total.quantization_engagements,calls);
        auto plan=result.floorplan.plan;auto prior_total=total.quantization_engagements;
#ifndef STAGE_PRECISION_BASELINE
        // Validate all seven exact additions before projecting immutable old bytes.
        plan=buried_policy_fixture::prior_accounted_plan(std::move(plan));
        prior_total=buried_policy_fixture::prior_display_counts(std::move(prior_total));
#endif
        plan.accounting.quantization_engagements=legalize_precision_fixture::select(select(plan.accounting.quantization_engagements,false),false);
        legacy<<"BOARD "<<label<<'\n';node(legacy,pcb_model_json(result.model));node(legacy,floorplan_plan_json(plan));
        legacy<<render_floorplan_ledger(plan);
        counts("floorplan",plan.accounting.quantization_engagements);
        counts("zone",result.zone_accounting.quantization_engagements);
        counts("placement",result.placement_accounting.quantization_engagements);counts("aggregate",prior_total);
        begin();const auto again=pcb_placement_accounting(result);const auto a=render_floorplan_ledger(result.floorplan.plan);const auto b=render_floorplan_ledger(result.floorplan.plan);const auto replay=end();
        require(replay.empty()&&again.quantization_engagements==total.quantization_engagements&&a==b,"aggregate and cached render manufacture no work");
#ifndef STAGE_PRECISION_BASELINE
        auto expected=select(result.floorplan.plan.accounting.quantization_engagements);
        if(result.zone_accounting_ownership==PcbZoneAccountingOwnership::SeparateFromFloorplan)
            checked_quantization_merge(expected,select(result.zone_accounting.quantization_engagements));
        checked_quantization_merge(expected,select(result.placement_accounting.quantization_engagements));
        require(expected==calls,"actual zone ancestry determines exactly-once ownership");
#endif
    }
}
} // namespace stage_test

namespace schgen {
PcbStageResult stage_precision_fixture_build(const PcbStageInput& in){
    using namespace stage_test;
    const auto label="stage/"+std::to_string(serial++)+"/"+in.sheet;
    legacy<<label<<' '<<std::quoted(in.facing)<<' '<<std::quoted(in.outer_dir)<<' '<<in.pilot<<'\n';
    begin();
    try{
        auto result=build_pcb_stage_zone(in);const auto calls=end();
        account(label,result.quantization_engagements,calls);poses(result);
        // Only the explicitly named new family is removed before feeding the
        // original independent stage/mutation assertions. All old counts stay.
        result.quantization_engagements=stage_precision_fixture::select(result.quantization_engagements,false);
        return result;
    }catch(const PcbZoneInfeasible& e){(void)end();legacy<<"ERROR "<<std::quoted(e.what())<<'\n';throw;}
}
}

// Scalar and registry contracts are supplied below; only the candidate links
// the independently entry-instrumented new primitive TU.
#ifndef STAGE_PRECISION_BASELINE
#include "stage_precision_scalar_contracts.hpp"
#endif
extern "C" void __cyg_profile_func_enter(void* fn,void*){
#ifndef STAGE_PRECISION_BASELINE
    if(!stage_test::observing.load(std::memory_order_relaxed))return;
    stage_test::observe(fn);
#else
    (void)fn;
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    using namespace stage_test;
    if(argc<2||argc>3)throw std::runtime_error("repo [--capture]");
    const std::filesystem::path root=argv[1];capture=argc==3;
    if(capture&&std::string(argv[2])!="--capture")throw std::runtime_error("unknown option");
#ifndef STAGE_PRECISION_BASELINE
    if(!capture)expected_additive=parse_json_file((root/"native/tests/data/stage_precision/additive_counts.json").string());
    scalar_contracts();ownership_contracts();
#endif
    auto* stdout_buffer=std::cout.rdbuf(std::cerr.rdbuf());
    for(const auto& name:{"carrier","devkit_mini"})stage_reference::baseline(root,name);
    std::cout.rdbuf(stdout_buffer);
    trials();refits();boards(root);
#ifdef STAGE_PRECISION_BASELINE
    std::cout<<legacy.str();
#else
    require(legacy.str()==placement_fixture::read(root/"native/tests/data/stage_precision/legacy_output.txt"),"all independent pre-change native geometry bits, outputs, errors and prior counters byteexact");
    for(const auto& name:names)require(exercised.count(name),"real producer exercised "+name);
    if(capture)std::cout<<"{\n"<<additive.str()<<"\n}\n";
#endif
    std::cerr<<checks<<" stage precision assertions; "<<stage_reference::checks<<" frozen geometry assertions passed\n";return 0;
}catch(const std::exception& e){std::cerr<<"Stage precision FAILED: "<<e.what()<<'\n';return 1;}}
