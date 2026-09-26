#include "schgen/copper_debt.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
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
CircuitSheetIr& sheet(CopperDebtSources& s,const std::string& scope,const std::string& name) {
    for(auto& c:s.circuits)if(c.scope==scope && c.sheet==name)return c.circuit;
    throw std::runtime_error(name);
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: copper_debt_contracts REPOSITORY");
        const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"catalog");
        const auto sources=author_copper_debt_sources(root);
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
                for(const auto& w:a.where) {
                    const auto split=w.rfind(':'); require(split!=std::string::npos,"site separator");
                    std::ifstream in(root/w.substr(0,split));require(bool(in),"site file");
                    std::string line;const int n=std::stoi(w.substr(split+1));
                    for(int k=0;k<n;++k)require(bool(std::getline(in,line)),"site line");
                    require(line.find("ENTRY(")!=std::string::npos && line.find(a.eid)!=std::string::npos,"structured claim site");
                }
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
        rejects(sources,[](auto& s){s.emission.isolation_prefixes.clear();},"missing isolation targets");
        rejects(sources,[](auto& s){s.emission.isolation_prefixes={""};},"universal prefix");
        rejects(sources,[](auto& s){s.emission.ground_layer="In2.Cu";},"wrong reference layer");
        rejects(sources,[](auto& s){s.emission.thermal_credit_needs.clear();},"missing emitter evidence");
        rejects(sources,[](auto& s){s.emission.thermal_copper.clear();},"missing pour emission");
        rejects(sources,[](auto& s){s.emission.thermal_via_drill=0.2;},"via geometry");
        rejects(sources,[](auto& s){s.thermal.specs.clear();},"missing thermal specs");
        rejects(sources,[](auto& s){s.thermal.footprint_specs.clear();},"missing DYD override");
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
        ThermalCopper empty; const auto r=analyze_copper_debt(&empty,sources);
        for(const auto& e:r.entries)require(e.status=="NOTHING","empty PCB granted evidence");
        std::cout<<checks<<" copper-debt contracts PASS (Python baseline fields + live provenance mutations)\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
