// Repository policy contracts, not a replacement placement/flow geometry gate.
// Port of the non-geometric policies in test_lightweight_contracts.py and
// test_hs_family_contracts.py. Production authoring, catalogs and JSON are real;
// no Python, saved circuit JSON, board snapshot or geometry result is used.
#include "schgen/project.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0, mutations = 0;
void require(bool value, const std::string& why) {
    ++checks; if (!value) throw std::runtime_error(why);
}
const std::vector<std::string> lightweight{
    "lcd", "microsd", "uart_bridge", "usb_jtag", "usbc_otg", "pd_input", "pmod"};
const std::vector<std::string> critical{"hdmi_tx", "camera", "hdmi_rx_term"};
const std::set<std::string> known{
    "hot_loop", "bulk_in", "bulk_out", "sw_node", "fb_cluster", "boot",
    "vcc_cap", "bias_cap", "rt_r", "ldo_stage", "proximity", "same_side"};
const JsonNode null;
const JsonNode& get(const JsonNode& n, const std::string& key) {
    if (n.kind != JsonKind::Object) return null;
    if (const auto* p = object_field(n, key)) return *p;
    return null;
}
bool string(const JsonNode& n, const std::string& s) {
    return n.kind == JsonKind::String && n.string_value == s;
}
bool nonblank(const JsonNode& n) {
    return n.kind == JsonKind::String && n.string_value.find_first_not_of(" \t\r\n\f\v") != std::string::npos;
}
JsonNode text(const std::string& s) { JsonNode n; n.kind=JsonKind::String; n.string_value=s; return n; }
JsonNode number(double v) { JsonNode n; n.kind=JsonKind::Number; n.number_value=v; return n; }
JsonNode object() { JsonNode n; n.kind=JsonKind::Object; return n; }
JsonNode array(std::initializer_list<JsonNode> values = {}) {
    JsonNode n; n.kind=JsonKind::Array; n.array_value=values; return n;
}
void set(JsonNode& n, const std::string& key, JsonNode value) {
    require(n.kind==JsonKind::Object, "mutation target is not object: "+key);
    for (auto& [k,v]:n.object_value) if(k==key) { v=std::move(value); return; }
    n.object_value.emplace_back(key,std::move(value));
}
void erase(JsonNode& n, const std::string& key) {
    require(n.kind==JsonKind::Object,"erase target is not object");
    const auto before=n.object_value.size();
    n.object_value.erase(std::remove_if(n.object_value.begin(),n.object_value.end(),
        [&](const auto& row){return row.first==key;}),n.object_value.end());
    require(n.object_value.size()+1==before,"mutation did not erase exactly one "+key);
}
JsonNode& edit(JsonNode& n,const std::string& key) {
    for(auto& [k,v]:n.object_value)if(k==key)return v;
    throw std::runtime_error("missing mutable field "+key);
}
struct Input {
    std::string sheet;
    bool light = false;
    JsonNode contract;
    CircuitSheetIr circuit;
    std::set<std::string> wired;
};
using Findings = std::set<std::string>;
// This assertion helper deliberately takes caller-owned values: mutations of
// either authored IR or JSON must be observed, not reloaded from a baseline.
Findings policy(const Input& in) {
    Findings out;
    const auto demand=[&](bool ok,const std::string& code){if(!ok)out.insert(code);};
    demand(in.wired.count(in.sheet)!=0,"wired");
    demand(in.circuit.name==in.sheet,"circuit-identity");
    const auto& c=in.contract;
    if(c.kind!=JsonKind::Object){out.insert("contract-object");return out;}
    demand(string(get(c,"sheet"),in.sheet),"sheet");
    if(in.light){
        demand(string(get(c,"subsystem"),in.sheet),"subsystem");
        demand(string(get(c,"tier"),"lightweight"),"lightweight-tier");
    }else{
        demand(string(get(c,"contract"),"placement/v2"),"critical-version");
        demand(!string(get(c,"tier"),"lightweight"),"critical-tier");
        const auto& cites=get(c,"citations");
        demand(cites.kind==JsonKind::Array&&!cites.array_value.empty(),"citations");
        for(const auto& cite:cites.array_value)demand(nonblank(cite),"citations");
    }
    std::map<std::string,const CircuitPartIr*> parts;
    for(const auto& p:in.circuit.parts)parts.emplace(p.ref,&p);
    const auto reference=[&](const JsonNode& ref){
        demand(nonblank(ref)&&parts.count(ref.string_value)!=0,"reference");
    };
    const auto& roles=get(c,"roles");
    demand(roles.kind==JsonKind::Null||roles.kind==JsonKind::Object,"roles-shape");
    for(const auto& [ref,value]:roles.object_value){(void)value;reference(text(ref));}
    const auto& structures=get(c,"structures");
    demand(structures.kind==JsonKind::Array&&!structures.array_value.empty(),"structures");
    std::vector<const JsonNode*> crystals;
    for(const auto& s:structures.array_value){
        if(s.kind!=JsonKind::Object){out.insert("structure-object");continue;}
        const auto& type=get(s,"type");
        demand(type.kind==JsonKind::String&&(in.light?
            type.string_value=="proximity"||type.string_value=="same_side":known.count(type.string_value)!=0),"structure-type");
        const auto& basis=get(s,"basis");
        demand(nonblank(basis),"structure-basis");
        if(in.light)demand(basis.kind==JsonKind::String&&basis.string_value.find("judgment")!=std::string::npos,"judgment");
        for(const auto* key:{"anchor","ic","inductor","cap","resistor","cin","cout"}){
            const auto& ref=get(s,key);if(ref.kind!=JsonKind::Null)reference(ref);
        }
        for(const auto* key:{"members","caps","ics"}){
            const auto& refs=get(s,key);
            demand(refs.kind==JsonKind::Null||refs.kind==JsonKind::Array,"references-shape");
            for(const auto& ref:refs.array_value)reference(ref);
        }
        const auto& from=get(s,"min_from");
        demand(from.kind==JsonKind::Null||from.kind==JsonKind::Array,"min-from-shape");
        for(const auto& row:from.array_value){
            demand(row.kind==JsonKind::Object,"min-from-shape");
            if(get(row,"part").kind!=JsonKind::Null)reference(get(row,"part"));
        }
        if(in.light&&string(type,"proximity")){
            demand(nonblank(get(s,"anchor")),"proximity-anchor");
            const auto& members=get(s,"members");
            demand(members.kind==JsonKind::Array&&!members.array_value.empty(),"proximity-members");
            for(const auto& ref:members.array_value)demand(ref.kind==JsonKind::String,"proximity-members");
            const auto& mm=get(s,"max_mm");
            demand(mm.kind==JsonKind::Number&&std::isfinite(mm.number_value)&&mm.number_value>0,"proximity-distance");
        }
        if(in.light&&string(type,"same_side")){
            const auto& ics=get(s,"ics");
            demand(ics.kind==JsonKind::Array&&!ics.array_value.empty(),"same-side-ics");
        }
        // Symbol/dossier pin membership is a netlist policy, distinct from the
        // existing geometry gate's footprint-pad and placed-coordinate checks.
        const auto& pins=get(s,"anchor_pins");
        if(in.light&&pins.kind!=JsonKind::Null){
            demand(pins.kind==JsonKind::Array,"anchor-pins");
            const auto part=parts.find(get(s,"anchor").string_value);
            if(!pins.array_value.empty()){
                demand(part!=parts.end()&&!part->second->pin_numbers.empty(),"anchor-pin-table");
                for(const auto& pin:pins.array_value)demand(pin.kind==JsonKind::String&&part!=parts.end()&&
                    std::find(part->second->pin_numbers.begin(),part->second->pin_numbers.end(),pin.string_value)!=part->second->pin_numbers.end(),"anchor-pins");
            }
        }
        const auto& members=get(s,"members");
        if(string(type,"proximity")&&members.kind==JsonKind::Array&&members.array_value.size()==1&&string(members.array_value[0],"Y1"))
            crystals.push_back(&s);
    }
    const auto& external=get(c,"external");
    demand(external.kind==JsonKind::Null||external.kind==JsonKind::Object,"external-shape");
    if(in.light)for(const auto& [key,value]:external.object_value){
        (void)value;demand(key=="near_max","lightweight-external");
    }
    if(!in.light)for(const auto* key:{"near_max","far"}){
        const auto& terms=get(external,key);
        demand(terms.kind==JsonKind::Null||terms.kind==JsonKind::Array,"external-terms");
        for(const auto& term:terms.array_value)
            demand(term.kind==JsonKind::Object&&nonblank(get(term,"basis")),"external-basis");
    }
    if(in.sheet=="usb_jtag"){
        demand(crystals.size()==1,"crystal-count");
        if(crystals.size()==1){
            const auto& s=*crystals.front();
            demand(string(get(s,"anchor"),"U1"),"crystal-anchor");
            const auto& pins=get(s,"anchor_pins");std::vector<std::string> names;
            for(const auto& pin:pins.array_value)if(pin.kind==JsonKind::String)names.push_back(pin.string_value);
            std::sort(names.begin(),names.end());
            demand(pins.kind==JsonKind::Array&&pins.array_value.size()==2&&names==std::vector<std::string>{"19","20"},"crystal-pins");
            const auto& mm=get(s,"max_mm");demand(mm.kind==JsonKind::Number&&mm.number_value==5.0,"crystal-distance");
            const auto& basis=get(s,"basis");demand(basis.kind==JsonKind::String&&basis.string_value.find("crystal")!=std::string::npos,"crystal-basis");
        }
    }
    return out;
}
std::set<std::string> exercised;
void reject(const Input& original,const std::string& code,const std::function<void(Input&)>& mutate){
    auto in=original;mutate(in);const auto failures=policy(in);++mutations;
    require(failures.count(code)!=0,original.sheet+": mutant did not trip "+code);
    exercised.insert(code);
}
JsonNode& first(Input& in,const std::string& type="proximity"){
    for(auto& s:edit(in.contract,"structures").array_value)if(string(get(s,"type"),type))return s;
    throw std::runtime_error("fixture lacks "+type);
}
JsonNode& crystal(Input& in){
    for(auto& s:edit(in.contract,"structures").array_value){
        const auto& m=get(s,"members");
        if(m.kind==JsonKind::Array&&m.array_value.size()==1&&string(m.array_value[0],"Y1"))return s;
    }
    throw std::runtime_error("no original crystal structure");
}
void mutation_contracts(const Input& in){
    reject(in,"wired",[](auto& x){x.wired.erase(x.sheet);});
    reject(in,"sheet",[](auto& x){set(x.contract,"sheet",text("wrong"));});
    reject(in,"circuit-identity",[](auto& x){x.circuit.name="wrong";});
    reject(in,"contract-object",[](auto& x){x.contract=array();});
    reject(in,"structures",[](auto& x){set(x.contract,"structures",array());});
    reject(in,"structure-object",[](auto& x){edit(x.contract,"structures").array_value[0]=text("bad");});
    reject(in,"structure-type",[](auto& x){set(first(x),"type",text("unimplemented"));});
    const auto& structures=get(in.contract,"structures").array_value;
    for(std::size_t k=0;k<structures.size();++k){
        reject(in,"structure-basis",[k](auto& x){erase(edit(x.contract,"structures").array_value[k],"basis");});
        reject(in,"structure-basis",[k](auto& x){set(edit(x.contract,"structures").array_value[k],"basis",text(" \t\n"));});
        if(in.light)reject(in,"judgment",[k](auto& x){set(edit(x.contract,"structures").array_value[k],"basis",text("citation without numeric provenance"));});
    }
    for(const auto* key:{"anchor","ic","inductor","cap","resistor","cin","cout"})
        reject(in,"reference",[key](auto& x){set(first(x),key,text("MISSING999"));});
    for(const auto* key:{"members","caps","ics"})
        reject(in,"reference",[key](auto& x){set(first(x),key,array({text("MISSING999")}));});
    reject(in,"reference",[](auto& x){auto r=object();set(r,"MISSING999",text("role"));set(x.contract,"roles",r);});
    reject(in,"reference",[](auto& x){auto r=object();set(r,"part",text("MISSING999"));set(first(x),"min_from",array({r}));});
    reject(in,"reference",[](auto& x){const auto ref=get(first(x),"anchor").string_value;
        const auto old=x.circuit.parts.size();x.circuit.parts.erase(std::remove_if(x.circuit.parts.begin(),x.circuit.parts.end(),
            [&](const auto& p){return p.ref==ref;}),x.circuit.parts.end());require(old==x.circuit.parts.size()+1,"IR mutation missed its part");});
    reject(in,"roles-shape",[](auto& x){set(x.contract,"roles",array());});
    reject(in,"references-shape",[](auto& x){set(first(x),"members",text("R1"));});
    reject(in,"min-from-shape",[](auto& x){set(first(x),"min_from",array({text("R1")}));});
    reject(in,"external-shape",[](auto& x){set(x.contract,"external",array());});
    if(in.light){
        reject(in,"subsystem",[](auto& x){set(x.contract,"subsystem",text("wrong"));});
        reject(in,"lightweight-tier",[](auto& x){set(x.contract,"tier",text("critical"));});
        reject(in,"lightweight-external",[](auto& x){auto ext=object();set(ext,"flow",array());set(x.contract,"external",ext);});
        reject(in,"proximity-anchor",[](auto& x){erase(first(x),"anchor");});
        reject(in,"proximity-members",[](auto& x){set(first(x),"members",array());});
        reject(in,"proximity-members",[](auto& x){set(first(x),"members",array({number(1)}));});
        for(double distance:{0.0,-1.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()})
            reject(in,"proximity-distance",[distance](auto& x){set(first(x),"max_mm",number(distance));});
        reject(in,"proximity-distance",[](auto& x){set(first(x),"max_mm",text("invalid"));});
        // Some lightweight packages legitimately have proximity structures only.
        if(std::any_of(structures.begin(),structures.end(),[](const auto& s){return string(get(s,"type"),"same_side");}))
            reject(in,"same-side-ics",[](auto& x){set(first(x,"same_side"),"ics",array());});
        for(std::size_t k=0;k<structures.size();++k)if(!get(structures[k],"anchor_pins").array_value.empty()){
            reject(in,"anchor-pins",[k](auto& x){set(edit(x.contract,"structures").array_value[k],"anchor_pins",array({text("999999")}));});
            reject(in,"anchor-pin-table",[k](auto& x){const auto ref=get(edit(x.contract,"structures").array_value[k],"anchor").string_value;
                bool changed=false;for(auto& p:x.circuit.parts)if(p.ref==ref){p.pin_numbers.clear();changed=true;}require(changed,"missing pin-table target");});
        }
    }else{
        reject(in,"critical-version",[](auto& x){set(x.contract,"contract",text("placement/v1"));});
        reject(in,"critical-tier",[](auto& x){set(x.contract,"tier",text("lightweight"));});
        reject(in,"citations",[](auto& x){erase(x.contract,"citations");});
        reject(in,"citations",[](auto& x){set(x.contract,"citations",array());});
        reject(in,"citations",[](auto& x){set(x.contract,"citations",array({number(1)}));});
        reject(in,"citations",[](auto& x){set(x.contract,"citations",array({text("")}));});
        for(const auto* key:{"near_max","far"}){
            auto good=in;auto ext=object(),term=object();set(term,"basis",text("independent threshold evidence"));
            set(ext,key,array({term}));set(good.contract,"external",ext);
            require(policy(good).empty(),"well-evidenced external threshold rejected");
            reject(good,"external-basis",[key](auto& x){erase(edit(edit(x.contract,"external"),key).array_value[0],"basis");});
            reject(good,"external-basis",[key](auto& x){set(edit(edit(x.contract,"external"),key).array_value[0],"basis",text(""));});
            reject(good,"external-terms",[key](auto& x){set(edit(x.contract,"external"),key,text("bad"));});
        }
    }
    if(in.sheet=="usb_jtag"){
        reject(in,"crystal-count",[](auto& x){set(crystal(x),"members",array({text("C1")}));});
        reject(in,"crystal-count",[](auto& x){const auto extra=crystal(x);edit(x.contract,"structures").array_value.push_back(extra);});
        reject(in,"crystal-anchor",[](auto& x){set(crystal(x),"anchor",text("U2"));});
        for(auto pins:{array({text("19")}),array({text("19"),text("19")}),array({text("18"),text("20")})})
            reject(in,"crystal-pins",[pins](auto& x){set(crystal(x),"anchor_pins",pins);});
        reject(in,"crystal-distance",[](auto& x){set(crystal(x),"max_mm",number(std::nextafter(5.0,6.0)));});
        reject(in,"crystal-basis",[](auto& x){set(crystal(x),"basis",text("judgment:5.0 generic evidence"));});
        auto reordered=in;set(crystal(reordered),"anchor_pins",array({text("20"),text("19")}));
        require(policy(reordered).empty(),"original sorted-pin semantics changed");
    }
}
} // namespace
int main(int argc,char** argv){
    try{
        require(argc==2,"usage: placement_metadata_contracts REPOSITORY");const fs::path root=fs::canonical(argv[1]);
        require(open_part_catalog((root/"native/catalog.bin").string()),"part catalog unavailable");
        struct Close { ~Close(){close_part_catalog();} } close;
        const auto config=load_project_config(resolve_project_paths(root,"carrier"));
        const std::set<std::string> wired(config.wired_sheets.begin(),config.wired_sheets.end());
        std::size_t lookups=0,authored=0;
        ProjectAuthoringInput author;author.project_root=root/"carrier";
        author.context.part=[&](const std::string& name){++lookups;return lookup_part_catalog(name);};
        const auto factories=native_project_factories("carrier",author);
        for(const bool light:{true,false})for(const auto& name:light?lightweight:critical){
            // Same library-first contract precedence as load_board_inputs.
            auto file=root/"subsystems"/name/"placement_contract.json";
            if(!fs::is_regular_file(file))file=root/"carrier/subsystems"/name/"placement_contract.json";
            require(fs::is_regular_file(file),"missing actual placement contract: "+name);
            auto f=std::find_if(factories.begin(),factories.end(),[&](const auto& v){return v.name==name;});
            require(f!=factories.end()&&bool(f->circuit),"missing actual native factory: "+name);
            Input in{name,light,parse_json_file(file.string()),f->circuit(),wired};++authored;
            require(!in.circuit.parts.empty(),"fresh native circuit is empty: "+name);
            const auto findings=policy(in);
            std::string detail;for(const auto& code:findings)detail+=" "+code;
            require(findings.empty(),"real metadata policy failed for "+name+":"+detail);
            mutation_contracts(in);
            require(policy(in).empty(),"mutation contaminated original input: "+name);
        }
        const Findings expected{"wired","circuit-identity","contract-object","sheet","subsystem","lightweight-tier",
            "critical-version","critical-tier","citations","reference","roles-shape","structures","structure-object",
            "structure-type","structure-basis","judgment","references-shape","min-from-shape","proximity-anchor",
            "proximity-members","proximity-distance","same-side-ics","anchor-pins","anchor-pin-table","external-shape",
            "lightweight-external","external-terms","external-basis","crystal-count","crystal-anchor","crystal-pins",
            "crystal-distance","crystal-basis"};
        require(exercised==expected,"a metadata policy lacks an independent negative mutation");
        require(authored==10,"incomplete family census");
        require(lookups>0,"no live part catalog consumption");
        std::cout<<"Placement metadata: "<<checks<<" assertions PASS; "<<authored<<" fresh native circuits, "
            <<mutations<<" rejected mutations, "<<exercised.size()<<" policies (no geometry duplication)\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<"Placement metadata FAIL: "<<e.what()<<'\n';return 1;}
}
