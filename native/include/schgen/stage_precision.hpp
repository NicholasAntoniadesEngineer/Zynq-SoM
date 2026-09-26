#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Actual stage scalar boundaries. An optional sink belongs to this invocation;
// it is never stored in cached geometry. Null is the pure diagnostic path.
// Count attempted work before arithmetic; rejected trials remain counted.
// Callers retain all operand evaluation, branch conditions and rounding order.
double stage_shift_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_root_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_connector_alignment_delta_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_connector_clearance_line_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_connector_clearance_delta_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_ldo_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_power_mirror_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_layout_width_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_hot_leftover_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_hot_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_proximity_leftover_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_proximity_rebase_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_proximity_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_proximity_face_shift_precision4dp(double value, QuantizationCounts* counts = nullptr);
double stage_refit_pad_precision3dp(double value, QuantizationCounts* counts = nullptr);
int stage_candidate_radius_trunc(double value, QuantizationCounts* counts = nullptr);
int stage_seat_radius_trunc(double value, QuantizationCounts* counts = nullptr);
// Radius conversions truncate toward zero after the caller's exact quotient.
// The candidate cap remains AFTER narrowing. Undefined nonfinite/out-of-range
// conversions reject; every formerly defined conversion is unchanged.
} // namespace schgen

