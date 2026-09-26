// Standalone numeric regression coverage; no Python, catalogs or generated files.
// Deliberate supported-domain errors are tested rather than silently extending
// the double-only Sexpr representation or the bounded decimal rounding kernel.
#include "schgen/occupancy.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/quantize.hpp"
#include "../src/accurate_norm.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <random>
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

void norm_contracts() {
    // Independently rounded MPFR 256-bit hypot results for exact binary64
    // inputs. All failed by one subnormal ULP before the single-round fix.
    struct Case { double x, y, expected; };
    for (const auto& c : {
        Case{0x1.edc9cd02eb226p-1023, 0x1.40e6a86941c2p-1027, 0x1.ee3207de7814ep-1023},
        {0x1.33819717c742cp-1023, 0x1.3c1fb462b4e86p-1023, 0x1.b903e06a5fa02p-1023},
        {0x1.5f326a1ea3982p-1023, 0x1.65175d028c49ap-1023, 0x1.f4da4c5ed4f06p-1023},
        {0x1.971df44f6d24p-1026, 0x1.b273a287f56ep-1026, 0x1.29b245eedc4b8p-1025},
        {0x1.7c93bed016d44p-1024, 0x1.c0edcddf4e96p-1025, 0x1.b9d73b414c824p-1024}}) {
        for (double sign : {-1.0, 1.0}) {
            require(schgen::accurate_hypot2(sign*c.x, c.y) == c.expected,
                    "subnormal norm incorrectly rounded");
            require(schgen::accurate_hypot2(c.y, sign*c.x) == c.expected,
                    "subnormal norm changed under permutation");
        }
    }
    for (int exponent = -1074; exponent <= 1020; ++exponent) {
        const double unit = std::ldexp(1.0, exponent);
        require(schgen::accurate_hypot2(3*unit, 4*unit) == 5*unit,
                "exact Pythagorean norm failed");
        require(schgen::accurate_hypot2(unit, 0) == unit, "axis norm changed");
    }
    for (double x : {std::numeric_limits<double>::denorm_min(),
                     std::nextafter(std::numeric_limits<double>::min(), 0.0),
                     std::numeric_limits<double>::min(),
                     std::nextafter(std::numeric_limits<double>::min(), 1.0),
                     std::numeric_limits<double>::max()}) {
        require(schgen::accurate_hypot2(x, 0) == x, "norm endpoint changed");
    }
    const double inf = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    require(schgen::accurate_hypot2(inf, nan) == inf, "norm infinity precedence");
    require(std::isnan(schgen::accurate_hypot2(1, nan)), "norm NaN propagation");
    require(!std::signbit(schgen::accurate_hypot2(-0.0, -0.0)), "norm signed zero");
    require(schgen::accurate_hypot2(std::numeric_limits<double>::max(),
                                  std::numeric_limits<double>::max()) == inf,
            "norm overflow classification");
}

void outline_contracts() {
    struct Case { double value, expected; };
    for (const auto& c : {Case{0, 0}, {-0.0, 0}, {1, 5}, {5, 5},
                          {5+1e-7, 5}, {5+2e-6, 10}, {-5, 0}, {-6, 0}, {-10, -5},
                          // Preserve the floating expression's existing bias
                          // and operation order even when 1e-6 is below an ULP.
                          {1e12, 1000000000005.0}, {-1e12, -999999999995.0}}) {
        require(schgen::outline_snap_up(c.value) == c.expected,
                "outline mathematical boundary failed");
    }
    require(!std::signbit(schgen::outline_snap_up(-1)), "outline negative zero changed");
    const double inf = std::numeric_limits<double>::infinity();
    for (double value : {inf, -inf, std::numeric_limits<double>::quiet_NaN()})
        rejects([&] { schgen::outline_snap_up(value); }, "outline nonfinite accepted");
    // Historical parity is distinct from mathematical accuracy. Restrict the
    // old expression to its defined int-conversion domain before comparing.
    std::mt19937_64 random(615827);
    for (int i = 0; i < 100000; ++i) {
        const double value = (static_cast<double>(random() % 20000000000000ULL)
                              - 10000000000000.0) / 1000;
        const int old_units = static_cast<int>((value + 5.0 - 1e-6) / 5.0);
        require(schgen::outline_snap_up(value) == static_cast<double>(old_units)*5.0,
                "defined historical outline output changed");
    }
    for (double units : {static_cast<double>(std::numeric_limits<int>::min()),
                         static_cast<double>(std::numeric_limits<int>::max())}) {
        for (double delta : {-10.0, -5.0, 0.0, 5.0, 10.0}) {
            const double value = units*5.0 + delta;
            const auto reference = static_cast<std::int64_t>((value+5.0-1e-6)/5.0);
            require(schgen::outline_snap_up(value) == static_cast<double>(reference)*5.0,
                    "outline int boundary corrupted");
        }
    }
}

