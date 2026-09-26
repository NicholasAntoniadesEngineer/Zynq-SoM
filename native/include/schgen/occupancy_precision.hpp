#pragma once

#include "schgen/execution_accounting.hpp"

namespace schgen {

class OccupancyFrontierCounter;
// A borrowed, invocation-local binding for ONE named operation. Construction
// does not touch the map. Insertions preserve its reference, but erase/clear,
// assignment, swap and checked_quantization_merge are forbidden while bound.
// Never store this in geometry or share its map with concurrent writers.
class OccupancyFrontierSlot {
public:
    explicit OccupancyFrontierSlot(QuantizationCounts* counts) noexcept : counts_(counts) {}
    OccupancyFrontierSlot(const OccupancyFrontierSlot&) = delete;
    OccupancyFrontierSlot& operator=(const OccupancyFrontierSlot&) = delete;
private:
    QuantizationCounts* counts_;
    std::size_t* value_ = nullptr;
    friend class OccupancyFrontierCounter;
    friend double occupancy_frontier_key1dp(double, OccupancyFrontierCounter);
};

// Implicit views retain ordinary pointer/null/default call syntax while keeping
// ONE scalar definition and its exact registry source identity (no overload).
// This changes the function-pointer/ABI signature; rebuild every caller.
class OccupancyFrontierCounter {
public:
    OccupancyFrontierCounter(QuantizationCounts* counts = nullptr) noexcept : counts_(counts) {}
    OccupancyFrontierCounter(OccupancyFrontierSlot& slot) noexcept
        : counts_(slot.counts_), slot_(&slot) {}
private:
    QuantizationCounts* counts_;
    OccupancyFrontierSlot* slot_ = nullptr;
    friend double occupancy_frontier_key1dp(double, OccupancyFrontierCounter);
};

// Each optional sink belongs to the CURRENT invocation, never the occupancy
// geometry. Pass it explicitly through copies, trials and refinement calls.
// Null is the pure/diagnostic path. Non-null records one attempted operation
// before arithmetic, including rejected candidates; counter overflow throws.
// Import the enclosing invocation's accounting once, without invoking these
// functions again. None of these operations owns a global or a stored sink.
double occupancy_component_precision4dp(double value, QuantizationCounts* counts = nullptr);
double occupancy_reach_precision4dp(double value, QuantizationCounts* counts = nullptr);
double occupancy_frontier_key1dp(double distance, OccupancyFrontierCounter counts = {});
double occupancy_shape_key4dp(double distance, QuantizationCounts* counts = nullptr);

// Preserve divide/floor/narrow and divide/truncate/add-one respectively.
// Caller bucket/step is NOT replaced. All formerly defined scalar results are
// retained (including signed nonzero divisors); nonfinite inputs, zero divisor,
// unrepresentable conversion and inclusive-count overflow fail before UB.
int occupancy_cell_index(double coordinate, double bucket, QuantizationCounts* counts = nullptr);
int occupancy_axis_count(double extent, double step, QuantizationCounts* counts = nullptr);

} // namespace schgen
