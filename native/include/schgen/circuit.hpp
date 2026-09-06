#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

struct CircuitPinRefIr {
    std::string ref;
    std::string pin;
};

struct CircuitFieldIr {
    std::string key;
    std::string value;
};

struct CircuitPinNameIr {
    std::string name;
    std::vector<std::string> numbers;
};

struct CircuitPartIr {
    std::string ref;
    std::string lib_id;
    std::string value;
    std::string footprint;
    std::vector<CircuitFieldIr> fields;
    std::vector<CircuitPinNameIr> pin_names;
    std::vector<std::string> pin_numbers;
};

struct CircuitNetIr {
    std::string name;
    std::string net_class;
    std::vector<CircuitPinRefIr> pins;
};

struct CircuitPortIr {
    std::string net;
    std::string kind;
    std::string pair_with;
    bool has_pair_with = false;
    int32_t impedance = 0;
    bool has_impedance = false;
    std::string role;
    bool has_role = false;
    std::string bus;
    bool has_bus = false;
    int32_t speed_hz = 0;
    bool has_speed_hz = false;
    double level_v = 0.0;
    bool has_level_v = false;
    std::string expect;
    bool has_expect = false;
};

struct CircuitHintIr {
    std::string net;
    std::string style;
};

struct CircuitLoadIr {
    std::string rail;
    double amps = 0.0;
    std::string note;
};

struct CircuitWaiverIr {
    std::string kind;
    std::string key;
    std::string reason;
};

struct CircuitSheetIr {
    std::string schema;
    std::string name;
    std::string title;
    std::vector<CircuitPartIr> parts;
    std::vector<CircuitNetIr> nets;
    std::vector<CircuitPinRefIr> nc;
    std::vector<CircuitPortIr> port_types;
    std::vector<CircuitHintIr> hints;
    std::vector<CircuitLoadIr> loads;
    std::vector<CircuitWaiverIr> waivers;
};

bool compile_circuit_catalog(const std::string& circuits_dir,
                             const std::string& catalog_path);
bool open_circuit_catalog(const std::string& catalog_path);
bool close_circuit_catalog();
CircuitSheetIr lookup_circuit_catalog(const std::string& name);
std::size_t circuit_catalog_count();

}  // namespace schgen
