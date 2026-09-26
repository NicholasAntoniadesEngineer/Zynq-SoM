#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// One attempted scalar round per entry, counted before arithmetic. Sinks are
// explicitly invocation-owned; geometry copies and rollback never own/reset
// them. Null retains the pure diagnostic path. All operations preserve the
// original py_round(value, 4), including ties, signed zero and nonfinite values.
// Nested position -> centroid/hull boundaries intentionally remain separate.
double legalize_position_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_centroid_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_bbox_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_anchor_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_bound_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_margin_precision4dp(double value, QuantizationCounts* counts = nullptr);
double legalize_trial_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
} // namespace schgen
