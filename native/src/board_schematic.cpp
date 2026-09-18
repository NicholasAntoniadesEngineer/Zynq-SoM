#include "schgen/board_schematic.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/pack.hpp"
#include "schgen/quantize.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <future>
#include <iterator>
#include <limits>
#include <map>
#include <regex>
#include <set>
#include <thread>
#include <unistd.h>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen {
namespace {
namespace fs = std::filesystem;
using Pin = std::pair<std::string, std::string>;
using Point = std::pair<double, double>;
constexpr std::int64_t stride = 1000;
constexpr double gap = 12.7, pitch = 2.54, stub = 12.7, top = 25.4;
bool starts(const std::string& s, const std::string& p) { return s.rfind(p, 0) == 0; }
bool rail(const CircuitNetIr& n) { return n.net_class == "power" || n.net_class == "ground"; }
std::string repr(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (const unsigned char ch : s) {
        if (ch == quote || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) { out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15]; }
        else out += static_cast<char>(ch);
    }
    return out + quote;
}
template<class Range> std::string list_repr(const Range& values) {
    std::string out = "[";
    for (const auto& s : values) { if (out.size() > 1) out += ", "; out += repr(s); }
    return out + "]";
}
std::string join(const std::vector<std::string>& xs, const std::string& separator) {
    std::string out;
    for (std::size_t i = 0; i < xs.size(); ++i) { if (i) out += separator; out += xs[i]; }
    return out;
}
std::string norm(const std::string& s) {
    const auto first = s.find_first_not_of('/'); return first == std::string::npos ? "" : s.substr(first);
}
const CircuitNetIr* find_net(const CircuitSheetIr& c, const std::string& name) {
    const auto it = std::find_if(c.nets.begin(), c.nets.end(), [&](const auto& n) { return n.name == name; });
    return it == c.nets.end() ? nullptr : &*it;
}
void safe_leaf(const std::string& name, const std::string& kind) {
    if (name.empty() || name == "." || name == ".." || name.find_first_of("/\\") != std::string::npos ||
        std::any_of(name.begin(), name.end(), [](unsigned char ch) { return ch < 32 || ch == 127; }))
        throw BoardSchematicError("invalid " + kind + " name " + repr(name));
}
void safe_subdir(const std::string& name) {
    if (name.empty()) return;
    if (fs::path(name).is_absolute() || name.find('\\') != std::string::npos)
        throw BoardSchematicError("invalid board sheet subdirectory " + repr(name));
    for (const auto& part : fs::path(name)) safe_leaf(part.string(), "sheet subdirectory");
}
void write(const fs::path& path, const std::string& value) {
    write_atomic_file(path.string(), {value.begin(), value.end()});
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "schgen_board_check_XXXXXX").string();
        if (!::mkdtemp(pattern.data())) throw BoardSchematicError("cannot create board scratch directory: " + std::string(std::strerror(errno)));
        path = pattern;
    }
    ~Scratch() { std::error_code ignored; fs::remove_all(path, ignored); }
    Scratch(const Scratch&) = delete;
    Scratch& operator=(const Scratch&) = delete;
};
double width(const std::string& s) { return text_wh(s, 1.27, default_engine_config.char_w, 1.6).first; }
double up(double v) { return gceil(v, symbol_grid); }
SchematicSymbolResolver resolver(SymbolLibrary& lib) {
    return [&lib](const std::string& id) -> const SymbolDef& { return lib.get(id); };
}

