#include "schgen/precision_ops.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/quantize.hpp"
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool ok, const char* message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
std::uint64_t bits(double value) {
    std::uint64_t result = 0;
    static_assert(sizeof result == sizeof value, "binary64 test platform required");
    std::memcpy(&result, &value, sizeof result);
    return result;
}
template<class Error, class F> void rejects(F action, const char* message) {
    bool caught = false;
    try { action(); } catch (const Error&) { caught = true; }
    require(caught, message);
}
void round_contracts() {
    const double inf = std::numeric_limits<double>::infinity();
    std::vector<double> values{0., -0., inf, -inf, std::numeric_limits<double>::quiet_NaN(),
        11.24955, -11.24955, .00005, -.00005, .0005, -.0005, 1e-300, -1e-300,
        4503599627370496., -4503599627370496.};
    // Neighbours of decimal halfway values distinguish exact-binary decimal
    // rounding from the incorrect multiply/nearbyint/divide approximation.
    for (int n = -500; n <= 500; ++n)
        for (double unit : {.001, .0001}) {
            const double value = (n + .5) * unit;
            values.insert(values.end(), {std::nextafter(value, -inf), value,
                                          std::nextafter(value, inf)});
        }
    for (double value : values) {
        require(bits(estimate_position_precision(value)) == bits(py_round(value, 4)),
                "estimate position bits preserve old scalar expression");
        require(bits(estimate_pad_precision(value)) == bits(py_round(value, 3)),
                "estimate pad bits preserve old scalar expression");
        require(bits(breathe_delta_precision(value)) == bits(py_round(value, 4)),
                "breathe delta bits preserve old scalar expression");
        require(bits(breathe_commit_precision(value)) == bits(py_round(value, 4)),
                "breathe commit bits preserve old scalar expression");
    }
    bool order_matters = false;
    for (double origin : {25., -25., 25.00005})
        for (double local : {0., .000049, .000051, 11.24955, -11.24955})
            for (double offset : {.000049, -.000049, .013337, -3.141592}) {
                const auto old_position = py_round(py_round(origin + local, 4) + offset, 4);
                const auto replacement = estimate_position_precision(
                    estimate_position_precision(origin + local) + offset);
                require(bits(old_position) == bits(replacement), "nested position rounding order preserved");
                order_matters |= bits(old_position) != bits(py_round(origin + local + offset, 4));
                const auto old_delta = py_round(fixed_part_grid(25 + local + offset) - 25 - local, 4);
                const auto delta = breathe_delta_precision(fixed_part_grid(25 + local + offset) - 25 - local);
                require(bits(old_delta) == bits(delta), "grid/subtract/subtract/round delta order preserved");
                require(bits(py_round(local + offset, 4)) == bits(breathe_commit_precision(local + offset)),
                        "commit addition precedes precision boundary");
            }
    require(order_matters, "fixture proves flattening nested rounds changes genuine output bits");
}
void step_contracts() {
    const double inf = std::numeric_limits<double>::infinity();
    for (double step : {.25, .1, .7, 1.27})
        for (int n = -500; n <= 500; ++n) {
            const double distance = n * step;
            for (double value : {std::nextafter(distance, -inf), distance, std::nextafter(distance, inf)}) {
                require(breathe_forward_steps(value, step) == static_cast<int>(value / step) + 1,
                        "forward retains divide/truncate/add order");
                require(breathe_retreat_steps(value, step) == static_cast<int>(value / step),
                        "retreat retains divide/truncate order including negative values");
            }
        }
    const double low = std::numeric_limits<int>::min(), high = std::numeric_limits<int>::max();
    require(breathe_retreat_steps(high + .75, 1) == std::numeric_limits<int>::max(),
            "range check judges truncated result, not fractional input");
    require(breathe_retreat_steps(low - .75, 1) == std::numeric_limits<int>::min(),
            "negative fractional boundary remains defined truncation");
    require(breathe_forward_steps(high - .25, 1) == std::numeric_limits<int>::max(),
            "forward checks plus-one overflow after truncation");
    require(breathe_forward_steps(low - .75, 1) == std::numeric_limits<int>::min() + 1,
            "forward lower bound preserves defined addition");
    for (auto operation : {breathe_forward_steps, breathe_retreat_steps}) {
        for (double step : {0., -0., -.25, inf, -inf, std::numeric_limits<double>::quiet_NaN()})
            rejects<std::invalid_argument>([&] { operation(1, step); }, "invalid step rejects before arithmetic");
        for (double distance : {inf, -inf, std::numeric_limits<double>::quiet_NaN()})
            rejects<std::invalid_argument>([&] { operation(distance, .25); }, "nonfinite distance rejects before narrowing");
        for (double distance : {low - 1, high + 1, 1e300})
            rejects<std::out_of_range>([&] { operation(distance, 1); }, "out-of-range conversion rejects");
        rejects<std::out_of_range>([&] { operation(1e300, 1e-300); }, "quotient overflow rejects before int conversion");
    }
    rejects<std::out_of_range>([&] { breathe_forward_steps(high, 1); }, "forward plus-one overflow rejects");
}
} // namespace

int main() {
    try {
        round_contracts();
        step_contracts();
        std::cout << checks << " pure precision operation contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Precision operations FAILED: " << e.what() << '\n';
        return 1;
    }
}
