#include "schgen/module_pin_map.hpp"

#include "schgen/placement_report.hpp"
#include "schgen/project.hpp"

#include <algorithm>
#include <regex>
#include <set>
#include <tuple>

namespace schgen {
namespace {

const char* const empty_cell = module_pin_map_empty_cell;
const char* const list_joiner = ",";
const char* const key_joiner = ".";
const char* const default_port_kind = "single";
const char* const port_class = "port";
const char* const signal_class = "signal";
const char* const open_prefix = "unconnected-";
const char* const programmable_prefix = "IO_";
const char* const bank_pattern = "_([0-9]+)$";
const char* const digits = "0123456789";

[[noreturn]] void refuse(const std::string& why) { throw ProjectError("module pin map: " + why); }

std::string key_of(const std::string& connector, const std::string& pin) { return connector + key_joiner + pin; }

bool starts(const std::string& text, const std::string& prefix) { return text.rfind(prefix, 0) == 0; }

bool numeric(const std::string& text) { return !text.empty() && text.find_first_not_of(digits) == std::string::npos; }

bool pin_less(const std::string& a, const std::string& b) {
    const bool a_numeric = numeric(a), b_numeric = numeric(b);
    if (a_numeric != b_numeric) return a_numeric;
    if (a_numeric && std::stoul(a) != std::stoul(b)) return std::stoul(a) < std::stoul(b);
    return a < b;
}

std::string joined(const std::set<std::string>& items) {
    if (items.empty()) return empty_cell;
    std::string out;
    for (const std::string& item : items) out += (out.empty() ? "" : list_joiner) + item;
    return out;
}

std::set<std::string> split(const std::string& cell) {
    std::set<std::string> out;
    if (cell == empty_cell) return out;
    std::size_t start = 0;
    while (start <= cell.size()) {
        const std::size_t end = cell.find(list_joiner, start);
        out.insert(cell.substr(start, end == std::string::npos ? end : end - start));
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return out;
}

const std::string* mapped(const std::map<std::string, std::string>& table, const std::string& key) {
    const auto found = table.find(key);
    return found == table.end() ? nullptr : &found->second;
}

std::string board_net_of(const std::string& module_net, const LinkMapping& mapping) {
    if (starts(module_net, open_prefix)) return empty_cell;
    for (const auto* table : {&mapping.function_map, &mapping.pudc_straps, &mapping.vcco_rail_map, &mapping.rebound_som_rails})
        if (const std::string* target = mapped(*table, module_net)) return *target;
    for (const auto& [rail, reason] : mapping.isolated_som_rails) {
        (void)reason;
        const std::string* alias = mapped(mapping.rail_aliases, rail);
        if ((alias ? *alias : rail) == module_net) return empty_cell;
    }
    return module_net;
}

using PinNets = std::map<std::pair<std::string, std::string>, std::string>;

bool module_sheet(const std::map<std::string, std::string>& module_sheets, const std::string& sheet) {
    const auto found = module_sheets.find(sheet);
    return found != module_sheets.end() && !found->second.empty();
}

PinNets circuit_pin_nets(const ModulePinInputs& in) {
    PinNets out;
    for (const CircuitSheetIr& sheet : in.sheets) {
        if (!module_sheet(in.module_sheets, sheet.name)) continue;
        const auto role = in.module_sheets.find(sheet.name);
        for (const CircuitNetIr& net : sheet.nets)
            for (const CircuitPinRefIr& pin : net.pins) {
                if (pin.ref != role->second) continue;
                if (!out.emplace(std::make_pair(role->second, pin.pin), net.name).second)
                    refuse("pin " + key_of(role->second, pin.pin) + " sits on two nets of the circuits");
            }
    }
    return out;
}

std::map<std::string, std::string> names_of(const XdcStrings& table) {
    std::map<std::string, std::string> out;
    for (const auto& [key, value] : table) out[key] = value;
    return out;
}

bool consumer_net(const CircuitNetIr& net, const std::string& name) { return net.name == name && net.net_class != signal_class; }

}

ModulePinMap build_module_pin_map(const ModulePinInputs& in) {
    const PinNets circuit = circuit_pin_nets(in);
    const auto ball_names = names_of(in.fpga.pin_names);
    std::map<std::string, std::set<std::string>> net_balls;
    for (const auto& [ball, net] : in.fpga.ball_net) {
        const auto name = ball_names.find(ball);
        if (name != ball_names.end() && starts(name->second, programmable_prefix)) net_balls[net].insert(ball);
    }
    std::map<std::string, std::pair<std::string, std::string>> controller_pins;
    for (const auto& [net, entry] : in.controller.nets)
        for (const std::string& jpin : entry.j_pins) controller_pins[jpin] = {entry.port, std::to_string(entry.pin)};
    const std::regex bank(bank_pattern);
    ModulePinMap map;
    for (const auto& [connector, data] : in.module.connectors)
        for (const auto& [pin, module_net] : data.pins) {
            ModulePinRow row;
            row.connector = connector;
            row.pin = pin;
            row.module_net = module_net;
            row.board_net = board_net_of(module_net, in.mapping);
            std::set<std::string> sheets, kinds, balls, names, banks;
            if (row.board_net != empty_cell)
                for (const CircuitSheetIr& sheet : in.sheets) {
                    if (module_sheet(in.module_sheets, sheet.name)) continue;
                    const auto net = std::find_if(sheet.nets.begin(), sheet.nets.end(), [&](const CircuitNetIr& n) { return consumer_net(n, row.board_net); });
                    if (net == sheet.nets.end()) continue;
                    sheets.insert(sheet.name);
                    const auto typed = std::find_if(sheet.port_types.begin(), sheet.port_types.end(), [&](const CircuitPortIr& p) { return p.net == row.board_net; });
                    if (typed != sheet.port_types.end() && !typed->kind.empty()) kinds.insert(typed->kind);
                    else if (net->net_class == port_class) kinds.insert(default_port_kind);
                }
            const auto owned = net_balls.find(module_net);
            if (owned != net_balls.end())
                for (const std::string& ball : owned->second) {
                    balls.insert(ball);
                    names.insert(ball_names.at(ball));
                    std::smatch suffix;
                    if (std::regex_search(ball_names.at(ball), suffix, bank)) banks.insert(suffix[1].str());
                }
            row.sheets = joined(sheets);
            row.port_kind = joined(kinds);
            row.ball = joined(balls);
            row.ball_name = joined(names);
            row.bank = joined(banks);
            const auto drive = controller_pins.find(key_of(connector, pin));
            row.ctrl_port = drive == controller_pins.end() ? empty_cell : drive->second.first;
            row.ctrl_pin = drive == controller_pins.end() ? empty_cell : drive->second.second;
            map.rows.push_back(std::move(row));
        }
    std::stable_sort(map.rows.begin(), map.rows.end(), [](const ModulePinRow& a, const ModulePinRow& b) {
        if (a.connector != b.connector) return a.connector < b.connector;
        return pin_less(a.pin, b.pin);
    });
    return map;
}

std::string ModulePinMap::text() const {
    std::string out = "module_pins\torder=connector,pin\n" +
                      placement_report_row({"conn", "pin", "module_net", "board_net", "sheets", "port", "ball", "ball_name", "bank", "ctrl_port", "ctrl_pin"}) + "\n";
    for (const ModulePinRow& row : rows)
        out += placement_report_row({row.connector, row.pin, row.module_net, row.board_net, row.sheets, row.port_kind, row.ball, row.ball_name, row.bank,
                                     row.ctrl_port, row.ctrl_pin}) + "\n";
    return out;
}

std::vector<std::string> verify_module_pin_map(const ModulePinMap& map, const ModulePinInputs& in, const std::vector<XdcPin>& constraints) {
    std::vector<std::string> errors;
    const auto ball_names = names_of(in.fpga.pin_names);
    std::map<std::string, std::size_t> seen;
    std::map<std::string, const ModulePinRow*> by_key;
    for (const ModulePinRow& row : map.rows) {
        ++seen[key_of(row.connector, row.pin)];
        by_key.emplace(key_of(row.connector, row.pin), &row);
    }
    const PinNets circuit = circuit_pin_nets(in);
    std::set<std::string> expected;
    for (const auto& [connector, data] : in.module.connectors)
        for (const auto& [pin, net] : data.pins) {
            const std::string key = key_of(connector, pin);
            expected.insert(key);
            const auto count = seen.find(key);
            if (count == seen.end()) {
                errors.push_back("pin " + key + " is missing from the map");
                continue;
            }
            if (count->second != 1) errors.push_back("pin " + key + " appears " + std::to_string(count->second) + " times in the map");
            const ModulePinRow& row = *by_key.at(key);
            if (row.module_net != net) errors.push_back("pin " + key + " is on module net " + row.module_net + " in the map but " + net + " in the module interface");
            const auto placed = circuit.find({connector, pin});
            const std::string board = placed == circuit.end() ? std::string(empty_cell) : placed->second;
            if (row.board_net != board) errors.push_back("pin " + key + " is on board net " + row.board_net + " in the map but " + board + " in the circuits");
        }
    for (const auto& [key, count] : seen)
        if (!expected.count(key)) errors.push_back("map row " + key + " is not a pin of the module interface");
    for (const ModulePinRow& row : map.rows) {
        const std::string key = key_of(row.connector, row.pin);
        std::set<std::string> holders;
        if (row.board_net != empty_cell)
            for (const CircuitSheetIr& sheet : in.sheets)
                if (!module_sheet(in.module_sheets, sheet.name) &&
                    std::any_of(sheet.nets.begin(), sheet.nets.end(), [&](const CircuitNetIr& n) { return consumer_net(n, row.board_net); }))
                    holders.insert(sheet.name);
        if (split(row.sheets) != holders) errors.push_back("pin " + key + " lists sheets " + row.sheets + " but the circuits carry net " + row.board_net + " on " + joined(holders));
        std::set<std::string> balls;
        for (const auto& [ball, net] : in.fpga.ball_net) {
            if (net != row.module_net) continue;
            const auto name = ball_names.find(ball);
            if (name != ball_names.end() && starts(name->second, programmable_prefix)) balls.insert(ball);
        }
        if (split(row.ball) != balls) errors.push_back("pin " + key + " lists balls " + row.ball + " but the module netlist puts net " + row.module_net + " on " + joined(balls));
        const bool wired = row.ctrl_port != empty_cell || row.ctrl_pin != empty_cell;
        bool known = false;
        for (const auto& [net, entry] : in.controller.nets)
            if (std::find(entry.j_pins.begin(), entry.j_pins.end(), key) != entry.j_pins.end()) {
                known = true;
                if (row.ctrl_port != entry.port || row.ctrl_pin != std::to_string(entry.pin))
                    errors.push_back("pin " + key + " is on controller " + row.ctrl_port + "/" + row.ctrl_pin + " in the map but " + entry.port + "/" + std::to_string(entry.pin) + " in the controller map");
            }
        if (wired && !known) errors.push_back("pin " + key + " names controller " + row.ctrl_port + "/" + row.ctrl_pin + " that the controller map does not know");
    }
    for (const XdcPin& entry : constraints) {
        const auto row = by_key.find(entry.jpin);
        if (row == by_key.end()) {
            errors.push_back("constrained pin " + entry.jpin + " is missing from the map");
            continue;
        }
        if (row->second->ball != entry.ball) errors.push_back("pin " + entry.jpin + " is on ball " + row->second->ball + " in the map but " + entry.ball + " in the constraints");
        if (row->second->bank != entry.bank) errors.push_back("pin " + entry.jpin + " is in bank " + row->second->bank + " in the map but " + entry.bank + " in the constraints");
        if (row->second->board_net != entry.net) errors.push_back("pin " + entry.jpin + " is on board net " + row->second->board_net + " in the map but " + entry.net + " in the constraints");
    }
    return errors;
}

}
