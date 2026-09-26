#include "pcb_placement_fixture.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/quantize.hpp"
#include "schgen/ratsnest_gate.hpp"
#include <cmath>
#include <iostream>
#include <limits>

namespace {
using namespace placement_fixture;
std::size_t checks = 0;
void require(bool good, const std::string &why) {
    ++checks;
    if (!good) throw std::runtime_error(why);
}
void exact(double a, double b, const std::string &why) {
    require(a == b && (a != 0 || std::signbit(a) == std::signbit(b)), why);
}
void equal(const J &a, const J &b, const std::string &where) {
    require(a.kind == b.kind, where + " type");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), where + " fields");
        for (const auto &[k, v] : b.object_value) equal(field(a, k), v, where + "/" + k);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), where + " length");
        for (std::size_t i = 0; i < b.array_value.size(); ++i) equal(a.array_value[i], b.array_value[i], where);
    } else if (a.kind == JsonKind::Number) exact(a.number_value, b.number_value, where);
    else if (a.kind == JsonKind::String) require(a.string_value == b.string_value, where);
    else if (a.kind == JsonKind::Bool) require(a.bool_value == b.bool_value, where);
}
void rows(const std::vector<FloorplanAttemptObservation> &actual, const J &expected) {
    require(actual.size() == expected.array_value.size(), "completed attempt count");
    for (std::size_t i = 0; i < actual.size(); ++i) {
        const auto &a = actual[i];
        const auto &b = expected.array_value[i];
        exact(a.w, number(b, "w"), "attempt width");
        exact(a.h, number(b, "h"), "attempt height");
        require(a.packed == field(b, "packed").bool_value, "attempt packed");
        require(a.punch_free == field(b, "free").bool_value, "attempt free");
        const auto &e = field(b, "est");
        require(a.estimate.has_value() == (e.kind != JsonKind::Null), "estimate presence");
        if (a.estimate) exact(*a.estimate, e.number_value, "estimate exact rounding");
    }
}
void unit(const std::filesystem::path &root) {
    const auto fixture = parse_json_file((root / "native/tests/data/experiment_tools/observer_reference.json").string());
    FloorplanBoundTrace trace;
    auto observer = trace.observer();
    const auto &bound = field(fixture, "bound");
    std::size_t index = 0;
    for (const auto &e : field(bound, "events").array_value) {
        if (string(e, "kind") == "estimate")
            observe_floorplan_experiment_estimate(&observer, number(e, "value"), !object_field(e, "sheet"));
        else {
            bool threw = false;
            try {
                run_floorplan_experiment_attempt(&observer, field(e, "free").bool_value, [&] {
                    if (auto p = object_field(e, "during"))
                        observe_floorplan_experiment_estimate(&observer, p->number_value, true);
                    if (object_field(e, "throw")) throw std::runtime_error("independent failure");
                    return field(e, "packed").bool_value;
                }, [&](bool packed) {
                    return FloorplanAttemptObservation{number(e, "w"), number(e, "h"), packed,
                        field(e, "free").bool_value, std::nullopt};
                });
            } catch (const std::runtime_error &) { threw = true; }
            require(threw == (object_field(e, "throw") != nullptr), "attempt throw boundary");
        }
        rows(trace.attempts, field(bound, "states").array_value.at(index++));
    }
    rows(trace.distinct_outlines(), field(bound, "distinct"));
    std::size_t snapshots = 0, executions = 0;
    auto attempt = [&] { ++executions; return false; };
    auto snap = [&](bool value) { ++snapshots; return FloorplanAttemptObservation{1, 2, value, false, {}}; };
    FloorplanExperiment empty;
    require(!run_floorplan_experiment_attempt(nullptr, true, attempt, snap), "null attempt result");
    require(!run_floorplan_experiment_attempt(&empty, true, attempt, snap), "empty attempt result");
    PcbPlacementExperiment silent;
    auto frame_factory = [&] { ++snapshots; return PcbPlacementObservation{}; };
    observe_pcb_experiment_checkpoint(nullptr, frame_factory);
    observe_pcb_experiment_checkpoint(&silent, frame_factory);
    require(snapshots == 0 && executions == 2, "default observers create zero snapshots");
    empty.conservative_only = true;
    bool blocked = false;
    try { (void)run_floorplan_experiment_attempt(&empty, true, attempt, snap); }
    catch (const FloorplanError &e) {
        blocked = true;
        require(e.what() == string(field(fixture, "conservative_only"), "error"), "exact forced rejection");
    }
    require(blocked && executions == 2, "conservative-only rejects before work");
    require(!run_floorplan_experiment_attempt(&empty, false, attempt, snap), "conservative allowed");
    for (double value : {0., .1, 2.2, 987.25, std::numeric_limits<double>::max()}) {
        empty.ordinary_via_mm = value;
        validate_floorplan_experiment(empty);
        exact(floorplan_experiment_via_cost(&empty, false, est_via_cost(false)), value, "explicit ordinary knob");
        exact(floorplan_experiment_via_cost(&empty, true, est_via_cost(true)), est_via_cost(true), "impedance stays physical");
    }
    for (double value : {-1., std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
                          std::numeric_limits<double>::quiet_NaN()}) {
        empty.ordinary_via_mm = value;
        bool rejected = false;
        try { validate_floorplan_experiment(empty); } catch (const FloorplanError &) { rejected = true; }
        require(rejected, "nonfinite/negative override rejected");
    }
    exact(floorplan_experiment_via_cost(nullptr, false, est_via_cost(false)), est_via_cost(false), "default cost unchanged");
    const auto &source = field(fixture, "snapshots");
    std::map<std::string, PcbExperimentPart> parts;
    PcbFootprintPool pool;
    std::map<std::pair<std::string, std::string>, std::pair<int, std::string>> nets;
    for (const auto &[r, p] : field(source, "parts").object_value)
        parts[r] = {p.array_value.at(0).string_value, p.array_value.at(1).string_value, p.array_value.at(2).string_value};
    for (const auto &[key, bytes] : field(source, "footprints").object_value)
        pool[key] = pcb_check_footprint(key, bytes.string_value);
    for (const auto &row : field(source, "pin_net").array_value) {
        const auto &p = row.array_value;
        nets[{p.at(0).string_value, p.at(1).string_value}] = {static_cast<int>(p.at(2).array_value.at(0).number_value), p.at(2).array_value.at(1).string_value};
    }
    std::vector<PcbPlacementObservation> captured;
    for (const auto &f : field(source, "frames").array_value) {
        FloorplanOffsets pos; FloorplanRotations rotations;
        std::map<std::string, std::string> sides;
        PcbFootprintPool resolved;
        auto set = [&](const std::string &key) { const auto v = strings(field(f, key)); return std::set<std::string>(v.begin(), v.end()); };
        const auto grid = set("grid_placed"), fixed = set("fixed"), mh = set("mh_refs"), jacks = set("som_j_refs"), mirrors = set("mirror_refs");
        for (const auto &[r, xy] : field(f, "pos").object_value) pos[r] = point(xy);
        for (const auto &[r, key] : field(f, "resolvable").object_value) resolved[r] = pool.at(key.string_value);
        for (const auto &[r, side] : field(f, "side_of").object_value) sides[r] = side.string_value;
        for (const auto &[r, rot] : field(f, "fixed_rot").object_value) rotations[r] = rot.number_value;
        auto got = capture_pcb_experiment_frame({pos, parts, resolved, sides, rotations, grid, fixed, mh, jacks, nets, mirrors}, "probe");
        const auto &expected = field(f, "expected").array_value;
        require(got.has_positions && got.instances.size() == expected.size(), "frame size");
        for (std::size_t i = 0; i < expected.size(); ++i) {
            const auto &a = got.instances[i];
            const auto &b = expected[i];
            require(a.ref == string(b, "ref") && a.sheet == string(b, "sheet") && a.side == string(b, "side") &&
                a.value == string(b, "value") && a.footprint == string(b, "footprint") && a.mirror == field(b, "mirror").bool_value,
                "actual checkpoint metadata");
            exact(a.x, number(b, "x"), "emission x"); exact(a.y, number(b, "y"), "emission y");
            exact(a.rotation, number(b, "rotation"), "checkpoint rotation");
            require(a.mod == pool.at(std::filesystem::path(string(b, "mod_path")).stem().string()), "actual immutable footprint version");
            require(a.pad_nets.size() == field(b, "pad_nets").object_value.size(), "pad-net count");
            for (const auto &[pin, n] : field(b, "pad_nets").object_value)
                require(a.pad_nets.at(pin) == std::make_pair(static_cast<int>(n.array_value[0].number_value), n.array_value[1].string_value), "pad-net identity");
        }
        // Destroy/mutate all borrowed geometry: owned snapshots must remain valid.
        pos.clear(); rotations.clear(); resolved.clear();
        captured.push_back(std::move(got));
    }
    require(captured[0].instances.back().mod != captured[1].instances[1].mod, "historical footprint does not become final footprint");
    require(captured[0].instances.back().side == "bottom" && captured[1].instances[1].side == "top", "historical side does not become final side");
}
void live(const std::filesystem::path &root, const std::string &project) {
    auto fixture = load(root, project);
    auto plain = build_pcb_model(fixture.input);
    auto enabled = fixture.input;
    FloorplanBoundTrace trace;
    enabled.floorplan.experiment = std::make_shared<FloorplanExperiment>(trace.observer());
    std::vector<PcbPlacementObservation> observations;
    auto observer = std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint = [&](const auto &row) { observations.push_back(row); };
    enabled.experiment = observer;
    auto observed = build_pcb_model(enabled);
    equal(pcb_model_json(observed.model), pcb_model_json(plain.model), project + " observer-neutral model");
    require(observed.stages == plain.stages, "observer-neutral stage poses");
    const auto a = pcb_placement_accounting(plain), b = pcb_placement_accounting(observed);
    require(a.quantization_engagements == b.quantization_engagements && a.fallback_events == b.fallback_events,
            "observer-neutral production accounting");
    require(!trace.attempts.empty(), "real packing attempts recorded");
    const std::vector<std::string> names{"zone_pack", "plan_lattice", "shape_bind", "step3_emission", "l4_pull", "edge_seat", "breathe", "refit_facing", "reorder", "corridor_eviction", "instantiate", "emission_frame", "escape_copper"};
    require(observations.size() == names.size(), "all real checkpoints");
    for (std::size_t i = 0; i < names.size(); ++i) {
        const auto &o = observations[i];
        require(o.stage == names[i], "execution order");
        require(o.has_positions == (i >= 3), "checkpoint position availability");
        require(o.plan.has_value() == (i == 1), "plan metadata only at plan_lattice");
        auto moved = observed.model.stage_moves.find(o.stage);
        require(o.moved == (moved == observed.model.stage_moves.end() ? std::nullopt : std::optional<int>(moved->second)), "movement metadata");
        for (const auto &inst : o.instances) require(inst.ref.rfind("FID", 0) != 0, "no retrospective fiducials");
    }
    auto empty = fixture.input;
    empty.experiment = std::make_shared<PcbPlacementExperiment>();
    empty.floorplan.experiment = std::make_shared<FloorplanExperiment>();
    auto silent = build_pcb_model(empty);
    equal(pcb_model_json(silent.model), pcb_model_json(plain.model), project + " default-empty model");
    const auto c = pcb_placement_accounting(silent);
    require(a.quantization_engagements == c.quantization_engagements && a.fallback_events == c.fallback_events, "default-empty accounting");
    std::cout << project << ": live null/empty/recording observer parity, " << trace.attempts.size() << " completed attempts\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc < 2 || argc > 3) throw std::runtime_error("usage: experiment_observer_contracts ROOT [--live]");
        unit(argv[1]);
        if (argc == 3 && std::string(argv[2]) == "--live")
            for (const auto *project : {"carrier", "devkit_mini"}) live(argv[1], project);
        std::cout << "experiment observer contracts: " << checks << " assertions passed\n";
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
