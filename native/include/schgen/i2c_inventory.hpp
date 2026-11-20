#pragma once

#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

struct I2cBusError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct I2cBus {
    std::string name, space, data, clock;
};

struct I2cDevice {
    std::string sheet, ref, part, label, bus, space;
    int address = 0;
};

struct I2cBridgeLink {
    std::string sheet, ref, part, from, to;
    bool shared = false;
};

struct I2cPullup {
    std::string bus, line, sheet, ref, value, rail;
};

struct I2cInventory {
    std::vector<I2cBus> buses;
    std::vector<I2cDevice> devices;
    std::vector<I2cBridgeLink> bridges;
    std::vector<I2cPullup> pullups;
    std::string text() const;
};

I2cInventory build_i2c_inventory(const std::vector<ProjectCircuit>& sheets, const PartFacts& facts);
std::vector<std::string> i2c_address_collisions(const I2cInventory& inventory);
std::vector<std::string> verify_i2c_inventory(const I2cInventory& inventory, const std::vector<ProjectCircuit>& sheets,
                                              const PartFacts& facts);
void check_i2c_address_collisions(const std::vector<ProjectCircuit>& sheets);
std::string i2c_address_hex(int address);

}
