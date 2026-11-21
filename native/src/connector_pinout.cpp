#include "schgen/connector_pinout.hpp"

#include "schgen/board_schematic.hpp"
#include "schgen/constraints.hpp"
#include "schgen/placement_report.hpp"

#include <algorithm>
#include <array>
#include <map>
#include <set>
#include <tuple>

namespace schgen {
namespace {

const char* const empty_cell = connector_pinout_empty_cell;
const char* const protect_role = "protect";
const char* const ground_type = "ground";
const char* const port_type = "port";
const char* const signal_type = "signal";
const char* const declared_open = connector_pinout_declared_open;
const char* const list_joiner = ",";
const char* const part_joiner = ":";
const char* const digits = "0123456789";
const char key_separator = '\t';
const std::array scope_classes{PartClass::connector, PartClass::header};

[[noreturn]] void refuse(const std::string& why) { throw ProjectError("connector pinout: " + why); }

std::string key_of(const std::string& first, const std::string& second) { return first + key_separator + second; }

std::string key_of(const std::string& first, const std::string& second, const std::string& third) { return key_of(key_of(first, second), third); }

bool in_scope(const PartFacts& facts, const CircuitSheetIr& sheet, const CircuitPartIr& part) {
    const PartClass kind = symbol_class(facts, part.lib_id, part.ref + " (" + sheet.name + ")");
    return std::find(scope_classes.begin(), scope_classes.end(), kind) != scope_classes.end();
}

bool numeric(const std::string& text) { return !text.empty() && text.find_first_not_of(digits) == std::string::npos; }

bool pin_less(const std::string& a, const std::string& b) {
    const bool a_numeric = numeric(a), b_numeric = numeric(b);
    if (a_numeric != b_numeric) return a_numeric;
    if (a_numeric && std::stoul(a) != std::stoul(b)) return std::stoul(a) < std::stoul(b);
    return a < b;
}

std::map<std::string, std::int64_t> bands_of(const SheetIndex& index) { return {index.begin(), index.end()}; }

std::string board_ref_of(const std::map<std::string, std::int64_t>& bands, const CircuitSheetIr& sheet, const CircuitPartIr& part) {
    const auto band = bands.find(sheet.name);
    if (band == bands.end()) refuse("sheet " + sheet.name + " has no band in the sheet index");
    return board_renamed_ref(part.ref, band->second, sheet.name);
}

std::string net_key(const CircuitSheetIr& sheet, const CircuitNetIr& net) {
    return net.net_class == signal_type ? key_of(sheet.name, net.name) : net.name;
}

using PinNets = std::map<std::string, const CircuitNetIr*>;

PinNets pin_nets_of(const CircuitSheetIr& sheet) {
    PinNets out;
    for (const CircuitNetIr& net : sheet.nets)
        for (const CircuitPinRefIr& pin : net.pins)
            if (!out.emplace(key_of(pin.ref, pin.pin), &net).second) refuse("pin " + pin.ref + "." + pin.pin + " of sheet " + sheet.name + " sits on two nets");
    return out;
}

std::string pin_name_of(const CircuitSheetIr& sheet, const CircuitPartIr& part, const std::string& pin) {
    std::string found;
    for (const CircuitPinNameIr& entry : part.pin_names)
        if (std::find(entry.numbers.begin(), entry.numbers.end(), pin) != entry.numbers.end()) {
            if (!found.empty()) refuse("pin " + pin + " of " + part.ref + " (" + sheet.name + ") has two symbol names");
            found = entry.name;
        }
    if (found.empty()) refuse("pin " + pin + " of " + part.ref + " (" + sheet.name + ") has no symbol pin name");
    return found;
}

using Holders = std::map<std::string, std::map<std::string, PinoutProtector>>;

Holders protectors_by_net(const std::vector<CircuitSheetIr>& sheets, const std::map<std::string, std::int64_t>& bands) {
    Holders out;
    for (const CircuitSheetIr& sheet : sheets) {
        std::set<std::string> guards;
        for (const CircuitServiceIr& served : sheet.layout.serves)
            if (served.role == protect_role) guards.insert(served.part);
        if (guards.empty()) continue;
        std::map<std::string, const CircuitPartIr*> parts;
        for (const CircuitPartIr& part : sheet.parts) parts.emplace(part.ref, &part);
        for (const CircuitNetIr& net : sheet.nets) {
            if (net.net_class == ground_type) continue;
            for (const CircuitPinRefIr& pin : net.pins) {
                if (!guards.count(pin.ref)) continue;
                const auto part = parts.find(pin.ref);
                if (part == parts.end()) refuse("protecting part " + pin.ref + " of sheet " + sheet.name + " is not a part of that sheet");
                const std::string board_ref = board_ref_of(bands, sheet, *part->second);
                out[net_key(sheet, net)].emplace(board_ref, PinoutProtector{board_ref, part->second->value});
            }
        }
    }
    return out;
}

std::string impedance_text(const CircuitPortIr& port) { return port.has_impedance && port.impedance ? std::to_string(port.impedance) : std::string(empty_cell); }

std::string protector_cell(const std::vector<PinoutProtector>& protectors) {
    if (protectors.empty()) return empty_cell;
    std::string out;
    for (const PinoutProtector& item : protectors) out += (out.empty() ? "" : list_joiner) + item.board_ref + part_joiner + item.part;
    return out;
}

}

ConnectorPinout build_connector_pinout(const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PartFacts& facts) {
    const auto bands = bands_of(index);
    const Holders holders = protectors_by_net(sheets, bands);
    ConnectorPinout out;
    for (const CircuitSheetIr& sheet : sheets) {
        const PinNets nets = pin_nets_of(sheet);
        std::set<std::string> open;
        for (const CircuitPinRefIr& pin : sheet.nc) open.insert(key_of(pin.ref, pin.pin));
        for (const CircuitPartIr& part : sheet.parts) {
            if (!in_scope(facts, sheet, part)) continue;
            const std::string board_ref = board_ref_of(bands, sheet, part);
            for (const std::string& pin : part.pin_numbers) {
                ConnectorPinRow row;
                row.sheet = sheet.name;
                row.ref = part.ref;
                row.board_ref = board_ref;
                row.part = part.value;
                row.pin = pin;
                row.pin_name = pin_name_of(sheet, part, pin);
                row.declared = open.count(key_of(part.ref, pin)) ? declared_open : empty_cell;
                const auto net = nets.find(key_of(part.ref, pin));
                if (net == nets.end()) {
                    row.net = row.net_type = row.port_kind = row.route_class = row.impedance = empty_cell;
                } else {
                    const CircuitNetIr& found = *net->second;
                    row.net = found.name;
                    row.net_type = found.net_class;
                    row.port_kind = row.route_class = row.impedance = empty_cell;
                    if (found.net_class == port_type) {
                        const CircuitPortIr port = circuit_port_type(sheet, found.name);
                        row.port_kind = port.kind;
                        row.route_class = port_net_class(port);
                        row.impedance = impedance_text(port);
                    }
                    const auto guards = holders.find(net_key(sheet, found));
                    if (guards != holders.end())
                        for (const auto& [ref, guard] : guards->second) row.protectors.push_back(guard);
                }
                out.rows.push_back(std::move(row));
            }
        }
    }
    std::stable_sort(out.rows.begin(), out.rows.end(), [](const ConnectorPinRow& a, const ConnectorPinRow& b) {
        if (a.sheet != b.sheet) return a.sheet < b.sheet;
        if (a.ref != b.ref) return a.ref < b.ref;
        return pin_less(a.pin, b.pin);
    });
    return out;
}

std::string ConnectorPinout::text() const {
    std::string out = "connector_pins\torder=sheet,ref,pin\n" +
                      placement_report_row({"sheet", "ref", "board_ref", "part", "pin", "pin_name", "net", "net_type", "port", "route_class", "ohm", "declared", "protect"}) + "\n";
    for (const ConnectorPinRow& row : rows)
        out += placement_report_row({row.sheet, row.ref, row.board_ref, row.part, row.pin, row.pin_name, row.net, row.net_type, row.port_kind, row.route_class, row.impedance,
                                     row.declared, protector_cell(row.protectors)}) + "\n";
    return out;
}

std::vector<std::string> verify_connector_pinout(const ConnectorPinout& pinout, const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PartFacts& facts) {
    std::vector<std::string> errors;
    const auto bands = bands_of(index);
    std::map<std::string, std::size_t> seen;
    std::map<std::string, const ConnectorPinRow*> by_key;
    for (const ConnectorPinRow& row : pinout.rows) {
        const std::string key = key_of(row.sheet, row.ref, row.pin);
        ++seen[key];
        by_key.emplace(key, &row);
    }
    std::set<std::string> expected;
    std::set<std::string> connector_nets;
    std::map<std::string, std::set<std::string>> listed_on_net;
    for (const ConnectorPinRow& row : pinout.rows) {
        if (row.net == empty_cell) continue;
        const auto sheet = std::find_if(sheets.begin(), sheets.end(), [&](const CircuitSheetIr& s) { return s.name == row.sheet; });
        if (sheet == sheets.end()) continue;
        const auto net = std::find_if(sheet->nets.begin(), sheet->nets.end(), [&](const CircuitNetIr& n) { return n.name == row.net; });
        if (net == sheet->nets.end()) continue;
        for (const PinoutProtector& guard : row.protectors) listed_on_net[net_key(*sheet, *net)].insert(guard.board_ref);
    }
    for (const CircuitSheetIr& sheet : sheets)
        for (const CircuitPartIr& part : sheet.parts) {
            if (!in_scope(facts, sheet, part)) continue;
            for (const std::string& pin : part.pin_numbers) {
                const std::string key = key_of(sheet.name, part.ref, pin);
                expected.insert(key);
                const auto count = seen.find(key);
                const std::string name = sheet.name + ":" + part.ref + "." + pin;
                if (count == seen.end()) {
                    errors.push_back("connector pin " + name + " is missing from the pinout");
                    continue;
                }
                if (count->second != 1) errors.push_back("connector pin " + name + " appears " + std::to_string(count->second) + " times in the pinout");
                const ConnectorPinRow& row = *by_key.at(key);
                const CircuitNetIr* net = nullptr;
                std::size_t holders = 0;
                for (const CircuitNetIr& candidate : sheet.nets)
                    for (const CircuitPinRefIr& member : candidate.pins)
                        if (member.ref == part.ref && member.pin == pin) {
                            net = &candidate;
                            ++holders;
                        }
                if (holders > 1) errors.push_back("connector pin " + name + " sits on " + std::to_string(holders) + " nets of the circuit");
                const std::string want = net ? net->name : std::string(empty_cell);
                if (row.net != want) errors.push_back("connector pin " + name + " is on net " + row.net + " in the pinout but " + want + " in the circuit");
                const bool open = std::any_of(sheet.nc.begin(), sheet.nc.end(), [&](const CircuitPinRefIr& p) { return p.ref == part.ref && p.pin == pin; });
                if ((row.declared == declared_open) != open)
                    errors.push_back("connector pin " + name + (open ? " is declared unconnected in the circuit but not marked in the pinout" : " is marked unconnected in the pinout but not declared in the circuit"));
                if (open && net) errors.push_back("connector pin " + name + " is declared unconnected but sits on net " + net->name);
                if (!net) continue;
                connector_nets.insert(net_key(sheet, *net));
                const bool typed = net->net_class == port_type;
                const CircuitPortIr port = typed ? circuit_port_type(sheet, net->name) : CircuitPortIr{};
                if (row.port_kind != (typed ? port.kind : std::string(empty_cell))) errors.push_back("connector pin " + name + " lists port kind " + row.port_kind + " that differs from the circuit");
                if (row.route_class != (typed ? port_net_class(port) : std::string(empty_cell)))
                    errors.push_back("connector pin " + name + " lists route class " + row.route_class + " that differs from the layout constraints");
                if (row.impedance != (typed ? impedance_text(port) : std::string(empty_cell)))
                    errors.push_back("connector pin " + name + " lists impedance " + row.impedance + " that differs from the layout constraints");
            }
        }
    for (const auto& [key, count] : seen)
        if (!expected.count(key)) errors.push_back("pinout row " + key + " is not a pin of a connector part of the circuits");
    for (const CircuitSheetIr& sheet : sheets) {
        std::set<std::string> guards;
        for (const CircuitServiceIr& served : sheet.layout.serves)
            if (served.role == protect_role) guards.insert(served.part);
        for (const CircuitNetIr& net : sheet.nets) {
            if (net.net_class == ground_type) continue;
            for (const CircuitPinRefIr& pin : net.pins) {
                if (!guards.count(pin.ref)) continue;
                const auto part = std::find_if(sheet.parts.begin(), sheet.parts.end(), [&](const CircuitPartIr& p) { return p.ref == pin.ref; });
                if (part == sheet.parts.end()) continue;
                const std::string board_ref = board_ref_of(bands, sheet, *part);
                const std::string key = net_key(sheet, net);
                const bool on_connector = connector_nets.count(key) != 0;
                const auto listed = listed_on_net.find(key);
                const bool shown = listed != listed_on_net.end() && listed->second.count(board_ref) != 0;
                if (on_connector && !shown) errors.push_back("protecting part " + board_ref + " sits on connector net " + net.name + " but appears on no pinout row of it");
                if (!on_connector && shown) errors.push_back("protecting part " + board_ref + " is listed on net " + net.name + " that no connector pin reaches");
            }
        }
    }
    for (const ConnectorPinRow& row : pinout.rows)
        for (const PinoutProtector& guard : row.protectors) {
            const auto sheet = std::find_if(sheets.begin(), sheets.end(), [&](const CircuitSheetIr& s) { return s.name == row.sheet; });
            bool found = false;
            for (const CircuitSheetIr& other : sheets) {
                for (const CircuitPartIr& part : other.parts) {
                    if (part.value != guard.part || board_ref_of(bands, other, part) != guard.board_ref) continue;
                    found = std::any_of(other.layout.serves.begin(), other.layout.serves.end(), [&](const CircuitServiceIr& s) { return s.part == part.ref && s.role == protect_role; });
                }
            }
            if (!found || sheet == sheets.end()) errors.push_back("pinout row " + key_of(row.sheet, row.ref, row.pin) + " lists " + guard.board_ref + " that is not a protecting part");
        }
    return errors;
}

}
