// Standalone contracts: real repository inputs, no Python or shared outputs.
#include "schgen/project.hpp"
#include "schgen/project_catalog.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);  // Also active under NDEBUG.
}

struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen-project-contracts-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = pattern;
    }
    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;
    ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};

struct Environment {
    std::optional<std::string> previous;
    Environment() { if (const auto* value = std::getenv("SCHGEN_PROJECT")) previous = value; }
    ~Environment() {
        if (previous) ::setenv("SCHGEN_PROJECT", previous->c_str(), 1);
        else ::unsetenv("SCHGEN_PROJECT");
    }
};

struct CatalogGuard {
    ~CatalogGuard() { try { close_circuit_catalog(); } catch (...) { std::abort(); } }
};

std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    require(bool(out), "cannot create " + path.string());
    out << text;
    out.close();
    require(bool(out), "cannot write " + path.string());
}

std::string changed(std::string text, const std::string& before, const std::string& after) {
    const auto pos = text.find(before);
    require(!before.empty() && pos != std::string::npos, "missing mutation: " + before);
    require(text.find(before, pos + before.size()) == std::string::npos, "ambiguous mutation: " + before);
    text.replace(pos, before.size(), after);
    return text;
}

JsonNode& member(JsonNode& node, const std::string& key) {
    for (auto& item : node.object_value) if (item.first == key) return item.second;
    throw std::runtime_error("missing mutable fixture field " + key);
}

template <typename F>
void rejects(F action, const std::vector<std::string>& messages) {
    try { action(); }
    catch (const std::runtime_error& error) {
        for (const auto& message : messages) {
            require(std::string(error.what()).find(message) != std::string::npos,
                    "expected diagnostic '" + message + "', got: " + error.what());
        }
        return;
    }
    throw std::runtime_error("invalid input was accepted");
}

struct Suite {
    unsigned passed = 0, failed = 0;
    template <typename F>
    void run(const std::string& label, F action) {
        try { action(); ++passed; }
        catch (const std::exception& error) { ++failed; std::cerr << label << ": " << error.what() << '\n'; }
    }
};

// Lossless comparison of every field, optional-presence flag and ordered list
// between the public loader and the binary catalog's independent encoding.
std::string record(const CircuitSheetIr& s) {
    std::ostringstream out;
    out << std::setprecision(17);
    const auto text = [&](const std::string& v) { out << v.size() << ':' << v << ';'; };
    const auto text_list = [&](const std::vector<std::string>& vs) {
        out << vs.size() << '['; for (const auto& v : vs) text(v); out << ']';
    };
    const auto pin_list = [&](const std::vector<CircuitPinRefIr>& ps) {
        out << ps.size() << '['; for (const auto& p : ps) { text(p.ref); text(p.pin); } out << ']';
    };
    text(s.schema); text(s.name); text(s.title);
    out << s.parts.size() << '[';
    for (const auto& p : s.parts) {
        text(p.ref); text(p.lib_id); text(p.value); text(p.footprint);
        out << p.fields.size() << '[';
        for (const auto& f : p.fields) { text(f.key); text(f.value); }
        out << ']' << p.pin_names.size() << '[';
        for (const auto& pn : p.pin_names) { text(pn.name); text_list(pn.numbers); }
        out << ']'; text_list(p.pin_numbers);
    }
    out << ']' << s.nets.size() << '[';
    for (const auto& n : s.nets) { text(n.name); text(n.net_class); pin_list(n.pins); }
    out << ']'; pin_list(s.nc);
    out << s.port_types.size() << '[';
    for (const auto& p : s.port_types) {
        text(p.net); text(p.kind); text(p.pair_with); text(p.role); text(p.bus); text(p.expect);
        out << p.has_pair_with << ',' << p.impedance << ',' << p.has_impedance << ','
            << p.has_role << ',' << p.has_bus << ',' << p.speed_hz << ',' << p.has_speed_hz << ','
            << p.level_v << ',' << p.has_level_v << ',' << p.has_expect << ';';
    }
    out << ']' << s.hints.size() << '[';
    for (const auto& h : s.hints) { text(h.net); text(h.style); }
    out << ']' << s.loads.size() << '[';
    for (const auto& l : s.loads) { text(l.rail); out << l.amps << ';'; text(l.note); }
    out << ']' << s.waivers.size() << '[';
    for (const auto& w : s.waivers) { text(w.kind); text(w.key); text(w.reason); }
    out << ']';
    return out.str();
}

