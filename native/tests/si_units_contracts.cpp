// Independent repository policy from test_si_units.py, not a second SI engine.
// Fresh native authoring -> real research -> actual CSV/DRU/Markdown consumers.
// No Python, saved circuit.json, generated board, subprocess, or output writes.
#include "schgen/manufacturing_exports.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>

namespace {
using namespace schgen;
using Findings = std::set<std::string>;
std::size_t checks = 0, mutations = 0;
void require(bool value, const std::string& why) {
    ++checks; if (!value) throw std::runtime_error(why);
}
struct Figure { const char* net; double mil, mm; const char* cite; };
// Literal independent expectations transcribed from the original test, never
// calculated by the native converter or copied from generated output.
const std::vector<Figure> figures{
    {"FMC_CLK0_M2C_P",5,.127,"VITA 57.1"}, {"FMC_LA11_N",5,.127,"VITA 57.1"},
    {"CAM_CLK_P",20,.508,"D-PHY"}, {"CAM_D1_N",20,.508,"D-PHY"},
    {"ETH_PHY_MDI0_P",50,1.27,"802.3"}, {"ETH_LINE_MDI_3_N",50,1.27,"802.3"},
    {"HDMI_RX_D2_P",118,2.9972,"HDMI 1.4b"},
    {"ZYNQ_HDMI_TX_TMDS_CLK_N",118,2.9972,"HDMI 1.4b"},
    {"USB_D+",150,3.81,"USB 2.0"}, {"DBG_USB_DM",150,3.81,"USB-IF"}};
const PairSignalSpec* find(const std::vector<PairSignalSpec>& specs, const std::string& net) {
    const auto it=std::find_if(specs.begin(),specs.end(),[&](const auto& p){return p.net_p==net||p.net_n==net;});
    return it==specs.end()?nullptr:&*it;
}
PairSignalSpec& edit(std::vector<PairSignalSpec>& specs, const std::string& net) {
    for(auto& p:specs)if(p.net_p==net||p.net_n==net)return p;
    throw std::runtime_error("missing mutable pair: "+net);
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* p=object_field(n,key);require(p!=nullptr,"missing JSON field: "+key);return *p;
}
JsonNode& edit(JsonNode& n, const std::string& key) {
    for(auto& [k,v]:n.object_value)if(k==key)return v;
    throw std::runtime_error("missing mutable JSON field: "+key);
}
bool pair_kind(const std::string& k) { return k=="diff_pair"||k=="tmds_pair"||k=="usb_hs_pair"; }
Findings research_policy(const std::vector<PairSignalSpec>& specs,const JsonNode& raw) {
    Findings out;
    for(const auto& f:figures){
        const auto* p=find(specs,f.net);
        if(!p){out.insert("cited-population");continue;}
        if(p->intra_pair_skew_mil!=f.mil||p->intra_pair_skew_mm()!=f.mm)out.insert("cited-length");
        if(p->spec_cite.find(f.cite)==std::string::npos)out.insert("citation");
    }
    const auto* tmds=find(specs,"ZYNQ_HDMI_TX_TMDS_2_P");
    if(!tmds||tmds->intra_pair_skew_mm()!=2.9972||
       tmds->intra_pair_skew_mm()<=19*.15||tmds->spec_cite.find("0.15")==std::string::npos)
        out.insert("dimensionless-is-not-length");
    for(const auto& p:specs){
        if(p.match_tol_mil!=p.intra_pair_skew_mil)out.insert("group-policy");
        if(p.net_p.rfind("SD_",0)==0)out.insert("sd-is-uncited");
    }
    for(const auto& row:field(raw,"single_ended").array_value){
        const auto& len=field(row,"max_len_mil");const auto* note=object_field(row,"max_len_mil_note");
        if(len.kind!=JsonKind::Number||!(len.number_value>0||
           (note&&note->kind==JsonKind::String&&note->string_value=="n/a")))out.insert("unavailable-length");
    }
    return out;
}
// Small test-only CSV reader, including quoted commas/newlines/doubled quotes.
// This parses emitted evidence; it does not generate layout constraints.
using Rows = std::vector<std::vector<std::string>>;
Rows csv(const std::string& s) {
    Rows rows;std::vector<std::string> row;std::string cell;bool quoted=false;
    for(std::size_t i=0;i<s.size();++i){const auto c=s[i];
        if(c=='"'){
            if(quoted&&i+1<s.size()&&s[i+1]=='"'){cell+='"';++i;}else quoted=!quoted;
        }else if(!quoted&&(c==','||c=='\n')){
            if(c=='\n'&&!cell.empty()&&cell.back()=='\r')cell.pop_back();
            row.push_back(cell);cell.clear();if(c=='\n'){rows.push_back(row);row.clear();}
        }else cell+=c;
    }
    require(!quoted&&row.empty()&&cell.empty(),"unterminated CSV output");return rows;
}
struct Outputs { Rows csv_rows; std::string dru, md; };
Outputs outputs(const std::vector<ProjectCircuit>& sheets,const std::vector<PairSignalSpec>& specs,
                const SiConstraintsModel& model) {
    return {csv(generate_layout_constraints(sheets,specs,"independent SI contract").csv),
            render_si_design_rules(model),render_si_markdown(model)};
}
std::string line_with(const std::string& doc,const std::string& needle) {
    const auto at=doc.find(needle);if(at==std::string::npos)return {};
    const auto begin=doc.rfind('\n',at),end=doc.find('\n',at);
    return doc.substr(begin==std::string::npos?0:begin+1,
        (end==std::string::npos?doc.size():end)-(begin==std::string::npos?0:begin+1));
}
Findings consumer_policy(const std::vector<PairSignalSpec>& specs,const SiConstraintsModel& model,
                         const Outputs& out) {
    Findings errors;std::size_t n=0;std::set<std::string> seen;
    const std::vector<std::string> header{"net","sheet","kind","net_class","impedance_ohm",
        "track_width_mm","pair_gap_mm","pair_with","length_match_group","match_tolerance_mm","notes"};
    if(out.csv_rows.empty()||out.csv_rows.front()!=header){errors.insert("csv-schema");return errors;}
    std::map<std::string,std::set<double>> budgets;
    for(std::size_t i=1;i<out.csv_rows.size();++i){const auto& r=out.csv_rows[i];
        if(r.size()!=header.size()){errors.insert("csv-schema");continue;}
        if(r[2]=="sd_bus"&&r[7].empty()&&r[9]!="2.5")errors.insert("sd-policy");
        if(!pair_kind(r[2])||r[7].empty())continue;
        ++n;seen.insert(r[0]);const auto* p=find(specs,r[0]);
        if(!p){errors.insert("csv-research");continue;}
        if(!find(model.pairs,r[0]))errors.insert("si-model-population");
        budgets[r[2]].insert(p->intra_pair_skew_mm());
        std::size_t end=0;double value=0;
        try{value=std::stod(r[9],&end);}catch(const std::exception&){errors.insert("csv-length");}
        if(end!=r[9].size()||value!=p->intra_pair_skew_mm())errors.insert("csv-length");
        if(r[10].find(p->spec_cite)==std::string::npos)errors.insert("csv-citation");
    }
    if(n!=148)errors.insert("pair-row-census");
    const std::map<std::string,std::set<double>> expected{
        {"diff_pair",{.127,.508,1.27}},{"tmds_pair",{2.9972}},{"usb_hs_pair",{3.81}}};
    if(budgets!=expected)errors.insert("no-per-kind-budget");
    for(const auto& p:model.pairs){
        if(!seen.count(p.net_p)||!seen.count(p.net_n))errors.insert("csv-pair-halves");
        // Locate the actual pair-specific condition, not a same-valued rule for
        // some other pair. Read the number from that rule independently.
        const auto at=out.dru.find("(condition \"(A.NetName == '"+p.net_p+"' && B.NetName == '"+p.net_n+"')");
        const auto number=at==std::string::npos?std::string::npos:out.dru.find("(constraint skew (max ",at);
        if(number==std::string::npos)errors.insert("dru-pair");
        else if(std::stod(out.dru.substr(number+22))!=p.intra_pair_skew_mm())errors.insert("dru-length");
        const auto line=line_with(out.md,"| `"+p.net_p+"` | `"+p.net_n+"` |");
        const auto mm=line.find(" mil (");
        if(mm==std::string::npos)errors.insert("markdown-pair");
        else if(std::stod(line.substr(mm+6))!=p.intra_pair_skew_mm())errors.insert("markdown-length");
        if(line.find(p.spec_cite)==std::string::npos)errors.insert("markdown-citation");
    }
    for(const auto& g:model.groups){
        if(g.members.empty()){errors.insert("group-minimum");continue;}
        const auto it=std::min_element(g.members.begin(),g.members.end(),
            [](const auto& a,const auto& b){return a.intra_pair_skew_mil<b.intra_pair_skew_mil;});
        if(g.tol_mil!=it->intra_pair_skew_mil)errors.insert("group-minimum");
    }
    return errors;
}
void killed(const Findings& errors,const std::string& code) {
    ++mutations;require(errors.count(code)!=0,"mutation survived: "+code);
}
void replace_once(std::string& s,const std::string& from,const std::string& to) {
    const auto at=s.find(from);require(at!=std::string::npos,"mutation target absent: "+from);s.replace(at,from.size(),to);
}
void mutations_for(const std::vector<ProjectCircuit>& sheets,const JsonNode& raw,
                   const std::vector<PairSignalSpec>& specs,const SiConstraintsModel& model,const Outputs& out) {
    for(const auto& f:figures){
        auto changed=specs;edit(changed,f.net).intra_pair_skew_mil=f.mm;
        killed(research_policy(changed,raw),"cited-length");
        // All consumers may agree on a wrong unit: independent figures must
        // still kill it, rather than accepting tautological cross-consistency.
        const auto poisoned=build_si_constraints(sheets,changed);
        (void)outputs(sheets,changed,poisoned);
        changed=specs;edit(changed,f.net).spec_cite="uncited";
        killed(research_policy(changed,raw),"citation");
        changed=specs;const auto net=std::string(f.net);
        changed.erase(std::remove_if(changed.begin(),changed.end(),[&](const auto& p){return p.net_p==net||p.net_n==net;}),changed.end());
        killed(research_policy(changed,raw),"cited-population");
        require(!check_si_constraints(build_si_constraints(sheets,changed)).ok,"missing researched pair passed actual SI gate");
        bool rejected=false;try{(void)generate_layout_constraints(sheets,changed,"missing targets");}
        catch(const ProjectError& e){rejected=std::string(e.what()).find("no per-kind default")!=std::string::npos;}
        require(rejected,"missing pair accepted by actual CSV generator");
    }
    auto changed=specs;edit(changed,"ZYNQ_HDMI_TX_TMDS_2_P").intra_pair_skew_mil=.15;
    killed(research_policy(changed,raw),"dimensionless-is-not-length");
    changed=specs;changed.front().match_tol_mil+=1;killed(research_policy(changed,raw),"group-policy");
    changed=specs;changed.front().net_p="SD_FAKE_P";killed(research_policy(changed,raw),"sd-is-uncited");
    auto altered=raw;auto& rows=edit(altered,"single_ended").array_value;require(!rows.empty(),"single-ended census empty");
    auto& row=rows.front();edit(row,"max_len_mil").number_value=0;
    row.object_value.erase(std::remove_if(row.object_value.begin(),row.object_value.end(),
        [](const auto& item){return item.first=="max_len_mil_note";}),row.object_value.end());
    killed(research_policy(specs,altered),"unavailable-length");
    JsonNode note;note.kind=JsonKind::String;note.string_value="n/a";row.object_value.emplace_back("max_len_mil_note",note);
    require(research_policy(specs,altered).empty(),"explicit unavailable length must pass");
    auto broken=out;broken.csv_rows.front().pop_back();killed(consumer_policy(specs,model,broken),"csv-schema");
    broken=out;auto pair=std::find_if(broken.csv_rows.begin()+1,broken.csv_rows.end(),
        [](const auto& r){return pair_kind(r[2])&&!r[7].empty();});
    require(pair!=broken.csv_rows.end(),"CSV pairs absent");const auto i=static_cast<std::size_t>(pair-broken.csv_rows.begin());
    broken.csv_rows[i][9]="0.15";killed(consumer_policy(specs,model,broken),"csv-length");
    broken=out;broken.csv_rows[i][10]="lost citation";killed(consumer_policy(specs,model,broken),"csv-citation");
    broken=out;broken.csv_rows[i][0]="NOT_RESEARCHED_P";
    killed(consumer_policy(specs,model,broken),"csv-research");
    broken=out;broken.csv_rows.erase(broken.csv_rows.begin()+static_cast<std::ptrdiff_t>(i));
    killed(consumer_policy(specs,model,broken),"pair-row-census");
    broken=out;const auto lost=model.pairs.front().net_n;
    broken.csv_rows.erase(std::remove_if(broken.csv_rows.begin()+1,broken.csv_rows.end(),
        [&](const auto& r){return r[0]==lost;}),broken.csv_rows.end());
    killed(consumer_policy(specs,model,broken),"csv-pair-halves");
    broken=out;const auto sd=std::find_if(broken.csv_rows.begin()+1,broken.csv_rows.end(),[](const auto& r){return r[2]=="sd_bus"&&r[7].empty();});
    require(sd!=broken.csv_rows.end(),"SD policy census empty");(*sd)[9]="0.15";
    killed(consumer_policy(specs,model,broken),"sd-policy");
    broken=out;replace_once(broken.dru,"(constraint skew (max 0.127mm))","(constraint skew (max 0.15mm))");
    killed(consumer_policy(specs,model,broken),"dru-length");
    broken=out;broken.dru.clear();killed(consumer_policy(specs,model,broken),"dru-pair");
    broken=out;replace_once(broken.md,"mil (0.127 mm)","mil (0.15 mm)");
    killed(consumer_policy(specs,model,broken),"markdown-length");
    broken=out;replace_once(broken.md,model.pairs.front().spec_cite,"missing citation");
    killed(consumer_policy(specs,model,broken),"markdown-citation");
    broken=out;broken.md.clear();killed(consumer_policy(specs,model,broken),"markdown-pair");
    auto altered_model=model;altered_model.groups.front().tol_mil+=1;
    killed(consumer_policy(specs,altered_model,out),"group-minimum");
    altered_model=model;altered_model.pairs.clear();
    killed(consumer_policy(specs,altered_model,out),"si-model-population");
    changed=specs;for(auto& p:changed)if(p.intra_pair_skew_mil==5)p.intra_pair_skew_mil=20;
    killed(consumer_policy(changed,build_si_constraints(sheets,changed),out),"no-per-kind-budget");
    changed=specs;changed.front().z_diff_ohm+=1;
    require(!check_si_constraints(build_si_constraints(sheets,changed)).ok,"actual impedance gate accepted divergence");
    // Positive control: genuinely changed live research must flow through every
    // consumer. This is a parameter test, not approval to change repository policy.
    changed=specs;auto& varied=edit(changed,"FMC_CLK0_M2C_P");varied.intra_pair_skew_mil=4;varied.match_tol_mil=4;
    const auto live=build_si_constraints(sheets,changed);const auto emitted=outputs(sheets,changed,live);
    const auto group=std::find_if(live.groups.begin(),live.groups.end(),[&](const auto& g){return g.interface==varied.interface;});
    require(group!=live.groups.end()&&group->members.size()>1&&group->tol_mil==4,"live heterogeneous group minimum");
    require(varied.intra_pair_skew_mm()==.1016&&emitted.dru.find("(max 0.1016mm)")!=std::string::npos&&
        emitted.md.find("mil (0.1016 mm)")!=std::string::npos,"changed research did not reach native documents");
    bool changed_csv=false;for(const auto& r:emitted.csv_rows)if(r[0]==varied.net_p){changed_csv=true;require(r[9]=="0.1016","changed research absent from CSV");}
    require(changed_csv,"changed pair missing from CSV");
}
} // namespace
int main(int argc,char** argv) {
    try{
        require(argc==2,"usage: si_units_contracts REPOSITORY");const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"real native part catalog unavailable");
        struct Close { ~Close(){close_part_catalog();} } close;
        std::size_t lookups=0;ProjectAuthoringInput author;author.project_root=root/"carrier";
        author.context.part=[&](const std::string& name){++lookups;return lookup_part_catalog(name);};
        std::vector<ProjectCircuit> sheets;for(const auto& f:native_project_factories("carrier",author))
            sheets.push_back({f.name,{},f.circuit()});
        require(sheets.size()==37&&lookups>0,"fresh native carrier factory/catalog census");
        const auto raw=parse_json_file((root/"carrier/research/si_spec.json").string());const auto specs=parse_signal_specs(raw);
        require(research_policy(specs,raw).empty(),"real SI research violates independent policy");
        const auto model=build_si_constraints(sheets,specs);require(check_si_constraints(model).ok,"fresh native declared/researched SI gate");
        const auto out=outputs(sheets,specs,model);
        const auto findings=consumer_policy(specs,model,out);
        require(findings.empty(),"native SI consumer policy failed: "+(findings.empty()?std::string{}:*findings.begin()));
        mutations_for(sheets,raw,specs,model,out);
        require(research_policy(specs,raw).empty()&&consumer_policy(specs,model,out).empty(),"mutations altered originals");
        std::cout<<"PASS: "<<checks<<" SI policy assertions, "<<mutations<<" rejected mutations, 37 fresh circuits, 148 emitted pair rows\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
