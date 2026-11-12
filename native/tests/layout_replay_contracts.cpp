#include "schgen/board_pcb.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/layout_json.hpp"
#include "schgen/layout_kernel.hpp"
#include "schgen/layout_stage.hpp"
#include "schgen/measure.hpp"
#include "schgen/pcb_drc.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/placement_integrity.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/thermal_checks.hpp"
#include "fresh_project_schematic.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <random>

namespace {

using namespace schgen;
using namespace schgen::layout;

namespace fixture {
constexpr std::uint64_t walk_seed = 20261111;
constexpr Nm walk_range = 5000000, walk_grid = 50000;
constexpr int flip_odds = 4, probe_stride = 25;
constexpr Nm hull_tolerance = 500;
constexpr double length_tolerance = 1e-3;
constexpr std::size_t report_limit = 8;
const char* const plane_net = "GND";
const char* const overmold_part = "HDMI-019S";
const char* const repeat_project = "devkit_mini";
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("layout replay contract failed: " + what);
}

std::string file_text(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("layout replay cannot read " + path.string());
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

void margins_match_the_flow_gate(const PcbModel& model, const PcbPlacementGatePolicy& gates, const Kernel& kernel) {
    std::vector<double> expected;
    for (const auto& term : check_pcb_placement_flow(PcbCheckInput(model), gates).terms)
        if (!term.advisory && (term.kind == "far" || term.kind == "near_max"))
            expected.push_back(term.kind == "far" ? term.measured - term.bound : term.bound - term.measured);
    std::size_t matched = 0;
    std::size_t soft_rules = 0, soft_met = 0;
    for (const auto& margin : kernel.margins()) {
        if (margin.kind == "soft_gap") {
            ++soft_rules;
            if (margin.value >= 0) ++soft_met;
            continue;
        }
        require(margin.value >= 0, "baseline margin of " + margin.source);
        if (margin.kind != "group_gap") continue;
        require(matched < expected.size() &&
                std::fabs(margin.value / constants::nano_scale.value - expected[matched]) <= fixture::length_tolerance,
                "kernel margin equals the flow gate for " + margin.source);
        ++matched;
    }
    require(matched == expected.size(), "every flow-gate bound has a kernel rule");
    std::cout << "  soft owner rules met on the baseline: " << soft_met << " of " << soft_rules << "\n";
}

std::string pose_text(const layout::Pose& pose) {
    return "(" + std::to_string(to_mm(pose.at.x)) + ", " + std::to_string(to_mm(pose.at.y)) + ") turn " +
           std::to_string(static_cast<int>(pose.turn)) + (pose.face == Face::top ? " top" : " bottom");
}

void geometry_matches_the_gates(const PcbModel& model, const ModelBinding& binding) {
    const PcbCheckInput input(model);
    for (std::size_t index = 0; index < model.insts.size(); ++index) {
        const layout::Pose& pose = binding.placement[index];
        const Variant& variant = binding.problem.footprints[binding.problem.parts[index].footprint].on(pose.face);
        const Box4 court = input.courtyard_at(index);
        require(placed(variant.gate_box, pose.at, pose.turn) == box_nm(court.x0, court.y0, court.x1, court.y1),
                "gate box of " + model.insts[index].ref);
        if (!variant.pad_hull) continue;
        const Box hull = placed(*variant.pad_hull, pose.at, pose.turn);
        const Box4 pads = input.pad_bbox_at(index);
        const Box gate{nearest_nm(pads.x0), nearest_nm(pads.y0), nearest_nm(pads.x1), nearest_nm(pads.y1)};
        require(std::llabs(hull.x0 - gate.x0) <= fixture::hull_tolerance &&
                std::llabs(hull.y0 - gate.y0) <= fixture::hull_tolerance &&
                std::llabs(hull.x1 - gate.x1) <= fixture::hull_tolerance &&
                std::llabs(hull.y1 - gate.y1) <= fixture::hull_tolerance,
                "pad hull of " + model.insts[index].ref);
    }
}

void airwire_matches_measure(const ProjectPaths& paths, const std::string& pcb, const Kernel& kernel,
                             const std::string& power_class) {
    measure::Options options;
    options.power_classes.push_back(power_class);
    const auto board = measure::read_board(sexpr_loads(pcb),
        parse_json_text(file_text(paths.project_root / "Zynq_Carrier.kicad_pro")),
        parse_json_text(file_text(paths.sheet_index_file)));
    const auto report = measure::measure_board(board, options);
    const Wirelength length = kernel.measured_wirelength();
    const auto close = [](Nm exact, double measured) {
        return std::fabs(to_mm(exact) - measured) <= fixture::length_tolerance;
    };
    std::cout << "  airwire mm: signal " << to_mm(length.signal) << " power " << to_mm(length.power)
              << " plane " << to_mm(length.plane) << "; measure: signal " << report.airwire.signal.manhattan
              << " power " << report.airwire.power.manhattan << " plane " << report.airwire.plane.manhattan
              << " (" << report.airwire.plane.connections << " plane connections)\n";
    require(close(length.signal, report.airwire.signal.manhattan), "signal airwire equals measure");
    require(close(length.power, report.airwire.power.manhattan), "power airwire equals measure");
    require(length.plane > 0 && report.airwire.plane.manhattan > 0, "plane airwire is measured on both sides");
}

std::map<std::string, std::size_t> thermal_drills(const Sexpr& document) {
    std::map<std::string, std::size_t> drills;
    for (const auto& footprint : scan_thermal_copper(document, "layout").footprints)
        for (const auto& pad : footprint.pads)
            if (pad.drill > 0) ++drills[footprint.ref];
    return drills;
}

bool may_flip(const ModelBinding& binding, std::size_t part) {
    const Part& item = binding.problem.parts[part];
    const Footprint& footprint = binding.problem.footprints[item.footprint];
    if (!footprint.flippable || item.top_only) return false;
    for (const auto& pad : footprint.top.pads)
        if (pad.through) return false;
    return true;
}

void differential_walk(const std::string& project, const PcbPlacementInput& inputs, const PcbModel& model,
                       const ModelBinding& binding,
                       const PcbEmitPolicy& policy, std::size_t states, std::size_t drc_samples,
                       const std::filesystem::path& scratch, const std::filesystem::path& project_file) {
    Kernel kernel(binding.problem, binding.placement);
    const auto thermal_baseline = thermal_drills(render_pcb(model, policy).document);
    std::vector<std::size_t> movable;
    for (std::size_t part = 0; part < binding.problem.parts.size(); ++part)
        if (!binding.problem.parts[part].fixed) movable.push_back(part);
    require(!movable.empty(), "board has movable parts");
    std::mt19937_64 random(fixture::walk_seed);
    std::map<std::string, std::size_t> rejected, stricter;
    std::size_t proposals = 0, accepted = 0, probes = 0, drc_done = 0;
    const std::size_t drc_stride = drc_samples ? std::max<std::size_t>(1, states / drc_samples) : 0;
    const Nm span = 2 * fixture::walk_range / fixture::walk_grid + 1;
    while (accepted < states) {
        ++proposals;
        const std::size_t part = movable[random() % movable.size()];
        layout::Pose pose = kernel.placement()[part];
        pose.at.x += (static_cast<Nm>(random() % static_cast<std::uint64_t>(span)) - span / 2) * fixture::walk_grid;
        pose.at.y += (static_cast<Nm>(random() % static_cast<std::uint64_t>(span)) - span / 2) * fixture::walk_grid;
        if (const auto& edge = binding.problem.parts[part].edge) {
            const bool sideways = turned(edge->mouth, pose.turn).x != 0;
            pose.at.x = sideways ? kernel.placement()[part].at.x : pose.at.x;
            pose.at.y = sideways ? pose.at.y : kernel.placement()[part].at.y;
        } else {
            pose.turn = static_cast<Turn>(random() % turn_count);
            if (random() % fixture::flip_odds == 0 && may_flip(binding, part)) pose.face = opposite(pose.face);
        }
        const auto refusal = kernel.rejection(part, pose);
        if (refusal) {
            ++rejected[breach_name(refusal->kind)];
            if (refusal->kind != Breach::locked && proposals % fixture::probe_stride == 0) {
                Placement trial = kernel.placement();
                trial[part] = pose;
                ++probes;
                if (judge_model(inputs, model_with(model, binding, trial)).ok()) ++stricter[breach_name(refusal->kind)];
            }
            continue;
        }
        const layout::Pose before = kernel.placement()[part];
        require(kernel.move(part, pose), "accepted pose applies");
        ++accepted;
        const PcbModel moved = model_with(model, binding, kernel.placement());
        const GateVerdict verdict = judge_model(inputs, moved);
        if (!verdict.ok())
            throw std::runtime_error("layout replay contract failed: " + project + " state " +
                std::to_string(accepted) + ": kernel accepted " + binding.problem.parts[part].reference +
                " from " + pose_text(before) + " to " + pose_text(pose) + " but gates say " + verdict.text());
        if (drc_stride && accepted % drc_stride == 0 && drc_done < drc_samples) {
            const auto directory = scratch / project / ("state-" + std::to_string(accepted));
            std::filesystem::create_directories(directory);
            std::filesystem::copy_file(project_file, directory / project_file.filename(),
                                       std::filesystem::copy_options::overwrite_existing);
            std::ofstream(directory / "Zynq_Carrier.kicad_pcb", std::ios::binary) << render_pcb(moved, policy).pcb;
            const auto drc = run_pcb_drc(directory / "Zynq_Carrier.kicad_pcb");
            ++drc_done;
            const auto overlap = drc.by_type.find("courtyards_overlap");
            require(overlap == drc.by_type.end() || overlap->second == 0,
                    project + " state " + std::to_string(accepted) + ": KiCad reports courtyard overlap");
            require(drc.n_errors && *drc.n_errors == 0,
                    project + " state " + std::to_string(accepted) + ": KiCad reports design-rule errors");
            require(thermal_drills(render_pcb(moved, policy).document) == thermal_baseline,
                    project + " state " + std::to_string(accepted) + ": thermal vias changed");
        }
    }
    kernel.verify();
    require(kernel.violations().empty(), "walk ends legal");
    std::cout << "  walk: " << accepted << " accepted of " << proposals << " proposals; KiCad checks " << drc_done << "\n";
    for (const auto& [kind, count] : rejected) std::cout << "    rejected " << kind << ": " << count << "\n";
    std::cout << "  probes of rejected moves: " << probes << "\n";
    for (const auto& [kind, count] : stricter)
        std::cout << "    kernel stricter than the gates on " << kind << ": " << count << "\n";
}

void integrity_gate_catches(const std::string& project, const PcbModel& model) {
    const auto judged = [](const PcbModel& candidate) {
        return check_placement_integrity(PcbCheckInput(candidate), candidate);
    };
    const auto module_connector = [](const PcbCheckInstance& instance) {
        return pcb_is_df40_part(instance.sheet, static_cast<int>(instance.pad_nets.size()));
    };
    const PlacementIntegrityResult baseline = judged(model);
    std::cout << baseline.summary();
    require(baseline.ok, project + " baseline passes the integrity gate");
    require(baseline.corridors > 0 && baseline.corridor_subjects > 0, project + " has escape corridors to judge");
    const auto controlled = [&](const PcbCheckInstance& instance) {
        return instance.side == "top" &&
               std::any_of(instance.pad_nets.begin(), instance.pad_nets.end(), [&](const auto& pad) {
                   const auto klass = model.netclass_of.find(pad.second.second);
                   if (klass == model.netclass_of.end()) return false;
                   const auto geometry = model.classes.find(klass->second);
                   return geometry != model.classes.end() && geometry->second.has_value();
               });
    };
    const auto exposed = std::find_if(model.insts.begin(), model.insts.end(), controlled);
    require((exposed != model.insts.end()) == (baseline.controlled_parts > 0),
            project + " integrity gate counts the controlled parts the model holds");
    if (exposed != model.insts.end()) {
        PcbModel flipped = model;
        flipped.insts[static_cast<std::size_t>(exposed - model.insts.begin())].side = "bottom";
        const PlacementIntegrityResult verdict = judged(flipped);
        require(!verdict.ok && verdict.rear_controlled.size() == 1,
                project + " integrity gate rejects a controlled part on the rear");
    }
    const auto connector = std::find_if(model.insts.begin(), model.insts.end(), module_connector);
    const auto rear = std::find_if(model.insts.begin(), model.insts.end(), [&](const PcbCheckInstance& instance) {
        return instance.side == "bottom" && !module_connector(instance);
    });
    require(connector != model.insts.end() && rear != model.insts.end(),
            project + " has a module connector and a rear part");
    const Box4 corridor =
        pcb_escape_corridor_board(*connector->mod, connector->x, connector->y, connector->rotation);
    PcbModel intruding = model;
    auto& moved = intruding.insts[static_cast<std::size_t>(rear - model.insts.begin())];
    moved.x = (corridor.x0 + corridor.x1) / 2;
    moved.y = (corridor.y0 + corridor.y1) / 2;
    const PlacementIntegrityResult verdict = judged(intruding);
    require(!verdict.ok && !verdict.corridor_intrusions.empty(),
            project + " integrity gate rejects a rear part inside an escape corridor");
}

void squeezed_board_passes(const std::string& project, const PcbPlacementInput& inputs, const PcbModel& model,
                           const PcbEmitPolicy& policy, const AdapterOptions& options,
                           const std::filesystem::path& scratch, const std::filesystem::path& project_file) {
    const StageResult stage = squeeze_stage(inputs, model, policy, options);
    std::cout << stage.report;
    const double before = to_mm(stage.squeeze.before.width) * to_mm(stage.squeeze.before.height);
    const double after = to_mm(stage.squeeze.after.width) * to_mm(stage.squeeze.after.height);
    require(after < before, project + " squeeze shrinks the board");
    const GateVerdict verdict = judge_model(inputs, stage.model);
    require(verdict.ok(), project + " squeezed board passes its gates: " + verdict.text());
    const auto rendered = render_pcb(stage.model, policy);
    require(thermal_drills(rendered.document) == thermal_drills(render_pcb(model, policy).document),
            project + " squeeze keeps every thermal via");
    const auto directory = scratch / project / "squeezed";
    std::filesystem::create_directories(directory);
    std::filesystem::copy_file(project_file, directory / project_file.filename(),
                               std::filesystem::copy_options::overwrite_existing);
    std::ofstream(directory / "Zynq_Carrier.kicad_pcb", std::ios::binary) << rendered.pcb;
    const auto drc = run_pcb_drc(directory / "Zynq_Carrier.kicad_pcb");
    require(drc.n_errors && *drc.n_errors == 0, project + " squeezed board has no KiCad design-rule errors");
    if (project == fixture::repeat_project)
        require(render_pcb(squeeze_stage(inputs, model, policy, options).model, policy).pcb == rendered.pcb,
                project + " squeeze repeats exactly");
}

void replay(const std::filesystem::path& root, const std::string& project, std::size_t states,
            std::size_t drc_samples, bool squeezes, const std::filesystem::path& scratch) {
    const auto paths = resolve_project_paths(root, std::filesystem::path(project));
    const auto schematic = test::fresh_project_schematic(paths, load_project_circuits(paths));
    const auto stage = prepare_board_pcb(paths, {}, {}, schematic);
    const PcbModel& model = stage.placement.model;
    const PcbEmitPolicy policy = pcb_emit_policy(load_project_config(paths));
    const PcbPlacementGatePolicy gates = pcb_placement_gate_policy(stage.inputs);
    const AdapterOptions options{fixture::plane_net,
        project_edge_clearance(parse_json_text(file_text(paths.project_root / "Zynq_Carrier.kicad_pro"))),
        {fixture::overmold_part}, 0};
    const ModelBinding binding = bind_model(model, policy, &gates, options);
    const Constraints& rules = binding.problem.constraints;
    std::map<std::string, std::size_t> ties;
    std::size_t small_parts = 0, owned_parts = 0;
    for (const auto& entry : binding.problem.ownership) {
        if (entry.tie == Tie::none) continue;
        ++small_parts;
        ++ties[tie_name(entry.tie)];
        if (entry.owner) ++owned_parts;
    }
    std::cout << "  ownership: " << owned_parts << " of " << small_parts << " movable two-pin parts have an owner (";
    for (const auto& [tie, count] : ties) std::cout << tie << " " << count << " ";
    std::cout << "), " << rules.soft_gaps.size() << " soft rules\n";
    std::cout << "  rules: " << rules.pad_gaps.size() << " pad gaps, " << rules.nearest_gaps.size() << " nearest, "
              << rules.face_pairs.size() << " face pairs, " << rules.group_gaps.size() << " subsystem bounds\n";
    std::cout << project << ": " << model.board_w << " x " << model.board_h << " mm, "
              << binding.problem.parts.size() << " parts, " << binding.problem.footprints.size()
              << " footprints, " << binding.problem.nets.size() << " nets\n";
    const std::string original = render_pcb(model, policy).pcb;
    require(render_pcb(model_with(model, binding, binding.placement), policy).pcb == original,
            project + " round trip is byte-identical");
    geometry_matches_the_gates(model, binding);
    require(judge_model(stage.inputs, model).ok(), project + " baseline passes its gates");
    integrity_gate_catches(project, model);
    const Kernel kernel(binding.problem, binding.placement);
    const auto found = kernel.violations();
    for (std::size_t index = 0; index < found.size() && index < fixture::report_limit; ++index)
        std::cout << "  VIOLATION " << breach_name(found[index].kind) << " "
                  << binding.problem.parts[found[index].part].reference << " / "
                  << binding.problem.parts[found[index].other].reference << "\n";
    require(found.empty(), project + " baseline is legal in the kernel (" + std::to_string(found.size()) + " violations)");
    require(kernel.outline_holds(), project + " baseline outline holds the module and fixed copper");
    airwire_matches_measure(paths, original, kernel, policy.power_class);
    margins_match_the_flow_gate(model, gates, kernel);
    const std::string exported = document_json(binding.problem, binding.placement);
    const Document restored = read_document(parse_json_text(exported));
    require(document_json(restored.problem, restored.placement) == exported, project + " export round trip");
    const Kernel reloaded(restored.problem, restored.placement);
    require(reloaded.violations().empty() && reloaded.routed_length() == kernel.routed_length(),
            project + " reloaded problem behaves identically");
    if (states)
        differential_walk(project, stage.inputs, model, binding, policy, states, drc_samples, scratch,
                          paths.project_root / "Zynq_Carrier.kicad_pro");
    if (squeezes) {
        AdapterOptions strict = options;
        strict.edge_setback = stage.inputs.floorplan.place_clear;
        squeezed_board_passes(project, stage.inputs, model, policy, strict, scratch,
                              paths.project_root / "Zynq_Carrier.kicad_pro");
    }
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 6)
            throw std::runtime_error("usage: layout_replay_contracts REPOSITORY SCRATCH STATES DRC_SAMPLES SQUEEZES");
        const auto root = std::filesystem::absolute(argv[1]);
        const std::filesystem::path scratch = argv[2];
        const std::size_t states = std::stoull(argv[3]), drc_samples = std::stoull(argv[4]);
        const bool squeezes = std::stoull(argv[5]) != 0;
        for (const char* project : {"carrier", "devkit_mini"})
            replay(root, project, states, drc_samples, squeezes, scratch);
        std::cout << "layout replay contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
