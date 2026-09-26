#include "schgen/experiment_observers.hpp"
#include "schgen/floorplan.hpp"
#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cmath>
#include <tuple>

namespace schgen {
void validate_floorplan_experiment(const FloorplanExperiment &experiment) {
    if (experiment.ordinary_via_mm &&
        (!std::isfinite(*experiment.ordinary_via_mm) || *experiment.ordinary_via_mm < 0))
        throw FloorplanError("experiment: ordinary via cost must be finite and nonnegative");
}
void require_floorplan_experiment_policy(const FloorplanExperiment &experiment, bool punch_free) {
    if (experiment.conservative_only && punch_free)
        throw FloorplanError("w12 probe: conservative-only forced");
}
double floorplan_experiment_via_cost(const FloorplanExperiment *experiment, bool impedance,
                                   double normal_cost) {
    if (!experiment)
        return normal_cost;
    validate_floorplan_experiment(*experiment);
    return !impedance && experiment->ordinary_via_mm ? *experiment->ordinary_via_mm : normal_cost;
}
void FloorplanBoundTrace::completed(const FloorplanAttemptObservation &row) {
    attempts.push_back({row.w, row.h, row.packed, row.punch_free, std::nullopt});
}
void FloorplanBoundTrace::estimated(double value) {
    if (!attempts.empty())
        attempts.back().estimate = py_round(value, 1);
}
std::vector<FloorplanAttemptObservation> FloorplanBoundTrace::distinct_outlines() const {
    std::vector<FloorplanAttemptObservation> rows;
    std::map<std::tuple<bool, double, double>, std::size_t> indices;
    for (const auto &row : attempts) {
        auto [at, fresh] = indices.emplace(std::make_tuple(row.punch_free, row.w, row.h), rows.size());
        if (fresh)
            rows.push_back(row);
        else if (row.estimate && !rows.at(at->second).estimate)
            rows.at(at->second) = row;
    }
    std::stable_sort(rows.begin(), rows.end(), [](const auto &a, const auto &b) {
        return std::make_pair(a.punch_free, a.w * a.h) < std::make_pair(b.punch_free, b.w * b.h);
    });
    return rows;
}
FloorplanExperiment FloorplanBoundTrace::observer() {
    FloorplanExperiment result;
    result.attempt_completed = [this](const auto &row) { completed(row); };
    result.unscoped_estimate = [this](double value) { estimated(value); };
    return result;
}
FloorplanExperimentPlan capture_floorplan_experiment_plan(const FloorplanPlan &plan, double estimate) {
    FloorplanExperimentPlan result;
    result.w = plan.board_w;
    result.h = plan.board_h;
    result.estimate = py_round(estimate, 1);
    result.punch_free = plan.punch_free;
    for (const auto *blocks : {&plan.edge_blocks, &plan.interior_blocks})
        for (const auto &block : *blocks) {
            if (block.side == "bottom") result.bottom_blocks.push_back(block.name);
            if (block.shape_idx) result.shapes.emplace_back(block.name, block.shape_idx);
        }
    std::sort(result.bottom_blocks.begin(), result.bottom_blocks.end());
    return result;
}
PcbPlacementObservation capture_pcb_experiment_frame(const PcbExperimentFrame &frame,
                                                    std::string stage, std::optional<int> moved) {
    PcbPlacementObservation result;
    result.stage = std::move(stage);
    result.has_positions = !frame.positions.empty();
    result.moved = moved;
    result.fixed = frame.fixed;
    if (result.fixed.empty()) {
        result.fixed = frame.mounting_holes;
        result.fixed.insert(frame.som_refs.begin(), frame.som_refs.end());
    }
    result.grid_placed = frame.grid_placed;
    for (const auto &[ref, mod] : frame.resolved) {
        const auto position = frame.positions.find(ref);
        if (position == frame.positions.end()) continue;
        if (!mod) throw FloorplanError("experiment: unresolved footprint for " + ref);
        const auto &part = frame.parts.at(ref);
        PcbCheckInstance inst;
        inst.ref = ref;
        inst.sheet = part.sheet;
        inst.footprint = part.footprint;
        inst.value = part.value;
        inst.mod = mod;
        inst.side = result.fixed.count(ref) ? "top" : frame.side_of.at(ref);
        const auto rotation = frame.rotations.find(ref);
        inst.rotation = rotation == frame.rotations.end() ? 0 : rotation->second;
        inst.mirror = frame.mirror_refs.count(ref) != 0;
        const auto x = frame.origin_x + position->second.first;
        const auto y = frame.origin_y + position->second.second;
        const bool grid = frame.grid_placed.count(ref) != 0;
        inst.x = grid ? py_round(x, 4) : fixed_part_grid(x);
        inst.y = grid ? py_round(y, 4) : fixed_part_grid(y);
        for (const auto &name : pad_names_from_text(mod->bytes)) {
            const auto net = frame.pin_nets.find({ref, name});
            inst.pad_nets[name] = net == frame.pin_nets.end() ? std::make_pair(0, std::string{}) : net->second;
        }
        result.instances.push_back(std::move(inst));
    }
    return result;
}
} // namespace schgen
