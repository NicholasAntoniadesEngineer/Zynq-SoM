// Complete symbol-library contracts; no Python, catalogs or board generation.
// Usage: symbols_contracts <repository> [--installed]
#include "schgen/symbols.hpp"
#include "schgen/circuit.hpp"
#include "schgen/json.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <string>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using schgen::JsonKind;
using schgen::JsonNode;
using schgen::Sexpr;
using schgen::SexprList;
using schgen::SymbolLibrary;

std::size_t checks = 0;
void require(bool condition, const std::string& message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
template <typename F>
void rejects(F action, const std::string& expected) {
    try { action(); }
    catch (const schgen::SymbolError& error) {
        require(std::string(error.what()).find(expected) != std::string::npos,
                "wrong SymbolError: " + std::string(error.what()));
        return;
    }
    throw std::runtime_error("expected SymbolError: " + expected);
}
struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen-symbols-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = fs::canonical(pattern);
    }
    ~TempDir() { std::error_code error; fs::remove_all(path, error); }
};
void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream stream(path, std::ios::binary);
    stream << text;
    stream.close();
    require(bool(stream), "cannot write temporary fixture");
}
const JsonNode& field(const JsonNode& node, const std::string& name) {
    const auto* out = schgen::object_field(node, name);
    require(out != nullptr, "missing golden field " + name);
    return *out;
}
double num(const JsonNode& node) {
    require(node.kind == JsonKind::Number, "expected golden number");
    return node.number_value;
}
std::string str(const JsonNode& node) {
    require(node.kind == JsonKind::String, "expected golden string");
    return node.string_value;
}
bool boolean(const JsonNode& node) {
    require(node.kind == JsonKind::Bool, "expected golden bool");
    return node.bool_value;
}
const SexprList& list(const Sexpr& node) { return std::get<SexprList>(node.v); }
std::string tag(const Sexpr& node) {
    if (!std::holds_alternative<SexprList>(node.v) || list(node).empty()) return "";
    const auto* sym = std::get_if<Sexpr::Sym>(&list(node)[0].v);
    return sym ? sym->name : "";
}
std::string property(const Sexpr& node, const std::string& key) {
    for (const auto& child : list(node)) {
        if (tag(child) == "property" && std::get<std::string>(list(child)[1].v) == key)
            return std::get<std::string>(list(child)[2].v);
    }
    throw std::runtime_error("missing property " + key);
}
std::string fingerprint(const std::string& text) {
    std::uint64_t value = UINT64_C(14695981039346656037);
    for (const unsigned char byte : text) value = (value ^ byte) * UINT64_C(1099511628211);
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << value;
    return out.str();
}

