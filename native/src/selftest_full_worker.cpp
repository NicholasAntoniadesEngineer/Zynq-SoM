#include "selftest_full_internal.hpp"
#include "schgen/process.hpp"

namespace schgen {
using namespace selftesting;

JsonNode selftest_worker_request(const SelftestBuilt& b, SymbolLibrary& lib) {
    std::set<std::string> ids;
    for (const auto& p : b.circuit.parts) ids.insert(p.lib_id);
    for (const auto& p : b.page.placement.powers) ids.insert(p.lib_id);
    auto symbols = arr();
    for (const auto& id : ids) symbols.array_value.push_back(obj({
        {"lib_id", j(id)}, {"raw", j(sexpr_dumps(lib.get(id).raw))}}));
    return obj({{"schema", j("schgen.selftest-worker/1")},
        {"circuit", circuit_json(b.circuit)}, {"symbols", symbols}});
}

std::string selftest_worker_emit(const JsonNode& request, const fs::path& outdir) {
    object_shape(request, {"schema", "circuit", "symbols"}, "selftest worker request");
    if (string(member(request, "schema")) != "schgen.selftest-worker/1")
        throw std::invalid_argument("selftest worker: unsupported schema");
    const auto c = parse_circuit_ir(member(request, "circuit"));
    std::vector<SymbolDef> defs;
    std::set<std::string> ids;
    for (const auto& s : array_items(member(request, "symbols"))) {
        object_shape(s, {"lib_id", "raw"}, "selftest worker symbol");
        const auto id = string(member(s, "lib_id"));
        if (!ids.insert(id).second) throw std::invalid_argument("selftest worker: duplicate symbol " + id);
        auto def = parse_symbol(id, sexpr_loads(string(member(s, "raw"))));
        for (const auto& p : def.pins)
            if (!symbol_on_grid(p.x) || !symbol_on_grid(p.y))
                throw SymbolError("selftest worker: off-grid symbol " + id);
        defs.push_back(std::move(def));
    }
    // No library search paths: omitted definitions must fail, never resolve a
    // potentially newer file or use a catalog from the parent process.
    SymbolLibrary empty(std::vector<fs::path>{});
    auto lib = empty.with_definitions(defs);
    return build_selftest_sheet(c, lib, outdir).text;
}

SelftestDeterminism selftest_hashseed_determinism(const CircuitSheetIr& c,
        SymbolLibrary& lib, const fs::path& scratch, const SelftestFullOptions& options) {
    if (options.worker_command.empty())
        throw std::invalid_argument("selftest requires a native worker command for cross-process determinism");
    if (options.worker_timeout.count() <= 0)
        throw std::invalid_argument("selftest worker timeout must be positive");
    const auto base = build_selftest_sheet(c, lib, scratch / "hs-input");
    const auto request = scratch / "worker-request.json";
    publish(request, json_text(selftest_worker_request(base, lib)) + "\n");
    const auto env = find_executable("env");
    if (!env) throw ProcessError("selftest: cannot find env for isolated hash-seed worker");
    std::vector<std::string> outputs;
    for (const auto* seed : {"0", "987654321"}) {
        const auto directory = scratch / (std::string("hs") + seed);
        // Existing outputs cannot masquerade as a successful child build.
        if (fs::exists(directory))
            return {false, "worker output directory already exists: " + directory.string()};
        std::vector<std::string> argv = {env->string(), std::string("PYTHONHASHSEED=") + seed};
        argv.insert(argv.end(), options.worker_command.begin(), options.worker_command.end());
        argv.push_back(fs::absolute(request).string());
        argv.push_back(fs::absolute(directory).string());
        ProcessResult result;
        try { result = run_process(argv, options.worker_timeout); }
        catch (const ProcessError& e) {
            return {false, "subprocess build failed (seed " + std::string(seed) + "): " + e.what()};
        }
        if (result.exit_code != 0)
            return {false, "subprocess build failed (seed " + std::string(seed) + "): exit " +
                std::to_string(result.exit_code) + ": " + shorten(result.stderr_text, 300)};
        const auto file = directory / (c.name + ".kicad_sch");
        if (result.stdout_text.empty() || !fs::is_regular_file(file) || read(file) != result.stdout_text)
            return {false, "subprocess build failed (seed " + std::string(seed) + "): missing/empty/inconsistent emitted schematic"};
        outputs.push_back(std::move(result.stdout_text));
    }
    if (outputs[0] != outputs[1])
        return {false, "HASH-SEED DRIFT (set/dict iteration leaks into output):\n    " +
            drift_diff(outputs[0], outputs[1], "seed-0", "seed-987654321")};
    if (outputs[0] != base.text)
        return {false, "worker output differs from parent build:\n    " +
            drift_diff(base.text, outputs[0], "parent", "worker")};
    return {true, "byte-identical across PYTHONHASHSEED {0, 987654321}"};
}
} // namespace schgen
