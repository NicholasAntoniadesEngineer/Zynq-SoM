#include "schgen/schematic.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace schgen;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
template<class F> void rejects(F action, const std::string& fragment) {
    try { action(); }
    catch (const std::exception& error) {
        require(std::string(error.what()).find(fragment) != std::string::npos,
                "wrong rejection: " + std::string(error.what()));
        return;
    }
    throw std::runtime_error("expected rejection: " + fragment);
}

std::string read(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    require(input.good(), "cannot read " + path.string());
    return std::string(std::istreambuf_iterator<char>(input), {});
}
void equal_text(const std::string& actual, const std::string& expected, const std::string& where) {
    if (actual == expected) return;
    const auto common = std::min(actual.size(), expected.size());
    std::size_t at = 0;
    while (at < common && actual[at] == expected[at]) ++at;
    throw std::runtime_error(where + ": bytes differ at " + std::to_string(at) +
        " (actual " + std::to_string(actual.size()) + ", expected " + std::to_string(expected.size()) +
        ")\nactual: " + actual.substr(at, 180) + "\nexpected: " + expected.substr(at, 180));
}
const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    require(value != nullptr, "fixture missing field " + key);
    return *value;
}
std::string string_field(const JsonNode& node, const std::string& key) {
    const auto& value = field(node, key);
    require(value.kind == JsonKind::String, "fixture field is not a string: " + key);
    return value.string_value;
}
std::string optional_string(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    return value && value->kind != JsonKind::Null ? value->string_value : "";
}
JsonNode str(const std::string& value) {
    JsonNode node; node.kind = JsonKind::String; node.string_value = value; return node;
}
JsonNode num(double value) {
    JsonNode node; node.kind = JsonKind::Number; node.number_value = value; return node;
}
JsonNode object(std::vector<std::pair<std::string, JsonNode>> values = {}) {
    JsonNode node; node.kind = JsonKind::Object; node.object_value = std::move(values); return node;
}
JsonNode array(std::vector<JsonNode> values = {}) {
    JsonNode node; node.kind = JsonKind::Array; node.array_value = std::move(values); return node;
}

const SexprList& values(const Sexpr& node) {
    const auto* list = std::get_if<SexprList>(&node.v);
    require(list != nullptr, "expected S-expression list");
    return *list;
}
bool tag(const Sexpr& node, const std::string& name) {
    const auto* list = std::get_if<SexprList>(&node.v);
    if (!list || list->empty()) return false;
    const auto* symbol = std::get_if<Sexpr::Sym>(&list->front().v);
    return symbol && symbol->name == name;
}
std::vector<const Sexpr*> children(const Sexpr& node, const std::string& name) {
    std::vector<const Sexpr*> out;
    for (const auto& child : values(node)) if (tag(child, name)) out.push_back(&child);
    return out;
}
const Sexpr& child(const Sexpr& node, const std::string& name) {
    const auto found = children(node, name);
    require(!found.empty(), "missing S-expression child " + name);
    return *found.front();
}
std::string text_at(const Sexpr& node, std::size_t index = 1) {
    const auto& list = values(node);
    require(index < list.size() && std::holds_alternative<std::string>(list[index].v),
            "expected quoted S-expression text");
    return std::get<std::string>(list[index].v);
}