void synthetic_contracts(const fs::path& data) {
    SymbolLibrary library(std::vector<fs::path>{data});
    const auto& mixed = library.get("SymbolContracts:Mixed");
    require(mixed.pins.size() == 3 && mixed.pins[0].name == "nested"
            && mixed.pins[1].name == "child" && mixed.pins[2].name == "top", "pin traversal order");
    require(mixed.pins[0].number == "10" && mixed.pins[0].rotation == 270
            && mixed.pins[1].rotation == 90, "numeric pin number / truncating rotation");
    require(mixed.pins[0].hidden && mixed.pins[1].hidden && !mixed.pins[2].hidden,
            "pin hide syntax differs from Python");
    require(mixed.pin_names_hidden && mixed.pin_numbers_hidden, "symbol hide forms");
    require(mixed.body == std::array<double, 4>{-9, -8, 11, 7}, "primitive body union");
    require(library.pin_numbers("SymbolContracts:Mixed") == std::set<std::string>{"10", "2"},
            "pin_numbers must deduplicate common/alternate numbers");
    require(library.get("SymbolContracts:PinOnly").body ==
            std::array<double, 4>{-2.54, -1.27, 5.08, 3.81}, "pin-only bounds");
    require(library.get("SymbolContracts:Empty").body == std::array<double, 4>{}, "empty bounds");
    require(library.get("SymbolContracts:ArcBounds").body ==
            std::array<double, 4>{1, 2, 5, 6}, "arc control-point bounds");
    const auto& defaults = library.get("SymbolContracts:Defaults");
    require(defaults.pins.size() == 1 && defaults.pins[0].x == 0 && defaults.pins[0].y == 0
            && defaults.pins[0].length == 2.54 && defaults.pins[0].etype == "passive"
            && defaults.pins[0].number.empty() && defaults.pins[0].name.empty()
            && !defaults.pins[0].hidden && !defaults.pin_names_hidden
            && !defaults.pin_numbers_hidden, "optional pin metadata defaults");
    require(library.get("SymbolContracts:BarePinHide").pins[0].hidden
            && !library.get("SymbolContracts:EmptyPinHide").pins[0].hidden, "bare vs empty hide");
    const auto& numeric = library.get("SymbolContracts:NumericQuotes").pins[0];
    require(numeric.number == "1.123456789" && numeric.name == "1e-08" && numeric.x == 1.27
            && numeric.y == -2.54 && numeric.rotation == 270 && numeric.length == 0
            && numeric.hidden, "numeric atom precision / quoted coordinate and hide semantics");
    library.get("SymbolContracts:GridInside");
    rejects([&] { library.get("SymbolContracts:GridOutside"); }, "OFF-GRID");
    rejects([&] { library.get("SymbolContracts:OffGrid"); }, "SymbolContracts:OffGrid pin 1");
    rejects([&] { library.get("SymbolContracts:BrokenAt"); }, "missing coordinate");
    rejects([&] { library.get("SymbolContracts:Nonfinite"); }, "finite");
    rejects([&] { library.get("SymbolContracts:NotThere"); }, "symbol 'NotThere' not in SymbolContracts");
    rejects([&] { library.get("Missing:FOO"); }, "library 'Missing' not found");
    rejects([&] { library.get("SymbolContracts"); }, "symbol '' not in SymbolContracts");
    require(!schgen::symbol_on_grid(std::numeric_limits<double>::infinity())
            && !schgen::symbol_on_grid(std::numeric_limits<double>::quiet_NaN()), "nonfinite grid");
    require(&library.get("SymbolContracts:Mixed") == &mixed, "definition cache/reference stability");
    schgen::SymbolPin rounding_pin;
    rounding_pin.x = -3.81;
    rounding_pin.y = 5.08;
    // Python adds the anchor AFTER the rotated local coordinate. Reassociating
    // those expressions crosses the four-place rounding boundary in Release.
    require(schgen::pin_page_position(rounding_pin, -0.00005, 0.00015, -30)
            == std::pair<double, double>{1.2699, -8.8899}, "pin transform expression grouping");
}

void inheritance_contracts(const fs::path& data, SymbolLibrary& real) {
    SymbolLibrary library(std::vector<fs::path>{data});
    const auto& base = library.get("SymbolContracts:Base");
    const auto original = schgen::sexpr_dumps(base.raw);
    const auto& child = library.get("SymbolContracts:Child");
    const auto& grandchild = library.get("SymbolContracts:Grandchild");
    require(child.body == base.body && child.pins.size() == 3 && grandchild.pins.size() == 3,
            "inherited graphics/pins/alternate units lost");
    require(child.pin_names_hidden && child.pin_numbers_hidden, "visibility inheritance");
    require(property(child.raw, "Value") == "Child" && property(child.raw, "Custom") == "inherited"
            && property(child.raw, "Added") == "new", "child property merge");
    require(property(grandchild.raw, "Value") == "Grandchild" && property(grandchild.raw, "Custom").empty()
            && property(grandchild.raw, "Added") == "new", "multi-level/empty property override");
    for (const auto& item : list(grandchild.raw)) {
        require(tag(item) != "extends", "flattened symbol still references external parent");
        if (tag(item) == "symbol") {
            require(std::get<std::string>(list(item)[1].v).find("Grandchild_") == 0,
                    "inherited unit name not flattened");
        }
    }
    require(schgen::sexpr_dumps(base.raw) == original, "flattening mutated shared base");
    for (const auto* name : {"CycleA", "CycleB", "SelfCycle"}) {
        rejects([&] { library.get(std::string("SymbolContracts:") + name); }, "inheritance cycle");
    }
    rejects([&] { library.get("SymbolContracts:MissingParent"); }, "symbol 'Absent' not in SymbolContracts");
    rejects([&] { library.get("SymbolContracts:DerivedDrawing"); }, "cannot override pins or graphics");
    rejects([] { schgen::parse_symbol("bad", schgen::sexpr_loads("(symbol X (extends Y))")); },
            "unresolved extends");
    const auto& upstream = real.get("74xGxx:74AHC1G08");
    const auto& upstream_base = real.get("74xGxx:74LVC1G08");
    require(upstream.pins.size() == 5 && upstream.body == upstream_base.body,
            "actual KiCad extends did not inherit physical symbol");
    require(property(upstream.raw, "Value") == "74AHC1G08", "actual KiCad value override lost");
}

