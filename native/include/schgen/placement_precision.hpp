#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Each scalar boundary counts attempted work through an optional invocation-owned
// sink. No sink pointer is stored in a Context/Shape/cache; nullptr is the pure path.
// Keep arithmetic and branch ordering at the call site; rejected trials count.
double placement_turn_dimension_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_turn_offset_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_connector_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_behind_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_pack_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_edge_mirror_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_variant_dimension_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_member_box_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_member_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_bottom_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_lift_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_shape_key_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_l4_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_edge_seat_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_foreign_pad_precision3dp(double value, QuantizationCounts* counts = nullptr);
double placement_evict_trial_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_emission_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double placement_fiducial_precision4dp(double value, QuantizationCounts* counts = nullptr);
int placement_l4_distance_trunc(double value, QuantizationCounts* counts = nullptr);
// L4 distance truncates toward zero AFTER the caller's original min(dist,40).
// Formerly undefined nonfinite/out-of-int-range conversions reject explicitly.
} // namespace schgen
