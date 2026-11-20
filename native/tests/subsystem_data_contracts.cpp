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
  "placement": {"region": "board", "silk_label": null, "far_guard_mm": null, "escape_basis": null, "escape_escalates": false, "reserves_edge": false},
  "checks": {"dividers": [], "divider_sources": [], "iset_window_ma": null},
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

const std::string quiet_placement =
    R"("placement": {"region": "board", "silk_label": null, "far_guard_mm": null, "escape_basis": null, "escape_escalates": false, "reserves_edge": false})";
const std::string quiet_checks = R"("checks": {"dividers": [], "divider_sources": [], "iset_window_ma": null})";

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

void reads_facts() {
    const SubsystemFacts quiet = subsystem_data_facts(parse_json_text(widget), "widget");
    require(quiet.placement.region == SheetRegion::board && !quiet.placement.silk_label && !quiet.placement.far_guard_mm &&
                !quiet.placement.escape_basis && !quiet.placement.escape_escalates && !quiet.placement.reserves_edge,
            "null and false state that a subsystem has no such fact");
    require(quiet.checks.dividers.empty() && quiet.checks.divider_sources.empty() && !quiet.checks.iset_window_ma, "empty checks are read");
    const std::string filled_placement =
        R"("placement": {"region": "under_module", "silk_label": "ETH", "far_guard_mm": 14.5, "escape_basis": "stays in the region", "escape_escalates": true, "reserves_edge": true})";
    const std::string filled_checks =
        R"("checks": {"dividers": [{"net": "SET", "source": "+VDD", "limits": [{"volts": 21.0, "hi": 1.2, "tag": "no trip"}, {"volts": 24.0, "lo": 1.1, "tag": "cutoff"}], "why": "set divider"}], "divider_sources": ["SENSE"], "iset_window_ma": [125, 150]})";
    const SubsystemFacts filled = subsystem_data_facts(parse_json_text(replaced(replaced(widget, quiet_placement, filled_placement), quiet_checks, filled_checks)), "widget");
    require(filled.placement.region == SheetRegion::under_module && filled.placement.silk_label == "ETH" && filled.placement.far_guard_mm == 14.5 &&
                filled.placement.escape_basis == "stays in the region" && filled.placement.escape_escalates && filled.placement.reserves_edge,
            "placement facts are read");
    require(filled.checks.dividers.size() == 1 && filled.checks.dividers.front().net == "SET" && filled.checks.dividers.front().source == "+VDD" &&
                filled.checks.dividers.front().why == "set divider" && filled.checks.dividers.front().limits.size() == 2 &&
                filled.checks.dividers.front().limits.front().hi == 1.2 && !filled.checks.dividers.front().limits.front().lo &&
                filled.checks.dividers.front().limits.back().lo == 1.1 && filled.checks.dividers.front().limits.back().tag == "cutoff",
            "divider checks are read");
    require(filled.checks.divider_sources.size() == 1 && filled.checks.divider_sources.front() == "SENSE" && filled.checks.iset_window_ma &&
                filled.checks.iset_window_ma->low_ma == 125 && filled.checks.iset_window_ma->high_ma == 150,
            "divider sources and the ISET window are read");
}

