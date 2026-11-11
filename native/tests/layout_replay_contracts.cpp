#include "schgen/board_pcb.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/layout_json.hpp"
#include "schgen/layout_kernel.hpp"
#include "schgen/measure.hpp"
#include "schgen/pcb_drc.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "fresh_project_schematic.hpp"

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
}

struct Verdict {
    bool fanout = false, mechanical = false, on_board = false, grouped = false;
    bool ok() const { return fanout && mechanical && on_board && grouped; }
    std::string text() const {
        return std::string("fanout=") + (fanout ? "pass" : "FAIL") + " mechanical=" +
               (mechanical ? "pass" : "FAIL") + " on_board=" + (on_board ? "pass" : "FAIL") +
               " grouped=" + (grouped ? "pass" : "FAIL");
    }
};

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("layout replay contract failed: " + what);
}

std::string file_text(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("layout replay cannot read " + path.string());
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

Verdict judge(const PcbModel& model) {
    const PcbCheckInput input(model);
    const auto ratsnest = check_ratsnest(input);
    return {check_fanout(input, 0).ok, check_placement_mech(input).ok, ratsnest.off_board.empty(),
            ratsnest.dispersed.empty()};
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

bool may_flip(const ModelBinding& binding, std::size_t part) {
    const Part& item = binding.problem.parts[part];
    const Footprint& footprint = binding.problem.footprints[item.footprint];
    if (!footprint.flippable || item.top_only) return false;
    for (const auto& pad : footprint.top.pads)
        if (pad.through) return false;
    return true;
}

void differential_walk(const std::string& project, const PcbModel& model, const ModelBinding& binding,
                       const PcbEmitPolicy& policy, std::size_t states, std::size_t drc_samples,
                       const std::filesystem::path& scratch, const std::filesystem::path& project_file) {
    Kernel kernel(binding.problem, binding.placement);
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
        pose.turn = static_cast<Turn>(random() % turn_count);
        if (random() % fixture::flip_odds == 0 && may_flip(binding, part)) pose.face = opposite(pose.face);
        const auto refusal = kernel.rejection(part, pose);
        if (refusal) {
            ++rejected[breach_name(refusal->kind)];
            if (refusal->kind != Breach::locked && proposals % fixture::probe_stride == 0) {
                Placement trial = kernel.placement();
                trial[part] = pose;
                ++probes;
                if (judge(model_with(model, binding, trial)).ok()) ++stricter[breach_name(refusal->kind)];
            }
            continue;
        }
        const layout::Pose before = kernel.placement()[part];
        require(kernel.move(part, pose), "accepted pose applies");
        ++accepted;
        const PcbModel moved = model_with(model, binding, kernel.placement());
        const Verdict verdict = judge(moved);
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

void replay(const std::filesystem::path& root, const std::string& project, std::size_t states,
            std::size_t drc_samples, const std::filesystem::path& scratch) {
    const auto paths = resolve_project_paths(root, std::filesystem::path(project));
    const auto schematic = test::fresh_project_schematic(paths, load_project_circuits(paths));
    const auto stage = prepare_board_pcb(paths, {}, {}, schematic);
    const PcbModel& model = stage.placement.model;
    const PcbEmitPolicy policy = pcb_emit_policy(load_project_config(paths));
    const ModelBinding binding = bind_model(model, policy, {fixture::plane_net,
        project_edge_clearance(parse_json_text(file_text(paths.project_root / "Zynq_Carrier.kicad_pro")))});
    std::cout << project << ": " << model.board_w << " x " << model.board_h << " mm, "
              << binding.problem.parts.size() << " parts, " << binding.problem.footprints.size()
              << " footprints, " << binding.problem.nets.size() << " nets\n";
    const std::string original = render_pcb(model, policy).pcb;
    require(render_pcb(model_with(model, binding, binding.placement), policy).pcb == original,
            project + " round trip is byte-identical");
    geometry_matches_the_gates(model, binding);
    require(judge(model).ok(), project + " baseline passes its gates");
    const Kernel kernel(binding.problem, binding.placement);
    const auto found = kernel.violations();
    for (std::size_t index = 0; index < found.size() && index < fixture::report_limit; ++index)
        std::cout << "  VIOLATION " << breach_name(found[index].kind) << " "
                  << binding.problem.parts[found[index].part].reference << " / "
                  << binding.problem.parts[found[index].other].reference << "\n";
    require(found.empty(), project + " baseline is legal in the kernel (" + std::to_string(found.size()) + " violations)");
    airwire_matches_measure(paths, original, kernel, policy.power_class);
    const std::string exported = document_json(binding.problem, binding.placement);
    const Document restored = read_document(parse_json_text(exported));
    require(document_json(restored.problem, restored.placement) == exported, project + " export round trip");
    const Kernel reloaded(restored.problem, restored.placement);
    require(reloaded.violations().empty() && reloaded.routed_length() == kernel.routed_length(),
            project + " reloaded problem behaves identically");
    if (states)
        differential_walk(project, model, binding, policy, states, drc_samples, scratch,
                          paths.project_root / "Zynq_Carrier.kicad_pro");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 5) throw std::runtime_error("usage: layout_replay_contracts REPOSITORY SCRATCH STATES DRC_SAMPLES");
        const auto root = std::filesystem::absolute(argv[1]);
        const std::filesystem::path scratch = argv[2];
        const std::size_t states = std::stoull(argv[3]), drc_samples = std::stoull(argv[4]);
        for (const char* project : {"carrier", "devkit_mini"}) replay(root, project, states, drc_samples, scratch);
        std::cout << "layout replay contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
