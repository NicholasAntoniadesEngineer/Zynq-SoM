#include "board_pipeline_internal.hpp"
#include <cmath>
#include <iomanip>
#include <set>

namespace schgen::board_pipeline_detail {
std::string read(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    if(!f) throw ProjectError("cannot read " + p.string());
    std::string s{std::istreambuf_iterator<char>(f),{}};
    if(f.bad()) throw ProjectError("cannot finish reading " + p.string());
    return s;
}
std::string quote(const std::string& s) {
    std::string out="\""; const char* hex="0123456789abcdef";
    for(unsigned char c:s) {
        if(c=='"'||c=='\\'){out+='\\';out+=static_cast<char>(c);}
        else if(c<32){out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}
        else out+=static_cast<char>(c);
    }
    return out+'"';
}
std::string json(const JsonNode& n) {
    switch(n.kind) {
    case JsonKind::Null:return "null";
    case JsonKind::String:return quote(n.string_value);
    case JsonKind::Bool:return n.bool_value?"true":"false";
    case JsonKind::Number:{if(!std::isfinite(n.number_value))throw ProjectError("nonfinite JSON number");
        std::ostringstream o;o.imbue(std::locale::classic());o<<std::setprecision(17)<<n.number_value;return o.str();}
    case JsonKind::Array:{std::string s="[";for(const auto& v:n.array_value){if(s.size()>1)s+=',';s+=json(v);}return s+']';}
    case JsonKind::Object:{std::string s="{";for(const auto& [k,v]:n.object_value){if(s.size()>1)s+=',';s+=quote(k)+':'+json(v);}return s+'}';}
    }
    throw ProjectError("invalid JSON kind");
}
JsonNode number(double v){JsonNode n;n.kind=JsonKind::Number;n.number_value=v;return n;}
JsonNode text(std::string v){JsonNode n;n.kind=JsonKind::String;n.string_value=std::move(v);return n;}
std::string join(const std::vector<std::string>& values,const std::string& separator){
    std::string out;for(const auto& v:values){if(!out.empty())out+=separator;out+=v;}return out;
}
Context::Context(const ProjectPaths& p,const BoardPipelineOptions& o):paths(p),options(o),
    out(o.output_root.empty()?p.project_root:fs::absolute(o.output_root)),reports(out/"reports"),docs(out/"docs"),
    renders(out/"renders"),manufacturing(out/"manufacturing"),library(p.repository_root),inbox(quantizations,fallbacks) {
    result.output_root=out;
    for(const auto& d:{out,reports,docs,renders,manufacturing,out/"fpga",out/"firmware"})fs::create_directories(d);
    register_native_quantizations(quantizations);register_native_fallbacks(fallbacks);
}
void Context::status(const std::string& name,BoardGateStatus s,const std::string& value){
    if(std::any_of(result.gates.begin(),result.gates.end(),[&](const auto& g){return g.name==name;}))
        throw ProjectError("duplicate board gate: "+name);
    const bool hard=name=="contract_coverage_lint"?options.enforce_coverage_lint:board_pipeline_gate_mandatory(name);
    result.gates.push_back({name,hard,s,value});
    if(options.progress)options.progress(name+": "+value);
}
void Context::gate(const std::string& name,bool ok,const std::string& value){status(name,ok?BoardGateStatus::passed:BoardGateStatus::failed,value);}
void Context::report(const std::string& name,const std::string& value){publish_text(reports/name,value+"\n");}
}
namespace schgen {
namespace {
const char* status_name(BoardGateStatus s){switch(s){case BoardGateStatus::passed:return "PASS";case BoardGateStatus::failed:return "FAIL";case BoardGateStatus::skipped:return "SKIP";case BoardGateStatus::unavailable:return "UNAVAILABLE";}throw ProjectError("invalid board gate status");}
const std::vector<std::string> required={"inputs","subsystem_structure","carrier_structure","sheet_gates","cc","symbol_law","link","board_schematic","constraints","diagram","bom_footprints","power_tree","rail_ampacity","testpoints","design_rules","part_rules","bom_values","footprint_pads","spice","pcb","pcb_drc","pcb_geometry","assembly","thermal","copper_debt","fab_profile","xdc","vivado","firmware","manual","testplan","gallery","devicetree","scfw","power_sequence","floorplan","quantize_census","fallbacks","stage_movement","pipeline_doc","model3d","si","manifest","ledger"};
}
bool board_pipeline_gate_mandatory(const std::string& name){
    static const std::set<std::string> advisory={"pin_completeness","contract_coverage","contract_coverage_lint","floorplan_composition","return_path","cpl","render3d","golden","sheet_render","root_erc","ratsnest_images"};
    return !advisory.count(name);
}
bool BoardPipelineResult::complete() const {
    for(const auto& name:required)if(std::none_of(gates.begin(),gates.end(),[&](const auto& g){return g.name==name;}))return false;
    return !gates.empty()&&std::none_of(gates.begin(),gates.end(),[](const auto& g){return g.status==BoardGateStatus::unavailable;});
}
bool BoardPipelineResult::ok() const {
    std::set<std::string> seen;
    for(const auto& g:gates){if(!seen.insert(g.name).second)return false;
        if((g.mandatory||board_pipeline_gate_mandatory(g.name)) && g.status!=BoardGateStatus::passed && !(g.status==BoardGateStatus::skipped&&(g.name=="manual"||g.name=="scfw")))return false;}
    for(const auto& name:required)if(!seen.count(name))return false;
    return sheets>0;
}
std::string BoardPipelineResult::report() const {
    std::string s;for(const auto& g:gates)s+=g.name+": "+status_name(g.status)+(g.mandatory?"":" (advisory)")+" — "+g.report+"\n";
    if(!timing_seconds.empty()){s+="\n=== board native phase timing (wall s) ===\n";for(const auto& [name,seconds]:timing_seconds)s+=name+": "+std::to_string(seconds)+"\n";}
    return s+"BOARD: "+(ok()?"PASS":"FAIL")+" ("+std::to_string(sheets)+" sheets)\n";
}
std::string board_pipeline_verdict_json(const BoardPipelineResult& r){
    using board_pipeline_detail::quote;
    std::string s="{\n \"board_ok\": "+std::string(r.ok()?"true":"false")+",\n \"complete\": "+(r.complete()?"true":"false")+",\n \"gates\": {";
    bool first=true;for(const auto& g:r.gates){s+=first?"\n":",\n";first=false;s+="  "+quote(g.name)+": {\"status\": "+quote(status_name(g.status))+", \"mandatory\": "+(g.mandatory?"true":"false")+", \"report\": "+quote(g.report)+"}";}
    s+="\n },\n \"quantization\": {";first=true;for(const auto& [k,v]:r.quantization){if(!first)s+=',';first=false;s+=quote(k)+':'+v.str();}
    s+="},\n \"fallbacks\": {";first=true;for(const auto& [k,v]:r.fallbacks){if(!first)s+=',';first=false;s+=quote(k)+':'+v.str();}
    return s+"}\n}\n";
}
std::string board_pipeline_experiment_json(const BoardPipelineResult& r){
    using namespace board_pipeline_detail;
    std::map<std::string,std::string> fields;
    const auto floating=[](double value){auto text=json(number(value));
        if(text.find_first_of(".eE")==std::string::npos)text+=".0";return text;};
    if(r.measurements){
        const auto& m=*r.measurements;
        fields.emplace("board_w",floating(m.board_w));fields.emplace("board_h",floating(m.board_h));
        fields.emplace("ratsnest","{\"cross_mm\":"+floating(m.cross_mm)+",\"n_bottom\":"+
            std::to_string(m.n_bottom)+",\"n_top\":"+std::to_string(m.n_top)+"}");
    }
    std::string fallbacks="{";
    for(const auto& [name,count]:r.fallbacks){if(fallbacks.size()>1)fallbacks+=',';fallbacks+=quote(name)+':'+count.str();}
    fields.emplace("fallbacks",fallbacks+'}');
    // Historical diagnostic scope; the complete native gate map remains in
    // board_verdicts.json. Do not turn optional render skips into new reds.
    const std::set<std::string> diagnostic_gates={"assembly","connector_model","connector_spacing",
        "escape_lanes","fallbacks","fanout","placement_contract","placement_flow","placement_mech",
        "quantize_census","ratsnest","refdes_silk","return_path","return_stitch"};
    for(const auto& gate:r.gates){
        if(!diagnostic_gates.count(gate.name))continue;
        const auto name=gate.name=="ratsnest"?"ratsnest_gate":gate.name=="fallbacks"?"fallback_gate":gate.name;
        if(!fields.emplace(name,std::string("{\"ok\":")+(gate.status==BoardGateStatus::passed?"true}":"false}")).second)
            throw ProjectError("duplicate experiment measurement key "+name);
    }
    std::string document="{";
    for(const auto& [name,value]:fields){if(document.size()>1)document+=',';document+=quote(name)+':'+value;}
    return document+"}\n";
}
BoardPipelineResult run_board_pipeline(const ProjectPaths& p,const BoardPipelineOptions& o){
    using namespace board_pipeline_detail;
    Context c(p,o);
    c.attempt("inputs",[&]{c.authored=author_board_pipeline_inputs(p);publish_board_pipeline_inputs(*c.authored,p,c.out);c.circuits=c.authored->circuits;
        std::vector<std::string> names;for(const auto& sc:c.circuits){c.sheets.push_back(sc.circuit);names.push_back(sc.name);}
        c.index=extend_sheet_index(load_sheet_index(p),names).index;c.result.sheets=c.sheets.size();c.loaded=true;c.gate("inputs",true,"live C++ factories authored once; canonical snapshots published; actual IR retained");});
    if(c.loaded){schematic_stage(c);electrical_stages(c);pcb_stages(c);document_stages(c);audit_stages(c);}
    for(const auto& name:required)if(std::none_of(c.result.gates.begin(),c.result.gates.end(),[&](const auto& g){return g.name==name;}))c.gate(name,false,"stage did not run; prerequisite unavailable");
    c.result.quantization=c.quantizations.engagements();c.result.fallbacks=c.fallbacks.census();c.result.ledger=c.ledger.render();
    if(c.pcb&&c.geometry){const auto& model=c.pcb->placement.model;
        c.result.measurements=BoardPipelineResult::Measurements{model.board_w,model.board_h,
            c.geometry->ratsnest.cross_mm,model.n_top,model.n_bottom};}
    c.report("build_ledger.txt",c.result.ledger);publish_text(c.reports/"gates.txt",c.result.report());
    publish_text(c.reports/"board_verdicts.json",board_pipeline_verdict_json(c.result));
    publish_text(c.reports/"experiment_verdicts.json",board_pipeline_experiment_json(c.result));
    return std::move(c.result);
}
}