void fixture_contracts(Suite& suite, const fs::path& repo) {
    const auto fixture_dir = repo / "native/tests/data/project";
    const auto config_text = read(fixture_dir / "project.json");
    const auto circuit_text = read(fixture_dir / "circuit.json");
    suite.run("config defaults and source order", [&] {
        TempDir tmp;
        write(tmp.path / "project.json", config_text);
        const auto paths = resolve_project_paths(repo, tmp.path);
        const auto config = load_project_config(paths);
        require(config.name == "fixture" && config.wired_sheets == std::vector<std::string>{"zeta", "alpha"}, "name/order changed");
        require(config.module_offset == std::array<double, 2>{-10, 6.25}, "offset changed");
        require(config.module_face_anchors == ProjectStrings{{"zeta", "E"}, {"alpha", "S"}}, "anchor order changed");
        require(config.reg_band_prefixes == std::vector<std::string>{"power", "bringup"}, "prefix order changed");
        require(config.bank_rails.empty() && config.header_desc.empty() && config.switch_desc.empty()
                && config.escape.kind == JsonKind::Object && config.escape.object_value.empty(), "optional defaults changed");
        require(object_field(config.raw, "extension") != nullptr, "extension metadata dropped");
        require(default_engine_config.grid == 1.27 && default_engine_config.char_w == 0.95
                && default_engine_config.misplaced_overlap == 0.20 && default_engine_config.cross_k == 3.0
                && default_engine_config.visual_clearance_mm == 0.2, "engine defaults changed");
        require(!paths.is_default_project && paths.parts_dir == repo / "parts", "external project paths wrong");
        require(load_sheet_index(paths).empty() && !fs::exists(paths.sheet_index_file), "missing index was written");
        rejects([&] { load_project_manifest(paths); }, {paths.manifest_file.string()});
        require(read(paths.project_file) == config_text, "config load changed source");
    });
    const std::vector<std::pair<std::string, std::string>> invalid_configs = {
        {changed(config_text, "\"name\": \"fixture\"", "\"name\": null"), "name"},
        {changed(config_text, "[-10, 6.25]", "[0]"), "module_offset"},
        {changed(config_text, "[-10, 6.25]", "[false, 6.25]"), "module_offset"},
        {changed(config_text, "\"pilot_prox_sheets\": []", "\"pilot_prox_sheets\": {}"), "pilot_prox_sheets"},
        {changed(config_text, "\"extension\"", "\"fpga\": null, \"extension\""), "fpga"},
        {changed(config_text, "\"extension\"", "\"silk_labels\": {\"headers\": null}, \"extension\""), "headers"},
        {changed(config_text, "\"extension\"", "\"escape\": [], \"extension\""), "escape"},
        {"{\"name\":\"a\",\"name\":\"b\"}", "duplicate key"},
        {"{", "json"}, {"[]", "object"}};
    for (std::size_t i = 0; i < invalid_configs.size(); ++i) {
        suite.run("malformed config " + std::to_string(i), [&] {
            TempDir tmp;
            write(tmp.path / "project.json", invalid_configs[i].first);
            const auto paths = resolve_project_paths(repo, tmp.path);
            rejects([&] { load_project_config(paths); }, {paths.project_file.string(), invalid_configs[i].second});
        });
    }
    suite.run("ordered canonical records and implicit port default", [&] {
        const auto s = load_circuit_json(fixture_dir / "circuit.json");
        require(s.parts[0].ref == "U2" && s.parts[1].ref == "R1", "parts reordered");
        require(s.parts[0].fields[0].key == "Z" && s.parts[0].fields[1].key == "A", "fields reordered");
        require(s.parts[0].pin_names[0].name == "ZZ" && s.parts[0].pin_names[0].numbers == std::vector<std::string>{"2", "1"}, "aliases reordered");
        require(s.parts[0].pin_numbers == std::vector<std::string>{"2", "1", "3"}, "pin table reordered");
        require(s.nets[0].name == "Z_P" && s.nets[1].name == "A_N" && s.nets[0].pins.size() == 3, "nets or repeated pins changed");
        require(s.nc.size() == 2 && s.nc[0].ref == "U2" && s.nc[1].pin == "A99", "NC order changed");
        require(s.port_types[0].net == "Z_P" && s.port_types[0].has_bus && s.port_types[0].bus.empty()
                && s.port_types[0].has_speed_hz && !s.port_types[1].has_speed_hz, "optional port metadata changed");
        require(s.hints[0].net == "Z_P" && s.hints[1].net == "A_N", "hints reordered");
        require(s.loads.size() == 3 && s.loads[0].note == "first" && s.loads[1].note == "second" && s.loads[2].rail == "VIN", "load grouping changed");
        require(s.waivers.size() == 3 && s.waivers[0].kind == "tp_waivers" && s.waivers[0].key == "Z_P"
                && s.waivers[2].kind == "part_rule_waivers", "Python waiver attribute order changed");
        const auto pt = circuit_port_type(s, "untyped");
        require(pt.kind == "single" && !pt.has_pair_with && !pt.has_impedance && !pt.has_role
                && !pt.has_bus && !pt.has_speed_hz && !pt.has_level_v && !pt.has_expect, "implicit PortType default changed");
        require(circuit_port_type(s, "Z_P").pair_with == "A_N", "explicit PortType lost");
        TempDir tmp;
        CatalogGuard guard;
        compile_circuit_catalog(fixture_dir.string(), (tmp.path / "circuits.bin").string());
        open_circuit_catalog((tmp.path / "circuits.bin").string());
        require(record(s) == record(lookup_circuit_catalog("fixture")), "catalog fixture differs from direct load");
    });
    const std::vector<std::tuple<std::string, std::string, std::string>> mutations = {
        {"schgen.circuit/1", "schgen.circuit/2", "schema"},
        {"\"title\": \"Ordered fixture\"", "\"title\": false", "title"},
        {"\"ref\": \"R1\"", "\"ref\": \"U2\"", "duplicate reference"},
        {"\"ref\": \"R1\"", "\"ref\": \"R1\", \"unknown\": 1", "unknown key"},
        {"\"name\": \"A_N\"", "\"name\": \"Z_P\"", "duplicate net"},
        {"\"net_class\": \"power\"", "\"net_class\": \"other\"", "unknown net_class"},
        {"\"U2.1\", \"R1.2\"", "\"U2.1\", \"MISSING.1\"", "unknown part"},
        {"\"U2.1\", \"R1.2\"", "\"U2.99\", \"R1.2\"", "pin does not exist"},
        {"\"U2.1\", \"R1.2\"", "\"U2.2\", \"R1.2\"", "already on net"},
        {"\"nc\": [\"U2.3\", \"R1.A99\"]", "\"nc\": [\"U2.1\"]", "cannot be NC"},
        {"\"NC\": [\"3\"]", "\"NC\": [\"99\"]", "targets undeclared pin"},
        {"\"NC\": [\"3\"]", "\"NC\": []", "at least one pin"},
        {"\"U2.1\", \"R1.2\"", "\"U2.\", \"R1.2\"", "bad pin spec"},
        {"\"speed_hz\": 480000000", "\"speed_hz\": 2147483648", "32-bit integer"},
        {"\"speed_hz\": 480000000", "\"speed_hz\": -2147483649", "32-bit integer"},
        {"\"speed_hz\": 480000000", "\"speed_hz\": 1.5", "integer"},
        {"\"speed_hz\": 480000000", "\"speed_hz\": true", "number or null"},
        {"\"speed_hz\": 480000000", "\"speed_hz\": 1e999", "circuit.json"},
        {"\"bus\": \"\", \"speed_hz\": null", "\"bus\": null, \"speed_hz\": null", "conflicting reciprocal"},
        {"\"pair_with\": \"A_N\"", "\"pair_with\": \"Z_P\"", "pair with itself"},
        {"\"level_v\": 1.8", "\"level_v\": true", "number or null"},
        {"[[0.5, \"third\"]]", "[]", "non-empty arrays"},
        {"[[0.5, \"third\"]]", "[[true, \"third\"]]", "[amps, note]"},
        {"\"hints\": {\"Z_P\": \"wire\", \"A_N\": \"label\"}", "\"hints\": null", "hints"},
        {"\"thermal_waivers\": {}", "\"thermal_waivers\": {\"U2\": false}", "thermal_waivers"}};
    for (const auto& mutation : mutations) {
        const auto& before = std::get<0>(mutation);
        const auto& after = std::get<1>(mutation);
        const auto& diagnostic = std::get<2>(mutation);
        suite.run("invalid circuit " + diagnostic + " " + after, [&] {
            TempDir tmp;
            const auto source = tmp.path / "source/circuit.json";
            const auto text = changed(circuit_text, before, after);
            write(source, text);
            rejects([&] { load_circuit_json(source); }, {source.string(), diagnostic});
            rejects([&] { compile_circuit_catalog(source.parent_path().string(), (tmp.path / "bad.bin").string()); }, {source.string(), diagnostic});
            require(!fs::exists(tmp.path / "bad.bin") && read(source) == text, "invalid load wrote output");
        });
    }
    suite.run("JSON syntax, missing files and integer boundaries", [&] {
        TempDir tmp;
        const auto input = tmp.path / "circuit.json";
        rejects([&] { load_circuit_json(input); }, {input.string(), "missing"});
        for (const std::string bad : {"", "{", "[]", "{}", "{\"schema\":1,\"schema\":2}"}) {
            write(input, bad);
            rejects([&] { load_circuit_json(input); }, {input.string()});
        }
        for (const int32_t value : {std::numeric_limits<int32_t>::min(), std::numeric_limits<int32_t>::max()}) {
            write(input, changed(circuit_text, "\"speed_hz\": 480000000", "\"speed_hz\": " + std::to_string(value)));
            require(load_circuit_json(input).port_types.front().speed_hz == value, "int32 boundary changed");
        }
    });
    suite.run("in-memory edits are authoritative without modifying source", [&] {
        auto root = parse_json_file((fixture_dir / "circuit.json").string());
        const auto original = load_circuit_json(fixture_dir / "circuit.json");
        require(record(parse_circuit_ir(root)) == record(original), "in-memory and file parsers diverged");
        member(root, "title").string_value = "In-memory edit";
        member(member(root, "nets").array_value[0], "pins").array_value.erase(
            member(member(root, "nets").array_value[0], "pins").array_value.begin() + 1);
        member(member(member(root, "port_types"), "Z_P"), "speed_hz").number_value = 12000000;
        const auto edited = parse_circuit_ir(root);
        require(edited.title == "In-memory edit" && edited.nets[0].pins.size() == 2
                && edited.port_types[0].speed_hz == 12000000, "caller edits were bypassed");
        require(record(load_circuit_json(fixture_dir / "circuit.json")) == record(original), "in-memory parse changed file");
        require(read(fixture_dir / "circuit.json") == circuit_text, "source JSON changed");
    });
    const auto memory_reject = [&](const std::string& label, const std::function<void(JsonNode&)>& edit,
                                   const std::string& diagnostic) {
        suite.run("invalid in-memory IR " + label, [&] {
            auto root = parse_json_file((fixture_dir / "circuit.json").string());
            edit(root);
            rejects([&] { parse_circuit_ir(root); }, {diagnostic});
        });
    };
    memory_reject("unknown pin owner", [](JsonNode& root) {
        member(member(root, "nets").array_value[0], "pins").array_value[0].string_value = "UNKNOWN.2";
    }, "unknown part");
    memory_reject("pin conflict", [](JsonNode& root) {
        member(member(root, "nets").array_value[1], "pins").array_value[0].string_value = "U2.2";
    }, "already on net");
    memory_reject("NC conflict", [](JsonNode& root) {
        member(root, "nc").array_value[0].string_value = "U2.2";
    }, "cannot be NC");
    memory_reject("unknown schema", [](JsonNode& root) {
        member(root, "schema").string_value = "schgen.circuit/9";
    }, "schema");
    memory_reject("reciprocal pair mismatch", [](JsonNode& root) {
        member(member(member(root, "port_types"), "A_N"), "impedance").number_value = 90;
    }, "conflicting reciprocal");
    memory_reject("integer overflow", [](JsonNode& root) {
        member(member(member(root, "port_types"), "Z_P"), "speed_hz").number_value = 2147483648.0;
    }, "32-bit integer");
    memory_reject("boolean numeric value", [](JsonNode& root) {
        member(member(member(root, "port_types"), "Z_P"), "speed_hz").kind = JsonKind::Bool;
    }, "number or null");
    memory_reject("NaN voltage", [](JsonNode& root) {
        member(member(member(root, "port_types"), "Z_P"), "level_v").number_value = std::numeric_limits<double>::quiet_NaN();
    }, "level_v: number must be finite");
    memory_reject("infinite load", [](JsonNode& root) {
        member(member(root, "loads"), "VIN").array_value[0].array_value[0].number_value = std::numeric_limits<double>::infinity();
    }, "loads.VIN[0][0]: number must be finite");
    memory_reject("duplicate top-level key", [](JsonNode& root) {
        root.object_value.push_back(root.object_value.front());
    }, "duplicate key");
    memory_reject("duplicate nested field", [](JsonNode& root) {
        auto& fields = member(member(root, "parts").array_value[0], "fields");
        fields.object_value.push_back(fields.object_value.front());
    }, "parts[0].fields: duplicate key");
    memory_reject("missing required member", [](JsonNode& root) {
        root.object_value.erase(root.object_value.begin());
    }, "missing required field 'schema'");
    suite.run("discovery precedence, missing JSON and explicit order", [&] {
        TempDir tmp;
        write(tmp.path / "project.json", config_text);
        const auto paths = resolve_project_paths(repo, tmp.path);
        const auto add = [&](const std::string& name) {
            write(paths.subsystems_dir / name / "circuit.json", changed(circuit_text, "\"name\": \"fixture\"", "\"name\": \"" + name + "\""));
        };
        add("zeta"); add("alpha");
        write(paths.subsystems_dir / "zeta.py", "raise RuntimeError('must never execute')");
        write(paths.subsystems_dir / "zeta/zeta.py", "not even valid Python");
        write(paths.subsystems_dir / "__init__.py", "");
        write(paths.subsystems_dir / "test_ignored.py", "");
        write(paths.subsystems_dir / ".hidden/circuit.json", "bad json");
        write(paths.subsystems_dir / "_private/circuit.json", "bad json");
        write(paths.subsystems_dir / "nested/deeper/circuit.json", "bad json");
        const auto inventory = inventory_project_circuits(paths);
        require(inventory.size() == 2 && inventory[0].name == "alpha" && inventory[1].name == "zeta", "inventory order/filter changed");
        require(inventory[1].authoring_path == paths.subsystems_dir / "zeta/zeta.py" && inventory[0].has_circuit_json, "foldered precedence lost");
        const auto selected = load_project_circuits(paths, {"zeta", "alpha", "zeta"});
        require(selected.size() == 3 && selected[0].name == "zeta" && selected[1].name == "alpha", "selection reordered");
        require(load_project_circuits(paths, {}).empty(), "explicit empty selection changed");
        require(load_project_circuits(paths)[0].name == "alpha", "default load order changed");
        const auto canonical = discover_project_subsystems(paths.subsystems_dir);
        require(canonical.size() == inventory.size(), "project and catalog inventories diverged");
        for (std::size_t i = 0; i < canonical.size(); ++i) {
            require(canonical[i].name == inventory[i].name && canonical[i].circuit_json == inventory[i].path, "canonical layout differs");
        }
        write(tmp.path / "outside/circuit.json", changed(circuit_text, "\"name\": \"fixture\"", "\"name\": \"linked\""));
        fs::create_directory_symlink(tmp.path / "outside", paths.subsystems_dir / "linked");
        require(inventory_project_circuits(paths).size() == 2, "symlink added noncanonical sheet");
        rejects([&] { load_project_circuit(paths, "linked"); }, {"symlinked subsystem"});
        write(paths.subsystems_dir / "legacy.py", "not valid Python");
        rejects([&] { inventory_project_circuits(paths); }, {"legacy/circuit.json", "incomplete subsystem migration"});
        rejects([&] { load_project_circuits(paths); }, {"legacy/circuit.json", "incomplete subsystem migration"});
        rejects([&] { load_project_circuit(paths, "../alpha"); }, {"invalid name"});
        write(paths.subsystems_dir / "alpha/circuit.json", circuit_text);
        rejects([&] { load_project_circuit(paths, "alpha"); }, {"alpha/circuit.json", "does not match"});
    });
    suite.run("missing and empty subsystem directories", [&] {
        TempDir tmp;
        write(tmp.path / "project.json", config_text);
        const auto paths = resolve_project_paths(repo, tmp.path);
        rejects([&] { inventory_project_circuits(paths); }, {paths.subsystems_dir.string(), "directory"});
        fs::create_directory(paths.subsystems_dir);
        require(inventory_project_circuits(paths).empty(), "empty inventory changed");
        rejects([&] { load_project_circuits(paths); }, {"no subsystem circuits"});
        fs::create_directories(paths.subsystems_dir / "broken/circuit.json");
        require(inventory_project_circuits(paths).empty(), "directory counted as JSON");
        rejects([&] { load_project_circuit(paths, "broken"); }, {"broken/circuit.json", "regular file"});
    });
    suite.run("stable and positional sheet bands", [&] {
        const SheetIndex original{{"zeta", 8}, {"retired", 3}};
        const auto update = extend_sheet_index(original, {"new_z", "zeta", "new_a"});
        require(update.index == SheetIndex{{"zeta", 8}, {"retired", 3}, {"new_a", 9}, {"new_z", 10}}, "stable bands changed");
        require(update.unseen == std::vector<std::string>{"new_a", "new_z"}, "unseen order changed");
        require(extend_sheet_index(update.index, {"new_z", "zeta"}).unseen.empty(), "known sheets reassigned");
        require(positional_sheet_index({"b", "a", "b"}) == SheetIndex{{"b", 3}, {"a", 2}}, "positional overwrite changed");
        require(extend_sheet_index({}, {"b", "a", "a"}).index == SheetIndex{{"a", 2}, {"b", 3}}, "Python duplicate overwrite changed");
        rejects([&] { extend_sheet_index({{"a", 0}}, {}); }, {"positive"});
        rejects([&] { extend_sheet_index({{"a", 1}, {"b", 1}}, {}); }, {"duplicate band"});
        rejects([&] { extend_sheet_index({{"a", std::numeric_limits<int32_t>::max()}}, {"b"}); }, {"overflow"});
        TempDir tmp;
        write(tmp.path / "project.json", config_text);
        const auto paths = resolve_project_paths(repo, tmp.path);
        const std::string index_text = "{\"zeta\":8,\"retired\":3}";
        write(paths.sheet_index_file, index_text);
        require(load_sheet_index(paths) == original, "loaded index order changed");
        extend_sheet_index(load_sheet_index(paths), {"added"});
        require(read(paths.sheet_index_file) == index_text, "read-only extension wrote source");
        for (const std::string bad : {"{\"a\":true}", "{\"a\":1.5}", "{\"a\":2147483648}", "{\"a\":-1}", "{\"a\":1,\"b\":1}"}) {
            write(paths.sheet_index_file, bad);
            rejects([&] { load_sheet_index(paths); }, {paths.sheet_index_file.string()});
        }
    });
    suite.run("manifest null device and extension records", [&] {
        TempDir tmp;
        write(tmp.path / "project.json", config_text);
        const auto paths = resolve_project_paths(repo, tmp.path);
        write(paths.manifest_file, "{\"device\":null,\"artifacts\":[{\"path\":\"report.txt\",\"sha256\":\"abc\"}],\"rails\":[{\"name\":\"VIN\"}]}");
        const auto manifest = load_project_manifest(paths);
        require(!manifest.device && manifest.artifacts.size() == 1 && manifest.artifacts[0].path == "report.txt", "manifest metadata changed");
        require(object_field(manifest.raw, "rails") != nullptr, "manifest data dropped");
    });
}

