// Diagnostic only. Optional integration (no production/CMake edits required):
// add_executable(schgen_compact_stage_profile tests/compact_stage_profile.cpp)
// target_link_libraries(schgen_compact_stage_profile PRIVATE schgen_core)
// target_compile_options(schgen_compact_stage_profile PRIVATE
//     -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
#include "schgen/board_pcb.hpp"
#include "schgen/catalog.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/validation.hpp"
#include <charconv>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <set>
#include <tuple>

namespace {
using namespace schgen;
using Clock = std::chrono::steady_clock;
double seconds(Clock::time_point start, Clock::time_point end = Clock::now()) {
    return std::chrono::duration<double>(end - start).count();
}
struct Options {
    std::filesystem::path repo;
    std::string project = "carrier", kicad = "kicad-cli", compact, inputs = "prepared";
    int runs = 1;
};
void help() {
    std::cout << "compact_stage_profile --repo ROOT --project NAME --compact-search off|on|both\n"
        "  [--runs N] [--input-mode cold|prepared] [--kicad-cli PATH]\n"
        "cold: reload/validate circuits, relink, re-extract netlist and resolve inputs per repetition.\n"
        "prepared: load once; reuse only parsed PcbPlacementInput across repetitions.\n"
        "both: off then on on the same input object each repetition (fixed order; not randomized).\n"
        "Neither mode reuses zones, floorplans or placed models; OS/catalog caches are not flushed.\n"
        "Construction only, NO ACCEPTANCE: no board gates, source audit, DRC or KiCad/3D renders.\n"
        "Normal in-memory floorplan documents and PCB text emission are included.\n";
}
Options parse(int argc, char** argv) {
    Options out;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (!seen.insert(arg).second) throw std::invalid_argument("duplicate option: " + arg);
        if (i + 1 == argc) throw std::invalid_argument("missing value: " + arg);
        const std::string value = argv[++i];
        if (arg == "--repo") out.repo = value;
        else if (arg == "--project") out.project = value;
        else if (arg == "--kicad-cli") out.kicad = value;
        else if (arg == "--compact-search") out.compact = value;
        else if (arg == "--input-mode") out.inputs = value;
        else if (arg == "--runs") {
            const auto result = std::from_chars(value.data(), value.data() + value.size(), out.runs);
            if (result.ec != std::errc{} || result.ptr != value.data() + value.size() || out.runs < 1 || out.runs > 1000)
                throw std::invalid_argument("runs must be an integer in [1,1000]");
        } else throw std::invalid_argument("unknown option: " + arg);
    }
    if (out.repo.empty() || (out.compact != "off" && out.compact != "on" && out.compact != "both"))
        throw std::invalid_argument("--repo and explicit --compact-search off|on|both required");
    if (out.inputs != "cold" && out.inputs != "prepared") throw std::invalid_argument("input-mode must be cold|prepared");
    return out;
}
struct LoadResult {
    PcbPlacementInput input;
    std::vector<std::pair<std::string, double>> times;
    std::size_t circuits = 0;
};
LoadResult load(const ProjectPaths& paths, const NetlistExtractOptions& extraction) {
    // Same sequence and providers as prepare_board_pcb / pcb-stage. In particular
    // use the real project schematic extraction, not synthetic/fixture connectivity.
    LoadResult out;
    auto mark = Clock::now();
    auto tick = [&](const std::string& name) {
        const auto now = Clock::now(); out.times.emplace_back(name, seconds(mark, now)); mark = now;
    };
    const auto circuits = load_project_circuits(paths);
    out.circuits = circuits.size();
    tick("circuit_load");
    SymbolLibrary library(paths.repository_root);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& source : circuits) {
        validate_circuit(source.circuit, library);
        sheets.push_back(source.circuit);
    }
    tick("circuit_validate");
    const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
        parse_json_file((paths.project_root / "som_mapping.json").string()));
    if (!link.ok()) throw ProjectError(link.report());
    tick("link");
    const auto nets = extract_netlist(paths.project_root / "Zynq_Carrier.kicad_sch", extraction);
    tick("netlist_extract");
    BoardInputOptions options;
    options.compact_search = false; // Set explicitly again on each trial copy.
    out.input = load_board_inputs(paths, circuits, link, nets, options);
    tick("board_input_resolve");
    return out;
}
void print_load(const LoadResult& input, int generation) {
    for (const auto& [name, elapsed] : input.times)
        std::cout << "input generation=" << generation << " phase=" << name << " seconds=" << elapsed << '\n';
    std::cout << "input generation=" << generation << " circuits=" << input.circuits
        << " nets=" << input.input.netlist.size() << " footprints=" << input.input.footprints.size() << '\n';
}
struct AttemptCounts {
    std::size_t completed = 0, packed = 0, rejected = 0, punch_free = 0, unscoped_estimates = 0;
    std::set<std::tuple<double, double, bool>> outlines;
    void add(const FloorplanAttemptObservation& row) {
        ++completed;
        row.packed ? ++packed : ++rejected;
        if (row.punch_free) ++punch_free;
        outlines.emplace(row.w, row.h, row.punch_free);
    }
};
struct StageRow {
    std::string stage;
    double seconds;
    std::size_t attempts, packed, instances;
};
struct Profile {
    AttemptCounts attempts;
    std::vector<StageRow> stages;
    Clock::time_point mark;
    std::size_t previous_attempts = 0, previous_packed = 0;
    void checkpoint(const PcbPlacementObservation& row) {
        const auto now = Clock::now();
        stages.push_back({row.stage, seconds(mark, now), attempts.completed - previous_attempts,
            attempts.packed - previous_packed, row.instances.size()});
        previous_attempts = attempts.completed; previous_packed = attempts.packed; mark = now;
    }
};
void receipt(const std::string& scope, const QuantizationCounts& counts) {
    for (const auto& [name, n] : counts)
        std::cout << "receipt scope=" << scope << " operation=" << name << " calls=" << n << '\n';
}
void scalar(const JsonNode& value) {
    if (value.kind == JsonKind::Number) std::cout << value.number_value;
    else if (value.kind == JsonKind::String) std::cout << std::quoted(value.string_value);
    else throw std::runtime_error("unexpected outline tally type");
}
std::string trial(const PcbPlacementInput& source, bool compact, int run, int generation) {
    const auto copy_start = Clock::now();
    auto input = source;
    input.floorplan.compact_search = compact;
    const auto copy_seconds = seconds(copy_start);
    // Fresh observers for every trial. Existing non-diagnostic policy is retained.
    if (input.experiment || input.floorplan.experiment)
        throw std::runtime_error("profile requires inputs without preinstalled experiment observers");
    Profile profile;
    auto floor = std::make_shared<FloorplanExperiment>();
    floor->attempt_completed = [&](const auto& row) { profile.attempts.add(row); };
    floor->unscoped_estimate = [&](double) { ++profile.attempts.unscoped_estimates; };
    auto pcb = std::make_shared<PcbPlacementExperiment>();
    pcb->checkpoint = [&](const auto& row) { profile.checkpoint(row); };
    input.floorplan.experiment = floor;
    input.experiment = pcb;
    std::cout << "trial run=" << run << " generation=" << generation << " compact_search=" << compact
        << " input_copy_seconds=" << copy_seconds << " status=started\n" << std::flush;
    ExecutionFailureReceipt failure;
    const auto start = Clock::now();
    profile.mark = start;
    PcbPlacementResult result;
    try { result = build_pcb_model(input, &failure); }
    catch (...) {
        std::cout << "trial status=construction_failed elapsed_seconds=" << seconds(start)
            << " completed_outer_attempts=" << profile.attempts.completed
            << " receipt_captured=" << failure.captured << " receipt_unavailable=" << failure.unavailable << '\n';
        if (failure.captured && !failure.unavailable) receipt("failure_prefix", failure.accounting.quantization_engagements);
        throw;
    }
    const auto end = Clock::now();
    profile.stages.push_back({"model_return_tail", seconds(profile.mark, end),
        profile.attempts.completed - profile.previous_attempts, profile.attempts.packed - profile.previous_packed, 0});
    const auto model_seconds = seconds(start, end);
    const auto emit_start = Clock::now();
    const auto emission = render_pcb(result.model, pcb_emit_policy(input.floorplan.project));
    const auto emit_seconds = seconds(emit_start);
    const auto hash = pcb_sha256(emission.pcb);
    const auto accounting = pcb_placement_accounting(result);
    std::cout << "trial status=constructed_no_acceptance model_seconds=" << model_seconds
        << " pcb_text_emit_seconds=" << emit_seconds << " construction_seconds=" << model_seconds + emit_seconds
        << " board_w=" << result.model.board_w << " board_h=" << result.model.board_h
        << " top=" << result.model.n_top << " bottom=" << result.model.n_bottom
        << " instances=" << result.model.insts.size() << " pcb_sha256=" << hash << '\n';
    for (const auto& row : profile.stages)
        std::cout << "stage interval_ending=" << row.stage << " seconds=" << row.seconds
            << " outer_attempts=" << row.attempts << " packed=" << row.packed << " snapshot_instances=" << row.instances << '\n';
    const auto& a = profile.attempts;
    std::cout << "work completed_outer_attempts=" << a.completed << " packed=" << a.packed << " rejected=" << a.rejected
        << " punch_free=" << a.punch_free << " distinct_outline_punch_keys=" << a.outlines.size()
        << " unscoped_estimate_callbacks=" << a.unscoped_estimates
        << " internal_order_retry_count=unavailable shape_trial_count=unavailable\n";
    std::size_t pass = 0;
    for (const auto& d : result.floorplan.plan.accounting.decisions) if (d.name == "outline_candidates") {
        std::cout << "sizing pass=" << ++pass;
        for (const auto& [name, value] : d.inputs) { std::cout << ' ' << name << '='; scalar(value); }
        std::cout << '\n';
    }
    receipt("zone_subset_of_model", result.zone_accounting.quantization_engagements);
    receipt("floorplan_includes_zone", result.floorplan.plan.accounting.quantization_engagements);
    receipt("placement_only", result.placement_accounting.quantization_engagements);
    receipt("model_total", accounting.quantization_engagements);
    receipt("pcb_text_emit_only", emission.quantization_engagements);
    std::cout << "fallback model_total=" << accounting.fallback_events.size()
        << " pcb_text_emit_only=" << emission.fallback_events.size() << '\n';
    std::cout << std::flush;
    return hash;
}
} // namespace
int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--help") { help(); return 0; }
        const auto options = parse(argc, argv);
        std::cout << std::setprecision(17);
        std::cout << "CONSTRUCTION_ONLY_NO_ACCEPTANCE input_mode=" << options.inputs
            << " zone_cache=none model_cache=none OS_cache=uncontrolled\n"
            << "Stage intervals include observer snapshot/measurement overhead; not exclusive algorithm timings.\n"
            << "Outer attempt callbacks exclude inner order retries and early sizing filters; sizing ledger reports filters.\n"
            << "Receipt scopes overlap as labelled; do not sum subsets with model_total.\n"
            << "No source audit, full board acceptance, DRC, board publication, or KiCad/3D render performed.\n"
            << "Normal in-memory floorplan documents and PCB text emission are included.\n";
        const auto paths = resolve_project_paths(options.repo, options.project);
        const auto catalog_start = Clock::now();
        if (!open_part_catalog(paths.part_catalog_file.string())) throw ProjectError("cannot open native part catalog");
        std::cout << "catalog_open_once_seconds=" << seconds(catalog_start) << '\n';
        NetlistExtractOptions extraction;
        extraction.kicad_cli = options.kicad;
        std::optional<LoadResult> prepared;
        std::map<bool, std::string> first_hash;
        for (int run = 1; run <= options.runs; ++run) {
            if (!prepared || options.inputs == "cold") { prepared = load(paths, extraction); print_load(*prepared, run); }
            const int generation = options.inputs == "prepared" ? 1 : run;
            for (const bool compact : {false, true}) {
                if ((compact && options.compact == "off") || (!compact && options.compact == "on")) continue;
                const auto hash = trial(prepared->input, compact, run, generation);
                auto [it, inserted] = first_hash.emplace(compact, hash);
                if (!inserted && it->second != hash) throw std::runtime_error("repeat PCB bytes changed; investigate input drift/nondeterminism");
                std::cout << "repeat compact_search=" << compact << " same_as_first=" << (!inserted ? "true" : "first") << '\n';
            }
        }
        std::cout << "PROFILE_COMPLETE_NO_ACCEPTANCE\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "PROFILE_FAILED_NO_ACCEPTANCE: " << error.what() << '\n';
        return 1;
    }
}
