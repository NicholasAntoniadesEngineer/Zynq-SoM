// Diagnostic only. Optional integration (no production/CMake edits required):
// add_executable(schgen_compact_stage_profile tests/compact_stage_profile.cpp)
// target_link_libraries(schgen_compact_stage_profile PRIVATE schgen_core)
// target_compile_options(schgen_compact_stage_profile PRIVATE
//     -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
#include "schgen/board_pcb.hpp"
#include "schgen/catalog.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/validation.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include <charconv>
#include <cmath>
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
    std::filesystem::path schematic;
    std::string project = "carrier", kicad = "kicad-cli", compact, inputs = "prepared";
    int runs = 1;
    bool constraint_first = false;
    bool edge_translation = false;
    std::optional<int> interior_order;
    std::optional<FloorplanPoint> outline;
    std::optional<FloorplanPoint> initial_outline;
};
void help() {
    std::cout << "compact_stage_profile --repo ROOT --project NAME --compact-search off|on|both\n"
        "  [--runs N] [--input-mode cold|prepared] [--kicad-cli PATH]\n"
        "  [--schematic PATH] (use a freshly qualified schematic instead of the stored project output)\n"
        "  [--constraint-first off|on] (opt-in candidate, requires --compact-search on)\n"
        "  [--interior-order 0|1|2|3] (single connectivity/area/scarcity/constraint order, no order retries)\n"
        "  [--edge-translation off|on] (opt-in bounded edge repair, requires --compact-search on)\n"
        "  [--outline-mm WIDTHxHEIGHT] (explicit diagnostic outline; skips automatic sizing search)\n"
        "  [--initial-outline-mm WIDTHxHEIGHT] (validated starting candidate for automatic sizing)\n"
        "cold: reload/validate circuits, relink, re-extract netlist and resolve inputs per repetition.\n"
        "prepared: load once; reuse only parsed PcbPlacementInput across repetitions.\n"
        "both: off then on using the same compact-capable input each repetition (fixed order; not randomized).\n"
        "on/both resolve ownership inputs before trials; off alone uses default-only input preparation.\n"
        "Neither mode reuses zones, floorplans or placed models; OS/catalog caches are not flushed.\n"
        "Construction timings exclude the subsequent placement/flow/composition diagnostics.\n"
        "NO ACCEPTANCE: no full board gates, source audit, DRC or KiCad/3D renders.\n"
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
        else if (arg == "--schematic") out.schematic = value;
        else if (arg == "--project") out.project = value;
        else if (arg == "--kicad-cli") out.kicad = value;
        else if (arg == "--compact-search") out.compact = value;
        else if (arg == "--input-mode") out.inputs = value;
        else if (arg == "--interior-order") {
            if(value.size()!=1 || value[0]<'0' || value[0]>'3')throw std::invalid_argument("interior-order must be 0|1|2|3");
            out.interior_order=value[0]-'0';
        }
        else if (arg == "--outline-mm"||arg=="--initial-outline-mm") {
            const auto separator=value.find('x');
            if(separator==std::string::npos || separator==0 || separator+1==value.size() ||
               value.find('x',separator+1)!=std::string::npos)
                throw std::invalid_argument("outline-mm must be WIDTHxHEIGHT");
            const auto dimension=[](const std::string& text) {
                double v=0;const auto parsed=std::from_chars(text.data(),text.data()+text.size(),v);
                if(parsed.ec!=std::errc{} || parsed.ptr!=text.data()+text.size() || !std::isfinite(v) || v<=0)
                    throw std::invalid_argument("outline-mm dimensions must be finite positive numbers");
                return v;
            };
            const FloorplanPoint dimensions{dimension(value.substr(0,separator)),dimension(value.substr(separator+1))};
            if(arg=="--outline-mm")out.outline=dimensions;else out.initial_outline=dimensions;
        }
        else if (arg == "--constraint-first") {
            if (value != "on" && value != "off") throw std::invalid_argument("constraint-first must be off|on");
            out.constraint_first = value == "on";
        }
        else if (arg == "--edge-translation") {
            if(value!="on"&&value!="off")throw std::invalid_argument("edge-translation must be off|on");
            out.edge_translation=value=="on";
        }
        else if (arg == "--runs") {
            const auto result = std::from_chars(value.data(), value.data() + value.size(), out.runs);
            if (result.ec != std::errc{} || result.ptr != value.data() + value.size() || out.runs < 1 || out.runs > 1000)
                throw std::invalid_argument("runs must be an integer in [1,1000]");
        } else throw std::invalid_argument("unknown option: " + arg);
    }
    if (out.repo.empty() || (out.compact != "off" && out.compact != "on" && out.compact != "both"))
        throw std::invalid_argument("--repo and explicit --compact-search off|on|both required");
    if (out.inputs != "cold" && out.inputs != "prepared") throw std::invalid_argument("input-mode must be cold|prepared");
    if (out.constraint_first && out.compact != "on")
        throw std::invalid_argument("constraint-first requires --compact-search on");
    if(out.edge_translation&&out.compact!="on")throw std::invalid_argument("edge-translation requires --compact-search on");
    if(out.outline&&out.initial_outline)throw std::invalid_argument("initial-outline-mm cannot be combined with outline-mm");
    if(out.interior_order&&out.constraint_first)throw std::invalid_argument("single interior-order conflicts with constraint-first portfolio");
    return out;
}
struct LoadResult {
    PcbPlacementInput input;
    std::vector<std::pair<std::string, double>> times;
    std::size_t circuits = 0;
};
LoadResult load(const ProjectPaths& paths, const NetlistExtractOptions& extraction, bool compact_capable,
                const std::filesystem::path& schematic) {
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
    const auto source=schematic.empty()?paths.project_root / "Zynq_Carrier.kicad_sch":schematic;
    std::cout<<"input schematic="<<source.string()<<" freshness=caller_responsibility\n";
    const auto nets = extract_netlist(source, extraction);
    tick("netlist_extract");
    BoardInputOptions options;
    // Compact mode has real input requirements, not just a solver toggle.
    // Resolve them here so profiling cannot silently omit owned alternatives.
    options.compact_search = compact_capable;
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
PcbPlacementInput trial_input(const PcbPlacementInput& source,bool compact,
                             const std::optional<FloorplanPoint>& outline) {
    auto input=source;
    input.floorplan.compact_search=compact;
    if(outline) {
        if(!input.floorplan.spec)input.floorplan.spec.emplace();
        input.floorplan.spec->outline=outline;
    }
    return input;
}
std::string trial(const PcbPlacementInput& source, bool compact, int run, int generation,
                  bool constraint_first = false,const std::optional<FloorplanPoint>& outline=std::nullopt,bool edge_translation=false,
                  const std::optional<FloorplanPoint>& initial_outline=std::nullopt,
                  const std::optional<int>& interior_order=std::nullopt) {
    const auto copy_start = Clock::now();
    auto input = trial_input(source,compact,outline);
    const auto copy_seconds = seconds(copy_start);
    // Fresh observers for every trial. Existing non-diagnostic policy is retained.
    if (input.experiment || input.floorplan.experiment)
        throw std::runtime_error("profile requires inputs without preinstalled experiment observers");
    Profile profile;
    auto floor = std::make_shared<FloorplanExperiment>();
    floor->compact_constraint_first = constraint_first;
    floor->compact_edge_translation = edge_translation;
    floor->initial_outline=initial_outline;
    floor->interior_order=interior_order;
    if(interior_order)std::cout<<"single_interior_order="<<*interior_order<<" alternate_order_retries=disabled\n";
    std::size_t edge_candidates=0,edge_repairs=0;
    std::vector<FloorplanReseatObservation> reseats;
    floor->reseat_completed=[&](const auto& row){reseats.push_back(row);};
    const auto print_reseats=[&]{
        for(const auto& r:reseats)
            std::cout<<"reseat width="<<r.w<<" height="<<r.h<<" incoming="<<r.incoming
                     <<" displaced="<<r.displaced<<" incoming_seated="<<r.incoming_seated
                     <<" displaced_reseated="<<r.displaced_reseated<<" punch_free="<<r.punch_free
                     <<" order="<<r.order<<'\n';
    };
    floor->edge_translation_completed=[&](std::size_t candidates,char edge,double) {
        edge_candidates+=candidates;edge_repairs+=edge!='\0';
    };
    floor->attempt_completed = [&](const auto& row) { profile.attempts.add(row); };
    floor->unscoped_estimate = [&](double) { ++profile.attempts.unscoped_estimates; };
    auto pcb = std::make_shared<PcbPlacementExperiment>();
    pcb->checkpoint = [&](const auto& row) { profile.checkpoint(row); };
    input.floorplan.experiment = floor;
    input.experiment = pcb;
    std::cout << "trial run=" << run << " generation=" << generation << " compact_search=" << compact
        << " constraint_first=" << constraint_first
        << " edge_translation=" << edge_translation
        << " input_copy_seconds=" << copy_seconds << " status=started\n" << std::flush;
    if(outline)std::cout<<"outline_override width_mm="<<outline->first<<" height_mm="<<outline->second
                        <<" automatic_sizing=disabled source_policy_otherwise_unchanged=1\n"<<std::flush;
    if(initial_outline)std::cout<<"initial_outline width_mm="<<initial_outline->first<<" height_mm="<<initial_outline->second
                               <<" automatic_sizing=enabled seed_requires_validation=1\n"<<std::flush;
    ExecutionFailureReceipt failure;
    const auto start = Clock::now();
    profile.mark = start;
    PcbPlacementResult result;
    try { result = build_pcb_model(input, &failure); }
    catch (...) {
        print_reseats();
        std::cout<<"edge_search candidates="<<edge_candidates<<" repairs="<<edge_repairs<<'\n';
        std::cout << "trial status=construction_failed elapsed_seconds=" << seconds(start)
            << " completed_outer_attempts=" << profile.attempts.completed
            << " receipt_captured=" << failure.captured << " receipt_unavailable=" << failure.unavailable << '\n';
        if (failure.captured && !failure.unavailable) receipt("failure_prefix", failure.accounting.quantization_engagements);
        throw;
    }
    const auto end = Clock::now();
    std::cout<<"edge_search candidates="<<edge_candidates<<" repairs="<<edge_repairs<<'\n';
    profile.stages.push_back({"model_return_tail", seconds(profile.mark, end),
        profile.attempts.completed - profile.previous_attempts, profile.attempts.packed - profile.previous_packed, 0});
    const auto model_seconds = seconds(start, end);
    const auto emit_start = Clock::now();
    const auto emission = render_pcb(result.model, pcb_emit_policy(input.floorplan.project));
    const auto emit_seconds = seconds(emit_start);
    const auto hash = pcb_sha256(emission.pcb);
    const auto accounting = pcb_placement_accounting(result);
    print_reseats();
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
    for(const auto& d:result.floorplan.plan.accounting.decisions)if(d.name=="sizing_winner") {
        std::cout<<"sizing_winner";
        for(const auto& [name,value]:d.inputs){std::cout<<' '<<name<<'=';scalar(value);}
        std::cout<<'\n';
    }
    receipt("zone_subset_of_model", result.zone_accounting.quantization_engagements);
    receipt("floorplan_includes_zone", result.floorplan.plan.accounting.quantization_engagements);
    receipt("placement_only", result.placement_accounting.quantization_engagements);
    receipt("model_total", accounting.quantization_engagements);
    receipt("pcb_text_emit_only", emission.quantization_engagements);
    std::cout << "fallback model_total=" << accounting.fallback_events.size()
        << " pcb_text_emit_only=" << emission.fallback_events.size() << '\n';
    std::map<std::string, std::size_t> fallback_counts;
    for (const auto& name : accounting.fallback_events) ++fallback_counts[name];
    for (const auto& [name, count] : fallback_counts)
        std::cout << "fallback_count name=" << name << " count=" << count << '\n';
    const auto diagnostic_start = Clock::now();
    const auto gates = check_pcb_placement_gates(input, result.model);
    std::cout << "postconstruction_diagnostic seconds=" << seconds(diagnostic_start)
        << " placement_contract_ok=" << gates.placement_contract.ok
        << " placement_flow_ok=" << gates.placement_flow.ok
        << " hard_red=" << gates.composition.hard_red
        << " hard_margin_min=" << gates.composition.hard_margin_min
        << " hard_margin_sum=" << gates.composition.hard_margin_sum << '\n';
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
            if (!prepared || options.inputs == "cold") {
                prepared = load(paths, extraction, options.compact != "off", options.schematic);
                print_load(*prepared, run);
                std::cout << "input compact_capable=" << (options.compact != "off")
                    << " owned_groups=" << prepared->input.owned_groups.size() << '\n';
            }
            const int generation = options.inputs == "prepared" ? 1 : run;
            for (const bool compact : {false, true}) {
                if ((compact && options.compact == "off") || (!compact && options.compact == "on")) continue;
                const auto hash = trial(prepared->input, compact, run, generation, options.constraint_first,options.outline,options.edge_translation,options.initial_outline,options.interior_order);
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
