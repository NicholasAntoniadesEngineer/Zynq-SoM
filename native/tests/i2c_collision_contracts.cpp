#include "board_pipeline_internal.hpp"
#include "schgen/i2c_inventory.hpp"
#include "schgen/manufacturing_exports.hpp"
#include "schgen/power_checks.hpp"
#include "schgen/project.hpp"
#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace {
using namespace schgen;
using namespace schgen::board_pipeline_detail;
const int expected_arguments = 2;
const char* const collision_text = "I2C address collision";
const char* const unlisted_text = "which is the net of none of";
const char* const expander_sheet = "bringup_rails";
const char* const services_sheet = "board_services";
const char* const monitor_sheet = "power_mon";
const char* const motor_sheet = "motor_sense";
const char* const edid_sheet = "hdmi_rx";
const char* const expander_strap = "A1";
const char* const expander_supply = "+3V3_SC";
const char* const eeprom_part_id = "24AA025E48";
const char* const eeprom_low_pin = "5";
const char* const eeprom_high_pin = "4";
const char* const eeprom_ground = "GND";
const char* const eeprom_supply = "+3V3_AUX";
const char* const monitor_part_id = "INA3221";
const char* const monitor_strap = "A0";
const char* const monitor_ground = "GND";
const char* const edid_part = "M24C02";
const char* const edid_low_pin = "1";
const char* const edid_supply_pin = "8";
const int edid_raised_address = 0x51;
const int third_monitor_address = 0x42;
std::size_t assertions = 0;
void require(bool ok, const std::string& why) { ++assertions; if (!ok) throw std::runtime_error(why); }
struct Temp {
    fs::path path;
    Temp() { auto s = (fs::temp_directory_path() / "schgen_i2c_collision_XXXXXX").string(); if (!::mkdtemp(s.data())) throw std::runtime_error("temporary folder"); path = s; }
    ~Temp() { std::error_code e; fs::remove_all(path, e); }
};
CircuitSheetIr& sheet(std::vector<ProjectCircuit>& sheets, const std::string& name) {
    for (auto& sc : sheets) if (sc.name == name) return sc.circuit;
    throw std::runtime_error("board has no sheet " + name);
}
std::string pin_number(const CircuitPartIr& p, const std::string& name) {
    for (const auto& pn : p.pin_names) if (pn.name == name) return pn.numbers.at(0);
    throw std::runtime_error("part " + p.ref + " has no pin " + name);
}
const CircuitPartIr& part_with_id(const CircuitSheetIr& c, const std::string& id) {
    for (const auto& p : c.parts) if (p.lib_id.find(id) != std::string::npos || p.value.find(id) != std::string::npos) return p;
    throw std::runtime_error("sheet " + c.name + " has no part " + id);
}
std::string net_of(const CircuitSheetIr& c, const std::string& ref, const std::string& pin) {
    for (const auto& n : c.nets) for (const auto& p : n.pins) if (p.ref == ref && p.pin == pin) return n.name;
    throw std::runtime_error("pin " + ref + "." + pin + " of sheet " + c.name + " is on no net");
}
void rewire(CircuitSheetIr& c, const std::string& ref, const std::string& pin, const std::string& net) {
    for (auto& n : c.nets) n.pins.erase(std::remove_if(n.pins.begin(), n.pins.end(), [&](const auto& p) { return p.ref == ref && p.pin == pin; }), n.pins.end());
    for (auto& n : c.nets) if (n.name == net) { n.pins.push_back({ref, pin}); return; }
    throw std::runtime_error("sheet " + c.name + " has no net " + net);
}
void rejected(const std::vector<ProjectCircuit>& sheets, const std::vector<std::string>& fragments) {
    bool caught = false;
    try { check_i2c_address_collisions(sheets); }
    catch (const I2cBusError& e) {
        caught = true;
        const std::string what = e.what();
        require(what.find(collision_text) != std::string::npos, "unexpected failure: " + what);
        for (const auto& fragment : fragments) require(what.find(fragment) != std::string::npos, "collision message lost " + fragment + ": " + what);
    }
    require(caught, "a collision was accepted");
}
void failed_step(const fs::path& root, const std::vector<ProjectCircuit>& sheets) {
    Temp tmp;
    const auto paths = resolve_project_paths(root, "carrier");
    BoardPipelineOptions o; o.output_root = tmp.path / "out"; o.no_render = true;
    Context c(paths, o);
    c.circuits = sheets;
    c.power = PowerCheckResult{};
    c.testpoints = TestpointCoverage{};
    manifest_stage(c);
    require(c.result.gates.size() == 1 && c.result.gates.front().name == "manifest", "the manifest step left exactly one verdict");
    const auto& gate = c.result.gates.front();
    require(gate.status == BoardGateStatus::failed && gate.mandatory, "a collision fails the mandatory manifest gate");
    require(gate.report.find(collision_text) != std::string::npos, "gate report names the collision: " + gate.report);
    require(!fs::exists(c.out / "manifest.json"), "no manifest is published after a collision");
}
const I2cDevice& device(const I2cInventory& inventory, const std::string& sheet_name, const std::string& ref) {
    for (const auto& d : inventory.devices) if (d.sheet == sheet_name && d.ref == ref) return d;
    throw std::runtime_error("inventory has no device " + sheet_name + ":" + ref);
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: i2c_collision_contracts REPOSITORY");
        const auto root = fs::absolute(argv[1]);
        for (const std::string board : {"carrier", "devkit_mini"}) {
            check_i2c_address_collisions(load_project_circuits(resolve_project_paths(root, board)));
            std::cout << board << ": no I2C address collision\n";
        }
        const auto carrier = load_project_circuits(resolve_project_paths(root, "carrier"));

        auto expander = carrier;
        auto& rails = sheet(expander, expander_sheet);
        const auto& tca = part_with_id(rails, "TCA9535");
        rewire(rails, tca.ref, pin_number(tca, expander_strap), expander_supply);
        rejected(expander, {std::string(expander_sheet) + ":" + tca.ref + "=0x22", "usb_pd:U1=0x22"});
        failed_step(root, expander);

        auto eeprom = carrier;
        auto& services = sheet(eeprom, services_sheet);
        const auto& memory = part_with_id(services, eeprom_part_id);
        rewire(services, memory.ref, eeprom_low_pin, eeprom_ground);
        rewire(services, memory.ref, eeprom_high_pin, eeprom_supply);
        rejected(eeprom, {std::string(services_sheet) + ":" + memory.ref + "=0x52", std::string(services_sheet) + ":U2=0x52"});
        failed_step(root, eeprom);

        auto motor = carrier;
        auto& sense = sheet(motor, motor_sheet);
        const auto& third = part_with_id(sense, monitor_part_id);
        require(device(build_i2c_inventory(carrier, default_part_facts()), motor_sheet, third.ref).address == third_monitor_address,
                "the third current monitor is seen at 0x42");
        rewire(sense, third.ref, pin_number(third, monitor_strap), monitor_ground);
        const auto& first = part_with_id(sheet(motor, monitor_sheet), monitor_part_id);
        rejected(motor, {std::string(motor_sheet) + ":" + third.ref + "=0x40", std::string(monitor_sheet) + ":" + first.ref + "=0x40"});
        failed_step(root, motor);

        auto separate = carrier;
        auto& edid = sheet(separate, edid_sheet);
        const auto& rom = part_with_id(edid, edid_part);
        rewire(edid, rom.ref, edid_low_pin, net_of(edid, rom.ref, edid_supply_pin));
        const auto split = build_i2c_inventory(separate, default_part_facts());
        const auto& raised = device(split, edid_sheet, rom.ref);
        const auto& identity = device(split, services_sheet, part_with_id(sheet(separate, services_sheet), eeprom_part_id).ref);
        require(raised.address == edid_raised_address && identity.address == edid_raised_address, "two devices share an address");
        require(raised.space != identity.space, "the two devices sit on electrically separate buses");
        check_i2c_address_collisions(separate);
        require(i2c_address_collisions(split).empty(), "same address on separate buses is not a collision");

        auto unlisted = carrier;
        auto& loose = sheet(unlisted, motor_sheet);
        const auto& strapped = part_with_id(loose, monitor_part_id);
        std::set<std::string> targets;
        for (const std::string name : {"GND", "VS", "SDA", "SCL"}) targets.insert(net_of(loose, strapped.ref, pin_number(strapped, name)));
        const auto other = std::find_if(loose.nets.begin(), loose.nets.end(), [&](const auto& n) { return !targets.count(n.name); });
        require(other != loose.nets.end(), "the sheet has a net no strap value names");
        rewire(loose, strapped.ref, pin_number(strapped, monitor_strap), other->name);
        bool refused = false;
        try { (void)build_i2c_inventory(unlisted, default_part_facts()); }
        catch (const I2cBusError& e) {
            refused = std::string(e.what()).find(unlisted_text) != std::string::npos &&
                      std::string(e.what()).find(std::string(motor_sheet) + ":" + strapped.ref) != std::string::npos;
            require(refused, std::string("unexpected failure: ") + e.what());
        }
        require(refused, "a strap tied to an unlisted net was accepted");

        std::cout << assertions << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
