#include "schgen/subsystem_data.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {

using namespace schgen;

std::size_t checks = 0;

void require(bool condition, const std::string& detail) {
    ++checks;
    if (!condition) throw std::runtime_error(detail);
}

template <class Call> void rejects(Call call, const std::string& needle) {
    bool thrown = false;
    try {
        call();
    } catch (const std::runtime_error& error) {
        thrown = std::string(error.what()).find(needle) != std::string::npos;
        if (!thrown) throw std::runtime_error("expected '" + needle + "', got: " + error.what());
    }
    require(thrown, "accepted: expected '" + needle + "'");
}

std::string replaced(std::string text, const std::string& before, const std::string& after) {
    const auto at = text.find(before);
    if (at == std::string::npos) throw std::runtime_error("fixture lacks " + before);
    return text.replace(at, before.size(), after);
}

const char* const widget = R"json({
  "schema": "schgen.subsystem/1",
  "name": "widget",
  "title": "Widget sensor",
  "interface": ["+VDD", "GND", "SCL", "SDA"],
  "parts": [
    {"ref": "R1", "symbol": "Device:R", "value": "4k7", "footprint": "Resistor_SMD:R_0603_1608Metric", "fields": {"LCSC": "C23162"}},
    {"ref": "R2", "symbol": "Device:R", "value": "4k7", "footprint": "Resistor_SMD:R_0603_1608Metric", "fields": {"LCSC": "C23162"}}
  ],
  "nets": [
    {"name": "+VDD", "pins": ["R1.1", "R2.1"]},
    {"name": "SCL", "class": "port", "pins": ["R1.2"]},
    {"name": "SDA", "class": "port", "pins": ["R2.2"]},
    {"name": "GND", "pins": []}
  ],
  "unconnected": [],
  "ports": [
    {"net": "SCL", "kind": "i2c", "role": "scl", "bus": {"instance": "i2c", "default": "WIDGET_I2C"}, "expect": {"instance": "non_empty"}},
    {"net": "SDA", "kind": "i2c", "role": "sda", "bus": {"instance": "i2c", "default": "WIDGET_I2C"}, "expect": {"instance": "as_given", "default": "controller"}}
  ],
  "hints": [],
  "draws": [{"rail": "+VDD", "amps": 0.002, "note": {"instance": "draws", "default": "two pull-ups"}}],
  "waivers": [],
  "purpose": [{"part": "R1", "role": "pull", "net": "SCL"}, {"part": "R2", "role": "pull", "net": "SDA"}],
  "free": []
})json";

JsonNode settings(const std::string& text) { return parse_json_text(text); }

const CircuitPortIr& port(const CircuitSheetIr& sheet, const std::string& net) {
    for (const auto& item : sheet.port_types)
        if (item.net == net) return item;
    throw std::runtime_error("no port " + net);
}

void loads_and_resolves() {
    const JsonNode document = parse_json_text(widget);
    const CircuitSheetIr plain = author_subsystem_data(document, SubsystemMeta{}, {});
    require(plain.name == "widget" && plain.parts.size() == 2 && plain.nets.size() == 4, "the file's parts and nets are built");
    require(port(plain, "SCL").bus == "WIDGET_I2C" && !port(plain, "SCL").has_expect, "defaults apply with no board settings");
    require(port(plain, "SDA").expect == "controller" && plain.loads.front().note == "two pull-ups", "stated defaults are used");
    require(plain.layout.serves.size() == 2 && plain.layout.serves.front().net == "SCL", "each part's purpose is carried");
    const SubsystemMeta board(settings(R"({"buses": {"i2c": "SENSORS"}, "expects": {"SCL": "module", "SDA": ""},
                                           "notes": {"draws": "measured"}, "bind": {"+VDD": "+3V3"}})"));
    const CircuitSheetIr bound = author_subsystem_data(document, board, {});
    require(port(bound, "SCL").bus == "SENSORS" && port(bound, "SCL").expect == "module", "board settings replace the defaults");
    require(port(bound, "SDA").has_expect && port(bound, "SDA").expect.empty(), "an expectation taken as given keeps an empty value");
    require(bound.loads.front().note == "measured" && bound.loads.front().rail == "+3V3", "notes and net bindings follow the board");
}

void refuses_bad_files() {
    const auto load = [](const std::string& text) { return author_subsystem_data(parse_json_text(text), SubsystemMeta{}, {}); };
    rejects([&] { load(replaced(widget, "\"hints\": []", "\"hints\": [], \"extra\": 1")); }, "extra");
    rejects([&] { load(replaced(widget, "schgen.subsystem/1", "schgen.subsystem/0")); }, "schema is not");
    rejects([&] { load(replaced(widget, "\"role\": \"pull\", \"net\": \"SCL\"", "\"role\": \"pull\", \"net\": \"SCL\", \"pin\": \"R1.2\"")); },
            "exactly one of");
    rejects([&] { load(replaced(widget, "\"instance\": \"non_empty\"", "\"instance\": \"sometimes\"")); }, "unknown per-board mode");
    rejects([&] { load(replaced(widget, "\"pins\": [\"R1.2\"]", "\"pins\": [\"R9.2\"]")); }, "unknown part");
    rejects([&] { load(replaced(widget, "\"amps\": 0.002", "\"amps\": 0")); }, "amps must be > 0");
}

void finds_files_at_run_time() {
    const std::filesystem::path library =
        std::filesystem::temp_directory_path() / ("schgen_subsystem_data_" + std::to_string(getpid()));
    std::filesystem::remove_all(library);
    std::filesystem::create_directories(library / "widget");
    std::filesystem::create_directories(library / "notes_only");
    std::ofstream(library / "widget" / subsystem_data_file) << widget;
    AuthoringContext context;
    context.library = library;
    const auto found = subsystem_library(context);
    require(found.size() == 1 && found.front().name == "widget" && found.front().interface.size() == 4,
            "a subsystem is found by its file alone");
    require(author_subsystem("widget", SubsystemMeta{}, context).parts.size() == 2, "a found subsystem builds by name");
    rejects([&] { author_subsystem("absent", SubsystemMeta{}, context); }, "unknown subsystem");
    rejects([] { author_subsystem("widget", SubsystemMeta{}, {}); }, "unknown subsystem");
    std::filesystem::create_directories(library / "gadget");
    std::ofstream(library / "gadget" / subsystem_data_file) << widget;
    rejects([&] { subsystem_library(context); }, "differs from its folder");
    rejects([&] { author_subsystem("gadget", SubsystemMeta{}, context); }, "differs from its folder");
    std::filesystem::remove_all(library);
}

}

int main() {
    try {
        loads_and_resolves();
        refuses_bad_files();
        finds_files_at_run_time();
        std::cout << "subsystem data contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "subsystem data contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