void repository_contracts(Suite& suite, const fs::path& repo) {
    suite.run("selection precedence and stable paths", [&] {
        Environment env;
        ::unsetenv("SCHGEN_PROJECT");
        const auto carrier = resolve_project_paths(repo);
        require(carrier.is_default_project && carrier.project_root == repo / "carrier", "default project changed");
        ::setenv("SCHGEN_PROJECT", "devkit_mini", 1);
        require(resolve_project_paths(repo).project_root == repo / "devkit_mini", "environment selection ignored");
        require(resolve_project_paths(repo, "carrier").is_default_project, "explicit selection did not override environment");
        require(resolve_project_paths(repo, repo / "devkit_mini").project_root == repo / "devkit_mini", "absolute selection changed");
        require(resolve_project_paths(repo, "devkit_mini/../carrier/").is_default_project, "lexical normalization changed");
        require(carrier.som_interface_file == repo / "carrier/som_interface.json" && carrier.som_schematic == repo / "som/Zynq_SoM.kicad_sch", "SoM paths wrong");
        require(carrier.part_catalog_file == repo / "native/catalog.bin" && carrier.fpga_dir == repo / "carrier/fpga", "downstream paths wrong");
        const auto catalogs = project_catalog_paths(repo, "carrier");
        require(carrier.part_catalog_file == catalogs.part_catalog && carrier.circuit_catalog_file == catalogs.circuit_catalog, "catalog paths diverged");
        rejects([&] { resolve_project_paths(repo, "missing-project"); }, {"missing-project"});
        rejects([&] { resolve_project_paths(repo, "parts"); }, {"parts/project.json", "missing"});
    });
    const std::vector<std::string> carrier_names = {
        "board_aux", "board_qwiic", "board_services", "bringup_en", "bringup_en_modules", "bringup_modules", "bringup_rails",
        "camera", "debug_boot", "ethernet", "fmc", "hdmi_rx", "hdmi_rx_term", "hdmi_tx", "lcd", "mechanical", "microsd",
        "motor_pwm", "motor_sense", "pd_input", "pmod", "pmod_expansion", "power", "power_mon", "power_som", "rj45_connector",
        "som_decoupling", "som_j1", "som_j2", "som_j3", "uart_bridge", "usb_jtag", "usb_jtag_connector", "usb_pd", "usb_uart_connector", "usbc_otg", "user_io"};
    const std::vector<std::string> devkit_names = {"debug_boot", "mechanical", "pd_input", "power", "power_mon", "power_som", "som_decoupling", "som_j1", "som_j2", "som_j3", "uart_bridge", "usb_uart_connector"};
    for (const std::string project : {"carrier", "devkit_mini"}) {
        suite.run("real repository " + project, [&] {
            const bool carrier = project == "carrier";
            const auto paths = resolve_project_paths(repo, project);
            const auto config_before = read(paths.project_file), index_before = read(paths.sheet_index_file);
            const auto config = load_project_config(paths);
            require(config.name == project, "project name changed");
            require(config.module_offset == (carrier ? std::array<double, 2>{-10, 6} : std::array<double, 2>{0, 0}), "project offset changed");
            require(config.bank_rails == ProjectStrings{{"13", "+3V3"}, {"33", "+3V3"}, {"34", "+3V3"}, {"35", carrier ? "+2V5_VADJ" : "+3V3"}}, "project banks changed");
            require(config.wired_sheets.size() == (carrier ? 23u : 4u) && config.pilot_prox_sheets.size() == (carrier ? 2u : 0u), "placement metadata changed");
            require(config.header_desc.front() == std::make_pair(std::string(carrier ? "J11001" : "J1001"), std::string(carrier ? "GPIO" : "JTAG")), "silk metadata changed");
            const auto* pairs = object_field(config.escape, "genuine_pairs");
            require(pairs && pairs->number_value == (carrier ? 15 : 4), "escape metadata changed");
            const auto& expected = carrier ? carrier_names : devkit_names;
            const auto inventory = inventory_project_circuits(paths);
            require(inventory.size() == expected.size(), "real inventory count changed");
            for (std::size_t i = 0; i < expected.size(); ++i) {
                require(inventory[i].name == expected[i] && inventory[i].has_circuit_json, "missing canonical circuit: " + expected[i]);
            }
            const auto sheets = load_project_circuits(paths);
            require(sheets.size() == expected.size(), "loaded sheet count changed");
            std::size_t parts = 0, nets = 0, ports = 0, nc = 0;
            TempDir tmp;
            CatalogGuard guard;
            const auto catalog = (tmp.path / "circuits.bin").string();
            compile_circuit_catalog(paths.subsystems_dir.string(), catalog);
            open_circuit_catalog(catalog);
            require(circuit_catalog_count() == expected.size(), "catalog inventory differs");
            for (std::size_t i = 0; i < sheets.size(); ++i) {
                const auto& s = sheets[i];
                require(s.name == expected[i] && s.path == inventory[i].path, "record provenance changed");
                require(record(s.circuit) == record(lookup_circuit_catalog(s.name)), "catalog data differs: " + s.name);
                parts += s.circuit.parts.size(); nets += s.circuit.nets.size(); ports += s.circuit.port_types.size(); nc += s.circuit.nc.size();
            }
            require(parts == (carrier ? 564u : 147u) && nets == (carrier ? 818u : 321u)
                    && ports == (carrier ? 387u : 46u) && nc == (carrier ? 130u : 55u), "real IR totals changed");
            const auto index = load_sheet_index(paths);
            require(index.size() == expected.size() && extend_sheet_index(index, expected).unseen.empty(), "stable sheet bands diverged");
            require(index.front() == std::make_pair(expected.front(), int32_t(1)), "first sheet band changed");
            const auto manifest = load_project_manifest(paths);
            require(manifest.device == "XC7Z020-CLG484 (U2 on the SoM)" && !manifest.artifacts.empty(), "real manifest missing");
            for (const auto& artifact : manifest.artifacts) require(artifact.sha256.size() == 64, "manifest artifact hash dropped");
            for (const std::string key : {"bom", "rails", "gpio_map", "i2c_map", "xdc", "testpoints"}) require(object_field(manifest.raw, key), "manifest lost " + key);
            require(read(paths.project_file) == config_before && read(paths.sheet_index_file) == index_before, "repository metadata changed");
            std::cout << project << ": " << sheets.size() << " sheets, " << parts << " parts, " << nets << " nets; full catalog parity\n";
        });
    }
    suite.run("simultaneous projects without catalog contamination", [&] {
        TempDir tmp;
        CatalogGuard guard;
        const auto carrier_paths = resolve_project_paths(repo, "carrier");
        const auto devkit_paths = resolve_project_paths(repo, "devkit_mini");
        const auto file = (tmp.path / "carrier.bin").string();
        compile_circuit_catalog(carrier_paths.subsystems_dir.string(), file);
        open_circuit_catalog(file);
        const auto before = record(lookup_circuit_catalog("som_j2"));
        const auto carrier = load_project_circuit(carrier_paths, "som_j2");
        const auto devkit = load_project_circuit(devkit_paths, "som_j2");
        require(record(carrier.circuit) != record(devkit.circuit), "devkit silently loaded carrier IR");
        require(circuit_catalog_count() == 37 && record(lookup_circuit_catalog("som_j2")) == before, "direct load changed process-global catalog");
    });
    suite.run("real projects with only JSON and no catalog", [&] {
        TempDir tmp;
        for (const std::string name : {"carrier", "devkit_mini"}) {
            const auto original = resolve_project_paths(repo, name);
            const auto expected = load_project_circuits(original);
            const auto copy = tmp.path / name;
            write(copy / "project.json", read(original.project_file));
            write(copy / "sheet_index.json", read(original.sheet_index_file));
            for (const auto& circuit : expected) write(copy / "subsystems" / circuit.name / "circuit.json", read(circuit.path));
            const auto paths = resolve_project_paths(tmp.path, name);
            require(load_project_config(paths).name == name, "JSON-only config failed");
            const auto inventory = inventory_project_circuits(paths);
            for (const auto& entry : inventory) require(!entry.authoring_path, "invented Python dependency");
            const auto actual = load_project_circuits(paths);
            require(actual.size() == expected.size(), "JSON-only inventory lost circuits");
            for (std::size_t i = 0; i < actual.size(); ++i) {
                require(record(actual[i].circuit) == record(expected[i].circuit), "JSON-only circuit changed");
            }
            require(!fs::exists(paths.part_catalog_file) && !fs::exists(paths.circuit_catalog_file), "direct loading created catalogs");
        }
    });
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: schgen_project_contracts REPOSITORY_ROOT");
        const auto repo = fs::absolute(argv[1]).lexically_normal();
        Suite suite;
        fixture_contracts(suite, repo);
        repository_contracts(suite, repo);
        std::cout << "project contracts: " << suite.passed << " passed, " << suite.failed << " failed\n";
        return suite.failed ? 1 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
