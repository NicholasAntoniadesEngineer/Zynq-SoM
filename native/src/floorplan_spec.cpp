#include "floorplan_internal.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <locale>
#include <sstream>

namespace schgen::floorplan_detail {

bool starts(const std::string& value, const std::string& prefix) {
    return value.compare(0, prefix.size(), prefix) == 0;
}
std::string number(double value, int precision) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    if (precision >= 0) out << std::fixed << std::setprecision(precision);
    else out << std::setprecision(6) << std::defaultfloat;
    out << value;
    return out.str();
}
std::string repr(const std::string& value) {
    std::string out = "'";
    for (char c : value) {
        if (c == '\\' || c == '\'') out += '\\';
        if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else out += c;
    }
    return out + "'";
}
JsonNode jvalue(const std::string& value) {
    JsonNode n; n.kind = JsonKind::String; n.string_value = value; return n;
}
JsonNode jvalue(const char* value) { return jvalue(std::string(value)); }
JsonNode jvalue(double value) {
    JsonNode n; n.kind = JsonKind::Number; n.number_value = value; return n;
}
JsonNode jvalue(int value) { return jvalue(static_cast<double>(value)); }
JsonNode jvalue(bool value) {
    JsonNode n; n.kind = JsonKind::Bool; n.bool_value = value; return n;
}
JsonNode jobject(std::vector<std::pair<std::string, JsonNode>> fields) {
    JsonNode n; n.kind = JsonKind::Object; n.object_value = std::move(fields); return n;
}
JsonNode jarray(std::vector<JsonNode> values) {
    JsonNode n; n.kind = JsonKind::Array; n.array_value = std::move(values); return n;
}
JsonNode point_json(FloorplanPoint p) { return jarray({jvalue(p.first), jvalue(p.second)}); }
JsonNode halo_json(Halo h) { return jarray({jvalue(h.w), jvalue(h.e), jvalue(h.n), jvalue(h.s)}); }
int side_mask(const std::string& side) { return side == "bottom" ? occ_bottom : occ_top; }
bool overmold(const FloorplanBlock& b) {
    return std::any_of(b.conns.begin(), b.conns.end(), [](const auto& c) { return c.value == "HDMI-019S"; });
}
}  // namespace schgen::floorplan_detail

