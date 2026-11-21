#include "schgen/run_config.hpp"
#include "schgen/copper_debt.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool b,const std::string& why){++checks;if(!b)throw std::runtime_error(why);}
const JsonNode& at(const JsonNode& n,const std::string& k){auto* p=object_field(n,k);if(!p)throw std::runtime_error(k);return *p;}
template<class F> void rejects(const CopperDebtSources& original,F&& mutation,const std::string& why) {
    auto s=original;mutation(s);
    try { (void)analyze_copper_debt(nullptr,s); } catch(const CopperProvenanceError&) { ++checks;return; }
    throw std::runtime_error("accepted invalid provenance: "+why);
}
JsonNode& member(JsonNode& n,const std::string& k){for(auto& e:n.object_value)if(e.first==k)return e.second;throw std::runtime_error(k);}
JsonNode& claim_node(JsonNode& doc,const std::string& id){
    for(auto& c:member(doc,"claims").array_value)if(member(c,"id").string_value==id)return c;
    throw std::runtime_error(id);
}
JsonNode text_node(const std::string& v){JsonNode n;n.kind=JsonKind::String;n.string_value=v;return n;}
template<class F> void loader_rejects(const JsonNode& original,F&& mutation,const std::string& why) {
    auto doc=original;mutation(doc);
    try { (void)parse_copper_claims(doc,"scratch claims"); } catch(const CopperProvenanceError&) { ++checks;return; }
    throw std::runtime_error("loader accepted: "+why);
}
template<class F> void claims_reject(const CopperDebtSources& original,const JsonNode& document,F&& mutation,const std::string& why) {
    auto doc=document;mutation(doc);
    auto s=original;s.claims=parse_copper_claims(doc,"scratch claims");
    try { (void)analyze_copper_debt(nullptr,s); } catch(const CopperProvenanceError&) { ++checks;return; }
    throw std::runtime_error("accepted invalid claim: "+why);
}
CircuitSheetIr& sheet(CopperDebtSources& s,const std::string& scope,const std::string& name) {
    for(auto& c:s.circuits)if(c.scope==scope && c.sheet==name)return c.circuit;
    throw std::runtime_error(name);
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: copper_debt_contracts REPOSITORY");
        schgen::apply_run_config(std::filesystem::path(argv[1])/schgen::run_config_file,"carrier");
        const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"catalog");
        const auto sources=author_copper_debt_sources(root);
        const auto& claims_text=sources.claims;
        const auto claims_path=root/"subsystems/copper_claims.json";
        std::string claims_file_text;
        { std::ifstream in(claims_path); claims_file_text.assign(std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()); }
        require(!claims_file_text.empty(),"claims file");
        const auto fixture=parse_json_file((root/"native/tests/data/component_basis/python_copper.json").string());
        for(const auto& row:fixture.array_value) {
            const auto name=at(row,"name").string_value;
            const auto expected=copper_debt_result_from_json(at(row,"result"));
            std::optional<ThermalCopper> copper;
            if(name!="unmeasured")copper=scan_thermal_copper(root/"native/tests/data/pcb_emit"/(name+".kicad_pcb"));
            const auto got=analyze_copper_debt(copper?&*copper:nullptr,sources);
            require(got.inventory==expected.inventory,name+": inventory");
            require(got.entries.size()==8,"entry coverage");
            for(std::size_t i=0;i<got.entries.size();++i) {
                const auto& a=got.entries[i];const auto& b=expected.entries[i];
                require(a.eid==b.eid && a.title==b.title && a.assumes==b.assumes &&
                    a.emits==b.emits && a.status==b.status && a.risk==b.risk,name+": entry "+a.eid);
                require(!a.where.empty(),"missing provenance");
                require(a.where.size()==1 && a.where[0]==claims_text.reference+"#"+a.eid,"claim location");
                require(claims_file_text.find("\"id\": \""+a.eid+"\"")!=std::string::npos,"claim id in file");
            }
            require(copper_debt_report(got)==copper_debt_report(copper_debt_result_from_json(copper_debt_result_json(got))),"report roundtrip");
        }
        const auto cases=parse_json_file((root/"native/tests/data/component_basis/python_copper_cases.json").string());
        for(const auto& row:cases.array_value) {
            const auto copper=thermal_copper_from_json(at(row,"copper"));
            const auto got=analyze_copper_debt(&copper,sources);
            const auto& expected=at(row,"entries").array_value;
            for(std::size_t i=0;i<got.entries.size();++i) {
                const auto& e=got.entries[i];
                require(e.emits==at(expected[i],"emits").string_value &&
                    e.status==at(expected[i],"status").string_value,
                    "Python synthetic evidence case "+at(row,"name").string_value+" "+e.eid);
            }
        }
        // Live IR, emitter and thermal policy changes all invalidate provenance.
        rejects(sources,[](auto& s){s.circuits.clear();},"empty live inputs");
        rejects(sources,[](auto& s){s.emission.isolation.clear();},"missing isolation targets");
        rejects(sources,[](auto& s){for(auto& row:s.emission.isolation)row.second.margin_mm=0;},"zero isolation margin");
        rejects(sources,[](auto& s){s.emission.ground_layer="In2.Cu";},"wrong reference layer");
        rejects(sources,[](auto& s){s.emission.thermal_credit_needs.clear();},"missing emitter evidence");
        rejects(sources,[](auto& s){s.emission.thermal_copper.clear();},"missing pour emission");
        rejects(sources,[](auto& s){s.emission.thermal_via_drill=0.2;},"via geometry");
        rejects(sources,[](auto& s){s.thermal.specs.clear();},"missing thermal specs");
        rejects(sources,[](auto& s){s.thermal.pour_needs.clear();},"missing thermal evidence");
        rejects(sources,[](auto& s){s.geometry[0].width_mm+=0.01;},"geometry drift");
        for(const auto* scope:{"library","carrier"}) {
            rejects(sources,[&](auto& s){
                auto& c=sheet(s,scope,"ethernet");
                for(auto& n:c.nets)if(n.name=="BS_COMMON")n.pins.erase(n.pins.begin());
            },"Bob-Smith pin removal");
            rejects(sources,[&](auto& s){
                auto& c=sheet(s,scope,"ethernet");
                for(auto& p:c.parts)if(p.ref=="C5")p.footprint="Capacitor_SMD:C_0402_1005Metric";
            },"2kV component substitution");
        }
        for(const auto* scope:{"carrier","devkit_mini"}) {
            rejects(sources,[&](auto& s){sheet(s,scope,"mechanical").nets[0].name="GND";},"chassis connection");
            rejects(sources,[&](auto& s){
                auto& c=sheet(s,scope,"som_decoupling");
                for(auto& n:c.nets)if(n.name=="GND")n.pins.erase(n.pins.begin());
            },"SoM cap ground pin");
        }
        const auto document=parse_json_file(claims_path.string());
        require(parse_copper_claims(document,"scratch claims").claims.size()==8,"claims round parse");
        for(const auto* scope:{"library","carrier","devkit_mini"})
            rejects(sources,[&](auto& s){
                auto& c=sheet(s,scope,"power");
                std::string other;
                for(auto& n:c.nets)if(n.name!="GND"){other=n.name;break;}
                for(auto& n:c.nets)for(auto p=n.pins.begin();p!=n.pins.end();++p)if(p->ref=="U1"&&p->pin=="3"){
                    auto moved=*p;n.pins.erase(p);
                    for(auto& o:c.nets)if(o.name==other)o.pins.push_back(moved);
                    return;
                }
            },"buck ground pad moved to another net");
        for(const auto* scope:{"carrier","devkit_mini"})
            rejects(sources,[&](auto& s){
                auto& c=sheet(s,scope,"mechanical");
                c.parts.erase(std::remove_if(c.parts.begin(),c.parts.end(),[](const auto& p){return p.ref=="H4";}),c.parts.end());
            },"mounting hole removed");
        for(const auto* scope:{"library","carrier"})
            rejects(sources,[&](auto& s){
                for(auto& p:sheet(s,scope,"ethernet").parts)if(p.ref=="C5")for(auto& f:p.fields)if(f.key=="LCSC")f.value="C0";
            },"2kV capacitor order code changed");
        loader_rejects(document,[](auto& d){member(claim_node(d,"CD-01"),"checks").array_value[0].object_value.emplace_back("kind_extra",text_node("x"));},"unknown key in a check");
        loader_rejects(document,[](auto& d){claim_node(d,"CD-01").object_value.emplace_back("extra",text_node("x"));},"unknown key in a claim");
        loader_rejects(document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[0],"kind")=text_node("telepathy");},"unknown check kind");
        loader_rejects(document,[](auto& d){member(member(claim_node(d,"CD-01"),"measure"),"kind")=text_node("telepathy");},"unknown measure kind");
        loader_rejects(document,[](auto& d){member(claim_node(d,"CD-01"),"checks").array_value.clear();},"claim with empty checks");
        loader_rejects(document,[](auto& d){auto& c=claim_node(d,"CD-01");c.object_value.erase(std::remove_if(c.object_value.begin(),c.object_value.end(),[](const auto& e){return e.first=="checks";}),c.object_value.end());},"claim without checks");
        loader_rejects(document,[](auto& d){member(claim_node(d,"CD-01"),"measure").object_value.emplace_back("extra",text_node("x"));},"unknown key in a measure");
        loader_rejects(document,[](auto& d){member(member(claim_node(d,"CD-01"),"measure"),"emits")=text_node("{nonsense}");},"unknown placeholder");
        loader_rejects(document,[](auto& d){member(claim_node(d,"CD-02"),"id")=text_node("CD-01");},"duplicate claim id");
        loader_rejects(document,[](auto& d){member(d,"schema")=text_node("schgen.copper_claims/2");},"wrong schema");
        loader_rejects(document,[](auto& d){member(d,"claims").array_value.clear();},"no claims");
        claims_reject(sources,document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[0],"refs").array_value.push_back(text_node("Z99"));},"claim names a part absent from its sheet");
        claims_reject(sources,document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[0],"sheet")=text_node("no_such_sheet");},"claim names an absent sheet");
        claims_reject(sources,document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[0],"scopes").array_value.push_back(text_node("no_such_board"));},"claim names an absent scope");
        claims_reject(sources,document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[1],"rth_ja")=[]{JsonNode n;n.kind=JsonKind::Number;n.number_value=1.0;return n;}();},"thermal figure differs from the part facts");
        claims_reject(sources,document,[](auto& d){member(member(claim_node(d,"CD-01"),"checks").array_value[2],"part")=text_node("NO-SUCH-PART");},"thermal credit for an unknown part");
        for(const auto* mpn:{"LM61460AANRJRR","TLV75725PDYDR"}) {
            rejects(sources,[&](auto& s){s.emission.thermal_copper.at(mpn).need.min_vias+=1;},"thermal copper need row changed alone");
            rejects(sources,[&](auto& s){s.emission.thermal_copper.at(mpn).need.radius_mm+=0.1;},"thermal copper need radius changed alone");
            rejects(sources,[&](auto& s){s.emission.thermal_copper.at(mpn).need.pour_layers.push_back("In2.Cu");},"thermal copper need layers changed alone");
        }
        for(const char* id:{"CD-01","CD-02"}) {
            claims_reject(sources,document,[&](auto& d){auto& need=member(member(claim_node(d,id),"checks").array_value[2],"need");member(need,"min_vias").number_value+=1;},"claim need vias changed alone");
            claims_reject(sources,document,[&](auto& d){auto& need=member(member(claim_node(d,id),"checks").array_value[2],"need");member(need,"radius_mm").number_value+=0.1;},"claim need radius changed alone");
            claims_reject(sources,document,[&](auto& d){auto& need=member(member(claim_node(d,id),"checks").array_value[2],"need");member(need,"pour_layers").array_value.push_back(text_node("In2.Cu"));},"claim need layers changed alone");
        }
        rejects(sources,[](auto& s){for(auto& n:s.thermal.pour_needs)n.second.min_vias+=1;},"thermal pour need changed alone");
        rejects(sources,[](auto& s){for(auto& n:s.emission.thermal_credit_needs)n.radius_mm+=0.1;},"emitter pour need changed alone");
        {
            std::size_t measured=0;
            for(const auto& row:fixture.array_value) {
                const auto name=at(row,"name").string_value;
                if(name=="unmeasured")continue;
                const auto copper=scan_thermal_copper(root/"native/tests/data/pcb_emit"/(name+".kicad_pcb"));
                const auto real=analyze_copper_debt(&copper,sources);
                if(real.entries[6].status!="EMITTED")continue;
                auto other=sources;other.claims.plane.net="NO_SUCH_PLANE_NET";
                const auto got=analyze_copper_debt(&copper,other);
                for(const std::size_t i:{0,1,6,7})require(got.entries[i].status=="NOTHING",name+": plane net absent, "+got.entries[i].eid);
                require(got.entries[2].status!="EMITTED",name+": exposed-pad claim without plane net");
                ++measured;
            }
            require(measured>0,"a fixture with the ground plane");
        }
        ThermalCopper empty; const auto r=analyze_copper_debt(&empty,sources);
        for(const auto& e:r.entries)require(e.status=="NOTHING","empty PCB granted evidence");
        std::cout<<checks<<" copper-debt contracts PASS (Python baseline fields + live provenance mutations)\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
