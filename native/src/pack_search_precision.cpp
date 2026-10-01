#include "schgen/pack_search_precision.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <cstdint>
namespace schgen {

int fallback_axis_count(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "fallback_axis_count");
    if (!std::isfinite(value)) throw std::invalid_argument("fallback_axis_count: finite value required");
    if (value <= static_cast<double>(std::numeric_limits<int>::min()) - 1.0 ||
        value >= static_cast<double>(std::numeric_limits<int>::max()))
        throw std::out_of_range("fallback_axis_count: inclusive count does not fit int");
    return static_cast<int>(value) + 1;
}

double fallback_coordinate_precision3dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "fallback_coordinate_precision3dp");
    if (!std::isfinite(value)) throw std::invalid_argument("fallback_coordinate_precision3dp: finite value required");
    return py_round(value, 3);
}

double fallback_rank_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "fallback_rank_precision4dp");
    if (!std::isfinite(value)) throw std::invalid_argument("fallback_rank_precision4dp: finite value required");
    return py_round(value, 4);
}

long seat_lower_index(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_lower_index");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_lower_index: finite value required");
    const double rounded = std::ceil(value);
    const double upper = std::ldexp(1.0, std::numeric_limits<long>::digits);
    if (rounded < -upper || rounded >= upper)
        throw std::out_of_range("seat_lower_index: index does not fit long");
    return static_cast<long>(rounded);
}

long seat_upper_index(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_upper_index");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_upper_index: finite value required");
    const double rounded = std::floor(value);
    const double upper = std::ldexp(1.0, std::numeric_limits<long>::digits);
    if (rounded < -upper || rounded >= upper)
        throw std::out_of_range("seat_upper_index: index does not fit long");
    return static_cast<long>(rounded);
}

int seat_vertical_extent(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_vertical_extent");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_vertical_extent: finite value required");
    if (value <= static_cast<double>(std::numeric_limits<int>::min()) ||
        value >= static_cast<double>(std::numeric_limits<int>::max()) + 1.0)
        throw std::out_of_range("seat_vertical_extent: symmetric extent does not fit int");
    return static_cast<int>(value);
}

double seat_coordinate_precision6dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_coordinate_precision6dp");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_coordinate_precision6dp: finite value required");
    return py_round(value, 6);
}

double seat_coverage_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_coverage_precision4dp");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_coverage_precision4dp: finite value required");
    return py_round(value, 4);
}

double seat_split_precision4dp(double value, QuantizationCounts* counts) {
    if (counts) checked_quantization_add(*counts, "seat_split_precision4dp");
    if (!std::isfinite(value)) throw std::invalid_argument("seat_split_precision4dp: finite value required");
    return py_round(value, 4);
}

namespace pack_search_detail {
std::size_t checked_product(std::size_t a, std::size_t b, std::size_t limit) {
    if (a && b > limit / a) throw std::length_error("search candidate product exceeds capacity");
    return a * b;
}
std::size_t inclusive_count(long first, long last, std::size_t limit) {
    if (first > last) return 0;
    using U = std::make_unsigned_t<long>;
    const U distance = static_cast<U>(last) - static_cast<U>(first);
    if (static_cast<std::uintmax_t>(distance) >= static_cast<std::uintmax_t>(limit))
        throw std::length_error("search interval exceeds capacity");
    return static_cast<std::size_t>(distance) + 1;
}
int next_depth(int depth) {
    if (depth == std::numeric_limits<int>::max())
        throw std::overflow_error("seat_band recursion depth overflow");
    return depth + 1;
}
}
} // namespace schgen
