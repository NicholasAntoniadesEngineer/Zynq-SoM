// Optional independent developer oracle; requires MPFR/GMP, never linked into
// the product or the default contracts. See numerical_reliability.md for build.
#include "schgen/occupancy.hpp"
#include "schgen/quantize.hpp"
#include "../src/accurate_norm.hpp"
#include <mpfr.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {
double from_bits(std::uint64_t bits) {
    double value;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}
bool same(double a, double b) {
    return a == b && (a != 0 || std::signbit(a) == std::signbit(b));
}
unsigned facing_oracle() {
    // Enough precision to retain exact differences/products across the entire
    // binary64 exponent span. atan2 is independent of the legacy acos formula.
    mpfr_t x,y,u,v,dot,cross,one,two,angle,pi;
    mpfr_inits2(4608,x,y,u,v,dot,cross,one,two,angle,pi,(mpfr_ptr)0);
    mpfr_const_pi(pi,MPFR_RNDN);
    unsigned count=0;
    const auto check = [&](double zx,double zy,double ox,double oy,double dx,double dy) {
        const auto difference = [&](mpfr_ptr dst,double endpoint,double origin) {
            mpfr_set_d(dst,endpoint,MPFR_RNDN); mpfr_set_d(one,origin,MPFR_RNDN);
            mpfr_sub(dst,dst,one,MPFR_RNDN);
        };
        difference(x,ox,zx); difference(y,oy,zy); difference(u,dx,zx); difference(v,dy,zy);
        mpfr_mul(one,x,u,MPFR_RNDN); mpfr_mul(two,y,v,MPFR_RNDN); mpfr_add(dot,one,two,MPFR_RNDN);
        mpfr_mul(one,x,v,MPFR_RNDN); mpfr_mul(two,y,u,MPFR_RNDN); mpfr_sub(cross,one,two,MPFR_RNDN);
        mpfr_abs(cross,cross,MPFR_RNDN); mpfr_atan2(angle,cross,dot,MPFR_RNDN);
        mpfr_mul_ui(angle,angle,180,MPFR_RNDN); mpfr_div(angle,angle,pi,MPFR_RNDN);
        mpfr_hypot(one,x,y,MPFR_RNDN); mpfr_hypot(two,u,v,MPFR_RNDN);
        const bool degenerate = mpfr_cmp_d(one,1e-9)<=0 || mpfr_cmp_d(two,1e-9)<=0;
        const double expected = degenerate ? 180 : mpfr_get_d(angle,MPFR_RNDN);
        const auto actual = schgen::accurate_facing_dot(zx,zy,ox,oy,dx,dy);
        // Verification error budget in degrees, not a design/gate tolerance.
        // Includes subtraction rounding and libm/radians-to-degrees rounding.
        if (!std::isfinite(actual.second) || std::fabs(actual.second-expected)>5e-13) {
            std::cerr << "angle mismatch: " << actual.second << " expected=" << expected << '\n';
            throw std::runtime_error("MPFR facing angle mismatch");
        }
        if (zx==0 && zy==0) {
            // Here coordinate subtraction is exact, so the independently
            // computed dot also checks finite cancellation and overflow sign.
            const double expected_dot=mpfr_get_d(dot,MPFR_RNDN);
            const double ulp=std::fabs(std::nextafter(expected_dot,0.0)-expected_dot);
            if ((std::isinf(expected_dot) && actual.first!=expected_dot) ||
                (std::isfinite(expected_dot) && (!std::isfinite(actual.first) ||
                 std::fabs(actual.first-expected_dot)>2*ulp)))
                throw std::runtime_error("MPFR facing dot mismatch");
        }
        ++count;
    };
    const double largest=std::numeric_limits<double>::max();
    for (double small : {std::numeric_limits<double>::denorm_min(),1e-200,1e-9,
                          std::nextafter(1e-9,1.0),1e-8,1e-4,1.0,1e100,1e200,largest}) {
        for (double sign : {-1.0,1.0}) {
            check(0,0,largest,largest,sign*small,0);
            check(0,0,sign*small,0,largest,largest);
            check(0,0,largest,largest,sign*small,-sign*small);
        }
    }
    for (double sign : {-1.0,1.0}) {
        check(-largest,0,largest,largest,-largest,sign*largest);
        check(-largest,-largest,largest,largest,-largest,-largest);
        check(0,0,1e308,2e-308,sign*1e-308,-sign*1e308);
    }
    // Includes cancellation after individually overflowing products, and
    // near-parallel/antiparallel angles down to one representable input step.
    for (int exponent=520; exponent<=1023; exponent+=7) {
        const double p=std::ldexp(1.0,exponent);
        for (double target : {std::nextafter(p,0),p,std::nextafter(p,INFINITY)}) {
            check(0,0,p,p,p,-target);
            check(0,0,p,p,p,target);
            check(0,0,p,p,-p,-target);
        }
    }
    std::mt19937_64 random(981325);
    for (unsigned i=0;i<2000;++i) {
        const auto sample=[&] {
            const double fraction=0.5+static_cast<double>(random()%0x100000000ULL)/0x200000000ULL;
            const double sign=random()%2 ? 1.0 : -1.0;
            return std::ldexp(sign*fraction,600+random()%425);
        };
        check(0,0,sample(),sample(),sample(),sample());
    }
    for (unsigned i=0;i<1000;++i) {
        const auto small=[&] {
            const double fraction=0.5+static_cast<double>(random()%0x100000000ULL)/0x200000000ULL;
            const double sign=random()%2 ? 1.0 : -1.0;
            return std::ldexp(sign*fraction,static_cast<int>(random()%1405)-1074);
        };
        const double x=small(), y=small();
        check(0,0,largest,largest,x,y);
        check(0,0,x,y,-largest,largest);
    }
    for (unsigned i=0;i<1000;++i) {
        const auto coordinate=[&] {
            const double fraction=0.5+static_cast<double>(random()%0x100000000ULL)/0x200000000ULL;
            const double sign=random()%2 ? 1.0 : -1.0;
            return std::ldexp(sign*fraction,800+random()%225);
        };
        const double zx=coordinate(),zy=coordinate(),ox=coordinate(),oy=coordinate(),dx=coordinate(),dy=coordinate();
        check(zx,zy,ox,oy,dx,dy);
    }
    mpfr_clears(x,y,u,v,dot,cross,one,two,angle,pi,(mpfr_ptr)0);
    return count;
}
}

