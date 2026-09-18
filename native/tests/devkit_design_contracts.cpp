// Devkit electrical regression: real canonical designs, no Python or catalogs.
// Usage: schgen_devkit_design_contracts <repository-root>
#include "schgen/project.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using schgen::CircuitPartIr;
using schgen::CircuitSheetIr;
using Board = std::vector<schgen::ProjectCircuit>;

void require(bool value, const std::string& message) {
    // Keep every assertion active in Release/NDEBUG builds.
    if (!value) throw std::runtime_error(message);
}

const CircuitSheetIr& sheet(const Board& board, const std::string& name) {
    for (const auto& entry : board) if (entry.name == name) return entry.circuit;
    throw std::runtime_error("missing sheet " + name);
}

std::string field(const CircuitPartIr& part, const std::string& key) {
    for (const auto& item : part.fields) if (item.key == key) return item.value;
    return {};
}

std::string net_of(const CircuitSheetIr& circuit, const std::string& ref,
                   const std::string& pin) {
    std::string found;
    for (const auto& net : circuit.nets) {
        for (const auto& p : net.pins) {
            if (p.ref != ref || p.pin != pin) continue;
            require(found.empty() || found == net.name, "multiply connected pin " + ref);
            found = net.name;
        }
    }
    return found;
}

std::vector<std::string> check_pullup(const Board& board, const std::string& net) {
    std::vector<std::string> owners;
    for (const auto& entry : board) {
        for (const auto& part : entry.circuit.parts) {
            if (part.lib_id != "Device:R") continue;
            const auto a = net_of(entry.circuit, part.ref, "1");
            const auto b = net_of(entry.circuit, part.ref, "2");
            if (a != net && b != net) continue;
            require((a == net ? b : a) == "+3V3_SC", net + " pull-up on wrong rail");
            require(part.value == "4k7" && field(part, "LCSC") == "C23162"
                    && part.footprint == "Resistor_SMD:R_0603_1608Metric"
                    && field(part, "BOM") != "exclude", net + " wrong pull-up part");
            owners.push_back(entry.name + ":" + part.ref);
        }
    }
    require(owners.size() == 1 && owners.front().find("debug_boot:") == 0,
            net + " needs exactly one populated local pull-up");
    return owners;
}

struct Probe {
    const char* net;
    const char* owner;
    const char* ref;
};
const std::vector<Probe> probes = {
    {"+3V3_SC", "power_mon", "TP1"},
    {"STM32_I2C2_SCL", "power_mon", "TP2"},
    {"STM32_I2C2_SDA", "power_mon", "TP3"},
    {"EN_5V0", "power", "TP5"},
    {"EN_3V3", "power", "TP6"},
    {"EN_1V8", "power", "TP7"},
    {"SDIO_CLK", "debug_boot", "TP1"},
    {"SDIO_CMD", "debug_boot", "TP2"},
    {"VBUS_OUT_EN", "debug_boot", "TP3"},
};

void check_probe(const Board& board, const Probe& expected) {
    std::vector<std::string> owners;
    for (const auto& entry : board) {
        for (const auto& waiver : entry.circuit.waivers) {
            require(waiver.kind != "tp_waivers" || waiver.key != expected.net,
                    std::string(expected.net) + " must have a physical pad, not a waiver");
        }
        for (const auto& part : entry.circuit.parts) {
            if (part.lib_id != "Connector:TestPoint"
                || net_of(entry.circuit, part.ref, "1") != expected.net) continue;
            require(part.footprint == "TestPoint:TestPoint_Pad_D1.5mm"
                    && part.value == expected.net && field(part, "BOM") == "exclude",
                    std::string(expected.net) + " needs an unpopulated physical copper pad");
            require(entry.name.rfind("som_j", 0) != 0,
                    "probe would be skipped by connector-only PCB seating");
            owners.push_back(entry.name + ":" + part.ref);
        }
    }
    require(owners == std::vector<std::string>{std::string(expected.owner) + ":" + expected.ref},
            std::string(expected.net) + " missing/misplaced/duplicate physical testpoint");
}

