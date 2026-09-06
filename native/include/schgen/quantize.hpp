#pragma once

namespace schgen {

double fixed_part_grid(double value);
double evict_corridor_grid(double origin, double value);
double som_pose_half_mm(double value);
double placeholder_zone_half_mm(double value);
double legalize_pose_quantum(double value);
double quant_credit(double value);
double snap_erosion_bound(double bound);
double snap_erosion_pad(double mm);
double outline_snap_up(double value);
double outline_grow(int step);
double fine_shrink(double base, int step);
double est_via_cost(bool impedance_controlled);
double gsnap(double value, double unit);
double gfloor(double value, double unit);
double gceil(double value, double unit);

}  // namespace schgen
