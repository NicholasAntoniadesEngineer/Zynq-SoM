// Standalone pure-engine contracts; no Python, module or board generation.
// Usage: design_rules_contracts <fixtures-dir> [--live <repo>] [--corpus <json>]
//                               [--benchmark]
#include "schgen/design_rules.hpp"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <future>
#include <iostream>
#include <map>
#include <new>
#include <stdexcept>
#include <system_error>

namespace {
using namespace schgen;
using Sheets = std::vector<CircuitSheetIr>;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message); // Active in NDEBUG builds.
}
const JsonNode& field(const JsonNode& node, const std::string& name) {
    const auto* result = object_field(node, name);
    require(result != nullptr, "fixture missing field " + name);
    return *result;
}
std::string str(const JsonNode& node, const std::string& name) {
    return field(node, name).string_value;
}
void equal_json(const JsonNode& actual, const JsonNode& expected, const std::string& where) {
    require(actual.kind == expected.kind, where + ": different JSON kind");
    switch (actual.kind) {
        case JsonKind::Null: break;
        case JsonKind::Bool: require(actual.bool_value == expected.bool_value, where + ": bool differs"); break;
        case JsonKind::Number: require(actual.number_value == expected.number_value, where + ": number differs"); break;
        case JsonKind::String:
            require(actual.string_value == expected.string_value, where + ": text differs\nactual: "
                + actual.string_value + "\nexpected: " + expected.string_value); break;
        case JsonKind::Array:
            require(actual.array_value.size() == expected.array_value.size(), where + ": array length differs");
            for (std::size_t i = 0; i < actual.array_value.size(); ++i)
                equal_json(actual.array_value[i], expected.array_value[i], where + "[" + std::to_string(i) + "]");
            break;
        case JsonKind::Object:
            require(actual.object_value.size() == expected.object_value.size(), where + ": object size differs");
            for (std::size_t i = 0; i < actual.object_value.size(); ++i) {
                // Dictionary insertion order is part of the transport contract.
                require(actual.object_value[i].first == expected.object_value[i].first, where + ": key order differs");
                equal_json(actual.object_value[i].second, expected.object_value[i].second,
                    where + "." + actual.object_value[i].first);
            }
            break;
    }
}

// Explicit typed inputs, deliberately not parse_circuit_ir: these corpus
// mutations include floating/duplicate/unknown pins to test the gate independently
// of the separate IR semantic validator. Real board fixtures use that validator.
CircuitSheetIr typed_sheet(const JsonNode& node) {
    CircuitSheetIr sc; sc.name = str(node, "name"); sc.title = str(node, "title");
    for (const auto& item : field(node, "parts").array_value) {
        CircuitPartIr p; p.ref = str(item, "ref"); p.lib_id = str(item, "lib_id");
        p.value = str(item, "value"); p.footprint = str(item, "footprint");
        for (const auto& f : field(item, "fields").object_value) p.fields.push_back({f.first, f.second.string_value});
        sc.parts.push_back(std::move(p));
    }
    for (const auto& item : field(node, "nets").array_value) {
        CircuitNetIr n; n.name = str(item, "name"); n.net_class = str(item, "net_class");
        for (const auto& pin : field(item, "pins").array_value) {
            const auto at = pin.string_value.find('.');
            n.pins.push_back({pin.string_value.substr(0, at), pin.string_value.substr(at + 1)});
        }
        sc.nets.push_back(std::move(n));
    }
    for (const auto& item : field(node, "port_types").object_value) {
        CircuitPortIr pt; pt.net = item.first; pt.kind = str(item.second, "kind"); sc.port_types.push_back(pt);
    }
    for (const auto* key : {"tp_waivers", "decap_waivers", "pull_waivers", "reset_waivers", "strap_waivers", "ep_waivers"})
        for (const auto& item : field(node, key).object_value) sc.waivers.push_back({key, item.first, item.second.string_value});
    return sc;
}
std::vector<SymbolDef> symbol_defs(const JsonNode& node) {
    std::vector<SymbolDef> out;
    for (const auto& item : field(node, "symbols").array_value) {
        SymbolDef symbol; symbol.lib_id = str(item, "lib_id");
        for (const auto& pin : field(item, "pins").array_value) {
            SymbolPin p; p.number = str(pin, "number"); p.name = str(pin, "name"); p.etype = str(pin, "etype");
            symbol.pins.push_back(std::move(p));
        }
        out.push_back(std::move(symbol));
    }
    return out;
}
void compare(const DesignRuleIndex& index, const JsonNode& expected, const std::string& where) {
    equal_json(design_rule_result_json(index.check()), field(expected, "design"), where + ".design");
    const auto& coverage = field(expected, "coverage");
    if (object_field(coverage, "exception")) {
        try { index.check_testpoints(); }
        catch (const UnnettedTestpoint&) { return; }
        throw std::runtime_error(where + ": expected unnetted testpoint exception");
    }
    equal_json(testpoint_coverage_json(index.check_testpoints()), coverage, where + ".coverage");
}

