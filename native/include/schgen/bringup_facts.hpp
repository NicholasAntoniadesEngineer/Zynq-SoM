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
struct DipPosition { std::string switch_ref; int position = 0; std::string net; };
struct EnCell { std::string sheet, gate, dip_net, override_net, enable; };
struct BringupExpander { std::string ref; int addr = 0; ProjectStrings ports; };
struct BringupMonitor {
    std::string ref;
    int addr = 0;
    std::map<int, std::pair<std::string, std::string>> channels;
};
struct RegulatorStage {
    std::string ref, value, enable, rail_in, rail_out;
    std::optional<double> vout;
    std::optional<std::string> pg_led;
};
struct ModuleGate {
    std::string ref, module, rail_in, rail_out, enable;
    std::optional<int> ilim_ma;
    std::optional<std::string> status_led;
};

std::optional<double> bringup_parse_value_ohms(const std::string&);
std::string bringup_c_ident(const std::string&);
Stm32PinMap stm32_pin_map(const SomZynq& live, const SomInterface& contract);
std::vector<std::string> dip_switch_refs(const CircuitSheetIr&);
std::vector<DipPosition> dip_positions(const CircuitSheetIr&, const std::string& ref,
    const std::vector<std::string>& common = {"+3V3_SC", "GND"});
std::vector<EnCell> en_cells(const CircuitSheetIr&);
BringupExpander bringup_expander(const CircuitSheetIr&);
std::vector<BringupMonitor> ina3221_monitors(const CircuitSheetIr&);
std::vector<RegulatorStage> regulator_chain(const CircuitSheetIr& power,
    const std::string& root = "+VIN", const CircuitSheetIr* monitor = nullptr);
std::vector<ModuleGate> module_gates(const CircuitSheetIr&);
std::optional<int> bringup_shunt_mohm(const CircuitSheetIr&,
    const std::string& in_p, const std::string& in_n);
int bringup_id_eeprom_addr(const CircuitSheetIr&);

} // namespace schgen
