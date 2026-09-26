#pragma once

#include "schgen/pcb_checks.hpp"

#include <functional>
#include <set>
#include <utility>

namespace schgen {
struct FloorplanInput;
struct FloorplanPlan;

// Opt-in diagnostics only. Callbacks receive completed events, never a solver
// acceptance predicate. They run synchronously; a throwing callback aborts the
// caller. Keep observers and anything borrowed by their callbacks alive for the
// entire solve. Nothing here reads/writes files or changes global parameters.
struct FloorplanAttemptObservation {
    double w = 0, h = 0;
    bool packed = false, punch_free = false;
    std::optional<double> estimate;
};
struct FloorplanExperiment {
    // Null keeps the native ordinary-net cost unchanged. Impedance-controlled
    // nets always retain their normal cost. Zero is a valid experiment value.
    std::optional<double> ordinary_via_mm;
    bool conservative_only = false;
    std::function<void(const FloorplanAttemptObservation &)> attempt_completed;
    std::function<void(double)> unscoped_estimate;
};
void validate_floorplan_experiment(const FloorplanExperiment &);
void require_floorplan_experiment_policy(const FloorplanExperiment &, bool punch_free);
double floorplan_experiment_via_cost(const FloorplanExperiment *, bool impedance,
                                   double normal_cost);

// The snapshot factory runs AFTER normal return, never on rejection-by-throw.
// In-attempt estimator calls therefore still address the last completed row.
// The null/default observer path never invokes a snapshot factory.
template <class Attempt, class Snapshot>
bool run_floorplan_experiment_attempt(const FloorplanExperiment *experiment,
                                     bool punch_free, Attempt &&attempt,
                                     Snapshot &&snapshot) {
    if (!experiment)
        return std::forward<Attempt>(attempt)();
    require_floorplan_experiment_policy(*experiment, punch_free);
    const bool packed = std::forward<Attempt>(attempt)();
    if (experiment->attempt_completed)
        experiment->attempt_completed(std::forward<Snapshot>(snapshot)(packed));
    return packed;
}
inline void observe_floorplan_experiment_estimate(const FloorplanExperiment *experiment,
                                                 double value, bool unscoped) {
    if (unscoped && experiment && experiment->unscoped_estimate)
        experiment->unscoped_estimate(value);
}

// W12BOUND compatibility: every normal attempt return, including packed=false,
// is retained. An unscoped estimate updates only the latest completed row.
// Distinct outlines keep the first row unless its estimate is missing and a
// later row has one; equal-area ties retain first-key insertion order.
struct FloorplanBoundTrace {
    std::vector<FloorplanAttemptObservation> attempts;
    void completed(const FloorplanAttemptObservation &);
    void estimated(double);
    std::vector<FloorplanAttemptObservation> distinct_outlines() const;
    FloorplanExperiment observer(); // callbacks borrow *this; do not move it
};

struct FloorplanExperimentPlan {
    double w = 0, h = 0, estimate = 0;
    bool punch_free = false;
    std::vector<std::string> bottom_blocks;
    std::vector<std::pair<std::string, int>> shapes; // edge then interior order
};
FloorplanExperimentPlan capture_floorplan_experiment_plan(const FloorplanPlan &, double estimate);
// Reuses the native cross estimator with caller-owned, unbound zone inputs.
// Its private copy discards observation callbacks and accounting observations;
// measurement never mutates production accounting or reruns packing/gates.
FloorplanExperimentPlan measure_floorplan_experiment_plan(const FloorplanInput &, const FloorplanPlan &);

struct PcbExperimentPart { std::string sheet, footprint, value; };
// A borrowed view of CURRENT placement state. It must be assembled at the
// executing checkpoint, not from a final model or the pose-only stage map.
// Resolved mods already contain the current mirror transform. Observing uses
// the normal pure quantizer without incrementing production accounting.
struct PcbExperimentFrame {
    const std::map<std::string, std::pair<double, double>> &positions;
    const std::map<std::string, PcbExperimentPart> &parts;
    const std::map<std::string, PcbCheckFootprintPtr> &resolved;
    const std::map<std::string, std::string> &side_of;
    const std::map<std::string, double> &rotations;
    const std::set<std::string> &grid_placed, &fixed, &mounting_holes, &som_refs;
    const std::map<std::pair<std::string, std::string>, std::pair<int, std::string>> &pin_nets;
    const std::set<std::string> &mirror_refs;
    double origin_x = 25, origin_y = 25;
};
struct PcbPlacementObservation {
    std::string stage;
    bool has_positions = false;
    std::optional<int> moved; // missing at first tracked stage/domain boundary
    std::optional<FloorplanExperimentPlan> plan;
    // Value-owned checkpoint snapshot; footprint bytes/documents are immutable.
    // No synthetic fiducials here, including at emission_frame/escape_copper.
    std::vector<PcbCheckInstance> instances;
    std::set<std::string> fixed, grid_placed;
};
PcbPlacementObservation capture_pcb_experiment_frame(const PcbExperimentFrame &,
    std::string stage, std::optional<int> moved = std::nullopt);
struct PcbPlacementExperiment {
    std::function<void(const PcbPlacementObservation &)> checkpoint;
};
template <class Snapshot>
void observe_pcb_experiment_checkpoint(const PcbPlacementExperiment *experiment,
                                      Snapshot &&snapshot) {
    if (experiment && experiment->checkpoint)
        experiment->checkpoint(std::forward<Snapshot>(snapshot)());
}
} // namespace schgen