void core_contracts() {
    equal_text(schematic_stable_uuid({}), "0063361f-0233-58ee-b399-512d6d920cc9", "empty UUID name");
    equal_text(schematic_stable_uuid({"board", "root"}), "a16aeacf-2c90-5d0f-a821-7909a4db69a1",
               "board namespace UUID");
    SchematicIdFactory ids("scope");
    equal_text(ids("wire"), "1d2cc7ac-d2bd-55a1-9735-a2d142d9a7d5", "wire UUID zero");
    equal_text(ids("pin"), "45e6164f-cfd9-5c9e-9581-35e8e30c026c", "independent pin counter");
    equal_text(ids("wire"), "9a94c41c-7801-5916-90bb-2c36913b5476", "wire UUID one");
    equal_text(schematic_stable_uuid({"a", "b"}), schematic_stable_uuid({"a/b"}),
               "UUID slash concatenation changed");
    SchematicDesign design;
    design.circuit.name = "empty"; design.circuit.title = "Empty";
    const auto empty = emit_schematic(design, std::vector<SymbolDef>{});
    require(empty.project == "empty" && empty.instance_path == "/" + empty.root_uuid,
            "project/default non-bare instance path changed");
    require(empty.text.back() == '\n' && empty.text[empty.text.size() - 2] == ')',
            "output must have exactly one trailing newline");
    equal_text(sexpr_dumps(empty.document) + "\n", empty.text, "tree/text output disagree");
    equal_text(emit_schematic(design, std::vector<SymbolDef>{}, {"", "", ""}).text, empty.text,
               "empty option fallback changed");
    const auto explicit_path = emit_schematic(design, std::vector<SymbolDef>{}, {"/", "project", "root"});
    require(explicit_path.root_uuid == "root" && explicit_path.project == "project" &&
            explicit_path.instance_path == "/", "explicit instance options changed");
    SchematicPlacedPower power; power.value = "PWR_FLAG";
    require(power.net_name() == "PWR_FLAG" && !power.show_value, "power defaults changed");
    power.net = "GND";
    require(power.net_name() == "GND", "power net override changed");
    SchematicPlacedPart part; part.ref = "R1"; part.lib_id = "Device:R"; part.value = "10k";
    design.parts.push_back(part);
    rejects([&] { emit_schematic(design, std::vector<SymbolDef>{}); }, "missing symbol definition Device:R");
    rejects([&] { emit_schematic(design, SchematicSymbolResolver{}); }, "symbol resolver is required");
    SymbolDef symbol; symbol.lib_id = "Device:R";
    symbol.raw = sexpr_loads("(symbol \"R\")");
    rejects([&] { emit_schematic(design, std::vector<SymbolDef>{symbol, symbol}); }, "duplicate symbol definition");
    symbol.raw = sexpr_loads("(wrong \"R\")");
    rejects([&] { emit_schematic(design, std::vector<SymbolDef>{symbol}); }, "invalid symbol block");
    symbol.raw = sexpr_loads("(symbol \"R\")");
    for (const auto bad : {std::numeric_limits<double>::quiet_NaN(),
                           std::numeric_limits<double>::infinity(), 0x1p63}) {
        design.parts[0].x = bad;
        rejects([&] { emit_schematic(design, std::vector<SymbolDef>{symbol}); }, "numeric domain");
    }
}

