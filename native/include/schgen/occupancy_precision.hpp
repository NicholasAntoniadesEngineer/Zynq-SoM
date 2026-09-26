#pragma once

#include "schgen/execution_accounting.hpp"

namespace schgen {

// Each optional sink belongs to the CURRENT invocation, never the occupancy
// geometry. Pass it explicitly through copies, trials and refinement calls.
// Null is the pure/diagnostic path. Non-null records one attempted operation
// before arithmetic, including rejected candidates; counter overflow throws.
// Import the enclosing invocation's accounting once, without invoking these
// functions again. None of these operations owns a global or a stored sink.
double occupancy_component_precision4dp(double value, QuantizationCounts* counts = nullptr);
double occupancy_reach_precision4dp(double value, QuantizationCounts* counts = nullptr);
double occupancy_frontier_key1dp(double distance, QuantizationCounts* counts = nullptr);
double occupancy_shape_key4dp(double distance, QuantizationCounts* counts = nullptr);

// Preserve divide/floor/narrow and divide/truncate/add-one respectively.
// Caller bucket/step is NOT replaced. All formerly defined scalar results are
// retained (including signed nonzero divisors); nonfinite inputs, zero divisor,
// unrepresentable conversion and inclusive-count overflow fail before UB.
int occupancy_cell_index(double coordinate, double bucket, QuantizationCounts* counts = nullptr);
int occupancy_axis_count(double extent, double step, QuantizationCounts* counts = nullptr);

} // namespace schgen
