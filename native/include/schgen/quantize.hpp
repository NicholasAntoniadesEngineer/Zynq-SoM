#pragma once

namespace schgen {

namespace quantization_policy {
inline constexpr double kGridMm = 1.27;
inline constexpr double kHalfMm = 0.5;
inline constexpr double kCreditMm = 0.05;
inline constexpr double kSnapErosionMm = 0.75;
inline constexpr double kOutlineSnapMm = 5.0;
inline constexpr double kFineSnapMm = 1.0;
// These compiled estimator costs are the policy actually consumed. Do not
// manufacture barrel/annulus/stack operands or recompute 7.6 with different
// floating-point rounding. Caller experiment overrides are resolved separately.
inline constexpr double kViaOrdinaryMm = 2.2;
inline constexpr double kViaImpedanceMm = 7.6;
}

double fixed_part_grid(double value);
double evict_corridor_grid(double origin, double value);
double som_pose_half_mm(double value);
double placeholder_zone_half_mm(double value);
double legalize_pose_quantum(double value);
double quant_credit(double value);
double snap_erosion_bound(double bound);
double snap_erosion_pad(double mm);
// Historical biased truncation formula; throws for nonfinite input/result.
double outline_snap_up(double value);
double outline_grow(int step);
double fine_shrink(double base, int step);
double est_via_cost(bool impedance_controlled);
double gsnap(double value, double unit);
double gfloor(double value, double unit);
double gceil(double value, double unit);

}  // namespace schgen