std::string mini(const std::string& name, const std::string& pin = "1", const std::string& x = "1.27") {
    return "(kicad_symbol_lib (symbol \"" + name
        + "\" (pin passive line (at " + x + " 0) (number \"" + pin + "\"))))";
}
void cache_and_lookup_contracts() {
    TempDir tmp;
    const auto a = tmp.path / "first";
    const auto b = tmp.path / "second";
    const auto source = a / "FOO.kicad_sym";
    write(source, mini("FOO", "FLAT"));
    write(a / "FOO/FOO.kicad_sym", mini("FOO", "NESTED"));
    write(b / "FOO.kicad_sym", mini("FOO", "SECOND"));
    SymbolLibrary first(std::vector<fs::path>{a, b});
    require(first.get("FOO:FOO").pins[0].number == "FLAT", "flat path priority");
    SymbolLibrary second(std::vector<fs::path>{b, a});
    require(second.get("FOO:FOO").pins[0].number == "SECOND", "extra path priority");
    SymbolLibrary only_nested(std::vector<fs::path>{a / "FOO"});
    require(only_nested.get("FOO:FOO").pins[0].number == "NESTED", "explicit directory lookup");
    write(a / "NEST/NEST.kicad_sym", mini("NEST"));
    require(first.get("NEST:NEST").pins.size() == 1, "nested generated library lookup");
    schgen::clear_symbol_file_cache();
    const auto cached = schgen::load_symbol_library_file(source);
    fs::create_symlink(source, tmp.path / "alias.kicad_sym");
    require(cached == schgen::load_symbol_library_file(tmp.path / "alias.kicad_sym"),
            "canonical path cache does not share parses");
    std::vector<std::future<std::shared_ptr<const Sexpr>>> workers;
    for (int i = 0; i < 4; ++i) {
        workers.push_back(std::async(std::launch::async, [&] { return schgen::load_symbol_library_file(source); }));
    }
    for (auto& worker : workers) require(worker.get() == cached, "concurrent shared parse differs");
    const auto before = fs::last_write_time(source);
    write(source, mini("FOO", "FLAT", "2.54"));
    fs::last_write_time(source, before + std::chrono::nanoseconds(1));
    const auto reparsed = schgen::load_symbol_library_file(source);
    require(reparsed != cached, "nanosecond mtime change did not reparse");
    require(first.get("FOO:FOO").pins[0].x == 1.27, "existing Library snapshot changed");
    SymbolLibrary fresh(std::vector<fs::path>{a});
    require(fresh.get("FOO:FOO").pins[0].x == 2.54, "new Library missed changed file");
    first.clear();
    require(first.get("FOO:FOO").pins[0].x == 2.54, "Library clear failed to reload");
    const auto timestamp = fs::last_write_time(source);
    write(source, mini("FOO", "LONGER_NUMBER", "2.54"));
    fs::last_write_time(source, timestamp);
    require(schgen::load_symbol_library_file(source) != reparsed, "size-only change did not reparse");
    write(a / "Broken.kicad_sym", "(kicad_symbol_lib (symbol");
    rejects([&] { fresh.get("Broken:X"); }, "sexpr:");
    write(a / "Broken.kicad_sym", mini("X"));
    require(fresh.get("Broken:X").pins.size() == 1, "failed parse poisoned cache");
    write(a / "Wrong.kicad_sym", "(footprint X)");
    rejects([&] { fresh.get("Wrong:X"); }, "expected kicad_symbol_lib");
    rejects([&] { schgen::load_symbol_library_file(a / "absent"); }, "symbol library");
    const auto paths = schgen::symbol_search_paths(tmp.path, {a, b});
    require(paths[0] == a && paths[1] == b && paths[paths.size() - 2] == tmp.path / "schgen/lib"
            && paths.back() == tmp.path / "parts", "repository/extra search paths changed");
}