// json.dumps(indent=2, ensure_ascii=True), preserving insertion order. JsonNode
// stores numbers as doubles; integral values use integer spelling (as project
// config integers do). Nonfinite numbers cannot enter a KiCad project file.
std::string json_string(const std::string& s) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    const auto unit = [&](std::uint32_t c) { out += "\\u"; for (int k = 12; k >= 0; k -= 4) out += hex[(c >> k) & 15]; };
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
            const int count = first >= 0xf0 ? 3 : first >= 0xe0 ? 2 : 1;
            if (first < 0xc2 || first > 0xf4) throw BoardSchematicError("invalid UTF-8 in board project JSON");
            std::uint32_t c = first & (count == 3 ? 7 : count == 2 ? 15 : 31);
            for (int k = 0; k < count; ++k) {
                if (i == s.size() || (static_cast<unsigned char>(s[i]) & 0xc0) != 0x80)
                    throw BoardSchematicError("invalid UTF-8 in board project JSON");
                c = (c << 6) | (static_cast<unsigned char>(s[i++]) & 63);
            }
            if ((count == 1 && c < 0x80) || (count == 2 && c < 0x800) ||
                (count == 3 && c < 0x10000) || c > 0x10ffff)
                throw BoardSchematicError("invalid UTF-8 in board project JSON");
            if (c > 0xffff) { c -= 0x10000; unit(0xd800 + (c >> 10)); unit(0xdc00 + (c & 1023)); }
            else unit(c);
        }
    }
    return out + '"';
}
std::string dump(const JsonNode& j, std::size_t indent = 0) {
    if (j.kind == JsonKind::Null) return "null";
    if (j.kind == JsonKind::Bool) return j.bool_value ? "true" : "false";
    if (j.kind == JsonKind::String) return json_string(j.string_value);
    if (j.kind == JsonKind::Number) {
        if (!std::isfinite(j.number_value)) throw BoardSchematicError("nonfinite board project JSON number");
        char buffer[128];
        const auto result = std::to_chars(buffer, buffer + sizeof(buffer), j.number_value);
        if (result.ec != std::errc{}) throw BoardSchematicError("cannot format board project number");
        return {buffer, result.ptr};
    }
    const bool object = j.kind == JsonKind::Object;
    const std::size_t count = object ? j.object_value.size() : j.array_value.size();
    if (!count) return object ? "{}" : "[]";
    std::string out = object ? "{\n" : "[\n";
    for (std::size_t i = 0; i < count; ++i) {
        out += std::string(indent + 2, ' ');
        if (object) out += json_string(j.object_value[i].first) + ": " + dump(j.object_value[i].second, indent + 2);
        else out += dump(j.array_value[i], indent + 2);
        out += i + 1 == count ? "\n" : ",\n";
    }
    return out + std::string(indent, ' ') + (object ? '}' : ']');
}
JsonNode object(std::vector<std::pair<std::string, JsonNode>> values = {}) { JsonNode n; n.kind = JsonKind::Object; n.object_value = std::move(values); return n; }
JsonNode string(const std::string& s) { JsonNode n; n.kind = JsonKind::String; n.string_value = s; return n; }
JsonNode number(double v) { JsonNode n; n.kind = JsonKind::Number; n.number_value = v; return n; }
void put(JsonNode& j, const std::string& key, JsonNode value) {
    for (auto& [k, old] : j.object_value) if (k == key) { old = std::move(value); return; }
    j.object_value.emplace_back(key, std::move(value));
}
}  // namespace

std::string board_renamed_ref(const std::string& ref, std::int64_t band, const std::string& sheet) {
    static const std::regex pattern("^(#?[A-Za-z_]+?)0*([0-9]+)$");
    std::smatch match;
    if (!std::regex_match(ref, match, pattern)) throw BoardSchematicError("cannot uniquify reference " + repr(ref));
    std::string digits = match[2].str();
    const auto nonzero = digits.find_first_not_of('0'); digits = nonzero == std::string::npos ? "0" : digits.substr(nonzero);
    const std::string prefix = match[1].str();
    if (digits.size() > 3) throw BoardSchematicError("uniquify: reference " + repr(ref) +
        (sheet.empty() ? "" : " on sheet " + repr(sheet)) + " has number " + digits + " >= 1000 (or a sheet has 1000+ '" +
        prefix + "' parts) — the index*1000+num stride would collide into sheet " +
        (band == std::numeric_limits<std::int64_t>::max() ? "9223372036854775808" : std::to_string(band + 1)) +
        "'s band; widen _UNIQ_STRIDE before this many parts exist");
    const auto num = std::stoll(digits);
    if (band < 0 || band > (std::numeric_limits<std::int64_t>::max() - num) / stride)
        throw BoardSchematicError("invalid board reference band " + std::to_string(band));
    return prefix + std::to_string(band * stride + num);
}

