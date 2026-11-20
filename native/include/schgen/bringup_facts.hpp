#pragma once

#include "schgen/project.hpp"
#include "schgen/som_interface.hpp"
#include <map>
#include <optional>

namespace schgen {

struct Stm32Net {
    std::string net, port;
    int pin = 0;
    std::vector<std::string> j_pins;
};
struct Stm32PinMap {
    std::string value;
    std::map<std::string, Stm32Net> nets, internal;
};
struct BringupExpander { std::string ref; int addr = 0; ProjectStrings ports; };
struct BringupMonitor {
    std::string ref;
    int addr = 0;
    std::map<int, std::pair<std::string, std::string>> channels;
};

Stm32PinMap stm32_pin_map(const SomZynq& live, const SomInterface& contract);
BringupExpander bringup_expander(const CircuitSheetIr&);
std::vector<BringupMonitor> ina3221_monitors(const CircuitSheetIr&);
int bringup_id_eeprom_addr(const CircuitSheetIr&);

} // namespace schgen
