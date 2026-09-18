#include "schgen/selftest.hpp"
#include "schgen/json.hpp"
#include "schgen/validation.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <tuple>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool ok, const std::string& message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& node, const std::string& name) {
    const auto* value = object_field(node, name);
    if (!value) throw std::runtime_error("fixture field missing: " + name);
    return *value;
}
void same_circuit(const CircuitSheetIr& a, const CircuitSheetIr& b) {
    require(std::tie(a.schema,a.name,a.title)==std::tie(b.schema,b.name,b.title),"circuit identity differs");
    require(a.parts.size()==b.parts.size(),"part count differs");
    for (std::size_t i=0;i<a.parts.size();++i) {
        const auto& p=a.parts[i];const auto& q=b.parts[i];
        require(std::tie(p.ref,p.lib_id,p.value,p.footprint,p.pin_numbers)==
                std::tie(q.ref,q.lib_id,q.value,q.footprint,q.pin_numbers),"part data/order differs");
        require(p.fields.size()==q.fields.size()&&p.pin_names.size()==q.pin_names.size(),"part metadata count differs");
        for (std::size_t j=0;j<p.fields.size();++j)
            require(std::tie(p.fields[j].key,p.fields[j].value)==std::tie(q.fields[j].key,q.fields[j].value),"fields differ");
        for (std::size_t j=0;j<p.pin_names.size();++j)
            require(std::tie(p.pin_names[j].name,p.pin_names[j].numbers)==std::tie(q.pin_names[j].name,q.pin_names[j].numbers),"pin names differ");
    }
    auto pins=[](const auto& p,const auto& q) {
        require(p.size()==q.size(),"pin count differs");
        for (std::size_t i=0;i<p.size();++i)require(std::tie(p[i].ref,p[i].pin)==std::tie(q[i].ref,q[i].pin),"pin order differs");
    };
    require(a.nets.size()==b.nets.size(),"net count differs");
    for (std::size_t i=0;i<a.nets.size();++i) {
        require(std::tie(a.nets[i].name,a.nets[i].net_class)==std::tie(b.nets[i].name,b.nets[i].net_class),"net identity differs");
        pins(a.nets[i].pins,b.nets[i].pins);
    }
    pins(a.nc,b.nc);
    require(a.port_types.empty()&&b.port_types.empty()&&a.hints.empty()&&b.hints.empty()
        &&a.loads.empty()&&b.loads.empty()&&a.waivers.empty()&&b.waivers.empty(),"unexpected fixture metadata");
}
void same_proof(const PlacerMutationProof& actual,const JsonNode& fixture) {
    const auto& expected=field(fixture,"proof").array_value;
    require(actual.baseline_ok==expected.at(0).bool_value,"baseline result differs");
    require(actual.mutation_killed==expected.at(1).bool_value,"mutation result differs");
    require(actual.diagnostic==expected.at(2).string_value,"diagnostic differs: "+actual.diagnostic);
    require(actual.baseline_failure.empty(),"clean baseline returned a failure");
}
void remove_part(CircuitSheetIr& c,const std::string& ref) {
    c.parts.erase(std::remove_if(c.parts.begin(),c.parts.end(),[&](const auto& p){return p.ref==ref;}),c.parts.end());
    for(auto& n:c.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[&](const auto& p){return p.ref==ref;}),n.pins.end());
    c.nc.erase(std::remove_if(c.nc.begin(),c.nc.end(),[&](const auto& p){return p.ref==ref;}),c.nc.end());
}
}  // namespace

int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: selftest_contracts <fixture-directory>");
        const fs::path dir(argv[1]);
        SymbolLibrary library(std::vector<fs::path>{dir/"symbols"});
        const auto rail_json=parse_json_file((dir/"rail_decoup_dropped.json").string());
        const auto clamp_json=parse_json_file((dir/"clamp_thresh_strict.json").string());
        const auto rail=selftest_rail_decoupling_fixture(),clamp=selftest_esd_clamp_fixture();
        same_circuit(rail,parse_circuit_ir(field(rail_json,"circuit")));
        same_circuit(clamp,parse_circuit_ir(field(clamp_json,"circuit")));
        const auto rail_proof=selftest_rail_decoup_dropped(library);
        same_proof(rail_proof,rail_json);
        require(rail_proof.mutation_attempts==1,"rail mutation did not reach Engine::run exactly once");
        require(rail_proof.mutation_failure=="engine left parts unplaced: ['C1'] — no topology pattern matched them",
                "rail mutation was not killed by the real missing-part gate");
        const auto clamp_proof=selftest_clamp_thresh_strict(library);
        same_proof(clamp_proof,clamp_json);
        require(clamp_proof.mutation_attempts==8,"clamp mutation skipped ordinary retry/expansion policy");
        require(clamp_proof.mutation_failure=="placement infeasible after 8 expansions; last failure:\n"
                "route: route: cell contested: #blocked vs SIG_1 (wire SIG_1)",
                "clamp mutation was not killed by the real router");
        same_proof(selftest_rail_decoup_dropped(rail,library),rail_json);
        same_proof(selftest_clamp_thresh_strict(clamp,library),clamp_json);
        same_circuit(rail,selftest_rail_decoupling_fixture());
        same_circuit(clamp,selftest_esd_clamp_fixture());

        // Negative controls: no target means no kill. These expected results
        // were frozen from the original Python monkeypatch implementation too.
        auto rail_no_cap=rail;remove_part(rail_no_cap,"C1");
        const auto rail_control=parse_json_file((dir/"rail_without_cap.json").string());
        same_circuit(rail_no_cap,parse_circuit_ir(field(rail_control,"circuit")));
        const auto survived_rail=selftest_rail_decoup_dropped(rail_no_cap,library);
        same_proof(survived_rail,rail_control);
        require(survived_rail.mutation_failure.empty(),"non-applicable rail mutation manufactured a failure");
        auto clamp_no_array=clamp;remove_part(clamp_no_array,"U1");
        const auto clamp_control=parse_json_file((dir/"clamp_without_array.json").string());
        same_circuit(clamp_no_array,parse_circuit_ir(field(clamp_control,"circuit")));
        const auto survived_clamp=selftest_clamp_thresh_strict(clamp_no_array,library);
        same_proof(survived_clamp,clamp_control);
        require(survived_clamp.mutation_failure.empty(),"non-applicable clamp mutation manufactured a failure");
        require(survived_clamp.mutation_attempts==1,"clean unchanged geometry should pass the first attempt");

        // Original fixtures remain green after repeated mutations: no global
        // monkeypatch, shared library mutation, or persistent Engine state.
        require(build_schematic_placement(rail,library).parts.size()==2,"rail mutation leaked into production build");
        require(place_and_route_schematic(clamp,library).placement.parts.size()==2,"strict shunt mutation leaked into production build");

        auto incomplete=rail;incomplete.nets[0].pins.clear();
        bool rejected=false;
        try { selftest_rail_decoup_dropped(incomplete,library); }
        catch(const ValidationError&) { rejected=true; }
        require(rejected,"electrically incomplete fixture was incorrectly credited as a killed mutation");
        auto unknown=clamp;unknown.parts[0].lib_id="MissingSelftest:DoesNotExist";
        rejected=false;
        try { selftest_clamp_thresh_strict(unknown,library); }
        catch(const ValidationError&) { rejected=true; }
        require(rejected,"resolver failure was incorrectly credited as a killed mutation");
        std::cout<<checks<<" selftest contracts passed (2 killed mutants + 2 surviving negative controls)\n";
    } catch(const std::exception& e) {
        std::cerr<<"selftest contract failure: "<<e.what()<<'\n';return 1;
    }
}
