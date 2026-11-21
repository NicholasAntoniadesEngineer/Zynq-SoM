#pragma once

#include "schgen/bringup_facts.hpp"
#include "schgen/circuit.hpp"
#include "schgen/link.hpp"
#include "schgen/som_interface.hpp"
#include "schgen/xdc.hpp"

#include <map>
#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* module_pin_map_empty_cell = "-";

struct ModulePinRow {
    std::string connector, pin, module_net, board_net, sheets, port_kind, ball, ball_name, bank, ctrl_port, ctrl_pin;
};

struct ModulePinMap {
    std::vector<ModulePinRow> rows;
    std::string text() const;
};

struct ModulePinInputs {
    const SomInterface& module;
    const LinkMapping& mapping;
    const std::vector<CircuitSheetIr>& sheets;
    const std::map<std::string, std::string>& module_sheets;
    const SomZynq& fpga;
    const Stm32PinMap& controller;
};

ModulePinMap build_module_pin_map(const ModulePinInputs& inputs);

std::vector<std::string> verify_module_pin_map(const ModulePinMap& map, const ModulePinInputs& inputs, const std::vector<XdcPin>& constraints);

}
