#include "schgen/i2c_inventory.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace {
using namespace schgen;
const int expected_arguments = 2;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}
bool rejected(const I2cInventory& inventory, const std::vector<ProjectCircuit>& sheets, const PartFacts& facts) {
    return !verify_i2c_inventory(inventory, sheets, facts).empty();
}
const I2cBus& bus(const I2cInventory& inventory, const std::string& name) {
    for (const auto& b : inventory.buses) if (b.name == name) return b;
    throw std::runtime_error("bus map has no bus " + name);
}
I2cInventory board(const std::filesystem::path& root, const std::string& project, const PartFacts& facts) {
    const auto sheets = load_project_circuits(resolve_project_paths(root, project));
    const auto inventory = build_i2c_inventory(sheets, facts);
    const auto errors = verify_i2c_inventory(inventory, sheets, facts);
    require(errors.empty(), project + " bus map is complete: " + (errors.empty() ? std::string() : errors.front()));
    require(i2c_address_collisions(inventory).empty(), project + " has no address collision");
    std::size_t instances = 0;
    for (const auto& sheet : sheets)
        for (const auto& part : sheet.circuit.parts) instances += part_fact_for(facts.i2c_devices, part.value, part.footprint) != nullptr;
    require(instances > 0 && inventory.devices.size() == instances, project + " one row per I2C device instance");
    std::set<std::string> keys;
    for (const auto& d : inventory.devices) require(keys.insert(d.sheet + ":" + d.ref).second, project + " device appears once: " + d.ref);
    for (const auto& p : inventory.pullups) require(!p.rail.empty() && !p.value.empty(), project + " pull-up carries value and rail");
    require(inventory.text() == build_i2c_inventory(sheets, facts).text(), project + " report is reproducible");

    auto dropped = inventory;
    dropped.devices.erase(dropped.devices.begin());
    require(rejected(dropped, sheets, facts), project + " mutation: dropped device");
    auto doubled = inventory;
    doubled.devices.push_back(doubled.devices.front());
    require(rejected(doubled, sheets, facts), project + " mutation: duplicated device");
    auto foreign = inventory;
    foreign.devices.front().ref += "X";
    require(rejected(foreign, sheets, facts), project + " mutation: device that is not in the circuits");
    auto moved = inventory;
    moved.devices.front().bus += "_X";
    require(rejected(moved, sheets, facts), project + " mutation: device on a bus the map does not list");
    auto collided = inventory;
    collided.devices.push_back(collided.devices.front());
    collided.devices.back().ref += "X";
    require(!i2c_address_collisions(collided).empty(), project + " mutation: same address, same space collides");
    return inventory;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: i2c_bus_map_contracts REPOSITORY");
        const std::filesystem::path root = std::filesystem::absolute(argv[1]);
        const PartFacts facts = load_part_facts(root / "parts" / "part_facts.json");
        const auto carrier = board(root, "carrier", facts);
        const auto devkit = board(root, "devkit_mini", facts);
        require(bus(carrier, "STM32_I2C2").space == bus(carrier, "AUX_I2C").space, "the level translator joins one address space");
        for (const std::string other : {"CAM_I2C", "HDMI_TX_DDC", "LCD_CTP"})
            require(bus(carrier, other).space != bus(carrier, "STM32_I2C2").space, other + " is a separate address space");
        require(std::any_of(carrier.devices.begin(), carrier.devices.end(), [](const I2cDevice& d) { return d.sheet == "motor_sense"; }),
                "the motor current monitor is in the carrier bus map");
        require(devkit.buses.size() == 1, "devkit_mini has one bus");
        std::cout << "i2c bus map: " << checks << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
