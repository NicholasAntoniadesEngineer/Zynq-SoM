#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Count actual scalar attempts in the invocation-owned optional receipt.
double pack_fanout_reach_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_band_sort_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_contact_column_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_plane_bound_precision3dp(double value, QuantizationCounts* counts = nullptr);
double pack_isolation_bound_precision3dp(double value, QuantizationCounts* counts = nullptr);
double pack_ladder_coordinate_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_redundancy_candidate_precision6dp(double value, QuantizationCounts* counts = nullptr);
double pack_aabb_coordinate_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_block_area_precision1dp(double value, QuantizationCounts* counts = nullptr);
double pack_xy_coordinate_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_box_coordinate_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_svg_map_precision1dp(double value, QuantizationCounts* counts = nullptr);
double pack_unique_coordinate_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_centroid_coordinate_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_row_extent_precision4dp(double value, QuantizationCounts* counts = nullptr);
double pack_halfturn_origin_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_rotated_origin_precision(double value, int digits, QuantizationCounts* counts = nullptr);
double pack_named_center_precision(double value, int digits, QuantizationCounts* counts = nullptr);
} // namespace schgen
