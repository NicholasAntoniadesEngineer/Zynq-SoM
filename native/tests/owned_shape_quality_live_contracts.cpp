#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/netlist_gate.hpp"
#include "../src/floorplan_internal.hpp"
#include <algorithm>
#include <iostream>

int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 3 || !open_part_catalog(argv[2])) throw std::runtime_error("usage: quality-live REPOSITORY CATALOG");
        const auto require = [](bool ok, const char* why) { if (!ok) throw std::runtime_error(why); };
        const auto paths = resolve_project_paths(argv[1], "carrier");
        const auto circuits = load_project_circuits(paths);
        std::vector<CircuitSheetIr> sheets;
        for (const auto& c : circuits) sheets.push_back(c.circuit);
        const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
            parse_json_file((paths.project_root / "som_mapping.json").string()));
        require(link.ok(), "live link failed");
        BoardInputOptions options; options.compact_search = true;
        auto input = load_board_inputs(paths, circuits, link,
            extract_netlist(paths.project_root / "Zynq_Carrier.kicad_sch"), options);
        input.floorplan.sheets.erase(std::remove_if(input.floorplan.sheets.begin(), input.floorplan.sheets.end(),
            [&](const auto& s) { return !input.owned_groups.count(s.name); }), input.floorplan.sheets.end());
        auto& spec = *input.floorplan.spec; spec.edges.clear(); spec.ordered_edges.clear();
        for (auto i = spec.interior.begin(); i != spec.interior.end();)
            if (!input.owned_groups.count(i->first)) i = spec.interior.erase(i); else ++i;
        const auto zones = build_pcb_zone_geometry(input);
        input.floorplan.owned_shape_quality[{"stale", 99}] = {};
        const auto prepared = prepare_pcb_floorplan(input, zones);
        require(prepared.owned_shape_quality.size() == zones.owned_shape_quality.size() &&
            !prepared.owned_shape_quality.count({"stale", 99}), "stale quality transported");
        for (const auto& [key, q] : zones.owned_shape_quality) {
            const auto& actual = prepared.owned_shape_quality.at(key);
            require(actual.state == q.state && actual.subjects == q.subjects &&
                actual.bypass_pad_gaps == q.bypass_pad_gaps && actual.bulk_pad_gaps == q.bulk_pad_gaps &&
                actual.fanout_starved == q.fanout_starved && actual.diagnostics == q.diagnostics &&
                actual.measurements.size() == q.measurements.size(), "quality transport changed evidence");
        }
        auto legacy = input; legacy.floorplan.compact_search = false;
        require(prepare_pcb_floorplan(legacy, zones).owned_shape_quality.empty(), "default inherited compact quality");
        require(prepared.accounting.quantization_engagements == zones.quantization_engagements,
            "quality transport changed invocation counts");

        // Narrow native seat/estimator probe, NOT Engine::run or a board solve.
        // Only these two zones are loaded; the trial seats a single block on an
        // empty fixture canvas, matching the selector's first-partial context.
        floorplan_detail::Engine engine(prepared);
        engine.initialize(); engine.prepare_geometry(); engine.prepare_cross();
        engine.plan.board_w = engine.plan.board_h = 200;
        std::size_t tied = 0, elected = 0;
        for (const auto& [sheet, variants] : zones.geometry.shapes) {
            const auto sheet_name = sheet;
            for (std::size_t i = 0; i < variants.size(); ++i) {
                const auto marker = variants[i].tag.find("/owned-pins-");
                if (marker == std::string::npos) continue;
                const auto tag = variants[i].tag.substr(0, marker);
                const auto parent = std::find_if(variants.begin(), variants.end(), [&](const auto& s) { return s.tag == tag; });
                require(parent != variants.end(), "missing candidate parent");
                const int old_index = static_cast<int>(parent - variants.begin());
                if (parent->w != variants[i].w || parent->h != variants[i].h) continue;
                const auto& offers = engine.shape_sets[1].at(sheet);
                std::vector<SeatShapeCand> candidates;
                for (int index : {old_index, static_cast<int>(i)}) {
                    const auto& s = offers.at(static_cast<std::size_t>(index));
                    candidates.push_back({index, s.w, s.h, s.reach, s.inset,
                        floorplan_detail::side_mask(s.side), s.side, s.comps, -200, 400, -200, 400});
                }
                Occupancy occupancy(200, 200, floorplan_detail::clear, 10, engine.max_reach,
                    floorplan_detail::occ_step, floorplan_detail::frontier_half);
                QuantizationCounts probe_counts;
                auto hits = seat_shape_candidates(occupancy, 100, 100, candidates, 200, 200,
                    floorplan_detail::clear, &probe_counts);
                require(hits.size() == 2, "same-size live candidate lost before selector");
                std::sort(hits.begin(), hits.end(), [](const auto& a, const auto& b) {
                    return std::tie(a.dist_key, a.index) < std::tie(b.dist_key, b.index);
                });
                auto rank = [&](const SeatShapeHit& hit) {
                    FloorplanBlock block; block.name = sheet_name; block.kind = "interior";
                    block.x = hit.x; block.y = hit.y; block.w = hit.w; block.h = hit.h;
                    block.side = hit.side; block.shape_idx = hit.index;
                    return OwnedShapeTieRank{hit.index, true, hit.w, hit.h,
                        engine.estimate({&block}, sheet_name), hit.dist_key, hit.side};
                };
                const auto best = rank(hits.front()); const auto next = rank(hits.back());
                if (best.estimator != next.estimator || best.distance_key != next.distance_key) continue;
                ++tied;
                const auto before_counts = engine.plan.accounting.quantization_engagements;
                const auto chosen = owned_shape_select_tied_bucket(prepared.compact_search,
                    prepared.owned_shape_quality, sheet, {best, next});
                const auto reversed = owned_shape_select_tied_bucket(prepared.compact_search,
                    prepared.owned_shape_quality, sheet, {next, best});
                require(engine.plan.accounting.quantization_engagements == before_counts, "quality comparison manufactured precision calls");
                require(chosen == static_cast<int>(i) && reversed == chosen, "real same-size bucket winner changed with permutation");
                const auto bound = bind_pcb_zone_shapes(zones, {{sheet, *chosen}});
                require(bound.top_off.at(sheet) == variants[i].top_off && bound.bot_off.at(sheet) == variants[i].bot_off,
                    "elected alternative not bindable");
                ++elected;
            }
        }
        require(elected > 0, "no live same-size tied owned alternative exercised");
        close_part_catalog();
        std::cout << "PASS transport " << prepared.owned_shape_quality.size() << " shapes; " << tied
                  << " native feasible same-size estimator/distance ties, " << elected
                  << " owned candidates elected and bound; no board solve/render\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
