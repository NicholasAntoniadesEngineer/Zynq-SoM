#include "schgen/legalize_precision.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/quantize.hpp"
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include <array>
#include <cstring>
#include <iostream>

namespace {
using namespace schgen;
using legalize_precision_fixture::names;
std::array<std::size_t,7> entries{};
std::size_t pose_entries=0;
bool observing=false;
const std::array<double(*)(double,QuantizationCounts*),7> operations{{
    legalize_position_precision4dp,legalize_centroid_precision4dp,
    legalize_bbox_precision4dp,legalize_anchor_precision4dp,
    legalize_bound_precision4dp,legalize_margin_precision4dp,
    legalize_trial_pose_precision4dp}};
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t n;std::memcpy(&n,&x,sizeof n);return n;}
void begin(){entries={};pose_entries=0;observing=true;}
QuantizationCounts end(){observing=false;QuantizationCounts q;
    for(std::size_t i=0;i<names.size();++i)if(entries[i])q[names[i]]=entries[i];return q;}
void declarations(){
    NativeQuantizations q;register_native_quantizations(q);
    const auto ds=q.declarations();require(ds.size()==64,"40 prior plus seven legalizer and seventeen stage declarations");
    const auto manifest=native_board_policy_audit_sources();
    require(std::count_if(manifest.begin(),manifest.end(),[](const auto& s){
        return s.path=="native/src/legalize_precision.cpp";})==1,"exact scalar source is in production manifest once");
    for(std::size_t i=0;i<names.size();++i){
        const auto d=std::find_if(ds.begin(),ds.end(),[&](const auto& v){return v.name==names[i];});
        require(d!=ds.end()&&d->symbol=="native/src/legalize_precision.cpp::schgen::"+names[i]
            &&d->arity==1&&d->value=="round(value, 4)"&&!d->basis.empty()
            &&d->proof_class==(i==6?"re-validated":"pre-proof"),"exact scalar registration, arity and proof metadata");
        std::int64_t invocation=0;
        for(const double x:{-0.0,.00005,-.00005,1.23455,-1.23455}){
            const auto expected=py_round(x,4);const auto before=q.engagements();
            begin();const auto actual=q.invoke(names[i],{x});const auto observed=end();
            require(bits(actual)==bits(expected)&&observed==QuantizationCounts{{names[i],1}}&&pose_entries==0,
                "registry executes only the actual declared scalar once");
            auto wanted=before;wanted[names[i]]=AuditInteger(++invocation);
            require(q.engagements()==wanted,"one invocation changes only its registry counter");
        }
        for(const auto& args:std::vector<std::vector<double>>{{},{1.,2.}}){
            const auto before=q.engagements();bool rejected=false;begin();
            try{q.invoke(names[i],args);}catch(const std::invalid_argument&){rejected=true;}
            require(end().empty()&&pose_entries==0&&rejected&&q.engagements()==before,"bad arity cannot execute or increment");
        }
    }
    for(const auto& d:ds)require(d.symbol!="native/src/legalize.cpp::schgen::predicted_centroid"
        &&d.symbol!="native/src/legalize.cpp::schgen::predicted_bbox"
        &&d.symbol!="native/src/legalize.cpp::schgen::evaluate_terms","no broad legalizer registration");
}
void adapters(){
    const QuantizationCounts prior{{"legalize_pose_quantum",2250},{"legalize_unknown_future_precision",19},{"fixed_part_grid",17}};
    auto input=prior;for(const auto& n:names)input[n]=23;
    require(legalize_precision_fixture::select(input,false)==prior,"only seven exact additions leave legacy comparison");
    require(occupancy_precision_fixture::select(input,false)==prior,"occupancy historical adapter retains all prior and unknown names");
    require(floorplan_precision_fixture::select(input,false)==prior,"floorplan historical adapter retains all prior and unknown names");
    input[occupancy_precision_fixture::names[0]]=31;
    require(occupancy_precision_fixture::select(input)==QuantizationCounts{{occupancy_precision_fixture::names[0],31}},
        "occupancy positive-family selection remains exact");
    std::ostringstream expected,actual;connector_fixture::counts(expected,"TEST",prior);connector_fixture::counts(actual,"TEST",input);
    require(actual.str()==expected.str(),"connector historical adapter preserves all prior and unknown names");
}
void board_receipt(const std::filesystem::path& root){
    auto fixture=placement_fixture::load(root,"carrier");
    begin();const auto result=build_pcb_model(fixture.input);const auto observed=end();
    const auto total=pcb_placement_accounting(result);
    require(legalize_precision_fixture::select(total.quantization_engagements)==observed,"actual aggregate matches independent scalar entries");
    require(legalize_precision_fixture::select(result.floorplan.plan.accounting.quantization_engagements)==observed,
        "floorplan owns all executed legalizer operations");
    require(total.quantization_engagements.at("legalize_pose_quantum")==pose_entries&&pose_entries==2250,
        "legacy carrier pose quantum remains independently pinned");
    for(const auto& n:names)require(observed.count(n)&&observed.at(n)>0,"carrier exercises each registered legalizer family");
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
    begin();require(inbox.merge_once("pcb/placement",total)&&!inbox.merge_once("pcb/placement",total),"receipt imported once, replay rejected");
    require(end().empty()&&pose_entries==0,"registry import cannot replay scalar math");
    const auto imported=q.engagements();
    for(const auto& n:names)require(imported.at(n)==AuditInteger::decimal(std::to_string(observed.at(n))),"exact imported scalar engagement");
    const auto saved=total.quantization_engagements;begin();
    const auto a=render_floorplan_ledger(result.floorplan.plan),b=render_floorplan_ledger(result.floorplan.plan);
    require(end().empty()&&pose_entries==0&&a==b&&q.engagements()==imported
        &&pcb_placement_accounting(result).quantization_engagements==saved,"cached replay preserves registry and producer counts");
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){
    if(!observing)return;
    for(std::size_t i=0;i<operations.size();++i)if(fn==reinterpret_cast<void*>(operations[i]))++entries[i];
    if(fn==reinterpret_cast<void*>(&schgen::legalize_pose_quantum))++pose_entries;
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{
    require(argc==2,"repo root required");declarations();adapters();board_receipt(argv[1]);
    std::cout<<"Legalizer registry, exact-family adapters and independent carrier receipt PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
