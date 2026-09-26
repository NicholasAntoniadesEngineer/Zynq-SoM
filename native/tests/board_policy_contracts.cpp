#include "schgen/board_policy.hpp"
#include "schgen/project_outputs.hpp"
#include "floorplan_internal.hpp"
#include "board_policy_ledger_reference.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <set>
#include <unistd.h>

namespace {
using namespace schgen;namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool value,const std::string& why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>void rejects(F fn,const std::string& why){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}require(caught,why);}
const JsonNode& field(const JsonNode& n,const std::string& key){const auto* p=object_field(n,key);if(!p)throw std::runtime_error("fixture field "+key);return *p;}
std::vector<std::string> strings(const JsonNode& a){std::vector<std::string> out;for(const auto& n:a.array_value)out.push_back(n.string_value);return out;}
struct Temp{fs::path path;Temp(){auto s=(fs::temp_directory_path()/"schgen_policy_contract_XXXXXX").string();if(!::mkdtemp(s.data()))throw std::runtime_error("mkdtemp");path=s;}~Temp(){std::error_code ec;fs::remove_all(path,ec);}};
const NativeLedgerDeclaration& declaration(const NativeBoardPolicy& p,const std::string& name){for(const auto& d:p.ledger_declarations)if(d.name==name)return d;throw std::runtime_error("missing declaration "+name);}
void metadata(const fs::path& root){
    const auto reference=parse_json_file((root/"native/tests/data/board_policy/python_reference.json").string());
    const auto actual=floorplan_ledger_policy();std::vector<std::string> assumptions;std::vector<FloorplanLedgerPolicy> calcs;
    for(const auto& d:actual){if(d.kind=="ASSUME")assumptions.push_back(d.name);else calcs.push_back(d);require(!d.basis.empty(),"authored basis retained");}
    auto expected_assumptions=strings(field(reference,"assumptions"));
    const std::set<std::string> retired{"placeholder_aspect","placeholder_min","placeholder_max","zone_step","som_side_band","via_size","via_clearance","stack_thickness"};
    std::vector<std::string> migrated_assumptions;
    for(const auto& name:expected_assumptions){if(name=="via_size"){migrated_assumptions.push_back("via_ordinary_cost");migrated_assumptions.push_back("via_impedance_cost");}if(!retired.count(name))migrated_assumptions.push_back(name);}
    migrated_assumptions.push_back("breathe_epsilon");migrated_assumptions.push_back("breathe_search_step");
    migrated_assumptions.push_back("mounting_hole_inset");migrated_assumptions.push_back("edge_pad_clearance");
    migrated_assumptions.push_back("compose_guard");
    migrated_assumptions.push_back("compose_repair_max");
    migrated_assumptions.push_back("compose_median_passes");
    migrated_assumptions.push_back("compose_channel_min_nets");
    migrated_assumptions.push_back("compose_channel_floor");
    migrated_assumptions.push_back("compose_channel_per_net");
    migrated_assumptions.push_back("compose_hop_weight");
    migrated_assumptions.push_back("compose_seed_weight");
    migrated_assumptions.push_back("floorplan_svg_origin_x");
    migrated_assumptions.push_back("floorplan_svg_origin_y");
    migrated_assumptions.push_back("floorplan_svg_scale");
    migrated_assumptions.push_back("escape_construct_radius");
    migrated_assumptions.push_back("escape_lattice");
    migrated_assumptions.push_back("escape_lane_handle");
    migrated_assumptions.push_back("escape_hole_clearance");
    migrated_assumptions.push_back("small_part_routing_factor");
    migrated_assumptions.push_back("point_segment_tolerance");
    migrated_assumptions.push_back("visual_axis_tolerance");
    migrated_assumptions.push_back("collinear_overlap_tolerance");
    migrated_assumptions.push_back("segment_cross_tolerance");
    migrated_assumptions.push_back("label_courtyard_gap");
    migrated_assumptions.push_back("label_orbit_tau");
    require(assumptions==migrated_assumptions,"independent historical assumption order plus reviewed native migration");
    const auto& expected=field(reference,"calculations").array_value;require(calcs.size()==expected.size(),"independent calculation census");
    for(std::size_t k=0;k<expected.size();++k){require(calcs[k].name==field(expected[k],"name").string_value,"calculation name");const auto inputs=(calcs[k].name=="est_via_ordinary"||calcs[k].name=="est_via_impedance")?std::vector<std::string>{"via_cost"}:strings(field(expected[k],"inputs"));require(calcs[k].inputs==inputs,"ordered input contract including truthful native via policy");require(calcs[k].repeated==field(expected[k],"repeated").bool_value,"conditional/repeated semantics");}
    const auto stages=native_board_pipeline_metadata();const auto& es=field(reference,"stages").array_value;require(stages.stages.size()==es.size(),"stage census");
    for(std::size_t i=0;i<es.size();++i){const auto& s=stages.stages[i];const auto& e=es[i].array_value;require(s.name==e[0].string_value&&s.domain==e[1].string_value&&s.may_move==e[2].bool_value&&s.tracked==e[3].bool_value,"independent stage order/domain/movement policy");require(!s.validated_by.empty()&&!s.desc.empty(),"stage proof/description nonempty");}
    const auto fb=parse_json_file((root/"native/tests/data/verification_audits/python_state.json").string());
    const auto& ef=field(fb,"fallbacks").array_value;require(ef.size()==stages.fallbacks.size(),"independent fallback population");
    NativeFallbacks f;register_native_fallbacks(f);
    for(const auto& entry:ef){const auto name=field(entry,"name").string_value;auto hit=std::find_if(stages.fallbacks.begin(),stages.fallbacks.end(),[&](const auto& d){return d.name==name;});require(hit!=stages.fallbacks.end(),"independent fallback name");require(hit->stage==field(entry,"stage").string_value&&!hit->meaning.empty(),"independent fallback stage");f.record(hit->name);}
    for(const auto& [name,count]:f.census())require(count==AuditInteger(1),"metadata matches live fallback registry: "+name);
    NativeQuantizations q;register_native_quantizations(q);require(stages.quantization.size()==q.declarations().size(),"current transform metadata census");
    for(const auto& [name,count]:q.engagements())require(!count.nonzero(),"metadata collection never executes "+name);
}
void providers(const fs::path& root){
    ProjectPaths paths;paths.repository_root=root;
    FloorplanInput in;in.cross_budget_k=4.25;in.place_clear=.73;
    auto policy=make_native_board_policy(paths,in);require(policy.providers_complete(),"all reviewed producer providers complete");
    require(policy.ledger_declarations.size()==90&&policy.missing_providers.empty(),"reviewed current coverage (72 assumes,18 calcs; no gaps)");
    require(declaration(policy,"compose_guard").resolve().number_value==4.0,"preserved compose_guard value");
    require(declaration(policy,"compose_repair_max").resolve().number_value==16.0,"preserved compose_repair_max value");
    require(declaration(policy,"compose_median_passes").resolve().number_value==8.0,"preserved compose_median_passes value");
    require(declaration(policy,"compose_channel_min_nets").resolve().number_value==6.0,"preserved compose_channel_min_nets value");
    require(declaration(policy,"compose_channel_floor").resolve().number_value==2.0,"preserved compose_channel_floor value");
    require(declaration(policy,"compose_channel_per_net").resolve().number_value==0.2,"preserved compose_channel_per_net value");
    require(declaration(policy,"compose_hop_weight").resolve().number_value==1.0,"preserved compose_hop_weight value");
    require(declaration(policy,"compose_seed_weight").resolve().number_value==0.05,"preserved compose_seed_weight value");
    require(declaration(policy,"floorplan_svg_origin_x").resolve().number_value==46.0,"preserved floorplan_svg_origin_x value");
    require(declaration(policy,"floorplan_svg_origin_y").resolve().number_value==64.0,"preserved floorplan_svg_origin_y value");
    require(declaration(policy,"floorplan_svg_scale").resolve().number_value==6.0,"preserved floorplan_svg_scale value");
    require(declaration(policy,"escape_construct_radius").resolve().number_value==1.8,"preserved escape_construct_radius value");
    require(declaration(policy,"escape_lattice").resolve().number_value==0.05,"preserved escape_lattice value");
    require(declaration(policy,"escape_lane_handle").resolve().number_value==1.0,"preserved escape_lane_handle value");
    require(declaration(policy,"escape_hole_clearance").resolve().number_value==0.5,"preserved escape_hole_clearance value");
    require(declaration(policy,"mounting_hole_inset").resolve().number_value==5.,"unchanged mounting-hole geometry policy");
    require(declaration(policy,"edge_pad_clearance").resolve().number_value==.4,"unchanged edge pad geometry policy");
    require(declaration(policy,"cross_k").resolve().number_value==4.25,"actual caller cross coefficient");
    require(declaration(policy,"place_clear").resolve().number_value==.73,"actual caller clearance");
    in.cross_budget_k=9;in.place_clear=.1;
    require(declaration(policy,"cross_k").resolve().number_value==4.25,"provider owns invocation scalar, not caller lifetime");
    require(declaration(make_native_board_policy(paths,in),"cross_k").resolve().number_value==9,"next invocation reads fresh caller value");
    NativeLedger ledger;for(const auto& d:policy.ledger_declarations)ledger.declare(d);
    ledger.open_step("floorplan.sizing");ledger.close_step("floorplan.sizing");require(ledger.audit_state().recorded.size()==72,"every real assumption resolves at step entry");
    for(const auto& gap:policy.missing_providers){require(!gap.decision_source.empty()&&!gap.action.empty(),"missing provider actionable");require(std::none_of(policy.ledger_declarations.begin(),policy.ledger_declarations.end(),[&](const auto& d){return d.name==gap.name;}),"missing policy never fabricated");}
    // Known C++ storage is independent from the producer's historical display
    // defaults and current observed rows. Poisoning observations grants nothing.
    in.accounting.decisions.push_back({"floorplan.sizing","ASSUME","bogus",{}, {},1,""});
    auto poisoned=make_native_board_policy(paths,in);require(poisoned.ledger_declarations.size()==policy.ledger_declarations.size(),"observed rows cannot create declarations");
    require(declaration(poisoned,"edge_margin").resolve().number_value==floorplan_detail::edge_margin,"live compiled policy read");
    require(floorplan_live_assumption("place_grid",in)==1.27&&!floorplan_live_assumption("bogus",in),"real quantization provider; unknown name cannot use a frozen fallback");
    FloorplanInput actual=in;actual.som.w=30;actual.som.h=40;actual.accounting={};
    floorplan_detail::Engine producer(actual);producer.ledger_open();
    for(const auto& d:poisoned.ledger_declarations)if(d.kind=="ASSUME"){
        const auto value=floorplan_live_assumption(d.name,actual);
        require(value.has_value(),"registered assumption has live producer provider: "+d.name);
        const auto row=std::find_if(producer.plan.accounting.decisions.begin(),producer.plan.accounting.decisions.end(),[&](const auto& r){return r.kind=="ASSUME"&&r.name==d.name;});
        require(row!=producer.plan.accounting.decisions.end()&&row->value.number_value==*value&&*value==d.resolve().number_value,"actual producer and independent provider agree: "+d.name);
    }
    // Immutable original Python assumptions remain byte-identical in the
    // producer; this change exposes metadata without modifying its math/output.
    for(const auto* project:{"carrier","devkit_mini"}){
        auto reference=parse_json_file((root/"native/tests/data/floorplan"/(std::string(project)+".json")).string());
        FloorplanInput base;base.som.w=30;base.som.h=40;floorplan_detail::Engine engine(base);engine.ledger_open();
        const auto migrated=board_policy_reference::migrate(field(reference,"expected"),root/"native/tests/data");
        const auto& rows=field(migrated,"ledger").array_value;
        for(const auto& row:engine.plan.accounting.decisions){auto hit=std::find_if(rows.begin(),rows.end(),[&](const auto& r){return field(r,"kind").string_value==row.kind&&field(r,"name").string_value==row.name;});require(hit!=rows.end(),"independent producer assumption exists");require(field(*hit,"text").string_value==row.text,"immutable producer assumption text");}
    }
    const auto files=native_board_policy_audit_sources();std::set<std::string> names;for(const auto& f:files){require(names.insert(f.path).second&&fs::is_regular_file(root/f.path),"explicit unique existing decision file: "+f.path);require(f.path.find(".py")==f.path.npos,"no Python source audit input");}
    for(const auto& f:board_pipeline_audit_sources())require(names.count(f.path),"host minimum audit scope retained");
    for(const auto& d:policy.ledger_declarations)for(const auto& cover:d.covers)require(names.count(cover.substr(0,cover.find("::"))),"covered symbol owner included");
    auto bad=in;bad.place_clear=-1;rejects([&]{make_native_board_policy(paths,bad);},"negative clearance rejects");bad=in;bad.cross_budget_k=std::numeric_limits<double>::infinity();rejects([&]{make_native_board_policy(paths,bad);},"nonfinite cross coefficient rejects");
    BoardPipelineOptions options;options.output_root="keep-output";options.fallback_baseline="keep-fallback";options.fanout_baseline="keep-fanout";options.no_render=true;options.pcb.place_clear=.73;options.audit.compiler="keep-clang";options.audit.flags={"-DKEEP_CALLER=1"};options.audit.timeout=std::chrono::milliseconds{321};
    const auto installed=configure_native_board_policy(options,paths,in);require(options.ledger_declarations.size()==90&&installed.providers_complete(),"factory installs complete independently reviewed declarations");
    require(options.output_root=="keep-output"&&options.fallback_baseline=="keep-fallback"&&options.fanout_baseline=="keep-fanout"&&options.no_render&&options.pcb.place_clear==.73,"caller execution settings preserved");
    require(options.audit.compiler=="keep-clang"&&options.audit.flags.front()=="-DKEEP_CALLER=1"&&options.audit.timeout.count()==321,"compiler settings preserved");
    rejects([&]{configure_native_board_policy(options,paths,in);},"never silently replace existing policy");require(options.ledger_declarations.size()==90,"failed installation atomic");
}
void defects(){
    // Mutation contract for the existing auditor: our policy is never a waiver
    // for unregistered, buried, deleted or raw quantization source defects.
    NativeLedger l;NativeLedgerDeclaration d;d.name="margin";d.kind="ASSUME";d.step="floorplan.sizing";d.source="policy";d.basis="Reviewed edge margin";d.covers={"policy.cpp::margin"};d.resolve=[]{return floorplan_detail::jvalue(10.);};l.declare(d);l.open_step("floorplan.sizing");l.close_step("floorplan.sizing");
    NativeQuantizations q;CppSourceCensus c;c.n_files=1;c.constants={{"policy.cpp::margin","policy.cpp:1",false}};
    require(check_native_audits(c,l,q).ok,"registered test policy passes direct census");
    auto bad=c;bad.constants.push_back({"policy.cpp::unreviewed","policy.cpp:2",false});require(!check_native_audits(bad,l,q).ok,"new constants still reject");
    bad=c;bad.constants.front().buried=true;require(check_native_audits(bad,l,q).ok,"exact reviewed cover may declare buried policy");
    bad.constants.push_back({"policy.cpp::mover::unreviewed","policy.cpp:2",true});require(!check_native_audits(bad,l,q).ok,"uncovered buried engineering policy still rejects");
    bad=c;bad.quantization.push_back({"policy.cpp:3","policy.cpp::mover","raw-round"});require(!check_native_audits(bad,l,q).ok,"raw quantization still rejects");
    bad=c;bad.constants.clear();bad.functions.insert("policy.cpp::mover");require(!check_native_audits(bad,l,q).ok,"deleted storage leaves stale cover");
}
void compiler_contract(const fs::path& root){
    Temp temp;publish_text(temp.path/"policy.cpp","namespace policy { constexpr double edge_margin=10.; double apply(double v){ return v+edge_margin; } }\n");
    NativeLedger l;NativeLedgerDeclaration d;d.name="margin";d.kind="ASSUME";d.step="floorplan.sizing";d.source="policy";d.basis="Reviewed edge margin";d.covers={"policy.cpp::policy::edge_margin"};d.resolve=[]{return floorplan_detail::jvalue(10.);};l.declare(d);l.open_step("floorplan.sizing");l.close_step("floorplan.sizing");NativeQuantizations q;
    require(check_native_audits(temp.path,{{"policy.cpp"}},l,q).ok,"real compiler accepts covered policy");
    publish_text(temp.path/"policy.cpp","namespace policy { constexpr double edge_margin=10.; constexpr double surprise=.25; double apply(double v){return v+surprise;} }\n");
    require(!check_native_audits(temp.path,{{"policy.cpp"}},l,q).ok,"real compiler rejects added unreviewed constant");
    // One real problematic required file proves metadata cannot greenwash the
    // existing raw/buried sites. Do not assert fragile diagnostic counts.
    CppAuditOptions opts;opts.flags={"-I"+(root/"native/include").string(),"-I"+(root/"native/src").string()};
    const auto source=scan_cpp_audit_sources(root,{{"native/src/pcb_placement_breathe.cpp"},{"native/src/precision_ops.cpp"},{"native/include/schgen/board_decision_policy.hpp"}},opts);
    require(std::any_of(source.constants.begin(),source.constants.end(),[](const auto& x){return x.symbol=="native/include/schgen/board_decision_policy.hpp::schgen::board_decision_policy::breathe_epsilon_mm";}),"actual lifted breathe epsilon remains visible in its defining header");
    ProjectPaths paths;paths.repository_root=root;FloorplanInput input;
    const auto policy=make_native_board_policy(paths,input);
    for(const auto& d:policy.ledger_declarations)for(const auto& cover:d.covers)
        if(cover.find("native/include/schgen/board_decision_policy.hpp::")==0)
            require(std::count_if(source.constants.begin(),source.constants.end(),[&](const auto& constant){return constant.symbol==cover;})==1,
                    "reviewed shared policy has exactly one actual compiler-resolved storage: "+d.name);
    require(!source.quantization.empty(),"actual precision implementation sites remain visible, not exempted");
    require(std::all_of(source.quantization.begin(),source.quantization.end(),[](const auto& q){return q.function.find("native/src/precision_ops.cpp::schgen::")==0;}),"breathe raw sites are extracted into actual scalar operations");
}
}
int main(int argc,char** argv){try{if(argc<2||argc>3)throw std::runtime_error("usage: board_policy_contracts REPO [--compiler]");const fs::path root=fs::absolute(argv[1]);metadata(root);providers(root);defects();if(argc==3){if(std::string(argv[2])!="--compiler")throw std::runtime_error("unknown mode");compiler_contract(root);}std::cout<<"Native board policy: "<<checks<<" contracts passed\n";return 0;}catch(const std::exception& e){std::cerr<<"Native board policy: "<<e.what()<<'\n';return 1;}}
