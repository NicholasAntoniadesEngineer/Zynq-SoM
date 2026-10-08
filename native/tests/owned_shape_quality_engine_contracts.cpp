#include "floorplan_internal.hpp"
#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/netlist_gate.hpp"
#include "fresh_project_schematic.hpp"
#include <algorithm>
#include <iostream>
#include <limits>

namespace {
using namespace schgen;
using floorplan_detail::Engine;
std::size_t checks = 0;
void require(bool ok, const char* why) { ++checks; if (!ok) throw std::runtime_error(why); }
bool equal(const JsonNode& a, const JsonNode& b) {
    if (a.kind != b.kind || a.bool_value != b.bool_value || a.number_value != b.number_value ||
        a.string_value != b.string_value || a.array_value.size() != b.array_value.size() ||
        a.object_value.size() != b.object_value.size()) return false;
    for (std::size_t i = 0; i < a.array_value.size(); ++i)
        if (!equal(a.array_value[i], b.array_value[i])) return false;
    for (std::size_t i = 0; i < a.object_value.size(); ++i)
        if (a.object_value[i].first != b.object_value[i].first ||
            !equal(a.object_value[i].second, b.object_value[i].second)) return false;
    return true;
}
using Offers = std::map<std::string, std::tuple<std::string, std::string, int,
    std::optional<double>, std::optional<double>>>;
Offers offers(const Engine& e) {
    Offers out;
    for (const auto& [name, s] : e.side_offers)
        out[name] = {s.offered, s.chosen, s.shape, s.incumbent, s.challenger};
    return out;
}
OwnedShapeQuality quality(double a, double b) {
    OwnedShapeQuality q; q.state = OwnedShapeQualityState::Measured;
    q.fanout_starved = 0;
    q.bypass_pad_gaps = {{"C1", a}, {"C2", b}};
    q.bulk_pad_gaps = {{"C3", 9}};
    for (const auto* cap : {"C1", "C2", "C3"})
        q.subjects[cap] = {"U1", "5", "1", "2", "VCC", "GND", "top", "top",
            std::string(cap) == "C3" ? OwnedShapeRole::OutputBulk : OwnedShapeRole::Bypass};
    return q;
}
FloorplanInput input(int variants) {
    FloorplanInput in;
    in.som.w = in.som.h = 8;
    in.module_offset = FloorplanPoint{0, 0}; in.compact_search = true;
    for (int i = 0; i < variants; ++i) {
        FloorplanZoneShape shape; shape.w = 8; shape.h = 6;
        shape.tag = "fixture-" + std::to_string(i);
        in.geometry.shapes["pilot"].push_back(shape);
    }
    return in;
}
struct Result { FloorplanPlan plan; Offers side; int chosen; };
Result pack(const FloorplanInput& in, const std::set<int>& infeasible = {}) {
    // Same minimal actual-engine setup style as compact_retry_contracts.
    // No wrapper/reimplemented selector, mock estimator or comparator sorting.
    Engine e(in); e.board_size(80, 70); e.plan.punch_free = true;
    FloorplanBlock b; b.name = "pilot"; b.kind = "interior"; b.zone = "E";
    b.w = 8; b.h = 6; b.x = -11; b.y = -13;
    e.plan.interior_blocks.push_back(b); e.zbox[b.name] = {8, 6};
    const auto& shapes = in.geometry.shapes.at("pilot");
    for (std::size_t i = 0; i < shapes.size(); ++i)
        e.shape_sets[1][b.name].push_back({infeasible.count(static_cast<int>(i)) ? 200. : shapes[i].w,
            shapes[i].h, {}, {}, shapes[i].side, {}});
    e.plan.accounting.quantization_engagements = {{"entry-sentinel", 19}};
    require(e.attempt_pack_impl(false), "actual engine fixture did not pack");
    const auto& placed = e.plan.interior_blocks.at(0);
    require(placed.x != -11 && placed.y != -13, "actual placement/refinement did not execute");
    require(e.side_offers.at("pilot").shape == placed.shape_idx, "offer and final shape index differ");
    require(e.plan.accounting.quantization_engagements.at("entry-sentinel") == 19,
        "engine lost incoming receipt");
    return {e.plan, offers(e), placed.shape_idx};
}
void unchanged(const Result& a, const Result& b, const char* why) {
    require(a.chosen == b.chosen && a.side == b.side &&
        equal(floorplan_plan_json(a.plan), floorplan_plan_json(b.plan)) &&
        a.plan.accounting.quantization_engagements == b.plan.accounting.quantization_engagements &&
        a.plan.accounting.fallback_events == b.plan.accounting.fallback_events, why);
}
void synthetic() {
    auto in = input(2); const auto baseline = pack(in);
    require(baseline.chosen == 0, "baseline should retain incumbent index zero");
    in.owned_shape_quality = {{{"pilot", 0}, quality(3, 4)}, {{"pilot", 1}, quality(2, 4)}};
    const auto improved = pack(in);
    require(improved.chosen == 1, "engine failed to replace dominated same-primary original");
    require(improved.plan.interior_blocks[0].w == baseline.plan.interior_blocks[0].w &&
        improved.plan.interior_blocks[0].h == baseline.plan.interior_blocks[0].h &&
        improved.plan.interior_blocks[0].x == baseline.plan.interior_blocks[0].x &&
        improved.plan.interior_blocks[0].y == baseline.plan.interior_blocks[0].y,
        "same-primary quality unexpectedly changed rectangle placement");
    require(improved.plan.accounting.quantization_engagements == baseline.plan.accounting.quantization_engagements,
        "selection changed actual-work counts in identical-geometry fixture");
    for (int mutation = 0; mutation < 10; ++mutation) {
        auto bad = in; auto& q = bad.owned_shape_quality.at({"pilot", 1});
        switch (mutation) {
            case 0: q.state = OwnedShapeQualityState::Rejected; break;
            case 1: q.state = OwnedShapeQualityState::NotApplicable; break;
            case 2: q.bypass_pad_gaps.at("C1") = std::numeric_limits<double>::quiet_NaN(); break;
            case 3: q.bypass_pad_gaps.erase("C2"); break;
            case 4: q.subjects.at("C1").owner = "U2"; break;
            case 5: q.subjects.at("C1").cap_side = "bottom"; break;
            case 6: q.subjects.at("C1").role = OwnedShapeRole::OutputBulk; break;
            case 7: bad.owned_shape_quality.erase({"pilot", 0}); break;
            case 8: bad.owned_shape_quality.erase({"pilot", 1}); break;
            case 9: q.fanout_starved.reset(); break;
        }
        unchanged(pack(bad), baseline, "invalid/missing quality changed actual engine output/receipts");
    }
    auto equal_quality = in; equal_quality.owned_shape_quality.at({"pilot", 1}) = quality(3, 4);
    unchanged(pack(equal_quality), baseline, "equal quality lost stable incumbent");
    auto tradeoff = in; tradeoff.owned_shape_quality.at({"pilot", 1}) = quality(2, 5);
    unchanged(pack(tradeoff), baseline, "incomparable quality lost stable incumbent");
    auto legacy = in; legacy.compact_search = false;
    auto legacy_empty = legacy; legacy_empty.owned_shape_quality.clear();
    unchanged(pack(legacy), pack(legacy_empty), "default engine behavior/receipts changed");
    auto blocked_empty = in; blocked_empty.owned_shape_quality.clear();
    unchanged(pack(in, {1}), pack(blocked_empty, {1}), "quality overrode feasibility");

    auto cycle = input(4);
    // Shape zero has no feasible seat. Same-size B/1, C/2 and A/3 remain.
    // Invalid dominance-else-index sorting cycles; a streaming dominance fold
    // from B/1 would choose A/3. The true nondominated frontier chooses C/2.
    std::vector<int> insertion{1, 2, 3}; int permutations = 0;
    const auto without_quality = pack(cycle, {0});
    require(without_quality.chosen == 1, "three-way baseline must start from B/1");
    do {
        cycle.owned_shape_quality.clear();
        for (int index : insertion)
            cycle.owned_shape_quality[{"pilot", index}] = index == 1 ? quality(1, 2) :
                index == 2 ? quality(2, 0) : quality(0, 1);
        const auto selected = pack(cycle, {0});
        require(selected.chosen == 2, "actual engine did not select complete three-way frontier C/2");
        require(selected.plan.accounting.quantization_engagements == without_quality.plan.accounting.quantization_engagements,
            "three-way quality changed identical-geometry execution counts");
        ++permutations;
    } while (std::next_permutation(insertion.begin(), insertion.end()));
    require(permutations == 6, "all metadata population permutations tested");
    std::cout << "PASS actual Engine::attempt_pack_impl: original 0 -> improved 1; "
                 "invalid/missing/default unchanged; three-way B/1 -> frontier C/2 (not fold A/3), six input permutations\n";
}

void pilots(const char* root, const char* catalog) {
    // Read-only circuit/hierarchy/catalog sources; no hidden opened singleton.
    close_part_catalog(); auto paths = resolve_project_paths(root, "carrier");
    paths.part_catalog_file = catalog;
    const auto circuits = load_project_circuits(paths);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& c : circuits) sheets.push_back(c.circuit);
    const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
        parse_json_file((paths.project_root / "som_mapping.json").string()));
    require(link.ok(), "live link failed");
    BoardInputOptions options; options.compact_search = true;
    auto in = load_board_inputs(paths, circuits, link,
        extract_netlist(test::fresh_project_schematic(paths,circuits)), options);
    in.floorplan.sheets.erase(std::remove_if(in.floorplan.sheets.begin(), in.floorplan.sheets.end(),
        [&](const auto& s) { return !in.owned_groups.count(s.name); }), in.floorplan.sheets.end());
    auto& spec = *in.floorplan.spec; spec.edges.clear(); spec.ordered_edges.clear();
    for (auto i = spec.interior.begin(); i != spec.interior.end();)
        if (!in.owned_groups.count(i->first)) i = spec.interior.erase(i); else ++i;
    const auto zones = build_pcb_zone_geometry(in);
    const auto prepared = prepare_pcb_floorplan(in, zones);
    const auto run = [&](const FloorplanInput& input) {
        Engine e(input); e.initialize(); e.prepare_geometry(); e.prepare_cross();
        // Fixed test canvas for two real zones; no full-carrier sizing/search.
        e.board_size(200, 200); e.plan.punch_free = true;
        require(e.attempt_pack_impl(false), "two-pilot complete pack attempt failed");
        require(e.plan.interior_blocks.size() == 2, "two-pilot scope changed");
        return e.plan;
    };
    auto no_quality = prepared; no_quality.owned_shape_quality.clear();
    const auto before = run(no_quality), after = run(prepared);
    std::size_t changed = 0, owned = 0;
    for (const auto& b : after.interior_blocks) {
        const auto previous = std::find_if(before.interior_blocks.begin(), before.interior_blocks.end(),
            [&](const auto& old) { return old.name == b.name; });
        require(previous != before.interior_blocks.end(), "pilot vanished");
        const auto& shape = zones.geometry.shapes.at(b.name).at(static_cast<std::size_t>(b.shape_idx));
        const bool owned_shape = shape.tag.find("/owned-pins-") != std::string::npos;
        owned += owned_shape;
        if (previous->shape_idx != b.shape_idx) {
            ++changed;
            require(previous->w == b.w && previous->h == b.h, "quality changed pilot primary dimensions");
        }
        const auto bound = bind_pcb_zone_shapes(zones, {{b.name, b.shape_idx}});
        require(bound.top_off.at(b.name) == shape.top_off && bound.bot_off.at(b.name) == shape.bot_off,
            "whole-pack selected shape did not bind");
        std::cout << b.name << " complete pack: " << previous->shape_idx << " -> " << b.shape_idx
                  << " " << shape.tag << " (" << b.w << " x " << b.h << ")\n";
    }
    require(changed > 0 && owned > 0, "real two-pilot pack did not select an improved owned alternative");
    std::cout << "PASS two real pilots through complete attempt_pack_impl (seat/refine), " << changed
              << " changed selections, " << owned << " owned alternatives bound; no full-carrier solve/render\n";
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 1 && argc != 3) throw std::runtime_error("usage: quality-engine [REPOSITORY CATALOG]");
        synthetic();
        if (argc == 3) pilots(argv[1], argv[2]);
        std::cout << "PASS " << checks << " engine selection assertions\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
