#include "pcb_escape_internal.hpp"

namespace schgen {
using namespace pcb_escape;
JsonNode PcbEscapePlanResult::json() const {
    auto ls = obj(), counts = obj(), prs = arr(), cors = obj();
    for (const auto &[ref, rows] : lanes) {
        auto a = arr();
        for (const auto &r : rows)
            a.array_value.push_back(
                obj({{"pad", str(r.pad)},
                     {"net", str(r.net)},
                     {"lane", num(r.lane)},
                     {"row", num(r.row)},
                     {"dir", str(r.direction)},
                     {"port", arr({num(r.port_x), num(r.port_y)})},
                     {"layer", str(r.layer)},
                     {"width", num(r.width)},
                     {"si_class", str(r.si_class)},
                     {"bus_group", r.bus_group ? str(*r.bus_group) : JsonNode{}}}));
        ls.object_value.emplace_back(ref, std::move(a));
    }
    for (const auto &[ref, n] : netted_counts)
        counts.object_value.emplace_back(ref, num(n));
    for (const auto &r : pairs)
        prs.array_value.push_back(obj({{"base", str(r.base)},
                                       {"conn", str(r.conn)},
                                       {"halves", strings(r.halves)},
                                       {"si_class", str(r.si_class)},
                                       {"same_row", boolean(r.same_row)},
                                       {"delta_lane", num(r.delta_lane)},
                                       {"convergence", str(r.convergence)}}));
    for (const auto &[key, c] : corridors)
        cors.object_value.emplace_back(key,
                                       obj({{"rect", box(c.rect)}, {"purpose", str(c.purpose)}}));
    return obj(
        {{"schema", str(schema)},
         {"lanes", std::move(ls)},
         {"netted_counts", std::move(counts)},
         {"pairs", std::move(prs)},
         {"genuine_pairs", strings(genuine_pairs)},
         {"t1_constraints", obj({{"corridors", std::move(cors)}, {"consumer", str(consumer)}})},
         {"content_key", str(content_key)}});
}
JsonNode PcbEscapeMetadata::json() const {
    auto ts = obj(), cs = obj(), vs = obj(), led = arr(), coex = arr(), via_ladder = arr();
    for (const auto &[dia, drill] : ladder())
        via_ladder.array_value.push_back(arr({num(dia), num(drill)}));
    for (const auto &[key, c] : triage)
        ts.object_value.emplace_back(key, obj({{"net", str(c.net)},
                                               {"function", str(c.function)},
                                               {"class", str(c.klass)},
                                               {"basis", str(c.basis)}}));
    for (const auto &[ref, per] : coverage_mm) {
        auto c = obj();
        for (const auto &[pad, d] : per)
            c.object_value.emplace_back(pad, num(d));
        cs.object_value.emplace_back(ref, std::move(c));
    }
    for (const auto &[ref, n] : vias)
        vs.object_value.emplace_back(ref, num(n));
    for (const auto &r : ledger) {
        auto e = obj({{"conn", str(r.conn)}, {"kind", str(r.kind)}});
        if (r.kind == "seat")
            e.object_value.insert(e.object_value.end(), {{"members", strings(r.members)},
                                                         {"u", num(r.u)},
                                                         {"v", num(r.v)},
                                                         {"dia", num(r.dia)},
                                                         {"drill", num(r.drill)},
                                                         {"worst_cover_mm", num(r.worst)},
                                                         {"depth", num(r.depth)}});
        else if (r.kind == "split_u")
            e.object_value.insert(
                e.object_value.end(),
                {{"at", num(r.at)}, {"members", strings(r.members)}, {"depth", num(r.depth)}});
        else if (r.kind == "split_row")
            e.object_value.insert(e.object_value.end(),
                                  {{"members", strings(r.members)}, {"depth", num(r.depth)}});
        else if (r.kind == "redundant_via")
            e.object_value.insert(e.object_value.end(), {{"u", num(r.u)}, {"v", num(r.v)}});
        else
            throw PcbEscapeError("unknown escape ledger kind " + r.kind);
        led.array_value.push_back(std::move(e));
    }
    for (const auto &c : coexistence)
        coex.array_value.push_back(obj({{"conn", str(c.conn)},
                                        {"ref", str(c.ref)},
                                        {"sheet", str(c.sheet)},
                                        {"verdict", str(c.verdict)},
                                        {"basis", str(c.basis)}}));
    return obj(
        {{"version", str("escape/v1")},
         {"constants",
          obj({{"R_CONSTRUCT", num(radius)},
               {"VIA_LADDER", std::move(via_ladder)},
               {"LATTICE_MM", num(lattice)},
               {"CLR", obj({{"margin_over_netclass_rule", num(.10)},
                            {"hole_foreign", num(.30)},
                            {"hole_hole", num(hole_hole)},
                            {"hole_samenet_pad", num(.10)},
                            {"track_foreign", num(.15)},
                            {"edge", num(.30)}})},
               {"widths",
                obj({{"spine", num(.30)}, {"stub_pair", num(.30)}, {"stub_single", num(.25)}})},
               {"zone_grow", num(2.)}})},
         {"v1_verdict", str(v1.summary())},
         {"v1_scalars",
          obj({{"n_pairs", num(v1.n_pairs)},
               {"n_pair_contacts", num(v1.n_pair_contacts)},
               {"n_fail", num(v1.n_fail())},
               {"worst_distance", v1.worst_distance ? num(*v1.worst_distance) : JsonNode{}}})},
         {"triage", std::move(ts)},
         {"coverage_mm", std::move(cs)},
         {"worst_cover_mm", num(worst_cover_mm)},
         {"vias", std::move(vs)},
         {"ledger", std::move(led)},
         {"escape_region", box(escape_region)},
         {"plane", obj({{"layer", str("In1.Cu")},
                        {"rect", box(plane)},
                        {"source", str("GAP1 embed._gnd_plane_zone (canonical; T2 emits no zone)")},
                        {"voids_checked", strings(voids_checked)}})},
         {"coexistence", std::move(coex)},
         {"som_interface_sha256", str(som_interface_sha256)}});
}
JsonNode PcbEscapeCopperResult::copper_json() const {
    auto out = arr();
    for (const auto &c : copper) {
        auto n = obj({{"kind", str(c.kind)}});
        if (c.kind == "via")
            n.object_value.insert(
                n.object_value.end(),
                {{"x", num(c.x)}, {"y", num(c.y)}, {"size", num(c.size)}, {"drill", num(c.drill)}});
        else if (c.kind == "segment")
            n.object_value.insert(n.object_value.end(), {{"x1", num(c.x1)},
                                                         {"y1", num(c.y1)},
                                                         {"x2", num(c.x2)},
                                                         {"y2", num(c.y2)},
                                                         {"width", num(c.width)},
                                                         {"layer", str(c.layer)}});
        else
            throw PcbEscapeError("unknown escape copper kind " + c.kind);
        n.object_value.insert(n.object_value.end(), {{"net", num(c.net)},
                                                     {"net_name", str(c.net_name)},
                                                     {"group", str(c.group)},
                                                     {"conn", str(c.conn)},
                                                     {"role", str(c.role)}});
        out.array_value.push_back(std::move(n));
    }
    return out;
}
namespace {
std::string quote(const std::string &text) {
    std::string out = "\"";
    const char *hex = "0123456789abcdef";
    auto escaped = [&](unsigned c) {
        out += "\\u";
        for (int k = 12; k >= 0; k -= 4)
            out += hex[(c >> k) & 15];
    };
    for (std::size_t i = 0; i < text.size();) {
        unsigned c = static_cast<unsigned char>(text[i++]);
        if (c >= 128) {
            unsigned count = (c & 0xe0) == 0xc0   ? 1
                             : (c & 0xf0) == 0xe0 ? 2
                             : (c & 0xf8) == 0xf0 ? 3
                                                  : 4;
            if (count == 4 || i + count > text.size())
                throw PcbEscapeError("invalid UTF-8 in escape report");
            c &= (1u << (6 - count)) - 1;
            for (unsigned k = 0; k < count; ++k) {
                unsigned v = static_cast<unsigned char>(text[i++]);
                if ((v & 0xc0) != 0x80)
                    throw PcbEscapeError("invalid UTF-8 in escape report");
                c = (c << 6) | (v & 63);
            }
            if (c <= 0xffff)
                escaped(c);
            else {
                c -= 0x10000;
                escaped(0xd800 + (c >> 10));
                escaped(0xdc00 + (c & 1023));
            }
        } else if (c == '"' || c == '\\') {
            out += '\\';
            out += static_cast<char>(c);
        } else if (c == '\b')
            out += "\\b";
        else if (c == '\f')
            out += "\\f";
        else if (c == '\n')
            out += "\\n";
        else if (c == '\r')
            out += "\\r";
        else if (c == '\t')
            out += "\\t";
        else if (c < 32 || c == 127)
            escaped(c);
        else
            out += static_cast<char>(c);
    }
    return out + '"';
}
std::string dump(const JsonNode &n, std::size_t indent = 0, const std::string &key = "",
                 bool counts = false) {
    if (n.kind == JsonKind::Null)
        return "null";
    if (n.kind == JsonKind::String)
        return quote(n.string_value);
    if (n.kind == JsonKind::Bool)
        return n.bool_value ? "true" : "false";
    if (n.kind == JsonKind::Number) {
        if (!std::isfinite(n.number_value))
            throw PcbEscapeError("nonfinite escape report number");
        if (counts || key == "row" || key == "lane" || key == "delta_lane")
            return f(n.number_value, 0);
        return pyfloat(n.number_value);
    }
    const bool object = n.kind == JsonKind::Object;
    if (!object && n.kind != JsonKind::Array)
        throw PcbEscapeError("unexpected escape JSON node");
    std::vector<std::pair<std::string, const JsonNode *>> children;
    if (object) {
        for (const auto &p : n.object_value)
            children.emplace_back(p.first, &p.second);
        std::stable_sort(children.begin(), children.end(),
                         [](auto a, auto b) { return a.first < b.first; });
    } else
        for (const auto &a : n.array_value)
            children.emplace_back("", &a);
    std::string out = object ? "{" : "[";
    if (!children.empty()) {
        out += '\n';
        for (std::size_t i = 0; i < children.size(); ++i) {
            out += std::string(indent + 1, ' ');
            if (object)
                out += quote(children[i].first) + ": ";
            out += dump(*children[i].second, indent + 1, children[i].first,
                        key == "netted_counts" || key == "vias");
            out += i + 1 == children.size() ? "\n" : ",\n";
        }
        out += std::string(indent, ' ');
    }
    return out + (object ? "}" : "]");
}
} // namespace
std::string render_pcb_escape_block(const PcbEscapePlanResult &plan,
                                    const PcbEscapeMetadata &meta) {
    auto p = plan.json(), all = meta.json(), subset = obj();
    for (const auto &key : {"worst_cover_mm", "vias", "coverage_mm", "escape_region", "plane",
                            "coexistence", "som_interface_sha256", "constants"})
        subset.object_value.emplace_back(key, required(all, key));
    p.object_value.emplace_back("escape_meta", std::move(subset));
    return dump(p) + "\n";
}
} // namespace schgen
