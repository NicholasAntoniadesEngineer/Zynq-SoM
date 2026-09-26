#include "experiment_tools_internal.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "accurate_norm.hpp"

namespace schgen {
namespace experiment_detail {
void apply_layers(PcbPlacementInput &input, const std::vector<std::string> &sheets) {
    if (sheets.empty()) return;
    if (!input.floorplan.spec) throw FloorplanSpecError("experiment: either-side candidates require an authored floorplan spec");
    for (const auto &sheet : sheets) input.floorplan.spec->interior[sheet].layer = "either";
}
namespace {
void add_stage(ExperimentDocument &document, const PcbPlacementObservation &observation) {
    auto row = jo({{"stage", j(observation.stage)}});
    const auto index = field(document.data, "rows").array_value.size();
    const auto base = "/rows/" + std::to_string(index);
    if (observation.plan) {
        const auto &p = *observation.plan;
        auto shapes = jo(); for (const auto &[name, shape] : p.shapes) set(shapes, name, j(shape));
        for (auto entry : {std::make_pair("est_cross", j(p.estimate)), {"board", j(fmt(p.w)+"x"+fmt(p.h))},
                {"area", j(p.w*p.h)}, {"punch_free", jb(p.punch_free)},
                {"bottom_blocks", strings(p.bottom_blocks)}, {"shapes", shapes}})
            set(row, entry.first, std::move(entry.second));
        document.float_paths.insert(base + "/est_cross"); document.float_paths.insert(base + "/area");
    }
    if (observation.has_positions) {
        const auto lengths = experiment_cross_lengths(observation.instances);
        set(row, "cross", j(lengths.cross)); set(row, "total", j(lengths.total));
        set(row, "n_cross", j(lengths.n_cross)); set(row, "moved", observation.moved ? j(*observation.moved) : JsonNode{});
        document.float_paths.insert(base + "/cross"); document.float_paths.insert(base + "/total");
    }
    field(document.data, "rows").array_value.push_back(std::move(row));
}
} // namespace
} // namespace experiment_detail
ExperimentLengths experiment_cross_lengths(const std::vector<PcbCheckInstance> &instances) {
    PcbCheckModel model; model.insts = instances;
    const auto nets = ratsnest_net_pad_positions(model);
    const auto edges = ratsnest_mst(nets);
    ExperimentLengths result;
    for (const auto &[name, pads] : nets) for (const auto &[a, b] : edges.at(name)) {
        const auto &left = pads.at(static_cast<std::size_t>(a)), &right = pads.at(static_cast<std::size_t>(b));
        const double length = accurate_hypot2(std::get<0>(left)-std::get<0>(right), std::get<1>(left)-std::get<1>(right));
        result.total += length;
        if (std::get<3>(left) != std::get<3>(right)) { result.cross += length; ++result.n_cross; }
    }
    result.cross = py_round(result.cross, 1); result.total = py_round(result.total, 1);
    return result;
}
ExperimentProbeResult run_w12_bound(PcbPlacementInput input, const std::string &tag, const std::vector<std::string> &sheets) {
    using namespace experiment_detail;
    apply_layers(input, sheets);
    FloorplanBoundTrace trace;
    auto observer = std::make_shared<FloorplanExperiment>(input.floorplan.experiment ? *input.floorplan.experiment : FloorplanExperiment{});
    const auto previous = *observer;
    observer->attempt_completed = [&](const auto &row) { trace.completed(row); if (previous.attempt_completed) previous.attempt_completed(row); };
    observer->unscoped_estimate = [&](double value) { trace.estimated(value); if (previous.unscoped_estimate) previous.unscoped_estimate(value); };
    input.floorplan.experiment = observer;
    ExperimentProbeResult result;
    result.placement = build_pcb_model(input);
    auto candidates = ja();
    result.document.data = jo({{"tag", j(tag)}, {"K", j(input.floorplan.cross_budget_k)},
        {"n_calls", j(static_cast<double>(trace.attempts.size()))}, {"cands", ja()}});
    result.document.float_paths.insert("/K");
    for (const auto &row : trace.distinct_outlines()) {
        const auto base = "/cands/" + std::to_string(candidates.array_value.size());
        candidates.array_value.push_back(jo({{"w", j(row.w)}, {"h", j(row.h)}, {"packed", jb(row.packed)},
            {"free", jb(row.punch_free)}, {"est", row.estimate ? j(*row.estimate) : JsonNode{}}}));
        for (const auto *key : {"/w", "/h", "/est"}) result.document.float_paths.insert(base + key);
    }
    set(result.document.data, "cands", std::move(candidates));
    result.output = "W12BOUND " + render_experiment_json(result.document) + "\n";
    return result;
}
ExperimentProbeResult run_w12_stageprobe(PcbPlacementInput input, const std::string &tag,
    const std::vector<std::string> &sheets, bool conservative_only) {
    using namespace experiment_detail;
    apply_layers(input, sheets);
    auto floorplan = std::make_shared<FloorplanExperiment>(input.floorplan.experiment ? *input.floorplan.experiment : FloorplanExperiment{});
    floorplan->conservative_only = floorplan->conservative_only || conservative_only;
    input.floorplan.experiment = floorplan;
    ExperimentProbeResult result;
    result.document.data = jo({{"tag", j(tag)}, {"rows", ja()}});
    const auto previous = input.experiment;
    auto observer = std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint = [&](const auto &row) {
        add_stage(result.document, row);
        if (previous && previous->checkpoint) previous->checkpoint(row);
    };
    input.experiment = observer;
    result.placement = build_pcb_model(input);
    const auto &model = result.placement.model;
    const auto lengths = experiment_cross_lengths(model.insts);
    const auto base = "/rows/" + std::to_string(field(result.document.data, "rows").array_value.size());
    field(result.document.data, "rows").array_value.push_back(jo({{"stage", j("FINAL_MODEL")},
        {"cross", j(lengths.cross)}, {"total", j(lengths.total)}, {"n_bottom", j(model.n_bottom)}, {"n_top", j(model.n_top)},
        {"board", j(fmt(model.board_w)+"x"+fmt(model.board_h))}}));
    result.document.float_paths.insert(base + "/cross"); result.document.float_paths.insert(base + "/total");
    result.output = "W12PROBE " + render_experiment_json(result.document) + "\n";
    return result;
}
} // namespace schgen
