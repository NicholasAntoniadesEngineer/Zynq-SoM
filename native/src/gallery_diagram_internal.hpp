#pragma once
#include "schgen/atomic_file.hpp"
#include "schgen/project.hpp"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <locale>
#include <sstream>

namespace schgen::document_detail {
namespace fs = std::filesystem;
inline std::string join(const std::vector<std::string> &parts, const std::string &sep) {
    std::string out;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i)
            out += sep;
        out += parts[i];
    }
    return out;
}
inline std::string read(const fs::path &path) {
    std::ifstream f(path, std::ios::binary);
    if (!f)
        throw ProjectError("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
inline void publish(const fs::path &path, const std::string &text) {
    write_atomic_file(path.string(), {text.begin(), text.end()});
}
inline std::vector<std::uint32_t> codepoints(const std::string &text) {
    std::vector<std::uint32_t> out;
    for (std::size_t i = 0; i < text.size();) {
        const auto c = static_cast<unsigned char>(text[i++]);
        unsigned n = c < 0x80                 ? 0
                     : c >= 0xc2 && c <= 0xdf ? 1
                     : c >= 0xe0 && c <= 0xef ? 2
                     : c >= 0xf0 && c <= 0xf4 ? 3
                                              : 4;
        if (n == 4 || i + n > text.size())
            throw ProjectError("invalid document UTF-8");
        std::uint32_t cp = n ? c & ((1u << (6 - n)) - 1) : c;
        for (unsigned k = 0; k < n; ++k) {
            const auto b = static_cast<unsigned char>(text[i++]);
            if ((b & 0xc0) != 0x80)
                throw ProjectError("invalid document UTF-8");
            cp = (cp << 6) | (b & 63);
        }
        if ((n == 1 && cp < 0x80) || (n == 2 && cp < 0x800) || (n == 3 && cp < 0x10000) ||
            cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))
            throw ProjectError("invalid document UTF-8");
        out.push_back(cp);
    }
    return out;
}
inline bool space(std::uint32_t cp) {
    return (cp >= 9 && cp <= 13) || (cp >= 28 && cp <= 32) || cp == 0x85 || cp == 0xa0 ||
           cp == 0x1680 || (cp >= 0x2000 && cp <= 0x200a) || cp == 0x2028 || cp == 0x2029 ||
           cp == 0x202f || cp == 0x205f || cp == 0x3000;
}
inline std::string xml(const std::string &s) {
    std::string out;
    for (char c : s)
        out += c == '&' ? "&amp;" : c == '<' ? "&lt;" : c == '>' ? "&gt;" : std::string(1, c);
    return out;
}
inline std::string fixed(double value, int precision = 0) {
    std::ostringstream s;
    s.imbue(std::locale::classic());
    s << std::fixed << std::setprecision(precision) << value;
    return s.str();
}
inline std::string pyfloat(double value) {
    char b[128];
    auto r = std::to_chars(b, b + sizeof b, value, std::chars_format::general);
    if (r.ec != std::errc{})
        throw ProjectError("document number formatting failed");
    std::string s(b, r.ptr);
    if (s.find_first_of(".eE") == s.npos)
        s += ".0";
    return s;
}
inline fs::path absolute(const fs::path &p) { return fs::absolute(p).lexically_normal(); }
} // namespace schgen::document_detail
