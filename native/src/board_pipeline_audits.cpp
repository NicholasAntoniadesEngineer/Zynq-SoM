#include "board_pipeline_internal.hpp"
#include "schgen/quantize.hpp"
#include <set>

namespace schgen {
std::vector<CppAuditSource> board_pipeline_audit_sources(){
    std::vector<CppAuditSource> out;
    for(const auto* name:{"quantize.cpp","native_audit_quantize.cpp","floorplan_internal.hpp","floorplan_geometry.cpp","floorplan_cross.cpp","floorplan_pack.cpp","floorplan_compose.cpp","floorplan_build.cpp","floorplan_notes.cpp","floorplan_svg.cpp","floorplan_md.cpp","pcb_stage_internal.hpp","pcb_stage_geometry.cpp","pcb_stage_search.cpp","pcb_stage_power.cpp","pcb_stage_zone.cpp","pcb_placement_internal.hpp","pcb_placement_inputs.cpp","pcb_placement_pack.cpp","pcb_placement_variants.cpp","pcb_placement_zones.cpp","pcb_placement_model.cpp","pcb_placement_moves.cpp","pcb_placement_breathe.cpp","pcb_placement_build.cpp","pcb_escape_internal.hpp","pcb_escape_copper.cpp","pcb_escape_plan.cpp","pcb_escape_model.cpp","pcb_escape_triage.cpp","pcb_embed.cpp","pcb_emit.cpp","pcb_project.cpp","pcb_silk.cpp","legalize.cpp","occupancy.cpp","pack.cpp","ratsnest_gate.cpp"})out.push_back({std::string("native/src/")+name});
    out.push_back({"native/src/legalize_precision.cpp"});
    out.push_back({"native/src/stage_precision.cpp"});
    out.push_back({"native/src/placement_precision.cpp"});
    return out;
}
void import_board_floorplan_ledger(NativeLedger& ledger,const FloorplanAccounting& accounting,
    const std::vector<NativeLedgerDeclaration>& declarations){
    using namespace board_pipeline_detail;
    if(accounting.decisions.empty())throw ProjectError("floorplan decision stream missing");
    std::map<std::string,const NativeLedgerDeclaration*> registry;
    for(const auto& d:declarations)if(!registry.emplace(d.name,&d).second)throw ProjectError("duplicate floorplan declaration "+d.name);
    // Validate the entire stream before writing a prefix into the ledger.
    std::vector<std::string> stack;std::set<std::string> assumptions;
    for(const auto& row:accounting.decisions){
        if(row.depth<0)throw ProjectError("negative floorplan ledger depth");
        if(row.kind=="STEP"){
            if(static_cast<std::size_t>(row.depth)>stack.size())throw ProjectError("floorplan ledger depth skipped");
            if((row.depth==0&&row.name!="floorplan.sizing")||(row.depth==1&&row.name!="sizing.pass")||row.depth>1)
                throw ProjectError("unknown floorplan producer step "+row.name);
            stack.resize(static_cast<std::size_t>(row.depth));stack.push_back(row.name);continue;}
        if(row.kind!="ASSUME"&&row.kind!="CALC")throw ProjectError("unknown floorplan decision kind "+row.kind);
        if(static_cast<std::size_t>(row.depth)>stack.size()||row.depth==0)throw ProjectError("floorplan decision outside its step");
        stack.resize(static_cast<std::size_t>(row.depth));
        if(stack.back()!=row.step)throw ProjectError("floorplan decision step mismatch "+row.name);
        const auto it=registry.find(row.name);if(it==registry.end())throw ProjectError("missing reviewed native ledger declaration: "+row.name);
        const auto& d=*it->second;if(d.kind!=row.kind||d.step!=row.step)throw ProjectError("floorplan declaration kind/step drift: "+row.name);
        if(row.kind=="ASSUME"){
            if(!assumptions.insert(row.name).second)throw ProjectError("duplicate producer assumption "+row.name);
            if(!d.resolve||json(d.resolve())!=json(row.value))throw ProjectError("live assumption differs from producer: "+row.name);
        }else{std::vector<std::string> keys;for(const auto& [name,v]:row.inputs){(void)v;if(name!="label")keys.push_back(name);}
            if(keys!=d.inputs)throw ProjectError("floorplan calculation inputs drift: "+row.name);}
    }
    for(const auto& d:declarations)if(d.kind=="ASSUME"&&(d.step=="floorplan.sizing"||d.step=="sizing.pass")&&!assumptions.count(d.name))
        throw ProjectError("producer omitted declared assumption "+d.name);
    stack.clear();
    for(const auto& row:accounting.decisions){
        const auto depth=static_cast<std::size_t>(row.depth);
        while(stack.size()>depth){ledger.close_step(stack.back());stack.pop_back();}
        if(row.kind=="STEP"){ledger.open_step(row.name,row.value.kind==JsonKind::String?row.value.string_value:"");stack.push_back(row.name);}
        else if(row.kind=="CALC"){std::vector<std::pair<std::string,JsonNode>> inputs;std::string label;
            for(const auto& [name,v]:row.inputs)if(name=="label")label=v.kind==JsonKind::String?v.string_value:json(v);else inputs.emplace_back(name,v);
            ledger.calc(row.name,row.value,inputs,label);}
    }
    while(!stack.empty()){ledger.close_step(stack.back());stack.pop_back();}
}
}
namespace schgen::board_pipeline_detail {
namespace {
void declare_calculation(NativeLedger& ledger,const std::string& name,const std::string& step,
    const std::string& unit,std::vector<std::string> inputs,const std::string& expression,bool repeated=false){
    NativeLedgerDeclaration d;d.name=name;d.kind="CALC";d.step=step;d.unit=unit;d.inputs=std::move(inputs);
    d.expression=expression;d.basis="Actual native board invocation observations";d.repeated=repeated;ledger.declare(std::move(d));
}
void declare_pipeline(NativeLedger& l){
    declare_calculation(l,"sheet_census","netlist","sheets",{"n_sheets","n_som_j","n_decoupling"},"n_sheets - n_som_j - n_decoupling");
    declare_calculation(l,"board_net_census","link","nets",{"n_sheet_nets","n_som_contract_nets","n_cross_sheet"},"len(union(sheet nets, som contract nets))");
    declare_calculation(l,"law5_airwire_measured","gates","mm",{"cross_mm","budget_mm","headroom_mm","n_cross","n_subsystems","board_w","board_h"},"budget_mm = cross_k * (board_w * board_h) ** 0.5 * n_subsystems");
    declare_calculation(l,"fanout_d13_gate","gates","subjects",{"n_subjects","n_starved","baseline"},"starved = clearance < intelligent_need(pins) - touch_eps");
    declare_calculation(l,"quantize_engagement","census","calls",{"klass","value"},"count of calls that ran this registered transform",true);
    declare_calculation(l,"fallback_engagement","census","firings",{"stage","ceiling"},"count of times this registered degraded path bound",true);
    declare_calculation(l,"register_silence","census","registrations",{"quantize_registered","quantize_engaged","fallback_registered","fallback_fired"},"registered - engaged = declared machinery this build never used");
}
void record_pipeline_before(Context& c){
    std::size_t som=0,dec=0;for(const auto& s:c.sheets){som+=s.name.rfind("som_j",0)==0;dec+=s.name=="som_decoupling";}
    c.ledger.open_step("netlist");c.ledger.calc("sheet_census",number(c.sheets.size()-som-dec),{{"n_sheets",number(c.sheets.size())},{"n_som_j",number(som)},{"n_decoupling",number(dec)}});c.ledger.close_step("netlist");
    std::map<std::string,std::size_t> multi;for(const auto& s:c.sheets)for(const auto& n:s.nets)++multi[n.name];
    const auto som_nets=link_som_nets_from_json(parse_json_file(c.paths.som_interface_file.string()));std::set<std::string> all;std::size_t cross=0;
    for(const auto& [name,n]:multi){all.insert(name);cross+=n>=2;}for(const auto& [name,pins]:som_nets){(void)pins;all.insert(name);}
    c.ledger.open_step("link");c.ledger.calc("board_net_census",number(all.size()),{{"n_sheet_nets",number(multi.size())},{"n_som_contract_nets",number(som_nets.size())},{"n_cross_sheet",number(cross)}});c.ledger.close_step("link");
}
void record_pipeline_after(Context& c,const fs::path& baseline){
    if(!c.geometry)throw ProjectError("final gate observations unavailable for ledger");
    const auto& r=c.geometry->ratsnest;const auto& f=c.geometry->fanout;const auto& m=c.pcb->placement.model;
    c.ledger.open_step("gates");c.ledger.calc("law5_airwire_measured",number(py_round(r.cross_mm,1)),{{"cross_mm",number(py_round(r.cross_mm,1))},{"budget_mm",number(py_round(r.cross_budget_mm,1))},{"headroom_mm",number(py_round(r.cross_budget_mm-r.cross_mm,1))},{"n_cross",number(r.n_cross)},{"n_subsystems",number(r.n_subsystems)},{"board_w",number(m.board_w)},{"board_h",number(m.board_h)}});
    c.ledger.calc("fanout_d13_gate",number(f.n_subjects),{{"n_subjects",number(f.n_subjects)},{"n_starved",number(f.n_starved)},{"baseline",number(f.baseline.value_or(-1))}});c.ledger.close_step("gates");
    const auto q=c.quantizations.engagements(),fb=c.fallbacks.census();const auto ceiling=load_fallback_baseline(baseline);
    std::map<std::string,NativeQuantizationDeclaration> qdefs;for(const auto& d:c.quantizations.declarations())qdefs.emplace(d.name,d);
    std::map<std::string,std::string> stages;for(const auto& d:c.options.pipeline_metadata.fallbacks)stages.emplace(d.name,d.stage);
    std::size_t nq=0,nf=0;c.ledger.open_step("census");
    for(const auto& [name,n]:q)if(n.nonzero()){++nq;const auto& d=qdefs.at(name);c.ledger.calc("quantize_engagement",text(n.str()),{{"klass",text(d.proof_class)},{"value",text(d.value.substr(0,std::min<std::size_t>(60,d.value.find('\n'))))}},name);}
    for(const auto& [name,n]:fb)if(n.nonzero()){++nf;if(!stages.count(name))throw ProjectError("missing live fallback stage metadata "+name);
        c.ledger.calc("fallback_engagement",text(n.str()),{{"stage",text(stages.at(name))},{"ceiling",text(!ceiling?"-1":ceiling->count(name)?ceiling->at(name).str():"0")}},name);}
    c.ledger.calc("register_silence",number(q.size()-nq+fb.size()-nf),{{"quantize_registered",number(q.size())},{"quantize_engaged",number(nq)},{"fallback_registered",number(fb.size())},{"fallback_fired",number(nf)}});c.ledger.close_step("census");
}
}
void audit_stages(Context& c){
    const auto fb=c.options.fallback_baseline.empty()?c.paths.reports_dir/"fallback_baseline.json":c.options.fallback_baseline;
    c.attempt("fallbacks",[&]{if(!c.pcb)throw ProjectError("census producer did not finish");const auto r=check_fallback_ratchet(c.fallbacks.census(),fb,c.reports/"fallback_baseline.json");c.report("fallbacks.txt",r.summary());c.gate("fallbacks",r.ok,r.summary());});
    bool imported=false;
    c.attempt("ledger_import",[&]{
        if(c.options.ledger_declarations.empty())throw ProjectError("reviewed native ledger declarations are required; scanner output cannot supply them");
        declare_pipeline(c.ledger);
        for(const auto& d:c.options.ledger_declarations)c.ledger.declare(d);
        if(!c.pcb)throw ProjectError("floorplan accounting unavailable");
        record_pipeline_before(c);
        import_board_floorplan_ledger(c.ledger,c.pcb->placement.floorplan.plan.accounting,c.options.ledger_declarations);
        record_pipeline_after(c,fb);
        imported=true;c.gate("ledger_import",true,"actual floorplan decisions imported once; no geometry replay");});
    c.attempt("quantize_census",[&]{
        if(!imported)throw ProjectError("native ledger import incomplete");
        if(c.options.audit_sources.empty())throw ProjectError("reviewed C++ decision manifest required; no Python audit fallback");
        std::set<std::string> files;for(const auto& f:c.options.audit_sources)files.insert(f.path);
        for(const auto& f:board_pipeline_audit_sources())if(!files.count(f.path))throw ProjectError("board audit manifest omits decision source: "+f.path);
        const auto r=c.measure("source_audit",[&]{return check_native_audits(c.paths.repository_root,c.options.audit_sources,c.ledger,c.quantizations,c.options.audit);});
        c.report("quantize_census.txt",r.summary());c.gate("quantize_census",r.ok,r.summary());c.gate("ledger",r.ok,r.summary());});
    c.attempt("pipeline_doc",[&]{auto meta=c.options.pipeline_metadata;
        if(meta.stages.empty()||meta.fallbacks.empty())throw ProjectError("native stage/fallback metadata manifest is required for pipeline documentation");
        meta.quantization.clear();for(const auto& q:c.quantizations.declarations())meta.quantization.push_back({q.name,q.value,q.proof_class,q.basis});
        const auto r=run_manufacturing_pipeline(meta,c.paths.repository_root,c.docs/"GEOMETRY_PIPELINE.md");c.gate("pipeline_doc",true,r.second?"updated":"unchanged");});
}
}
