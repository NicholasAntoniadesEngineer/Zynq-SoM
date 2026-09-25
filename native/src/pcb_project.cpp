#include "pcb_project_defaults.hpp"
#include <fstream>
#include <iterator>

namespace schgen {
using namespace pcb_emission;
namespace {
std::string pointer_token(const std::string &s) {
    std::string r;
    for (char c : s)
        r += c == '~' ? "~0" : c == '/' ? "~1" : std::string(1, c);
    return r;
}
std::string quote(const std::string &s) {
    static const char hex[] = "0123456789abcdef";
    std::string r = "\"";
    auto u16 = [&](unsigned n) {
        r += "\\u";
        for (int shift : {12, 8, 4, 0})
            r += hex[(n >> shift) & 15];
    };
    for (std::size_t i = 0; i < s.size();) {
        unsigned c = static_cast<unsigned char>(s[i++]);
        if (c == '"' || c == '\\') {
            r += '\\';
            r += static_cast<char>(c);
        } else if (c == '\b')
            r += "\\b";
        else if (c == '\f')
            r += "\\f";
        else if (c == '\n')
            r += "\\n";
        else if (c == '\r')
            r += "\\r";
        else if (c == '\t')
            r += "\\t";
        else if (c < 32 || c == 127)
            u16(c);
        else if (c < 128)
            r += static_cast<char>(c);
        else {
            int count = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc0 ? 1 : 0;
            if (!count || i + count > s.size())
                throw PcbEmissionError("invalid UTF-8 in project metadata");
            unsigned cp = c & ((1u << (6 - count)) - 1);
            for (int k = 0; k < count; ++k) {
                unsigned b = static_cast<unsigned char>(s[i++]);
                if ((b & 0xc0) != 0x80)
                    throw PcbEmissionError("invalid UTF-8 in project metadata");
                cp = (cp << 6) | (b & 63);
            }
            if (cp > 0x10ffff)
                throw PcbEmissionError("invalid Unicode in project metadata");
            if (cp <= 0xffff)
                u16(cp);
            else {
                cp -= 0x10000;
                u16(0xd800 + (cp >> 10));
                u16(0xdc00 + (cp & 1023));
            }
        }
    }
    return r + '"';
}
std::string dump(const JsonNode &n, const PcbProjectDocument &document,
                 const std::string &path = "", int level = 0) {
    switch (n.kind) {
    case JsonKind::Null:
        return "null";
    case JsonKind::Bool:
        return n.bool_value ? "true" : "false";
    case JsonKind::String:
        return quote(n.string_value);
    case JsonKind::Number: {
        double x = jnum(n);
        if (document.float_paths.count(path) || std::trunc(x) != x)
            return pyfloat(x);
        auto original = document.integer_tokens.find(path);
        if (original != document.integer_tokens.end() && std::stod(original->second) == x)
            return x == 0 ? "0" : original->second;
        return x == 0 ? "0" : fmt(x, 0, true);
    }
    case JsonKind::Array: {
        if (n.array_value.empty())
            return "[]";
        std::string s = "[\n";
        for (std::size_t i = 0; i < n.array_value.size(); ++i) {
            if (i)
                s += ",\n";
            s += std::string((level + 1) * 2, ' ') +
                 dump(n.array_value[i], document, path + "/" + std::to_string(i), level + 1);
        }
        return s + "\n" + std::string(level * 2, ' ') + "]";
    }
    case JsonKind::Object: {
        if (n.object_value.empty())
            return "{}";
        std::string s = "{\n";
        for (std::size_t i = 0; i < n.object_value.size(); ++i) {
            if (i)
                s += ",\n";
            const auto &[key, val] = n.object_value[i];
            s += std::string((level + 1) * 2, ' ') + quote(key) + ": " +
                 dump(val, document, path + "/" + pointer_token(key), level + 1);
        }
        return s + "\n" + std::string(level * 2, ' ') + "}";
    }
    }
    throw PcbEmissionError("invalid JSON kind");
}
void erase_paths(PcbProjectDocument &document, const std::string &prefix) {
    auto &paths = document.float_paths;
    for (auto i = paths.begin(); i != paths.end();)
        if (*i == prefix || starts(*i, prefix + "/"))
            i = paths.erase(i);
        else
            ++i;
    auto &integers = document.integer_tokens;
    for (auto i = integers.begin(); i != integers.end();)
        if (i->first == prefix || starts(i->first, prefix + "/"))
            i = integers.erase(i);
        else
            ++i;
}
void add_paths(std::set<std::string> &paths, const std::set<std::string> &source,
               const std::string &prefix) {
    for (const auto &p : source)
        paths.insert(prefix + p);
}
JsonNode class_dict(const std::string &name, const std::optional<DifferentialGeometry> &geo,
                    bool power, bool def, const PcbEmitPolicy &p) {
    double track = p.default_track, clear = p.default_clearance, width = .2, gap = .2;
    if (power) {
        track = p.power_track;
        clear = p.power_clearance;
    } else if (geo) {
        track = width = geo->width_mm;
        gap = geo->gap_mm;
    }
    return jo({{"bus_width", j(12)},
               {"clearance", j(py_round(clear, 4))},
               {"diff_pair_gap", j(py_round(gap, 4))},
               {"diff_pair_via_gap", j(.25)},
               {"diff_pair_width", j(py_round(width, 4))},
               {"line_style", j(0)},
               {"microvia_diameter", j(.3)},
               {"microvia_drill", j(.1)},
               {"name", j(name)},
               {"pcb_color", j(std::string("rgba(0, 0, 0, 0.000)"))},
               {"priority", j(def     ? 2147483647
                              : power ? 10
                                      : 5)},
               {"schematic_color", j(std::string("rgba(0, 0, 0, 0.000)"))},
               {"track_width", j(py_round(track, 4))},
               {"tuning_profile", j(std::string())},
               {"via_diameter", j(.6)},
               {"via_drill", j(.3)},
               {"wire_width", j(6)}});
}
} // namespace
PcbProjectDocument read_pcb_project(const std::filesystem::path &path) {
    PcbProjectDocument out;
    out.data = parse_json_file(path.string());
    kind(out.data, JsonKind::Object);
    // Parsing/validation stays in the shared parser. A lexical pass records
    // number tokens; JSON tree preorder determines pointer paths. Integer
    // lexemes must survive the shared double-only tree without precision loss.
    std::ifstream stream(path, std::ios::binary);
    if (!stream)
        throw PcbEmissionError("cannot read project " + path.string());
    std::string text{std::istreambuf_iterator<char>(stream), {}};
    std::vector<std::string> numbers;
    for (std::size_t i = 0; i < text.size();) {
        char c = text[i++];
        if (c == '"') {
            while (i < text.size()) {
                char next = text[i++];
                if (next == '\\') {
                    if (i < text.size())
                        ++i;
                } else if (next == '"')
                    break;
            }
        } else if (c == '-' || (c >= '0' && c <= '9')) {
            auto start = i - 1;
            while (i < text.size()) {
                char d = text[i];
                if ((d >= '0' && d <= '9') || d == '-' || d == '+' || d == '.' || d == 'e' ||
                    d == 'E')
                    ++i;
                else
                    break;
            }
            numbers.push_back(text.substr(start, i - start));
        }
    }
    std::size_t index = 0;
    std::function<void(const JsonNode &, const std::string &)> walk = [&](const JsonNode &n,
                                                                          const std::string &path) {
        if (n.kind == JsonKind::Number) {
            if (index >= numbers.size() || std::stod(numbers[index]) != n.number_value)
                throw PcbEmissionError("project changed during read");
            const auto &token = numbers[index++];
            if (token.find_first_of(".eE") != token.npos)
                out.float_paths.insert(path);
            else
                out.integer_tokens[path] = token;
        } else if (n.kind == JsonKind::Array) {
            for (std::size_t i = 0; i < n.array_value.size(); ++i)
                walk(n.array_value[i], path + "/" + std::to_string(i));
        } else if (n.kind == JsonKind::Object)
            for (const auto &[k, v] : n.object_value)
                walk(v, path + "/" + pointer_token(k));
    };
    walk(out.data, "");
    if (index != numbers.size())
        throw PcbEmissionError("project changed during read");
    return out;
}
std::string render_pcb_project(const PcbModel &m, const std::string &filename,
                               const PcbProjectDocument *existing, const PcbEmitPolicy &p) {
    PcbProjectDocument doc = existing ? *existing : PcbProjectDocument{jo(), {}, {}};
    kind(doc.data, JsonKind::Object);
    auto &d = doc.data;
    if (!object_field(d, "meta"))
        set(d, "meta", jo({{"filename", j(filename)}, {"version", j(3)}}));
    if (!object_field(d, "erc"))
        set(d, "erc",
            jo({{"rule_severities", jo({{"pin_not_driven", j(std::string("warning"))}})}}));
    auto previous = object_field(d, "board");
    JsonNode board = previous ? *previous : jo();
    kind(board, JsonKind::Object);
    auto settings = design_settings(p);
    set(board, "design_settings", std::move(settings.data));
    set(d, "board", std::move(board));
    erase_paths(doc, "/board/design_settings");
    add_paths(doc.float_paths, settings.float_paths, "/board/design_settings");
    JsonNode classes = ja({class_dict("Default", std::nullopt, false, true, p)});
    for (const auto &[name, geo] : m.classes)
        classes.array_value.push_back(class_dict(name, geo, name == p.power_class, false, p));
    JsonNode patterns = ja();
    for (const auto &[net, cls] : m.netclass_of)
        patterns.array_value.push_back(jo({{"netclass", j(cls)}, {"pattern", j(net)}}));
    set(d, "net_settings",
        jo({{"classes", std::move(classes)},
            {"meta", jo({{"version", j(4)}})},
            {"net_colors", JsonNode{}},
            {"netclass_assignments", JsonNode{}},
            {"netclass_patterns", std::move(patterns)}}));
    erase_paths(doc, "/net_settings");
    for (std::size_t i = 0; i <= m.classes.size(); ++i)
        for (auto key :
             {"clearance", "diff_pair_gap", "diff_pair_via_gap", "diff_pair_width",
              "microvia_diameter", "microvia_drill", "track_width", "via_diameter", "via_drill"})
            doc.float_paths.insert("/net_settings/classes/" + std::to_string(i) + "/" + key);
    if (!object_field(d, "pcbnew"))
        set(d, "pcbnew", jo({{"last_paths", jo()}, {"page_layout_descr_file", j(std::string())}}));
    return dump(d, doc) + "\n";
}
void write_pcb_project(const PcbModel &m, const std::filesystem::path &path,
                       const PcbEmitPolicy &p) {
    std::optional<PcbProjectDocument> prior;
    if (std::filesystem::exists(path))
        prior = read_pcb_project(path);
    publish(path, render_pcb_project(m, path.filename().string(), prior ? &*prior : nullptr, p));
}
std::string render_pcb_design_rules(const PcbModel &m, const PcbEmitPolicy &p) {
    std::string s =
        "(version 1)\n\n# Generated by schgen/generate/pcb.py — board-level design rules for\n# "
        "the PCB foundation. Stackup: JLCPCB JLC04161H-7628 (4L 1.6mm).\n# Net classes + per-net "
        "assignment live in the .kicad_pro net_settings;\n# these rules pin the geometry KiCad's "
        "DRC enforces.\n\n(rule \"minimum_clearance\"\n  (constraint clearance (min " +
        pyfloat(p.default_clearance) +
        "mm))\n)\n\n(rule \"minimum_track\"\n  (constraint track_width (min " +
        pyfloat(p.default_track) +
        "mm))\n)\n\n(rule \"POWER_track\"\n  (condition \"A.NetClass == 'POWER'\")\n  (constraint "
        "track_width (min " +
        pyfloat(p.power_track) + "mm) (opt " + pyfloat(p.power_track) + "mm))\n)\n";
    for (const auto &[name, g] : m.classes)
        if (g) {
            auto w = pyfloat(g->width_mm), gap = pyfloat(g->gap_mm);
            s += "\n(rule \"" + name + "_geometry\"\n  (condition \"A.NetClass == '" + name +
                 "'\")\n  (constraint track_width (min " + w + "mm) (opt " + w + "mm) (max " + w +
                 "mm))\n  (constraint diff_pair_gap (min " + gap + "mm) (opt " + gap + "mm))\n)\n";
        }
    return s;
}
void write_pcb_design_rules(const PcbModel &m, const std::filesystem::path &path,
                            const PcbEmitPolicy &p) {
    publish(path, render_pcb_design_rules(m, p));
}
} // namespace schgen