void json_contracts() {
    CircuitSheetIr circuit; circuit.name = "in-memory"; circuit.title = "Retained";
    CircuitPartIr source_part; source_part.ref = "R1"; source_part.footprint = "memory:fp";
    circuit.parts.push_back(source_part);
    const auto empty = schematic_design_from_json(object(), circuit);
    require(empty.circuit.parts[0].footprint == "memory:fp" && empty.paper == "A4" && empty.standalone,
            "placement adapter lost supplied IR/defaults");
    const auto valid_part = object({{"ref", str("R1")}, {"lib_id", str("Device:R")},
        {"value", str("10k")}, {"x", num(0)}, {"y", num(1)}});
    const auto decoded = schematic_design_from_json(object({{"parts", array({valid_part})},
        {"sheets", array({object({{"name", str("child")}, {"file", str("child.kicad_sch")},
            {"x", num(1)}, {"y", num(2)}, {"w", num(3)}, {"h", num(4)}, {"uuid", str("id")},
            {"pins", array({object({{"name", str("pin")}, {"x", num(2)}, {"y", num(4)}})})}})})}}), circuit);
    require(decoded.parts.size() == 1 && !decoded.parts[0].ref_pos && !decoded.parts[0].val_pos &&
            decoded.parts[0].rotation == 0 && decoded.sheets[0].page == "2" &&
            decoded.sheets[0].pins[0].rotation == 180 &&
            decoded.sheets[0].pins[0].shape == "bidirectional", "placed dataclass defaults changed");
    rejects([&] { schematic_design_from_json(array(), circuit); }, "must be an object");
    rejects([&] { schematic_design_from_json(object({{"paper", num(1)}}), circuit); }, "must be a string");
    rejects([&] { schematic_design_from_json(object({{"standalone", num(1)}}), circuit); }, "must be a bool");
    rejects([&] { schematic_design_from_json(object({{"wires", object()}}), circuit); }, "must be an array");
    rejects([&] { schematic_design_from_json(object({{"parts", array({object()})}}), circuit); }, "missing placement field");
    for (const auto bad_rotation : {1.5, 2147483648.0, -2147483649.0}) {
        auto row = valid_part; row.object_value.emplace_back("rotation", num(bad_rotation));
        rejects([&] { schematic_design_from_json(object({{"parts", array({row})}}), circuit); }, "rotation must be an integer");
    }
    auto row = valid_part; row.object_value.emplace_back("ref_pos", array({num(0), num(1)}));
    rejects([&] { schematic_design_from_json(object({{"parts", array({row})}}), circuit); }, "must be [x, y, rotation]");
    row = valid_part; row.object_value.emplace_back("val_pos", array({num(0), num(std::numeric_limits<double>::infinity()), num(0)}));
    rejects([&] { schematic_design_from_json(object({{"parts", array({row})}}), circuit); }, "must be a finite number");
}

void structural_contracts(const SchematicDesign& design, const std::vector<SymbolDef>& symbols,
                          const SchematicOptions& options, const SchematicOutput& result) {
    std::vector<std::string> calls;
    const auto resolved = emit_schematic(design, [&](const std::string& id) -> const SymbolDef& {
        calls.push_back(id);
        const auto found = std::find_if(symbols.begin(), symbols.end(),
            [&](const auto& symbol) { return symbol.lib_id == id; });
        require(found != symbols.end(), "fixture symbol not found");
        return *found;
    }, options);
    equal_text(resolved.text, result.text, "resolver/vector overload parity");
    std::set<std::string> unique;
    for (const auto& part : design.parts) unique.insert(part.lib_id);
    for (const auto& power : design.powers) unique.insert(power.lib_id);
    std::vector<std::string> expected_calls(unique.begin(), unique.end());
    for (const auto& part : design.parts) expected_calls.push_back(part.lib_id);
    for (const auto& power : design.powers) expected_calls.push_back(power.lib_id);
    require(calls == expected_calls, "library access order changed");
    std::vector<std::string> embedded;
    for (const auto* symbol : children(child(result.document, "lib_symbols"), "symbol"))
        embedded.push_back(text_at(*symbol));
    require(embedded == std::vector<std::string>(unique.begin(), unique.end()),
            "embedded symbols must be deduplicated, sorted, and renamed by lib_id");
    auto wire_variant = design;
    wire_variant.wires.insert(wire_variant.wires.begin(), {9.1, 8.2, 7.3, 6.4});
    const auto changed = emit_schematic(wire_variant, symbols, options);
    const auto old_symbols = children(result.document, "symbol");
    const auto new_symbols = children(changed.document, "symbol");
    require(old_symbols.size() == new_symbols.size(), "adding a wire changed symbol count");
    for (std::size_t i = 0; i < old_symbols.size(); ++i)
        equal_text(sexpr_dumps(*old_symbols[i]), sexpr_dumps(*new_symbols[i]), "wire changed symbol/pin UUIDs");
    auto instance_variant = options; instance_variant.instance_path = "/different/instance";
    const auto changed_path = emit_schematic(design, symbols, instance_variant);
    require(changed_path.root_uuid == result.root_uuid, "instance path changed root UUID");
    for (const auto* sheet : children(changed_path.document, "sheet")) {
        const auto& path = child(child(child(*sheet, "instances"), "project"), "path");
        require(text_at(path) == "/" + result.root_uuid, "sheet instances incorrectly use symbol instance_path");
    }
    for (const auto* symbol : children(changed_path.document, "symbol")) {
        const auto& path = child(child(child(*symbol, "instances"), "project"), "path");
        require(text_at(path) == "/different/instance", "symbol instance_path override lost");
    }
}

