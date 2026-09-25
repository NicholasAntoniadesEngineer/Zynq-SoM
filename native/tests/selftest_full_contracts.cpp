#include "selftest_full_internal.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/process.hpp"

#include <cstdlib>
#include <iostream>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool ok, const std::string& message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* f = object_field(n, key);
    if (!f) throw std::runtime_error("fixture field missing: " + key);
    return *f;
}
void equal_text(const std::string& a, const std::string& b, const std::string& why) {
    ++checks;
    if (a == b) return;
    std::size_t i = 0; while (i < a.size() && i < b.size() && a[i] == b[i]) ++i;
    throw std::runtime_error(why + " differs at byte " + std::to_string(i) + ": " +
        a.substr(i, 180) + " != " + b.substr(i, 180));
}
template<class F> void rejects(F fn, const std::string& message) {
    bool rejected = false;
    try { fn(); } catch (const std::exception&) { rejected = true; }
    require(rejected, message);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "schgen_full_contracts_XXXXXX").string();
        if (!::mkdtemp(pattern.data())) throw std::runtime_error("mkdtemp failed");
        path = pattern;
    }
    ~Scratch() { std::error_code error; fs::remove_all(path, error); }
};
std::vector<std::string> strings(const JsonNode& n) {
    std::vector<std::string> out;
    for (const auto& s : n.array_value) out.push_back(s.string_value);
    return out;
}
void stack_equal(const SelftestStackVerdict& v, const JsonNode& n, const std::string& why) {
    equal_text(selftesting::join(v.failures), selftesting::join(strings(field(n, "failures"))), why + " failures");
    require(v.passed == strings(field(n, "passed")), why + " passed gates");
}
void geometry_equal(const SheetGeometry& g, const JsonNode& n) {
    const auto& boxes = field(n, "boxes").array_value;
    const auto& wires = field(n, "wires").array_value;
    require(boxes.size() == g.boxes.size() && wires.size() == g.wires.size(), "geometry count");
    auto coordinate = [](double v, const JsonNode& o, const std::string& key) {
        require(v == field(o, key).number_value, "exact geometry coordinate " + key);
    };
    for (std::size_t i = 0; i < boxes.size(); ++i) {
        const auto& a = g.boxes[i]; const auto& b = boxes[i];
        coordinate(a.x0, b, "x0"); coordinate(a.y0, b, "y0");
        coordinate(a.x1, b, "x1"); coordinate(a.y1, b, "y1");
        equal_text(a.kind, field(b, "kind").string_value, "box kind");
        equal_text(a.owner, field(b, "owner").string_value, "box owner");
    }
    for (std::size_t i = 0; i < wires.size(); ++i) {
        const auto& a = g.wires[i]; const auto& b = wires[i];
        coordinate(a.x0, b, "x0"); coordinate(a.y0, b, "y0");
        coordinate(a.x1, b, "x1"); coordinate(a.y1, b, "y1");
        equal_text(a.net, field(b, "net").string_value, "wire net");
    }
}
PcbCheckFootprintPtr resistor(const fs::path& path) {
    return pcb_check_footprint(path.string(), selftesting::read(path));
}
void ratsnest_contracts(const SelftestModelFixtures& f, const JsonNode& reference) {
    for (const std::string name : {"base", "offboard", "dispersed"}) {
        auto model = f.ratsnest;
        if (name == "offboard") for (auto& p : model.insts) if (p.ref == "R6") p.x += 200;
        if (name == "dispersed") {
            const std::vector<std::pair<double,double>> points = {{2,2},{55,2},{55,36},{2,36}};
            std::size_t i = 0;
            for (auto& p : model.insts) if (p.sheet == "subsys_a") {
                p.x = 25 + points.at(i).first; p.y = 25 + points.at(i++).second;
            }
        }
        auto r = check_ratsnest(PcbCheckInput(model));
        const auto& expected = field(reference, name);
        equal_text(r.summary(), field(expected, "summary").string_value, "ratsnest Python " + name);
        require(r.ok == field(expected, "ok").bool_value, "ratsnest verdict " + name);
        require(r.cross_mm == field(expected, "cross_mm").number_value &&
                r.total_mm == field(expected, "total_mm").number_value, "ratsnest exact lengths");
        const auto npp = ratsnest_net_pad_positions(model); const auto edges = ratsnest_mst(npp);
        equal_text(check_ratsnest(PcbCheckInput(model), &npp, &edges).summary(), r.summary(), "supplied MST matches calculated MST");
    }
    const auto baseline = check_ratsnest(PcbCheckInput(f.ratsnest));
    require(baseline.ok && baseline.n_subsystems == 2, "real baseline is clean");
    require(!check_ratsnest(PcbCheckInput(f.ratsnest), nullptr, nullptr, 0).cross_ok(), "zero cross budget rejects real cross edges");
    auto missing = f.ratsnest; missing.insts.front().mod.reset();
    rejects([&] { check_ratsnest(PcbCheckInput(missing)); }, "missing footprint must throw");
    auto invalid = f.ratsnest; invalid.board_w = 0;
    rejects([&] { check_ratsnest(PcbCheckInput(invalid)); }, "zero width must throw");
    invalid = f.ratsnest; invalid.board_h = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { check_ratsnest(PcbCheckInput(invalid)); }, "NaN dimensions must throw");
    const auto npp = ratsnest_net_pad_positions(f.ratsnest); auto bad_edges = ratsnest_mst(npp);
    bad_edges.begin()->second.push_back({-1, 0});
    rejects([&] { check_ratsnest(PcbCheckInput(f.ratsnest), &npp, &bad_edges); }, "invalid edge must throw");
    // A prepared snapshot stays immutable when its original model is changed.
    auto mutable_model = f.ratsnest; PcbCheckInput prepared(mutable_model);
    mutable_model.insts.back().x += 200;
    require(check_ratsnest(prepared).ok && !check_ratsnest(PcbCheckInput(mutable_model)).ok,
            "mutation requires fresh geometry, baseline snapshot remains clean");
}
void worker_contracts(const SelftestBuilt& b, SymbolLibrary& lib, const fs::path& scratch,
                      const std::string& executable) {
    auto request = selftest_worker_request(b, lib);
    equal_text(selftest_worker_emit(request, scratch / "direct"), b.text, "worker rebuilds exact bytes");
    const auto path = scratch / "request.json";
    selftesting::publish(path, selftesting::json_text(request));
    equal_text(selftest_worker_emit(parse_json_file(path.string()), scratch / "decoded"), b.text,
          "worker JSON roundtrip preserves source IR and symbols");
    auto missing = request;
    for (auto& [key, value] : missing.object_value) if (key == "symbols") value.array_value.clear();
    rejects([&] { selftest_worker_emit(missing, scratch / "missing"); }, "worker cannot reload missing symbols from disk");
    auto duplicate = request;
    for (auto& [key, value] : duplicate.object_value) if (key == "symbols") value.array_value.push_back(value.array_value.front());
    rejects([&] { selftest_worker_emit(duplicate, scratch / "duplicate"); }, "duplicate symbol snapshots rejected");
    SelftestFullOptions options;
    options.worker_command = {executable, "--worker"};
    require(selftest_hashseed_determinism(b.circuit, lib, scratch / "seeds", options).ok, "fresh native subprocesses agree");
    require(!selftest_hashseed_determinism(b.circuit, lib, scratch / "seeds", options).ok, "stale child directories cannot pass");
    for (const auto* mode : {"--empty-worker", "--drift-worker", "--wrong-worker"}) {
        options.worker_command = {executable, mode};
        const auto result = selftest_hashseed_determinism(b.circuit, lib, scratch / mode, options);
        require(!result.ok, std::string("worker negative control ") + mode);
        if (std::string(mode) == "--drift-worker") require(result.diagnostic.find("HASH-SEED DRIFT") != std::string::npos, "drift is diagnosed");
        if (std::string(mode) == "--wrong-worker") require(result.diagnostic.find("differs from parent") != std::string::npos, "identical wrong outputs cannot pass");
    }
    options.worker_command = {(scratch / "absent-executable").string()};
    require(!selftest_hashseed_determinism(b.circuit, lib, scratch / "absent", options).ok, "missing worker cannot pass");
    options.worker_command.clear();
    rejects([&] { selftest_hashseed_determinism(b.circuit, lib, scratch / "unconfigured", options); }, "empty command cannot skip proof");
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 4 && std::string(argv[1]).find("worker") != std::string::npos) {
            const std::string mode = argv[1];
            if (mode == "--empty-worker") return 0; // Negative control, never a production worker.
            auto request = parse_json_file(argv[2]);
            auto text = selftest_worker_emit(request, argv[3]);
            if (mode == "--drift-worker" || mode == "--wrong-worker") {
                text += mode == "--drift-worker" ? std::string("; seed ") + std::getenv("PYTHONHASHSEED") + "\n" : "; wrong but repeatable\n";
                selftesting::publish(fs::path(argv[3]) / (field(field(request,"circuit"),"name").string_value + ".kicad_sch"), text);
            }
            std::cout << text; return 0;
        }
        require(argc == 3, "usage: selftest_full_contracts <repository> <real-resistor-footprint>");
        const auto root = fs::absolute(argv[1]); const auto executable = fs::absolute(argv[0]).string();
        const auto reference = parse_json_file((root / "native/tests/data/selftest_full/python_reference.json").string());
        require(field(reference,"exit_code").number_value == 0, "Python reference run passed");
        Scratch scratch; SymbolLibrary library(root);
        auto fixtures = selftest_model_fixtures(resistor(argv[2]));
        ratsnest_contracts(fixtures, field(reference, "ratsnest"));
        std::vector<SelftestSheetInput> inputs;
        for (const auto& [name, data] : field(reference, "sheets").object_value) {
            auto c = parse_circuit_ir(field(data, "circuit"));
            const auto built = build_selftest_sheet(c, library, scratch.path / "compare" / name);
            equal_text(built.text, field(data,"text").string_value, name + " Python baseline bytes");
            const auto mutations = selftest_sheet_mutations(built, library);
            const auto& expected = field(data, "mutations").array_value;
            require(mutations.size() == expected.size(), name + " mutation count");
            for (std::size_t i = 0; i < mutations.size(); ++i) {
                equal_text(mutations[i].name, field(expected[i],"name").string_value, name + " mutation order");
                equal_text(mutations[i].description, field(expected[i],"description").string_value, name + " mutation description");
                if (mutations[i].geometry) geometry_equal(*mutations[i].geometry, field(expected[i], "geometry"));
            }
            if (name == "m1_rc") {
                equal_text(selftesting::json_text(selftesting::circuit_json(c)),
                      selftesting::json_text(selftesting::circuit_json(selftest_rc_fixture())), "native RC fixture matches Python IR");
                worker_contracts(built, library, scratch.path / "workers", executable);
            }
            inputs.push_back({std::move(c), field(data,"path").string_value, name});
        }
        SelftestFullOptions options; options.scratch_parent = scratch.path;
        options.worker_command = {executable, "--worker"}; options.keep = true;
        options.progress = [](const auto& s) { std::cout << s << std::flush; };
        const auto result = run_full_selftest(inputs, fixtures, library, options);
        require(result.ok(), result.report);
        require(result.injected == 63 && result.killed == 63 && result.models.injected == 18,
                "all 63 independently established mutations must execute and die");
        const auto& expected_stacks = field(reference, "stacks").array_value; std::size_t i = 0;
        for (const auto& sheet : result.sheets) {
            stack_equal(sheet.baseline, expected_stacks.at(i++), sheet.name + " baseline");
            for (const auto& mutation : sheet.mutations) {
                require(mutation.killed, "each mutation receives a real kill");
                stack_equal(mutation.verdict, expected_stacks.at(i++), sheet.name + " " + mutation.name);
            }
            require(sheet.determinism.ok && sheet.hashseed.ok, "both determinism checks passed");
        }
        require(i == expected_stacks.size(), "every Python stack result compared");
        const auto report = field(reference, "report").string_value;
        for (const auto& p : result.models.proofs) {
            require(p.baseline_ok && p.mutation_killed, "model proof requires clean baseline and own mutation");
            require(report.find(p.diagnostic) != std::string::npos, "Python model diagnostic " + p.name + ": " + p.diagnostic);
        }
        require(fs::is_directory(result.scratch), "keep retains audit artifacts");
        const auto json = selftest_full_result_json(result);
        require(field(json,"ok").bool_value && field(json,"injected").number_value == 63 &&
                field(field(json,"models"),"proofs").array_value.size() == 18, "structured result retains all evidence");
        rejects([&] { run_full_selftest({}, fixtures, library, options); }, "empty sheet selection cannot claim success");
        auto duplicate = inputs; duplicate.push_back(inputs.front());
        rejects([&] { run_full_selftest(duplicate, fixtures, library, options); }, "duplicate scratch names cannot contaminate proofs");
        auto unsafe = inputs; unsafe.front().scratch_name = "../outside";
        rejects([&] { run_full_selftest(unsafe, fixtures, library, options); }, "unsafe output names rejected");
        const auto clean = build_selftest_sheet(inputs.front().circuit, library, scratch.path / "errors");
        rejects([&] { selftest_gate_stack(clean.circuit, clean.schematic, library, nullptr,
            {(scratch.path / "no-kicad").string()}); }, "KiCad execution failure cannot count as a kill");
        // A circuit too small to exercise a visual/label mutation must fail its
        // coverage requirement even when the available live gates are green.
        const auto tiny = selftest_sheet({fixtures.board.front(), "one-resistor", "tiny"}, library, scratch.path / "tiny");
        require(!tiny.problems.empty(), "inapplicable mutations are reported as problems");
        std::cout << "Full selftest: " << checks << " contracts passed; live KiCad 63/63, two fresh-process determinism proofs\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Full selftest contract FAILED: " << e.what() << '\n'; return 1;
    }
}
