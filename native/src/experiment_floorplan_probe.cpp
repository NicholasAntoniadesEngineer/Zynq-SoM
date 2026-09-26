#include "floorplan_internal.hpp"

namespace schgen {
FloorplanExperimentPlan measure_floorplan_experiment_plan(const FloorplanInput &input,
                                                         const FloorplanPlan &plan) {
    auto local = input;
    local.accounting = {};
    if (input.experiment) {
        auto experiment = std::make_shared<FloorplanExperiment>();
        experiment->ordinary_via_mm = input.experiment->ordinary_via_mm;
        local.experiment = std::move(experiment);
    }
    floorplan_detail::Engine engine(local);
    engine.plan = plan;
    engine.plan.accounting = {};
    engine.prepare_cross();
    return capture_floorplan_experiment_plan(plan, engine.estimate());
}
} // namespace schgen
