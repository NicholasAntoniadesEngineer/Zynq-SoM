#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Actual scalar entries, including failed conversion attempts, accrue to the
// current invocation. Never store this sink in copied grid/index geometry.
int silk_cell_floor(double value, double cell, QuantizationCounts* counts = nullptr);
int breathe_grid_extent(double extent, double cell, QuantizationCounts* counts = nullptr);
int breathe_stamp_index(double quotient, QuantizationCounts* counts = nullptr);
int breathe_free_index(double quotient, QuantizationCounts* counts = nullptr);
double refdes_size_precision3dp(double value, QuantizationCounts* counts = nullptr);
double refdes_pose_precision4dp(double value, QuantizationCounts* counts = nullptr);
}