void facing_contracts() {
    const double large = 1e200, maximum = std::numeric_limits<double>::max();
    for (double magnitude : {1e155, large, maximum}) {
        const auto perpendicular = schgen::accurate_facing_dot(0,0,magnitude,magnitude,-magnitude,magnitude);
        require(perpendicular.first == 0 && perpendicular.second == 90,
                "overflowing perpendicular facing vectors");
        require(schgen::accurate_facing_dot(0,0,magnitude,magnitude,magnitude,magnitude).second == 0,
                "overflowing parallel facing vectors");
        require(schgen::accurate_facing_dot(0,0,magnitude,magnitude,-magnitude,-magnitude).second == 180,
                "overflowing antiparallel facing vectors");
    }
    const double power = 0x1p520;
    require(schgen::accurate_facing_dot(0,0,power,power,power,std::nextafter(-power,0)).first == 0x1p987,
            "finite dot lost in overflowing product cancellation");
    require(schgen::accurate_facing_dot(0,0,power,power,power,std::nextafter(-power,-INFINITY)).first == -0x1p988,
            "negative dot lost in overflowing product cancellation");
    const auto unbalanced = schgen::accurate_facing_dot(0,0,maximum,maximum,1e-8,0);
    require(std::isfinite(unbalanced.first) && unbalanced.second == 45,
            "overflowed norm corrupts finite high/low-magnitude angle");
    const auto thin = schgen::accurate_facing_dot(0,0,1e308,2e-308,1e-308,-1e308);
    require(std::fabs(thin.first + 1) < 1e-15 && thin.second == 90,
            "vector scaling erased small component products");
    require(schgen::accurate_facing_dot(-maximum,0,maximum,maximum,-maximum,maximum).second > 63 &&
            schgen::accurate_facing_dot(-maximum,0,maximum,maximum,-maximum,maximum).second < 64,
            "finite coordinate subtraction overflow");
    const auto zero = schgen::accurate_facing_dot(-maximum,-maximum,maximum,maximum,-maximum,-maximum);
    require(zero.first == 0 && zero.second == 180, "degenerate overflowing displacement");
    for (double tiny : {0.0, std::numeric_limits<double>::denorm_min(), 1e-200, 1e-9}) {
        require(schgen::accurate_facing_dot(0,0,maximum,maximum,tiny,0).second == 180,
                "existing degenerate vector threshold changed");
    }
    for (double invalid : {std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity(),
                           std::numeric_limits<double>::quiet_NaN()}) {
        for (int index = 0; index < 6; ++index) {
            double values[] = {0,0,1,0,0,1}; values[index] = invalid;
            const auto face = schgen::accurate_facing_dot(values[0],values[1],values[2],values[3],values[4],values[5]);
            require(std::isnan(face.first) && std::isnan(face.second), "invalid geometry silently accepted");
        }
    }
    // Historical parity on finite, nonoverflowing intermediate arithmetic.
    std::mt19937_64 random(54938);
    for (int i = 0; i < 100000; ++i) {
        const auto sample = [&] { return (static_cast<double>(random()%2000000)-1000000)/1000; };
        const double zx=sample(), zy=sample(), ox=sample(), oy=sample(), dx=sample(), dy=sample();
        const double x=ox-zx, y=oy-zy, u=dx-zx, v=dy-zy;
        const double dot=x*u+y*v, n1=schgen::accurate_hypot2(x,y), n2=schgen::accurate_hypot2(u,v);
        const double angle = n1<=1e-9 || n2<=1e-9 ? 180 :
            std::acos(std::max(-1.0,std::min(1.0,dot/(n1*n2))))*(180.0/3.141592653589793);
        const auto actual=schgen::accurate_facing_dot(zx,zy,ox,oy,dx,dy);
        require(actual.first==dot && actual.second==angle, "ordinary facing arithmetic changed");
    }
}

}  // namespace

int main() {
    try {
        parser_contracts();
        formatter_contracts();
        rounding_contracts();
        norm_contracts();
        outline_contracts();
        facing_contracts();
        std::cout << "native numeric contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "native numeric contracts failed: " << e.what() << '\n';
        return 1;
    }
}
