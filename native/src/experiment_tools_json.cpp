#include "experiment_tools_internal.hpp"
#include <array>
#include <cstdint>
#include <regex>

namespace schgen::experiment_detail {
std::string universal_newlines(const std::string &bytes) {
    std::string out;
    for (std::size_t i = 0; i < bytes.size(); ++i) {
        if (bytes[i] != '\r') out += bytes[i];
        else { out += '\n'; if (i + 1 < bytes.size() && bytes[i + 1] == '\n') ++i; }
    }
    return out;
}
std::string tail_characters(const std::string &text, std::size_t count) {
    std::size_t i = text.size();
    while (i && count--) {
        --i;
        while (i && (static_cast<unsigned char>(text[i]) & 0xc0) == 0x80) --i;
    }
    return text.substr(i);
}
std::string tail_lines(const std::string &text, std::size_t count) {
    std::vector<std::string> lines;
    std::size_t start = 0;
    for (std::size_t i = 0; i < text.size();) {
        const auto c = static_cast<unsigned char>(text[i]);
        std::size_t skip = 0;
        if (c == '\r') skip = i + 1 < text.size() && text[i + 1] == '\n' ? 2 : 1;
        else if (c == '\n' || c == '\v' || c == '\f' || (c >= 0x1c && c <= 0x1e)) skip = 1;
        else if (text.compare(i, 2, "\xc2\x85") == 0) skip = 2;
        else if (text.compare(i, 3, "\xe2\x80\xa8") == 0 || text.compare(i, 3, "\xe2\x80\xa9") == 0) skip = 3;
        if (!skip) { ++i; continue; }
        lines.push_back(text.substr(start, i - start)); i += skip; start = i;
    }
    if (start < text.size()) lines.push_back(text.substr(start));
    const auto first = lines.size() > count ? lines.size() - count : 0;
    return document_detail::join({lines.begin() + static_cast<std::ptrdiff_t>(first), lines.end()}, "\n");
}
// MD5 is solely the historical PCB byte fingerprint, never a security proof.
std::string diagnostic_md5(const std::string &bytes) {
    constexpr std::array<std::uint32_t, 64> constants{{
        0xd76aa478,0xe8c7b756,0x242070db,0xc1bdceee,0xf57c0faf,0x4787c62a,0xa8304613,0xfd469501,
        0x698098d8,0x8b44f7af,0xffff5bb1,0x895cd7be,0x6b901122,0xfd987193,0xa679438e,0x49b40821,
        0xf61e2562,0xc040b340,0x265e5a51,0xe9b6c7aa,0xd62f105d,0x02441453,0xd8a1e681,0xe7d3fbc8,
        0x21e1cde6,0xc33707d6,0xf4d50d87,0x455a14ed,0xa9e3e905,0xfcefa3f8,0x676f02d9,0x8d2a4c8a,
        0xfffa3942,0x8771f681,0x6d9d6122,0xfde5380c,0xa4beea44,0x4bdecfa9,0xf6bb4b60,0xbebfbc70,
        0x289b7ec6,0xeaa127fa,0xd4ef3085,0x04881d05,0xd9d4d039,0xe6db99e5,0x1fa27cf8,0xc4ac5665,
        0xf4292244,0x432aff97,0xab9423a7,0xfc93a039,0x655b59c3,0x8f0ccc92,0xffeff47d,0x85845dd1,
        0x6fa87e4f,0xfe2ce6e0,0xa3014314,0x4e0811a1,0xf7537e82,0xbd3af235,0x2ad7d2bb,0xeb86d391}};
    constexpr std::array<unsigned, 16> shifts{{7,12,17,22,5,9,14,20,4,11,16,23,6,10,15,21}};
    std::vector<unsigned char> data(bytes.begin(), bytes.end());
    const auto bits = static_cast<std::uint64_t>(data.size()) * 8;
    data.push_back(0x80);
    while (data.size() % 64 != 56) data.push_back(0);
    for (unsigned i = 0; i < 8; ++i) data.push_back(static_cast<unsigned char>(bits >> (8 * i)));
    std::array<std::uint32_t, 4> hash{{0x67452301,0xefcdab89,0x98badcfe,0x10325476}};
    for (std::size_t offset = 0; offset < data.size(); offset += 64) {
        std::array<std::uint32_t, 16> words{};
        for (std::size_t j = 0; j < 16; ++j)
            for (unsigned k = 0; k < 4; ++k) words[j] |= std::uint32_t(data[offset + 4*j + k]) << (8*k);
        auto a = hash[0], b = hash[1], c = hash[2], d = hash[3];
        for (unsigned i = 0; i < 64; ++i) {
            std::uint32_t f; unsigned word;
            if (i < 16) { f = (b & c) | (~b & d); word = i; }
            else if (i < 32) { f = (d & b) | (~d & c); word = (5*i+1)%16; }
            else if (i < 48) { f = b ^ c ^ d; word = (3*i+5)%16; }
            else { f = c ^ (b | ~d); word = (7*i)%16; }
            const auto value = a + f + constants[i] + words[word];
            const auto shift = shifts[4*(i/16)+(i%4)];
            a = d; d = c; c = b; b += (value << shift) | (value >> (32-shift));
        }
        hash[0] += a; hash[1] += b; hash[2] += c; hash[3] += d;
    }
    const char *hex = "0123456789abcdef";
    std::string out;
    for (auto word : hash) for (unsigned i = 0; i < 4; ++i) {
        const auto byte = (word >> (8*i)) & 255; out += hex[byte >> 4]; out += hex[byte & 15];
    }
    return out;
}
std::string repr_value(const ExperimentDocument &document, const JsonNode &node, const std::string &path) {
    if (node.kind == JsonKind::String) return repr(node.string_value);
    if (node.kind != JsonKind::Object && node.kind != JsonKind::Array) return scalar(document, node, path);
    std::vector<std::string> entries;
    if (node.kind == JsonKind::Object) {
        for (const auto &[key, value] : node.object_value)
            entries.push_back(repr(key) + ": " + repr_value(document, value, path + "/" + pointer(key)));
        return "{" + document_detail::join(entries, ", ") + "}";
    }
    for (std::size_t i = 0; i < node.array_value.size(); ++i)
        entries.push_back(repr_value(document, node.array_value[i], path + "/" + std::to_string(i)));
    return "[" + document_detail::join(entries, ", ") + "]";
}
namespace {
std::string quoted(const std::string &value, bool ascii) {
    if (ascii) return quote(value);
    (void)document_detail::codepoints(value); // reject malformed UTF-8
    std::string out = "\"";
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c < 32) {
            switch (c) {
            case '\n': out += "\\n"; break; case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break; case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            default: out += "\\u00"; out += "0123456789abcdef"[c >> 4]; out += "0123456789abcdef"[c & 15];
            }
        } else out += static_cast<char>(c);
    }
    return out + '"';
}
std::string dump(const ExperimentDocument &d, const JsonNode &n, const std::string &path,
                 int indent, bool ascii, int depth) {
    if (n.kind == JsonKind::Null) return "null";
    if (n.kind == JsonKind::Bool) return n.bool_value ? "true" : "false";
    if (n.kind == JsonKind::String) return quoted(n.string_value, ascii);
    if (n.kind == JsonKind::Number) return scalar(d, n, path);
    const bool object = n.kind == JsonKind::Object;
    const auto size = object ? n.object_value.size() : n.array_value.size();
    const bool pretty = indent >= 0;
    std::string out = object ? "{" : "[";
    for (std::size_t i = 0; i < size; ++i) {
        if (i) out += pretty ? "," : ", ";
        if (pretty) out += "\n" + std::string((depth + 1) * indent, ' ');
        const auto key = object ? n.object_value[i].first : std::to_string(i);
        if (object) out += quoted(key, ascii) + ": ";
        out += dump(d, object ? n.object_value[i].second : n.array_value[i], path + "/" + pointer(key), indent, ascii, depth + 1);
    }
    if (pretty && size) out += "\n" + std::string(depth * indent, ' ');
    return out + (object ? "}" : "]");
}
} // namespace
} // namespace schgen::experiment_detail
namespace schgen {
std::string render_experiment_json(const ExperimentDocument &d, int indent, bool ascii) {
    if (indent < -1 || indent > 16) throw std::invalid_argument("experiment: invalid JSON indentation");
    return experiment_detail::dump(d, d.data, "", indent, ascii, 0);
}
ExperimentDocument experiment_either_side_spec(const ExperimentDocument &raw, const std::vector<std::string> &sheets) {
    using namespace experiment_detail;
    auto copy = raw;
    auto &interior = field(copy.data, "interior"); kind(interior, JsonKind::Object);
    for (const auto &sheet : sheets) {
        auto found = std::find_if(interior.object_value.begin(), interior.object_value.end(), [&](const auto &entry) { return entry.first == sheet; });
        if (found == interior.object_value.end()) {
            interior.object_value.emplace_back(sheet, jo()); found = std::prev(interior.object_value.end());
        }
        kind(found->second, JsonKind::Object); set(found->second, "layer", j("either"));
        erase_metadata(copy, "/interior/" + pointer(sheet) + "/layer");
    }
    return copy;
}
double parse_experiment_ordinary_via(const std::string &argument) {
    static const std::regex literal(R"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)");
    if (!std::regex_match(argument, literal)) throw std::invalid_argument("experiment: ordinary via cost must be a finite nonnegative decimal literal");
    double value;
    try { value = std::stod(argument); } catch (const std::exception &) {
        throw std::invalid_argument("experiment: ordinary via cost out of range");
    }
    FloorplanExperiment experiment; experiment.ordinary_via_mm = value;
    validate_floorplan_experiment(experiment); return value;
}
} // namespace schgen
