#include "schgen/quantize.hpp"

#include "schgen/occupancy.hpp"

#include <cmath>

namespace schgen {
namespace {

constexpr double kGridMm = 1.27;
constexpr double kHalfMm = 0.5;
constexpr double kCreditMm = 0.05;
constexpr double kSnapErosionMm = 0.75;
constexpr double kOutlineSnapMm = 5.0;
constexpr double kFineSnapMm = 1.0;
constexpr double kViaOrdinaryMm = 2.2;
constexpr double kViaImpedanceMm = 7.6;

}  // namespace

double fixed_part_grid(double value) {
    return py_round(py_round(value / kGridMm, 0) * kGridMm, 4);
}

double evict_corridor_grid(double origin, double value) {
    return py_round(fixed_part_grid(origin + value) - origin, 4);
}

double som_pose_half_mm(double value) {
    return py_round(py_round(value * 2.0, 0) / 2.0, 1);
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
    const int n = static_cast<int>((value + kOutlineSnapMm - 1e-6)
                                   / kOutlineSnapMm);
    return py_round(static_cast<double>(n) * kOutlineSnapMm, 1);
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
