#include "schgen/subsystem_scaffold.hpp"
#include "schgen/subsystem_registration.hpp"
#include "schgen/subsystem_package_checks.hpp"

#include <algorithm>
#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <sys/resource.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t assertions = 0;
void require(bool condition, const std::string& message) {
    ++assertions;
    if (!condition) throw std::runtime_error(message);
}
template<class F> void rejects(F action, const std::string& message) {
    bool failed = false;
    try { action(); } catch (const std::exception&) { failed = true; }
    require(failed, message);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "schgen-scaffold-contracts-XXXXXX").string();
        const auto created = ::mkdtemp(pattern.data());
        require(created != nullptr, "allocate private scratch");
        path = created;
    }
    ~Scratch() { std::error_code ignored; fs::remove_all(path, ignored); }
};
std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    require(bool(in), "read " + file.string());
    return {std::istreambuf_iterator<char>(in), {}};
}
void write(const fs::path& file, const std::string& text) {
    std::ofstream out(file, std::ios::binary);
    out << text;
    out.close();
    require(bool(out), "write private fixture");
}
std::set<std::string> children(const fs::path& path) {
    std::set<std::string> names;
    for (const auto& entry : fs::directory_iterator(path)) names.insert(entry.path().filename().string());
    return names;
}
const std::string& file(const SubsystemScaffold& rendered, const std::string& name) {
    for (const auto& entry : rendered.files) if (entry.name == name) return entry.contents;
    throw std::runtime_error("missing rendered file: " + name);
}
void rendering(const fs::path& repo) {
    const auto rendered = render_subsystem_scaffold("widget");
    require(rendered.name == "widget" && rendered.files.size() == 7, "native package shape");
    std::set<std::string> names;
    for (const auto& entry : rendered.files) {
        require(names.insert(entry.name).second, "unique native asset");
        require(!entry.contents.empty() && entry.contents.back() == '\n', "complete text file");
        require(entry.contents.find("@NAME@") == std::string::npos, "unexpanded placeholder");
        require(fs::path(entry.name).extension() != ".py", "no generated Python");
    }
    require(names == std::set<std::string>{"CMakeLists.txt", "README.md", "subsystem.json",
        "widget.hpp", "widget.cpp", "widget.cir", "test_widget.cpp"}, "exact package files");
    const auto reference = parse_json_file((repo / "native/tests/data/subsystem_scaffold/python_reference.json").string());
    auto expected_spice = object_field(reference, "widget_cir")->string_value;
    const auto source = expected_spice.find("widget.py");
    require(source != std::string::npos, "independent Python SPICE reference");
    expected_spice.replace(source, 9, "widget.cpp");
    require(file(rendered, "widget.cir") == expected_spice, "SPICE bytes differ beyond source extension migration");
    const auto metadata = parse_json_text(file(rendered, "subsystem.json"));
    require(object_field(metadata, "name")->string_value == "widget", "metadata name");
    require(object_field(metadata, "default_meta")->object_value.size() == 4, "four metadata channels");
    require(file(rendered, "widget.cpp").find("return meta.finish(c)") != std::string::npos, "live metadata builder");
    require(file(rendered, "widget.cpp").find("fill in the widget netlist") != std::string::npos, "unimplemented fails closed");
    require(file(rendered, "test_widget.cpp").find("subsystem_definition(\"widget\")") != std::string::npos,
            "generated test exercises configured registry");
    require(file(rendered, "CMakeLists.txt").find("schgen_register_subsystem_package(widget)") != std::string::npos,
            "explicit build registration");
    const auto again = render_subsystem_scaffold("widget");
    for (const auto& entry : rendered.files) require(file(again, entry.name) == entry.contents, "deterministic renderer");
    for (const auto& name : std::vector<std::string>{"", ".", "..", "../widget", "a/b", "a\\b", "A", "_a", "a__b",
            "bad-name", "has space", "9a", "foo;bar", "foo\nbar", "foo\"bar", "é", "con", "nul", "aux", "prn", "com9", "lpt1",
            std::string(64, 'a'), std::string("a\0b", 3)})
        rejects([&] { (void)render_subsystem_scaffold(name); }, "unsafe native package name accepted");
    for (const auto& name : {"a", "widget2", "class", "a_b", "a_", "com0"})
        require(render_subsystem_scaffold(name).name == name, "valid native name rejected");
    require(render_subsystem_scaffold(std::string(63, 'a')).name.size() == 63, "maximum identifier boundary");
}
void publication() {
    Scratch scratch;
    const auto root = scratch.path / "library with spaces";
    fs::create_directory(root);
    const auto before = children(scratch.path);
    (void)render_subsystem_scaffold("widget");
    require(children(scratch.path) == before && children(root).empty(), "rendering wrote source");
    const auto result = scaffold_subsystem(root, "widget");
    const auto rendered = render_subsystem_scaffold("widget");
    require(result.package == root / "widget", "published path");
    require(children(root) == std::set<std::string>{"widget"}, "staging directory leaked");
    require(children(result.package).size() == 7, "partial package publication");
    for (const auto& entry : rendered.files) require(read(result.package / entry.name) == entry.contents, "published bytes");
    require(subsystem_scaffold_summary(result).find("-DSCHGEN_SUBSYSTEM_PACKAGES=widget") != std::string::npos,
            "native next-step guidance");
    write(result.package / "widget.cpp", "USER AUTHORED\n");
    write(result.package / "custom.asset", "USER ASSET\n");
    const auto owned = children(result.package);
    rejects([&] { scaffold_subsystem(root, "widget"); }, "existing user package overwritten");
    require(children(result.package) == owned && read(result.package / "widget.cpp") == "USER AUTHORED\n" &&
            read(result.package / "custom.asset") == "USER ASSET\n", "collision touched user package");
    fs::create_directory(root / "empty");
    rejects([&] { scaffold_subsystem(root, "empty"); }, "empty directory overwritten");
    require(children(root / "empty").empty(), "empty collision touched");
    write(root / "regular", "EXISTING FILE\n");
    rejects([&] { scaffold_subsystem(root, "regular"); }, "file collision accepted");
    require(read(root / "regular") == "EXISTING FILE\n", "file collision touched");
    fs::create_directory_symlink(result.package, root / "linked");
    fs::create_symlink(scratch.path / "absent", root / "dangling");
    for (const auto* name : {"linked", "dangling"}) {
        const auto target = fs::read_symlink(root / name);
        rejects([&] { scaffold_subsystem(root, name); }, "symlink collision accepted");
        require(fs::read_symlink(root / name) == target, "symlink replaced");
    }
    fs::create_directory_symlink(root, scratch.path / "root_link");
    rejects([&] { scaffold_subsystem(scratch.path / "root_link", "escape"); }, "root symlink followed");
    rejects([&] { scaffold_subsystem(scratch.path / "root_link" / "", "escape"); }, "trailing slash bypassed root nofollow");
    rejects([&] { scaffold_subsystem(scratch.path / "absent", "widget"); }, "implicit root creation");
    rejects([&] { scaffold_subsystem(root, "../escape"); }, "traversal accepted");
    require(!fs::exists(root / "escape") && !fs::exists(scratch.path / "absent"), "unsafe call touched outside package");

    std::atomic<unsigned> winners{0}, collisions{0}, ready{0};
    std::atomic<bool> start{false};
    std::vector<std::thread> workers;
    for (unsigned i = 0; i < 16; ++i) workers.emplace_back([&] {
        ++ready;
        while (!start.load()) std::this_thread::yield();
        try { scaffold_subsystem(root, "race"); ++winners; }
        catch (const std::exception& error) {
            if (std::string(error.what()).find("already exists") != std::string::npos) ++collisions;
        }
    });
    while (ready.load() != 16) std::this_thread::yield();
    start = true;
    for (auto& worker : workers) worker.join();
    require(winners == 1 && collisions == 15, "concurrent no-replace publication");
    for (const auto& entry : render_subsystem_scaffold("race").files)
        require(read(root / "race" / entry.name) == entry.contents, "racing publisher changed winner");

    // Fault injection in a child: interrupt a real staged file write after one
    // byte. No test hook or production failure bypass is needed.
    const auto saved = children(root);
    const auto pid = ::fork();
    require(pid >= 0, "fork write-failure contract");
    if (pid == 0) {
        std::signal(SIGXFSZ, SIG_IGN);
        const rlimit limit{1, 1};
        if (::setrlimit(RLIMIT_FSIZE, &limit) != 0) ::_exit(3);
        try { scaffold_subsystem(root, "write_failure"); } catch (const std::exception&) { ::_exit(0); }
        ::_exit(2);
    }
    int status = 0;
    require(::waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0, "write failure not rejected");
    require(children(root) == saved, "failed publication leaked/changed files");
}
SymbolDef symbol(const std::string& name, const std::vector<std::array<std::string, 3>>& pins) {
    SymbolDef out;
    out.lib_id = name;
    for (const auto& pin : pins) { SymbolPin p; p.number = pin[0]; p.name = pin[1]; p.etype = pin[2]; out.pins.push_back(p); }
    return out;
}
SubsystemDefinition electrical(int mutation = 0) {
    return {"widget", {"+VDD", "GND"}, [mutation](const SubsystemMeta& meta, const AuthoringContext& context) {
        CircuitAuthor c("widget", "widget", context);
        c.part("U1", "Test:IC", "IC");
        if (mutation != 1) c.part("C1", "Device:C", "100n");
        c.net("+VDD", {"U1.1"});
        c.net("GND", {"U1.2"});
        if (mutation != 1) { c.net("+VDD", {"C1.1"}); c.net("GND", {"C1.2"}); }
        c.net(mutation == 2 ? "+VDD" : "GND", {"U1.3"});
        if (mutation == 3) {
            c.part("R1", "Device:R", "10k");
            c.net("FLOAT", {"U1.4", "R1.1"});
            c.nc({"R1.2"});
        } else if (mutation != 4) c.net("GND", {"U1.4"});
        return mutation == 5 ? c.finish() : meta.finish(c);
    }};
}
void local_checks() {
    const std::vector<SymbolDef> symbols{
        symbol("Test:IC", {{"1", "VDD", "power_in"}, {"2", "GND", "power_in"},
                           {"3", "EP", "power_in"}, {"4", "MODE", "input"}}),
        symbol("Device:C", {{"1", "1", "passive"}, {"2", "2", "passive"}}),
        symbol("Device:R", {{"1", "1", "passive"}, {"2", "2", "passive"}})};
    const auto resolve = [&](const std::string& lib) -> const SymbolDef& {
        for (const auto& entry : symbols) if (entry.lib_id == lib) return entry;
        throw std::runtime_error("missing symbol");
    };
    const auto good = check_subsystem_local(electrical(), {}, resolve);
    require(good.ok(), good.summary());
    require(good.design_rules.checked.front().second == 1, "live IC supply checked");
    const auto decap = check_subsystem_local(electrical(1), {}, resolve);
    require(!decap.ok() && decap.design_rules.decap.size() == 1, "decap mutation undetected");
    const auto ep = check_subsystem_local(electrical(2), {}, resolve);
    require(!ep.ok() && ep.design_rules.ep.size() == 1, "exposed-pad mutation undetected");
    const auto strap = check_subsystem_local(electrical(3), {}, resolve);
    require(!strap.ok() && strap.design_rules.strap.size() == 1, "floating strap mutation undetected");
    require(!check_subsystem_local(electrical(4), {}, resolve).ok(), "unassigned pin passed");
    const auto ignored_meta = check_subsystem_local(electrical(5), {}, resolve);
    require(!ignored_meta.ok() && ignored_meta.errors.size() == 2, "metadata ignored without failing both bind checks");
    auto def = electrical();
    def.interface.push_back("MISSING");
    require(!check_subsystem_local(def, {}, resolve).ok(), "interface drift passed");
    def = electrical(); def.interface.push_back("GND");
    require(!check_subsystem_local(def, {}, resolve).ok(), "duplicate interface passed");
    def = electrical(); def.circuit = {};
    require(!check_subsystem_local(def, {}, resolve).ok(), "missing factory passed");
    def.circuit = [](const SubsystemMeta&, const AuthoringContext&) -> CircuitSheetIr {
        throw CircuitAuthoringError("fill in the widget netlist");
    };
    require(!check_subsystem_local(def, {}, resolve).ok(), "unimplemented stub passed");
    def.circuit = [](const SubsystemMeta&, const AuthoringContext&) { return CircuitAuthor("widget").finish(); };
    def.interface.clear();
    require(!check_subsystem_local(def, {}, resolve).ok(), "empty implementation passed");
    require(!check_subsystem_local(electrical(), {}, [](const auto&) -> const SymbolDef& {
        throw SymbolError("unavailable live symbol");
    }).ok(), "unresolved symbols silently skipped");
    auto no_pins = symbols.front(); no_pins.pins.clear();
    require(!check_subsystem_local(electrical(), {}, [&](const auto&) -> const SymbolDef& { return no_pins; }).ok(),
            "empty pin resolver passed");
    auto policy = good;
    policy.design_rules.i2c.push_back("board-side pullup needed");
    policy.design_rules.reset.push_back("board-side RC needed");
    require(policy.ok() && policy.summary().find("advisory:") != std::string::npos, "board policy promoted to local failure");
    policy.errors.push_back("hard"); require(!policy.ok(), "hard error waived");
}
void registration() {
    auto builtin = electrical(); builtin.name = "builtin";
    auto ext = electrical();
    const auto merged = merge_subsystem_definitions({builtin}, {ext});
    require(merged.size() == 2 && merged.front().name == "builtin" && merged.back().name == "widget", "registration order");
    require(merged.back().circuit(SubsystemMeta{}, {}).parts.size() == 2, "registered live callback");
    const auto configured = append_configured_subsystem_definitions({});
    require(std::all_of(configured.begin(), configured.end(), [](const auto& entry) {
        return !entry.name.empty() && !entry.interface.empty() && bool(entry.circuit);
    }), "configured registration must retain live factories");
    rejects([&] { merge_subsystem_definitions({ext}, {ext}); }, "builtin shadow accepted");
    rejects([&] { merge_subsystem_definitions({}, {ext, ext}); }, "duplicate extension accepted");
    rejects([&] { merge_subsystem_definitions({ext, ext}, {}); }, "duplicate builtin accepted");
    ext.circuit = {};
    rejects([&] { merge_subsystem_definitions({}, {ext}); }, "non-callable registration accepted");
    ext = electrical(); ext.interface.clear();
    rejects([&] { merge_subsystem_definitions({}, {ext}); }, "empty interface registered");
    ext = electrical(); ext.interface.push_back("GND");
    rejects([&] { merge_subsystem_definitions({}, {ext}); }, "duplicate port registered");
    ext = electrical(); ext.interface.push_back("");
    rejects([&] { merge_subsystem_definitions({}, {ext}); }, "empty port registered");
}
} // namespace
int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: subsystem_scaffold_contracts REPOSITORY");
        rendering(argv[1]); publication(); local_checks(); registration();
        std::cout << "PASS: " << assertions << " native scaffold, publication, registration, and electrical contracts\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