int main() {
    // 256 bits is ample for the exact <=106-bit tiny-input sum of squares,
    // and for exact binary64 * 10^digits (digits <=15). It also leaves ample
    // separation when rounding a supported <=2^53 / 10^digits rational to
    // binary64. This does not claim proof for all normal-range norm inputs.
    mpfr_t a, b, result, scale;
    mpfr_inits2(256, a, b, result, scale, (mpfr_ptr)0);
    unsigned norms = 0, rounds = 0, rejected = 0, outlines = 0;
    try {
        std::mt19937_64 random(83476);
        for (unsigned i = 0; i < 1000000; ++i) {
            auto u = random() & 0x7fefffffffffffffULL;
            auto v = random() & 0x7fefffffffffffffULL;
            if (i % 2 == 0) { u &= 0xfffffffffffffULL; v &= 0xfffffffffffffULL; }
            // Include the normal/subnormal transition and branch boundary.
            if (i % 16 == 1) { u = 0x10000000000000ULL + (random()%5)-2;
                               v &= 0xfffffffffffffULL; }
            const double x = from_bits(u), y = from_bits(v);
            mpfr_set_d(a, x, MPFR_RNDN); mpfr_set_d(b, y, MPFR_RNDN);
            mpfr_hypot(result, a, b, MPFR_RNDN);
            const double expected = mpfr_get_d(result, MPFR_RNDN);
            const double actual = schgen::accurate_hypot2(x, y);
            if (!same(actual, expected)) {
                std::cerr << std::hexfloat << "norm mismatch " << x << ' ' << y
                          << " actual=" << actual << " expected=" << expected << '\n';
                throw std::runtime_error("MPFR norm mismatch");
            }
            ++norms;
        }
        for (unsigned i = 0; i < 250000; ++i) {
            double value = from_bits(random() & 0xffefffffffffffffULL);
            // Dense coverage of the application domain and the cap, beyond
            // random bit patterns (most of which are tiny or integral).
            if (i % 3 == 0) value = static_cast<double>(random()%1000000000ULL)/1e5;
            if (i % 3 == 1) value = std::ldexp(1.0 + (random()%1024)/1024.0,
                                              static_cast<int>(random()%60)-8);
            if (i % 7 == 0) value = -value;
            const int digits = i % 16;
            mpfr_set_d(a, value, MPFR_RNDN);
            mpfr_ui_pow_ui(scale, 10, digits, MPFR_RNDN);
            mpfr_mul(result, a, scale, MPFR_RNDN);
            mpfr_rint(result, result, MPFR_RNDN);
            mpfr_abs(b, result, MPFR_RNDN);
            const bool integral = value == std::floor(value);
            const bool supported = integral || mpfr_cmp_d(b, 0x1p53) <= 0;
            if (!supported) {
                bool threw = false;
                try { (void)schgen::py_round(value, digits); }
                catch (const std::runtime_error&) { threw = true; }
                if (!threw) throw std::runtime_error("round cap not enforced");
                ++rejected;
                continue;
            }
            mpfr_div(result, result, scale, MPFR_RNDN);
            const double expected = integral ? value : mpfr_get_d(result, MPFR_RNDN);
            if (!same(schgen::py_round(value, digits), expected))
                throw std::runtime_error("MPFR decimal rounding mismatch");
            ++rounds;
        }
        for (unsigned i = 0; i < 100000; ++i) {
            const double value = from_bits(random() & 0xffefffffffffffffULL);
            // Model each binary64 arithmetic stage of the established biased
            // formula, then independently truncate in arbitrary precision.
            // This intentionally does not replace it with ideal ceil(value/5).
            mpfr_set_d(a, value, MPFR_RNDN);
            mpfr_add_ui(a, a, 5, MPFR_RNDN);
            mpfr_set_d(a, mpfr_get_d(a, MPFR_RNDN), MPFR_RNDN);
            mpfr_set_d(b, 1e-6, MPFR_RNDN);
            mpfr_sub(a, a, b, MPFR_RNDN);
            mpfr_set_d(a, mpfr_get_d(a, MPFR_RNDN), MPFR_RNDN);
            mpfr_div_ui(a, a, 5, MPFR_RNDN);
            mpfr_set_d(a, mpfr_get_d(a, MPFR_RNDN), MPFR_RNDN);
            mpfr_trunc(a, a);
            mpfr_mul_ui(a, a, 5, MPFR_RNDN);
            double expected = mpfr_get_d(a, MPFR_RNDN);
            if (expected == 0) expected = 0; // Historical integer +0.
            if (!std::isfinite(expected)) {
                bool threw = false;
                try { (void)schgen::outline_snap_up(value); }
                catch (const std::runtime_error&) { threw = true; }
                if (!threw) throw std::runtime_error("outline overflow accepted");
            } else if (!same(schgen::outline_snap_up(value), expected)) {
                throw std::runtime_error("MPFR outline truncation mismatch");
            }
            ++outlines;
        }
        const auto angles=facing_oracle();
        std::cout << "MPFR oracle PASS: " << norms << " norms, " << rounds
                  << " supported decimal rounds, " << rejected << " cap rejections, "
                  << outlines << " outlines, " << angles << " facing angles\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        mpfr_clears(a, b, result, scale, (mpfr_ptr)0);
        return 1;
    }
    mpfr_clears(a, b, result, scale, (mpfr_ptr)0);
}
