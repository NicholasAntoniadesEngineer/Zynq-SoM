#include "floorplan_internal.hpp"
#include "native_audit_quantize_internal.hpp"
#include "pack_refine_internal.hpp"
#include <algorithm>
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
struct Case {double w,h;std::vector<Block> blocks;bool terminal_trap=false;};
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
    if(c.terminal_trap){
        // Intentionally inconsistent nominal/candidate dimensions force a
        // late seating rejection after an earlier local recovery. All four
        // physical candidates are too large; none may be accepted.
        FloorplanBlock b;b.name="terminal";b.kind="interior";b.zone="E";b.x=-11;b.y=-13;b.w=1;b.h=1;
        e.plan.interior_blocks.push_back(b);e.zbox[b.name]={1,1};e.som_pull[b.name]=0;
        for(int k=0;k<4;++k)e.shape_sets[1][b.name].push_back({c.w*2,c.h*2,{}, {},"top",{}});
    }
    e.plan.accounting.quantization_engagements.clear();
    e.plan.accounting.quantization_engagements["entry-sentinel"]=19;
    e.plan.accounting.fallback_events={"entry-fallback"};
}
struct Result {bool ok;FloorplanPlan plan;decltype(offers(std::declval<Engine>())) side;std::size_t calls;};
Result trial(const FloorplanInput& in,const Case& c,int order,std::size_t skip=0,bool* selected=nullptr){
    Engine e(in);setup(e,c);e.compact_order=order;entries=0;observing=true;
    bool ok=false;try{ok=e.attempt_pack_impl(false,nullptr,{},nullptr,skip,selected);}catch(...){observing=false;throw;}observing=false;
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
void invariant_edge_failure(bool constraint_first,bool translate,bool recovery=false,bool shapes=false) {
    auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();
    experiment->compact_constraint_first=constraint_first;
    experiment->compact_edge_translation=translate;in.experiment=experiment;
    if(recovery){experiment->interior_order=0;experiment->failed_first_retry=true;}
    if(shapes){experiment->interior_order=0;experiment->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,0,false,true};}
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
void reseat_trace_contract(){
    const Case c{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    auto plain=input();Engine baseline(plain);setup(baseline,c);const bool expected=baseline.attempt_pack(false);
    auto traced=input();auto observer=std::make_shared<FloorplanExperiment>();
    std::vector<FloorplanReseatObservation> rows;
    observer->reseat_completed=[&](const auto& r){rows.push_back(r);};traced.experiment=observer;
    Engine e(traced);setup(e,c);
    require(e.attempt_pack(false)==expected,"observation changed outcome");
    require(equal(floorplan_plan_json(e.plan),floorplan_plan_json(baseline.plan))&&offers(e)==offers(baseline),
        "observation changed layout, offers or real accounting");
    require(!rows.empty(),"witness did not execute reseat trials");
    std::size_t success=0,failed=0;
    for(const auto& r:rows){
        require(r.w==70&&r.h==50&&r.punch_free&&!r.incoming.empty()&&!r.displaced.empty()&&r.incoming!=r.displaced,"reseat identity");
        require(!r.displaced_reseated||r.incoming_seated,"impossible successful reseat");
        if(r.displaced_reseated)++success;else ++failed;
    }
    require(failed>0,"failed victim trials must be observed");
    require(success==static_cast<std::size_t>(std::count(e.plan.accounting.fallback_events.begin(),e.plan.accounting.fallback_events.end(),"interior_reseat_retry")),"success trace disagrees with retained actual events");
    observer->reseat_completed=[](const auto&){throw std::runtime_error("reseat observer stop");};
    Engine interrupted(traced);setup(interrupted,c);const auto start=layout(interrupted.plan);
    bool threw=false;try{interrupted.attempt_pack(false);}catch(const std::runtime_error& x){threw=std::string(x.what())=="reseat observer stop";}
    require(threw&&equal(layout(interrupted.plan),start)&&interrupted.compact_order==0,"observer failure must propagate and restore candidate state");
    std::cout<<"reseat trace PASS success="<<success<<" failed="<<failed<<'\n';
}
void reseat_offer_rollback_contract(){
    std::size_t rejected_after_seating=0;
    for(const Case& c:std::vector<Case>{
        {70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}},
        {70,60,{{9,16,1,0},{18,27,2,1},{25,14,2,0},{11,29,1,1},{27,30,1,1},{31,7,1,0},{30,18,3,1}}}}) {
        for(int order=0;order<3;++order) for(bool seed_offer:{false,true}) {
            auto in=input();auto observer=std::make_shared<FloorplanExperiment>();in.experiment=observer;
            Engine e(in);setup(e,c);e.compact_order=order;
            if(seed_offer)for(const auto& b:e.plan.interior_blocks)e.side_offers[b.name]={"prior","prior",-7,1.,2.};
            const auto prior=offers(e);
            observer->reseat_completed=[&](const auto& row){
                if(!row.displaced_reseated) {
                    if(seed_offer)require(offers(e).at(row.incoming)==prior.at(row.incoming),"failed reseat leaked rejected side offer");
                    else require(!e.side_offers.count(row.incoming),"failed reseat invented side offer");
                    if(row.incoming_seated)++rejected_after_seating;
                }
            };
            (void)e.attempt_pack_impl(false);
        }
    }
    require(rejected_after_seating>0,"rollback witness must seat incoming and fail displaced block");
    std::cout<<"reseat offer rollback PASS rejected_after_seating="<<rejected_after_seating<<'\n';
}
void failed_first_contract(){
    std::size_t retries=0,rescued=0,preserved=0;
    const std::vector<Case> cases{
        {80,70,{{8,6,2,1},{7,5,2,0}}},
        {70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}},
        {70,60,{{9,16,1,0},{18,27,2,1},{25,14,2,0},{11,29,1,1},{27,30,1,1},{31,7,1,0},{30,18,3,1}}},
        {80,70,{{8,6,2,100},{90,80,1,0}}}};
    for(const auto& c:cases)for(int order=0;order<4;++order){
        auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();
        experiment->interior_order=order;experiment->failed_first_retry=true;in.experiment=experiment;
        Engine first(in);setup(first,c);first.compact_order=order;
        const auto start=layout(first.plan);const auto start_offers=offers(first);
        std::string failed;entries=0;observing=true;
        bool expected_ok=first.attempt_pack_impl(false,nullptr,{},&failed);observing=false;
        auto expected_counts=first.plan.accounting.quantization_engagements;
        auto expected_events=first.plan.accounting.fallback_events;
        auto expected_layout=expected_ok?layout(first.plan):start;
        auto expected_offers=expected_ok?offers(first):start_offers;
        auto calls=entries;
        if(expected_ok)++preserved;
        if(!expected_ok&&!failed.empty()){
            ++retries;Engine second(in);setup(second,c);second.compact_order=order;
            entries=0;observing=true;expected_ok=second.attempt_pack_impl(false,nullptr,failed);observing=false;
            calls+=entries;auto delta=second.plan.accounting.quantization_engagements;delta.erase("entry-sentinel");
            checked_quantization_merge(expected_counts,delta);
            expected_events.push_back("interior_failed_first_retry");
            expected_events.insert(expected_events.end(),second.plan.accounting.fallback_events.begin()+1,second.plan.accounting.fallback_events.end());
            if(expected_ok){++rescued;second.plan.composition.push_back("failure-directed order: "+failed+" first");expected_layout=layout(second.plan);expected_offers=offers(second);}
        }
        Engine wrapped(in);setup(wrapped,c);wrapped.compact_order=2;
        entries=0;observing=true;const bool actual=wrapped.attempt_pack(false);observing=false;
        require(actual==expected_ok&&entries==calls&&entries<=2,"failed-first retry must execute at most the independently observed two trials");
        require(wrapped.plan.accounting.quantization_engagements==expected_counts&&wrapped.plan.accounting.fallback_events==expected_events,
                "failed-first retry loses, duplicates or invents executed work");
        require(equal(layout(wrapped.plan),expected_layout)&&offers(wrapped)==expected_offers&&wrapped.compact_order==2,
                "failed-first retry incumbent or terminal rollback differs from independent trials");
    }
    require(retries>0&&rescued>0&&preserved>0,"failed-first fixtures must exercise failed trials, real rescues and preserved incumbents");
    auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();
    experiment->interior_order=0;experiment->failed_first_retry=true;in.experiment=experiment;
    int rejected=0;experiment->stage_rejected=[&](const auto&){if(++rejected==2)throw std::runtime_error("recovery stop");};
    Engine interrupted(in);setup(interrupted,cases.back());interrupted.compact_order=2;
    const auto start=layout(interrupted.plan);const auto side=offers(interrupted);
    bool threw=false;try{interrupted.attempt_pack(false);}catch(const std::runtime_error& error){threw=std::string(error.what())=="recovery stop";}
    require(threw&&equal(layout(interrupted.plan),start)&&offers(interrupted)==side&&interrupted.compact_order==2,
            "recovery observer exception must propagate and restore candidate state");
    require(std::count(interrupted.plan.accounting.fallback_events.begin(),interrupted.plan.accounting.fallback_events.end(),"interior_failed_first_retry")==1,
            "interrupted recovery must retain its executed fallback event");
    experiment->interior_order.reset();bool invalid=false;
    try{validate_floorplan_experiment(*experiment);}catch(const FloorplanError&){invalid=true;}
    require(invalid,"failed-first retry without explicit order accepted");
    std::cout<<"failed-first retry PASS retries="<<retries<<" rescued="<<rescued<<" preserved="<<preserved<<'\n';
}
void single_order_contract(){
    std::size_t interrupted_trials=0;
    const Case c{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    for(bool compact:{false,true})for(int order=0;order<4;++order){
        auto in=input();in.compact_search=compact;
        auto experiment=std::make_shared<FloorplanExperiment>();experiment->interior_order=order;in.experiment=experiment;
        const auto direct=trial(in,c,order);
        Engine e(in);setup(e,c);e.compact_order=2;
        entries=0;observing=true;const bool ok=e.attempt_pack(false);observing=false;
        require(ok==direct.ok&&equal(floorplan_plan_json(e.plan),floorplan_plan_json(direct.plan))&&offers(e)==direct.side,
            "single-order adapter differs from isolated trial");
        require(entries==direct.calls&&entries==1&&e.compact_order==2,"single-order repeated or leaked order state");
        experiment->reseat_completed=[](const auto&){throw std::runtime_error("single-order stop");};
        Engine interrupted(in);setup(interrupted,c);interrupted.compact_order=2;
        try{interrupted.attempt_pack(false);}catch(const std::runtime_error& error){
            require(std::string(error.what())=="single-order stop","single-order exception identity changed");
            ++interrupted_trials;
            require(interrupted.compact_order==2,"exception leaked forced order state");
        }
    }
    require(interrupted_trials>0,"single-order exception witness never executed");
    for(int invalid:{-1,4}){
        FloorplanExperiment experiment;experiment.interior_order=invalid;bool rejected=false;
        try{validate_floorplan_experiment(experiment);}catch(const FloorplanError&){rejected=true;}
        require(rejected,"invalid single order accepted");
    }
    FloorplanExperiment conflict;conflict.interior_order=0;conflict.compact_constraint_first=true;
    bool rejected=false;try{validate_floorplan_experiment(conflict);}catch(const FloorplanError&){rejected=true;}
    require(rejected,"ambiguous order portfolio accepted");
    std::cout<<"single-order diagnostic contracts PASS\n";
}
}
namespace {
void alternative_pose_retry_contract(){
    std::vector<Case> cases{
        {80,70,{{8,6,2,1},{7,5,2,0}}},
        {70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}},
        {70,60,{{9,16,1,0},{18,27,2,1},{25,14,2,0},{11,29,1,1},{27,30,1,1},{31,7,1,0},{30,18,3,1}}},
        {80,70,{{8,6,2,100},{90,80,1,0}}}};
    // Neighbouring finite fixtures cover successful continuations as well as
    // dead ends; this is not an unbounded randomized campaign.
    const auto crowded=cases[1];
    for(int w=65;w<=85;w+=5)for(int h=45;h<=65;h+=5){
        auto c=crowded;c.w=w;c.h=h;cases.push_back(std::move(c));
    }
    std::size_t searches=0,attempts=0,exhausted=0,capped=0,recovered=0;
    for(const auto& c:cases)for(int order=0;order<3;++order)for(std::size_t budget:{1u,4096u}) {
        const auto normal=trial(input(),c,order);
        auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();in.experiment=experiment;
        experiment->reseat_pose_limits=FloorplanPoseRetryLimits{8,budget};
        std::vector<FloorplanPoseRetryObservation> rows;
        experiment->pose_retry_completed=[&](const auto& row){rows.push_back(row);};
        const auto result=trial(in,c,order);
        if(normal.ok)require(result.ok&&rows.empty()&&equal(floorplan_plan_json(normal.plan),floorplan_plan_json(result.plan))&&normal.side==result.side,
                             "pose recovery replaced an ordinary incumbent or its receipts");
        if(!normal.ok&&result.ok){
            ++recovered;
            // Independent rectangle checks for these zero-halo synthetic
            // blocks, not the production occupancy predicate under test.
            const auto& blocks=result.plan.interior_blocks;
            for(std::size_t i=0;i<blocks.size();++i){const auto& a=blocks[i];
                require(a.x>=0&&a.y>=0&&a.x+a.w<=c.w&&a.y+a.h<=c.h,"recovered block outside board");
                for(std::size_t j=0;j<i;++j){const auto& b=blocks[j];
                    require(a.side!=b.side||a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y,
                            "recovered same-face rectangles overlap");
                }
            }
        }
        const auto count=[&](const char* key){return static_cast<std::size_t>(std::count(result.plan.accounting.fallback_events.begin(),result.plan.accounting.fallback_events.end(),key));};
        std::size_t tried=0,limited=0,full=0;
        for(const auto& row:rows){
            require(row.generated<=8&&row.frontier_nodes<=budget&&row.attempted<=row.generated,"pose retry exceeded query bounds");
            require(row.incoming!=row.displaced&&(!row.success||row.attempted>0),"pose retry identity/success evidence invalid");
            tried+=row.attempted;limited+=row.budget_exhausted;full+=row.result_capped;
        }
        require(count("interior_reseat_pose_search")==rows.size()&&count("interior_reseat_pose_trial")==tried&&
                count("interior_reseat_pose_budget")==limited&&count("interior_reseat_pose_cap")==full,"pose retry event receipt disagrees with observations");
        searches+=rows.size();attempts+=tried;exhausted+=limited;capped+=full;
        experiment->pose_retry_completed={};const auto repeat=trial(in,c,order);
        require(result.ok==repeat.ok&&equal(floorplan_plan_json(result.plan),floorplan_plan_json(repeat.plan))&&result.side==repeat.side,
                "pose retry not reproducible or callback changed behavior");
    }
    std::cout<<"pose coverage searches="<<searches<<" attempts="<<attempts<<" exhausted="<<exhausted<<" capped="<<capped<<" recovered="<<recovered<<'\n';
    require(searches>0&&attempts>0&&exhausted>0&&capped>0&&recovered>0,"pose recovery fixtures missed successful, attempted or limited searches");
    std::size_t replays=0,skips=0,replay_recovered=0,hints=0,empty_hints=0;
    std::optional<std::pair<Case,int>> interrupted_case;
    auto replay_cases=cases;for(auto c:cases){c.terminal_trap=true;replay_cases.push_back(std::move(c));}
    for(const auto& c:replay_cases)for(int order=0;order<3;++order)for(int hint:{0,1,3,98,99,-1,-2,-3,-4,-5}){
        auto replay_input=input();auto config=std::make_shared<FloorplanExperiment>();replay_input.experiment=config;
        const std::size_t limit=hint==98?99:3;
        const bool prefer=hint==3||hint==98;
        config->interior_order=order;config->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,limit,hint!=0};
        QuantizationCounts expected{{"entry-sentinel",19}};std::vector<std::string> events{"entry-fallback"};
        std::optional<Result> accepted;std::size_t calls=0,executed=0;
        std::vector<std::size_t> branches;for(std::size_t i=0;i<=limit;++i)branches.push_back(i);
        if(prefer)std::rotate(branches.begin()+1,branches.begin()+hint,branches.begin()+hint+1);
        std::optional<std::size_t> exhausted;
        for(const auto skip:branches){
            if(exhausted&&skip>=*exhausted)continue;
            if(skip){if(prefer&&executed==1)events.push_back("interior_reseat_pose_hint");events.push_back("interior_reseat_pose_resume");}
            bool selected=false;auto r=trial(replay_input,c,order,skip,&selected);++executed;calls+=r.calls;
            auto delta=r.plan.accounting.quantization_engagements;delta.erase("entry-sentinel");checked_quantization_merge(expected,delta);
            const auto& ev=r.plan.accounting.fallback_events;events.insert(events.end(),ev.begin()+1,ev.end());
            if(r.ok){if(skip)++replay_recovered;accepted=std::move(r);break;}
            if(!selected){exhausted=skip;if(hint==98&&skip==98)++empty_hints;}
        }
        Engine wrapped(replay_input);setup(wrapped,c);const auto entry=layout(wrapped.plan);const auto side=offers(wrapped);
        if(hint){
            Engine::ContinuationKey key{c.w+(hint==-1?1:0),c.h+(hint==-2?1:0),hint!=-3,hint==-4,order+(hint==-5?1:0)};
            wrapped.continuation_hint=std::make_pair(key,static_cast<std::size_t>(hint<0?3:hint));
        }
        entries=0;observing=true;bool ok=false;
        try{ok=wrapped.attempt_pack(false);}catch(...){observing=false;throw;}observing=false;
        require(ok==accepted.has_value()&&entries==calls,"continuation result or actual invocation count mismatch");
        require(wrapped.plan.accounting.quantization_engagements==expected&&wrapped.plan.accounting.fallback_events==events,
                "continuation lost/duplicated executed work or reordered events");
        require(equal(layout(wrapped.plan),accepted?layout(accepted->plan):entry)&&offers(wrapped)==(accepted?accepted->side:side),
                "continuation result differs from independently replayed branch or failed rollback");
        const auto resumed=std::count(events.begin(),events.end(),"interior_reseat_pose_resume");
        require(resumed==static_cast<std::ptrdiff_t>(executed-1)&&static_cast<std::size_t>(resumed)<=limit,"continuation exceeded restart budget");
        if(hint==98&&resumed)require(resumed>=2,"empty high hint incorrectly pruned lower branches");
        replays+=resumed;skips+=std::count(events.begin(),events.end(),"interior_reseat_pose_skip");
        hints+=std::count(events.begin(),events.end(),"interior_reseat_pose_hint");
        if(resumed&&!interrupted_case)interrupted_case=std::make_pair(c,order);
    }
    require(replays>0&&skips>0&&hints>0&&empty_hints>0,"continuation fixtures missed advisory or exhausted hint paths");
    {
        auto replay_input=input();auto config=std::make_shared<FloorplanExperiment>();replay_input.experiment=config;
        config->interior_order=interrupted_case->second;config->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,3};
        config->pose_retry_completed=[](const auto& row){if(row.skipped)throw std::runtime_error("replay observer stop");};
        Engine interrupted(replay_input);setup(interrupted,interrupted_case->first);
        const auto entry=layout(interrupted.plan);const auto side=offers(interrupted);
        bool threw=false;entries=0;observing=true;
        try{interrupted.attempt_pack(false);}catch(const std::runtime_error& error){threw=std::string(error.what())=="replay observer stop";}observing=false;
        require(threw&&entries==2,"replay interruption did not stop on second real attempt");
        require(equal(layout(interrupted.plan),entry)&&offers(interrupted)==side,"interrupted continuation leaked branch state");
        require(interrupted.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries&&
                std::count(interrupted.plan.accounting.fallback_events.begin(),interrupted.plan.accounting.fallback_events.end(),"interior_reseat_pose_resume")==1,
                "interrupted continuation lost executed prefix");
        config->interior_order.reset();bool rejected=false;
        try{validate_floorplan_experiment(*config);}catch(const FloorplanError&){rejected=true;}
        require(rejected,"continuation accepted without explicit order");
        config->interior_order=0;config->failed_first_retry=true;
        validate_floorplan_experiment(*config);
        config->failed_first_retry=false;config->reseat_pose_limits->continuations=0;config->reseat_pose_limits->reuse_continuation=true;rejected=false;
        try{validate_floorplan_experiment(*config);}catch(const FloorplanError&){rejected=true;}
        require(rejected,"reuse accepted without continuation budget");
    }
    std::cout<<"pose continuation PASS replays="<<replays<<" skipped="<<skips<<" recovered="<<replay_recovered<<" hints="<<hints<<" empty_hints="<<empty_hints<<'\n';
    auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();in.experiment=experiment;
    experiment->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096};experiment->interior_order=0;
    experiment->pose_retry_completed=[](const auto&){throw std::runtime_error("pose observer stop");};
    Engine e(in);setup(e,cases[1]);const auto before=layout(e.plan);const auto side=offers(e);
    bool threw=false;try{e.attempt_pack(false);}catch(const std::runtime_error& error){threw=std::string(error.what())=="pose observer stop";}
    require(threw,"pose observer interruption fixture did not reach recovery");
    require(equal(layout(e.plan),before)&&offers(e)==side,"pose observer failure did not restore entry state");
    require(std::count(e.plan.accounting.fallback_events.begin(),e.plan.accounting.fallback_events.end(),"interior_reseat_pose_search")==1,
            "observer failure lost executed pose-search receipt");
    experiment->pose_retry_completed={};
    const auto failed=trial(in,cases[1],0);Engine terminal(in);setup(terminal,cases[1]);
    const auto initial=layout(terminal.plan);const auto initial_side=offers(terminal);
    require(!failed.ok&&!terminal.attempt_pack(false),"terminal rollback witness unexpectedly succeeded");
    require(equal(layout(terminal.plan),initial)&&offers(terminal)==initial_side,"terminal recovery failure leaked candidate state");
    require(terminal.plan.accounting.quantization_engagements==failed.plan.accounting.quantization_engagements&&
            terminal.plan.accounting.fallback_events==failed.plan.accounting.fallback_events,"terminal rollback lost or duplicated executed receipts");
    for(const auto limit:std::vector<FloorplanPoseRetryLimits>{{0,1},{1,1},{2,0}}){experiment->reseat_pose_limits=limit;
        bool rejected=false;try{validate_floorplan_experiment(*experiment);}catch(const FloorplanError&){rejected=true;}require(rejected,"invalid pose limits accepted by shared validator");
        rejected=false;try{Engine invalid(in);}catch(const FloorplanError&){rejected=true;}require(rejected,"invalid pose limits accepted");}
    experiment->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096};in.compact_search=false;
    bool rejected=false;try{Engine invalid(in);}catch(const FloorplanError&){rejected=true;}
    require(rejected,"pose recovery accepted without compact search");
    {
        auto joint_input=input();auto joint=std::make_shared<FloorplanExperiment>();joint_input.experiment=joint;
        joint->interior_order=0;joint->joint_separation_states=8;
        const auto direct=trial(joint_input,cases[1],0);Engine wrapped(joint_input);setup(wrapped,cases[1]);
        const auto entry=layout(wrapped.plan);const auto side=offers(wrapped);
        require(!direct.ok&&!wrapped.attempt_pack(false)&&equal(layout(wrapped.plan),entry)&&offers(wrapped)==side,
            "joint-only explicit-order failure did not restore entry state");
        require(wrapped.plan.accounting.quantization_engagements==direct.plan.accounting.quantization_engagements&&
                wrapped.plan.accounting.fallback_events==direct.plan.accounting.fallback_events,"joint-only rollback changed executed receipts");
    }
    std::cout<<"alternative pose retry PASS searches="<<searches<<" attempts="<<attempts<<" budgets="<<exhausted<<" caps="<<capped<<" recovered="<<recovered<<'\n';
}
void neighbour_retry_contract() {
    // Fixed deterministic witness found by bounded synthetic exploration.
    // b1 has no wired participation: it was frozen even though its position
    // is only a packer decision. The near bound is feasible when it can move.
    const Case recovery{63,67,{{6,24,1,2},{9,20,1,7},{23,20,1,3},{18,15,1,4},{7,15,1,7},{6,14,1,5}}};
    auto rescue=input();auto config=std::make_shared<FloorplanExperiment>();rescue.experiment=config;config->interior_order=0;
    rescue.compose.index.hard.push_back({"near_max","b0","b0","b1",11,"test",true,{},{}});
    rescue.compose.wired_participants.insert("b0");
    for(std::size_t i=0;i<recovery.blocks.size();++i){
        const auto& b=recovery.blocks[i];const auto name="b"+std::to_string(i);
        rescue.compose.metrics[name]={{{"p",b.w/2,b.h/2}},{{"p",b.w/2-.5,b.h/2-.5,b.w/2+.5,b.h/2+.5}},{b.w,b.h}};
    }
    require(!trial(rescue,recovery,0).ok,"frozen-neighbour witness unexpectedly passed");
    config->joint_separation_states=32;
    for(bool compact:{false,true}) {
        Engine e(rescue);setup(e,recovery);const auto initial=e.plan;
        require(e.attempt_pack(compact),"joint neighbour translation did not recover feasible witness");
        require(e.plan.som_x==initial.som_x&&e.plan.som_y==initial.som_y&&e.plan.board_w==63&&e.plan.board_h==67,
            "neighbour recovery moved SoM or enlarged outline");
        FloorplanOffsets poses;
        for(std::size_t i=0;i<e.plan.interior_blocks.size();++i){
            const auto& b=e.plan.interior_blocks[i];const auto& size=recovery.blocks[i];
            require(b.w==size.w&&b.h==size.h&&b.shape_idx==0&&b.side=="top","neighbour translation changed shape or face");
            poses[b.name]={b.x,b.y};
        }
        FloorplanLegalizeInput checked;checked.board_w=63;checked.board_h=67;
        checked.metrics=rescue.compose.metrics;checked.index=rescue.compose.index;
        require(floorplan_evaluate_terms(checked,poses).front().ok,"recovered neighbour violated unchanged hard bound");
        require(std::count(e.plan.accounting.fallback_events.begin(),e.plan.accounting.fallback_events.end(),
            "legalize_neighbour_retry")==1,"recovered witness did not count exactly one neighbourhood solve");
        // Enlarging the moving set can let an ordinary axis solve succeed;
        // do not require an unnecessary second joint search after that.
        require(std::count(e.plan.accounting.fallback_events.begin(),e.plan.accounting.fallback_events.end(),
            "legalize_joint_retry")>=1,"recovered witness discarded constrained-only failed search");
        Engine repeat(rescue);setup(repeat,recovery);
        require(repeat.attempt_pack(compact)&&equal(layout(repeat.plan),layout(e.plan))&&
            repeat.plan.accounting.fallback_events==e.plan.accounting.fallback_events&&
            repeat.plan.accounting.quantization_engagements==e.plan.accounting.quantization_engagements,
            "neighbour recovery layout or work receipts are not deterministic");
    }
    const Case c{80,70,{{8,6,1,10},{7,5,1,0}}};
    auto in=input();auto experiment=std::make_shared<FloorplanExperiment>();
    experiment->interior_order=0;in.experiment=experiment;
    in.compose.index.hard.push_back({"near_max","b0","b0","b1",100,"test",true,{},{}});
    in.compose.wired_participants.insert("b0");
    for(const auto* n:{"b0","b1"})in.compose.metrics[n]={{{"p",1,1}},{{"p",0,0,2,2}},{8,6}};
    const auto ordinary=trial(in,c,0);require(ordinary.ok,"neighbour incumbent fixture must pass");
    experiment->joint_separation_states=8;
    const auto enabled=trial(in,c,0);
    require(enabled.ok&&equal(layout(enabled.plan),layout(ordinary.plan))&&enabled.side==ordinary.side,
        "neighbour retry replaced a valid incumbent");
    require(enabled.plan.accounting.quantization_engagements==ordinary.plan.accounting.quantization_engagements&&
            enabled.plan.accounting.fallback_events==ordinary.plan.accounting.fallback_events,
        "valid incumbent performed extra work");
    // An impossible hard bound exercises every failure path without relaxing
    // the requirement. Only b0 was initially movable; b1 is a search neighbour.
    in.compose.index.hard.front().bound=-1;
    const auto direct=trial(in,c,0);
    require(!direct.ok&&std::count(direct.plan.accounting.fallback_events.begin(),
        direct.plan.accounting.fallback_events.end(),"legalize_neighbour_retry")==1,
        "noncompact failure must execute exactly one neighbour retry");
    Engine wrapped(in);setup(wrapped,c);const auto entry=layout(wrapped.plan);const auto side=offers(wrapped);
    require(!wrapped.attempt_pack(false)&&equal(layout(wrapped.plan),entry)&&offers(wrapped)==side,
        "failed neighbour retry leaked poses or side offers");
    require(wrapped.plan.accounting.quantization_engagements==direct.plan.accounting.quantization_engagements&&
            wrapped.plan.accounting.fallback_events==direct.plan.accounting.fallback_events,
        "neighbour rollback lost or duplicated failed work");
    Engine compact_failure(in);setup(compact_failure,c);
    require(!compact_failure.attempt_pack(true)&&equal(layout(compact_failure.plan),entry)&&
        compact_failure.plan.accounting.quantization_engagements==direct.plan.accounting.quantization_engagements&&
        compact_failure.plan.accounting.fallback_events==direct.plan.accounting.fallback_events,
        "pre-compaction failure repeated identical noncompact attempts");
    experiment->stage_rejected=[](const auto& row){
        if(std::any_of(row.diagnostics.begin(),row.diagnostics.end(),[](const auto& line){
            return line.rfind("retry: jointly translate interior neighbours",0)==0;
        }))throw std::runtime_error("neighbour observer stop");
    };
    Engine interrupted(in);setup(interrupted,c);bool threw=false;
    try{interrupted.attempt_pack(false);}catch(const std::runtime_error& error){threw=std::string(error.what())=="neighbour observer stop";}
    require(threw&&equal(layout(interrupted.plan),entry)&&offers(interrupted)==side,
        "interrupted neighbour retry leaked state");
    require(std::count(interrupted.plan.accounting.fallback_events.begin(),interrupted.plan.accounting.fallback_events.end(),
        "legalize_neighbour_retry")==1,"interrupted retry lost executed event");
    std::cout<<"neighbour retry incumbent/failure/exception contracts PASS\n";
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){if(observing&&fn==reinterpret_cast<void*>(&native_run_overflow_tol))++entries;}
extern "C" void __cyg_profile_func_exit(void*,void*){}
void victim_shape_portfolio_contract(){
    using schgen::floorplan_detail::shape_area_trial_order;
    require(shape_area_trial_order({}).empty(),"empty retry catalog must remain empty");
    require(shape_area_trial_order({8,2,2,6,1})==std::vector<std::size_t>({4,1,2,3,0}),
            "area-ordered retries must retain every alternative and stable equal-area order");
    for(bool bottom:{false,true}) {
        auto in=input();auto config=std::make_shared<FloorplanExperiment>();
        config->shape_area_first=true;in.experiment=config;
        Engine e(in);setup(e,Case{70,50,{{16,12,4,0}}});
        if(bottom)config->require_bottom_sheets.insert("b0");
        auto& shapes=e.shape_sets[1]["b0"];
        shapes[1].w=14;shapes[1].h=10;
        shapes[2].w=8;shapes[2].h=8;
        shapes[3].w=12;shapes[3].h=8;
        require(e.attempt_pack_impl(false),"area-first fixture must pack");
        require(e.plan.interior_blocks.front().shape_idx==(bottom?3:2),
                "area-first must select smallest eligible envelope and preserve face constraint");
    }
    using schgen::floorplan_detail::permitted_shape_count;
    for(std::size_t n=0;n<128;++n){
        require(permitted_shape_count(n,std::nullopt)==n,"unrestricted scarcity changed");
        require(permitted_shape_count(n,-1)==0&&permitted_shape_count(n,static_cast<int>(n))==0,
                "invalid selected shape counted as available");
        for(std::size_t index=0;index<n;++index)
            require(permitted_shape_count(n,static_cast<int>(index))==1,
                    "pinned shape falsely retains all registered alternatives");
    }
    require(permitted_shape_count(87,72)<permitted_shape_count(2,std::nullopt),
            "pinned large catalog should precede a two-choice group in scarcity order");
    for(std::size_t n=0;n<=8;++n)for(unsigned mask=0;mask<(1U<<n);++mask) {
        const auto allowed=[&](std::size_t i){return (mask&(1U<<i))!=0;};
        std::size_t expected=0;
        for(std::size_t i=0;i<n;++i)if(allowed(i))++expected;
        require(permitted_shape_count(n,std::nullopt,allowed)==expected,
                "face-ineligible shapes inflate scarcity");
        for(int selected=-1;selected<=static_cast<int>(n);++selected)
            require(permitted_shape_count(n,selected,allowed)==
                    (selected>=0&&selected<static_cast<int>(n)&&allowed(selected)?1U:0U),
                    "pinned choice must also satisfy face restriction");
    }
    {
        const Case constrained{70,50,{{16,12,2,0},{16,12,4,0}}};
        auto in=input();Engine scarce(in),forced(in);
        setup(scarce,constrained);setup(forced,constrained);
        scarce.owned_shape_choices["b1"]=0;forced.owned_shape_choices["b1"]=0;
        scarce.compact_order=2;forced.compact_order=0;
        require(scarce.attempt_pack_impl(false)&&forced.attempt_pack_impl(false,nullptr,"b1"),
                "scarcity integration fixture must pack");
        require(equal(layout(scarce.plan),layout(forced.plan)),
                "scarcity order did not prioritize the actually single-choice group");
    }
    {
        const Case constrained{70,50,{{16,12,2,0},{16,12,4,0}}};
        auto in=input();auto config=std::make_shared<FloorplanExperiment>();in.experiment=config;
        Engine scarce(in),forced(in);setup(scarce,constrained);setup(forced,constrained);
        config->require_bottom_sheets.insert("b1");
        scarce.shape_sets[1]["b1"][3].side="top";
        forced.shape_sets[1]["b1"][3].side="top";
        scarce.compact_order=2;forced.compact_order=0;
        require(scarce.attempt_pack_impl(false)&&forced.attempt_pack_impl(false,nullptr,"b1"),
                "bottom-restricted scarcity integration fixture must pack");
        require(equal(layout(scarce.plan),layout(forced.plan)),
                "scarcity order ignored the single eligible bottom alternative");
    }
    std::size_t preserved=0,recovered=0,failed=0,queries=0,incoming_recovered=0,incoming_queries=0;
    std::size_t combination_only=0,paired_queries=0,area_queries=0,pose_shape_queries=0,shape_skips=0;
    bool exception_checked=false;
    std::size_t pair_trials=0,pair_success=0,pair_finalists=0;
    const Case crowded{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    for(bool area_first:{false,true})for(bool rotate:{false,true})for(int w=65;w<=85;w+=5)for(int h=45;h<=65;h+=5)for(int order=0;order<3;++order){
        auto c=crowded;c.w=w;c.h=h;
        const auto prepare=[&](Engine& e){
            setup(e,c);
            for(auto& [name,shapes]:e.shape_sets[1]) {
                (void)name;
                if(shapes.size()>2) {
                    if(rotate)std::swap(shapes[2].w,shapes[2].h);
                    if(area_first)shapes[2].w*=0.8;
                }
            }
        };
        auto in=input();auto config=std::make_shared<FloorplanExperiment>();in.experiment=config;
        config->interior_order=order;config->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,2};
        config->shape_area_first=area_first;
        Engine original(in);prepare(original);const bool original_ok=original.attempt_pack(false);
        auto expected_counts=original.plan.accounting.quantization_engagements;
        auto expected_events=original.plan.accounting.fallback_events;
        std::optional<Result> branch;
        if(!original_ok){
            Engine direct(in);prepare(direct);direct.compact_order=order;entries=0;observing=true;
            const bool ok=direct.attempt_pack_impl(false,nullptr,{},nullptr,0,nullptr,true,true);
            observing=false;
            require(direct.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries,"shape branch operation count");
            branch=Result{ok,direct.plan,offers(direct),entries};
            Engine skipped(in),skip_repeat(in);prepare(skipped);prepare(skip_repeat);
            skipped.compact_order=skip_repeat.compact_order=order;
            const bool skip_ok=skipped.attempt_pack_impl(false,nullptr,{},nullptr,1,nullptr,true,true);
            require(skip_repeat.attempt_pack_impl(false,nullptr,{},nullptr,1,nullptr,true,true)==skip_ok &&
                    equal(floorplan_plan_json(skipped.plan),floorplan_plan_json(skip_repeat.plan)) &&
                    offers(skipped)==offers(skip_repeat),"pose/shape continuation replay is not deterministic");
            bool shape_since_pose=false;
            for(const auto& event:skipped.plan.accounting.fallback_events) {
                if(event=="interior_reseat_pose_trial")shape_since_pose=false;
                if(event=="interior_reseat_shape_trial")shape_since_pose=true;
                if(event=="interior_reseat_pose_skip"&&shape_since_pose)++shape_skips;
            }
            Engine previous(in);prepare(previous);previous.compact_order=order;
            const bool previous_ok=previous.attempt_pack_impl(false,nullptr,{},nullptr,0,nullptr,true,false);
            if(previous_ok)require(ok&&equal(floorplan_plan_json(previous.plan),floorplan_plan_json(direct.plan))&&offers(previous)==offers(direct),"incoming shapes replaced a successful victim strategy");
            else if(ok){
                const bool used_pair=std::find(direct.plan.accounting.fallback_events.begin(),
                    direct.plan.accounting.fallback_events.end(),"interior_reseat_pair_recovered")!=
                    direct.plan.accounting.fallback_events.end();
                if(!used_pair)++incoming_recovered;
                Engine incoming_only(in);prepare(incoming_only);incoming_only.compact_order=order;
                const bool alone=incoming_only.attempt_pack_impl(false,nullptr,{},nullptr,0,nullptr,false,true);
                if(!used_pair&&!alone)++combination_only;
            }
            auto delta=direct.plan.accounting.quantization_engagements;delta.erase("entry-sentinel");
            checked_quantization_merge(expected_counts,delta);
            expected_events.push_back("interior_reseat_shape_retry");
            expected_events.insert(expected_events.end(),direct.plan.accounting.fallback_events.begin()+1,direct.plan.accounting.fallback_events.end());
        }
        config->reseat_pose_limits->victim_shapes=true;
        Engine actual(in);prepare(actual);const auto initial=layout(actual.plan);const auto initial_offers=offers(actual);
        const bool ok=actual.attempt_pack(false);
        require(offers(actual).at("entry")==initial_offers.at("entry"),
                "shape/pair recovery modified an unrelated side offer");
        require(ok==(original_ok||(branch&&branch->ok)),"shape portfolio omitted or replaced a strategy");
        require(actual.plan.accounting.quantization_engagements==expected_counts&&actual.plan.accounting.fallback_events==expected_events,
                "shape portfolio lost or duplicated executed work");
        if(original_ok){++preserved;require(equal(layout(actual.plan),layout(original.plan))&&offers(actual)==offers(original),"shape portfolio replaced an incumbent");}
        else if(ok){++recovered;require(equal(layout(actual.plan),layout(branch->plan))&&offers(actual)==branch->side,"shape strategy result mismatch");}
        else {++failed;require(equal(layout(actual.plan),initial)&&offers(actual)==initial_offers,"shape strategy failure leaked state");}
        if(ok){const auto& blocks=actual.plan.interior_blocks;
            for(std::size_t i=0;i<blocks.size();++i){const auto& a=blocks[i];
                require(a.x>=0&&a.y>=0&&a.x+a.w<=c.w&&a.y+a.h<=c.h,"shape branch outside outline");
                for(std::size_t j=0;j<i;++j){const auto& b=blocks[j];
                    require(a.side!=b.side||a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y,"shape branch rectangles overlap");
                }
            }
        }
        queries+=std::count(expected_events.begin(),expected_events.end(),"interior_reseat_shape_trial");
        const auto pair_count=[&](const auto* name){return std::count(expected_events.begin(),expected_events.end(),name);};
        require(pair_count("interior_reseat_pair_trial")==pair_count("interior_reseat_pair_recovered")+
                pair_count("interior_reseat_pair_rejected"),"completed paired trials lack a terminal outcome");
        pair_trials+=pair_count("interior_reseat_pair_trial");
        pair_success+=pair_count("interior_reseat_pair_recovered");
        if(ok&&pair_count("interior_reseat_pair_recovered"))++pair_finalists;
        if(area_first)area_queries+=std::count(expected_events.begin(),expected_events.end(),"interior_reseat_shape_trial");
        incoming_queries+=std::count(expected_events.begin(),expected_events.end(),"interior_reseat_incoming_shape_trial");
        // Pass 2 is the only source of incoming-shape queries. A displaced
        // shape query after entering that pass proves paired exploration,
        // rather than two independent earlier strategies being mislabeled.
        bool incoming_phase=false,pose_phase=false;
        for(const auto& event:expected_events) {
            if(event=="interior_reseat_pose_trial")pose_phase=true;
            if(event=="interior_reseat_pose_search"||event=="interior_reseat_incoming_shape_trial"||
               event=="interior_reseat_retry"||event=="interior_reseat_shape_retry"||
               event=="interior_failed_first_retry"||event=="interior_reseat_pose_resume"||
               event=="interior_reseat_pair_trial")pose_phase=false;
            if(event=="interior_reseat_pair_trial")incoming_phase=false;
            if(pose_phase&&event=="interior_reseat_shape_trial")++pose_shape_queries;
            if(event=="interior_reseat_incoming_shape_trial")incoming_phase=true;
            if(incoming_phase&&event=="interior_reseat_shape_trial")++paired_queries;
            // A recovered block can be followed by another block's ordinary
            // victim-only pass; those later queries are not paired trials.
            if(event=="interior_reseat_retry")incoming_phase=false;
        }
        Engine repeat(in);prepare(repeat);require(repeat.attempt_pack(false)==ok&&equal(floorplan_plan_json(repeat.plan),floorplan_plan_json(actual.plan))&&offers(repeat)==offers(actual),"shape portfolio is not deterministic");
        if(!ok&&!exception_checked&&std::count(expected_events.begin(),expected_events.end(),"interior_reseat_shape_trial")){
            Engine interrupted(in);prepare(interrupted);
            config->stage_rejected=[&](const auto&){
                const auto& events=interrupted.plan.accounting.fallback_events;
                if(std::find(events.begin(),events.end(),"interior_reseat_shape_retry")!=events.end())
                    throw std::runtime_error("shape observer interrupted");
            };
            try{(void)interrupted.attempt_pack(false);}catch(const std::runtime_error& e){exception_checked=std::string(e.what())=="shape observer interrupted";}
            config->stage_rejected={};
            require(exception_checked&&equal(layout(interrupted.plan),initial)&&offers(interrupted)==initial_offers,"shape exception did not restore entry state");
            const auto& events=interrupted.plan.accounting.fallback_events;
            require(std::count(events.begin(),events.end(),"interior_reseat_shape_retry")==1&&
                std::count(events.begin(),events.end(),"interior_reseat_shape_trial")>0,"shape exception lost executed attempts");
        }
    }
    require(preserved&&recovered&&failed&&queries&&exception_checked,"shape fixtures missed preservation, recovery, rollback, exception or actual queries");
    require(incoming_recovered&&incoming_queries,"incoming-shape strategy has no tested recovery or work");
    require(combination_only>0,"no witness where both shape strategies succeed but either alone fails");
    require(paired_queries>0,"alternative incoming shapes never tried alternative displaced shapes");
    require(area_queries>0,"area-first corpus did not execute alternative shape recovery");
    require(pose_shape_queries>0,"alternative incoming poses never reconsidered displaced shapes");
    require(pair_trials&&pair_success&&pair_finalists,"pair corpus lacks executed trials, recovery or a complete finalist");
    std::cout<<"paired relocation trials="<<pair_trials<<" recovered="<<pair_success<<" finalists="<<pair_finalists<<'\n';
    require(shape_skips>0,"continuation corpus never skipped a recovered alternative victim shape");
    std::cout<<"pose/shape combination queries="<<pose_shape_queries<<'\n';
    std::cout<<"pose/shape continuation skips="<<shape_skips<<'\n';
    {
        auto locked_input=input();auto locked_config=std::make_shared<FloorplanExperiment>();locked_input.experiment=locked_config;
        locked_config->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096};
        Engine locked(locked_input);setup(locked,crowded);
        for(const auto& b:locked.plan.interior_blocks)locked.owned_shape_choices[b.name]=0;
        (void)locked.attempt_pack_impl(false,nullptr,{},nullptr,0,nullptr,true,true);
        const auto& events=locked.plan.accounting.fallback_events;
        require(std::count(events.begin(),events.end(),"interior_reseat_incoming_shape_trial")==0,"incoming recovery ignored explicit shape selection");
    }
    std::cout<<"incoming shape recovery PASS recovered="<<incoming_recovered<<" queries="<<incoming_queries<<'\n';
    std::cout<<"shape interaction PASS combination_only="<<combination_only<<" paired_queries="<<paired_queries<<'\n';
    std::cout<<"victim shape portfolio PASS preserved="<<preserved<<" recovered="<<recovered<<" failed="<<failed<<" queries="<<queries<<'\n';
    FloorplanExperiment invalid;invalid.reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,0,false,true};
    bool rejected=false;try{validate_floorplan_experiment(invalid);}catch(const FloorplanError&){rejected=true;}
    require(rejected,"shape portfolio silently accepted missing explicit order");
}
void combined_order_shape_contract(){
    const Case crowded{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    std::size_t combined_attempts=0,recovered=0,failed_cases=0;
    bool exception_verified=false;
    for(std::size_t continuations:{0,2})for(bool rotate:{false,true})for(int w=65;w<=85;w+=5)for(int h=45;h<=65;h+=5)for(int order=0;order<3;++order){
        auto c=crowded;c.w=w;c.h=h;
        auto in=input();auto config=std::make_shared<FloorplanExperiment>();in.experiment=config;
        config->interior_order=order;config->failed_first_retry=true;
        config->reseat_pose_limits=FloorplanPoseRetryLimits{8,4096,continuations,false,true};
        auto prepare=[&](Engine& e){setup(e,c);e.compact_order=order;
            if(rotate)for(auto& [name,shapes]:e.shape_sets[1]){(void)name;if(shapes.size()>2)std::swap(shapes[2].w,shapes[2].h);}
        };
        Engine first(in);prepare(first);std::string subject;
        bool selected=false;
        entries=0;observing=true;
        bool expected=first.attempt_pack_impl(false,nullptr,{},&subject,0,&selected);
        if(!expected&&selected)for(std::size_t skip=1;skip<=continuations;++skip){
            Engine replay(in);prepare(replay);bool replay_selected=false;
            expected=replay.attempt_pack_impl(false,nullptr,{},nullptr,skip,&replay_selected);
            if(expected||!replay_selected)break;
        }
        if(!expected&&!subject.empty()){Engine promoted(in);prepare(promoted);expected=promoted.attempt_pack_impl(false,nullptr,subject);}
        if(!expected){Engine shapes(in);prepare(shapes);expected=shapes.attempt_pack_impl(false,nullptr,{},nullptr,0,nullptr,true,true);}
        bool combined=false;
        if(!expected&&!subject.empty()){
            ++combined_attempts;combined=true;Engine both(in);prepare(both);
            expected=both.attempt_pack_impl(false,nullptr,subject,nullptr,0,nullptr,true,true);
            if(expected)++recovered;
        }
        observing=false;const auto reference_calls=entries;
        Engine actual(in);prepare(actual);const auto initial=layout(actual.plan);const auto initial_offers=offers(actual);
        entries=0;observing=true;const bool ok=actual.attempt_pack(false);observing=false;
        require(ok==expected,"combined order/shape strategy omitted or fabricated a result");
        require(entries==reference_calls,"combined wrapper omitted or duplicated an independently executed strategy");
        require(actual.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries,
                "combined strategy lost independently observed work");
        const auto& events=actual.plan.accounting.fallback_events;
        if(combined)require(std::count(events.begin(),events.end(),"interior_reseat_shape_retry")==2&&
                            std::count(events.begin(),events.end(),"interior_failed_first_retry")==2,
                            "combined attempt must record both executed strategy dimensions");
        if(!ok){++failed_cases;require(equal(layout(actual.plan),initial)&&offers(actual)==initial_offers,
                                      "combined failed strategy leaked partial state");}
        else for(const auto& a:actual.plan.interior_blocks){
            require(a.x>=0&&a.y>=0&&a.x+a.w<=w&&a.y+a.h<=h,"combined recovery outside board");
            for(const auto& b:actual.plan.interior_blocks)if(a.name!=b.name)
                require(a.side!=b.side||a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y,
                        "combined recovery overlaps same-face blocks");
        }
        Engine repeat(in);prepare(repeat);require(repeat.attempt_pack(false)==ok&&
            equal(floorplan_plan_json(actual.plan),floorplan_plan_json(repeat.plan))&&offers(actual)==offers(repeat),
            "combined recovery not reproducible including accounting");
        if(combined&&!ok&&!exception_verified){
            Engine interrupted(in);prepare(interrupted);
            config->stage_rejected=[&](const auto&){
                const auto& seen=interrupted.plan.accounting.fallback_events;
                if(std::count(seen.begin(),seen.end(),"interior_reseat_shape_retry")==2)
                    throw std::runtime_error("combined stop");
            };
            entries=0;observing=true;
            try{(void)interrupted.attempt_pack(false);}catch(const std::runtime_error& e){exception_verified=std::string(e.what())=="combined stop";}
            observing=false;config->stage_rejected={};
            require(exception_verified&&equal(layout(interrupted.plan),initial)&&offers(interrupted)==initial_offers,
                    "interrupted combined attempt leaked state or swallowed exception");
            require(interrupted.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries&&
                std::count(interrupted.plan.accounting.fallback_events.begin(),interrupted.plan.accounting.fallback_events.end(),"interior_reseat_shape_retry")==2,
                "interrupted combined attempt lost executed work");
        }
    }
    require(combined_attempts&&failed_cases&&exception_verified,"combined fixture missed execution, rollback or exception");
    std::cout<<"combined order/shape PASS attempts="<<combined_attempts<<" recovered="<<recovered<<" failures="<<failed_cases<<'\n';
}
void shape_choice_replay_contract() {
    const auto hit=[](int index,const char* side){SeatShapeHit h;h.index=index;h.side=side;return h;};
    const std::vector<SeatShapeHit> face_hits{hit(0,"top"),hit(1,"top"),hit(2,"top"),hit(3,"bottom"),hit(4,"bottom")};
    require(floorplan_detail::face_diverse_replay_indices(face_hits,face_hits[0])==std::vector<int>({0,3,1,2,4}),
            "same-face rotations starved the opposite-face first retry");
    require(floorplan_detail::face_diverse_replay_indices(face_hits,face_hits[4])==std::vector<int>({4,0,1,2,3}),
            "bottom incumbent did not retain a top-face retry or lost an offer");
    require(floorplan_detail::face_diverse_replay_indices({face_hits[0],face_hits[1],face_hits[2]},face_hits[1])==std::vector<int>({1,0,2}),
            "single-face retry order changed");
    require(floorplan_detail::face_diverse_replay_indices({face_hits[3]},face_hits[3])==std::vector<int>({3}),
            "singleton replay fabricated an alternative");
    auto in=input();auto config=std::make_shared<FloorplanExperiment>();
    config->interior_order=0;in.experiment=config;
    const Case roomy{80,70,{{8,6,2,100},{7,5,2,1}}};
    Engine baseline(in);setup(baseline,roomy);require(baseline.attempt_pack(false),"roomy control failed");
    config->shape_choice_replays=16;
    Engine unchanged(in);setup(unchanged,roomy);
    unchanged.shape_replay_hint=std::make_pair(Engine::ContinuationKey{80,70,true,false,0},std::map<std::string,int>{{"b0",1}});
    require(unchanged.attempt_pack(false),"replay displaced success");
    require(equal(floorplan_plan_json(baseline.plan),floorplan_plan_json(unchanged.plan))&&
            offers(baseline)==offers(unchanged),"successful incumbent or accounting changed");
    // Two independently selectable early blocks plus a genuinely impossible
    // final block: all four side combinations must execute before exhaustion.
    const Case impossible{80,70,{{8,6,2,100},{7,5,2,1}},true};
    Engine failed(in);setup(failed,impossible);const auto initial=layout(failed.plan);
    const auto initial_offers=offers(failed);
    std::vector<std::map<std::string,int>> executed_prefixes;
    config->stage_rejected=[&](const auto&){executed_prefixes.push_back(failed.shape_replay_choices);};
    entries=0;observing=true;require(!failed.attempt_pack(false),"oversized terminal accepted");observing=false;
    config->stage_rejected={};
    const auto& events=failed.plan.accounting.fallback_events;
    require(std::count(events.begin(),events.end(),"interior_shape_choice_replay")==3,
            "two-choice replay must explore combined alternatives, not isolated switches only");
    require(entries==4&&failed.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries,
            "replay lost or invented actual scalar work");
    require(equal(initial,layout(failed.plan))&&initial_offers==offers(failed)&&
            failed.owned_shape_choices.empty()&&!failed.shape_replay_trace,
            "exhaustion leaked plan, offers, restrictions or borrowed trace");
    require(std::count(events.begin(),events.end(),"interior_shape_choice_budget")==0,
            "complete prefix exhaustion incorrectly claimed a budget cutoff");
    // Re-run each observed prefix as an isolated ordinary attempt. Sum every
    // receipt, not merely a selected counter or the successful final attempt.
    config->shape_choice_replays=0;
    QuantizationCounts expected{{"entry-sentinel",19}};
    std::vector<std::string> expected_events{"entry-fallback"};
    require(executed_prefixes.size()==4,"missing completed prefix observations");
    for(std::size_t i=0;i<executed_prefixes.size();++i) {
        Engine isolated(in);setup(isolated,impossible);isolated.shape_replay_choices=executed_prefixes[i];
        require(!isolated.attempt_pack(false),"isolated impossible prefix accepted");
        auto delta=isolated.plan.accounting.quantization_engagements;delta.erase("entry-sentinel");
        checked_quantization_merge(expected,delta);
        if(i)expected_events.push_back("interior_shape_choice_replay");
        const auto& isolated_events=isolated.plan.accounting.fallback_events;
        expected_events.insert(expected_events.end(),isolated_events.begin()+1,isolated_events.end());
    }
    require(failed.plan.accounting.quantization_engagements==expected&&events==expected_events,
            "replay aggregate differs from independently executed prefix receipts");
    config->shape_choice_replays=16;
    const Engine::ContinuationKey hint_key{80,70,true,false,0};
    for(int mode=0;mode<3;++mode) {
        Engine hinted(in);setup(hinted,impossible);
        auto key=hint_key;auto choices=executed_prefixes.at(2);
        if(mode==1)std::get<0>(key)=81; // Different outline: cannot reuse ordering.
        if(mode==2)choices["b0"]=999; // Not in the newly generated frontier.
        hinted.shape_replay_hint=std::make_pair(key,choices);
        std::vector<std::map<std::string,int>> actual;
        config->stage_rejected=[&](const auto&){actual.push_back(hinted.shape_replay_choices);};
        require(!hinted.attempt_pack(false),"stale success hint bypassed failed geometry");
        config->stage_rejected={};
        require(actual.size()==executed_prefixes.size()&&
                std::set<std::map<std::string,int>>(actual.begin(),actual.end())==
                std::set<std::map<std::string,int>>(executed_prefixes.begin(),executed_prefixes.end()),
                "hint injected or pruned a prefix");
        require(hinted.plan.accounting.quantization_engagements==expected&&equal(layout(hinted.plan),initial),
                "hint reused acceptance, changed isolated work or leaked layout");
        const auto& hinted_events=hinted.plan.accounting.fallback_events;
        require(std::count(hinted_events.begin(),hinted_events.end(),"interior_shape_choice_hint")==
                (mode==0?1:0),"hint promotion accounting mismatch");
        require(mode==0?actual.at(1)==choices:actual==executed_prefixes,
                "matching hint not prioritised or stale hint affected order");
    }
    config->shape_choice_replays=1;
    Engine capped(in);setup(capped,impossible);require(!capped.attempt_pack(false),"capped impossible fixture accepted");
    require(std::count(capped.plan.accounting.fallback_events.begin(),capped.plan.accounting.fallback_events.end(),
                       "interior_shape_choice_budget")==1,"unexplored branches lost budget receipt");
    config->shape_choice_replays=2;
    const Case many_shapes{80,70,{{8,6,6,100},{7,5,2,1}},true};
    Engine fair(in);setup(fair,many_shapes);
    std::vector<std::map<std::string,int>> replayed;
    std::map<std::string,int> root_choices;
    config->owned_shape_selection_completed=[&](const auto& name,const auto&,const auto&,int chosen){
        if(fair.shape_replay_choices.empty())root_choices.emplace(name,chosen);
    };
    config->stage_rejected=[&](const auto&){replayed.push_back(fair.shape_replay_choices);};
    require(!fair.attempt_pack(false),"fair-frontier terminal accepted");config->stage_rejected={};
    config->owned_shape_selection_completed={};
    require(replayed.size()==3&&replayed[0].empty()&&replayed[1].size()==1&&replayed[1].at("b0")!=root_choices.at("b0")&&
            replayed[2].at("b0")==root_choices.at("b0")&&replayed[2].at("b1")!=root_choices.at("b1"),
            "shape-rich first block starved the next block's first alternative");
    config->shape_choice_replays=1;
    // Existing hard shape restrictions must remain hard and survive rollback.
    Engine pinned(in);setup(pinned,impossible);pinned.owned_shape_choices={{"b0",1},{"b1",1}};
    require(!pinned.attempt_pack(false)&&pinned.owned_shape_choices==std::map<std::string,int>{{"b0",1},{"b1",1}},
            "replay relaxed caller restrictions");
    require(std::count(pinned.plan.accounting.fallback_events.begin(),pinned.plan.accounting.fallback_events.end(),
                       "interior_shape_choice_replay")==0,"replayed a restricted singleton");
    Engine interrupted(in);setup(interrupted,impossible);
    config->stage_rejected=[&](const auto&){
        if(std::count(interrupted.plan.accounting.fallback_events.begin(),interrupted.plan.accounting.fallback_events.end(),
                      "interior_shape_choice_replay"))throw std::runtime_error("shape replay stop");
    };
    bool propagated=false;entries=0;observing=true;
    try{(void)interrupted.attempt_pack(false);}catch(const std::runtime_error& e){propagated=std::string(e.what())=="shape replay stop";}
    observing=false;config->stage_rejected={};
    require(propagated&&equal(initial,layout(interrupted.plan))&&initial_offers==offers(interrupted)&&
            interrupted.owned_shape_choices.empty()&&!interrupted.shape_replay_trace,
            "interrupted replay swallowed exception or leaked state");
    require(entries==2&&interrupted.plan.accounting.quantization_engagements.at("run_overflow_tol")==entries,
            "exception lost executed replay work");
    config->shape_choice_replays=32;
    const Case trap{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    config->shape_choice_replays=0;
    Engine trapped(in);setup(trapped,trap);require(!trapped.attempt_pack(false),"recovery control no longer fails");
    config->shape_choice_replays=32;
    Engine recovered(in);setup(recovered,trap);
    const bool ok=recovered.attempt_pack(false);
    std::cout<<"shape-choice recovery witness="<<ok<<" replays="<<std::count(recovered.plan.accounting.fallback_events.begin(),
        recovered.plan.accounting.fallback_events.end(),"interior_shape_choice_replay")<<'\n';
    require(ok,"shape-choice recovery witness not recovered");
    require(recovered.shape_replay_hint&& !recovered.shape_replay_hint->second.empty(),
            "successful replay did not retain its ordering hint");
    for(const auto& a:recovered.plan.interior_blocks) {
        require(a.x>=0&&a.y>=0&&a.x+a.w<=trap.w&&a.y+a.h<=trap.h,"replay escaped board bounds");
        for(const auto& b:recovered.plan.interior_blocks)if(a.name!=b.name)
            require(a.side!=b.side||a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y,
                    "replay accepted overlapping same-face rectangles");
    }
    Engine repeated(in);setup(repeated,trap);require(repeated.attempt_pack(false)&&
        equal(floorplan_plan_json(recovered.plan),floorplan_plan_json(repeated.plan))&&offers(recovered)==offers(repeated),
        "replay changed deterministic output or accounting");
    config->shape_choice_replays=2;
    auto hard=in;FloorplanTerm term;term.kind="far_min";term.sheet="b0";term.subject="b0";term.target_raw="b1";term.bound=1000;term.enforced=true;
    hard.compose.index.hard={term,{"near_max","b0","b0","b1",100,"test",true,{},{}}};
    hard.compose.wired_participants.insert("b0");
    for(const auto* name:{"b0","b1"}) {
        hard.compose.metrics[name]={{{"U1",1,1}},{{"U1",0,0,2,2}},{8,6}};
        hard.compose.shape_metrics[{name,1}]=hard.compose.metrics[name];
    }
    Engine constrained(hard);setup(constrained,roomy);
    require(!constrained.attempt_pack(false),"shape replay bypassed impossible authored hardware distance");
}
int main(){try{
    shape_choice_replay_contract();
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
    reseat_trace_contract();
    reseat_offer_rollback_contract();
    single_order_contract();
    failed_first_contract();
    alternative_pose_retry_contract();
    victim_shape_portfolio_contract();
    combined_order_shape_contract();
    neighbour_retry_contract();
    for(bool first:{false,true})for(bool translate:{false,true})invariant_edge_failure(first,translate);
    for(bool translate:{false,true})invariant_edge_failure(false,translate,true);
    for(bool translate:{false,true})invariant_edge_failure(false,translate,false,true);
    std::cout<<"compact retry contracts PASS\n";return 0;
}catch(const std::exception& e){observing=false;std::cerr<<e.what()<<'\n';return 1;}}