SchematicDesign uniquify_board_design(const SchematicDesign& source, std::int64_t band) {
    SchematicDesign d = source;
    std::map<std::string, std::string> refs;
    std::set<std::string> used;
    for (auto& p : d.circuit.parts) {
        auto renamed = board_renamed_ref(p.ref, band, d.circuit.name);
        if (!refs.emplace(p.ref, renamed).second || !used.insert(renamed).second)
            throw BoardSchematicError("uniquify: colliding reference " + repr(p.ref) + " on sheet " + repr(d.circuit.name));
        p.ref = std::move(renamed);
    }
    const auto mapped = [&](const std::string& ref) -> const std::string& {
        const auto it = refs.find(ref);
        if (it == refs.end()) throw BoardSchematicError("uniquify: unknown reference " + repr(ref) + " on sheet " + repr(d.circuit.name));
        return it->second;
    };
    for (auto& net : d.circuit.nets) for (auto& pin : net.pins) pin.ref = mapped(pin.ref);
    for (auto& pin : d.circuit.nc) pin.ref = mapped(pin.ref);
    for (auto& p : d.parts) p.ref = mapped(p.ref);
    for (auto& p : d.powers) {
        p.ref = board_renamed_ref(p.ref, band, d.circuit.name);
        if (!used.insert(p.ref).second) throw BoardSchematicError("uniquify: colliding power reference " + repr(p.ref));
    }
    // Python leaves annotation/waiver keys unchanged: only electrically used
    // references and emitted instance references are transformed.
    d.standalone = false;
    return d;
}

void strip_duplicate_board_flags(std::vector<SchematicDesign>& designs, SymbolLibrary& library) {
    std::set<std::string> driven;
    for (const auto& d : designs) {
        std::map<Pin, std::string> types;
        for (const auto& p : d.parts) for (const auto& q : library.get(p.lib_id).pins) types[{p.ref, q.number}] = q.etype;
        for (const auto& n : d.circuit.nets) if (n.net_class != "signal")
            for (const auto& p : n.pins) if (types[{p.ref, p.pin}] == "power_out") { driven.insert(n.name); break; }
    }
    std::set<std::pair<std::int64_t, std::string>> flagged;
    for (std::size_t sheet = 0; sheet < designs.size(); ++sheet) {
        auto& d = designs[sheet];
        std::set<Point> pins, labels, junctions;
        for (const auto& p : d.parts) for (const auto& q : library.get(p.lib_id).pins) pins.insert(pin_page_position(q, p.x, p.y, p.rotation));
        for (const auto& p : d.hlabels) labels.emplace(p.x, p.y);
        for (const auto& p : d.llabels) labels.emplace(p.x, p.y);
        for (const auto& p : d.junctions) junctions.emplace(p.x, p.y);
        // Stable IDs avoid invalidating the original Python list-comprehension
        // traversal when earlier flags, anchors and wires are removed.
        std::vector<bool> removed_power(d.powers.size()), removed_wire(d.wires.size());
        for (std::size_t fi = 0; fi < d.powers.size(); ++fi) {
            const auto& flag = d.powers[fi];
            if (removed_power[fi] || flag.lib_id != "power:PWR_FLAG") continue;
            const auto& name = flag.net_name(); const auto* n = find_net(d.circuit, name);
            const bool local = n && n->net_class == "signal";
            const auto scope = std::make_pair(local ? static_cast<std::int64_t>(sheet) : -1, name);
            if ((local || !driven.count(name)) && flagged.insert(scope).second) continue;
            const Point pos{flag.x, flag.y}; std::vector<std::size_t> touching;
            for (std::size_t i = 0; i < d.wires.size(); ++i) if (!removed_wire[i]) {
                const auto& w = d.wires[i]; if (Point{w.x0, w.y0} == pos || Point{w.x1, w.y1} == pos) touching.push_back(i);
            }
            if (touching.size() != 1) continue;
            const auto wi = touching.front(); const auto& w = d.wires[wi];
            const Point far = Point{w.x0, w.y0} == pos ? Point{w.x1, w.y1} : Point{w.x0, w.y0};
            std::vector<std::size_t> anchors;
            for (std::size_t i = 0; i < d.powers.size(); ++i) if (i != fi && !removed_power[i]) {
                const auto& p = d.powers[i]; if (Point{p.x, p.y} == far && p.net_name() == name) anchors.push_back(i);
            }
            bool others = false;
            for (std::size_t i = 0; i < d.wires.size(); ++i) if (i != wi && !removed_wire[i]) {
                const auto& v = d.wires[i]; const Point a{v.x0, v.y0}, b{v.x1, v.y1};
                if (a == pos || a == far || b == pos || b == far) { others = true; break; }
            }
            if (anchors.size() != 1 || others || pins.count(pos) || pins.count(far) || labels.count(pos) ||
                labels.count(far) || junctions.count(pos) || junctions.count(far)) continue;
            removed_power[fi] = removed_power[anchors.front()] = true; removed_wire[wi] = true;
        }
        std::size_t i = 0;
        d.powers.erase(std::remove_if(d.powers.begin(), d.powers.end(), [&](const auto&) { return removed_power[i++]; }), d.powers.end());
        i = 0;
        d.wires.erase(std::remove_if(d.wires.begin(), d.wires.end(), [&](const auto&) { return removed_wire[i++]; }), d.wires.end());
    }
}

