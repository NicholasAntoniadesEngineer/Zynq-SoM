#include "pcb_placement_fixture.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/stage_precision.hpp"
#include "schgen/placement_precision.hpp"
#include "schgen/precision_ops.hpp"
#include "schgen/pack_geometry_precision.hpp"
#include "schgen/pack_precision.hpp"
#include "schgen/output_precision.hpp"
#include <array>
#include <iostream>
#include <limits>

namespace {
using namespace schgen;
struct Injected : std::runtime_error { Injected():std::runtime_error("injected checkpoint failure"){} };
struct Op {const char* name;void* address;};
const std::array<Op,8> ops{{
 {"stage_root_pose_precision4dp",reinterpret_cast<void*>(&stage_root_pose_precision4dp)},
 {"stage_hot_extent_precision4dp",reinterpret_cast<void*>(&stage_hot_extent_precision4dp)},
 {"placement_bottom_pose_precision4dp",reinterpret_cast<void*>(&placement_bottom_pose_precision4dp)},
 {"placement_emission_pose_precision4dp",reinterpret_cast<void*>(&placement_emission_pose_precision4dp)},
 {"pack_pair_gap_precision4dp",reinterpret_cast<void*>(&pack_pair_gap_precision4dp)},
 {"pack_shelf_pose_precision4dp",reinterpret_cast<void*>(&pack_shelf_pose_precision4dp)},
 {"floorplan_ledger_value_precision1dp",reinterpret_cast<void*>(&floorplan_ledger_value_precision1dp)},
 {"escape_copper_precision4dp",reinterpret_cast<void*>(&escape_copper_precision4dp)}
}};
thread_local bool observing=false;
thread_local std::array<std::size_t,8> entries{};
void begin(){entries={};observing=true;}
void require(bool b,const std::string& m){if(!b)throw std::runtime_error(m);}
void verify(const ExecutionAccounting& receipt,const std::string& label){
    observing=false;
    for(std::size_t i=0;i<ops.size();++i){auto p=receipt.quantization_engagements.find(ops[i].name);
        const auto n=p==receipt.quantization_engagements.end()?0:p->second;
        require(n==entries[i],label+": entry mismatch "+ops[i].name+" receipt="+std::to_string(n)+" real="+std::to_string(entries[i]));}
}
void inbox(const ExecutionAccounting& receipt){
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);
    NativeAccountingInbox in(q,f);
    require(in.merge_once("pcb/placement",receipt),"first import");
    const auto before=q.engagements();
    require(!in.merge_once("pcb/placement",receipt)&&before==q.engagements(),"duplicate import rejected without recount");
}
void reject_receipt_mutations(const ExecutionAccounting& receipt){
    for(std::size_t i=0;i<ops.size();++i)if(entries[i]){
        auto dropped=receipt;dropped.quantization_engagements.erase(ops[i].name);
        bool rejected=false;try{verify(dropped,"dropped-prefix mutation");}catch(const std::runtime_error&){rejected=true;}
        require(rejected,"independent observer rejects a dropped real prefix");
        auto doubled=receipt;checked_quantization_add(doubled.quantization_engagements,ops[i].name,entries[i]);
        rejected=false;try{verify(doubled,"double-count mutation");}catch(const std::runtime_error&){rejected=true;}
        require(rejected,"independent observer rejects duplicate real work");return;
    }
    require(false,"receipt mutation needs actual observed work");
}
void checkpoints(const std::filesystem::path& root,bool two_side){
    for(const std::string stop:{"zone_pack","l4_pull","escape_copper"}){
        auto fixture=placement_fixture::load(root,"devkit_mini");fixture.input.two_side=two_side;
        auto observer=std::make_shared<PcbPlacementExperiment>();
        // Avoid diagnostic estimator work in the plan_lattice snapshot: attach
        // only for zone_pack then disable it, or observe later placement stages
        // via a separately owned explicit solve below.
        ExecutionFailureReceipt failure;bool injected=false;
        if(stop=="zone_pack"){
            observer->checkpoint=[&](const PcbPlacementObservation& p){if(p.stage==stop)throw Injected();};
            fixture.input.experiment=observer;
            begin();try{(void)build_pcb_model(fixture.input,&failure);}catch(const Injected&){injected=true;}
        }else{
            const auto zones=build_pcb_zone_geometry(fixture.input);
            auto planning=fixture.input;planning.two_side=true;
            const auto planning_zones=two_side?zones:build_pcb_zone_geometry(planning);
            const auto stage=generate_floorplan(prepare_pcb_floorplan(planning,planning_zones));
            observer->checkpoint=[&](const PcbPlacementObservation& p){if(p.stage==stop)throw Injected();};
            fixture.input.experiment=observer;
            begin();try{(void)place_pcb_model_accounted(fixture.input,zones,stage,
                two_side?PcbZoneAccountingOwnership::IncludedInFloorplan:PcbZoneAccountingOwnership::SeparateFromFloorplan,&failure);
            }catch(const Injected&){injected=true;}
        }
        observing=false;require(injected&&failure.captured,"original injected exception and receipt "+stop);
        require(!failure.accounting.quantization_engagements.empty(),"nonempty real prefix "+stop);
        verify(failure.accounting,stop);inbox(failure.accounting);
    }
}
void floorplan_failure(const std::filesystem::path& root,bool two_side){
    auto fixture=placement_fixture::load(root,"devkit_mini");fixture.input.two_side=two_side;
    auto observer=std::make_shared<FloorplanExperiment>();
    observer->attempt_completed=[](const FloorplanAttemptObservation&){throw Injected();};
    fixture.input.floorplan.experiment=observer;
    ExecutionFailureReceipt failure;bool injected=false;
    begin();try{(void)build_pcb_model(fixture.input,&failure);}catch(const Injected&){injected=true;}
    observing=false;require(injected&&failure.captured,"floorplan propagated injected failure");
    verify(failure.accounting,"floorplan seeded zones "+std::to_string(two_side));inbox(failure.accounting);
    reject_receipt_mutations(failure.accounting);
}
void success(const std::filesystem::path& root,bool two_side){
    auto fixture=placement_fixture::load(root,"devkit_mini");fixture.input.two_side=two_side;
    const auto original=build_pcb_model(fixture.input);
    ExecutionFailureReceipt failure;
    begin();const auto result=build_pcb_model(fixture.input,&failure);observing=false;
    require(!failure.captured&&failure.accounting.quantization_engagements.empty()&&failure.accounting.fallback_events.empty(),"success never publishes failure receipt");
    const auto total=pcb_placement_accounting(result),before=pcb_placement_accounting(original);
    verify(total,"success");
    require(total.quantization_engagements==before.quantization_engagements&&total.fallback_events==before.fallback_events,"successful receipt unchanged");
    const auto policy=pcb_emit_policy(fixture.input.floorplan.project);
    require(render_pcb(result.model,policy).pcb==render_pcb(original.model,policy).pcb,"successful full PCB bytes unchanged");
    require(render_floorplan_ledger(result.floorplan.plan)==render_floorplan_ledger(original.floorplan.plan),"successful ledger bytes unchanged");inbox(total);
    auto observer=std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint=[](const PcbPlacementObservation& p){if(p.stage=="escape_copper")throw Injected();};
    fixture.input.experiment=observer;
    ExecutionFailureReceipt late;bool injected=false;
    begin();try{(void)build_pcb_model(fixture.input,&late);}catch(const Injected&){injected=true;}
    observing=false;require(injected&&late.captured,"late failure crosses complete model builder");
    verify(late.accounting,"complete model late failure");
    require(late.accounting.quantization_engagements==total.quantization_engagements&&
        late.accounting.fallback_events==total.fallback_events,"late failed prefix equals complete successful receipt exactly");
    inbox(late.accounting);
}
void overflow(){
    ExecutionFailureReceipt sink;sink.captured=true;sink.accounting.quantization_engagements["real"]=3;
    ExecutionFailureReceipt child;child.captured=true;child.accounting.quantization_engagements["real"]=1;
    bool rejected=false;try{capture_execution_failure(&sink,{{{"real",std::numeric_limits<std::size_t>::max()}},{}},&child);}catch(const std::overflow_error&){rejected=true;}
    require(rejected&&sink.unavailable&&!sink.captured&&sink.accounting.quantization_engagements.empty(),"receipt merge overflow prevents partial publication");
    ExecutionFailureReceipt parent;
    capture_execution_failure(&parent,{{{"completed",2}},{}},&sink);
    require(parent.unavailable&&!parent.captured&&parent.accounting.quantization_engagements.empty(),"unavailable propagates through outer catch without importing its prefix");
}
void owning_overflow(const std::filesystem::path& root){
    auto fixture=placement_fixture::load(root,"devkit_mini");
    fixture.input.two_side=false;
    const auto planning_zones=build_pcb_zone_geometry(fixture.input);
    const std::string key="stage_root_pose_precision4dp";
    const auto n=planning_zones.quantization_engagements.at(key);
    require(n>0,"owning overflow requires actual completed stage work");
    // A single shared planning/emission zone is counted once, including in
    // top-preferred mode. Exact MAX is valid; MAX+1 must never yield a receipt.
    fixture.input.floorplan.accounting.quantization_engagements[key]=std::numeric_limits<std::size_t>::max()-n;
    const auto prepared=prepare_pcb_floorplan(fixture.input,planning_zones);
    require(prepared.accounting.quantization_engagements.at(key)==std::numeric_limits<std::size_t>::max(),"prepare succeeds at exact maximum");
    const auto stage=generate_floorplan(prepared);
    require(stage.plan.accounting.quantization_engagements.at(key)==std::numeric_limits<std::size_t>::max(),"successful child retains exact maximum");
    ExecutionFailureReceipt exact_failure;
    const auto exact=build_pcb_model(fixture.input,&exact_failure);
    require(pcb_placement_accounting(exact).quantization_engagements.at(key)==std::numeric_limits<std::size_t>::max()&&
            !exact_failure.captured&&!exact_failure.unavailable,"shared zone at MAX is counted once without phantom overflow");
    ++fixture.input.floorplan.accounting.quantization_engagements[key];
    ExecutionFailureReceipt failure;bool rejected=false;
    try{(void)build_pcb_model(fixture.input,&failure);}catch(const std::overflow_error&){rejected=true;}
    require(rejected&&failure.unavailable&&!failure.captured&&failure.accounting.quantization_engagements.empty(),"owning model rejects zone merge overflow without a partial receipt");
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);
    NativeAccountingInbox in(q,f);const auto before=q.engagements();
    if(failure.captured)in.merge_once("pcb/placement",failure.accounting);
    require(q.engagements()==before,"pipeline import condition skips unavailable model receipt");
}
void constructor_failure(const std::filesystem::path& root){
    auto fixture=placement_fixture::load(root,"devkit_mini");
    auto input=fixture.input.floorplan;input.som.w=0;
    input.accounting.quantization_engagements["stage_root_pose_precision4dp"]=7;
    ExecutionFailureReceipt failure;bool rejected=false;
    try{(void)build_floorplan(input,&failure);}catch(const FloorplanError& e){rejected=std::string(e.what())=="floorplan: SoM dimensions must be finite and > 0";}
    require(rejected&&failure.captured&&!failure.unavailable,"direct constructor error publishes inherited prefix");
    require(failure.accounting.quantization_engagements==input.accounting.quantization_engagements&&failure.accounting.fallback_events==input.accounting.fallback_events,"direct constructor seed is exact");
}
void invalid_stage(const std::filesystem::path& root){
    auto fixture=placement_fixture::load(root,"devkit_mini");
    std::size_t exercised=0;
    for(const auto& [sheet,contract]:fixture.input.contracts){
        (void)contract;
        auto input=fixture.input;
        auto& fields=input.contracts.at(sheet).object_value;
        for(auto& [key,value]:fields)if(key=="structures")value.array_value.clear();
        ExecutionFailureReceipt failure;bool rejected=false;
        begin();try{(void)build_pcb_model(input,&failure);}catch(const PcbZoneInfeasible& e){
            rejected=std::string(e.what())==sheet+": contract has no hot_loop/proximity structure";
        }
        observing=false;
        if(!rejected)continue;
        require(failure.captured,"nested invalid stage preserves original failure");
        verify(failure.accounting,"nested stage failure "+sheet);inbox(failure.accounting);
        ++exercised;
    }
    require(exercised>0,"invalid-stage negative cases exercised");
}
}
extern "C" void __cyg_profile_func_enter(void* f,void*){if(!observing)return;for(std::size_t i=0;i<ops.size();++i)if(f==ops[i].address){++entries[i];break;}}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{require(argc==2,"repo path required");overflow();constructor_failure(argv[1]);owning_overflow(argv[1]);invalid_stage(argv[1]);for(bool two_side:{true,false}){checkpoints(argv[1],two_side);floorplan_failure(argv[1],two_side);success(argv[1],two_side);}std::cout<<"model failure receipts PASS\n";}catch(const std::exception& e){observing=false;std::cerr<<e.what()<<'\n';return 1;}}