void power_contracts(SymbolLibrary& real) {
    const auto original = schgen::sexpr_dumps(real.get("schgen:+5V_USB").raw);
    const auto& dynamic = real.get("schgen:+NATIVE_TEST_RAIL");
    require(dynamic.pins.size() == 1 && dynamic.pins[0].name == "+NATIVE_TEST_RAIL"
            && property(dynamic.raw, "Value") == "+NATIVE_TEST_RAIL", "power synthesis failed");
    require(schgen::sexpr_dumps(dynamic.raw).find("+5V_USB") == std::string::npos,
            "template strings not fully substituted");
    require(schgen::sexpr_dumps(real.get("schgen:+5V_USB").raw) == original,
            "power synthesis mutated template");
    rejects([&] { real.get("schgen:NOT_A_RAIL"); }, "symbol 'NOT_A_RAIL' not in schgen");
    TempDir tmp;
    write(tmp.path / "schgen.kicad_sym", "(kicad_symbol_lib)");
    SymbolLibrary empty(std::vector<fs::path>{tmp.path});
    rejects([&] { empty.get("schgen:+MISSING"); }, "rail template '+5V_USB' missing");
    write(tmp.path / "schgen.kicad_sym",
          "(kicad_symbol_lib (symbol \"+5V_USB\" (bare +5V_USB) (property \"Value\" \"+5V_USB\")))");
    empty.clear();
    const auto out = schgen::sexpr_dumps(empty.get("schgen:+NEW").raw);
    require(out.find("(bare +5V_USB)") != std::string::npos
            && out.find("\"+NEW\"") != std::string::npos, "bare Sym atoms were substituted");
    write(tmp.path / "schgen.kicad_sym",
        "(kicad_symbol_lib (symbol \"Root\" (pin power_in line (at 0 0) (number \"1\")))"
        " (symbol \"+5V_USB\" (extends \"Root\") (property \"Value\" \"+5V_USB\")))");
    empty.clear();
    require(empty.get("schgen:+INHERITED_RAIL").pins.size() == 1,
            "synthesized rail did not flatten inherited template");
}

void golden_contracts(SymbolLibrary& library, const JsonNode& golden) {
    const auto& anchor = field(golden, "anchor").array_value;
    const auto& rotations = field(golden, "rotations").array_value;
    std::size_t pin_count = 0;
    for (const auto& record : field(golden, "symbols").array_value) {
        const auto id = str(field(record, "lib_id"));
        const auto& actual = library.get(id);
        require(actual.lib_id == id, id + ": identity");
        require(actual.pin_names_hidden == boolean(field(record, "pin_names_hidden"))
                && actual.pin_numbers_hidden == boolean(field(record, "pin_numbers_hidden")), id + ": visibility");
        const auto& body = field(record, "body").array_value;
        for (std::size_t i = 0; i < 4; ++i) require(actual.body[i] == num(body[i]), id + ": body coordinate");
        const auto raw = schgen::sexpr_dumps(actual.raw);
        require(fingerprint(raw) == str(field(record, "raw_fnv1a64"))
                && raw.size() == num(field(record, "raw_bytes")), id + ": raw expression changed");
        const auto& pins = field(record, "pins").array_value;
        require(actual.pins.size() == pins.size(), id + ": pin count");
        std::set<std::string> numbers;
        for (std::size_t i = 0; i < pins.size(); ++i) {
            const auto& p = actual.pins[i];
            const auto& g = pins[i].array_value;
            const auto context = id + ": pin[" + std::to_string(i) + "] " + p.number;
            require(p.number == str(g[0]) && p.name == str(g[1]) && p.etype == str(g[2])
                    && p.x == num(g[3]) && p.y == num(g[4]) && p.rotation == num(g[5])
                    && p.length == num(g[6]) && p.hidden == boolean(g[7]), context + " metadata/order");
            numbers.insert(p.number);
            const auto& positions = field(record, "pin_positions").array_value[i].array_value;
            for (std::size_t r = 0; r < rotations.size(); ++r) {
                const auto point = schgen::pin_page_position(p, num(anchor[0]), num(anchor[1]),
                                                            static_cast<int>(num(rotations[r])));
                require(point.first == num(positions[2 * r]) && point.second == num(positions[2 * r + 1]),
                        context + " page transform " + std::to_string(r));
            }
        }
        require(library.pin_numbers(id) == numbers, id + ": pin_numbers set");
        pin_count += pins.size();
        const auto& bodies = field(record, "body_positions").array_value;
        for (std::size_t r = 0; r < rotations.size(); ++r) {
            const auto box = schgen::symbol_body_box_page(actual, num(anchor[0]), num(anchor[1]),
                                                         static_cast<int>(num(rotations[r])));
            for (std::size_t i = 0; i < 4; ++i) require(box[i] == num(bodies[r].array_value[i]), id + ": page body");
        }
    }
    for (const auto& entry : field(golden, "geometry_cases").array_value) {
        const auto& v = entry.array_value;
        schgen::SymbolPin pin;
        pin.x = num(v[0]); pin.y = num(v[1]);
        const auto point = schgen::pin_page_position(pin, num(v[2]), num(v[3]), static_cast<int>(num(v[4])));
        require(point.first == num(v[5]) && point.second == num(v[6]), "rounding/noncardinal pin transform");
        const auto body_point = schgen::sch_xform(pin.x, pin.y, num(v[2]), num(v[3]), static_cast<int>(num(v[4])));
        require(body_point.first == num(v[7]) && body_point.second == num(v[8]), "rounding body transform");
    }
    std::cout << field(golden, "symbols").array_value.size() << " symbols / " << pin_count
              << " pin records match frozen Python metadata, raw expressions and transforms\n";
}

