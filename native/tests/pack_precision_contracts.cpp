#include "placement_precision_fixture.hpp"
// Compile pack_precision.cpp alone with function-entry instrumentation. The
// immutable baseline mode compiles against the saved pre-extraction sources.
#include "schgen/pack.hpp"
#include "schgen/pack_edges.hpp"
#include "schgen/native_audit_state.hpp"
#include "pcb_placement_fixture.hpp"
#include "ledger_accounting_fixture.hpp"
#include "pack_precision_fixture.hpp"
#ifndef PACK_PRECISION_BASELINE
#include "schgen/pack_precision.hpp"
#define PACK_COUNTS(q) , &(q)
#else
#define PACK_COUNTS(q)
#endif
#include <atomic>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <thread>

namespace {
using namespace schgen;
using namespace pack_precision_fixture;
std::array<std::atomic<std::size_t>,6> observed{};
std::atomic<bool> recording{false};
std::ostringstream legacy;
void require(bool condition,const std::string& why) { if(!condition)throw std::runtime_error(why); }
std::uint64_t bits(double x) { std::uint64_t b;std::memcpy(&b,&x,sizeof b);return b; }
void number(double x) { legacy<<bits(x)<<' '; }
void node(const JsonNode& n) {
    legacy<<static_cast<int>(n.kind)<<' ';
    switch(n.kind) {
    case JsonKind::Null:break;
    case JsonKind::Bool:legacy<<n.bool_value;break;
    case JsonKind::Number:number(n.number_value);break;
    case JsonKind::String:legacy<<std::quoted(n.string_value);break;
    case JsonKind::Array:legacy<<n.array_value.size()<<' ';for(const auto& v:n.array_value)node(v);break;
    case JsonKind::Object:legacy<<n.object_value.size()<<' ';for(const auto& [key,v]:n.object_value){legacy<<std::quoted(key)<<' ';node(v);}break;
    }
    legacy<<'\n';
}
void begin() { for(auto& n:observed)n=0;recording=true; }
QuantizationCounts end() {
    recording=false;QuantizationCounts q;
    for(std::size_t i=0;i<names.size();++i)if(observed[i])q[names[i]]=observed[i].load();
    return q;
}
void receipt(const QuantizationCounts& owned,const QuantizationCounts& entries) {
#ifndef PACK_PRECISION_BASELINE
    require(select(owned)==entries,"owned counts differ from independent scalar entries");
#else
    (void)owned;(void)entries;
#endif
}
void prior_counts(const QuantizationCounts& q) {
    for(const auto& [name,n]:placement_precision_fixture::select(select(q,false),false))legacy<<std::quoted(name)<<' '<<n<<'\n';
}
template<class Error,class F> void rejects(F action) {
    bool caught=false;try{action();}catch(const Error&){caught=true;}
    require(caught,"expected domain rejection");
}
#ifndef PACK_PRECISION_BASELINE
using Round=double(*)(double,QuantizationCounts*);
const std::array<Round,5> rounds{{pack_shelf_pose_precision4dp,pack_shelf_extent_precision4dp,
    pack_control_pose_precision4dp,pack_edge_pose_precision4dp,pack_hf_cap_pose_precision4dp}};
const std::array<std::size_t,5> indices{{0,1,3,4,5}};
void scalar_contracts() {
    const QuantizationCounts unknown{{"pack_shelf_pose_precision4dp_extra",7},{"pack_unknown",9}};
    require(select(unknown,false)==unknown && select(unknown).empty(),"unknown accounting names filtered");
    for(std::size_t i=0;i<rounds.size();++i) {
        const auto& name=names[indices[i]];
        for(int k=-512;k<=512;++k) {
            const double middle=(k+.5)/10000.;
            for(double v:{std::nextafter(middle,-INFINITY),middle,std::nextafter(middle,INFINITY)}) {
                QuantizationCounts q;begin();const double value=rounds[i](v,&q);const auto calls=end();
                require(bits(value)==bits(py_round(v,4)),"rounding order/tie semantics changed");
                receipt(q,calls);require(calls==QuantizationCounts{{name,1}},"scalar entry missing");
            }
        }
        for(double v:{0.,-0.,1e-300,-1e-300,1e300,double(INFINITY),double(NAN)})
            require(bits(rounds[i](v,nullptr))==bits(py_round(v,4)),"IEEE scalar result changed");
        QuantizationCounts full{{name,SIZE_MAX}};begin();
        rejects<std::overflow_error>([&]{rounds[i](1,&full);});const auto overflow_calls=end();
        require(full.at(name)==SIZE_MAX && overflow_calls==QuantizationCounts{{name,1}},"counter wrapped");
        QuantizationCounts rejected;begin();
        rejects<std::runtime_error>([&]{rounds[i](0x1.0000000000001p51,&rejected);});
        receipt(rejected,end());require(rejected==QuantizationCounts{{name,1}},"round cap attempt not retained");
    }
    for(double v:{-10.9,-.9,-0.,0.,.9,1.,double(INT32_MAX)+.75,double(INT32_MIN)-.75}) {
        QuantizationCounts q;begin();const int fit=pack_control_fit_trunc(v,&q);receipt(q,end());
        require(fit==static_cast<int>(v)&&q==QuantizationCounts{{names[2],1}},"defined truncation changed");
    }
    for(double v:{double(INFINITY),double(-INFINITY),double(NAN)})
        rejects<std::invalid_argument>([&]{pack_control_fit_trunc(v);});
    for(double v:{double(INT32_MAX)+1,double(INT32_MIN)-1,1e300,-1e300})
        rejects<std::out_of_range>([&]{pack_control_fit_trunc(v);});
    // Dyadic inputs are exact; integer division is an independent truncation oracle.
    for(int n=-100000;n<=100000;++n)
        require(pack_control_fit_trunc(n/16.)==n/16,"exact dyadic truncation oracle");
    NativeQuantizations registry;register_native_quantizations(registry);
    const auto declarations=registry.declarations();
    for(std::size_t i=0;i<names.size();++i) {
        const auto d=std::find_if(declarations.begin(),declarations.end(),[&](const auto& item){return item.name==names[i];});
        require(d!=declarations.end()&&d->arity==1&&d->symbol=="native/src/pack_precision.cpp::schgen::"+names[i],
                "stable scalar identity and one-value arity");
        begin();const double actual=registry.invoke(names[i],{1.23455});const auto calls=end();
        require(bits(actual)==bits(i==2?1.:py_round(1.23455,4))&&calls==QuantizationCounts{{names[i],1}},
                "registry does not execute real boundary once");
        const auto counts=registry.engagements();
        for(const auto& args:std::vector<std::vector<double>>{{},{1.,2.}}) {
            begin();rejects<std::invalid_argument>([&]{registry.invoke(names[i],args);});
            require(end().empty()&&registry.engagements()==counts,"arity failure cannot enter scalar or count");
        }
    }
    std::array<QuantizationCounts,2> owned;
    begin();std::array<std::thread,2> workers;
    for(std::size_t i=0;i<workers.size();++i)workers[i]=std::thread([&,i]{
        for(int k=0;k<20;++k)(void)shelf_pack({},4,{},.3,&owned[i]);
    });
    for(auto& worker:workers)worker.join();const auto calls=end();
    require(owned[0]==owned[1]&&owned[0]==QuantizationCounts{{names[1],40}}&&
            calls==QuantizationCounts{{names[1],80}},"independent sinks share state");
}
#endif
void producer_contracts() {
    for(double width:{2.,4.00005,10.})for(int count:{0,1,5}) {
        std::vector<ShelfItem> items;
        for(int i=0;i<count;++i)items.push_back({"R"+std::to_string(i),{-.125,-.375,1.125,.375},.05,i%2==0});
        QuantizationCounts q;begin();const auto p=shelf_pack(items,width,{},.3 PACK_COUNTS(q));receipt(q,end());
        number(p.packed_w);number(p.packed_h);
        for(const auto& [ref,x,y]:p.placed){legacy<<std::quoted(ref)<<' ';number(x);number(y);}
#ifndef PACK_PRECISION_BASELINE
        require(q.at(names[1])==2,"empty/final shelf extents must count twice");
        require((q.count(names[0])?q.at(names[0]):0)==2*items.size(),"shelf coordinate multiplicity");
#endif
    }
    const std::vector<std::tuple<std::string,double,double,double,double>> controls{
        {"SW3",-.4,-.2,.4,.2},{"SW1",-.4,-.2,.4,.2},{"SW2",-.4,-.2,.4,.2}};
    for(double width:{-1.,0.,2.799999,2.8,5.599999,5.6,100.}) {
        QuantizationCounts q;begin();const auto g=grid_controls(controls,width,2,.3,.5 PACK_COUNTS(q));receipt(q,end());
        number(g.packed_w);number(g.packed_h);
        for(const auto& [ref,x,y]:g.offs){legacy<<std::quoted(ref)<<' ';number(x);number(y);}
        for(const auto& b:g.occ){number(b.x0);number(b.y0);number(b.x1);number(b.y1);}
#ifndef PACK_PRECISION_BASELINE
        require(q==QuantizationCounts{{names[2],1},{names[3],6}},"grid counts before clamp/placement");
#endif
    }
#ifndef PACK_PRECISION_BASELINE
    QuantizationCounts bad;begin();
    rejects<std::invalid_argument>([&]{grid_controls(controls,INFINITY,2,.3,.5,&bad);});
    receipt(bad,end());require(bad==QuantizationCounts{{names[2],1}},"invalid quotient attempt lost");
    QuantizationCounts finite_bad;begin();
    rejects<std::out_of_range>([&]{grid_controls(controls,std::numeric_limits<double>::max(),2,.3,.5,&finite_bad);});
    receipt(finite_bad,end());require(finite_bad==QuantizationCounts{{names[2],1}},"finite out-of-range quotient attempt lost");
#endif
    PackEdgesSpec spec{100,80,2,.750049,.5,3,2,.25,35,25,20,20};
    for(bool spilling:{false,true}) {
        std::vector<PackEdgeBlock> blocks;
        for(const auto* edge:{"N","E","S","W"}) {
            PackEdgeBlock b;b.name=edge;b.assigned_edge=edge;b.current_edge=edge;
            b.w=spilling?200:7.12345;b.h=spilling?200:4.12345;blocks.push_back(b);
        }
        QuantizationCounts q;begin();const auto p=pack_edges(blocks,{},spec PACK_COUNTS(q));receipt(q,end());
        for(const auto& pose:p.poses){legacy<<pose.name<<' '<<pose.edge<<' ';number(pose.x);number(pose.y);}
        for(const auto& spill:p.spilled)legacy<<std::quoted(spill)<<'\n';
#ifndef PACK_PRECISION_BASELINE
        require(spilling?q.empty():q==QuantizationCounts{{names[4],6}},"edge branch/spill multiplicity");
#endif
    }
    QuantizationCounts q;begin();const auto hf=hf_cap_pose(-0.,11.24955,.5,.125 PACK_COUNTS(q));receipt(q,end());
    number(hf.first);number(hf.second);require(std::signbit(hf.second),"HF y must remain unrounded");
}
void board_contracts(const std::filesystem::path& root) {
    for(const auto& project:{"carrier","devkit_mini"}) {
        auto fixture=placement_fixture::load(root,project);
        begin();const auto result=build_pcb_model(fixture.input);const auto entries=end();
        const auto totals=pcb_placement_accounting(result);receipt(totals.quantization_engagements,entries);
#ifndef PACK_PRECISION_BASELINE
        require(!entries.empty(),"real board must exercise instrumented pack boundaries");
        // Prove the independent observer rejects a missing or invented call.
        auto missing=totals.quantization_engagements;
        const auto name=entries.begin()->first;
        missing.erase(name);
        rejects<std::runtime_error>([&]{receipt(missing,entries);});
        auto invented=totals.quantization_engagements;
        ++invented[name];
        rejects<std::runtime_error>([&]{receipt(invented,entries);});
#endif
        auto plan=result.floorplan.plan;
        auto old_counts=totals.quantization_engagements;
#ifndef PACK_PRECISION_BASELINE
        plan.accounting.quantization_engagements=ledger_accounting_fixture::before_initial_receipt_fix(plan.accounting.quantization_engagements);
        old_counts=ledger_accounting_fixture::before_initial_receipt_fix(old_counts);
#endif
        plan.accounting.quantization_engagements=placement_precision_fixture::select(select(plan.accounting.quantization_engagements,false),false);
        legacy<<project<<'\n';node(pcb_model_json(result.model));node(floorplan_plan_json(plan));
        prior_counts(old_counts);
        begin();const auto again=pcb_placement_accounting(result);const auto replay=end();
        require(replay.empty()&&again.quantization_engagements==totals.quantization_engagements,"receipt replay manufactures work");
    }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
#ifndef PACK_PRECISION_BASELINE
    if(!recording.load(std::memory_order_relaxed))return;
    for(std::size_t i=0;i<rounds.size();++i)if(fn==reinterpret_cast<void*>(rounds[i])){++observed[indices[i]];return;}
    if(fn==reinterpret_cast<void*>(schgen::pack_control_fit_trunc))++observed[2];
#else
    (void)fn;
#endif
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
int main(int argc,char** argv) { try {
    require(argc==2,"expected repository root");
#ifndef PACK_PRECISION_BASELINE
    scalar_contracts();
#endif
    producer_contracts();
#ifndef PACK_PRECISION_BASELINE
    // Freeze primitive operands/results, not a historical whole-board search.
    // Real-board calls remain independently instrumented below; geometry and
    // current-input reproducibility belong to the placement/floorplan suites.
    const auto saved=placement_fixture::read(std::filesystem::path(argv[1])/"native/tests/data/pack_precision_legacy.txt");
    const auto boundary=saved.find("carrier\n");
    require(boundary!=std::string::npos,"historical primitive boundary missing");
    require(legacy.str()==saved.substr(0,boundary),"fixed primitive pack geometry changed");
#endif
    board_contracts(argv[1]);
#ifdef PACK_PRECISION_BASELINE
    std::cout<<legacy.str();
#else
    std::cout<<"Pack precision scalar, fixed producer geometry and independently observed board ownership contracts PASS\n";
#endif
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;} }