void corpus(const std::filesystem::path& path) {
    const auto data = parse_json_file(path.string());
    for (const auto& test : field(data, "power_names").array_value)
        require(is_power_pin_name(str(test, "name")) == field(test, "expected").bool_value,
                "power pin inference: " + str(test, "name"));
    for (const auto& test : field(data, "cases").array_value) {
        Sheets sheets;
        for (const auto& node : field(test, "sheets").array_value) sheets.push_back(typed_sheet(node));
        const auto defs = symbol_defs(test);
        const auto name = str(test, "name");
        const DesignRuleIndex index(sheets, defs);
        compare(index, field(test, "expected"), name);
        // Public convenience APIs cannot diverge from reusable index checks.
        equal_json(design_rule_result_json(check_design_rules(sheets, defs)),
                   field(field(test, "expected"), "design"), name + ".free");
        if (!object_field(field(field(test, "expected"), "coverage"), "exception"))
            equal_json(testpoint_coverage_json(check_testpoint_coverage(sheets)),
                       field(field(test, "expected"), "coverage"), name + ".coverage-free");
    }
    std::cout << "PASS " << path.filename().string() << ": " << field(data, "cases").array_value.size()
              << " cases; " << field(data, "power_names").array_value.size() << " power-pin vectors\n";
}

void remove_part(Sheets& sheets, const std::string& owner, const std::string& ref) {
    bool found = false;
    for (auto& s : sheets) if (s.name == owner) {
        const auto n = s.parts.size();
        s.parts.erase(std::remove_if(s.parts.begin(), s.parts.end(), [&](const auto& p) { return p.ref == ref; }), s.parts.end());
        require(s.parts.size() + 1 == n, "mutation missing part " + owner + ":" + ref);
        found = true;
        for (auto& net : s.nets) net.pins.erase(std::remove_if(net.pins.begin(), net.pins.end(),
            [&](const auto& p) { return p.ref == ref; }), net.pins.end());
        s.nc.erase(std::remove_if(s.nc.begin(), s.nc.end(), [&](const auto& p) { return p.ref == ref; }), s.nc.end());
    }
    require(found, "mutation missing sheet " + owner);
}

double median(std::vector<double> values) {
    std::sort(values.begin(), values.end());
    const auto n = values.size();
    return n % 2 ? values[n / 2] : (values[n / 2 - 1] + values[n / 2]) / 2;
}
template<class F> double timed(F action) {
    const auto start = std::chrono::steady_clock::now(); action();
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
}
void benchmark(const std::string& name, const Sheets& sheets, const std::vector<SymbolDef>& defs) {
    // Report generation, fixture parsing and disk I/O excluded. First sample
    // includes index construction; warm samples use the same immutable index.
    std::size_t sink = 0;
    const double first = timed([&] { DesignRuleIndex idx(sheets, defs); sink += idx.check().findings().size() + idx.check_testpoints().covered(); });
    std::vector<double> fresh, warm;
    const DesignRuleIndex index(sheets, defs);
    for (int i = 0; i < 101; ++i) {
        fresh.push_back(timed([&] { DesignRuleIndex idx(sheets, defs); sink += idx.check().waived.size() + idx.check_testpoints().covered(); }));
        warm.push_back(timed([&] { sink += index.check().waived.size() + index.check_testpoints().covered(); }));
    }
    std::cout << "BENCH " << name << " (ms): first_index+both_checks=" << first
              << " fresh_index+both_checks_median=" << median(fresh)
              << " reused_index+both_checks_median=" << median(warm)
              << " samples=101 checksum=" << sink << '\n';
}

