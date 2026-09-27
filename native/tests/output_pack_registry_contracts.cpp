#include "schgen/output_precision.hpp"
#include "schgen/pack_precision.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/pack.hpp"
#include "schgen/quantize.hpp"
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
namespace {
using namespace schgen;
const std::array<std::string,25> names{{"floorplan_svg_extent_trunc",
    "floorplan_svg_grid_trunc",
    "floorplan_svg_coordinate_precision1dp",
    "pcb_project_integer_trunc",
    "pcb_project_class_precision4dp",
    "pcb_silk_position_precision3dp",
    "pcb_silk_stroke_precision3dp",
    "ratsnest_pad_precision3dp",
    "ratsnest_area_precision1dp",
    "ratsnest_dispersion_precision2dp",
    "ratsnest_budget_precision1dp",
    "escape_ground_precision4dp",
    "escape_scan_precision3dp",
    "escape_copper_precision4dp",
    "escape_coverage_precision4dp",
    "escape_region_precision4dp",
    "escape_port_precision4dp",
    "escape_width_precision4dp",
    "escape_corridor_precision4dp",
    "pack_shelf_pose_precision4dp",
    "pack_shelf_extent_precision4dp",
    "pack_control_fit_trunc",
    "pack_control_pose_precision4dp",
    "pack_edge_pose_precision4dp",
    "pack_hf_cap_pose_precision4dp"}};
const std::array<void*,25> addresses{{reinterpret_cast<void*>(&floorplan_svg_extent_trunc),
    reinterpret_cast<void*>(&floorplan_svg_grid_trunc),
    reinterpret_cast<void*>(&floorplan_svg_coordinate_precision1dp),
    reinterpret_cast<void*>(&pcb_project_integer_trunc),
    reinterpret_cast<void*>(&pcb_project_class_precision4dp),
    reinterpret_cast<void*>(&pcb_silk_position_precision3dp),
    reinterpret_cast<void*>(&pcb_silk_stroke_precision3dp),
    reinterpret_cast<void*>(&ratsnest_pad_precision3dp),
    reinterpret_cast<void*>(&ratsnest_area_precision1dp),
    reinterpret_cast<void*>(&ratsnest_dispersion_precision2dp),
    reinterpret_cast<void*>(&ratsnest_budget_precision1dp),
    reinterpret_cast<void*>(&escape_ground_precision4dp),
    reinterpret_cast<void*>(&escape_scan_precision3dp),
    reinterpret_cast<void*>(&escape_copper_precision4dp),
    reinterpret_cast<void*>(&escape_coverage_precision4dp),
    reinterpret_cast<void*>(&escape_region_precision4dp),
    reinterpret_cast<void*>(&escape_port_precision4dp),
    reinterpret_cast<void*>(&escape_width_precision4dp),
    reinterpret_cast<void*>(&escape_corridor_precision4dp),
    reinterpret_cast<void*>(&pack_shelf_pose_precision4dp),
    reinterpret_cast<void*>(&pack_shelf_extent_precision4dp),
    reinterpret_cast<void*>(&pack_control_fit_trunc),
    reinterpret_cast<void*>(&pack_control_pose_precision4dp),
    reinterpret_cast<void*>(&pack_edge_pose_precision4dp),
    reinterpret_cast<void*>(&pack_hf_cap_pose_precision4dp)}};
std::array<std::size_t,25> entries{};
bool observing=false;
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
std::uint64_t bits(double x){std::uint64_t result;std::memcpy(&result,&x,sizeof result);return result;}
void begin(){entries={};observing=true;}
QuantizationCounts end(){
    observing=false;QuantizationCounts result;
    for(std::size_t i=0;i<names.size();++i)if(entries[i])result[names[i]]=entries[i];
    return result;
}
void registry(){
    NativeQuantizations q;register_native_quantizations(q);
    const auto ds=q.declarations();require(ds.size()==122,"108 prior plus fourteen geometry");
    for(const auto& path:{"native/src/output_precision.cpp","native/src/pack_precision.cpp"}){
        for(const auto& sources:{native_board_policy_audit_sources(),board_pipeline_audit_sources()})
            require(std::count_if(sources.begin(),sources.end(),[&](const auto& source){return source.path==path;})==1,
                "scalar source appears once in each manifest");
    }
    for(std::size_t i=0;i<names.size();++i){
        const auto d=std::find_if(ds.begin(),ds.end(),[&](const auto& row){return row.name==names[i];});
        const std::string source=i<19?"output_precision.cpp":"pack_precision.cpp";
        const std::size_t arity=i==2?3:1;
        require(d!=ds.end()&&d->symbol=="native/src/"+source+"::schgen::"+names[i]
            &&d->arity==arity&&!d->basis.empty()&&!d->value.empty(),"exact scalar identity and arity");
        std::int64_t invocation=0;
        for(double x:{-0.,0.,.00005,-.00005,1.23455,-1.23455,39.9}){
            std::vector<double> args{x};double expected;
            if(i==2){args={x,46.,6.};expected=svg_map(x,46.,6.);}
            else if(i<2||i==21)expected=static_cast<double>(static_cast<int>(x));
            else if(i==3)expected=std::trunc(x);
            else{
                const int digits=i==8||i==10?1:i==9?2:i==5||i==6||i==7||i==12?3:4;
                expected=py_round(x,digits);
            }
            const auto before=q.engagements();begin();
            const double actual=q.invoke(names[i],args);const auto observed=end();
            require(bits(actual)==bits(expected)&&observed==QuantizationCounts{{names[i],1}},
                "real scalar callback once with exact result bits");
            auto wanted=before;wanted[names[i]]=AuditInteger(++invocation);
            require(q.engagements()==wanted,"only invoked registry count changes");
        }
        for(const auto& args:std::vector<std::vector<double>>{{},std::vector<double>(arity+1,1.)}){
            const auto before=q.engagements();bool rejected=false;begin();
            try{q.invoke(names[i],args);}catch(const std::invalid_argument&){rejected=true;}
            require(end().empty()&&rejected&&q.engagements()==before,"arity rejection precedes scalar entry and counts");
        }
    }
    for(const auto* unknown:{"escape_unknown_precision","pack_shelf_pose_precision4dp_typo","floorplan_svg_coordinate_precision1dp_typo"}){
        const auto before=q.engagements();bool rejected=false;begin();
        try{q.invoke(unknown,{1.});}catch(const std::logic_error&){rejected=true;}
        require(end().empty()&&rejected&&q.engagements()==before,"unknown name remains rejected without work");
    }
}
void adapters(){
    const QuantizationCounts prior{{"fixed_part_grid",3},{"legalize_pose_quantum",5},
        {"escape_unknown_precision",7},{"pack_shelf_pose_precision4dp_typo",11},
        {"floorplan_svg_coordinate_precision1dp_typo",13},{"placement_unknown_precision",17}};
    auto mixed=prior;for(const auto& name:names)mixed[name]=19;
    require(placement_precision_fixture::select(mixed,false)==prior,"placement historical exact additions only");
    require(stage_precision_fixture::select(mixed,false)==prior,"stage historical exact additions only");
    require(legalize_precision_fixture::select(mixed,false)==prior,"legalizer historical exact additions only");
    require(occupancy_precision_fixture::select(mixed,false)==prior,"occupancy historical exact additions only");
    require(floorplan_precision_fixture::select(mixed,false)==prior,"floorplan historical exact additions only");
    std::ostringstream expected,actual;
    connector_fixture::counts(expected,"TEST",prior);connector_fixture::counts(actual,"TEST",mixed);
    require(actual.str()==expected.str(),"connector historical unknown-name preservation");
    QuantizationCounts output,pack;
    for(std::size_t i=0;i<names.size();++i)(i<19?output:pack)[names[i]]=19;
    require(output_precision_fixture::select(mixed)==output&&pack_precision_fixture::select(mixed)==pack,
        "independent exact positive families");
    require(placement_precision_fixture::select(output_precision_fixture::select(mixed,false),false)==prior,
        "output immutable64 baseline projection");
    require(placement_precision_fixture::select(pack_precision_fixture::select(mixed,false),false)==prior,
        "pack immutable64 baseline projection");
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) noexcept {
    if(!observing)return;
    for(std::size_t i=0;i<addresses.size();++i)if(fn==addresses[i]){++entries[i];return;}
}
extern "C" void __cyg_profile_func_exit(void*,void*) noexcept {}
int main(){try{
    registry();adapters();std::cout<<"output19 + pack6 integrated registry and exact adapters PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
