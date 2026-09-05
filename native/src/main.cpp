#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    try {
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
        std::cout << "schgen native occupancy+seat+route+sexpr+emit"
                  << " — kernel self-check ok\n";
        std::cout << "full board generate is still `python -m schgen board` "
                     "until gates and the design DSL land in this binary\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "schgen: " << exc.what() << "\n";
        return 1;
    }
}
