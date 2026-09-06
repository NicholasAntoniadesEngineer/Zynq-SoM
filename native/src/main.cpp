#include "schgen/catalog.hpp"
#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/quantize.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/turn.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "catalog-compile") {
            if (argc != 4) {
                throw std::runtime_error(
                    "usage: schgen catalog-compile <parts_dir> <catalog.bin>");
            }
            if (!schgen::compile_part_catalog(argv[2], argv[3])) {
                throw std::runtime_error("catalog-compile returned false");
            }
            std::cout << "catalog compiled " << argv[3] << "\n";
            return 0;
        }
        const schgen::Box4 a{0.0, 0.0, 10.0, 8.0};
        const schgen::Box4 b{12.0, 0.0, 16.0, 8.0};
        if (schgen::boxes_overlap(a, b, 0.3)) {
            throw std::runtime_error("schgen: separated boxes reported overlap");
        }
        if (!schgen::spot_free(a, 0.25, {b}, {}, {})) {
            throw std::runtime_error("schgen: spot_free rejected a free site");
        }
        schgen::Occupancy occ(160.0, 140.0, 0.3, 20.0, 3.32, 1.0, 0.05);
        occ.add(55.0, 45.0, 50.0, 50.0, {}, {}, 3, {});
        if (!occ.fits_hashed(10.0, 10.0, 16.0, 10.0, {}, {}, 3, {})) {
            throw std::runtime_error("schgen: occupancy rejected a free pose");
        }
        const auto turned = schgen::turn_box({1.0, -2.0, 9.0, 2.0}, 90.0);
        if (turned.x0 != -2.0 || turned.y0 != -9.0 || turned.x1 != 2.0
            || turned.y1 != -1.0) {
            throw std::runtime_error("schgen: turn_box missed a quarter turn");
        }
        if (schgen::outline_snap_up(161.0001) != 165.0) {
            throw std::runtime_error("schgen: outline_snap_up missed the 5 mm grid");
        }
        const auto axis = schgen::pair_axis(a, b);
        if (!axis.axis_x || !axis.a_first) {
            throw std::runtime_error("schgen: pair_axis flipped a separated pair");
        }
        const auto bf = schgen::bellman_ford(2, {0}, {1}, {1.0});
        if (!bf.feasible || bf.dist.size() != 2) {
            throw std::runtime_error("schgen: bellman_ford rejected a free edge");
        }
        const auto dfs = schgen::seat_dfs({{a}, {b}}, {}, 0.3, 1000);
        if (!dfs.solved || dfs.pick.size() != 2) {
            throw std::runtime_error("schgen: seat_dfs failed a free pair");
        }
        const std::string dumped = schgen::sexpr_dumps(
            schgen::sexpr_loads("(kicad_pcb (version 20241229))"));
        if (dumped.find("kicad_pcb") == std::string::npos) {
            throw std::runtime_error("schgen: sexpr roundtrip dropped the tag");
        }
        if (!schgen::cross_edge_fanout_hold(
                {{0.0, 10.0, 20.0, 8.0, {}, {}, 'N'},
                 {40.0, 10.0, 20.0, 8.0, {}, {}, 'S'}},
                0.3)) {
            throw std::runtime_error("schgen: cross_edge_fanout_hold rejected a free pair");
        }
        if (schgen::rects_overlap_any({{0.0, 0.0, 10.0, 8.0}},
                                      {{12.0, 0.0, 16.0, 8.0}}, 1e-6)) {
            throw std::runtime_error("schgen: rects_overlap_any flagged a gap");
        }
        std::cout << "schgen native occupancy+seat+route+sexpr+emit"
                  << " — kernel self-check ok\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "schgen: " << exc.what() << "\n";
        return 1;
    }
}
