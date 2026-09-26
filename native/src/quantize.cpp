#include "schgen/quantize.hpp"

#include "schgen/occupancy.hpp"

#include <cmath>
#include <stdexcept>

namespace schgen {
using namespace quantization_policy;

double fixed_part_grid(double value) {
    return py_round(py_round(value / kGridMm, 0) * kGridMm, 4);
}

double evict_corridor_grid(double origin, double value) {
    return py_round(fixed_part_grid(origin + value) - origin, 4);
}

double som_pose_half_mm(double value) {
    return py_round(py_round(value * (1.0 / kHalfMm), 0) / (1.0 / kHalfMm), 1);
}

double placeholder_zone_half_mm(double value) {
    return som_pose_half_mm(value);
}

double legalize_pose_quantum(double value) {
    return py_round(py_round(value / kHalfMm, 0) * kHalfMm, 4);
}

double quant_credit(double value) {
    return value + kCreditMm;
}

double snap_erosion_bound(double bound) {
    return bound >= 5.0 ? bound - kSnapErosionMm : bound;
}

double snap_erosion_pad(double mm) {
    return mm + (mm >= 5.0 ? kSnapErosionMm : 0.0);
}

double outline_snap_up(double value) {
    if (!std::isfinite(value)) {
        throw std::runtime_error("outline_snap_up: finite dimension required");
    }
    // Preserve the established truncation-toward-zero formula (including
    // negative inputs and its 1e-6 bias), without an out-of-range int cast.
    const double n = std::trunc((value + kOutlineSnapMm - 1e-6) / kOutlineSnapMm);
    const double snapped = n * kOutlineSnapMm;
    if (!std::isfinite(snapped)) {
        throw std::runtime_error("outline_snap_up: snapped dimension overflow");
    }
    // The former integer intermediate canonicalized both signs of zero.
    return py_round(snapped == 0.0 ? 0.0 : snapped, 1);
}

double outline_grow(int step) {
    return static_cast<double>(step) * kOutlineSnapMm;
}

double fine_shrink(double base, int step) {
    return py_round(base - static_cast<double>(step) * kFineSnapMm, 1);
}

double est_via_cost(bool impedance_controlled) {
    return impedance_controlled ? kViaImpedanceMm : kViaOrdinaryMm;
}

double gsnap(double value, double unit) {
    return py_round(py_round(value / unit, 0) * unit, 3);
}

double gfloor(double value, double unit) {
    return py_round(std::floor(value / unit + 1e-6) * unit, 3);
}

double gceil(double value, double unit) {
    return py_round(std::ceil(value / unit - 1e-6) * unit, 3);
}

}  // namespace schgen
