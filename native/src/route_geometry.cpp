#include "schgen/route_geometry.hpp"

#include <algorithm>
#include <cmath>

namespace schgen::route {
namespace {

using Wide = __int128;

Wide cross(Point origin, Point a, Point b) {
    return static_cast<Wide>(a.x - origin.x) * static_cast<Wide>(b.y - origin.y) -
           static_cast<Wide>(a.y - origin.y) * static_cast<Wide>(b.x - origin.x);
}

Wide dot(Point origin, Point a, Point b) {
    return static_cast<Wide>(a.x - origin.x) * static_cast<Wide>(b.x - origin.x) +
           static_cast<Wide>(a.y - origin.y) * static_cast<Wide>(b.y - origin.y);
}

int sign(Wide value) { return value > 0 ? 1 : value < 0 ? -1 : 0; }

bool between(Point a, Point b, Point p) {
    return std::min(a.x, b.x) <= p.x && p.x <= std::max(a.x, b.x) && std::min(a.y, b.y) <= p.y && p.y <= std::max(a.y, b.y);
}

bool crossing(Point a, Point b, Point c, Point d) {
    const int first = sign(cross(a, b, c)), second = sign(cross(a, b, d));
    const int third = sign(cross(c, d, a)), fourth = sign(cross(c, d, b));
    if (first != second && third != fourth) return true;
    if (first == 0 && between(a, b, c)) return true;
    if (second == 0 && between(a, b, d)) return true;
    if (third == 0 && between(c, d, a)) return true;
    return fourth == 0 && between(c, d, b);
}

bool point_closer(Point p, Point a, Point b, Nm reach) {
    const Wide limit = static_cast<Wide>(reach) * static_cast<Wide>(reach);
    const Wide along = dot(a, p, b), span = dot(a, b, b);
    if (span == 0 || along <= 0) return dot(p, a, a) < limit;
    if (along >= span) return dot(p, b, b) < limit;
    const Wide off = cross(a, b, p);
    return off * off < limit * span;
}

bool inside(const Shape& shape, Point p) {
    if (shape.count < 3) return false;
    int turn = 0;
    for (std::size_t index = 0; index < shape.count; ++index) {
        const int side = sign(cross(shape.core[index], shape.core[(index + 1) % shape.count], p));
        if (side == 0) continue;
        if (turn != 0 && side != turn) return false;
        turn = side;
    }
    return true;
}

std::size_t edges(const Shape& shape) { return shape.count <= 2 ? 1 : shape.count; }

std::pair<Point, Point> edge(const Shape& shape, std::size_t index) {
    if (shape.count == 1) return {shape.core[0], shape.core[0]};
    return {shape.core[index], shape.core[(index + 1) % shape.count]};
}

}

Box Shape::bound() const {
    Box box{core[0].x, core[0].y, core[0].x, core[0].y};
    for (std::size_t index = 1; index < count; ++index) {
        box.x0 = std::min(box.x0, core[index].x);
        box.y0 = std::min(box.y0, core[index].y);
        box.x1 = std::max(box.x1, core[index].x);
        box.y1 = std::max(box.y1, core[index].y);
    }
    return {box.x0 - radius, box.y0 - radius, box.x1 + radius, box.y1 + radius};
}

Shape disc(Point centre, Nm radius) {
    Shape shape;
    shape.core[0] = centre;
    shape.count = 1;
    shape.radius = radius;
    return shape;
}

Shape capsule(Point from, Point to, Nm half_width) {
    if (from == to) return disc(from, half_width);
    Shape shape;
    shape.core[0] = from;
    shape.core[1] = to;
    shape.count = 2;
    shape.radius = half_width;
    return shape;
}

Shape rectangle(Box box) {
    Shape shape;
    shape.core = {Point{box.x0, box.y0}, Point{box.x1, box.y0}, Point{box.x1, box.y1}, Point{box.x0, box.y1}};
    shape.count = core_limit;
    return shape;
}

bool closer(const Shape& first, const Shape& second, Nm reach) {
    if (reach <= 0) return false;
    for (std::size_t a = 0; a < edges(first); ++a)
        for (std::size_t b = 0; b < edges(second); ++b) {
            const auto [p, q] = edge(first, a);
            const auto [r, s] = edge(second, b);
            if (crossing(p, q, r, s)) return true;
        }
    if (inside(first, second.core[0]) || inside(second, first.core[0])) return true;
    for (std::size_t point = 0; point < first.count; ++point)
        for (std::size_t b = 0; b < edges(second); ++b) {
            const auto [r, s] = edge(second, b);
            if (point_closer(first.core[point], r, s, reach)) return true;
        }
    for (std::size_t point = 0; point < second.count; ++point)
        for (std::size_t a = 0; a < edges(first); ++a) {
            const auto [p, q] = edge(first, a);
            if (point_closer(second.core[point], p, q, reach)) return true;
        }
    return false;
}

bool apart(const Shape& first, const Shape& second, Nm need) { return !closer(first, second, need + first.radius + second.radius); }

bool touching(const Shape& first, const Shape& second) { return closer(first, second, first.radius + second.radius + 1); }

bool within(const Shape& shape, Box box, Nm margin) {
    const Box bound = shape.bound();
    return bound.x0 >= box.x0 + margin && bound.y0 >= box.y0 + margin && bound.x1 <= box.x1 - margin && bound.y1 <= box.y1 - margin;
}

double length_of(Point from, Point to) { return std::hypot(static_cast<double>(to.x - from.x), static_cast<double>(to.y - from.y)); }

}
