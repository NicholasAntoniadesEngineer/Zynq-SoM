// Standalone numeric regression coverage; no Python, catalogs or generated files.
// Deliberate supported-domain errors are tested rather than silently extending
// the double-only Sexpr representation or the bounded decimal rounding kernel.
#include "schgen/occupancy.hpp"
#include "schgen/sexpr.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template <typename F>
void rejects(F action, const char* message) {
    try {
        action();
    } catch (const std::runtime_error&) {
        return;
    }
    throw std::runtime_error(message);
}

double number(const char* text) {
    return std::get<double>(schgen::sexpr_loads(text).v);
}

void parser_contracts() {
    require(number("9007199254740992") == 0x1p53, "exact 2^53 rejected");
    require(number("9007199254740994") == 0x1.0000000000001p53,
            "exact integer above 2^53 rejected");
    require(number("-9223372036854775808") == -0x1p63, "INT64_MIN rejected");
    require(number("9223372036854774784") == std::nextafter(0x1p63, 0.0),
            "largest supported positive integer rejected");
    require(number("1.27e2") == 127.0, "ordinary exponent changed");
    require(number("2.2250738585072014e-308") == std::numeric_limits<double>::min(),
            "minimum normal double rejected");
    require(std::signbit(number("-0.0")), "parsed negative zero lost");
    for (const char* token : {
             "9007199254740993", "-9007199254740993",
             "9223372036854775807", "9223372036854775808",
             "-9223372036854775809", "9999999999999999999999999999999999",
             "9223372036854775808.0", "-9223372036854777856.0",
             "1e309", "-1e309", "1e-999", "-1e-999", "nan", "inf", "-inf"}) {
        rejects([&] { schgen::sexpr_loads(token); }, token);
    }
    const auto symbol = schgen::sexpr_loads("999999999999999999999999999999suffix");
    require(std::get<schgen::Sexpr::Sym>(symbol.v).name
                == "999999999999999999999999999999suffix",
            "numeric prefix incorrectly rejects symbol");
    rejects([] { schgen::sexpr_loads(")"); }, "unexpected delimiter accepted");
    // errno from an earlier rejected token must not poison the next parse.
    require(number("42") == 42.0 && number("0.125") == 0.125,
            "numeric error leaked into next parse");
}

void formatter_contracts() {
    require(schgen::sexpr_fmt_num(-0x1p63) == "-9223372036854775808",
            "INT64_MIN formatting changed");
    const double upper = std::nextafter(0x1p63, 0.0);
    require(schgen::sexpr_fmt_num(upper) == "9223372036854774784",
            "largest supported positive integer formatting changed");
    require(number(schgen::sexpr_fmt_num(upper).c_str()) == upper,
            "supported boundary did not round-trip");
    for (double value : {0x1p63, std::nextafter(-0x1p63, -INFINITY),
                         1e100, -1e100, std::numeric_limits<double>::max(),
                         std::numeric_limits<double>::infinity(),
                         -std::numeric_limits<double>::infinity(),
                         std::numeric_limits<double>::quiet_NaN()}) {
        rejects([&] { schgen::sexpr_fmt_num(value); }, "out-of-domain format accepted");
        rejects([&] { schgen::sexpr_dumps(schgen::Sexpr{value}); },
                "dumps bypassed numeric domain");
    }
    struct Case { double value; const char* expected; };
    for (const auto& c : {Case{0, "0"}, {-0.0, "0"}, {1.27, "1.27"},
                          {-11.24955, "-11.24955"}, {0.123456789, "0.123457"},
                          {1e-9, "0"}, {-1e-9, "-0"}, {168, "168"}}) {
        require(schgen::sexpr_fmt_num(c.value) == c.expected,
                "ordinary geometry numeric bytes changed");
    }
    const std::string fixture = "(at 1.27 -11.24955 90)";
    require(schgen::sexpr_dumps(schgen::sexpr_loads(fixture)) == fixture,
            "ordinary geometry s-expression bytes changed");
}

void rounding_contracts() {
    struct Case { double value; int digits; double expected; };
    // Exact expected doubles from Python round(), including decimal traps where
    // multiplying by 10^digits first would introduce a false halfway case.
    for (const auto& c : {Case{11.24955, 4, 11.2495}, {-11.24955, 4, -11.2495},
                          {2.675, 2, 2.67}, {1.005, 2, 1.0},
                          {0.125, 2, 0.12}, {0.375, 2, 0.38},
                          {0.15, 1, 0.1}, {0.35, 1, 0.3},
                          {2.5, 0, 2.0}, {3.5, 0, 4.0}, {-2.5, 0, -2.0},
                          {0.49999999999999994, 0, 0.0},
                          {1.2345678901234567, 15, 1.234567890123457},
                          {1.0000000000000002, 15, 1.0}}) {
        require(schgen::py_round(c.value, c.digits) == c.expected,
                "Python rounding equivalence failed");
    }
    for (double integral : {1e15, -1e15, 0x1p63, -0x1p63,
                            std::numeric_limits<double>::max()}) {
        for (int digits : {0, 4, 15}) {
            require(schgen::py_round(integral, digits) == integral,
                    "integral double corrupted during rounding");
        }
    }
    require(std::signbit(schgen::py_round(-0.0, 4)), "negative zero lost");
    require(std::signbit(schgen::py_round(-1e-100, 15)), "rounded negative zero lost");
    require(schgen::py_round(std::numeric_limits<double>::denorm_min(), 15) == 0.0,
            "subnormal rounding failed");
    const double inf = std::numeric_limits<double>::infinity();
    require(schgen::py_round(inf, 4) == inf && schgen::py_round(-inf, 4) == -inf,
            "nonfinite passthrough changed");
    require(std::isnan(schgen::py_round(std::numeric_limits<double>::quiet_NaN(), 4)),
            "NaN passthrough changed");
    for (int digits : {-1, 16, 40, 100, std::numeric_limits<int>::max(),
                       std::numeric_limits<int>::min()}) {
        for (double value : {0.0, 1.25, inf}) {
            rejects([&] { schgen::py_round(value, digits); },
                    "unsupported digits accepted");
        }
    }
    rejects([] { schgen::py_round(123.456, 15); },
            "inexact quantized numerator accepted");
    rejects([] { schgen::py_round(0x1.0000000000001p51, 15); },
            "large left-shift quantization accepted");
    // The exact binary input times ten is 9007199254740992.5; half-even
    // quantization gives exactly 2^53 decimal units, the inclusive limit.
    const double boundary = 900719925474099.25;
    require(schgen::py_round(boundary, 1) == 900719925474099.2,
            "inclusive quantized boundary rejected");
    require(schgen::py_round(-boundary, 1) == -900719925474099.2,
            "negative inclusive quantized boundary rejected");
    const double below = std::nextafter(boundary, 0.0);
    require(schgen::py_round(below, 1) == 900719925474099.1,
            "value below quantized boundary changed");
    require(schgen::py_round(-below, 1) == -900719925474099.1,
            "negative value below quantized boundary changed");
    const double above = std::nextafter(boundary, inf);
    rejects([&] { schgen::py_round(above, 1); },
            "value above quantized boundary accepted");
    rejects([&] { schgen::py_round(-above, 1); },
            "negative value above quantized boundary accepted");
}

}  // namespace

int main() {
    try {
        parser_contracts();
        formatter_contracts();
        rounding_contracts();
        std::cout << "native numeric contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "native numeric contracts failed: " << e.what() << '\n';
        return 1;
    }
}
