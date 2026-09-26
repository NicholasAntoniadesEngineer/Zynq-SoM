#include "schgen/board_policy.hpp"
#include "schgen/board_decision_policy.hpp"
#include "schgen/pack.hpp"
#include "schgen/pcb_stage_templates.hpp"
#include "floorplan_internal.hpp"
#include "buried_policy_fixture.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <set>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool ok,const char* why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F> void rejects(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}
    require(rejected,"modified additive evidence was silently discarded");}
std::uint64_t bits(double value){std::uint64_t b;std::memcpy(&b,&value,sizeof b);return b;}
struct Expected {const char* name;const char* symbol;double value;};
// Independent literal expectations, transcribed from the pre-migration consumers.
const Expected expected[]={
    {"block_clearance","floorplan::clear",.3},
    {"place_clear_baseline","placement::clear",.5},
    {"small_part_routing_factor","floorplan::small_part_routing_factor",3.5},
    {"point_segment_tolerance","pack::point_segment_tolerance_mm",1e-6},
    {"visual_axis_tolerance","pack::visual_axis_tolerance_mm",1e-6},
    {"collinear_overlap_tolerance","pack::collinear_overlap_tolerance_mm",1e-6},
    {"segment_cross_tolerance","pack::segment_cross_tolerance_mm2",1e-9},
    {"label_courtyard_gap","pack::label_courtyard_gap_mm",.9},
    {"label_orbit_tau","pack::label_orbit_tau",6.283185307179586}};
