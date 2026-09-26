#include "schgen/board_policy.hpp"
#include "schgen/board_decision_policy.hpp"
#include "floorplan_internal.hpp"
#include "board_policy_ledger_reference.hpp"
#include "pcb_placement_fixture.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool p,const std::string& why){++checks;if(!p)throw std::runtime_error(why);}
template<class F>void rejects(F f,const std::string& why){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}require(rejected,why);}
std::uint64_t bits(double v){std::uint64_t out=0;static_assert(sizeof(out)==sizeof(v));std::memcpy(&out,&v,sizeof(v));return out;}
bool equal(const JsonNode& a,const JsonNode& b){
    if(a.kind!=b.kind||a.bool_value!=b.bool_value||bits(a.number_value)!=bits(b.number_value)||a.string_value!=b.string_value||
       a.array_value.size()!=b.array_value.size()||a.object_value.size()!=b.object_value.size())return false;
    for(std::size_t i=0;i<a.array_value.size();++i)if(!equal(a.array_value[i],b.array_value[i]))return false;
    for(std::size_t i=0;i<a.object_value.size();++i)if(a.object_value[i].first!=b.object_value[i].first||!equal(a.object_value[i].second,b.object_value[i].second))return false;
    return true;
}
const NativeLedgerDeclaration& declaration(const NativeBoardPolicy& p,const std::string& name){
    for(const auto& d:p.ledger_declarations)if(d.name==name)return d;
    throw std::runtime_error("missing declaration "+name);
}
void provenance(const std::filesystem::path& root){
    const std::set<std::string> retired{"placeholder_aspect","placeholder_min","placeholder_max","zone_step","som_side_band"};
    const std::set<std::string> replaced{"via_size","via_clearance","stack_thickness"};
    std::set<std::string> seen;
    const auto rows=floorplan_ledger_migrations();require(rows.size()==10,"five retirements, three truthful via replacements and two exposed breathe policies");
    FloorplanInput in;ProjectPaths paths;paths.repository_root=root;const auto p=make_native_board_policy(paths,in);
    for(const auto& row:rows){
        require(seen.insert(row.name).second&&!row.reason.empty(),"unique documented provenance");
        if(row.name=="breathe_epsilon"||row.name=="breathe_search_step"){
            require(row.disposition=="exposed"&&row.replacements.empty(),"existing hidden policy is exposed, not redefined");
            require(floorplan_live_assumption(row.name,in).has_value()&&declaration(p,row.name).resolve().number_value==*floorplan_live_assumption(row.name,in),"exposed policy resolves actual producer storage");
            continue;
        }
        if(retired.count(row.name))require(row.disposition=="retired"&&row.replacements.empty(),"unused assumptions truly retire");
        else{require(replaced.count(row.name)&&row.disposition=="replaced","no extra provenance exceptions");
            const auto expected=row.name=="stack_thickness"?std::vector<std::string>{"via_impedance_cost"}:std::vector<std::string>{"via_ordinary_cost","via_impedance_cost"};
            require(row.replacements==expected,"explicit via operand replacement ownership");}
        require(!floorplan_live_assumption(row.name,in),"retired operand has no fabricated provider");
        rejects([&]{declaration(p,row.name);},"retired operand not declared");
    }
    require(p.providers_complete()&&p.ledger_declarations.size()==66,"current complete provider census");
    for(const auto* board:{"carrier","devkit_mini"}){
        const auto file=root/"native/tests/data/floorplan"/(std::string(board)+".json");
        const auto original=parse_json_file(file.string());const auto& expected=board_policy_reference::field(original,"expected");
        const auto migrated=board_policy_reference::migrate(expected,root/"native/tests/data");
        require(board_policy_reference::field(expected,"ledger").array_value.size()==board_policy_reference::field(migrated,"ledger").array_value.size()+4,"only reviewed replacement and additive ledger population changes");
        // Byte-level geometry/count comparisons live in floorplan_contracts and
        // pcb_placement_contracts; this helper may alter ONLY these two fields.
        for(std::size_t i=0;i<expected.object_value.size();++i){
            const auto& a=expected.object_value[i];const auto& b=migrated.object_value[i];
            require(a.first==b.first,"reference object order unchanged");
            if(a.first!="ledger"&&a.first!="decisions"){
                require(equal(a.second,b.second),"reference geometry, counts and events unchanged: "+a.first);
            }
        }
    }
}
void full_import(const std::filesystem::path& root,const std::string& board){
    const auto fixture=placement_fixture::load(root,board);
    const auto zones=build_pcb_zone_geometry(fixture.input);
    const auto input=prepare_pcb_floorplan(fixture.input,zones);
    ProjectPaths paths;paths.repository_root=root;
    const auto policy=make_native_board_policy(paths,input);
    const auto solved=generate_floorplan(input);
    NativeLedger ledger;for(const auto& d:policy.ledger_declarations)ledger.declare(d);
    import_board_floorplan_ledger(ledger,solved.plan.accounting,policy.ledger_declarations);
    const auto state=ledger.audit_state();require(state.problems.empty(),board+" full actual floorplan import");
    for(const auto& d:policy.ledger_declarations)if(!d.repeated)require(state.recorded.count(d.name),board+" actual invocation records "+d.name);
    auto poisoned=solved.plan.accounting;
    for(auto& row:poisoned.decisions)if(row.name=="edge_depth_cap")row.value.number_value+=1;
    NativeLedger bad;for(const auto& d:policy.ledger_declarations)bad.declare(d);
    rejects([&]{import_board_floorplan_ledger(bad,poisoned,policy.ledger_declarations);},board+" producer/provider divergence rejects");
    require(bad.entries().empty(),board+" failed full import leaves no prefix");
}
FloorplanInput cross_input(){
    FloorplanInput in;in.som.w=20;in.som.h=20;
    in.footprints["one"]={"synthetic-one-pad",sexpr_loads(R"((footprint "one" (fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd") (width 0.05)) (pad "1" smd rect (at 0 0) (size 1 1))))")};
    in.footprint_of["Test:One"]="one";
    for(int k=1;k<=2;++k){const std::string name=k==1?"source":"sink",ref="U"+std::to_string(k*1000+1);
        CircuitSheetIr s;s.name=name;s.parts.push_back({"U1","Test:One","one","Test:One",{},{},{}});
        s.nets.push_back({"signal","port",{{"U1","1"}}});in.sheets.push_back(s);in.sheet_index.emplace_back(name,k);
        in.geometry.zone_box[name]={2,2};in.geometry.top_off[name][ref]={0,0};in.geometry.side_of[ref]="top";
        in.geometry.resolvable[ref]="one";in.geometry.bbox_of[ref]={-1,-1,1,1};
    }
    FloorplanZoneShape top;top.w=top.h=2;top.top_off["U2001"]={0,0};
    auto bottom=top;bottom.side="bottom";in.geometry.shapes["sink"]={top,bottom};return in;
}
void via(const std::filesystem::path& root){
    require(bits(est_via_cost(false))==UINT64_C(0x400199999999999a),"ordinary compiled bits preserved");
    require(bits(est_via_cost(true))==UINT64_C(0x401e666666666666),"impedance compiled bits preserved");
    // Real independent counterexample: the old physical formula would drift.
    volatile double size=.6,clearance=.25,thickness=1.6;
    require(bits(2*2*(size+2*clearance)+2*thickness)!=bits(est_via_cost(true)),"must not reconstruct the physical via formula");
    ProjectPaths paths;paths.repository_root=root;
    const std::vector<std::optional<double>> overrides{std::nullopt,0.,3.125,std::nextafter(2.2,3.)};
    for(bool impedance:{false,true})for(const auto& override:overrides){
        auto in=cross_input();std::size_t observations=0;
        auto experiment=std::make_shared<FloorplanExperiment>();experiment->ordinary_via_mm=override;
        experiment->unscoped_estimate=[&](double){++observations;};in.experiment=experiment;
        if(impedance)in.impedance_net_classes["signal"]="DP100_TMDS";
        const double ordinary=override.value_or(2.2),cost=impedance?7.6:ordinary;
        const auto policy=make_native_board_policy(paths,in);
        require(bits(declaration(policy,"via_ordinary_cost").resolve().number_value)==bits(ordinary),"actual optional override (including zero) reaches provider");
        require(bits(declaration(policy,"via_impedance_cost").resolve().number_value)==bits(7.6),"ordinary override never changes impedance provider");
        require(observations==0&&in.accounting.quantization_engagements.empty(),"policy reads do not execute solver or counters");
        floorplan_detail::Engine e(in);e.ledger_open();e.ledger_initial(50,50);e.prepare_cross();
        require(e.cross_nets.size()==1&&bits(e.cross_nets.front().via_cost)==bits(cost),"actual net estimator uses identical resolved policy");
        require(e.plan.accounting.quantization_engagements.at("est_via_cost")==1,"exactly one actual per-net pricing engagement");
        for(const auto& row:e.plan.accounting.decisions)if(row.name=="via_ordinary_cost"||row.name=="est_via_ordinary")
            require(bits(row.value.number_value)==bits(ordinary),"assumption and calculation record actual ordinary override");
        require(observations==0,"ledger policy does not invoke estimate observer");
        FloorplanBlock a,b;a.name="source";b.name="sink";a.w=a.h=b.w=b.h=2;b.x=3;b.y=4;b.shape_idx=1;b.side="bottom";
        e.plan.interior_blocks={a,b};require(bits(e.estimate())==bits(5.+cost),"real selected-bottom 3-4-5 MST plus actual via cost");
        require(observations==1,"existing estimate observer preserved");
        NativeLedger ledger;for(const auto& d:policy.ledger_declarations)ledger.declare(d);
        import_board_floorplan_ledger(ledger,e.plan.accounting,policy.ledger_declarations);
        require(ledger.audit_state().problems.empty(),"actual decision stream imports without replay");
        auto poisoned=policy.ledger_declarations;
        for(auto& d:poisoned)if(d.name=="via_ordinary_cost")d.resolve=[] {JsonNode n;n.kind=JsonKind::Number;n.number_value=-99;return n;};
        NativeLedger bad;for(const auto& d:poisoned)bad.declare(d);
        rejects([&]{import_board_floorplan_ledger(bad,e.plan.accounting,poisoned);},"drifted provider cannot pass actual import");
        require(bad.entries().empty(),"failed import is atomic");
        experiment->ordinary_via_mm=999;
        require(bits(declaration(policy,"via_ordinary_cost").resolve().number_value)==bits(ordinary),"provider owns invocation override; no borrowed mutable observer");
    }
    for(double bad:{-1.,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
        auto in=cross_input();auto experiment=std::make_shared<FloorplanExperiment>();experiment->ordinary_via_mm=bad;in.experiment=experiment;
        rejects([&]{make_native_board_policy(paths,in);},"invalid caller override rejects");
        rejects([&]{floorplan_detail::Engine e(in);},"matching native solver override validation");
    }
}
void precision(){
    // Pre-extraction expressions, independent of the new named policies.
    for(int i=-2048;i<=2048;++i)for(double delta:{-.000000001,0.,.000000001}){
        const double x=i*.635+delta;
        require(bits(fixed_part_grid(x))==bits(py_round(py_round(x/1.27,0)*1.27,4)),"placement grid expression bits");
        require(bits(som_pose_half_mm(x))==bits(py_round(py_round(x*2.,0)/2.,1)),"half-grid multiply/divide order bits");
        require(bits(legalize_pose_quantum(x))==bits(py_round(py_round(x/.5,0)*.5,4)),"legalizer quantum bits");
    }
    require(board_decision_policy::df40_min_pins==40&&!pcb_is_df40_part("logic",39)&&pcb_is_df40_part("logic",40),"shared DF40 threshold boundaries");
    require(pcb_is_df40_part("som_j2",3)&&!pcb_is_df40_part("som_jx",3),"DF40 sheet-name semantics preserved");
}
}
int main(int argc,char** argv){try{
    if(argc!=2)throw std::runtime_error("usage: board_policy_migration_contracts ROOT");
    provenance(argv[1]);via(argv[1]);precision();
    for(const auto* board:{"carrier","devkit_mini"})full_import(argv[1],board);
    std::cout<<"Native board policy migration: "<<checks<<" contracts passed\n";return 0;
}catch(const std::exception& e){std::cerr<<"Native board policy migration: "<<e.what()<<'\n';return 1;}}
