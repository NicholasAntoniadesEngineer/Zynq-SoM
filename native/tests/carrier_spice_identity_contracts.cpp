#include "schgen/project_authoring.hpp"
#include "schgen/power_checks.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>

namespace {
using namespace schgen;
void require(bool ok, const std::string& why) { if(!ok) throw std::runtime_error(why); }
struct Passive { std::string first, second, value; };
using Passives = std::map<std::string, Passive>;
Passives read_passives(const std::string& text,const std::string& subsystem="board_aux") {
    std::istringstream lines(text); std::string line; bool inside=false, found=false, ended=false;
    Passives result;
    while(std::getline(lines,line)) {
        std::istringstream words(line); std::string name; if(!(words>>name)||name[0]=='*')continue;
        if(name==".subckt") {
            std::string sub;words>>sub;
            if(sub==subsystem) { require(!found,"duplicate "+subsystem+" subcircuit");inside=found=true; }
            continue;
        }
        if(name==".ends"&&inside) { inside=false;ended=true;continue; }
        if(!inside||(name[0]!='R'&&name[0]!='C'))continue;
        Passive row;std::string extra;
        require(bool(words>>row.first>>row.second>>row.value)&&!(words>>extra),"malformed passive row "+name);
        require(result.emplace(name,row).second,"duplicate passive row "+name);
    }
    require(found&&ended&&!inside,"missing/unterminated "+subsystem+" subcircuit");return result;
}
void verify(const CircuitSheetIr& live,const Passives& spice,
            const std::map<std::string,std::string>& rails={{"+3V3","V3V3"},{"+3V3_AUX","V3V3_AUX"},{"+3V3_SC","V3V3_SC"}},
            std::size_t expected_count=11) {
    std::map<std::pair<std::string,std::string>,std::string> pins;
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
    require(count==expected_count&&spice.size()==count,"missing/extra SPICE passive coverage");
}
template<class F> void rejects(F f) { bool bad=false;try{f();}catch(const std::exception&){bad=true;}require(bad,"SPICE identity mutation escaped"); }
void verify_hdmi(const CircuitSheetIr& live,const Passives& spice) {
    const std::vector<std::pair<std::string,std::string>> lanes{
        {"HDMI_RX_D2_P","D2P"},{"HDMI_RX_D2_N","D2N"},{"HDMI_RX_D1_P","D1P"},{"HDMI_RX_D1_N","D1N"},
        {"HDMI_RX_D0_P","D0P"},{"HDMI_RX_D0_N","D0N"},{"HDMI_RX_CLK_P","CLKP"},{"HDMI_RX_CLK_N","CLKN"}};
    std::map<std::string,std::string> nets{{"+3V3","AVCC"}};
    require(live.parts.size()==10,"HDMI termination must contain eight resistors and two bypass capacitors");
    for(const auto& part:live.parts){
        const bool resistor=part.ref.size()==2&&part.ref[0]=='R'&&part.ref[1]>='1'&&part.ref[1]<='8';
        const bool capacitor=part.ref=="C1"||part.ref=="C2";
        require((resistor&&part.lib_id=="Device:R")||(capacitor&&part.lib_id=="Device:C"),"HDMI passive reference/type mismatch");
    }
    for(std::size_t i=0;i<lanes.size();++i){
        nets.emplace(lanes[i]);const auto& row=spice.at("R"+std::to_string(i+1));
        require(row.first==lanes[i].second&&row.second=="AVCC"&&parse_si_value(row.value)==std::optional<double>{49.9},
                "HDMI termination census/value/lane mismatch");
    }
    for(const auto& [ref,value]:std::map<std::string,double>{{"C1",1e-7},{"C2",1e-6}}){
        const auto& row=spice.at(ref);
        const auto parsed=parse_si_value(row.value);
        // Decimal SI multiplication can differ from a literal by a few ULPs;
        // this is floating-point representation allowance, not part tolerance.
        require(row.first=="AVCC"&&row.second=="GND"&&parsed&&std::isfinite(*parsed)&&
                std::abs(*parsed-value)<=4*std::numeric_limits<double>::epsilon()*value,
                "HDMI AVCC bypass identity mismatch");
    }
    verify(live,spice,nets,10);
}
}
int main(int argc,char** argv) {
    try {
        require(argc==3||argc==4,"usage: carrier_spice_identity_contracts REPO CATALOG [SPICE_FILE]");
        require(open_part_catalog(argv[2]),"open native catalog");
        ProjectAuthoringInput input;input.context=make_authoring_context(argv[1]);
        const auto live=author_project_subsystem("carrier","board_aux",input);
        const auto path=argc==4?std::filesystem::path(argv[3]):std::filesystem::path(argv[1])/"carrier/subsystems/board_aux/board_aux.cir";
        std::ifstream file(path);require(bool(file),"read board_aux SPICE model");
        const std::string bytes{std::istreambuf_iterator<char>(file),{}};
        const auto rows=read_passives(bytes);verify(live,rows);
        auto pre_bias=rows;
        pre_bias.at("C5")={"V3V3_AUX","GND","100n"};
        pre_bias.at("R4")={"V3V3_AUX","AUX_ISO_EN","100k"};
        rejects([&]{verify(live,pre_bias);});
        auto historical=pre_bias;
        historical.at("C3")={"V3V3_SC","GND","100n"};
        historical.at("C4")={"V3V3_AUX","GND","100n"};
        historical.at("C5")={"V3V3_AUX","GND","10u"};
        const auto electrical=[](const Passives& parts) {
            std::multiset<std::tuple<char,std::string,std::string,double>> result;
            for(const auto& [ref,p]:parts)
                result.emplace(ref.front(),p.first,p.second,*parse_si_value(p.value));
            return result;
        };
        require(electrical(pre_bias)==electrical(historical),"historical label correction changed the passive network");
        rejects([&]{verify(live,historical);});
        for(const auto& row:rows) {
            auto missing=rows;missing.erase(row.first);rejects([&]{verify(live,missing);});
            auto wrong=rows;wrong.at(row.first).first="wrong_rail";rejects([&]{verify(live,wrong);});
        }
        const auto hdmi=author_project_subsystem("carrier","hdmi_rx_term",input);
        std::ifstream hdmi_file(std::filesystem::path(argv[1])/"carrier/subsystems/hdmi_rx_term/hdmi_rx_term.cir");
        require(bool(hdmi_file),"read HDMI termination SPICE model");
        const std::string hdmi_bytes{std::istreambuf_iterator<char>(hdmi_file),{}};
        const auto hdmi_rows=read_passives(hdmi_bytes,"hdmi_rx_term");verify_hdmi(hdmi,hdmi_rows);
        for(const auto& entry:hdmi_rows){
            const auto& ref=entry.first;
            auto missing=hdmi_rows;missing.erase(ref);rejects([&]{verify_hdmi(hdmi,missing);});
            auto wrong=hdmi_rows;wrong.at(ref).second="wrong_rail";rejects([&]{verify_hdmi(hdmi,wrong);});
            auto value=hdmi_rows;value.at(ref).value="1";rejects([&]{verify_hdmi(hdmi,value);});
            auto live_missing=hdmi;
            live_missing.parts.erase(std::find_if(live_missing.parts.begin(),live_missing.parts.end(),[&](const auto& p){return p.ref==ref;}));
            rejects([&]{verify_hdmi(live_missing,hdmi_rows);});
        }
        auto common_mode_error=hdmi;auto model_error=hdmi_rows;
        for(auto& part:common_mode_error.parts)if(part.ref=="R1")part.value="100R";
        model_error.at("R1").value="100";
        rejects([&]{verify_hdmi(common_mode_error,model_error);});
        auto wrong_type=hdmi;for(auto& part:wrong_type.parts)if(part.ref=="R1")part.lib_id="Device:C";
        rejects([&]{verify_hdmi(wrong_type,hdmi_rows);});
        auto swapped=hdmi_rows;std::swap(swapped.at("R1").first,swapped.at("R2").first);
        rejects([&]{verify_hdmi(hdmi,swapped);});
        close_part_catalog();std::cout<<"21 live SPICE passive identities, HDMI census and ownership mutations PASS\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
