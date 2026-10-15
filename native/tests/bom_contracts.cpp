#include "schgen/bom.hpp"
#include "schgen/project.hpp"
#include "historical_input_contracts.hpp"

#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <stdexcept>
#include <tuple>

namespace {
void require(bool test, const char* message) {
    if (!test) throw std::runtime_error(message);
}
schgen::CircuitPartIr part(std::string ref, std::string value, std::string footprint,
                           std::vector<schgen::CircuitFieldIr> fields = {}) {
    schgen::CircuitPartIr result;
    result.ref = std::move(ref); result.value = std::move(value);
    result.footprint = std::move(footprint); result.fields = std::move(fields);
    return result;
}
void inventory(const std::vector<schgen::CircuitSheetIr>& sheets, const schgen::BomOutput& bom) {
    using Identity = std::tuple<std::string,std::string,std::string>;
    std::map<std::string,Identity> expected, actual;
    for(const auto& sheet:sheets) for(const auto& p:sheet.parts) {
        std::string lcsc; bool excluded=false;
        for(const auto& field:p.fields) {
            if(field.key=="LCSC")lcsc=field.value;
            if(field.key=="BOM"&&field.value=="exclude")excluded=true;
        }
        if(!excluded)require(expected.emplace(sheet.name+":"+p.ref,
            Identity{p.value,p.footprint,lcsc}).second,"duplicate input BOM reference");
    }
    for(const auto& row:bom.rows) {
        require(!row.refs.empty(),"empty BOM group");
        for(const auto& ref:row.refs)require(actual.emplace(ref,
            Identity{row.value,row.footprint,row.lcsc}).second,"duplicate output BOM reference");
    }
    require(actual==expected,"BOM must contain each included part exactly once with its complete identity");
}
}
int main(int argc, char** argv) {
    try {
        schgen::CircuitSheetIr a, b;
        a.name = "a"; b.name = "b";
        a.parts = {part("R2", "10k", "R_0603", {{"LCSC", "C1"}}),
                   part("R10", "10k", "R_0603", {{"LCSC", "C1"}}),
                   part("H1", "mount", "", {{"BOM", "exclude"}}),
                   part("U1", "chip,\"quoted\"", "pkg"),
                   part("J1", "connector", "")};
        b.parts = {part("R1", "10k", "R_0603", {{"LCSC", "C1"}})};
        const auto result = schgen::generate_bom({a, b});
        require(result.rows.size() == 3, "BOM exclusion/grouping");
        require(result.csv == "Comment,Designator,Footprint,LCSC\r\n"
            "10k,\"a:R10,a:R2,b:R1\",R_0603,C1\r\n"
            "\"chip,\"\"quoted\"\"\",a:U1,pkg,\r\n"
            "connector,a:J1,,\r\n", "CSV quoting/order/newlines differ");
        require(result.missing_lcsc == std::vector<std::string>{
                    "a:J1 (connector)", "a:U1 (chip,\"quoted\")"}, "missing LCSC evidence");
        require(result.missing_footprints == std::vector<std::string>{"connector: a:J1"},
                "unplaceable part evidence");
        require(schgen::generate_bom({a, b}, false).rows[0].refs ==
                    std::vector<std::string>{"R10", "R2", "R1"}, "standalone ref policy");
        require(schgen::generate_bom({}).csv == "Comment,Designator,Footprint,LCSC\r\n",
                "empty BOM header");
        a.parts = {part("R1", "line\nbreak", "tab\t", {{"BOM", "EXCLUDE"}})};
        require(schgen::generate_bom({a}).csv.find("\"line\nbreak\",a:R1,tab\t,\r\n") !=
                    std::string::npos, "newline CSV cell or exact BOM exclude policy");
        if (argc == 2) for(const std::string project:{"carrier","devkit_mini"}) {
            const auto paths = schgen::resolve_project_paths(argv[1], project);
            std::vector<schgen::CircuitSheetIr> sheets;
            for (const auto& circuit : schgen::load_project_circuits(paths)) sheets.push_back(circuit.circuit);
            std::ifstream file(paths.project_root / "manufacturing/bom_jlc.csv", std::ios::binary);
            require(file.good(), "cannot read published board BOM");
            const std::string golden((std::istreambuf_iterator<char>(file)), {});
            const auto real = schgen::generate_bom(sheets);
            // This is a regenerated publication, not an immutable historical
            // oracle (18778526 refreshed both boards). Compare current inputs
            // directly, then independently verify every included part identity.
            require(real.csv==golden,"published BOM differs from current circuit inputs");
            inventory(sheets,real);
            require(!real.rows.empty()&&!real.rows.front().refs.empty(),"real BOM mutation preimage");
            for(int mutation=0;mutation<5;++mutation){
                auto changed=real;
                if(mutation==0)changed.rows.front().refs.erase(changed.rows.front().refs.begin());
                if(mutation==1){const auto copy=changed.rows.front().refs.front();changed.rows.front().refs.push_back(copy);}
                if(mutation==2)changed.rows.front().value+="_drift";
                if(mutation==3)changed.rows.front().footprint+="_drift";
                if(mutation==4)changed.rows.front().lcsc+="_drift";
                bool rejected=false;try{inventory(sheets,changed);}catch(const std::runtime_error&){rejected=true;}
                require(rejected,"independent BOM inventory accepted a missing, duplicate or altered part");
            }
            require(real.missing_footprints.empty(), "board contains unplaceable BOM rows");
            require(sheets.size() == (project=="carrier"?37u:12u), "board BOM omitted circuits");
            if(project!="carrier")continue;
            // Retain the reviewed capacitor identities and negative checks,
            // but do not compare projected old inputs with current publication.
            auto historical=sheets;
            for(auto& sheet:historical)sheet=historical_input_contracts::project(sheet,"carrier");
            const auto identity=[&](const char* ref,const char* value,const char* footprint,const char* lcsc){
                std::size_t found=0;
                for(const auto& row:real.rows)for(const auto& actual:row.refs)if(actual==ref){
                    ++found;require(row.value==value&&row.footprint==footprint&&row.lcsc==lcsc,
                                    "current reviewed capacitor BOM identity");
                }
                require(found==1,"current capacitor BOM reference must appear exactly once");
            };
            identity("board_aux:C1","10u","Capacitor_SMD:C_0805_2012Metric","C15850");
            identity("board_aux:C5","100p","Capacitor_SMD:C_0603_1608Metric","C14858");
            require(real.rows.size()==schgen::generate_bom(historical).rows.size()+1,
                    "reviewed filter creates exactly one extra BOM group");
            for(const auto* ref:{"C1","C5"}){
                auto changed=sheets;bool rejected=false;
                for(auto& sheet:changed)if(sheet.name=="board_aux")for(auto& p:sheet.parts)
                    if(p.ref==ref)p.value="100n";
                try{for(auto& sheet:changed)sheet=historical_input_contracts::project(sheet,"carrier");}
                catch(const std::runtime_error&){rejected=true;}
                require(rejected,"reverted capacitor BOM must not pass historical projection");
            }
        }
        std::cout << "BOM native contracts passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
