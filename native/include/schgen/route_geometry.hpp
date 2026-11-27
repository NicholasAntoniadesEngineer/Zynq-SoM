#pragma once

#include "schgen/layout_geometry.hpp"

#include <array>
#include <cstdint>

namespace schgen::route {

using layout::Box;
using layout::Nm;
using layout::Point;

inline constexpr std::size_t core_limit = 4;

struct Shape {
    std::array<Point, core_limit> core{};
    std::uint8_t count = 0;
    Nm radius = 0;
    Box bound() const;
};

Shape disc(Point centre, Nm radius);
Shape capsule(Point from, Point to, Nm half_width);
Shape rectangle(Box box);

bool closer(const Shape& first, const Shape& second, Nm reach);
bool apart(const Shape& first, const Shape& second, Nm need);
bool touching(const Shape& first, const Shape& second);
bool within(const Shape& shape, Box box, Nm margin);
double length_of(Point from, Point to);

}