BoardHierarchy make_board_hierarchy(const std::vector<BoardSheetDesign>& inputs, SymbolLibrary& lib,
                                   const std::string& root_name, const std::string& subdir) {
    safe_leaf(root_name, "board root"); safe_subdir(subdir);
    if (inputs.empty()) throw BoardSchematicError("cannot build an empty board hierarchy");
    BoardHierarchy out; out.root_uuid = schematic_stable_uuid({root_name, "root"});
    out.root.circuit.schema = "schgen.circuit/1"; out.root.circuit.name = root_name;
    out.root.circuit.title = "carrier board root";
    std::vector<SchematicDesign> designs; std::set<std::string> names, all_refs;
    std::set<std::int64_t> bands;
    for (const auto& in : inputs) {
        const auto& name = in.design.circuit.name; safe_leaf(name, "sheet");
        (void)board_renamed_ref("X0", in.reference_band, name);
        if (!names.insert(name).second) throw BoardSchematicError("duplicate board sheet " + repr(name));
        if (subdir.empty() && name == root_name) throw BoardSchematicError("board root collides with child sheet " + repr(name));
        if (!bands.insert(in.reference_band).second) throw BoardSchematicError("duplicate board reference band " + std::to_string(in.reference_band));
        designs.push_back(uniquify_board_design(in.design, in.reference_band));
        for (const auto& p : designs.back().circuit.parts) if (!all_refs.insert(p.ref).second)
            throw BoardSchematicError("duplicate board reference " + repr(p.ref));
    }
    strip_duplicate_board_flags(designs, lib);
    struct Entry { std::string name, uuid; std::vector<std::string> ports; std::map<std::string, std::string> shapes; double w, h; };
    std::vector<Entry> entries;
    for (auto& d : designs) {
        Entry e; e.name = d.circuit.name; e.uuid = schematic_stable_uuid({root_name, "sheet-symbol", e.name});
        for (const auto& n : d.circuit.nets) if (n.net_class == "port") e.ports.push_back(n.name);
        std::sort(e.ports.begin(), e.ports.end());
        for (const auto& h : d.hlabels) e.shapes[h.name] = h.shape;
        double max_width = e.ports.empty() ? 10.0 : 0.0;
        for (const auto& p : e.ports) max_width = std::max(max_width, width(p));
        e.w = up(max_width + 12.7); e.h = pitch * (e.ports.size() + 1);
        out.sheets.push_back({e.name, std::move(d), e.uuid}); entries.push_back(std::move(e));
    }
    struct Paper { const char* name; double w, h; };
    std::vector<std::pair<double, std::vector<std::size_t>>> geometry;
    bool fits = false;
    for (const auto page : {Paper{"A3",420,297}, Paper{"A2",594,420}, Paper{"A1",841,594}}) {
        const double height = page.h - top - 25.4;
        if (std::any_of(entries.begin(), entries.end(), [&](const auto& e) { return e.h > height; })) continue;
        std::vector<std::vector<std::size_t>> cols; std::vector<std::size_t> col; double used_h = 0;
        for (std::size_t i = 0; i < entries.size(); ++i) {
            if (!col.empty() && used_h + entries[i].h > height) { cols.push_back(col); col.clear(); used_h = 0; }
            col.push_back(i); used_h += entries[i].h + gap;
        }
        if (!col.empty()) cols.push_back(col);
        double right = 10.16; geometry.clear();
        for (const auto& c : cols) {
            double label_width = 0, sheet_width = 0; bool any_port = false;
            for (const auto i : c) { sheet_width = std::max(sheet_width, entries[i].w);
                for (const auto& p : entries[i].ports) { label_width = std::max(label_width, width(p)); any_port = true; } }
            if (!any_port) label_width = 10.0;
            const double x = up(right + label_width + stub);
            geometry.emplace_back(x, c); right = x + sheet_width + gap;
        }
        if (right <= page.w - 10.16) { out.root.paper = page.name; fits = true; break; }
    }
    if (!fits) throw BoardSchematicError("board hierarchy exceeds A1 sheet capacity");
    for (const auto& [x, col] : geometry) {
        double y = top;
        for (const auto i : col) {
            const auto& e = entries[i]; SchematicSheetSymbol sym;
            sym.name = e.name; sym.file = (subdir.empty() ? "" : subdir + "/") + e.name + ".kicad_sch";
            sym.x = x; sym.y = y; sym.w = e.w; sym.h = e.h; sym.uuid = e.uuid; sym.page = std::to_string(i + 2);
            for (std::size_t k = 0; k < e.ports.size(); ++k) {
                const auto& name = e.ports[k]; const double py = y + pitch * (k + 1);
                const auto shape = e.shapes.find(name);
                sym.pins.push_back({name, x, py, 180, shape == e.shapes.end() ? "bidirectional" : shape->second});
                out.root.wires.push_back({x, py, x - stub, py}); out.root.hlabels.push_back({name, x - stub, py, 180, "bidirectional"});
            }
            out.root.sheets.push_back(std::move(sym)); y += e.h + gap;
        }
    }
    return out;
}

