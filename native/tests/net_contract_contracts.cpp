#include "schgen/net_contract.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <spawn.h>
#include <sstream>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;
namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t assertions = 0, compiled_headers = 0, compiled_names = 0;
void require(bool ok, const std::string& message) {
    ++assertions;
    if (!ok) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    require(value != nullptr, "missing independent fixture field " + key);
    return *value;
}
std::string read(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "read " + path.string());
    return {std::istreambuf_iterator<char>(stream), {}};
}
void write(const fs::path& path, const std::string& bytes) {
    fs::create_directories(path.parent_path());
    std::ofstream stream(path, std::ios::binary); stream << bytes; stream.close();
    require(bool(stream), "write private test file " + path.string());
}
template<class F> void rejects(F action, const std::string& fragment) {
    bool caught = false;
    try { action(); } catch (const std::exception& error) {
        caught = true;
        require(std::string(error.what()).find(fragment) != std::string::npos,
                "unexpected rejection: " + std::string(error.what()));
    }
    require(caught, "expected rejection: " + fragment);
}
int run(std::vector<std::string> args) {
    std::vector<char*> argv;
    for (auto& arg : args) argv.push_back(arg.data());
    argv.push_back(nullptr);
    pid_t child = -1;
    const auto error = ::posix_spawnp(&child, args.front().c_str(), nullptr, nullptr, argv.data(), environ);
    require(error == 0, "required C++ compiler/program could not execute: " + args.front());
    int status = 0; pid_t waited;
    do { waited = ::waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    require(waited == child, "wait for compiler/program");
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}
using Rows = std::vector<NetContractEntry>;
Rows rows(const JsonNode& fixture) {
    Rows out;
    for (const auto& row : fixture.array_value)
        out.push_back({row.array_value.at(0).string_value, row.array_value.at(1).string_value});
    return out;
}
void same(const Rows& actual, const Rows& expected, const std::string& context) {
    require(actual.size() == expected.size(), context + ": omitted/extra names");
    for (std::size_t i = 0; i < actual.size(); ++i)
        require(actual[i].name == expected[i].name && actual[i].identifier == expected[i].identifier,
                context + ": identifier/original-name/order drift at " + std::to_string(i));
}
void compile_header(const std::string& header, const Rows& som, const Rows& rails,
                    const std::string& ns, const fs::path& scratch) {
    write(scratch / "nets.hpp", header);
    std::ostringstream main;
    main << "#include \"nets.hpp\"\n#include \"nets.hpp\"\n";
    const auto check = [&](const Rows& expected, const std::string& domain, const std::string& inventory) {
        main << "static_assert(" << ns << "::" << inventory << ".size() == " << expected.size() << ");\n";
        for (std::size_t i = 0; i < expected.size(); ++i) {
            const auto& entry = expected[i];
            const auto expression = ns + "::" + domain + "::" + entry.identifier;
            main << "static_assert(" << expression << ".size() == " << entry.name.size() << ");\n"
                 << "static_assert(" << ns << "::" << inventory << '[' << i << "] == " << expression << ");\n";
            // Independent numeric byte assertions, not the renderer's literal
            // escaping or parsed generated text. Check every original byte.
            for (std::size_t j = 0; j < entry.name.size(); ++j)
                main << "static_assert(static_cast<unsigned char>(" << expression << '[' << j << "]) == "
                     << static_cast<unsigned>(static_cast<unsigned char>(entry.name[j])) << ");\n";
            ++compiled_names;
        }
    };
    check(som, "SOM", "som_names"); check(rails, "RAILS", "rail_names");
    main << "const void* second_translation_unit();\nint main() { return second_translation_unit() == &"
         << ns << "::som_names ? 0 : 1; }\n";
    write(scratch / "main.cpp", main.str());
    write(scratch / "second.cpp", "#include \"nets.hpp\"\nconst void* second_translation_unit() { return &" + ns + "::som_names; }\n");
    const char* configured = std::getenv("CXX");
    const std::string compiler = configured && *configured ? configured : "c++";
    require(run({compiler, "-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-ffp-contract=off",
                 (scratch / "main.cpp").string(), (scratch / "second.cpp").string(), "-o", (scratch / "probe").string()}) == 0,
            "generated C++17 header failed strict compile/link");
    require(run({(scratch / "probe").string()}) == 0, "generated header ODR/multi-TU identity failed");
    ++compiled_headers;
}
void add_som(NetContractInput& input, const std::string& name) {
    if (input.som.connectors.empty()) input.som.connectors.push_back({"J1", {}});
    auto& pins = input.som.connectors.front().second.pins;
    pins.emplace_back(std::to_string(pins.size() + 1), name);
}
void live_project(const fs::path& repo, const fs::path& scratch, const JsonNode& fixtures, const std::string& name) {
    const auto paths = resolve_project_paths(repo, name);
    const auto input = load_net_contract_input(paths);
    const auto& reference = field(field(fixtures, "projects"), name);
    const auto som = rows(field(reference, "som")), rails = rows(field(reference, "rails"));
    const auto document = generate_net_contract_header(input);
    same(document.som, som, name + " original Python SOM");
    same(document.rails, rails, name + " original Python POWER + rails");
    require(document.header.find(".py") == std::string::npos, "generated Python deliverable");
    require(generate_net_contract_header(input).header == document.header, "repeat generation changed bytes");
    require(open_part_catalog(paths.part_catalog_file.string()), "open existing read-only part catalog");
    ProjectAuthoringInput authoring;
    authoring.project_root = paths.project_root; authoring.context = make_authoring_context(repo);
    NetContractInput authored; authored.som = input.som;
    for (const auto& factory : native_project_factories(name, authoring)) {
        authored.circuits.push_back(factory.circuit());
        require(authored.circuits.back().name == factory.name, "native constructor sheet identity");
    }
    require(authored.circuits.size() == input.circuits.size(), "native authoring/canonical sheet count");
    require(generate_net_contract_header(authored).header == document.header,
            "fresh native-authored IR differs from independently captured legacy net inventory");
    require(close_part_catalog(), "close read-only catalog after native authoring");
    auto reordered = input;
    std::reverse(reordered.circuits.begin(), reordered.circuits.end());
    std::reverse(reordered.som.connectors.begin(), reordered.som.connectors.end());
    for (auto& circuit : reordered.circuits) std::reverse(circuit.nets.begin(), circuit.nets.end());
    for (auto& connector : reordered.som.connectors) std::reverse(connector.second.pins.begin(), connector.second.pins.end());
    reordered.circuits.push_back(input.circuits.front());
    add_som(reordered, som.front().name);
    require(generate_net_contract_header(reordered).header == document.header, "order/duplicate changed inventory");
    compile_header(document.header, som, rails, "schgen_nets", scratch / name);
    const auto destination = scratch / name / "published/nets.hpp";
    require(write_net_contract_header(input, destination).header == document.header, "publisher returned different bytes");
    require(read(destination) == document.header, "published header differs");
    auto changed = input;
    changed.circuits.front().nets.push_back({"+NEW_RAIL", "power", {}});
    changed.circuits.front().nets.push_back({"+NOT_POWER", "signal", {}});
    changed.circuits.front().nets.push_back({"NO_PLUS", "power", {}});
    add_som(changed, "NEW_SOM_SIGNAL");
    const auto mutant = generate_net_contract_header(changed);
    auto expected_som = som, expected_rails = rails;
    expected_som.push_back({"NEW_SOM_SIGNAL", "NEW_SOM_SIGNAL"});
    expected_rails.push_back({"+NEW_RAIL", "PNEW_RAIL"});
    const auto order = [](const auto& a, const auto& b) { return a.name < b.name; };
    std::sort(expected_som.begin(), expected_som.end(), order);
    std::sort(expected_rails.begin(), expected_rails.end(), order);
    same(mutant.som, expected_som, "mutated live SOM"); same(mutant.rails, expected_rails, "mutated live rails");
    write_net_contract_header(changed, destination);
    require(read(destination) == mutant.header, "explicit replacement failed");
    compile_header(mutant.header, expected_som, expected_rails, "schgen_nets", scratch / (name + "-mutant"));
    // Read-only project loader consumes ONLY actual JSON: no constructors or
    // prebuilt catalog are copied into this private project mirror.
    auto isolated = paths;
    isolated.subsystems_dir = scratch / name / "json-only/subsystems";
    isolated.som_interface_file = scratch / name / "json-only/som_interface.json";
    for (const auto& source : inventory_project_circuits(paths))
        write(isolated.subsystems_dir / source.name / "circuit.json", read(source.path));
    write(isolated.som_interface_file, read(paths.som_interface_file));
    require(generate_net_contract_header(load_net_contract_input(isolated)).header == document.header,
            "Python-free canonical project changed inventory");
    fs::remove(isolated.som_interface_file);
    rejects([&] { load_net_contract_input(isolated); }, "som_interface");
    write(isolated.som_interface_file, "{bad json");
    rejects([&] { load_net_contract_input(isolated); }, "json");
}
void adversarial(const fs::path& scratch, const JsonNode& fixture) {
    const std::vector<std::string> expected{
        "net_empty", "P3V3", "net_x3556", "net_x5f7265736572766564", "net_x5f5f7265736572766564",
        "net_x636c617373", "net_x6f70657261746f72", "net_x74656d706c617465", "net_x616e64",
        "net_x636f5f6177616974", "A_B", "A_B", "A_B", "A_B", "net_x615f5f62",
        "net_xc2b5", "net_xc2b2", "net_xe4b8ade69687", "net_xc3a9", "net_x65cc81",
        "net_xf09f9099", "net_x00", "line_break", "net_x71756f7465225c656e64",
        "net_empty", "net_x636c617373", "net_x3f", "net_x2bc2b5", "net_xefbc9956",
        "Z_", "a_b", "net_x6e616d657370616365", "SOM", "RAILS", "net_x4e554c4c"};
    const auto& captured = field(fixture, "identifiers").array_value;
    require(captured.size() == expected.size(), "independent original-identifier coverage changed");
    NetContractInput input; Rows values;
    for (std::size_t i = 0; i < captured.size(); ++i) {
        const auto name = captured[i].array_value.at(0).string_value;
        require(net_contract_identifier(name) == expected[i], "reviewed C++ identifier differs for legacy edge " + std::to_string(i));
        // Distinct colliding originals are tested separately, never silently
        // accepted together. Compile one representative per reviewed identifier.
        if (std::none_of(values.begin(), values.end(), [&](const auto& row) { return row.identifier == expected[i]; })) {
            add_som(input, name); values.push_back({name, expected[i]});
        }
    }
    add_som(input, "std"); values.push_back({"std", "std"});
    // Include control bytes immediately followed by octal/hex digits, trigraph
    // spellings, and arbitrary UTF-8-independent byte data in literal values.
    const std::string bytes = std::string("n\001" "78\0A", 6) + static_cast<char>(255) + "\?\?/";
    add_som(input, bytes); values.push_back({bytes, "net_x6e0137380041ff3f3f2f"});
    std::sort(values.begin(), values.end(), [](const auto& a, const auto& b) {
        return std::lexicographical_compare(a.name.begin(), a.name.end(), b.name.begin(), b.name.end(),
            [](unsigned char x, unsigned char y) { return x < y; });
    });
    const auto result = generate_net_contract_header(input, "board::nets");
    same(result.som, values, "adversarial source bytes");
    compile_header(result.header, values, {}, "board::nets", scratch / "adversarial");
    const auto empty = generate_net_contract_header({});
    compile_header(empty.header, {}, {}, "schgen_nets", scratch / "empty");
    for (const std::string ns : {"", "::bad", "bad::", "bad::::x", "a;b", "a-b", "class", "std", "_private", "x::__bad", "a::std", "NULL"})
        rejects([&] { generate_net_contract_header({}, ns); }, "unsafe C++ namespace");
    const auto collision = [&](std::string a, std::string b, const std::string& domain) {
        NetContractInput changed;
        if (domain == "SOM") { add_som(changed, a); add_som(changed, b); }
        else { changed.circuits.emplace_back(); changed.circuits.front().nets = {{a, "power", {}}, {b, "power", {}}}; }
        const auto target = scratch / "collision.hpp"; write(target, "sentinel");
        rejects([&] { write_net_contract_header(changed, target); }, domain + " identifier collision");
        require(read(target) == "sentinel", "collision modified existing output");
    };
    collision("A-B", "A/B", "SOM"); collision("A B", "A_B", "SOM");
    collision("+3V3", "P3V3", "SOM");
    collision("class", "net_x636c617373", "SOM"); collision("", "net_empty", "SOM");
    collision("+A-B", "+A_B", "RAILS");
    NetContractInput shared; add_som(shared, "+3V3"); shared.circuits.emplace_back();
    shared.circuits.front().nets.push_back({"+3V3", "power", {}});
    const auto overlap = generate_net_contract_header(shared);
    require(overlap.som.size() == 1 && overlap.rails.size() == 1, "separate domains incorrectly collide");
    rejects([&] { write_net_contract_header({}, scratch / "nets.py"); }, "C++ header");
    require(!fs::exists(scratch / "nets.py"), "Python output created");
    const auto link = scratch / "link.hpp", target = scratch / "target.hpp";
    write(target, "preserve"); fs::create_symlink(target, link);
    rejects([&] { write_net_contract_header({}, link); }, "refuse symlink");
    require(read(target) == "preserve" && fs::is_symlink(link), "symlink publication altered target");
    fs::create_directory(scratch / "directory.hpp");
    rejects([&] { write_net_contract_header({}, scratch / "directory.hpp"); }, "non-file");
    rejects([&] { write_net_contract_header({}, scratch / "not-created/nets.hpp", "bad::"); }, "unsafe C++ namespace");
    require(!fs::exists(scratch / "not-created"), "invalid namespace created output directories");
    const auto file_parent = scratch / "file-parent"; write(file_parent, "retain");
    bool io_failed = false;
    try { write_net_contract_header({}, file_parent / "nets.hpp"); }
    catch (const fs::filesystem_error& error) {
        io_failed = true;
        require(error.code() == std::errc::not_a_directory || error.code() == std::errc::file_exists,
                "non-directory output parent raised an unrelated I/O error");
    }
    require(io_failed, "non-directory output parent must fail publication");
    require(read(file_parent) == "retain", "I/O failure damaged existing parent");
}
} // namespace
int main(int argc, char** argv) {
    try {
        require(argc == 3, "usage: net_contract_contracts REPOSITORY PRIVATE_SCRATCH");
        const auto repo = fs::absolute(argv[1]), scratch_root = fs::absolute(argv[2]);
        fs::create_directories(scratch_root);
        auto pattern = (scratch_root / "run-XXXXXX").string();
        const char* created = ::mkdtemp(pattern.data());
        require(created != nullptr, "allocate unique private test scratch");
        const fs::path scratch = created;
        const auto fixture = parse_json_file((repo / "native/tests/data/net_contract/legacy_reference.json").string());
        live_project(repo, scratch, fixture, "carrier"); live_project(repo, scratch, fixture, "devkit_mini");
        adversarial(scratch, fixture);
        std::cout << "PASS: " << assertions << " native net-contract assertions; " << compiled_headers
                  << " strict C++17 two-TU headers executed; " << compiled_names << " names checked byte-for-byte\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
