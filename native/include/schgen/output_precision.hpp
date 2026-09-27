#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Each entry is one real scalar conversion, not a covering function. Null is
// an explicitly unaccounted diagnostic invocation; receipts are caller-owned.
int floorplan_svg_extent_trunc(double, QuantizationCounts* = nullptr);
int floorplan_svg_grid_trunc(double, QuantizationCounts* = nullptr);
// Keep affine arithmetic in the same contraction context as the old pack.cpp
// svg_map boundary; callers must not precompute it under different FP flags.
double floorplan_svg_coordinate_precision1dp(double value, double origin, double scale,
                                             QuantizationCounts* = nullptr);
double pcb_project_integer_trunc(double, QuantizationCounts* = nullptr);
double pcb_project_class_precision4dp(double, QuantizationCounts* = nullptr);
double pcb_silk_position_precision3dp(double, QuantizationCounts* = nullptr);
double pcb_silk_stroke_precision3dp(double, QuantizationCounts* = nullptr);
double ratsnest_pad_precision3dp(double, QuantizationCounts* = nullptr);
double ratsnest_area_precision1dp(double, QuantizationCounts* = nullptr);
double ratsnest_dispersion_precision2dp(double, QuantizationCounts* = nullptr);
double ratsnest_budget_precision1dp(double, QuantizationCounts* = nullptr);
double escape_ground_precision4dp(double, QuantizationCounts* = nullptr);
double escape_scan_precision3dp(double, QuantizationCounts* = nullptr);
double escape_copper_precision4dp(double, QuantizationCounts* = nullptr);
double escape_coverage_precision4dp(double, QuantizationCounts* = nullptr);
double escape_region_precision4dp(double, QuantizationCounts* = nullptr);
double escape_port_precision4dp(double, QuantizationCounts* = nullptr);
double escape_width_precision4dp(double, QuantizationCounts* = nullptr);
double escape_corridor_precision4dp(double, QuantizationCounts* = nullptr);
} // namespace schgen