BoardNetlistResult check_board_netlist(const std::vector<BoardPlacedSheet>& sheets,
                                     const ExtractedNetlist& extracted, SymbolLibrary& lib) {
    // Preserve Python ordered-dict replacement for manually supplied duplicates.
    ExtractedNetlist nets; std::map<std::string, std::size_t> indices;
    for (const auto& e : extracted) { const auto [it, added] = indices.emplace(e.first, nets.size());
        if (added) nets.push_back(e); else nets[it->second].second = e.second; }
    std::map<Pin, std::string> actual;
    for (const auto& [name, pins] : nets) for (const auto& p : pins) if (!starts(p.ref, "#")) actual[{p.ref,p.pin}] = name;
    using Member = std::pair<std::string, CircuitPinRefIr>;
    using Table = std::map<std::string, std::vector<Member>>;
    Table ports, rails; std::set<std::string> has_input, deferred;
    for (const auto& sheet : sheets) {
        const auto& c = sheet.design.circuit;
        for (const auto& n : c.nets) {
            Table* target = nullptr;
            if (n.net_class == "port") {
                target = &ports;
                for (const auto& p : c.port_types) if (p.net == n.name && p.has_expect && !p.expect.empty()) deferred.insert(n.name);
                for (const auto& pr : n.pins) {
                    const auto part = std::find_if(c.parts.begin(), c.parts.end(), [&](const auto& p) { return p.ref == pr.ref; });
                    if (part == c.parts.end()) continue;
                    try { for (const auto& pin : lib.get(part->lib_id).pins)
                        if (pin.number == pr.pin && pin.etype == "input") { has_input.insert(n.name); break; }
                    } catch (const SymbolError&) { /* Legacy gate: completeness belongs to the build boundary. */ }
                }
            } else if (rail(n)) target = &rails;
            if (target) { auto& members = (*target)[n.name]; for (const auto& p : n.pins) members.emplace_back(sheet.name, p); }
        }
    }
    BoardNetlistResult out; out.lines = {"board netlist gate", std::string(60, '=')};
    for (const auto& kind_table : {std::make_pair("port", &ports), std::make_pair("rail", &rails)}) {
        for (const auto& [name, members] : *kind_table.second) {
            std::set<std::string> got, sheets_in; std::vector<std::string> missing;
            for (const auto& [sheet, p] : members) {
                sheets_in.insert(sheet); const auto it = actual.find({p.ref,p.pin});
                if (it == actual.end() || starts(it->second,"unconnected-")) missing.push_back(sheet + ":" + p.ref + "." + p.pin);
                else got.insert(norm(it->second));
            }
            const std::string prefix = std::string(kind_table.first) + " " + repr(name);
            if (!missing.empty() || got.size() != 1 || norm(*got.begin()) != name) {
                ++out.failures; out.lines.push_back("  FAIL " + prefix + ": extracted as " + list_repr(got) + " " +
                    (missing.empty() ? "" : "missing " + list_repr(missing)));
            } else {
                const std::vector<std::string> sorted(sheets_in.begin(), sheets_in.end());
                out.lines.push_back("  ok   " + prefix + ": 1 net, " + std::to_string(members.size()) + " pins across " +
                    std::to_string(sheets_in.size()) + " sheet(s) [" + join(sorted, ", ") + "]");
            }
        }
    }
    for (const auto& [name, members] : ports) if (has_input.count(name) && !deferred.count(name)) {
        std::set<std::string> sheets_in; for (const auto& m : members) sheets_in.insert(m.first);
        if (sheets_in.size() < 2) {
            ++out.failures; out.lines.push_back("  FAIL port " + repr(name) + ": undriven input — carries an input pin but resolves to a single sheet " +
                list_repr(sheets_in) + " with no cross-sheet driver (silent OPEN); drive it, add its peer sheet, or declare expect= on the port");
        }
    }
    out.lines.push_back("  (info) undriven-input PORT check: " + std::to_string(has_input.size()) + " input-bearing PORT nets examined (" +
        std::to_string(deferred.size()) + " expect-deferred)");
    out.lines.push_back(out.ok() ? "BOARD GATE: PASS — every linked net merged across sheets" : "BOARD GATE: FAIL (" + std::to_string(out.failures) + ")");
    return out;
}
std::string BoardNetlistResult::summary() const {
    auto copy = lines;
    if (erc_ran) copy.push_back("  (info) root ERC errors: " + (erc_exit_code == 0 ? std::string("0") : "present — see " + erc_report.string()));
    return join(copy, "\n");
}
std::string strip_board_report_timestamp(const std::string& report) {
    const auto lf = report.find('\n');
    static const std::regex timestamp("\\([^)]*?(Encoding [^)]*)\\)");
    return std::regex_replace(report.substr(0, lf), timestamp, "($1)") + "\n" +
        (lf == std::string::npos ? "" : report.substr(lf + 1));
}
BoardNetlistResult check_board_netlist(const std::vector<BoardPlacedSheet>& sheets, const fs::path& root_path,
    const fs::path& reports, SymbolLibrary& lib, const NetlistExtractOptions& options) {
    auto out = check_board_netlist(sheets, extract_netlist(root_path, options), lib);
    fs::create_directories(reports);
    const auto erc = run_kicad_erc(root_path, options);
    out.erc_ran = true; out.erc_exit_code = erc.exit_code; out.erc_report = reports / "board.erc.rpt";
    // Missing reports on a failing process still leave useful diagnostics, not
    // a stale report from an earlier board invocation.
    write(out.erc_report, strip_board_report_timestamp(erc.report.empty() ? erc.stderr_text : erc.report));
    write(reports / "board_gate.txt", out.summary() + "\n");
    return out;
}
std::string board_project_json(const JsonNode& existing, const std::string& root_name) {
    safe_leaf(root_name, "board root");
    if (existing.kind != JsonKind::Object) throw BoardSchematicError("board project JSON must be an object");
    auto result = existing;
    put(result, "meta", object({{"filename",string(root_name + ".kicad_pro")},{"version",number(3)}}));
    put(result, "erc", object({{"rule_severities",object({{"pin_not_driven",string("warning")}})}}));
    return dump(result) + "\n";
}
bool BoardSchematicResult::ok() const {
    return board.ok() && std::all_of(per_sheet.begin(), per_sheet.end(), [](const auto& s) { return s.ok(); });
}
BoardSchematicResult build_board_schematic(const std::vector<BoardSheetInput>& inputs, SymbolLibrary& library,
                                         const fs::path& outdir, const BoardSchematicOptions& options) {
    BoardSchematicResult out; std::vector<BoardSheetDesign> designs;
    for (const auto& in : inputs) {
        BoardSheetGateResult gate; gate.name = in.circuit.name;
        gate.electrical = check_circuit_electrical(in.circuit, library);
        // Bad pin tables cannot safely enter the placer; retain the full native
        // completeness diagnostics rather than failing inside geometry lookup.
        if (!gate.electrical.completeness_errors.empty()) throw BoardSchematicError(gate.electrical.completeness_summary());
        BoardPreparedSheet prepared;
        if (in.prepared) prepared = *in.prepared;
        else { auto page = place_and_route_schematic(in.circuit, library); prepared.placement = std::move(page.placement); prepared.routed = std::move(page.routed); }
        gate.visual = check_visual_geometry(schematic_route_geometry(prepared.placement, prepared.routed));
        const auto& p = prepared.placement; SchematicDesign d; d.circuit = in.circuit;
        d.parts = p.parts; d.powers = p.powers; d.hlabels = p.hlabels; d.llabels = p.llabels;
        d.no_connects = p.no_connects; d.paper = p.paper; apply_schematic_route(d, prepared.routed);
        designs.push_back({std::move(d), in.reference_band}); out.per_sheet.push_back(std::move(gate));
    }
    auto hierarchy = make_board_hierarchy(designs, library, options.root_name, options.sheet_subdir);
    const auto sheet_dir = outdir / options.sheet_subdir;
    fs::create_directories(sheet_dir); Scratch scratch;
    std::vector<fs::path> checks;
    for (std::size_t i = 0; i < hierarchy.sheets.size(); ++i) {
        const auto& sheet = hierarchy.sheets[i];
        const SchematicOptions child_options{"/" + hierarchy.root_uuid + "/" + sheet.symbol_uuid, options.root_name,
            schematic_stable_uuid({options.root_name, "sheet", sheet.name})};
        write(sheet_dir / (sheet.name + ".kicad_sch"), emit_schematic(sheet.design, resolver(library), child_options).text);
        auto verify = sheet.design; verify.standalone = true;
        const auto vpath = scratch.path / (sheet.name + ".uniqcheck.kicad_sch");
        write(vpath, emit_schematic(verify, resolver(library)).text);
        checks.push_back(vpath);
    }
    // All symbol resolution and emission above is sequential. Each worker only
    // reads immutable IR/files and uses the exporter's private process scratch.
    // Collect, don't short-circuit: Python executor.map waits for all submitted
    // tasks on exit, then exposes the first exception in input (not finish) order.
    std::vector<std::exception_ptr> exceptions(checks.size());
    std::atomic<std::size_t> next{0};
    const auto hardware = std::thread::hardware_concurrency();
    const std::size_t count = std::min(checks.size(), options.netlist_workers ? options.netlist_workers :
        std::min<std::size_t>(8, hardware ? hardware : 8));
    std::vector<std::future<void>> workers;
    for (std::size_t w = 0; w < count; ++w) workers.push_back(std::async(std::launch::async, [&] {
        for (;;) {
            const auto i = next.fetch_add(1);
            if (i >= checks.size()) return;
            try { out.per_sheet[i].netlist = check_netlist(hierarchy.sheets[i].design.circuit, checks[i], options.extraction); }
            catch (...) { exceptions[i] = std::current_exception(); }
        }
    }));
    for (auto& worker : workers) worker.get();
    for (const auto& error : exceptions) if (error) std::rethrow_exception(error);
    for (std::size_t i = 0; i < hierarchy.sheets.size(); ++i) {
        const auto& sheet = hierarchy.sheets[i];
        if (!out.per_sheet[i].netlist.ok) {
            const auto summary = out.per_sheet[i].netlist.summary(); const auto lf = summary.find('\n');
            std::string first = lf == std::string::npos ? "" : summary.substr(lf + 1, summary.find('\n', lf + 1) - lf - 1);
            const auto nonspace = first.find_first_not_of(" \t\r\n"); first = nonspace == std::string::npos ? "" : first.substr(nonspace);
            out.per_sheet_failures.push_back(sheet.name + (first.empty() ? "" : ": " + first));
        }
    }
    out.root_path = outdir / (options.root_name + ".kicad_sch");
    out.project_path = outdir / (options.root_name + ".kicad_pro");
    write(out.root_path, emit_schematic(hierarchy.root, resolver(library), {"",options.root_name,hierarchy.root_uuid}).text);
    const auto existing = fs::exists(out.project_path) ? parse_json_file(out.project_path.string()) : object();
    write(out.project_path, board_project_json(existing, options.root_name));
    out.board = check_board_netlist(hierarchy.sheets, out.root_path,
        options.reports_dir.empty() ? outdir : options.reports_dir, library, options.extraction);
    std::vector<std::string> messages;
    for (const auto& sheet : out.per_sheet) {
        if (!sheet.electrical.ok()) {
            messages.push_back("BOARD: electrical gate FAIL on " + sheet.name + ":");
            for (const auto& failure : sheet.electrical.completeness_errors) messages.push_back("  " + failure);
            for (const auto& failure : sheet.electrical.input_driver_errors) messages.push_back("  " + failure);
        }
        if (!sheet.visual.ok) {
            messages.push_back("BOARD: visual gate FAIL on " + sheet.name + ":");
            for (const auto& failure : sheet.visual.findings) messages.push_back("  " + failure);
        }
    }
    if (!out.per_sheet_failures.empty()) {
        messages.push_back("BOARD: per-sheet netlist gate FAIL on uniquified circuit:");
        for (const auto& failure : out.per_sheet_failures) messages.push_back("  " + failure);
    }
    messages.push_back("board: emitted " + out.root_path.string() + " (+" + std::to_string(hierarchy.sheets.size()) +
        " sub-sheets, root labels bind ports by canonical name)");
    messages.push_back(out.board.summary()); out.report = join(messages, "\n");
    return out;
}

}  // namespace schgen
