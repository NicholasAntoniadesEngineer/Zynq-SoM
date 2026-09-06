#include "schgen/sexpr.hpp"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace schgen {
namespace {

struct Parser {
    std::string_view text;
    std::size_t i = 0;

    void skip_ws() {
        while (i < text.size() && (text[i] == ' ' || text[i] == '\t'
                                   || text[i] == '\r' || text[i] == '\n')) {
            ++i;
        }
    }

    Sexpr parse() {
        skip_ws();
        if (i >= text.size()) {
            throw std::runtime_error("sexpr: unexpected EOF");
        }
        const char c = text[i];
        if (c == '(') {
            ++i;
            SexprList out;
            while (true) {
                skip_ws();
                if (i < text.size() && text[i] == ')') {
                    ++i;
                    return Sexpr{out};
                }
                out.push_back(parse());
            }
        }
        if (c == '"') {
            ++i;
            std::string buf;
            while (i < text.size()) {
                const char ch = text[i];
                if (ch == '\\' && i + 1 < text.size()) {
                    buf.push_back(text[i + 1]);
                    i += 2;
                    continue;
                }
                if (ch == '"') {
                    ++i;
                    return Sexpr{buf};
                }
                buf.push_back(ch);
                ++i;
            }
            throw std::runtime_error("sexpr: unterminated string");
        }
        const std::size_t j0 = i;
        while (i < text.size() && text[i] != ' ' && text[i] != '\t'
               && text[i] != '\r' && text[i] != '\n' && text[i] != '('
               && text[i] != ')' && text[i] != '"') {
            ++i;
        }
        const std::string tok(text.substr(j0, i - j0));
        char* end = nullptr;
        const long long as_int = std::strtoll(tok.c_str(), &end, 10);
        if (end == tok.c_str() + tok.size()) {
            return Sexpr{static_cast<double>(as_int)};
        }
        end = nullptr;
        const double as_float = std::strtod(tok.c_str(), &end);
        if (end == tok.c_str() + tok.size()) {
            return Sexpr{as_float};
        }
        return Sexpr{Sexpr::Sym{tok}};
    }
};

}  // namespace

std::string sexpr_fmt_num(double value) {
    if (std::isfinite(value) && value == std::floor(value)
        && value >= static_cast<double>(INT64_MIN)
        && value <= static_cast<double>(INT64_MAX)) {
        return std::to_string(static_cast<int64_t>(value));
    }
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6f", value);
    std::string s(buf);
    while (!s.empty() && s.back() == '0') {
        s.pop_back();
    }
    if (!s.empty() && s.back() == '.') {
        s.pop_back();
    }
    return s.empty() ? "0" : s;
}

Sexpr sexpr_loads(std::string_view text) {
    Parser p{text, 0};
    Sexpr node = p.parse();
    p.skip_ws();
    if (p.i != text.size()) {
        throw std::runtime_error("sexpr: trailing data at "
                                 + std::to_string(p.i));
    }
    return node;
}

std::string sexpr_dumps(const Sexpr& node, int indent) {
    const std::string pad(static_cast<std::size_t>(indent), '\t');
    if (std::holds_alternative<Sexpr::Sym>(node.v)) {
        return std::get<Sexpr::Sym>(node.v).name;
    }
    if (std::holds_alternative<std::string>(node.v)) {
        std::string esc = std::get<std::string>(node.v);
        std::string out = "\"";
        for (char ch : esc) {
            if (ch == '\\' || ch == '"') {
                out.push_back('\\');
            }
            out.push_back(ch);
        }
        out.push_back('"');
        return out;
    }
    if (std::holds_alternative<bool>(node.v)) {
        return std::get<bool>(node.v) ? "yes" : "no";
    }
    if (std::holds_alternative<double>(node.v)) {
        return sexpr_fmt_num(std::get<double>(node.v));
    }
    const auto& lst = std::get<SexprList>(node.v);
    if (lst.empty()) {
        return "()";
    }
    bool has_list = false;
    std::vector<std::string> inner;
    inner.reserve(lst.size());
    std::size_t flat = 0;
    for (const Sexpr& x : lst) {
        if (std::holds_alternative<SexprList>(x.v)) {
            has_list = true;
        }
        inner.push_back(sexpr_dumps(x, indent + 1));
        // Python len() is code points; UTF-8 em-dash is 3 bytes / 1 char.
        for (unsigned char ch : inner.back()) {
            if ((ch & 0xC0) != 0x80) {
                ++flat;
            }
        }
    }
    if (!has_list && flat < 90) {
        std::string out = "(";
        for (std::size_t i = 0; i < inner.size(); ++i) {
            if (i != 0) {
                out.push_back(' ');
            }
            out += inner[i];
        }
        out.push_back(')');
        return out;
    }
    std::string out = "(" + inner[0];
    for (std::size_t i = 1; i < inner.size(); ++i) {
        out.push_back('\n');
        out.append(static_cast<std::size_t>(indent + 1), '\t');
        out += inner[i];
    }
    out.push_back('\n');
    out += pad;
    out.push_back(')');
    return out;
}

}  // namespace schgen
