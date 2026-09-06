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

Sexpr sexpr_loads(std::string_view text);
std::string sexpr_dumps(const Sexpr& node, int indent = 0);
std::string sexpr_fmt_num(double value);

}  // namespace schgen
