#pragma once

// Small, value-only authoring vocabulary. No geometry, catalog/library setup,
// filesystem I/O, publication or verification context belongs in this header.
#include "schgen/json.hpp"
#include <algorithm>
#include <charconv>
#include <cstddef>
#include <initializer_list>

namespace schgen::authoring_values {
template<class T, class K> auto find(T& entries, const K& key) {
    auto it = std::find_if(entries.begin(), entries.end(), [&](const auto& e) { return e.first == key; });
    return it == entries.end() ? nullptr : &it->second;
}
inline bool starts(const std::string& s, const std::string& prefix) { return s.compare(0, prefix.size(), prefix) == 0; }
inline unsigned codepoint(const std::string& s, std::size_t& i) {
    const auto byte = static_cast<unsigned char>(s[i++]);
    if (byte < 128) return byte;
    int extra = (byte & 0xe0) == 0xc0 ? 1 : (byte & 0xf0) == 0xe0 ? 2 : (byte & 0xf8) == 0xf0 ? 3 : 0;
    unsigned cp = byte & ((1u << (6 - extra)) - 1);
    if (!extra || i + extra > s.size()) return byte;
    for (int k = 0; k < extra; ++k) {
        auto c = static_cast<unsigned char>(s[i]);
        if ((c & 0xc0) != 0x80) return byte;
        cp = (cp << 6) | (c & 63); ++i;
    }
    return cp;
}
inline bool whitespace(unsigned cp) {
    return (cp >= 9 && cp <= 13) || (cp >= 0x1c && cp <= 0x20) || cp == 0x85 || cp == 0xa0 || cp == 0x1680 ||
        (cp >= 0x2000 && cp <= 0x200a) || cp == 0x2028 || cp == 0x2029 || cp == 0x202f || cp == 0x205f || cp == 0x3000;
}
inline std::string trim(const std::string& s) {
    std::size_t begin = s.size(), end = 0, i = 0;
    while (i < s.size()) { auto start = i; auto cp = codepoint(s, i); if (!whitespace(cp)) { begin = std::min(begin, start); end = i; } }
    return begin == s.size() ? "" : s.substr(begin, end - begin);
}
inline std::string repr(const std::string& s) {
    char q = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, q);
    for (unsigned char c : s) {
        if (c == q || c == '\\') { out += '\\'; out += char(c); }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 32 || c == 127) { const char* h = "0123456789abcdef"; out += "\\x"; out += h[c >> 4]; out += h[c & 15]; }
        else out += char(c);
    }
    return out + q;
}
inline std::string number17(double value) {
    // Same general/17-digit to_chars operation as the old model helper. This
    // fixed precision needs far fewer than 768 bytes for every double (including
    // signed zero, infinity and NaN); the variable-precision helper's range-error
    // branch cannot be reached by the authoring PortType diagnostic.
    char out[768];
    const auto result = std::to_chars(out, out + sizeof out, value, std::chars_format::general, 17);
    return {out, result.ptr};
}
inline JsonNode j(const std::string& s) { JsonNode n; n.kind = JsonKind::String; n.string_value = s; return n; }
inline JsonNode j(const char* s) { return j(std::string(s)); }
inline JsonNode j(double d) { JsonNode n; n.kind = JsonKind::Number; n.number_value = d; return n; }
inline JsonNode j(bool b) { JsonNode n; n.kind = JsonKind::Bool; n.bool_value = b; return n; }
inline JsonNode obj(std::initializer_list<std::pair<std::string, JsonNode>> fs = {}) { JsonNode n; n.kind = JsonKind::Object; n.object_value = fs; return n; }
inline JsonNode arr(std::initializer_list<JsonNode> fs = {}) { JsonNode n; n.kind = JsonKind::Array; n.array_value = fs; return n; }
inline JsonNode strings(const std::vector<std::string>& ss) { auto n = arr(); for (const auto& s : ss) n.array_value.push_back(j(s)); return n; }
} // namespace schgen::authoring_values
