#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Invocation-owned optional receipts. Count each attempted scalar before arithmetic;
// rejected candidates retain entries. No geometry object stores a sink.
double pack_pair_gap_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_edge_component_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_som_grid_precision0dp(double value, QuantizationCounts* counts = nullptr);
double pack_som_cell_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_som_diameter_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_som_component_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_som_band_component_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_cout_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_bulk_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_zone_component_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_rotated_offset_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_corridor_bound_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_mirror_offset_precision4dp(double value, QuantizationCounts* counts = nullptr);
int pack_som_grid_trunc(double value, QuantizationCounts* counts = nullptr);
} // namespace schgen
