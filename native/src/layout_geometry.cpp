#include "schgen/layout_geometry.hpp"

#include <cmath>
#include <string>

namespace schgen::layout {
namespace {

double lattice_value(double millimetres) {
    if (!std::isfinite(millimetres)) throw LayoutError("layout: non-finite coordinate");
    const double scaled = millimetres * constants::nano_scale.value;
    if (std::fabs(scaled) > constants::span_limit.value)
        throw LayoutError("layout: coordinate beyond the span limit: " + std::to_string(millimetres));
    return scaled;
}

bool on_lattice(double scaled) {
    return std::fabs(scaled - std::round(scaled)) <= constants::lattice_tolerance.value;
}

}

double area_mm2(Box box) { return to_mm(box.width()) * to_mm(box.height()); }

Nm to_nm(double millimetres) {
    const double scaled = lattice_value(millimetres);
    if (!on_lattice(scaled))
        throw LayoutError("layout: coordinate off the nanometre lattice: " + std::to_string(millimetres));
    return static_cast<Nm>(std::round(scaled));
}

Nm ceil_nm(double millimetres) {
    const double scaled = lattice_value(millimetres);
    return static_cast<Nm>(on_lattice(scaled) ? std::round(scaled) : std::ceil(scaled));
}

Nm nearest_nm(double millimetres) {
    return static_cast<Nm>(std::round(lattice_value(millimetres)));
}

double to_mm(Nm value) { return static_cast<double>(value) / constants::nano_scale.value; }

Turn turn_of(double degrees) {
    if (!std::isfinite(degrees)) throw LayoutError("layout: non-finite rotation");
    const double quarters = degrees / constants::quarter_degrees.value;
    if (quarters != std::round(quarters))
        throw LayoutError("layout: rotation is not a quarter turn: " + std::to_string(degrees));
    const long long index = static_cast<long long>(quarters) % turn_count;
    return static_cast<Turn>(index < 0 ? index + turn_count : index);
}

double degrees_of(Turn turn) {
    return static_cast<int>(turn) * constants::quarter_degrees.value;
}

Box box_nm(double x0, double y0, double x1, double y1) {
    return {to_nm(x0), to_nm(y0), to_nm(x1), to_nm(y1)};
}

}