void fixture_contracts(const std::filesystem::path& fixture_dir,
                       const std::filesystem::path& output_dir) {
    const auto data = parse_json_file((fixture_dir / "cases.json").string());
    require(string_field(data, "schema") == "schgen.schematic.contracts.v1", "fixture schema changed");
    std::vector<SymbolDef> symbols;
    std::vector<std::string> original_raw;
    for (const auto& row : field(data, "symbols").array_value) {
        SymbolDef symbol; symbol.lib_id = string_field(row, "lib_id");
        symbol.raw = sexpr_loads(string_field(row, "raw"));
        for (const auto& number : field(row, "pins").array_value) {
            SymbolPin pin; pin.number = number.string_value; symbol.pins.push_back(pin);
        }
        original_raw.push_back(sexpr_dumps(symbol.raw));
        symbols.push_back(std::move(symbol));
    }
    for (const auto& row : field(data, "uuids").array_value) {
        std::vector<std::string> parts;
        for (const auto& part : field(row, "parts").array_value) parts.push_back(part.string_value);
        equal_text(schematic_stable_uuid(parts), string_field(row, "uuid"), "Python UUIDv5 golden");
    }
    std::size_t count = 0, bytes = 0;
    for (const auto& row : field(data, "cases").array_value) {
        const auto name = string_field(row, "name");
        const auto& placed = field(row, "design");
        const auto& ir = field(placed, "circuit");
        // Python permits a completely empty Circuit for an empty sheet.
        CircuitSheetIr circuit;
        if (!string_field(ir, "name").empty()) circuit = parse_circuit_ir(ir);
        else { circuit.name = ""; circuit.title = string_field(ir, "title"); }
        const auto design = schematic_design_from_json(placed, std::move(circuit));
        const auto& args = field(row, "options");
        const SchematicOptions options{optional_string(args, "instance_path"),
            optional_string(args, "project"), optional_string(args, "sheet_uuid")};
        const auto result = emit_schematic(design, symbols, options);
        const auto filename = std::filesystem::path(string_field(row, "golden"));
        require(filename == filename.filename(), "golden fixture name must be a basename");
        equal_text(result.text, read(fixture_dir / filename), name + " Python schematic golden");
        const auto& expected = field(row, "expected");
        equal_text(result.root_uuid, string_field(expected, "root_uuid"), name + " root UUID");
        equal_text(result.project, string_field(expected, "project"), name + " project");
        equal_text(result.instance_path, string_field(expected, "instance_path"), name + " instance path");
        structural_contracts(design, symbols, options, result);
        if (!output_dir.empty()) {
            std::filesystem::create_directories(output_dir);
            std::ofstream output(output_dir / filename, std::ios::binary);
            output << result.text;
            require(output.good(), "cannot write requested test artifact");
        }
        ++count; bytes += result.text.size();
    }
    for (std::size_t i = 0; i < symbols.size(); ++i)
        equal_text(sexpr_dumps(symbols[i].raw), original_raw[i], "emitter mutated caller/library symbol tree");
    std::cout << "Python schematic parity: " << count << " files, " << bytes << " bytes, "
              << field(data, "uuids").array_value.size() << " UUID vectors\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 1 || argc == 2 || argc == 4,
                "usage: schematic_contracts [FIXTURE_DIR [--emit-dir TEMP_OUTPUT_DIR]]");
        if (argc == 4) require(std::string(argv[2]) == "--emit-dir", "expected --emit-dir");
        core_contracts();
        json_contracts();
        if (argc >= 2) fixture_contracts(argv[1], argc == 4 ? argv[3] : "");
        std::cout << "Native schematic contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
