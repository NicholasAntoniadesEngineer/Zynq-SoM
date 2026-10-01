#pragma once
#include "schgen/execution_accounting.hpp"
#include <cstddef>
#include <limits>
#include <stdexcept>
namespace schgen {
// Optional synchronous invocation-owned receipts. Count attempted boundary entry
// before validation; never store a borrowed map in geometry.
// inclusive truncation count, quotient computed by caller.
int fallback_axis_count(double value, QuantizationCounts* counts = nullptr);
// candidate coordinate after unchanged origin-plus-index-times-pitch.
double fallback_coordinate_precision3dp(double value, QuantizationCounts* counts = nullptr);
// hypot rank computed after both rounded coordinates.
double fallback_rank_precision4dp(double value, QuantizationCounts* counts = nullptr);
// ceil of caller quotient minus original epsilon.
long seat_lower_index(double value, QuantizationCounts* counts = nullptr);
// floor of caller quotient plus original epsilon.
long seat_upper_index(double value, QuantizationCounts* counts = nullptr);
// truncate caller quotient before symmetric range.
int seat_vertical_extent(double value, QuantizationCounts* counts = nullptr);
// each horizontal and vertical candidate coordinate.
double seat_coordinate_precision6dp(double value, QuantizationCounts* counts = nullptr);
// accepted coverage value for seat ledger.
double seat_coverage_precision4dp(double value, QuantizationCounts* counts = nullptr);
// split midpoint for ledger before recursive children.
double seat_split_precision4dp(double value, QuantizationCounts* counts = nullptr);
namespace pack_search_detail {
// Exact integer safety utilities used by the production allocation/loop path.
// Not precision operations, and never registered as quantization covers.
std::size_t checked_product(std::size_t a, std::size_t b, std::size_t limit);
std::size_t inclusive_count(long first, long last, std::size_t limit);
int next_depth(int depth);
// Shared production iteration primitive: never increments the final endpoint.
// Count is obtained from inclusive_count; guard also makes direct misuse safe.
template<class Visit>
void for_each_index(long first, std::size_t count, Visit visit) {
    long value = first;
    for (std::size_t remaining = count; remaining != 0; --remaining) {
        visit(value);
        if (remaining > 1) {
            if (value == std::numeric_limits<long>::max())
                throw std::overflow_error("search index increment overflow");
            ++value;
        }
    }
}
}
} // namespace schgen
