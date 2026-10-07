#include "floorplan_internal.hpp"
#include "native_audit_quantize_internal.hpp"
#include <iostream>
#include <stdexcept>
#include <tuple>
using namespace schgen;
using floorplan_detail::Engine;
namespace {
thread_local bool observing=false;
thread_local std::size_t entries=0;
void require(bool p,const char* why){if(!p)throw std::runtime_error(why);}
bool equal(const JsonNode& a,const JsonNode& b){
    if(a.kind!=b.kind||a.bool_value!=b.bool_value||a.number_value!=b.number_value||a.string_value!=b.string_value||a.array_value.size()!=b.array_value.size()||a.object_value.size()!=b.object_value.size())return false;
    for(std::size_t i=0;i<a.array_value.size();++i)if(!equal(a.array_value[i],b.array_value[i]))return false;
    for(std::size_t i=0;i<a.object_value.size();++i)if(a.object_value[i].first!=b.object_value[i].first||!equal(a.object_value[i].second,b.object_value[i].second))return false;
    return true;
}
JsonNode layout(FloorplanPlan plan){plan.accounting={};return floorplan_plan_json(plan);}
auto offers(const Engine& e){
    std::map<std::string,std::tuple<std::string,std::string,int,std::optional<double>,std::optional<double>>> out;
    for(const auto& [name,s]:e.side_offers)out[name]={s.offered,s.chosen,s.shape,s.incumbent,s.challenger};
    return out;
}
struct Block {double w,h;int variants=1;double priority=0;};
struct Case {double w,h;std::vector<Block> blocks;};
FloorplanInput input(){FloorplanInput in;in.som.w=8;in.som.h=8;in.module_offset=FloorplanPoint{0,0};in.compact_search=true;return in;}
void setup(Engine& e,const Case& c){
    e.board_size(c.w,c.h);e.plan.punch_free=true;e.compact_order=0;
    e.plan.spilled={"entry-spill"};e.plan.composition={"entry-composition"};
    e.side_offers["entry"]={"top/bottom","top",7,9.,10.};
    for(std::size_t i=0;i<c.blocks.size();++i){
        const auto& s=c.blocks[i];FloorplanBlock b;b.name="b"+std::to_string(i);b.kind="interior";b.zone="E";b.x=-11;b.y=-13;b.w=s.w;b.h=s.h;b.shape_idx=0;
        e.plan.interior_blocks.push_back(b);e.zbox[b.name]={s.w,s.h};e.som_pull[b.name]=s.priority;
        for(int k=0;k<s.variants;++k)e.shape_sets[1][b.name].push_back({s.w,s.h,{}, {},k%2?"bottom":"top",{}});
    }
    e.plan.accounting.quantization_engagements.clear();
    e.plan.accounting.quantization_engagements["entry-sentinel"]=19;
    e.plan.accounting.fallback_events={"entry-fallback"};
}
struct Result {bool ok;FloorplanPlan plan;decltype(offers(std::declval<Engine>())) side;std::size_t calls;};
Result trial(const FloorplanInput& in,const Case& c,int order){
    Engine e(in);setup(e,c);e.compact_order=order;entries=0;observing=true;
    bool ok=false;try{ok=e.attempt_pack_impl(false);}catch(...){observing=false;throw;}observing=false;
    const auto calls=entries;require(e.plan.accounting.quantization_engagements.at("run_overflow_tol")==calls,"direct receipt disagrees with actual scalar entries");
    return {ok,e.plan,offers(e),calls};
}
enum class Mutation {None,DropCount,DuplicateCount,Layout,Offers};
void check(const char* name,const Case& c,int winner,Mutation mutation=Mutation::None){
    const auto in=input();Engine e(in);setup(e,c);const auto start=layout(e.plan);const auto start_offers=offers(e);
    QuantizationCounts expected{{"entry-sentinel",19}};std::vector<std::string> events{"entry-fallback"};std::size_t calls=0;std::optional<Result> accepted;
    const int attempts=winner<0?3:winner+1;
    for(int order=0;order<attempts;++order){auto r=trial(in,c,order);require(r.ok==(order==winner),"synthetic witness no longer exercises expected order outcome");
        auto delta=r.plan.accounting.quantization_engagements;delta.erase("entry-sentinel");checked_quantization_merge(expected,delta);calls+=r.calls;
        const auto& ev=r.plan.accounting.fallback_events;require(!ev.empty()&&ev.front()=="entry-fallback","isolated trial lost event seed");events.insert(events.end(),ev.begin()+1,ev.end());
        if(r.ok)accepted=std::move(r);}
    entries=0;observing=true;bool ok=false;try{ok=e.attempt_pack(false);}catch(...){observing=false;throw;}observing=false;
    if(mutation==Mutation::DropCount)--e.plan.accounting.quantization_engagements.at("run_overflow_tol");
    if(mutation==Mutation::DuplicateCount)++e.plan.accounting.quantization_engagements.at("run_overflow_tol");
    if(mutation==Mutation::Layout)e.plan.interior_blocks.front().x+=1;
    if(mutation==Mutation::Offers)e.side_offers["entry"].shape+=1;
    require(ok==(winner>=0),"wrapper result mismatch");require(entries==calls&&entries==static_cast<std::size_t>(attempts),"trial short-circuit or actual invocation count mismatch");
    require(e.plan.accounting.quantization_engagements==expected,"all failed/successful work must be counted exactly once");require(e.compact_order==0,"order state leaked");
    require(e.plan.accounting.fallback_events==events,"ordered attempt evidence must preserve seed and each trial once");
    require(equal(layout(e.plan),accepted?layout(accepted->plan):start),"accepted/terminal layout differs from independent trial/entry snapshot");
    require(offers(e)==(accepted?accepted->side:start_offers),"accepted/terminal side offers mismatch");
    std::cout<<name<<" PASS winner="<<winner<<" attempts="<<attempts<<" observed="<<entries<<'\n';
}
void exception_contract(bool constraint_first=false){
    auto in=input();
    if(constraint_first){
        auto experiment=std::make_shared<FloorplanExperiment>();
        experiment->compact_constraint_first=true;
        in.experiment=experiment;
    }
    FloorplanTerm term;term.kind="near_max";term.sheet="b0";term.subject="b0";term.target_raw="b1";term.bound=100.;term.enforced=true;
    in.compose.index.hard.push_back(term);
    const Case c{80,70,{{8,6,1,10},{7,5,2,0}}};
    auto seed=[&](Engine& e){setup(e,c);
        // Force b1's real bottom variant. Its missing per-shape metrics must
        // throw only AFTER both blocks have been placed and offers recorded.
        e.shape_sets[1].at("b1").front().w=200;
    };
    const std::string message="floorplan: b1 chose shape 1 but no per-shape zone metrics were registered — the legalizer would judge shape-0 geometry (silent breakage)";
    auto throwing=[&](Engine& e,bool wrapper){
        entries=0;observing=true;bool rejected=false;
        try{if(wrapper)(void)e.attempt_pack(false);else (void)e.attempt_pack_impl(false);}
        catch(const std::logic_error& error){observing=false;require(error.what()==message,"original missing-metrics exception changed");rejected=true;}
        catch(...){observing=false;throw;}
        observing=false;require(rejected,"missing chosen-shape metrics must throw");
        require(entries==1,"exception must stop after first actual trial, without retry");
        require(e.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries,"exception prefix differs from observed scalar entries");
    };
    Engine direct(in);seed(direct);const auto start=layout(direct.plan);const auto start_offers=offers(direct);
    throwing(direct,false);
    require(!equal(layout(direct.plan),start)&&offers(direct)!=start_offers,"exception witness must mutate both layout and side offers");
    require(direct.plan.interior_blocks.at(0).x!=-11&&direct.plan.interior_blocks.at(1).shape_idx==1,"exception witness must actually place both blocks");
    Engine wrapped(in);seed(wrapped);throwing(wrapped,true);
    require(wrapped.compact_order==0,"exception leaked retry-order state");
    require(wrapped.plan.accounting.quantization_engagements==direct.plan.accounting.quantization_engagements,"exception lost or duplicated actual failed-prefix counts");
    require(wrapped.plan.accounting.fallback_events==direct.plan.accounting.fallback_events,"exception lost ordered failed-prefix evidence");
    std::cout<<"exception prefix/identity/no-retry PASS; layout_restored="<<equal(layout(wrapped.plan),start)<<" offers_restored="<<(offers(wrapped)==start_offers)<<'\n';
    require(equal(layout(wrapped.plan),start),"exception must restore entry layout while preserving failed-prefix receipts");
    require(offers(wrapped)==start_offers,"exception must restore entry side offers");
    std::cout<<"exception rollback PASS\n";
}
void invariant_edge_failure(bool constraint_first,bool translate) {
    auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();
    experiment->compact_constraint_first=constraint_first;
    experiment->compact_edge_translation=translate;in.experiment=experiment;
    const auto seed=[](Engine& e) {
        setup(e,{40,40,{}});
        FloorplanBlock b;b.name="edge";b.kind="edge";
        e.plan.edge_blocks.push_back(b);e.zbox[b.name]={12,20};e.edge_of[b.name]="N";
    };
    Engine direct(in);seed(direct);bool invariant=false;
    require(!direct.attempt_pack_impl(false,&invariant)&&invariant,"edge/SoM conflict is independent of interior order");
    Engine wrapped(in);seed(wrapped);const auto start=layout(wrapped.plan);const auto side=offers(wrapped);
    std::size_t searches=0;
    experiment->edge_translation_completed=[&](std::size_t,char,double){++searches;};
    entries=0;observing=true;const bool ok=wrapped.attempt_pack(false);observing=false;
    require(!ok&&entries==(translate?0u:1u),"invariant edge failure executes once, not once per order");
    require(searches==(translate?1u:0u),"bounded edge search is not repeated for interior alternatives");
    require(wrapped.plan.accounting.quantization_engagements==direct.plan.accounting.quantization_engagements&&
            wrapped.plan.accounting.fallback_events==direct.plan.accounting.fallback_events,"only executed single-trial work retained");
    require(equal(layout(wrapped.plan),start)&&offers(wrapped)==side&&wrapped.compact_order==0,"early stop restores caller candidate state");
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){if(observing&&fn==reinterpret_cast<void*>(&native_run_overflow_tol))++entries;}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(){try{
    check("canonical",{80,70,{{8,6,2,1},{7,5,2,0}}},0);
    check("area-wins",{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}},1);
    check("constrained-wins",{70,60,{{9,16,1,0},{18,27,2,1},{25,14,2,0},{11,29,1,1},{27,30,1,1},{31,7,1,0},{30,18,3,1}}},2);
    const Case failed{80,70,{{8,6,2,100},{90,80,1,0}}};
    const auto partial=trial(input(),failed,0);
    require(!partial.ok&&partial.plan.interior_blocks.front().x!=-11,"all-fail witness must perform actual partial placement");
    check("all-fail-partial",failed,-1);
    for(auto mutation:{Mutation::DropCount,Mutation::DuplicateCount,Mutation::Layout,Mutation::Offers}){
        bool rejected=false;try{check("mutation",failed,-1,mutation);}catch(const std::runtime_error&){rejected=true;}
        require(rejected,"mutation escaped independent assertions");
    }
    std::cout<<"four receipt/layout/offer mutations rejected\n";
    exception_contract();
    for(bool first:{false,true})for(bool translate:{false,true})invariant_edge_failure(first,translate);
    std::cout<<"compact retry contracts PASS\n";return 0;
}catch(const std::exception& e){observing=false;std::cerr<<e.what()<<'\n';return 1;}}
