#include "schgen/geometry_cli.hpp"
#include "schgen/atomic_file.hpp"

#include <algorithm>
#include <fstream>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t checks = 0;
void require(bool ok, const std::string& message) { ++checks; if (!ok) throw std::runtime_error(message); }
std::string read(const fs::path& path) {
    std::ifstream file(path, std::ios::binary); require(bool(file), "read " + path.string());
    return {std::istreambuf_iterator<char>(file), {}};
}
void write(const fs::path& path, const std::string& bytes) { write_atomic_file(path.string(), {bytes.begin(), bytes.end()}); }
const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key); require(value != nullptr, "missing field " + key); return *value;
}
template<class F> void rejects(F action, const std::string& text) {
    std::string message;
    try { action(); } catch (const std::exception& ex) { message = ex.what(); }
    require(!message.empty() && message.find(text) != message.npos, "expected " + text + "; got " + message);
}
std::optional<GeometryCommandOptions> parse(std::vector<std::string> args) {
    args.insert(args.begin(), "schgen"); std::vector<char*> argv;
    for (auto& arg : args) argv.push_back(arg.data());
    return parse_geometry_command(static_cast<int>(argv.size()), argv.data());
}
std::pair<int, std::string> run(const std::vector<std::string>& args) {
    auto options = parse(args); require(bool(options), "recognized geometry command");
    std::ostringstream stream;
    struct Redirect { std::streambuf* old; ~Redirect() { std::cout.rdbuf(old); } } redirect{std::cout.rdbuf(stream.rdbuf())};
    const int code = execute_geometry_command(*options);
    return {code, stream.str()};
}
using Snapshot = std::map<std::string, std::string>;
fs::path executable(const std::string& name) {
    const auto* environment = std::getenv("PATH");
    std::istringstream paths(environment ? environment : ""); std::string directory;
    while (std::getline(paths, directory, ':')) {
        const auto path = fs::absolute(fs::path(directory.empty() ? "." : directory) / name);
        if (fs::is_regular_file(path) && ::access(path.c_str(), X_OK) == 0) return path;
    }
    throw std::runtime_error("live proof requires installed trusted tool " + name);
}
class WithoutAuditCompiler {
    std::optional<std::string> original;
public:
    explicit WithoutAuditCompiler(const fs::path& directory) {
        // Actual trusted executables only. No fake tool, fixed verdict or audit
        // callback: the real board audit must fail to spawn its missing clang++.
        const auto spice = executable("ngspice");
        fs::create_directories(directory); fs::create_symlink(spice, directory / "ngspice");
        if (const auto* value = std::getenv("PATH")) original = value;
        if (::setenv("PATH", directory.c_str(), 1) != 0) throw std::runtime_error("cannot isolate tool PATH");
    }
    ~WithoutAuditCompiler() {
        if (original) (void)::setenv("PATH", original->c_str(), 1);
        else (void)::unsetenv("PATH");
    }
    WithoutAuditCompiler(const WithoutAuditCompiler&) = delete;
    WithoutAuditCompiler& operator=(const WithoutAuditCompiler&) = delete;
};
Snapshot snapshot(const fs::path& root) {
    Snapshot result;
    for (const auto& entry : fs::recursive_directory_iterator(root)) {
        require(!entry.is_symlink(), "test snapshot contains symlink");
        const auto key = entry.path().lexically_relative(root).generic_string();
        if (entry.is_regular_file()) result.emplace(key, read(entry.path()));
        else if (entry.is_directory()) result.emplace(key + "/", "");
    }
    return result;
}
void parser(const JsonNode& reference) {
    for (const auto& row : field(reference, "cases").array_value) {
        std::vector<std::string> args;
        for (const auto& value : field(row, "args").array_value) args.push_back(value.string_value);
        const auto options = parse(args); require(bool(options), "legacy case recognized");
        require(options->compose.repair == field(row, "repair").bool_value, "legacy repair precedence");
        require(options->compose.dry_run == field(row, "dry_run").bool_value, "legacy dry-run");
        require(options->compose.max_steps == field(row, "max_steps").number_value, "legacy reserved max-steps");
        std::vector<std::string> intents;
        for (const auto& value : field(row, "allow_intent").array_value) intents.push_back(value.string_value);
        require(options->compose.allow_intent == intents, "legacy repeated intent sequence");
    }
    for (const auto& args : std::vector<std::vector<std::string>>{{}, {"board"}, {"--help"}, {"--repo", "compose", "nets"}, {"nets", "--output", "floorplan"}})
        require(!parse(args), "unrelated command must remain available to other dispatchers");
    require(parse({"--repo", "R", "--project", "P", "floorplan", "--export"})->export_spec, "leading global options");
    const auto o = parse({"compose", "--repo", "R", "--project", "P", "-o", "OUT", "--kicad-cli", "TOOL"});
    require(o->repository == "R" && o->project == "P" && o->output == "OUT" && o->kicad_cli == "TOOL", "native transport options");
    for (const auto& args : std::vector<std::vector<std::string>>{
        {"floorplan", "--repair"}, {"floorplan", "--allow-intent", "a:N->S"}, {"floorplan", "--dry-run"},
        {"compose", "--export"}, {"compose", "--waive"}, {"floorplan", "extra"},
        {"floorplan", "--output"}, {"floorplan", "--output", ""}, {"compose", "--max-steps", ""},
        {"compose", "--max-steps", "1.2"}, {"compose", "--max-steps", "nan"}, {"compose", "--max-steps", "2147483648"},
        {"compose", "--repair", "--allow-intent", "bad"}, {"compose", "--no-render"},
        {"compose", "--repair", "--dry-run", "--no-render"}, {"floorplan", "--export", "--export"},
        {"compose", "-o", "one", "--output", "two"}, {"--repo", "one", "compose", "--repo", "two"}})
        rejects([&] { (void)parse(args); }, "");
    for (const auto* name : {"floorplan", "compose"}) {
        const auto result = run({name, "--help", "--repo", "/missing/repository"});
        require(result.first == 0 && result.second.find("usage: schgen " + std::string(name)) != result.second.npos, "help without inputs/catalog/executable");
    }
    require(geometry_command_help("compose").find("PROJECT/floorplan.json even with --output") != std::string::npos, "help discloses source mutation");
    rejects([] { (void)geometry_command_help("board"); }, "unknown");
}
void safety(const fs::path& repo, const fs::path& work) {
    const auto project = work / "safety/devkit_mini";
    write(project / "project.json", "{}"); write(project / "floorplan.json", "{}\n");
    const auto original = snapshot(project);
    const auto invoke = [&](const fs::path& output, const std::vector<std::string>& extra) {
        std::vector<std::string> args{"floorplan", "--repo", repo.string(), "--project", project.string(), "--output", output.string(), "--kicad-cli", "/no/extractor"};
        args.insert(args.end(), extra.begin(), extra.end()); return run(args);
    };
    for (const auto& output : {repo, repo.parent_path(), repo / "native/unsafe", repo / "parts/unsafe", project.parent_path(), project / "subsystems/unsafe", repo / "carrier/reports"})
        rejects([&] { (void)invoke(output, {}); }, "output");
    const auto external = work / "external"; fs::create_directories(external);
    const auto linked = work / "linked"; fs::create_directory_symlink(external, linked);
    rejects([&] { (void)invoke(linked, {}); }, "unsafe output directory");
    const auto destination = work / "unsafe-target";
    write(external / "keep", "DO NOT TOUCH\n"); fs::create_directories(destination / "docs");
    fs::create_symlink(external / "keep", destination / "docs/FLOORPLAN.md");
    rejects([&] { (void)invoke(destination, {}); }, "symlink output refused");
    fs::create_symlink(external / "absent", destination / "floorplan.json");
    rejects([&] { (void)invoke(destination, {"--export"}); }, "symlink output refused");
    const auto hard = work / "hard"; fs::create_directories(hard / "docs");
    fs::create_hard_link(external / "keep", hard / "docs/FLOORPLAN.svg");
    rejects([&] { (void)invoke(hard, {}); }, "unshared regular file");
    const auto directory = work / "directory"; fs::create_directories(directory / "floorplan.json");
    rejects([&] { (void)invoke(directory, {"--export"}); }, "unshared regular file");
    const auto ledger = work / "bad-ledger"; fs::create_directories(ledger / "reports");
    fs::create_symlink(external / "keep", ledger / "reports/compose_ledger.json");
    rejects([&] { (void)run({"compose", "--repo", repo.string(), "--project", project.string(), "-o", ledger.string()}); }, "symlink output refused");
    const auto board = work / "unsafe-board"; fs::create_directories(board / "manufacturing");
    fs::create_symlink(external / "keep", board / "manufacturing/ASSEMBLY.md");
    rejects([&] { (void)run({"compose", "--repair", "--repo", repo.string(), "--project", project.string(), "-o", board.string()}); }, "symlink in board output tree");
    require(read(external / "keep") == "DO NOT TOUCH\n", "output preflight preserves outside bytes");
    require(snapshot(project) == original, "all preflight failures precede authoring or spec edits");
}
fs::path mirror(const fs::path& repo, const fs::path& work) {
    const auto input = repo / "devkit_mini", output = work / "input/devkit_mini";
    for (const auto& entry : fs::recursive_directory_iterator(input)) {
        if (!entry.is_regular_file()) continue;
        const auto relative = entry.path().lexically_relative(input);
        const auto top = *relative.begin();
        if (top != "subsystems" && top != "research" && top != "reports" && relative.has_parent_path()) continue;
        if (entry.path().extension() != ".json" && entry.path().extension() != ".md" && entry.path().extension() != ".cir") continue;
        write(output / relative, read(entry.path()));
    }
    // Poison ALL canonical IR and cached board transports. A live geometry
    // command must use native factories and new private extraction instead.
    for (const auto& entry : fs::recursive_directory_iterator(output / "subsystems"))
        if (entry.path().filename() == "circuit.json") write(entry.path(), "NOT CANONICAL JSON\n");
    for (const auto* name : {"Zynq_Carrier.kicad_sch", "Zynq_Carrier.kicad_pcb", "board.net", "board.xml"}) write(output / name, "POISON CACHED TRANSPORT\n");
    return output;
}
void live(const fs::path& repo, const fs::path& work, const JsonNode& reference, bool apply) {
    const auto kicad = executable("kicad-cli");
    const auto project = mirror(repo, work);
    const auto before = snapshot(project);
    const auto fanout = read(repo / "carrier/reports/fanout_baseline.json");
    auto invoke = [&](const std::string& name, const fs::path& output, const std::vector<std::string>& extra) {
        std::vector<std::string> args{name, "--repo", repo.string(), "--project", project.string(), "--output", output.string()};
        if (std::find(extra.begin(), extra.end(), "--kicad-cli") == extra.end()) {
            args.push_back("--kicad-cli"); args.push_back(kicad.string());
        }
        args.insert(args.end(), extra.begin(), extra.end());
        const auto result = run(args); write(output / "command.txt", result.second); return result;
    };
    const auto docs = invoke("floorplan", work / "documents", {});
    require(docs.first == 0 && docs.second.find(field(reference, "floorplan_notice").string_value) != docs.second.npos, "legacy floorplan notice");
    require(read(work / "documents/docs/FLOORPLAN.svg").find("<svg") != std::string::npos, "actual SVG publication");
    require(!read(work / "documents/docs/FLOORPLAN.md").empty(), "actual Markdown publication");
    const auto exported = invoke("floorplan", work / "exported", {"--export"});
    require(exported.first == 0 && exported.second.find(field(reference, "export_notice").string_value) != exported.second.npos, "legacy export notice");
    const auto spec = load_floorplan_spec((work / "exported/floorplan.json").string());
    require(spec && !spec->names().empty(), "export parses as real editable floorplan seed");
    const auto dry = invoke("compose", work / "dry", {"--repair", "--dry-run", "--allow-intent", "pd_input:N->S"});
    require(dry.first == 0 && dry.second.find("applying") == dry.second.npos, "healthy dry-run does not force intent edit");
    require(!fs::exists(work / "dry/Zynq_Carrier.kicad_pcb"), "dry-run never runs board publication");
    const auto measured = invoke("compose", work / "measure", {"--measure"});
    require(measured.first == 0 && measured.second.find("100x100") != measured.second.npos, "fresh real devkit dimensions");
    const auto ledger = parse_json_file((work / "measure/reports/compose_ledger.json").string());
    const auto& record = field(ledger.array_value.back(), "ledger");
    require(field(field(record, "flow_gate"), "ok").bool_value, "real placement-flow gate passes");
    require(field(field(record, "law5"), "ok").bool_value, "real ratsnest gate passes");
    require(snapshot(project) == before, "floorplan/export/measure/dry-run preserve every source byte and cached poison");
    require(!fs::exists(work / "documents/Zynq_Carrier.kicad_sch"), "extraction remains private");
    const auto error_output = work / "missing-tool";
    rejects([&] { (void)invoke("floorplan", error_output, {"--kicad-cli", "/missing/kicad-cli"}); }, "cannot execute /missing/kicad-cli");
    require(!fs::exists(error_output), "failed extraction publishes nothing");
    if (!apply) return;
    // A real, newly authored advisory contract makes a repair opportunity.
    // It is deliberately NOT promoted to a hard gate or supplied as a verdict.
    write(project / "subsystems/power_mon/placement_contract.json", R"({
 "contract":"geometry-cli mutation", "sheet":"power_mon", "structures":[],
 "external":{"near_max":[{"other":"uart_bridge","max_mm":0.01,"basis":"negative live-input contract test"}]}
})");
    const auto candidates = invoke("compose", work / "candidates", {"--repair", "--dry-run"});
    require(candidates.first == 0 && candidates.second.find("AddPull power_mon") != candidates.second.npos, "real mutated contract produces actual candidates");
    require(candidates.second.find("predicted agg-hard-margin") != candidates.second.npos, "at least one actual candidate is eligible");
    const auto spec_bytes = read(project / "floorplan.json");
    // Bounded negative proof, NOT full-board acceptance: the actual compiler
    // is unavailable in both cases and its mandatory audit must fail closed.
    // KiCad is selected by its trusted absolute path; real ngspice stays usable.
    WithoutAuditCompiler tools(work / "tools-without-audit-compiler");
    // Two additional independent full-pipeline hard failures after an eligible edit:
    // missing local package collateral, then a zero-ceiling fallback ratchet.
    const auto collateral = project / "subsystems/power_som/README.md";
    fs::rename(collateral, project / "retained-power-som-README.txt");
    for (const auto* failure : {"carrier_structure", "fallbacks"}) {
        if (std::string(failure) == "fallbacks") {
            fs::rename(project / "retained-power-som-README.txt", collateral);
            write(project / "reports/fallback_baseline.json", "{\"counts\":{}}\n");
        }
        const auto unchanged = snapshot(project);
        const auto output = work / (std::string("apply-") + failure);
        const auto result = invoke("compose", output, {"--repair", "--no-render"});
        require(result.first == 1, "complete board failure must fail compose apply");
        require(result.second.find("compose: applying ") != result.second.npos, "negative proof reached actual apply, not rejected prediction");
        require(result.second.find("board build FAILED") != result.second.npos && result.second.find("REVERTED") != result.second.npos, "full board rejection invokes rollback");
        require(result.second.find("ACCEPTED") == result.second.npos, "no fake acceptance after full-board failure");
        require(read(project / "floorplan.json") == spec_bytes, "exact original spec restored");
        require(snapshot(project) == unchanged, "isolated board run changes no source or baseline bytes");
        const auto verdict = parse_json_file((output / "reports/board_verdicts.json").string());
        require(!field(verdict, "board_ok").bool_value, "actual full-board verdict fails");
        const auto& gates = field(verdict, "gates");
        require(field(field(gates, failure), "status").string_value == "FAIL" && field(field(gates, failure), "mandatory").bool_value, "deliberately mutated mandatory gate is not waived");
        require(field(field(gates, "native_policy"), "status").string_value == "PASS", "apply ran reviewed native policy");
        const auto& audit = field(gates, "quantize_census");
        require(field(audit, "status").string_value == "FAIL" && field(audit, "mandatory").bool_value, "missing trusted compiler is a mandatory failure");
        require(field(audit, "report").string_value.find("cannot execute clang++") != std::string::npos, "real compiler spawn failed; no supplied gate result");
        for (const auto* gate : {"placement_contract", "placement_flow", "pcb_drc", "quantize_census", "ledger"})
            require(object_field(gates, gate) != nullptr, "full pipeline includes " + std::string(gate));
        require(fs::is_regular_file(output / "Zynq_Carrier.kicad_pcb"), "full native board artifacts exist even after rejection");
        require(read(repo / "carrier/reports/fanout_baseline.json") == fanout, "isolated repair never ratchets shared carrier baseline");
    }
}
}

