// Instrument ONLY precision_ops.cpp with -finstrument-functions -fno-inline.
// The independent observer below is never production accounting.
#include "floorplan_precision_fixture.hpp"
#include "floorplan_internal.hpp"
#include "schgen/precision_ops.hpp"
#include "schgen/native_audit_state.hpp"
#include <atomic>
#include <cmath>
#include <cstring>
#include <iostream>
#include <thread>

namespace {
using namespace schgen;
using namespace floorplan_precision_fixture;
using schgen::floorplan_detail::Engine;
using schgen::floorplan_detail::jvalue;
using Op=double(*)(double);
const std::array<Op,6> operations{{floorplan_candidate_area_precision1dp,
    floorplan_seed_aspect_precision4dp,floorplan_ledger_value_precision1dp,
    floorplan_ledger_margin_precision3dp,floorplan_ledger_dimension_precision4dp,
    floorplan_ledger_display_precision4dp}};
const std::array<int,6> digits{{1,4,1,3,4,4}};
std::array<std::atomic<std::size_t>,6> entries{};
std::atomic<bool> observing{false};
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
void begin(){for(auto& value:entries)value=0;observing=true;}
QuantizationCounts end(){observing=false;QuantizationCounts out;for(std::size_t i=0;i<names.size();++i)if(entries[i])out[names[i]]=entries[i];return out;}
std::uint64_t bits(double x){std::uint64_t v;std::memcpy(&v,&x,sizeof(v));return v;}
template<class F> void rejects(F f,const std::string& why){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}require(rejected,why);}
QuantizationCounts decoded(const JsonNode& row){QuantizationCounts out;for(const auto& [key,value]:row.object_value)out[key]=static_cast<std::size_t>(value.number_value);return out;}
void show(const QuantizationCounts& values){std::cout<<'{';bool first=true;for(const auto& [key,count]:values){if(!first)std::cout<<',';first=false;std::cout<<std::quoted(key)<<':'<<count;}std::cout<<'}';}
void scalars(){
    for(std::size_t op=0;op<operations.size();++op){
        const auto compare=[&](double value){const double expected=py_round(value,digits[op]),actual=operations[op](value);require(bits(actual)==bits(expected),"original rounding bits: "+names[op]);};
        const double scale=std::pow(10.,digits[op]);
        for(int k=-2048;k<=2048;++k){const double tie=(k+.5)/scale;for(double value:{tie,std::nextafter(tie,-INFINITY),std::nextafter(tie,INFINITY)})compare(value);}
        for(double value:{0.,-0.,double(INFINITY),double(-INFINITY),double(NAN),std::numeric_limits<double>::max(),std::numeric_limits<double>::denorm_min()})compare(value);
    }
    NativeQuantizations registry;register_native_quantizations(registry);
    require(registry.declarations().size()==40,"34 prior operations plus six occupancy operations");
    const auto declarations=registry.declarations();
    for(std::size_t i=0;i<names.size();++i){
        const auto found=std::find_if(declarations.begin(),declarations.end(),[&](const auto& d){return d.name==names[i];});
        require(found!=declarations.end()&&found->arity==1&&found->symbol=="native/src/precision_ops.cpp::schgen::"+names[i],"real scalar identity and arity");
        begin();const double result=registry.invoke(names[i],{1.23455});const auto actual=end();
        require(actual==QuantizationCounts{{names[i],1}}&&bits(result)==bits(py_round(1.23455,digits[i])),"registry executes exactly one actual function");
        begin();rejects([&]{registry.invoke(names[i],{});},"arity error");require(end().empty(),"arity failure executes no primitive");
    }
}
FloorplanInput small_input(){FloorplanInput input;input.som.w=input.som.h=20;return input;}
std::string old_shown(double value){auto text=floorplan_detail::number(py_round(value,4),4);while(!text.empty()&&text.back()=='0')text.pop_back();if(!text.empty()&&text.back()=='.')text.pop_back();return text.empty()||text=="-0"?"0":text;}
void ledger_boundaries(){
    const auto input=small_input();Engine engine(input);
    begin();engine.ledger_open();const auto opened=end();
    const auto policy_rows=floorplan_ledger_policy();
    const auto assumptions=static_cast<std::size_t>(std::count_if(policy_rows.begin(),policy_rows.end(),[](const auto& d){return d.kind=="ASSUME";}));
    require(policy_rows.size()==83&&opened==QuantizationCounts{{names[5],assumptions}}&&select(engine.plan.accounting.quantization_engagements)==opened,"83 unchanged policy rows; each real numeric assumption displayed once");
    for(double value:{-0.,-.00001,-.00005,.00005,.00015,1.23445,1.23455,-1.23455,10.,1e-12}){
        begin();const auto before=engine.plan.accounting.quantization_engagements.at(names[5]);
        engine.calc("overmold_side_gap",jvalue(value),{{"plug_width",jvalue(value)},{"copper_half_width",jvalue(value)}});
        require(end()==QuantizationCounts{{names[5],3}}&&engine.plan.accounting.quantization_engagements.at(names[5])==before+3,"value and two numeric inputs are actual separate calls");
        const auto& text=engine.plan.accounting.decisions.back().text;
        const auto shown=old_shown(value);
        require(text.find("= "+shown)!=text.npos&&text.find("plug_width="+shown+" copper_half_width="+shown)!=text.npos,"legacy four-decimal format bytes including negative zero");
    }
    begin();engine.calc("overmold_side_gap",jvalue(true),{{"plug_width",jvalue("string")},{"copper_half_width",jvalue(false)}});
    require(end().empty()&&engine.plan.accounting.decisions.back().text.find("plug_width=string copper_half_width=no")!=std::string::npos,"non-numeric scalars never fabricate quantization counts");
    const auto rows=engine.plan.accounting.decisions.size();
    begin();rejects([&]{engine.calc("missing",jvalue(0.),{});},"unknown calculation rejects");require(end().empty(),"unknown declaration does no precision work");
    begin();rejects([&]{engine.calc("overmold_side_gap",jvalue(0.),{},"sizing.pass");},"wrong step rejects");require(end().empty(),"wrong step rejects before numeric work");
    begin();rejects([&]{engine.calc("overmold_side_gap",jvalue(0.),{{"wrong",jvalue(1.)}});},"wrong key rejects");require(end()==QuantizationCounts{{names[5],1}},"actually formatted rejected input counted, unexecuted result not counted");
    begin();rejects([&]{engine.calc("overmold_side_gap",jvalue(0.),{{"plug_width",JsonNode{}}});},"non-scalar input rejects");require(end().empty(),"non-scalar error does not fake numeric work");
    require(engine.plan.accounting.decisions.size()==rows,"failed calculation cannot append a successful decision");
    const auto saved=engine.plan.accounting.quantization_engagements;
    begin();const auto first=render_floorplan_ledger(engine.plan);const auto second=render_floorplan_ledger(engine.plan);const auto json=floorplan_plan_json(engine.plan);(void)json;
    require(end().empty()&&first==second&&engine.plan.accounting.quantization_engagements==saved,"cached render and serialization are pure observers");
    Engine overflow(input);overflow.plan.accounting.quantization_engagements[names[5]]=std::numeric_limits<std::size_t>::max();
    begin();rejects([&]{overflow.calc("overmold_side_gap",jvalue(1.),{{"plug_width",jvalue(1.)},{"copper_half_width",jvalue(1.)}});},"counter overflow rejects");require(end().empty()&&overflow.plan.accounting.decisions.empty(),"overflow happens before unbooked scalar or decision");
    Engine side(input);side.side_offers["fixed"]={"top","top",0,std::nullopt,std::nullopt};side.side_offers["choice"]={"bottom","top",0,1.23455,1.11115};
    begin();side.ledger_sides();const auto calls=end();
    require(calls==QuantizationCounts{{names[2],2},{names[3],1},{names[5],9}}&&select(side.plan.accounting.quantization_engagements)==calls,"actual side-choice and fixed-side paths retain separate value/margin/display calls");
    std::array<QuantizationCounts,2> independent;begin();std::array<std::thread,2> threads;
    for(std::size_t k=0;k<threads.size();++k)threads[k]=std::thread([&,k]{Engine e(input);for(int n=0;n<20;++n)e.calc("overmold_side_gap",jvalue(1.),{{"plug_width",jvalue(1.)},{"copper_half_width",jvalue(1.)}});independent[k]=e.plan.accounting.quantization_engagements;});
    for(auto& thread:threads)thread.join();
    require(end()==QuantizationCounts{{names[5],120}}&&independent[0]==QuantizationCounts{{names[5],60}}&&independent[1]==independent[0],"parallel invocations own separate counters with no production globals");
}
void inherited_accounting(){
    auto input=small_input();FloorplanSpec spec;spec.outline=std::make_pair(100.,80.);input.spec=spec;
    begin();const auto first=build_floorplan(input);const auto work=end();
    require(select(first.accounting.quantization_engagements)==work,"fresh fixed invocation owns all actual calls");
    for(std::size_t i=0;i<names.size();++i)input.accounting.quantization_engagements[names[i]]=7+i;
    input.accounting.quantization_engagements["fixed_part_grid"]=19;
    const auto inherited=input.accounting.quantization_engagements;
    begin();const auto second=build_floorplan(input);const auto repeated=end();
    auto expected=first.accounting.quantization_engagements;checked_quantization_merge(expected,inherited);
    require(repeated==work&&second.accounting.quantization_engagements==expected&&input.accounting.quantization_engagements==inherited,
            "existing input accounting imported exactly once, including same-name counts across conservative restore");
    require(!second.punch_free&&std::count(second.accounting.fallback_events.begin(),second.accounting.fallback_events.end(),"punch_free_plan_rejected")==1,
            "equal fixed free trial restores conservative plan without discarding executed precision work");
}
void boards(const std::filesystem::path& root,const std::filesystem::path& data,bool capture){
    using placement_fixture::field;
    JsonNode additions;if(!capture)additions=parse_json_file((data/"additive_counts.json").string());
    std::ostringstream baseline,fixed;policy(baseline);policy(fixed);
    bool first=true;if(capture)std::cout<<"{\n";
    for(int variant=0;variant<4;++variant){
        const auto project=variant==1?"carrier":"devkit_mini";const auto name=std::string(project)+(variant==2?"_single":variant==3?"_fixed":"");
        auto fixture=placement_fixture::load(root,project);fixture.input.two_side=variant!=2;
        if(variant==3){if(!fixture.input.floorplan.spec)fixture.input.floorplan.spec=FloorplanSpec{};fixture.input.floorplan.spec->outline=std::make_pair(100.,100.);}
        begin();const auto result=build_pcb_model(fixture.input);const auto observed=end();const auto total=pcb_placement_accounting(result);
        require(select(result.floorplan.plan.accounting.quantization_engagements)==observed&&select(total.quantization_engagements)==observed,"all new actual work owned exactly by floorplan invocation "+name);
        require(select(result.zone_accounting.quantization_engagements).empty()&&select(result.placement_accounting.quantization_engagements).empty(),"no downstream double import "+name);
        require(observed.at(names[0])>0&&observed.at(names[2])>0&&observed.at(names[4])==2&&observed.at(names[5])>0,"real build and ledger primitives engaged");
        require(variant==3?!observed.count(names[1]):observed.at(names[1])==1,"only auto sizing executes the aspect operation");
        if(!capture)require(observed==decoded(field(additions,name)),"explicit independent additive fixture "+name);
        if(capture){if(!first)std::cout<<",\n";first=false;std::cout<<std::quoted(name)<<':';show(observed);}
        auto& output=variant==3?fixed:baseline;plan(output,name,result.floorplan.plan);
        counts(output,"ZONE",result.zone_accounting.quantization_engagements);counts(output,"PLACEMENT",result.placement_accounting.quantization_engagements);counts(output,"AGGREGATE",total.quantization_engagements);
        NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
        begin();require(inbox.merge_once("pcb/placement",total)&&!inbox.merge_once("pcb/placement",total),"one production receipt with replay rejection");require(end().empty(),"import performs no math");
        for(const auto& op:names){const auto entry=observed.find(op);require(q.engagements().at(op)==AuditInteger::decimal(std::to_string(entry==observed.end()?0:entry->second)),"exact imported new count");}
        const auto saved=total.quantization_engagements;const auto saved_q=q.engagements();begin();const auto a=render_floorplan_ledger(result.floorplan.plan);const auto b=render_floorplan_ledger(result.floorplan.plan);
        require(end().empty()&&a==b&&pcb_placement_accounting(result).quantization_engagements==saved&&q.engagements()==saved_q,"post-import render cannot mutate solver census");
    }
    if(capture)std::cout<<"\n}\n";
    require(baseline.str()==placement_fixture::read(data/"legacy_output.txt"),"all three legacy plans, ledger bytes, 83 policy rows and prior 28 ownership counts byteexact");
    require(fixed.str()==placement_fixture::read(data/"fixed_legacy.txt"),"independent legacy fixed-outline branch output/counts byteexact");
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){if(!observing.load(std::memory_order_relaxed))return;for(std::size_t i=0;i<operations.size();++i)if(fn==reinterpret_cast<void*>(operations[i])){++entries[i];break;}}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    if(argc<2||argc>4||(argc==4&&std::string(argv[3])!="--capture-additive"))throw std::runtime_error("repo [fixture-directory [--capture-additive]]");
    const auto root=std::filesystem::path(argv[1]);const auto data=argc>=3?std::filesystem::path(argv[2]):root/"native/tests/data/floorplan_precision";
    scalars();ledger_boundaries();inherited_accounting();boards(root,data,argc==4);std::cerr<<checks<<" floorplan precision contracts passed\n";return 0;
}catch(const std::exception& e){std::cerr<<"Floorplan precision FAILED: "<<e.what()<<'\n';return 1;}}
