#include "schgen/placement_precision.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/quantize.hpp"
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include <array>
#include <cstring>
#include <iostream>

namespace {
using namespace schgen;
using placement_precision_fixture::names;
std::array<std::size_t,19> entries{};
bool observing=false;
const std::array<double(*)(double,QuantizationCounts*),18> operations{{
    placement_turn_dimension_precision4dp,
    placement_turn_offset_precision4dp,
    placement_connector_pose_precision4dp,
    placement_behind_pose_precision4dp,
    placement_pack_extent_precision4dp,
    placement_edge_mirror_pose_precision4dp,
    placement_variant_dimension_precision4dp,
    placement_member_box_precision4dp,
    placement_member_pose_precision4dp,
    placement_bottom_pose_precision4dp,
    placement_lift_extent_precision4dp,
    placement_shape_key_precision4dp,
    placement_l4_pose_precision4dp,
    placement_edge_seat_precision4dp,
    placement_foreign_pad_precision3dp,
    placement_evict_trial_precision4dp,
    placement_emission_pose_precision4dp,
    placement_fiducial_precision4dp}};
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t n;std::memcpy(&n,&x,sizeof n);return n;}
void begin(){entries={};observing=true;}
QuantizationCounts end(){
    observing=false;QuantizationCounts q;
    for(std::size_t i=0;i<names.size();++i)if(entries[i])q[names[i]]=entries[i];
    return q;
}
void declarations(){
    NativeQuantizations q;register_native_quantizations(q);
    const auto ds=q.declarations();
    require(ds.size()==83,"64 prior plus nineteen placement declarations");
    for(const auto& name:{"placement_unknown_future_precision","placement_turn_offset_precision4dp_typo"}){
        const auto before=q.engagements();bool rejected=false;begin();
        try{q.invoke(name,{1.});}catch(const std::logic_error&){rejected=true;}
        require(end().empty()&&rejected&&q.engagements()==before,"unknown name cannot enter scalar or manufacture counts");
    }
    const auto manifest=native_board_policy_audit_sources();
    require(std::count_if(manifest.begin(),manifest.end(),[](const auto& s){
        return s.path=="native/src/placement_precision.cpp";})==1,"scalar manifest source exactly once");
    const auto minimum=board_pipeline_audit_sources();
    require(std::count_if(minimum.begin(),minimum.end(),[](const auto& s){
        return s.path=="native/src/placement_precision.cpp";})==1,"minimum manifest source exactly once");
    for(std::size_t i=0;i<names.size();++i){
        const auto d=std::find_if(ds.begin(),ds.end(),[&](const auto& v){return v.name==names[i];});
        const std::string value=i==18?"int(value)":i==14?"round(value, 3)":"round(value, 4)";
        require(d!=ds.end()&&d->arity==1&&d->symbol=="native/src/placement_precision.cpp::schgen::"+names[i]
            &&d->value==value&&!d->basis.empty()&&d->proof_class=="pre-proof","exact scalar metadata");
        std::int64_t invocation=0;
        for(double x:{-0.,0.,.00005,-.00005,1.23455,-1.23455,39.9}){
            const double expected=i==18?static_cast<double>(static_cast<int>(x)):py_round(x,i==14?3:4);
            const auto before=q.engagements();
            begin();const double actual=q.invoke(names[i],{x});const auto observed=end();
            require(bits(actual)==bits(expected)&&observed==QuantizationCounts{{names[i],1}},
                "registry executes the named production scalar once, preserving bits");
            auto wanted=before;wanted[names[i]]=AuditInteger(++invocation);
            require(q.engagements()==wanted,"only the invoked registry engagement changes");
        }
        for(const auto& args:std::vector<std::vector<double>>{{},{1.,2.}}){
            const auto before=q.engagements();bool rejected=false;begin();
            try{q.invoke(names[i],args);}catch(const std::invalid_argument&){rejected=true;}
            require(end().empty()&&rejected&&q.engagements()==before,"arity rejected before scalar entry or count");
        }
    }
}
void adapters(){
    const QuantizationCounts prior{{"fixed_part_grid",17},{"legalize_pose_quantum",29},
        {"placement_unknown_future_precision",31},{"placement_turn_offset_precision4dp_typo",37}};
    auto mixed=prior;for(const auto& name:names)mixed[name]=43;
    require(placement_precision_fixture::select(mixed,false)==prior,"placement removes only its exact names");
    require(stage_precision_fixture::select(mixed,false)==prior,"stage keeps unknown and historical names");
    require(legalize_precision_fixture::select(mixed,false)==prior,"legalizer keeps unknown and historical names");
    require(occupancy_precision_fixture::select(mixed,false)==prior,"occupancy keeps unknown and historical names");
    require(floorplan_precision_fixture::select(mixed,false)==prior,"floorplan keeps unknown and historical names");
    std::ostringstream expected,actual;
    connector_fixture::counts(expected,"TEST",prior);connector_fixture::counts(actual,"TEST",mixed);
    require(actual.str()==expected.str(),"connector keeps unknown and historical names");
    mixed[stage_precision_fixture::names[0]]=47;
    require(stage_precision_fixture::select(mixed)==QuantizationCounts{{stage_precision_fixture::names[0],47}},
        "stage positive-family selection stays exact");
    mixed[legalize_precision_fixture::names[0]]=53;
    require(legalize_precision_fixture::select(mixed)==QuantizationCounts{{legalize_precision_fixture::names[0],53}},
        "legalizer positive-family selection stays exact");
}
} // namespace
extern "C" void __cyg_profile_func_enter(void* fn,void*) noexcept {
    if(!observing)return;
    for(std::size_t i=0;i<operations.size();++i)
        if(fn==reinterpret_cast<void*>(operations[i])){++entries[i];return;}
    if(fn==reinterpret_cast<void*>(schgen::placement_l4_distance_trunc))++entries[18];
}
extern "C" void __cyg_profile_func_exit(void*,void*) noexcept {}
int main(){
    try{declarations();adapters();std::cout<<"placement registry and exact-family adapters PASS\n";return 0;}
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