void library_benchmark(const std::string& name, const Sheets& sheets, const std::filesystem::path& repo) {
    std::vector<double> cold, warm;
    std::size_t sink = 0;
    std::unique_ptr<SymbolLibrary> lib;
    DesignRuleSymbolResolver resolve = [&](const std::string& id) -> const SymbolDef& { return lib->get(id); };
    for (int i = 0; i < 5; ++i) {
        lib.reset();
        clear_symbol_file_cache(); // Symbol cache only; not the OS page cache.
        cold.push_back(timed([&] {
            lib = std::make_unique<SymbolLibrary>(repo);
            const DesignRuleIndex index(sheets, resolve);
            sink += index.check().waived.size() + index.check_testpoints().covered();
        }));
    }
    for (int i = 0; i < 101; ++i) warm.push_back(timed([&] {
        const DesignRuleIndex index(sheets, resolve);
        sink += index.check().waived.size() + index.check_testpoints().covered();
    }));
    std::cout << "BENCH " << name << " (ms): cleared_symbol_cache+Library+index+checks_median=" << median(cold)
              << " warm_Library+fresh_index+checks_median=" << median(warm)
              << " samples=5/101 checksum=" << sink << '\n';
}

void board(const std::filesystem::path& path, const std::filesystem::path& repo, bool bench) {
    const auto data = parse_json_file(path.string()); const auto name = str(data, "name");
    Sheets frozen;
    for (const auto& node : field(data, "sheets").array_value) frozen.push_back(parse_circuit_ir(node));
    const auto defs = symbol_defs(data);
    compare(DesignRuleIndex(frozen, defs), field(data, "expected"), name + ".frozen");
    require(DesignRuleIndex(frozen, defs).check().ok() && check_testpoint_coverage(frozen).ok(), name + ": baseline must pass");
    auto sheets = frozen;
    std::unique_ptr<SymbolLibrary> lib;
    DesignRuleSymbolResolver resolver;
    if (!repo.empty()) {
        sheets.clear();
        std::vector<std::filesystem::path> paths;
        for (const auto& entry : std::filesystem::directory_iterator(repo / name / "subsystems"))
            if (std::filesystem::is_regular_file(entry.path() / "circuit.json")) paths.push_back(entry.path() / "circuit.json");
        std::sort(paths.begin(), paths.end());
        for (const auto& p : paths) sheets.push_back(load_circuit_json(p));
        require(sheets.size() == frozen.size(), "live sheet count drifted: " + name);
        lib = std::make_unique<SymbolLibrary>(repo);
        resolver = [&](const std::string& id) -> const SymbolDef& { return lib->get(id); };
        compare(DesignRuleIndex(sheets, resolver), field(data, "expected"), name + ".live");
    }
    std::size_t pulls = 0, probes = 0;
    for (const auto& mutation : field(data, "mutations").array_value) {
        auto missing = sheets;
        remove_part(missing, str(mutation, "owner"), str(mutation, "ref"));
        const DesignRuleIndex index = resolver ? DesignRuleIndex(missing, resolver) : DesignRuleIndex(missing, defs);
        compare(index, field(mutation, "expected"), name + "." + str(mutation, "name"));
        if (str(mutation, "kind") == "pull") {
            const auto result = index.check();
            require(!result.ok() && result.i2c.size() == 1
                    && result.i2c.front().find(str(mutation, "target_net")) == 0,
                    "pull-up removal did not fail its specific I2C gate"); ++pulls;
        } else {
            const auto result = index.check_testpoints();
            require(!result.ok() && result.errors.size() == 1
                    && result.errors.front().find(str(mutation, "target_net")) == 0,
                    "probe removal did not fail its specific coverage gate"); ++probes;
        }
    }
    require(pulls == (name == "carrier" ? 8 : 2), "not all physical pull-ups were tested");
    require(probes == (name == "carrier" ? 0 : 9), "not all nine physical probes were tested");
    if (bench) {
        benchmark(name, sheets, defs);
        if (!repo.empty()) library_benchmark(name, sheets, repo);
    }
    std::cout << "PASS " << name << ": " << sheets.size() << " sheets, " << pulls << " pull-up removals, "
              << probes << " probe removals; " << (repo.empty() ? "frozen IR/pins" : "frozen and live canonical IR/native SymbolLibrary") << '\n';
}