void circuit_contracts(SymbolLibrary& library, const fs::path& repo) {
    std::set<std::string> ids;
    std::size_t circuits = 0, parts = 0;
    for (const auto* project : {"carrier", "devkit_mini"}) {
        std::vector<fs::path> paths;
        for (const auto& folder : fs::directory_iterator(repo / project / "subsystems")) {
            if (fs::is_regular_file(folder.path() / "circuit.json")) paths.push_back(folder.path() / "circuit.json");
        }
        std::sort(paths.begin(), paths.end());
        for (const auto& path : paths) {
            const auto circuit = schgen::load_circuit_json(path);
            ++circuits;
            for (const auto& part : circuit.parts) {
                ids.insert(part.lib_id);
                ++parts;
                const auto numbers = library.pin_numbers(part.lib_id);
                std::set<std::string> assigned;
                for (const auto& net : circuit.nets) {
                    for (const auto& pin : net.pins) if (pin.ref == part.ref) assigned.insert(pin.pin);
                }
                for (const auto& pin : circuit.nc) if (pin.ref == part.ref) assigned.insert(pin.pin);
                require(assigned == numbers, std::string(project) + ":" + circuit.name + ":" + part.ref
                        + " symbol pin completeness mismatch (" + part.lib_id + ")");
                if (!part.pin_numbers.empty()) {
                    require(std::set<std::string>(part.pin_numbers.begin(), part.pin_numbers.end()) == numbers,
                            circuit.name + ":" + part.ref + " expanded IR pin table drift");
                }
            }
        }
    }
    require(circuits > 0 && parts > 0 && !ids.empty(), "real-project inventory is empty");
    std::cout << circuits << " circuits / " << parts << " parts / " << ids.size()
              << " library IDs pass native symbol pin completeness\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2 || (argc == 3 && std::string(argv[2]) == "--installed"),
                "usage: symbols_contracts <repository> [--installed]");
        const fs::path repo = fs::canonical(argv[1]);
        const auto data = repo / "native/tests/data/symbols";
        SymbolLibrary library = argc == 3 ? SymbolLibrary(repo) : SymbolLibrary(
            std::vector<fs::path>{data / "kicad", repo / "schgen/lib", repo / "parts"});
        const auto golden = schgen::parse_json_file((data / "python_metadata.json").string());
        require(str(field(golden, "schema")) == "schgen.symbols.python_baseline/1", "wrong baseline schema");
        synthetic_contracts(data);
        cache_and_lookup_contracts();
        inheritance_contracts(data, library);
        power_contracts(library);
        golden_contracts(library, golden);
        circuit_contracts(library, repo);
        std::cout << "symbols contracts passed (" << checks << " checks; "
                  << (argc == 3 ? "installed KiCad" : "frozen KiCad fixtures") << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
