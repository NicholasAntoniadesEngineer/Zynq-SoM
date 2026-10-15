#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Each scalar counts its actual entry before arithmetic. Sinks belong to the
// current producer invocation, never to copied/cached geometry. Null is the
// pure diagnostic path. Callers retain the original operand evaluation order.
double pack_shelf_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_shelf_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
int pack_control_fit_trunc(double value, QuantizationCounts* counts = nullptr);
double pack_control_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_edge_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
// Integer tick index on the 1e-4 mm grid, not a millimetre coordinate.
double pack_edge_lower_tick_ceil(double value, QuantizationCounts* counts = nullptr);
double pack_hf_cap_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
}