const NativeLedgerDeclaration& declaration(const NativeBoardPolicy& p,const std::string& name){
    for(const auto& d:p.ledger_declarations)if(d.name==name)return d;
    throw std::runtime_error("missing actual policy provider: "+name);
}
void behavior(){
    require(bits(FloorplanLegalizeInput{}.clear)==bits(.3),"legalize default changed");
    require(bits(PcbStageInput{}.place_clear)==bits(.5),"stage default changed");
    require(bits(FloorplanPlan{}.factor)==bits(3.5),"reported routing factor changed");
    // Probe both sides of each strict/inclusive comparison with independent
    // literals. Caller units, axes and endpoint exclusions remain unchanged.
    for(double e:{-2e-6,-1e-6,-.5e-6,0.0,.5e-6,1e-6,2e-6}){
        require(point_on_seg(1,e,0,0,2,0,false)==(std::abs(e)<=1e-6),"point-to-segment tolerance changed");
        require(point_on_seg(e,0,0,0,2,0,true)==(e>1e-6),"strict endpoint tolerance changed");
        require(visual_hv_cross(0,0,2,0,e,-1,e,1)==(e>1e-6),"visual interior threshold changed");
        require(collinear_overlap(0,0,2,0,0,e,2,e)==(std::abs(e)<1e-6),"collinear axis threshold changed");
    }
    for(double e:{.25e-9,.5e-9,1e-9,2e-9})
        require(segments_cross(0,0,1,0,.5,-e,.5,e)==(e>1e-9),"signed cross-product tolerance changed");
    const auto walls=wall_sep_edges(true,{"a","b"},{2,3},10,.3,{{true,"a","b",.5}},{});
    require(walls.size()==5,"wall/separation population changed");
    for(std::size_t i=0;i<4;++i)require(walls[i].sep_index==-1,"explicit wall sentinel lost");
    require(walls.back().sep_index==0,"explicit separation index lost");
}
void policy(const std::filesystem::path& root,bool compiler){
    FloorplanInput in;in.som.w=30;in.som.h=40;ProjectPaths paths;paths.repository_root=root;
    const auto p=make_native_board_policy(paths,in);
    floorplan_detail::Engine producer(in);producer.ledger_open();
    require(buried_policy_fixture::prior_policy(floorplan_ledger_policy()).size()==83,"prior policy population lost");
    require(buried_policy_fixture::prior_plan(producer.plan).accounting.decisions.size()+7==producer.plan.accounting.decisions.size(),"exact additive population lost");
    const auto original_counts=producer.plan.accounting.quantization_engagements;
    auto prior_counts=original_counts;prior_counts.at("floorplan_ledger_display_precision4dp")-=7;
    require(buried_policy_fixture::prior_accounted_plan(producer.plan).accounting.quantization_engagements==prior_counts,
        "only seven actual numeric assumption displays may be projected");
    require(producer.plan.accounting.quantization_engagements==original_counts,"projection mutated producer receipt");
    auto tagged=original_counts;tagged["independent_other_counter"]=123;
    auto tagged_expected=prior_counts;tagged_expected["independent_other_counter"]=123;
    require(buried_policy_fixture::prior_display_counts(tagged)==tagged_expected,"projection changed another counter");
    rejects([&]{buried_policy_fixture::prior_display_counts({});});
    for(std::size_t count:{0,6,7})
        rejects([&]{buried_policy_fixture::prior_display_counts({{"floorplan_ledger_display_precision4dp",count}});});
    for(const auto& e:buried_policy_fixture::additions){
        for(int mutation=0;mutation<4;++mutation){
            auto changed=producer.plan;auto& rows=changed.accounting.decisions;
            auto found=std::find_if(rows.begin(),rows.end(),[&](const auto& r){return r.name==e.name;});
            if(mutation==0)found->value.number_value=std::nextafter(found->value.number_value,INFINITY);
            if(mutation==1)found->text+="changed";
            if(mutation==2)rows.erase(found);
            if(mutation==3){const auto duplicate=*found;rows.push_back(duplicate);}
            rejects([&]{buried_policy_fixture::prior_plan(changed);});
        }
        auto changed=floorplan_ledger_policy();
        for(auto& row:changed)if(row.name==e.name)row.legacy_cover+="wrong";
        rejects([&]{buried_policy_fixture::prior_policy(changed);});
    }
    require(p.ledger_declarations.size()==90,"complete authored declaration population changed");
    for(const auto& row:expected){
        const auto& d=declaration(p,row.name);
        require(bits(d.resolve().number_value)==bits(row.value),"independent policy bits changed");
        require(d.covers==std::vector<std::string>{std::string("native/include/schgen/board_decision_policy.hpp::schgen::board_decision_policy::")+row.symbol},"provider covers wrong storage");
        const auto found=std::find_if(producer.plan.accounting.decisions.begin(),producer.plan.accounting.decisions.end(),[&](const auto& r){return r.name==row.name;});
        require(found!=producer.plan.accounting.decisions.end()&&bits(found->value.number_value)==bits(row.value),"producer did not record actual assumption value");
    }
    if(!compiler)return;
    const std::vector<CppAuditSource> sources{{"native/include/schgen/board_decision_policy.hpp"},
        {"native/include/schgen/floorplan.hpp"},{"native/include/schgen/legalize.hpp"},
        {"native/include/schgen/pcb_stage_templates.hpp"},{"native/src/floorplan_internal.hpp"},
        {"native/src/pcb_stage_internal.hpp"},{"native/src/pack.cpp"}};
    CppAuditOptions options;options.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
    options.timeout=std::chrono::milliseconds{120000};
    const auto census=scan_cpp_audit_sources(root,sources,options);
    NativeLedger ledger;for(const auto& d:p.ledger_declarations)ledger.declare(d);
    ledger.open_step("floorplan.sizing");ledger.close_step("floorplan.sizing");
    NativeQuantizations q;register_native_quantizations(q);
    const auto result=check_native_audits(census,ledger,q);
    require(result.buried.empty(),"actual changed-source census still has buried policy");
    std::set<std::string> constants;for(const auto& c:census.constants)constants.insert(c.symbol);
    for(const auto& row:expected){
        const auto& d=declaration(p,row.name);require(constants.count(d.covers.front())==1,"covered producer storage absent from actual compiler census");
        NativeLedger missing;
        for(const auto& copy:p.ledger_declarations)if(copy.name!=row.name)missing.declare(copy);
        missing.open_step("floorplan.sizing");missing.close_step("floorplan.sizing");
        const auto negative=check_native_audits(census,missing,q);
        require(std::find(negative.undeclared.begin(),negative.undeclared.end(),d.covers.front())!=negative.undeclared.end(),"removing real policy cover did not fail");
    }
    NativeLedger unrecorded;for(const auto& d:p.ledger_declarations)unrecorded.declare(d);
    const auto absent=check_native_audits(census,unrecorded,q).absent;
    for(const auto& row:expected){
        require(std::find(absent.begin(),absent.end(),row.name)!=absent.end(),"policy declaration without live record passed");
        require(std::find(result.absent.begin(),result.absent.end(),row.name)==result.absent.end(),"live assumption record absent");
    }
    // This focused census is not a full-board PASS: unrelated raw transforms
    // and covers whose owner files are outside this scope remain visible.
    std::cout<<"focused census: buried="<<result.buried.size()<<", undeclared="<<result.undeclared.size()
        <<", raw="<<result.unregistered_quantization.size()<<", stale="<<result.stale.size()<<'\n';
}
}
int main(int argc,char** argv){try{
    if(argc<2||argc>3)throw std::runtime_error("usage: buried_policy_contracts PRIVATE_ROOT [--compiler]");
    behavior();policy(std::filesystem::canonical(argv[1]),argc==3&&std::string(argv[2])=="--compiler");
    std::cout<<checks<<" buried policy contracts PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
