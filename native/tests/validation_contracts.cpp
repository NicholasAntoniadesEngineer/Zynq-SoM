// Standalone gates over real symbol libraries and canonical circuits. No
// Python, emitter, process-global catalogs, or repository output writes.
#include "schgen/validation.hpp"

#include <algorithm>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>

namespace {
namespace fs = std::filesystem;
using namespace schgen;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);  // Active under NDEBUG.
}

bool contains(const std::vector<std::string>& messages, const std::string& wanted) {
    return std::any_of(messages.begin(), messages.end(), [&](const auto& s) {
        return s.find(wanted) != std::string::npos;
    });
}

template <typename F>
void rejects(F action, const std::vector<std::string>& messages) {
    try { action(); }
    catch (const ValidationError& error) {
        for (const auto& wanted : messages) {
            require(std::string(error.what()).find(wanted) != std::string::npos,
                    "expected " + wanted + ", got: " + error.what());
        }
        return;
    }
    throw std::runtime_error("expected ValidationError");
}

struct Suite {
    std::size_t passed = 0, failed = 0;
    template <typename F>
    void run(const std::string& label, F action) {
        try { action(); ++passed; }
        catch (const std::exception& error) { ++failed; std::cerr << label << ": " << error.what() << '\n'; }
    }
};

CircuitPartIr part(const std::string& ref, const std::string& symbol) {
    CircuitPartIr p;
    p.ref = ref; p.lib_id = "Validation:" + symbol; p.value = symbol;
    return p;
}

CircuitSheetIr circuit(SymbolLibrary& library, const std::string& other = "Drivers",
                       const std::string& pin = "1") {
    CircuitSheetIr c;
    c.schema = "schgen.circuit/1"; c.name = "fixture"; c.title = "Validation fixture";
    c.parts = {part("U1", "Input"), part("U2", other)};
    c.nets = {{"DATA", "signal", {{"U1", "1"}, {"U2", pin}}}};
    for (const auto& number : library.pin_numbers("Validation:" + other)) {
        if (number != pin) c.nc.push_back({"U2", number});
    }
    return c;
}

