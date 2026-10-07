#pragma once
#include "schgen/circuit.hpp"
#include <map>
#include <set>
#include <stdexcept>
#include <string>
namespace board_aux_frozen {
using Pins=std::map<std::pair<std::string,std::string>,std::string>;
// Independent prechange51ba61d8 identity oracle. Do not load the regenerated
// circuit.json as its own baseline. Net groups retain every connected pin.
inline Pins pins() {
    const std::map<std::string,std::vector<std::string>> groups{
        {"+3V3",{"U1.5","C1.1","SW1.1","SW1.3","SW1.5","SW1.7"}},
        {"+3V3_AUX",{"U1.1","C2.1","C3.1","D1.2","U2.7","R4.1","R5.1","R6.1","C5.1","TP1.1"}},
        {"GND",{"U1.2","R1.2","C1.2","C2.2","C3.2","R2.2","R3.2","U2.1","C4.2","C5.2"}},
        {"EN_AUX",{"U1.4","SW1.8","R2.1"}}, {"BS_ISET_AUX",{"U1.3","R1.1"}},
        {"BS_PG_AUX",{"D1.1","R3.1"}}, {"+3V3_SC",{"U2.2","C4.1"}},
        {"STM32_I2C2_SCL",{"U2.3"}}, {"STM32_I2C2_SDA",{"U2.4"}},
        {"AUX_I2C_SCL",{"U2.6","R5.2","TP2.1"}}, {"AUX_I2C_SDA",{"U2.5","R6.2","TP3.1"}},
        {"AUX_ISO_EN",{"U2.8","R4.2"}}};
    Pins result;
    for(const auto& [net,ps]:groups)for(const auto& pin:ps){const auto dot=pin.find('.');result.emplace(std::make_pair(pin.substr(0,dot),pin.substr(dot+1)),net);}
    return result;
}
inline void verify(const schgen::CircuitSheetIr& c) {
    auto expected=pins();
    std::set<std::string> refs{"U1","U2","C1","C2","C3","C4","C5","R1","R2","R3","R4","R5","R6","D1","SW1","TP1","TP2","TP3"};
    Pins actual;std::set<std::string> actual_refs,nc;
    for(const auto& n:c.nets)for(const auto& p:n.pins)if(!actual.emplace(std::make_pair(p.ref,p.pin),n.name).second)throw std::runtime_error("duplicate pin");
    for(const auto& p:c.parts)if(!actual_refs.insert(p.ref).second)throw std::runtime_error("duplicate ref");
    for(const auto& p:c.nc)nc.insert(p.ref+"."+p.pin);
    if(actual!=expected||actual_refs!=refs||nc!=std::set<std::string>{"SW1.2","SW1.4","SW1.6"})throw std::runtime_error("frozen original pin/reference/NC identity changed");
}
inline void mutation_checks(const schgen::CircuitSheetIr& c) {
    auto reject=[&](const auto& bad){bool caught=false;try{verify(bad);}catch(const std::runtime_error&){caught=true;}if(!caught)throw std::runtime_error("identity mutation escaped");};
    auto bad=c;for(auto& n:bad.nets)for(auto& p:n.pins)if(p.ref=="R5"&&p.pin=="2")p.ref="R6";else if(p.ref=="R6"&&p.pin=="2")p.ref="R5";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="TP3")p.ref="TP999";reject(bad); // same count, lost original feature
    bad=c;bad.nc.pop_back();reject(bad);
}
}
