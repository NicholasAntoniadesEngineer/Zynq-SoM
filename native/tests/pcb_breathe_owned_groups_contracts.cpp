#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/netlist_gate.hpp"
#include "pcb_placement_internal.hpp"
#include "fresh_project_schematic.hpp"
#include <iostream>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
struct Fixture {
    PcbPlacementInput in;
    PcbZoneResult zones;
    FloorplanStage stage;
    std::unique_ptr<Placer> placer;
    std::string owner, cap;
    Fixture(const PcbPlacementInput& source, bool compact, int fixed, bool opposite,
            bool reverse = false) : in(source) {
        in.floorplan.compact_search = compact;
        const auto& row = owned_group_placements(*in.owned_groups.at("bringup_rails")).at(0);
        owner = row.owner; cap = row.cap;
        stage.plan.board_w = stage.plan.board_h = 120;
        stage.plan.som_x = stage.plan.som_y = 90;
        placer = std::make_unique<Placer>(in, zones, stage);
        const std::string side = reverse ? "bottom" : "top";
        part(owner, side, 60, 60, true, fixed == 1);
        part(cap, opposite ? (reverse ? "top" : "bottom") : side, 68, 64, false, fixed == 2);
        part("U_OTHER", side, 70, 60, true, false);
        part("J_FIXED", side, 58, 60, false, true);
    }
    void part(const std::string& ref, const std::string& side, double x, double y,
              bool active, bool fixed) {
        std::string bytes = "(footprint probe (layer F.Cu)";
        for (int k = 1; k <= (active ? 3 : 2); ++k)
            bytes += " (pad \"" + std::to_string(k) +
                "\" smd rect (at 0 0) (size 0.2 0.2) (layers F.Cu F.Mask))";
        bytes += ")";
        auto& p = *placer;
        // Synthetic geometry deliberately puts the capacitor nearer a wrong
        // subject. Trusted ownership itself comes from the real input resolver.
        p.ctx.by_ref[ref] = {ref, ref, "bringup_rails", "probe", "probe", "probe"};
        p.ctx.pool[ref] = pcb_check_footprint(ref, bytes);
        p.geometry.resolvable[ref] = ref;
        p.geometry.bbox_of[ref] = {-.5, -.5, .5, .5};
        p.geometry.side_of[ref] = side;
        if (fixed) p.geometry.conn_edge[ref] = "left";
        p.pos[ref] = {x, y};
    }
};
}
int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 3 || !open_part_catalog(argv[2]))
            throw std::runtime_error("usage: breathe-owned REPOSITORY CATALOG");
        const auto paths = resolve_project_paths(argv[1], "carrier");
        const auto circuits = load_project_circuits(paths);
        std::vector<CircuitSheetIr> sheets;
        for (const auto& c : circuits) sheets.push_back(c.circuit);
        const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
            parse_json_file((paths.project_root / "som_mapping.json").string()));
        require(link.ok(), "live hierarchy link failed");
        BoardInputOptions options; options.compact_search = true;
        const auto source = load_board_inputs(paths, circuits, link,
            extract_netlist(test::fresh_project_schematic(paths,circuits)), options);
        for (bool reverse : {false, true}) for (bool opposite : {false, true})
            for (int fixed : {0, 1, 2}) {
                Fixture f(source, true, fixed, opposite, reverse);
                const auto before = f.placer->pos;
                f.placer->breathe("A");
                const auto owner = f.placer->pos.at(f.owner), cap = f.placer->pos.at(f.cap);
                require(std::abs(cap.first-owner.first-8) < 1e-9 &&
                        std::abs(cap.second-owner.second-4) < 1e-9,
                        "breathe assigned declared capacitor to nearest foreign owner");
                if (fixed)
                    require(owner == before.at(f.owner) && cap == before.at(f.cap),
                            "fixed ownership member granted movement to its group");
                else
                    require(owner.first > before.at(f.owner).first,
                            "test must exercise an actual owned-group move");
                require(f.placer->pos.at("J_FIXED") == before.at("J_FIXED"), "fixed obstacle moved");
            }
        Fixture legacy(source, false, 0, false), empty(source, false, 0, false);
        empty.in.owned_groups.clear();
        legacy.placer->breathe("A"); empty.placer->breathe("A");
        require(legacy.placer->pos == empty.placer->pos &&
                legacy.placer->ctx.quantization == empty.placer->ctx.quantization,
                "default behavior/counts changed when ownership attached");
        Fixture missing(source, true, 0, false);
        missing.placer->pos.erase(missing.cap);
        bool rejected = false;
        try { missing.placer->breathe("A"); } catch (const std::exception&) { rejected = true; }
        require(rejected, "partial owned group silently lost its membership");
        Fixture null(source, true, 0, false);
        null.in.owned_groups["bringup_rails"] = nullptr;
        rejected = false;
        try { null.placer->breathe("A"); } catch (const std::exception&) { rejected = true; }
        require(rejected, "null trusted ownership silently accepted");
        close_part_catalog();
        std::cout << "PASS 12 owned breathe cases, fixed-member closure, default parity and invalid evidence rejection\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
