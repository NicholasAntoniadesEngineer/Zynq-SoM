// Diagnostic only. Optional integration (no production/CMake edits required):
// add_executable(schgen_compact_stage_profile tests/compact_stage_profile.cpp)
// target_link_libraries(schgen_compact_stage_profile PRIVATE schgen_core)
// target_compile_options(schgen_compact_stage_profile PRIVATE
//     -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
#include "schgen/board_pcb.hpp"
#include "schgen/catalog.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/legalize.hpp"
#include "schgen/validation.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/pcb_placement_search.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/thermal_via_planning.hpp"
#include "schgen/verification_audits.hpp"
#include "courtyard_area_diagnostic.hpp"
#include <charconv>
#include <cmath>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <tuple>

namespace {
using namespace schgen;
using Clock = std::chrono::steady_clock;
std::size_t nonsearch_events(const std::vector<std::string>& events) {
    return static_cast<std::size_t>(std::count_if(events.begin(),events.end(),
        [](const auto& name){return !is_board_search_effort(name);}));
}
double seconds(Clock::time_point start, Clock::time_point end = Clock::now()) {
    return std::chrono::duration<double>(end - start).count();
}
struct Options {
    std::filesystem::path repo;
    std::filesystem::path schematic;
    std::optional<std::filesystem::path> floorplan_spec;
    std::string project = "carrier", kicad = "kicad-cli", compact, inputs = "prepared";
    int runs = 1;
    bool observers = true;
    bool thermal_trace = false;
    bool constraint_first = false;
    bool edge_translation = false;
    bool edge_feasibility = false;
    bool owned_selection_trace = false;
    bool failed_first_retry = false;
    bool owned_quality_first = false;
    bool shape_area_first = false;
    std::size_t shape_choice_replays=0;
    bool owned_extent_alternatives = false;
    bool owned_face_cohesion = false;
    std::set<std::string> contract_group_face_sheets;
    std::set<std::string> require_bottom_sheets;
    bool contract_group_rotations = false;
    std::optional<FloorplanPoseRetryLimits> reseat_pose_limits;
    std::optional<std::size_t> joint_states;
    std::map<std::string,std::string> owned_shapes, offered_shapes;
    bool multiscale_outline = false;
    std::optional<int> interior_order;
    std::optional<FloorplanPoint> outline;
    std::optional<FloorplanPoint> initial_outline;
    std::vector<std::string> search_strategies;
};
PcbPlacementSearchStrategy search_strategy(const std::string& text) {
    PcbPlacementSearchStrategy result;
    std::set<std::string> seen;
    std::size_t begin=0;
    for(;;) {
        const auto end=text.find('+',begin);
        const auto token=text.substr(begin,end==std::string::npos?end:end-begin);
        if(!seen.insert(token).second)throw std::invalid_argument("duplicate search-strategy component: "+token);
        if(token=="extent")result.owned_extent_alternatives=true;
        else if(token=="vertical")result.vertical_compaction=true;
        else if(token=="granular-minor")result.granular_minor_occupancy=true;
        else if(token=="rotations")result.contract_group_rotations=true;
        else if(token=="area-first"||token=="estimator-first") {
            if(result.shape_area_first)throw std::invalid_argument("conflicting search-strategy rankings");
            result.shape_area_first=token=="area-first";
        } else throw std::invalid_argument("unknown search-strategy component: "+token);
        if(end==std::string::npos)break;
        begin=end+1;
    }
    return result;
}
void help() {
    std::cout << "  [--search-strategy extent|rotations|vertical|granular-minor|area-first|estimator-first] (join with + for combined strategies; repeat; baseline retained; no acceptance)\n";
    std::cout << "    Each strategy starts from baseline settings; repeated options are not cumulative. search_total includes every attempt and screening.\n";
    std::cout << "  [--shape-area-first on|off] (experimental legal-shape envelope ranking; compact on required)\n";
    std::cout << "  [--contract-group-face-sheet SHEET] (repeat for multiple sheets; experimental rigid-group face candidates)\n";
    std::cout << "  [--contract-group-rotations on|off] (requires contract-group-face-sheet)\n";
    std::cout << "  [--reseat-poses N --reseat-frontier N] (failure-only alternative poses; both required)\n";
    std::cout << "  [--reseat-continuations N] (capped first-recovery replays; explicit interior order required)\n";
    std::cout << "  [--reseat-victim-shapes on|off] (additional failure-only shape strategy; explicit interior order required)\n";
    std::cout << "  [--reseat-reuse on|off] (advisory continuation ordering; requires continuations)\n";
    std::cout << "  [--joint-separation-states N] (failure-only coupled-axis search)\n";
    std::cout << "  [--shape-choice-replays N] (failure-only shape/side prefixes per packing call; requires explicit interior order)\n";
    std::cout << "  [--floorplan-spec PATH] (explicit candidate policy; project default is not edited)\n";
    std::cout << "compact_stage_profile --repo ROOT --project NAME --compact-search off|on|both\n"
        "  [--runs N] [--input-mode cold|prepared] [--kicad-cli PATH]\n"
        "  [--observers on|off] (off removes diagnostic callbacks, preserving solver policy and receipts)\n"
        "  [--schematic PATH] (use a freshly qualified schematic instead of the stored project output)\n"
        "  [--constraint-first off|on] (opt-in candidate, requires --compact-search on)\n"
        "  [--interior-order 0|1|2|3] (single connectivity/area/scarcity/constraint order, no order retries)\n"
        "  [--failed-first-retry off|on] (one failed-block-first restart; requires compact on and explicit interior-order)\n"
        "  [--edge-translation off|on] (opt-in bounded edge repair, requires --compact-search on)\n"
        "  [--edge-feasibility off|on] (constraint-aware initial runs, requires --compact-search on)\n"
        "  [--owned-selection-trace off|on] (read-only multi-alternative selection trace)\n"
        "  [--thermal-trace off|on] (postconstruction pad-only stage capacity; requires observers)\n"
        "  [--owned-quality-first off|on] (same-pose same-face quality-first experiment)\n"
        "  [--owned-extent-alternatives off|on] (append bounded extent-first local candidates)\n"
        "  [--owned-face-cohesion off|on] (append initial owner/cap same-face packs)\n"
        "  [--owned-shape SHEET=TAG] (restrict a measured owned candidate; repeat for different sheets)\n"
        "  [--offered-shape SHEET=TAG] (restrict any unique offered tag; no owned-quality claim)\n"
        "  [--require-bottom-sheet SHEET] (compact diagnostic: require an already offered bottom-primary shape)\n"
        "  [--outline-mm WIDTHxHEIGHT] (explicit diagnostic outline; skips automatic sizing search)\n"
        "  [--initial-outline-mm WIDTHxHEIGHT] (validated starting candidate for automatic sizing)\n"
        "  [--multiscale-outline off|on] (local axis/diagonal refinement; can miss smaller grid candidates)\n"
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
        if (!seen.insert(arg).second && arg!="--owned-shape" && arg!="--offered-shape" && arg!="--contract-group-face-sheet" && arg!="--require-bottom-sheet" && arg!="--search-strategy") throw std::invalid_argument("duplicate option: " + arg);
        if (i + 1 == argc) throw std::invalid_argument("missing value: " + arg);
        const std::string value = argv[++i];
        if (arg == "--repo") out.repo = value;
        else if(arg=="--search-strategy") {
            const auto proposed=search_strategy(value);
            for(const auto& prior:out.search_strategies) {
                const auto existing=search_strategy(prior);
                if(proposed.shape_area_first==existing.shape_area_first&&
                   proposed.vertical_compaction==existing.vertical_compaction&&
                   proposed.granular_minor_occupancy==existing.granular_minor_occupancy&&
                   proposed.owned_extent_alternatives==existing.owned_extent_alternatives&&
                   proposed.contract_group_rotations==existing.contract_group_rotations)
                    throw std::invalid_argument("duplicate search-strategy: "+value);
            }
            out.search_strategies.push_back(value);
        }
        else if (arg == "--schematic") out.schematic = value;
        else if (arg == "--floorplan-spec") {
            if(value.empty())throw std::invalid_argument("floorplan-spec requires a nonempty path");
            out.floorplan_spec=value;
        }
        else if (arg == "--project") out.project = value;
        else if(arg=="--shape-choice-replays"){
            std::size_t n=0;const auto parsed=std::from_chars(value.data(),value.data()+value.size(),n);
            if(parsed.ec!=std::errc{}||parsed.ptr!=value.data()+value.size()||!n)
                throw std::invalid_argument("invalid shape-choice replay limit");
            out.shape_choice_replays=n;
        }
        else if(arg=="--joint-separation-states"){
            std::size_t n=0;const auto parsed=std::from_chars(value.data(),value.data()+value.size(),n);
            if(parsed.ec!=std::errc{}||parsed.ptr!=value.data()+value.size()||!n||n>std::numeric_limits<std::size_t>::max()/2)
                throw std::invalid_argument("invalid joint separation state limit");
            out.joint_states=n;
        }
        else if(arg=="--reseat-victim-shapes") {
            if(value!="on"&&value!="off")throw std::invalid_argument("reseat-victim-shapes must be on|off");
            if(!out.reseat_pose_limits)out.reseat_pose_limits.emplace();
            out.reseat_pose_limits->victim_shapes=value=="on";
        }
        else if(arg=="--reseat-reuse") {
            if(value!="on"&&value!="off")throw std::invalid_argument("reseat-reuse must be on|off");
            if(!out.reseat_pose_limits)out.reseat_pose_limits.emplace();
            out.reseat_pose_limits->reuse_continuation=value=="on";
        }
        else if(arg=="--reseat-poses"||arg=="--reseat-frontier"||arg=="--reseat-continuations") {
            std::size_t n=0;const auto parsed=std::from_chars(value.data(),value.data()+value.size(),n);
            if(parsed.ec!=std::errc{}||parsed.ptr!=value.data()+value.size()||!n)
                throw std::invalid_argument("reseat limits must be positive integers");
            if(!out.reseat_pose_limits)out.reseat_pose_limits.emplace();
            if(arg=="--reseat-poses")out.reseat_pose_limits->poses=n;
            else if(arg=="--reseat-frontier")out.reseat_pose_limits->frontier_nodes=n;
            else out.reseat_pose_limits->continuations=n;
        }
        else if(arg=="--contract-group-rotations") {
            if(value!="on"&&value!="off")throw std::invalid_argument("contract-group-rotations must be on|off");
            out.contract_group_rotations=value=="on";
        }
        else if(arg=="--contract-group-face-sheet") {
            if(value.empty())throw std::invalid_argument("contract-group-face-sheet requires a sheet");
            if(!out.contract_group_face_sheets.insert(value).second)throw std::invalid_argument("duplicate contract-group-face-sheet: "+value);
        }
        else if (arg == "--kicad-cli") out.kicad = value;
        else if (arg == "--compact-search") out.compact = value;
        else if (arg == "--input-mode") out.inputs = value;
        else if (arg == "--observers") {
            if(value!="on"&&value!="off")throw std::invalid_argument("observers must be on|off");
            out.observers=value=="on";
        }
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
        else if (arg == "--multiscale-outline") {
            if(value!="on"&&value!="off")throw std::invalid_argument("multiscale-outline must be off|on");
            out.multiscale_outline=value=="on";
        }
        else if (arg == "--constraint-first") {
            if (value != "on" && value != "off") throw std::invalid_argument("constraint-first must be off|on");
            out.constraint_first = value == "on";
        }
        else if (arg == "--require-bottom-sheet") {
            if(value.empty()||!out.require_bottom_sheets.insert(value).second)
                throw std::invalid_argument("require-bottom-sheet requires a unique sheet");
        }
        else if (arg == "--owned-shape" || arg == "--offered-shape") {
            const auto split=value.find('=');
            if(split==std::string::npos||split==0||split+1==value.size()||value.find('=',split+1)!=std::string::npos||
               !(arg=="--owned-shape"?out.owned_shapes:out.offered_shapes).emplace(value.substr(0,split),value.substr(split+1)).second)
                throw std::invalid_argument(arg+" requires unique SHEET=TAG");
        }
        else if (arg == "--owned-face-cohesion") {
            if(value!="on"&&value!="off")throw std::invalid_argument("owned-face-cohesion must be off|on");
            out.owned_face_cohesion=value=="on";
        }
        else if (arg == "--failed-first-retry") {
            if(value!="on"&&value!="off")throw std::invalid_argument("failed-first-retry must be off|on");
            out.failed_first_retry=value=="on";
        }
        else if (arg == "--shape-area-first") {
            if(value!="on"&&value!="off")throw std::invalid_argument("shape-area-first must be on|off");
            out.shape_area_first=value=="on";
        }
        else if (arg == "--owned-quality-first") {
            if(value!="on"&&value!="off")throw std::invalid_argument("owned-quality-first must be off|on");
            out.owned_quality_first=value=="on";
        }
        else if (arg == "--owned-extent-alternatives") {
            if(value!="on"&&value!="off")throw std::invalid_argument("owned-extent-alternatives must be off|on");
            out.owned_extent_alternatives=value=="on";
        }
        else if (arg == "--thermal-trace") {
            if(value!="on"&&value!="off")throw std::invalid_argument("thermal-trace must be off|on");
            out.thermal_trace=value=="on";
        }
        else if (arg == "--owned-selection-trace") {
            if(value!="on"&&value!="off")throw std::invalid_argument("owned-selection-trace must be off|on");
            out.owned_selection_trace=value=="on";
        }
        else if (arg == "--edge-feasibility") {
            if(value!="on"&&value!="off")throw std::invalid_argument("edge-feasibility must be off|on");
            out.edge_feasibility=value=="on";
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
    if(!out.search_strategies.empty()) {
        if(out.compact!="on")throw std::invalid_argument("search-strategy requires compact on");
        if(out.thermal_trace||out.owned_selection_trace)
            throw std::invalid_argument("search-strategy requires per-model thermal/selection traces off");
        for(const auto& name:out.search_strategies)
            if((search_strategy(name).contract_group_rotations.value_or(false)||search_strategy(name).vertical_compaction)&&out.contract_group_face_sheets.empty())
                throw std::invalid_argument("rotations/vertical search-strategy requires contract-group-face-sheet");
    }
    if(!out.observers&&out.owned_selection_trace)throw std::invalid_argument("owned-selection-trace requires observers on");
    if(!out.observers&&out.thermal_trace)throw std::invalid_argument("thermal-trace requires observers on");
    if (out.constraint_first && out.compact != "on")
        throw std::invalid_argument("constraint-first requires --compact-search on");
    if(out.edge_translation&&out.compact!="on")throw std::invalid_argument("edge-translation requires --compact-search on");
    if(out.edge_feasibility&&out.compact!="on")throw std::invalid_argument("edge-feasibility requires --compact-search on");
    if(out.shape_choice_replays&&(out.compact!="on"||!out.interior_order))throw std::invalid_argument("shape-choice replays require compact on and explicit interior-order");
    if(out.failed_first_retry&&(out.compact!="on"||!out.interior_order))throw std::invalid_argument("failed-first-retry requires --compact-search on and --interior-order");
    if(out.owned_quality_first&&out.compact!="on")throw std::invalid_argument("owned-quality-first requires --compact-search on");
    if(out.shape_area_first&&out.compact!="on")throw std::invalid_argument("shape-area-first requires --compact-search on");
    if(out.owned_extent_alternatives&&out.compact!="on")throw std::invalid_argument("owned-extent-alternatives requires --compact-search on");
    if(out.owned_face_cohesion&&out.compact!="on")throw std::invalid_argument("owned-face-cohesion requires --compact-search on");
    if(!out.owned_shapes.empty()&&out.compact!="on")throw std::invalid_argument("owned-shape requires --compact-search on");
    if(!out.offered_shapes.empty()&&out.compact!="on")throw std::invalid_argument("offered-shape requires --compact-search on");
    for(const auto& [sheet,tag]:out.offered_shapes)if(out.owned_shapes.count(sheet))
        throw std::invalid_argument("offered-shape and owned-shape overlap: "+sheet);
    if(!out.contract_group_face_sheets.empty()&&out.compact!="on")throw std::invalid_argument("contract-group-face-sheet requires --compact-search on");
    if(out.contract_group_rotations&&out.contract_group_face_sheets.empty())throw std::invalid_argument("contract-group-rotations requires --contract-group-face-sheet");
    if(out.reseat_pose_limits&&(out.compact!="on"||out.reseat_pose_limits->poses<2||!out.reseat_pose_limits->frontier_nodes))
        throw std::invalid_argument("reseat requires --compact-search on, --reseat-poses >=2 and --reseat-frontier >0");
    if(out.reseat_pose_limits&&out.reseat_pose_limits->victim_shapes&&!out.interior_order)
        throw std::invalid_argument("victim-shape recovery requires interior-order");
    if(out.reseat_pose_limits&&out.reseat_pose_limits->continuations&&!out.interior_order)
        throw std::invalid_argument("reseat continuations require interior-order");
    if(out.reseat_pose_limits&&out.reseat_pose_limits->reuse_continuation&&!out.reseat_pose_limits->continuations)
        throw std::invalid_argument("reseat reuse requires a positive continuation budget");
    if(out.outline&&out.initial_outline)throw std::invalid_argument("initial-outline-mm cannot be combined with outline-mm");
    if(out.outline&&out.multiscale_outline)throw std::invalid_argument("multiscale-outline conflicts with fixed outline-mm");
    if(out.interior_order&&out.constraint_first)throw std::invalid_argument("single interior-order conflicts with constraint-first portfolio");
    return out;
}
struct LoadResult {
    PcbPlacementInput input;
    std::vector<std::pair<std::string, double>> times;
    std::size_t circuits = 0;
};
LoadResult load(const ProjectPaths& paths, const NetlistExtractOptions& extraction, bool compact_capable,
                const std::filesystem::path& schematic,
                const std::optional<std::filesystem::path>& floorplan_spec=std::nullopt) {
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
    validate_board_input_connectivity(circuits,load_sheet_index(paths),nets);
    tick("netlist_extract");
    BoardInputOptions options;
    // Compact mode has real input requirements, not just a solver toggle.
    // Resolve them here so profiling cannot silently omit owned alternatives.
    options.compact_search = compact_capable;
    options.floorplan_spec = floorplan_spec;
    if(floorplan_spec)std::cout<<"input floorplan_spec="<<floorplan_spec->string()<<" explicit_policy=1\n";
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
                  bool observers = true, bool thermal_trace = false,
                  bool constraint_first = false,const std::optional<FloorplanPoint>& outline=std::nullopt,bool edge_translation=false,
                  const std::optional<FloorplanPoint>& initial_outline=std::nullopt,
                  const std::optional<int>& interior_order=std::nullopt,bool multiscale_outline=false,bool edge_feasibility=false,bool owned_selection_trace=false,bool owned_quality_first=false,bool owned_face_cohesion=false,const std::map<std::string,std::string>& owned_shapes={},const std::set<std::string>& contract_group_face_sheets={},bool failed_first_retry=false,bool owned_extent_alternatives=false,bool contract_group_rotations=false,const std::optional<FloorplanPoseRetryLimits>& reseat_pose_limits=std::nullopt,const std::optional<std::size_t>& joint_states=std::nullopt,const std::set<std::string>& require_bottom_sheets={},bool shape_area_first=false,std::size_t shape_choice_replays=0,const std::map<std::string,std::string>& offered_shapes={},const std::vector<std::string>& search_strategies={}) {
    const auto copy_start = Clock::now();
    auto input = trial_input(source,compact,outline);
    for(const auto& selected:contract_group_face_sheets)if(std::none_of(input.floorplan.sheets.begin(),input.floorplan.sheets.end(),
        [&](const auto& sheet){return sheet.name==selected;}))
        throw std::invalid_argument("unknown contract-group-face-sheet: "+selected);
    const auto copy_seconds = seconds(copy_start);
    // Fresh observers for every trial. Existing non-diagnostic policy is retained.
    if (input.experiment || input.floorplan.experiment)
        throw std::runtime_error("profile requires inputs without preinstalled experiment observers");
    Profile profile;
    auto floor = std::make_shared<FloorplanExperiment>();
    floor->compact_constraint_first = constraint_first;
    floor->compact_edge_translation = edge_translation;
    floor->compact_edge_feasibility = edge_feasibility;
    floor->failed_first_retry=failed_first_retry;
    floor->owned_quality_first = owned_quality_first;
    floor->shape_area_first = shape_area_first;
    std::cout<<"shape_area_first="<<shape_area_first<<'\n';
    floor->owned_extent_alternatives = owned_extent_alternatives;
    floor->owned_face_cohesion = owned_face_cohesion;
    floor->owned_shape_tags=owned_shapes;
    floor->offered_shape_tags=offered_shapes;
    for(const auto& [sheet,tag]:offered_shapes)std::cout<<"offered_shape_restriction sheet="<<sheet<<" tag="<<tag<<'\n';
    floor->require_bottom_sheets=require_bottom_sheets;
    for(const auto& sheet:require_bottom_sheets)std::cout<<"required_bottom_sheet="<<sheet<<'\n';
    floor->contract_group_face_sheets=contract_group_face_sheets;
    floor->contract_group_rotations=contract_group_rotations;
    floor->reseat_pose_limits=reseat_pose_limits;
    floor->joint_separation_states=joint_states;
    floor->shape_choice_replays=shape_choice_replays;
    if(shape_choice_replays)std::cout<<"shape_choice_replays="<<shape_choice_replays<<'\n';
    if(joint_states)std::cout<<"joint_separation_states="<<*joint_states<<'\n';
    if(observers)floor->joint_retry_completed=[](const JointSeparationWork& w,bool ok){
        std::cout<<"joint_retry generated="<<w.generated<<" visited="<<w.visited<<" axes="<<w.axis_solves
                 <<" domain_probes="<<w.domain_probes<<" domain_rejections="<<w.domain_rejections
                 <<" proposals="<<w.qualifications<<" rejected="<<w.qualification_rejections<<" capped="<<w.budget_exhausted<<" success="<<ok<<'\n';
    };
    if(reseat_pose_limits)std::cout<<"reseat_limits poses="<<reseat_pose_limits->poses<<" frontier="<<reseat_pose_limits->frontier_nodes<<" continuations="<<reseat_pose_limits->continuations<<" reuse="<<reseat_pose_limits->reuse_continuation<<" victim_shapes="<<reseat_pose_limits->victim_shapes<<'\n';
    if(observers)floor->pose_retry_completed=[](const auto& r){
        std::cout<<"pose_retry incoming="<<r.incoming<<" displaced="<<r.displaced
                 <<" generated="<<r.generated<<" frontier="<<r.frontier_nodes<<" attempted="<<r.attempted<<" skipped="<<r.skipped
                 <<" budget_exhausted="<<r.budget_exhausted<<" result_capped="<<r.result_capped<<" success="<<r.success<<'\n';
    };
    std::cout<<"contract_group_rotations="<<contract_group_rotations<<'\n';
    for(const auto& selected:contract_group_face_sheets)std::cout<<"contract_group_face_sheet="<<selected<<'\n';
    for(const auto& [sheet,tag]:owned_shapes)std::cout<<"owned_shape_restriction sheet="<<sheet<<" tag="<<tag<<'\n';
    std::map<std::string,std::set<std::pair<int,std::string>>> face_offers;
    if(observers&&(owned_selection_trace||!contract_group_face_sheets.empty()))floor->owned_shape_catalogued=[&](const auto& sheet,int index,const auto& tag){
        if(contract_group_face_sheets.count(sheet))face_offers[sheet].emplace(index,tag);
        if(owned_selection_trace)std::cout<<"owned_shape_catalog sheet="<<sheet<<" index="<<index<<" tag="<<std::quoted(tag)<<'\n';
    };
    const auto print_face_offers=[&] {
        if(!search_strategies.empty()) {
            std::cout<<"contract_face_offers status=unavailable reason=multi_strategy_catalogs_require_separate_scope\n";
            return;
        }
        for(const auto& sheet:contract_group_face_sheets) {
            const auto found=face_offers.find(sheet);
            if(!observers||found==face_offers.end()) {
                std::cout<<"contract_face_offers sheet="<<sheet<<" status=catalog_unobserved\n";continue;
            }
            std::size_t count=0;
            for(const auto& [index,tag]:found->second){(void)index;if(tag.rfind("contract-bottom",0)==0)++count;}
            std::cout<<"contract_face_offers sheet="<<sheet<<" tagged_offers="<<found->second.size()
                     <<" contract_bottom="<<count<<" status="<<(count?"offered":"no_contract_bottom_offers")<<'\n';
        }
    };
    if(observers&&owned_selection_trace)floor->owned_shape_selection_completed=[event=std::size_t{0}](const std::string& sheet,const auto& alternatives,const auto& quality,int selected) mutable {
        ++event;
        for(const auto& rank:alternatives){
            const auto found=quality.find({sheet,rank.index});
            std::cout<<"owned_selection event="<<event<<" sheet="<<sheet<<" index="<<rank.index<<" chosen="<<(rank.index==selected)
                     <<" width="<<rank.w<<" height="<<rank.h<<" estimator="<<rank.estimator
                     <<" distance_key="<<rank.distance_key<<" side="<<rank.side;
            if(found==quality.end()) {std::cout<<" owned_quality=unavailable\n";continue;}
            const auto& q=found->second;
            for(const auto& [cap,gap]:q.bypass_pad_gaps)std::cout<<" gap_"<<cap<<'='<<gap;
            for(const auto& [cap,subject]:q.subjects)std::cout<<" sides_"<<cap<<'='<<subject.owner_side<<'/'<<subject.cap_side;
            std::cout<<'\n';
        }
    };
    if(observers)floor->edge_feasibility_rejected=[](const std::string& edge,const std::string& reason,double low,double high){
        std::cout<<"edge_rejection edge="<<edge<<" reason="<<reason<<" start_low="<<low<<" start_high="<<high<<'\n';
    };
    if(observers)floor->edge_feasibility_completed=[](std::size_t runs,std::size_t intervals,std::size_t rejected){
        std::cout<<"edge_feasibility runs="<<runs<<" intervals="<<intervals<<" rejected="<<rejected<<'\n';
    };
    floor->initial_outline=initial_outline;
    floor->interior_order=interior_order;
    floor->multiscale_outline=multiscale_outline;
    std::cout<<"multiscale_outline="<<multiscale_outline<<'\n';
    if(interior_order)std::cout<<"single_interior_order="<<*interior_order<<" alternate_order_retries=disabled\n";
    std::size_t edge_candidates=0,edge_repairs=0;
    std::vector<FloorplanReseatObservation> reseats;
    if(observers)floor->reseat_completed=[&](const auto& row){reseats.push_back(row);};
    const auto print_reseats=[&]{
        for(const auto& r:reseats)
            std::cout<<"reseat width="<<r.w<<" height="<<r.h<<" incoming="<<r.incoming
                     <<" displaced="<<r.displaced<<" incoming_seated="<<r.incoming_seated
                     <<" displaced_reseated="<<r.displaced_reseated<<" punch_free="<<r.punch_free
                     <<" order="<<r.order<<'\n';
    };
    if(observers)floor->edge_translation_completed=[&](std::size_t candidates,char edge,double shift) {
        edge_candidates+=candidates;edge_repairs+=edge!='\0';
        std::cout<<"edge_translation candidates="<<candidates<<" edge="<<(edge?std::string(1,edge):"none")
                 <<" shift_mm="<<shift<<'\n';
    };
    if(observers)floor->attempt_completed = [&](const auto& row) { profile.attempts.add(row); };
    if(observers)floor->stage_rejected=[](const auto& row) {
        std::cout<<"stage_rejection width="<<row.w<<" height="<<row.h<<" stage="<<row.stage
                 <<" subject="<<std::quoted(row.subject)<<" compact="<<row.compact
                 <<" punch_free="<<row.punch_free<<" order="<<row.order<<'\n';
        for(const auto& line:row.diagnostics)std::cout<<"stage_rejection_detail "<<std::quoted(line)<<'\n';
    };
    if(observers)floor->unscoped_estimate = [&](double) { ++profile.attempts.unscoped_estimates; };
    auto pcb = std::make_shared<PcbPlacementExperiment>();
    if(observers&&thermal_trace)pcb->thermal_trial=[](const auto& ref,double x,double y,const auto& reason) {
        std::cout<<"thermal_trial ref="<<ref<<" x="<<x<<" y="<<y<<" result="<<std::quoted(reason)<<'\n';
    };
    std::vector<PcbPlacementObservation> thermal_snapshots;
    pcb->checkpoint = [&](const auto& row) {
        profile.checkpoint(row);
        if(thermal_trace && row.has_positions) thermal_snapshots.push_back(row);
    };
    input.floorplan.experiment = floor;
    if(observers)input.experiment = pcb;
    std::cout << "trial run=" << run << " generation=" << generation << " compact_search=" << compact
        << " constraint_first=" << constraint_first
        << " edge_translation=" << edge_translation
        << " edge_feasibility=" << edge_feasibility
        << " owned_selection_trace=" << owned_selection_trace
        << " owned_quality_first=" << owned_quality_first
        << " owned_extent_alternatives=" << owned_extent_alternatives
        << " failed_first_retry=" << failed_first_retry
        << " owned_face_cohesion=" << owned_face_cohesion
        << " input_copy_seconds=" << copy_seconds << " status=started\n" << std::flush;
    std::cout<<"observers="<<(observers?"on":"off")<<" model_timing_includes_diagnostic_callbacks="<<observers<<'\n';
    if(outline)std::cout<<"outline_override width_mm="<<outline->first<<" height_mm="<<outline->second
                        <<" automatic_sizing=disabled source_policy_otherwise_unchanged=1\n"<<std::flush;
    if(initial_outline)std::cout<<"initial_outline width_mm="<<initial_outline->first<<" height_mm="<<initial_outline->second
                               <<" automatic_sizing=enabled seed_requires_validation=1\n"<<std::flush;
    ExecutionFailureReceipt failure;
    const auto start = Clock::now();
    profile.mark = start;
    PcbPlacementResult result;
    std::optional<ExecutionAccounting> search_accounting;
    try {
        if(search_strategies.empty())result=build_pcb_model(input,&failure);
        else {
            std::vector<PcbPlacementSearchStrategy> strategies;
            for(const auto& name:search_strategies)strategies.push_back(search_strategy(name));
            auto search=search_pcb_models(input,strategies,&failure);
            for(std::size_t i=0;i<search.attempts.size();++i) {
                const auto& attempt=search.attempts[i];
                std::cout<<"search_attempt index="<<i<<" strategy="<<(i?search_strategies.at(i-1):"baseline")
                         <<" status="<<attempt.status<<" detail="<<std::quoted(attempt.detail)<<'\n';
                receipt("search_attempt_"+std::to_string(i),attempt.accounting.quantization_engagements);
                for(std::size_t event=0;event<attempt.accounting.fallback_events.size();++event)
                    std::cout<<"search_fallback attempt="<<i<<" index="<<event
                             <<" name="<<attempt.accounting.fallback_events[event]<<'\n';
            }
            search_accounting=std::move(search.accounting);
            receipt("search_total",search_accounting->quantization_engagements);
            if(!search.incumbent) {
                failure.captured=true;failure.accounting=*search_accounting;
                throw std::runtime_error("model search produced no screened incumbent");
            }
            std::cout<<"search_incumbent attempt="<<*search.incumbent_attempt
                     <<" scope=screened_model_not_full_board_acceptance\n";
            result=std::move(*search.incumbent);
        }
    }
    catch (...) {
        print_reseats();
        if(observers)std::cout<<"edge_search candidates="<<edge_candidates<<" repairs="<<edge_repairs<<'\n';
        std::cout << "trial status=" << (search_strategies.empty()?"construction_failed":"search_failed") << " elapsed_seconds=" << seconds(start)
            << " completed_outer_attempts=" << (observers?std::to_string(profile.attempts.completed):"unavailable")
            << " receipt_captured=" << failure.captured << " receipt_unavailable=" << failure.unavailable << '\n';
        print_face_offers();
        if (failure.captured && !failure.unavailable) {
            receipt("failure_prefix", failure.accounting.quantization_engagements);
            for(std::size_t i=0;i<failure.accounting.fallback_events.size();++i)
                std::cout<<"failure_fallback index="<<i<<" name="<<failure.accounting.fallback_events[i]<<'\n';
        }
        throw;
    }
    const auto end = Clock::now();
    if(search_accounting)std::cout<<"timing_scope model_seconds=all_strategy_construction_screening_and_diagnostic_output"
        <<" model_total_receipt=selected_construction_only search_total_receipt=all_attempts_and_screening\n";
    // Read existing board-space stage records after the timed construction.
    // This exposes connector-only jumps without adding solver callbacks/work.
    if(observers) {
        const auto before=result.stages.find("l4_pull"),after=result.stages.find("edge_seat");
        if(before!=result.stages.end()&&after!=result.stages.end())
            for(const auto& [ref,pose]:after->second) {
                const auto previous=before->second.find(ref);
                if(previous!=before->second.end()&&previous->second!=pose)
                    std::cout<<"edge_seat_move ref="<<ref<<" coordinates=board"
                             <<" from_x="<<std::get<0>(previous->second)<<" from_y="<<std::get<1>(previous->second)
                             <<" to_x="<<std::get<0>(pose)<<" to_y="<<std::get<1>(pose)<<'\n';
            }
    }
    if(observers)for(const auto& block:result.floorplan.plan.edge_blocks)
        std::cout<<"edge_assignment sheet="<<block.name<<" edge="<<block.edge
                 <<" x="<<block.x<<" y="<<block.y<<" w="<<block.w<<" h="<<block.h<<'\n';
    print_face_offers();
    if(observers)std::cout<<"edge_search candidates="<<edge_candidates<<" repairs="<<edge_repairs<<'\n';
    if(observers)profile.stages.push_back({"model_return_tail", seconds(profile.mark, end),
        profile.attempts.completed - profile.previous_attempts, profile.attempts.packed - profile.previous_packed, 0});
    const auto model_seconds = seconds(start, end);
    const auto emit_start = Clock::now();
    const auto emission = render_pcb(result.model, pcb_emit_policy(input.floorplan.project));
    const auto emit_seconds = seconds(emit_start);
    const auto silk = check_refdes_overlap(emission.document,true);
    std::cout<<"emission_refdes_check ok="<<silk.ok<<" top_pairs="<<silk.top_pairs.size()
             <<" bottom_pairs="<<silk.bottom_pairs<<'\n';
    for(const auto& pair:silk.top_pairs)
        std::cout<<"emission_refdes_overlap first="<<pair.first<<" second="<<pair.second<<'\n';
    if(thermal_trace) {
        const auto trace_start=Clock::now();
        QuantizationCounts trace_counts;
        for(const auto& snapshot:thermal_snapshots) {
            PcbCheckModel model;
            model.origin_x=result.model.origin_x;
            model.origin_y=result.model.origin_y;
            model.board_w=result.model.board_w;
            model.board_h=result.model.board_h;
            model.net_numbers=result.model.net_numbers;
            model.insts=snapshot.instances;
            // Checkpoints expose actual poses, not historical escape copper.
            // Keep these explicitly pad-only rather than injecting final vias.
            for(const auto& field:plan_preferred_thermal_vias(model,pcb_emit_policy(input.floorplan.project),&trace_counts)) {
                std::cout<<"thermal_stage stage="<<snapshot.stage<<" ref="<<field.ref
                         <<" preferred="<<field.sites.chosen.size()<<" requested="<<field.requested
                         <<" copper=not_in_snapshot\n";
                if(field.sites.chosen.size()<field.requested) {
                    std::map<std::string,std::size_t> blockers;
                    for(const auto& rejected:field.sites.rejected) {
                        ++blockers[rejected.blocker.kind+":"+rejected.blocker.label];
                        std::cout<<"thermal_stage_rejected_site stage="<<snapshot.stage<<" ref="<<field.ref
                                 <<" x="<<rejected.candidate.first<<" y="<<rejected.candidate.second
                                 <<" blocker="<<std::quoted(rejected.blocker.kind+":"+rejected.blocker.label)
                                 <<" blocker_x="<<rejected.blocker.x<<" blocker_y="<<rejected.blocker.y<<'\n';
                    }
                    for(const auto& [label,count]:blockers)
                        std::cout<<"thermal_stage_blocker stage="<<snapshot.stage<<" ref="<<field.ref
                                 <<" label="<<std::quoted(label)<<" count="<<count<<'\n';
                }
            }
        }
        std::cout<<"thermal_trace seconds="<<seconds(trace_start)<<" scope=postconstruction_no_acceptance\n";
        receipt("thermal_trace_only",trace_counts);
    }
    for (const auto& diagnostic : emission.diagnostics)
        std::cout << "pcb_emission_diagnostic " << std::quoted(diagnostic) << '\n';
    const auto hash = pcb_sha256(emission.pcb);
    const auto accounting = pcb_placement_accounting(result);
    for(const auto& sheet:require_bottom_sheets) {
        std::size_t top=0,bottom=0;
        for(const auto& part:result.model.insts)if(part.sheet==sheet) {
            if(part.side=="bottom")++bottom;else ++top;
        }
        std::cout<<"required_bottom_result sheet="<<sheet<<" top_parts="<<top<<" bottom_parts="<<bottom<<'\n';
    }
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
    if(observers)std::cout << "work completed_outer_attempts=" << a.completed << " packed=" << a.packed << " rejected=" << a.rejected
        << " punch_free=" << a.punch_free << " distinct_outline_punch_keys=" << a.outlines.size()
        << " unscoped_estimate_callbacks=" << a.unscoped_estimates
        << " internal_order_retry_count=unavailable shape_trial_count=unavailable\n";
    else std::cout<<"work observer_counts=unavailable reason=observers_disabled production_receipts=retained\n";
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
    std::map<std::string, std::size_t> emission_fallback_counts;
    for (const auto& name : emission.fallback_events) ++emission_fallback_counts[name];
    for (const auto& [name, count] : emission_fallback_counts)
        std::cout << "emission_fallback_count name=" << name << " count=" << count << '\n';
    const auto diagnostic_start = Clock::now();
    const auto gates = check_pcb_placement_gates(input, result.model);
    const PcbCheckInput prepared(result.model);
    // Postconstruction evidence only; never a free-space or acceptance claim.
    // Actual final poses may have been refit after the floorplan reservation.
    std::cout<<"courtyard_coverage scope=final_same_face_courtyards_vs_plan_envelopes"
             <<" excludes=fanout_clearance_through_hole_access reusable_area=UNVERIFIED\n";
    for(const auto& block:result.floorplan.plan.interior_blocks) {
        std::vector<Box4> primary,opposite;
        for(std::size_t i=0;i<result.model.insts.size();++i) {
            const auto& part=result.model.insts[i];
            if(part.sheet==block.name)
                (part.side==block.side?primary:opposite).push_back(prepared.courtyard_at(i));
        }
        std::cout<<"courtyard_coverage sheet="<<block.name<<" primary_side="<<block.side
                 <<" envelope_mm2="<<block.w*block.h
                 <<" primary_union_mm2="<<courtyard_diagnostic::union_area(primary)
                 <<" opposite_union_mm2="<<courtyard_diagnostic::union_area(opposite)
                 <<" primary_parts="<<primary.size()<<" opposite_parts="<<opposite.size()<<'\n';
    }
    const auto fanout = check_fanout(prepared,0);
    const auto ratsnest = check_ratsnest(prepared);
    std::cout<<fanout.summary()<<'\n';
    std::cout<<ratsnest.summary()<<'\n';
    std::cout << "postconstruction_diagnostic seconds=" << seconds(diagnostic_start)
        << " fanout_ok=" << fanout.ok << " ratsnest_ok=" << ratsnest.ok
        << " placement_contract_ok=" << gates.placement_contract.ok
        << " placement_flow_ok=" << gates.placement_flow.ok
        << " hard_red=" << gates.composition.hard_red
        << " model_nonsearch_fallback_events=" << nonsearch_events(accounting.fallback_events)
        << " emission_nonsearch_fallback_events=" << nonsearch_events(emission.fallback_events)
        << " fallback_acceptance=UNVERIFIED_requires_project_baseline" << '\n';
    const auto margin_row=[](const PcbComposeMarginStats& group,const char* unit) {
        std::cout<<"hard_margins unit="<<unit<<" measured="<<group.measured
                 <<" unresolved="<<group.unresolved<<" sum="<<group.sum<<" min=";
        if(group.minimum)std::cout<<*group.minimum;else std::cout<<"unavailable";
        std::cout<<'\n';
    };
    margin_row(gates.composition.hard_margins.distance_mm,"mm");
    margin_row(gates.composition.hard_margins.facing_degrees,"degrees");
    for(const auto& violation:gates.placement_contract.violations)
        std::cout<<"placement_contract_violation="<<std::quoted(violation)<<'\n';
    if(!owned_shapes.empty()) {
        const PcbCheckInput measured(result.model);
        std::map<std::string,std::size_t> indices;
        for(std::size_t i=0;i<result.model.insts.size();++i)
            if(!indices.emplace(result.model.insts[i].ref,i).second)throw std::runtime_error("duplicate final reference");
        for(const auto& [sheet,trusted]:input.owned_groups)for(const auto& row:owned_group_placements(*trusted)){
            const auto oi=indices.at(row.owner),ci=indices.at(row.cap);
            const auto a=measured.geometry_at(oi).pad_boxes.at(row.owner_pin);
            const auto b=measured.geometry_at(ci).pad_boxes.at(row.cap_pin);
            const double gap=std::hypot(std::max({0.,a.x0-b.x1,b.x0-a.x1}),std::max({0.,a.y0-b.y1,b.y0-a.y1}));
            std::cout<<"owned_final sheet="<<sheet<<" owner="<<row.owner<<'.'<<row.owner_pin
                     <<" member="<<row.cap<<'.'<<row.cap_pin<<" pad_gap_mm="<<gap
                     <<" sides="<<result.model.insts[oi].side<<'/'<<result.model.insts[ci].side<<" proximity=UNVERIFIED\n";
        }
    }
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
            << "Observer mode on includes snapshot/measurement overhead; off omits callbacks and stage intervals.\n"
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
                prepared = load(paths, extraction, options.compact != "off", options.schematic, options.floorplan_spec);
                print_load(*prepared, run);
                std::cout << "input compact_capable=" << (options.compact != "off")
                    << " owned_groups=" << prepared->input.owned_groups.size() << '\n';
            }
            const int generation = options.inputs == "prepared" ? 1 : run;
            for (const bool compact : {false, true}) {
                if ((compact && options.compact == "off") || (!compact && options.compact == "on")) continue;
                const auto hash = trial(prepared->input, compact, run, generation, options.observers,options.thermal_trace,options.constraint_first,options.outline,options.edge_translation,options.initial_outline,options.interior_order,options.multiscale_outline,options.edge_feasibility,options.owned_selection_trace,options.owned_quality_first,options.owned_face_cohesion,options.owned_shapes,options.contract_group_face_sheets,options.failed_first_retry,options.owned_extent_alternatives,options.contract_group_rotations,options.reseat_pose_limits,options.joint_states,options.require_bottom_sheets,options.shape_area_first,options.shape_choice_replays,options.offered_shapes,options.search_strategies);
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