void electrical_contracts(Suite& suite, const fs::path& fixtures) {
    SymbolLibrary library(std::vector<fs::path>{fixtures});
    const std::vector<std::string> driver_types = {
        "output", "bidirectional", "tri_state", "passive", "power_out", "open_collector", "open_emitter"};
    for (std::size_t i = 0; i < driver_types.size(); ++i) {
        suite.run("driver type " + driver_types[i], [&] {
            const auto c = circuit(library, "Drivers", std::to_string(i + 1));
            require(library.get("Validation:Drivers").pins[i].etype == driver_types[i], "fixture driver etype changed");
            const auto result = check_circuit_electrical(c, library);
            require(result.ok(), result.summary());
            require(result.coverage.size() == 2 && result.coverage[1].symbol_pins.size() == 7
                    && result.coverage[1].assigned_pins.size() == 1 && result.coverage[1].nc_pins.size() == 6,
                    "symbol-backed census incomplete");
            validate_circuit(c, library);
            require(check_inputs_driven(c, library).empty(), "valid driver rejected");
        });
    }
    const std::vector<std::string> nondrivers = {"input", "power_in", "unspecified", "free", "no_connect"};
    for (std::size_t i = 0; i < nondrivers.size(); ++i) {
        suite.run("non-driver type " + nondrivers[i], [&] {
            const auto c = circuit(library, "NonDrivers", std::to_string(i + 1));
            require(library.get("Validation:NonDrivers").pins[i].etype == nondrivers[i], "non-driver fixture changed");
            const auto result = check_circuit_electrical(c, library);
            require(!result.ok() && result.completeness_errors.empty(), "driver gate confused with completeness");
            require(result.input_driver_errors == std::vector<std::string>{
                "net 'DATA': input pin(s) with no same-sheet driver and not a PORT — undriven input"}, "undriven message changed");
            require(check_inputs_driven(c, library) == result.input_driver_errors, "driver APIs disagree");
            validate_circuit(c, library);  // Python's model validation is separate.
        });
    }
    for (const std::string net_class : {"power", "ground", "port"}) {
        suite.run("external net driver exemption " + net_class, [&] {
            auto c = circuit(library, "NonDrivers");
            c.nets[0].net_class = net_class;
            c.nc.push_back(c.nets[0].pins.back()); c.nets[0].pins.pop_back();
            require(check_circuit_electrical(c, library).ok(), "single public net rejected");
        });
    }
    suite.run("power input alone is not a signal input", [&] {
        auto c = circuit(library, "NonDrivers", "2");
        c.nets[0].pins.erase(c.nets[0].pins.begin());
        c.nets[0].pins.push_back({"U2", "3"});
        c.nc.erase(std::remove_if(c.nc.begin(), c.nc.end(), [](const auto& p) { return p.pin == "3"; }), c.nc.end());
        c.nc.push_back({"U1", "1"});
        require(check_circuit_electrical(c, library).ok(), "power_in mistaken for input");
    });
    suite.run("single-pin internal net", [&] {
        auto c = circuit(library);
        c.nc.push_back(c.nets[0].pins.back()); c.nets[0].pins.pop_back();
        const auto r = check_circuit_electrical(c, library);
        require(r.completeness_errors == std::vector<std::string>{"net 'DATA': single-pin internal signal net"}, r.summary());
        require(r.input_driver_errors.size() == 1, "isolated input passed driver gate");
        rejects([&] { validate_circuit(c, library); }, {"circuit 'fixture' incomplete:\n  net 'DATA'", "single-pin"});
    });
    suite.run("empty internal net retains Python check", [&] {
        auto c = circuit(library);
        for (const auto& pin : c.nets[0].pins) c.nc.push_back(pin);
        c.nets[0].pins.clear();
        require(check_circuit_completeness(c, library) == std::vector<std::string>{"net 'DATA': single-pin internal signal net"}, "empty internal net accepted");
    });
    suite.run("actual hidden and multi-unit pins exceed IR metadata", [&] {
        auto c = circuit(library, "Multi", "2");
        c.parts[1].pin_numbers = {"2"};  // Deliberately stale, not authoritative.
        c.nc.clear();
        const auto r = check_circuit_electrical(c, library);
        require(r.coverage[1].symbol_pins == std::vector<std::string>{"1", "10", "2", "3"}, "hidden/unit pins lost or duplicates counted");
        require(r.coverage[1].unassigned_pins == std::vector<std::string>{"1", "10", "3"}, "unassigned coverage changed");
        require(r.completeness_errors == std::vector<std::string>{
            "U2.1: UNASSIGNED (net it or declare nc())", "U2.10: UNASSIGNED (net it or declare nc())",
            "U2.3: UNASSIGNED (net it or declare nc())"}, r.summary());
        c.nc = {{"U2", "1"}, {"U2", "10"}, {"U2", "3"}};
        require(check_circuit_electrical(c, library).ok(), "explicit author NC not accepted");
    });
    suite.run("in-memory assignment removed is detected", [&] {
        auto c = circuit(library);
        c.nets[0].pins[1].pin = "99";
        c.parts[1].pin_numbers.push_back("99");
        const auto r = check_circuit_electrical(c, library);
        require(contains(r.completeness_errors, "U2.99: pin does not exist")
                && contains(r.completeness_errors, "U2.1: UNASSIGNED"), "IR metadata masked invalid symbol pin");
    });
    for (const std::string mode : {"unknown net owner", "unknown NC owner", "invalid NC pin", "NC plus net", "cross-net ownership"}) {
        suite.run(mode, [&] {
            auto c = circuit(library);
            std::string expected;
            if (mode == "unknown net owner") { c.nets[0].pins.push_back({"BAD", "1"}); expected = "unknown part 'BAD'"; }
            else if (mode == "unknown NC owner") { c.nc.push_back({"BAD", "1"}); expected = "unknown part 'BAD'"; }
            else if (mode == "invalid NC pin") { c.nc.push_back({"U2", "99"}); expected = "pin does not exist"; }
            else if (mode == "NC plus net") { c.nc.push_back({"U1", "1"}); expected = "cannot be NC"; }
            else { c.nets.push_back({"OTHER", "port", {{"U1", "1"}}}); expected = "already on net 'DATA'"; }
            require(contains(check_circuit_completeness(c, library), expected), "invalid edited IR accepted");
            rejects([&] { validate_circuit(c, library); }, {expected});
        });
    }
    suite.run("same-net stacked pins and repeated NC accepted", [&] {
        auto c = circuit(library);
        c.nets[0].pins.push_back(c.nets[0].pins.back()); c.nc.push_back(c.nc.front());
        require(check_circuit_electrical(c, library).ok(), "benign repeated physical pin rejected");
    });
    suite.run("duplicate pin etypes use Python final traversal entry", [&] {
        require(!check_inputs_driven(circuit(library, "LastInput"), library).empty(), "first etype incorrectly won");
        const auto c = circuit(library, "LastDriver");
        require(check_inputs_driven(c, library).empty(), "final output etype lost");
        require(check_circuit_electrical(c, library).coverage[1].symbol_pins.size() == 1, "duplicate unit pin counted twice");
    });
    for (const std::string symbol : {"Missing", "OffGrid", "EmptyPin"}) {
        suite.run("symbol errors fail closed " + symbol, [&] {
            auto c = circuit(library);
            c.parts[0].lib_id = "Validation:" + symbol;
            c.parts[0].pin_numbers = {"1"};
            rejects([&] { validate_circuit(c, library); }, {"fixture", "U1", "Validation:" + symbol});
            rejects([&] { check_inputs_driven(c, library); }, {"fixture", "U1", "Validation:" + symbol});
        });
    }
    suite.run("missing library cannot fall back to metadata", [&] {
        auto c = circuit(library); c.parts[0].lib_id = "MISSING:Input";
        c.parts[0].pin_numbers = {"1"};
        rejects([&] { check_circuit_electrical(c, library); }, {"U1", "MISSING:Input"});
    });
    suite.run("pinless mechanical symbols are legitimate", [&] {
        CircuitSheetIr c; c.name = "mechanical"; c.parts = {part("H1", "NoPins")};
        const auto r = check_circuit_electrical(c, library);
        require(r.ok() && r.coverage.size() == 1 && r.coverage[0].symbol_pins.empty(), "pinless symbol rejected");
    });
    suite.run("net diagnostics preserve source order and quote style", [&] {
        auto c = circuit(library, "NonDrivers");
        c.nets[0].name = "z's";
        c.nets.push_back({"alpha", "signal", {{"U2", "1"}, {"U1", "1"}}});
        require(check_inputs_driven(c, library) == std::vector<std::string>{
            "net \"z's\": input pin(s) with no same-sheet driver and not a PORT — undriven input",
            "net 'alpha': input pin(s) with no same-sheet driver and not a PORT — undriven input"}, "diagnostic order/quoting changed");
    });
}

