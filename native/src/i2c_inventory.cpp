#include "schgen/i2c_inventory.hpp"

#include "schgen/placement_report.hpp"

#include <algorithm>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

namespace schgen {
namespace {

const char* const signal_class = "signal";
const char* const power_class = "power";
const char* const ground_class = "ground";
const char* const i2c_kind = "i2c";
const char* const data_role = "sda";
const char* const clock_role = "scl";
const char* const pull_role = "pull";
const char* const space_joiner = "+";

[[noreturn]] void refuse(const std::string& why) { throw I2cBusError("I2C inventory: " + why); }

std::string instance(const std::string& sheet, const std::string& ref) { return sheet + ":" + ref; }

struct Sheet {
    const ProjectCircuit* source = nullptr;
    std::map<std::string, const CircuitPartIr*> parts;
    std::map<std::pair<std::string, std::string>, const CircuitNetIr*> pin_net;
    std::map<std::string, std::vector<const CircuitNetIr*>> part_nets;
    std::map<std::string, const CircuitNetIr*> nets;

    explicit Sheet(const ProjectCircuit& sheet) : source(&sheet) {
        for (const CircuitPartIr& part : sheet.circuit.parts)
            if (!parts.emplace(part.ref, &part).second) refuse("sheet " + sheet.name + " holds part " + part.ref + " twice");
        for (const CircuitNetIr& net : sheet.circuit.nets) {
            if (!nets.emplace(net.name, &net).second) refuse("sheet " + sheet.name + " holds net " + net.name + " twice");
            for (const CircuitPinRefIr& pin : net.pins) {
                if (!pin_net.emplace(std::make_pair(pin.ref, pin.pin), &net).second)
                    refuse("pin " + pin.ref + "." + pin.pin + " of sheet " + sheet.name + " sits on two nets");
                part_nets[pin.ref].push_back(&net);
            }
        }
    }
    const std::string& name() const { return source->name; }
    std::string key(const CircuitNetIr& net) const { return net.net_class == signal_class ? name() + "/" + net.name : net.name; }
    const CircuitNetIr* net_at(const std::string& ref, const std::string& pin) const {
        const auto found = pin_net.find({ref, pin});
        return found == pin_net.end() ? nullptr : found->second;
    }
    bool serves(const std::string& ref, const std::string& role) const {
        const auto& rows = source->circuit.layout.serves;
        return std::any_of(rows.begin(), rows.end(), [&](const CircuitServiceIr& row) { return row.part == ref && row.role == role; });
    }
};

struct TypedPort {
    std::string sheet;
    const CircuitPortIr* port = nullptr;
};

struct Segment {
    std::string data, clock, name, origin;
};

class Union {
public:
    std::string find(const std::string& key) {
        auto found = parent.find(key);
        if (found == parent.end()) return key;
        const std::string root = find(found->second);
        found->second = root;
        return root;
    }
    void join(const std::string& a, const std::string& b) {
        const std::string ra = find(a), rb = find(b);
        if (ra != rb) parent[std::max(ra, rb)] = std::min(ra, rb);
    }

private:
    std::map<std::string, std::string> parent;
};

const I2cDeviceFact* device_fact(const PartFacts& facts, const CircuitPartIr& part) {
    return part_fact_for(facts.i2c_devices, part.value, part.footprint);
}

const I2cBridgeFact* bridge_fact(const PartFacts& facts, const CircuitPartIr& part) {
    return part_fact_for(facts.i2c_bridges, part.value, part.footprint);
}

std::string part_name(const PartFacts& facts, const CircuitPartIr& part) {
    for (const auto& [name, fact] : facts.i2c_devices)
        if (&fact == device_fact(facts, part)) return name;
    for (const auto& [name, fact] : facts.i2c_bridges)
        if (&fact == bridge_fact(facts, part)) return name;
    refuse("part " + part.ref + " has no I2C row");
}

std::string pin_text(const I2cPinFact& pin) { return pin.name + " (" + pin.number + ")"; }

const CircuitNetIr& pin_net(const Sheet& sheet, const CircuitPartIr& part, const I2cPinFact& pin, const std::string& what) {
    const CircuitNetIr* net = sheet.net_at(part.ref, pin.number);
    if (!net) refuse(what + " " + pin_text(pin) + " of " + instance(sheet.name(), part.ref) + " is on no net");
    return *net;
}

std::map<std::string, std::vector<TypedPort>> typed_ports(const std::vector<Sheet>& sheets) {
    std::map<std::string, std::vector<TypedPort>> out;
    for (const Sheet& sheet : sheets)
        for (const CircuitPortIr& port : sheet.source->circuit.port_types) {
            const auto net = sheet.nets.find(port.net);
            if (net == sheet.nets.end()) refuse("sheet " + sheet.name() + " types port " + port.net + ", which is not one of its nets");
            out[sheet.key(*net->second)].push_back({sheet.name(), &port});
        }
    return out;
}

void check_line(const std::map<std::string, std::vector<TypedPort>>& typed, const std::string& key, const std::string& role,
                const std::string& what) {
    const auto found = typed.find(key);
    if (found == typed.end()) return;
    for (const TypedPort& port : found->second)
        if (port.port->kind != i2c_kind || port.port->role != role)
            refuse(what + " is on net " + key + ", which sheet " + port.sheet + " types as kind " + port.port->kind +
                   (port.port->has_role ? " role " + port.port->role : std::string()) + ", not kind " + i2c_kind + " role " + role);
}

void add_segment(std::map<std::string, Segment>& segments, Segment segment) {
    const auto found = segments.find(segment.data);
    if (found == segments.end()) {
        segments.emplace(segment.data, std::move(segment));
        return;
    }
    if (found->second.clock != segment.clock)
        refuse("data net " + segment.data + " pairs with clock net " + found->second.clock + " (" + found->second.origin + ") and " +
               segment.clock + " (" + segment.origin + ")");
}

std::string select_list(const I2cStrapFact& strap) {
    std::string out;
    for (const auto& [target, value] : strap.selects) out += (out.empty() ? "" : ", ") + target.name;
    return out;
}

int address_of(const Sheet& sheet, const CircuitPartIr& part, const I2cDeviceFact& fact) {
    int address = fact.base;
    for (const I2cStrapFact& strap : fact.straps) {
        const std::string tied = sheet.key(pin_net(sheet, part, strap.pin, "address strap"));
        std::set<int> values;
        for (const auto& [target, value] : strap.selects) {
            const CircuitNetIr* net = sheet.net_at(part.ref, target.number);
            if (net && sheet.key(*net) == tied) values.insert(value);
        }
        if (values.empty())
            refuse("address strap " + pin_text(strap.pin) + " of " + instance(sheet.name(), part.ref) + " is on net " + tied +
                   ", which is the net of none of " + select_list(strap));
        if (values.size() != 1)
            refuse("address strap " + pin_text(strap.pin) + " of " + instance(sheet.name(), part.ref) + " is on net " + tied +
                   ", which selects more than one value among " + select_list(strap));
        address += *values.begin();
    }
    return address;
}

}

std::string i2c_address_hex(int address) {
    std::ostringstream out;
    out << "0x" << std::uppercase << std::hex << std::setfill('0') << std::setw(2) << address;
    return out.str();
}

I2cInventory build_i2c_inventory(const std::vector<ProjectCircuit>& sources, const PartFacts& facts) {
    std::vector<Sheet> sheets;
    for (const ProjectCircuit& source : sources) sheets.emplace_back(source);
    const auto typed = typed_ports(sheets);

    std::map<std::string, Segment> segments;
    struct Placed {
        const Sheet* sheet;
        const CircuitPartIr* part;
        const I2cDeviceFact* fact;
        std::string data;
    };
    std::vector<Placed> placed;
    for (const Sheet& sheet : sheets)
        for (const CircuitPartIr& part : sheet.source->circuit.parts) {
            const I2cDeviceFact* fact = device_fact(facts, part);
            if (!fact) continue;
            const std::string who = instance(sheet.name(), part.ref);
            const CircuitNetIr& data = pin_net(sheet, part, fact->data, "data pin");
            const CircuitNetIr& clock = pin_net(sheet, part, fact->clock, "clock pin");
            for (const CircuitNetIr* net : {&data, &clock})
                if (net->net_class == power_class || net->net_class == ground_class)
                    refuse("a bus pin of " + who + " is on the " + net->net_class + " net " + net->name);
            if (&data == &clock) refuse("the data and clock pins of " + who + " share net " + data.name);
            check_line(typed, sheet.key(data), data_role, "data pin " + pin_text(fact->data) + " of " + who);
            check_line(typed, sheet.key(clock), clock_role, "clock pin " + pin_text(fact->clock) + " of " + who);
            add_segment(segments, {sheet.key(data), sheet.key(clock), {}, who});
            placed.push_back({&sheet, &part, fact, sheet.key(data)});
        }
    for (const Sheet& sheet : sheets) {
        std::map<std::string, std::pair<std::vector<std::string>, std::vector<std::string>>> lines;
        for (const CircuitPortIr& port : sheet.source->circuit.port_types) {
            if (port.kind != i2c_kind) continue;
            if (!port.has_bus) refuse("sheet " + sheet.name() + " types " + port.net + " as " + i2c_kind + " with no bus");
            const std::string key = sheet.key(*sheet.nets.at(port.net));
            (port.role == data_role ? lines[port.bus].first : lines[port.bus].second).push_back(key);
        }
        for (const auto& [bus, pair] : lines) {
            if (pair.first.size() != 1 || pair.second.size() != 1)
                refuse("sheet " + sheet.name() + " types bus " + bus + " with " + std::to_string(pair.first.size()) + " data and " +
                       std::to_string(pair.second.size()) + " clock ports, not one of each");
            add_segment(segments, {pair.first.front(), pair.second.front(), {}, "sheet " + sheet.name() + " bus " + bus});
        }
    }
    std::set<std::string> clocks;
    for (const auto& [data, segment] : segments) clocks.insert(segment.clock);
    for (const auto& [data, segment] : segments)
        if (clocks.count(data)) refuse("net " + data + " is the data net of one bus and the clock net of another");

    std::map<std::string, std::string> owner;
    for (auto& [data, segment] : segments) {
        std::set<std::string> names;
        for (const std::string& key : {segment.data, segment.clock}) {
            const auto found = typed.find(key);
            if (found == typed.end()) continue;
            for (const TypedPort& port : found->second)
                if (port.port->kind == i2c_kind && port.port->has_bus) names.insert(port.port->bus);
        }
        if (names.size() > 1) {
            std::string list;
            for (const std::string& name : names) list += (list.empty() ? "" : ", ") + name;
            refuse("the bus on data net " + segment.data + " is typed with more than one bus name: " + list);
        }
        segment.name = names.empty() ? segment.data : *names.begin();
        const auto [at, fresh] = owner.emplace(segment.name, segment.data);
        if (!fresh) refuse("bus name " + segment.name + " labels two electrical buses, data nets " + at->second + " and " + segment.data);
    }

    I2cInventory inventory;
    Union spaces;
    for (const Sheet& sheet : sheets)
        for (const CircuitPartIr& part : sheet.source->circuit.parts) {
            const I2cBridgeFact* fact = bridge_fact(facts, part);
            if (!fact) continue;
            for (const auto& [from, to] : fact->joins) {
                const std::string a = sheet.key(pin_net(sheet, part, from, "bridge pin"));
                const std::string b = sheet.key(pin_net(sheet, part, to, "bridge pin"));
                if (fact->shares_addresses) spaces.join(a, b);
                inventory.bridges.push_back({sheet.name(), part.ref, part_name(facts, part), a, b, fact->shares_addresses});
            }
        }
    std::map<std::string, std::set<std::string>> members;
    std::map<std::string, std::string> clock_space;
    for (const auto& [data, segment] : segments) {
        const std::string root = spaces.find(data);
        members[root].insert(segment.name);
        const auto [at, fresh] = clock_space.emplace(root, spaces.find(segment.clock));
        if (!fresh && at->second != spaces.find(segment.clock))
            refuse("bus " + segment.name + " shares the data line of another bus but not its clock line");
    }
    std::map<std::string, std::string> space_name;
    for (const auto& [root, names] : members) {
        std::string name;
        for (const std::string& bus : names) name += (name.empty() ? "" : space_joiner) + bus;
        space_name[root] = name;
    }
    std::map<std::string, std::pair<std::string, std::string>> line_of;
    for (const auto& [data, segment] : segments) {
        inventory.buses.push_back({segment.name, space_name.at(spaces.find(data)), segment.data, segment.clock});
        line_of[segment.data] = {segment.name, data_role};
        line_of[segment.clock] = {segment.name, clock_role};
    }

    for (const Sheet& sheet : sheets)
        for (const CircuitNetIr& net : sheet.source->circuit.nets) {
            if (!line_of.count(sheet.key(net))) continue;
            for (const CircuitPinRefIr& pin : net.pins) {
                const auto part = sheet.parts.find(pin.ref);
                if (part == sheet.parts.end())
                    refuse("net " + sheet.key(net) + " names pin " + pin.ref + "." + pin.pin + " of no part on sheet " + sheet.name());
                const CircuitPartIr& p = *part->second;
                if (device_fact(facts, p) || bridge_fact(facts, p)) continue;
                const std::string who = instance(sheet.name(), p.ref);
                if (symbol_class(facts, p.lib_id, who) != PartClass::integrated_circuit) continue;
                refuse(who + " (" + p.value + ") is an integrated circuit on bus net " + sheet.key(net) +
                       " with no i2c_devices or i2c_bridges row");
            }
        }

    for (const Placed& device : placed) {
        const auto& segment = segments.at(device.data);
        inventory.devices.push_back({device.sheet->name(), device.part->ref, part_name(facts, *device.part), device.fact->label,
                                     segment.name, space_name.at(spaces.find(device.data)),
                                     address_of(*device.sheet, *device.part, *device.fact)});
    }

    for (const Sheet& sheet : sheets)
        for (const CircuitPartIr& part : sheet.source->circuit.parts) {
            if (!sheet.serves(part.ref, pull_role)) continue;
            const auto found = sheet.part_nets.find(part.ref);
            if (found == sheet.part_nets.end()) continue;
            const auto& nets = found->second;
            for (const CircuitNetIr* net : nets) {
                const auto line = line_of.find(sheet.key(*net));
                if (line == line_of.end()) continue;
                const std::string who = instance(sheet.name(), part.ref);
                if (nets.size() != 2) refuse("pull-up " + who + " on bus net " + sheet.key(*net) + " has " + std::to_string(nets.size()) + " netted pins, not two");
                const CircuitNetIr* rail = nets.front() == net ? nets.back() : nets.front();
                inventory.pullups.push_back({line->second.first, line->second.second, sheet.name(), part.ref, part.value, sheet.key(*rail)});
            }
        }

    std::sort(inventory.buses.begin(), inventory.buses.end(),
              [](const I2cBus& a, const I2cBus& b) { return std::tie(a.space, a.name) < std::tie(b.space, b.name); });
    std::sort(inventory.devices.begin(), inventory.devices.end(), [](const I2cDevice& a, const I2cDevice& b) {
        return std::tie(a.space, a.address, a.sheet, a.ref) < std::tie(b.space, b.address, b.sheet, b.ref);
    });
    std::sort(inventory.bridges.begin(), inventory.bridges.end(), [](const I2cBridgeLink& a, const I2cBridgeLink& b) {
        return std::tie(a.sheet, a.ref, a.from) < std::tie(b.sheet, b.ref, b.from);
    });
    std::sort(inventory.pullups.begin(), inventory.pullups.end(), [](const I2cPullup& a, const I2cPullup& b) {
        return std::tie(a.bus, a.line, a.sheet, a.ref) < std::tie(b.bus, b.line, b.sheet, b.ref);
    });
    return inventory;
}

std::string I2cInventory::text() const {
    std::string out = "buses\torder=space,bus\n" + placement_report_row({"space", "bus", "sda", "scl"}) + "\n";
    for (const I2cBus& bus : buses) out += placement_report_row({bus.space, bus.name, bus.data, bus.clock}) + "\n";
    out += "devices\torder=space,address,sheet,ref\n" + placement_report_row({"space", "bus", "address", "sheet", "ref", "part"}) + "\n";
    for (const I2cDevice& d : devices)
        out += placement_report_row({d.space, d.bus, i2c_address_hex(d.address), d.sheet, d.ref, d.part}) + "\n";
    out += "bridges\torder=sheet,ref,from\n" + placement_report_row({"sheet", "ref", "part", "from", "to", "shared"}) + "\n";
    for (const I2cBridgeLink& b : bridges)
        out += placement_report_row({b.sheet, b.ref, b.part, b.from, b.to, b.shared ? "yes" : "no"}) + "\n";
    out += "pullups\torder=bus,line,sheet,ref\n" + placement_report_row({"bus", "line", "sheet", "ref", "value", "rail"}) + "\n";
    for (const I2cPullup& p : pullups) out += placement_report_row({p.bus, p.line, p.sheet, p.ref, p.value, p.rail}) + "\n";
    return out;
}

std::vector<std::string> i2c_address_collisions(const I2cInventory& inventory) {
    std::map<std::pair<std::string, int>, std::vector<const I2cDevice*>> shared;
    for (const I2cDevice& device : inventory.devices) shared[{device.space, device.address}].push_back(&device);
    std::vector<std::string> out;
    for (const auto& [where, devices] : shared) {
        if (devices.size() < 2) continue;
        std::string list;
        for (const I2cDevice* d : devices) list += (list.empty() ? "" : ", ") + instance(d->sheet, d->ref) + "=" + i2c_address_hex(d->address);
        out.push_back("I2C address collision on " + where.first + ": " + list);
    }
    return out;
}

std::vector<std::string> verify_i2c_inventory(const I2cInventory& inventory, const std::vector<ProjectCircuit>& sheets,
                                              const PartFacts& facts) {
    std::vector<std::string> errors;
    std::map<std::string, std::size_t> seen;
    for (const I2cDevice& device : inventory.devices) ++seen[instance(device.sheet, device.ref)];
    std::set<std::string> expected;
    for (const ProjectCircuit& sheet : sheets)
        for (const CircuitPartIr& part : sheet.circuit.parts) {
            if (!device_fact(facts, part)) continue;
            const std::string key = instance(sheet.name, part.ref);
            expected.insert(key);
            const auto count = seen.find(key);
            if (count == seen.end()) errors.push_back("I2C device " + key + " is missing from the bus map");
            else if (count->second != 1) errors.push_back("I2C device " + key + " appears " + std::to_string(count->second) + " times in the bus map");
        }
    for (const auto& [key, count] : seen)
        if (!expected.count(key)) errors.push_back("bus map device " + key + " is not an I2C device of the circuits");
    std::set<std::pair<std::string, std::string>> buses;
    for (const I2cBus& bus : inventory.buses) buses.emplace(bus.name, bus.space);
    for (const I2cDevice& device : inventory.devices)
        if (!buses.count({device.bus, device.space}))
            errors.push_back("bus map device " + instance(device.sheet, device.ref) + " names bus " + device.bus + " in space " + device.space +
                             ", which the bus list does not hold");
    return errors;
}

void check_i2c_address_collisions(const std::vector<ProjectCircuit>& sheets) {
    const auto collisions = i2c_address_collisions(build_i2c_inventory(sheets, default_part_facts()));
    if (collisions.empty()) return;
    std::string text;
    for (const std::string& line : collisions) text += (text.empty() ? "" : "; ") + line;
    throw I2cBusError(text);
}

}
