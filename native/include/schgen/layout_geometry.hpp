#pragma once

#include "schgen/named_constant.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <stdexcept>

namespace schgen::layout {

class LayoutError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

namespace constants {
inline constexpr NamedConstant nano_scale{"nano_scale", 1e6, "nm/mm", "standard",
    "nanometres per millimetre"};
inline constexpr NamedConstant quarter_degrees{"quarter_degrees", 90.0, "deg", "standard",
    "degrees in one quarter turn"};
inline constexpr NamedConstant lattice_tolerance{"lattice_tolerance", 1e-3, "nm", "policy",
    "largest distance from the nanometre lattice accepted when converting from millimetres"};
inline constexpr NamedConstant span_limit{"span_limit", 1e9, "nm", "policy",
    "largest coordinate magnitude, which keeps squared distances inside 64 bits"};
inline constexpr std::array geometry_registry{nano_scale, quarter_degrees, lattice_tolerance,
                                              span_limit};
}

using Nm = std::int64_t;

inline constexpr int turn_count = 4;
inline constexpr std::size_t edge_count = 4;

enum class Turn : std::uint8_t { none, quarter, half, three_quarter };

enum class Face : std::uint8_t { top, bottom };

struct Point {
    Nm x = 0, y = 0;
};

struct Box {
    Nm x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    constexpr Nm width() const { return x1 - x0; }
    constexpr Nm height() const { return y1 - y0; }
};

struct Disc {
    Point centre;
    Nm radius = 0;
};

constexpr bool operator==(Point a, Point b) { return a.x == b.x && a.y == b.y; }
constexpr bool operator!=(Point a, Point b) { return !(a == b); }
constexpr bool operator==(Box a, Box b) {
    return a.x0 == b.x0 && a.y0 == b.y0 && a.x1 == b.x1 && a.y1 == b.y1;
}
constexpr bool operator!=(Box a, Box b) { return !(a == b); }

constexpr Face opposite(Face face) { return face == Face::top ? Face::bottom : Face::top; }

constexpr Turn combined(Turn first, Turn second) {
    return static_cast<Turn>((static_cast<int>(first) + static_cast<int>(second)) % turn_count);
}

constexpr Point turned(Point point, Turn turn) {
    switch (turn) {
    case Turn::quarter: return {point.y, -point.x};
    case Turn::half: return {-point.x, -point.y};
    case Turn::three_quarter: return {-point.y, point.x};
    case Turn::none: break;
    }
    return point;
}

constexpr Box spanning(Point a, Point b) {
    return {std::min(a.x, b.x), std::min(a.y, b.y), std::max(a.x, b.x), std::max(a.y, b.y)};
}

constexpr Box turned(Box box, Turn turn) {
    return spanning(turned(Point{box.x0, box.y0}, turn), turned(Point{box.x1, box.y1}, turn));
}

constexpr Point shifted(Point point, Point by) { return {point.x + by.x, point.y + by.y}; }

constexpr Box shifted(Box box, Point by) {
    return {box.x0 + by.x, box.y0 + by.y, box.x1 + by.x, box.y1 + by.y};
}

constexpr Point placed(Point local, Point at, Turn turn) { return shifted(turned(local, turn), at); }

constexpr Box placed(Box local, Point at, Turn turn) { return shifted(turned(local, turn), at); }

constexpr Disc placed(Disc local, Point at, Turn turn) {
    return {placed(local.centre, at, turn), local.radius};
}

constexpr Box united(Box a, Box b) {
    return {std::min(a.x0, b.x0), std::min(a.y0, b.y0), std::max(a.x1, b.x1), std::max(a.y1, b.y1)};
}

constexpr Box grown(Box box, Nm margin) {
    return {box.x0 - margin, box.y0 - margin, box.x1 + margin, box.y1 + margin};
}

constexpr bool inside(Box inner, Box outer) {
    return inner.x0 >= outer.x0 && inner.y0 >= outer.y0 && inner.x1 <= outer.x1 && inner.y1 <= outer.y1;
}

template <typename Length>
constexpr Length axis_gap(Length low_a, Length high_a, Length low_b, Length high_b) {
    return std::max({low_a - high_b, low_b - high_a, Length{0}});
}

constexpr Nm squared(Nm value) { return value * value; }

template <typename Rectangle>
constexpr auto squared_box_gap(const Rectangle& a, const Rectangle& b) {
    const auto across = axis_gap(a.x0, a.x1, b.x0, b.x1), along = axis_gap(a.y0, a.y1, b.y0, b.y1);
    return across * across + along * along;
}

constexpr Nm squared_gap(Box a, Box b) { return squared_box_gap(a, b); }

template <typename Length>
constexpr Length module_gap_needed(Length height, Length stack, Length low, Length tall) {
    return height > stack ? tall : low;
}

constexpr bool overlaps(Box a, Box b) {
    return std::min(a.x1, b.x1) > std::max(a.x0, b.x0) && std::min(a.y1, b.y1) > std::max(a.y0, b.y0);
}

constexpr bool overlaps(Box box, Disc disc) {
    const Nm reach_x = axis_gap(box.x0, box.x1, disc.centre.x, disc.centre.x);
    const Nm reach_y = axis_gap(box.y0, box.y1, disc.centre.y, disc.centre.y);
    return squared(reach_x) + squared(reach_y) < squared(disc.radius);
}

constexpr bool overlaps(Disc a, Disc b) {
    return squared(a.centre.x - b.centre.x) + squared(a.centre.y - b.centre.y) <
           squared(a.radius + b.radius);
}

constexpr bool gap_at_least(Box a, Box b, Nm need) {
    return need <= 0 || squared_gap(a, b) >= squared(need);
}

constexpr bool gap_at_least(Box box, Disc disc, Nm need) {
    const Nm reach = disc.radius + need;
    return reach <= 0 || squared(axis_gap(box.x0, box.x1, disc.centre.x, disc.centre.x)) +
                             squared(axis_gap(box.y0, box.y1, disc.centre.y, disc.centre.y)) >=
                             squared(reach);
}

constexpr bool gap_at_least(Disc a, Disc b, Nm need) {
    const Nm reach = a.radius + b.radius + need;
    return reach <= 0 || squared(a.centre.x - b.centre.x) + squared(a.centre.y - b.centre.y) >= squared(reach);
}

constexpr Nm overlap_area(Box a, Box b) {
    const Nm width = std::min(a.x1, b.x1) - std::max(a.x0, b.x0);
    const Nm height = std::min(a.y1, b.y1) - std::max(a.y0, b.y0);
    return width > 0 && height > 0 ? width * height : 0;
}

Nm to_nm(double millimetres);
double area_mm2(Box box);
Nm ceil_nm(double millimetres);
Nm nearest_nm(double millimetres);
double to_mm(Nm value);
Turn turn_of(double degrees);
double degrees_of(Turn turn);
Box box_nm(double x0, double y0, double x1, double y1);

}
