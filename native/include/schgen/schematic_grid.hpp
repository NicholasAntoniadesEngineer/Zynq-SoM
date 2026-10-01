#pragma once
#include "schgen/execution_accounting.hpp"
#include "schgen/quantize.hpp"

namespace schgen::schematic_grid {
// Receipts for the existing registered scalar operations, not new operations.
// A caller-owned sink covers the attempted entry, including a throwing scalar.
// The arithmetic and unit argument remain exactly those of the original call.
inline double gsnap(double value, double unit, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "gsnap");
    return schgen::gsnap(value, unit);
}
inline double gfloor(double value, double unit, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "gfloor");
    return schgen::gfloor(value, unit);
}
inline double gceil(double value, double unit, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "gceil");
    return schgen::gceil(value, unit);
}
}
