#pragma once

#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace schgen {

struct Sexpr;

using SexprList = std::vector<Sexpr>;

struct Sexpr {
    struct Sym {
        std::string name;
    };
    std::variant<Sym, std::string, double, bool, SexprList> v;
};

// Numeric domain: finite doubles in [-2^63, 2^63). Integer tokens must also
// fit int64_t and be exactly representable as doubles (no silent integer loss).
// Floating tokens use strtod precision; range errors, including underflow, throw.
// Out-of-domain values throw std::runtime_error rather than clamp or truncate.
Sexpr sexpr_loads(std::string_view text);
std::string sexpr_dumps(const Sexpr& node, int indent = 0);
// Same finite domain as loads; retains the geometry format of six fractional
// decimal places with trailing zeros removed. This is intentionally lossy for
// fractions beyond six places, not a general-purpose double round-trip format.
std::string sexpr_fmt_num(double value);

}  // namespace schgen