const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    require(value != nullptr, "missing fixture field " + key);
    return *value;
}

void visual_contracts(Suite& suite, const fs::path& fixtures) {
    const auto cases = parse_json_file((fixtures / "visual_cases.json").string());
    require(cases.kind == JsonKind::Array && cases.array_value.size() == 27, "visual fixture coverage changed");
    for (const auto& test : cases.array_value) {
        const auto name = require_string(test, "name", false, "case");
        suite.run("visual " + name, [&] {
            SheetGeometry geo;
            for (const auto& row : field(test, "boxes").array_value) {
                const auto& v = row.array_value;
                require(v.size() == 6, "bad box fixture");
                geo.boxes.push_back({v[0].number_value, v[1].number_value, v[2].number_value, v[3].number_value,
                                     v[4].string_value, v[5].string_value});
            }
            for (const auto& row : field(test, "wires").array_value) {
                const auto& v = row.array_value;
                require(v.size() == 5, "bad wire fixture");
                geo.wires.push_back({v[0].number_value, v[1].number_value, v[2].number_value, v[3].number_value, v[4].string_value});
            }
            for (const auto& row : field(test, "junctions").array_value) {
                require(row.array_value.size() == 2, "bad junction fixture");
                geo.junctions.push_back({row.array_value[0].number_value, row.array_value[1].number_value});
            }
            std::vector<std::string> expected;
            for (const auto& finding : field(test, "findings").array_value) expected.push_back(finding.string_value);
            const auto* clearance = object_field(test, "clearance");
            const auto result = check_visual_geometry(geo, clearance ? clearance->number_value : default_engine_config.visual_clearance_mm);
            require(result.ok == expected.empty() && result.findings == expected, result.summary());
            std::string summary = expected.empty() ? "VISUAL GATE: PASS (0 overlaps, 0 crossings)" : "VISUAL GATE: FAIL";
            for (const auto& finding : expected) summary += "\n  " + finding;
            require(result.summary() == summary, "visual summary changed");
        });
    }
    for (const std::string kind : {"pin_name", "pin_number", "reference", "value", "label"}) {
        suite.run("wire over text kind " + kind, [&] {
            SheetGeometry geo;
            geo.boxes = {{4, -1, 6, 1, kind, "U1"}};
            geo.wires = {{0, 0, 10, 0, "A"}};
            require(check_visual_geometry(geo).findings == std::vector<std::string>{"wire(A) over " + kind + "(U1)"}, "text category escaped gate");
        });
    }
    suite.run("clearance and crossing epsilon boundaries", [&] {
        SheetGeometry geo;
        geo.wires = {{0, 5, 10, 5, "A"}, {1e-6, 0, 1e-6, 10, "A"}};
        require(check_visual_geometry(geo).ok, "crossing epsilon boundary changed");
        geo.wires[1].x0 = geo.wires[1].x1 = 2e-6;
        require(contains(check_visual_geometry(geo).findings, "CROSS"), "interior crossing outside epsilon missed");
        geo.wires = {{0, 0, 1, 0, "A"}, {1 - 0.5e-6, 0, 2, 0, "A"}};
        require(check_visual_geometry(geo).ok, "sub-epsilon overlap changed");
        geo.wires[1].x0 = 1 - 2e-6;
        require(contains(check_visual_geometry(geo).findings, "same-net wire-over-wire"), "overlap outside epsilon missed");
        const VisualBox a{0, 0, 1, 1, "value", "U1"}, b{1, 0, 2, 1, "value", "U2"};
        require(!a.intersects(b) && a.intersects(b, 0.2), "strict box intersection changed");
    });
    suite.run("same-owner non-text and foreign non-text semantics", [&] {
        SheetGeometry geo;
        geo.boxes = {{0, 0, 5, 5, "body", "U1"}, {1, 1, 2, 2, "decoration", "U1"}};
        require(check_visual_geometry(geo).ok, "same-owner exemption lost");
        geo.boxes[1].owner = "U2";
        require(!check_visual_geometry(geo).ok, "foreign ordinary box ignored");
    });
    suite.run("junction net ordering and Python quoting", [&] {
        SheetGeometry geo;
        geo.wires = {{0, 0, 5, 0, "z's"}, {5, 0, 5, 5, "A"}};
        geo.junctions = {{5, 0}};
        const auto result = check_visual_geometry(geo);
        require(result.findings.back() == "cross-net junction @(5.00,0.00): ['A', \"z's\"]", "junction names changed");
    });
    for (const double bad : {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()}) {
        suite.run("nonfinite visual inputs fail closed", [&] {
            SheetGeometry geo;
            geo.boxes = {{0, 0, bad, 1, "body", "U1"}};
            rejects([&] { check_visual_geometry(geo); }, {"boxes[0]", "finite"});
            geo.boxes.clear(); geo.wires = {{0, 0, bad, 0, "A"}};
            rejects([&] { check_visual_geometry(geo); }, {"wires[0]", "finite"});
            geo.wires.clear(); geo.junctions = {{bad, 0}};
            rejects([&] { check_visual_geometry(geo); }, {"junctions[0]", "finite"});
            rejects([&] { check_visual_geometry({}, bad); }, {"clearance"});
        });
    }
    suite.run("invalid geometry shapes rejected", [&] {
        SheetGeometry geo;
        geo.boxes = {{2, 0, 1, 1, "body", "U1"}};
        rejects([&] { check_visual_geometry(geo); }, {"inverted"});
        geo.boxes.clear(); geo.wires = {{0, 0, 5, 5, "A"}};
        rejects([&] { check_visual_geometry(geo); }, {"orthogonal"});
        geo.wires = {{0, 0, 0, 0, "A"}};
        rejects([&] { check_visual_geometry(geo); }, {"zero-length"});
        geo.wires = {{0, 0, 5, 0, ""}};
        rejects([&] { check_visual_geometry(geo); }, {"net must not be empty"});
        rejects([&] { check_visual_geometry({}, -0.1); }, {"clearance"});
    });
    suite.run("missing box metadata cannot claim own-owner exception", [&] {
        SheetGeometry geo;
        geo.boxes = {{0, 0, 1, 1, "body", ""}, {0, 0, 1, 1, "body", ""}};
        rejects([&] { check_visual_geometry(geo); }, {"boxes[0]", "kind and owner"});
        geo.boxes = {{0, 0, 1, 1, "", "U1"}};
        rejects([&] { check_visual_geometry(geo); }, {"kind and owner"});
    });
}

