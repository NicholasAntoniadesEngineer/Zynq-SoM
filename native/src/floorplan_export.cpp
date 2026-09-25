#include "schgen/floorplan.hpp"
#include "schgen/atomic_file.hpp"

#include <charconv>
#include <cmath>
#include <cstdint>

namespace schgen {
namespace {
std::string quoted(const std::string& s) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    auto unit = [&](std::uint32_t c) {
        out += "\\u";
        for (int k = 12; k >= 0; k -= 4) out += hex[(c >> k) & 15];
    };
    for (std::size_t i = 0; i < s.size();) {
        const auto first = static_cast<unsigned char>(s[i++]);
        if (first == '"' || first == '\\') { out += '\\'; out += static_cast<char>(first); }
        else if (first == '\b') out += "\\b";
        else if (first == '\f') out += "\\f";
        else if (first == '\n') out += "\\n";
        else if (first == '\r') out += "\\r";
        else if (first == '\t') out += "\\t";
        else if (first < 32 || first == 127) unit(first);
        else if (first < 128) out += static_cast<char>(first);
        else {
            auto invalid = [] { throw FloorplanError("floorplan export: invalid UTF-8"); };
            if (first < 0xc2 || first > 0xf4) invalid();
            const int count = first >= 0xf0 ? 3 : first >= 0xe0 ? 2 : 1;
            std::uint32_t c = first & (count == 3 ? 7 : count == 2 ? 15 : 31);
            for (int k = 0; k < count; ++k) {
                if (i == s.size() || (static_cast<unsigned char>(s[i]) & 0xc0) != 0x80) invalid();
                c = (c << 6) | (static_cast<unsigned char>(s[i++]) & 63);
            }
            if ((count == 1 && c < 0x80) || (count == 2 && c < 0x800) ||
                (count == 3 && c < 0x10000) || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) invalid();
            if (c > 0xffff) { c -= 0x10000; unit(0xd800 + (c >> 10)); unit(0xdc00 + (c & 1023)); }
            else unit(c);
        }
    }
    return out + '"';
}

std::string pretty(const JsonNode& node, std::size_t indent = 0) {
    if (node.kind == JsonKind::Null) return "null";
    if (node.kind == JsonKind::Bool) return node.bool_value ? "true" : "false";
    if (node.kind == JsonKind::String) return quoted(node.string_value);
    if (node.kind == JsonKind::Number) {
        if (!std::isfinite(node.number_value)) throw FloorplanError("floorplan export: non-finite number");
        char buffer[128];
        const auto r = std::to_chars(buffer, buffer + sizeof(buffer), node.number_value, std::chars_format::general);
        if (r.ec != std::errc{}) throw FloorplanError("floorplan export: cannot format number");
        std::string s(buffer, r.ptr);
        // Python uses fixed notation for doubles in [1e-4, 1e16).
        const double magnitude = std::abs(node.number_value);
        if (magnitude >= 1e-4 && magnitude < 1e16 && s.find_first_of("eE") != std::string::npos) {
            const auto fixed = std::to_chars(buffer, buffer + sizeof(buffer), node.number_value, std::chars_format::fixed);
            if (fixed.ec != std::errc{}) throw FloorplanError("floorplan export: cannot format number");
            s.assign(buffer, fixed.ptr);
        }
        if (s.find_first_of(".eE") == std::string::npos) s += ".0";
        return s;
    }
    const bool object = node.kind == JsonKind::Object;
    const auto count = object ? node.object_value.size() : node.array_value.size();
    if (!count) return object ? "{}" : "[]";
    std::string out = object ? "{\n" : "[\n";
    for (std::size_t i = 0; i < count; ++i) {
        out += std::string(indent + 2, ' ');
        if (object) out += quoted(node.object_value[i].first) + ": " + pretty(node.object_value[i].second, indent + 2);
        else out += pretty(node.array_value[i], indent + 2);
        out += i + 1 == count ? "\n" : ",\n";
    }
    return out + std::string(indent, ' ') + (object ? '}' : ']');
}
}  // namespace

std::string render_floorplan_spec_json(const FloorplanPlan& plan) {
    return pretty(export_floorplan_spec(plan)) + "\n";
}

std::filesystem::path write_floorplan_spec(const FloorplanPlan& plan,
                                          const std::filesystem::path& path) {
    const auto bytes = render_floorplan_spec_json(plan);
    write_atomic_file(path.string(), {bytes.begin(), bytes.end()});
    return path;
}
}  // namespace schgen
