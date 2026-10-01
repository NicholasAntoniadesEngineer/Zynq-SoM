#include "schgen/project_authoring.hpp"
#include "schgen/power_checks.hpp"
#include <fstream>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
void require(bool ok, const std::string& why) { if(!ok) throw std::runtime_error(why); }
struct Passive { std::string first, second, value; };
using Passives = std::map<std::string, Passive>;
Passives read_passives(const std::string& text) {
    std::istringstream lines(text); std::string line; bool inside=false, found=false, ended=false;
    Passives result;
    while(std::getline(lines,line)) {
        std::istringstream words(line); std::string name; if(!(words>>name)||name[0]=='*')continue;
        if(name==".subckt") {
            std::string sub;words>>sub;
            if(sub=="board_aux") { require(!found,"duplicate board_aux subcircuit");inside=found=true; }
            continue;
        }
        if(name==".ends"&&inside) { inside=false;ended=true;continue; }
        if(!inside||(name[0]!='R'&&name[0]!='C'))continue;
        Passive row;std::string extra;
        require(bool(words>>row.first>>row.second>>row.value)&&!(words>>extra),"malformed passive row "+name);
        require(result.emplace(name,row).second,"duplicate passive row "+name);
    }
    require(found&&ended&&!inside,"missing/unterminated board_aux subcircuit");return result;
}
void verify(const CircuitSheetIr& live,const Passives& spice) {
    std::map<std::pair<std::string,std::string>,std::string> pins;
    const std::map<std::string,std::string> rails{{"+3V3","V3V3"},{"+3V3_AUX","V3V3_AUX"},{"+3V3_SC","V3V3_SC"}};
    for(const auto& net:live.nets)for(const auto& pin:net.pins)
        require(pins.emplace(std::make_pair(pin.ref,pin.pin),rails.count(net.name)?rails.at(net.name):net.name).second,
                "multiply-netted live pin");
    std::size_t count=0;
    for(const auto& part:live.parts) {
        if(part.lib_id!="Device:C"&&part.lib_id!="Device:R")continue;
        ++count;const auto it=spice.find(part.ref);require(it!=spice.end(),"missing SPICE passive "+part.ref);
        const auto expected=parse_si_value(part.value),actual=parse_si_value(it->second.value);
        require(expected&&actual&&*expected==*actual,"SPICE/live passive value mismatch: "+part.ref);
        require(pins.at({part.ref,"1"})==it->second.first&&pins.at({part.ref,"2"})==it->second.second,
                "SPICE/live terminal ownership mismatch: "+part.ref);
    }
    require(count==11&&spice.size()==count,"missing/extra SPICE passive coverage");
}
template<class F> void rejects(F f) { bool bad=false;try{f();}catch(const std::exception&){bad=true;}require(bad,"SPICE identity mutation escaped"); }
}
int main(int argc,char** argv) {
    try {
        require(argc==3,"usage: carrier_spice_identity_contracts REPO CATALOG");
        require(open_part_catalog(argv[2]),"open native catalog");
        ProjectAuthoringInput input;input.context=make_authoring_context(argv[1]);
        const auto live=author_project_subsystem("carrier","board_aux",input);
        const auto path=std::filesystem::path(argv[1])/"carrier/subsystems/board_aux/board_aux.cir";
        std::ifstream file(path);require(bool(file),"read board_aux SPICE model");
        const std::string bytes{std::istreambuf_iterator<char>(file),{}};
        const auto rows=read_passives(bytes);verify(live,rows);
        auto historical=rows;
        historical.at("C3")={"V3V3_SC","GND","100n"};
        historical.at("C4")={"V3V3_AUX","GND","100n"};
        historical.at("C5")={"V3V3_AUX","GND","10u"};
        const auto electrical=[](const Passives& parts) {
            std::multiset<std::tuple<char,std::string,std::string,double>> result;
            for(const auto& [ref,p]:parts)
                result.emplace(ref.front(),p.first,p.second,*parse_si_value(p.value));
            return result;
        };
        require(electrical(rows)==electrical(historical),"label correction changed the passive network");
        rejects([&]{verify(live,historical);});
        for(const auto& row:rows) {
            auto missing=rows;missing.erase(row.first);rejects([&]{verify(live,missing);});
            auto wrong=rows;wrong.at(row.first).first="wrong_rail";rejects([&]{verify(live,wrong);});
        }
        close_part_catalog();std::cout<<"11 live SPICE passive identities and ownership mutations PASS\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