void repository_contracts(Suite& suite, const fs::path& repo) {
    SymbolLibrary library(repo);
    for (const std::string project : {"carrier", "devkit_mini"}) {
        suite.run("real electrical census " + project, [&] {
            const auto circuits = load_project_circuits(resolve_project_paths(repo, project));
            require(circuits.size() == (project == "carrier" ? 37u : 12u), "real circuit count changed");
            std::size_t parts = 0, pins = 0, assigned = 0, nc = 0;
            std::size_t source_parts = 0, source_assigned = 0, source_nc = 0;
            for (const auto& item : circuits) {
                const auto source = parse_json_file(item.path.string());
                source_parts += field(source, "parts").array_value.size();
                std::set<std::string> source_connections, source_no_connects;
                for (const auto& net : field(source, "nets").array_value) {
                    for (const auto& pin : field(net, "pins").array_value) source_connections.insert(pin.string_value);
                }
                for (const auto& pin : field(source, "nc").array_value) source_no_connects.insert(pin.string_value);
                source_assigned += source_connections.size(); source_nc += source_no_connects.size();
                const auto result = check_circuit_electrical(item.circuit, library);
                require(result.ok(), item.name + ": " + result.summary());
                require(result.coverage.size() == item.circuit.parts.size(), "part omitted from symbol-backed census");
                for (const auto& p : result.coverage) {
                    const auto authoritative = library.pin_numbers(p.lib_id);
                    require(std::set<std::string>(p.symbol_pins.begin(), p.symbol_pins.end()) == authoritative,
                            item.name + ": missing library pins on " + p.ref);
                    require(p.unassigned_pins.empty() && p.assigned_pins.size() + p.nc_pins.size() == authoritative.size(),
                            item.name + ": not every physical pin is assigned or explicit NC on " + p.ref);
                    for (const auto& pin : p.assigned_pins) require(source_connections.count(p.ref + "." + pin), "pin assignment not present in source JSON");
                    for (const auto& pin : p.nc_pins) require(source_no_connects.count(p.ref + "." + pin), "NC invented without source declaration");
                    ++parts; pins += authoritative.size(); assigned += p.assigned_pins.size(); nc += p.nc_pins.size();
                }
            }
            require(parts == source_parts && assigned == source_assigned && nc == source_nc,
                    "electrical census lost or invented source parts/connections/NCs");
            require(pins == assigned + nc && pins > parts, "symbol-pin census is incomplete");
            std::cout << project << ": " << circuits.size() << " circuits, " << parts << " parts, " << pins
                      << " symbol pins = " << assigned << " assigned + " << nc << " explicit NC; inputs driven\n";
        });
        suite.run("real inline-symbol missing pin cannot pass " + project, [&] {
            auto c = load_project_circuit(resolve_project_paths(repo, project), "power").circuit;
            std::optional<CircuitPinRefIr> victim;
            for (const auto& part : c.parts) {
                if (!part.pin_numbers.empty()) continue;
                for (const auto& net : c.nets) {
                    for (const auto& pin : net.pins) if (pin.ref == part.ref) { victim = pin; break; }
                    if (victim) break;
                }
                if (victim) break;
            }
            require(victim.has_value(), "real inline-symbol coverage case disappeared");
            for (auto& net : c.nets) {
                net.pins.erase(std::remove_if(net.pins.begin(), net.pins.end(), [&](const auto& pin) {
                    return pin.ref == victim->ref && pin.pin == victim->pin;
                }), net.pins.end());
            }
            const auto errors = check_circuit_completeness(c, library);
            require(contains(errors, victim->ref + "." + victim->pin + ": UNASSIGNED"), "missing actual pin passed metadata-only gate");
            rejects([&] { validate_circuit(c, library); }, {": UNASSIGNED"});
        });
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2 || (argc == 3 && std::string(argv[2]) == "--electrical"),
                "usage: schgen_validation_contracts REPOSITORY_ROOT [--electrical]");
        const fs::path repo = fs::absolute(argv[1]);
        const auto fixtures = repo / "native/tests/data/validation";
        Suite suite;
        electrical_contracts(suite, fixtures);
        repository_contracts(suite, repo);
        if (argc == 2) visual_contracts(suite, fixtures);
        std::cout << "validation contracts: " << suite.passed << " passed, " << suite.failed << " failed\n";
        return suite.failed ? 1 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
