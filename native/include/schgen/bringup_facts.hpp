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

Stm32PinMap stm32_pin_map(const SomZynq& live, const SomInterface& contract);

} // namespace schgen
