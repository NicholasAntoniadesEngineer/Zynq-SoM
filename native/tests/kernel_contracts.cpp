#include "schgen/occupancy.hpp"
#include "schgen/route.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value, const char* message) {
    // Unlike assert(), these checks remain enabled in Release builds.
    if (!value) throw std::runtime_error(message);
}

template <typename F>
void rejects(F action) {
    try {
        action();
    } catch (const std::runtime_error&) {
        return;
    }
    throw std::runtime_error("invalid input unexpectedly accepted");
}

void rounding() {
    // Exact expected values from the established Python differential tests.
    const std::vector<std::pair<double, double>> cases = {
        {11.24955, 11.2495}, {40.74095, 40.7409},
        {0.00005, 0.0001}, {-0.00005, -0.0001}, {-11.24955, -11.2495},
        {1.23456, 1.2346}, {1.23454, 1.2345}};
    for (const auto& [value, expected] : cases) {
        require(schgen::py_round(value, 4) == expected,
                "decimal rounding changed a placement coordinate");
    }
    require(schgen::py_round(2.5, 0) == 2.0, "half-even rounding failed");
    require(schgen::py_round(3.5, 0) == 4.0, "half-even rounding failed");
    require(std::signbit(schgen::py_round(-0.0, 4)), "negative zero lost");
}

void sexpr() {
    const std::string unicode =
        "(descr \"TF-SMD_TF-01A — TF-01A (TF-SMD_TF-01A) "
        "(EasyEDA/LCSC C91145, faithful conversion)\")";
    require(schgen::sexpr_dumps(schgen::sexpr_loads(unicode)) == unicode,
            "UTF-8 text changed line wrapping");
    require(schgen::sexpr_dumps(schgen::sexpr_loads(
                "(general (thickness 1.6))")) ==
                "(general\n\t(thickness 1.6)\n)", "nested serialization changed");
    for (const auto* invalid : {"", "(", "(a", "\"unterminated", "(a) (b)", ")"}) {
        rejects([&] { schgen::sexpr_loads(invalid); });
    }
}

void routing() {
    constexpr double grid_mm = 1.27;
    schgen::RouteGrid grid;
    grid.claim("A", {{0, 0}, {1, 0}}, "stem");
    rejects([&] { grid.claim("B", {{1, 0}}, "crossing"); });
    require(grid.free_or("A", {1, 0}) && !grid.free_or("B", {1, 0}),
            "net ownership changed after rejection");
    rejects([&] { grid.claim("B", {{2, 0}, {1, 0}}, "late conflict"); });
    require(grid.free_or("A", {2, 0}), "failed route claim left occupied cells");
    grid.block_box(-1.0, 2.0, 4.0, 5.0, grid_mm);
    const auto way = schgen::route_bfs_join(
        grid, "A", {{0.0, 0.0}}, {{5.08, 0.0}}, grid_mm);
    require(way == std::vector<schgen::RoutePoint>{{0.0, 0.0}, {5.08, 0.0}},
            "straight route changed");
    rejects([&] { schgen::route_cells_between({0, 0}, {1.27, 1.27}, grid_mm); });
    rejects([&] { schgen::route_cell_of(0.5, 0.0, grid_mm); });
}

void seating() {
    const schgen::Box4 a{0, 0, 2, 2}, hit{0.5, 0.5, 2.5, 2.5}, free{4, 0, 6, 2};
    const auto result = schgen::seat_dfs({{a}, {hit, free}}, {}, 0.3, 1000);
    require(result.solved && !result.budget_hit
                && result.pick == std::vector<int>{0, 1},
            "DFS did not select the first legal arrangement");
    const auto impossible = schgen::seat_dfs({{a}, {hit}}, {}, 0.3, 1000);
    require(!impossible.solved && !impossible.budget_hit,
            "overlapping seats were accepted");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected one test name");
        const std::string name = argv[1];
        if (name == "rounding") rounding();
        else if (name == "sexpr") sexpr();
        else if (name == "routing") routing();
        else if (name == "seating") seating();
        else throw std::runtime_error("unknown test");
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << '\n';
        return 1;
    }
}
