#pragma once
#include "schgen/authoring.hpp"
#include <algorithm>
#include <array>
#include <stdexcept>
#include <vector>

namespace direct_enable_reference {
inline void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
// Test-only forward projection of the immutable pre-d2a1ec20 oracle. Never
// overwrite a live circuit or bless new output. All unlisted fields survive
// for the consumer's complete independent IR comparison.
inline schgen::CircuitSheetIr project(schgen::CircuitSheetIr old){
    require(old.name=="power_som","direct-enable reference requires power_som");
    const auto retired=[](const std::string& ref){return ref=="R12"||ref=="D5"||ref=="C20";};
    const std::array<std::array<const char*,5>,3> identities{{
        {{"R12","Device:R","10k","Resistor_SMD:R_0603_1608Metric","C25804"}},
        {{"D5","Device:D_Zener","MMSZ5231B","Diode_SMD:D_SOD-123","C85181"}},
        {{"C20","Device:C","100n","Capacitor_SMD:C_0603_1608Metric","C14663"}}
    }};
    for(const auto& id:identities){
        require(std::count_if(old.parts.begin(),old.parts.end(),[&](const auto& p){return p.ref==id[0];})==1,
                "unique retired reference part");
        const auto& p=*std::find_if(old.parts.begin(),old.parts.end(),[&](const auto& p){return p.ref==id[0];});
        require(p.lib_id==id[1]&&p.value==id[2]&&p.footprint==id[3]&&
            p.fields.size()==1&&p.fields[0].key=="LCSC"&&p.fields[0].value==id[4]&&
            p.pin_names.empty()&&p.pin_numbers.empty(),"exact retired reference identity");
    }
    std::vector<std::pair<std::string,std::string>> connections;
    for(const auto& net:old.nets)for(const auto& pin:net.pins)
        if(retired(pin.ref)||(pin.ref=="U4"&&pin.pin=="7"))
            connections.emplace_back(pin.ref+"."+pin.pin,net.name);
    std::sort(connections.begin(),connections.end());
    require(connections==std::vector<std::pair<std::string,std::string>>{
        {"C20.1","EN_5V_SOM"},{"C20.2","GND"},{"D5.1","EN_5V_SOM"},
        {"D5.2","GND"},{"R12.1","+VIN_SYS"},{"R12.2","EN_5V_SOM"},{"U4.7","EN_5V_SOM"}},
        "exact retired reference connectivity");
    for(const std::string name:{"+VIN_SYS","EN_5V_SOM"})
        require(std::count_if(old.nets.begin(),old.nets.end(),[&](const auto& n){return n.name==name;})==1,
                "unique reference enable and supply nets");
    const auto& enable=*std::find_if(old.nets.begin(),old.nets.end(),[](const auto& n){return n.name=="EN_5V_SOM";});
    require(enable.pins.size()==4&&enable.net_class=="signal","retired net has no unreviewed consumers");
    old.parts.erase(std::remove_if(old.parts.begin(),old.parts.end(),[&](const auto& p){return retired(p.ref);}),old.parts.end());
    old.nets.erase(std::remove_if(old.nets.begin(),old.nets.end(),[](const auto& n){return n.name=="EN_5V_SOM";}),old.nets.end());
    for(auto& net:old.nets){
        net.pins.erase(std::remove_if(net.pins.begin(),net.pins.end(),[&](const auto& p){return retired(p.ref);}),net.pins.end());
        if(net.name=="+VIN_SYS")net.pins.insert(net.pins.begin(),{"U4","7"});
    }
    return old;
}
}
