#include "schgen/native_audit_state.hpp"
#include "pcb_placement_fixture.hpp"
#include <atomic>
#include <thread>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error("accounting: "+why);}
template<class Error,class F>void rejects(F f,const std::string& why){bool raised=false;try{f();}catch(const Error&){raised=true;}require(raised,why);}
void counts_and_events(){
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);
    int executed=0;q.declare({"must-not-run","test.cpp::must_not_run","throws","Import must not reexecute math","pre-proof",0,[&](const auto&)->double{++executed;throw std::runtime_error("math reexecuted");}});
    q.record_count("must-not-run",42);q.merge_counts({{"must-not-run",7}});
    require(executed==0&&q.engagements().at("must-not-run")==AuditInteger(49),"record/merge never evaluates a transform");
    rejects<std::invalid_argument>([&]{q.record_count("must-not-run",-1);},"negative signed count rejected before conversion");
    rejects<std::invalid_argument>([&]{q.merge_counts(std::map<std::string,int>{{"must-not-run",-2}});},"negative signed batch rejected");
    rejects<std::logic_error>([&]{q.record_count("missing",0);},"unknown zero quantum rejected");
    const auto old=q.engagements();rejects<std::logic_error>([&]{q.merge_counts({{"fixed_part_grid",8},{"missing",0}});},"batch validates all labels");
    require(q.engagements()==old,"unknown late batch entry leaves every count intact");
    q.record_count("fixed_part_grid",UINT64_MAX);
    rejects<std::overflow_error>([&]{q.record_count("fixed_part_grid",1);},"single engagement overflow");
    rejects<std::overflow_error>([&]{q.invoke("fixed_part_grid",{1});},"invocation overflow retains original checked boundary");
    const auto full=q.engagements();rejects<std::overflow_error>([&]{q.merge_counts({{"est_via_cost",1},{"fixed_part_grid",1}});},"batch engagement overflow");
    require(q.engagements()==full,"overflow never partially merges an earlier key");
    require(full.at("fixed_part_grid").str()=="18446744073709551615","no double narrowing above 2^53");
    q.record_count("fixed_part_grid",0);require(q.engagements()==full,"zero at uint64 max is valid");

    f.record("seat_node_budget");f.merge_events({"cand_cap_truncated","seat_node_budget"});
    require(f.snapshot()==std::vector<std::string>{"seat_node_budget","cand_cap_truncated","seat_node_budget"},"event order and duplicates preserved");
    f.record_count("seat_node_budget",5);f.merge_counts({{"cand_cap_truncated",3}});
    require(f.census().at("seat_node_budget")==AuditInteger(7)&&f.census().at("cand_cap_truncated")==AuditInteger(4),"compact counts combine with actual event log");
    rejects<std::logic_error>([&]{f.snapshot();},"legacy snapshot cannot silently drop compact counts");
    const auto checkpoint=f.checkpoint();f.record("seat_node_budget");f.restore_checkpoint(checkpoint);
    require(f.checkpoint().counts==checkpoint.counts&&f.checkpoint().events==checkpoint.events,"compact checkpoint rollback exact");
    auto corrupt=checkpoint;corrupt.counts["seat_node_budget"]=0;
    rejects<std::invalid_argument>([&]{f.restore_checkpoint(corrupt);},"checkpoint cannot omit logged events");
    corrupt=checkpoint;corrupt.counts["unknown"]=0;rejects<std::logic_error>([&]{f.restore_checkpoint(corrupt);},"checkpoint rejects unknown zero label");
    require(f.checkpoint().counts==checkpoint.counts&&f.checkpoint().events==checkpoint.events,"invalid checkpoint leaves both representations intact");
    const auto before=f.checkpoint();rejects<std::logic_error>([&]{f.merge_events({"seat_node_budget","unknown"});},"unknown event rejects whole event batch");
    require(f.checkpoint().counts==before.counts&&f.checkpoint().events==before.events,"event validation has no partial append");
    rejects<std::invalid_argument>([&]{f.record_count("seat_node_budget",-1);},"negative fallback count rejected");
    rejects<std::logic_error>([&]{f.merge_counts({{"seat_node_budget",1},{"unknown",0}});},"unknown fallback count rejected");
    f.reset();f.record_count("seat_node_budget",UINT64_MAX);
    rejects<std::overflow_error>([&]{f.record("seat_node_budget");},"event overflow checked before append");
    rejects<std::overflow_error>([&]{f.merge_counts({{"cand_cap_truncated",3},{"seat_node_budget",1}});},"compact fallback overflow rejects whole batch");
    require(f.checkpoint().events.empty()&&f.census().at("cand_cap_truncated")==AuditInteger{},"overflow cannot append or alter another count");
    f.restore({"cand_cap_truncated"});require(f.census().at("seat_node_budget")==AuditInteger{}&&f.snapshot()==std::vector<std::string>{"cand_cap_truncated"},"legacy event restore explicitly replaces compact state");
}
void inbox_contracts(){
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
    // Actual emitted labels, not algorithm names guessed from function names.
    NativeAccountingBatch b{{{"som_pose_half_mm",2},{"placeholder_zone_half_mm",4},{"fixed_part_grid",6},
        {"outline_snap_up",8},{"outline_grow_step",10},{"outline_fine_grid",82},{"est_via_cost",12},{"run_overflow_tol",14},
        {"quant_credit",16},{"snap_erosion_bound",18},{"snap_erosion_pad",20},{"seat_slide",22}},
        {"legalize_only_compaction","punch_free_plan_rejected","interior_reseat_retry","cand_cap_truncated","seat_node_budget","bottom_variant_contract_reject","corridor_evict_moved","corridor_stray_unmovable"}};
    require(inbox.merge_once("build/physical/1",b),"first actual call aggregate imported");
    const auto initial_q=q.engagements(),initial_f=f.census();
    require(!inbox.merge_once("build/physical/1",b),"cached/doc replay is not counted twice");
    require(q.engagements()==initial_q&&f.census()==initial_f,"replay leaves totals exact");
    auto changed=b;changed.quantization_engagements["quant_credit"]++;
    rejects<std::logic_error>([&]{inbox.merge_once("build/physical/1",changed);},"same receipt changed counts must not silently disappear");
    changed=b;std::swap(changed.fallback_events[0],changed.fallback_events[1]);rejects<std::logic_error>([&]{inbox.merge_once("build/physical/1",changed);},"same receipt event order is part of payload");
    changed=b;changed.fallback_events.push_back("unknown");rejects<std::logic_error>([&]{inbox.merge_once("bad-call",changed);},"fallback error prevents quantum commit too");
    require(q.engagements()==initial_q&&f.census()==initial_f,"joint validation is all-or-nothing");
    require(inbox.merge_once("bad-call",b),"failed receipt never became consumed");
    rejects<std::invalid_argument>([&]{inbox.merge_once("",b);},"empty invocation identity rejected");
    q.reset_engagements();rejects<std::logic_error>([&]{inbox.merge_once("build/physical/1",b);},"independent reset cannot hide stale receipt state");
    inbox.reset();require(inbox.merge_once("build/physical/1",b),"joint new-build reset resets receipts and both count families");
    require(q.engagements()==initial_q&&f.census()==initial_f,"new build contains one import, not old events");
    f.restore(f.snapshot());rejects<std::logic_error>([&]{inbox.merge_once("later",b);},"independent restore cannot desynchronize receipt ownership");
    inbox.reset();q.record_count("fixed_part_grid",UINT64_MAX);auto before=f.checkpoint();
    rejects<std::overflow_error>([&]{inbox.merge_once("overflow",b);},"joint quantum overflow rejects events");
    require(f.checkpoint().counts==before.counts&&f.checkpoint().events==before.events,"overflow did not touch fallback state");
    inbox.reset();f.record_count("seat_node_budget",UINT64_MAX);const auto prior=q.engagements();
    rejects<std::overflow_error>([&]{inbox.merge_once("overflow",b);},"joint fallback overflow rejects quantization counts");require(q.engagements()==prior,"fallback overflow did not touch quantum state");
    inbox.reset();std::atomic<int> merged{0};std::vector<std::thread> threads;
    for(int i=0;i<4;++i)threads.emplace_back([&]{for(int j=0;j<25;++j)if(inbox.merge_once("shared-call",b))++merged;});
    for(auto& t:threads)t.join();require(merged==1&&q.engagements()==initial_q&&f.census()==initial_f,"concurrent duplicate receipt counts exactly once");
    inbox.reset();threads.clear();for(int i=0;i<4;++i)threads.emplace_back([&,i]{for(int j=0;j<10;++j)inbox.merge_once(std::to_string(i)+"/"+std::to_string(j),b);});
    for(auto& t:threads)t.join();require(q.engagements().at("outline_fine_grid")==AuditInteger(3280)&&f.census().at("seat_node_budget")==AuditInteger(40),"independent actual calls accumulate without lost updates");
    inbox.reset();PcbStageResult stage;stage.quantization_engagements["quant_credit"]=3;stage.fallback_events={"seat_node_budget"};
    require(inbox.merge_once("standalone-stage",stage),"actual PcbStageResult adapter compiles and imports");
    FloorplanAccounting accounting;accounting.quantization_engagements["fixed_part_grid"]=5;require(inbox.merge_once("standalone-plan",accounting),"actual FloorplanAccounting adapter compiles and imports");
}
void live_zone(const std::filesystem::path& root){
    auto fixture=placement_fixture::load(root,"devkit_mini");
    const auto zones=build_pcb_zone_geometry(fixture.input); // actual native stage solver work
    const auto prepared=prepare_pcb_floorplan(fixture.input,zones);
    require(prepared.accounting.quantization_engagements==zones.quantization_engagements,"actual parent aggregate already owns zone quantization");
    require(prepared.accounting.fallback_events==zones.fallback_events,"actual parent aggregate already owns ordered zone events");
    const auto& expected=placement_fixture::field(fixture.source,"zone_quant");
    for(const auto& [name,n]:expected.object_value){const auto p=zones.quantization_engagements.find(name);
        require((p==zones.quantization_engagements.end()?0:p->second)==n.number_value,"independent captured actual zone count "+name);}
    require(zones.fallback_events==placement_fixture::strings(placement_fixture::field(fixture.source,"zone_events")),"independent captured actual zone event order");
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
    require(inbox.merge_once("actual-physical-call",prepared.accounting),"actual emitted aggregate imported directly");
    for(const auto& [name,n]:zones.quantization_engagements)require(q.engagements().at(name)==AuditInteger::decimal(std::to_string(n)),"no native result count narrowing/doubling "+name);
    require(f.snapshot()==zones.fallback_events,"no duplicate child event import");
    require(!inbox.merge_once("actual-physical-call",prepared.accounting),"reused actual aggregate is idempotent");
    // A standalone-zone entry point uses the zone result itself, NOT both it
    // and its parent. Use a fresh inbox to demonstrate that alternative path.
    inbox.reset();require(inbox.merge_once("standalone-zone",zones),"actual PcbZoneResult direct import");
}
}
std::size_t native_accounting_contracts(const std::filesystem::path& root){checks=0;counts_and_events();inbox_contracts();live_zone(root);return checks;}