void refuses_bad_facts() {
    const auto load = [](const std::string& text) { return author_subsystem_data(parse_json_text(text), SubsystemMeta{}, {}); };
    const auto with_placement = [&](const std::string& placement) { return replaced(widget, quiet_placement, placement); };
    const auto with_checks = [&](const std::string& checks) { return replaced(widget, quiet_checks, checks); };
    const auto without = [&](const std::string& line) { return replaced(widget, "  " + line + ",\n", ""); };
    rejects([&] { load(without(quiet_placement)); }, "field 'placement' is missing or has the wrong type");
    rejects([&] { load(without(quiet_checks)); }, "field 'checks' is missing or has the wrong type");
    rejects([&] { load(with_placement(R"("placement": [])")); }, "field 'placement' is missing or has the wrong type");
    rejects([&] { load(with_checks(R"("checks": null)")); }, "field 'checks' is missing or has the wrong type");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"reserves_edge\": false", "\"reserves_edge\": false, \"extra\": 1"))); },
            "unknown key 'extra' in widget placement");
    rejects([&] { load(with_checks(replaced(quiet_checks, "\"iset_window_ma\": null", "\"iset_window_ma\": null, \"extra\": 1"))); },
            "unknown key 'extra' in widget checks");
    for (const std::string key : {"region", "silk_label", "far_guard_mm", "escape_basis", "escape_escalates", "reserves_edge"}) {
        const auto at = quiet_placement.find("\"" + key + "\"");
        const auto end = quiet_placement.find(',', at);
        const std::string cut = end == std::string::npos ? quiet_placement.substr(0, at - 2) + "}" : quiet_placement.substr(0, at) + quiet_placement.substr(end + 2);
        rejects([&] { load(with_placement(cut)); }, "field '" + key + "' is missing");
    }
    for (const std::string key : {"dividers", "divider_sources", "iset_window_ma"}) {
        const auto at = quiet_checks.find("\"" + key + "\"");
        const auto end = quiet_checks.find("], ", at);
        const std::string cut = key == "iset_window_ma" ? quiet_checks.substr(0, at - 2) + "}" : quiet_checks.substr(0, at) + quiet_checks.substr(end + 3);
        rejects([&] { load(with_checks(cut)); }, "field '" + key + "' is missing");
    }
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"board\"", "\"above\""))); }, "field 'region' is 'above', not board or under_module");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"board\"", "\"\""))); }, "field 'region' is empty");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"board\"", "1"))); }, "field 'region' is missing or has the wrong type");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"silk_label\": null", "\"silk_label\": \"\""))); }, "field 'silk_label' is neither null nor a name");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"silk_label\": null", "\"silk_label\": 1"))); }, "field 'silk_label' is neither null nor a name");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"far_guard_mm\": null", "\"far_guard_mm\": 0"))); },
            "field 'far_guard_mm' is neither null nor a number above zero");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"far_guard_mm\": null", "\"far_guard_mm\": \"14\""))); },
            "field 'far_guard_mm' is neither null nor a number above zero");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"escape_basis\": null", "\"escape_basis\": \"\""))); },
            "field 'escape_basis' is neither null nor a name");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"escape_escalates\": false", "\"escape_escalates\": null"))); },
            "field 'escape_escalates' is missing or has the wrong type");
    rejects([&] { load(with_placement(replaced(quiet_placement, "\"reserves_edge\": false", "\"reserves_edge\": 0"))); },
            "field 'reserves_edge' is missing or has the wrong type");
    const std::string good_divider =
        R"({"net": "SET", "source": "+VDD", "limits": [{"volts": 21.0, "hi": 1.2, "tag": "no trip"}], "why": "set divider"})";
    const auto with_divider = [&](const std::string& divider) {
        return with_checks("\"checks\": {\"dividers\": [" + divider + "], \"divider_sources\": [], \"iset_window_ma\": null}");
    };
    load(with_divider(good_divider));
    rejects([&] { load(with_checks(replaced(quiet_checks, "\"dividers\": []", "\"dividers\": {}"))); }, "field 'dividers' is missing or has the wrong type");
    rejects([&] { load(with_checks(replaced(quiet_checks, "\"dividers\": []", "\"dividers\": [1]"))); }, "'dividers' holds a value that is not an object");
    rejects([&] { load(with_divider(replaced(good_divider, "\"why\": \"set divider\"", "\"why\": \"set divider\", \"extra\": 1"))); },
            "unknown key 'extra' in widget checks divider");
    for (const std::string key : {"net", "source", "why"}) {
        rejects([&] { load(with_divider(replaced(good_divider, "\"" + key + "\": ", "\"" + key + "_\": "))); }, "unknown key '" + key + "_'");
        rejects([&] { load(with_divider(replaced(good_divider, key == "why" ? "\"set divider\"" : key == "net" ? "\"SET\"" : "\"+VDD\"", "\"\""))); },
                "field '" + key + "' is empty");
    }
    rejects([&] { load(with_divider(replaced(good_divider, "[{\"volts\": 21.0, \"hi\": 1.2, \"tag\": \"no trip\"}]", "[]"))); }, "divider SET states no limits");
    rejects([&] { load(with_divider(replaced(good_divider, "\"tag\": \"no trip\"", "\"tag\": \"no trip\", \"extra\": 1"))); },
            "unknown key 'extra' in widget checks divider limit");
    rejects([&] { load(with_divider(replaced(good_divider, "\"volts\": 21.0, ", ""))); }, "field 'volts' is missing or has the wrong type");
    rejects([&] { load(with_divider(replaced(good_divider, "\"hi\": 1.2, ", ""))); }, "a limit of divider SET states neither lo nor hi");
    rejects([&] { load(with_divider(replaced(good_divider, "\"hi\": 1.2", "\"hi\": \"1.2\""))); }, "field 'hi' is not a number");
    rejects([&] { load(with_divider(replaced(good_divider, "\"hi\": 1.2", "\"hi\": 1.2, \"lo\": 1.2"))); }, "a limit of divider SET has lo not below hi");
    rejects([&] { load(with_divider(replaced(good_divider, "\"tag\": \"no trip\"", "\"tag\": \"\""))); }, "field 'tag' is empty");
    rejects([&] { load(with_checks(replaced(quiet_checks, "\"divider_sources\": []", "\"divider_sources\": [\"\"]"))); }, "'divider_sources' holds a value that is not a name");
    rejects([&] { load(with_checks(replaced(quiet_checks, "\"divider_sources\": []", "\"divider_sources\": \"X\""))); },
            "field 'divider_sources' is missing or has the wrong type");
    for (const std::string window : {"[]", "[125]", "[125, 150, 175]", "[\"a\", 150]", "125", "[150, 125]", "[125, 125]", "[0, 150]", "[-1, 150]"})
        rejects([&] { load(with_checks(replaced(quiet_checks, "\"iset_window_ma\": null", "\"iset_window_ma\": " + window))); }, "field 'iset_window_ma' is ");
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
    require(load_subsystem_facts(library, "widget").placement.region == SheetRegion::board, "facts are read from a library file by name");
    rejects([&] { load_subsystem_facts(library, "absent"); }, "unknown subsystem absent");
    rejects([&] { load_subsystem_facts({}, "widget"); }, "unknown subsystem widget");
    rejects([&] { author_subsystem("absent", SubsystemMeta{}, context); }, "unknown subsystem");
    rejects([] { author_subsystem("widget", SubsystemMeta{}, {}); }, "unknown subsystem");
    std::filesystem::create_directories(library / "gadget");
    std::ofstream(library / "gadget" / subsystem_data_file) << widget;
    rejects([&] { load_subsystem_facts(library, "gadget"); }, "its name differs from its folder gadget");
    rejects([&] { subsystem_library(context); }, "differs from its folder");
    rejects([&] { author_subsystem("gadget", SubsystemMeta{}, context); }, "differs from its folder");
    std::filesystem::create_directories(library / "bare");
    std::ofstream(library / "bare" / subsystem_data_file) << replaced(replaced(widget, "widget", "bare"), quiet_checks + ",\n", "");
    rejects([&] { load_subsystem_facts(library, "bare"); }, "field 'checks' is missing or has the wrong type");
    rejects([&] { subsystem_library(context); }, "field 'checks' is missing or has the wrong type");
    std::filesystem::remove_all(library);
}

}

int main() {
    try {
        loads_and_resolves();
        refuses_bad_files();
        reads_facts();
        refuses_bad_facts();
        finds_files_at_run_time();
        std::cout << "subsystem data contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "subsystem data contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
