#pragma once
#include <algorithm>
#include <cmath>
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
    int exponent = 0;
    std::frexp(largest, &exponent);
    if (exponent < -1023) {
        constexpr double normal = std::numeric_limits<double>::min();
        return normal * accurate_hypot2(a / normal, b / normal);
    }
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
// Predictor arithmetic mirrors the pure numeric reference. The public legacy
// facing_dot boundary retains its established platform-libm report values.
inline std::pair<double, double> accurate_facing_dot(double zx, double zy,
        double ox, double oy, double dx, double dy) {
    ox -= zx; oy -= zy; dx -= zx; dy -= zy;
    const double dot = ox * dx + oy * dy;
    const double out_norm = accurate_hypot2(ox, oy), down_norm = accurate_hypot2(dx, dy);
    if (out_norm <= 1e-9 || down_norm <= 1e-9) return {dot, 180};
    const double cosine = std::max(-1.0, std::min(1.0, dot / (out_norm * down_norm)));
    return {dot, std::acos(cosine) * (180.0 / 3.141592653589793)};
}
}