void check_interfaces(const Board& board) {
    const auto& monitor = sheet(board, "power_mon");
    for (const auto* net : {"STM32_I2C2_SCL", "STM32_I2C2_SDA"}) {
        const auto pt = schgen::circuit_port_type(monitor, net);
        const bool clock = std::string(net) == "STM32_I2C2_SCL";
        require(pt.kind == "i2c" && pt.bus == "STM32_I2C2"
                && pt.role == (clock ? "scl" : "sda")
                && pt.has_speed_hz && pt.speed_hz == 400000, "I2C type/speed drift");
        for (const auto* ref : {"U1", "U2"}) {
            require(net_of(monitor, ref, clock ? "6" : "7") == net,
                    "pull-up disconnected from INA3221 bus");
        }
    }
    double draw = 0;
    for (const auto& load : monitor.loads) if (load.rail == "+3V3_SC") draw += load.amps;
    require(std::abs(draw - 0.002) < 1e-12, "monitor load budget changed");
    draw = 0;
    for (const auto& load : sheet(board, "debug_boot").loads) {
        if (load.rail == "+3V3_SC") draw += load.amps;
    }
    require(std::abs(draw - 0.0055) < 1e-12, "debug budget lost both I2C pull-up loads");
    // +5% rail, -1% resistor: both low must fit the added 1.5 mA budget.
    require(2 * 3.3 * 1.05 / (4700 * 0.99) < 0.0015, "I2C draw budget insufficient");
    const auto& connector = sheet(board, "som_j1");
    require(connector.parts.size() == 1 && connector.parts.front().ref == "J1",
            "SoM connector fanout must retain its single-connector core");
    for (const auto* net : {"SDIO_CLK", "SDIO_CMD"}) {
        for (const auto* name : {"som_j1", "debug_boot"}) {
            const auto pt = schgen::circuit_port_type(sheet(board, name), net);
            require(pt.kind == "sd_bus" && pt.bus == "SDIO"
                    && pt.has_level_v && pt.level_v == 1.8, "SDIO voltage/type changed");
        }
        // Probe branch must not add a bias resistor, translator or extra load.
        const auto& debug = sheet(board, "debug_boot");
        for (const auto& n : debug.nets) if (n.name == net) {
            require(n.pins.size() == 1 && n.pins.front().ref.rfind("TP", 0) == 0,
                    "SDIO probe branch gained non-probe loading");
        }
    }
}

void check_waivers(const Board& board) {
    std::map<std::string, std::string> actual;
    for (const auto& entry : board) for (const auto& waiver : entry.circuit.waivers) {
        require(waiver.kind != "pull_waivers", "devkit pull-up fix must not add pull waivers");
        if (waiver.kind == "tp_waivers") actual.emplace(entry.name + ":" + waiver.key, waiver.reason);
    }
    const std::map<std::string, std::string> original = {
        {"power_mon:+VIN_SYS", "reg-side of RS1 — probe across the shunt (the +VIN @ pd_input TP is the post-shunt/load side)"},
        {"power_mon:+5V_REG", "reg-side of RS2 — probe across the shunt (the +5V TP is the post-shunt/load side)"},
        {"power_mon:+3V3_REG", "reg-side of RS3 — probe across the shunt (the +3V3 TP is the post-shunt/load side)"},
        {"power_mon:+1V8_REG", "reg-side of RS4 — probe across the shunt (the +1V8 TP is the post-shunt/load side)"},
        {"pd_input:CHASSIS_GND", "chassis island is probeable at every connector shell tab (USB-C/HDMI/magjack); no pad needed"},
    };
    require(actual == original, "existing testpoint waivers changed or new waiver added");
}

template <typename F>
void rejects(F action, const std::string& context) {
    try { action(); }
    catch (const std::runtime_error&) { return; }
    throw std::runtime_error("regression escaped detection: " + context);
}

void remove_part(Board& board, const std::string& owner, const std::string& ref) {
    for (auto& entry : board) if (entry.name == owner) {
        auto& parts = entry.circuit.parts;
        const auto old_size = parts.size();
        parts.erase(std::remove_if(parts.begin(), parts.end(),
                    [&](const auto& part) { return part.ref == ref; }), parts.end());
        require(parts.size() + 1 == old_size, "mutation did not remove its target");
        for (auto& net : entry.circuit.nets) {
            auto& pins = net.pins;
            pins.erase(std::remove_if(pins.begin(), pins.end(),
                       [&](const auto& pin) { return pin.ref == ref; }), pins.end());
        }
    }
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: schgen_devkit_design_contracts <repository-root>");
        const auto board = schgen::load_project_circuits(
            schgen::resolve_project_paths(argv[1], "devkit_mini"));
        for (const auto* net : {"STM32_I2C2_SCL", "STM32_I2C2_SDA"}) {
            const auto owners = check_pullup(board, net);
            const auto ref = owners.front().substr(owners.front().find(':') + 1);
            auto missing = board;
            remove_part(missing, "debug_boot", ref);
            rejects([&] { check_pullup(missing, net); }, std::string(net) + " missing pull-up");
            auto wrong_value = board;
            for (auto& entry : wrong_value) if (entry.name == "debug_boot") {
                for (auto& part : entry.circuit.parts) if (part.ref == ref) part.value = "10k";
            }
            rejects([&] { check_pullup(wrong_value, net); }, std::string(net) + " wrong value");
            auto wrong_rail = board;
            for (auto& entry : wrong_rail) if (entry.name == "debug_boot") {
                for (auto& n : entry.circuit.nets) if (n.name == "+3V3_SC") n.name = "+3V3";
            }
            rejects([&] { check_pullup(wrong_rail, net); }, std::string(net) + " switched rail");
        }
        for (const auto& probe : probes) {
            check_probe(board, probe);
            auto missing = board;
            remove_part(missing, probe.owner, probe.ref);
            rejects([&] { check_probe(missing, probe); }, std::string(probe.net) + " missing pad");
        }
        check_interfaces(board);
        check_waivers(board);
        std::cout << "devkit design contracts passed: 2 pull-ups, 9 physical probes, "
                     "15 rejected mutations, interface/load/waiver contracts\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
