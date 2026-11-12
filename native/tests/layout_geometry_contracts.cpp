#include "schgen/layout_geometry.hpp"

#include <functional>
#include <iostream>
#include <limits>
#include <string>

namespace {

using namespace schgen::layout;

struct TurnCase {
    Turn turn;
    double degrees;
    Box court;
    Point first, second;
};

namespace expected {
constexpr Nm unit = 1000000;
constexpr Box local_court{-1 * unit, -2 * unit, 5 * unit, 3 * unit};
constexpr Point local_first{4 * unit, 0}, local_second{0, -1 * unit};
constexpr Point origin{50 * unit, 40 * unit};
constexpr TurnCase turn_cases[] = {
    {Turn::none, 0, {49 * unit, 38 * unit, 55 * unit, 43 * unit}, {54 * unit, 40 * unit}, {50 * unit, 39 * unit}},
    {Turn::quarter, 90, {48 * unit, 35 * unit, 53 * unit, 41 * unit}, {50 * unit, 36 * unit}, {49 * unit, 40 * unit}},
    {Turn::half, 180, {45 * unit, 37 * unit, 51 * unit, 42 * unit}, {46 * unit, 40 * unit}, {50 * unit, 41 * unit}},
    {Turn::three_quarter, 270, {47 * unit, 39 * unit, 52 * unit, 45 * unit}, {50 * unit, 44 * unit}, {51 * unit, 40 * unit}}};
constexpr double lattice_sample = 27.2531, wrapped_degrees = 450, negative_degrees = -90;
constexpr Nm lattice_nm = 27253100;
constexpr double skew_degrees = 45, off_lattice = 0.0000004, beyond_span = 2000;
constexpr double ceil_sample = 3.2101234567;
constexpr Nm ceil_nm_value = 3210124;
constexpr Box base_box{0, 0, 10 * unit, 10 * unit};
constexpr Box touching_box{10 * unit, 0, 20 * unit, 10 * unit};
constexpr Box crossing_box{9 * unit, 9 * unit, 20 * unit, 20 * unit};
constexpr Nm crossing_area = unit * unit;
constexpr Box far_box{13 * unit, 14 * unit, 20 * unit, 20 * unit};
constexpr Nm far_gap = 5 * unit;
constexpr Disc hole_disc{{30480000, 30480000}, 3450000};
constexpr Disc mark_disc{{34 * unit, 34 * unit}, 1250000};
constexpr Box mark_box{32750000, 32750000, 35250000, 35250000};
constexpr Disc side_disc{{15 * unit, 5 * unit}, 5 * unit};
constexpr Disc corner_disc{{13 * unit, 14 * unit}, 5 * unit};
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("layout geometry contract failed: " + what);
}

void rejects(const std::string& what, const std::function<void()>& action) {
    try {
        action();
    } catch (const LayoutError&) {
        return;
    }
    throw std::runtime_error("layout geometry contract failed: accepted " + what);
}

void turns_follow_board_convention() {
    for (const auto& item : expected::turn_cases) {
        require(placed(expected::local_court, expected::origin, item.turn) == item.court, "courtyard turn");
        require(placed(expected::local_first, expected::origin, item.turn) == item.first, "first pad turn");
        require(placed(expected::local_second, expected::origin, item.turn) == item.second, "second pad turn");
        require(turn_of(item.degrees) == item.turn && degrees_of(item.turn) == item.degrees, "degrees");
        for (const auto& other : expected::turn_cases)
            require(turned(turned(expected::local_first, item.turn), other.turn) ==
                        turned(expected::local_first, combined(item.turn, other.turn)), "turn composition");
    }
    require(turn_of(expected::wrapped_degrees) == Turn::quarter, "wrapped rotation");
    require(turn_of(expected::negative_degrees) == Turn::three_quarter, "negative rotation");
    require(combined(Turn::quarter, Turn::three_quarter) == Turn::none, "full turn");
    rejects("a skew rotation", [] { turn_of(expected::skew_degrees); });
}

void conversion_is_exact_or_loud() {
    require(to_nm(expected::lattice_sample) == expected::lattice_nm, "millimetres to nanometres");
    require(to_mm(to_nm(expected::lattice_sample)) == expected::lattice_sample, "round trip");
    require(ceil_nm(expected::ceil_sample) == expected::ceil_nm_value, "ceiling conversion");
    require(ceil_nm(expected::lattice_sample) == expected::lattice_nm, "ceiling keeps lattice values");
    rejects("an off-lattice value", [] { to_nm(expected::off_lattice); });
    rejects("a value beyond the span", [] { to_nm(expected::beyond_span); });
    rejects("a non-finite value", [] { to_nm(std::numeric_limits<double>::infinity()); });
}

void overlap_is_strict() {
    require(!overlaps(expected::base_box, expected::touching_box), "touching boxes do not overlap");
    require(overlaps(expected::base_box, expected::crossing_box), "crossing boxes overlap");
    require(overlap_area(expected::base_box, expected::crossing_box) == expected::crossing_area, "overlap area");
    require(overlap_area(expected::base_box, expected::touching_box) == 0, "no area when touching");
    require(overlaps(expected::mark_box, expected::hole_disc), "box near a disc overlaps by bounding box");
    require(!overlaps(expected::mark_disc, expected::hole_disc), "discs beside each other do not overlap");
    require(!overlaps(expected::base_box, expected::side_disc), "disc touching a side does not overlap");
    require(overlaps(grown(expected::base_box, 1), expected::side_disc), "one nanometre closer overlaps");
    require(!overlaps(expected::base_box, expected::corner_disc), "disc touching a corner does not overlap");
    require(overlaps(grown(expected::base_box, 1), expected::corner_disc), "corner one nanometre closer overlaps");
}

void gaps_compare_exactly() {
    require(gap_at_least(expected::base_box, expected::far_box, expected::far_gap), "gap equal to the need passes");
    require(!gap_at_least(expected::base_box, expected::far_box, expected::far_gap + 1), "one nanometre short fails");
    require(gap_at_least(expected::base_box, expected::crossing_box, 0), "no need always passes");
    require(inside(expected::crossing_box, united(expected::base_box, expected::crossing_box)), "union contains parts");
    require(opposite(Face::top) == Face::bottom && opposite(Face::bottom) == Face::top, "faces");
}

}

int main() {
    try {
        turns_follow_board_convention();
        conversion_is_exact_or_loud();
        overlap_is_strict();
        gaps_compare_exactly();
        std::cout << "layout geometry contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
