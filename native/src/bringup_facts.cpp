#include "schgen/bringup_facts.hpp"
#include "bringup_internal.hpp"
#include <regex>

namespace schgen {
using namespace bringup_detail;

Stm32PinMap stm32_pin_map(const SomZynq& live,const SomInterface& contract) {
    std::map<std::string,std::vector<std::string>> jpins;
    for(const auto& [conn,data]:contract.connectors) for(const auto& [pin,net]:data.pins)jpins[net].push_back(conn+"."+pin);
    for(auto& entry:jpins)std::stable_sort(entry.second.begin(),entry.second.end(),[](const auto& a,const auto& b){
        const auto ap=a.find('.'),bp=b.find('.');
        return std::make_pair(a.substr(0,ap),std::stoi(a.substr(ap+1)))<std::make_pair(b.substr(0,bp),std::stoi(b.substr(bp+1)));
    });
    Stm32PinMap out;out.value=live.value.value_or("None");
    static const std::regex gpio(R"(P([A-G])(\d+))");
    for(const auto& [num,net]:live.ball_net) {
        if(starts(net,"unconnected-"))continue;
        std::smatch m;const auto pname=lookup(live.pin_names,num);
        if(!std::regex_match(pname,m,gpio))continue;
        Stm32Net e{net,m[1],std::stoi(m[2]),jpins[net]};
        (e.j_pins.empty()?out.internal:out.nets)[net]=std::move(e);
    }return out;
}
} // namespace schgen