namespace schgen {
using namespace floorplan_detail;
namespace {
bool edge(const std::string& value) { return value == "N" || value == "E" || value == "S" || value == "W"; }
bool layer(const std::string& value) { return value == "top" || value == "bottom" || value == "either"; }
std::string str(const JsonNode* value) { return value && value->kind == JsonKind::String ? value->string_value : ""; }
bool truth(const JsonNode* n) {
    if (!n || n->kind == JsonKind::Null) return false;
    if (n->kind == JsonKind::Bool) return n->bool_value;
    if (n->kind == JsonKind::Number) return n->number_value != 0;
    if (n->kind == JsonKind::String) return !n->string_value.empty();
    return n->kind == JsonKind::Array ? !n->array_value.empty() : !n->object_value.empty();
}
double numeric(const JsonNode* n, const std::string& error) {
    if (!n) throw FloorplanSpecError(error);
    double value;
    if (n->kind == JsonKind::Number) value = n->number_value;
    else if (n->kind == JsonKind::Bool) value = n->bool_value ? 1 : 0;
    else if (n->kind == JsonKind::String) {
        std::size_t consumed = 0;
        try { value = std::stod(n->string_value, &consumed); }
        catch (const std::exception&) { throw FloorplanSpecError(error); }
        if (n->string_value.find_first_not_of(" \t\r\n", consumed) != std::string::npos)
            throw FloorplanSpecError(error);
    } else throw FloorplanSpecError(error);
    if (!std::isfinite(value)) throw FloorplanSpecError(error + " (finite values required)");
    return value;
}
std::string string_list(std::vector<std::string> values) {
    std::sort(values.begin(), values.end());
    std::string s = "[";
    for (const auto& value : values) { if (s.size() > 1) s += ", "; s += repr(value); }
    return s + "]";
}
JsonNode strings(const std::vector<std::string>& values) {
    std::vector<JsonNode> a;
    for (const auto& value : values) a.push_back(jvalue(value));
    return jarray(std::move(a));
}
JsonNode pull_json(const FloorplanPull& pull) {
    auto n = jobject({{"to", jvalue(pull.to)}, {"weight", jvalue(pull.weight)}});
    if (pull.face_present) n.object_value.emplace_back("face", jvalue(pull.face));
    if (pull.exclusive_present) n.object_value.emplace_back("exclusive", jvalue(pull.exclusive));
    n.object_value.emplace_back("basis", jvalue(pull.basis));
    return n;
}
}  // namespace

std::string FloorplanTerm::target() const { return target_raw.substr(0, target_raw.find('.')); }
std::map<std::string, std::string> FloorplanSpec::edge_of() const {
    std::map<std::string, std::string> out;
    for (const auto& [e, ns] : edges) for (const auto& n : ns) out[n] = e;
    return out;
}
std::map<std::string, int> FloorplanSpec::edge_order() const {
    std::map<std::string, int> out;
    for (const auto& [e, ns] : ordered_edges) {
        (void)e;
        for (std::size_t i = 0; i < ns.size(); ++i) out[ns[i]] = static_cast<int>(i);
    }
    return out;
}
std::map<std::string, std::string> FloorplanSpec::layer_of() const {
    std::map<std::string, std::string> out;
    for (const auto& [n, a] : interior) {
        if (a.side && layer(*a.side)) out[n] = *a.side;
        if (a.layer) out[n] = *a.layer;
    }
    return out;
}
std::set<std::string> FloorplanSpec::names() const {
    std::set<std::string> out;
    for (const auto& [n, e] : edge_of()) { (void)e; out.insert(n); }
    for (const auto& [n, a] : interior) { (void)a; out.insert(n); }
    return out;
}

FloorplanSpec floorplan_spec_from_json(const JsonNode& raw, const std::string& source,
                                      const std::optional<std::set<std::string>>& valid) {
    const std::string prefix = std::filesystem::path(source).filename().string() + ": ";
    auto fail = [&](const std::string& message) { throw FloorplanSpecError(prefix + message); };
    if (raw.kind != JsonKind::Object) fail("top level must be a JSON object");
    FloorplanSpec spec;
    spec.source = source;
    if (const auto* o = object_field(raw, "outline"); o && str(o) != "auto") {
        if (o->kind != JsonKind::Object || !object_field(*o, "w") || !object_field(*o, "h"))
            fail("outline must be \"auto\" or {\"w\":<mm>,\"h\":<mm>}");
        const auto error = prefix + "outline w/h must be numbers";
        const double w = numeric(object_field(*o, "w"), error), h = numeric(object_field(*o, "h"), error);
        if (w <= 0 || h <= 0) fail("outline w/h must be > 0");
        spec.outline = {w, h};
    }
    std::map<std::string, std::string> seen;
    if (const auto* e = object_field(raw, "edges")) {
        if (e->kind != JsonKind::Object) fail("edges must be an object");
        auto entries = e->object_value;
        std::sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        for (const auto& [key, names] : entries) {
            const auto where = "edges[" + repr(key) + "]";
            if (!edge(key)) fail(where + " — illegal edge (must be one of N/E/S/W)");
            if (names.kind != JsonKind::Array) fail(where + " must be a list of subsystem names");
            for (const auto& n : names.array_value) {
                if (n.kind != JsonKind::String) fail(where + " entries must be strings");
                const auto& name = n.string_value;
                if (valid && !valid->count(name)) fail(where + " names unknown subsystem " + repr(name));
                if (seen.count(name)) fail("subsystem " + repr(name) + " placed twice (" + seen.at(name) + " and " + where + ")");
                seen[name] = where;
                spec.edges[key].push_back(name);
            }
            spec.edges.try_emplace(key);
        }
    }
    if (const auto* interior = object_field(raw, "interior")) {
        if (interior->kind != JsonKind::Object) fail("interior must be an object");
        auto entries = interior->object_value;
        std::sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        for (const auto& [name, a] : entries) {
            const auto where = "interior[" + repr(name) + "]";
            if (valid && !valid->count(name)) fail("interior names unknown subsystem " + repr(name));
            if (seen.count(name)) fail("subsystem " + repr(name) + " placed twice (" + seen.at(name) + " and interior)");
            if (a.kind != JsonKind::Object) fail(where + " must be an object (\"side\" or \"near\")");
            std::vector<std::string> keys;
            bool unknown = false;
            for (const auto& [k, v] : a.object_value) {
                (void)v; keys.push_back(k);
                unknown |= k != "side" && k != "near" && k != "pull" && k != "layer";
            }
            if (unknown) fail(where + " only \"side\", \"near\", \"pull\" or \"layer\" are allowed (got " + string_list(keys) + ")");
            FloorplanAnchor anchor;
            if (const auto* v = object_field(a, "side")) {
                if (!edge(str(v)) && !layer(str(v))) fail(where + ".side must be N/E/S/W (zone anchor) or top/bottom/either (copper-face eligibility, bottom-side P1)");
                anchor.side = str(v);
            }
            if (const auto* v = object_field(a, "layer")) {
                if (!layer(str(v))) fail(where + ".layer must be top/bottom/either (copper-face eligibility; use \"side\" for the N/E/S/W zone anchor)");
                anchor.layer = str(v);
                if (anchor.side && layer(*anchor.side)) fail(where + " declares the copper face twice (side=" + repr(*anchor.side) + " and layer=" + repr(*anchor.layer) + ") — keep exactly one");
            }
            if (const auto* v = object_field(a, "near")) {
                if (v->kind != JsonKind::String) fail(where + ".near must be a subsystem name");
                if (valid && !valid->count(str(v))) fail(where + ".near references unknown subsystem " + repr(str(v)));
                anchor.near = str(v);
            }
            if (const auto* p = object_field(a, "pull")) {
                const auto pwhere = where + ".pull";
                if (p->kind != JsonKind::Object) fail(pwhere + " must be an object");
                std::vector<std::string> extra;
                for (const auto& [k, v] : p->object_value) {
                    (void)v;
                    if (k != "to" && k != "weight" && k != "face" && k != "exclusive" && k != "basis") extra.push_back(k);
                }
                if (!extra.empty()) fail(pwhere + " unknown key(s) " + string_list(extra) + " (allowed: ['basis', 'exclusive', 'face', 'to', 'weight'])");
                for (const auto* k : {"to", "weight", "basis"})
                    if (!object_field(*p, k)) fail(pwhere + " requires " + repr(k) + " (weight/basis make the seat auditable)");
                FloorplanPull pull;
                const auto* to = object_field(*p, "to");
                if (to->kind != JsonKind::String || (valid && !valid->count(str(to))))
                    fail(pwhere + ".to references unknown subsystem " + repr(str(to)));
                pull.to = str(to);
                pull.weight = numeric(object_field(*p, "weight"), prefix + pwhere + ".weight must be a number");
                if (pull.weight <= 0) fail(pwhere + ".weight must be > 0 (got " + number(pull.weight) + ")");
                if (const auto* face = object_field(*p, "face")) {
                    pull.face_present = true; pull.face = str(face);
                    if (pull.face != "center" && pull.face != "inboard") fail(pwhere + ".face must be \"inboard\" or \"center\" (got " + repr(pull.face) + ")");
                }
                pull.basis = str(object_field(*p, "basis"));
                if (pull.basis.find_first_not_of(" \t\n\r") == std::string::npos)
                    fail(pwhere + ".basis must be a non-empty string (LAW 7: every seat carries its why)");
                const bool edge_target = spec.edge_of().count(pull.to) != 0;
                if (pull.face == "inboard" && !edge_target) fail(pwhere + ".face=\"inboard\" requires pull.to " + repr(pull.to) + " to be on an edge list (an interior block has no inboard face)");
                pull.exclusive_present = object_field(*p, "exclusive") != nullptr;
                pull.exclusive = truth(object_field(*p, "exclusive"));
                if (pull.exclusive && (!anchor.near || *anchor.near != pull.to || !edge_target))
                    fail(pwhere + ".exclusive requires the entry's \"near\" anchor to be pull.to (" + repr(pull.to) + ") AND " + repr(pull.to) + " to be an edge block — the packer's edge-seat branch fires only on that anchor, so a mismatched exclusive pull would silently do nothing");
                anchor.pull = std::move(pull);
            }
            seen[name] = "interior";
            spec.interior.emplace(name, std::move(anchor));
        }
    }
    if (const auto* order = object_field(raw, "edge_order"); truth(order)) {
        if (order->kind != JsonKind::Object) fail("edge_order must be an object");
        for (const auto& [e, names] : order->object_value) {
            const auto where = "edge_order[" + repr(e) + "]";
            if (!spec.edges.count(e)) fail(where + " — edge not in 'edges'");
            const auto error = where + " must list only members of edges[" + repr(e) + "]";
            auto invalid = [&] { fail(error); };
            if (names.kind != JsonKind::Array) invalid();
            const auto& members = spec.edges.at(e);
            for (const auto& n : names.array_value) {
                if (n.kind != JsonKind::String || std::find(members.begin(), members.end(), str(&n)) == members.end()) invalid();
                spec.ordered_edges[e].push_back(n.string_value);
            }
            spec.ordered_edges.try_emplace(e);
        }
    }
    return spec;
}

std::optional<FloorplanSpec> load_floorplan_spec(const std::string& path,
                            const std::optional<std::set<std::string>>& valid) {
    if (!std::filesystem::exists(path)) return std::nullopt;
    JsonNode raw;
    try { raw = parse_json_file(path); }
    catch (const std::exception& e) {
        throw FloorplanSpecError(std::filesystem::path(path).filename().string() + ": invalid JSON — " + e.what());
    }
    return floorplan_spec_from_json(raw, path, valid);
}

JsonNode export_floorplan_spec(const FloorplanPlan& plan) {
    JsonNode edges = jobject({}), interior = jobject({});
    for (const std::string e : {"N", "E", "S", "W"}) {
        std::vector<const FloorplanBlock*> blocks;
        for (const auto& b : plan.edge_blocks) if (b.edge == e) blocks.push_back(&b);
        std::sort(blocks.begin(), blocks.end(), [&](const auto* a, const auto* b) {
            return std::make_pair(e == "N" || e == "S" ? a->x : a->y, a->name) <
                   std::make_pair(e == "N" || e == "S" ? b->x : b->y, b->name);
        });
        std::vector<std::string> names;
        for (const auto* b : blocks) names.push_back(b->name);
        if (!names.empty()) edges.object_value.emplace_back(e, strings(names));
    }
    std::map<std::string, const FloorplanBlock*> by_name;
    for (const auto& b : plan.interior_blocks) by_name.emplace(b.name, &b);
    for (const auto& [name, b] : by_name) {
        auto a = starts(b->zone, "@") ? jobject({{"near", jvalue(b->zone.substr(1))}})
            : jobject({{"side", jvalue(edge(b->zone) ? b->zone : "E")}});
        if (b->layer_pref != "top") a.object_value.emplace_back("layer", jvalue(b->layer_pref));
        if (b->pull) a.object_value.emplace_back("pull", pull_json(*b->pull));
        interior.object_value.emplace_back(name, std::move(a));
    }
    return jobject({{"outline", jvalue("auto")}, {"_comment", jvalue(
        "DECLARATIVE carrier floorplan - edit this to drive the PCB placement. Each edge list = MEMBERSHIP; along-edge order derives from J-affinity unless an optional top-level edge_order key pins it. interior: {\"side\":N/E/S/W} or {\"near\":<subsystem>}. Any subsystem omitted falls back to auto-derivation. Regenerate this seed with `schgen floorplan --export`.")},
        {"edges", std::move(edges)}, {"interior", std::move(interior)}});
}
}  // namespace schgen