template<class E, class F> void throws(F action, const std::string& message) {
    try { action(); }
    catch (const E&) { return; }
    throw std::runtime_error(message);
}
void resolver_contracts() {
    CircuitSheetIr sc; sc.name = "failure";
    CircuitPartIr p; p.ref = "U1"; p.lib_id = "missing:IC"; sc.parts.push_back(p);
    p.ref = "U2"; sc.parts.push_back(p);
    sc.nets.push_back({"+3V3", "power", {{"U1", "1"}, {"U2", "1"}}});
    SymbolDef definition; definition.lib_id = p.lib_id;
    for (const auto& n : {"1", "2", "3"}) { SymbolPin pin; pin.number = n; pin.name = "VDD"; definition.pins.push_back(pin); }
    std::size_t calls = 0;
    DesignRuleSymbolResolver missing = [&](const std::string&) -> const SymbolDef& { ++calls; throw SymbolError("missing symbol"); };
    const DesignRuleIndex unresolved({sc}, missing);
    require(calls == 1 && unresolved.check().ok(), "missing symbol wasn't cached/skipped");
    unresolved.check(); unresolved.check_testpoints(); require(calls == 1, "resolver retained by index");
    for (int kind = 0; kind < 3; ++kind) {
        DesignRuleSymbolResolver failure = [kind](const std::string&) -> const SymbolDef& {
            if (kind == 0) throw std::out_of_range("absent symbol");
            if (kind == 1) throw std::runtime_error("custom resolver failed");
            throw std::invalid_argument("malformed symbol");
        };
        require(check_design_rules({sc}, failure).ok(), "ordinary resolver compatibility skip changed");
    }
    DesignRuleSymbolResolver allocation = [](const std::string&) -> const SymbolDef& { throw std::bad_alloc(); };
    DesignRuleSymbolResolver system = [](const std::string&) -> const SymbolDef& { throw std::system_error(std::make_error_code(std::errc::io_error)); };
    DesignRuleSymbolResolver other = [](const std::string&) -> const SymbolDef& { throw 42; };
    throws<std::bad_alloc>([&] { check_design_rules({sc}, allocation); }, "allocation error swallowed");
    throws<std::system_error>([&] { check_design_rules({sc}, system); }, "system error swallowed");
    throws<int>([&] { check_design_rules({sc}, other); }, "non-standard exception swallowed");
    calls = 0;
    DesignRuleSymbolResolver found = [&](const std::string&) -> const SymbolDef& { ++calls; return definition; };
    const DesignRuleIndex snapshot({sc}, found);
    const auto before = design_rule_result_json(snapshot.check());
    require(!snapshot.check().ok() && calls == 1, "known symbol not checked");
    definition.pins.clear(); sc.parts.clear();
    equal_json(design_rule_result_json(snapshot.check()), before, "index must own pin and circuit snapshots");
    require(check_design_rules({sc}, found).ok(), "new index must observe input edits");
    auto copied = snapshot;
    std::vector<std::future<DesignRuleResult>> jobs;
    for (int i = 0; i < 8; ++i) jobs.push_back(std::async(std::launch::async, [&] { return copied.check(); }));
    for (auto& job : jobs) equal_json(design_rule_result_json(job.get()), before, "concurrent immutable index");
    std::cout << "PASS resolver failures, snapshot ownership, once-per-ID cache, concurrent reads\n";
}

void result_contracts() {
    DesignRuleResult empty;
    require(empty.ok() && empty.findings().empty(), "empty result properties");
    require(empty.summary().find("0 IC supply pins") != std::string::npos, "default checked counts");
    TestpointCoverage cov; cov.required = {{"A", "rail"}}; cov.have = {{"A", {}}};
    cov.waived = {{"A", {"sheet", "reason"}}}; cov.extras = {{"ignored", {"bogus"}}};
    require(cov.covered() == 1 && cov.report().find("TP @ ") != std::string::npos,
            "presence of empty have list must still beat waiver");
    require(cov.report().find("bogus") == std::string::npos, "legacy extras field must remain unused");
    require(cov.report().back() != '\n' && empty.report().back() != '\n', "report trailing newline changed");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc >= 2, "usage: design_rules_contracts <fixtures-dir> [--live <repo>] [--corpus <json>] [--benchmark]");
        std::filesystem::path repo, extra; bool bench = false;
        for (int i = 2; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--benchmark") bench = true;
            else if (arg == "--live" && i + 1 < argc) repo = argv[++i];
            else if (arg == "--corpus" && i + 1 < argc) extra = argv[++i];
            else throw std::runtime_error("unknown/incomplete option: " + arg);
        }
        resolver_contracts(); result_contracts();
        const std::filesystem::path fixtures(argv[1]);
        corpus(fixtures / "contracts.json");
        if (!extra.empty()) corpus(extra);
        board(fixtures / "carrier.json", repo, bench);
        board(fixtures / "devkit_mini.json", repo, bench);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n'; return 1;
    }
}
