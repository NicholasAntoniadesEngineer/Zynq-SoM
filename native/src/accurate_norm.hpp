#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>

namespace schgen {
// Scaled, compensated two-component norm. Explicit FMA retains product error;
// a differential square-root correction avoids platform libm's one-ULP drift.
// Numerical compatibility reference: CPython 3.14 mathmodule.c vector_norm
// https://github.com/python/cpython/blob/3.14/Modules/mathmodule.c
// This is native arithmetic, not an interpreter/runtime dependency.
inline double accurate_hypot2(double first, double second) {
    const double a = std::fabs(first), b = std::fabs(second);
    if (std::isinf(a) || std::isinf(b)) return std::numeric_limits<double>::infinity();
    if (std::isnan(a) || std::isnan(b)) return std::numeric_limits<double>::quiet_NaN();
    const double largest = std::max(a, b);
    if (largest == 0) return 0;
    if (largest <= std::numeric_limits<double>::min()) {
        // Subnormals are exact integer multiples of 2^-1074. Rounding a
        // scaled square root to double and then rescaling rounds twice; even
        // a correctly rounded intermediate can choose the wrong subnormal.
        // Here both components have at most 53 bits and the squared sum fits
        // in 106 bits. Round the exact integer square root directly to units
        // of 2^-1074. The result has at most 53 bits, so rescaling is exact.
        const auto x = static_cast<std::uint64_t>(std::ldexp(a, 1074));
        const auto y = static_cast<std::uint64_t>(std::ldexp(b, 1074));
        using Wide = __uint128_t;
        const Wide squared = Wide{x} * x + Wide{y} * y;
        auto root = static_cast<std::uint64_t>(std::sqrt(static_cast<double>(squared)));
        while (Wide{root} * root > squared) --root;
        while (Wide{root + 1} * (root + 1) <= squared) ++root;
        // (root + 1/2)^2 = root^2 + root + 1/4. The squared sum is
        // integral, so an exact halfway case is impossible.
        if (squared - Wide{root} * root > root) ++root;
        return std::ldexp(static_cast<double>(root), -1074);
    }
    int exponent = 0;
    std::frexp(largest, &exponent);
    const double scale = std::ldexp(1.0, -exponent);
    double total = 1, product_error = 0, sum_error = 0;
    const auto accumulate = [&](double left, double right) {
        const double product = left * right;
        product_error += std::fma(left, right, -product);
        const double combined = total + product;
        sum_error += product - (combined - total);
        total = combined;
    };
    const double x = a * scale, y = b * scale;
    accumulate(x, x);
    accumulate(y, y);
    const double estimate = std::sqrt(total - 1 + (product_error + sum_error));
    accumulate(-estimate, estimate);
    const double residual = total - 1 + (product_error + sum_error);
    return (estimate + residual / (2 * estimate)) / scale;
}
namespace accurate_norm_detail {
// A finite displacement/product may exceed binary64's exponent range. Keep
// its power of two separately; individual components must be scaled separately
// so a huge x component cannot erase a tiny but significant y product.
struct Scaled { double fraction; int exponent; };
inline Scaled difference(double endpoint, double origin, double ordinary) {
    int exponent = 0;
    if (std::isfinite(ordinary))
        return {std::frexp(ordinary, &exponent), exponent};
    const double half = endpoint * 0.5 - origin * 0.5;
    const double fraction = std::frexp(half, &exponent);
    return {fraction, exponent + 1};
}
inline Scaled sum_products(Scaled a, Scaled b, Scaled c, Scaled d) {
    const bool first = a.fraction != 0 && b.fraction != 0;
    const bool second = c.fraction != 0 && d.fraction != 0;
    if (!first && !second) return {0, 0};
    const int e1 = a.exponent + b.exponent, e2 = c.exponent + d.exponent;
    const int exponent = first ? (second ? std::max(e1, e2) : e1) : e2;
    const double p = a.fraction * b.fraction, q = c.fraction * d.fraction;
    const double pe = std::ldexp(std::fma(a.fraction, b.fraction, -p), e1-exponent);
    const double qe = std::ldexp(std::fma(c.fraction, d.fraction, -q), e2-exponent);
    const double left = std::ldexp(p, e1-exponent), right = std::ldexp(q, e2-exponent);
    // TwoSum retains cancellation error; FMA above retains each product's
    // error. Uncompensated products can lose the sign of a finite residual.
    const double sum = left + right, recovered = sum - left;
    const double error = (left - (sum - recovered)) + (right - recovered);
    int adjustment = 0;
    const double fraction = std::frexp(sum + (error + (pe + qe)), &adjustment);
    return {fraction, fraction == 0 ? 0 : exponent + adjustment};
}
}
// Preserve ordinary predictor arithmetic and its established rounding. For
// finite overflow only, use scaled dot/determinant and atan2; acos(dot/norms)
// cannot recover an angle after its intermediate products have overflowed.
// Nonfinite coordinates are invalid geometry and return NaN for BOTH results.
inline std::pair<double, double> accurate_facing_dot(double zx, double zy,
        double ox, double oy, double dx, double dy) {
    if (!std::isfinite(zx) || !std::isfinite(zy) || !std::isfinite(ox) ||
        !std::isfinite(oy) || !std::isfinite(dx) || !std::isfinite(dy)) {
        const double nan = std::numeric_limits<double>::quiet_NaN();
        return {nan, nan};
    }
    const double original_ox = ox, original_oy = oy, original_dx = dx, original_dy = dy;
    ox -= zx; oy -= zy; dx -= zx; dy -= zy;
    const double dot = ox * dx + oy * dy;
    const double out_norm = accurate_hypot2(ox, oy), down_norm = accurate_hypot2(dx, dy);
    const bool degenerate = out_norm <= 1e-9 || down_norm <= 1e-9;
    if (std::isfinite(dot) && degenerate) return {dot, 180};
    const double denominator = out_norm * down_norm;
    if (std::isfinite(dot) && std::isfinite(denominator)) {
        const double cosine = std::max(-1.0, std::min(1.0, dot / denominator));
        return {dot, std::acos(cosine) * (180.0 / 3.141592653589793)};
    }
    using namespace accurate_norm_detail;
    const auto x = difference(original_ox, zx, ox), y = difference(original_oy, zy, oy);
    const auto u = difference(original_dx, zx, dx), v = difference(original_dy, zy, dy);
    const auto scaled_dot = sum_products(x, u, y, v);
    const double corrected_dot = std::ldexp(scaled_dot.fraction, scaled_dot.exponent);
    if (degenerate) return {corrected_dot, 180};
    const auto cross = sum_products(x, v, {-y.fraction, y.exponent}, u);
    const int exponent = scaled_dot.fraction == 0 ? cross.exponent :
        (cross.fraction == 0 ? scaled_dot.exponent : std::max(scaled_dot.exponent, cross.exponent));
    const double angle = std::atan2(std::ldexp(std::fabs(cross.fraction), cross.exponent-exponent),
                                   std::ldexp(scaled_dot.fraction, scaled_dot.exponent-exponent));
    return {corrected_dot, angle * (180.0 / 3.141592653589793)};
}
}