int main(int argc, char** argv) {
    try {
        if (argc < 3 || argc > 4) throw std::runtime_error("usage: geometry_cli_contracts REPO PRIVATE_SCRATCH_OR_--system-temp [--live-kicad|--live-apply]");
        const auto repo = fs::canonical(argv[1]);
        // In-tree native builds are intentionally forbidden geometry output
        // roots. Exercise destination safety outside the source tree instead
        // of weakening that production boundary for the test runner.
        const auto base = std::string(argv[2]) == "--system-temp"
            ? fs::canonical(fs::temp_directory_path()) : fs::absolute(argv[2]);
        fs::create_directories(base);
        auto pattern = (base / "geometry-contracts-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "private test directory"); const fs::path work = pattern;
        const auto reference = parse_json_file((repo / "native/tests/data/geometry_cli/legacy_cli.json").string());
        parser(reference); safety(repo, work);
        if (argc == 4) {
            const std::string mode = argv[3]; require(mode == "--live-kicad" || mode == "--live-apply", "unknown live mode");
            live(repo, work, reference, mode == "--live-apply");
        }
        std::cout << "geometry CLI contracts: " << checks << " passed; proof " << work << '\n'; return 0;
    } catch (const std::exception& ex) { std::cerr << "geometry CLI FAILED after " << checks << ": " << ex.what() << '\n'; return 1; }
}
