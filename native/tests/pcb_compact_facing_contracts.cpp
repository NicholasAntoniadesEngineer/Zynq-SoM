#include "pcb_placement_fixture.hpp"
#include "pcb_placement_internal.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include <iostream>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
std::pair<FloorplanPoint, FloorplanPoint> centers(Placer& p) {
    const auto input = p.ctx.stage_input("power_som", p.geometry);
    const pcb_stage::Engine engine(input);
    const auto outputs = engine.output_refs();
    std::vector<FloorplanPoint> all, own;
    for (const auto& r : p.geometry.refs_by_sheet.at("power_som")) {
        all.push_back(p.pos.at(r));
        if (outputs.count(r)) own.push_back(p.pos.at(r));
    }
    return {points_centroid(all), points_centroid(own)};
}
double facing(Placer& p) {
    const auto [zone, output] = centers(p);
    return facing_align_dot(zone.first, zone.second, output.first, output.second,
        p.plan.som_x + p.plan.som.w / 2 - zone.first,
        p.plan.som_y + p.plan.som.h / 2 - zone.second);
}
Box4 checked_span(Placer& p) {
    PcbCheckModel model;
    model.origin_x = model.origin_y = 0;
    for (const auto& r : p.geometry.refs_by_sheet.at("power_som")) {
        PcbCheckInstance i;
        i.ref = r; i.sheet = "power_som"; i.side = p.side(r);
        i.mod = p.mod(r); i.x = p.pos.at(r).first; i.y = p.pos.at(r).second;
        i.rotation = p.rot(r);
        model.insts.push_back(i);
    }
    PcbCheckInput checked(std::move(model));
    require(check_pcb_placement_contract(checked, "power_som",
        &p.ctx.in.contracts.at("power_som"), p.ctx.board_refs.at("power_som")).ok,
        "local hardware contract");
    std::vector<Box4> boxes;
    for (std::size_t k = 0; k < checked.model().insts.size(); ++k)
        boxes.push_back(checked.courtyard_at(k));
    return *boxes_union(boxes);
}
void downstream(JsonNode& contract, const std::string& target) {
    for (auto& [key, external] : contract.object_value)
        if (key == "external")
            for (auto& [name, value] : external.object_value)
                if (name == "downstream") { value.string_value = target; return; }
    throw std::runtime_error("missing explicit downstream");
}
void run(const std::filesystem::path& root) {
    auto f = placement_fixture::load(root, "carrier");
    const auto zones = build_pcb_zone_geometry(f.input);
    for (auto& b : f.stage.plan.interior_blocks)
        if (b.name == "power_som") b.shape_idx = 2;
    for (const auto* scenario : {"default", "compact", "fixed", "unknown", "sheet"}) {
        const std::string mode = scenario;
        f.input.floorplan.compact_search = mode != "default";
        downstream(f.input.contracts.at("power_som"),
                   mode == "unknown" ? "@unknown" : mode == "sheet" ? "test_target" : "@som");
        Placer p(f.input, zones, f.stage);
        p.seed();
        p.origins.clear(); p.origins["power_som"] = {};
        const auto [zone, output] = centers(p);
        // Derive an opposing target from the actual frozen asymmetric group;
        // no board-specific placement coordinate is used to repair production.
        const FloorplanPoint target{zone.first - 10 * (output.first - zone.first),
                                    zone.second - 10 * (output.second - zone.second)};
        f.stage.plan.som_x = target.first - f.stage.plan.som.w / 2;
        f.stage.plan.som_y = target.second - f.stage.plan.som.h / 2;
        if (mode == "fixed")
            p.geometry.conn_rot[p.geometry.refs_by_sheet.at("power_som").front()] = 0;
        if (mode == "sheet") {
            p.geometry.refs_by_sheet["test_target"] = {"target"};
            p.pos["target"] = target;
        }
        const auto positions = p.pos;
        const auto rotations = p.rotations;
        const auto sides = p.geometry.side_of;
        const auto nets = p.pin_net;
        const auto span = checked_span(p);
        const auto counts = p.ctx.quantization;
        require(facing(p) < 0, "independent failing starting direction");
        p.refit();
        require(nets == p.pin_net && sides == p.geometry.side_of, "net identities and faces unchanged");
        if (mode == "compact" || mode == "sheet") {
            require(facing(p) > 0, "virtual or real downstream facing repaired");
            const auto after = checked_span(p);
            if (mode == "compact") {
                require(std::abs(span.x0-after.x0)<1e-10 && std::abs(span.y0-after.y0)<1e-10 &&
                        std::abs(span.x1-after.x1)<1e-10 && std::abs(span.y1-after.y1)<1e-10,
                        "asymmetric courtyard reservation retained to floating arithmetic precision");
                require(p.ctx.quantization.at("refit_pose_precision") ==
                        2 * p.geometry.refs_by_sheet.at("power_som").size(), "actual trial receipt");
                const auto accepted = p.pos;
                p.refit();
                require(accepted == p.pos, "already-facing incumbent retained");
                require(p.ctx.quantization.at("refit_pose_precision") ==
                        4 * p.geometry.refs_by_sheet.at("power_som").size(), "rejected trial receipt retained");
            }
        } else {
            require(p.pos == positions && p.rotations == rotations && p.ctx.quantization == counts,
                    "default, unknown target and fixed connector remain untouched");
        }
        std::cout << mode << " PASS\n";
    }
}
}
int main(int argc, char** argv) {
    try { if (argc != 2) return 2; run(argv[1]); return 0; }
    catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
